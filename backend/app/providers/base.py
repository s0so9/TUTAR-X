"""Base provider interface for football data access.

This module defines the abstract contract for football data providers.
Implementations can be mock/development providers or real API integrations.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import date

from app.domain.entities import Competition, Season, Team, Player, Venue
from app.domain.match import Match, MatchEvent, Lineup
from app.domain.statistics import Standing, TeamMatchStatistic, PlayerMatchStatistic
from app.domain.availability import Injury, Suspension
from app.domain.odds import Odds
from app.domain.live import LiveMatchState


class FootballDataProvider(ABC):
    """
    Abstract base class for football data providers.
    
    This interface defines the contract for accessing football data.
    Implementations can provide mock data (for development/testing) or
    connect to real data sources (APIs, databases).
    
    Not all methods need to be implemented immediately. Providers can
    raise NotImplementedError for features not yet supported.
    """
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the provider name/identifier."""
        pass
    
    @abstractmethod
    def is_development_data(self) -> bool:
        """
        Return True if this provider supplies mock/development data.
        
        This flag is critical for ensuring development data is never
        presented as real football information to end users.
        """
        pass
    
    # === Competition and Season ===
    
    @abstractmethod
    def get_competitions(self) -> List[Competition]:
        """Get available competitions."""
        pass
    
    @abstractmethod
    def get_competition(self, competition_id: str) -> Optional[Competition]:
        """Get a specific competition by ID."""
        pass
    
    @abstractmethod
    def get_seasons(self, competition_id: str) -> List[Season]:
        """Get seasons for a competition."""
        pass
    
    @abstractmethod
    def get_current_season(self, competition_id: str) -> Optional[Season]:
        """Get the current season for a competition."""
        pass
    
    # === Teams ===
    
    @abstractmethod
    def get_teams(self, competition_id: str, season_id: str) -> List[Team]:
        """Get teams in a competition season."""
        pass
    
    @abstractmethod
    def get_team(self, team_id: str) -> Optional[Team]:
        """Get a specific team by ID."""
        pass
    
    # === Players ===
    
    def get_team_players(self, team_id: str) -> List[Player]:
        """Get players for a team. Optional method."""
        raise NotImplementedError("Player data not implemented")
    
    def get_player(self, player_id: str) -> Optional[Player]:
        """Get a specific player by ID. Optional method."""
        raise NotImplementedError("Player data not implemented")
    
    # === Venues ===
    
    def get_venue(self, venue_id: str) -> Optional[Venue]:
        """Get a specific venue by ID. Optional method."""
        raise NotImplementedError("Venue data not implemented")
    
    # === Matches ===
    
    @abstractmethod
    def get_matches(
        self,
        competition_id: Optional[str] = None,
        season_id: Optional[str] = None,
        team_id: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        status: Optional[str] = None,
    ) -> List[Match]:
        """
        Get matches with optional filters.
        
        Args:
            competition_id: Filter by competition
            season_id: Filter by season
            team_id: Filter by team (home or away)
            from_date: Filter matches from this date
            to_date: Filter matches to this date
            status: Filter by match status
            
        Returns:
            List of matching fixtures
        """
        pass
    
    @abstractmethod
    def get_match(self, match_id: str) -> Optional[Match]:
        """Get a specific match by ID."""
        pass
    
    # === Match Details ===
    
    def get_match_events(self, match_id: str) -> List[MatchEvent]:
        """Get events for a match. Optional method."""
        raise NotImplementedError("Match events not implemented")
    
    def get_match_lineups(self, match_id: str) -> List[Lineup]:
        """Get lineups for a match. Optional method."""
        raise NotImplementedError("Lineups not implemented")
    
    # === Statistics ===
    
    def get_standings(self, competition_id: str, season_id: str) -> List[Standing]:
        """Get league standings. Optional method."""
        raise NotImplementedError("Standings not implemented")
    
    def get_team_match_statistics(self, match_id: str) -> List[TeamMatchStatistic]:
        """Get team statistics for a match. Optional method."""
        raise NotImplementedError("Team match statistics not implemented")
    
    def get_team_match_statistics_firsthalf(self, match_id: str) -> List[TeamMatchStatistic]:
        """Get first-half team statistics for a match. Returns empty list if not available. Optional method."""
        raise NotImplementedError("First-half statistics not implemented")
    
    def get_player_match_statistics(self, match_id: str) -> List[PlayerMatchStatistic]:
        """Get player statistics for a match. Optional method."""
        raise NotImplementedError("Player match statistics not implemented")
    
    # === Player Availability ===
    
    def get_team_injuries(self, team_id: str) -> List[Injury]:
        """Get current injuries for a team. Optional method."""
        raise NotImplementedError("Injury data not implemented")
    
    def get_team_suspensions(self, team_id: str) -> List[Suspension]:
        """Get current suspensions for a team. Optional method."""
        raise NotImplementedError("Suspension data not implemented")
    
    # === Odds ===
    
    def get_match_odds(self, match_id: str) -> List[Odds]:
        """Get betting odds for a match. Optional method."""
        raise NotImplementedError("Odds data not implemented")
    
    # === Live Data ===
    
    def get_live_match_state(self, match_id: str) -> Optional[LiveMatchState]:
        """Get current live state of a match. Optional method."""
        raise NotImplementedError("Live match data not implemented")
