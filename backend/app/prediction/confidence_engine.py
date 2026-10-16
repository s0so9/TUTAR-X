"""Confidence assessment engine.

This module implements multi-component confidence assessment for predictions.

Components:
- model_agreement: Agreement between ensemble models [0, 1]
- data_quality: Data quality score from DataQualityGate [0, 1]
- sample_size_score: Normalized sample size adequacy [0, 1]
- calibration_reliability: Calibration performance (1 - brier_score) [0, 1]
- lineup_certainty: Lineup confirmation status [0, 0.5, 1]
- feature_stability: Stability of recent predictions [0, 1]

Overall confidence is a weighted average of these components.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ConfidenceComponents:
    """Individual confidence components."""
    
    model_agreement: float = 0.0
    """Agreement between ensemble models [0, 1]"""
    
    data_quality: float = 0.0
    """Data quality score [0, 1]"""
    
    sample_size_score: float = 0.0
    """Sample size adequacy [0, 1]"""
    
    calibration_reliability: float = 0.0
    """Calibration reliability (1 - brier_score) [0, 1]"""
    
    lineup_certainty: float = 0.5
    """Lineup confirmation: 1.0 confirmed, 0.5 expected, 0.0 unknown"""
    
    feature_stability: float = 1.0
    """Stability of recent predictions [0, 1]"""
    
    def validate(self) -> None:
        """Validate all components are in [0, 1]."""
        components = {
            "model_agreement": self.model_agreement,
            "data_quality": self.data_quality,
            "sample_size_score": self.sample_size_score,
            "calibration_reliability": self.calibration_reliability,
            "lineup_certainty": self.lineup_certainty,
            "feature_stability": self.feature_stability,
        }
        
        for name, value in components.items():
            if not (0.0 <= value <= 1.0):
                raise ValueError(f"{name} must be in [0, 1], got {value}")


@dataclass
class ConfidenceWeights:
    """Weights for confidence components.
    
    Default weights sum to 1.0 for interpretability.
    """
    
    model_agreement: float = 0.25
    data_quality: float = 0.25
    sample_size_score: float = 0.15
    calibration_reliability: float = 0.15
    lineup_certainty: float = 0.10
    feature_stability: float = 0.10
    
    def validate(self) -> None:
        """Validate weights are non-negative and sum to approximately 1.0."""
        weights = [
            self.model_agreement,
            self.data_quality,
            self.sample_size_score,
            self.calibration_reliability,
            self.lineup_certainty,
            self.feature_stability,
        ]
        
        for w in weights:
            if w < 0:
                raise ValueError(f"Weights must be non-negative, got {w}")
        
        total = sum(weights)
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"Weights should sum to ~1.0, got {total}")
    
    def normalize(self) -> None:
        """Normalize weights to sum to exactly 1.0."""
        total = (
            self.model_agreement +
            self.data_quality +
            self.sample_size_score +
            self.calibration_reliability +
            self.lineup_certainty +
            self.feature_stability
        )
        
        if total > 0:
            self.model_agreement /= total
            self.data_quality /= total
            self.sample_size_score /= total
            self.calibration_reliability /= total
            self.lineup_certainty /= total
            self.feature_stability /= total


@dataclass
class ConfidenceAssessment:
    """Complete confidence assessment."""
    
    overall_confidence: float
    """Overall confidence score [0, 1]"""
    
    confidence_label: str
    """Confidence tier: HIGH (>0.7), MEDIUM (0.4-0.7), LOW (<0.4)"""
    
    components: ConfidenceComponents
    """Individual component scores"""
    
    weights: ConfidenceWeights
    """Weights used in calculation"""
    
    component_breakdown: Dict[str, float] = field(default_factory=dict)
    """Weighted contribution of each component"""


class ConfidenceEngine:
    """Engine for assessing prediction confidence.
    
    Combines multiple confidence factors into a single overall score
    with component breakdown for interpretability.
    """
    
    def __init__(self, weights: Optional[ConfidenceWeights] = None):
        """Initialize confidence engine.
        
        Args:
            weights: Custom component weights (uses defaults if None)
        """
        self.weights = weights or ConfidenceWeights()
        self.weights.normalize()
    
    def assess(
        self,
        model_agreement: float,
        data_quality_score: Optional[float],  # Can be None = unknown/insufficient
        n_matches: int,
        brier_score: Optional[float] = None,
        lineup_status: str = "expected",
        recent_predictions: Optional[List[float]] = None
    ) -> ConfidenceAssessment:
        """Assess confidence for a prediction.
        
        Args:
            model_agreement: Model agreement score [0, 1] from ensemble
            data_quality_score: Data quality score [0, 1] from DataQualityGate (None = unknown)
            n_matches: Number of historical matches available
            brier_score: Calibration Brier score (optional)
            lineup_status: Lineup confirmation ("confirmed", "expected", "unknown")
            recent_predictions: List of recent prediction probabilities for stability
            
        Returns:
            ConfidenceAssessment with overall score and breakdown
        """
        # FIXED: Handle None data_quality_score as "insufficient_data"
        # None = data quality unknown → use minimal score (0.0) and flag as insufficient
        if data_quality_score is None:
            data_quality_score = 0.0
            data_quality_insufficient = True
        else:
            data_quality_insufficient = False
        
        # Build components
        components = ConfidenceComponents(
            model_agreement=model_agreement,
            data_quality=data_quality_score,
            sample_size_score=self._calculate_sample_size_score(n_matches),
            calibration_reliability=self._calculate_calibration_reliability(brier_score),
            lineup_certainty=self._get_lineup_certainty(lineup_status),
            feature_stability=self._calculate_feature_stability(recent_predictions)
        )
        
        components.validate()
        
        # Calculate weighted average
        overall = (
            components.model_agreement * self.weights.model_agreement +
            components.data_quality * self.weights.data_quality +
            components.sample_size_score * self.weights.sample_size_score +
            components.calibration_reliability * self.weights.calibration_reliability +
            components.lineup_certainty * self.weights.lineup_certainty +
            components.feature_stability * self.weights.feature_stability
        )
        
        # Determine label
        # If data quality is insufficient/unknown, cap at LOW
        if data_quality_insufficient:
            label = "LOW_INSUFFICIENT_DATA"
            overall = min(overall, 0.39)  # Cap at LOW tier
        elif overall > 0.7:
            label = "HIGH"
        elif overall >= 0.4:
            label = "MEDIUM"
        else:
            label = "LOW"
        
        # Calculate component breakdown (weighted contributions)
        breakdown = {
            "model_agreement": components.model_agreement * self.weights.model_agreement,
            "data_quality": components.data_quality * self.weights.data_quality,
            "sample_size_score": components.sample_size_score * self.weights.sample_size_score,
            "calibration_reliability": components.calibration_reliability * self.weights.calibration_reliability,
            "lineup_certainty": components.lineup_certainty * self.weights.lineup_certainty,
            "feature_stability": components.feature_stability * self.weights.feature_stability,
        }
        
        # Add flag if data quality was insufficient
        if data_quality_insufficient:
            breakdown["data_quality_status"] = "insufficient"
        
        return ConfidenceAssessment(
            overall_confidence=overall,
            confidence_label=label,
            components=components,
            weights=self.weights,
            component_breakdown=breakdown
        )
    
    def _calculate_sample_size_score(self, n_matches: int) -> float:
        """Calculate sample size adequacy score.
        
        Uses sigmoid function: score = 1 / (1 + exp(-k * (n - n0)))
        where n0 = 30 (inflection point), k = 0.1 (steepness)
        
        Args:
            n_matches: Number of historical matches
            
        Returns:
            Score in [0, 1]
        """
        n0 = 30  # Inflection point (50% score)
        k = 0.1  # Steepness
        
        # Sigmoid: S(x) = 1 / (1 + exp(-k * (x - n0)))
        score = 1.0 / (1.0 + math.exp(-k * (n_matches - n0)))
        
        return score
    
    def _calculate_calibration_reliability(
        self,
        brier_score: Optional[float]
    ) -> float:
        """Calculate calibration reliability from Brier score.
        
        reliability = 1 - brier_score
        
        Brier score of 0 = perfect calibration → reliability = 1.0
        Brier score of 0.25 = random → reliability = 0.75
        
        Args:
            brier_score: Brier score [0, 1] (None if not available)
            
        Returns:
            Reliability in [0, 1]
        """
        if brier_score is None:
            # No calibration data available - use neutral value
            return 0.7
        
        # Clip brier_score to [0, 1]
        brier_score = max(0.0, min(1.0, brier_score))
        
        return 1.0 - brier_score
    
    def _get_lineup_certainty(self, lineup_status: str) -> float:
        """Get lineup certainty score.
        
        Args:
            lineup_status: "confirmed", "expected", or "unknown"
            
        Returns:
            Certainty: 1.0 (confirmed), 0.5 (expected), 0.0 (unknown)
        """
        status_map = {
            "confirmed": 1.0,
            "expected": 0.5,
            "unknown": 0.0
        }
        
        return status_map.get(lineup_status.lower(), 0.5)
    
    def _calculate_feature_stability(
        self,
        recent_predictions: Optional[List[float]]
    ) -> float:
        """Calculate feature stability from recent prediction variance.
        
        stability = 1 - variance(recent_predictions)
        
        Low variance → high stability → high confidence
        High variance → low stability → low confidence
        
        Args:
            recent_predictions: List of recent home_win_prob predictions
                               for the same match (e.g., last 5 updates)
            
        Returns:
            Stability in [0, 1]. Returns 0.5 (neutral) when insufficient data.
        """
        if not recent_predictions or len(recent_predictions) < 2:
            # Insufficient data - return neutral score (not confident absence or presence of stability)
            return 0.5
        
        # Calculate variance
        mean = sum(recent_predictions) / len(recent_predictions)
        variance = sum((p - mean) ** 2 for p in recent_predictions) / len(recent_predictions)
        
        # Maximum realistic variance for probabilities ≈ 0.25 (when values span 0-1)
        # Normalize to [0, 1] and invert (high variance → low stability)
        stability = max(0.0, 1.0 - (variance * 4.0))
        
        return min(1.0, stability)
