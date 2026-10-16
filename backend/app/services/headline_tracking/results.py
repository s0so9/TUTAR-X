"""Where the final result of a frozen match comes from, and how a pick is settled against it.

* ``DbResultFetcher``: the local ``matches`` row, only when it says FINISHED with both scores
  (free: no network).
* ``LiveCenterResultFetcher``: the live match centre (FotMob matchDetails through the existing
  paced client, cached 15 s live / 1 h once finished).
* ``ChainedResultFetcher``: first final answer wins.

Settlement uses the full-time score (90 minutes), the same ``landed`` logic as
docs/live-tests/2026-10-14/score_picks.py. A match that went to extra time or penalties has no
90-minute score in the source, so its picks are voided (listed as void with the reason, not
counted in the hit rate). Cancelled / abandoned / postponed matches are void.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Sequence

from sqlalchemy.orm import Session

from app.prediction.headline_picks import landed
from app.services.headline_tracking.records import RESULT_LOST, RESULT_VOID, RESULT_WON

logger = logging.getLogger(__name__)

STATUS_FINISHED = "FINISHED"
VOID_STATUSES = frozenset({"CANCELLED", "ABANDONED", "POSTPONED"})

REASON_CANCELLED = "maç iptal / yarıda kaldı / ertelendi"
REASON_EXTRA_TIME = "uzatmaya gitti: 90 dakika skoru kaynakta yok"


@dataclass(frozen=True)
class MatchResult:
    status: str
    home_goals: Optional[int] = None
    away_goals: Optional[int] = None
    went_to_extra_time: bool = False
    source: str = ""

    @property
    def is_final(self) -> bool:
        if self.status in VOID_STATUSES:
            return True
        return self.status == STATUS_FINISHED and self.home_goals is not None and self.away_goals is not None


ResultFetcher = Callable[[str], Awaitable[Optional[MatchResult]]]


def settle_outcome(key: str, result: MatchResult) -> tuple[Optional[str], Optional[str]]:
    """(won | lost | void, reason) for a final result; (None, None) when it is not final yet."""
    if not result.is_final:
        return None, None
    if result.status in VOID_STATUSES:
        return RESULT_VOID, REASON_CANCELLED
    if result.went_to_extra_time:
        return RESULT_VOID, REASON_EXTRA_TIME
    assert result.home_goals is not None and result.away_goals is not None
    return (RESULT_WON if landed(key, result.home_goals, result.away_goals) else RESULT_LOST), None


def final_score_of(result: MatchResult) -> Optional[dict]:
    if result.status in VOID_STATUSES or result.home_goals is None or result.away_goals is None:
        return None
    return {"home": result.home_goals, "away": result.away_goals, "extra_time": result.went_to_extra_time}


class DbResultFetcher:
    """FINISHED rows of the local matches table (provider id = FotMob id, route id fotmob_<id>)."""

    def __init__(self, session_factory: Callable[[], Session]):
        self._factory = session_factory

    def _lookup(self, match_id: str) -> Optional[MatchResult]:
        from app.database.models import Match

        provider_id = match_id[len("fotmob_"):] if match_id.startswith("fotmob_") else match_id
        with self._factory() as session:
            row = session.query(Match).filter(Match.provider_id == provider_id).first()
            if row is None:
                return None
            status = getattr(row.status, "value", str(row.status))
            if status != STATUS_FINISHED or row.home_score is None or row.away_score is None:
                return None
            return MatchResult(
                status=STATUS_FINISHED,
                home_goals=int(row.home_score),
                away_goals=int(row.away_score),
                source="matches_table",
            )

    async def __call__(self, match_id: str) -> Optional[MatchResult]:
        try:
            return self._lookup(match_id)  # one indexed row: cheaper than a thread hop
        except Exception:
            logger.exception("headline tracking: local result lookup failed for %s", match_id)
            return None


class LiveCenterResultFetcher:
    """Status and score from the live match centre service."""

    def __init__(self, service=None):
        self._service = service

    async def __call__(self, match_id: str) -> Optional[MatchResult]:
        from app.services.live_center.service import LiveCenterError, get_live_center_service

        service = self._service or get_live_center_service()
        try:
            response = await service.get(match_id)
        except LiveCenterError as exc:
            logger.warning("headline tracking: live centre has no result for %s yet (%s)", match_id, exc.code)
            return None
        status_text = (response.status_text or "").strip().upper()
        went_to_extra_time = response.penalty_score is not None or status_text in {"AET", "PEN", "AP"}
        return MatchResult(
            status=response.status,
            home_goals=response.score.home,
            away_goals=response.score.away,
            went_to_extra_time=went_to_extra_time,
            source="live_center",
        )


class ChainedResultFetcher:
    def __init__(self, fetchers: Sequence[ResultFetcher]):
        self._fetchers = list(fetchers)

    async def __call__(self, match_id: str) -> Optional[MatchResult]:
        last: Optional[MatchResult] = None
        for fetch in self._fetchers:
            result = await fetch(match_id)
            if result is None:
                continue
            if result.is_final:
                return result
            last = result
        return last
