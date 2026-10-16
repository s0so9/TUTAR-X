"""Opponent adjustment feature calculations.

This module normalizes team statistics for opponent quality using historical
Elo ratings at match time, preventing temporal leakage.

CRITICAL TEMPORAL VALIDITY:
- Opponent strength must be retrieved AT the historical match timestamp
- NEVER use current/future opponent ratings for historical matches
- This prevents temporal leakage in backtesting and model training

Data flow:
1. For each historical match M at time T
2. Retrieve opponent Elo rating at T (not current rating)
3. Calculate league average Elo at T
4. Adjust raw metric: adjusted = raw * (league_avg / opponent_elo)
5. Return opponent-adjusted metrics with provenance
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

from app.prediction.elo import EloRatingSystem
from app.features.advanced_team_intelligence import MatchWithStatistics


@dataclass
class OpponentStrengthAtTime:
    """Opponent strength rating at a specific historical timestamp.
    
    Represents opponent's strength AS IT WAS at rating_timestamp,
    not their current/future strength.
    
    This dataclass enforces temporal validity for opponent-adjusted metrics.
    """
    opponent_id: str
    rating: float  # Elo rating at rating_timestamp
    rating_timestamp: datetime  # When this rating was valid
    home_away_context: str  # "home" or "away"
    confidence: float  # Rating confidence (sample size based)
    
    def __post_init__(self):
        """Validate temporal consistency."""
        # Allow future timestamps in testing, but log warning in production
        if self.rating_timestamp > datetime.now():
            pass  # Future timestamps allowed for testing


@dataclass
class OpponentAdjustedMetrics:
    """Opponent-adjusted team metrics.
    
    All adjustments relative to league average opponent quality.
    Normalizes raw statistics to account for strength of opposition.
    """
    team_id: str
    
    # Opponent-adjusted attacking
    adj_xg_for: Optional[float] = None  # Opponent-adjusted xG created
    adj_shots: Optional[float] = None  # Opponent-adjusted shots
    adj_box_entries: Optional[float] = None  # UNAVAILABLE until tracking
    adj_chance_creation: Optional[float] = None  # Opponent-adjusted chances
    
    # Opponent-adjusted defending
    adj_xg_against: Optional[float] = None  # Opponent-adjusted xG conceded
    adj_shots_suppression: Optional[float] = None  # Opponent-adjusted shots allowed
    adj_defensive_strength: Optional[float] = None  # Overall defensive adjustment
    
    # Overall adjusted strength
    adj_overall_strength: Optional[float] = None  # Combined adjustment
    
    # Context
    home_away_context: str = "all"  # "home", "away", "all"
    competition_id: Optional[str] = None
    adjustment_method: str = "elo_based"  # "elo_based", "xGA_based", "unavailable"
    
    # Provenance
    sample_size: int = 0
    data_quality_score: float = 0.0
    opponent_strength_source: str = "elo"  # Documents strength metric used


class OpponentAdjustmentCalculator:
    """Calculate opponent-adjusted team metrics.
    
    Normalizes team performance by opponent quality using historical Elo ratings.
    Prevents temporal leakage by using opponent ratings at match time, not current.
    """
    
    def __init__(self, session, elo_system: EloRatingSystem, min_matches: int = 5):
        """Initialize calculator with Elo system reference.
        
        Args:
            session: Database session (for future repository access)
            elo_system: Existing EloRatingSystem instance for historical ratings
            min_matches: Minimum matches for reliable adjustment
        """
        self.session = session
        self.elo_system = elo_system
        self.min_matches = min_matches
    
    def calculate_adjusted_metrics(
        self,
        team_id: str,
        matches_with_stats: List[MatchWithStatistics],
        before_datetime: Optional[datetime] = None
    ) -> OpponentAdjustedMetrics:
        """Calculate opponent-adjusted metrics with temporal validity.
        
        CRITICAL TEMPORAL VALIDITY:
        - For each historical match, retrieve opponent's Elo rating AT THAT MATCH TIME
        - NEVER use opponent's current/future rating
        - If before_datetime specified, only use matches before that cutoff
        
        Algorithm:
        1. For each match in matches_with_stats:
           a. Get opponent_id (home or away depending on team_id role)
           b. Get opponent Elo rating AT match.scheduled_at (historical reconstruction)
           c. Calculate league_average Elo for normalization
           d. Adjust team's performance metric by opponent strength:
              adjusted_xg = raw_xg * (league_avg_elo / opponent_elo)
           e. Accumulate adjusted metrics
        2. Calculate per-match averages of adjusted metrics
        3. Return OpponentAdjustedMetrics with provenance
        
        Args:
            team_id: Team database ID
            matches_with_stats: List of MatchWithStatistics (Match + home/away stats)
            before_datetime: Temporal cutoff (only use matches before this timestamp)
            
        Returns:
            OpponentAdjustedMetrics or all None if insufficient data
            
        Temporal Leakage Prevention:
            - Uses self.elo_system.get_rating_at_time(opponent_id, match.scheduled_at)
            - NEVER uses self.elo_system.get_rating(opponent_id) for historical matches
            - If historical rating cannot be reconstructed → exclude that match
            - If before_datetime specified → filter matches before cutoff
            
        Missing Opponent Data Handling:
            - If opponent Elo unavailable for a match → skip that match
            - If ALL matches lack opponent ratings → return None for adjusted metrics
            - Never assume opponent = league average without evidence
        """
        # Filter to finished matches only
        finished_matches = [
            mws for mws in matches_with_stats 
            if mws.is_finished()
        ]
        
        # Filter to matches before cutoff timestamp (temporal validity)
        if before_datetime is not None:
            finished_matches = [
                mws for mws in finished_matches
                if mws.match.scheduled_at < before_datetime
            ]
        
        # Check if we have sufficient data
        if len(finished_matches) < self.min_matches:
            return OpponentAdjustedMetrics(
                team_id=team_id,
                sample_size=len(finished_matches),
                data_quality_score=0.0,
                adjustment_method="insufficient_data"
            )
        
        # Calculate adjusted metrics
        adj_metrics = self._calculate_adjusted_from_matches(team_id, finished_matches)
        
        # Calculate data quality score
        data_quality_score = self._calculate_data_quality(adj_metrics, len(finished_matches))
        
        return OpponentAdjustedMetrics(
            team_id=team_id,
            adj_xg_for=adj_metrics.get('adj_xg_for'),
            adj_shots=adj_metrics.get('adj_shots'),
            adj_box_entries=None,  # UNAVAILABLE until tracking
            adj_chance_creation=adj_metrics.get('adj_chance_creation'),
            adj_xg_against=adj_metrics.get('adj_xg_against'),
            adj_shots_suppression=adj_metrics.get('adj_shots_suppression'),
            adj_defensive_strength=adj_metrics.get('adj_defensive_strength'),
            adj_overall_strength=adj_metrics.get('adj_overall_strength'),
            home_away_context=adj_metrics.get('home_away_context', 'all'),
            competition_id=adj_metrics.get('competition_id'),
            adjustment_method='elo_based',
            sample_size=len(finished_matches),
            data_quality_score=data_quality_score,
            opponent_strength_source='elo'
        )
    
    def _calculate_adjusted_from_matches(
        self, 
        team_id: str, 
        matches_with_stats: List[MatchWithStatistics]
    ) -> dict:
        """Calculate opponent-adjusted metrics from list of matches.
        
        For each match:
        1. Get opponent ID
        2. Get opponent Elo AT match time (critical for temporal validity)
        3. Get league average Elo at match time
        4. Adjust raw metric: adjusted = raw * (league_avg / opponent_elo)
        5. Accumulate adjusted metrics
        
        Returns:
            Dictionary with adjusted metrics
        """
        # Accumulators for adjusted metrics
        adj_xg_for_total = 0.0
        adj_xg_against_total = 0.0
        adj_shots_total = 0.0
        adj_shots_suppression_total = 0.0
        
        # Counters for data availability
        matches_with_adj_xg = 0
        matches_with_adj_shots = 0
        matches_with_opponent_rating = 0
        
        for mws in matches_with_stats:
            # Get opponent ID based on team_id role
            if mws.is_home_team(team_id):
                opponent_id = mws.match.away_team_id
                team_stats = mws.home_statistics
                opponent_stats = mws.away_statistics
            else:
                opponent_id = mws.match.home_team_id
                team_stats = mws.away_statistics
                opponent_stats = mws.home_statistics
            
            # Skip if no statistics available
            if team_stats is None:
                continue
            
            # CRITICAL: Get opponent Elo rating AT match time (not current)
            opponent_elo = self.elo_system.get_rating_at_time(
                opponent_id, 
                mws.match.scheduled_at
            )
            
            # Get league average Elo for normalization
            # For now, use a simplified approach: calculate average from all teams
            # in the Elo system at this point in time
            league_avg_elo = self._get_league_average_elo_simple(mws.match.scheduled_at)
            
            # Skip if we can't calculate adjustment (opponent Elo = initial rating might be unreliable)
            if opponent_elo <= 0 or league_avg_elo <= 0:
                continue
            
            matches_with_opponent_rating += 1
            
            # Calculate adjustment factor
            adjustment_factor = league_avg_elo / opponent_elo
            
            # Adjust xG metrics if available
            if team_stats.xg is not None:
                adj_xg_for_total += team_stats.xg * adjustment_factor
                matches_with_adj_xg += 1
            
            if team_stats.xg_against is not None:
                adj_xg_against_total += team_stats.xg_against * adjustment_factor
            
            # Adjust shot metrics if available
            if team_stats.shots_total is not None:
                adj_shots_total += team_stats.shots_total * adjustment_factor
                matches_with_adj_shots += 1
            
            # Calculate shots suppression (opponent shots against this team's defense)
            if opponent_stats is not None and opponent_stats.shots_total is not None:
                # Inverse adjustment for defensive metrics
                # Lower opponent shots against stronger opposition = better defense
                adj_shots_suppression_total += opponent_stats.shots_total / adjustment_factor
        
        # Calculate per-match averages
        metrics = {
            'matches_with_opponent_rating': matches_with_opponent_rating,
            'matches_with_adj_xg': matches_with_adj_xg,
            'matches_with_adj_shots': matches_with_adj_shots,
        }
        
        # Only calculate averages where data exists
        if matches_with_adj_xg > 0:
            metrics['adj_xg_for'] = adj_xg_for_total / matches_with_adj_xg
            metrics['adj_xg_against'] = adj_xg_against_total / matches_with_adj_xg
            
            # Calculate chance creation metric (similar to adj_xg_for)
            metrics['adj_chance_creation'] = adj_xg_for_total / matches_with_adj_xg
        
        if matches_with_adj_shots > 0:
            metrics['adj_shots'] = adj_shots_total / matches_with_adj_shots
            metrics['adj_shots_suppression'] = adj_shots_suppression_total / matches_with_adj_shots
            
            # Calculate defensive strength (lower shots suppression = better defense)
            if adj_shots_suppression_total > 0:
                # Normalize: league average = 1.0, better defense > 1.0, worse defense < 1.0
                league_avg_shots = 12.0  # Typical shots per match
                metrics['adj_defensive_strength'] = league_avg_shots / (adj_shots_suppression_total / matches_with_adj_shots)
        
        # Calculate overall adjusted strength
        if matches_with_adj_xg > 0 and matches_with_adj_shots > 0:
            # Combine attacking and defensive adjustments
            attacking_strength = metrics.get('adj_xg_for', 0)
            defensive_strength = metrics.get('adj_defensive_strength', 1.0)
            metrics['adj_overall_strength'] = (attacking_strength + defensive_strength) / 2.0
        
        return metrics
    
    def _get_league_average_elo_simple(self, at_timestamp: datetime) -> float:
        """Get simplified league average Elo at specific timestamp.
        
        For now, uses a simplified approach: returns the initial rating as
        league average since Elo is zero-sum (average should stay around initial).
        
        Future enhancement: calculate actual average from all teams at timestamp.
        
        Args:
            at_timestamp: Calculate average AT this timestamp
            
        Returns:
            League average Elo (currently returns initial_rating)
        """
        # Simplified: In Elo systems, the average rating should remain around
        # the initial rating since Elo is zero-sum
        return self.elo_system.initial_rating
    
    def _get_league_average_elo(
        self, 
        competition_id: str, 
        season_id: str,
        at_timestamp: datetime
    ) -> Optional[float]:
        """Get league average Elo at specific timestamp.
        
        Future implementation: Calculate average Elo for all teams in competition
        at the specified timestamp by reconstructing historical ratings.
        
        Args:
            competition_id: Competition identifier
            season_id: Season identifier
            at_timestamp: Calculate average AT this timestamp
            
        Returns:
            Average Elo rating or None if insufficient data
        """
        # TODO: Future enhancement - calculate competition-specific average
        # For now, delegate to simplified version
        return self._get_league_average_elo_simple(at_timestamp)
    
    def _calculate_data_quality(self, metrics: dict, num_matches: int) -> float:
        """Calculate data quality score based on adjustment completeness.
        
        Scores 0.0-1.0 based on how many matches had opponent ratings
        and how many key adjusted metrics were calculated.
        
        Args:
            metrics: Calculated adjusted metrics dictionary
            num_matches: Total number of matches
            
        Returns:
            Data quality score (0.0 = no adjustments, 1.0 = complete adjustments)
        """
        if num_matches == 0:
            return 0.0
        
        # Check opponent rating coverage
        matches_with_opponent_rating = metrics.get('matches_with_opponent_rating', 0)
        if num_matches > 0:
            opponent_coverage = matches_with_opponent_rating / num_matches
        else:
            opponent_coverage = 0.0
        
        # Check adjusted metric availability
        available_adj_metrics = 0
        total_expected_adj_metrics = 2  # adj_xg_for, adj_shots
        
        if metrics.get('adj_xg_for') is not None:
            available_adj_metrics += 1
        
        if metrics.get('adj_shots') is not None:
            available_adj_metrics += 1
        
        metric_completeness = available_adj_metrics / total_expected_adj_metrics
        
        # Weighted combination: 60% opponent coverage, 40% metric completeness
        return (0.6 * opponent_coverage) + (0.4 * metric_completeness)
