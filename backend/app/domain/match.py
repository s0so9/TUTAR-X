"""Match-related domain models."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

from app.domain.base import BaseEntity
from app.domain.enums import MatchStatus, MatchEventType, MatchOutcome


class Match(BaseEntity):
    """Football match."""

    competition_id: str = Field(..., description="Competition identifier")
    season_id: str = Field(..., description="Season identifier")
    home_team_id: str = Field(..., description="Home team identifier")
    away_team_id: str = Field(..., description="Away team identifier")
    venue_id: Optional[str] = Field(None, description="Venue identifier")
    
    scheduled_at: datetime = Field(..., description="Scheduled kickoff time")
    status: MatchStatus = Field(MatchStatus.SCHEDULED, description="Match status")
    
    # Scores
    home_score: Optional[int] = Field(None, description="Home team score")
    away_score: Optional[int] = Field(None, description="Away team score")
    home_score_ht: Optional[int] = Field(None, description="Home team half-time score")
    away_score_ht: Optional[int] = Field(None, description="Away team half-time score")
    
    # Timing
    minute: Optional[int] = Field(None, description="Current match minute")
    added_time: Optional[int] = Field(None, description="Added time in minutes")
    
    # Outcome
    outcome: Optional[MatchOutcome] = Field(None, description="Match outcome")
    
    # Match round/week
    round: Optional[int] = Field(None, description="Match round/gameweek")
    
    # Data freshness
    provider_fetched_at: Optional[datetime] = Field(None, description="When data was last fetched from provider")
    
    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "id": "match_123",
                "competition_id": "comp_premier_league",
                "season_id": "season_2023_2024",
                "home_team_id": "team_manchester_united",
                "away_team_id": "team_liverpool",
                "scheduled_at": "2026-10-05T15:00:00",
                "status": "scheduled",
                "round": 7,
            }
        }


class MatchEvent(BaseModel):
    """Match event (goal, card, substitution, etc.)."""

    id: str = Field(..., description="Event identifier")
    match_id: str = Field(..., description="Match identifier")
    type: MatchEventType = Field(..., description="Event type")
    minute: int = Field(..., description="Event minute")
    added_time: Optional[int] = Field(None, description="Added time")
    team_id: str = Field(..., description="Team identifier")
    player_id: Optional[str] = Field(None, description="Player identifier")
    related_player_id: Optional[str] = Field(None, description="Related player (assist, substituted player)")
    description: Optional[str] = Field(None, description="Event description")
    
    class Config:
        """Pydantic configuration."""

        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "event_goal_123",
                "match_id": "match_123",
                "type": "goal",
                "minute": 34,
                "team_id": "team_manchester_united",
                "player_id": "player_123",
                "related_player_id": "player_456",  # Assist
            }
        }


class Lineup(BaseModel):
    """Match lineup."""

    id: str = Field(..., description="Lineup identifier")
    match_id: str = Field(..., description="Match identifier")
    team_id: str = Field(..., description="Team identifier")
    formation: Optional[str] = Field(None, description="Formation (e.g., '4-3-3')")
    starting_xi: List[str] = Field(default_factory=list, description="Starting XI player IDs")
    substitutes: List[str] = Field(default_factory=list, description="Substitute player IDs")
    coach: Optional[str] = Field(None, description="Coach name")
    
    class Config:
        """Pydantic configuration."""

        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "lineup_123",
                "match_id": "match_123",
                "team_id": "team_manchester_united",
                "formation": "4-3-3",
                "starting_xi": ["player_1", "player_2", "player_3"],
                "substitutes": ["player_4", "player_5"],
            }
        }
