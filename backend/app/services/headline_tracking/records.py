"""Frozen headline picks (Banko / Oranlı) stored in the existing ``prediction_versions`` table.

One row per pick, stage ``headline_banko`` / ``headline_oranli`` (no schema change):

  selected_market          market key, e.g. HOME_OR_DRAW / OVER_2_5 / BTTS_YES
  selection_text           Turkish outcome text as the match page prints it
  selection_probability    model probability at freeze time
  selection_fair_odds      1 / probability
  selection_odds           bookmaker odds at freeze time, NULL without odds
  actual_result            NULL until settled, then 'won' | 'lost' | 'void'
  settled_at               when the result was recorded
  prediction_data (JSON)   rule version, kind, frozen_at, kick-off, teams, competition, 1X2
                           probabilities, line-up type of both sides, source, the Banko tier
                           (banko records since headline_v2; informational, reports derive it
                           from selection_probability), and after settlement the final score

Records are immutable: a frozen pick is never overwritten (only the settlement fields and the
final score are added later). The table has no unique (match_id, stage) constraint, so freezing
checks first, and after the insert removes a concurrent duplicate (the oldest row survives).
"""

from __future__ import annotations

import copy
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import PredictionVersionDB
from app.prediction.headline_picks import RULE_VERSION, PickCandidate, banko_tier
from app.prediction.prediction_version import PredictionStage, PredictionVersion, PredictionVersionManager
from app.services.prediction_persistence import PredictionPersistenceService

logger = logging.getLogger(__name__)

KINDS = ("banko", "oranli")
STAGE_BY_KIND: Dict[str, str] = {
    "banko": PredictionStage.HEADLINE_BANKO.value,
    "oranli": PredictionStage.HEADLINE_ORANLI.value,
}
KIND_BY_STAGE: Dict[str, str] = {stage: kind for kind, stage in STAGE_BY_KIND.items()}
HEADLINE_STAGES = tuple(STAGE_BY_KIND.values())

SOURCE_LIVE = "live_freeze"
SOURCE_MANUAL_2026_10_14 = "manual_record_2026-10-14"

RESULT_WON = "won"
RESULT_LOST = "lost"
RESULT_VOID = "void"

_freeze_lock = threading.Lock()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Database datetimes come back naive (UTC by convention): make them aware."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def to_db_time(value: datetime) -> datetime:
    """Naive UTC, the way the rest of prediction_versions stores its timestamps."""
    return as_utc(value).replace(tzinfo=None)  # type: ignore[union-attr]


def iso(value: Optional[datetime]) -> Optional[str]:
    aware = as_utc(value)
    return aware.isoformat().replace("+00:00", "Z") if aware else None


