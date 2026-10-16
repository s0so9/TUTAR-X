"""Ensemble prediction engine with multiple weighting strategies.

This module implements the core ensemble engine that combines multiple model
predictions using configurable weighting strategies.

Weighting Strategies:
- StaticWeights: Manual per-model weights, normalized
- ReliabilityWeights: weight = model_confidence * data_quality_score
- DynamicWeights: League-specific adjustments applied on top of reliability weights

The ensemble calculates model agreement metrics and returns ModelAvailability
when fewer than 2 valid predictions are provided.
"""

from __future__ import annotations

import math
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from app.prediction.interfaces import ModelPrediction, ModelAvailability

logger = logging.getLogger(__name__)
from app.domain.enums import ModelType


@dataclass
class WeightingStrategy(ABC):
    """Abstract base class for model weighting strategies."""

    @abstractmethod
    def calculate_weights(
        self,
        predictions: List[ModelPrediction],
        context: Optional[Dict] = None
    ) -> Dict[str, float]:
        """Calculate weights for each model prediction.
        
        Args:
            predictions: List of model predictions
            context: Optional context with league info, etc.
            
        Returns:
            Dictionary mapping model_id to weight (unnormalized)
        """
        pass


@dataclass
class StaticWeights(WeightingStrategy):
    """Static per-model weights.
    
    Weights are manually configured and normalized to sum to 1.0.
    """
    
    weights: Dict[str, float]
    
    def calculate_weights(
        self,
        predictions: List[ModelPrediction],
        context: Optional[Dict] = None
    ) -> Dict[str, float]:
        """Return configured weights for available models.
        
        BUGFIX: Models not explicitly configured now get weight 0.0 instead of 1.0.
        This prevents untested/unvalidated models from dominating the ensemble.
        """
        result = {}
        for pred in predictions:
            result[pred.model_id] = self.weights.get(pred.model_id, 0.0)
        return result


@dataclass
class ReliabilityWeights(WeightingStrategy):
    """Reliability-based weighting.
    
    weight = model_confidence * data_quality_score
    
    Models with higher confidence and better data quality receive more weight.
    """
    
    def calculate_weights(
        self,
        predictions: List[ModelPrediction],
        context: Optional[Dict] = None
    ) -> Dict[str, float]:
        """Calculate weights based on confidence and data quality."""
        weights = {}
        for pred in predictions:
            confidence = pred.confidence_score
            data_quality = pred.data_quality_score
            weights[pred.model_id] = confidence * data_quality
        return weights


@dataclass
class DynamicWeights(WeightingStrategy):
    """Dynamic league-specific weighting.
    
    Applies league-specific adjustments on top of reliability weights.
    
    Example: In Serie A (defensive league), Dixon-Coles might get +10% weight,
    Poisson -5%. In Bundesliga (high-scoring), opposite adjustments.
    """
    
    league_adjustments: Dict[str, Dict[str, float]]
    """
    Mapping of league_id -> {model_id: adjustment_multiplier}
    Example: {
        "serie_a": {"dixon_coles_v1": 1.10, "poisson_v1": 0.95},
        "bundesliga": {"poisson_v1": 1.05, "dixon_coles_v1": 0.95}
    }
    """
    
    def calculate_weights(
        self,
        predictions: List[ModelPrediction],
        context: Optional[Dict] = None
    ) -> Dict[str, float]:
        """Calculate weights with league-specific adjustments."""
        # Start with reliability weights
        base_strategy = ReliabilityWeights()
        weights = base_strategy.calculate_weights(predictions, context)
        
        # Apply league-specific adjustments if available
        if context and "league_id" in context:
            league_id = context["league_id"]
            adjustments = self.league_adjustments.get(league_id, {})
            
            for model_id in weights:
                multiplier = adjustments.get(model_id, 1.0)
                weights[model_id] *= multiplier
        
        return weights


