"""Test calibration rescaling preserves distribution structure and target probabilities."""

import pytest
from app.prediction.model_orchestrator import CalibrationIntegration


class TestCalibrationDistributionInvariant:
    """Test that calibration rescaling correctly preserves category probabilities."""
    
    def test_rescale_uses_category_sum_not_original_prob(self):
        """Test that rescaling uses actual category sum from distribution."""
        integration = CalibrationIntegration()
        
        # Distribution: Home=0.4, Draw=0.4, Away=0.2 (sum=1.0)
        score_dist = {
            (1, 0): 0.4,  # Home win
            (0, 0): 0.4,  # Draw
            (0, 1): 0.2,  # Away win
        }
        
        # Original 1X2 from distribution
        original_home = 0.4
        original_draw = 0.4
        original_away = 0.2
        
        # Calibrated 1X2: Home=0.6, Draw=0.2, Away=0.2
        calibrated_home = 0.6
        calibrated_draw = 0.2
        calibrated_away = 0.2
        
        rescaled = integration._rescale_score_distribution(
            score_dist, original_home, original_draw, original_away,
            calibrated_home, calibrated_draw, calibrated_away
        )
        
        # Check category sums match calibrated targets
        home_sum = sum(p for (h, a), p in rescaled.items() if h > a)
        draw_sum = sum(p for (h, a), p in rescaled.items() if h == a)
        away_sum = sum(p for (h, a), p in rescaled.items() if h < a)
        
        assert home_sum == pytest.approx(0.6, abs=1e-6), f"Home sum {home_sum} != 0.6"
        assert draw_sum == pytest.approx(0.2, abs=1e-6), f"Draw sum {draw_sum} != 0.2"
        assert away_sum == pytest.approx(0.2, abs=1e-6), f"Away sum {away_sum} != 0.2"
        
        # Check total distribution sums to 1.0
        total = sum(rescaled.values())
        assert total == pytest.approx(1.0, abs=1e-6)
    
    def test_zero_category_with_positive_target_fallback(self):
        """Test that zero category sum with positive target uses fallback."""
        integration = CalibrationIntegration()
        
        # Distribution has NO home wins (home_sum=0)
        score_dist = {
            (0, 0): 0.3,  # Draw
            (1, 1): 0.2,  # Draw
            (0, 1): 0.3,  # Away
            (0, 2): 0.2,  # Away
        }
        
        rescaled = integration._rescale_score_distribution(
            score_dist, 0.0, 0.5, 0.5,
            0.1, 0.4, 0.5
        )
        
        # Should create fallback home scorelines
        home_sum = sum(p for (h, a), p in rescaled.items() if h > a)
        assert home_sum == pytest.approx(0.1, abs=1e-6), \
            "Should use fallback to achieve target home prob"
    
    def test_normalization_preserves_targets(self):
        """Test that final normalization doesn't distort category targets."""
        integration = CalibrationIntegration()
        
        # Multi-scoreline distribution
        score_dist = {
            (1, 0): 0.20,
            (2, 0): 0.15,
            (2, 1): 0.10,  # Home category sum = 0.45
            (0, 0): 0.15,
            (1, 1): 0.10,  # Draw category sum = 0.25
            (0, 1): 0.15,
            (0, 2): 0.10,
            (1, 2): 0.05,  # Away category sum = 0.30
        }
        
        rescaled = integration._rescale_score_distribution(
            score_dist, 0.45, 0.25, 0.30,
            0.50, 0.30, 0.20
        )
        
        home_sum = sum(p for (h, a), p in rescaled.items() if h > a)
        draw_sum = sum(p for (h, a), p in rescaled.items() if h == a)
        away_sum = sum(p for (h, a), p in rescaled.items() if h < a)
        
        # After normalization, targets should be preserved
        assert home_sum == pytest.approx(0.50, abs=1e-6)
        assert draw_sum == pytest.approx(0.30, abs=1e-6)
        assert away_sum == pytest.approx(0.20, abs=1e-6)
        assert (home_sum + draw_sum + away_sum) == pytest.approx(1.0, abs=1e-6)
    
    def test_proportional_rescaling_within_category(self):
        """Test that within-category scoreline proportions are preserved."""
        integration = CalibrationIntegration()
        
        # Home category has 3 scorelines with specific proportions
        score_dist = {
            (1, 0): 0.20,  # 20% of total, 40% of home
            (2, 0): 0.15,  # 15% of total, 30% of home
            (2, 1): 0.15,  # 15% of total, 30% of home
            (0, 0): 0.50,  # Draw
        }
        # Home category original sum = 0.50
        
        rescaled = integration._rescale_score_distribution(
            score_dist, 0.50, 0.50, 0.0,
            0.30, 0.70, 0.0
        )
        
        # Within home category, proportions should be preserved
        # Original: (1,0)=0.20, (2,0)=0.15, (2,1)=0.15 → ratio 4:3:3
        home_scorelines = {k: v for k, v in rescaled.items() if k[0] > k[1]}
        
        # New values should be scaled proportionally
        # Scale = 0.30 / 0.50 = 0.6
        assert home_scorelines[(1, 0)] == pytest.approx(0.20 * 0.6, abs=1e-6)
        assert home_scorelines[(2, 0)] == pytest.approx(0.15 * 0.6, abs=1e-6)
        assert home_scorelines[(2, 1)] == pytest.approx(0.15 * 0.6, abs=1e-6)
        
        # Ratio preserved: 4:3:3
        ratio_12 = home_scorelines[(1, 0)] / home_scorelines[(2, 0)]
        ratio_23 = home_scorelines[(2, 0)] / home_scorelines[(2, 1)]
        assert ratio_12 == pytest.approx(0.20 / 0.15, abs=1e-6)
        assert ratio_23 == pytest.approx(1.0, abs=1e-6)
    
    def test_extreme_calibration_adjustment(self):
        """Test extreme calibration shift (e.g., 0.10 → 0.60)."""
        integration = CalibrationIntegration()
        
        score_dist = {
            (1, 0): 0.05,
            (2, 0): 0.05,  # Home sum = 0.10
            (0, 0): 0.30,  # Draw sum = 0.30
            (0, 1): 0.40,
            (0, 2): 0.20,  # Away sum = 0.60
        }
        
        # Extreme shift: home 0.10 → 0.60
        rescaled = integration._rescale_score_distribution(
            score_dist, 0.10, 0.30, 0.60,
            0.60, 0.20, 0.20
        )
        
        home_sum = sum(p for (h, a), p in rescaled.items() if h > a)
        draw_sum = sum(p for (h, a), p in rescaled.items() if h == a)
        away_sum = sum(p for (h, a), p in rescaled.items() if h < a)
        
        assert home_sum == pytest.approx(0.60, abs=1e-6)
        assert draw_sum == pytest.approx(0.20, abs=1e-6)
        assert away_sum == pytest.approx(0.20, abs=1e-6)
    
    def test_empty_distribution_handled(self):
        """Test that empty distribution is handled gracefully."""
        integration = CalibrationIntegration()
        
        score_dist = {}
        
        rescaled = integration._rescale_score_distribution(
            score_dist, 0.33, 0.33, 0.34,
            0.50, 0.30, 0.20
        )
        
        # Empty distribution should stay empty (no fallback without scores)
        assert len(rescaled) == 0
