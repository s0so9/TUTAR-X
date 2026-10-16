"""Odds and betting market domain models."""

from datetime import datetime
from typing import Optional, Dict
from pydantic import BaseModel, Field, field_validator


class Odds(BaseModel):
    """Betting odds for a match."""

    id: str = Field(..., description="Odds identifier")
    match_id: str = Field(..., description="Match identifier")
    bookmaker: str = Field(..., description="Bookmaker name")
    
    # Match result (1X2)
    home_win_odds: Optional[float] = Field(None, gt=1.0, description="Home win odds")
    draw_odds: Optional[float] = Field(None, gt=1.0, description="Draw odds")
    away_win_odds: Optional[float] = Field(None, gt=1.0, description="Away win odds")
    
    # Over/Under
    over_under_line: Optional[float] = Field(None, description="Over/under line (e.g., 2.5)")
    over_odds: Optional[float] = Field(None, gt=1.0, description="Over odds")
    under_odds: Optional[float] = Field(None, gt=1.0, description="Under odds")
    
    # Both Teams To Score
    btts_yes_odds: Optional[float] = Field(None, gt=1.0, description="BTTS yes odds")
    btts_no_odds: Optional[float] = Field(None, gt=1.0, description="BTTS no odds")
    
    # Asian Handicap
    asian_handicap_line: Optional[float] = Field(None, description="Asian handicap line")
    asian_handicap_home_odds: Optional[float] = Field(None, gt=1.0, description="Home handicap odds")
    asian_handicap_away_odds: Optional[float] = Field(None, gt=1.0, description="Away handicap odds")
    
    # Metadata
    fetched_at: datetime = Field(..., description="When odds were fetched")
    updated_at: Optional[datetime] = Field(None, description="Last odds update")
    
    # Phase 5: Market Intelligence fields
    source_provider: Optional[str] = Field(None, description="Data source provider (e.g., 'development', 'sofascore')")
    normalized_market_type: Optional[str] = Field(None, description="Normalized market type (e.g., 'match_result', 'over_under', 'btts')")
    selection_label: Optional[str] = Field(None, description="Selection label (e.g., 'home', 'draw', 'away', 'over', 'under')")
    odds_timestamp: Optional[datetime] = Field(None, description="Timestamp when these specific odds were published by bookmaker")
    
    class Config:
        """Pydantic configuration."""

        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "odds_123",
                "match_id": "match_123",
                "bookmaker": "Bet365",
                "home_win_odds": 2.10,
                "draw_odds": 3.40,
                "away_win_odds": 3.60,
                "over_under_line": 2.5,
                "over_odds": 1.90,
                "under_odds": 1.95,
                "fetched_at": "2026-10-03T10:00:00",
            }
        }
