"""Temporal intelligence feature calculations.

This module implements recency weighting, exponential decay, and regime-change
detection for temporal intelligence.

CRITICAL: Manager/Coach Change Data UNAVAILABLE
- No manager tracking in Team model
- No manager_events table
- RegimeChange.detected_by always 'statistical' in current implementation
- Statistical detection uses performance-based shift detection
- External manager events can be integrated in future when provider data available

Data flow:
1. Apply exponential recency weighting to historical matches
2. Calculate weighted form and performance metrics
3. Detect statistical regime changes (performance shifts)
4. Calculate post-regime form if changes detected
5. Return temporal metrics with provenance
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
import math
from scipy import stats  # For t-test in regime detection

from app.features.advanced_team_intelligence import MatchWithStatistics
from app.domain.enums import MatchStatus


@dataclass
class TemporalWeighting:
    """Temporal weighting configuration.
    
    Defines how historical matches are weighted by recency.
    """
    method: str  # "linear", "exponential", "custom"
    decay_factor: Optional[float] = None  # For exponential decay (e.g., 0.95)
    halflife_matches: Optional[int] = None  # Alternative parameterization
    
    def __post_init__(self):
        """Validate configuration."""
        if self.method == "exponential":
            if self.decay_factor is None and self.halflife_matches is None:
                raise ValueError("Exponential weighting requires decay_factor or halflife_matches")
            
            # Calculate decay_factor from halflife if provided
            if self.halflife_matches is not None and self.decay_factor is None:
                self.decay_factor = 0.5 ** (1.0 / self.halflife_matches)


@dataclass
class RegimeChange:
    """Detected regime change event.
    
    Represents a significant shift in team performance/context.
    May be statistical detection OR external event data (future).
    
    CURRENT LIMITATION: Manager/coach change detection UNAVAILABLE
    - No Team.manager field
    - No manager_events table
    - detected_by always 'statistical' in current implementation
    """
    event_type: str  # "statistical_shift", "manager_change" (future), "tactical_shift", etc.
    event_date: datetime
    detected_by: str  # "statistical", "external_data" (future), "manual" (future)
    confidence: float  # 0.0-1.0 (statistical detection has lower confidence)
    description: Optional[str] = None  # Human-readable description
    
    def is_verified_external(self) -> bool:
        """Check if this is a verified external event (not statistical inference).
        
        Returns False in current implementation (no external manager data).
        """
        return self.detected_by in ["external_data", "manual"]


@dataclass
class TemporalIntelligenceMetrics:
    """Temporal intelligence for a team.
    
    Provides recency-weighted performance metrics and regime change detection.
    """
    team_id: str
    
    # Recency-weighted form
    recent_form_weighted: Optional[float] = None  # Weighted points per match
    recent_xg_weighted: Optional[float] = None  # Weighted xG per match
    
    # Trend detection
    form_trend: Optional[str] = None  # "improving", "declining", "stable"
    form_acceleration: Optional[float] = None  # Rate of change (points/match per match)
    
    # Regime changes
    recent_regime_changes: List[RegimeChange] = field(default_factory=list)
    post_regime_form: Optional[float] = None  # Form after most recent regime change
    
    # Temporal snapshots (for walk-forward validation)
    snapshot_timestamp: Optional[datetime] = None
    
    # Provenance
    weighting_config: Optional[TemporalWeighting] = None
    sample_size: int = 0


class TemporalIntelligenceCalculator:
    """Calculate temporally-weighted metrics and detect regime changes.
    
    Implements:
    - Exponential recency weighting (most recent matches weighted more)
    - Statistical regime-change detection (performance shift detection)
    - Form trend analysis (improving/declining/stable)
    - Post-regime form calculation
    
    LIMITATION: Manager/coach change events UNAVAILABLE in current implementation.
    """
    
    def __init__(
        self,
        session,
        weighting: Optional[TemporalWeighting] = None,
        min_matches: int = 5,
        regime_detection_enabled: bool = True
    ):
        """Initialize calculator with weighting configuration.
        
        Args:
            session: Database session (for future repository access)
            weighting: Temporal weighting configuration (default: exponential with 0.95 decay)
            min_matches: Minimum matches for reliable metrics
            regime_detection_enabled: Whether to detect statistical regime changes
        """
        self.session = session
        self.weighting = weighting or TemporalWeighting(method="exponential", decay_factor=0.95)
        self.min_matches = min_matches
        self.regime_detection_enabled = regime_detection_enabled
    
    def calculate_temporal_metrics(
        self,
        team_id: str,
        matches_with_stats: List[MatchWithStatistics],
        before_datetime: Optional[datetime] = None,
        known_regime_changes: Optional[List[RegimeChange]] = None
    ) -> TemporalIntelligenceMetrics:
        """Calculate temporally-weighted metrics.
        
        TEMPORAL VALIDITY: Only uses matches strictly before before_datetime.
        
        Args:
            team_id: Team database ID
            matches_with_stats: List of MatchWithStatistics (chronologically ordered)
            before_datetime: Only use matches before this timestamp (temporal validity)
            known_regime_changes: Optional list of externally-verified regime changes (future)
            
        Returns:
            TemporalIntelligenceMetrics with weighted values
            
        Algorithm:
            1. Filter matches before_datetime if specified (temporal validity)
            2. Apply temporal weighting (exponential decay from most recent)
            3. Calculate weighted form metrics (points, xG)
            4. Detect form trend (improving/declining/stable)
            5. Calculate form acceleration (rate of change)
            6. Detect statistical regime changes if enabled
            7. Combine with known_regime_changes if provided (future)
            8. Calculate post-regime form if changes detected
            9. Return metrics with provenance
        """
        # 1. Filter to finished matches only
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
            return TemporalIntelligenceMetrics(
                team_id=team_id,
                sample_size=len(finished_matches),
                weighting_config=self.weighting,
                snapshot_timestamp=before_datetime
            )
        
        # 2-3. Apply temporal weighting and calculate weighted metrics
        weighted_metrics = self._calculate_weighted_metrics(team_id, finished_matches)
        
        # 4-5. Detect form trend and acceleration
        form_trend, form_acceleration = self._detect_form_trend(team_id, finished_matches)
        
        # 6-7. Detect regime changes
        regime_changes = []
        if self.regime_detection_enabled:
            statistical_changes = self.detect_regime_changes(team_id, finished_matches)
            regime_changes.extend(statistical_changes)
        
        # Combine with known regime changes (future capability)
        if known_regime_changes:
            regime_changes.extend(known_regime_changes)
        
        # Sort by date (most recent first)
        regime_changes.sort(key=lambda rc: rc.event_date, reverse=True)
        
        # 8. Calculate post-regime form if changes detected
        post_regime_form = None
        if regime_changes and len(regime_changes) > 0:
            most_recent_change = regime_changes[0]
            post_regime_form = self._calculate_post_regime_form(
                team_id, 
                finished_matches, 
                most_recent_change.event_date
            )
        
        # 9. Return metrics with provenance
        return TemporalIntelligenceMetrics(
            team_id=team_id,
            recent_form_weighted=weighted_metrics.get('form_weighted'),
            recent_xg_weighted=weighted_metrics.get('xg_weighted'),
            form_trend=form_trend,
            form_acceleration=form_acceleration,
            recent_regime_changes=regime_changes,
            post_regime_form=post_regime_form,
            snapshot_timestamp=before_datetime,
            weighting_config=self.weighting,
            sample_size=len(finished_matches)
        )
    
    def detect_regime_changes(
        self,
        team_id: str,
        matches_with_stats: List[MatchWithStatistics],
        min_matches_before: int = 5,
        min_matches_after: int = 3,
        significance_threshold: float = 0.05
    ) -> List[RegimeChange]:
        """Detect potential regime changes from performance shifts.
        
        STATISTICAL DETECTION ONLY - does not know actual manager changes.
        Uses sliding window to detect significant performance shifts.
        
        CRITICAL: Manager/coach change detection UNAVAILABLE
        - No external manager event data
        - detected_by always 'statistical'
        - Cannot determine cause of performance shift
        
        Algorithm:
            1. Sliding window over match history
            2. For each potential changepoint (between min_before and min_after):
               a. Split matches into before/after
               b. Calculate performance metrics (points/match) for each period
               c. Apply t-test to detect significant difference
            3. If significant shift detected:
               a. Create RegimeChange with detected_by="statistical"
               b. Confidence based on statistical significance level
               c. event_type = "statistical_shift" (cannot determine cause)
            4. Return list of detected changes
        
        Args:
            team_id: Team database ID
            matches_with_stats: List of MatchWithStatistics (chronologically ordered)
            min_matches_before: Minimum matches in "before" period
            min_matches_after: Minimum matches in "after" period
            significance_threshold: P-value threshold (default 0.05)
        
        Returns:
            List of statistically-detected RegimeChange events
            
        Notes:
            - These are INFERRED changes, not ground truth
            - Lower confidence than external manager-change data
            - Should be validated in backtesting before production use
            - Cannot distinguish manager change from other causes (injuries, tactics, etc.)
        """
        detected_changes = []
        
        # Need enough matches for both periods
        if len(matches_with_stats) < min_matches_before + min_matches_after:
            return detected_changes
        
        # Extract points for each match
        match_points = self._extract_match_points(team_id, matches_with_stats)
        
        # Try different changepoints (sliding window)
        for changepoint_idx in range(min_matches_before, len(match_points) - min_matches_after + 1):
            # Split into before/after periods
            before_points = match_points[:changepoint_idx]
            after_points = match_points[changepoint_idx:]
            
            # Skip if insufficient data in either period
            if len(before_points) < min_matches_before or len(after_points) < min_matches_after:
                continue
            
            # Perform t-test to detect significant difference
            t_statistic, p_value = stats.ttest_ind(before_points, after_points)
            
            # Check if difference is significant
            if p_value < significance_threshold:
                # Calculate confidence based on significance level
                confidence = 1.0 - p_value
                
                # Determine if performance improved or declined
                mean_before = sum(before_points) / len(before_points)
                mean_after = sum(after_points) / len(after_points)
                
                if mean_after > mean_before:
                    description = f"Statistical improvement detected: {mean_before:.2f} → {mean_after:.2f} points/match"
                else:
                    description = f"Statistical decline detected: {mean_before:.2f} → {mean_after:.2f} points/match"
                
                # Get changepoint date (match after split point)
                changepoint_match = matches_with_stats[changepoint_idx]
                event_date = changepoint_match.match.scheduled_at
                
                # Create RegimeChange
                regime_change = RegimeChange(
                    event_type="statistical_shift",
                    event_date=event_date,
                    detected_by="statistical",  # ALWAYS statistical in current implementation
                    confidence=min(confidence, 0.85),  # Cap at 0.85 for statistical detection
                    description=description
                )
                
                detected_changes.append(regime_change)
                
                # Only detect most significant change (earliest with p < threshold)
                break
        
        return detected_changes
    
    def _calculate_weighted_metrics(
        self, 
        team_id: str, 
        matches_with_stats: List[MatchWithStatistics]
    ) -> dict:
        """Calculate recency-weighted metrics using configured weighting.
        
        Applies exponential decay: most recent match has weight 1.0,
        previous match has weight decay_factor, etc.
        
        Args:
            team_id: Team identifier
            matches_with_stats: List of matches (chronologically ordered, oldest first)
            
        Returns:
            Dictionary with weighted metrics
        """
        if self.weighting.method != "exponential":
            # Only exponential weighting implemented currently
            return {}
        
        num_matches = len(matches_with_stats)
        if num_matches == 0:
            return {}
        
        # Calculate weights (exponential decay from most recent)
        weights = []
        total_weight = 0.0
        for i in range(num_matches):
            # Most recent match (last in list) has weight = 1.0
            # Earlier matches have progressively lower weights
            matches_back = num_matches - 1 - i
            weight = self.weighting.decay_factor ** matches_back
            weights.append(weight)
            total_weight += weight
        
        # Calculate weighted form (points per match)
        weighted_points_total = 0.0
        weighted_xg_total = 0.0
        xg_weight_total = 0.0
        
        for i, mws in enumerate(matches_with_stats):
            weight = weights[i]
            
            # Calculate points for this match
            points = self._calculate_match_points(team_id, mws)
            weighted_points_total += points * weight
            
            # Calculate xG if available
            team_stats = mws.get_team_statistics(team_id)
            if team_stats is not None and team_stats.xg is not None:
                weighted_xg_total += team_stats.xg * weight
                xg_weight_total += weight
        
        # Calculate weighted averages
        metrics = {}
        if total_weight > 0:
            metrics['form_weighted'] = weighted_points_total / total_weight
        
        if xg_weight_total > 0:
            metrics['xg_weighted'] = weighted_xg_total / xg_weight_total
        
        return metrics
    
    def _detect_form_trend(
        self, 
        team_id: str, 
        matches_with_stats: List[MatchWithStatistics]
    ) -> tuple[Optional[str], Optional[float]]:
        """Detect form trend (improving/declining/stable) and acceleration.
        
        Uses linear regression over recent matches to detect trend.
        
        Args:
            team_id: Team identifier
            matches_with_stats: List of matches (chronologically ordered)
            
        Returns:
            Tuple of (form_trend: "improving"/"declining"/"stable", form_acceleration: float)
        """
        if len(matches_with_stats) < self.min_matches:
            return None, None
        
        # Extract points for each match
        match_points = self._extract_match_points(team_id, matches_with_stats)
        
        # Perform linear regression: y = ax + b
        # x = match index (0, 1, 2, ..., n-1)
        # y = points
        n = len(match_points)
        x_values = list(range(n))
        
        # Calculate slope (acceleration)
        x_mean = sum(x_values) / n
        y_mean = sum(match_points) / n
        
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, match_points))
        denominator = sum((x - x_mean) ** 2 for x in x_values)
        
        if denominator == 0:
            return "stable", 0.0
        
        slope = numerator / denominator  # Points per match per match
        
        # Classify trend based on slope
        # Threshold: >0.1 points/match per match = improving
        #           <-0.1 points/match per match = declining
        if slope > 0.1:
            form_trend = "improving"
        elif slope < -0.1:
            form_trend = "declining"
        else:
            form_trend = "stable"
        
        return form_trend, slope
    
    def _calculate_post_regime_form(
        self, 
        team_id: str, 
        matches_with_stats: List[MatchWithStatistics],
        regime_change_date: datetime
    ) -> Optional[float]:
        """Calculate form after most recent regime change.
        
        Args:
            team_id: Team identifier
            matches_with_stats: All matches
            regime_change_date: Date of regime change
            
        Returns:
            Points per match after regime change, or None if insufficient data
        """
        # Filter to matches after regime change
        post_regime_matches = [
            mws for mws in matches_with_stats
            if mws.match.scheduled_at >= regime_change_date
        ]
        
        if len(post_regime_matches) < 3:  # Need at least 3 matches
            return None
        
        # Calculate average points
        total_points = 0.0
        for mws in post_regime_matches:
            total_points += self._calculate_match_points(team_id, mws)
        
        return total_points / len(post_regime_matches)
    
    def _extract_match_points(
        self, 
        team_id: str, 
        matches_with_stats: List[MatchWithStatistics]
    ) -> List[float]:
        """Extract points from each match for team.
        
        Args:
            team_id: Team identifier
            matches_with_stats: List of matches
            
        Returns:
            List of points (3.0 for win, 1.0 for draw, 0.0 for loss)
        """
        points = []
        for mws in matches_with_stats:
            points.append(self._calculate_match_points(team_id, mws))
        return points
    
    def _calculate_match_points(
        self, 
        team_id: str, 
        mws: MatchWithStatistics
    ) -> float:
        """Calculate points for team in a match.
        
        Args:
            team_id: Team identifier
            mws: MatchWithStatistics
            
        Returns:
            Points (3.0 for win, 1.0 for draw, 0.0 for loss)
        """
        match = mws.match
        
        # Check if scores available
        if match.home_score is None or match.away_score is None:
            return 0.0
        
        # Determine team's score and opponent's score
        if mws.is_home_team(team_id):
            team_score = match.home_score
            opponent_score = match.away_score
        else:
            team_score = match.away_score
            opponent_score = match.home_score
        
        # Calculate points
        if team_score > opponent_score:
            return 3.0
        elif team_score == opponent_score:
            return 1.0
        else:
            return 0.0
