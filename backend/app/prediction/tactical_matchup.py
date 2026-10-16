"""Tactical matchup engine - STRUCTURED FEATURES ONLY, NO LLM.

This module analyzes tactical matchups based on STRUCTURED tactical profiles.
ALL conclusions derived from data - NEVER invented.

Tactical dimensions:
- pressing_intensity: [0, 1] (0 = low press, 1 = high press)
- possession_tendency: [0, 1] (0 = direct, 1 = possession-based)
- transition_speed: [0, 1] (0 = slow, 1 = fast transitions)
- build_up_style: [0, 1] (0 = long balls, 1 = short passing)

Returns explicit unavailability when data not available.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional


@dataclass
class TacticalProfile:
    """Structured tactical profile for a team.
    
    All values in [0, 1] for normalization.
    Values derived from historical match data (pass completion, pressing actions, etc.)
    """
    
    team_id: str
    
    pressing_intensity: Optional[float] = None
    """High press intensity [0, 1]"""
    
    possession_tendency: Optional[float] = None
    """Possession preference [0, 1]"""
    
    transition_speed: Optional[float] = None
    """Speed of transitions [0, 1]"""
    
    build_up_style: Optional[float] = None
    """Build-up style [0, 1] (0=direct, 1=short passing)"""
    
    # Data quality
    matches_analyzed: int = 0
    last_updated: Optional[datetime] = None
    
    @property
    def is_complete(self) -> bool:
        """Whether all tactical dimensions are available."""
        return all(x is not None for x in [
            self.pressing_intensity,
            self.possession_tendency,
            self.transition_speed,
            self.build_up_style
        ])
    
    @property
    def completeness_score(self) -> float:
        """Fraction of dimensions that are available [0, 1]."""
        available = sum(1 for x in [
            self.pressing_intensity,
            self.possession_tendency,
            self.transition_speed,
            self.build_up_style
        ] if x is not None)
        return available / 4.0


@dataclass
class TacticalMatchupResult:
    """Result of tactical matchup analysis."""
    
    home_advantage_score: float
    """Tactical advantage score [-1, 1] where positive = home favored"""
    
    key_matchup: str
    """Dominant tactical dimension driving the result"""
    
    confidence: float
    """Confidence in analysis based on data completeness [0, 1]"""
    
    advantage: str
    """Overall advantage: HOME, AWAY, or NEUTRAL"""
    
    dimension_advantages: Dict[str, float]
    """Per-dimension advantages: {"pressing": 0.2, "possession": -0.1, ...}"""
    
    explanation: str
    """Structured explanation of tactical matchup"""


class TacticalMatchupEngine:
    """Tactical matchup analyzer - STRUCTURED FEATURES ONLY.
    
    Compares tactical profiles on 4 dimensions and determines
    which team has tactical advantages.
    
    NO LLM. ALL conclusions from structured data.
    """
    
    MIN_MATCHES_FOR_PROFILE = 5
    """Minimum matches needed for reliable tactical profile"""
    
    def __init__(self):
        """Initialize tactical matchup engine."""
        pass
    
    def analyze(
        self,
        home_profile: TacticalProfile,
        away_profile: TacticalProfile
    ) -> TacticalMatchupResult | None:
        """Analyze tactical matchup between two teams.
        
        Args:
            home_profile: Home team tactical profile
            away_profile: Away team tactical profile
            
        Returns:
            TacticalMatchupResult or None if insufficient data
        """
        # Check data availability
        if not self._has_sufficient_data(home_profile, away_profile):
            return None
        
        # Calculate dimension-by-dimension advantages
        dimension_advantages = self._calculate_dimension_advantages(
            home_profile, away_profile
        )
        
        # Identify key matchup (largest absolute advantage)
        key_matchup = max(
            dimension_advantages.items(),
            key=lambda x: abs(x[1])
        )[0]
        
        # Calculate overall advantage score (weighted average)
        home_advantage_score = self._calculate_overall_advantage(dimension_advantages)
        
        # Determine advantage label
        if home_advantage_score > 0.15:
            advantage = "HOME"
        elif home_advantage_score < -0.15:
            advantage = "AWAY"
        else:
            advantage = "NEUTRAL"
        
        # Calculate confidence based on data completeness
        confidence = min(
            home_profile.completeness_score,
            away_profile.completeness_score
        )
        
        # If both teams analyzed from few matches, reduce confidence
        if home_profile.matches_analyzed < self.MIN_MATCHES_FOR_PROFILE:
            confidence *= 0.7
        if away_profile.matches_analyzed < self.MIN_MATCHES_FOR_PROFILE:
            confidence *= 0.7
        
        # Generate structured explanation
        explanation = self._generate_explanation(
            key_matchup, dimension_advantages, advantage
        )
        
        return TacticalMatchupResult(
            home_advantage_score=home_advantage_score,
            key_matchup=key_matchup,
            confidence=confidence,
            advantage=advantage,
            dimension_advantages=dimension_advantages,
            explanation=explanation
        )
    
    def _has_sufficient_data(
        self,
        home_profile: TacticalProfile,
        away_profile: TacticalProfile
    ) -> bool:
        """Check if sufficient tactical data available.
        
        Args:
            home_profile: Home team profile
            away_profile: Away team profile
            
        Returns:
            True if at least 2 dimensions available for both teams
        """
        return (
            home_profile.completeness_score >= 0.5 and
            away_profile.completeness_score >= 0.5
        )
    
    def _calculate_dimension_advantages(
        self,
        home_profile: TacticalProfile,
        away_profile: TacticalProfile
    ) -> Dict[str, float]:
        """Calculate advantage on each tactical dimension.
        
        Args:
            home_profile: Home team profile
            away_profile: Away team profile
            
        Returns:
            Dictionary of dimension -> advantage score [-1, 1]
        """
        advantages = {}
        
        # Pressing matchup
        if home_profile.pressing_intensity is not None and away_profile.pressing_intensity is not None:
            # High press vs low press: high presser has advantage
            # But extreme difference means low presser might exploit space
            press_diff = home_profile.pressing_intensity - away_profile.pressing_intensity
            if abs(press_diff) > 0.4:
                # Extreme difference: counter-pressing opportunity for low presser
                advantages["pressing"] = press_diff * 0.5
            else:
                advantages["pressing"] = press_diff
        
        # Possession matchup
        if home_profile.possession_tendency is not None and away_profile.possession_tendency is not None:
            # Possession-based team vs direct team: depends on execution
            # Moderate advantage to possession team
            poss_diff = home_profile.possession_tendency - away_profile.possession_tendency
            advantages["possession"] = poss_diff * 0.6
        
        # Transition speed matchup
        if home_profile.transition_speed is not None and away_profile.transition_speed is not None:
            # Fast transitions vs slow: fast team has advantage
            trans_diff = home_profile.transition_speed - away_profile.transition_speed
            advantages["transition"] = trans_diff * 0.7
        
        # Build-up style matchup
        if home_profile.build_up_style is not None and away_profile.build_up_style is not None:
            # Short passing vs long balls: tactical flexibility advantage
            build_diff = home_profile.build_up_style - away_profile.build_up_style
            advantages["build_up"] = build_diff * 0.5
        
        return advantages
    
    def _calculate_overall_advantage(
        self,
        dimension_advantages: Dict[str, float]
    ) -> float:
        """Calculate overall tactical advantage score.
        
        Weighted average of dimension advantages.
        
        Args:
            dimension_advantages: Per-dimension advantages
            
        Returns:
            Overall advantage score [-1, 1]
        """
        if not dimension_advantages:
            return 0.0
        
        # Weights for each dimension
        weights = {
            "pressing": 0.30,
            "possession": 0.25,
            "transition": 0.25,
            "build_up": 0.20
        }
        
        weighted_sum = 0.0
        total_weight = 0.0
        
        for dimension, advantage in dimension_advantages.items():
            weight = weights.get(dimension, 0.25)
            weighted_sum += advantage * weight
            total_weight += weight
        
        if total_weight == 0:
            return 0.0
        
        overall = weighted_sum / total_weight
        
        # Bound to [-1, 1]
        return max(-1.0, min(1.0, overall))
    
    def _generate_explanation(
        self,
        key_matchup: str,
        dimension_advantages: Dict[str, float],
        advantage: str
    ) -> str:
        """Generate structured explanation of tactical matchup.
        
        Args:
            key_matchup: Dominant tactical dimension
            dimension_advantages: Per-dimension advantages
            advantage: Overall advantage (HOME/AWAY/NEUTRAL)
            
        Returns:
            Structured explanation string
        """
        key_advantage = dimension_advantages.get(key_matchup, 0.0)
        
        dimension_names = {
            "pressing": "pressing intensity",
            "possession": "possession tendency",
            "transition": "transition speed",
            "build_up": "build-up style"
        }
        
        key_name = dimension_names.get(key_matchup, key_matchup)
        
        if advantage == "HOME":
            direction = "home team's advantage in"
        elif advantage == "AWAY":
            direction = "away team's advantage in"
        else:
            direction = "balanced matchup with slight differences in"
        
        explanation = f"Tactical matchup driven by {direction} {key_name} "
        explanation += f"(advantage score: {key_advantage:+.2f}). "
        
        # Add secondary factors
        other_dimensions = [
            (dim, adv) for dim, adv in dimension_advantages.items()
            if dim != key_matchup and abs(adv) > 0.1
        ]
        
        if other_dimensions:
            explanation += "Secondary factors: "
            factors = [
                f"{dimension_names.get(dim, dim)} ({adv:+.2f})"
                for dim, adv in other_dimensions
            ]
            explanation += ", ".join(factors)
        
        return explanation
