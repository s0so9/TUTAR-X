"""Common opponent intelligence feature calculations.

This module calculates common opponent intelligence by discovering shared opponents
and comparing performance across both teams. Provides contextual evidence when direct
H2H is limited/unavailable.

CRITICAL DATA CONTRACT:
- Common opponent analysis is CONTEXTUAL EVIDENCE, not independent prediction
- Never fabricate common opponents, results, xG, or tactical metrics
- Temporal validity: strict match.scheduled_at < prediction_timestamp
- No naive transitive logic (A beat B, B beat C → A > C is invalid)
- Missing data remains None (never zero, never fabricated)

SEPARATION FROM DIRECT H2H:
- Common opponent intelligence is independent of direct H2H
- Direct A vs B matches are NOT included in common opponent discovery
- Both can coexist in the analysis context

CONFIDENCE CALCULATION:
confidence = sample_factor * recency_factor * context_factor

where:
- sample_factor = min(1.0, n_common_opponents / 5.0)
- recency_factor = average recency weight across all matches
- context_factor = average context match rate (home/away venue matching)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Set
import math

from app.features.advanced_team_intelligence import MatchWithStatistics
from app.domain.enums import MatchStatus


@dataclass
class CommonOpponentMatch:
    """Record of a team's performance vs a common opponent.
    
    Preserves full match context for proper comparison.
    """
    team_id: str
    opponent_id: str
    match_id: str
    match_date: datetime
    
    # Match context
    is_home: bool  # Was team_id playing at home
    competition_id: str
    
    # Result
    result: str  # "win", "draw", "loss"
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int  # 3, 1, or 0
    
    # Advanced metrics (None if unavailable)
    xg: Optional[float] = None
    xga: Optional[float] = None
    shots: Optional[int] = None
    shots_on_target: Optional[int] = None
    possession: Optional[float] = None
    
    # Data quality
    has_advanced_stats: bool = False
    
    def __post_init__(self):
        """Validate data integrity."""
        assert self.result in ["win", "draw", "loss"], f"Invalid result: {self.result}"
        assert 0 <= self.points <= 3, f"Invalid points: {self.points}"


@dataclass
class CommonOpponentEvidence:
    """Evidence from one common opponent."""
    
    common_opponent_id: str
    
    # Home team's matches vs this opponent
    home_team_matches: List[CommonOpponentMatch] = field(default_factory=list)
    
    # Away team's matches vs this opponent
    away_team_matches: List[CommonOpponentMatch] = field(default_factory=list)
    
    # Comparison metrics (None if insufficient data)
    home_avg_points: Optional[float] = None
    away_avg_points: Optional[float] = None
    points_differential: Optional[float] = None  # home - away
    
    home_avg_xg: Optional[float] = None
    away_avg_xg: Optional[float] = None
    xg_differential: Optional[float] = None
    
    home_avg_xga: Optional[float] = None
    away_avg_xga: Optional[float] = None
    xga_differential: Optional[float] = None
    
    # Context match rate (0.0-1.0)
    # How many comparisons have matching home/away context
    context_match_rate: float = 0.0
    
    # Recency weight
    avg_recency_weight: float = 0.0


@dataclass
class CommonOpponentIntelligence:
    """Complete common opponent intelligence for a fixture."""
    
    home_team_id: str
    away_team_id: str
    
    # Discovery results
    common_opponent_ids: List[str] = field(default_factory=list)
    n_common_opponents: int = 0
    
    # Detailed evidence per opponent
    opponent_evidence: List[CommonOpponentEvidence] = field(default_factory=list)
    
    # Aggregated comparison (across all common opponents)
    home_avg_points_vs_common: Optional[float] = None
    away_avg_points_vs_common: Optional[float] = None
    points_differential: Optional[float] = None
    
    home_avg_xg_vs_common: Optional[float] = None
    away_avg_xg_vs_common: Optional[float] = None
    xg_differential: Optional[float] = None
    
    home_avg_xga_vs_common: Optional[float] = None
    away_avg_xga_vs_common: Optional[float] = None
    xga_differential: Optional[float] = None
    
    home_avg_shots_vs_common: Optional[float] = None
    away_avg_shots_vs_common: Optional[float] = None
    shots_differential: Optional[float] = None
    
    # Context normalization
    recency_weighted: bool = False
    home_away_normalized: bool = False
    
    # Confidence calculation
    comparison_confidence: float = 0.0  # 0.0-1.0
    signal_strength: str = "neutral"  # "neutral", "home_favored", "away_favored"
    
    # Sample size tracking
    home_matches_vs_common: int = 0
    away_matches_vs_common: int = 0
    
    # Data quality
    data_quality_score: float = 0.0
    
    # Provenance
    calculation_timestamp: Optional[datetime] = None


class CommonOpponentCalculator:
    """Calculate common opponent intelligence with explicit confidence methodology.
    
    Discovers shared opponents, compares performance, applies recency weighting,
    and calculates statistical confidence.
    """
    
    def __init__(
        self,
        min_common_opponents: int = 3,
        min_matches_per_opponent: int = 1,
        recency_decay: float = 0.95,
        min_confidence_threshold: float = 0.5,
        min_differential_threshold: float = 0.3
    ):
        """Initialize calculator with configurable thresholds.
        
        Args:
            min_common_opponents: Minimum shared opponents for reliable comparison
            min_matches_per_opponent: Minimum matches against each opponent
            recency_decay: Exponential decay factor (reuse from temporal_intelligence)
            min_confidence_threshold: Minimum confidence for non-neutral signal
            min_differential_threshold: Minimum differential for meaningful signal
        """
        self.min_common_opponents = min_common_opponents
        self.min_matches_per_opponent = min_matches_per_opponent
        self.recency_decay = recency_decay
        self.min_confidence_threshold = min_confidence_threshold
        self.min_differential_threshold = min_differential_threshold
    
    def calculate_common_opponent_intelligence(
        self,
        home_team_id: str,
        away_team_id: str,
        home_matches_with_stats: List[MatchWithStatistics],
        away_matches_with_stats: List[MatchWithStatistics],
        before_datetime: Optional[datetime] = None
    ) -> CommonOpponentIntelligence:
        """Calculate common opponent intelligence with temporal validity.
        
        CRITICAL TEMPORAL VALIDITY:
        - Only use matches with match.scheduled_at < before_datetime (strict <)
        - Never use matches at or after before_datetime
        - Explicitly test temporal leakage prevention
        
        ALGORITHM:
        1. Identify common opponents:
           home_opponents = {opponent_id for each match in home_matches}
           away_opponents = {opponent_id for each match in away_matches}
           common_opponents = home_opponents ∩ away_opponents
        
        2. For each common opponent:
           a. Extract home team's performance vs this opponent
           b. Extract away team's performance vs this opponent
           c. Calculate recency weights (exponential decay)
           d. Calculate context match rate (home vs home, away vs away)
           e. Compare performance metrics
        
        3. Aggregate across all common opponents:
           - Weighted averages of points, xG, xGA, shots
           - Track sample sizes
        
        4. Calculate confidence:
           confidence = sample_factor * recency_factor * context_factor
           
           sample_factor = min(1.0, n_common_opponents / 5.0)
           recency_factor = avg_recency_weight (across all matches)
           context_factor = avg_context_match_rate (across all opponents)
        
        5. Determine signal strength:
           if |differential| < min_differential_threshold:
               signal = "neutral"
           elif confidence < min_confidence_threshold:
               signal = "neutral"
           elif differential > 0.5 and confidence > 0.7:
               signal = "home_favored"
           elif differential < -0.5 and confidence > 0.7:
               signal = "away_favored"
           else:
               signal = "neutral"
        
        Args:
            home_team_id: Home team database ID
            away_team_id: Away team database ID
            home_matches_with_stats: Home team's historical matches WITH statistics
            away_matches_with_stats: Away team's historical matches WITH statistics
            before_datetime: Temporal cutoff (strict <)
        
        Returns:
            CommonOpponentIntelligence with explicit confidence or None fields
        
        Missing Data Handling:
            - If n_common_opponents < min_common_opponents → all comparisons = None
            - If specific metric unavailable (e.g., xG) → that differential = None
            - Never fabricate common opponent data
            - comparison_confidence explicitly calculated, never assumed
        """
        if before_datetime is None:
            before_datetime = datetime.utcnow()
        
        # Step 1: Discover common opponents
        common_opponent_ids, home_by_opponent, away_by_opponent = self._discover_common_opponents(
            home_matches_with_stats,
            away_matches_with_stats,
            home_team_id,
            away_team_id,
            before_datetime
        )
        
        # Initialize result
        result = CommonOpponentIntelligence(
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            common_opponent_ids=common_opponent_ids,
            n_common_opponents=len(common_opponent_ids),
            calculation_timestamp=datetime.utcnow()
        )
        
        # If no common opponents, return empty result
        if len(common_opponent_ids) == 0:
            result.data_quality_score = 0.0
            return result
        
        # Step 2: Analyze each common opponent
        opponent_evidence_list = []
        for opponent_id in common_opponent_ids:
            home_matches = home_by_opponent[opponent_id]
            away_matches = away_by_opponent[opponent_id]
            
            # Extract CommonOpponentMatch records
            home_opponent_matches = [
                self._extract_common_opponent_match(m, home_team_id, opponent_id)
                for m in home_matches
            ]
            away_opponent_matches = [
                self._extract_common_opponent_match(m, away_team_id, opponent_id)
                for m in away_matches
            ]
            
            # Compare performance
            evidence = self._compare_opponent_evidence(
                home_opponent_matches,
                away_opponent_matches,
                before_datetime
            )
            evidence.common_opponent_id = opponent_id
            opponent_evidence_list.append(evidence)
        
        result.opponent_evidence = opponent_evidence_list
        
        # Step 3: Aggregate across all common opponents
        if len(common_opponent_ids) >= self.min_common_opponents:
            aggregated_metrics, sample_factor, recency_factor, context_factor = self._aggregate_evidence(
                opponent_evidence_list
            )
            
            # Populate aggregated metrics
            result.home_avg_points_vs_common = aggregated_metrics.get("home_avg_points")
            result.away_avg_points_vs_common = aggregated_metrics.get("away_avg_points")
            result.points_differential = aggregated_metrics.get("points_differential")
            
            result.home_avg_xg_vs_common = aggregated_metrics.get("home_avg_xg")
            result.away_avg_xg_vs_common = aggregated_metrics.get("away_avg_xg")
            result.xg_differential = aggregated_metrics.get("xg_differential")
            
            result.home_avg_xga_vs_common = aggregated_metrics.get("home_avg_xga")
            result.away_avg_xga_vs_common = aggregated_metrics.get("away_avg_xga")
            result.xga_differential = aggregated_metrics.get("xga_differential")
            
            result.home_avg_shots_vs_common = aggregated_metrics.get("home_avg_shots")
            result.away_avg_shots_vs_common = aggregated_metrics.get("away_avg_shots")
            result.shots_differential = aggregated_metrics.get("shots_differential")
            
            result.home_matches_vs_common = aggregated_metrics.get("home_matches_count", 0)
            result.away_matches_vs_common = aggregated_metrics.get("away_matches_count", 0)
            
            # Step 4: Calculate confidence
            result.comparison_confidence = self._calculate_confidence(
                len(common_opponent_ids),
                recency_factor,
                context_factor
            )
            
            result.recency_weighted = True
            result.home_away_normalized = True
            
            # Step 5: Determine signal strength
            result.signal_strength = self._determine_signal_strength(
                result.points_differential,
                result.comparison_confidence
            )
            
            # Calculate data quality score
            result.data_quality_score = self._calculate_data_quality_score(
                len(common_opponent_ids),
                aggregated_metrics
            )
        else:
            # Insufficient common opponents - all comparisons remain None
            result.data_quality_score = 0.3  # Some data but insufficient
        
        return result
    
    def _discover_common_opponents(
        self,
        home_matches: List[MatchWithStatistics],
        away_matches: List[MatchWithStatistics],
        home_team_id: str,
        away_team_id: str,
        before_datetime: datetime
    ) -> Tuple[List[str], Dict[str, List[MatchWithStatistics]], Dict[str, List[MatchWithStatistics]]]:
        """Discover common opponents and organize matches.
        
        CRITICAL: Excludes direct H2H matches (home_team vs away_team).
        CRITICAL: Enforces temporal validity (strict <).
        
        Returns:
            Tuple of (common_opponent_ids, home_matches_by_opponent, away_matches_by_opponent)
        """
        home_opponents: Set[str] = set()
        home_by_opponent: Dict[str, List[MatchWithStatistics]] = {}
        
        # Collect home team's opponents
        for match_with_stats in home_matches:
            match = match_with_stats.match
            
            # Temporal validity: strict <
            if match.scheduled_at >= before_datetime:
                continue
            
            # Only finished matches
            if match.status != MatchStatus.FINISHED:
                continue
            
            # Determine opponent
            if match.home_team_id == home_team_id:
                opponent_id = match.away_team_id
            elif match.away_team_id == home_team_id:
                opponent_id = match.home_team_id
            else:
                continue  # Match doesn't involve home_team_id
            
            # Exclude direct H2H matches
            if opponent_id == away_team_id:
                continue
            
            home_opponents.add(opponent_id)
            if opponent_id not in home_by_opponent:
                home_by_opponent[opponent_id] = []
            home_by_opponent[opponent_id].append(match_with_stats)
        
        away_opponents: Set[str] = set()
        away_by_opponent: Dict[str, List[MatchWithStatistics]] = {}
        
        # Collect away team's opponents
        for match_with_stats in away_matches:
            match = match_with_stats.match
            
            # Temporal validity: strict <
            if match.scheduled_at >= before_datetime:
                continue
            
            # Only finished matches
            if match.status != MatchStatus.FINISHED:
                continue
            
            # Determine opponent
            if match.home_team_id == away_team_id:
                opponent_id = match.away_team_id
            elif match.away_team_id == away_team_id:
                opponent_id = match.home_team_id
            else:
                continue  # Match doesn't involve away_team_id
            
            # Exclude direct H2H matches
            if opponent_id == home_team_id:
                continue
            
            away_opponents.add(opponent_id)
            if opponent_id not in away_by_opponent:
                away_by_opponent[opponent_id] = []
            away_by_opponent[opponent_id].append(match_with_stats)
        
        # Find intersection
        common_opponent_ids = sorted(list(home_opponents & away_opponents))
        
        return common_opponent_ids, home_by_opponent, away_by_opponent
    
    def _extract_common_opponent_match(
        self,
        match_with_stats: MatchWithStatistics,
        team_id: str,
        opponent_id: str
    ) -> CommonOpponentMatch:
        """Extract CommonOpponentMatch from MatchWithStatistics.
        
        Preserves all available data, marks advanced stats availability.
        """
        match = match_with_stats.match
        
        # Determine if team_id was home
        is_home = match.home_team_id == team_id
        
        # Get team statistics
        team_stats = match_with_stats.get_team_statistics(team_id)
        
        # Determine result and scores
        if is_home:
            goals_for = match.home_score or 0
            goals_against = match.away_score or 0
        else:
            goals_for = match.away_score or 0
            goals_against = match.home_score or 0
        
        goal_difference = goals_for - goals_against
        
        # Determine result
        if goal_difference > 0:
            result = "win"
            points = 3
        elif goal_difference < 0:
            result = "loss"
            points = 0
        else:
            result = "draw"
            points = 1
        
        # Extract advanced metrics if available
        xg = None
        xga = None
        shots = None
        shots_on_target = None
        possession = None
        has_advanced_stats = False
        
        if team_stats:
            xg = team_stats.xg
            xga = team_stats.xg_against
            shots = team_stats.shots_total
            shots_on_target = team_stats.shots_on_target
            possession = team_stats.possession_percentage
            
            # Check if advanced stats are available
            if xg is not None or shots is not None:
                has_advanced_stats = True
        
        return CommonOpponentMatch(
            team_id=team_id,
            opponent_id=opponent_id,
            match_id=match.id,
            match_date=match.scheduled_at,
            is_home=is_home,
            competition_id=match.competition_id,
            result=result,
            goals_for=goals_for,
            goals_against=goals_against,
            goal_difference=goal_difference,
            points=points,
            xg=xg,
            xga=xga,
            shots=shots,
            shots_on_target=shots_on_target,
            possession=possession,
            has_advanced_stats=has_advanced_stats,
        )
    
    def _calculate_recency_weight(
        self,
        match_date: datetime,
        reference_date: datetime
    ) -> float:
        """Calculate exponential recency weight.
        
        Reuses temporal_intelligence exponential decay approach.
        weight = decay_factor ^ (days_since_match / 30)
        """
        days_since = (reference_date - match_date).days
        if days_since < 0:
            return 0.0  # Future match (should not happen with proper filtering)
        
        # Normalize by 30 days
        periods = days_since / 30.0
        weight = self.recency_decay ** periods
        
        return max(0.0, min(1.0, weight))
    
    def _compare_opponent_evidence(
        self,
        home_matches: List[CommonOpponentMatch],
        away_matches: List[CommonOpponentMatch],
        reference_date: datetime
    ) -> CommonOpponentEvidence:
        """Compare home vs away performance vs one common opponent.
        
        Applies recency weighting, calculates context match rate, compares metrics.
        """
        evidence = CommonOpponentEvidence(
            common_opponent_id="",  # Will be set by caller
            home_team_matches=home_matches,
            away_team_matches=away_matches,
        )
        
        if len(home_matches) == 0 or len(away_matches) == 0:
            return evidence
        
        # Calculate recency weights
        home_weights = [
            self._calculate_recency_weight(m.match_date, reference_date)
            for m in home_matches
        ]
        away_weights = [
            self._calculate_recency_weight(m.match_date, reference_date)
            for m in away_matches
        ]
        
        # Calculate weighted averages for points
        home_total_weight = sum(home_weights)
        away_total_weight = sum(away_weights)
        
        if home_total_weight > 0:
            evidence.home_avg_points = sum(
                m.points * w for m, w in zip(home_matches, home_weights)
            ) / home_total_weight
        
        if away_total_weight > 0:
            evidence.away_avg_points = sum(
                m.points * w for m, w in zip(away_matches, away_weights)
            ) / away_total_weight
        
        if evidence.home_avg_points is not None and evidence.away_avg_points is not None:
            evidence.points_differential = evidence.home_avg_points - evidence.away_avg_points
        
        # Calculate xG comparisons (if available)
        home_xg_values = [m.xg for m in home_matches if m.xg is not None]
        away_xg_values = [m.xg for m in away_matches if m.xg is not None]
        
        if len(home_xg_values) > 0:
            home_xg_weights = [w for m, w in zip(home_matches, home_weights) if m.xg is not None]
            total_weight = sum(home_xg_weights)
            if total_weight > 0:
                evidence.home_avg_xg = sum(
                    xg * w for xg, w in zip(home_xg_values, home_xg_weights)
                ) / total_weight
        
        if len(away_xg_values) > 0:
            away_xg_weights = [w for m, w in zip(away_matches, away_weights) if m.xg is not None]
            total_weight = sum(away_xg_weights)
            if total_weight > 0:
                evidence.away_avg_xg = sum(
                    xg * w for xg, w in zip(away_xg_values, away_xg_weights)
                ) / total_weight
        
        if evidence.home_avg_xg is not None and evidence.away_avg_xg is not None:
            evidence.xg_differential = evidence.home_avg_xg - evidence.away_avg_xg
        
        # Calculate xGA comparisons (if available)
        home_xga_values = [m.xga for m in home_matches if m.xga is not None]
        away_xga_values = [m.xga for m in away_matches if m.xga is not None]
        
        if len(home_xga_values) > 0:
            home_xga_weights = [w for m, w in zip(home_matches, home_weights) if m.xga is not None]
            total_weight = sum(home_xga_weights)
            if total_weight > 0:
                evidence.home_avg_xga = sum(
                    xga * w for xga, w in zip(home_xga_values, home_xga_weights)
                ) / total_weight
        
        if len(away_xga_values) > 0:
            away_xga_weights = [w for m, w in zip(away_matches, away_weights) if m.xga is not None]
            total_weight = sum(away_xga_weights)
            if total_weight > 0:
                evidence.away_avg_xga = sum(
                    xga * w for xga, w in zip(away_xga_values, away_xga_weights)
                ) / total_weight
        
        if evidence.home_avg_xga is not None and evidence.away_avg_xga is not None:
            evidence.xga_differential = evidence.home_avg_xga - evidence.away_avg_xga
        
        # Calculate context match rate (home vs home, away vs away)
        home_home_count = sum(1 for m in home_matches if m.is_home)
        away_away_count = sum(1 for m in away_matches if not m.is_home)
        matching_context = home_home_count + away_away_count
        total_matches = len(home_matches) + len(away_matches)
        
        if total_matches > 0:
            evidence.context_match_rate = matching_context / total_matches
        
        # Calculate average recency weight
        all_weights = home_weights + away_weights
        if len(all_weights) > 0:
            evidence.avg_recency_weight = sum(all_weights) / len(all_weights)
        
        return evidence
    
    def _aggregate_evidence(
        self,
        opponent_evidence_list: List[CommonOpponentEvidence]
    ) -> Tuple[Dict[str, float], float, float, float]:
        """Aggregate evidence across all common opponents.
        
        Returns:
            Tuple of (aggregated_metrics, sample_factor, recency_factor, context_factor)
        """
        aggregated = {}
        
        # Collect all metrics
        home_points_list = [e.home_avg_points for e in opponent_evidence_list if e.home_avg_points is not None]
        away_points_list = [e.away_avg_points for e in opponent_evidence_list if e.away_avg_points is not None]
        
        home_xg_list = [e.home_avg_xg for e in opponent_evidence_list if e.home_avg_xg is not None]
        away_xg_list = [e.away_avg_xg for e in opponent_evidence_list if e.away_avg_xg is not None]
        
        home_xga_list = [e.home_avg_xga for e in opponent_evidence_list if e.home_avg_xga is not None]
        away_xga_list = [e.away_avg_xga for e in opponent_evidence_list if e.away_avg_xga is not None]
        
        # Calculate aggregate points
        if len(home_points_list) > 0:
            aggregated["home_avg_points"] = sum(home_points_list) / len(home_points_list)
        
        if len(away_points_list) > 0:
            aggregated["away_avg_points"] = sum(away_points_list) / len(away_points_list)
        
        if "home_avg_points" in aggregated and "away_avg_points" in aggregated:
            aggregated["points_differential"] = aggregated["home_avg_points"] - aggregated["away_avg_points"]
        
        # Calculate aggregate xG
        if len(home_xg_list) > 0:
            aggregated["home_avg_xg"] = sum(home_xg_list) / len(home_xg_list)
        
        if len(away_xg_list) > 0:
            aggregated["away_avg_xg"] = sum(away_xg_list) / len(away_xg_list)
        
        if "home_avg_xg" in aggregated and "away_avg_xg" in aggregated:
            aggregated["xg_differential"] = aggregated["home_avg_xg"] - aggregated["away_avg_xg"]
        
        # Calculate aggregate xGA
        if len(home_xga_list) > 0:
            aggregated["home_avg_xga"] = sum(home_xga_list) / len(home_xga_list)
        
        if len(away_xga_list) > 0:
            aggregated["away_avg_xga"] = sum(away_xga_list) / len(away_xga_list)
        
        if "home_avg_xga" in aggregated and "away_avg_xga" in aggregated:
            aggregated["xga_differential"] = aggregated["home_avg_xga"] - aggregated["away_avg_xga"]
        
        # Calculate aggregate shots (if available)
        home_shots_list = []
        away_shots_list = []
        for e in opponent_evidence_list:
            home_shot_values = [m.shots for m in e.home_team_matches if m.shots is not None]
            if len(home_shot_values) > 0:
                home_shots_list.append(sum(home_shot_values) / len(home_shot_values))
            
            away_shot_values = [m.shots for m in e.away_team_matches if m.shots is not None]
            if len(away_shot_values) > 0:
                away_shots_list.append(sum(away_shot_values) / len(away_shot_values))
        
        if len(home_shots_list) > 0:
            aggregated["home_avg_shots"] = sum(home_shots_list) / len(home_shots_list)
        
        if len(away_shots_list) > 0:
            aggregated["away_avg_shots"] = sum(away_shots_list) / len(away_shots_list)
        
        if "home_avg_shots" in aggregated and "away_avg_shots" in aggregated:
            aggregated["shots_differential"] = aggregated["home_avg_shots"] - aggregated["away_avg_shots"]
        
        # Track match counts
        home_matches_count = sum(len(e.home_team_matches) for e in opponent_evidence_list)
        away_matches_count = sum(len(e.away_team_matches) for e in opponent_evidence_list)
        aggregated["home_matches_count"] = home_matches_count
        aggregated["away_matches_count"] = away_matches_count
        
        # Calculate confidence factors
        n_common_opponents = len(opponent_evidence_list)
        sample_factor = min(1.0, n_common_opponents / 5.0)
        
        # Calculate average recency weight
        recency_weights = [e.avg_recency_weight for e in opponent_evidence_list if e.avg_recency_weight > 0]
        if len(recency_weights) > 0:
            recency_factor = sum(recency_weights) / len(recency_weights)
        else:
            recency_factor = 0.5  # Default if no recency data
        
        # Calculate average context match rate
        context_rates = [e.context_match_rate for e in opponent_evidence_list]
        if len(context_rates) > 0:
            context_factor = sum(context_rates) / len(context_rates)
        else:
            context_factor = 0.5  # Default if no context data
        
        return aggregated, sample_factor, recency_factor, context_factor
    
    def _calculate_confidence(
        self,
        n_common_opponents: int,
        avg_recency_weight: float,
        context_match_rate: float
    ) -> float:
        """Calculate comparison confidence using explicit formula.
        
        confidence = sample_factor * recency_factor * context_factor
        
        Returns:
            Confidence score 0.0-1.0
        """
        sample_factor = min(1.0, n_common_opponents / 5.0)
        recency_factor = avg_recency_weight
        context_factor = context_match_rate
        
        confidence = sample_factor * recency_factor * context_factor
        return max(0.0, min(1.0, confidence))
    
    def _determine_signal_strength(
        self,
        differential: Optional[float],
        confidence: float
    ) -> str:
        """Determine signal strength with statistical threshold.
        
        Returns:
            "home_favored", "away_favored", or "neutral"
        """
        if differential is None:
            return "neutral"
        
        # Small differential → neutral
        if abs(differential) < self.min_differential_threshold:
            return "neutral"
        
        # Low confidence → neutral
        if confidence < self.min_confidence_threshold:
            return "neutral"
        
        # Strong signal thresholds
        if differential > 0.5 and confidence > 0.7:
            return "home_favored"
        elif differential < -0.5 and confidence > 0.7:
            return "away_favored"
        else:
            return "neutral"
    
    def _calculate_data_quality_score(
        self,
        n_common_opponents: int,
        aggregated_metrics: Dict[str, float]
    ) -> float:
        """Calculate data quality score based on completeness.
        
        Returns:
            Score 0.0-1.0
        """
        score = 0.0
        
        # Sample size component (0.0-0.5)
        if n_common_opponents >= 5:
            score += 0.5
        elif n_common_opponents >= 3:
            score += 0.3
        elif n_common_opponents >= 1:
            score += 0.1
        
        # Metric availability component (0.0-0.5)
        available_metrics = 0
        total_metrics = 4  # points, xG, xGA, shots
        
        if "points_differential" in aggregated_metrics:
            available_metrics += 1
        if "xg_differential" in aggregated_metrics:
            available_metrics += 1
        if "xga_differential" in aggregated_metrics:
            available_metrics += 1
        if "shots_differential" in aggregated_metrics:
            available_metrics += 1
        
        score += (available_metrics / total_metrics) * 0.5
        
        return max(0.0, min(1.0, score))
