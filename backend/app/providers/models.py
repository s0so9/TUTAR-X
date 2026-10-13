"""Provider-independent normalized models for football data.

All models include source metadata fields:
- provider: str - Name of the provider that supplied the data
- source_id: str - Provider-specific identifier for the resource
- fetched_at: datetime - When this data was fetched
- source_updated_at: Optional[datetime] - When the provider last updated this data
- is_live: bool - Whether this data represents live/in-progress information
- data_freshness_seconds: Optional[int] - Age of data in seconds

All optional fields use Optional[T] to explicitly represent unavailable data.
NEVER invent values for missing fields.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator

from app.domain.enums import MatchStatus, MatchEventType, MatchOutcome


class ProviderMetadata(BaseModel):
    """Source metadata for provider data."""

    provider: str = Field(..., description="Provider name (e.g., 'ryzellx', 'fotmob', 'openligadb')")
    source_id: str = Field(..., description="Provider-specific resource identifier")
    fetched_at: datetime = Field(..., description="Timestamp when data was fetched")
    source_updated_at: Optional[datetime] = Field(None, description="Provider's last update timestamp")
    is_live: bool = Field(False, description="Whether data represents live/in-progress state")
    data_freshness_seconds: Optional[int] = Field(None, description="Age of data in seconds")


class ProviderCompetition(BaseModel):
    """Normalized competition/league data from provider."""

    # Source metadata
    provider: str
    source_id: str
    fetched_at: datetime
    source_updated_at: Optional[datetime] = None
    is_live: bool = False
    data_freshness_seconds: Optional[int] = None

    # Competition data
    name: str
    country: Optional[str] = None
    level: Optional[int] = None
    type: Optional[str] = None
    season: Optional[str] = None
    logo_url: Optional[str] = None


class ProviderTeam(BaseModel):
    """Normalized team data from provider."""

    # Source metadata
    provider: str
    source_id: str
    fetched_at: datetime
    source_updated_at: Optional[datetime] = None
    is_live: bool = False
    data_freshness_seconds: Optional[int] = None

    # Team data
    name: str
    short_name: Optional[str] = None
    code: Optional[str] = None
    country: Optional[str] = None
    founded: Optional[int] = None
    venue_name: Optional[str] = None
    logo_url: Optional[str] = None


class ProviderPlayer(BaseModel):
    """Normalized player data from provider."""

    # Source metadata
    provider: str
    source_id: str
    fetched_at: datetime
    source_updated_at: Optional[datetime] = None
    is_live: bool = False
    data_freshness_seconds: Optional[int] = None

    # Player data
    name: str
    date_of_birth: Optional[str] = None  # ISO date string
    nationality: Optional[str] = None
    position: Optional[str] = None
    shirt_number: Optional[int] = None
    team_id: Optional[str] = None
    team_name: Optional[str] = None
    height_cm: Optional[int] = None
    weight_kg: Optional[int] = None
    photo_url: Optional[str] = None


class ProviderMatch(BaseModel):
    """Normalized match data from provider."""

    # Source metadata
    provider: str
    source_id: str
    fetched_at: datetime
    source_updated_at: Optional[datetime] = None
    is_live: bool = False
    data_freshness_seconds: Optional[int] = None

    # Match identifiers
    competition_id: Optional[str] = None
    competition_name: Optional[str] = None
    season: Optional[str] = None

    # Teams
    home_team_id: str
    home_team_name: str
    away_team_id: str
    away_team_name: str

    # Venue
    venue_name: Optional[str] = None

    # Timing
    scheduled_at: datetime
    status: MatchStatus
    minute: Optional[int] = None
    added_time: Optional[int] = None

    # Scores
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    home_score_ht: Optional[int] = None
    away_score_ht: Optional[int] = None

    # Outcome
    outcome: Optional[MatchOutcome] = None

    # Match round/week
    round: Optional[int] = None


class ProviderMatchEvent(BaseModel):
    """Normalized match event data from provider."""

    # Source metadata
    provider: str
    source_id: str
    fetched_at: datetime
    source_updated_at: Optional[datetime] = None
    is_live: bool = False
    data_freshness_seconds: Optional[int] = None

    # Event data
    match_id: str
    type: MatchEventType
    minute: int
    added_time: Optional[int] = None
    team_id: str
    team_name: Optional[str] = None
    player_id: Optional[str] = None
    player_name: Optional[str] = None
    related_player_id: Optional[str] = None
    related_player_name: Optional[str] = None
    description: Optional[str] = None


class ProviderLineup(BaseModel):
    """Normalized lineup data from provider."""

    # Source metadata
    provider: str
    source_id: str
    fetched_at: datetime
    source_updated_at: Optional[datetime] = None
    is_live: bool = False
    data_freshness_seconds: Optional[int] = None

    # Lineup data
    match_id: str
    team_id: str
    team_name: Optional[str] = None
    formation: Optional[str] = None
    starting_xi: List[str] = Field(default_factory=list, description="Player IDs")
    starting_xi_names: Optional[List[str]] = Field(None, description="Player names for convenience")
    substitutes: List[str] = Field(default_factory=list, description="Player IDs")
    substitutes_names: Optional[List[str]] = Field(None, description="Player names for convenience")
    coach: Optional[str] = None


class ProviderMatchStats(BaseModel):
    """Normalized team match statistics from provider."""

    # Source metadata
    provider: str
    source_id: str
    fetched_at: datetime
    source_updated_at: Optional[datetime] = None
    is_live: bool = False
    data_freshness_seconds: Optional[int] = None

    # Match and team identifiers
    match_id: str
    team_id: str
    team_name: Optional[str] = None
    period: Optional[str] = Field(None, description="Match period: 'full', 'first_half', 'second_half'")

    # Goals
    goals_scored: Optional[int] = None
    goals_conceded: Optional[int] = None

    # Expected goals
    xg: Optional[float] = None
    xg_against: Optional[float] = None

    # Shots
    shots_total: Optional[int] = None
    shots_on_target: Optional[int] = None
    shots_off_target: Optional[int] = None
    shots_blocked: Optional[int] = None

    # Possession
    possession_percentage: Optional[float] = None

    # Passing
    passes_completed: Optional[int] = None
    passes_attempted: Optional[int] = None
    pass_accuracy: Optional[float] = None

    # Set pieces
    corners: Optional[int] = None
    free_kicks: Optional[int] = None
    offsides: Optional[int] = None

    # Discipline
    yellow_cards: Optional[int] = None
    red_cards: Optional[int] = None
    fouls_committed: Optional[int] = None

    # Defensive
    tackles: Optional[int] = None
    interceptions: Optional[int] = None
    clearances: Optional[int] = None
    saves: Optional[int] = None


class ProviderShot(BaseModel):
    """Normalized shot data from provider."""

    # Source metadata
    provider: str
    source_id: str
    fetched_at: datetime
    source_updated_at: Optional[datetime] = None
    is_live: bool = False
    data_freshness_seconds: Optional[int] = None

    # Shot data
    match_id: str
    team_id: str
    team_name: Optional[str] = None
    player_id: Optional[str] = None
    player_name: Optional[str] = None
    minute: Optional[int] = None
    xg: Optional[float] = None
    result: Optional[str] = None  # e.g., 'goal', 'saved', 'missed', 'blocked'
    coordinates: Optional[Dict[str, float]] = None  # e.g., {'x': 85.5, 'y': 50.2}
    body_part: Optional[str] = None  # e.g., 'right_foot', 'left_foot', 'head'
    situation: Optional[str] = None  # e.g., 'open_play', 'set_piece', 'counter_attack'


class ProviderStanding(BaseModel):
    """Normalized league standing/table entry from provider."""

    # Source metadata
    provider: str
    source_id: str
    fetched_at: datetime
    source_updated_at: Optional[datetime] = None
    is_live: bool = False
    data_freshness_seconds: Optional[int] = None

    # Standing identifiers
    competition_id: Optional[str] = None
    competition_name: Optional[str] = None
    season: Optional[str] = None
    team_id: str
    team_name: str

    # Table position
    position: int
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0

    # Goals
    goals_for: int = 0
    goals_against: int = 0
    goal_difference: int = 0

    # Points
    points: int = 0

    # Home/away splits
    home_played: Optional[int] = None
    home_won: Optional[int] = None
    home_drawn: Optional[int] = None
    home_lost: Optional[int] = None
    away_played: Optional[int] = None
    away_won: Optional[int] = None
    away_drawn: Optional[int] = None
    away_lost: Optional[int] = None

    # Form
    form: Optional[str] = None  # e.g., 'WWDLL'


class PlayerPosition(BaseModel):
    """Player position coordinates on the pitch.

    Optional spatial data. Defaults to None. MUST NOT FABRICATE.
    Only set when provider supplies real tracking coordinates.

    Coordinate system: standard pitch dimensions in meters
    - x: 0 to 120 meters (pitch length)
    - y: 0 to 80 meters (pitch width)
    """

    player_id: str = Field(..., description="Player identifier")
    player_name: Optional[str] = Field(None, description="Player name if available")
    team_id: str = Field(..., description="Team identifier")
    x: float = Field(..., description="X coordinate in meters (0-120)")
    y: float = Field(..., description="Y coordinate in meters (0-80)")
    timestamp: datetime = Field(..., description="Timestamp of position data")

    @field_validator('x')
    @classmethod
    def validate_x(cls, v: float) -> float:
        """Validate x coordinate within realistic pitch bounds."""
        if not (0 <= v <= 120):
            raise ValueError(f"x coordinate must be between 0 and 120 meters, got {v}")
        return v

    @field_validator('y')
    @classmethod
    def validate_y(cls, v: float) -> float:
        """Validate y coordinate within realistic pitch bounds."""
        if not (0 <= v <= 80):
            raise ValueError(f"y coordinate must be between 0 and 80 meters, got {v}")
        return v


class BallPosition(BaseModel):
    """Ball position coordinates on the pitch.

    Optional spatial data. Defaults to None. MUST NOT FABRICATE.
    Only set when provider supplies real tracking coordinates.

    Coordinate system: standard pitch dimensions in meters
    - x: 0 to 120 meters (pitch length)
    - y: 0 to 80 meters (pitch width)
    - z: 0 to 30 meters (height, optional)
    """

    x: float = Field(..., description="X coordinate in meters (0-120)")
    y: float = Field(..., description="Y coordinate in meters (0-80)")
    z: Optional[float] = Field(None, description="Z coordinate (height) in meters (0-30)")
    timestamp: datetime = Field(..., description="Timestamp of position data")

    @field_validator('x')
    @classmethod
    def validate_x(cls, v: float) -> float:
        """Validate x coordinate within realistic pitch bounds."""
        if not (0 <= v <= 120):
            raise ValueError(f"x coordinate must be between 0 and 120 meters, got {v}")
        return v

    @field_validator('y')
    @classmethod
    def validate_y(cls, v: float) -> float:
        """Validate y coordinate within realistic pitch bounds."""
        if not (0 <= v <= 80):
            raise ValueError(f"y coordinate must be between 0 and 80 meters, got {v}")
        return v

    @field_validator('z')
    @classmethod
    def validate_z(cls, v: Optional[float]) -> Optional[float]:
        """Validate z coordinate within realistic bounds if present."""
        if v is not None and not (0 <= v <= 30):
            raise ValueError(f"z coordinate must be between 0 and 30 meters, got {v}")
        return v


class FieldDimensions(BaseModel):
    """Football pitch dimensions.

    Standard FIFA pitch dimensions range:
    - Length: 90-120 meters
    - Width: 45-90 meters
    """

    length_m: float = Field(..., description="Pitch length in meters")
    width_m: float = Field(..., description="Pitch width in meters")

    @field_validator('length_m')
    @classmethod
    def validate_length(cls, v: float) -> float:
        """Validate pitch length within FIFA standard range."""
        if not (90 <= v <= 120):
            raise ValueError(f"Pitch length must be between 90 and 120 meters, got {v}")
        return v

    @field_validator('width_m')
    @classmethod
    def validate_width(cls, v: float) -> float:
        """Validate pitch width within FIFA standard range."""
        if not (45 <= v <= 90):
            raise ValueError(f"Pitch width must be between 45 and 90 meters, got {v}")
        return v


class DataQualityIndicators(BaseModel):
    """Data quality indicators for live match data.

    Flags indicating what data types are actually present in the response.
    All default to False - only set to True when real data is present.
    """

    has_player_positions: bool = Field(False, description="True if player positions available")
    has_ball_tracking: bool = Field(False, description="True if ball tracking available")
    has_xg: bool = Field(False, description="True if xG data available")
    has_shots: bool = Field(False, description="True if shot data available")
    has_events: bool = Field(False, description="True if event data available")
    has_shot_coordinates: bool = Field(False, description="True if shot coordinates available")
    has_live_statistics: bool = Field(False, description="True if live statistics available")


class ProviderLiveMatch(BaseModel):
    """Normalized live match state from provider.

    This model focuses on real-time match state and recent events,
    optimized for live score updates and notifications.
    """

    # Source metadata
    provider: str
    source_id: str
    fetched_at: datetime
    source_updated_at: Optional[datetime] = None
    is_live: bool = True
    data_freshness_seconds: Optional[int] = None

    # Match identifiers
    match_id: str

    # Live state
    status: MatchStatus
    minute: Optional[int] = None
    added_time: Optional[int] = None

    # Teams
    home_team_id: Optional[str] = None
    home_team_name: Optional[str] = None
    away_team_id: Optional[str] = None
    away_team_name: Optional[str] = None

    # Competition
    competition_id: Optional[str] = None

    # Scores
    home_score: int
    away_score: int

    # Recent events (limited to last few events for efficient updates)
    live_events: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Recent match events in simplified format"
    )

    # Last update timestamp from provider
    last_updated: datetime

    # Spatial data (Phase 10A) - all optional, MUST NOT FABRICATE
    player_positions: Optional[List[PlayerPosition]] = Field(
        None,
        description="Optional spatial data. Defaults to None. MUST NOT FABRICATE. Only set when provider supplies real coordinates."
    )

    ball_position: Optional[BallPosition] = Field(
        None,
        description="Optional spatial data. Defaults to None. MUST NOT FABRICATE. Only set when provider supplies real coordinates."
    )

    field_dimensions: Optional[FieldDimensions] = Field(
        None,
        description="Pitch dimensions. Optional, defaults to None."
    )

    data_quality: Optional[DataQualityIndicators] = Field(
        None,
        description="Data quality indicators. Optional, defaults to None."
    )
