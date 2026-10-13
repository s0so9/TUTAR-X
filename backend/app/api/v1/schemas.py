"""API response schemas for version 1.

These schemas define the contract for API responses.
They are separate from domain models to allow flexibility
in API versioning without changing internal domain structures.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from app.domain.enums import MatchStatus, MatchOutcome


class MarketOutcomeResponse(BaseModel):
    """Market outcome response schema."""

    label: str = Field(..., description="Outcome label")
    model_probability: float = Field(..., description="Raw model probability")
    calibrated_probability: Optional[float] = Field(None, description="Calibrated probability")
    fair_odds: float = Field(..., description="Fair decimal odds")

    # Phase 5: Market Intelligence fields (all optional for backward compatibility)
    real_odds: Optional[float] = Field(None, description="Real bookmaker odds if available")
    implied_probability: Optional[float] = Field(None, description="Implied probability from real odds")
    market_edge: Optional[float] = Field(None, description="Market edge (implied_prob - model_prob)")
    bookmaker: Optional[str] = Field(None, description="Bookmaker source")
    odds_timestamp: Optional[datetime] = Field(None, description="When odds were recorded")

    # Odds & Value Intelligence fields (all optional for backward compatibility)
    expected_value: Optional[float] = Field(None, description="Expected value of this outcome")
    expected_value_percent: Optional[float] = Field(None, description="Expected value as percentage")
    value_classification: Optional[str] = Field(None, description="Value classification (NO_VALUE, LOW_VALUE, VALUE, STRONG_VALUE, MODEL_MARKET_CONFLICT = model implausibly far above the market; never value, value_score 0)")
    value_score: Optional[float] = Field(None, description="Normalized value score 0-1")

    class Config:
        """Pydantic configuration."""
        # Suppress warnings about model_* field names conflicting with Pydantic's namespace
        protected_namespaces = ()


class BookmakerComparisonResponse(BaseModel):
    """Bookmaker comparison response schema."""

    label: str = Field(..., description="Outcome label")
    fair_probability: float = Field(..., description="Fair probability from model")
    fair_odds: float = Field(..., description="Fair decimal odds")
    bookmaker_odds: float = Field(..., description="Bookmaker decimal odds")
    implied_probability: float = Field(..., description="Implied probability from bookmaker odds")
    edge_value: float = Field(..., description="Edge (implied - fair probability)")
    has_value_flag: bool = Field(..., description="Whether this outcome has betting value (always False for MODEL_MARKET_CONFLICT)")

    # Odds & Value Intelligence fields (all optional for backward compatibility)
    expected_value: Optional[float] = Field(None, description="Expected value of this outcome")
    expected_value_percent: Optional[float] = Field(None, description="Expected value as percentage")
    value_classification: Optional[str] = Field(None, description="Value classification (NO_VALUE, LOW_VALUE, VALUE, STRONG_VALUE, MODEL_MARKET_CONFLICT = model implausibly far above the market; never value, value_score 0)")
    value_score: Optional[float] = Field(None, description="Normalized value score 0-1")


class MarketAnalysisResponse(BaseModel):
    """Market analysis response schema."""

    market_type: str = Field(..., description="Market type (e.g., match_result, btts)")
    line: Optional[float] = Field(None, description="Over/Under line if applicable")
    outcomes: List[MarketOutcomeResponse] = Field(..., description="Outcome probabilities and fair odds")
    bookmaker_comparison: Optional[List[BookmakerComparisonResponse]] = Field(
        None,
        description="Bookmaker comparison (only when real odds provided)"
    )
    bookmaker_overround: Optional[float] = Field(None, description="Bookmaker overround/margin")
    has_bookmaker_odds: bool = Field(..., description="Whether bookmaker odds were provided")


class EasyMatchSignalResponse(BaseModel):
    """Easy match signal response schema."""

    name: str = Field(..., description="Signal name")
    value: float = Field(..., description="Signal value (0-1)")
    weight: float = Field(..., description="Weight in overall score")
    available: bool = Field(..., description="Whether signal was available")
    description: Optional[str] = Field(None, description="Signal description")


class EasyMatchResponse(BaseModel):
    """Easy match detection response schema."""

    match_id: str = Field(..., description="Match identifier")
    is_easy_match: bool = Field(..., description="Whether match qualifies as Easy Match")
    confidence_score: float = Field(..., description="Confidence score (0-100)")
    threshold: float = Field(..., description="Easy Match threshold")
    signals: List[EasyMatchSignalResponse] = Field(..., description="Individual signals")
    dominant_outcome: Optional[str] = Field(None, description="Dominant predicted outcome")
    dominant_probability: Optional[float] = Field(None, description="Probability of dominant outcome")
    reasons: List[str] = Field(..., description="Reasons for Easy Match determination")
    warnings: List[str] = Field(..., description="Data quality warnings")
    data_sufficient: bool = Field(..., description="Whether sufficient data was available")


class TeamFormResponse(BaseModel):
    """Team form response schema."""

    wins: Optional[int] = Field(None, description="Wins in recent matches")
    draws: Optional[int] = Field(None, description="Draws in recent matches")
    losses: Optional[int] = Field(None, description="Losses in recent matches")
    points: Optional[int] = Field(None, description="Points (3×wins + draws)")
    matches_analyzed: Optional[int] = Field(None, description="Number of matches analyzed")
    goals_for: Optional[int] = Field(None, description="Goals scored")
    goals_against: Optional[int] = Field(None, description="Goals conceded")
    form_string: Optional[str] = Field(None, description="Form string (e.g., WWDLW)")


class HeadToHeadResponse(BaseModel):
    """Head-to-head response schema."""

    total_matches: Optional[int] = Field(None, description="Total H2H matches analyzed")
    home_wins: Optional[int] = Field(None, description="Home team wins in H2H")
    draws: Optional[int] = Field(None, description="Draws in H2H")
    away_wins: Optional[int] = Field(None, description="Away team wins in H2H")
    home_goals: Optional[int] = Field(None, description="Total goals scored by home team in H2H")
    away_goals: Optional[int] = Field(None, description="Total goals scored by away team in H2H")


class MatchPredictionResponse(BaseModel):
    """Match prediction response schema."""

    match_id: str = Field(..., description="Match identifier")
    home_win_probability: float = Field(..., description="Home win probability")
    draw_probability: float = Field(..., description="Draw probability")
    away_win_probability: float = Field(..., description="Away win probability")
    home_xg: float = Field(..., description="Home expected goals")
    away_xg: float = Field(..., description="Away expected goals")
    btts_probability: float = Field(..., description="Both teams to score probability")
    predicted_score: Optional[str] = Field(
        None,
        description="Most likely scoreline (e.g., '3-1') - distinct from TUTAR X PICK"
    )
    mensione_pick: Optional[Dict[str, Any]] = Field(
        None,
        description="TUTAR X recommended pick with market, confidence, and reasoning (field name: mensione_pick for backward compatibility)"
    )
    prediction_version_id: Optional[str] = Field(
        None,
        description="Unique identifier for this prediction version (immutable)"
    )
    market_analysis: Optional[List[MarketAnalysisResponse]] = Field(
        None,
        description="Market analysis across supported markets"
    )
    easy_match: Optional[EasyMatchResponse] = Field(
        None,
        description="Easy Match detection result"
    )
    home_form: Optional[TeamFormResponse] = Field(
        None,
        description="Home team recent form"
    )
    away_form: Optional[TeamFormResponse] = Field(
        None,
        description="Away team recent form"
    )
    head_to_head: Optional[HeadToHeadResponse] = Field(
        None,
        description="Head-to-head historical record"
    )
    shot_markets: Optional[Dict[str, Any]] = Field(
        None,
        description="Shot market predictions (team shots, SOT, total shots)"
    )
    squad_info: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Starting-XI market value and unavailable (injured/suspended) players per side, "
            "from FotMob line-ups (source: fotmob, unofficial). None = no line-up data. "
            "Per side, unavailable = None means no usable injury/suspension data (only "
            "predicted pre-match line-ups carry it), not zero missing players."
        )
    )
    is_development_data: bool = Field(..., description="Whether this is development/mock data")


class TeamInfoResponse(BaseModel):
    """Team information response schema."""

    id: str = Field(..., description="Team identifier")
    name: str = Field(..., description="Team name")
    short_name: Optional[str] = Field(None, description="Team short name")
    code: Optional[str] = Field(None, description="Team code")
    logo_url: Optional[str] = Field(None, description="Team logo URL")


class MatchStatisticsResponse(BaseModel):
    """Match statistics response schema."""

    # Goals
    goals_scored: Optional[int] = Field(None, description="Goals scored")
    goals_conceded: Optional[int] = Field(None, description="Goals conceded")

    # Expected goals
    xg: Optional[float] = Field(None, description="Expected goals")
    xg_against: Optional[float] = Field(None, description="Expected goals against")

    # Shots
    shots_total: Optional[int] = Field(None, description="Total shots")
    shots_on_target: Optional[int] = Field(None, description="Shots on target")
    shots_off_target: Optional[int] = Field(None, description="Shots off target")
    shots_blocked: Optional[int] = Field(None, description="Shots blocked")

    # Possession
    possession_percentage: Optional[float] = Field(None, description="Possession percentage")

    # Passing
    passes_completed: Optional[int] = Field(None, description="Passes completed")
    passes_attempted: Optional[int] = Field(None, description="Passes attempted")
    pass_accuracy: Optional[float] = Field(None, description="Pass accuracy percentage")

    # Set pieces
    corners: Optional[int] = Field(None, description="Corners")
    free_kicks: Optional[int] = Field(None, description="Free kicks")
    offsides: Optional[int] = Field(None, description="Offsides")

    # Discipline
    yellow_cards: Optional[int] = Field(None, description="Yellow cards")
    red_cards: Optional[int] = Field(None, description="Red cards")
    fouls_committed: Optional[int] = Field(None, description="Fouls committed")

    # Defensive
    tackles: Optional[int] = Field(None, description="Tackles")
    interceptions: Optional[int] = Field(None, description="Interceptions")
    clearances: Optional[int] = Field(None, description="Clearances")
    saves: Optional[int] = Field(None, description="Goalkeeper saves")


class MatchResponse(BaseModel):
    """Match response schema for API v1."""

    id: str = Field(..., description="Match identifier")
    competition_id: str = Field(..., description="Competition identifier")
    competition_name: Optional[str] = Field(None, description="Competition name (fallback from provider if not in database)")
    season_id: str = Field(..., description="Season identifier")
    home_team_id: str = Field(..., description="Home team identifier")
    away_team_id: str = Field(..., description="Away team identifier")
    venue_id: Optional[str] = Field(None, description="Venue identifier")

    # Team information
    home_team: Optional[TeamInfoResponse] = Field(None, description="Home team information")
    away_team: Optional[TeamInfoResponse] = Field(None, description="Away team information")

    scheduled_at: datetime = Field(..., description="Scheduled kickoff time")
    status: MatchStatus = Field(..., description="Match status")

    home_score: Optional[int] = Field(None, description="Home team score")
    away_score: Optional[int] = Field(None, description="Away team score")
    home_score_ht: Optional[int] = Field(None, description="Home team half-time score")
    away_score_ht: Optional[int] = Field(None, description="Away team half-time score")

    # Match statistics
    home_statistics: Optional[MatchStatisticsResponse] = Field(None, description="Home team statistics")
    away_statistics: Optional[MatchStatisticsResponse] = Field(None, description="Away team statistics")
    home_statistics_ht: Optional[MatchStatisticsResponse] = Field(None, description="Home team first-half statistics")
    away_statistics_ht: Optional[MatchStatisticsResponse] = Field(None, description="Away team first-half statistics")

    minute: Optional[int] = Field(None, description="Current match minute")
    added_time: Optional[int] = Field(None, description="Added time in minutes")
    outcome: Optional[MatchOutcome] = Field(None, description="Match outcome")
    round: Optional[int] = Field(None, description="Match round/gameweek")

    created_at: Optional[datetime] = Field(None, description="Record creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Record last update timestamp")
    provider_fetched_at: Optional[datetime] = Field(None, description="When data was last fetched from provider")

    class Config:
        """Pydantic configuration."""

        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "competition_id": "comp_123",
                "season_id": "season_456",
                "home_team_id": "team_home",
                "away_team_id": "team_away",
                "home_team": {
                    "id": "team_home",
                    "name": "Home Team",
                    "short_name": "Home",
                    "code": "HOM",
                    "logo_url": "https://example.com/logo_home.png"
                },
                "away_team": {
                    "id": "team_away",
                    "name": "Away Team",
                    "short_name": "Away",
                    "code": "AWA",
                    "logo_url": "https://example.com/logo_away.png"
                },
                "venue_id": "venue_789",
                "scheduled_at": "2026-10-05T15:00:00",
                "status": "scheduled",
                "home_score": None,
                "away_score": None,
                "home_score_ht": None,
                "away_score_ht": None,
                "home_statistics": None,
                "away_statistics": None,
                "home_statistics_ht": None,
                "away_statistics_ht": None,
                "minute": None,
                "added_time": None,
                "outcome": None,
                "round": 7,
                "created_at": "2026-10-03T10:00:00",
                "updated_at": "2026-10-03T10:00:00",
            }
        }


class MatchListResponse(BaseModel):
    """Response schema for match list endpoint."""

    matches: List[MatchResponse] = Field(..., description="List of matches")
    count: int = Field(..., description="Number of matches returned")
    is_development_data: bool = Field(
        ...,
        description="Flag indicating if this is mock/development data"
    )

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "matches": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "competition_id": "comp_123",
                        "season_id": "season_456",
                        "home_team_id": "team_home",
                        "away_team_id": "team_away",
                        "scheduled_at": "2026-10-05T15:00:00",
                        "status": "scheduled",
                        "round": 7,
                        "created_at": "2026-10-03T10:00:00",
                        "updated_at": "2026-10-03T10:00:00",
                    }
                ],
                "count": 1,
                "is_development_data": True,
            }
        }


class MatchDetailResponse(BaseModel):
    """Response schema for single match detail endpoint."""

    match: MatchResponse = Field(..., description="Match details")
    is_development_data: bool = Field(
        ...,
        description="Flag indicating if this is mock/development data"
    )

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "match": {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "competition_id": "comp_123",
                    "season_id": "season_456",
                    "home_team_id": "team_home",
                    "away_team_id": "team_away",
                    "scheduled_at": "2026-10-05T15:00:00",
                    "status": "scheduled",
                    "round": 7,
                    "created_at": "2026-10-03T10:00:00",
                    "updated_at": "2026-10-03T10:00:00",
                },
                "is_development_data": True,
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response schema."""

    detail: str = Field(..., description="Error detail message")

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "detail": "Match not found"
            }
        }


class CompetitionResponse(BaseModel):
    """Competition response schema."""

    id: str = Field(..., description="Competition identifier")
    name: str = Field(..., description="Competition name")
    country: Optional[str] = Field(None, description="Country code")

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "id": "47",
                "name": "Premier League",
                "country": "ENG",
            }
        }


class CompetitionListResponse(BaseModel):
    """Response schema for competition list endpoint."""

    competitions: List[CompetitionResponse] = Field(..., description="List of competitions")
    count: int = Field(..., description="Number of competitions returned")
    is_development_data: bool = Field(
        ...,
        description="Flag indicating if this is mock/development data"
    )

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "competitions": [
                    {
                        "id": "47",
                        "name": "Premier League",
                        "country": "ENG",
                    },
                    {
                        "id": "54",
                        "name": "Bundesliga",
                        "country": "GER",
                    }
                ],
                "count": 2,
                "is_development_data": False,
            }
        }
