"""Tests for uncertainty assessment engine."""

import pytest
from unittest.mock import Mock

from app.prediction.uncertainty_engine import (
    UncertaintyEngine,
    UncertaintyAssessment,
    UncertaintyComponents,
    UncertaintyLevel
)
from app.prediction.model_disagreement import ModelDisagreementResult
from app.prediction.calibration_engine import CalibrationStatus


class TestUncertaintyEngine:
    """Test UncertaintyEngine."""
    
    def test_assess_low_uncertainty(self):
        """Test assessment with low uncertainty conditions."""
        engine = UncertaintyEngine()
        
        # High agreement, high quality, sufficient samples, fitted calibration
        disagreement = ModelDisagreementResult(
            model_count=5,
            available_model_count=5,
            mean_probability=0.65,
            probability_std=0.02,
            probability_range=0.05,
            agreement_score=0.94,  # High agreement
            disagreement_score=0.06,  # Low disagreement
            model_probabilities={}
        )
        
        feature_availability = {"availability_ratio": 0.95}  # 95% features available
        
        assessment = engine.assess(
            model_disagreement=disagreement,
            data_quality_score=0.9,
            feature_availability=feature_availability,
            sample_size=50,
            calibration_status="FITTED"
        )
        
        assert isinstance(assessment, UncertaintyAssessment)
        assert assessment.overall_uncertainty < 0.3
        assert assessment.uncertainty_level == UncertaintyLevel.LOW
        assert assessment.implied_confidence > 0.7
        assert "low uncertainty" in assessment.interpretation.lower()
    
    def test_assess_high_uncertainty(self):
        """Test assessment with high uncertainty conditions."""
        engine = UncertaintyEngine()
        
        # Low agreement, poor quality, few samples, not fitted
        disagreement = ModelDisagreementResult(
            model_count=5,
            available_model_count=5,
            mean_probability=0.50,
            probability_std=0.15,
            probability_range=0.35,
            agreement_score=0.25,  # Low agreement
            disagreement_score=0.75,  # High disagreement
            model_probabilities={}
        )
        
        feature_availability = {"availability_ratio": 0.40}  # Only 40% features
        
        assessment = engine.assess(
            model_disagreement=disagreement,
            data_quality_score=0.3,
            feature_availability=feature_availability,
            sample_size=10,  # Few samples
            calibration_status="NOT_FITTED"
        )
        
        assert assessment.overall_uncertainty > 0.6
        assert assessment.uncertainty_level in [UncertaintyLevel.HIGH, UncertaintyLevel.VERY_HIGH]
        assert assessment.implied_confidence < 0.4
    
    def test_assess_medium_uncertainty(self):
        """Test assessment with medium uncertainty conditions."""
        engine = UncertaintyEngine()
        
        disagreement = ModelDisagreementResult(
            model_count=5,
            available_model_count=5,
            mean_probability=0.60,
            probability_std=0.08,
            probability_range=0.18,
            agreement_score=0.60,  # Medium agreement
            disagreement_score=0.40,
            model_probabilities={}
        )
        
        feature_availability = {"availability_ratio": 0.75}
        
        assessment = engine.assess(
            model_disagreement=disagreement,
            data_quality_score=0.7,
            feature_availability=feature_availability,
            sample_size=25,
            calibration_status="INSUFFICIENT_DATA"
        )
        
        assert 0.3 <= assessment.overall_uncertainty <= 0.6
        assert assessment.uncertainty_level == UncertaintyLevel.MEDIUM
    
    def test_uncertainty_components_calculated(self):
        """Test that individual components are calculated correctly."""
        engine = UncertaintyEngine()
        
        disagreement = ModelDisagreementResult(
            model_count=3,
            available_model_count=3,
            mean_probability=0.50,
            probability_std=0.05,
            probability_range=0.12,
            agreement_score=0.85,
            disagreement_score=0.15,
            model_probabilities={}
        )
        
        assessment = engine.assess(
            model_disagreement=disagreement,
            data_quality_score=0.8,
            feature_availability={"availability_ratio": 0.9},
            sample_size=30,
            calibration_status="FITTED"
        )
        
        components = assessment.components
        assert isinstance(components, UncertaintyComponents)
        assert 0.0 <= components.model_disagreement <= 1.0
        assert 0.0 <= components.data_quality_deficit <= 1.0
        assert 0.0 <= components.feature_availability_deficit <= 1.0
        assert 0.0 <= components.sample_size_inadequacy <= 1.0
        assert 0.0 <= components.calibration_uncertainty <= 1.0
    
    def test_calibration_status_impact(self):
        """Test that calibration status affects uncertainty correctly."""
        engine = UncertaintyEngine()
        
        disagreement = ModelDisagreementResult(
            model_count=3,
            available_model_count=3,
            mean_probability=0.65,
            probability_std=0.03,
            probability_range=0.08,
            agreement_score=0.90,
            disagreement_score=0.10,
            model_probabilities={}
        )
        
        feature_availability = {"availability_ratio": 0.9}
        
        # Test FITTED (lowest uncertainty)
        fitted_assessment = engine.assess(
            model_disagreement=disagreement,
            data_quality_score=0.9,
            feature_availability=feature_availability,
            sample_size=50,
            calibration_status="FITTED"
        )
        
        # Test NOT_FITTED (highest uncertainty)
        not_fitted_assessment = engine.assess(
            model_disagreement=disagreement,
            data_quality_score=0.9,
            feature_availability=feature_availability,
            sample_size=50,
            calibration_status="NOT_FITTED"
        )
        
        # NOT_FITTED should have higher uncertainty
        assert not_fitted_assessment.overall_uncertainty > fitted_assessment.overall_uncertainty