class EnsembleEngine:
    """Ensemble engine that combines multiple model predictions.
    
    Features:
    - Multiple weighting strategies (static, reliability-based, dynamic)
    - Model agreement calculation
    - Handles insufficient predictions gracefully
    - Normalizes probabilities to sum to 1.0
    """
    
    def __init__(self, strategy: WeightingStrategy):
        """Initialize ensemble engine.
        
        Args:
            strategy: Weighting strategy to use
        """
        self.strategy = strategy
    
    def combine(
        self,
        predictions: List[ModelPrediction],
        context: Optional[Dict] = None
    ) -> ModelPrediction | ModelAvailability:
        """Combine multiple predictions using the configured strategy.
        
        Args:
            predictions: List of model predictions (must be ≥2 for ensemble)
            context: Optional context (league_id, etc.)
            
        Returns:
            Combined ModelPrediction or ModelAvailability if insufficient data
        """
        # Check minimum requirements
        if len(predictions) < 2:
            return ModelAvailability(
                model_id="ensemble_v1",
                available=False,
                reason="insufficient_models",
                missing_features=[f"Need at least 2 models, got {len(predictions)}"]
            )
        
        # Calculate weights
        raw_weights = self.strategy.calculate_weights(predictions, context)
        
        # Validate weights
        for model_id, weight in raw_weights.items():
            if weight is None or not isinstance(weight, (int, float)):
                logger.warning(
                    f"Invalid weight type for model {model_id}: {type(weight)}. Using 0.0"
                )
                raw_weights[model_id] = 0.0
            elif math.isnan(weight) or math.isinf(weight):
                logger.warning(
                    f"Invalid weight value for model {model_id}: {weight}. Using 0.0"
                )
                raw_weights[model_id] = 0.0
            elif weight < 0:
                logger.warning(
                    f"Negative weight for model {model_id}: {weight}. Using 0.0"
                )
                raw_weights[model_id] = 0.0
        
        # Normalize weights
        total_weight = sum(raw_weights.values())
        if total_weight == 0:
            # All weights zero - no eligible models
            logger.warning(
                f"All model weights are zero for {len(predictions)} predictions. "
                f"Strategy: {self.strategy.__class__.__name__}. Returning unavailable."
            )
            return ModelAvailability(
                model_id="ensemble_v1",
                available=False,
                reason="all_weights_zero",
                missing_features=[f"All {len(predictions)} models have zero weight"]
            )
        
        normalized_weights = {
            model_id: weight / total_weight
            for model_id, weight in raw_weights.items()
        }
        
        # Combine predictions
        combined_home_win = 0.0
        combined_draw = 0.0
        combined_away_win = 0.0
        combined_home_xg = 0.0
        combined_away_xg = 0.0
        
        for pred in predictions:
            weight = normalized_weights[pred.model_id]
            combined_home_win += pred.home_win_prob * weight
            combined_draw += pred.draw_prob * weight
            combined_away_win += pred.away_win_prob * weight
            combined_home_xg += pred.home_score_mean * weight
            combined_away_xg += pred.away_score_mean * weight
        
        # Normalize probabilities (handle floating point errors)
        total_prob = combined_home_win + combined_draw + combined_away_win
        if total_prob > 0:
            combined_home_win /= total_prob
            combined_draw /= total_prob
            combined_away_win /= total_prob
        
        # Calculate model agreement
        agreement_score = self._calculate_agreement(predictions)
        
        # Calculate ensemble confidence
        ensemble_confidence = self._calculate_ensemble_confidence(
            predictions, normalized_weights, agreement_score
        )
        
        # Calculate ensemble data quality
        ensemble_data_quality = sum(
            pred.data_quality_score * normalized_weights[pred.model_id]
            for pred in predictions
        )
        
        # Combine score distributions (weighted average)
        combined_score_distribution: Dict[Tuple[int, int], float] = {}
        for pred in predictions:
            if pred.score_distribution:
                weight = normalized_weights[pred.model_id]
                for scoreline, prob in pred.score_distribution.items():
                    if scoreline not in combined_score_distribution:
                        combined_score_distribution[scoreline] = 0.0
                    combined_score_distribution[scoreline] += prob * weight
        
        # Build metadata
        metadata = {
            "model_weights": normalized_weights,
            "weighting_strategy": self.strategy.__class__.__name__,
            "model_agreement": agreement_score,
            "n_models": len(predictions),
            "contributing_models": [pred.model_id for pred in predictions]
        }
        
        return ModelPrediction(
            model_id="ensemble_v1",
            home_score_mean=combined_home_xg,
            away_score_mean=combined_away_xg,
            home_win_prob=combined_home_win,
            draw_prob=combined_draw,
            away_win_prob=combined_away_win,
            score_distribution=combined_score_distribution,
            confidence_score=ensemble_confidence,
            data_quality_score=ensemble_data_quality,
            metadata=metadata
        )
    
    def _calculate_agreement(self, predictions: List[ModelPrediction]) -> float:
        """Calculate model agreement score.
        
        PHASE 6: Enhanced agreement calculation using comprehensive probability variance.
        
        Agreement = 1 - (std_dev of home_win_prob * 3), normalized to [0, 1]
        
        When all models agree perfectly: std_dev = 0, agreement = 1.0
        When models maximally disagree: std_dev ≈ 0.33, agreement ≈ 0.0
        
        Args:
            predictions: List of model predictions
            
        Returns:
            Agreement score in [0, 1], where 1 = perfect agreement
        """
        if len(predictions) < 2:
            return 1.0
        
        # PHASE 6: Enhanced agreement using all 1X2 probabilities
        # Extract all probability dimensions
        home_probs = []
        draw_probs = []
        away_probs = []
        
        for pred in predictions:
            # Handle both attribute name variations
            home_prob = getattr(pred, 'home_win_probability', 
                               getattr(pred, 'home_win_prob', 0.33))
            draw_prob = getattr(pred, 'draw_probability', 
                               getattr(pred, 'draw_prob', 0.33))
            away_prob = getattr(pred, 'away_win_probability', 
                               getattr(pred, 'away_win_prob', 0.33))
            
            home_probs.append(home_prob)
            draw_probs.append(draw_prob)
            away_probs.append(away_prob)
        
        # Calculate standard deviation for each outcome
        def safe_std_dev(values):
            if len(set(values)) <= 1:  # All identical
                return 0.0
            mean_val = sum(values) / len(values)
            variance = sum((v - mean_val) ** 2 for v in values) / len(values)
            return math.sqrt(variance)
        
        home_std = safe_std_dev(home_probs)
        draw_std = safe_std_dev(draw_probs)
        away_std = safe_std_dev(away_probs)
        
        # Average standard deviation across all outcomes
        avg_std_dev = (home_std + draw_std + away_std) / 3.0
        
        # Convert to agreement score (normalize by factor of 3)
        # Max realistic std_dev for probabilities ≈ 0.33 (when probs range 0-1)
        agreement = max(0.0, 1.0 - (avg_std_dev * 3.0))
        
        return min(1.0, agreement)
    
    def _calculate_ensemble_confidence(
        self,
        predictions: List[ModelPrediction],
        weights: Dict[str, float],
        agreement_score: float
    ) -> float:
        """Calculate overall ensemble confidence.
        
        Ensemble confidence is weighted average of model confidences,
        adjusted by model agreement.
        
        Args:
            predictions: List of model predictions
            weights: Normalized weights for each model
            agreement_score: Model agreement score [0, 1]
            
        Returns:
            Ensemble confidence in [0, 1]
        """
        # Weighted average of individual model confidences
        avg_confidence = sum(
            pred.confidence_score * weights[pred.model_id]
            for pred in predictions
        )
        
        # Adjust by agreement (low agreement reduces confidence)
        # Use square root to avoid overly penalizing moderate disagreement
        agreement_factor = math.sqrt(agreement_score)
        
        ensemble_confidence = avg_confidence * (0.7 + 0.3 * agreement_factor)
        
        return min(1.0, max(0.0, ensemble_confidence))
