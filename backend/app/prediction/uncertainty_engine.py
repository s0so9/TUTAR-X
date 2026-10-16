"""Uncertainty assessment engine.

This module combines multiple measurable uncertainty sources into a unified
uncertainty assessment.

Uncertainty vs. Probability:
---------------------------
These are distinct concepts:
- Probability: "Home win has 65% chance" (the prediction itself)
- Uncertainty: "We are 40% uncertain about this prediction" (confidence in the prediction)

High uncertainty means we should be less confident in the probability estimate,
regardless of what that estimate is.

Uncertainty Sources:
-------------------
1. Model disagreement: Do models agree on the probability?
2. Data quality: Is the input data reliable and complete?
3. Feature availability: Are key features available?
4. Sample size: Do we have enough historical data?
5. Calibration status: Is the calibration well-fitted?
6. Probability dispersion: Is the score distribution concentrated or spread?

Each component contributes to overall uncertainty through weighted combination.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any
import math

from app.prediction.model_disagreement import ModelDisagreementResult


class UncertaintyLevel(str, Enum):
    """Uncertainty level categories."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


@dataclass
class UncertaintyComponents:
    """Individual uncertainty contributors.
    
    Each component is in [0, 1] where 0 = no uncertainty, 1 = maximum uncertainty.
    """
    
    model_disagreement: float
    """Model disagreement contribution (0 = high agreement, 1 = high disagreement)"""
    
    data_quality_deficit: float
    """Data quality deficit (1 - data_quality_score)"""
    
    feature_availability_deficit: float
    """Proportion of eligible features that are unavailable"""
    
    sample_size_inadequacy: float
    """Sample size inadequacy (higher = fewer samples)"""
    
    calibration_uncertainty: float
    """Uncertainty from calibration status"""
    
    probability_dispersion: float
    """Probability dispersion (optional, from score distribution entropy)"""


@dataclass
class UncertaintyAssessment:
    """Overall uncertainty assessment.
    
    Combines multiple uncertainty sources into unified assessment.
    """
    
    overall_uncertainty: float
    """Overall uncertainty score [0, 1] where 0 = low, 1 = high"""
    
    uncertainty_level: UncertaintyLevel
    """Categorical uncertainty level"""
    
    components: UncertaintyComponents
    """Individual component contributions"""
    
    interpretation: str
    """Human-readable explanation of uncertainty"""
    
    # Inverse: confidence from uncertainty
    implied_confidence: float
    """Implied confidence = 1 - overall_uncertainty"""


