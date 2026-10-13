"""Feature engineering module.

This module provides deterministic feature engineering for football match prediction.
All features are calculated from historical data only, with proper data leakage prevention.
"""

from app.features.base import (
    FeatureCalculator,
    MatchContext,
    TeamHistoricalData,
)
from app.features.team_strength import TeamStrengthCalculator
from app.features.form import FormCalculator
from app.features.match_features import MatchFeatureExtractor

# Database-backed feature extraction (production)
from app.features.database_extractor import DatabaseFeatureExtractor
from app.features.team_form import TeamFormFeatureCalculator, TeamFormFeatures
from app.features.attack_defence import AttackDefenceFeatureCalculator, AttackDefenceFeatures
from app.features.data_quality import DataQualityFeatureCalculator, DataQualityFeatures
from app.features.aggregator import FeatureAggregator, FeatureSet
from app.features.advanced_team_intelligence import (
    MatchWithStatistics,
    AdvancedTeamMetrics,
    AdvancedTeamIntelligenceCalculator,
)
from app.features.opponent_adjustment import (
    OpponentStrengthAtTime,
    OpponentAdjustedMetrics,
    OpponentAdjustmentCalculator,
)
from app.features.temporal_intelligence import (
    TemporalWeighting,
    RegimeChange,
    TemporalIntelligenceMetrics,
    TemporalIntelligenceCalculator,
)
from app.features.lineup_intelligence import (
    PlayerAvailabilityStatus,
    PlayerAvailability,
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
from app.features.common_opponent_intelligence import (
    CommonOpponentMatch,
    CommonOpponentEvidence,
    CommonOpponentIntelligence,
    CommonOpponentCalculator,
)
from app.features.advanced_feature_engineering import (
    FeatureAvailability,
    AdvancedFeatureMetadata,
    InteractionFeature,
    AdvancedFeatureSet,
    AdvancedFeatureEngineer,
    ADVANCED_FEATURE_VERSION,
    CANDIDATE_INTERACTIONS,
)

__all__ = [
    # Base (existing)
    "FeatureCalculator",
    "MatchContext",
    "TeamHistoricalData",
    "TeamStrengthCalculator",
    "FormCalculator",
    "MatchFeatureExtractor",
    # Database-backed (new)
    "DatabaseFeatureExtractor",
    "TeamFormFeatureCalculator",
    "TeamFormFeatures",
    "AttackDefenceFeatureCalculator",
    "AttackDefenceFeatures",
    "DataQualityFeatureCalculator",
    "DataQualityFeatures",
    "FeatureAggregator",
    "FeatureSet",
    # Advanced Team Intelligence (Phase 10)
    "MatchWithStatistics",
    "AdvancedTeamMetrics",
    "AdvancedTeamIntelligenceCalculator",
    # Opponent Adjustment (Phase 10 Group 1)
    "OpponentStrengthAtTime",
    "OpponentAdjustedMetrics",
    "OpponentAdjustmentCalculator",
    # Temporal Intelligence (Phase 10 Group 1)
    "TemporalWeighting",
    "RegimeChange",
    "TemporalIntelligenceMetrics",
    "TemporalIntelligenceCalculator",
    # Lineup Intelligence (Phase 10 Group 2)
    "PlayerAvailabilityStatus",
    "PlayerAvailability",
    "LineupImpactEstimate",
    "LineupIntelligenceCalculator",
    # Tactical Matchup (Phase 10 Group 2)
    "TacticalProfile",
    "TacticalMatchup",
    "TacticalMatchupCalculator",
    # Shot Intelligence (Phase 10 Group 2)
    "ShotIntelligenceMetrics",
    "ShotIntelligenceCalculator",
    # Shot Production (Phase 10 Group 2)
    "ShotProduction",
    "ShotProductionCalculator",
    # Common Opponent Intelligence (Phase 10 Group 3)
    "CommonOpponentMatch",
    "CommonOpponentEvidence",
    "CommonOpponentIntelligence",
    "CommonOpponentCalculator",
    # Advanced Feature Engineering (Phase 10 Group 4)
    "FeatureAvailability",
    "AdvancedFeatureMetadata",
    "InteractionFeature",
    "AdvancedFeatureSet",
    "AdvancedFeatureEngineer",
    "ADVANCED_FEATURE_VERSION",
    "CANDIDATE_INTERACTIONS",
]
