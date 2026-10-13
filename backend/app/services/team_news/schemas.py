"""Pydantic response models of the team-news API.

Missing data is an explicit ``None`` plus a ``missing_reason`` code (see
``MISSING_REASON_LABELS_TR`` in constants / docs/live-layer.md), never 0.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    source: str = Field(..., description="Machine source key, e.g. fotmob_match_lineup")
    label: str = Field(..., description="Turkish label for the UI")
    observed_at: Optional[datetime] = Field(None, description="Latest observation used from this source (UTC)")


class TeamRef(BaseModel):
    team_id: Optional[str] = Field(None, description="Local teams.id (UUID); null when the team is not in the local DB")
    provider_id: Optional[str] = Field(None, description="FotMob team id")
    name: Optional[str] = None


class PlayerRef(BaseModel):
    player_id: Optional[str] = Field(None, description="Local players.id (UUID)")
    provider_id: str = Field(..., description="FotMob player id")
    name: Optional[str] = None
    shirt_number: Optional[int] = None
    position_id: Optional[int] = Field(None, description="FotMob pitch-slot id in this line-up (starters)")
    usual_position_id: Optional[int] = Field(None, description="FotMob usual role id: 0 GK, 1 DEF, 2 MID, 3 FWD")
    primary_position: Optional[str] = Field(None, description="Primary position label as sent by FotMob")


class FormCoverage(BaseModel):
    """How many appearances contributed to each sum (FotMob omits some values)."""

    minutes_apps: int = 0
    goals_apps: int = 0
    assists_apps: int = 0
    xg_apps: int = 0
    xg_zero_rule_apps: int = Field(
        0,
        description="Appearances counted as xG 0 because FotMob tracked shots in the match "
        "(shotmap present) and the player had none (documented zero rule)",
    )
    xa_apps: int = 0
    rated_apps: int = 0


class PlayerForm(BaseModel):
    """Player form over the team's last N finished matches before kickoff."""

    window_matches: int = Field(..., description="Team matches in the window (local DB, before kickoff)")
    matches_with_data: int = Field(..., description="Window matches with player-level data for this team")
    apps: Optional[int] = None
    starts: Optional[int] = None
    minutes: Optional[int] = None
    goals: Optional[int] = None
    assists: Optional[int] = None
    xg: Optional[float] = None
    xa: Optional[float] = None
    avg_rating: Optional[float] = None
    coverage: FormCoverage = Field(default_factory=FormCoverage)
    missing_reason: Optional[str] = None


class ContributionShare(BaseModel):
    """Share of the team's goals / xG / minutes over the window matches with data."""

    matches_used: int = 0
    player_goals: Optional[int] = None
    team_goals: Optional[int] = None
    goals_share: Optional[float] = None
    player_xg: Optional[float] = None
    team_xg: Optional[float] = None
    xg_share: Optional[float] = None
    player_minutes: Optional[int] = None
    team_minutes: Optional[int] = Field(
        None, description="Sum over matches of the longest minutes_played of any team player (match length as FotMob counts it)"
    )
    minutes_share: Optional[float] = None
    missing_reason: Optional[str] = None


class LineupPlayer(PlayerRef):
    form: PlayerForm


class SideLineup(BaseModel):
    snapshot_id: str
    lineup_type: Optional[str] = Field(None, description="As sent by FotMob: predicted / standard / lastStarting11 / ...")
    lineup_status: str = Field(
        ..., description="Derived from lineup_type: confirmed | predicted | last_match_xi (placeholder XI of the previous match) | other"
    )
    lineup_type_label: Optional[str] = None
    lineup_source: Optional[str] = None
    based_on_match_id: Optional[str] = Field(
        None, description="lastStarting11 only: FotMob id of the earlier match the XI was copied from"
    )
    formation: Optional[str] = None
    observed_at: datetime
    last_observed_at: datetime
    timestamp_basis: str
    starters: list[LineupPlayer]
    bench: Optional[list[PlayerRef]] = None


class AvailabilityReport(BaseModel):
    id: str
    source: str
    status: str
    raw_type: Optional[str] = None
    reason: Optional[str] = None
    injury_id: Optional[str] = None
    expected_return: Optional[str] = None
    expected_return_date: Optional[str] = None
    first_observed_at: datetime
    last_observed_at: datetime
    timestamp_basis: str
    source_updated_at: Optional[datetime] = None


