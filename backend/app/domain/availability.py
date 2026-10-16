"""Player availability domain models."""

from datetime import date
from typing import Optional
from pydantic import BaseModel, Field

from app.domain.enums import InjuryStatus, SuspensionType


class Injury(BaseModel):
    """Player injury record."""

    id: str = Field(..., description="Injury identifier")
    player_id: str = Field(..., description="Player identifier")
    team_id: str = Field(..., description="Team identifier")
    
    injury_type: str = Field(..., description="Type of injury")
    status: InjuryStatus = Field(..., description="Injury status")
    
    start_date: date = Field(..., description="Injury start date")
    expected_return_date: Optional[date] = Field(None, description="Expected return date")
    actual_return_date: Optional[date] = Field(None, description="Actual return date")
    
    description: Optional[str] = Field(None, description="Injury description")
    severity: Optional[str] = Field(None, description="Injury severity")
    
    class Config:
        """Pydantic configuration."""

        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "injury_123",
                "player_id": "player_123",
                "team_id": "team_manchester_united",
                "injury_type": "Hamstring",
                "status": "out",
                "start_date": "2026-09-15",
                "expected_return_date": "2026-10-15",
            }
        }


class Suspension(BaseModel):
    """Player suspension record."""

    id: str = Field(..., description="Suspension identifier")
    player_id: str = Field(..., description="Player identifier")
    team_id: str = Field(..., description="Team identifier")
    competition_id: Optional[str] = Field(None, description="Competition identifier")
    
    type: SuspensionType = Field(..., description="Suspension type")
    
    start_date: date = Field(..., description="Suspension start date")
    end_date: date = Field(..., description="Suspension end date")
    
    matches_remaining: int = Field(0, ge=0, description="Matches remaining in suspension")
    total_matches: int = Field(1, ge=1, description="Total suspension matches")
    
    reason: Optional[str] = Field(None, description="Suspension reason")
    
    class Config:
        """Pydantic configuration."""

        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "suspension_123",
                "player_id": "player_123",
                "team_id": "team_manchester_united",
                "type": "red_card",
                "start_date": "2026-10-01",
                "end_date": "2026-10-15",
                "matches_remaining": 2,
                "total_matches": 3,
            }
        }
