"""Tactical matchup intelligence feature calculations.

This module implements tactical profile extraction and matchup advantage calculation
using ONLY AVAILABLE metrics from TeamMatchStatistic.

AVAILABLE metrics from TeamMatchStatistic:
- possession_percentage
- shots_total, shots_on_target
- passes_completed, passes_attempted
- tackles, interceptions, clearances
- corners
- fouls_committed

UNAVAILABLE metrics (remain None until provider integration):
- PPDA (requires defensive action tracking per possession)
- Field Tilt (requires territorial zone data)
- Progressive passes (requires pass progression tracking)
- Box entries (requires zone-entry tracking)
- High turnovers (requires possession-recovery zone tracking)

Data flow:
1. Extract tactical profile from historical TeamMatchStatistic data
2. Calculate AVAILABLE metrics only (possession, shots, passes, defensive actions)
3. Leave UNAVAILABLE metrics as None
4. Calculate matchup advantage as normalized differentials between team profiles
5. Return bounded advantage scores [-1, 1] with provenance
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
import math

from app.features.advanced_team_intelligence import MatchWithStatistics
from app.domain.enums import MatchStatus


@dataclass
class TacticalProfile:
    """Team tactical profile from available TeamMatchStatistic metrics.
    
    Contains ONLY metrics available from current data providers.
    UNAVAILABLE metrics remain None (never fabricated).
    """
    team_id: str
    
    # Possession & control (AVAILABLE)
    possession_avg: Optional[float] = None  # Average possession %
    pass_completion_rate: Optional[float] = None  # passes_completed / passes_attempted
    
    # Attacking intensity (AVAILABLE)
    shots_per_match: Optional[float] = None
    shots_on_target_per_match: Optional[float] = None
    shot_accuracy: Optional[float] = None  # SOT / total shots
    corners_per_match: Optional[float] = None
    
    # Defensive activity (AVAILABLE)
    tackles_per_match: Optional[float] = None
    interceptions_per_match: Optional[float] = None
    clearances_per_match: Optional[float] = None
    fouls_per_match: Optional[float] = None
    defensive_actions_per_match: Optional[float] = None  # tackles + interceptions
    
    # UNAVAILABLE FIELDS (explicitly None until provider integration)
    ppda: Optional[float] = None  # UNAVAILABLE - no defensive action tracking per possession
    field_tilt: Optional[float] = None  # UNAVAILABLE - no territorial zone data
    progressive_passes_per_match: Optional[float] = None  # UNAVAILABLE - no progression tracking
    progressive_carries_per_match: Optional[float] = None  # UNAVAILABLE - no movement tracking
    box_entries_per_match: Optional[float] = None  # UNAVAILABLE - no zone entry tracking
    high_turnovers_per_match: Optional[float] = None  # UNAVAILABLE - no recovery zone tracking
    
    # Provenance
    sample_size: int = 0
    matches_with_possession_data: int = 0
    matches_with_shot_data: int = 0
    matches_with_pass_data: int = 0
    matches_with_defensive_data: int = 0
    data_quality_score: float = 0.0


@dataclass
class TacticalMatchup:
    """Tactical matchup advantage between home and away teams.
    
    All advantages bounded [-1.0, 1.0]:
    - Positive = advantage for home team
    - Negative = advantage for away team
    - 0.0 = neutral matchup
    - None = cannot calculate (insufficient data)
    """
    home_team_id: str
    away_team_id: str
    
    # Matchup advantages (bounded -1 to +1)
    possession_advantage: Optional[float] = None  # Home possession style vs Away
    shot_volume_advantage: Optional[float] = None  # Home shot creation vs Away
    shot_quality_advantage: Optional[float] = None  # Home shot accuracy vs Away
    defensive_intensity_advantage: Optional[float] = None  # Home defensive actions vs Away
    
    # Overall matchup score (weighted combination of available advantages)
    overall_matchup_advantage: Optional[float] = None  # -1 to +1, 0 = neutral
    
    # UNAVAILABLE advantages (remain None)
    pressing_advantage: Optional[float] = None  # UNAVAILABLE - requires PPDA
    buildup_advantage: Optional[float] = None  # UNAVAILABLE - requires progressive passes
    territorial_advantage: Optional[float] = None  # UNAVAILABLE - requires Field Tilt
    transition_advantage: Optional[float] = None  # UNAVAILABLE - requires turnover zone data
    
    # Metadata
    available_metrics: List[str] = field(default_factory=list)  # Which metrics were used
    unavailable_metrics: List[str] = field(default_factory=list)  # Which metrics are UNAVAILABLE
    data_quality_score: float = 0.0
    home_sample_size: int = 0
    away_sample_size: int = 0


class TacticalMatchupCalculator:
    """Calculate tactical matchup advantages using AVAILABLE metrics only.
    
    Reuses MatchWithStatistics from Group 1 (advanced_team_intelligence.py).
    Calculates advantage scores as normalized differentials bounded to [-1, 1].
    """
    
    def __init__(self, session, min_matches: int = 5):
        """Initialize calculator with minimum sample size requirement.
        
        Args:
            session: Database session (for future repository access)
            min_matches: Minimum matches required for reliable tactical profile
        """
        self.session = session
        self.min_matches = min_matches
    
    def calculate_tactical_profile(
        self,
        team_id: str,
        matches_with_stats: List[MatchWithStatistics],
        before_datetime: Optional[datetime] = None
    ) -> TacticalProfile:
        """Extract tactical profile from historical matches.
        
        PATTERN: Same structure as AdvancedTeamIntelligenceCalculator.
        AVAILABLE METRICS ONLY: No PPDA, Field Tilt, progressive passes, box entries.
        TEMPORAL VALIDITY: Only uses matches strictly before before_datetime.
        
        Args:
            team_id: Team database ID
            matches_with_stats: List of MatchWithStatistics (Match + home/away stats)
            before_datetime: Only use matches before this timestamp (temporal validity)
            
        Returns:
            TacticalProfile with AVAILABLE metrics calculated, UNAVAILABLE as None
        """
        # Filter to finished matches only
        finished_matches = [
            mws for mws in matches_with_stats
            if mws.is_finished()
        ]
        
        # Filter to matches strictly before before_datetime (temporal validity)
        if before_datetime is not None:
            finished_matches = [
                mws for mws in finished_matches
                if mws.match.scheduled_at < before_datetime  # STRICT < to prevent leakage
            ]
        
        # Check if we have sufficient data
        if len(finished_matches) < self.min_matches:
            return TacticalProfile(
                team_id=team_id,
                sample_size=len(finished_matches),
                data_quality_score=0.0,
            )
        
        # Accumulators for AVAILABLE metrics
        possession_sum = 0.0
        possession_count = 0
        
        shots_sum = 0.0
        sot_sum = 0.0
        shot_count = 0
        
        passes_completed_sum = 0.0
        passes_attempted_sum = 0.0
        pass_count = 0
        
        tackles_sum = 0.0
        interceptions_sum = 0.0
        clearances_sum = 0.0
        fouls_sum = 0.0
        defensive_count = 0
        
        corners_sum = 0.0
        corners_count = 0
        
        # Extract metrics from matches
        for mws in finished_matches:
            stats = mws.get_team_statistics(team_id)
            if stats is None:
                continue
            
            # Possession
            if stats.possession_percentage is not None:
                possession_sum += stats.possession_percentage
                possession_count += 1
            
            # Shots
            if stats.shots_total is not None:
                shots_sum += stats.shots_total
                shot_count += 1
            if stats.shots_on_target is not None:
                sot_sum += stats.shots_on_target
            
            # Passes
            if stats.passes_completed is not None and stats.passes_attempted is not None:
                passes_completed_sum += stats.passes_completed
                passes_attempted_sum += stats.passes_attempted
                pass_count += 1
            
            # Defensive actions
            if stats.tackles is not None:
                tackles_sum += stats.tackles
                defensive_count += 1
            if stats.interceptions is not None:
                interceptions_sum += stats.interceptions
            if stats.clearances is not None:
                clearances_sum += stats.clearances
            if stats.fouls_committed is not None:
                fouls_sum += stats.fouls_committed
            
            # Corners
            if stats.corners is not None:
                corners_sum += stats.corners
                corners_count += 1
        
        # Calculate averages
        possession_avg = possession_sum / possession_count if possession_count > 0 else None
        
        shots_per_match = shots_sum / shot_count if shot_count > 0 else None
        sot_per_match = sot_sum / shot_count if shot_count > 0 else None
        shot_accuracy = (sot_sum / shots_sum) if shots_sum > 0 else None
        
        pass_completion_rate = (passes_completed_sum / passes_attempted_sum) if passes_attempted_sum > 0 else None
        
        tackles_per_match = tackles_sum / defensive_count if defensive_count > 0 else None
        interceptions_per_match = interceptions_sum / defensive_count if defensive_count > 0 else None
        clearances_per_match = clearances_sum / defensive_count if defensive_count > 0 else None
        fouls_per_match = fouls_sum / defensive_count if defensive_count > 0 else None
        defensive_actions_per_match = (tackles_sum + interceptions_sum) / defensive_count if defensive_count > 0 else None
        
        corners_per_match = corners_sum / corners_count if corners_count > 0 else None
        
        # Calculate data quality score
        data_quality = self._calculate_data_quality(
            possession_count, shot_count, pass_count, defensive_count, len(finished_matches)
        )
        
        return TacticalProfile(
            team_id=team_id,
            possession_avg=possession_avg,
            pass_completion_rate=pass_completion_rate,
            shots_per_match=shots_per_match,
            shots_on_target_per_match=sot_per_match,
            shot_accuracy=shot_accuracy,
            corners_per_match=corners_per_match,
            tackles_per_match=tackles_per_match,
            interceptions_per_match=interceptions_per_match,
            clearances_per_match=clearances_per_match,
            fouls_per_match=fouls_per_match,
            defensive_actions_per_match=defensive_actions_per_match,
            # UNAVAILABLE metrics remain None
            ppda=None,
            field_tilt=None,
            progressive_passes_per_match=None,
            progressive_carries_per_match=None,
            box_entries_per_match=None,
            high_turnovers_per_match=None,
            # Provenance
            sample_size=len(finished_matches),
            matches_with_possession_data=possession_count,
            matches_with_shot_data=shot_count,
            matches_with_pass_data=pass_count,
            matches_with_defensive_data=defensive_count,
            data_quality_score=data_quality,
        )
    
    def calculate_matchup(
        self,
        home_profile: TacticalProfile,
        away_profile: TacticalProfile
    ) -> TacticalMatchup:
        """Calculate tactical matchup advantage between two teams.
        
        All advantages bounded [-1.0, 1.0]:
        - Uses tanh normalization for bounded output
        - Positive = home advantage, Negative = away advantage
        - If either team's metric is None → advantage = None
        - overall_matchup_advantage = weighted mean of non-None advantages
        
        Args:
            home_profile: Home team tactical profile
            away_profile: Away team tactical profile
            
        Returns:
            TacticalMatchup with bounded advantage scores
        """
        available_metrics = []
        unavailable_metrics = ["ppda", "field_tilt", "progressive_passes", "box_entries", "high_turnovers"]
        
        # Calculate possession advantage
        possession_advantage = self._calculate_advantage(
            home_profile.possession_avg,
            away_profile.possession_avg,
            scale=20.0  # 20 percentage points difference → ±0.76
        )
        if possession_advantage is not None:
            available_metrics.append("possession")
        
        # Calculate shot volume advantage
        shot_volume_advantage = self._calculate_advantage(
            home_profile.shots_per_match,
            away_profile.shots_per_match,
            scale=10.0  # 10 shots difference → ±0.76
        )
        if shot_volume_advantage is not None:
            available_metrics.append("shot_volume")
        
        # Calculate shot quality advantage
        shot_quality_advantage = self._calculate_advantage(
            home_profile.shot_accuracy,
            away_profile.shot_accuracy,
            scale=0.3  # 0.3 (30 percentage points) difference → ±0.76
        )
        if shot_quality_advantage is not None:
            available_metrics.append("shot_quality")
        
        # Calculate defensive intensity advantage
        defensive_intensity_advantage = self._calculate_advantage(
            home_profile.defensive_actions_per_match,
            away_profile.defensive_actions_per_match,
            scale=15.0  # 15 defensive actions difference → ±0.76
        )
        if defensive_intensity_advantage is not None:
            available_metrics.append("defensive_intensity")
        
        # Calculate overall matchup advantage (weighted mean of available)
        advantages = [
            (possession_advantage, 0.25),
            (shot_volume_advantage, 0.35),
            (shot_quality_advantage, 0.25),
            (defensive_intensity_advantage, 0.15),
        ]
        
        overall_matchup_advantage = self._weighted_mean_bounded(advantages)
        
        # Calculate data quality
        data_quality = (home_profile.data_quality_score + away_profile.data_quality_score) / 2.0
        
        return TacticalMatchup(
            home_team_id=home_profile.team_id,
            away_team_id=away_profile.team_id,
            possession_advantage=possession_advantage,
            shot_volume_advantage=shot_volume_advantage,
            shot_quality_advantage=shot_quality_advantage,
            defensive_intensity_advantage=defensive_intensity_advantage,
            overall_matchup_advantage=overall_matchup_advantage,
            # UNAVAILABLE advantages remain None
            pressing_advantage=None,
            buildup_advantage=None,
            territorial_advantage=None,
            transition_advantage=None,
            # Metadata
            available_metrics=available_metrics,
            unavailable_metrics=unavailable_metrics,
            data_quality_score=data_quality,
            home_sample_size=home_profile.sample_size,
            away_sample_size=away_profile.sample_size,
        )
    
    def _calculate_advantage(
        self,
        home_value: Optional[float],
        away_value: Optional[float],
        scale: float
    ) -> Optional[float]:
        """Calculate normalized advantage score using tanh.
        
        Advantage = tanh((home - away) / scale)
        Result bounded to [-1.0, 1.0].
        
        Args:
            home_value: Home team metric value
            away_value: Away team metric value
            scale: Scale factor for normalization
            
        Returns:
            Bounded advantage score or None if either value is None
        """
        if home_value is None or away_value is None:
            return None
        
        differential = home_value - away_value
        advantage = math.tanh(differential / scale)
        
        # Ensure bounded to [-1, 1] (tanh guarantees this, but explicit for safety)
        return max(-1.0, min(1.0, advantage))
    
    def _weighted_mean_bounded(
        self,
        advantages_with_weights: List[tuple[Optional[float], float]]
    ) -> Optional[float]:
        """Calculate weighted mean of advantage scores.
        
        Only includes non-None advantages in calculation.
        Renormalizes weights to sum to 1.0.
        
        Args:
            advantages_with_weights: List of (advantage, weight) tuples
            
        Returns:
            Weighted mean or None if no advantages available
        """
        valid_advantages = [(adv, w) for adv, w in advantages_with_weights if adv is not None]
        
        if not valid_advantages:
            return None
        
        total_weight = sum(w for _, w in valid_advantages)
        if total_weight == 0:
            return None
        
        weighted_sum = sum(adv * w for adv, w in valid_advantages)
        return weighted_sum / total_weight
    
    def _calculate_data_quality(
        self,
        possession_count: int,
        shot_count: int,
        pass_count: int,
        defensive_count: int,
        total_matches: int
    ) -> float:
        """Calculate data quality score based on data completeness.
        
        Returns:
            Data quality score in [0.0, 1.0]
        """
        if total_matches == 0:
            return 0.0
        
        # Calculate coverage for each data type
        possession_coverage = possession_count / total_matches
        shot_coverage = shot_count / total_matches
        pass_coverage = pass_count / total_matches
        defensive_coverage = defensive_count / total_matches
        
        # Weighted average (shots and possession more important)
        quality = (
            possession_coverage * 0.3 +
            shot_coverage * 0.4 +
            pass_coverage * 0.15 +
            defensive_coverage * 0.15
        )
        
        return min(1.0, quality)
