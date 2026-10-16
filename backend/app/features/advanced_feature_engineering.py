"""Advanced feature engineering for Groups 1-3 intelligence integration.

This module transforms separate intelligence components from Groups 1-3 into a clean,
auditable, production-ready feature engineering layer.

ARCHITECTURE:
    Groups 1-3 Calculators (unchanged)
        ↓
    AdvancedFeatureEngineer (new, Group 4)
        ↓
    MatchFeatureSnapshot.advanced_feature_set (optional field, added)
        ↓
    7 existing models (unchanged)

DATA PRINCIPLES:
- Missing data → None (never 0, never fabricated)
- Temporal validity: all features use strict < before_datetime
- Partial availability preserved
- Provenance tracked per feature
- Data quality aggregated across sources

PHASE: Phase 10 Group 4
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
import math

from app.features.advanced_team_intelligence import (
    MatchWithStatistics,
    AdvancedTeamMetrics,
    AdvancedTeamIntelligenceCalculator,
)
from app.features.opponent_adjustment import (
    OpponentAdjustedMetrics,
    OpponentAdjustmentCalculator,
)
from app.features.temporal_intelligence import (
    TemporalIntelligenceMetrics,
    TemporalIntelligenceCalculator,
)
from app.features.lineup_intelligence import (
    LineupImpactEstimate,
    LineupIntelligenceCalculator,
)
from app.features.tactical_matchup import (
    TacticalProfile,
    TacticalMatchup,
    TacticalMatchupCalculator,
)
from app.features.shot_intelligence import (
    ShotIntelligenceMetrics,
    ShotIntelligenceCalculator,
)
from app.features.shot_production import (
    ShotProduction,
    ShotProductionCalculator,
)
from app.features.snapshot_cache import FeatureSnapshotCache, CacheKey
from app.features.common_opponent_intelligence import (
    CommonOpponentIntelligence,
    CommonOpponentCalculator,
)


# Feature version for semantic versioning
ADVANCED_FEATURE_VERSION = "1.0.0"


class FeatureAvailability(str, Enum):
    """Feature availability classification."""
    RAW = "raw"  # Direct from TeamMatchStatistic
    DERIVED = "derived"  # Calculated from raw (e.g., xg_per_shot)
    INTERACTION = "interaction"  # Interaction between features (e.g., differential)
    MODEL_READY = "model_ready"  # Ready for production models
    UNAVAILABLE = "unavailable"  # Missing, cannot calculate


@dataclass
class AdvancedFeatureMetadata:
    """Provenance and metadata for a single feature.
    
    Tracks source, timestamp, transformation, and quality for full auditability.
    """
    feature_name: str
    source_module: str  # e.g., "advanced_team_intelligence", "opponent_adjustment"
    source_timestamp: Optional[datetime]  # When raw data was fetched (None for derived)
    prediction_timestamp: datetime  # When prediction is being made
    historical_window: str  # e.g., "recent", "medium", "season"
    home_away_context: Optional[str] = None  # "home", "away", "all", None
    competition_context: Optional[str] = None  # Competition ID if relevant
    availability: FeatureAvailability = FeatureAvailability.UNAVAILABLE
    data_quality_score: float = 0.0  # 0.0-1.0 from source calculator
    feature_version: str = ADVANCED_FEATURE_VERSION
    transformation_applied: Optional[str] = None  # e.g., "differential", "ratio"
    
    def validate_temporal_consistency(self) -> bool:
        """Validate that source_timestamp < prediction_timestamp.
        
        Returns:
            True if temporal consistency valid or cannot validate (source_timestamp None)
        """
        if self.source_timestamp is None:
            return True  # Derived features have no source timestamp
        return self.source_timestamp < self.prediction_timestamp


@dataclass
class InteractionFeature:
    """Explicit interaction feature definition.
    
    Defines how two features interact to create a derived feature.
    """
    feature_a: str
    feature_b: str
    operation: str  # "difference", "ratio", "multiply", "divide"
    name: str  # Output feature name
    
    def compute(self, features: Dict[str, Optional[float]]) -> Optional[float]:
        """Compute interaction from feature dict.
        
        Handles None inputs and div-by-zero gracefully.
        Returns None if inputs unavailable or computation invalid.
        
        Args:
            features: Dictionary of feature name -> value
            
        Returns:
            Computed interaction value or None if cannot compute
        """
        a_val = features.get(self.feature_a)
        b_val = features.get(self.feature_b)
        
        if a_val is None or b_val is None:
            return None
        
        if self.operation == "difference":
            return a_val - b_val
        elif self.operation == "ratio":
            total = a_val + b_val
            if total == 0:
                return None
            return a_val / total
        elif self.operation == "multiply":
            return a_val * b_val
        elif self.operation == "divide":
            if b_val == 0:
                return None
            return a_val / b_val
        else:
            return None


@dataclass
class AdvancedFeatureSet:
    """Complete engineered feature collection from Groups 1-3.
    
    Represents the unified feature state at a specific prediction timestamp.
    """
    features: Dict[str, Optional[float]] = field(default_factory=dict)
    feature_metadata: Dict[str, AdvancedFeatureMetadata] = field(default_factory=dict)
    interaction_features: List[str] = field(default_factory=list)
    redundancy_flags: Dict[str, List[str]] = field(default_factory=dict)
    overall_data_quality: float = 0.0  # 0.0-1.0 weighted quality score
    feature_version: str = ADVANCED_FEATURE_VERSION
    snapshot_timestamp: datetime = field(default_factory=datetime.utcnow)
    temporal_validity_checked: bool = False
    
    def validate_no_leakage(self) -> bool:
        """Validate no temporal leakage in feature set.
        
        Returns:
            True if all feature metadata passes temporal consistency check
        """
        for name, metadata in self.feature_metadata.items():
            if not metadata.validate_temporal_consistency():
                return False
        return True


# Candidate interaction features (disabled by default, enabled via flag)
CANDIDATE_INTERACTIONS = [
    InteractionFeature("home_xg_for_per_match", "away_xg_against_per_match", "multiply", "home_attack_vs_away_defense"),
    InteractionFeature("away_xg_for_per_match", "home_xg_against_per_match", "multiply", "away_attack_vs_home_defense"),
    InteractionFeature("home_shots_per_match", "away_shots_per_match", "difference", "shot_volume_edge"),
    InteractionFeature("home_adj_xg_for", "away_adj_xg_for", "difference", "adj_xg_differential"),
    InteractionFeature("home_temporal_form_weighted", "away_temporal_form_weighted", "difference", "temporal_form_edge"),
    InteractionFeature("home_xg_for_per_match", "away_xg_for_per_match", "ratio", "xg_share_home"),
    InteractionFeature("home_shots_per_match", "away_shots_per_match", "ratio", "shot_share_home"),
]


class AdvancedFeatureEngineer:
    """Advanced feature engineer integrating Groups 1-3 calculators.
    
    Transforms separate intelligence components into unified feature representation
    for model consumption.
    """
    
    def __init__(
        self,
        create_interactions: bool = False,
        interactions: Optional[List[InteractionFeature]] = None,
        feature_cache: Optional[FeatureSnapshotCache] = None
    ):
        """Initialize feature engineer.
        
        Args:
            create_interactions: Whether to create interaction features
            interactions: Explicit list of interactions to compute (default: CANDIDATE_INTERACTIONS)
            feature_cache: Optional cache for feature snapshot deduplication
        """
        self.create_interactions = create_interactions
        self.interactions = interactions if interactions is not None else CANDIDATE_INTERACTIONS
        self.feature_cache = feature_cache
    
    def engineer_features(
        self,
        home_team_id: str,
        away_team_id: str,
        matches_with_stats: List[MatchWithStatistics],
        before_datetime: datetime,
        prediction_timestamp: Optional[datetime] = None,
    ) -> AdvancedFeatureSet:
        """Engineer features from all Groups 1-3 calculators.
        
        ALGORITHM:
        1. Call all 8 calculators with before_datetime (temporal validity)
        2. Extract raw features from calculator outputs
        3. Create normalized/derived features (differentials, shares, rates)
        4. Create interaction features (if enabled)
        5. Track provenance for each feature
        6. Calculate overall data quality
        7. Flag potential redundancy
        8. Validate temporal validity
        
        Args:
            home_team_id: Home team database ID
            away_team_id: Away team database ID
            matches_with_stats: Historical matches with statistics
            before_datetime: Temporal cutoff (strict <)
            prediction_timestamp: When prediction is being made (defaults to before_datetime)
            
        Returns:
            AdvancedFeatureSet with all available features and metadata
        """
        if prediction_timestamp is None:
            prediction_timestamp = before_datetime
        
        # Clear cache at start of prediction
        if self.feature_cache:
            self.feature_cache.clear()
        
        features: Dict[str, Optional[float]] = {}
        feature_metadata: Dict[str, AdvancedFeatureMetadata] = {}
        quality_scores: List[float] = []
        quality_weights: List[float] = []
        
        # 1. Advanced Team Intelligence (Group 1) - WITH CACHING
        team_intel_calc = AdvancedTeamIntelligenceCalculator(session=None, min_matches=5)
        
        # Home team
        home_cache_key = CacheKey(home_team_id, "recent", prediction_timestamp, "team_intelligence")
        if self.feature_cache:
            home_team_metrics = self.feature_cache.get(home_cache_key)
        else:
            home_team_metrics = None
        
        if home_team_metrics is None:
            home_team_metrics = team_intel_calc.calculate_advanced_metrics(
                team_id=home_team_id,
                matches_with_stats=matches_with_stats,
                before_datetime=before_datetime
            )
            if self.feature_cache:
                self.feature_cache.set(home_cache_key, home_team_metrics)
        
        # Away team
        away_cache_key = CacheKey(away_team_id, "recent", prediction_timestamp, "team_intelligence")
        if self.feature_cache:
            away_team_metrics = self.feature_cache.get(away_cache_key)
        else:
            away_team_metrics = None
        
        if away_team_metrics is None:
            away_team_metrics = team_intel_calc.calculate_advanced_metrics(
                team_id=away_team_id,
                matches_with_stats=matches_with_stats,
                before_datetime=before_datetime
            )
            if self.feature_cache:
                self.feature_cache.set(away_cache_key, away_team_metrics)
        
        # Extract team intelligence features
        self._extract_team_metrics(
            home_team_metrics, "home", prediction_timestamp, features, feature_metadata
        )
        self._extract_team_metrics(
            away_team_metrics, "away", prediction_timestamp, features, feature_metadata
        )
        
        if home_team_metrics.data_quality_score > 0:
            quality_scores.append(home_team_metrics.data_quality_score)
            quality_weights.append(0.25)
        if away_team_metrics.data_quality_score > 0:
            quality_scores.append(away_team_metrics.data_quality_score)
            quality_weights.append(0.25)
        
        # 2. Opponent Adjustment (Group 1) - WITH CACHING
        # Note: OpponentAdjustmentCalculator needs EloRatingSystem, passing None for now
        # In production, this would be wired properly
        try:
            opp_adj_calc = OpponentAdjustmentCalculator(session=None, elo_system=None, min_matches=5)
            
            # Home team
            home_opp_key = CacheKey(home_team_id, "recent", prediction_timestamp, "opponent_adjustment")
            if self.feature_cache:
                home_adj_metrics = self.feature_cache.get(home_opp_key)
            else:
                home_adj_metrics = None
            
            if home_adj_metrics is None:
                home_adj_metrics = opp_adj_calc.calculate_adjusted_metrics(
                    team_id=home_team_id,
                    matches_with_stats=matches_with_stats,
                    before_datetime=before_datetime
                )
                if self.feature_cache:
                    self.feature_cache.set(home_opp_key, home_adj_metrics)
            
            # Away team
            away_opp_key = CacheKey(away_team_id, "recent", prediction_timestamp, "opponent_adjustment")
            if self.feature_cache:
                away_adj_metrics = self.feature_cache.get(away_opp_key)
            else:
                away_adj_metrics = None
            
            if away_adj_metrics is None:
                away_adj_metrics = opp_adj_calc.calculate_adjusted_metrics(
                    team_id=away_team_id,
                    matches_with_stats=matches_with_stats,
                    before_datetime=before_datetime
                )
                if self.feature_cache:
                    self.feature_cache.set(away_opp_key, away_adj_metrics)
            
            self._extract_opponent_adjusted(
                home_adj_metrics, "home", prediction_timestamp, features, feature_metadata
            )
            self._extract_opponent_adjusted(
                away_adj_metrics, "away", prediction_timestamp, features, feature_metadata
            )
            
            if home_adj_metrics.data_quality_score > 0:
                quality_scores.append(home_adj_metrics.data_quality_score)
                quality_weights.append(0.15)
            if away_adj_metrics.data_quality_score > 0:
                quality_scores.append(away_adj_metrics.data_quality_score)
                quality_weights.append(0.15)
        except Exception:
            # OpponentAdjustment may fail without Elo system, continue without it
            pass
        
        # 3. Temporal Intelligence (Group 1) - WITH CACHING
        temporal_calc = TemporalIntelligenceCalculator(session=None, min_matches=5)
        
        # Home team
        home_temporal_key = CacheKey(home_team_id, "recent", prediction_timestamp, "temporal_intelligence")
        if self.feature_cache:
            home_temporal = self.feature_cache.get(home_temporal_key)
        else:
            home_temporal = None
        
        if home_temporal is None:
            home_temporal = temporal_calc.calculate_temporal_metrics(
                team_id=home_team_id,
                matches_with_stats=matches_with_stats,
                before_datetime=before_datetime
            )
            if self.feature_cache:
                self.feature_cache.set(home_temporal_key, home_temporal)
        
        # Away team
        away_temporal_key = CacheKey(away_team_id, "recent", prediction_timestamp, "temporal_intelligence")
        if self.feature_cache:
            away_temporal = self.feature_cache.get(away_temporal_key)
        else:
            away_temporal = None
        
        if away_temporal is None:
            away_temporal = temporal_calc.calculate_temporal_metrics(
                team_id=away_team_id,
                matches_with_stats=matches_with_stats,
                before_datetime=before_datetime
            )
            if self.feature_cache:
                self.feature_cache.set(away_temporal_key, away_temporal)
        
        self._extract_temporal(
            home_temporal, "home", prediction_timestamp, features, feature_metadata
        )
        self._extract_temporal(
            away_temporal, "away", prediction_timestamp, features, feature_metadata
        )
        
        # TemporalIntelligenceMetrics doesn't have data_quality_score, use sample_size as proxy
        temporal_quality = min(1.0, home_temporal.sample_size / 10.0) if home_temporal.sample_size > 0 else 0.0
        if temporal_quality > 0:
            quality_scores.append(temporal_quality)
            quality_weights.append(0.15)
        temporal_quality_away = min(1.0, away_temporal.sample_size / 10.0) if away_temporal.sample_size > 0 else 0.0
        if temporal_quality_away > 0:
            quality_scores.append(temporal_quality_away)
            quality_weights.append(0.15)
        
        # 4. Lineup Intelligence (Group 2) - WITH CACHING
        lineup_calc = LineupIntelligenceCalculator(session=None)
        
        # Home team
        home_lineup_key = CacheKey(home_team_id, "recent", prediction_timestamp, "lineup_intelligence")
        if self.feature_cache:
            home_lineup = self.feature_cache.get(home_lineup_key)
        else:
            home_lineup = None
        
        if home_lineup is None:
            home_lineup = lineup_calc.calculate_lineup_impact(
                team_id=home_team_id,
                player_absences=[],  # No player absence data in this context
                historical_matches_with_stats=matches_with_stats,
                before_datetime=before_datetime
            )
            if self.feature_cache:
                self.feature_cache.set(home_lineup_key, home_lineup)
        
        # Away team
        away_lineup_key = CacheKey(away_team_id, "recent", prediction_timestamp, "lineup_intelligence")
        if self.feature_cache:
            away_lineup = self.feature_cache.get(away_lineup_key)
        else:
            away_lineup = None
        
        if away_lineup is None:
            away_lineup = lineup_calc.calculate_lineup_impact(
                team_id=away_team_id,
                player_absences=[],  # No player absence data in this context
                historical_matches_with_stats=matches_with_stats,
                before_datetime=before_datetime
            )
            if self.feature_cache:
                self.feature_cache.set(away_lineup_key, away_lineup)
        
        self._extract_lineup(
            home_lineup, "home", prediction_timestamp, features, feature_metadata
        )
        self._extract_lineup(
            away_lineup, "away", prediction_timestamp, features, feature_metadata
        )
        
        if home_lineup.data_quality > 0:
            quality_scores.append(home_lineup.data_quality)
            quality_weights.append(0.10)
        if away_lineup.data_quality > 0:
            quality_scores.append(away_lineup.data_quality)
            quality_weights.append(0.10)
        
        # 5. Tactical Matchup (Group 2) - WITH CACHING
        tactical_calc = TacticalMatchupCalculator(session=None, min_matches=5)
        
        # Home team tactical profile
        home_tactical_key = CacheKey(home_team_id, "recent", prediction_timestamp, "tactical_profile")
        if self.feature_cache:
            home_tactical_profile = self.feature_cache.get(home_tactical_key)
        else:
            home_tactical_profile = None
        
        if home_tactical_profile is None:
            home_tactical_profile = tactical_calc.calculate_tactical_profile(
                team_id=home_team_id,
                matches_with_stats=matches_with_stats,
                before_datetime=before_datetime
            )
            if self.feature_cache:
                self.feature_cache.set(home_tactical_key, home_tactical_profile)
        
        # Away team tactical profile
        away_tactical_key = CacheKey(away_team_id, "recent", prediction_timestamp, "tactical_profile")
        if self.feature_cache:
            away_tactical_profile = self.feature_cache.get(away_tactical_key)
        else:
            away_tactical_profile = None
        
        if away_tactical_profile is None:
            away_tactical_profile = tactical_calc.calculate_tactical_profile(
                team_id=away_team_id,
                matches_with_stats=matches_with_stats,
                before_datetime=before_datetime
            )
            if self.feature_cache:
                self.feature_cache.set(away_tactical_key, away_tactical_profile)
        
        tactical_matchup = tactical_calc.calculate_matchup(
            home_profile=home_tactical_profile,
            away_profile=away_tactical_profile
        )
        
        self._extract_tactical(
            tactical_matchup, prediction_timestamp, features, feature_metadata
        )
        
        if tactical_matchup.data_quality_score > 0:
            quality_scores.append(tactical_matchup.data_quality_score)
            quality_weights.append(0.10)
        
        # 6. Shot Intelligence (Group 2) - WITH CACHING
        shot_intel_calc = ShotIntelligenceCalculator(session=None, min_matches=5)
        
        # Home team
        home_shot_key = CacheKey(home_team_id, "recent", prediction_timestamp, "shot_intelligence")
        if self.feature_cache:
            home_shot_intel = self.feature_cache.get(home_shot_key)
        else:
            home_shot_intel = None
        
        if home_shot_intel is None:
            home_shot_intel = shot_intel_calc.calculate_shot_metrics(
                team_id=home_team_id,
                matches_with_stats=matches_with_stats,
                before_datetime=before_datetime
            )
            if self.feature_cache:
                self.feature_cache.set(home_shot_key, home_shot_intel)
        
        # Away team
        away_shot_key = CacheKey(away_team_id, "recent", prediction_timestamp, "shot_intelligence")
        if self.feature_cache:
            away_shot_intel = self.feature_cache.get(away_shot_key)
        else:
            away_shot_intel = None
        
        if away_shot_intel is None:
            away_shot_intel = shot_intel_calc.calculate_shot_metrics(
                team_id=away_team_id,
                matches_with_stats=matches_with_stats,
                before_datetime=before_datetime
            )
            if self.feature_cache:
                self.feature_cache.set(away_shot_key, away_shot_intel)
        
        self._extract_shot_intelligence(
            home_shot_intel, "home", prediction_timestamp, features, feature_metadata
        )
        self._extract_shot_intelligence(
            away_shot_intel, "away", prediction_timestamp, features, feature_metadata
        )
        
        if home_shot_intel.data_quality_score > 0:
            quality_scores.append(home_shot_intel.data_quality_score)
            quality_weights.append(0.075)
        if away_shot_intel.data_quality_score > 0:
            quality_scores.append(away_shot_intel.data_quality_score)
            quality_weights.append(0.075)
        
        # 7. Shot Production (Group 2) - WITH CACHING
        shot_prod_calc = ShotProductionCalculator(session=None, min_matches=5)
        
        # Build actual shot count lists from matches
        home_shot_counts = []
        away_shot_counts = []
        for mws in matches_with_stats:
            if mws.match.home_team_id == home_team_id and mws.home_statistics and mws.home_statistics.shots_total is not None:
                home_shot_counts.append(float(mws.home_statistics.shots_total))
            if mws.match.away_team_id == home_team_id and mws.away_statistics and mws.away_statistics.shots_total is not None:
                home_shot_counts.append(float(mws.away_statistics.shots_total))
            if mws.match.home_team_id == away_team_id and mws.home_statistics and mws.home_statistics.shots_total is not None:
                away_shot_counts.append(float(mws.home_statistics.shots_total))
            if mws.match.away_team_id == away_team_id and mws.away_statistics and mws.away_statistics.shots_total is not None:
                away_shot_counts.append(float(mws.away_statistics.shots_total))
        
        # Home team
        home_shot_prod_key = CacheKey(home_team_id, "recent", prediction_timestamp, "shot_production")
        if self.feature_cache:
            home_shot_prod = self.feature_cache.get(home_shot_prod_key)
        else:
            home_shot_prod = None
        
        if home_shot_prod is None:
            home_shot_prod = shot_prod_calc.calculate(
                team_id=home_team_id,
                shot_counts=home_shot_counts,
                before_datetime=before_datetime
            )
            if self.feature_cache:
                self.feature_cache.set(home_shot_prod_key, home_shot_prod)
        
        # Away team
        away_shot_prod_key = CacheKey(away_team_id, "recent", prediction_timestamp, "shot_production")
        if self.feature_cache:
            away_shot_prod = self.feature_cache.get(away_shot_prod_key)
        else:
            away_shot_prod = None
        
        if away_shot_prod is None:
            away_shot_prod = shot_prod_calc.calculate(
                team_id=away_team_id,
                shot_counts=away_shot_counts,
                before_datetime=before_datetime
            )
            if self.feature_cache:
                self.feature_cache.set(away_shot_prod_key, away_shot_prod)
        
        self._extract_shot_production(
            home_shot_prod, "home", prediction_timestamp, features, feature_metadata
        )
        self._extract_shot_production(
            away_shot_prod, "away", prediction_timestamp, features, feature_metadata
        )
        
        if home_shot_prod.data_quality_score > 0:
            quality_scores.append(home_shot_prod.data_quality_score)
            quality_weights.append(0.075)
        if away_shot_prod.data_quality_score > 0:
            quality_scores.append(away_shot_prod.data_quality_score)
            quality_weights.append(0.075)
        
        # 8. Common Opponent Intelligence (Group 3) - WITH CACHING
        # Note: Common opponent is pair-specific, cache key includes both teams
        common_opp_key = CacheKey(
            f"{home_team_id}__vs__{away_team_id}",
            "recent", 
            prediction_timestamp, 
            "common_opponent"
        )
        
        if self.feature_cache:
            common_opp_intel = self.feature_cache.get(common_opp_key)
        else:
            common_opp_intel = None
        
        if common_opp_intel is None:
            common_opp_calc = CommonOpponentCalculator(min_matches_per_opponent=2)
            common_opp_intel = common_opp_calc.calculate_common_opponent_intelligence(
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                home_matches_with_stats=matches_with_stats,  # Uses all matches, filters by team
                away_matches_with_stats=matches_with_stats,  # Uses all matches, filters by team
                before_datetime=before_datetime
            )
            if self.feature_cache:
                self.feature_cache.set(common_opp_key, common_opp_intel)
        
        self._extract_common_opponent(
            common_opp_intel, prediction_timestamp, features, feature_metadata
        )
        
        if common_opp_intel.data_quality_score > 0:
            quality_scores.append(common_opp_intel.data_quality_score)
            quality_weights.append(0.10)
        
        # Create derived features (differentials, shares, rates)
        self._create_derived_features(features, feature_metadata, prediction_timestamp)
        
        # Create interaction features if enabled
        interaction_feature_names = []
        if self.create_interactions:
            for interaction in self.interactions:
                value = interaction.compute(features)
                if value is not None:
                    features[interaction.name] = value
                    interaction_feature_names.append(interaction.name)
                    feature_metadata[interaction.name] = AdvancedFeatureMetadata(
                        feature_name=interaction.name,
                        source_module="feature_engineering",
                        source_timestamp=None,
                        prediction_timestamp=prediction_timestamp,
                        historical_window="recent",
                        availability=FeatureAvailability.INTERACTION,
                        data_quality_score=1.0,  # Interaction inherits from source features
                        transformation_applied=f"{interaction.operation}({interaction.feature_a}, {interaction.feature_b})"
                    )
        
        # Calculate overall data quality
        if quality_scores:
            total_weight = sum(quality_weights)
            if total_weight > 0:
                overall_quality = sum(q * w for q, w in zip(quality_scores, quality_weights)) / total_weight
            else:
                overall_quality = 0.0
        else:
            overall_quality = 0.0
        
        # Flag redundant features
        redundancy_flags = self.flag_redundant_features(features)
        
        # Build feature set
        feature_set = AdvancedFeatureSet(
            features=features,
            feature_metadata=feature_metadata,
            interaction_features=interaction_feature_names,
            redundancy_flags=redundancy_flags,
            overall_data_quality=overall_quality,
            feature_version=ADVANCED_FEATURE_VERSION,
            snapshot_timestamp=prediction_timestamp,
            temporal_validity_checked=False,
        )
        
        # Validate temporal validity
        feature_set.temporal_validity_checked = feature_set.validate_no_leakage()
        
        # Clear cache at end of prediction
        if self.feature_cache:
            self.feature_cache.clear()
        
        return feature_set
    
    def validate_no_leakage(
        self,
        advanced_feature_set: AdvancedFeatureSet,
        before_datetime: datetime
    ) -> bool:
        """Validate no temporal leakage in feature set.
        
        Args:
            advanced_feature_set: Feature set to validate
            before_datetime: Temporal cutoff
            
        Returns:
            True if no leakage detected
        """
        return advanced_feature_set.validate_no_leakage()
    
    def flag_redundant_features(
        self,
        features: Dict[str, Optional[float]]
    ) -> Dict[str, List[str]]:
        """Detect potential redundancy groups.
        
        Does NOT remove features, only flags them for model selection review.
        
        Args:
            features: Feature dictionary
            
        Returns:
            Dict mapping redundancy_group_name to list of feature_names
        """
        redundancy_groups = {}
        
        # xG redundancy (raw vs adjusted vs weighted)
        xg_features = [k for k in features.keys() if 'xg' in k.lower() and features[k] is not None]
        if len(xg_features) >= 2:
            redundancy_groups["xg_metrics"] = xg_features
        
        # Shot redundancy
        shot_features = [k for k in features.keys() if 'shot' in k.lower() and features[k] is not None]
        if len(shot_features) >= 2:
            redundancy_groups["shot_metrics"] = shot_features
        
        # Form redundancy
        form_features = [k for k in features.keys() if ('form' in k.lower() or 'points' in k.lower()) and features[k] is not None]
        if len(form_features) >= 2:
            redundancy_groups["form_metrics"] = form_features
        
        return redundancy_groups
    
    def populate_shot_intelligence(
        self,
        snapshot: 'MatchFeatureSnapshot',
        home_team_id: str,
        away_team_id: str,
        matches_with_stats: List[MatchWithStatistics],
        before_datetime: datetime
    ) -> None:
        """Populate shot intelligence fields in MatchFeatureSnapshot.
        
        Extends snapshot with home_shot_intelligence and away_shot_intelligence fields.
        Respects temporal validity: only uses data before before_datetime.
        
        Args:
            snapshot: MatchFeatureSnapshot to populate (modified in-place)
            home_team_id: Home team database ID
            away_team_id: Away team database ID
            matches_with_stats: Historical matches with statistics
            before_datetime: Temporal cutoff (strict <)
        """
        shot_intel_calc = ShotIntelligenceCalculator(session=None, min_matches=3)
        
        # Calculate home shot intelligence
        home_shot_intel = shot_intel_calc.calculate_shot_metrics(
            team_id=home_team_id,
            matches_with_stats=matches_with_stats,
            before_datetime=before_datetime
        )
        
        # Calculate away shot intelligence
        away_shot_intel = shot_intel_calc.calculate_shot_metrics(
            team_id=away_team_id,
            matches_with_stats=matches_with_stats,
            before_datetime=before_datetime
        )
        
        # Populate snapshot fields
        snapshot.home_shot_intelligence = home_shot_intel
        snapshot.away_shot_intelligence = away_shot_intel
    
    # Helper methods for feature extraction
    
    def _extract_team_metrics(
        self,
        metrics: AdvancedTeamMetrics,
        side: str,
        prediction_timestamp: datetime,
        features: Dict[str, Optional[float]],
        feature_metadata: Dict[str, AdvancedFeatureMetadata]
    ) -> None:
        """Extract features from AdvancedTeamMetrics."""
        prefix = f"{side}_"
        
        # xG metrics
        self._add_feature(
            features, feature_metadata,
            f"{prefix}xg_for_per_match", metrics.xg_for_per_match,
            "advanced_team_intelligence", metrics.provider_timestamp, prediction_timestamp,
            metrics.window_type, side, FeatureAvailability.RAW, metrics.data_quality_score
        )
        self._add_feature(
            features, feature_metadata,
            f"{prefix}xg_against_per_match", metrics.xg_against_per_match,
            "advanced_team_intelligence", metrics.provider_timestamp, prediction_timestamp,
            metrics.window_type, side, FeatureAvailability.RAW, metrics.data_quality_score
        )
        self._add_feature(
            features, feature_metadata,
            f"{prefix}xg_per_shot", metrics.xg_per_shot,
            "advanced_team_intelligence", metrics.provider_timestamp, prediction_timestamp,
            metrics.window_type, side, FeatureAvailability.DERIVED, metrics.data_quality_score, "xg/shot"
        )
        
        # Shot metrics
        self._add_feature(
            features, feature_metadata,
            f"{prefix}shots_per_match", metrics.shots_per_match,
            "advanced_team_intelligence", metrics.provider_timestamp, prediction_timestamp,
            metrics.window_type, side, FeatureAvailability.RAW, metrics.data_quality_score
        )
        self._add_feature(
            features, feature_metadata,
            f"{prefix}shots_on_target_per_match", metrics.shots_on_target_per_match,
            "advanced_team_intelligence", metrics.provider_timestamp, prediction_timestamp,
            metrics.window_type, side, FeatureAvailability.RAW, metrics.data_quality_score
        )
        
        # Possession
        self._add_feature(
            features, feature_metadata,
            f"{prefix}possession_avg", metrics.possession_avg,
            "advanced_team_intelligence", metrics.provider_timestamp, prediction_timestamp,
            metrics.window_type, side, FeatureAvailability.RAW, metrics.data_quality_score
        )
        
        # Home/away splits
        if side == "home":
            self._add_feature(
                features, feature_metadata,
                f"{prefix}xg_for_per_match_home", metrics.home_xg_for_per_match,
                "advanced_team_intelligence", metrics.provider_timestamp, prediction_timestamp,
                metrics.window_type, "home", FeatureAvailability.RAW, metrics.data_quality_score
            )
        else:
            self._add_feature(
                features, feature_metadata,
                f"{prefix}xg_for_per_match_away", metrics.away_xg_for_per_match,
                "advanced_team_intelligence", metrics.provider_timestamp, prediction_timestamp,
                metrics.window_type, "away", FeatureAvailability.RAW, metrics.data_quality_score
            )
    
    def _extract_opponent_adjusted(
        self,
        metrics: OpponentAdjustedMetrics,
        side: str,
        prediction_timestamp: datetime,
        features: Dict[str, Optional[float]],
        feature_metadata: Dict[str, AdvancedFeatureMetadata]
    ) -> None:
        """Extract features from OpponentAdjustedMetrics."""
        prefix = f"{side}_"
        
        self._add_feature(
            features, feature_metadata,
            f"{prefix}adj_xg_for", metrics.adj_xg_for,
            "opponent_adjustment", None, prediction_timestamp,
            "recent", side, FeatureAvailability.DERIVED, metrics.data_quality_score, "opponent_adjusted"
        )
        self._add_feature(
            features, feature_metadata,
            f"{prefix}adj_shots", metrics.adj_shots,
            "opponent_adjustment", None, prediction_timestamp,
            "recent", side, FeatureAvailability.DERIVED, metrics.data_quality_score, "opponent_adjusted"
        )
        self._add_feature(
            features, feature_metadata,
            f"{prefix}adj_xg_against", metrics.adj_xg_against,
            "opponent_adjustment", None, prediction_timestamp,
            "recent", side, FeatureAvailability.DERIVED, metrics.data_quality_score, "opponent_adjusted"
        )
        self._add_feature(
            features, feature_metadata,
            f"{prefix}adj_overall_strength", metrics.adj_overall_strength,
            "opponent_adjustment", None, prediction_timestamp,
            "recent", side, FeatureAvailability.DERIVED, metrics.data_quality_score, "opponent_adjusted"
        )
    
    def _extract_temporal(
        self,
        metrics: TemporalIntelligenceMetrics,
        side: str,
        prediction_timestamp: datetime,
        features: Dict[str, Optional[float]],
        feature_metadata: Dict[str, AdvancedFeatureMetadata]
    ) -> None:
        """Extract features from TemporalIntelligenceMetrics."""
        prefix = f"{side}_"
        
        # Calculate quality score from sample size (TemporalIntelligenceMetrics doesn't have data_quality_score)
        quality_score = min(1.0, metrics.sample_size / 10.0) if metrics.sample_size > 0 else 0.0
        
        self._add_feature(
            features, feature_metadata,
            f"{prefix}temporal_form_weighted", metrics.recent_form_weighted,
            "temporal_intelligence", None, prediction_timestamp,
            "recent", side, FeatureAvailability.DERIVED, quality_score, "temporal_weighted"
        )
        self._add_feature(
            features, feature_metadata,
            f"{prefix}temporal_xg_weighted", metrics.recent_xg_weighted,
            "temporal_intelligence", None, prediction_timestamp,
            "recent", side, FeatureAvailability.DERIVED, quality_score, "temporal_weighted"
        )
        self._add_feature(
            features, feature_metadata,
            f"{prefix}form_acceleration", metrics.form_acceleration,
            "temporal_intelligence", None, prediction_timestamp,
            "recent", side, FeatureAvailability.DERIVED, quality_score, "trend_detection"
        )
        self._add_feature(
            features, feature_metadata,
            f"{prefix}post_regime_form", metrics.post_regime_form,
            "temporal_intelligence", None, prediction_timestamp,
            "post_regime", side, FeatureAvailability.DERIVED, quality_score, "regime_detection"
        )
    
    def _extract_lineup(
        self,
        estimate: LineupImpactEstimate,
        side: str,
        prediction_timestamp: datetime,
        features: Dict[str, Optional[float]],
        feature_metadata: Dict[str, AdvancedFeatureMetadata]
    ) -> None:
        """Extract features from LineupImpactEstimate."""
        prefix = f"{side}_"
        
        self._add_feature(
            features, feature_metadata,
            f"{prefix}lineup_attacking_adjustment", estimate.attacking_adjustment,
            "lineup_intelligence", None, prediction_timestamp,
            "recent", side, FeatureAvailability.DERIVED, estimate.data_quality, "with_without"
        )
        self._add_feature(
            features, feature_metadata,
            f"{prefix}lineup_defensive_adjustment", estimate.defensive_adjustment,
            "lineup_intelligence", None, prediction_timestamp,
            "recent", side, FeatureAvailability.DERIVED, estimate.data_quality, "with_without"
        )
        self._add_feature(
            features, feature_metadata,
            f"{prefix}lineup_shot_adjustment", estimate.shot_adjustment,
            "lineup_intelligence", None, prediction_timestamp,
            "recent", side, FeatureAvailability.DERIVED, estimate.data_quality, "with_without"
        )
        self._add_feature(
            features, feature_metadata,
            f"{prefix}lineup_quality", estimate.lineup_quality,
            "lineup_intelligence", None, prediction_timestamp,
            "recent", side, FeatureAvailability.DERIVED, estimate.data_quality, "statistical"
        )
        self._add_feature(
            features, feature_metadata,
            f"{prefix}lineup_uncertainty", estimate.uncertainty,
            "lineup_intelligence", None, prediction_timestamp,
            "recent", side, FeatureAvailability.RAW, estimate.data_quality
        )
    
    def _extract_tactical(
        self,
        matchup: TacticalMatchup,
        prediction_timestamp: datetime,
        features: Dict[str, Optional[float]],
        feature_metadata: Dict[str, AdvancedFeatureMetadata]
    ) -> None:
        """Extract features from TacticalMatchup."""
        self._add_feature(
            features, feature_metadata,
            "tactical_possession_advantage", matchup.possession_advantage,
            "tactical_matchup", None, prediction_timestamp,
            "recent", "all", FeatureAvailability.DERIVED, matchup.data_quality_score, "matchup_differential"
        )
        self._add_feature(
            features, feature_metadata,
            "tactical_shot_volume_advantage", matchup.shot_volume_advantage,
            "tactical_matchup", None, prediction_timestamp,
            "recent", "all", FeatureAvailability.DERIVED, matchup.data_quality_score, "matchup_differential"
        )
        self._add_feature(
            features, feature_metadata,
            "tactical_shot_quality_advantage", matchup.shot_quality_advantage,
            "tactical_matchup", None, prediction_timestamp,
            "recent", "all", FeatureAvailability.DERIVED, matchup.data_quality_score, "matchup_differential"
        )
        self._add_feature(
            features, feature_metadata,
            "tactical_defensive_intensity_advantage", matchup.defensive_intensity_advantage,
            "tactical_matchup", None, prediction_timestamp,
            "recent", "all", FeatureAvailability.DERIVED, matchup.data_quality_score, "matchup_differential"
        )
        self._add_feature(
            features, feature_metadata,
            "tactical_overall_matchup_advantage", matchup.overall_matchup_advantage,
            "tactical_matchup", None, prediction_timestamp,
            "recent", "all", FeatureAvailability.DERIVED, matchup.data_quality_score, "weighted_matchup"
        )
    
    def _extract_shot_intelligence(
        self,
        metrics: ShotIntelligenceMetrics,
        side: str,
        prediction_timestamp: datetime,
        features: Dict[str, Optional[float]],
        feature_metadata: Dict[str, AdvancedFeatureMetadata]
    ) -> None:
        """Extract features from ShotIntelligenceMetrics."""
        prefix = f"{side}_"
        
        self._add_feature(
            features, feature_metadata,
            f"{prefix}shots_per_match_weighted", metrics.shots_per_match_weighted,
            "shot_intelligence", metrics.provider_timestamp, prediction_timestamp,
            metrics.window_type, side, FeatureAvailability.DERIVED, metrics.data_quality_score, "recency_weighted"
        )
        self._add_feature(
            features, feature_metadata,
            f"{prefix}sot_per_match_weighted", metrics.sot_per_match_weighted,
            "shot_intelligence", metrics.provider_timestamp, prediction_timestamp,
            metrics.window_type, side, FeatureAvailability.DERIVED, metrics.data_quality_score, "recency_weighted"
        )
        self._add_feature(
            features, feature_metadata,
            f"{prefix}xg_per_match_weighted", metrics.xg_per_match_weighted,
            "shot_intelligence", metrics.provider_timestamp, prediction_timestamp,
            metrics.window_type, side, FeatureAvailability.DERIVED, metrics.data_quality_score, "recency_weighted"
        )
        self._add_feature(
            features, feature_metadata,
            f"{prefix}shot_share", metrics.shot_share,
            "shot_intelligence", metrics.provider_timestamp, prediction_timestamp,
            metrics.window_type, side, FeatureAvailability.DERIVED, metrics.data_quality_score, "share"
        )
        self._add_feature(
            features, feature_metadata,
            f"{prefix}shot_on_target_rate", metrics.shot_on_target_rate,
            "shot_intelligence", metrics.provider_timestamp, prediction_timestamp,
            metrics.window_type, side, FeatureAvailability.DERIVED, metrics.data_quality_score, "rate"
        )
    
    def _extract_shot_production(
        self,
        prod: ShotProduction,
        side: str,
        prediction_timestamp: datetime,
        features: Dict[str, Optional[float]],
        feature_metadata: Dict[str, AdvancedFeatureMetadata]
    ) -> None:
        """Extract features from ShotProduction."""
        prefix = f"{side}_"
        
        self._add_feature(
            features, feature_metadata,
            f"{prefix}expected_shots_mean", prod.expected_shots_mean,
            "shot_production", None, prediction_timestamp,
            "recent", side, FeatureAvailability.DERIVED, prod.data_quality_score, "distribution_fit"
        )
        self._add_feature(
            features, feature_metadata,
            f"{prefix}over_12_shots_prob", prod.over_12_shots_prob,
            "shot_production", None, prediction_timestamp,
            "recent", side, FeatureAvailability.DERIVED, prod.data_quality_score, "probability"
        )
        self._add_feature(
            features, feature_metadata,
            f"{prefix}over_15_shots_prob", prod.over_15_shots_prob,
            "shot_production", None, prediction_timestamp,
            "recent", side, FeatureAvailability.DERIVED, prod.data_quality_score, "probability"
        )
        self._add_feature(
            features, feature_metadata,
            f"{prefix}expected_sot_mean", prod.expected_sot_mean,
            "shot_production", None, prediction_timestamp,
            "recent", side, FeatureAvailability.DERIVED, prod.data_quality_score, "distribution_fit"
        )
        self._add_feature(
            features, feature_metadata,
            f"{prefix}over_4_sot_prob", prod.over_4_sot_prob,
            "shot_production", None, prediction_timestamp,
            "recent", side, FeatureAvailability.DERIVED, prod.data_quality_score, "probability"
        )
    
    def _extract_common_opponent(
        self,
        intel: CommonOpponentIntelligence,
        prediction_timestamp: datetime,
        features: Dict[str, Optional[float]],
        feature_metadata: Dict[str, AdvancedFeatureMetadata]
    ) -> None:
        """Extract features from CommonOpponentIntelligence."""
        self._add_feature(
            features, feature_metadata,
            "common_opp_points_differential", intel.points_differential,
            "common_opponent_intelligence", None, prediction_timestamp,
            "recent", "all", FeatureAvailability.DERIVED, intel.data_quality_score, "differential"
        )
        self._add_feature(
            features, feature_metadata,
            "common_opp_xg_differential", intel.xg_differential,
            "common_opponent_intelligence", None, prediction_timestamp,
            "recent", "all", FeatureAvailability.DERIVED, intel.data_quality_score, "differential"
        )
        self._add_feature(
            features, feature_metadata,
            "common_opp_xga_differential", intel.xga_differential,
            "common_opponent_intelligence", None, prediction_timestamp,
            "recent", "all", FeatureAvailability.DERIVED, intel.data_quality_score, "differential"
        )
        self._add_feature(
            features, feature_metadata,
            "common_opp_comparison_confidence", intel.comparison_confidence,
            "common_opponent_intelligence", None, prediction_timestamp,
            "recent", "all", FeatureAvailability.RAW, intel.data_quality_score
        )
        
        # Common opponent strength index (confidence-weighted)
        if intel.points_differential is not None and intel.comparison_confidence is not None:
            if intel.n_common_opponents >= 3 and intel.comparison_confidence > 0.3:
                strength_index = intel.points_differential * intel.comparison_confidence
                self._add_feature(
                    features, feature_metadata,
                    "common_opp_strength_index", strength_index,
                    "common_opponent_intelligence", None, prediction_timestamp,
                    "recent", "all", FeatureAvailability.DERIVED, intel.data_quality_score, "confidence_weighted"
                )
    
    def _create_derived_features(
        self,
        features: Dict[str, Optional[float]],
        feature_metadata: Dict[str, AdvancedFeatureMetadata],
        prediction_timestamp: datetime
    ) -> None:
        """Create derived features (differentials, shares, rates)."""
        
        # Shot differential
        if features.get("home_shots_per_match") is not None and features.get("away_shots_per_match") is not None:
            shot_diff = features["home_shots_per_match"] - features["away_shots_per_match"]
            self._add_feature(
                features, feature_metadata,
                "shot_differential", shot_diff,
                "feature_engineering", None, prediction_timestamp,
                "recent", "all", FeatureAvailability.DERIVED, 1.0, "differential"
            )
        
        # xG differential
        if features.get("home_xg_for_per_match") is not None and features.get("away_xg_for_per_match") is not None:
            xg_diff = features["home_xg_for_per_match"] - features["away_xg_for_per_match"]
            self._add_feature(
                features, feature_metadata,
                "xg_differential", xg_diff,
                "feature_engineering", None, prediction_timestamp,
                "recent", "all", FeatureAvailability.DERIVED, 1.0, "differential"
            )
        
        # xGA differential
        if features.get("home_xg_against_per_match") is not None and features.get("away_xg_against_per_match") is not None:
            xga_diff = features["home_xg_against_per_match"] - features["away_xg_against_per_match"]
            self._add_feature(
                features, feature_metadata,
                "xga_differential", xga_diff,
                "feature_engineering", None, prediction_timestamp,
                "recent", "all", FeatureAvailability.DERIVED, 1.0, "differential"
            )
        
        # Temporal form differential
        if features.get("home_temporal_form_weighted") is not None and features.get("away_temporal_form_weighted") is not None:
            form_diff = features["home_temporal_form_weighted"] - features["away_temporal_form_weighted"]
            self._add_feature(
                features, feature_metadata,
                "temporal_form_differential", form_diff,
                "feature_engineering", None, prediction_timestamp,
                "recent", "all", FeatureAvailability.DERIVED, 1.0, "differential"
            )
        
        # Possession differential
        if features.get("home_possession_avg") is not None and features.get("away_possession_avg") is not None:
            poss_diff = features["home_possession_avg"] - features["away_possession_avg"]
            self._add_feature(
                features, feature_metadata,
                "possession_differential", poss_diff,
                "feature_engineering", None, prediction_timestamp,
                "recent", "all", FeatureAvailability.DERIVED, 1.0, "differential"
            )
        
        # SOT share home
        home_sot = features.get("home_shots_on_target_per_match")
        away_sot = features.get("away_shots_on_target_per_match")
        if home_sot is not None and away_sot is not None:
            total_sot = home_sot + away_sot
            if total_sot > 0:
                sot_share = home_sot / total_sot
                self._add_feature(
                    features, feature_metadata,
                    "shots_on_target_share_home", sot_share,
                    "feature_engineering", None, prediction_timestamp,
                    "recent", "home", FeatureAvailability.DERIVED, 1.0, "share"
                )
        
        # xG share home
        home_xg = features.get("home_xg_for_per_match")
        away_xg = features.get("away_xg_for_per_match")
        if home_xg is not None and away_xg is not None:
            total_xg = home_xg + away_xg
            if total_xg > 0:
                xg_share = home_xg / total_xg
                self._add_feature(
                    features, feature_metadata,
                    "xg_share_home", xg_share,
                    "feature_engineering", None, prediction_timestamp,
                    "recent", "home", FeatureAvailability.DERIVED, 1.0, "share"
                )
    
    def _add_feature(
        self,
        features: Dict[str, Optional[float]],
        feature_metadata: Dict[str, AdvancedFeatureMetadata],
        name: str,
        value: Optional[float],
        source_module: str,
        source_timestamp: Optional[datetime],
        prediction_timestamp: datetime,
        historical_window: str,
        home_away_context: Optional[str],
        availability: FeatureAvailability,
        data_quality_score: float,
        transformation: Optional[str] = None
    ) -> None:
        """Add feature with metadata."""
        features[name] = value
        feature_metadata[name] = AdvancedFeatureMetadata(
            feature_name=name,
            source_module=source_module,
            source_timestamp=source_timestamp,
            prediction_timestamp=prediction_timestamp,
            historical_window=historical_window,
            home_away_context=home_away_context,
            availability=availability if value is not None else FeatureAvailability.UNAVAILABLE,
            data_quality_score=data_quality_score if value is not None else 0.0,
            transformation_applied=transformation
        )
