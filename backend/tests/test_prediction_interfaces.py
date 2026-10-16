"""Tests for prediction engine core interfaces."""

import pytest
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.prediction.interfaces import (
    PredictionModelMetadata,
    ModelPrediction,
    ModelAvailability,
    PredictionModel,
)
from app.prediction.model_registry import ModelRegistry
from app.domain.enums import ModelType


class MockPredictionModel(PredictionModel):
    """Mock model for testing."""

    def __init__(self, model_id: str, required_features: List[str]):
        self.model_id = model_id
        self.required_features = required_features

    def predict(
        self,
        features: Dict[str, Optional[float]],
        match_context: Optional[Dict[str, Any]] = None
    ) -> ModelPrediction | ModelAvailability:
        """Generate mock prediction."""
        # Check requirements
        met, missing = self.check_requirements(features)
        
        if not met:
            return ModelAvailability(
                model_id=self.model_id,
                available=False,
                reason="insufficient_data",
                missing_features=missing
            )
        
        return ModelPrediction(
            model_id=self.model_id,
            home_score_mean=1.5,
            away_score_mean=1.0,
            score_distribution={(1, 1): 0.2, (2, 0): 0.15, (1, 0): 0.15},
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.9,
            metadata={"test": True}
        )

    def get_metadata(self) -> PredictionModelMetadata:
        """Return mock metadata."""
        return PredictionModelMetadata(
            model_id=self.model_id,
            model_type=ModelType.POISSON,
            version="1.0.0",
            description="Mock model for testing",
            required_features=self.required_features,
            optional_features=[],
            min_samples_required=5
        )

    def check_requirements(
        self, features: Dict[str, Optional[float]]
    ) -> Tuple[bool, List[str]]:
        """Check if requirements are met."""
        missing = []
        for feature in self.required_features:
            if feature not in features or features[feature] is None:
                missing.append(feature)
        return len(missing) == 0, missing


def test_model_prediction_valid():
    """Test valid ModelPrediction creation."""
    prediction = ModelPrediction(
        model_id="test_model",
        home_score_mean=1.8,
        away_score_mean=1.2,
        score_distribution={(0, 0): 0.05, (1, 0): 0.10, (1, 1): 0.15},
        home_win_prob=0.50,
        draw_prob=0.25,
        away_win_prob=0.25,
        confidence_score=0.85,
        data_quality_score=0.90,
        metadata={"source": "test"}
    )
    
    assert prediction.model_id == "test_model"
    assert prediction.home_score_mean == 1.8
    assert prediction.away_score_mean == 1.2
    assert prediction.home_win_prob == 0.50
    assert prediction.confidence_score == 0.85


def test_model_prediction_probability_sum_validation():
    """Test that probabilities must sum to 1.0."""
    with pytest.raises(ValueError, match="must sum to 1.0"):
        ModelPrediction(
            model_id="test_model",
            home_score_mean=1.5,
            away_score_mean=1.0,
            score_distribution={(1, 0): 0.2},
            home_win_prob=0.40,
            draw_prob=0.30,
            away_win_prob=0.20,  # Sum = 0.90, should fail
            confidence_score=0.8,
            data_quality_score=0.9,
            metadata={}
        )


def test_model_prediction_probability_range_validation():
    """Test that probabilities must be in 0-1 range."""
    # Pydantic's built-in validation catches range errors
    with pytest.raises(Exception):  # Will be ValidationError from Pydantic
        ModelPrediction(
            model_id="test_model",
            home_score_mean=1.5,
            away_score_mean=1.0,
            score_distribution={(1, 0): 0.2},
            home_win_prob=1.5,  # Invalid: > 1.0
            draw_prob=0.0,
            away_win_prob=-0.5,  # Invalid: < 0.0
            confidence_score=0.8,
            data_quality_score=0.9,
            metadata={}
        )


def test_model_prediction_score_distribution_validation():
    """Test that score distribution probabilities cannot exceed 1.0."""
    with pytest.raises(ValueError, match="must sum to ≤1.0"):
        ModelPrediction(
            model_id="test_model",
            home_score_mean=1.5,
            away_score_mean=1.0,
            score_distribution={(0, 0): 0.6, (1, 0): 0.5},  # Sum = 1.1 > 1.0
            home_win_prob=0.4,
            draw_prob=0.3,
            away_win_prob=0.3,
            confidence_score=0.8,
            data_quality_score=0.9,
            metadata={}
        )


