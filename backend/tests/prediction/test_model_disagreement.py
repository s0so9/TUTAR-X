"""Tests for model disagreement analysis."""

import pytest
from unittest.mock import Mock

from app.prediction.model_disagreement import (
    ModelDisagreementAnalyzer,
    ModelDisagreementResult
)
from app.prediction.interfaces import ModelPrediction


class TestModelDisagreementAnalyzer:
    """Test ModelDisagreementAnalyzer."""
    
    def test_analyze_high_agreement(self):
        """Test analysis with high model agreement (similar probabilities)."""
        analyzer = ModelDisagreementAnalyzer()
        
        # Create predictions with very similar probabilities
        predictions = [
            ModelPrediction(
                model_id="model1",
                home_score_mean=1.5,
                away_score_mean=1.0,
                home_win_prob=0.45,
                draw_prob=0.30,
                away_win_prob=0.25,
                confidence_score=0.8,
                data_quality_score=0.9
            ),
            ModelPrediction(
                model_id="model2",
                home_score_mean=1.6,
                away_score_mean=1.1,
                home_win_prob=0.47,
                draw_prob=0.28,
                away_win_prob=0.25,
                confidence_score=0.8,
                data_quality_score=0.9
            ),
            ModelPrediction(
                model_id="model3",
                home_score_mean=1.4,
                away_score_mean=0.9,
                home_win_prob=0.46,
                draw_prob=0.29,
                away_win_prob=0.25,
                confidence_score=0.8,
                data_quality_score=0.9
            )
        ]
        
        result = analyzer.analyze(predictions, "home_win")
        
        assert isinstance(result, ModelDisagreementResult)
        assert result.model_count == 3
        assert result.available_model_count == 3
        assert 0.45 <= result.mean_probability <= 0.47
        assert result.probability_std < 0.05  # Low std = high agreement
        assert result.agreement_score > 0.8  # High agreement
        assert result.disagreement_score < 0.2  # Low disagreement
        assert result.agreement_label in ["HIGH", "MEDIUM"]
    
    def test_analyze_low_agreement(self):
        """Test analysis with low model agreement (divergent probabilities)."""
        analyzer = ModelDisagreementAnalyzer()
        
        # Create predictions with very different probabilities
        predictions = [
            ModelPrediction(
                model_id="model1",
                home_score_mean=2.0,
                away_score_mean=0.8,
                home_win_prob=0.60,
                draw_prob=0.25,
                away_win_prob=0.15,
                confidence_score=0.8,
                data_quality_score=0.9
            ),
            ModelPrediction(
                model_id="model2",
                home_score_mean=1.2,
                away_score_mean=1.5,
                home_win_prob=0.30,
                draw_prob=0.30,
                away_win_prob=0.40,
                confidence_score=0.8,
                data_quality_score=0.9
            ),
            ModelPrediction(
                model_id="model3",
                home_score_mean=1.5,
                away_score_mean=1.2,
                home_win_prob=0.45,
                draw_prob=0.30,
                away_win_prob=0.25,
                confidence_score=0.8,
                data_quality_score=0.9
            )
        ]
        
        result = analyzer.analyze(predictions, "home_win")
        
        assert isinstance(result, ModelDisagreementResult)
        assert result.probability_std > 0.10  # High std = low agreement
        assert result.agreement_score < 0.7  # Low to medium agreement (relaxed threshold)
        assert result.disagreement_score > 0.3  # High disagreement
        assert result.agreement_label in ["LOW", "MEDIUM"]
    
    def test_analyze_single_model(self):
        """Test analysis with single model (insufficient for disagreement)."""
        analyzer = ModelDisagreementAnalyzer()
        
        predictions = [
            ModelPrediction(
                model_id="model1",
                home_score_mean=1.5,
                away_score_mean=1.0,
                home_win_prob=0.45,
                draw_prob=0.30,
                away_win_prob=0.25,
                confidence_score=0.8,
                data_quality_score=0.9
            )
        ]
        
        result = analyzer.analyze(predictions, "home_win")
        
        assert result.available_model_count == 1
        assert result.probability_std == 0.0
        assert result.agreement_score == 1.0  # No disagreement with single model
        assert result.disagreement_score == 0.0
        assert result.agreement_label == "INSUFFICIENT"
    
    def test_analyze_all_outcomes(self):
        """Test analyzing all three outcomes (home/draw/away)."""
        analyzer = ModelDisagreementAnalyzer()
        
        predictions = [
            ModelPrediction(
                model_id="model1",
                home_score_mean=1.5,
                away_score_mean=1.0,
                home_win_prob=0.45,
                draw_prob=0.30,
                away_win_prob=0.25,
                confidence_score=0.8,
                data_quality_score=0.9
            ),
            ModelPrediction(
                model_id="model2",
                home_score_mean=1.6,
                away_score_mean=1.1,
                home_win_prob=0.47,
                draw_prob=0.28,
                away_win_prob=0.25,
                confidence_score=0.8,
                data_quality_score=0.9
            )
        ]
        
        results = analyzer.analyze_all_outcomes(predictions)
        
        assert isinstance(results, dict)
        assert "home_win" in results
        assert "draw" in results
        assert "away_win" in results
        assert all(isinstance(r, ModelDisagreementResult) for r in results.values())
