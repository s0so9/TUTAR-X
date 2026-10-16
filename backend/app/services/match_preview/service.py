"""Match preview service: database history + FotMob live centre -> MatchPreviewResponse.

Sources and provenance
  * results, goals, xG: production database (read only), FotMob data (``matches.home_xg`` ...);
  * newer matches the database does not have yet: FotMob team page
    (``/api/data/teams?id=``, fixtures) through the paced FotMob client, marked
    ``source = "fotmob_team_fixtures"`` (goals only, no xG). Fetched only when the database
    may lag (see ``needs_fotmob_check``); when FotMob cannot confirm a possibly stale
    history, the side is flagged ``history_verified = false`` and no history-based
    sentence is written for it;
  * absentees, line-up type, formation, today's starters: the live match centre
    (``get_live_center_service().get``), which is cached and paced;
  * the previous match's starting XI: the local raw FotMob archive
    (``data/raw_cache/fotmob_match_details``) when it has the match, else the live match
    centre service (FotMob matchDetails, cached 1 h once finished).

The whole response is cached for ``CACHE_SECONDS`` and concurrent callers share one build.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from app.services.live_center.constants import ERROR_MESSAGES_TR
from app.services.live_center.parsers import LiveCenterPayloadError, parse_match_details
from app.services.live_center.schemas import LiveCenterResponse, TeamLineup
from app.services.live_center.service import LiveCenterError, get_live_center_service
from app.services.match_preview.highlights import build_highlights
from app.services.match_preview.history import (
    WINDOW_SIZE,
    FixturesPayloadError,
    as_utc,
    build_rest,
    build_window,
    database_latest_match,
    load_database_history,
    merge_history,
    parse_team_fixtures,
    previous_competitive_match,
    usable_fotmob_match_id,
)
from app.services.match_preview.rotation import compute_rotation, rotation_problem
from app.services.match_preview.schemas import (
    Absentee,
    AbsenteesInfo,
    LineupInfo,
    MatchPreviewResponse,
    PlayerRef,
    PreviewMatch,
    PreviewSide,
    RestInfo,
    RotationInfo,
)
from app.services.team_news.fotmob_client import FotMobError, TeamNewsFotMobClient

logger = logging.getLogger(__name__)

CACHE_SECONDS = 300
CACHE_MAX_ENTRIES = 256
DB_FRESH_HOURS = 12  # newest finished match of the whole database within this of "now" = up to date
QUIET_DAYS = 10  # a team whose newest local match is older than this is checked at FotMob
FOTMOB_STEP_TIMEOUT_SECONDS = 25.0
TEAM_PAGE_TTL_SECONDS = 600.0
HORIZON_CACHE_SECONDS = 60.0  # newest finished match of the database: one max() query per minute is enough

RAW_MATCH_DETAILS_DIR = Path(__file__).resolve().parents[3] / "data" / "raw_cache" / "fotmob_match_details"


class MatchPreviewError(Exception):
    """``code`` is a key of ERROR_MESSAGES_TR (or PREVIEW_ERRORS_TR)."""

    def __init__(self, code: str, status_code: int, detail: str = ""):
        super().__init__(detail or code)
        self.code = code
        self.status_code = status_code


PREVIEW_ERRORS_TR = {
    "teams_unknown": "Takım kimlikleri alınamadı.",
}


def error_message_tr(code: str) -> str:
    return PREVIEW_ERRORS_TR.get(code) or ERROR_MESSAGES_TR.get(code, code)


def _fmt_date(value: Optional[datetime]) -> str:
    return as_utc(value).strftime("%d.%m.%Y") if value else "bilinmiyor"


# ----------------------------------------------------------------------------- internal records


class _SideState:
    """Everything known about one team while the preview is built."""

    def __init__(self, side: str, team_id: str, team_name: Optional[str], lineup: TeamLineup):
        self.side = side
        self.team_id = team_id
        self.team_name = team_name
        self.lineup = lineup
        self.database: list[PreviewMatch] = []
        self.gap_fill: list[PreviewMatch] = []
        self.history: list[PreviewMatch] = []
        self.verified = True
        self.notes: list[str] = []
        self.unverified_reason: Optional[str] = None
        self.checked_fotmob = False
        self.previous: Optional[PreviewMatch] = None
        self.previous_xi: Optional[list[PlayerRef]] = None
        self.previous_xi_source: Optional[str] = None
        self.previous_xi_reason: Optional[str] = None


# ----------------------------------------------------------------------------- service


class MatchPreviewService:
    def __init__(
        self,
        live_center: Any = None,
        fotmob_client: Any = None,
        raw_details_dir: Optional[Path] = None,
        now: Optional[Callable[[], datetime]] = None,
        clock: Callable[[], float] = time.monotonic,
        cache_seconds: float = CACHE_SECONDS,
    ):
        self._live_center = live_center
        self._fotmob_client = fotmob_client
        self._raw_dir = Path(raw_details_dir) if raw_details_dir is not None else RAW_MATCH_DETAILS_DIR
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._clock = clock
        self._cache_seconds = cache_seconds
        self._cache: dict[str, tuple[float, MatchPreviewResponse]] = {}
        self._inflight: dict[str, asyncio.Future] = {}
        self._horizon_cache: Optional[tuple[float, Optional[datetime]]] = None

    def _database_horizon(self, db: Any) -> Optional[datetime]:
        cached = self._horizon_cache
        if cached is not None and cached[0] > self._clock():
            return cached[1]
        value = database_latest_match(db)
        self._horizon_cache = (self._clock() + HORIZON_CACHE_SECONDS, value)
        return value

    # --- collaborators (resolved late so tests can swap the live-centre singleton)

    def _centre_service(self) -> Any:
        return self._live_center if self._live_center is not None else get_live_center_service()

    def _client(self) -> Any:
        if self._fotmob_client is None:
            self._fotmob_client = TeamNewsFotMobClient()
        return self._fotmob_client

    # --- cache / coalescing

    async def get(self, match_id: str, db: Any) -> MatchPreviewResponse:
        cached = self._cache.get(match_id)
        if cached is not None and cached[0] > self._clock():
            return cached[1]
        pending = self._inflight.get(match_id)
        if pending is not None:
            return await asyncio.shield(pending)
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._inflight[match_id] = fut
        try:
            result = await self._build(match_id, db)
        except BaseException as exc:
            if not fut.done():
                fut.set_exception(exc)
                fut.exception()  # mark retrieved: waiters re-raise it
            raise
        else:
            if not fut.done():
                fut.set_result(result)
            self._cache[match_id] = (self._clock() + self._cache_seconds, result)
            if len(self._cache) > CACHE_MAX_ENTRIES:
                now = self._clock()
                for key in [k for k, (exp, _) in self._cache.items() if exp <= now]:
                    self._cache.pop(key, None)
            return result
        finally:
            self._inflight.pop(match_id, None)

    # --- build

    async def _build(self, match_id: str, db: Any) -> MatchPreviewResponse:
        centre: LiveCenterResponse = await self._centre_service().get(match_id, db)
        home_id, away_id = centre.teams.home.id, centre.teams.away.id
        if not home_id or not away_id:
            raise MatchPreviewError("teams_unknown", 503)
        now = self._now()
        notes: list[str] = []
        kickoff = centre.kickoff
        if kickoff is None:
            kickoff = now
            notes.append("Maç saati kaynakta yok; geçmiş maçlar şu ana kadar olanlarla sınırlandı.")
        kickoff = as_utc(kickoff)

        home = _SideState("home", home_id, centre.teams.home.name, centre.lineups.home)
        away = _SideState("away", away_id, centre.teams.away.name, centre.lineups.away)
        sides = (home, away)

        # 1) database history
        horizon = self._database_horizon(db)
        reference = min(now, kickoff)
        db_fresh = horizon is not None and reference - horizon <= timedelta(hours=DB_FRESH_HOURS)
        for s in sides:
            s.database = load_database_history(db, s.team_id, kickoff)
            s.history = list(s.database)

        # 2) FotMob team fixtures where the database may lag
        checks = [s for s in sides if self._needs_fotmob_check(s, db_fresh, reference)]
        if checks:
            results = await asyncio.gather(
                *(self._fetch_gap_fill(s, kickoff) for s in checks), return_exceptions=True
            )
            for s, res in zip(checks, results):
                s.checked_fotmob = True
                if isinstance(res, BaseException):
                    self._mark_check_failed(s, res, horizon, db_fresh, reference)
                else:
                    s.gap_fill = res
                    s.history = merge_history(s.database, res)
                    if res:
                        s.notes.append(
                            f"{len(res)} maç yerel veritabanında yoktu; FotMob takım sayfasından eklendi (xG yok)."
                        )
                        if horizon is not None and not db_fresh:
                            s.notes.append(f"Yerel veritabanı en son {_fmt_date(horizon)} maçlarına kadar.")

        # 3) previous match XI (rotation and the "started last match" flag of absentees)
        for s in sides:
            s.previous = previous_competitive_match(s.history, kickoff)
        xi_results = await asyncio.gather(
            *(self._load_previous_xi(s, db) for s in sides if self._needs_previous_xi(s)), return_exceptions=True
        )
        for res in xi_results:
            if isinstance(res, BaseException):  # one side's XI must never fail the whole preview
                logger.error("match-preview: previous XI step failed", exc_info=res)

        home_side = self._side_response(home, kickoff)
        away_side = self._side_response(away, kickoff)
        highlights = build_highlights(home_side, away_side)

        sources = [
            "Maç sonuçları ve xG: yerel veritabanı (FotMob verisi).",
            "Eksikler, kadro türü ve ilk 11: FotMob maç merkezi.",
        ]
        if any(s.previous_xi_source == "local_raw_cache" for s in sides):
            sources.append("Önceki maçın ilk 11'i: yerel FotMob arşivi.")
        if any(s.previous_xi_source == "fotmob_match_details" for s in sides):
            sources.append("Önceki maçın ilk 11'i: FotMob maç detayı.")
        if any(s.gap_fill for s in sides):
            sources.append("Yerel veritabanında olmayan son maçlar: FotMob takım sayfası (yalnızca skor).")
        return MatchPreviewResponse(
            match_id=centre.match_id,
            provider_match_id=centre.provider_match_id,
            generated_at=now,
            kickoff=centre.kickoff,
            status=centre.status,
            competition=centre.competition,
            home=home_side,
            away=away_side,
            highlights=highlights,
            database_latest_match_at=horizon,
            sources=sources,
            notes=notes,
        )

    # --- gap fill

    @staticmethod
    def _needs_fotmob_check(side: _SideState, db_fresh: bool, reference: datetime) -> bool:
        competitive = [m for m in side.database if not m.is_friendly]
        newest = side.database[0].date if side.database else None
        quiet = newest is None or reference - newest > timedelta(days=QUIET_DAYS)
        thin = len(competitive) < WINDOW_SIZE
        return (not db_fresh) or quiet or thin

    async def _fetch_gap_fill(self, side: _SideState, kickoff: datetime) -> list[PreviewMatch]:
        res = await asyncio.wait_for(
            self._client().team(side.team_id, ttl_seconds=TEAM_PAGE_TTL_SECONDS), FOTMOB_STEP_TIMEOUT_SECONDS
        )
        newest_local = side.database[0].date if side.database else None
        known = {m.match_id for m in side.database if m.match_id}
        return parse_team_fixtures(res.data, side.team_id, before=kickoff, after=newest_local, known_match_ids=known)

    @staticmethod
    def _mark_check_failed(
        side: _SideState, exc: BaseException, horizon: Optional[datetime], db_fresh: bool, reference: datetime
    ) -> None:
        if isinstance(exc, asyncio.TimeoutError):
            why = "FotMob zaman aşımı"
        elif isinstance(exc, FotMobError):
            why = "FotMob yanıt vermedi"
        elif isinstance(exc, FixturesPayloadError):
            why = "FotMob takım sayfası beklenen biçimde değil"
        else:
            logger.exception("match-preview: team fixtures for %s failed", side.team_id, exc_info=exc)
            why = "beklenmeyen hata"
        newest = side.database[0].date if side.database else None
        quiet = newest is None or reference - newest > timedelta(days=QUIET_DAYS)
        if db_fresh and not quiet:
            # the database is current and the team has recent matches: nothing suggests a gap
            side.notes.append(f"FotMob ile doğrulama yapılamadı ({why}); yerel veritabanı güncel görünüyor.")
            return
        side.verified = False
        side.unverified_reason = (
            f"Yerel veritabanı en son {_fmt_date(horizon)} maçlarına kadar; {side.team_name or 'takım'} için "
            f"sonraki maçlar eksik olabilir ve FotMob'dan doğrulanamadı ({why})."
        )
        side.notes.append(side.unverified_reason)

    # --- previous XI

    @staticmethod
    def _needs_previous_xi(side: _SideState) -> bool:
        if side.previous is None:
            return False
        lineup_type = side.lineup.lineup_type
        rotation_wanted = bool(side.lineup.starters) and lineup_type in ("confirmed", "predicted")
        absentees_wanted = any((p.reason_code or "").lower() != "doubtful" for p in side.lineup.unavailable)
        return rotation_wanted or absentees_wanted

    async def _load_previous_xi(self, side: _SideState, db: Any) -> None:
        previous = side.previous
        assert previous is not None
        fotmob_id = usable_fotmob_match_id(previous)
        if fotmob_id is None:
            side.previous_xi_reason = "Önceki maçın FotMob kimliği yok."
            return
        centre = await asyncio.to_thread(self._read_raw_details, fotmob_id)
        source = "local_raw_cache"
        if centre is None:
            source = "fotmob_match_details"
            try:
                centre = await asyncio.wait_for(
                    self._centre_service().get(f"fotmob_{fotmob_id}", db), FOTMOB_STEP_TIMEOUT_SECONDS
                )
            except LiveCenterError as exc:
                side.previous_xi_reason = f"Önceki maçın ilk 11'i alınamadı: {ERROR_MESSAGES_TR.get(exc.code, exc.code)}"
                return
            except asyncio.TimeoutError:
                side.previous_xi_reason = "Önceki maçın ilk 11'i alınamadı: FotMob zaman aşımı."
                return
            except Exception:  # noqa: BLE001 - a preview must not fail because of one side detail
                logger.exception("match-preview: previous XI of %s failed", fotmob_id)
                side.previous_xi_reason = "Önceki maçın ilk 11'i alınamadı."
                return
        if centre.status != "FINISHED":
            side.previous_xi_reason = "Önceki maç henüz bitmemiş görünüyor; ilk 11 karşılaştırması yapılmadı."
            return
        if centre.teams.home.id == side.team_id:
            lineup = centre.lineups.home
        elif centre.teams.away.id == side.team_id:
            lineup = centre.lineups.away
        else:
            side.previous_xi_reason = "Önceki maç verisinde takım bulunamadı."
            return
        if not lineup.starters:
            side.previous_xi_reason = "Önceki maçın ilk 11'i kaynakta yok."
            return
        side.previous_xi = [PlayerRef(id=p.id, name=p.name) for p in lineup.starters]
        side.previous_xi_source = source

    def _read_raw_details(self, fotmob_id: str) -> Optional[LiveCenterResponse]:
        """Previous match from the local raw FotMob archive; None when absent or unusable."""
        path = self._raw_dir / f"{fotmob_id}.json.gz"
        try:
            if not path.is_file():
                return None
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                data = json.load(fh)
            return parse_match_details(
                data, match_id=f"fotmob_{fotmob_id}", provider_match_id=fotmob_id, fetched_at=datetime.now(timezone.utc)
            )
        except (OSError, ValueError, LiveCenterPayloadError):
            logger.warning("match-preview: local raw match details %s unusable", path, exc_info=True)
            return None

    # --- per-side response

    def _side_response(self, s: _SideState, kickoff: datetime) -> PreviewSide:
        venue = "home" if s.side == "home" else "away"
        last5 = build_window(s.history, scope="last5")
        venue_last5 = build_window(s.history, scope="last5_venue", venue=venue)
        rest = build_rest(s.history, kickoff)
        if not s.verified:
            rest = RestInfo(missing_reason=s.unverified_reason)
            for window in (last5, venue_last5):
                window.missing_reason = s.unverified_reason
        started_ids = {p.id for p in (s.previous_xi or []) if p.id}
        absentees = self._absentees(s, started_ids if s.previous_xi is not None else None)
        lineup = self._lineup(s)
        return PreviewSide(
            team_id=s.team_id,
            team_name=s.team_name,
            last5=last5,
            venue_last5=venue_last5,
            rest=rest,
            absentees=absentees,
            lineup=lineup,
            history_verified=s.verified,
            data_notes=s.notes,
        )

    @staticmethod
    def _absentees(s: _SideState, started_ids: Optional[set[str]]) -> AbsenteesInfo:
        lineup = s.lineup
        if not lineup.unavailable and not lineup.starters and not lineup.substitutes:
            return AbsenteesInfo(
                available=False, missing_reason="FotMob bu maç için kadro ve eksik oyuncu verisi göndermedi."
            )
        players = [
            Absentee(
                id=p.id,
                name=p.name,
                reason=p.reason,
                reason_code=p.reason_code,
                expected_return=p.expected_return,
                expected_return_date=p.expected_return_date,
                started_previous_match=(p.id in started_ids) if (started_ids is not None and p.id) else None,
            )
            for p in lineup.unavailable
        ]
        return AbsenteesInfo(available=True, players=players)

    def _lineup(self, s: _SideState) -> LineupInfo:
        lu = s.lineup
        today = [PlayerRef(id=p.id, name=p.name) for p in lu.starters]
        rotation = RotationInfo(previous_match=s.previous)
        info = LineupInfo(lineup_type=lu.lineup_type, formation=lu.formation, starters_count=len(today), rotation=rotation)
        if not today:
            info.missing_reason = "Kadro henüz açıklanmadı."
            rotation.missing_reason = info.missing_reason
            return info
        if lu.lineup_type == "last_starting11":
            info.missing_reason = "FotMob henüz kadro vermedi; son maçın ilk 11'i gösteriliyor."
            rotation.missing_reason = "Kadro henüz açıklanmadı (FotMob son maçın ilk 11'ini gösteriyor); değişiklik sayısı hesaplanamadı."
            return info
        if lu.lineup_type not in ("confirmed", "predicted"):
            rotation.missing_reason = "Kadro türü bilinmiyor; değişiklik sayısı hesaplanamadı."
            return info
        if s.previous is None:
            rotation.missing_reason = "Önceki maç kaydı bulunamadı."
            return info
        if s.previous_xi is None:
            rotation.missing_reason = s.previous_xi_reason or "Önceki maçın ilk 11'i alınamadı."
            return info
        problem = rotation_problem(today, s.previous_xi)
        if problem:
            rotation.missing_reason = problem
            return info
        changes, came_in, dropped_out = compute_rotation(today, s.previous_xi)
        rotation.changes = changes
        rotation.came_in = came_in
        rotation.dropped_out = dropped_out
        rotation.previous_xi_source = s.previous_xi_source  # type: ignore[assignment]
        return info


_service: Optional[MatchPreviewService] = None


def get_match_preview_service() -> MatchPreviewService:
    global _service
    if _service is None:
        _service = MatchPreviewService()
    return _service
