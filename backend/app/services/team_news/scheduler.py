"""Optional background refresh of the team-news layer inside the FastAPI process.

Started from the app lifespan only when ``settings.team_news_refresh_enabled``
is true (default False). Cadence (settings.team_news_*):
  * squads of every team in the target competitions: every 6 h;
  * matches kicking off within 72 h: every 15 min, every 5 min within 2 h of
    kickoff (line-up snapshots + match unavailable lists);
  * matches finished in the last 24 h: checked every 30 min, player stats
    ingested until one fetch happened >= 6 h after kickoff.
A FotMob 403/captcha/challenge stops the loop for the lifetime of the process
(logged as an error); a 429 only skips the rest of the current tick.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.services.team_news.fotmob_client import (
    FotMobBlockedError,
    FotMobRateLimitedError,
    TeamNewsFotMobClient,
)
from app.services.team_news.raw_store import RawStore, default_raw_store
from app.services.team_news.service import MatchRef, TeamNewsService
from app.services.team_news.store import utc_now

logger = logging.getLogger(__name__)

REQUIRED_TABLES = ("team_squad_members", "player_availability", "player_match_stats", "lineup_snapshots", "team_news_matches")
TICK_SECONDS = 60.0


def parse_competitions(spec: str) -> list[int]:
    out: list[int] = []
    for tok in (spec or "").split(","):
        tok = tok.strip()
        if tok.isdigit() and int(tok) not in out:
            out.append(int(tok))
    return out


class TeamNewsRefreshLoop:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        cfg: Any = None,
        client: Optional[TeamNewsFotMobClient] = None,
        raw_store: Optional[RawStore] = None,
    ):
        if cfg is None:
            from app.config import settings as cfg  # noqa: N813
        self.cfg = cfg
        self.client = client or TeamNewsFotMobClient()
        self.service = TeamNewsService(session_factory, self.client, raw_store or default_raw_store())
        self.competitions = parse_competitions(cfg.team_news_competitions)
        self.last_squads: Optional[datetime] = None
        self.last_finished: Optional[datetime] = None
        self.stopped_reason: Optional[str] = None
        self.ticks = 0

    def match_due(self, ref: MatchRef, last_fetch: Optional[datetime], now: datetime) -> bool:
        if last_fetch is None:
            return True
        near = ref.kickoff_at is not None and ref.kickoff_at - now <= timedelta(hours=self.cfg.team_news_near_kickoff_hours)
        minutes = self.cfg.team_news_near_kickoff_refresh_minutes if near else self.cfg.team_news_match_refresh_minutes
        return now - last_fetch >= timedelta(minutes=minutes)

    async def tick(self, now: Optional[datetime] = None) -> dict[str, Any]:
        now = now or utc_now()
        self.ticks += 1
        finished_due = self.last_finished is None or now - self.last_finished >= timedelta(
            minutes=self.cfg.team_news_finished_refresh_minutes
        )
        summary = await self.service.run_cycle(
            now,
            hours_ahead=self.cfg.team_news_hours_ahead,
            lookback_hours=self.cfg.team_news_finished_lookback_hours,
            competitions=self.competitions,
            squads="none",
            match_due=lambda ref, last: self.match_due(ref, last, now),
            finished=finished_due,
        )
        if finished_due:
            self.last_finished = now
        if self.last_squads is None or now - self.last_squads >= timedelta(hours=self.cfg.team_news_squad_refresh_hours):
            teams = await self.service.discover_teams(self.competitions)
            summary["squads"] = await self.service.refresh_team_squads(teams)
            self.last_squads = now
        if summary.get("upcoming") or summary.get("finished") or summary.get("squads"):
            logger.info("team-news refresh: %s", summary)
        return summary

    async def run(self, stop: asyncio.Event) -> None:
        try:
            while not stop.is_set():
                try:
                    await self.tick()
                except FotMobBlockedError as exc:
                    self.stopped_reason = f"blocked: {exc}"
                    logger.error("team-news refresh STOPPED: FotMob refused/challenged the requests (%s)", exc)
                    return
                except FotMobRateLimitedError as exc:
                    logger.warning("team-news refresh: rate limited, retrying next tick (%s)", exc)
                except Exception:
                    logger.exception("team-news refresh tick failed")
                try:
                    await asyncio.wait_for(stop.wait(), timeout=TICK_SECONDS)
                except asyncio.TimeoutError:
                    pass
        finally:
            await self.client.aclose()


@dataclass
class RefresherHandle:
    task: asyncio.Task
    stop: asyncio.Event
    loop: TeamNewsRefreshLoop


def live_tables_present(session_factory: Callable[[], Session]) -> bool:
    with session_factory() as session:
        names = set(inspect(session.get_bind()).get_table_names())
    return all(t in names for t in REQUIRED_TABLES)


def start_team_news_refresher(session_factory: Callable[[], Session]) -> Optional[RefresherHandle]:
    """Start the loop as an asyncio task (call from the running event loop)."""
    try:
        if not live_tables_present(session_factory):
            logger.error("team-news refresh NOT started: tables missing (apply Alembic revision 20261013_team_news)")
            return None
    except Exception:
        logger.exception("team-news refresh NOT started: could not inspect the database")
        return None
    loop = TeamNewsRefreshLoop(session_factory)
    stop = asyncio.Event()
    task = asyncio.create_task(loop.run(stop), name="team-news-refresh")
    logger.info("team-news refresh started (competitions=%s)", loop.competitions)
    return RefresherHandle(task=task, stop=stop, loop=loop)


async def stop_team_news_refresher(handle: Optional[RefresherHandle], timeout: float = 10.0) -> None:
    if handle is None:
        return
    handle.stop.set()
    try:
        await asyncio.wait_for(handle.task, timeout=timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        handle.task.cancel()
    except Exception:
        logger.exception("team-news refresh: error while stopping")
