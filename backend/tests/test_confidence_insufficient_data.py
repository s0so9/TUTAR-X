"""Test confidence assessment with insufficient/unknown data quality.

This test ensures that missing data quality report is properly flagged
as "insufficient" rather than defaulting to medium quality (0.5).
"""

import pytest
from app.prediction.confidence_engine import ConfidenceEngine


class TestConfidenceInsufficientData:
    """Test confidence assessment handles insufficient data correctly."""
    
    def test_none_data_quality_produces_low_insufficient_label(self):
        """Test that None data quality results in LOW_INSUFFICIENT_DATA label."""
        engine = ConfidenceEngine()
        
        assessment = engine.assess(
            model_agreement=0.8,
            data_quality_score=None,  # Unknown/insufficient
            n_matches=10,
            brier_score=0.1,
            lineup_status="expected"
        )
        
        assert assessment.confidence_label == "LOW_INSUFFICIENT_DATA", \
            "None data quality should produce LOW_INSUFFICIENT_DATA label"
    
    def test_none_data_quality_caps_overall_confidence(self):
        """Test that None data quality caps confidence at LOW tier."""
        engine = ConfidenceEngine()
        
        # Even with perfect other metrics, should be capped
        assessment = engine.assess(
            model_agreement=1.0,  # Perfect agreement
            data_quality_score=None,  # But unknown data quality
            n_matches=100,  # Lots of data
            brier_score=0.0,  # Perfect calibration
            lineup_status="confirmed"  # Confirmed lineup
        )
        
        assert assessment.overall_confidence < 0.4, \
            "Insufficient data quality should cap confidence below MEDIUM (0.4)"
        assert assessment.confidence_label == "LOW_INSUFFICIENT_DATA"
    
    def test_valid_data_quality_normal_behavior(self):
        """Test that valid data quality score works normally."""
        engine = ConfidenceEngine()
        
        assessment = engine.assess(
            model_agreement=0.9,
            data_quality_score=0.8,  # Valid score
            n_matches=20,
            brier_score=0.05,
            lineup_status="confirmed"
        )
        
        # Should get HIGH or MEDIUM confidence
        assert assessment.confidence_label in ["HIGH", "MEDIUM"], \
            "Valid high scores should produce HIGH or MEDIUM confidence"
        assert assessment.overall_confidence >= 0.4
    
    def test_low_data_quality_score_different_from_none(self):
        """Test that low data quality score (0.1) is different from None."""
        engine = ConfidenceEngine()
        
        # Low but known data quality
        assessment_low = engine.assess(
            model_agreement=0.8,
            data_quality_score=0.1,  # Low but known
            n_matches=10,
            brier_score=0.1,
            lineup_status="expected"
        )
        
        # Unknown data quality
        assessment_none = engine.assess(
            model_agreement=0.8,
            data_quality_score=None,  # Unknown
            n_matches=10,
            brier_score=0.1,
            lineup_status="expected"
        )
        
        # None should have special label
        assert assessment_none.confidence_label == "LOW_INSUFFICIENT_DATA"
        # Low score should have standard LOW label
        assert assessment_low.confidence_label in ["LOW", "MEDIUM"]
    
    def test_insufficient_data_flag_in_breakdown(self):
        """Test that insufficient data is flagged in component breakdown."""
        engine = ConfidenceEngine()
        
        assessment = engine.assess(
            model_agreement=0.8,
            data_quality_score=None,
            n_matches=10
        )
        
        assert "data_quality_status" in assessment.component_breakdown, \
            "Should flag data quality status in breakdown"
        assert assessment.component_breakdown["data_quality_status"] == "insufficient", \
            "Should mark as 'insufficient'"
    
    def test_valid_data_no_insufficient_flag(self):
        """Test that valid data doesn't add insufficient flag."""
        engine = ConfidenceEngine()
        
        assessment = engine.assess(
            model_agreement=0.8,
            data_quality_score=0.7,  # Valid
            n_matches=10
        )
        
        # Should not have data_quality_status key (or if it does, not "insufficient")
        if "data_quality_status" in assessment.component_breakdown:
            assert assessment.component_breakdown["data_quality_status"] != "insufficient"
    
    def test_zero_data_quality_different_from_none(self):
        """Test that explicit 0.0 data quality is different from None."""
        engine = ConfidenceEngine()
        
        # Explicit 0.0 (known to be bad)
        assessment_zero = engine.assess(
            model_agreement=0.8,
            data_quality_score=0.0,  # Explicitly 0
            n_matches=10
        )
        
        # None (unknown)
        assessment_none = engine.assess(
            model_agreement=0.8,
            data_quality_score=None,  # Unknown
            n_matches=10
        )
        
        # None should trigger special handling
        assert assessment_none.confidence_label == "LOW_INSUFFICIENT_DATA"
        assert "data_quality_status" in assessment_none.component_breakdown
        
        # Explicit 0.0 should not trigger insufficient flag
        # (it's a valid score, just very low)
        if "data_quality_status" in assessment_zero.component_breakdown:
            assert assessment_zero.component_breakdown["data_quality_status"] != "insufficient"
    
    def test_data_quality_component_score_with_none(self):
        """Test that data_quality component is set to 0.0 when None is passed."""
        engine = ConfidenceEngine()
        
        assessment = engine.assess(
            model_agreement=0.8,
            data_quality_score=None,
            n_matches=10
        )
        
        assert assessment.components.data_quality == 0.0, \
            "None data quality should be treated as 0.0 in components"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
