"""Pydantic models of GET /api/v1/matches/{match_id}/live-center (shared contract).

Contract fields are listed in docs/live-center-data-sources.md. Fields marked
"additive" extend the shared contract without changing it. Missing data is
``null`` (never 0) and, per section, an entry in ``missing``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field

Side = Literal["home", "away"]
Number = Union[int, float]


class ScorePair(BaseModel):
    home: Optional[int] = None
    away: Optional[int] = None


class TeamInfo(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    short_name: Optional[str] = None
    logo_url: Optional[str] = None


class Teams(BaseModel):
    home: TeamInfo
    away: TeamInfo


class PersonRef(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None


class LiveEvent(BaseModel):
    id: str
    minute: Optional[int] = None
    added_time: Optional[int] = None
    period: Optional[str] = None
    side: Optional[Side] = Field(
        None,
        description="Team the event counts for. Own goal: the team that benefits (its score went up); "
        "the own-goal scorer is in 'player'. period_end: null.",
    )
    type: str
    player: Optional[PersonRef] = None
    assist: Optional[PersonRef] = None
    player_in: Optional[PersonRef] = None
    player_out: Optional[PersonRef] = None
    score_after: Optional[ScorePair] = None
    detail: Optional[str] = None


class GridPos(BaseModel):
    row: int = Field(..., description="0 = goalkeeper line, increasing towards the attack")
    col: int = Field(..., description="0 = the team's left flank (team attacking upwards), increasing to the right")
    rows_in_formation: int
    cols_in_row: Optional[int] = Field(None, description="additive: players in this row")


class LineupPlayer(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    shirt: Optional[int] = None
    position: Optional[Literal["GK", "DEF", "MID", "FWD"]] = None
    grid: Optional[GridPos] = None
    captain: bool = False
    rating: Optional[float] = None
    goals: Optional[int] = None
    assists: Optional[int] = None
    yellow: Optional[int] = None
    red: Optional[int] = None
    sub_out_minute: Optional[int] = None
    sub_in_minute: Optional[int] = None
    position_id: Optional[int] = Field(None, description="additive: FotMob pitch-slot id")


class UnavailablePlayer(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    reason: Optional[str] = Field(None, description="Turkish label of the source reason")
    reason_code: Optional[str] = Field(None, description="additive: source reason code (injury, suspension, ...)")
    expected_return: Optional[str] = Field(None, description="Source text, e.g. 'Mid October 2026'")
    expected_return_date: Optional[str] = Field(None, description="additive: source ISO date when sent")


class TeamLineup(BaseModel):
    formation: Optional[str] = None
    lineup_type: Optional[Literal["confirmed", "predicted", "last_starting11"]] = None
    coach: Optional[PersonRef] = None
    starters: list[LineupPlayer] = Field(default_factory=list)
    substitutes: list[LineupPlayer] = Field(default_factory=list)
    unavailable: list[UnavailablePlayer] = Field(default_factory=list)


class Lineups(BaseModel):
    home: TeamLineup
    away: TeamLineup


class StatEntry(BaseModel):
    key: str
    label_tr: str
    group: str
    home: Optional[Number] = None
    away: Optional[Number] = None
    unit: Literal["count", "percent", "decimal"]
    home_text: Optional[str] = None
    away_text: Optional[str] = None


class Stats(BaseModel):
    all: list[StatEntry] = Field(default_factory=list)
    first_half: Optional[list[StatEntry]] = None
    second_half: Optional[list[StatEntry]] = None


class Shot(BaseModel):
    minute: Optional[int] = None
    added_time: Optional[int] = Field(None, description="additive")
    side: Optional[Side] = None
    player: Optional[PersonRef] = None
    x: Optional[float] = Field(None, description="metres 0-105 along the pitch; the shooting team attacks towards 105")
    y: Optional[float] = Field(None, description="metres 0-68 across the pitch")
    xg: Optional[float] = None
    xgot: Optional[float] = Field(None, description="only for shots on target (saved or goal); null otherwise")
    outcome: Optional[Literal["goal", "saved", "missed", "blocked", "post"]] = None
    situation: Optional[str] = Field(None, description="source code, e.g. RegularPlay")
    situation_tr: Optional[str] = Field(None, description="additive")
    body_part: Optional[str] = Field(None, description="source code, e.g. RightFoot")
    body_part_tr: Optional[str] = Field(None, description="additive")
    is_own_goal: bool = Field(False, description="additive")
    period: Optional[str] = Field(None, description="additive: 1H/2H/ET")


class MomentumPoint(BaseModel):
    minute: Number
    value: Number = Field(..., description="source value, positive = home pressure, negative = away")


class MissingSection(BaseModel):
    section: str
    reason: str
    message_tr: Optional[str] = Field(None, description="additive: Turkish explanation")


class LiveCenterResponse(BaseModel):
    match_id: str
    provider: str = "fotmob"
    provider_match_id: Optional[str] = Field(None, description="additive: FotMob match id")
    fetched_at: datetime
    cache_ttl_seconds: int
    status: str
    status_text: Optional[str] = Field(None, description="additive: source status text, e.g. 'HT', '23'', 'FT'")
    minute: Optional[int] = None
    added_time: Optional[int] = None
    period: Optional[str] = None
    kickoff: Optional[datetime] = None
    competition: Optional[str] = Field(None, description="additive: source competition name")
    competition_id: Optional[str] = Field(None, description="additive: FotMob parent league id (e.g. 42)")
    round: Optional[str] = Field(None, description="additive: source round name")
    venue: Optional[str] = None
    venue_city: Optional[str] = Field(None, description="additive")
    referee: Optional[str] = None
    attendance: Optional[int] = None
    score: ScorePair
    halftime_score: Optional[ScorePair] = None
    penalty_score: Optional[ScorePair] = None
    teams: Teams
    events: list[LiveEvent] = Field(default_factory=list)
    lineups: Lineups
    stats: Stats
    shotmap: Optional[list[Shot]] = None
    momentum: Optional[list[MomentumPoint]] = None
    missing: list[MissingSection] = Field(default_factory=list)
    source_note: str = Field(
        "Veri kaynağı: FotMob (resmi olmayan, herkese açık JSON). Değerler kaynağın gönderdiği gibidir.",
        description="additive: data-source note for the UI",
    )
