"""Market reliability assessment.

This module combines multiple measurable factors into a unified market reliability score:
- Probability conviction (how confident is the prediction)
- Calibration status (is the probability well-calibrated)
- Uncertainty level (model agreement, data quality, etc.)
- Data quality (input data reliability)

Reliability Formula — Provisional Pending Group 6 Validation:
-------------------------------------------------------------
reliability = (0.25 * probability_factor +
               0.25 * calibration_factor +
               0.30 * uncertainty_factor +
               0.20 * data_quality_factor)

Rationale for Weights:
- probability_factor (25%): Conviction strength matters—a 90% prediction is more
  actionable than a 52% prediction. However, conviction alone doesn't guarantee
  reliability (could be confidently wrong), hence 25% not higher.

- calibration_factor (25%): Calibration quality is critical—uncalibrated probabilities
  may be systematically biased. Equal weight to conviction (25%) reflects that
  calibration affects the meaning of the probability value itself.

- uncertainty_factor (30%): Highest weight because uncertainty captures multiple
  independent reliability signals (model disagreement, data quality deficit, feature
  availability, sample size). This is a composite measure that aggregates several
  orthogonal concerns, justifying the 30% emphasis.

- data_quality_factor (20%): Explicit data quality check ensures input reliability
  is visible separately from uncertainty (even though data quality also contributes
  to uncertainty at 25% weight within uncertainty calculation). This double-weighting
  is intentional: data quality bounds all downstream reliability, so 20% direct +
  ~7.5% via uncertainty (0.25 * 0.30) = ~27.5% total influence is appropriate.

NOTE: These weights treat reliability dimensions as substitutable (multiplicative
combination). An alternative design would use independent gates (calibration MUST
be FITTED, data quality MUST exceed threshold) then score on conviction and
uncertainty. Current formula allows high conviction to partially offset moderate
uncertainty, which may or may not match actual betting value. Group 6 backtesting
will validate whether this formula correlates with profitable betting opportunities.

Where:
- probability_factor: Conviction strength (0 = low conviction near 0.5, 1 = high conviction)
- calibration_factor: 1.0 if FITTED, 0.7 if INSUFFICIENT, 0.5 if NOT_FITTED
- uncertainty_factor: 1 - uncertainty_score
- data_quality_factor: data_quality_score

Recommendation Logic:
--------------------
- STRONG_BET: reliability > 0.7 and probability > 0.65
- CONSIDER: reliability > 0.5 and probability > 0.55
- PASS: reliability 0.3-0.5
- AVOID: reliability < 0.3
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.prediction.calibration_engine import CalibrationStatus
from app.prediction.uncertainty_engine import UncertaintyAssessment, UncertaintyLevel


class ReliabilityLevel(str, Enum):
    """Market reliability level."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class BettingRecommendation(str, Enum):
    """Betting recommendation based on reliability."""
    STRONG_BET = "strong_bet"
    CONSIDER = "consider"
    PASS = "pass"
    AVOID = "avoid"


@dataclass
class MarketReliability:
    """Reliability assessment for a market prediction.
    
    Combines probability, calibration, uncertainty, and data quality
    into a unified reliability score.
    """
    
    market_key: str
    """Market identifier (e.g., "HOME_WIN", "OVER_2_5")"""
    
    probability: float
    """Raw or calibrated probability [0, 1]"""
    
    calibration_status: CalibrationStatus
    """Calibration status"""
    
    uncertainty: float
    """Uncertainty score [0, 1] from UncertaintyAssessment"""
    
    data_quality: float
    """Data quality score [0, 1]"""
    
    # Composite reliability score
    reliability_score: float
    """Overall reliability [0, 1] where 1 = highly reliable"""
    
    reliability_level: ReliabilityLevel
    """Categorical reliability level"""
    
    # Components breakdown
    probability_factor: float
    """Probability conviction factor [0, 1]"""
    
    calibration_factor: float
    """Calibration quality factor [0, 1]"""
    
    uncertainty_factor: float
    """Uncertainty factor [0, 1] = 1 - uncertainty"""
    
    data_quality_factor: float
    """Data quality factor [0, 1]"""
    
    # Interpretation
    recommendation: BettingRecommendation
    """Betting recommendation"""
    
    interpretation: str
    """Human-readable explanation"""


