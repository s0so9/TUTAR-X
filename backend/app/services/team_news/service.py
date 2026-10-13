"""Team-news services: ingestion of FotMob bodies and the live refresh jobs.

Two layers:

* ``apply_*`` functions (sync, DB only): parse one raw body and write it via
  ``TeamNewsStore``. The live refresh and the offline backfill
  (scripts/live/load_player_data.py) share them, so a raw file and a live
  response are ingested identically.
* ``TeamNewsService`` (async): fetches from FotMob through
  ``TeamNewsFotMobClient`` and runs the DB work in a worker thread (one
  session per unit of work), so the API event loop is never blocked.

Module-level coroutines ``refresh_team_squads``, ``refresh_match_team_news``
and ``ingest_finished_match`` are thin wrappers around the service.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Competition, Match, Team, TeamNewsMatch
from app.domain.enums import MatchStatus
from app.services.team_news.constants import (
    BASIS_MATCH_KICKOFF,
    BASIS_OBSERVED,
    SOURCE_MATCH_DETAILS,
    SOURCE_MATCH_LINEUP,
    SOURCE_PLAYER_PROFILE,
    SOURCE_TEAM_SQUAD,
    TARGET13_COMPETITIONS,
)
from app.services.team_news.fotmob_client import (
    FotMobBlockedError,
    FotMobError,
    FotMobRateLimitedError,
    TeamNewsFotMobClient,
)
from app.services.team_news.parsers import (
    FixtureRef,
    PayloadError,
    parse_league_fixtures,
    parse_match_payload,
    parse_player_payload,
    parse_team_payload,
)
from app.services.team_news.raw_store import RawStore
from app.services.team_news.store import TeamNewsStore, as_utc, utc_now

logger = logging.getLogger(__name__)

# A finished match is re-fetched (player ratings/xG get corrected after the
# final whistle) until one fetch happened at least this long after kickoff.
FINISHED_SETTLE_HOURS = 6.0


def _later(a: Optional[datetime], b: Optional[datetime]) -> Optional[datetime]:
    a, b = as_utc(a), as_utc(b)
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def _prefix(prefix: str, counts: dict[str, int]) -> dict[str, int]:
    return {f"{prefix}{k}": v for k, v in counts.items()}


# =========================================================================== apply (DB only)


def apply_team_payload(store: TeamNewsStore, data: Any, observed_at: datetime) -> dict[str, Any]:
    """Squad + squad injury list of one /api/data/teams body observed at ``observed_at``."""
    parsed = parse_team_payload(data, observed_at)
    counts: dict[str, Any] = {"team_provider_id": parsed.team_provider_id, "season": parsed.season}
    if not parsed.squad_sent:
        counts["squad_sent"] = False
        return counts
    if not parsed.season:
        # team_squad_members.season is required and is never guessed
        counts["season_missing"] = True
    counts.update(_prefix("squad_", store.upsert_squad(parsed, observed_at)))
    entries = [m.availability for m in parsed.members if m.availability is not None]
    counts.update(
        _prefix(
            "availability_",
            store.apply_availability(
                source=SOURCE_TEAM_SQUAD,
                entries=entries,
                observed_at=observed_at,
                basis=BASIS_OBSERVED,
                team_provider_id=parsed.team_provider_id,
            ),
        )
    )
    counts["members"] = len(parsed.members)
    counts["injured"] = len(entries)
    return counts


def apply_player_payload(store: TeamNewsStore, data: Any, observed_at: datetime) -> dict[str, Any]:
    """Profile + profile availability of one /api/data/playerData body."""
    parsed = parse_player_payload(data, observed_at)
    store.ensure_players([parsed.player])
    counts: dict[str, Any] = {"player_provider_id": parsed.player.provider_id}
    if parsed.availability_sent:
        counts.update(
            _prefix(
                "availability_",
                store.apply_availability(
                    source=SOURCE_PLAYER_PROFILE,
                    entries=parsed.availability,
                    observed_at=observed_at,
                    basis=BASIS_OBSERVED,
                    player_provider_id=parsed.player.provider_id,
                ),
            )
        )
    return counts


def apply_match_payload(
    store: TeamNewsStore,
    data: Any,
    fetched_at: datetime,
    *,
    ingest_stats: bool = True,
) -> dict[str, Any]:
    """Line-ups, unavailable lists, registry header and (finished) player stats.

    Timestamps: for a finished match the line-up/unavailable observations are
    stamped with the kickoff (basis ``match_kickoff``) because a post-match
    response carries the match-time lists; otherwise with the fetch time
    (basis ``observed``). Player stats always carry the fetch time.
    """
    parsed = parse_match_payload(data, fetched_at)
    finished = parsed.status == "finished"
    if finished and parsed.kickoff_at is not None:
        observed_at, basis = parsed.kickoff_at, BASIS_MATCH_KICKOFF
    else:
        observed_at, basis = fetched_at, BASIS_OBSERVED
    counts: dict[str, Any] = {
        "provider_match_id": parsed.provider_match_id,
        "status": parsed.status,
        "lineup_type": parsed.lineup_type,
    }
    match_db_id = store.match_id(parsed.provider_match_id)
    reg = store.upsert_team_news_match(
        provider_match_id=parsed.provider_match_id,
        header_source=SOURCE_MATCH_DETAILS,
        competition_provider_id=parsed.competition_provider_id,
        home_team_provider_id=parsed.home_team_provider_id,
        away_team_provider_id=parsed.away_team_provider_id,
        home_team_name=parsed.home_team_name,
        away_team_name=parsed.away_team_name,
        kickoff_at=parsed.kickoff_at,
        source_status=parsed.status,
    )
    reg.details_fetched_at = _later(reg.details_fetched_at, fetched_at)
    reg.last_error = None
    if parsed.status == "cancelled":
        return counts

    for side in parsed.sides.values():
        for obs in side.players:
            obs.observed_at = observed_at
        store.ensure_players(side.players)

    snapshots_created = 0
    for side_key, side in parsed.sides.items():
        _, created = store.record_lineup_snapshot(
            provider_match_id=parsed.provider_match_id,
            side=side,
            lineup_type=parsed.lineup_type,
            lineup_source=parsed.lineup_source,
            observed_at=observed_at,
            basis=basis,
            match_db_id=match_db_id,
        )
        snapshots_created += int(created)
        counts[f"{side_key}_lineup"] = side.has_lineup
        if side.unavailable is not None:
            res = store.apply_availability(
                source=SOURCE_MATCH_LINEUP,
                entries=side.unavailable,
                observed_at=observed_at,
                basis=basis,
                provider_match_id=parsed.provider_match_id,
                side=side_key,
                match_db_id=match_db_id,
            )
            counts.update(_prefix(f"{side_key}_unavailable_", res))
            attr = f"{side_key}_unavailable_observed_at"
            setattr(reg, attr, _later(getattr(reg, attr), observed_at))
    counts["snapshots_created"] = snapshots_created

    if ingest_stats and finished and parsed.player_stats:
        counts.update(_prefix("stats_", store.upsert_player_match_stats(parsed, fetched_at, SOURCE_MATCH_DETAILS, match_db_id)))
        reg.stats_ingested_at = _later(reg.stats_ingested_at, fetched_at)
    return counts


def relevant_match_content(data: Any) -> Any:
    """What decides whether a matchDetails body is archived again (raw_store)."""
    try:
        p = parse_match_payload(data, None)
    except PayloadError:
        return data
    return {
        "status": p.status,
        "lineup_type": p.lineup_type,
        "sides": {
            k: {
                "formation": s.formation,
                "starters": s.starters,
                "bench": s.bench,
                "unavailable": [u.report_key() + (u.player_provider_id,) for u in (s.unavailable or [])]
                if s.unavailable is not None
                else None,
            }
            for k, s in p.sides.items()
        },
        "stats": p.player_stats,
    }


def relevant_team_content(data: Any) -> Any:
    try:
        p = parse_team_payload(data, None)
    except PayloadError:
        return data
    return {
        "season": p.season,
        "members": [
            (m.player.provider_id, m.role, m.shirt_number, m.availability.report_key() if m.availability else None)
            for m in p.members
        ],
    }


def relevant_player_content(data: Any) -> Any:
    try:
        p = parse_player_payload(data, None)
    except PayloadError:
        return data
    obs = p.player
    return {
        "profile": [obs.name, obs.team_provider_id, obs.shirt_number, obs.market_value_eur, obs.contract_end],
        "availability": [a.report_key() for a in p.availability],
    }


# =========================================================================== match references


@dataclass
class MatchRef:
    provider_match_id: str
    match_db_id: Optional[str] = None
    kickoff_at: Optional[datetime] = None
    competition_provider_id: Optional[str] = None
    home_team_provider_id: Optional[str] = None
    away_team_provider_id: Optional[str] = None
    home_team_name: Optional[str] = None
    away_team_name: Optional[str] = None
    status: Optional[str] = None  # scheduled|started|finished|cancelled
    origins: list[str] = field(default_factory=list)


_DB_STATUS = {
    MatchStatus.SCHEDULED: "scheduled",
    MatchStatus.LIVE: "started",
    MatchStatus.HALF_TIME: "started",
    MatchStatus.FINISHED: "finished",
    MatchStatus.POSTPONED: "scheduled",
    MatchStatus.CANCELLED: "cancelled",
    MatchStatus.SUSPENDED: "started",
}


def split_match_identifier(value: str) -> tuple[Optional[str], Optional[str]]:
    """'fotmob_6106260' or '6106260' -> (provider id, None); other text -> (None, local id)."""
    text = (value or "").strip()
    if text.startswith("fotmob_"):
        rest = text[len("fotmob_"):]
        return (rest, None) if rest.isdigit() else (None, None)
    if text.isdigit():
        return text, None
    return None, text or None


def resolve_match_ref(session: Session, value: "MatchRef | str") -> Optional[MatchRef]:
    """Build a MatchRef from a local id / provider id, using `matches` and the registry."""
    if isinstance(value, MatchRef):
        return value
    provider_id, local_id = split_match_identifier(str(value))
    db_match = None
    if local_id is not None:
        db_match = session.get(Match, local_id)
        if db_match is None:
            return None
        provider_id = db_match.provider_id
    elif provider_id is not None:
        db_match = session.execute(select(Match).where(Match.provider_id == provider_id)).scalars().first()
    if provider_id is None:
        return None
    ref = MatchRef(provider_match_id=provider_id)
    if db_match is not None:
        ref.match_db_id = db_match.id
        ref.kickoff_at = as_utc(db_match.scheduled_at)
        ref.status = _DB_STATUS.get(db_match.status)
        ht, at = session.get(Team, db_match.home_team_id), session.get(Team, db_match.away_team_id)
        ref.home_team_provider_id = ht.provider_id if ht else None
        ref.away_team_provider_id = at.provider_id if at else None
        ref.home_team_name = ht.name if ht else None
        ref.away_team_name = at.name if at else None
        comp = session.get(Competition, db_match.competition_id) if db_match.competition_id else None
        ref.competition_provider_id = comp.provider_id if comp else None
        ref.origins.append("local_matches")
    reg = session.execute(
        select(TeamNewsMatch).where(TeamNewsMatch.provider_match_id == provider_id)
    ).scalar_one_or_none()
    if reg is not None:
        ref.kickoff_at = ref.kickoff_at or as_utc(reg.kickoff_at)
        ref.status = ref.status or reg.source_status
        ref.home_team_provider_id = ref.home_team_provider_id or reg.home_team_provider_id
        ref.away_team_provider_id = ref.away_team_provider_id or reg.away_team_provider_id
        ref.home_team_name = ref.home_team_name or reg.home_team_name
        ref.away_team_name = ref.away_team_name or reg.away_team_name
        ref.competition_provider_id = ref.competition_provider_id or reg.competition_provider_id
        ref.origins.append("team_news_matches")
    if db_match is None and reg is None:
        return None
    return ref


def db_matches_in_window(
    session: Session, start: datetime, end: datetime, competitions: Iterable[int | str]
) -> list[MatchRef]:
    comp_ids = [str(c) for c in competitions]
    rows = session.execute(
        select(Match, Competition.provider_id)
        .join(Competition, Competition.id == Match.competition_id)
        .where(Competition.provider_id.in_(comp_ids), Match.scheduled_at >= start, Match.scheduled_at <= end)
    ).all()
    team_ids = {m.home_team_id for m, _ in rows} | {m.away_team_id for m, _ in rows}
    teams = {
        t.id: t
        for t in session.execute(select(Team).where(Team.id.in_(sorted(team_ids)))).scalars()
    } if team_ids else {}
    out = []
    for m, comp_pid in rows:
        ht, at = teams.get(m.home_team_id), teams.get(m.away_team_id)
        out.append(
            MatchRef(
                provider_match_id=m.provider_id,
                match_db_id=m.id,
                kickoff_at=as_utc(m.scheduled_at),
                competition_provider_id=comp_pid,
                home_team_provider_id=ht.provider_id if ht else None,
                away_team_provider_id=at.provider_id if at else None,
                home_team_name=ht.name if ht else None,
                away_team_name=at.name if at else None,
                status=_DB_STATUS.get(m.status),
                origins=["local_matches"],
            )
        )
    return out


def _register_fixtures(store: TeamNewsStore, fixtures: list[FixtureRef]) -> int:
    for f in fixtures:
        store.upsert_team_news_match(
            provider_match_id=f.provider_match_id,
            header_source="fotmob_league_fixtures",
            competition_provider_id=f.competition_provider_id,
            home_team_provider_id=f.home_team_provider_id,
            away_team_provider_id=f.away_team_provider_id,
            home_team_name=f.home_team_name,
            away_team_name=f.away_team_name,
            kickoff_at=f.kickoff_at,
            source_status=f.status,
        )
    return len(fixtures)


def _registry_rows(session: Session, provider_ids: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for i in range(0, len(provider_ids), 500):
        chunk = provider_ids[i : i + 500]
        for r in session.execute(select(TeamNewsMatch).where(TeamNewsMatch.provider_match_id.in_(chunk))).scalars():
            out[r.provider_match_id] = {
                "details_fetched_at": as_utc(r.details_fetched_at),
                "stats_ingested_at": as_utc(r.stats_ingested_at),
            }
    return out


def _record_error(store: TeamNewsStore, provider_match_id: str, message: str) -> None:
    reg = store.upsert_team_news_match(provider_match_id=provider_match_id, header_source="error")
    reg.last_error = message[:300]


# =========================================================================== service


class TeamNewsService:
    """Async refresh jobs. One instance per process/loop; DB work in threads."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        client: TeamNewsFotMobClient,
        raw_store: Optional[RawStore] = None,
    ):
        self.session_factory = session_factory
        self.client = client
        self.raw_store = raw_store or RawStore(None)

    async def _db(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        def work() -> Any:
            with self.session_factory() as session:
                store = TeamNewsStore(session)
                try:
                    result = fn(store, *args, **kwargs)
                    session.commit()
                    return result
                except Exception:
                    session.rollback()
                    raise

        return await asyncio.to_thread(work)

    async def _read(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        def work() -> Any:
            with self.session_factory() as session:
                return fn(session, *args, **kwargs)

        return await asyncio.to_thread(work)

    # ------------------------------------------------------------------ squads

    async def refresh_team_squads(self, team_ids: Iterable[str]) -> dict[str, Any]:
        summary: dict[str, Any] = {"teams": 0, "ok": 0, "errors": 0, "members": 0, "injured": 0}
        for team_id in sorted({str(t) for t in team_ids if t}):
            summary["teams"] += 1
            try:
                res = await self.client.team(team_id)
            except (FotMobBlockedError, FotMobRateLimitedError):
                raise
            except FotMobError as exc:
                summary["errors"] += 1
                logger.warning("team-news: squad %s fetch failed: %s", team_id, exc)
                continue
            try:
                counts = await self._db(apply_team_payload, res.data, res.fetched_at)
            except PayloadError as exc:
                summary["errors"] += 1
                logger.warning("team-news: squad %s unusable: %s", team_id, exc)
                continue
            except Exception:  # one bad squad must not stop the refresh
                summary["errors"] += 1
                logger.exception("team-news: squad %s could not be stored", team_id)
                continue
            if not res.from_cache:
                self.raw_store.save("teams", team_id, res.raw, res.fetched_at, relevant_team_content(res.data))
            summary["ok"] += 1
            summary["members"] += int(counts.get("members") or 0)
            summary["injured"] += int(counts.get("injured") or 0)
        return summary

    # ------------------------------------------------------------------ matches

    async def refresh_match_team_news(self, match: "MatchRef | str") -> dict[str, Any]:
        """Pre-match matchDetails -> line-up snapshots + match unavailable lists."""
        ref = await self._to_ref(match)
        try:
            res = await self.client.match_details(ref.provider_match_id, ttl_seconds=60.0)
        except (FotMobBlockedError, FotMobRateLimitedError):
            raise
        except FotMobError as exc:
            await self._db(_record_error, ref.provider_match_id, str(exc))
            return {"provider_match_id": ref.provider_match_id, "error": str(exc)}
        counts = await self._db(apply_match_payload, res.data, res.fetched_at, ingest_stats=False)
        if not res.from_cache:
            self.raw_store.save(
                "match_details", ref.provider_match_id, res.raw, res.fetched_at, relevant_match_content(res.data)
            )
        return counts

    async def ingest_finished_match(self, match: "MatchRef | str") -> dict[str, Any]:
        """Finished matchDetails -> player_match_stats (+ final line-ups/lists)."""
        ref = await self._to_ref(match)
        try:
            res = await self.client.match_details(ref.provider_match_id, ttl_seconds=0.0)
        except (FotMobBlockedError, FotMobRateLimitedError):
            raise
        except FotMobError as exc:
            await self._db(_record_error, ref.provider_match_id, str(exc))
            return {"provider_match_id": ref.provider_match_id, "error": str(exc)}
        counts = await self._db(apply_match_payload, res.data, res.fetched_at, ingest_stats=True)
        if not res.from_cache:
            self.raw_store.save(
                "match_details", ref.provider_match_id, res.raw, res.fetched_at, relevant_match_content(res.data)
            )
        return counts

    async def refresh_player_profiles(self, player_ids: Iterable[str], max_players: int = 50) -> dict[str, Any]:
        summary: dict[str, Any] = {"players": 0, "ok": 0, "errors": 0}
        for pid in list(dict.fromkeys(str(p) for p in player_ids if p))[: max(0, max_players)]:
            summary["players"] += 1
            try:
                res = await self.client.player(pid)
                await self._db(apply_player_payload, res.data, res.fetched_at)
            except (FotMobBlockedError, FotMobRateLimitedError):
                raise
            except (FotMobError, PayloadError) as exc:
                summary["errors"] += 1
                logger.warning("team-news: player %s failed: %s", pid, exc)
                continue
            if not res.from_cache:
                self.raw_store.save("players", pid, res.raw, res.fetched_at, relevant_player_content(res.data))
            summary["ok"] += 1
        return summary

    async def _to_ref(self, match: "MatchRef | str") -> MatchRef:
        if isinstance(match, MatchRef):
            return match
        ref = await self._read(resolve_match_ref, match)
        if ref is not None:
            return ref
        provider_id, _ = split_match_identifier(str(match))
        if provider_id is None:
            raise ValueError(f"not a FotMob match id or known local match id: {match!r}")
        return MatchRef(provider_match_id=provider_id)

    # ------------------------------------------------------------------ discovery

    async def league_fixtures(self, competitions: Iterable[int | str]) -> list[FixtureRef]:
        out: list[FixtureRef] = []
        for comp in competitions:
            try:
                res = await self.client.league(comp, ttl_seconds=3600.0)
                out.extend(parse_league_fixtures(res.data, str(comp)))
            except (FotMobBlockedError, FotMobRateLimitedError):
                raise
            except (FotMobError, PayloadError) as exc:
                logger.warning("team-news: fixtures of league %s failed: %s", comp, exc)
        return out

    async def discover_teams(self, competitions: Iterable[int | str]) -> set[str]:
        teams: set[str] = set()
        for f in await self.league_fixtures(competitions):
            teams.update(t for t in (f.home_team_provider_id, f.away_team_provider_id) if t)
        return teams

    async def discover_matches(
        self,
        now: datetime,
        hours_ahead: float,
        lookback_hours: float,
        competitions: Iterable[int | str],
        use_fixtures: bool = True,
    ) -> list[MatchRef]:
        comps = [str(c) for c in competitions]
        start, end = now - timedelta(hours=lookback_hours), now + timedelta(hours=hours_ahead)
        refs: dict[str, MatchRef] = {}
        for r in await self._read(db_matches_in_window, start, end, comps):
            refs[r.provider_match_id] = r
        if use_fixtures:
            fixtures = [
                f for f in await self.league_fixtures(comps)
                if f.kickoff_at is not None and start <= f.kickoff_at <= end and f.status != "cancelled"
            ]
            await self._db(_register_fixtures, fixtures)
            for f in fixtures:
                ref = refs.get(f.provider_match_id)
                if ref is None:
                    refs[f.provider_match_id] = MatchRef(
                        provider_match_id=f.provider_match_id,
                        kickoff_at=f.kickoff_at,
                        competition_provider_id=f.competition_provider_id,
                        home_team_provider_id=f.home_team_provider_id,
                        away_team_provider_id=f.away_team_provider_id,
                        home_team_name=f.home_team_name,
                        away_team_name=f.away_team_name,
                        status=f.status,
                        origins=["fotmob_league_fixtures"],
                    )
                else:
                    ref.origins.append("fotmob_league_fixtures")
                    if ref.status != "finished":
                        ref.status = f.status  # the source is fresher than a non-final local row
                        ref.kickoff_at = f.kickoff_at or ref.kickoff_at
        return sorted(refs.values(), key=lambda r: (r.kickoff_at or now, r.provider_match_id))

    # ------------------------------------------------------------------ one cycle

    async def run_cycle(
        self,
        now: Optional[datetime] = None,
        *,
        hours_ahead: float = 72.0,
        lookback_hours: float = 24.0,
        competitions: Iterable[int | str] = TARGET13_COMPETITIONS,
        squads: str = "window",
        match_due: Optional[Callable[[MatchRef, Optional[datetime]], bool]] = None,
        finished: bool = True,
        max_requests: Optional[int] = None,
        use_fixtures: bool = True,
    ) -> dict[str, Any]:
        """Discover -> refresh upcoming matches -> ingest finished -> squads.

        squads: "none" | "window" (teams of the upcoming matches) | "all"
        (every team in the competitions' current fixtures).
        """
        now = now or utc_now()
        comps = list(competitions)
        start_requests = self.client.request_count
        summary: dict[str, Any] = {"started_at": now.isoformat(), "upcoming": 0, "finished": 0}

        def budget_left() -> bool:
            return max_requests is None or self.client.request_count - start_requests < max_requests

        refs = await self.discover_matches(now, hours_ahead, lookback_hours, comps, use_fixtures=use_fixtures)
        upcoming = [r for r in refs if r.status == "scheduled" and r.kickoff_at and r.kickoff_at >= now]
        done = [r for r in refs if r.status == "finished"]
        registry = await self._read(_registry_rows, [r.provider_match_id for r in refs])
        summary["discovered"] = len(refs)

        summary["errors"] = 0

        async def guarded(coro_fn, ref: MatchRef) -> Optional[dict[str, Any]]:
            try:
                return await coro_fn(ref)
            except (FotMobBlockedError, FotMobRateLimitedError):
                raise
            except Exception:  # one bad match must not stop the cycle
                summary["errors"] += 1
                logger.exception("team-news: match %s failed", ref.provider_match_id)
                return None

        refreshed = []
        for ref in upcoming:
            if not budget_left():
                summary["stopped"] = "max_requests"
                break
            last = (registry.get(ref.provider_match_id) or {}).get("details_fetched_at")
            if match_due is not None and not match_due(ref, last):
                continue
            res = await guarded(self.refresh_match_team_news, ref)
            if res is not None:
                refreshed.append(res)
        summary["upcoming"] = len(refreshed)
        summary["upcoming_with_lineup"] = sum(1 for r in refreshed if r.get("home_lineup") or r.get("away_lineup"))

        if finished:
            ingested = []
            for ref in done:
                if not budget_left():
                    summary["stopped"] = "max_requests"
                    break
                if not needs_finished_ingest(ref, registry.get(ref.provider_match_id), now):
                    continue
                res = await guarded(self.ingest_finished_match, ref)
                if res is not None:
                    ingested.append(res)
            summary["finished"] = len(ingested)
            summary["finished_stats_rows"] = sum(int(r.get("stats_inserted") or 0) + int(r.get("stats_updated") or 0) for r in ingested)

        if squads != "none" and budget_left():
            if squads == "all":
                team_ids = await self.discover_teams(comps)
            else:
                team_ids = {t for r in upcoming for t in (r.home_team_provider_id, r.away_team_provider_id) if t}
            ordered = sorted(team_ids)
            if max_requests is not None:
                remaining = max(0, max_requests - (self.client.request_count - start_requests))
                if len(ordered) > remaining:
                    ordered = ordered[:remaining]
                    summary["stopped"] = "max_requests"
            summary["squads"] = await self.refresh_team_squads(ordered)
        summary["requests"] = self.client.request_count - start_requests
        return summary


def needs_finished_ingest(ref: MatchRef, registry_row: Optional[dict[str, Any]], now: datetime) -> bool:
    """True until one stats fetch happened >= FINISHED_SETTLE_HOURS after kickoff."""
    last = (registry_row or {}).get("stats_ingested_at")
    if last is None:
        return True
    if ref.kickoff_at is None:
        return False
    settle = ref.kickoff_at + timedelta(hours=FINISHED_SETTLE_HOURS)
    return last < settle and now >= last + timedelta(minutes=25)


# =========================================================================== wrappers


async def refresh_team_squads(
    team_ids: Iterable[str], *, session_factory: Callable[[], Session], client: TeamNewsFotMobClient,
    raw_store: Optional[RawStore] = None,
) -> dict[str, Any]:
    return await TeamNewsService(session_factory, client, raw_store).refresh_team_squads(team_ids)


async def refresh_match_team_news(
    match: "MatchRef | str", *, session_factory: Callable[[], Session], client: TeamNewsFotMobClient,
    raw_store: Optional[RawStore] = None,
) -> dict[str, Any]:
    return await TeamNewsService(session_factory, client, raw_store).refresh_match_team_news(match)


async def ingest_finished_match(
    match: "MatchRef | str", *, session_factory: Callable[[], Session], client: TeamNewsFotMobClient,
    raw_store: Optional[RawStore] = None,
) -> dict[str, Any]:
    return await TeamNewsService(session_factory, client, raw_store).ingest_finished_match(match)
