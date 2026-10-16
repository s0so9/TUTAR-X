"""Market-specific feature eligibility and selection.

This module defines which features are eligible for which markets without
prescribing feature weights. Feature weighting will be determined through
backtesting in Group 6.

Market-Specific Modeling Philosophy:
-----------------------------------
Not all features are equally relevant to all markets. For example:
- Shot volume features are highly relevant for shot markets but less so for 1X2
- Common opponent intelligence may be more relevant for handicap markets
- xG features are critical for goal-based markets but not directly for shots

This module provides:
1. MarketType enum for all supported markets
2. Feature eligibility mappings (which features CAN be used for each market)
3. MarketFeatureSelector for extracting eligible features from snapshots

NOTE: This is ELIGIBILITY, not WEIGHTING. Optimal weights are determined empirically.

Runtime Behavior vs. Group 6 Optimization:
------------------------------------------
Feature eligibility defines which features are ELIGIBLE for each market (for Group 6
feature weight optimization during backtesting) but does NOT filter features at
runtime prediction.

Models receive the full MatchFeatureSnapshot via ModelOrchestrator.run() and extract
whatever features they need independently. The eligibility mappings serve as:
1. Documentation of which features are conceptually relevant to each market
2. Input to Group 6 feature selection/weighting during walk-forward backtesting
3. Basis for market-specific model evaluation and calibration

This design allows models to use their existing feature extraction logic while
providing structure for market-aware optimization in Group 6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Set

from app.prediction.feature_snapshot import MatchFeatureSnapshot


class MarketType(str, Enum):
    """Market types supported by the prediction system.
    
    Each market may use different feature sets for optimal prediction.
    """
    
    # Primary markets
    MATCH_RESULT_1X2 = "1x2"
    OVER_UNDER = "over_under"
    BTTS = "btts"
    DOUBLE_CHANCE = "double_chance"
    HANDICAP = "handicap"
    
    # Shot markets
    TEAM_SHOTS = "team_shots"
    TEAM_SHOTS_ON_TARGET = "team_shots_on_target"
    TOTAL_SHOTS = "total_shots"
    TOTAL_SHOTS_ON_TARGET = "total_shots_on_target"


# Feature eligibility mapping: which features are eligible for each market
# Features not listed are considered ineligible for that market
# This is NOT feature weighting - weights are determined through backtesting
MARKET_FEATURE_ELIGIBILITY: Dict[MarketType, List[str]] = {
    MarketType.MATCH_RESULT_1X2: [
        # Team strength
        "home_goals_scored_per_match",
        "away_goals_scored_per_match",
        "home_goals_conceded_per_match",
        "away_goals_conceded_per_match",
        "home_xg_per_match",
        "away_xg_per_match",
        "home_xg_against_per_match",
        "away_xg_against_per_match",
        "home_attack_strength",
        "away_attack_strength",
        "home_defense_strength",
        "away_defense_strength",
        "home_elo_rating",
        "away_elo_rating",
        
        # Form
        "home_form_points_per_match",
        "away_form_points_per_match",
        "home_form_win_rate",
        "away_form_win_rate",
        "home_form_goals_for",
        "away_form_goals_for",
        "home_form_goals_against",
        "away_form_goals_against",
        
        # League context
        "home_advantage_factor",
        "league_average_goals",
        "league_strength_rating",
        
        # Advanced features (if available)
        "team_intelligence_score_home",
        "team_intelligence_score_away",
        "opponent_adjustment_factor_home",
        "opponent_adjustment_factor_away",
        "temporal_form_trend_home",
        "temporal_form_trend_away",
        "lineup_impact_score_home",
        "lineup_impact_score_away",
        "tactical_matchup_score",
        "common_opponent_strength_delta",
    ],
    
    MarketType.OVER_UNDER: [
        # Goal-scoring features
        "home_goals_scored_per_match",
        "away_goals_scored_per_match",
        "home_goals_conceded_per_match",
        "away_goals_conceded_per_match",
        "home_xg_per_match",
        "away_xg_per_match",
        "home_xg_against_per_match",
        "away_xg_against_per_match",
        
        # Attack/defense balance
        "home_attack_strength",
        "away_attack_strength",
        "home_defense_strength",
        "away_defense_strength",
        
        # League context
        "league_average_goals",
        
        # Shot volume (correlated with goals)
        "home_shots_per_match",
        "away_shots_per_match",
        "home_shots_on_target_per_match",
        "away_shots_on_target_per_match",
        
        # Advanced features
        "team_intelligence_score_home",
        "team_intelligence_score_away",
        "opponent_adjustment_factor_home",
        "opponent_adjustment_factor_away",
        "shot_intelligence_volume_home",
        "shot_intelligence_volume_away",
    ],
    
    MarketType.BTTS: [
        # Goal-scoring ability
        "home_goals_scored_per_match",
        "away_goals_scored_per_match",
        "home_goals_conceded_per_match",
        "away_goals_conceded_per_match",
        
        # Attack/defense strength
        "home_attack_strength",
        "away_attack_strength",
        "home_defense_strength",
        "away_defense_strength",
        
        # Form
        "home_form_goals_for",
        "away_form_goals_for",
        
        # Clean sheet rates (inverse indicator)
        "home_form_clean_sheet_rate",
        "away_form_clean_sheet_rate",
    ],
    
    MarketType.DOUBLE_CHANCE: [
        # Same as 1X2 (derived from 1X2 probabilities)
        "home_goals_scored_per_match",
        "away_goals_scored_per_match",
        "home_goals_conceded_per_match",
        "away_goals_conceded_per_match",
        "home_xg_per_match",
        "away_xg_per_match",
        "home_attack_strength",
        "away_attack_strength",
        "home_defense_strength",
        "away_defense_strength",
        "home_elo_rating",
        "away_elo_rating",
        "home_form_points_per_match",
        "away_form_points_per_match",
        "home_advantage_factor",
        "league_average_goals",
    ],
    
    MarketType.HANDICAP: [
        # Strength differential features
        "home_goals_scored_per_match",
        "away_goals_scored_per_match",
        "home_goals_conceded_per_match",
        "away_goals_conceded_per_match",
        "home_xg_per_match",
        "away_xg_per_match",
        "home_elo_rating",
        "away_elo_rating",
        "home_attack_strength",
        "away_attack_strength",
        "home_defense_strength",
        "away_defense_strength",
        
        # Quality gap indicators
        "common_opponent_strength_delta",
        "team_intelligence_score_home",
        "team_intelligence_score_away",
    ],
    
    MarketType.TEAM_SHOTS: [
        # Shot volume features
        "home_shots_per_match",
        "away_shots_per_match",
        
        # Shot intelligence
        "shot_intelligence_volume_home",
        "shot_intelligence_volume_away",
        "shot_intelligence_quality_home",
        "shot_intelligence_quality_away",
        
        # Opponent shot suppression
        "home_shots_against_per_match",
        "away_shots_against_per_match",
        
        # Tactical context
        "tactical_matchup_score",
        "team_intelligence_score_home",
        "team_intelligence_score_away",
    ],
    
    MarketType.TEAM_SHOTS_ON_TARGET: [
        # SOT features
        "home_shots_on_target_per_match",
        "away_shots_on_target_per_match",
        
        # Shot quality
        "shot_intelligence_quality_home",
        "shot_intelligence_quality_away",
        "home_xg_per_match",
        "away_xg_per_match",
        
        # Opponent SOT suppression
        "home_shots_against_per_match",
        "away_shots_against_per_match",
    ],
    
    MarketType.TOTAL_SHOTS: [
        # Combined shot volume
        "home_shots_per_match",
        "away_shots_per_match",
        "shot_intelligence_volume_home",
        "shot_intelligence_volume_away",
        
        # League average (for context)
        "league_average_shots",
        
        # Tactical style (affects pace/volume)
        "tactical_matchup_score",
    ],
    
    MarketType.TOTAL_SHOTS_ON_TARGET: [
        # Combined SOT volume
        "home_shots_on_target_per_match",
        "away_shots_on_target_per_match",
        "shot_intelligence_quality_home",
        "shot_intelligence_quality_away",
        
        # xG (quality proxy)
        "home_xg_per_match",
        "away_xg_per_match",
    ],
}


@dataclass
class FeatureAvailabilityReport:
    """Report on feature availability for a market."""
    
    market_type: MarketType
    eligible_feature_count: int
    available_feature_count: int
    unavailable_feature_count: int
    availability_ratio: float  # available / eligible
    
    eligible_features: List[str] = field(default_factory=list)
    available_features: List[str] = field(default_factory=list)
    unavailable_features: List[str] = field(default_factory=list)
    
    # Feature values (only available features)
    feature_values: Dict[str, float] = field(default_factory=dict)


class MarketFeatureSelector:
    """Select and extract eligible features for specific markets.
    
    This class bridges the generic MatchFeatureSnapshot to market-specific
    feature sets without applying feature weighting.
    """
    
    def __init__(self):
        """Initialize selector."""
        pass
    
    def get_eligible_features(
        self,
        market: MarketType,
        snapshot: MatchFeatureSnapshot
    ) -> Dict[str, Optional[float]]:
        """Extract eligible features for a market from snapshot.
        
        Args:
            market: Market type
            snapshot: Match feature snapshot
            
        Returns:
            Dictionary mapping feature name to value (None if unavailable)
        """
        eligible_feature_names = MARKET_FEATURE_ELIGIBILITY.get(market, [])
        result: Dict[str, Optional[float]] = {}
        
        for feature_name in eligible_feature_names:
            value = self._extract_feature_value(feature_name, snapshot)
            result[feature_name] = value
        
        return result
    
    def get_feature_availability(
        self,
        market: MarketType,
        snapshot: MatchFeatureSnapshot
    ) -> FeatureAvailabilityReport:
        """Get feature availability report for a market.
        
        Args:
            market: Market type
            snapshot: Match feature snapshot
            
        Returns:
            FeatureAvailabilityReport with availability statistics
        """
        eligible_features = self.get_eligible_features(market, snapshot)
        
        available = {k: v for k, v in eligible_features.items() if v is not None}
        unavailable = {k for k, v in eligible_features.items() if v is None}
        
        eligible_count = len(eligible_features)
        available_count = len(available)
        unavailable_count = len(unavailable)
        availability_ratio = available_count / eligible_count if eligible_count > 0 else 0.0
        
        return FeatureAvailabilityReport(
            market_type=market,
            eligible_feature_count=eligible_count,
            available_feature_count=available_count,
            unavailable_feature_count=unavailable_count,
            availability_ratio=availability_ratio,
            eligible_features=list(eligible_features.keys()),
            available_features=list(available.keys()),
            unavailable_features=list(unavailable),
            feature_values=available
        )
    
    def _extract_feature_value(
        self,
        feature_name: str,
        snapshot: MatchFeatureSnapshot
    ) -> Optional[float]:
        """Extract a single feature value from snapshot.
        
        Args:
            feature_name: Feature name to extract
            snapshot: Match feature snapshot
            
        Returns:
            Feature value or None if unavailable
        """
        # Home team strength features
        if feature_name == "home_goals_scored_per_match":
            return snapshot.home_strength.goals_scored_per_match
        elif feature_name == "home_goals_conceded_per_match":
            return snapshot.home_strength.goals_conceded_per_match
        elif feature_name == "home_xg_per_match":
            return snapshot.home_strength.xg_per_match
        elif feature_name == "home_xg_against_per_match":
            return snapshot.home_strength.xg_against_per_match
        elif feature_name == "home_attack_strength":
            return snapshot.home_strength.attack_strength
        elif feature_name == "home_defense_strength":
            return snapshot.home_strength.defense_strength
        elif feature_name == "home_elo_rating":
            return snapshot.home_strength.elo_rating
        elif feature_name == "home_shots_per_match":
            return snapshot.home_strength.shots_per_match
        elif feature_name == "home_shots_on_target_per_match":
            return snapshot.home_strength.shots_on_target_per_match
        elif feature_name == "home_shots_against_per_match":
            return snapshot.home_strength.shots_against_per_match
        
        # Away team strength features
        elif feature_name == "away_goals_scored_per_match":
            return snapshot.away_strength.goals_scored_per_match
        elif feature_name == "away_goals_conceded_per_match":
            return snapshot.away_strength.goals_conceded_per_match
        elif feature_name == "away_xg_per_match":
            return snapshot.away_strength.xg_per_match
        elif feature_name == "away_xg_against_per_match":
            return snapshot.away_strength.xg_against_per_match
        elif feature_name == "away_attack_strength":
            return snapshot.away_strength.attack_strength
        elif feature_name == "away_defense_strength":
            return snapshot.away_strength.defense_strength
        elif feature_name == "away_elo_rating":
            return snapshot.away_strength.elo_rating
        elif feature_name == "away_shots_per_match":
            return snapshot.away_strength.shots_per_match
        elif feature_name == "away_shots_on_target_per_match":
            return snapshot.away_strength.shots_on_target_per_match
        elif feature_name == "away_shots_against_per_match":
            return snapshot.away_strength.shots_against_per_match
        
        # Home form features
        elif feature_name == "home_form_points_per_match":
            return snapshot.home_form.points_per_match
        elif feature_name == "home_form_win_rate":
            return snapshot.home_form.win_rate
        elif feature_name == "home_form_goals_for":
            return float(snapshot.home_form.goals_for) if snapshot.home_form.goals_for is not None else None
        elif feature_name == "home_form_goals_against":
            return float(snapshot.home_form.goals_against) if snapshot.home_form.goals_against is not None else None
        elif feature_name == "home_form_clean_sheet_rate":
            return snapshot.home_form.clean_sheet_rate
        
        # Away form features
        elif feature_name == "away_form_points_per_match":
            return snapshot.away_form.points_per_match
        elif feature_name == "away_form_win_rate":
            return snapshot.away_form.win_rate
        elif feature_name == "away_form_goals_for":
            return float(snapshot.away_form.goals_for) if snapshot.away_form.goals_for is not None else None
        elif feature_name == "away_form_goals_against":
            return float(snapshot.away_form.goals_against) if snapshot.away_form.goals_against is not None else None
        elif feature_name == "away_form_clean_sheet_rate":
            return snapshot.away_form.clean_sheet_rate
        
        # League context features
        elif feature_name == "home_advantage_factor":
            return snapshot.league_context.home_advantage_factor
        elif feature_name == "league_average_goals":
            return snapshot.league_context.league_average_goals
        elif feature_name == "league_strength_rating":
            return snapshot.league_context.league_strength_rating
        elif feature_name == "league_average_shots":
            # This would need to be added to LeagueContext in the future
            return None
        
        # Advanced features (if available)
        elif feature_name.startswith("team_intelligence_score"):
            if snapshot.advanced_feature_set is None:
                return None
            # Advanced feature extraction would go here
            # For now return None as placeholder
            return None
        
        elif feature_name.startswith("opponent_adjustment_factor"):
            if snapshot.advanced_feature_set is None:
                return None
            return None
        
        elif feature_name.startswith("temporal_form_trend"):
            if snapshot.advanced_feature_set is None:
                return None
            return None
        
        elif feature_name.startswith("lineup_impact_score"):
            if snapshot.advanced_feature_set is None:
                return None
            return None
        
        elif feature_name == "tactical_matchup_score":
            if snapshot.advanced_feature_set is None:
                return None
            return None
        
        elif feature_name == "common_opponent_strength_delta":
            if snapshot.common_opponent_intel is None:
                return None
            return snapshot.common_opponent_intel.strength_differential
        
        elif feature_name.startswith("shot_intelligence"):
            # Shot intelligence features would be extracted from snapshot
            # For now return None as placeholder
            return None
        
        else:
            # Unknown feature
            return None
