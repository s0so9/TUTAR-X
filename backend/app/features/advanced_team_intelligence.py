"""Advanced team intelligence feature calculations.

This module calculates advanced team metrics from historical match statistics.
Extends basic team strength with xG, shots, possession, and other advanced metrics
where actual provider data exists.

CRITICAL DATA CONTRACT:
- Match entity contains metadata only (teams, date, scores, status)
- TeamMatchStatistic contains advanced statistics (xG, shots, possession)
- This calculator requires BOTH Match and TeamMatchStatistic data
- Missing data remains None (never fabricated)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List

from app.domain.match import Match
from app.domain.statistics import TeamMatchStatistic
from app.domain.enums import MatchStatus


@dataclass
class MatchWithStatistics:
    """Match with associated team statistics.
    
    Pairs a Match with its home and away TeamMatchStatistic objects.
    Missing statistics are represented as None (not fabricated).
    """
    match: Match  # Match metadata (teams, date, scores, status)
    home_statistics: Optional[TeamMatchStatistic]  # Home team statistics
    away_statistics: Optional[TeamMatchStatistic]  # Away team statistics
    
    def is_home_team(self, team_id: str) -> bool:
        """Check if team_id is home team."""
        return self.match.home_team_id == team_id
    
    def get_team_statistics(self, team_id: str) -> Optional[TeamMatchStatistic]:
        """Get statistics for specified team."""
        if self.match.home_team_id == team_id:
            return self.home_statistics
        elif self.match.away_team_id == team_id:
            return self.away_statistics
        return None
    
    def is_finished(self) -> bool:
        """Check if match is finished."""
        return self.match.status == MatchStatus.FINISHED


@dataclass
class AdvancedTeamMetrics:
    """Advanced team intelligence metrics.
    
    All fields Optional — missing data remains None, never fabricated.
    Extends basic team strength with advanced metrics where available.
    """
    team_id: str
    
    # xG metrics (None if unavailable from provider)
    xg_for_per_match: Optional[float] = None
    xg_against_per_match: Optional[float] = None
    non_penalty_xg_per_match: Optional[float] = None  # UNAVAILABLE until provider separation
    
    # Shot volume (from TeamMatchStatistic when available)
    shots_per_match: Optional[float] = None
    shots_on_target_per_match: Optional[float] = None
    shots_inside_box_per_match: Optional[float] = None  # UNAVAILABLE until shot coordinates
    
    # Shot quality
    xg_per_shot: Optional[float] = None  # xg / shots (when both available)
    box_shot_percentage: Optional[float] = None  # UNAVAILABLE until shot coordinates
    big_chances_per_match: Optional[float] = None  # UNAVAILABLE until provider classification
    
    # Possession & territory (from TeamMatchStatistic when available)
    possession_avg: Optional[float] = None  # From TeamMatchStatistic.possession_percentage
    field_tilt: Optional[float] = None  # UNAVAILABLE until territorial data
    progressive_passes_per_match: Optional[float] = None  # UNAVAILABLE until progression tracking
    progressive_carries_per_match: Optional[float] = None  # UNAVAILABLE until movement tracking
    
    # Defensive pressure
    ppda: Optional[float] = None  # UNAVAILABLE until defensive action tracking
    high_turnovers_per_match: Optional[float] = None  # UNAVAILABLE until zone tracking
    
    # Set pieces
    set_piece_xg_per_match: Optional[float] = None  # UNAVAILABLE until xG event separation
    
    # Home/away separation (scalar values for venue-specific performance)
    home_xg_for_per_match: Optional[float] = None  # Separate home-only calculation
    away_xg_for_per_match: Optional[float] = None  # Separate away-only calculation
    
    # Provenance & data quality
    provider: Optional[str] = None
    provider_timestamp: Optional[datetime] = None
    sample_size: int = 0
    matches_with_xg: int = 0
    matches_with_shots: int = 0
    matches_with_possession: int = 0
    data_quality_score: float = 0.0  # 0.0-1.0 based on data completeness
    window_type: str = "recent"  # "recent", "medium", "season"


class AdvancedTeamIntelligenceCalculator:
    """Calculate advanced team metrics from historical match statistics.
    
    Extends basic team strength with xG, shots, possession where real data exists.
    Never fabricates unavailable metrics.
    """
    
    def __init__(
        self, 
        session, 
        recent_window: int = 5,
        medium_window: int = 10,
        season_window: int = 38,
        min_matches: int = 3
    ):
        """Initialize calculator with configurable windows.
        
        Args:
            session: Database session (for future repository access)
            recent_window: Number of matches for "recent" window
            medium_window: Number of matches for "medium" window
            season_window: Number of matches for "season" window
            min_matches: Minimum matches required for reliable metrics
        """
        self.session = session
        self.recent_window = recent_window
        self.medium_window = medium_window
        self.season_window = season_window
        self.min_matches = min_matches
    
    def calculate_advanced_metrics(
        self,
        team_id: str,
        matches_with_stats: List[MatchWithStatistics],
        window_type: str = "recent",
        before_datetime: Optional[datetime] = None
    ) -> AdvancedTeamMetrics:
        """Calculate advanced metrics from historical match statistics.
        
        CRITICAL: This method requires MatchWithStatistics objects, NOT raw Match objects.
        Caller must fetch TeamMatchStatistic for each match from repository.
        
        TEMPORAL VALIDITY: Only uses matches strictly before before_datetime.
        Uses strict < comparison to prevent temporal leakage.
        
        Args:
            team_id: Team database ID
            matches_with_stats: List of MatchWithStatistics (Match + home/away stats)
            window_type: "recent", "medium", or "season"
            before_datetime: Only use matches before this timestamp (temporal validity)
            
        Returns:
            AdvancedTeamMetrics with calculated values or None where unavailable
            
        Algorithm:
            1. Filter to finished matches only (match.status == FINISHED)
            2. Filter to matches STRICTLY before before_datetime (< comparison)
            3. Apply window size based on window_type
            4. For each match, extract team_statistics for team_id
            5. For each available metric in TeamMatchStatistic:
               - If field is None → skip (unavailable)
               - If field has value → accumulate
            6. Calculate per-match averages
            7. For UNAVAILABLE metrics (PPDA, Field Tilt, etc.) → return None
            8. Calculate home/away venue splits when sample sufficient
            9. Calculate data_quality_score based on completeness
            10. Return AdvancedTeamMetrics with provenance
            
        Missing Data Handling:
            - If TeamMatchStatistic is None for a match → skip that match
            - If individual field (e.g., xg) is None → exclude from that metric's calculation
            - If ALL matches lack a field → metric remains None (not zero)
            - Sample size tracks total matches, matches_with_xg tracks xG availability
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
        
        # 3. Apply window size based on window_type
        window_size = self._get_window_size(window_type)
        if len(finished_matches) > window_size:
            finished_matches = finished_matches[-window_size:]
        
        # Check if we have sufficient data
        if len(finished_matches) < self.min_matches:
            return AdvancedTeamMetrics(
                team_id=team_id,
                sample_size=len(finished_matches),
                window_type=window_type,
                data_quality_score=0.0
            )
        
        # 4-6. Extract and accumulate metrics
        metrics = self._calculate_metrics_from_matches(team_id, finished_matches)
        
        # 8. Calculate home/away venue splits
        if len(finished_matches) >= self.min_matches:
            home_metrics = self._calculate_venue_split(team_id, finished_matches, is_home=True)
            away_metrics = self._calculate_venue_split(team_id, finished_matches, is_home=False)
            metrics['home_xg_for_per_match'] = home_metrics.get('xg_for_per_match')
            metrics['away_xg_for_per_match'] = away_metrics.get('xg_for_per_match')
        
        # 9. Calculate data quality score
        data_quality_score = self._calculate_data_quality(metrics, len(finished_matches))
        
        # 10. Return AdvancedTeamMetrics with provenance
        return AdvancedTeamMetrics(
            team_id=team_id,
            xg_for_per_match=metrics.get('xg_for_per_match'),
            xg_against_per_match=metrics.get('xg_against_per_match'),
            non_penalty_xg_per_match=None,  # UNAVAILABLE
            shots_per_match=metrics.get('shots_per_match'),
            shots_on_target_per_match=metrics.get('shots_on_target_per_match'),
            shots_inside_box_per_match=None,  # UNAVAILABLE
            xg_per_shot=metrics.get('xg_per_shot'),
            box_shot_percentage=None,  # UNAVAILABLE
            big_chances_per_match=None,  # UNAVAILABLE
            possession_avg=metrics.get('possession_avg'),
            field_tilt=None,  # UNAVAILABLE
            progressive_passes_per_match=None,  # UNAVAILABLE
            progressive_carries_per_match=None,  # UNAVAILABLE
            ppda=None,  # UNAVAILABLE
            high_turnovers_per_match=None,  # UNAVAILABLE
            set_piece_xg_per_match=None,  # UNAVAILABLE
            home_xg_for_per_match=metrics.get('home_xg_for_per_match'),
            away_xg_for_per_match=metrics.get('away_xg_for_per_match'),
            provider=metrics.get('provider'),
            provider_timestamp=metrics.get('provider_timestamp'),
            sample_size=len(finished_matches),
            matches_with_xg=metrics.get('matches_with_xg', 0),
            matches_with_shots=metrics.get('matches_with_shots', 0),
            matches_with_possession=metrics.get('matches_with_possession', 0),
            data_quality_score=data_quality_score,
            window_type=window_type
        )
    
    def _get_window_size(self, window_type: str) -> int:
        """Get window size based on type."""
        window_map = {
            "recent": self.recent_window,
            "medium": self.medium_window,
            "season": self.season_window
        }
        return window_map.get(window_type, self.recent_window)
    
    def _calculate_metrics_from_matches(
        self, 
        team_id: str, 
        matches_with_stats: List[MatchWithStatistics]
    ) -> dict:
        """Calculate metrics from list of MatchWithStatistics.
        
        Accumulates available metrics and calculates per-match averages.
        Tracks data availability for each metric type.
        """
        # Accumulators
        xg_for_total = 0.0
        xg_against_total = 0.0
        shots_total = 0
        shots_on_target_total = 0
        possession_total = 0.0
        
        # Counters for data availability
        matches_with_xg = 0
        matches_with_shots = 0
        matches_with_possession = 0
        
        for mws in matches_with_stats:
            team_stats = mws.get_team_statistics(team_id)
            
            # Skip if no statistics available for this team in this match
            if team_stats is None:
                continue
            
            # Extract xG metrics (if available)
            if team_stats.xg is not None:
                xg_for_total += team_stats.xg
                matches_with_xg += 1
            
            if team_stats.xg_against is not None:
                xg_against_total += team_stats.xg_against
            
            # Extract shot metrics (if available)
            if team_stats.shots_total is not None:
                shots_total += team_stats.shots_total
                matches_with_shots += 1
            
            if team_stats.shots_on_target is not None:
                shots_on_target_total += team_stats.shots_on_target
            
            # Extract possession (if available)
            if team_stats.possession_percentage is not None:
                possession_total += team_stats.possession_percentage
                matches_with_possession += 1
        
        # Calculate per-match averages
        num_matches = len(matches_with_stats)
        metrics = {
            'matches_with_xg': matches_with_xg,
            'matches_with_shots': matches_with_shots,
            'matches_with_possession': matches_with_possession,
        }
        
        # Only calculate averages where data exists
        if matches_with_xg > 0:
            metrics['xg_for_per_match'] = xg_for_total / matches_with_xg
            metrics['xg_against_per_match'] = xg_against_total / matches_with_xg
        
        if matches_with_shots > 0:
            metrics['shots_per_match'] = shots_total / matches_with_shots
            metrics['shots_on_target_per_match'] = shots_on_target_total / matches_with_shots
            
            # Calculate xG per shot if both xG and shots available
            if matches_with_xg > 0 and shots_total > 0:
                metrics['xg_per_shot'] = xg_for_total / shots_total
        
        if matches_with_possession > 0:
            metrics['possession_avg'] = possession_total / matches_with_possession
        
        return metrics
    
    def _calculate_venue_split(
        self, 
        team_id: str, 
        matches_with_stats: List[MatchWithStatistics],
        is_home: bool
    ) -> dict:
        """Calculate metrics for home or away matches only.
        
        Args:
            team_id: Team identifier
            matches_with_stats: All matches
            is_home: True for home matches, False for away matches
            
        Returns:
            Dictionary with venue-specific metrics
        """
        venue_matches = [
            mws for mws in matches_with_stats
            if mws.is_home_team(team_id) == is_home
        ]
        
        if len(venue_matches) < self.min_matches:
            return {}
        
        return self._calculate_metrics_from_matches(team_id, venue_matches)
    
    def _calculate_data_quality(self, metrics: dict, num_matches: int) -> float:
        """Calculate data quality score based on field completeness.
        
        Scores 0.0-1.0 based on how many expected fields have data.
        
        Args:
            metrics: Calculated metrics dictionary
            num_matches: Total number of matches
            
        Returns:
            Data quality score (0.0 = no data, 1.0 = all fields available)
        """
        if num_matches == 0:
            return 0.0
        
        # Check presence of key metrics
        available_fields = 0
        total_expected_fields = 3  # xG, shots, possession
        
        if metrics.get('xg_for_per_match') is not None:
            available_fields += 1
        
        if metrics.get('shots_per_match') is not None:
            available_fields += 1
        
        if metrics.get('possession_avg') is not None:
            available_fields += 1
        
        field_completeness = available_fields / total_expected_fields
        
        # Also consider sample size quality
        sample_quality = min(num_matches / self.season_window, 1.0)
        
        # Weighted combination: 70% field completeness, 30% sample quality
        return (0.7 * field_completeness) + (0.3 * sample_quality)