class Absentee(BaseModel):
    player: PlayerRef
    status: str
    status_label: str
    raw_type: Optional[str] = None
    reason: Optional[str] = None
    expected_return: Optional[str] = None
    expected_return_date: Optional[str] = None
    primary_source: str
    reports: list[AvailabilityReport]
    listed_in_lineup: bool = Field(
        False, description="True when the same player is also a starter in the latest line-up snapshot (sources disagree)"
    )
    form: PlayerForm
    share: ContributionShare


class TeamLast5Match(BaseModel):
    match_id: str
    provider_match_id: Optional[str] = None
    kickoff_at: Optional[datetime] = None
    competition_provider_id: Optional[str] = None
    competition_name: Optional[str] = None
    venue: str = Field(..., description="home / away from this team's perspective")
    opponent: TeamRef
    goals_for: Optional[int] = None
    goals_against: Optional[int] = None
    result: Optional[str] = Field(None, description="W / D / L; null when the score is missing")
    xg_for: Optional[float] = None
    xg_against: Optional[float] = None
    player_data: bool = Field(False, description="player_match_stats rows exist for this team in this match")


class TeamLast5(BaseModel):
    matches: list[TeamLast5Match] = Field(default_factory=list)
    played: int = 0
    wins: Optional[int] = None
    draws: Optional[int] = None
    losses: Optional[int] = None
    goals_for: Optional[int] = None
    goals_against: Optional[int] = None
    xg_for: Optional[float] = None
    xg_against: Optional[float] = None
    xg_matches: int = 0
    missing_reason: Optional[str] = None


class SideFreshness(BaseModel):
    lineup_observed_at: Optional[datetime] = None
    match_unavailable_observed_at: Optional[datetime] = None
    squad_observed_at: Optional[datetime] = None
    player_profiles_observed_at: Optional[datetime] = None
    player_match_stats_fetched_at: Optional[datetime] = None
    last_team_match_at: Optional[datetime] = None


class SideTeamNews(BaseModel):
    side: str
    team: TeamRef
    lineup: Optional[SideLineup] = None
    lineup_missing_reason: Optional[str] = None
    absentees: list[Absentee] = Field(default_factory=list)
    absentees_missing_reason: Optional[str] = Field(
        None, description="Set when no availability source was observed for this side (empty list is then unknown, not 'all fit')"
    )
    last5: TeamLast5
    freshness: SideFreshness


class MatchInfo(BaseModel):
    requested_id: str
    provider_match_id: Optional[str] = None
    match_id: Optional[str] = Field(None, description="Local matches.id when the match is in the local DB")
    competition_provider_id: Optional[str] = None
    kickoff_at: Optional[datetime] = None
    status: Optional[str] = None
    as_of: datetime = Field(..., description="Point in time the availability/form were evaluated at (kickoff for started matches)")
    home: TeamRef
    away: TeamRef


class TeamNewsResponse(BaseModel):
    match: MatchInfo
    home: SideTeamNews
    away: SideTeamNews
    sources: list[SourceRef]
    generated_at: datetime
    is_development_data: bool = False
    notes: list[str] = Field(default_factory=list)


class SquadPlayer(BaseModel):
    player_id: str
    provider_id: str
    name: Optional[str] = None
    shirt_number: Optional[int] = None
    role: Optional[str] = None
    role_key: Optional[str] = None
    position: Optional[str] = None
    primary_position: Optional[str] = None
    positions: Optional[list[dict[str, Any]]] = None
    date_of_birth: Optional[str] = None
    nationality: Optional[str] = None
    country_code: Optional[str] = None
    height_cm: Optional[int] = None
    preferred_foot: Optional[str] = None
    market_value_eur: Optional[int] = None
    market_value_as_of: Optional[datetime] = None
    market_value_source: Optional[str] = None
    contract_end: Optional[str] = None
    first_seen_at: datetime
    last_seen_at: datetime
    in_latest_squad: bool
    availability_status: str = Field(
        ..., description="'unavailable' when an active report exists, else 'no_report' (not a fitness guarantee)"
    )
    availability: list[AvailabilityReport] = Field(default_factory=list)


class TeamSquadResponse(BaseModel):
    team: TeamRef
    season: Optional[str] = None
    squad_observed_at: Optional[datetime] = None
    players: list[SquadPlayer] = Field(default_factory=list)
    missing_reason: Optional[str] = None
    sources: list[SourceRef] = Field(default_factory=list)
    generated_at: datetime
    is_development_data: bool = False
