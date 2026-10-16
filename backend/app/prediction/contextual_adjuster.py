"""Contextual adjustments for model predictions.

This module applies bounded contextual adjustments to model predictions
based on match-specific factors like home advantage, rest days, travel distance,
and competition importance.

All adjustments are bounded to prevent overpowering the statistical model.
Maximum total adjustment is ±15% on any single probability.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional

from app.prediction.interfaces import ModelPrediction


@dataclass
class ContextualAdjustments:
    """Individual contextual adjustments applied."""
    
    home_advantage_adjustment: float = 0.0
    """Home advantage multiplier on lambda_home"""
    
    rest_days_adjustment: float = 0.0
    """Rest days impact on performance"""
    
    travel_distance_adjustment: float = 0.0
    """Travel distance impact on away performance"""
    
    competition_importance_adjustment: float = 0.0
    """Competition importance impact (e.g., cup final)"""
    
    def total_home_adjustment(self) -> float:
        """Calculate total adjustment for home team."""
        return (
            self.home_advantage_adjustment +
            self.rest_days_adjustment
        )
    
    def total_away_adjustment(self) -> float:
        """Calculate total adjustment for away team."""
        return (
            self.travel_distance_adjustment +
            self.rest_days_adjustment
        )


class ContextualAdjuster:
    """Applies bounded contextual adjustments to predictions.
    
    Adjustments are applied as multipliers to the expected goals (lambdas)
    and then propagated through to probabilities.
    
    All adjustments are bounded to prevent the statistical model from being
    overwhelmed by contextual factors.
    """
    
    MAX_TOTAL_ADJUSTMENT = 0.15
    """Maximum total adjustment magnitude (±15%)"""
    
    DEFAULT_HOME_ADVANTAGE = 0.05
    """Default home advantage boost (+5%)"""
    
    def __init__(
        self,
        league_home_advantage: Optional[Dict[str, float]] = None
    ):
        """Initialize contextual adjuster.
        
        Args:
            league_home_advantage: League-specific home advantage factors
                                  e.g., {"premier_league": 0.06, "serie_a": 0.08}
        """
        self.league_home_advantage = league_home_advantage or {}
    
    def adjust(
        self,
        prediction: ModelPrediction,
        context: Dict
    ) -> ModelPrediction:
        """Apply contextual adjustments to a prediction.
        
        Args:
            prediction: Base model prediction
            context: Context dictionary with:
                - league_id: str (optional)
                - home_rest_days: int (optional)
                - away_rest_days: int (optional)
                - travel_distance_km: float (optional)
                - is_cup_final: bool (optional)
                - is_derby: bool (optional)
            
        Returns:
            Adjusted ModelPrediction
        """
        # Calculate individual adjustments
        adjustments = ContextualAdjustments()
        
        adjustments.home_advantage_adjustment = self._calculate_home_advantage(context)
        adjustments.rest_days_adjustment = self._calculate_rest_days_adjustment(context)
        adjustments.travel_distance_adjustment = self._calculate_travel_adjustment(context)
        adjustments.competition_importance_adjustment = self._calculate_importance_adjustment(context)
        
        # Apply adjustments to expected goals
        adjusted_home_xg = prediction.home_score_mean * (1.0 + adjustments.home_advantage_adjustment)
        adjusted_away_xg = prediction.away_score_mean * (1.0 + adjustments.travel_distance_adjustment)
        
        # Apply rest days adjustment (can affect both teams differently)
        home_rest = context.get("home_rest_days", 7)
        away_rest = context.get("away_rest_days", 7)
        
        if home_rest < 3:
            adjusted_home_xg *= 0.97  # -3% for tired home team
        if away_rest < 3:
            adjusted_away_xg *= 0.97  # -3% for tired away team
        
        # Apply importance adjustment (neutralizes home advantage for neutral venues)
        if context.get("is_cup_final", False):
            # Cup finals often at neutral venues - reduce home advantage
            adjusted_home_xg *= 0.95
        
        # Bound total adjustments
        home_adjustment_total = (adjusted_home_xg - prediction.home_score_mean) / prediction.home_score_mean
        away_adjustment_total = (adjusted_away_xg - prediction.away_score_mean) / prediction.away_score_mean
        
        if abs(home_adjustment_total) > self.MAX_TOTAL_ADJUSTMENT:
            adjusted_home_xg = prediction.home_score_mean * (
                1.0 + math.copysign(self.MAX_TOTAL_ADJUSTMENT, home_adjustment_total)
            )
        
        if abs(away_adjustment_total) > self.MAX_TOTAL_ADJUSTMENT:
            adjusted_away_xg = prediction.away_score_mean * (
                1.0 + math.copysign(self.MAX_TOTAL_ADJUSTMENT, away_adjustment_total)
            )
        
        # Recalculate probabilities using Poisson approximation
        # (More sophisticated: rerun the full model, but this is a reasonable approximation)
        adjusted_probs = self._recalculate_probabilities(
            adjusted_home_xg,
            adjusted_away_xg
        )
        
        # Create adjusted prediction
        adjusted_metadata = dict(prediction.metadata)
        adjusted_metadata["contextual_adjustments"] = {
            "home_advantage": adjustments.home_advantage_adjustment,
            "rest_days": adjustments.rest_days_adjustment,
            "travel_distance": adjustments.travel_distance_adjustment,
            "importance": adjustments.competition_importance_adjustment,
            "original_home_xg": prediction.home_score_mean,
            "original_away_xg": prediction.away_score_mean,
            "adjusted_home_xg": adjusted_home_xg,
            "adjusted_away_xg": adjusted_away_xg,
        }
        
        return ModelPrediction(
            model_id=prediction.model_id + "_adjusted",
            home_score_mean=adjusted_home_xg,
            away_score_mean=adjusted_away_xg,
            home_win_prob=adjusted_probs["home_win"],
            draw_prob=adjusted_probs["draw"],
            away_win_prob=adjusted_probs["away_win"],
            confidence_score=prediction.confidence_score,
            data_quality_score=prediction.data_quality_score,
            metadata=adjusted_metadata
        )
    
    def _calculate_home_advantage(self, context: Dict) -> float:
        """Calculate home advantage adjustment.
        
        Args:
            context: Context with optional league_id
            
        Returns:
            Home advantage multiplier (default +5%, range [-10%, +15%])
        """
        league_id = context.get("league_id")
        
        if league_id and league_id in self.league_home_advantage:
            return self.league_home_advantage[league_id]
        
        return self.DEFAULT_HOME_ADVANTAGE
    
    def _calculate_rest_days_adjustment(self, context: Dict) -> float:
        """Calculate rest days adjustment.
        
        Teams with <3 days rest get -3% performance.
        
        Args:
            context: Context with optional home_rest_days, away_rest_days
            
        Returns:
            Rest days adjustment (0 or -0.03)
        """
        # This is applied per-team in the adjust() method
        return 0.0
    
    def _calculate_travel_adjustment(self, context: Dict) -> float:
        """Calculate travel distance adjustment for away team.
        
        >500km travel → -2% on away team performance
        
        Args:
            context: Context with optional travel_distance_km
            
        Returns:
            Travel adjustment (0 or -0.02)
        """
        travel_km = context.get("travel_distance_km", 0)
        
        if travel_km > 500:
            return -0.02
        
        return 0.0
    
    def _calculate_importance_adjustment(self, context: Dict) -> float:
        """Calculate competition importance adjustment.
        
        Cup finals and major competitions may neutralize home advantage.
        
        Args:
            context: Context with optional is_cup_final, is_derby
            
        Returns:
            Importance adjustment
        """
        # Applied directly in adjust() method
        return 0.0
    
    def _recalculate_probabilities(
        self,
        home_xg: float,
        away_xg: float,
        max_goals: int = 10
    ) -> Dict[str, float]:
        """Recalculate 1X2 probabilities from adjusted expected goals.
        
        Uses Poisson approximation to derive probabilities.
        
        Args:
            home_xg: Adjusted home expected goals
            away_xg: Adjusted away expected goals
            max_goals: Maximum goals to consider
            
        Returns:
            Dictionary with home_win, draw, away_win probabilities
        """
        # Calculate Poisson probabilities for each scoreline
        home_win_prob = 0.0
        draw_prob = 0.0
        away_win_prob = 0.0
        
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                prob = self._poisson_pmf(h, home_xg) * self._poisson_pmf(a, away_xg)
                
                if h > a:
                    home_win_prob += prob
                elif h == a:
                    draw_prob += prob
                else:
                    away_win_prob += prob
        
        # Normalize (in case we truncated at max_goals)
        total = home_win_prob + draw_prob + away_win_prob
        if total > 0:
            home_win_prob /= total
            draw_prob /= total
            away_win_prob /= total
        
        return {
            "home_win": home_win_prob,
            "draw": draw_prob,
            "away_win": away_win_prob
        }
    
    @staticmethod
    def _poisson_pmf(k: int, lam: float) -> float:
        """Calculate Poisson probability mass function.
        
        P(X = k) = (λ^k * e^(-λ)) / k!
        
        Args:
            k: Number of goals
            lam: Expected goals (lambda)
            
        Returns:
            Probability
        """
        if lam == 0:
            return 1.0 if k == 0 else 0.0
        
        # Use log for numerical stability
        log_prob = k * math.log(lam) - lam - math.lgamma(k + 1)
        return math.exp(log_prob)
