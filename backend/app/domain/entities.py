"""Core football entities."""

from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field

from app.domain.base import BaseEntity


class Competition(BaseEntity):
    """Football competition/league."""

    name: str = Field(..., description="Competition name")
    country: Optional[str] = Field(None, description="Country code")
    level: Optional[int] = Field(None, description="Competition level/tier")
    type: Optional[str] = Field(None, description="Competition type (league, cup, etc.)")

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "id": "comp_premier_league",
                "name": "Premier League",
                "country": "ENG",
                "level": 1,
                "type": "league",
            }
        }


class Season(BaseEntity):
    """Football season."""

    competition_id: str = Field(..., description="Competition identifier")
    year: str = Field(..., description="Season year (e.g., '2023/2024')")
    start_date: Optional[date] = Field(None, description="Season start date")
    end_date: Optional[date] = Field(None, description="Season end date")
    is_current: bool = Field(False, description="Whether this is the current season")

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "id": "season_2023_2024",
                "competition_id": "comp_premier_league",
                "year": "2023/2024",
                "start_date": "2023-08-11",
                "end_date": "2024-05-19",
                "is_current": True,
            }
        }


class Team(BaseEntity):
    """Football team."""

    name: str = Field(..., description="Team name")
    short_name: Optional[str] = Field(None, description="Team short name")
    code: Optional[str] = Field(None, description="Team code (3 letters)")
    country: Optional[str] = Field(None, description="Country code")
    founded: Optional[int] = Field(None, description="Year founded")
    venue_id: Optional[str] = Field(None, description="Home venue identifier")
    logo_url: Optional[str] = Field(None, description="Team logo URL")

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "id": "team_manchester_united",
                "name": "Manchester United",
                "short_name": "Man United",
                "code": "MUN",
                "country": "ENG",
                "founded": 1878,
            }
        }


class Player(BaseEntity):
    """Football player."""

    name: str = Field(..., description="Player name")
    date_of_birth: Optional[date] = Field(None, description="Date of birth")
    nationality: Optional[str] = Field(None, description="Nationality code")
    position: Optional[str] = Field(None, description="Position")
    shirt_number: Optional[int] = Field(None, description="Shirt number")
    team_id: Optional[str] = Field(None, description="Current team identifier")
    height_cm: Optional[int] = Field(None, description="Height in centimeters")
    weight_kg: Optional[int] = Field(None, description="Weight in kilograms")
    photo_url: Optional[str] = Field(None, description="Player photo URL")

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "id": "player_123",
                "name": "John Doe",
                "date_of_birth": "1995-05-15",
                "nationality": "ENG",
                "position": "Forward",
                "shirt_number": 10,
            }
        }


class Venue(BaseEntity):
    """Football venue/stadium."""

    name: str = Field(..., description="Venue name")
    city: Optional[str] = Field(None, description="City")
    country: Optional[str] = Field(None, description="Country code")
    capacity: Optional[int] = Field(None, description="Stadium capacity")
    surface: Optional[str] = Field(None, description="Playing surface type")
    address: Optional[str] = Field(None, description="Address")

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "id": "venue_old_trafford",
                "name": "Old Trafford",
                "city": "Manchester",
                "country": "ENG",
                "capacity": 74879,
                "surface": "Grass",
            }
        }
