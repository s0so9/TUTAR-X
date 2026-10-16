"""Change attribution engine.

Analyzes prediction changes between consecutive versions and explains
which factors (lineup, form, xG, tactical, model_update) caused the change.

Provides proportional attribution: factors sum to 1.0 (100% of change explained).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum
import math

from app.prediction.prediction_version import PredictionVersion


class AttributionFactorType(str, Enum):
    """Types of factors that can cause prediction changes."""
    
    LINEUP = "lineup"
    """Lineup changes or confirmations"""
    
    FORM = "form"
    """Recent team form updates"""
    
    OPPONENT = "opponent"
    """Opponent strength or form changes"""
    
    XG = "xg"
    """Expected goals model updates"""
    
    TACTICAL = "tactical"
    """Tactical matchup analysis changes"""
    
    MODEL_UPDATE = "model_update"
    """Model algorithm or calibration updates"""
    
    DATA_QUALITY = "data_quality"
    """Data quality improvements"""
    
    OTHER = "other"
    """Other unclassified factors"""


@dataclass
class AttributionFactor:
    """Single factor contributing to prediction change."""
    
    factor_type: AttributionFactorType
    """Type of factor"""
    
    magnitude: float
    """Proportional contribution to total change [0, 1]"""
    
    direction: str
    """Direction of influence: 'up' (favors home), 'down' (favors away), 'neutral'"""
    
    description: str = ""
    """Human-readable description of the factor"""
    
    def __post_init__(self):
        """Validate factor after initialization."""
        if not (0.0 <= self.magnitude <= 1.0):
            raise ValueError(f"magnitude must be in [0, 1], got {self.magnitude}")
        
        if self.direction not in ["up", "down", "neutral"]:
            raise ValueError(f"direction must be 'up', 'down', or 'neutral', got {self.direction}")


@dataclass
class ChangeAttribution:
    """Complete attribution of prediction change between two versions."""
    
    version_from: str
    """Source version identifier"""
    
    version_to: str
    """Target version identifier"""
    
    stage_from: str
    """Source stage"""
    
    stage_to: str
    """Target stage"""
    
    total_change: float
    """Total change magnitude in home_win_prob"""
    
    factors: List[AttributionFactor] = field(default_factory=list)
    """Individual attribution factors (should sum to 1.0 if meaningful change)"""
    
    def validate(self) -> None:
        """Validate attribution consistency."""
        if not self.factors:
            # No factors means no meaningful change
            return
        
        total_magnitude = sum(f.magnitude for f in self.factors)
        
        if not (0.99 <= total_magnitude <= 1.01):
            raise ValueError(
                f"Attribution factors should sum to 1.0, got {total_magnitude:.6f}"
            )


class ChangeAttributionEngine:
    """Analyzes and explains prediction changes between versions.
    
    Algorithm:
    1. Compare consecutive prediction versions
    2. Measure total change in key metrics (home_win_prob, xG, etc.)
    3. Identify what changed between versions:
       - Lineup data availability
       - Feature value changes (form, xG, etc.)
       - Model version changes
       - Data quality changes
    4. Estimate proportional contribution of each factor
    5. Normalize contributions to sum to 1.0
    
    If total change is below threshold (< 0.02 probability change),
    returns empty factors list (no meaningful change).
    """
    
    def __init__(self, min_change_threshold: float = 0.02):
        """Initialize change attribution engine.
        
        Args:
            min_change_threshold: Minimum change to consider meaningful
        """
        self.min_change_threshold = min_change_threshold
    
    def attribute(
        self,
        version_from: PredictionVersion,
        version_to: PredictionVersion
    ) -> ChangeAttribution:
        """Attribute prediction change between two versions.
        
        Args:
            version_from: Earlier prediction version
            version_to: Later prediction version
        
        Returns:
            ChangeAttribution with proportional factors
        """
        if version_from.match_id != version_to.match_id:
            raise ValueError(
                f"Versions must be for same match: "
                f"{version_from.match_id} vs {version_to.match_id}"
            )
        
        # Calculate total change
        pred_from = version_from.prediction_data
        pred_to = version_to.prediction_data
        
        home_prob_from = pred_from.get("home_win_prob", 0.0)
        home_prob_to = pred_to.get("home_win_prob", 0.0)
        
        total_change = abs(home_prob_to - home_prob_from)
        
        # If change below threshold, return empty attribution
        if total_change < self.min_change_threshold:
            return ChangeAttribution(
                version_from=version_from.version_id,
                version_to=version_to.version_id,
                stage_from=version_from.stage.value,
                stage_to=version_to.stage.value,
                total_change=total_change,
                factors=[]
            )
        
        # Detect factors
        factors = self._detect_factors(version_from, version_to, total_change)
        
        # Normalize factors to sum to 1.0
        if factors:
            total_magnitude = sum(f.magnitude for f in factors)
            if total_magnitude > 0:
                for factor in factors:
                    factor.magnitude /= total_magnitude
            else:
                # Edge case: all factors have zero magnitude
                # Should not happen due to fallback in _detect_factors, but guard anyway
                raise ValueError(
                    f"Cannot normalize factors: total magnitude is zero. "
                    f"Factors: {[(f.factor_type, f.magnitude) for f in factors]}"
                )
        
        attribution = ChangeAttribution(
            version_from=version_from.version_id,
            version_to=version_to.version_id,
            stage_from=version_from.stage.value,
            stage_to=version_to.stage.value,
            total_change=total_change,
            factors=factors
        )
        
        attribution.validate()
        
        return attribution
    
    def _detect_factors(
        self,
        version_from: PredictionVersion,
        version_to: PredictionVersion,
        total_change: float
    ) -> List[AttributionFactor]:
        """Detect factors contributing to change.
        
        Args:
            version_from: Earlier version
            version_to: Later version
            total_change: Total probability change
        
        Returns:
            List of AttributionFactor (unnormalized)
        """
        factors = []
        
        pred_from = version_from.prediction_data
        pred_to = version_to.prediction_data
        
        # Factor 1: Lineup changes
        lineup_factor = self._detect_lineup_changes(pred_from, pred_to)
        if lineup_factor:
            factors.append(lineup_factor)
        
        # Factor 2: Form changes
        form_factor = self._detect_form_changes(pred_from, pred_to)
        if form_factor:
            factors.append(form_factor)
        
        # Factor 3: xG changes
        xg_factor = self._detect_xg_changes(pred_from, pred_to)
        if xg_factor:
            factors.append(xg_factor)
        
        # Factor 4: Tactical changes
        tactical_factor = self._detect_tactical_changes(pred_from, pred_to)
        if tactical_factor:
            factors.append(tactical_factor)
        
        # Factor 5: Model updates
        model_factor = self._detect_model_updates(version_from, version_to)
        if model_factor:
            factors.append(model_factor)
        
        # Factor 6: Data quality changes
        quality_factor = self._detect_data_quality_changes(version_from, version_to)
        if quality_factor:
            factors.append(quality_factor)
        
        # If no specific factors detected, attribute to OTHER
        if not factors:
            factors.append(AttributionFactor(
                factor_type=AttributionFactorType.OTHER,
                magnitude=1.0,
                direction="neutral",
                description="Unclassified factors"
            ))
        
        return factors
    
    def _detect_lineup_changes(
        self,
        pred_from: Dict,
        pred_to: Dict
    ) -> Optional[AttributionFactor]:
        """Detect lineup-related changes."""
        player_impact_from = pred_from.get("player_impact")
        player_impact_to = pred_to.get("player_impact")
        
        # Check if lineup went from unavailable to available
        if player_impact_from is None and player_impact_to is not None:
            # Lineup confirmed
            return AttributionFactor(
                factor_type=AttributionFactorType.LINEUP,
                magnitude=0.4,  # High contribution
                direction="neutral",
                description="Lineup confirmed"
            )
        
        # Check for lineup changes (if both have player impact)
        if player_impact_from and player_impact_to:
            home_mult_from = player_impact_from.get("home_strength_multiplier", 1.0)
            home_mult_to = player_impact_to.get("home_strength_multiplier", 1.0)
            
            change = abs(home_mult_to - home_mult_from)
            if change > 0.05:
                direction = "up" if home_mult_to > home_mult_from else "down"
                return AttributionFactor(
                    factor_type=AttributionFactorType.LINEUP,
                    magnitude=0.3,
                    direction=direction,
                    description=f"Lineup impact change ({change:.2%})"
                )
        
        return None
    
    def _detect_form_changes(
        self,
        pred_from: Dict,
        pred_to: Dict
    ) -> Optional[AttributionFactor]:
        """Detect form-related changes."""
        # Check if ensemble metadata contains form changes
        ensemble_from = pred_from.get("ensemble_metadata", {})
        ensemble_to = pred_to.get("ensemble_metadata", {})
        
        # Simplified: check if form model contribution changed
        models_from = set(ensemble_from.get("contributing_models", []))
        models_to = set(ensemble_to.get("contributing_models", []))
        
        if "form_adjusted_v1" in models_to and "form_adjusted_v1" not in models_from:
            return AttributionFactor(
                factor_type=AttributionFactorType.FORM,
                magnitude=0.2,
                direction="neutral",
                description="Form model added to ensemble"
            )
        
        return None
    
    def _detect_xg_changes(
        self,
        pred_from: Dict,
        pred_to: Dict
    ) -> Optional[AttributionFactor]:
        """Detect xG-related changes."""
        home_xg_from = pred_from.get("home_xg", 0.0)
        home_xg_to = pred_to.get("home_xg", 0.0)
        away_xg_from = pred_from.get("away_xg", 0.0)
        away_xg_to = pred_to.get("away_xg", 0.0)
        
        home_change = abs(home_xg_to - home_xg_from)
        away_change = abs(away_xg_to - away_xg_from)
        
        total_xg_change = home_change + away_change
        
        if total_xg_change > 0.2:  # Meaningful xG change
            # Determine direction
            net_change = (home_xg_to - away_xg_to) - (home_xg_from - away_xg_from)
            direction = "up" if net_change > 0 else "down" if net_change < 0 else "neutral"
            
            return AttributionFactor(
                factor_type=AttributionFactorType.XG,
                magnitude=min(0.5, total_xg_change),  # Cap at 0.5
                direction=direction,
                description=f"Expected goals updated (±{total_xg_change:.2f})"
            )
        
        return None
    
    def _detect_tactical_changes(
        self,
        pred_from: Dict,
        pred_to: Dict
    ) -> Optional[AttributionFactor]:
        """Detect tactical matchup changes."""
        tactical_from = pred_from.get("tactical_matchup")
        tactical_to = pred_to.get("tactical_matchup")
        
        # Check if tactical went from unavailable to available
        if tactical_from is None and tactical_to is not None:
            return AttributionFactor(
                factor_type=AttributionFactorType.TACTICAL,
                magnitude=0.15,
                direction="neutral",
                description="Tactical analysis added"
            )
        
        # Check for tactical adjustment changes
        if tactical_from and tactical_to:
            home_adj_from = tactical_from.get("home_xG_adjustment", 0.0)
            home_adj_to = tactical_to.get("home_xG_adjustment", 0.0)
            
            change = abs(home_adj_to - home_adj_from)
            if change > 0.1:
                direction = "up" if home_adj_to > home_adj_from else "down"
                return AttributionFactor(
                    factor_type=AttributionFactorType.TACTICAL,
                    magnitude=0.2,
                    direction=direction,
                    description=f"Tactical adjustment changed (±{change:.2f})"
                )
        
        return None
    
    def _detect_model_updates(
        self,
        version_from: PredictionVersion,
        version_to: PredictionVersion
    ) -> Optional[AttributionFactor]:
        """Detect model version updates."""
        models_from = set(version_from.model_versions.items())
        models_to = set(version_to.model_versions.items())
        
        # Check for model version changes
        changed_models = models_to - models_from
        
        if changed_models:
            model_names = [model_id for model_id, _ in changed_models]
            return AttributionFactor(
                factor_type=AttributionFactorType.MODEL_UPDATE,
                magnitude=0.3,
                direction="neutral",
                description=f"Model updates: {', '.join(model_names[:2])}"
            )
        
        return None
    
    def _detect_data_quality_changes(
        self,
        version_from: PredictionVersion,
        version_to: PredictionVersion
    ) -> Optional[AttributionFactor]:
        """Detect data quality changes."""
        quality_from = version_from.data_quality_score
        quality_to = version_to.data_quality_score
        
        change = abs(quality_to - quality_from)
        
        if change > 0.1:  # Meaningful quality change
            direction = "up" if quality_to > quality_from else "down"
            return AttributionFactor(
                factor_type=AttributionFactorType.DATA_QUALITY,
                magnitude=0.15,
                direction=direction,
                description=f"Data quality changed ({change:.2%})"
            )
        
        return None