def test_model_prediction_negative_expected_goals():
    """Test that expected goals must be non-negative."""
    with pytest.raises(ValueError):
        ModelPrediction(
            model_id="test_model",
            home_score_mean=-1.0,  # Invalid: negative
            away_score_mean=1.0,
            score_distribution={(1, 0): 0.2},
            home_win_prob=0.4,
            draw_prob=0.3,
            away_win_prob=0.3,
            confidence_score=0.8,
            data_quality_score=0.9,
            metadata={}
        )


def test_model_availability():
    """Test ModelAvailability creation."""
    availability = ModelAvailability(
        model_id="test_model",
        available=False,
        reason="insufficient_data",
        missing_features=["home_goals_avg", "away_goals_avg"]
    )
    
    assert availability.model_id == "test_model"
    assert availability.available is False
    assert availability.reason == "insufficient_data"
    assert len(availability.missing_features) == 2


def test_model_registry_register_and_get():
    """Test model registration and retrieval."""
    registry = ModelRegistry()
    model = MockPredictionModel("model_1", ["feature_a", "feature_b"])
    
    registry.register(model)
    retrieved = registry.get("model_1")
    
    assert retrieved is not None
    assert retrieved.get_metadata().model_id == "model_1"


def test_model_registry_duplicate_registration():
    """Test that duplicate registration raises error."""
    registry = ModelRegistry()
    model = MockPredictionModel("model_1", ["feature_a"])
    
    registry.register(model)
    
    with pytest.raises(ValueError, match="already registered"):
        registry.register(model)


def test_model_registry_list_models():
    """Test listing all registered models."""
    registry = ModelRegistry()
    model1 = MockPredictionModel("model_1", ["feature_a"])
    model2 = MockPredictionModel("model_2", ["feature_b"])
    
    registry.register(model1)
    registry.register(model2)
    
    models = registry.list_models()
    
    assert len(models) == 2
    model_ids = [m.model_id for m in models]
    assert "model_1" in model_ids
    assert "model_2" in model_ids


def test_model_registry_get_by_type():
    """Test retrieving models by type."""
    registry = ModelRegistry()
    model1 = MockPredictionModel("poisson_1", ["feature_a"])
    model2 = MockPredictionModel("poisson_2", ["feature_b"])
    
    registry.register(model1)
    registry.register(model2)
    
    poisson_models = registry.get_by_type("poisson")
    
    assert len(poisson_models) == 2


def test_model_registry_get_nonexistent():
    """Test getting non-existent model returns None."""
    registry = ModelRegistry()
    
    result = registry.get("nonexistent")
    
    assert result is None


def test_mock_model_predict_with_sufficient_data():
    """Test mock model prediction with sufficient data."""
    model = MockPredictionModel("test_model", ["home_goals_avg", "away_goals_avg"])
    
    features = {
        "home_goals_avg": 1.5,
        "away_goals_avg": 1.0,
        "home_match_count": 10.0,
        "away_match_count": 10.0
    }
    
    result = model.predict(features)
    
    assert isinstance(result, ModelPrediction)
    assert result.model_id == "test_model"
    assert result.home_score_mean == 1.5
    assert result.confidence_score == 0.8


def test_mock_model_predict_with_insufficient_data():
    """Test mock model returns availability when data insufficient."""
    model = MockPredictionModel("test_model", ["home_goals_avg", "away_goals_avg"])
    
    features = {
        "home_goals_avg": 1.5,
        # Missing away_goals_avg
        "home_match_count": 10.0
    }
    
    result = model.predict(features)
    
    assert isinstance(result, ModelAvailability)
    assert result.model_id == "test_model"
    assert result.available is False
    assert "away_goals_avg" in result.missing_features


def test_model_metadata():
    """Test PredictionModelMetadata creation."""
    metadata = PredictionModelMetadata(
        model_id="poisson_v1",
        model_type=ModelType.POISSON,
        version="1.0.0",
        description="Poisson regression model",
        required_features=["home_goals_avg", "away_goals_avg"],
        optional_features=["home_xg", "away_xg"],
        min_samples_required=5
    )
    
    assert metadata.model_id == "poisson_v1"
    assert metadata.model_type == ModelType.POISSON
    assert len(metadata.required_features) == 2
    assert metadata.min_samples_required == 5
