"""Statistics domain models."""

from typing import Optional
from pydantic import BaseModel, Field


class PlayerMatchStatistic(BaseModel):
    """Player statistics for a specific match."""

    id: str = Field(..., description="Statistic identifier")
    match_id: str = Field(..., description="Match identifier")
    player_id: str = Field(..., description="Player identifier")
    team_id: str = Field(..., description="Team identifier")
    
    # Appearance
    minutes_played: int = Field(0, ge=0, le=120, description="Minutes played")
    started: bool = Field(False, description="Started the match")
    substituted_on: Optional[int] = Field(None, description="Minute substituted on")
    substituted_off: Optional[int] = Field(None, description="Minute substituted off")
    
    # Goals and assists
    goals: int = Field(0, ge=0, description="Goals scored")
    assists: int = Field(0, ge=0, description="Assists")
    
    # Expected
    xg: Optional[float] = Field(None, ge=0.0, description="Expected goals")
    xa: Optional[float] = Field(None, ge=0.0, description="Expected assists")
    
    # Shots
    shots_total: Optional[int] = Field(None, ge=0, description="Total shots")
    shots_on_target: Optional[int] = Field(None, ge=0, description="Shots on target")
    
    # Passing
    passes_completed: Optional[int] = Field(None, ge=0, description="Passes completed")
    passes_attempted: Optional[int] = Field(None, ge=0, description="Passes attempted")
    key_passes: Optional[int] = Field(None, ge=0, description="Key passes")
    
    # Defensive
    tackles: Optional[int] = Field(None, ge=0, description="Tackles")
    interceptions: Optional[int] = Field(None, ge=0, description="Interceptions")
    clearances: Optional[int] = Field(None, ge=0, description="Clearances")
    
    # Discipline
    yellow_cards: int = Field(0, ge=0, description="Yellow cards")
    red_cards: int = Field(0, ge=0, description="Red cards")
    fouls_committed: Optional[int] = Field(None, ge=0, description="Fouls committed")
    fouls_drawn: Optional[int] = Field(None, ge=0, description="Fouls drawn")
    
    # Rating
    rating: Optional[float] = Field(None, ge=0.0, le=10.0, description="Player rating")
    
    class Config:
        """Pydantic configuration."""

        from_attributes = True


class TeamMatchStatistic(BaseModel):
    """Team statistics for a specific match."""

    id: str = Field(..., description="Statistic identifier")
    match_id: str = Field(..., description="Match identifier")
    team_id: str = Field(..., description="Team identifier")
    
    # Goals
    goals_scored: int = Field(0, ge=0, description="Goals scored")
    goals_conceded: int = Field(0, ge=0, description="Goals conceded")
    
    # Expected goals
    xg: Optional[float] = Field(None, ge=0.0, description="Expected goals")
    xg_against: Optional[float] = Field(None, ge=0.0, description="Expected goals against")
    
    # Shots
    shots_total: Optional[int] = Field(None, ge=0, description="Total shots")
    shots_on_target: Optional[int] = Field(None, ge=0, description="Shots on target")
    shots_off_target: Optional[int] = Field(None, ge=0, description="Shots off target")
    shots_blocked: Optional[int] = Field(None, ge=0, description="Shots blocked")
    
    # Possession
    possession_percentage: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Possession percentage"
    )
    
    # Passing
    passes_completed: Optional[int] = Field(None, ge=0, description="Passes completed")
    passes_attempted: Optional[int] = Field(None, ge=0, description="Passes attempted")
    pass_accuracy: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Pass accuracy percentage"
    )
    
    # Set pieces
    corners: Optional[int] = Field(None, ge=0, description="Corners")
    free_kicks: Optional[int] = Field(None, ge=0, description="Free kicks")
    offsides: Optional[int] = Field(None, ge=0, description="Offsides")
    
    # Discipline
    yellow_cards: int = Field(0, ge=0, description="Yellow cards")
    red_cards: int = Field(0, ge=0, description="Red cards")
    fouls_committed: Optional[int] = Field(None, ge=0, description="Fouls committed")
    
    # Defensive
    tackles: Optional[int] = Field(None, ge=0, description="Tackles")
    interceptions: Optional[int] = Field(None, ge=0, description="Interceptions")
    clearances: Optional[int] = Field(None, ge=0, description="Clearances")
    saves: Optional[int] = Field(None, ge=0, description="Goalkeeper saves")
    
    class Config:
        """Pydantic configuration."""

        from_attributes = True


class Standing(BaseModel):
    """League standing/table entry."""

    id: str = Field(..., description="Standing identifier")
    competition_id: str = Field(..., description="Competition identifier")
    season_id: str = Field(..., description="Season identifier")
    team_id: str = Field(..., description="Team identifier")
    
    position: int = Field(..., ge=1, description="Table position")
    played: int = Field(0, ge=0, description="Matches played")
    won: int = Field(0, ge=0, description="Matches won")
    drawn: int = Field(0, ge=0, description="Matches drawn")
    lost: int = Field(0, ge=0, description="Matches lost")
    
    goals_for: int = Field(0, ge=0, description="Goals scored")
    goals_against: int = Field(0, ge=0, description="Goals conceded")
    goal_difference: int = Field(0, description="Goal difference")
    
    points: int = Field(0, ge=0, description="Points")
    
    # Home/away splits
    home_played: Optional[int] = Field(None, ge=0, description="Home matches played")
    home_won: Optional[int] = Field(None, ge=0, description="Home matches won")
    away_played: Optional[int] = Field(None, ge=0, description="Away matches played")
    away_won: Optional[int] = Field(None, ge=0, description="Away matches won")
    
    # Form
    form: Optional[str] = Field(None, description="Recent form (e.g., 'WWDLL')")
    
    class Config:
        """Pydantic configuration."""

        from_attributes = True
