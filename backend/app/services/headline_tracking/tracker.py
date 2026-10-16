"""Background tracker of the headline picks: freeze before kick-off, settle after full time.

One ``tick`` (every ``settings.headline_tick_seconds``, default 60 s):

1. FREEZE - the fixtures list (re-read every ``headline_schedule_refresh_seconds`` from the shared
   provider cache) is filtered to featured competitions; every SCHEDULED match whose kick-off is
   within ``headline_freeze_minutes_before`` (default 20) minutes and still ahead is predicted afresh
   (the same prediction the match page shows), the Banko / Oranlı rule is applied
   (app/prediction/headline_picks.py) and each pick is stored once. A match that already has a
   headline record is skipped, so freezing is idempotent and a record is never overwritten. When no
   pick qualifies nothing is stored for that stage and it is logged. A failed prediction is retried
   after two minutes until kick-off.
2. SETTLE - frozen, unsettled picks whose match kicked off at least
   ``headline_settle_first_check_minutes`` (95) ago are looked up (local FINISHED row first, then the
   live match centre; at most one lookup per match every ``headline_settle_check_seconds``) and
   settled once the result is final. Nothing is looked up before the match can be over.

The loop never raises: every failure is logged and the next tick tries again.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.prediction.headline_picks import HeadlinePicks, headline_picks_from_prediction
from app.services.headline_tracking import sources
from app.services.headline_tracking.records import (
    HEADLINE_STAGES,
    KIND_BY_STAGE,
    MatchFacts,
    existing_stages,
    freeze_pick,
    parse_iso,
    settle_row,
    unsettled_rows,
    utc_now,
)
from app.services.headline_tracking.results import (
    ChainedResultFetcher,
    DbResultFetcher,
    LiveCenterResultFetcher,
    MatchResult,
    ResultFetcher,
    final_score_of,
    settle_outcome,
)
from app.services.headline_tracking.sources import ScheduledMatch

logger = logging.getLogger(__name__)

PREDICTION_RETRY_SECONDS = 120.0
HEARTBEAT_EVERY_TICKS = 10

Schedule = Callable[[datetime], Awaitable[List[ScheduledMatch]]]
Predictor = Callable[[str], Awaitable[Dict[str, Any]]]
LineupLookup = Callable[[str], Awaitable[Optional[Dict[str, Any]]]]


def _model_1x2(prediction: Dict[str, Any]) -> Dict[str, Optional[float]]:
    def num(name: str) -> Optional[float]:
        value = prediction.get(name)
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    return {
        "home": num("home_win_probability"),
        "draw": num("draw_probability"),
        "away": num("away_win_probability"),
    }


@dataclass
class HeadlineTracker:
    session_factory: Callable[[], Session]
    cfg: Any = None
    schedule: Optional[Schedule] = None
    predictor: Optional[Predictor] = None
    results: Optional[ResultFetcher] = None
    lineup_lookup: Optional[LineupLookup] = None
    featured: Optional[set] = None

    ticks: int = field(default=0, init=False)
    _schedule_cache: List[ScheduledMatch] = field(default_factory=list, init=False, repr=False)
    _schedule_read_at: Optional[datetime] = field(default=None, init=False, repr=False)
    _evaluated: set = field(default_factory=set, init=False, repr=False)
    _retry_after: Dict[str, datetime] = field(default_factory=dict, init=False, repr=False)
    _last_result_check: Dict[str, datetime] = field(default_factory=dict, init=False, repr=False)
    _gave_up: set = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.cfg is None:
            from app.config import settings

            self.cfg = settings
        self.schedule = self.schedule or sources.fetch_schedule
        self.predictor = self.predictor or sources.fetch_prediction
        self.lineup_lookup = self.lineup_lookup or sources.fetch_lineup_types
        if self.results is None:
            self.results = ChainedResultFetcher([DbResultFetcher(self.session_factory), LiveCenterResultFetcher()])
        if self.featured is None:
            self.featured = sources.featured_competitions()

    # ------------------------------------------------------------------ tick

    async def tick(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        now = now or utc_now()
        self.ticks += 1
        summary: Dict[str, Any] = {
            "now": now.isoformat(),
            "upcoming_30m": 0,
            "frozen": [],
            "no_pick": [],
            "already_frozen": [],
            "prediction_failed": [],
            "settled": [],
            "waiting_for_result": 0,
            "unsettled_picks": 0,
            "errors": [],
        }
        for phase in (self._freeze_phase, self._settle_phase):
            try:
                await phase(now, summary)
            except Exception as exc:  # the loop must never stop
                logger.exception("headline tracking: %s failed", phase.__name__)
                summary["errors"].append(f"{phase.__name__}: {exc}")
        if self.ticks % HEARTBEAT_EVERY_TICKS == 1:  # first tick, then about every 10 minutes
            logger.info(
                "headline tracking alive: tick %d, %d featured match(es) in the next 30 min, %d unsettled pick(s)",
                self.ticks, summary["upcoming_30m"], summary["unsettled_picks"],
            )
        return summary

    # ---------------------------------------------------------------- freeze

    async def _fixtures(self, now: datetime) -> List[ScheduledMatch]:
        refresh = timedelta(seconds=float(self.cfg.headline_schedule_refresh_seconds))
        if self._schedule_read_at is None or now - self._schedule_read_at >= refresh:
            self._schedule_cache = list(await self.schedule(now))  # type: ignore[misc]
            self._schedule_read_at = now
        return self._schedule_cache

    async def _freeze_phase(self, now: datetime, summary: Dict[str, Any]) -> None:
        window = timedelta(minutes=float(self.cfg.headline_freeze_minutes_before))
        look_ahead = max(window, timedelta(minutes=30))
        # cheap pre-check first: is any featured match kicking off soon? (reads the cached list)
        fixtures = await self._fixtures(now)
        soon = [
            m for m in fixtures
            if m.competition_id in (self.featured or set())
            and m.status == "SCHEDULED"
            and timedelta(0) < m.kickoff_at - now <= look_ahead
        ]
        summary["upcoming_30m"] = len(soon)
        for m in sorted(soon, key=lambda x: x.kickoff_at):
            if m.kickoff_at - now > window or m.match_id in self._evaluated:
                continue
            if self._retry_after.get(m.match_id, now) > now:
                continue
            await self._freeze_match(m, now, summary)

    async def _freeze_match(self, m: ScheduledMatch, now: datetime, summary: Dict[str, Any]) -> None:
        with self.session_factory() as session:
            if existing_stages(session, m.match_id):
                self._evaluated.add(m.match_id)
                summary["already_frozen"].append(m.match_id)
                return
        try:
            prediction = await self.predictor(m.match_id)  # type: ignore[misc]
        except Exception as exc:
            logger.warning("headline tracking: no prediction for %s (%s), retrying", m.match_id, exc)
            self._retry_after[m.match_id] = now + timedelta(seconds=PREDICTION_RETRY_SECONDS)
            summary["prediction_failed"].append(m.match_id)
            return

        home = m.home_team or "Ev sahibi"
        away = m.away_team or "Deplasman"
        picks: HeadlinePicks = headline_picks_from_prediction(prediction, home, away)
        if picks.banko is None:
            logger.info("headline tracking: no banko qualifies for %s (%s - %s), nothing stored", m.match_id, home, away)
        if picks.oranli is None:
            logger.info("headline tracking: no oranli qualifies for %s (%s - %s), nothing stored", m.match_id, home, away)
        if picks.banko is None and picks.oranli is None:
            self._evaluated.add(m.match_id)
            summary["no_pick"].append(m.match_id)
            return

        lineup = sources.lineup_types_from_squad_info(prediction.get("squad_info"))
        if lineup is None or lineup.get("home") is None or lineup.get("away") is None:
            try:
                looked_up = await self.lineup_lookup(m.match_id)  # type: ignore[misc]
            except Exception:
                logger.exception("headline tracking: line-up lookup failed for %s", m.match_id)
                looked_up = None
            lineup = looked_up or lineup
        facts = MatchFacts(
            match_id=m.match_id,
            kickoff_at=m.kickoff_at,
            competition_id=m.competition_id,
            competition_name=m.competition_name,
            home_team=m.home_team,
            away_team=m.away_team,
        )
        model_1x2 = _model_1x2(prediction)
        try:
            with self.session_factory() as session:
                for kind, pick in (("banko", picks.banko), ("oranli", picks.oranli)):
                    if pick is None:
                        continue
                    row_id = freeze_pick(
                        session, kind, pick, facts,
                        frozen_at=now, model_1x2=model_1x2, lineup_types=lineup,
                    )
                    if row_id is not None:
                        summary["frozen"].append({"match_id": m.match_id, "kind": kind, "key": pick.key})
                        logger.info(
                            "headline tracking: froze %s %s for %s - %s (p=%.3f, kick-off in %.0f min)",
                            kind, pick.key, home, away, pick.probability, (m.kickoff_at - now).total_seconds() / 60,
                        )
        except Exception as exc:  # a failed write is retried on a later tick (records are checked first)
            logger.exception("headline tracking: could not store the picks of %s", m.match_id)
            self._retry_after[m.match_id] = now + timedelta(seconds=PREDICTION_RETRY_SECONDS)
            summary["errors"].append(f"freeze {m.match_id}: {exc}")
            return
        self._evaluated.add(m.match_id)

    # ---------------------------------------------------------------- settle

    async def _settle_phase(self, now: datetime, summary: Dict[str, Any]) -> None:
        first_check = timedelta(minutes=float(self.cfg.headline_settle_first_check_minutes))
        give_up = timedelta(hours=float(self.cfg.headline_settle_give_up_hours))
        min_gap = timedelta(seconds=float(self.cfg.headline_settle_check_seconds))

        with self.session_factory() as session:
            pending: Dict[str, List[str]] = {}
            kickoffs: Dict[str, Optional[datetime]] = {}
            for row in unsettled_rows(session):
                pending.setdefault(row.match_id, []).append(row.id)
                kickoffs[row.match_id] = parse_iso((row.prediction_data or {}).get("kickoff_at"))
                summary["unsettled_picks"] += 1

        for match_id, row_ids in pending.items():
            kickoff = kickoffs.get(match_id)
            if kickoff is None:
                continue  # no kick-off recorded: cannot tell when to look
            age = now - kickoff
            if age < first_check:
                continue
            if age > give_up:
                if match_id not in self._gave_up:
                    self._gave_up.add(match_id)
                    logger.warning(
                        "headline tracking: no final result for %s %.0f h after kick-off, no longer checking",
                        match_id, age.total_seconds() / 3600,
                    )
                continue
            last = self._last_result_check.get(match_id)
            if last is not None and now - last < min_gap:
                summary["waiting_for_result"] += 1
                continue
            self._last_result_check[match_id] = now
            try:
                result = await self.results(match_id)  # type: ignore[misc]
            except Exception:
                logger.exception("headline tracking: result lookup failed for %s", match_id)
                continue
            if result is None or not result.is_final:
                summary["waiting_for_result"] += 1
                continue
            summary["settled"].extend(self.settle_match(match_id, result, now))
            self._last_result_check.pop(match_id, None)

    def settle_match(self, match_id: str, result: MatchResult, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Settle every unsettled headline pick of a match against a final result."""
        settled: List[Dict[str, Any]] = []
        with self.session_factory() as session:
            for row in unsettled_rows(session):
                if row.match_id != match_id or row.stage not in HEADLINE_STAGES:
                    continue
                outcome, reason = settle_outcome(row.selected_market, result)
                if outcome is None:
                    continue
                if settle_row(
                    session, row, outcome=outcome, final_score=final_score_of(result), reason=reason,
                    result_source=result.source, now=now,
                ):
                    settled.append(
                        {"match_id": match_id, "kind": KIND_BY_STAGE[row.stage], "key": row.selected_market, "result": outcome}
                    )
                    logger.info("headline tracking: settled %s %s of %s as %s", KIND_BY_STAGE[row.stage], row.selected_market, match_id, outcome)
        return settled

    # ------------------------------------------------------------------- run

    async def run(self, stop: asyncio.Event) -> None:
        interval = float(self.cfg.headline_tick_seconds)
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:  # tick already isolates its phases; belt and braces
                logger.exception("headline tracking: tick failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass


# -------------------------------------------------------------------------- app lifecycle


@dataclass
class TrackerHandle:
    task: asyncio.Task
    stop: asyncio.Event
    tracker: HeadlineTracker


def _ensure_visible_logging() -> None:
    """The app configures no root logger (uvicorn only its own), so INFO lines of this package would
    vanish: give the package logger its own INFO stream handler unless the host already logs."""
    package_logger = logging.getLogger("app.services.headline_tracking")
    if package_logger.level == logging.NOTSET:
        package_logger.setLevel(logging.INFO)
    if not logging.getLogger().handlers and not package_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        package_logger.addHandler(handler)


def start_headline_tracker(session_factory: Callable[[], Session]) -> Optional[TrackerHandle]:
    """Start the loop as an asyncio task (call from the running event loop)."""
    try:
        with session_factory() as session:
            tables = set(inspect(session.get_bind()).get_table_names())
        if "prediction_versions" not in tables:
            logger.error("headline tracking NOT started: table prediction_versions is missing")
            return None
    except Exception:
        logger.exception("headline tracking NOT started: could not inspect the database")
        return None
    _ensure_visible_logging()
    tracker = HeadlineTracker(session_factory)
    stop = asyncio.Event()
    task = asyncio.create_task(tracker.run(stop), name="headline-tracking")
    logger.info(
        "headline tracking started (freeze %s min before kick-off, featured competitions %s)",
        tracker.cfg.headline_freeze_minutes_before, sorted(tracker.featured or []),
    )
    return TrackerHandle(task=task, stop=stop, tracker=tracker)


async def stop_headline_tracker(handle: Optional[TrackerHandle], timeout: float = 10.0) -> None:
    if handle is None:
        return
    handle.stop.set()
    try:
        await asyncio.wait_for(handle.task, timeout=timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        handle.task.cancel()
    except Exception:
        logger.exception("headline tracking: error while stopping")
