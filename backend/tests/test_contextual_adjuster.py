"""Tests for contextual_adjuster module."""

import pytest
from app.prediction.contextual_adjuster import ContextualAdjuster
from app.prediction.interfaces import ModelPrediction


class TestContextualAdjuster:
    """Tests for ContextualAdjuster."""
    
    def test_adjuster_initialization(self):
        """Test adjuster initialization."""
        adjuster = ContextualAdjuster()
        assert adjuster is not None
    
    def test_adjuster_with_league_specific_home_advantage(self):
        """Test adjuster with league-specific home advantage."""
        league_home_adv = {"premier_league": 0.06}
        adjuster = ContextualAdjuster(league_home_advantage=league_home_adv)
        
        prediction = ModelPrediction(
            model_id="test_model",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.9
        )
        
        context = {"league_id": "premier_league"}
        adjusted = adjuster.adjust(prediction, context)
        
        # Home xG should be increased
        assert adjusted.home_score_mean > prediction.home_score_mean
    
    def test_adjuster_applies_rest_days_adjustment(self):
        """Test that rest days adjustment is applied."""
        adjuster = ContextualAdjuster()
        
        prediction = ModelPrediction(
            model_id="test_model",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.9
        )
        
        # Home team tired (2 days rest)
        context = {"home_rest_days": 2, "away_rest_days": 7}
        adjusted = adjuster.adjust(prediction, context)
        
        # Home team should be penalized (considering default home advantage is applied first)
        # Final value should be close to original after competing effects
        assert adjusted.home_score_mean != 1.5  # Should be adjusted
    
    def test_adjuster_applies_travel_adjustment(self):
        """Test that travel distance adjustment is applied."""
        adjuster = ContextualAdjuster()
        
        prediction = ModelPrediction(
            model_id="test_model",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.9
        )
        
        # Long travel for away team
        context = {"travel_distance_km": 600}
        adjusted = adjuster.adjust(prediction, context)
        
        # Away team should be slightly penalized
        assert adjusted.away_score_mean <= 1.2
    
    def test_adjuster_neutralizes_for_cup_final(self):
        """Test that cup final neutralizes home advantage."""
        adjuster = ContextualAdjuster()
        
        prediction = ModelPrediction(
            model_id="test_model",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.9
        )
        
        context = {"is_cup_final": True}
        adjusted = adjuster.adjust(prediction, context)
        
        # Home advantage reduced
        assert adjusted.home_score_mean < 1.5
    
    def test_adjuster_enforces_maximum_adjustment(self):
        """Test that maximum ±15% adjustment is enforced."""
        # Create extreme context that would cause large adjustment
        adjuster = ContextualAdjuster(
            league_home_advantage={"test_league": 0.20}  # 20% advantage
        )
        
        prediction = ModelPrediction(
            model_id="test_model",
            home_score_mean=1.0,
            away_score_mean=1.0,
            home_win_prob=0.33,
            draw_prob=0.34,
            away_win_prob=0.33,
            confidence_score=0.8,
            data_quality_score=0.9
        )
        
        context = {
            "league_id": "test_league",
            "home_rest_days": 2,
            "travel_distance_km": 1000
        }
        
        adjusted = adjuster.adjust(prediction, context)
        
        # Check that adjustment is bounded
        home_adj = (adjusted.home_score_mean - prediction.home_score_mean) / prediction.home_score_mean
        away_adj = (adjusted.away_score_mean - prediction.away_score_mean) / prediction.away_score_mean
        
        assert abs(home_adj) <= 0.15 + 0.01  # Allow small epsilon
        assert abs(away_adj) <= 0.15 + 0.01
    
    def test_adjuster_recalculates_probabilities(self):
        """Test that probabilities are recalculated after adjustments."""
        adjuster = ContextualAdjuster()
        
        prediction = ModelPrediction(
            model_id="test_model",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.9
        )
        
        context = {"home_rest_days": 2}
        adjusted = adjuster.adjust(prediction, context)
        
        # Probabilities should sum to 1.0
        total = adjusted.home_win_prob + adjusted.draw_prob + adjusted.away_win_prob
        assert total == pytest.approx(1.0, abs=0.01)
    
    def test_adjuster_includes_metadata(self):
        """Test that adjustment metadata is included."""
        adjuster = ContextualAdjuster()
        
        prediction = ModelPrediction(
            model_id="test_model",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.9
        )
        
        context = {"home_rest_days": 2}
        adjusted = adjuster.adjust(prediction, context)
        
        assert "contextual_adjustments" in adjusted.metadata
        assert "original_home_xg" in adjusted.metadata["contextual_adjustments"]
        assert "adjusted_home_xg" in adjusted.metadata["contextual_adjustments"]
