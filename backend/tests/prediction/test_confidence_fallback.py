"""Test confidence fallback handles errors gracefully without raising new exceptions."""

import pytest
from app.prediction.confidence_engine import ConfidenceComponents, ConfidenceWeights, ConfidenceAssessment


class TestConfidenceFallback:
    """Test that confidence fallback doesn't raise TypeError."""
    
    def test_fallback_confidence_components_no_error(self):
        """Test that fallback ConfidenceComponents doesn't raise TypeError."""
        # This should not raise TypeError about wrong parameter names
        components = ConfidenceComponents(
            model_agreement=0.0,
            data_quality=0.0,
            sample_size_score=0.0,
            calibration_reliability=0.0,
            lineup_certainty=0.0,
            feature_stability=0.0,
        )
        
        # Validate should pass with all zeros
        components.validate()
        
        assert components.model_agreement == 0.0
        assert components.data_quality == 0.0
        assert components.sample_size_score == 0.0
        assert components.calibration_reliability == 0.0
        assert components.lineup_certainty == 0.0
        assert components.feature_stability == 0.0
    
    def test_fallback_confidence_assessment_valid(self):
        """Test that fallback confidence assessment is valid."""
        assessment = ConfidenceAssessment(
            overall_confidence=0.0,
            confidence_label="INSUFFICIENT_DATA",
            components=ConfidenceComponents(
                model_agreement=0.0,
                data_quality=0.0,
                sample_size_score=0.0,
                calibration_reliability=0.0,
                lineup_certainty=0.0,
                feature_stability=0.0,
            ),
            weights=ConfidenceWeights(),
            component_breakdown={}
        )
        
        assert assessment.overall_confidence == 0.0
        assert assessment.confidence_label == "INSUFFICIENT_DATA"
        assert assessment.components.model_agreement == 0.0
    
    def test_old_parameter_names_raise_type_error(self):
        """Test that old parameter names correctly raise TypeError."""
        with pytest.raises(TypeError, match="sample_size"):
            ConfidenceComponents(
                model_agreement=0.0,
                data_quality=0.0,
                sample_size=0.0,  # WRONG - should be sample_size_score
                calibration_reliability=0.0,
                lineup_certainty=0.0,
                prediction_stability=0.0,  # WRONG - should be feature_stability
            )
