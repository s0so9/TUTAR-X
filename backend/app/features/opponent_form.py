"""Opponent-adjusted form calculator with strength-of-schedule weighting.

This module calculates team form metrics that account for opponent strength,
providing a more nuanced assessment than raw win/loss records.
"""

import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from app.database.models import Match
from app.domain.enums import MatchOutcome


class OpponentAdjustedFormCalculator:
    """Calculate opponent-adjusted form scores with time decay.
    
    Features:
    - Time-decayed weighting: recent matches weighted more heavily
    - Strength-of-schedule adjustment: performance against strong opponents valued more
    - Returns normalized form scores in [-1, 1] range
    - Handles insufficient data explicitly (returns None)
    
    Opponent strength proxy uses goals scored/conceded ratio or Elo if available.
    """
    
    def __init__(
        self,
        time_decay_rate: float = 0.1,
        min_matches: int = 3
    ):
        """Initialize calculator.
        
        Args:
            time_decay_rate: Exponential decay rate for time weighting (default: 0.1)
            min_matches: Minimum matches required for valid calculation (default: 3)
        """
        self.time_decay_rate = time_decay_rate
        self.min_matches = min_matches
    
    def calculate(
        self,
        home_matches: List[Match],
        away_matches: List[Match],
        home_team_id: str,
        away_team_id: str,
        reference_date: datetime,
        elo_ratings: Optional[Dict[str, float]] = None
    ) -> Dict[str, Optional[float]]:
        """Calculate opponent-adjusted form scores for both teams.
        
        Args:
            home_matches: Historical matches for home team (chronologically ordered)
            away_matches: Historical matches for away team (chronologically ordered)
            home_team_id: Home team identifier
            away_team_id: Away team identifier
            reference_date: Date to calculate form relative to (usually match date)
            elo_ratings: Optional Elo ratings dict for opponent strength estimation
        
        Returns:
            Dict with:
                - home_form_score: float in [-1, 1] or None
                - away_form_score: float in [-1, 1] or None
                - home_form_matches_used: int
                - away_form_matches_used: int
        """
        home_score = self._calculate_team_form(
            home_matches,
            home_team_id,
            reference_date,
            elo_ratings
        )
        
        away_score = self._calculate_team_form(
            away_matches,
            away_team_id,
            reference_date,
            elo_ratings
        )
        
        return {
            "home_form_score": home_score[0] if home_score else None,
            "away_form_score": away_score[0] if away_score else None,
            "home_form_matches_used": home_score[1] if home_score else 0,
            "away_form_matches_used": away_score[1] if away_score else 0,
        }
    
    def _calculate_team_form(
        self,
        matches: List[Match],
        team_id: str,
        reference_date: datetime,
        elo_ratings: Optional[Dict[str, float]] = None
    ) -> Optional[Tuple[float, int]]:
        """Calculate form score for a single team.
        
        Args:
            matches: Historical matches for the team
            team_id: Team identifier
            reference_date: Reference date for form calculation
            elo_ratings: Optional Elo ratings for opponent strength
        
        Returns:
            (form_score, matches_used) or None if insufficient data
        """
        # Filter matches before reference date
        past_matches = [
            m for m in matches
            if m.scheduled_at < reference_date and m.outcome is not None
        ]
        
        if len(past_matches) < self.min_matches:
            return None
        
        # Take most recent matches
        recent_matches = past_matches[-20:]  # Consider up to 20 recent matches
        
        weighted_sum = 0.0
        weight_sum = 0.0
        
        for match in recent_matches:
            # Calculate time weight (exponential decay)
            days_ago = (reference_date - match.scheduled_at).days
            time_weight = math.exp(-self.time_decay_rate * days_ago / 30.0)  # decay per 30 days
            
            # Determine match result from team perspective
            match_points = self._get_match_points(match, team_id)
            
            # Estimate opponent strength
            opponent_id = (
                match.away_team_id if match.home_team_id == team_id
                else match.home_team_id
            )
            opponent_strength = self._estimate_opponent_strength(
                opponent_id,
                matches,
                elo_ratings
            )
            
            # Strength adjustment: performance against strong opponents weighted more
            # opponent_strength ranges from ~0.5 to ~1.5 (normalized)
            strength_multiplier = 0.5 + (opponent_strength * 0.5)
            
            # Combined weight
            total_weight = time_weight * strength_multiplier
            
            # Accumulate weighted score
            weighted_sum += match_points * total_weight
            weight_sum += total_weight
        
        if weight_sum == 0:
            return None
        
        # Calculate average weighted points (ranges from 0 to 3)
        avg_weighted_points = weighted_sum / weight_sum
        
        # Normalize to [-1, 1] range
        # 0 points = -1 (all losses)
        # 1.5 points = 0 (balanced)
        # 3 points = +1 (all wins)
        form_score = (avg_weighted_points - 1.5) / 1.5
        form_score = max(-1.0, min(1.0, form_score))  # Clamp to [-1, 1]
        
        return (form_score, len(recent_matches))
    
    def _get_match_points(self, match: Match, team_id: str) -> float:
        """Get points earned by team in this match.
        
        Args:
            match: Match object
            team_id: Team identifier
        
        Returns:
            3.0 for win, 1.0 for draw, 0.0 for loss
        """
        if match.outcome is None:
            return 1.0  # Default to draw if outcome unknown
        
        is_home = match.home_team_id == team_id
        
        if match.outcome == MatchOutcome.DRAW:
            return 1.0
        elif match.outcome == MatchOutcome.HOME_WIN:
            return 3.0 if is_home else 0.0
        elif match.outcome == MatchOutcome.AWAY_WIN:
            return 0.0 if is_home else 3.0
        else:
            return 1.0  # Unknown outcome
    
    def _estimate_opponent_strength(
        self,
        opponent_id: str,
        all_matches: List[Match],
        elo_ratings: Optional[Dict[str, float]] = None
    ) -> float:
        """Estimate opponent strength for weighting.
        
        Args:
            opponent_id: Opponent team identifier
            all_matches: All matches for context
            elo_ratings: Optional Elo ratings
        
        Returns:
            Strength estimate (0.5 = weak, 1.0 = average, 1.5 = strong)
        """
        # If Elo available, use that
        if elo_ratings and opponent_id in elo_ratings:
            opponent_elo = elo_ratings[opponent_id]
            # Normalize Elo: 1400 = weak (0.5), 1500 = average (1.0), 1600 = strong (1.5)
            return 0.5 + (opponent_elo - 1400) / 200.0
        
        # Fallback: estimate from goals scored/conceded ratio in recent matches
        opponent_matches = [
            m for m in all_matches
            if (m.home_team_id == opponent_id or m.away_team_id == opponent_id)
            and m.home_score is not None and m.away_score is not None
        ]
        
        if len(opponent_matches) < 3:
            return 1.0  # Default to average strength
        
        # Calculate goal differential
        total_goals_scored = 0
        total_goals_conceded = 0
        
        for match in opponent_matches[-10:]:  # Recent 10 matches
            if match.home_team_id == opponent_id:
                total_goals_scored += match.home_score
                total_goals_conceded += match.away_score
            else:
                total_goals_scored += match.away_score
                total_goals_conceded += match.home_score
        
        # Calculate strength from goal ratio
        if total_goals_conceded == 0:
            goal_ratio = 2.0  # Very strong defense
        else:
            goal_ratio = total_goals_scored / total_goals_conceded
        
        # Map goal ratio to strength: 0.5 = weak, 1.0 = average (1.0 ratio), 2.0 = strong
        # ratio < 0.75 = weak
        # ratio 0.75-1.25 = average
        # ratio > 1.25 = strong
        if goal_ratio < 0.75:
            strength = 0.5 + (goal_ratio / 0.75) * 0.25  # 0.5 to 0.75
        elif goal_ratio > 1.25:
            strength = 1.0 + min((goal_ratio - 1.0) / 2.0, 0.5)  # 1.0 to 1.5
        else:
            strength = 0.75 + (goal_ratio - 0.75) / 0.5 * 0.25  # 0.75 to 1.0
        
        return max(0.5, min(1.5, strength))
