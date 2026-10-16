"""Team form feature calculations."""

from typing import List
from dataclasses import dataclass
from datetime import datetime

from app.database.models import Match as MatchDB
from app.domain.enums import MatchOutcome
from app.features.base import FeatureCalculator


@dataclass
class TeamFormFeatures:
    """Team form metrics based on recent results."""
    
    team_id: str
    
    # Recent results
    last_n_results: List[str]  # ['W', 'D', 'L', ...]
    wins: int = 0
    draws: int = 0
    losses: int = 0
    
    # Goals
    goals_scored: int = 0
    goals_conceded: int = 0
    
    # Home/away splits (if enough data)
    home_wins: int = 0
    home_draws: int = 0
    home_losses: int = 0
    away_wins: int = 0
    away_draws: int = 0
    away_losses: int = 0
    
    # Form string (e.g., 'WWDLL')
    form_string: str = ""
    
    # Sample size
    sample_size: int = 0
    is_available: bool = False


class TeamFormFeatureCalculator(FeatureCalculator):
    """Calculate team form from recent matches."""
    
    def __init__(self, n: int = 5, min_matches: int = 3):
        """Initialize calculator.
        
        Args:
            n: Number of recent matches to consider
            min_matches: Minimum matches needed
        """
        self.n = n
        self.min_matches = min_matches
    
    def calculate_from_matches(
        self,
        matches: List[MatchDB],
        team_id: str,
        before_datetime: datetime
    ) -> TeamFormFeatures:
        """Calculate form features from recent matches.
        
        Args:
            matches: List of historical matches (ordered chronologically)
            team_id: Team database ID
            before_datetime: Calculate features before this datetime
            
        Returns:
            TeamFormFeatures with calculated metrics
        """
        # Take last n matches
        recent_matches = matches[-self.n:] if len(matches) >= self.n else matches
        
        if len(recent_matches) < self.min_matches:
            return TeamFormFeatures(
                team_id=team_id,
                last_n_results=[],
                sample_size=len(recent_matches),
                is_available=False
            )
        
        results = []
        wins = draws = losses = 0
        goals_scored = goals_conceded = 0
        home_wins = home_draws = home_losses = 0
        away_wins = away_draws = away_losses = 0
        
        for match in recent_matches:
            is_home = (match.home_team_id == team_id)
            
            # Determine result
            if match.outcome == MatchOutcome.DRAW:
                result = 'D'
                draws += 1
                if is_home:
                    home_draws += 1
                else:
                    away_draws += 1
            elif (is_home and match.outcome == MatchOutcome.HOME_WIN) or \
                 (not is_home and match.outcome == MatchOutcome.AWAY_WIN):
                result = 'W'
                wins += 1
                if is_home:
                    home_wins += 1
                else:
                    away_wins += 1
            else:
                result = 'L'
                losses += 1
                if is_home:
                    home_losses += 1
                else:
                    away_losses += 1
            
            results.append(result)
            
            # Goals
            if is_home:
                if match.home_score is not None:
                    goals_scored += match.home_score
                if match.away_score is not None:
                    goals_conceded += match.away_score
            else:
                if match.away_score is not None:
                    goals_scored += match.away_score
                if match.home_score is not None:
                    goals_conceded += match.home_score
        
        # Form string (most recent last)
        form_string = ''.join(results)
        
        return TeamFormFeatures(
            team_id=team_id,
            last_n_results=results,
            wins=wins,
            draws=draws,
            losses=losses,
            goals_scored=goals_scored,
            goals_conceded=goals_conceded,
            home_wins=home_wins,
            home_draws=home_draws,
            home_losses=home_losses,
            away_wins=away_wins,
            away_draws=away_draws,
            away_losses=away_losses,
            form_string=form_string,
            sample_size=len(recent_matches),
            is_available=True
        )
