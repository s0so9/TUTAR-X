"""Base classes and utilities for feature engineering.

This module provides the foundation for all feature engineering calculations.
All features must be deterministic and based on historical data only.
"""

from typing import List, Dict, Optional
from datetime import datetime
from dataclasses import dataclass

from app.domain.match import Match
from app.domain.statistics import Standing


@dataclass
class TeamHistoricalData:
    """Container for team's historical match data.
    
    Used for feature calculations. Contains only matches that occurred
    before the target match to prevent data leakage.
    """
    
    team_id: str
    matches: List[Match]  # Chronologically ordered, oldest first
    standings: Optional[Standing] = None
    
    def get_home_matches(self) -> List[Match]:
        """Get matches where team was home team."""
        return [m for m in self.matches if m.home_team_id == self.team_id]
    
    def get_away_matches(self) -> List[Match]:
        """Get matches where team was away team."""
        return [m for m in self.matches if m.away_team_id == self.team_id]
    
    def get_finished_matches(self) -> List[Match]:
        """Get only finished matches (exclude scheduled/live)."""
        from app.domain.enums import MatchStatus
        return [m for m in self.matches if m.status == MatchStatus.FINISHED]
    
    def get_recent_matches(self, n: int) -> List[Match]:
        """Get n most recent finished matches, chronologically ordered."""
        finished = self.get_finished_matches()
        return finished[-n:] if len(finished) >= n else finished


@dataclass
class MatchContext:
    """Context for a specific match feature calculation.
    
    Contains all historical data available before the match kickoff.
    Ensures no data leakage by only including prior information.
    """
    
    match_id: str
    home_team_id: str
    away_team_id: str
    scheduled_at: datetime
    competition_id: str
    season_id: str
    
    home_team_history: TeamHistoricalData
    away_team_history: TeamHistoricalData
    
    @property
    def has_sufficient_home_data(self, min_matches: int = 3) -> bool:
        """Check if home team has sufficient historical data."""
        return len(self.home_team_history.get_finished_matches()) >= min_matches
    
    @property
    def has_sufficient_away_data(self, min_matches: int = 3) -> bool:
        """Check if away team has sufficient historical data."""
        return len(self.away_team_history.get_finished_matches()) >= min_matches


class FeatureCalculator:
    """Base class for feature calculators.
    
    All feature calculators must:
    1. Be deterministic (same inputs → same outputs)
    2. Only use historical data (no future information)
    3. Handle insufficient data gracefully (return None or raise)
    4. Provide clear mathematical definitions
    """
    
    def calculate(self, context: MatchContext) -> Dict[str, Optional[float]]:
        """Calculate features for a match context.
        
        Args:
            context: Match context with historical data
            
        Returns:
            Dictionary mapping feature names to values.
            None values indicate insufficient data.
        """
        raise NotImplementedError("Subclasses must implement calculate()")
    
    @staticmethod
    def safe_divide(numerator: float, denominator: float, default: Optional[float] = None) -> Optional[float]:
        """Safely divide, returning default if denominator is zero."""
        if denominator == 0:
            return default
        return numerator / denominator
    
    @staticmethod
    def calculate_goals_scored(matches: List[Match], team_id: str) -> int:
        """Calculate total goals scored by team in given matches."""
        goals = 0
        for match in matches:
            if match.home_team_id == team_id and match.home_score is not None:
                goals += match.home_score
            elif match.away_team_id == team_id and match.away_score is not None:
                goals += match.away_score
        return goals
    
    @staticmethod
    def calculate_goals_conceded(matches: List[Match], team_id: str) -> int:
        """Calculate total goals conceded by team in given matches."""
        goals = 0
        for match in matches:
            if match.home_team_id == team_id and match.away_score is not None:
                goals += match.away_score
            elif match.away_team_id == team_id and match.home_score is not None:
                goals += match.home_score
        return goals
    
    @staticmethod
    def calculate_wins(matches: List[Match], team_id: str) -> int:
        """Calculate number of wins for team in given matches."""
        from app.domain.enums import MatchOutcome
        wins = 0
        for match in matches:
            if match.home_team_id == team_id and match.outcome == MatchOutcome.HOME_WIN:
                wins += 1
            elif match.away_team_id == team_id and match.outcome == MatchOutcome.AWAY_WIN:
                wins += 1
        return wins
    
    @staticmethod
    def calculate_draws(matches: List[Match], team_id: str) -> int:
        """Calculate number of draws for team in given matches."""
        from app.domain.enums import MatchOutcome
        return sum(1 for match in matches if match.outcome == MatchOutcome.DRAW)
    
    @staticmethod
    def calculate_losses(matches: List[Match], team_id: str) -> int:
        """Calculate number of losses for team in given matches."""
        from app.domain.enums import MatchOutcome
        losses = 0
        for match in matches:
            if match.home_team_id == team_id and match.outcome == MatchOutcome.AWAY_WIN:
                losses += 1
            elif match.away_team_id == team_id and match.outcome == MatchOutcome.HOME_WIN:
                losses += 1
        return losses
    
    @staticmethod
    def calculate_points(matches: List[Match], team_id: str) -> int:
        """Calculate total points (3 per win, 1 per draw) in given matches."""
        wins = FeatureCalculator.calculate_wins(matches, team_id)
        draws = FeatureCalculator.calculate_draws(matches, team_id)
        return (wins * 3) + (draws * 1)