class MarketReliabilityCalculator:
    """Calculate market reliability from measurable components.
    
    Weights (sum to 1.0):
    - Probability conviction: 0.25
    - Calibration status: 0.25
    - Uncertainty: 0.30
    - Data quality: 0.20
    """
    
    # Component weights
    WEIGHT_PROBABILITY = 0.25
    WEIGHT_CALIBRATION = 0.25
    WEIGHT_UNCERTAINTY = 0.30
    WEIGHT_DATA_QUALITY = 0.20
    
    # Reliability thresholds
    HIGH_RELIABILITY_THRESHOLD = 0.7
    LOW_RELIABILITY_THRESHOLD = 0.4
    
    # Recommendation thresholds
    STRONG_BET_RELIABILITY = 0.7
    STRONG_BET_PROBABILITY = 0.65
    CONSIDER_RELIABILITY = 0.5
    CONSIDER_PROBABILITY = 0.55
    AVOID_RELIABILITY = 0.3
    
    def __init__(self):
        """Initialize calculator."""
        pass
    
    def calculate(
        self,
        market_key: str,
        probability: float,
        calibration_status: CalibrationStatus,
        uncertainty_assessment: UncertaintyAssessment,
        data_quality_score: float
    ) -> MarketReliability:
        """Calculate market reliability.
        
        Args:
            market_key: Market identifier
            probability: Predicted probability [0, 1]
            calibration_status: Calibration status
            uncertainty_assessment: Uncertainty assessment
            data_quality_score: Data quality [0, 1]
            
        Returns:
            MarketReliability with all components
        """
        # Calculate component factors
        
        # 1. Probability conviction factor
        # Penalize low conviction (probabilities near 0.5)
        # Factor = (|prob - 0.5| / 0.5) for prob != 0.5
        # This gives 0.0 at prob=0.5, 1.0 at prob=0.0 or 1.0
        prob_factor = abs(probability - 0.5) / 0.5
        
        # 2. Calibration factor
        if calibration_status == CalibrationStatus.FITTED:
            calib_factor = 1.0
        elif calibration_status == CalibrationStatus.INSUFFICIENT_DATA:
            calib_factor = 0.7
        else:  # NOT_FITTED
            calib_factor = 0.5
        
        # 3. Uncertainty factor (inverse of uncertainty)
        uncertainty_factor = 1.0 - uncertainty_assessment.overall_uncertainty
        
        # 4. Data quality factor (direct)
        data_quality_factor = data_quality_score
        
        # Calculate weighted reliability score
        reliability = (
            self.WEIGHT_PROBABILITY * prob_factor +
            self.WEIGHT_CALIBRATION * calib_factor +
            self.WEIGHT_UNCERTAINTY * uncertainty_factor +
            self.WEIGHT_DATA_QUALITY * data_quality_factor
        )
        
        # Clamp to [0, 1]
        reliability = max(0.0, min(1.0, reliability))
        
        # Determine reliability level
        if reliability >= self.HIGH_RELIABILITY_THRESHOLD:
            level = ReliabilityLevel.HIGH
        elif reliability >= self.LOW_RELIABILITY_THRESHOLD:
            level = ReliabilityLevel.MEDIUM
        else:
            level = ReliabilityLevel.LOW
        
        # Determine recommendation
        if reliability >= self.STRONG_BET_RELIABILITY and probability >= self.STRONG_BET_PROBABILITY:
            recommendation = BettingRecommendation.STRONG_BET
        elif reliability >= self.CONSIDER_RELIABILITY and probability >= self.CONSIDER_PROBABILITY:
            recommendation = BettingRecommendation.CONSIDER
        elif reliability >= self.AVOID_RELIABILITY:
            recommendation = BettingRecommendation.PASS
        else:
            recommendation = BettingRecommendation.AVOID
        
        # Generate interpretation
        interpretation = self._generate_interpretation(
            level, recommendation, prob_factor, calib_factor,
            uncertainty_factor, data_quality_factor
        )
        
        return MarketReliability(
            market_key=market_key,
            probability=probability,
            calibration_status=calibration_status,
            uncertainty=uncertainty_assessment.overall_uncertainty,
            data_quality=data_quality_score,
            reliability_score=reliability,
            reliability_level=level,
            probability_factor=prob_factor,
            calibration_factor=calib_factor,
            uncertainty_factor=uncertainty_factor,
            data_quality_factor=data_quality_factor,
            recommendation=recommendation,
            interpretation=interpretation
        )
    
    def _generate_interpretation(
        self,
        level: ReliabilityLevel,
        recommendation: BettingRecommendation,
        prob_factor: float,
        calib_factor: float,
        uncertainty_factor: float,
        data_quality_factor: float
    ) -> str:
        """Generate human-readable interpretation.
        
        Args:
            level: Reliability level
            recommendation: Betting recommendation
            prob_factor: Probability conviction factor
            calib_factor: Calibration factor
            uncertainty_factor: Uncertainty factor
            data_quality_factor: Data quality factor
            
        Returns:
            Interpretation string
        """
        if level == ReliabilityLevel.HIGH:
            if recommendation == BettingRecommendation.STRONG_BET:
                return "High reliability with strong conviction. Good betting opportunity."
            else:
                return "High reliability but low probability conviction. Consider other markets."
        
        elif level == ReliabilityLevel.MEDIUM:
            # Identify weak components
            weak_components = []
            if prob_factor < 0.4:
                weak_components.append("low conviction")
            if calib_factor < 0.8:
                weak_components.append("calibration concerns")
            if uncertainty_factor < 0.6:
                weak_components.append("high uncertainty")
            if data_quality_factor < 0.6:
                weak_components.append("data quality issues")
            
            if weak_components:
                return f"Medium reliability. Concerns: {', '.join(weak_components)}."
            else:
                return "Medium reliability. Proceed with caution."
        
        else:  # LOW
            # Identify major issues
            major_issues = []
            if prob_factor < 0.3:
                major_issues.append("very low conviction")
            if calib_factor < 0.6:
                major_issues.append("poor calibration")
            if uncertainty_factor < 0.4:
                major_issues.append("very high uncertainty")
            if data_quality_factor < 0.4:
                major_issues.append("poor data quality")
            
            if major_issues:
                return f"Low reliability. Issues: {', '.join(major_issues)}. Avoid betting."
            else:
                return "Low reliability. Not recommended for betting."
