"""Tests for ensemble_engine module."""

import pytest
from app.prediction.ensemble_engine import (
    EnsembleEngine,
    StaticWeights,
    ReliabilityWeights,
    DynamicWeights,
)
from app.prediction.interfaces import ModelPrediction, ModelAvailability
from app.domain.enums import ModelType


class TestStaticWeights:
    """Tests for StaticWeights strategy."""
    
    def test_static_weights_returns_configured_weights(self):
        """Test that static weights returns configured values."""
        strategy = StaticWeights(weights={"model_a": 0.6, "model_b": 0.4})
        
        predictions = [
            ModelPrediction(
                model_id="model_a",
                home_score_mean=1.5,
                away_score_mean=1.2,
                home_win_prob=0.45,
                draw_prob=0.30,
                away_win_prob=0.25,
                confidence_score=0.8,
                data_quality_score=0.9
            ),
            ModelPrediction(
                model_id="model_b",
                home_score_mean=1.6,
                away_score_mean=1.1,
                home_win_prob=0.50,
                draw_prob=0.28,
                away_win_prob=0.22,
                confidence_score=0.75,
                data_quality_score=0.85
            )
        ]
        
        weights = strategy.calculate_weights(predictions)
        
        assert weights["model_a"] == 0.6
        assert weights["model_b"] == 0.4
    
    def test_static_weights_defaults_to_1_for_unknown_model(self):
        """Test that unknown models get default weight of 1.0."""
        strategy = StaticWeights(weights={"model_a": 0.6})
        
        predictions = [
            ModelPrediction(
                model_id="model_unknown",
                home_score_mean=1.5,
                away_score_mean=1.2,
                home_win_prob=0.45,
                draw_prob=0.30,
                away_win_prob=0.25,
                confidence_score=0.8,
                data_quality_score=0.9
            )
        ]
        
        weights = strategy.calculate_weights(predictions)
        assert weights["model_unknown"] == 1.0


class TestReliabilityWeights:
    """Tests for ReliabilityWeights strategy."""
    
    def test_reliability_weights_multiplies_confidence_and_quality(self):
        """Test that reliability weights = confidence * data_quality."""
        strategy = ReliabilityWeights()
        
        predictions = [
            ModelPrediction(
                model_id="model_a",
                home_score_mean=1.5,
                away_score_mean=1.2,
                home_win_prob=0.45,
                draw_prob=0.30,
                away_win_prob=0.25,
                confidence_score=0.8,
                data_quality_score=0.9
            ),
            ModelPrediction(
                model_id="model_b",
                home_score_mean=1.6,
                away_score_mean=1.1,
                home_win_prob=0.50,
                draw_prob=0.28,
                away_win_prob=0.22,
                confidence_score=0.6,
                data_quality_score=0.7
            )
        ]
        
        weights = strategy.calculate_weights(predictions)
        
        assert weights["model_a"] == pytest.approx(0.8 * 0.9)
        assert weights["model_b"] == pytest.approx(0.6 * 0.7)


