"""Tests for confidence_engine module."""

import pytest
from app.prediction.confidence_engine import (
    ConfidenceEngine,
    ConfidenceComponents,
    ConfidenceWeights,
    ConfidenceAssessment,
)


class TestConfidenceComponents:
    """Tests for ConfidenceComponents."""
    
    def test_components_validation_success(self):
        """Test that valid components pass validation."""
        components = ConfidenceComponents(
            model_agreement=0.8,
            data_quality=0.9,
            sample_size_score=0.7,
            calibration_reliability=0.85,
            lineup_certainty=1.0,
            feature_stability=0.95
        )
        
        components.validate()  # Should not raise
    
    def test_components_validation_out_of_range(self):
        """Test that out-of-range component raises ValueError."""
        components = ConfidenceComponents(model_agreement=1.5)
        
        with pytest.raises(ValueError, match="model_agreement must be in"):
            components.validate()


class TestConfidenceWeights:
    """Tests for ConfidenceWeights."""
    
    def test_default_weights_sum_to_one(self):
        """Test that default weights sum to approximately 1.0."""
        weights = ConfidenceWeights()
        weights.validate()  # Should not raise
    
    def test_weights_normalize(self):
        """Test that normalize() makes weights sum to 1.0."""
        weights = ConfidenceWeights(
            model_agreement=0.3,
            data_quality=0.3,
            sample_size_score=0.2,
            calibration_reliability=0.1,
            lineup_certainty=0.05,
            feature_stability=0.05
        )
        
        weights.normalize()
        
        total = (
            weights.model_agreement +
            weights.data_quality +
            weights.sample_size_score +
            weights.calibration_reliability +
            weights.lineup_certainty +
            weights.feature_stability
        )
        
        assert total == pytest.approx(1.0)


