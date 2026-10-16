"""Pydantic models of GET /api/v1/matches/{match_id}/preview ("Maç analizi").

Every number is a count or sum of real results / FotMob fields; nothing is
estimated. Unknown values are ``null`` with a ``missing_reason`` (never 0).
Result letters are Turkish: G = galibiyet, B = beraberlik, M = mağlubiyet.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Venue = Literal["home", "away"]
ResultLetter = Literal["G", "B", "M"]
MatchSource = Literal["database", "fotmob_team_fixtures"]
LineupType = Literal["confirmed", "predicted", "last_starting11"]


class PreviewMatch(BaseModel):
    """One played match of a team, seen from that team."""

    match_id: Optional[str] = Field(None, description="FotMob match id when known")
    date: datetime = Field(..., description="Kick-off, UTC")
    competition: Optional[str] = None
    is_friendly: bool = False
    venue: Venue = Field(..., description="Where THIS team played: home or away")
    opponent: Optional[str] = None
    opponent_id: Optional[str] = None
    goals_for: Optional[int] = None
    goals_against: Optional[int] = None
    result: Optional[ResultLetter] = None
    xg_for: Optional[float] = Field(None, description="null unless the source has xG for BOTH sides")
    xg_against: Optional[float] = None
    source: MatchSource = "database"


class FormWindow(BaseModel):
    """Last-N (default 5) matches of one team; friendlies are not part of it."""

    scope: Literal["last5", "last5_venue"]
    venue: Optional[Venue] = Field(None, description="last5_venue only: the venue the matches were played at")
    played: int = 0
    results: Optional[str] = Field(None, description="Most recent first, e.g. 'GGBMG'; null without matches")
    wins: Optional[int] = None
    draws: Optional[int] = None
    losses: Optional[int] = None
    goals_for: Optional[int] = None
    goals_against: Optional[int] = None
    xg_for: Optional[float] = Field(None, description="Sum over the matches that have xG (see xg_matches)")
    xg_against: Optional[float] = None
    xg_matches: int = Field(0, description="How many of the matches had xG")
    xg_missing_reason: Optional[str] = None
    matches: list[PreviewMatch] = Field(default_factory=list, description="Most recent first")
    missing_reason: Optional[str] = None


class RestInfo(BaseModel):
    previous_match: Optional[PreviewMatch] = None
    rest_days: Optional[int] = Field(None, description="Calendar days (UTC dates) between the previous match and kick-off")
    matches_last_14_days: Optional[int] = Field(None, description="Matches played in the 14 days before kick-off (friendlies included)")
    missing_reason: Optional[str] = None


class Absentee(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    reason: Optional[str] = Field(None, description="Turkish label of the FotMob reason")
    reason_code: Optional[str] = Field(None, description="FotMob reason code (injury, suspension, doubtful ...)")
    expected_return: Optional[str] = Field(None, description="As FotMob sends it, e.g. 'Mid October 2026'")
    expected_return_date: Optional[str] = None
    started_previous_match: Optional[bool] = Field(
        None, description="True when the player was in the previous match's starting XI; null when that XI is unknown"
    )


class AbsenteesInfo(BaseModel):
    available: bool = Field(..., description="False when the source sent no availability data for the team")
    players: list[Absentee] = Field(default_factory=list)
    missing_reason: Optional[str] = None


class PlayerRef(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None


class RotationInfo(BaseModel):
    """How many of today's starters were not in the previous match's starting XI."""

    previous_match: Optional[PreviewMatch] = None
    previous_xi_source: Optional[Literal["local_raw_cache", "fotmob_match_details"]] = None
    changes: Optional[int] = None
    came_in: list[PlayerRef] = Field(default_factory=list)
    dropped_out: list[PlayerRef] = Field(default_factory=list)
    missing_reason: Optional[str] = None


class LineupInfo(BaseModel):
    lineup_type: Optional[LineupType] = None
    formation: Optional[str] = None
    starters_count: int = 0
    rotation: RotationInfo = Field(default_factory=RotationInfo)
    missing_reason: Optional[str] = None


class PreviewSide(BaseModel):
    team_id: Optional[str] = None
    team_name: Optional[str] = None
    last5: FormWindow
    venue_last5: FormWindow
    rest: RestInfo
    absentees: AbsenteesInfo
    lineup: LineupInfo
    history_verified: bool = Field(
        True,
        description="False when the local database may lag behind the team's real last match and FotMob could not confirm it: "
        "no history-based highlight is written then and rest days are null",
    )
    data_notes: list[str] = Field(default_factory=list, description="Data-quality notes (database lag, gap fill ...)")


class Highlight(BaseModel):
    id: str
    kind: str
    side: Literal["home", "away", "both"]
    text: str = Field(..., description="Turkish sentence from a fixed template; the numbers are in the text")
    importance: int
    facts: dict[str, Any] = Field(default_factory=dict, description="The numbers the sentence is based on")


class MatchPreviewResponse(BaseModel):
    match_id: str
    provider_match_id: Optional[str] = None
    generated_at: datetime
    kickoff: Optional[datetime] = None
    status: Optional[str] = None
    competition: Optional[str] = None
    home: PreviewSide
    away: PreviewSide
    highlights: list[Highlight] = Field(default_factory=list)
    database_latest_match_at: Optional[datetime] = Field(
        None, description="Newest finished match in the local database (it can lag behind real life)"
    )
    sources: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
