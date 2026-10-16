"""Attack and defence feature calculations."""

from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime

from app.database.models import Match as MatchDB, MatchStatistic
from app.database.repository import MatchStatisticRepository
from app.features.base import FeatureCalculator


@dataclass
class AttackDefenceFeatures:
    """Attack and defence metrics for a team.
    
    All xG-related fields are Optional and will be None if xG data
    is not available. NEVER invent xG values.
    """
    
    team_id: str
    
    # Goals
    goals_per_match: Optional[float] = None
    goals_conceded_per_match: Optional[float] = None
    
    # Expected goals (may be None if not available)
    xg_per_match: Optional[float] = None
    xga_per_match: Optional[float] = None
    xg_sample_size: int = 0  # Number of matches with xG data
    
    # Shots (if available)
    shots_per_match: Optional[float] = None
    shots_on_target_per_match: Optional[float] = None
    
    # Sample size
    sample_size: int = 0
    is_available: bool = False


class AttackDefenceFeatureCalculator(FeatureCalculator):
    """Calculate attack and defence features from historical matches."""
    
    def __init__(self, session, min_matches: int = 5):
        """Initialize calculator.
        
        Args:
            session: SQLAlchemy session
            min_matches: Minimum matches needed for reliable features
        """
        self.session = session
        self.min_matches = min_matches
        self.match_stat_repo = MatchStatisticRepository(session)
    
    def calculate_from_matches(
        self,
        matches: List[MatchDB],
        team_id: str,
        before_datetime: datetime
    ) -> AttackDefenceFeatures:
        """Calculate attack/defence features from historical matches.
        
        Args:
            matches: List of historical matches (finished only)
            team_id: Team database ID
            before_datetime: Calculate features before this datetime
            
        Returns:
            AttackDefenceFeatures with calculated metrics
        """
        if len(matches) < self.min_matches:
            return AttackDefenceFeatures(
                team_id=team_id,
                sample_size=len(matches),
                is_available=False
            )
        
        # Calculate goals
        total_goals = 0
        total_conceded = 0
        
        # Track xG separately (may not be available for all matches)
        # IMPORTANT: Count each source only once to avoid double-counting
        total_xg = 0.0
        total_xga = 0.0
        xg_count = 0  # Number of matches with xG data
        xga_count = 0  # Number of matches with xGA data (tracked separately)
        
        # Track shots
        total_shots = 0
        total_shots_on_target = 0
        shots_count = 0  # Number of matches with shot data
        shots_on_target_count = 0  # May differ from shots_count
        
        for match in matches:
            # Track whether we've counted xG/xGA from this match
            xg_counted_this_match = False
            xga_counted_this_match = False
            
            # Goals
            if match.home_team_id == team_id:
                if match.home_score is not None:
                    total_goals += match.home_score
                if match.away_score is not None:
                    total_conceded += match.away_score
                
                # Try to get xG from match directly
                if match.home_xg is not None:
                    total_xg += match.home_xg
                    xg_count += 1
                    xg_counted_this_match = True
                if match.away_xg is not None:
                    total_xga += match.away_xg
                    xga_count += 1
                    xga_counted_this_match = True
                
            elif match.away_team_id == team_id:
                if match.away_score is not None:
                    total_goals += match.away_score
                if match.home_score is not None:
                    total_conceded += match.home_score
                
                if match.away_xg is not None:
                    total_xg += match.away_xg
                    xg_count += 1
                    xg_counted_this_match = True
                if match.home_xg is not None:
                    total_xga += match.home_xg
                    xga_count += 1
                    xga_counted_this_match = True
            
            # Get match statistics if available
            stat = self.match_stat_repo.get_by_match_and_team(
                match_id=match.id,
                team_id=team_id
            )
            
            if stat:
                # xG from statistics - ONLY if not already counted from match
                if stat.xg is not None and not xg_counted_this_match:
                    total_xg += stat.xg
                    xg_count += 1
                    xg_counted_this_match = True
                
                # xGA from statistics - ONLY if not already counted from match
                if stat.xg_against is not None and not xga_counted_this_match:
                    total_xga += stat.xg_against
                    xga_count += 1
                    xga_counted_this_match = True
                
                # Shots - count each field independently
                if stat.shots_total is not None:
                    total_shots += stat.shots_total
                    shots_count += 1
                if stat.shots_on_target is not None:
                    total_shots_on_target += stat.shots_on_target
                    shots_on_target_count += 1
        
        # Calculate per-match averages
        n_matches = len(matches)
        
        goals_per_match = self.safe_divide(total_goals, n_matches)
        goals_conceded_per_match = self.safe_divide(total_conceded, n_matches)
        
        # xG averages - use actual sample sizes, not zero-count
        # If no xG data exists, return None (not 0.0)
        xg_per_match = self.safe_divide(total_xg, xg_count) if xg_count > 0 else None
        xga_per_match = self.safe_divide(total_xga, xga_count) if xga_count > 0 else None
        
        # Shot averages - each stat has its own denominator
        shots_per_match = self.safe_divide(total_shots, shots_count) if shots_count > 0 else None
        shots_on_target_per_match = self.safe_divide(total_shots_on_target, shots_on_target_count) if shots_on_target_count > 0 else None
        
        return AttackDefenceFeatures(
            team_id=team_id,
            goals_per_match=goals_per_match,
            goals_conceded_per_match=goals_conceded_per_match,
            xg_per_match=xg_per_match,
            xga_per_match=xga_per_match,
            xg_sample_size=xg_count,
            shots_per_match=shots_per_match,
            shots_on_target_per_match=shots_on_target_per_match,
            sample_size=n_matches,
            is_available=True
        )