class TestConfidenceEngine:
    """Tests for ConfidenceEngine."""
    
    def test_engine_initialization_with_defaults(self):
        """Test engine initialization with default weights."""
        engine = ConfidenceEngine()
        assert engine.weights is not None
    
    def test_engine_initialization_with_custom_weights(self):
        """Test engine initialization with custom weights."""
        custom_weights = ConfidenceWeights(
            model_agreement=0.4,
            data_quality=0.3,
            sample_size_score=0.1,
            calibration_reliability=0.1,
            lineup_certainty=0.05,
            feature_stability=0.05
        )
        
        engine = ConfidenceEngine(weights=custom_weights)
        assert engine.weights.model_agreement == pytest.approx(0.4)
    
    def test_assess_high_confidence(self):
        """Test assessment with high confidence inputs."""
        engine = ConfidenceEngine()
        
        assessment = engine.assess(
            model_agreement=0.9,
            data_quality_score=0.95,
            n_matches=100,
            brier_score=0.15,
            lineup_status="confirmed",
            recent_predictions=[0.55, 0.54, 0.56, 0.55]
        )
        
        assert isinstance(assessment, ConfidenceAssessment)
        assert assessment.confidence_label == "HIGH"
        assert assessment.overall_confidence > 0.7
    
    def test_assess_medium_confidence(self):
        """Test assessment with medium confidence inputs."""
        engine = ConfidenceEngine()
        
        assessment = engine.assess(
            model_agreement=0.6,
            data_quality_score=0.7,
            n_matches=20,
            brier_score=0.25,
            lineup_status="expected",
            recent_predictions=None
        )
        
        assert assessment.confidence_label == "MEDIUM"
        assert 0.4 <= assessment.overall_confidence <= 0.7
    
    def test_assess_low_confidence(self):
        """Test assessment with low confidence inputs."""
        engine = ConfidenceEngine()
        
        assessment = engine.assess(
            model_agreement=0.2,
            data_quality_score=0.4,
            n_matches=3,
            brier_score=0.40,
            lineup_status="unknown",
            recent_predictions=[0.2, 0.8, 0.3, 0.7, 0.4]  # High variance
        )
        
        assert assessment.confidence_label == "LOW"
        assert assessment.overall_confidence < 0.4
    
    def test_sample_size_score_calculation(self):
        """Test sample size score calculation (sigmoid)."""
        engine = ConfidenceEngine()
        
        # With 30 matches (inflection point), should be ~0.5
        assessment = engine.assess(
            model_agreement=1.0,
            data_quality_score=1.0,
            n_matches=30,
            brier_score=0.0
        )
        
        # Sample size score should be around 0.5 at inflection
        assert 0.45 <= assessment.components.sample_size_score <= 0.55
    
    def test_sample_size_score_increases_with_matches(self):
        """Test that sample size score increases with more matches."""
        engine = ConfidenceEngine()
        
        assessment_10 = engine.assess(
            model_agreement=1.0,
            data_quality_score=1.0,
            n_matches=10
        )
        
        assessment_100 = engine.assess(
            model_agreement=1.0,
            data_quality_score=1.0,
            n_matches=100
        )
        
        assert assessment_100.components.sample_size_score > assessment_10.components.sample_size_score
    
    def test_calibration_reliability_from_brier_score(self):
        """Test calibration reliability calculation from Brier score."""
        engine = ConfidenceEngine()
        
        # Brier score of 0.1 should give reliability of 0.9
        assessment = engine.assess(
            model_agreement=1.0,
            data_quality_score=1.0,
            n_matches=100,
            brier_score=0.1
        )
        
        assert assessment.components.calibration_reliability == pytest.approx(0.9)
    
    def test_calibration_reliability_defaults_without_brier(self):
        """Test default calibration reliability when Brier score unavailable."""
        engine = ConfidenceEngine()
        
        assessment = engine.assess(
            model_agreement=1.0,
            data_quality_score=1.0,
            n_matches=100,
            brier_score=None
        )
        
        # Should default to neutral value (0.7)
        assert assessment.components.calibration_reliability == 0.7
    
    def test_lineup_certainty_confirmed(self):
        """Test lineup certainty for confirmed lineup."""
        engine = ConfidenceEngine()
        
        assessment = engine.assess(
            model_agreement=1.0,
            data_quality_score=1.0,
            n_matches=100,
            lineup_status="confirmed"
        )
        
        assert assessment.components.lineup_certainty == 1.0
    
    def test_lineup_certainty_expected(self):
        """Test lineup certainty for expected lineup."""
        engine = ConfidenceEngine()
        
        assessment = engine.assess(
            model_agreement=1.0,
            data_quality_score=1.0,
            n_matches=100,
            lineup_status="expected"
        )
        
        assert assessment.components.lineup_certainty == 0.5
    
    def test_lineup_certainty_unknown(self):
        """Test lineup certainty for unknown lineup."""
        engine = ConfidenceEngine()
        
        assessment = engine.assess(
            model_agreement=1.0,
            data_quality_score=1.0,
            n_matches=100,
            lineup_status="unknown"
        )
        
        assert assessment.components.lineup_certainty == 0.0
    
    def test_feature_stability_high_with_low_variance(self):
        """Test high feature stability with consistent predictions."""
        engine = ConfidenceEngine()
        
        assessment = engine.assess(
            model_agreement=1.0,
            data_quality_score=1.0,
            n_matches=100,
            recent_predictions=[0.50, 0.51, 0.49, 0.50, 0.51]
        )
        
        # Low variance → high stability
        assert assessment.components.feature_stability > 0.9
    
    def test_feature_stability_low_with_high_variance(self):
        """Test low feature stability with inconsistent predictions."""
        engine = ConfidenceEngine()
        
        assessment = engine.assess(
            model_agreement=1.0,
            data_quality_score=1.0,
            n_matches=100,
            recent_predictions=[0.1, 0.9, 0.2, 0.8, 0.3]  # Very high variance
        )
        
        # High variance → low stability
        assert assessment.components.feature_stability < 0.7
    
    def test_feature_stability_defaults_without_predictions(self):
        """Test default feature stability without recent predictions."""
        engine = ConfidenceEngine()
        
        assessment = engine.assess(
            model_agreement=1.0,
            data_quality_score=1.0,
            n_matches=100,
            recent_predictions=None
        )
        
        # Should default to neutral (0.5) when no measurement available
        assert assessment.components.feature_stability == 0.5
    
    def test_component_breakdown_included(self):
        """Test that component breakdown is included in assessment."""
        engine = ConfidenceEngine()
        
        assessment = engine.assess(
            model_agreement=0.8,
            data_quality_score=0.9,
            n_matches=50
        )
        
        assert len(assessment.component_breakdown) == 6
        assert "model_agreement" in assessment.component_breakdown
        assert "data_quality" in assessment.component_breakdown
        
        # Weighted contributions should sum to overall confidence
        total_contribution = sum(assessment.component_breakdown.values())
        assert total_contribution == pytest.approx(assessment.overall_confidence)