class TestDynamicWeights:
    """Tests for DynamicWeights strategy."""
    
    def test_dynamic_weights_applies_league_adjustments(self):
        """Test that league-specific adjustments are applied."""
        strategy = DynamicWeights(league_adjustments={
            "serie_a": {"model_a": 1.10, "model_b": 0.95}
        })
        
        predictions = [
            ModelPrediction(
                model_id="model_a",
                home_score_mean=1.5,
                away_score_mean=1.2,
                home_win_prob=0.45,
                draw_prob=0.30,
                away_win_prob=0.25,
                confidence_score=0.8,
                data_quality_score=0.9
            ),
            ModelPrediction(
                model_id="model_b",
                home_score_mean=1.6,
                away_score_mean=1.1,
                home_win_prob=0.50,
                draw_prob=0.28,
                away_win_prob=0.22,
                confidence_score=0.6,
                data_quality_score=0.7
            )
        ]
        
        context = {"league_id": "serie_a"}
        weights = strategy.calculate_weights(predictions, context)
        
        # Base reliability weight * league adjustment
        assert weights["model_a"] == pytest.approx(0.8 * 0.9 * 1.10)
        assert weights["model_b"] == pytest.approx(0.6 * 0.7 * 0.95)
    
    def test_dynamic_weights_without_league_context(self):
        """Test that dynamic weights work without league context."""
        strategy = DynamicWeights(league_adjustments={})
        
        predictions = [
            ModelPrediction(
                model_id="model_a",
                home_score_mean=1.5,
                away_score_mean=1.2,
                home_win_prob=0.45,
                draw_prob=0.30,
                away_win_prob=0.25,
                confidence_score=0.8,
                data_quality_score=0.9
            )
        ]
        
        weights = strategy.calculate_weights(predictions)
        
        # Should fall back to reliability weights
        assert weights["model_a"] == pytest.approx(0.8 * 0.9)


