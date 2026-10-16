"""Prediction domain models."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional, Dict, List
from pydantic import BaseModel, Field, field_validator

from app.domain.enums import PredictionMarketType, ModelType


class Prediction(BaseModel):
    """Match prediction."""

    id: str = Field(..., description="Prediction identifier")
    match_id: str = Field(..., description="Match identifier")
    model_id: str = Field(..., description="Model identifier")
    model_run_id: Optional[str] = Field(None, description="Model run identifier")
    
    # Match result probabilities (1X2)
    home_win_probability: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Home win probability"
    )
    draw_probability: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Draw probability"
    )
    away_win_probability: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Away win probability"
    )
    
    # Expected goals
    home_xg: Optional[float] = Field(None, ge=0.0, description="Home team expected goals")
    away_xg: Optional[float] = Field(None, ge=0.0, description="Away team expected goals")
    
    # Score predictions
    predicted_home_score: Optional[float] = Field(None, ge=0.0, description="Predicted home score")
    predicted_away_score: Optional[float] = Field(None, ge=0.0, description="Predicted away score")
    
    # BTTS
    btts_probability: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Both teams to score probability"
    )
    
    # Correct score distribution (top N scores)
    score_distribution: Optional[Dict[str, float]] = Field(
        None, description="Score distribution {'0-0': 0.05, '1-0': 0.08, ...}"
    )
    
    # Metadata
    generated_at: datetime = Field(..., description="When prediction was generated")
    confidence: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Prediction confidence"
    )
    
    @field_validator("home_win_probability", "draw_probability", "away_win_probability")
    @classmethod
    def validate_probability(cls, v: Optional[float]) -> Optional[float]:
        """Validate probability is between 0 and 1."""
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError("Probability must be between 0.0 and 1.0")
        return v
    
    class Config:
        """Pydantic configuration."""

        from_attributes = True
        # Suppress warnings about model_* field names conflicting with Pydantic's namespace
        protected_namespaces = ()
        json_schema_extra = {
            "example": {
                "id": "prediction_123",
                "match_id": "match_123",
                "model_id": "model_poisson_v1",
                "home_win_probability": 0.45,
                "draw_probability": 0.30,
                "away_win_probability": 0.25,
                "home_xg": 1.8,
                "away_xg": 1.3,
                "generated_at": "2026-10-03T10:00:00",
            }
        }


class PredictionMarket(BaseModel):
    """Prediction for a specific market."""

    id: str = Field(..., description="Market prediction identifier")
    prediction_id: str = Field(..., description="Parent prediction identifier")
    market_type: PredictionMarketType = Field(..., description="Market type")
    
    # Market-specific probabilities
    probabilities: Dict[str, float] = Field(..., description="Market outcome probabilities")
    
    # Fair odds (inverse of probability)
    fair_odds: Optional[Dict[str, float]] = Field(None, description="Fair odds for outcomes")
    
    # Expected value vs market
    market_odds: Optional[Dict[str, float]] = Field(None, description="Market odds")
    expected_value: Optional[Dict[str, float]] = Field(None, description="Expected value per outcome")
    
    # Line/threshold (for over/under, handicap, etc.)
    line: Optional[float] = Field(None, description="Market line/threshold")
    
    class Config:
        """Pydantic configuration."""

        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "market_pred_123",
                "prediction_id": "prediction_123",
                "market_type": "over_under",
                "line": 2.5,
                "probabilities": {"over": 0.55, "under": 0.45},
                "fair_odds": {"over": 1.82, "under": 2.22},
            }
        }


class Model(BaseModel):
    """Prediction model metadata.

    Designed to be compatible with future model registry/versioning work.
    Extended with richer metadata fields while remaining backwards-compatible
    with existing code that only sets id/name/type/version/parameters/created_at/is_active.
    """

    id: str = Field(..., description="Model identifier")
    name: str = Field(..., description="Model name")
    type: ModelType = Field(..., description="Model type")
    version: str = Field(..., description="Model version")

    description: Optional[str] = Field(None, description="Model description")

    # Parameters accepts mixed types (float, int, str, bool) to support
    # configuration values from all model types.
    parameters: Optional[Dict[str, Any]] = Field(
        None, description="Model configuration parameters"
    )

    # Extended metadata for model registry compatibility
    model_id: Optional[str] = Field(
        None,
        description="Canonical model identifier for registry (defaults to id)",
    )
    model_name: Optional[str] = Field(
        None,
        description="Canonical model name for registry (defaults to name)",
    )
    model_type: Optional[str] = Field(
        None,
        description="String representation of model type for registry",
    )

    # Run/determinism information
    is_deterministic: bool = Field(
        True,
        description="Whether the model produces deterministic outputs",
    )
    run_seed: Optional[int] = Field(
        None,
        description="Random seed used for this model run (if applicable)",
    )

    created_at: datetime = Field(..., description="Model creation timestamp")
    is_active: bool = Field(True, description="Whether model is active")

    # Tags for filtering/grouping in a registry
    tags: Optional[List[str]] = Field(
        None, description="Optional tags for categorisation"
    )

    def get_registry_id(self) -> str:
        """Return the canonical registry identifier."""
        return self.model_id or self.id

    def get_registry_name(self) -> str:
        """Return the canonical registry name."""
        return self.model_name or self.name

    def get_type_string(self) -> str:
        """Return model type as a string."""
        return self.model_type or self.type.value

    class Config:
        """Pydantic configuration."""

        from_attributes = True
        # Suppress warnings about model_* field names conflicting with Pydantic's namespace
        protected_namespaces = ()
        json_schema_extra = {
            "example": {
                "id": "model_poisson_v1",
                "name": "Poisson Model",
                "type": "poisson",
                "version": "1.0.0",
                "is_deterministic": True,
                "created_at": "2026-10-01T00:00:00",
                "is_active": True,
            }
        }


class ModelMetadata(BaseModel):
    """Extended model metadata for registry and versioning support.

    This is a richer companion to `Model` and is intended for use in
    model registries, comparison pipelines, and audit trails.
    It is kept separate from `Model` to avoid breaking existing code.
    """

    model_id: str = Field(..., description="Unique model identifier")
    model_name: str = Field(..., description="Human-readable model name")
    model_type: ModelType = Field(..., description="Model type enum")
    version: str = Field(..., description="Semantic version string e.g. '1.0.0'")

    description: Optional[str] = Field(None, description="Detailed model description")

    # Configuration snapshot
    configuration: Optional[Dict[str, Any]] = Field(
        None,
        description="Full model configuration / hyperparameters",
    )

    # Determinism
    is_deterministic: bool = Field(True, description="Produces identical output for identical input")
    run_seed: Optional[int] = Field(None, description="Seed for reproducibility (if stochastic)")

    # Lifecycle timestamps
    created_at: datetime = Field(..., description="When this model version was created")
    deployed_at: Optional[datetime] = Field(None, description="When this model was deployed")
    retired_at: Optional[datetime] = Field(None, description="When this model was retired")

    is_active: bool = Field(True, description="Whether this model is currently active")

    # Training / data references
    training_data_description: Optional[str] = Field(
        None, description="Description of training data used"
    )
    feature_names: Optional[List[str]] = Field(
        None, description="Features consumed by this model"
    )

    # Tags
    tags: Optional[List[str]] = Field(None, description="Tags for filtering")

    def to_model(self) -> "Model":
        """Convert to the simpler Model domain object."""
        return Model(
            id=self.model_id,
            name=self.model_name,
            type=self.model_type,
            version=self.version,
            description=self.description,
            parameters=self.configuration,
            model_id=self.model_id,
            model_name=self.model_name,
            model_type=self.model_type.value,
            is_deterministic=self.is_deterministic,
            run_seed=self.run_seed,
            created_at=self.created_at,
            is_active=self.is_active,
            tags=self.tags,
        )

    class Config:
        """Pydantic configuration."""

        from_attributes = True
        # Suppress warnings about model_* field names conflicting with Pydantic's namespace
        protected_namespaces = ()


class ModelVersion(BaseModel):
    """Model version tracking."""

    id: str = Field(..., description="Version identifier")
    model_id: str = Field(..., description="Model identifier")
    version: str = Field(..., description="Version string")
    
    changes: Optional[str] = Field(None, description="Version changes")
    parameters: Optional[Dict[str, float]] = Field(None, description="Version parameters")
    
    created_at: datetime = Field(..., description="Version creation timestamp")
    deployed_at: Optional[datetime] = Field(None, description="Deployment timestamp")
    
    class Config:
        """Pydantic configuration."""

        from_attributes = True
        # Suppress warnings about model_* field names conflicting with Pydantic's namespace
        protected_namespaces = ()


class ModelRun(BaseModel):
    """Model execution run."""

    id: str = Field(..., description="Run identifier")
    model_id: str = Field(..., description="Model identifier")
    model_version_id: Optional[str] = Field(None, description="Model version identifier")
    
    started_at: datetime = Field(..., description="Run start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Run completion timestamp")
    
    status: str = Field(..., description="Run status (running, completed, failed)")
    predictions_generated: int = Field(0, ge=0, description="Number of predictions generated")
    
    error_message: Optional[str] = Field(None, description="Error message if failed")
    
    class Config:
        """Pydantic configuration."""

        from_attributes = True
        # Suppress warnings about model_* field names conflicting with Pydantic's namespace
        protected_namespaces = ()


# Supporting structures for TUTAR X Prediction Engine Core

class PlayerImpactResult(BaseModel):
    """Result of player impact analysis."""
    
    player_id: str = Field(..., description="Player identifier")
    team: str = Field(..., description="Team (home/away)")
    impact_on_xg: float = Field(..., description="Impact on expected goals")
    availability_confirmed: bool = Field(..., description="Whether availability is confirmed")
    source: str = Field(..., description="Data source for this impact assessment")
    
    class Config:
        """Pydantic configuration."""
        from_attributes = True


class TacticalAdvantage(Enum):
    """Tactical matchup advantage types."""
    
    HOME_PRESSING = "home_pressing"
    AWAY_PRESSING = "away_pressing"
    HOME_COUNTER = "home_counter"
    AWAY_COUNTER = "away_counter"
    NEUTRAL = "neutral"


class TacticalEffect(BaseModel):
    """Single tactical matchup effect."""
    
    advantage: TacticalAdvantage = Field(..., description="Type of tactical advantage")
    magnitude: float = Field(..., ge=0.0, le=1.0, description="Effect magnitude 0-1")
    factors: List[str] = Field(..., description="Contributing factors")
    
    class Config:
        """Pydantic configuration."""
        from_attributes = True


class ConfidenceAssessment(BaseModel):
    """Overall prediction confidence assessment."""
    
    overall: float = Field(..., ge=0.0, le=1.0, description="Overall confidence score")
    data_quality_component: float = Field(..., ge=0.0, le=1.0, description="Data quality contribution")
    model_agreement_component: float = Field(..., ge=0.0, le=1.0, description="Model agreement contribution")
    historical_accuracy_component: float = Field(..., ge=0.0, le=1.0, description="Historical accuracy contribution")
    explanation: str = Field(..., description="Human-readable confidence explanation")
    
    class Config:
        """Pydantic configuration."""
        from_attributes = True
        # Suppress warnings about model_* field names conflicting with Pydantic's namespace
        protected_namespaces = ()


class PredictionWithOutcome(BaseModel):
    """Historical prediction with known outcome for calibration."""
    
    prediction_id: str = Field(..., description="Prediction identifier")
    match_id: str = Field(..., description="Match identifier")
    predicted_home_goals_mean: float = Field(..., ge=0.0, description="Predicted home goals")
    predicted_away_goals_mean: float = Field(..., ge=0.0, description="Predicted away goals")
    actual_home_goals: Optional[int] = Field(None, ge=0, description="Actual home goals scored")
    actual_away_goals: Optional[int] = Field(None, ge=0, description="Actual away goals scored")
    created_at: datetime = Field(..., description="Prediction creation timestamp")
    outcome_recorded_at: Optional[datetime] = Field(None, description="When outcome was recorded")
    
    class Config:
        """Pydantic configuration."""
        from_attributes = True
