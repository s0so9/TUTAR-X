"""Tests for calibration integration."""

import pytest
from app.prediction.model_orchestrator import (
    Calibrator1X2,
    CalibrationIntegration,
)
from app.prediction.interfaces import ModelPrediction
from app.prediction.calibration_engine import IsotonicCalibration, CalibrationData
from datetime import datetime


class TestCalibrator1X2:
    """Test Calibrator1X2 class."""
    
    def test_init(self):
        """Test initializing calibrator."""
        calibrator = Calibrator1X2()
        
        assert calibrator.home_calibrator is not None
        assert calibrator.draw_calibrator is not None
        assert calibrator.away_calibrator is not None
        assert not calibrator.is_fitted
    
    def test_calibrate_unfitted_returns_original(self):
        """Test that unfitted calibrator returns original probabilities."""
        calibrator = Calibrator1X2()
        
        home, draw, away = calibrator.calibrate_1x2(0.45, 0.30, 0.25)
        
        # Should return unchanged
        assert home == 0.45
        assert draw == 0.30
        assert away == 0.25
    
    def test_calibrate_renormalizes(self):
        """Test that calibrated probabilities sum to 1.0."""
        calibrator = Calibrator1X2()
        
        # Even if unfitted, should preserve sum
        home, draw, away = calibrator.calibrate_1x2(0.45, 0.30, 0.25)
        
        total = home + draw + away
        assert 0.999 <= total <= 1.001


class TestCalibrationIntegration:
    """Test CalibrationIntegration class."""
    
    def test_create_default(self):
        """Test creating default calibration integration."""
        integration = CalibrationIntegration.create_default()
        
        assert integration is not None
        assert integration.calibrator is not None
        assert not integration.calibrator.is_fitted
    
    def test_calibrate_with_unfitted_returns_unchanged(self):
        """Test calibration with unfitted calibrator returns uncalibrated."""
        integration = CalibrationIntegration.create_default()
        
        prediction = ModelPrediction(
            model_id="test_model",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.85,
        )
        
        calibrated = integration.calibrate_prediction(prediction)
        
        # Probabilities should be unchanged (unfitted)
        assert calibrated.home_win_prob == 0.45
        assert calibrated.draw_prob == 0.30
        assert calibrated.away_win_prob == 0.25
        
        # Metadata should indicate uncalibrated
        assert calibrated.metadata["calibration_status"] == "uncalibrated_fallback"
        assert calibrated.metadata["is_calibrated"] is False
        assert calibrated.metadata["original_home_prob"] == 0.45
    
    def test_calibrate_preserves_other_fields(self):
        """Test that calibration preserves non-probability fields."""
        integration = CalibrationIntegration.create_default()
        
        prediction = ModelPrediction(
            model_id="poisson_v1",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.85,
            metadata={"existing_key": "existing_value"}
        )
        
        calibrated = integration.calibrate_prediction(prediction)
        
        # Model ID should be preserved
        assert calibrated.model_id == "poisson_v1"
        
        # Expected goals should be preserved
        assert calibrated.home_score_mean == 1.5
        assert calibrated.away_score_mean == 1.2
        
        # Confidence and data quality preserved
        assert calibrated.confidence_score == 0.8
        assert calibrated.data_quality_score == 0.85
        
        # Existing metadata preserved
        assert calibrated.metadata["existing_key"] == "existing_value"
        
        # New calibration metadata added
        assert "calibration_status" in calibrated.metadata
    
    def test_calibrated_probabilities_sum_to_one(self):
        """Test that calibrated probabilities always sum to 1.0."""
        integration = CalibrationIntegration.create_default()
        
        prediction = ModelPrediction(
            model_id="test_model",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.85,
        )
        
        calibrated = integration.calibrate_prediction(prediction)
        
        total = calibrated.home_win_prob + calibrated.draw_prob + calibrated.away_win_prob
        assert 0.999 <= total <= 1.001
    
    def test_calibration_status_metadata(self):
        """Test that calibration status is properly recorded in metadata."""
        integration = CalibrationIntegration.create_default()
        
        prediction = ModelPrediction(
            model_id="test_model",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.85,
        )
        
        calibrated = integration.calibrate_prediction(prediction)
        
        # Check all expected metadata keys
        assert "calibration_status" in calibrated.metadata
        assert "is_calibrated" in calibrated.metadata
        assert "original_home_prob" in calibrated.metadata
        assert "original_draw_prob" in calibrated.metadata
        assert "original_away_prob" in calibrated.metadata
        
        # Verify status
        assert calibrated.metadata["calibration_status"] in [
            "calibrated",
            "uncalibrated_fallback",
            "insufficient_data"
        ]
