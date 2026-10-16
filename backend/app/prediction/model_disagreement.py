"""Model disagreement analysis.

This module analyzes disagreement between multiple prediction models by measuring
probability dispersion across model outputs.

Model Agreement Philosophy:
--------------------------
When multiple models produce similar probabilities, we have higher confidence.
When models disagree significantly, this signals uncertainty that should be
reflected in our overall confidence assessment.

Agreement Score Calculation:
- Uses standard deviation of probabilities across models
- Normalizes to [0, 1] where 1 = perfect agreement, 0 = maximum disagreement
- Formula: agreement = 1 - (std * 3), clamped to [0, 1]
- This matches the existing EnsembleEngine._calculate_agreement() methodology

Disagreement is simply the inverse: disagreement = 1 - agreement
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import math

from app.prediction.interfaces import ModelPrediction


@dataclass
class ModelDisagreementResult:
    """Model disagreement metrics for a specific outcome.
    
    Measures probability dispersion across multiple models.
    """
    
    model_count: int
    """Total number of models considered"""
    
    available_model_count: int
    """Number of models that provided predictions"""
    
    mean_probability: float
    """Mean probability across available models"""
    
    probability_std: float
    """Standard deviation of probabilities"""
    
    probability_range: float
    """Range (max - min) of probabilities"""
    
    agreement_score: float
    """Agreement score: 1 = perfect agreement, 0 = high disagreement"""
    
    disagreement_score: float
    """Disagreement score: 1 = high disagreement, 0 = perfect agreement"""
    
    # Individual model probabilities for transparency
    model_probabilities: Dict[str, float] = field(default_factory=dict)
    
    # Interpretation
    agreement_label: str = ""  # "HIGH", "MEDIUM", "LOW"


class ModelDisagreementAnalyzer:
    """Analyze model disagreement from orchestration results.
    
    Extracts probability dispersion metrics to quantify model agreement/disagreement.
    """
    
    # Agreement thresholds (consistent with existing confidence engine)
    HIGH_AGREEMENT_THRESHOLD = 0.8
    LOW_AGREEMENT_THRESHOLD = 0.5
    
    def __init__(self):
        """Initialize analyzer."""
        pass
    
    def analyze(
        self,
        model_predictions: List[ModelPrediction],
        outcome: str = "home_win"
    ) -> ModelDisagreementResult:
        """Calculate disagreement metrics for a specific outcome.
        
        Args:
            model_predictions: List of successful model predictions
            outcome: Which outcome to analyze ("home_win", "draw", "away_win")
            
        Returns:
            ModelDisagreementResult with disagreement metrics
        """
        # Extract probabilities for the specified outcome
        probabilities: List[float] = []
        model_probs: Dict[str, float] = {}
        
        for pred in model_predictions:
            if outcome == "home_win":
                prob = pred.home_win_prob
            elif outcome == "draw":
                prob = pred.draw_prob
            elif outcome == "away_win":
                prob = pred.away_win_prob
            else:
                raise ValueError(f"Unknown outcome: {outcome}")
            
            probabilities.append(prob)
            model_probs[pred.model_id] = prob
        
        # Check sufficient models
        if len(probabilities) < 2:
            return ModelDisagreementResult(
                model_count=len(model_predictions),
                available_model_count=len(probabilities),
                mean_probability=probabilities[0] if probabilities else 0.0,
                probability_std=0.0,
                probability_range=0.0,
                agreement_score=1.0,  # No disagreement with single model
                disagreement_score=0.0,
                model_probabilities=model_probs,
                agreement_label="INSUFFICIENT"
            )
        
        # Calculate statistics
        mean_prob = sum(probabilities) / len(probabilities)
        variance = sum((p - mean_prob) ** 2 for p in probabilities) / len(probabilities)
        std = math.sqrt(variance)
        prob_range = max(probabilities) - min(probabilities)
        
        # Calculate agreement score (formula from EnsembleEngine)
        # agreement = 1 - (std * 3), clamped to [0, 1]
        agreement = max(0.0, min(1.0, 1.0 - (std * 3)))
        disagreement = 1.0 - agreement
        
        # Determine label
        if agreement >= self.HIGH_AGREEMENT_THRESHOLD:
            label = "HIGH"
        elif agreement >= self.LOW_AGREEMENT_THRESHOLD:
            label = "MEDIUM"
        else:
            label = "LOW"
        
        return ModelDisagreementResult(
            model_count=len(model_predictions),
            available_model_count=len(probabilities),
            mean_probability=mean_prob,
            probability_std=std,
            probability_range=prob_range,
            agreement_score=agreement,
            disagreement_score=disagreement,
            model_probabilities=model_probs,
            agreement_label=label
        )
    
    def analyze_all_outcomes(
        self,
        model_predictions: List[ModelPrediction]
    ) -> Dict[str, ModelDisagreementResult]:
        """Analyze disagreement for home_win, draw, and away_win.
        
        Args:
            model_predictions: List of successful model predictions
            
        Returns:
            Dictionary mapping outcome to ModelDisagreementResult
        """
        return {
            "home_win": self.analyze(model_predictions, "home_win"),
            "draw": self.analyze(model_predictions, "draw"),
            "away_win": self.analyze(model_predictions, "away_win")
        }