def parse_iso(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return as_utc(datetime.fromisoformat(value.strip().replace("Z", "+00:00")))
    except ValueError:
        return None


@dataclass(frozen=True)
class MatchFacts:
    """What is known about the match when its picks are frozen."""

    match_id: str
    kickoff_at: Optional[datetime]
    competition_id: Optional[str] = None
    competition_name: Optional[str] = None
    home_team: Optional[str] = None
    away_team: Optional[str] = None


def build_prediction_data(
    kind: str,
    pick: PickCandidate,
    facts: MatchFacts,
    *,
    frozen_at: datetime,
    model_1x2: Optional[Dict[str, Optional[float]]],
    lineup_types: Optional[Dict[str, Any]],
    source: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    kickoff = as_utc(facts.kickoff_at)
    minutes_before = (
        round((kickoff - as_utc(frozen_at)).total_seconds() / 60.0, 1) if kickoff is not None else None
    )
    data: Dict[str, Any] = {
        "rule_version": RULE_VERSION,
        "kind": kind,
        "source": source,
        "frozen_at": iso(frozen_at),
        "kickoff_at": iso(kickoff),
        "minutes_before_kickoff": minutes_before,
        "match_id": facts.match_id,
        "home_team": facts.home_team,
        "away_team": facts.away_team,
        "competition_id": facts.competition_id,
        "competition_name": facts.competition_name,
        "market_name": pick.market_name,
        "outcome": pick.outcome,
        "odds_source": pick.odds_source,
        # 1X2 probabilities of the prediction the picks were taken from (None = not in the response)
        "model_1x2": model_1x2,
        # confirmed | predicted | last_starting11 | None (= not known) per side
        "lineup_type": lineup_types or {"home": None, "away": None, "source": None},
    }
    if kind == "banko":
        # informational only: reports derive the tier from selection_probability (report.row_to_item)
        data["banko_tier"] = banko_tier(pick.probability)
    if extra:
        data.update(extra)
    return data


def existing_stages(session: Session, match_id: str) -> Set[str]:
    """Headline stages already stored for a match."""
    stmt = select(PredictionVersionDB.stage).where(
        PredictionVersionDB.match_id == match_id,
        PredictionVersionDB.stage.in_(HEADLINE_STAGES),
    )
    return {row[0] for row in session.execute(stmt).all()}


def _rows_for(session: Session, match_id: str, stage: str) -> List[PredictionVersionDB]:
    stmt = (
        select(PredictionVersionDB)
        .where(PredictionVersionDB.match_id == match_id, PredictionVersionDB.stage == stage)
        .order_by(PredictionVersionDB.created_at.asc(), PredictionVersionDB.id.asc())
    )
    return list(session.execute(stmt).scalars().all())


def freeze_pick(
    session: Session,
    kind: str,
    pick: PickCandidate,
    facts: MatchFacts,
    *,
    frozen_at: datetime,
    model_1x2: Optional[Dict[str, Optional[float]]],
    lineup_types: Optional[Dict[str, Any]],
    source: str = SOURCE_LIVE,
    extra: Optional[Dict[str, Any]] = None,
    notes: Optional[List[str]] = None,
) -> Optional[str]:
    """Store one frozen pick. Returns the new row id, or None when the (match, stage) record
    already exists (an existing record is never touched)."""
    if kind not in STAGE_BY_KIND:
        raise ValueError(f"unknown pick kind: {kind!r}")
    stage = STAGE_BY_KIND[kind]
    data = build_prediction_data(
        kind, pick, facts, frozen_at=frozen_at, model_1x2=model_1x2, lineup_types=lineup_types,
        source=source, extra=extra,
    )
    persistence = PredictionPersistenceService(session)
    row_notes = list(notes or []) + [
        "confidence_score / data_quality_score are not used for headline picks (0.0 placeholders)"
    ]
    with _freeze_lock:
        if _rows_for(session, facts.match_id, stage):
            return None
        if source == SOURCE_LIVE:
            # created_at = now (the manager's own clock); the existence check was done above, so the
            # manager does not need to load (and convert) every version of the match again.
            manager = PredictionVersionManager(persistence_service=persistence)
            try:
                version = manager.create_version(
                    match_id=facts.match_id,
                    stage=PredictionStage(stage),
                    prediction_data=data,
                    data_quality_score=0.0,
                    confidence_score=0.0,
                    notes=row_notes,
                    allow_stage_overwrite=True,
                    mensione_pick={
                        "market": pick.key,
                        "selection": pick.outcome,
                        "probability": pick.probability,
                        "confidence": None,
                        "bookmaker_odds": pick.odds,
                        "fair_odds": pick.fair_odds,
                    },
                )
            except ValueError:
                session.rollback()
                return None
        else:
            version = PredictionVersion(
                version_id=_new_id(),
                match_id=facts.match_id,
                stage=PredictionStage(stage),
                created_at=to_db_time(frozen_at),
                prediction_data=data,
                data_quality_score=0.0,
                confidence_score=0.0,
                notes=row_notes,
                selected_market=pick.key,
                selection_text=pick.outcome,
                selection_probability=pick.probability,
                selection_odds=pick.odds,
                selection_fair_odds=pick.fair_odds,
            )
            try:
                persistence.save_version(version)
            except ValueError:
                session.rollback()
                return None
        _drop_concurrent_duplicates(session, facts.match_id, stage)
        return version.version_id


def _new_id() -> str:
    import uuid

    return str(uuid.uuid4())


def _drop_concurrent_duplicates(session: Session, match_id: str, stage: str) -> None:
    """Another process may have frozen the same pick between our check and our insert (no unique
    constraint exists). The oldest record survives; younger duplicates are removed."""
    rows = _rows_for(session, match_id, stage)
    if len(rows) <= 1:
        return
    for extra in rows[1:]:
        logger.warning("headline pick %s/%s frozen twice concurrently, dropping %s", match_id, stage, extra.id)
        session.delete(extra)
    session.commit()


def unsettled_rows(session: Session) -> List[PredictionVersionDB]:
    stmt = (
        select(PredictionVersionDB)
        .where(PredictionVersionDB.stage.in_(HEADLINE_STAGES), PredictionVersionDB.actual_result.is_(None))
        .order_by(PredictionVersionDB.created_at.asc())
    )
    return list(session.execute(stmt).scalars().all())


def settle_row(
    session: Session,
    row: PredictionVersionDB,
    *,
    outcome: str,
    final_score: Optional[Dict[str, Optional[int]]],
    reason: Optional[str],
    result_source: Optional[str],
    now: Optional[datetime] = None,
) -> bool:
    """Record the result of a frozen pick. Returns False when it was settled already."""
    if outcome not in (RESULT_WON, RESULT_LOST, RESULT_VOID):
        raise ValueError(f"unknown result: {outcome!r}")
    if row.actual_result is not None:
        return False
    now = now or utc_now()
    data = copy.deepcopy(row.prediction_data or {})
    data["final_score"] = final_score
    data["settlement"] = {"outcome": outcome, "reason": reason, "result_source": result_source, "settled_at": iso(now)}
    row.prediction_data = data  # new object: SQLAlchemy only sees reassigned JSON
    row.actual_result = outcome
    row.settled_at = to_db_time(now)
    session.commit()
    return True
