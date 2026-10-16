"""Live match state domain models."""

from datetime import datetime
from typing import Optional, Dict
from pydantic import BaseModel, Field

from app.domain.enums import MatchStatus


class LiveMatchState(BaseModel):
    """Current state of a live match."""

    id: str = Field(..., description="Live state identifier")
    match_id: str = Field(..., description="Match identifier")
    
    # Status
    status: MatchStatus = Field(..., description="Current match status")
    minute: int = Field(..., ge=0, description="Current minute")
    added_time: Optional[int] = Field(None, ge=0, description="Added time")
    
    # Score
    home_score: int = Field(0, ge=0, description="Home team score")
    away_score: int = Field(0, ge=0, description="Away team score")
    
    # Live statistics
    home_shots: Optional[int] = Field(None, ge=0, description="Home team shots")
    away_shots: Optional[int] = Field(None, ge=0, description="Away team shots")
    home_shots_on_target: Optional[int] = Field(None, ge=0, description="Home shots on target")
    away_shots_on_target: Optional[int] = Field(None, ge=0, description="Away shots on target")
    
    home_possession: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Home possession percentage"
    )
    away_possession: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Away possession percentage"
    )
    
    home_corners: Optional[int] = Field(None, ge=0, description="Home corners")
    away_corners: Optional[int] = Field(None, ge=0, description="Away corners")
    
    home_yellow_cards: int = Field(0, ge=0, description="Home yellow cards")
    away_yellow_cards: int = Field(0, ge=0, description="Away yellow cards")
    home_red_cards: int = Field(0, ge=0, description="Home red cards")
    away_red_cards: int = Field(0, ge=0, description="Away red cards")
    
    # Live xG
    home_xg: Optional[float] = Field(None, ge=0.0, description="Home live xG")
    away_xg: Optional[float] = Field(None, ge=0.0, description="Away live xG")
    
    # Momentum indicators
    momentum: Optional[str] = Field(
        None, description="Momentum indicator (home, away, neutral)"
    )
    dangerous_attacks_home: Optional[int] = Field(None, ge=0, description="Home dangerous attacks")
    dangerous_attacks_away: Optional[int] = Field(None, ge=0, description="Away dangerous attacks")
    
    # Timestamps
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    class Config:
        """Pydantic configuration."""

        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "live_state_123",
                "match_id": "match_123",
                "status": "live",
                "minute": 34,
                "home_score": 1,
                "away_score": 0,
                "home_shots": 8,
                "away_shots": 4,
                "home_possession": 58.0,
                "away_possession": 42.0,
                "updated_at": "2026-10-05T15:34:00",
            }
        }


class FeatureSnapshot(BaseModel):
    """Feature values snapshot for a match or team at a point in time."""

    id: str = Field(..., description="Snapshot identifier")
    match_id: Optional[str] = Field(None, description="Match identifier")
    team_id: Optional[str] = Field(None, description="Team identifier")
    
    snapshot_at: datetime = Field(..., description="Snapshot timestamp")
    
    # Feature values (flexible structure)
    features: Dict[str, float] = Field(..., description="Feature name to value mapping")
    
    # Metadata
    feature_set_version: Optional[str] = Field(None, description="Feature set version")
    
    class Config:
        """Pydantic configuration."""

        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "snapshot_123",
                "match_id": "match_123",
                "team_id": "team_manchester_united",
                "snapshot_at": "2026-10-05T14:00:00",
                "features": {
                    "attack_strength": 1.45,
                    "defense_strength": 0.92,
                    "form_last_5": 2.4,
                    "home_advantage": 0.35,
                },
                "feature_set_version": "v1.0",
            }
        }
