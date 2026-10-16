"""Team strength feature calculations.

This module calculates team strength metrics based on historical performance.
All calculations are deterministic and based on actual match results.
"""

from typing import Dict, Optional, List
from app.features.base import FeatureCalculator, MatchContext, TeamHistoricalData
from app.domain.match import Match


class TeamStrengthCalculator(FeatureCalculator):
    """Calculate team strength features.
    
    Metrics:
    - Attack strength: Goals scored per match
    - Defense strength: Goals conceded per match (lower is better)
    - Home strength: Performance in home matches
    - Away strength: Performance in away matches
    - Goal scoring rate: Average goals scored
    - Goal conceding rate: Average goals conceded
    """
    
    def __init__(self, min_matches: int = 3):
        """Initialize calculator.
        
        Args:
            min_matches: Minimum matches required for calculations
        """
        self.min_matches = min_matches
    
    def calculate(self, context: MatchContext) -> Dict[str, Optional[float]]:
        """Calculate team strength features for both teams.
        
        Returns features for home and away teams with prefixes.
        Returns None for features where insufficient data exists.
        """
        features = {}
        
        # Home team strength
        home_features = self._calculate_team_strength(
            context.home_team_history,
            prefix="home_"
        )
        features.update(home_features)
        
        # Away team strength
        away_features = self._calculate_team_strength(
            context.away_team_history,
            prefix="away_"
        )
        features.update(away_features)
        
        return features
    
    def _calculate_team_strength(
        self,
        team_history: TeamHistoricalData,
        prefix: str = ""
    ) -> Dict[str, Optional[float]]:
        """Calculate strength features for a single team.
        
        Args:
            team_history: Historical match data for the team
            prefix: Prefix for feature names (e.g., "home_", "away_")
            
        Returns:
            Dictionary of strength features
        """
        finished_matches = team_history.get_finished_matches()
        
        # Check if we have sufficient data
        if len(finished_matches) < self.min_matches:
            # INSUFFICIENT DATA: Return None to indicate missing team strength data
            # This prevents fabrication of statistics and forces models to handle uncertainty
            # The prediction system should use league averages or other appropriate priors
            return {
                f"{prefix}attack_strength": None,
                f"{prefix}defense_strength": None,
                f"{prefix}home_strength": None,
                f"{prefix}away_strength": None,
                f"{prefix}goal_scoring_rate": None,
                f"{prefix}goal_conceding_rate": None,
                # PoissonModel-compatible feature names also set to None
                f"{prefix}goals_scored_avg": None,
                f"{prefix}goals_conceded_avg": None,
            }
        
        team_id = team_history.team_id
        
        # Overall attack and defense
        goals_scored = self.calculate_goals_scored(finished_matches, team_id)
        goals_conceded = self.calculate_goals_conceded(finished_matches, team_id)
        num_matches = len(finished_matches)
        
        attack_strength = goals_scored / num_matches
        defense_strength = goals_conceded / num_matches
        
        # Home/away splits
        home_matches = [m for m in finished_matches if m.home_team_id == team_id]
        away_matches = [m for m in finished_matches if m.away_team_id == team_id]
        
        home_strength = self._calculate_venue_strength(home_matches, team_id)
        away_strength = self._calculate_venue_strength(away_matches, team_id)
        
        return {
            f"{prefix}attack_strength": attack_strength,
            f"{prefix}defense_strength": defense_strength,
            f"{prefix}home_strength": home_strength,
            f"{prefix}away_strength": away_strength,
            f"{prefix}goal_scoring_rate": attack_strength,  # Same as attack strength
            f"{prefix}goal_conceding_rate": defense_strength,  # Same as defense strength
            # Add PoissonModel-compatible feature names
            f"{prefix}goals_scored_avg": attack_strength,
            f"{prefix}goals_conceded_avg": defense_strength,
        }
    
    def _calculate_venue_strength(self, matches: List[Match], team_id: str) -> Optional[float]:
        """Calculate strength for home or away matches.
        
        Strength is calculated as points per match.
        3 points for win, 1 for draw, 0 for loss.
        
        Returns None if no matches available.
        """
        if not matches:
            return None
        
        points = self.calculate_points(matches, team_id)
        return points / len(matches)
    
    def calculate_home_attack_strength(self, team_history: TeamHistoricalData) -> Optional[float]:
        """Calculate attack strength specifically for home matches.
        
        Args:
            team_history: Historical match data
            
        Returns:
            Goals per home match, or None if insufficient data
        """
        home_matches = team_history.get_home_matches()
        finished_home = [m for m in home_matches if m.home_score is not None]
        
        if len(finished_home) < self.min_matches:
            return None
        
        goals = self.calculate_goals_scored(finished_home, team_history.team_id)
        return goals / len(finished_home)
    
    def calculate_away_attack_strength(self, team_history: TeamHistoricalData) -> Optional[float]:
        """Calculate attack strength specifically for away matches.
        
        Args:
            team_history: Historical match data
            
        Returns:
            Goals per away match, or None if insufficient data
        """
        away_matches = team_history.get_away_matches()
        finished_away = [m for m in away_matches if m.away_score is not None]
        
        if len(finished_away) < self.min_matches:
            return None
        
        goals = self.calculate_goals_scored(finished_away, team_history.team_id)
        return goals / len(finished_away)
    
    def calculate_home_defense_strength(self, team_history: TeamHistoricalData) -> Optional[float]:
        """Calculate defense strength specifically for home matches.
        
        Args:
            team_history: Historical match data
            
        Returns:
            Goals conceded per home match, or None if insufficient data
        """
        home_matches = team_history.get_home_matches()
        finished_home = [m for m in home_matches if m.away_score is not None]
        
        if len(finished_home) < self.min_matches:
            return None
        
        goals = self.calculate_goals_conceded(finished_home, team_history.team_id)
        return goals / len(finished_home)
    
    def calculate_away_defense_strength(self, team_history: TeamHistoricalData) -> Optional[float]:
        """Calculate defense strength specifically for away matches.
        
        Args:
            team_history: Historical match data
            
        Returns:
            Goals conceded per away match, or None if insufficient data
        """
        away_matches = team_history.get_away_matches()
        finished_away = [m for m in away_matches if m.home_score is not None]
        
        if len(finished_away) < self.min_matches:
            return None
        
        goals = self.calculate_goals_conceded(finished_away, team_history.team_id)
        return goals / len(finished_away)
