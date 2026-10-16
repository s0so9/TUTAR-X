"""Team form feature calculations.

This module calculates recent form metrics based on the most recent matches.
All calculations are deterministic and respect chronological ordering.
"""

from typing import Dict, Optional
from app.features.base import FeatureCalculator, MatchContext, TeamHistoricalData


class FormCalculator(FeatureCalculator):
    """Calculate team form features based on recent matches.
    
    Form metrics:
    - Recent wins (last N matches)
    - Recent draws
    - Recent losses
    - Recent goals scored
    - Recent goals conceded
    - Recent points
    - Recent average goals scored
    - Recent average goals conceded
    """
    
    def __init__(self, recent_matches: int = 5, min_matches: int = 3):
        """Initialize calculator.
        
        Args:
            recent_matches: Number of recent matches to consider for form
            min_matches: Minimum matches required for calculations
        """
        self.recent_matches = recent_matches
        self.min_matches = min_matches
    
    def calculate(self, context: MatchContext) -> Dict[str, Optional[float]]:
        """Calculate form features for both teams.
        
        Returns features for home and away teams with prefixes.
        Returns None for features where insufficient data exists.
        """
        features = {}
        
        # Home team form
        home_features = self._calculate_team_form(
            context.home_team_history,
            prefix="home_"
        )
        features.update(home_features)
        
        # Away team form
        away_features = self._calculate_team_form(
            context.away_team_history,
            prefix="away_"
        )
        features.update(away_features)
        
        return features
    
    def _calculate_team_form(
        self,
        team_history: TeamHistoricalData,
        prefix: str = ""
    ) -> Dict[str, Optional[float]]:
        """Calculate form features for a single team.
        
        Args:
            team_history: Historical match data for the team
            prefix: Prefix for feature names (e.g., "home_", "away_")
            
        Returns:
            Dictionary of form features
        """
        # Get all finished matches for match count
        finished_matches = team_history.get_finished_matches()
        match_count = len(finished_matches)
        
        # Get recent finished matches
        recent = team_history.get_recent_matches(self.recent_matches)
        
        # Check if we have sufficient data
        if len(recent) < self.min_matches:
            return {
                f"{prefix}recent_wins": None,
                f"{prefix}recent_draws": None,
                f"{prefix}recent_losses": None,
                f"{prefix}recent_goals_scored": None,
                f"{prefix}recent_goals_conceded": None,
                f"{prefix}recent_points": None,
                f"{prefix}recent_avg_goals_scored": None,
                f"{prefix}recent_avg_goals_conceded": None,
                f"{prefix}form_points_per_match": None,
                f"{prefix}match_count": float(match_count),  # Always include match count even when insufficient
                # NOTE: Do NOT override goals_scored_avg/goals_conceded_avg here
                # TeamStrengthCalculator may have already set these with fallback values
                f"{prefix}form_score": None,
                f"{prefix}form_matches_used": float(len(recent)),  # Number of matches attempted
            }
        
        team_id = team_history.team_id
        
        # Calculate form metrics
        wins = self.calculate_wins(recent, team_id)
        draws = self.calculate_draws(recent, team_id)
        losses = self.calculate_losses(recent, team_id)
        goals_scored = self.calculate_goals_scored(recent, team_id)
        goals_conceded = self.calculate_goals_conceded(recent, team_id)
        points = self.calculate_points(recent, team_id)
        
        num_matches = len(recent)
        avg_goals_scored = goals_scored / num_matches
        avg_goals_conceded = goals_conceded / num_matches
        points_per_match = points / num_matches
        
        return {
            f"{prefix}recent_wins": float(wins),
            f"{prefix}recent_draws": float(draws),
            f"{prefix}recent_losses": float(losses),
            f"{prefix}recent_goals_scored": float(goals_scored),
            f"{prefix}recent_goals_conceded": float(goals_conceded),
            f"{prefix}recent_points": float(points),
            f"{prefix}recent_avg_goals_scored": avg_goals_scored,
            f"{prefix}recent_avg_goals_conceded": avg_goals_conceded,
            f"{prefix}form_points_per_match": points_per_match,
            f"{prefix}match_count": float(match_count),
            # Aliases for model compatibility
            f"{prefix}goals_scored_avg": avg_goals_scored,  # Alias for Poisson/Dixon-Coles/NegBin
            f"{prefix}goals_conceded_avg": avg_goals_conceded,  # Alias for defensive metrics
            f"{prefix}form_score": points_per_match,  # Alias for form-adjusted model
            f"{prefix}form_matches_used": float(len(recent)),  # Number of matches in form calculation
        }
    
    def calculate_form_string(self, team_history: TeamHistoricalData, n: int = 5) -> Optional[str]:
        """Generate form string (e.g., "WWDLW") for recent matches.
        
        Args:
            team_history: Historical match data
            n: Number of recent matches to include
            
        Returns:
            Form string or None if insufficient data
        """
        from app.domain.enums import MatchOutcome
        
        recent = team_history.get_recent_matches(n)
        
        if len(recent) < self.min_matches:
            return None
        
        team_id = team_history.team_id
        form_chars = []
        
        for match in recent:
            if match.home_team_id == team_id:
                if match.outcome == MatchOutcome.HOME_WIN:
                    form_chars.append("W")
                elif match.outcome == MatchOutcome.DRAW:
                    form_chars.append("D")
                elif match.outcome == MatchOutcome.AWAY_WIN:
                    form_chars.append("L")
            elif match.away_team_id == team_id:
                if match.outcome == MatchOutcome.AWAY_WIN:
                    form_chars.append("W")
                elif match.outcome == MatchOutcome.DRAW:
                    form_chars.append("D")
                elif match.outcome == MatchOutcome.HOME_WIN:
                    form_chars.append("L")
        
        return "".join(form_chars)
    
    def calculate_win_rate(self, team_history: TeamHistoricalData) -> Optional[float]:
        """Calculate win rate from all finished matches.
        
        Args:
            team_history: Historical match data
            
        Returns:
            Win rate (0.0 to 1.0) or None if insufficient data
        """
        finished = team_history.get_finished_matches()
        
        if len(finished) < self.min_matches:
            return None
        
        wins = self.calculate_wins(finished, team_history.team_id)
        return wins / len(finished)
    
    def calculate_draw_rate(self, team_history: TeamHistoricalData) -> Optional[float]:
        """Calculate draw rate from all finished matches.
        
        Args:
            team_history: Historical match data
            
        Returns:
            Draw rate (0.0 to 1.0) or None if insufficient data
        """
        finished = team_history.get_finished_matches()
        
        if len(finished) < self.min_matches:
            return None
        
        draws = self.calculate_draws(finished, team_history.team_id)
        return draws / len(finished)
    
    def calculate_loss_rate(self, team_history: TeamHistoricalData) -> Optional[float]:
        """Calculate loss rate from all finished matches.
        
        Args:
            team_history: Historical match data
            
        Returns:
            Loss rate (0.0 to 1.0) or None if insufficient data
        """
        finished = team_history.get_finished_matches()
        
        if len(finished) < self.min_matches:
            return None
        
        losses = self.calculate_losses(finished, team_history.team_id)
        return losses / len(finished)
