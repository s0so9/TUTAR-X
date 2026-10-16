"""Test score distribution rescaling invariants after calibration.

This test ensures that score distribution rescaling maintains consistency
between marginal 1X2 probabilities and the score distribution.
"""

import pytest
from app.prediction.model_orchestrator import CalibrationIntegration
from app.prediction.interfaces import ModelPrediction


class TestCalibrationRescaling:
    """Test score distribution rescaling after 1X2 calibration."""
    
    def test_rescaled_distribution_sums_to_one(self):
        """Test that rescaled distribution sums to 1.0."""
        integration = CalibrationIntegration.create_default()
        
        # Create a mock prediction
        score_dist = {
            (0, 0): 0.10,
            (1, 0): 0.20,
            (1, 1): 0.15,
            (0, 1): 0.18,
            (2, 0): 0.12,
            (0, 2): 0.10,
            (2, 1): 0.08,
            (1, 2): 0.07,
        }
        
        prediction = ModelPrediction(
            model_id="test",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.40,
            draw_prob=0.15,
            away_win_prob=0.45,
            confidence_score=0.8,
            data_quality_score=0.9,
            score_distribution=score_dist,
            metadata={}
        )
        
        # Calibrate (will rescale distribution)
        calibrated = integration.calibrate_prediction(prediction)
        
        # Check total probability sums to 1.0
        total = sum(calibrated.score_distribution.values())
        assert abs(total - 1.0) < 1e-9, f"Distribution should sum to 1.0, got {total}"
    
    def test_category_sums_match_calibrated_probs(self):
        """Test that rescaled category sums match calibrated 1X2 probabilities."""
        integration = CalibrationIntegration.create_default()
        
        # Create prediction with clear category separation
        score_dist = {
            (2, 0): 0.20,  # Home
            (2, 1): 0.10,  # Home
            (1, 1): 0.20,  # Draw
            (0, 0): 0.10,  # Draw
            (0, 2): 0.25,  # Away
            (1, 2): 0.15,  # Away
        }
        
        prediction = ModelPrediction(
            model_id="test",
            home_score_mean=1.0,
            away_score_mean=1.0,
            home_win_prob=0.30,
            draw_prob=0.30,
            away_win_prob=0.40,
            confidence_score=0.8,
            data_quality_score=0.9,
            score_distribution=score_dist,
            metadata={}
        )
        
        calibrated = integration.calibrate_prediction(prediction)
        
        # Calculate category sums from rescaled distribution
        home_sum = sum(
            p for (h, a), p in calibrated.score_distribution.items()
            if h > a
        )
        draw_sum = sum(
            p for (h, a), p in calibrated.score_distribution.items()
            if h == a
        )
        away_sum = sum(
            p for (h, a), p in calibrated.score_distribution.items()
            if h < a
        )
        
        # Check category sums match calibrated probabilities
        assert abs(home_sum - calibrated.home_win_prob) < 1e-6, \
            f"Home category sum {home_sum} != home_win_prob {calibrated.home_win_prob}"
        assert abs(draw_sum - calibrated.draw_prob) < 1e-6, \
            f"Draw category sum {draw_sum} != draw_prob {calibrated.draw_prob}"
        assert abs(away_sum - calibrated.away_win_prob) < 1e-6, \
            f"Away category sum {away_sum} != away_win_prob {calibrated.away_win_prob}"
    
    def test_within_category_proportions_preserved(self):
        """Test that within-category proportions are preserved after rescaling."""
        integration = CalibrationIntegration.create_default()
        
        # Create prediction where home wins have specific proportions
        score_dist = {
            (1, 0): 0.10,  # Home - 33.3% of home wins
            (2, 0): 0.20,  # Home - 66.7% of home wins
            (1, 1): 0.30,  # Draw
            (0, 1): 0.40,  # Away
        }
        
        prediction = ModelPrediction(
            model_id="test",
            home_score_mean=1.0,
            away_score_mean=0.8,
            home_win_prob=0.30,
            draw_prob=0.30,
            away_win_prob=0.40,
            confidence_score=0.8,
            data_quality_score=0.9,
            score_distribution=score_dist,
            metadata={}
        )
        
        # Original home win proportions
        original_home_sum = 0.10 + 0.20  # 0.30
        original_1_0_prop = 0.10 / original_home_sum  # 33.3%
        original_2_0_prop = 0.20 / original_home_sum  # 66.7%
        
        calibrated = integration.calibrate_prediction(prediction)
        
        # Find home win scorelines in calibrated distribution
        home_scorelines = {
            k: v for k, v in calibrated.score_distribution.items()
            if k[0] > k[1]
        }
        
        if home_scorelines:
            calibrated_home_sum = sum(home_scorelines.values())
            
            # Check proportions preserved
            if (1, 0) in home_scorelines:
                cal_1_0_prop = home_scorelines[(1, 0)] / calibrated_home_sum
                assert abs(cal_1_0_prop - original_1_0_prop) < 1e-6, \
                    "Within-category proportion should be preserved"
            
            if (2, 0) in home_scorelines:
                cal_2_0_prop = home_scorelines[(2, 0)] / calibrated_home_sum
                assert abs(cal_2_0_prop - original_2_0_prop) < 1e-6, \
                    "Within-category proportion should be preserved"
    
    def test_handles_zero_category_sum(self):
        """Test rescaling when a category has zero probability in original distribution."""
        integration = CalibrationIntegration.create_default()
        
        # Distribution with NO draw scorelines
        score_dist = {
            (2, 0): 0.40,  # Home
            (2, 1): 0.10,  # Home
            (0, 2): 0.30,  # Away
            (1, 2): 0.20,  # Away
        }
        
        prediction = ModelPrediction(
            model_id="test",
            home_score_mean=1.5,
            away_score_mean=1.3,
            home_win_prob=0.50,
            draw_prob=0.00,  # Zero original draw prob
            away_win_prob=0.50,
            confidence_score=0.8,
            data_quality_score=0.9,
            score_distribution=score_dist,
            metadata={}
        )
        
        # Calibration increases draw probability
        # Since original draw sum is zero, should create plausible draw scorelines
        calibrated = integration.calibrate_prediction(prediction)
        
        # Should have some draw scorelines now if calibrated draw_prob > 0
        draw_scorelines = {
            k: v for k, v in calibrated.score_distribution.items()
            if k[0] == k[1]
        }
        
        if calibrated.draw_prob > 1e-6:
            assert len(draw_scorelines) > 0, "Should create draw scorelines when calibrated prob > 0"
            draw_sum = sum(draw_scorelines.values())
            assert abs(draw_sum - calibrated.draw_prob) < 1e-6, \
                f"Draw sum {draw_sum} should match calibrated {calibrated.draw_prob}"
    
    def test_rescaling_does_not_change_lambdas(self):
        """Test that rescaling does not change expected goals (lambdas)."""
        integration = CalibrationIntegration.create_default()
        
        score_dist = {
            (1, 0): 0.20,
            (1, 1): 0.30,
            (0, 1): 0.50,
        }
        
        original_home_lambda = 1.8
        original_away_lambda = 1.3
        
        prediction = ModelPrediction(
            model_id="test",
            home_score_mean=original_home_lambda,
            away_score_mean=original_away_lambda,
            home_win_prob=0.20,
            draw_prob=0.30,
            away_win_prob=0.50,
            confidence_score=0.8,
            data_quality_score=0.9,
            score_distribution=score_dist,
            metadata={}
        )
        
        calibrated = integration.calibrate_prediction(prediction)
        
        # Lambdas should remain unchanged
        assert calibrated.home_score_mean == original_home_lambda, \
            "Home lambda should not change during calibration"
        assert calibrated.away_score_mean == original_away_lambda, \
            "Away lambda should not change during calibration"
    
    def test_empty_distribution_returns_empty(self):
        """Test that empty score distribution returns empty."""
        integration = CalibrationIntegration.create_default()
        
        prediction = ModelPrediction(
            model_id="test",
            home_score_mean=1.0,
            away_score_mean=1.0,
            home_win_prob=0.33,
            draw_prob=0.34,
            away_win_prob=0.33,
            confidence_score=0.8,
            data_quality_score=0.9,
            score_distribution={},  # Empty
            metadata={}
        )
        
        calibrated = integration.calibrate_prediction(prediction)
        
        assert len(calibrated.score_distribution) == 0, \
            "Empty distribution should remain empty"
    
    def test_no_silent_fallback_to_scale_1(self):
        """Test that we don't silently fallback to scale factor 1.0 for near-zero categories."""
        integration = CalibrationIntegration.create_default()
        
        # Distribution with very small home probability
        score_dist = {
            (1, 0): 0.001,  # Home - very small
            (1, 1): 0.30,   # Draw
            (0, 1): 0.699,  # Away
        }
        
        prediction = ModelPrediction(
            model_id="test",
            home_score_mean=0.5,
            away_score_mean=2.0,
            home_win_prob=0.001,
            draw_prob=0.30,
            away_win_prob=0.699,
            confidence_score=0.8,
            data_quality_score=0.9,
            score_distribution=score_dist,
            metadata={}
        )
        
        # Calibration increases home probability significantly
        # Mock calibration by creating manually (since default calibrator is not fitted)
        calibrated_dist = integration._rescale_score_distribution(
            score_distribution=score_dist,
            original_home_prob=0.001,
            original_draw_prob=0.30,
            original_away_prob=0.699,
            calibrated_home_prob=0.15,  # Increased 150x
            calibrated_draw_prob=0.35,
            calibrated_away_prob=0.50
        )
        
        # Calculate actual home sum
        home_sum = sum(
            p for (h, a), p in calibrated_dist.items()
            if h > a
        )
        
        # Should reach target, not stay at original tiny value
        assert abs(home_sum - 0.15) < 1e-6, \
            f"Home sum {home_sum} should reach calibrated target 0.15, not stay at 0.001"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
