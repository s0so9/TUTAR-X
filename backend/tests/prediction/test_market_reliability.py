"""Tests for market reliability assessment."""

import pytest
from unittest.mock import Mock

from app.prediction.market_reliability import (
    MarketReliabilityCalculator,
    MarketReliability,
    ReliabilityLevel,
    BettingRecommendation
)
from app.prediction.calibration_engine import CalibrationStatus
from app.prediction.uncertainty_engine import (
    UncertaintyAssessment,
    UncertaintyComponents,
    UncertaintyLevel
)


class TestMarketReliabilityCalculator:
    """Test MarketReliabilityCalculator."""
    
    def test_calculate_high_reliability(self):
        """Test calculation with high reliability conditions."""
        calculator = MarketReliabilityCalculator()
        
        # High conviction, fitted calibration, low uncertainty, high data quality
        uncertainty = UncertaintyAssessment(
            overall_uncertainty=0.15,
            uncertainty_level=UncertaintyLevel.LOW,
            components=UncertaintyComponents(
                model_disagreement=0.10,
                data_quality_deficit=0.10,
                feature_availability_deficit=0.10,
                sample_size_inadequacy=0.20,
                calibration_uncertainty=0.0,
                probability_dispersion=0.0
            ),
            interpretation="Low uncertainty",
            implied_confidence=0.85
        )
        
        reliability = calculator.calculate(
            market_key="HOME_WIN",
            probability=0.70,  # High conviction
            calibration_status=CalibrationStatus.FITTED,
            uncertainty_assessment=uncertainty,
            data_quality_score=0.90
        )
        
        assert isinstance(reliability, MarketReliability)
        assert reliability.reliability_score >= 0.7
        assert reliability.reliability_level == ReliabilityLevel.HIGH
        assert reliability.recommendation in [BettingRecommendation.STRONG_BET, BettingRecommendation.CONSIDER]
    
    def test_calculate_low_reliability(self):
        """Test calculation with low reliability conditions."""
        calculator = MarketReliabilityCalculator()
        
        # Low conviction, no calibration, high uncertainty, poor data
        uncertainty = UncertaintyAssessment(
            overall_uncertainty=0.75,
            uncertainty_level=UncertaintyLevel.VERY_HIGH,
            components=UncertaintyComponents(
                model_disagreement=0.80,
                data_quality_deficit=0.70,
                feature_availability_deficit=0.60,
                sample_size_inadequacy=0.80,
                calibration_uncertainty=0.50,
                probability_dispersion=0.40
            ),
            interpretation="Very high uncertainty",
            implied_confidence=0.25
        )
        
        reliability = calculator.calculate(
            market_key="HOME_WIN",
            probability=0.52,  # Low conviction (near 0.5)
            calibration_status=CalibrationStatus.NOT_FITTED,
            uncertainty_assessment=uncertainty,
            data_quality_score=0.30
        )
        
        assert reliability.reliability_score < 0.4
        assert reliability.reliability_level == ReliabilityLevel.LOW
        assert reliability.recommendation in [BettingRecommendation.PASS, BettingRecommendation.AVOID]
    
    def test_probability_factor_calculation(self):
        """Test that probability factor correctly measures conviction."""
        calculator = MarketReliabilityCalculator()
        
        uncertainty = UncertaintyAssessment(
            overall_uncertainty=0.3,
            uncertainty_level=UncertaintyLevel.MEDIUM,
            components=UncertaintyComponents(
                model_disagreement=0.3,
                data_quality_deficit=0.2,
                feature_availability_deficit=0.2,
                sample_size_inadequacy=0.3,
                calibration_uncertainty=0.2,
                probability_dispersion=0.0
            ),
            interpretation="Medium uncertainty",
            implied_confidence=0.7
        )
        
        # High conviction (0.8)
        high_conv = calculator.calculate(
            market_key="HOME_WIN",
            probability=0.80,
            calibration_status=CalibrationStatus.FITTED,
            uncertainty_assessment=uncertainty,
            data_quality_score=0.8
        )
        
        # Low conviction (0.55, close to 0.5)
        low_conv = calculator.calculate(
            market_key="HOME_WIN",
            probability=0.55,
            calibration_status=CalibrationStatus.FITTED,
            uncertainty_assessment=uncertainty,
            data_quality_score=0.8
        )
        
        # High conviction should have higher probability factor
        assert high_conv.probability_factor > low_conv.probability_factor
    
    def test_calibration_factor_values(self):
        """Test that calibration status correctly affects calibration factor."""
        calculator = MarketReliabilityCalculator()
        
        uncertainty = UncertaintyAssessment(
            overall_uncertainty=0.3,
            uncertainty_level=UncertaintyLevel.MEDIUM,
            components=UncertaintyComponents(
                model_disagreement=0.3,
                data_quality_deficit=0.2,
                feature_availability_deficit=0.2,
                sample_size_inadequacy=0.3,
                calibration_uncertainty=0.0,
                probability_dispersion=0.0
            ),
            interpretation="Medium uncertainty",
            implied_confidence=0.7
        )
        
        # Test FITTED
        fitted = calculator.calculate(
            market_key="HOME_WIN",
            probability=0.65,
            calibration_status=CalibrationStatus.FITTED,
            uncertainty_assessment=uncertainty,
            data_quality_score=0.8
        )
        
        # Test NOT_FITTED
        not_fitted = calculator.calculate(
            market_key="HOME_WIN",
            probability=0.65,
            calibration_status=CalibrationStatus.NOT_FITTED,
            uncertainty_assessment=uncertainty,
            data_quality_score=0.8
        )
        
        # FITTED should have higher calibration factor and overall reliability
        assert fitted.calibration_factor > not_fitted.calibration_factor
        assert fitted.reliability_score > not_fitted.reliability_score
    
    def test_recommendation_logic(self):
        """Test betting recommendation logic."""
        calculator = MarketReliabilityCalculator()
        
        uncertainty = UncertaintyAssessment(
            overall_uncertainty=0.2,
            uncertainty_level=UncertaintyLevel.LOW,
            components=UncertaintyComponents(
                model_disagreement=0.15,
                data_quality_deficit=0.10,
                feature_availability_deficit=0.15,
                sample_size_inadequacy=0.20,
                calibration_uncertainty=0.0,
                probability_dispersion=0.0
            ),
            interpretation="Low uncertainty",
            implied_confidence=0.8
        )
        
        # STRONG_BET: high reliability (>0.7) + high probability (>0.65)
        strong_bet = calculator.calculate(
            market_key="HOME_WIN",
            probability=0.75,
            calibration_status=CalibrationStatus.FITTED,
            uncertainty_assessment=uncertainty,
            data_quality_score=0.90
        )
        assert strong_bet.recommendation == BettingRecommendation.STRONG_BET
        
        # Lower probability but still high reliability -> CONSIDER
        consider = calculator.calculate(
            market_key="HOME_WIN",
            probability=0.60,
            calibration_status=CalibrationStatus.FITTED,
            uncertainty_assessment=uncertainty,
            data_quality_score=0.90
        )
        # Could be STRONG_BET or CONSIDER depending on exact calculation
        assert consider.recommendation in [BettingRecommendation.STRONG_BET, BettingRecommendation.CONSIDER]
    
    def test_interpretation_generated(self):
        """Test that interpretation is generated."""
        calculator = MarketReliabilityCalculator()
        
        uncertainty = UncertaintyAssessment(
            overall_uncertainty=0.3,
            uncertainty_level=UncertaintyLevel.MEDIUM,
            components=UncertaintyComponents(
                model_disagreement=0.3,
                data_quality_deficit=0.2,
                feature_availability_deficit=0.2,
                sample_size_inadequacy=0.3,
                calibration_uncertainty=0.2,
                probability_dispersion=0.0
            ),
            interpretation="Medium uncertainty",
            implied_confidence=0.7
        )
        
        reliability = calculator.calculate(
            market_key="HOME_WIN",
            probability=0.65,
            calibration_status=CalibrationStatus.INSUFFICIENT_DATA,
            uncertainty_assessment=uncertainty,
            data_quality_score=0.7
        )
        
        assert isinstance(reliability.interpretation, str)
        assert len(reliability.interpretation) > 0