class TestEnsembleEngine:
    """Tests for EnsembleEngine."""
    
    def test_ensemble_combines_two_predictions(self):
        """Test that ensemble correctly combines two predictions."""
        strategy = StaticWeights(weights={"model_a": 0.5, "model_b": 0.5})
        engine = EnsembleEngine(strategy)
        
        predictions = [
            ModelPrediction(
                model_id="model_a",
                home_score_mean=1.5,
                away_score_mean=1.0,
                home_win_prob=0.50,
                draw_prob=0.30,
                away_win_prob=0.20,
                confidence_score=0.8,
                data_quality_score=0.9
            ),
            ModelPrediction(
                model_id="model_b",
                home_score_mean=1.3,
                away_score_mean=1.2,
                home_win_prob=0.40,
                draw_prob=0.35,
                away_win_prob=0.25,
                confidence_score=0.75,
                data_quality_score=0.85
            )
        ]
        
        result = engine.combine(predictions)
        
        assert isinstance(result, ModelPrediction)
        assert result.model_id == "ensemble_v1"
        
        # Check weighted averages (equal weights)
        assert result.home_score_mean == pytest.approx((1.5 + 1.3) / 2)
        assert result.away_score_mean == pytest.approx((1.0 + 1.2) / 2)
        assert result.home_win_prob == pytest.approx((0.50 + 0.40) / 2)
        assert result.draw_prob == pytest.approx((0.30 + 0.35) / 2)
        assert result.away_win_prob == pytest.approx((0.20 + 0.25) / 2)
    
    def test_ensemble_normalizes_probabilities(self):
        """Test that ensemble normalizes probabilities to sum to 1.0."""
        strategy = StaticWeights(weights={"model_a": 1.0})
        engine = EnsembleEngine(strategy)
        
        predictions = [
            ModelPrediction(
                model_id="model_a",
                home_score_mean=1.5,
                away_score_mean=1.0,
                home_win_prob=0.50,
                draw_prob=0.30,
                away_win_prob=0.20,
                confidence_score=0.8,
                data_quality_score=0.9
            ),
            ModelPrediction(
                model_id="model_b",
                home_score_mean=1.3,
                away_score_mean=1.2,
                home_win_prob=0.40,
                draw_prob=0.35,
                away_win_prob=0.25,
                confidence_score=0.75,
                data_quality_score=0.85
            )
        ]
        
        result = engine.combine(predictions)
        
        # Probabilities should sum to 1.0
        total_prob = result.home_win_prob + result.draw_prob + result.away_win_prob
        assert total_prob == pytest.approx(1.0, abs=0.001)
    
    def test_ensemble_returns_unavailable_with_one_prediction(self):
        """Test that ensemble returns ModelAvailability with <2 predictions."""
        strategy = StaticWeights(weights={})
        engine = EnsembleEngine(strategy)
        
        predictions = [
            ModelPrediction(
                model_id="model_a",
                home_score_mean=1.5,
                away_score_mean=1.0,
                home_win_prob=0.50,
                draw_prob=0.30,
                away_win_prob=0.20,
                confidence_score=0.8,
                data_quality_score=0.9
            )
        ]
        
        result = engine.combine(predictions)
        
        assert isinstance(result, ModelAvailability)
        assert result.model_id == "ensemble_v1"
        assert result.available is False
        assert "insufficient_models" in result.reason
    
    def test_ensemble_returns_unavailable_with_zero_predictions(self):
        """Test that ensemble returns ModelAvailability with no predictions."""
        strategy = StaticWeights(weights={})
        engine = EnsembleEngine(strategy)
        
        result = engine.combine([])
        
        assert isinstance(result, ModelAvailability)
        assert result.available is False
    
    def test_model_agreement_calculation_perfect_agreement(self):
        """Test model agreement calculation with perfect agreement."""
        strategy = StaticWeights(weights={"model_a": 0.5, "model_b": 0.5})
        engine = EnsembleEngine(strategy)
        
        predictions = [
            ModelPrediction(
                model_id="model_a",
                home_score_mean=1.5,
                away_score_mean=1.0,
                home_win_prob=0.50,
                draw_prob=0.30,
                away_win_prob=0.20,
                confidence_score=0.8,
                data_quality_score=0.9
            ),
            ModelPrediction(
                model_id="model_b",
                home_score_mean=1.5,
                away_score_mean=1.0,
                home_win_prob=0.50,
                draw_prob=0.30,
                away_win_prob=0.20,
                confidence_score=0.8,
                data_quality_score=0.9
            )
        ]
        
        result = engine.combine(predictions)
        
        # Perfect agreement should give score close to 1.0
        assert result.metadata["model_agreement"] == pytest.approx(1.0, abs=0.01)
    
    def test_model_agreement_calculation_disagreement(self):
        """Test model agreement calculation with disagreement."""
        strategy = StaticWeights(weights={"model_a": 0.5, "model_b": 0.5})
        engine = EnsembleEngine(strategy)
        
        predictions = [
            ModelPrediction(
                model_id="model_a",
                home_score_mean=1.5,
                away_score_mean=1.0,
                home_win_prob=0.70,
                draw_prob=0.20,
                away_win_prob=0.10,
                confidence_score=0.8,
                data_quality_score=0.9
            ),
            ModelPrediction(
                model_id="model_b",
                home_score_mean=1.0,
                away_score_mean=1.5,
                home_win_prob=0.30,
                draw_prob=0.30,
                away_win_prob=0.40,
                confidence_score=0.75,
                data_quality_score=0.85
            )
        ]
        
        result = engine.combine(predictions)
        
        # Significant disagreement should give lower score
        assert result.metadata["model_agreement"] < 0.7
    
    def test_ensemble_with_unequal_weights(self):
        """Test ensemble with unequal model weights."""
        strategy = StaticWeights(weights={"model_a": 0.7, "model_b": 0.3})
        engine = EnsembleEngine(strategy)
        
        predictions = [
            ModelPrediction(
                model_id="model_a",
                home_score_mean=2.0,
                away_score_mean=1.0,
                home_win_prob=0.60,
                draw_prob=0.25,
                away_win_prob=0.15,
                confidence_score=0.8,
                data_quality_score=0.9
            ),
            ModelPrediction(
                model_id="model_b",
                home_score_mean=1.0,
                away_score_mean=2.0,
                home_win_prob=0.20,
                draw_prob=0.30,
                away_win_prob=0.50,
                confidence_score=0.75,
                data_quality_score=0.85
            )
        ]
        
        result = engine.combine(predictions)
        
        # Should be weighted toward model_a (70%)
        expected_home_win = 0.7 * 0.60 + 0.3 * 0.20
        assert result.home_win_prob == pytest.approx(expected_home_win, abs=0.01)