class UncertaintyEngine:
    """Assess prediction uncertainty from multiple measurable sources.
    
    Component Weights — Provisional Pending Group 6 Validation:
    ------------------------------------------------------------
    - Model disagreement: 0.30
      Rationale: Inter-model variance is the most direct signal of prediction uncertainty.
      When models trained on the same data produce different predictions, this reveals
      fundamental uncertainty about the outcome. 30% weight emphasizes disagreement as
      the primary uncertainty indicator, consistent with ensemble uncertainty literature
      that treats model variance as the dominant epistemic uncertainty source.
      
    - Data quality: 0.25
      Rationale: Poor data quality propagates through all calculations. Missing matches,
      incomplete lineups, or stale data bound the ceiling for prediction reliability.
      25% weight reflects that input reliability constrains output reliability.
      
    - Feature availability: 0.20
      Rationale: Missing features mean missing information. Advanced features (tactical
      intelligence, opponent adjustment) add context beyond raw statistics. 20% weight
      scales proportionally with unavailable feature ratio.
      
    - Sample size: 0.15
      Rationale: Statistical reliability improves with sample size but plateaus beyond
      30-50 matches (diminishing returns). 15% weight captures that more data helps but
      isn't the dominant uncertainty driver once minimum thresholds are met.
      
    - Calibration: 0.10
      Rationale: Calibration maps raw model outputs to true frequencies but doesn't
      change underlying prediction uncertainty—it corrects systematic bias rather than
      reducing variance. 10% weight acknowledges calibration status matters for
      probability reliability without dominating overall uncertainty assessment.
    
    These weights will be validated during Group 6 walk-forward backtesting by measuring
    correlation between uncertainty scores and actual out-of-sample prediction errors.
    """
    
    # Component weights
    WEIGHT_MODEL_DISAGREEMENT = 0.30
    WEIGHT_DATA_QUALITY = 0.25
    WEIGHT_FEATURE_AVAILABILITY = 0.20
    WEIGHT_SAMPLE_SIZE = 0.15
    WEIGHT_CALIBRATION = 0.10
    
    # Uncertainty level thresholds
    LOW_THRESHOLD = 0.3
    MEDIUM_THRESHOLD = 0.6
    HIGH_THRESHOLD = 0.8
    
    # Sample size adequacy parameters
    SAMPLE_SIZE_TARGET = 30  # Target sample size for low uncertainty
    SAMPLE_SIZE_DECAY = 0.1  # Decay rate for sample size sigmoid
    
    def __init__(self):
        """Initialize uncertainty engine."""
        pass
    
    def assess(
        self,
        model_disagreement: ModelDisagreementResult,
        data_quality_score: float,
        feature_availability: Dict[str, Any],
        sample_size: int,
        calibration_status: str,  # "FITTED", "INSUFFICIENT_DATA", "NOT_FITTED"
        probability_dispersion: Optional[float] = None
    ) -> UncertaintyAssessment:
        """Assess overall uncertainty from components.
        
        Args:
            model_disagreement: Model disagreement analysis result
            data_quality_score: Data quality [0, 1] where 1 = perfect
            feature_availability: Dict with 'availability_ratio' key
            sample_size: Number of historical samples
            calibration_status: Calibration status string
            probability_dispersion: Optional probability dispersion measure
            
        Returns:
            UncertaintyAssessment with overall score and components
        """
        # Calculate individual components
        
        # 1. Model disagreement (already 0-1 disagreement score)
        disagreement_component = model_disagreement.disagreement_score
        
        # 2. Data quality deficit
        data_quality_deficit = 1.0 - max(0.0, min(1.0, data_quality_score))
        
        # 3. Feature availability deficit
        if isinstance(feature_availability, dict):
            availability_ratio = feature_availability.get('availability_ratio', 0.0)
        else:
            availability_ratio = 0.0
        feature_deficit = 1.0 - availability_ratio
        
        # 4. Sample size inadequacy using sigmoid
        # Sigmoid: 1 / (1 + exp(decay * (n - target)))
        # At n=target: inadequacy = 0.5
        # At n=0: inadequacy → 1.0
        # At n→∞: inadequacy → 0.0
        sample_inadequacy = 1.0 / (1.0 + math.exp(
            self.SAMPLE_SIZE_DECAY * (sample_size - self.SAMPLE_SIZE_TARGET)
        ))
        
        # 5. Calibration uncertainty
        if calibration_status == "FITTED":
            calibration_uncertainty = 0.0
        elif calibration_status == "INSUFFICIENT_DATA":
            calibration_uncertainty = 0.3
        elif calibration_status == "NOT_FITTED":
            calibration_uncertainty = 0.5
        else:
            calibration_uncertainty = 0.5  # Unknown status = high uncertainty
        
        # 6. Probability dispersion (optional, default to 0 if not provided)
        dispersion_component = probability_dispersion if probability_dispersion is not None else 0.0
        
        # Create components dataclass
        components = UncertaintyComponents(
            model_disagreement=disagreement_component,
            data_quality_deficit=data_quality_deficit,
            feature_availability_deficit=feature_deficit,
            sample_size_inadequacy=sample_inadequacy,
            calibration_uncertainty=calibration_uncertainty,
            probability_dispersion=dispersion_component
        )
        
        # Calculate weighted overall uncertainty
        overall = (
            self.WEIGHT_MODEL_DISAGREEMENT * disagreement_component +
            self.WEIGHT_DATA_QUALITY * data_quality_deficit +
            self.WEIGHT_FEATURE_AVAILABILITY * feature_deficit +
            self.WEIGHT_SAMPLE_SIZE * sample_inadequacy +
            self.WEIGHT_CALIBRATION * calibration_uncertainty
        )
        
        # Clamp to [0, 1]
        overall = max(0.0, min(1.0, overall))
        
        # Determine level
        if overall < self.LOW_THRESHOLD:
            level = UncertaintyLevel.LOW
        elif overall < self.MEDIUM_THRESHOLD:
            level = UncertaintyLevel.MEDIUM
        elif overall < self.HIGH_THRESHOLD:
            level = UncertaintyLevel.HIGH
        else:
            level = UncertaintyLevel.VERY_HIGH
        
        # Generate interpretation
        interpretation = self._generate_interpretation(level, components)
        
        return UncertaintyAssessment(
            overall_uncertainty=overall,
            uncertainty_level=level,
            components=components,
            interpretation=interpretation,
            implied_confidence=1.0 - overall
        )
    
    def _generate_interpretation(
        self,
        level: UncertaintyLevel,
        components: UncertaintyComponents
    ) -> str:
        """Generate human-readable interpretation of uncertainty.
        
        Args:
            level: Uncertainty level
            components: Uncertainty components
            
        Returns:
            Interpretation string
        """
        if level == UncertaintyLevel.LOW:
            return "Low uncertainty: Models agree, good data quality, sufficient sample size."
        
        elif level == UncertaintyLevel.MEDIUM:
            # Identify top contributors
            contributors = []
            if components.model_disagreement > 0.4:
                contributors.append("model disagreement")
            if components.data_quality_deficit > 0.4:
                contributors.append("data quality issues")
            if components.feature_availability_deficit > 0.4:
                contributors.append("missing features")
            if components.sample_size_inadequacy > 0.4:
                contributors.append("limited sample size")
            
            if contributors:
                return f"Medium uncertainty due to: {', '.join(contributors)}."
            else:
                return "Medium uncertainty: Some concerns about prediction reliability."
        
        elif level == UncertaintyLevel.HIGH:
            # Identify major contributors
            contributors = []
            if components.model_disagreement > 0.6:
                contributors.append("high model disagreement")
            if components.data_quality_deficit > 0.6:
                contributors.append("poor data quality")
            if components.feature_availability_deficit > 0.6:
                contributors.append("many missing features")
            if components.sample_size_inadequacy > 0.6:
                contributors.append("insufficient sample size")
            
            if contributors:
                return f"High uncertainty due to: {', '.join(contributors)}."
            else:
                return "High uncertainty: Prediction reliability is questionable."
        
        else:  # VERY_HIGH
            return "Very high uncertainty: Avoid betting on this prediction. Multiple reliability concerns."
