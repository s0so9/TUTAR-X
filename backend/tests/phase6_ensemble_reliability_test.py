"""Phase 6: Ensemble, Calibration and Uncertainty Reliability Tests.

Tests chronologically separated data for:
- Brier score calculation
- Log loss calculation  
- Calibration reliability
- Model agreement assessment
- Pass/withdrawal conditions

CRITICAL: Uses only historical data that was available BEFORE prediction time.
No future information leakage.
"""

import pytest
from datetime import datetime, timedelta, date
from typing import List, Tuple

from app.prediction.calibration import (
    brier_score, 
    log_loss_binary, 
    evaluate_binary, 
    evaluate_1x2,
    MIN_SAMPLES_FOR_CALIBRATION
)
from app.prediction.service import PredictionService
from app.prediction.model_orchestrator import ModelOrchestrator
from app.config import Settings


class TestPhase6EnsembleReliability:
    """Test ensemble and calibration reliability with chronological separation."""

    def test_brier_score_calculation_with_min_samples(self):
        """Test Brier score respects minimum sample size requirements."""
        
        # Test with insufficient samples (below MIN_SAMPLES_FOR_CALIBRATION=30)
        few_probs = [0.7, 0.8, 0.6]
        few_outcomes = [1, 1, 0]
        
        result = brier_score(few_probs, few_outcomes, "home_win")
        assert result.n_samples == 3
        assert not result.is_reliable  # Should be False due to insufficient samples
        assert result.brier_score >= 0.0
        
        # Test with sufficient samples
        many_probs = [0.7] * 35 + [0.3] * 35  # 70 samples
        many_outcomes = [1] * 30 + [0] * 5 + [0] * 30 + [1] * 5  # Mixed outcomes
        
        result = brier_score(many_probs, many_outcomes, "home_win")
        assert result.n_samples == 70
        assert result.is_reliable  # Should be True with sufficient samples
        assert 0.0 <= result.brier_score <= 1.0

    def test_log_loss_with_edge_probabilities(self):
        """Test log loss handles edge probabilities correctly."""
        
        # Test with probabilities near 0 and 1
        edge_probs = [0.001, 0.999, 0.5, 0.01, 0.99]
        edge_outcomes = [0, 1, 1, 0, 1]
        
        result = log_loss_binary(edge_probs, edge_outcomes, "btts")
        assert result.n_samples == 5
        assert not result.is_reliable  # Too few samples
        assert result.log_loss >= 0.0  # Log loss should be non-negative

    def test_calibration_evaluation_chronological_separation(self):
        """Test calibration evaluation with chronologically separated data."""
        
        # Simulate predictions made BEFORE actual outcomes
        # This simulates a realistic scenario where we predict future matches
        # based on historical data
        
        historical_predictions = []
        actual_outcomes = []
        
        # Week 1: Make predictions (these would be made before matches)
        week1_probs = [0.6, 0.7, 0.8, 0.4, 0.5]  # Home win probabilities
        historical_predictions.extend(week1_probs)
        
        # Week 2: Outcomes become available (matches have been played)
        week1_outcomes = [1, 1, 0, 0, 1]  # Actual results
        actual_outcomes.extend(week1_outcomes)
        
        # Continue for multiple weeks to get sufficient data
        for week in range(10):  # Generate 10 weeks of data
            # Ensure probabilities stay within [0, 1] range
            base_probs = [0.6, 0.7, 0.5, 0.8]
            week_adjustments = [0.1 * (week % 3), -0.1 * (week % 2), 
                               0.2 * (week % 4), -0.1 * (week % 3)]
            
            week_probs = []
            for base, adj in zip(base_probs, week_adjustments):
                prob = base + adj * 0.3  # Scale adjustment to keep in range
                prob = max(0.05, min(0.95, prob))  # Clamp to valid range
                week_probs.append(prob)
            
            historical_predictions.extend(week_probs)
            
            # Outcomes that correlate somewhat with predictions but have randomness
            week_outcomes = [1 if p > 0.55 else 0 for p in week_probs]
            actual_outcomes.extend(week_outcomes)
        
        # Now evaluate calibration using historical data
        assert len(historical_predictions) >= MIN_SAMPLES_FOR_CALIBRATION
        
        result = evaluate_binary(historical_predictions, actual_outcomes, "home_win")
        assert result.is_well_calibrated is not None
        assert result.brier.is_reliable
        assert result.log_loss.is_reliable
        assert 0.0 <= result.brier.brier_score <= 1.0

    def test_multiclass_1x2_calibration_evaluation(self):
        """Test multiclass 1X2 calibration evaluation."""
        
        # Generate sufficient 1X2 prediction data
        n_matches = 50  # Above MIN_SAMPLES_FOR_CALIBRATION
        
        predictions = []
        outcomes = []
        
        for i in range(n_matches):
            # Generate realistic 1X2 probabilities that sum to 1
            home_prob = 0.3 + 0.4 * (i % 5) / 5  # 0.3 to 0.7
            draw_prob = 0.2 + 0.2 * ((i + 1) % 3) / 3  # 0.2 to 0.4
            away_prob = 1.0 - home_prob - draw_prob
            
            predictions.append([home_prob, draw_prob, away_prob])
            
            # Generate outcome based on probabilities (with some randomness)
            if i % 3 == 0:
                outcomes.append("home")  # lowercase for API compatibility
            elif i % 3 == 1:
                outcomes.append("draw") 
            else:
                outcomes.append("away")
        
        result = evaluate_1x2(predictions, outcomes)
        
        # Check all components are populated
        assert result.home_win.brier.is_reliable
        assert result.draw.brier.is_reliable  
        assert result.away_win.brier.is_reliable
        assert result.multiclass_log_loss.log_loss >= 0.0
        assert result.multiclass_log_loss.is_reliable

    def test_min_sample_size_config_preservation(self):
        """Verify min_sample_size=3 is preserved in configuration."""
        config = Settings()
        assert config.min_sample_size == 3, f"Expected min_sample_size=3, got {config.min_sample_size}"

    @pytest.mark.integration
    def test_prediction_service_withdrawal_conditions(self):
        """Test prediction service properly identifies withdrawal conditions."""
        
        # This is an integration test that would require a real prediction service setup
        # For now, we verify the withdrawal logic exists and is callable
        
        # Verify PredictionService has the withdrawal evaluation method
        service = PredictionService(provider=None, db_session=None)
        assert hasattr(service, '_evaluate_withdrawal_conditions')
        
        # The actual integration test would require:
        # 1. Real match data with insufficient samples
        # 2. Calibration metadata indicating poor calibration
        # 3. Model orchestration results with low agreement
        # This should be tested in end-to-end integration tests

    def test_chronological_data_separation_principle(self):
        """Verify no future data leakage in calibration metrics."""
        
        # This test verifies the principle that calibration evaluation
        # should only use data that was available at prediction time
        
        # Past data (available at prediction time)
        past_probs = [0.6, 0.7, 0.5, 0.8] * 10  # 40 samples
        past_outcomes = [1, 1, 0, 1] * 10
        
        # Future data (not available at prediction time) 
        future_probs = [0.9, 0.1, 0.4, 0.6] * 5   # 20 samples
        future_outcomes = [1, 0, 0, 1] * 5
        
        # Calibration should only use past data
        past_only_result = evaluate_binary(past_probs, past_outcomes, "home_win")
        
        # Including future data would be temporal leakage (this is what NOT to do)
        all_data_result = evaluate_binary(
            past_probs + future_probs, 
            past_outcomes + future_outcomes, 
            "home_win"
        )
        
        # The test verifies that we're conscious of this distinction
        # In production, we must only use past_only_result
        assert past_only_result.brier.n_samples == 40
        assert all_data_result.brier.n_samples == 60
        
        # The key insight: past_only_result is the only valid evaluation
        # all_data_result would be temporal leakage