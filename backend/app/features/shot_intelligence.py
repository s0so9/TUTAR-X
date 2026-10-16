"""Shot intelligence feature calculations.

This module extracts shot volume and quality metrics from TeamMatchStatistic data.
Provides foundation for shot production probability modeling (shot_production.py).

AVAILABLE metrics from TeamMatchStatistic:
- shots_total, shots_on_target, shots_off_target, shots_blocked
- xg, xg_against (from providers with xG data)
- possession_percentage (for context)

UNAVAILABLE metrics (remain None until provider integration):
- shots_inside_box (requires shot coordinates)
- box_shot_percentage (requires shot coordinates)
- big_chances (requires provider classification)
- non_penalty_xg (requires xG event-type separation)

Data flow:
1. Extract shot metrics from historical TeamMatchStatistic data
2. Calculate per-match averages for shots, SOT, xG
3. Separate home/away venue performance when sample sufficient
4. Calculate shot quality metrics (xG/shot, SOT rate)
5. Calculate shot dominance (shot share)
6. Apply recency weighting for recent form
7. Return shot intelligence with provenance
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

from app.features.advanced_team_intelligence import MatchWithStatistics
from app.domain.enums import MatchStatus


@dataclass
class ShotIntelligenceMetrics:
    """Shot intelligence metrics extracted from TeamMatchStatistic.
    
    AVAILABLE fields from current TeamMatchStatistic:
    - shots_total, shots_on_target, shots_off_target, shots_blocked
    - xg, xg_against
    - possession_percentage
    
    UNAVAILABLE fields (remain None until provider integration):
    - shots_inside_box (requires shot coordinates)
    - box_shot_percentage (requires shot coordinates)
    - big_chances (requires provider classification)
    - non_penalty_xg (requires xG event-type separation)
    """
    team_id: str
    
    # Shot volume (AVAILABLE)
    shots_total_per_match: Optional[float] = None
    shots_on_target_per_match: Optional[float] = None
    shots_off_target_per_match: Optional[float] = None
    shots_blocked_per_match: Optional[float] = None
    
    # Home/away split (AVAILABLE)
    shots_home_per_match: Optional[float] = None
    shots_away_per_match: Optional[float] = None
    shots_on_target_home_per_match: Optional[float] = None
    shots_on_target_away_per_match: Optional[float] = None
    
    # Shot quality (AVAILABLE when both xg and shots exist)
    xg_for_per_match: Optional[float] = None
    xg_against_per_match: Optional[float] = None
    xg_per_shot: Optional[float] = None  # xG / shots_total
    shot_on_target_rate: Optional[float] = None  # SOT / total shots
    shot_conversion_rate: Optional[float] = None  # goals / shots (if available)
    
    # Shot suppression (defensive - AVAILABLE)
    shots_against_per_match: Optional[float] = None
    shots_on_target_against_per_match: Optional[float] = None
    
    # Shot dominance (AVAILABLE)
    shot_share: Optional[float] = None  # Team shots / (team + opponent shots)
    
    # Recency-weighted variants (exponentially weighted recent average)
    shots_per_match_weighted: Optional[float] = None
    sot_per_match_weighted: Optional[float] = None
    xg_per_match_weighted: Optional[float] = None
    
    # UNAVAILABLE FIELDS (explicitly None)
    shots_inside_box_per_match: Optional[float] = None  # UNAVAILABLE
    box_shot_percentage: Optional[float] = None  # UNAVAILABLE
    big_chances_per_match: Optional[float] = None  # UNAVAILABLE
    non_penalty_xg_per_match: Optional[float] = None  # UNAVAILABLE
    
    # Provenance
    provider: Optional[str] = None
    provider_timestamp: Optional[datetime] = None
    sample_size: int = 0
    matches_with_shot_data: int = 0
    matches_with_xg: int = 0
    data_quality_score: float = 0.0
    window_type: str = "recent"


class ShotIntelligenceCalculator:
    """Calculate shot intelligence from historical match statistics.
    
    Reuses MatchWithStatistics from Group 1 (advanced_team_intelligence.py).
    Follows temporal validity patterns from Group 1.
    Implements recency weighting with exponential decay.
    """
    
    def __init__(
        self,
        session,
        recent_window: int = 5,
        min_matches: int = 3,
        recency_decay: float = 0.95
    ):
        """Initialize calculator with window and weighting configuration.
        
        Args:
            session: Database session (for future repository access)
            recent_window: Number of matches for "recent" window
            min_matches: Minimum matches required for reliable metrics
            recency_decay: Exponential decay factor for recency weighting (0.95 default)
        """
        self.session = session
        self.recent_window = recent_window
        self.min_matches = min_matches
        self.recency_decay = recency_decay
    
    def calculate_shot_metrics(
        self,
        team_id: str,
        matches_with_stats: List[MatchWithStatistics],
        before_datetime: Optional[datetime] = None
    ) -> ShotIntelligenceMetrics:
        """Calculate shot intelligence metrics from historical data.
        
        TEMPORAL VALIDITY: Uses strict < comparison with before_datetime.
        REUSES: MatchWithStatistics from advanced_team_intelligence.py
        PATTERN: Same structure as AdvancedTeamIntelligenceCalculator.calculate_advanced_metrics
        
        Args:
            team_id: Team database ID
            matches_with_stats: List of MatchWithStatistics (Match + home/away stats)
            before_datetime: Only use matches before this timestamp (temporal validity)
            
        Returns:
            ShotIntelligenceMetrics with calculated values or None where unavailable
        """
        # 1. Filter to finished matches only
        finished_matches = [
            mws for mws in matches_with_stats
            if mws.is_finished()
        ]
        
        # 2. Filter to matches strictly before before_datetime (temporal validity)
        if before_datetime is not None:
            finished_matches = [
                mws for mws in finished_matches
                if mws.match.scheduled_at < before_datetime  # STRICT < to prevent leakage
            ]
        
        # 3. Apply window size (most recent matches)
        if len(finished_matches) > self.recent_window:
            finished_matches = finished_matches[-self.recent_window:]
        
        # Check if we have sufficient data
        if len(finished_matches) < self.min_matches:
            return ShotIntelligenceMetrics(
                team_id=team_id,
                sample_size=len(finished_matches),
                data_quality_score=0.0,
            )
        
        # Accumulators for shot metrics
        shots_total_sum = 0.0
        sot_sum = 0.0
        shots_off_target_sum = 0.0
        shots_blocked_sum = 0.0
        shot_count = 0
        
        xg_sum = 0.0
        xg_count = 0
        
        xg_against_sum = 0.0
        xg_against_count = 0
        
        goals_sum = 0.0
        goals_count = 0
        
        # Home/away splits
        shots_home_sum = 0.0
        sot_home_sum = 0.0
        home_count = 0
        
        shots_away_sum = 0.0
        sot_away_sum = 0.0
        away_count = 0
        
        # Opponent shots (for shot share and defensive metrics)
        opponent_shots_sum = 0.0
        opponent_sot_sum = 0.0
        opponent_shot_count = 0
        
        # Recency-weighted accumulators
        shots_weighted_sum = 0.0
        sot_weighted_sum = 0.0
        xg_weighted_sum = 0.0
        weight_sum = 0.0
        
        # Process matches (most recent first for recency weighting)
        for i, mws in enumerate(reversed(finished_matches)):
            stats = mws.get_team_statistics(team_id)
            if stats is None:
                continue
            
            # Recency weight (exponential decay: most recent = weight 1.0)
            weight = self.recency_decay ** i
            
            # Shot volume
            if stats.shots_total is not None:
                shots_total_sum += stats.shots_total
                shot_count += 1
                
                shots_weighted_sum += stats.shots_total * weight
                weight_sum += weight
                
                # Goals for conversion rate
                if stats.goals_scored is not None:
                    goals_sum += stats.goals_scored
                    goals_count += 1
            
            if stats.shots_on_target is not None:
                sot_sum += stats.shots_on_target
                sot_weighted_sum += stats.shots_on_target * weight
            
            if stats.shots_off_target is not None:
                shots_off_target_sum += stats.shots_off_target
            
            if stats.shots_blocked is not None:
                shots_blocked_sum += stats.shots_blocked
            
            # xG
            if stats.xg is not None:
                xg_sum += stats.xg
                xg_count += 1
                xg_weighted_sum += stats.xg * weight
            
            if stats.xg_against is not None:
                xg_against_sum += stats.xg_against
                xg_against_count += 1
            
            # Home/away splits
            if mws.is_home_team(team_id):
                home_count += 1
                if stats.shots_total is not None:
                    shots_home_sum += stats.shots_total
                if stats.shots_on_target is not None:
                    sot_home_sum += stats.shots_on_target
            else:  # Away team
                away_count += 1
                if stats.shots_total is not None:
                    shots_away_sum += stats.shots_total
                if stats.shots_on_target is not None:
                    sot_away_sum += stats.shots_on_target
            
            # Opponent shots (from opponent's statistics)
            opponent_id = mws.match.away_team_id if mws.is_home_team(team_id) else mws.match.home_team_id
            opponent_stats = mws.get_team_statistics(opponent_id)
            if opponent_stats is not None:
                if opponent_stats.shots_total is not None:
                    opponent_shots_sum += opponent_stats.shots_total
                    opponent_shot_count += 1
                if opponent_stats.shots_on_target is not None:
                    opponent_sot_sum += opponent_stats.shots_on_target
        
        # Calculate per-match averages
        shots_per_match = shots_total_sum / shot_count if shot_count > 0 else None
        sot_per_match = sot_sum / shot_count if shot_count > 0 else None
        shots_off_target_per_match = shots_off_target_sum / shot_count if shot_count > 0 else None
        shots_blocked_per_match = shots_blocked_sum / shot_count if shot_count > 0 else None
        
        xg_per_match = xg_sum / xg_count if xg_count > 0 else None
        xg_against_per_match = xg_against_sum / xg_against_count if xg_against_count > 0 else None
        
        # Home/away splits (only if sufficient sample)
        min_venue_matches = max(2, self.min_matches // 2)
        shots_home_per_match = shots_home_sum / home_count if home_count >= min_venue_matches else None
        sot_home_per_match = sot_home_sum / home_count if home_count >= min_venue_matches else None
        shots_away_per_match = shots_away_sum / away_count if away_count >= min_venue_matches else None
        sot_away_per_match = sot_away_sum / away_count if away_count >= min_venue_matches else None
        
        # Shot quality metrics
        xg_per_shot = (xg_sum / shots_total_sum) if shots_total_sum > 0 and xg_count > 0 else None
        sot_rate = (sot_sum / shots_total_sum) if shots_total_sum > 0 else None
        conversion_rate = (goals_sum / shots_total_sum) if shots_total_sum > 0 and goals_count > 0 else None
        
        # Opponent shot metrics (defensive)
        shots_against_per_match = opponent_shots_sum / opponent_shot_count if opponent_shot_count > 0 else None
        sot_against_per_match = opponent_sot_sum / opponent_shot_count if opponent_shot_count > 0 else None
        
        # Shot share (shot dominance)
        total_shots_in_matches = shots_total_sum + opponent_shots_sum
        shot_share = shots_total_sum / total_shots_in_matches if total_shots_in_matches > 0 else None
        
        # Recency-weighted averages
        shots_weighted = shots_weighted_sum / weight_sum if weight_sum > 0 else None
        sot_weighted = sot_weighted_sum / weight_sum if weight_sum > 0 else None
        xg_weighted = xg_weighted_sum / weight_sum if weight_sum > 0 and xg_count > 0 else None
        
        # Calculate data quality score
        data_quality = self._calculate_data_quality(shot_count, xg_count, len(finished_matches))
        
        return ShotIntelligenceMetrics(
            team_id=team_id,
            # Shot volume
            shots_total_per_match=shots_per_match,
            shots_on_target_per_match=sot_per_match,
            shots_off_target_per_match=shots_off_target_per_match,
            shots_blocked_per_match=shots_blocked_per_match,
            # Home/away splits
            shots_home_per_match=shots_home_per_match,
            shots_away_per_match=shots_away_per_match,
            shots_on_target_home_per_match=sot_home_per_match,
            shots_on_target_away_per_match=sot_away_per_match,
            # Shot quality
            xg_for_per_match=xg_per_match,
            xg_against_per_match=xg_against_per_match,
            xg_per_shot=xg_per_shot,
            shot_on_target_rate=sot_rate,
            shot_conversion_rate=conversion_rate,
            # Shot suppression
            shots_against_per_match=shots_against_per_match,
            shots_on_target_against_per_match=sot_against_per_match,
            # Shot dominance
            shot_share=shot_share,
            # Recency-weighted
            shots_per_match_weighted=shots_weighted,
            sot_per_match_weighted=sot_weighted,
            xg_per_match_weighted=xg_weighted,
            # UNAVAILABLE metrics remain None
            shots_inside_box_per_match=None,
            box_shot_percentage=None,
            big_chances_per_match=None,
            non_penalty_xg_per_match=None,
            # Provenance
            sample_size=len(finished_matches),
            matches_with_shot_data=shot_count,
            matches_with_xg=xg_count,
            data_quality_score=data_quality,
            window_type="recent",
        )
    
    def get_raw_shot_counts(
        self,
        team_id: str,
        matches_with_stats: List[MatchWithStatistics],
        before_datetime: Optional[datetime] = None
    ) -> tuple[List[float], List[float]]:
        """Get raw shot count lists for distribution fitting.
        
        Used by ShotProductionCalculator to fit Poisson/NegBin distributions.
        
        Args:
            team_id: Team database ID
            matches_with_stats: List of MatchWithStatistics
            before_datetime: Only use matches before this timestamp
            
        Returns:
            Tuple of (shots_list, sot_list) containing raw counts per match
        """
        # Filter to finished matches before cutoff
        finished_matches = [
            mws for mws in matches_with_stats
            if mws.is_finished()
        ]
        
        if before_datetime is not None:
            finished_matches = [
                mws for mws in finished_matches
                if mws.match.scheduled_at < before_datetime
            ]
        
        shots_list = []
        sot_list = []
        
        for mws in finished_matches:
            stats = mws.get_team_statistics(team_id)
            if stats is None:
                continue
            
            if stats.shots_total is not None:
                shots_list.append(float(stats.shots_total))
            
            if stats.shots_on_target is not None:
                sot_list.append(float(stats.shots_on_target))
        
        return (shots_list, sot_list)
    
    def _calculate_data_quality(
        self,
        shot_count: int,
        xg_count: int,
        total_matches: int
    ) -> float:
        """Calculate data quality score based on data completeness.
        
        Returns:
            Data quality score in [0.0, 1.0]
        """
        if total_matches == 0:
            return 0.0
        
        shot_coverage = shot_count / total_matches
        xg_coverage = xg_count / total_matches
        
        # Weighted average (shot data more important than xG for shot intelligence)
        quality = shot_coverage * 0.7 + xg_coverage * 0.3
        
        return min(1.0, quality)
