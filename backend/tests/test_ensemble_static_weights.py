"""Tests for Fix #8: Ensemble Static Weights undefined model handling.

Verifies that StaticWeights.calculate_weights() returns 0.0 for models
not explicitly configured (instead of 1.0 which could dominate ensemble).
"""
import pytest
from app.prediction.ensemble_engine import StaticWeights
from app.prediction.interfaces import ModelPrediction


def test_static_weights_configured_model():
    """Configured models receive their assigned weight."""
    strategy = StaticWeights(weights={
        "poisson_v1": 0.30,
        "dixon_coles_v1": 0.40,
        "negative_binomial_v1": 0.30
    })
    
    predictions = [
        ModelPrediction(
            model_id="poisson_v1",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.7,
            data_quality_score=0.8
        )
    ]
    
    weights = strategy.calculate_weights(predictions)
    assert weights["poisson_v1"] == 0.30


def test_static_weights_undefined_model_gets_zero():
    """BUGFIX: Undefined models get 0.0 weight instead of 1.0."""
    strategy = StaticWeights(weights={
        "poisson_v1": 0.30,
        "dixon_coles_v1": 0.70
    })
    
    predictions = [
        ModelPrediction(
            model_id="poisson_v1",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.7,
            data_quality_score=0.8
        ),
        ModelPrediction(
            model_id="untested_experimental_v1",  # Not in weights config
            home_score_mean=3.0,
            away_score_mean=3.0,
            home_win_prob=0.33,
            draw_prob=0.33,
            away_win_prob=0.34,
            confidence_score=0.5,
            data_quality_score=0.5
        )
    ]
    
    weights = strategy.calculate_weights(predictions)
    
    # Configured model gets its weight
    assert weights["poisson_v1"] == 0.30
    
    # BUGFIX: Undefined model gets 0.0 (not 1.0)
    assert weights["untested_experimental_v1"] == 0.0


def test_static_weights_multiple_undefined_models():
    """Multiple undefined models all get 0.0 weight."""
    strategy = StaticWeights(weights={
        "poisson_v1": 1.0
    })
    
    predictions = [
        ModelPrediction(
            model_id="poisson_v1",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.7,
            data_quality_score=0.8
        ),
        ModelPrediction(
            model_id="undefined_a",
            home_score_mean=2.0,
            away_score_mean=1.0,
            home_win_prob=0.5,
            draw_prob=0.3,
            away_win_prob=0.2,
            confidence_score=0.6,
            data_quality_score=0.7
        ),
        ModelPrediction(
            model_id="undefined_b",
            home_score_mean=1.0,
            away_score_mean=2.0,
            home_win_prob=0.2,
            draw_prob=0.3,
            away_win_prob=0.5,
            confidence_score=0.6,
            data_quality_score=0.7
        )
    ]
    
    weights = strategy.calculate_weights(predictions)
    
    assert weights["poisson_v1"] == 1.0
    assert weights["undefined_a"] == 0.0
    assert weights["undefined_b"] == 0.0


def test_static_weights_empty_config():
    """When no models configured, all get 0.0 weight."""
    strategy = StaticWeights(weights={})
    
    predictions = [
        ModelPrediction(
            model_id="any_model",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.7,
            data_quality_score=0.8
        )
    ]
    
    weights = strategy.calculate_weights(predictions)
    assert weights["any_model"] == 0.0
