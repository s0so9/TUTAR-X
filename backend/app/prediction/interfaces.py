"""Core prediction engine interfaces and data structures.

This module defines the base interfaces that all prediction models must implement,
along with supporting data structures for model outputs, availability, and metadata.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, field_validator

from app.domain.enums import ModelType


class PredictionModelMetadata(BaseModel):
    """Metadata describing a prediction model's interface requirements.
    
    This is distinct from domain.prediction.ModelMetadata (which tracks versioning/deployment).
    This class describes what a model needs to operate (features, samples, etc.).
    """

    model_id: str = Field(..., description="Unique model identifier")
    model_type: ModelType = Field(..., description="Model type")
    version: str = Field(..., description="Model version")
    description: str = Field(..., description="Model description")
    required_features: List[str] = Field(..., description="Required feature names")
    optional_features: List[str] = Field(default_factory=list, description="Optional feature names")
    min_samples_required: int = Field(..., ge=0, description="Minimum historical samples required")

    class Config:
        """Pydantic configuration."""
        from_attributes = True
        # Suppress warnings about model_* field names conflicting with Pydantic's namespace
        protected_namespaces = ()


class ModelPrediction(BaseModel):
    """Structured prediction output from a single model.
    
    Score Distribution Semantics:
    -----------------------------
    The score_distribution field contains probabilities for specific scorelines.
    Models MAY return partial distributions (e.g., only the top 10 most likely scorelines).
    
    - If distribution sums to < 1.0, the missing probability mass represents "all other scorelines"
    - Consumers that need normalized probabilities must renormalize the distribution themselves
    - Example: {(1,0): 0.15, (0,0): 0.10, (2,1): 0.08} (sum=0.33) means these are the top 3 
      scorelines with combined 33% probability, and all other scorelines account for 67%
    
    This design allows models to return compact distributions without computing all possible scores.
    """

    # Model identification
    model_id: str = Field(..., description="Model identifier")
    
    # Expected goals (required)
    home_score_mean: float = Field(..., ge=0.0, description="Expected home goals")
    away_score_mean: float = Field(..., ge=0.0, description="Expected away goals")
    
    # Score distribution (optional but recommended)
    score_distribution: Dict[Tuple[int, int], float] = Field(
        default_factory=dict,
        description="Scoreline probabilities e.g. {(0,0): 0.05, (1,0): 0.08}. May be partial (sum < 1.0)."
    )
    
    # 1X2 probabilities (required)
    home_win_prob: float = Field(..., ge=0.0, le=1.0, description="Home win probability")
    draw_prob: float = Field(..., ge=0.0, le=1.0, description="Draw probability")
    away_win_prob: float = Field(..., ge=0.0, le=1.0, description="Away win probability")
    
    # Quality metrics
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Model confidence")
    data_quality_score: float = Field(..., ge=0.0, le=1.0, description="Input data quality")
    
    # Additional metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional model-specific data")

    @field_validator("home_win_prob", "draw_prob", "away_win_prob")
    @classmethod
    def validate_probability_range(cls, v: float) -> float:
        """Validate probability is in valid range."""
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"Probability must be between 0.0 and 1.0, got {v}")
        return v

    def model_post_init(self, __context: Any) -> None:
        """Validate probability sum after initialization."""
        total = self.home_win_prob + self.draw_prob + self.away_win_prob
        if not (0.999 <= total <= 1.001):
            raise ValueError(
                f"Probabilities must sum to 1.0 (±0.001), got {total:.6f}. "
                f"home={self.home_win_prob}, draw={self.draw_prob}, away={self.away_win_prob}"
            )
        
        # Validate score distribution sums to ≤1.0
        if self.score_distribution:
            dist_sum = sum(self.score_distribution.values())
            if dist_sum > 1.0001:
                raise ValueError(
                    f"Score distribution probabilities must sum to ≤1.0, got {dist_sum:.6f}"
                )

    class Config:
        """Pydantic configuration."""
        from_attributes = True


class ModelAvailability(BaseModel):
    """Represents a model that cannot generate a prediction."""

    model_id: str = Field(..., description="Model identifier")
    available: bool = Field(False, description="Always False for this type")
    reason: str = Field(..., description="Reason for unavailability")
    missing_features: List[str] = Field(default_factory=list, description="Missing required features")

    class Config:
        """Pydantic configuration."""
        from_attributes = True


class PredictionModel(ABC):
    """Abstract base class for all prediction models.

    Each model must:
    1. Implement predict() that returns ModelPrediction or ModelAvailability
    2. Implement get_metadata() to expose model information
    3. Implement check_requirements() to validate data availability
    4. Handle missing/insufficient data gracefully
    5. Produce deterministic outputs for the same inputs
    6. Never fabricate data
    """

    @abstractmethod
    def predict(
        self,
        features: Dict[str, Optional[float]],
        match_context: Optional[Dict[str, Any]] = None
    ) -> ModelPrediction | ModelAvailability:
        """Generate prediction for a match.

        Args:
            features: Feature dictionary from MatchFeatureExtractor
            match_context: Additional context (lineups, injuries, etc.)

        Returns:
            ModelPrediction if successful, ModelAvailability if unable to predict
        """
        pass

    @abstractmethod
    def get_metadata(self) -> PredictionModelMetadata:
        """Return model metadata.

        Returns:
            PredictionModelMetadata with model information
        """
        pass

    @abstractmethod
    def check_requirements(self, features: Dict[str, Optional[float]]) -> Tuple[bool, List[str]]:
        """Check if required data is available.

        Args:
            features: Feature dictionary

        Returns:
            (requirements_met, missing_requirements)
        """
        pass


# ============================================================================
# SHOT MARKET STRUCTURES (Phase 10 Group 5)
# ============================================================================


class ShotMarketType(str, Enum):
    """Shot market types."""
    TEAM_SHOTS = "team_shots"
    TEAM_SHOTS_ON_TARGET = "team_shots_on_target"
    TOTAL_SHOTS = "total_shots"
    TOTAL_SHOTS_ON_TARGET = "total_shots_on_target"


class DistributionType(str, Enum):
    """Statistical distribution used for shot modeling."""
    POISSON = "poisson"
    NEGATIVE_BINOMIAL = "negative_binomial"
    UNAVAILABLE = "unavailable"


@dataclass
class ShotMarketThreshold:
    """Shot market threshold definition with probability.
    
    Represents P(X >= threshold) for a specific shot count threshold.
    """
    threshold: int  # e.g., 10, 12, 15, 18, 20 for shots
    over_probability: float  # P(X >= threshold)
    distribution_model: DistributionType
    expected_value: Optional[float] = None
    variance: Optional[float] = None
    data_quality: float = 0.0


@dataclass
class ShotMarketPrediction:
    """Shot market prediction with threshold probabilities.
    
    Contains distribution parameters and probabilities for multiple thresholds.
    """
    team_id: str
    market_type: ShotMarketType
    thresholds: List[ShotMarketThreshold]
    
    # Distribution parameters
    distribution_model: DistributionType
    expected_value: Optional[float] = None
    variance: Optional[float] = None
    
    # Availability
    available: bool = True
    unavailability_reason: Optional[str] = None
    
    # Provenance
    sample_size: int = 0
    data_quality_score: float = 0.0
    model_id: str = "shot_market_v1"
