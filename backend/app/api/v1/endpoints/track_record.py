"""Track record of the two headline picks (Banko / Oranlı).

GET /api/v1/track-record/headline?days=30&competition_id=42&rule_version=headline_v2
  Hit rate of the frozen Banko and Oranlı picks (won / lost / void / pending), by competition, by
  week, per Banko tier and the list of the picks themselves, for ONE rule version (default: the
  current one; "all" = every version). Only picks frozen before kick-off by the headline tracker (or
  imported from the hand-tracked night of 2026-10-14, source "manual_record_2026-10-14", rule
  headline_v1) are counted; nothing is added afterwards.
GET /api/v1/matches/{match_id}/headline-record
  The frozen Banko / Oranlı of one match (null per kind when nothing was frozen).
Both read the local database only.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.prediction.headline_picks import RULE_VERSION
from app.services.headline_tracking.report import ALL_RULE_VERSIONS, build_track_record, match_headline_record

router = APIRouter(tags=["track-record"])


class LineupTypes(BaseModel):
    home: Optional[str] = Field(None, description="confirmed | predicted | last_starting11 | null = unknown")
    away: Optional[str] = None
    source: Optional[str] = None


class FinalScore(BaseModel):
    home: Optional[int] = None
    away: Optional[int] = None
    extra_time: Optional[bool] = None


class Model1x2(BaseModel):
    home: Optional[float] = None
    draw: Optional[float] = None
    away: Optional[float] = None


class HeadlinePickItem(BaseModel):
    id: str
    match_id: str
    kind: str = Field(description="banko | oranli")
    stage: str
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    competition_id: Optional[str] = None
    competition_name: Optional[str] = None
    kickoff_at: Optional[str] = None
    frozen_at: Optional[str] = None
    minutes_before_kickoff: Optional[float] = None
    market_key: str
    label: str = Field(description='compact label, e.g. "1X", "2.5 Üst", "KG Var"')
    selection_text: Optional[str] = None
    market_name: Optional[str] = None
    probability: Optional[float] = None
    fair_odds: Optional[float] = None
    odds: Optional[float] = Field(None, description="bookmaker odds at freeze time; null = none known")
    lineup_type: LineupTypes
    model_1x2: Optional[Model1x2] = None
    result: Optional[str] = Field(None, description="won | lost | void | null = not settled yet")
    final_score: Optional[FinalScore] = None
    settled_at: Optional[str] = None
    source: Optional[str] = None
    rule_version: Optional[str] = None
    tier: Optional[str] = Field(
        None,
        description="Banko tier derived from the stored probability: cok_guclu (>= 0.90) | banko (0.85-0.90) | "
        "guclu (0.70-0.85); null for the Oranli or a probability outside 0.70-0.95",
    )


class KindSummary(BaseModel):
    won: int
    lost: int
    void: int
    pending: int
    settled: int = Field(description="won + lost")
    hit_rate: Optional[float] = Field(None, description="won / (won + lost); null while nothing is settled")


class KindPair(BaseModel):
    banko: KindSummary = Field(description="every frozen Banko slot pick, the guclu (0.70-0.85) ones included")
    oranli: KindSummary
    banko_strong: KindSummary = Field(
        description="the Bankos with p >= 0.85 only (tiers banko + cok_guclu); guclu picks are not Bankos"
    )


class BankoTiers(BaseModel):
    """The Banko picks of the period split by tier (derived from the stored probability)."""

    cok_guclu: KindSummary
    banko: KindSummary
    guclu: KindSummary


class BankoProgress(KindSummary):
    """Every recorded Banko with p >= min_probability of the rule version, all time and all competitions."""

    rule_version: str
    min_probability: float
    target: int = Field(description="recorded Bankos needed before a ~90 % hit rate can be checked")


class CompetitionRow(KindPair):
    competition_id: Optional[str] = None
    competition_name: Optional[str] = None
    total: int


class WeekRow(KindPair):
    week_start: str = Field(description="Monday (UTC) of the week of the kick-off, YYYY-MM-DD")


class CompetitionOption(BaseModel):
    id: str
    name: str


class HeadlineTrackRecordResponse(BaseModel):
    generated_at: str
    days: int
    competition_id: Optional[str] = None
    rule_version: str = Field(description='rule version shown ("all" = every version)')
    current_rule_version: str
    available_rule_versions: List[str]
    summary: KindPair
    banko_tiers: BankoTiers
    banko_progress: BankoProgress
    by_competition: List[CompetitionRow]
    by_week: List[WeekRow]
    available_competitions: List[CompetitionOption]
    picks: List[HeadlinePickItem]
    note: str


class MatchHeadlineRecordPicks(BaseModel):
    banko: Optional[HeadlinePickItem] = None
    oranli: Optional[HeadlinePickItem] = None


class MatchHeadlineRecordResponse(BaseModel):
    match_id: str
    frozen: bool
    picks: MatchHeadlineRecordPicks


@router.get(
    "/track-record/headline",
    response_model=HeadlineTrackRecordResponse,
    summary="Track record of the headline picks (Banko / Oranlı)",
)
def get_headline_track_record(
    days: int = Query(30, ge=1, le=366, description="Period: matches that kicked off in the last N days"),
    competition_id: Optional[str] = Query(None, description="Only this competition (FotMob league id, e.g. 42)"),
    rule_version: str = Query(
        RULE_VERSION,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_.\-]+$",
        description=f'Only picks frozen with this rule version (default: the current one); "{ALL_RULE_VERSIONS}" = every version',
    ),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return build_track_record(db, days=days, competition_id=competition_id, rule_version=rule_version)


@router.get(
    "/matches/{match_id}/headline-record",
    response_model=MatchHeadlineRecordResponse,
    summary="Frozen Banko / Oranlı of one match",
)
def get_match_headline_record(match_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    return match_headline_record(db, match_id)
