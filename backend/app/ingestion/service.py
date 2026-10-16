"""Ingestion service orchestrator."""

from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime
from sqlalchemy.orm import Session, sessionmaker

from app.providers.models import (
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchStats,
    ProviderCompetition,
    ProviderTeam,
    ProviderPlayer,
    ProviderStanding,
    ProviderLiveMatch,
)
from app.database.models import (
    Match,
    MatchEvent,
    MatchStatistic,
    Competition,
    Team,
    Player,
    Standing,
)
from app.ingestion.match_ingestion import MatchIngester
from app.ingestion.metadata_ingestion import MetadataIngester
from app.ingestion.live_ingestion import LiveIngester


@dataclass
class IngestionResult:
    """Result of an ingestion operation."""
    
    success: bool
    entity_type: str
    entity_count: int
    ingested_at: datetime
    errors: List[str]
    
    @classmethod
    def create_success(cls, entity_type: str, entity_count: int):
        """Create a success result."""
        return cls(
            success=True,
            entity_type=entity_type,
            entity_count=entity_count,
            ingested_at=datetime.utcnow(),
            errors=[]
        )
    
    @classmethod
    def create_error(cls, entity_type: str, error_message: str):
        """Create an error result."""
        return cls(
            success=False,
            entity_type=entity_type,
            entity_count=0,
            ingested_at=datetime.utcnow(),
            errors=[error_message]
        )


class IngestionService:
    """Orchestrate ingestion of provider data into database.
    
    This service coordinates all ingestion sub-services and handles:
    - Session management
    - Transaction boundaries
    - Error handling
    - Result tracking
    """
    
    def __init__(self, session_factory: sessionmaker):
        """Initialize ingestion service.
        
        Args:
            session_factory: SQLAlchemy sessionmaker for creating sessions
        """
        self.session_factory = session_factory
    
    def _get_session(self) -> Session:
        """Get a new database session."""
        return self.session_factory()
    
    def ingest_provider_matches(
        self,
        provider_matches: List[ProviderMatch]
    ) -> IngestionResult:
        """Ingest matches from provider.
        
        Args:
            provider_matches: List of normalized provider matches
            
        Returns:
            IngestionResult with success status and counts
        """
        session = self._get_session()
        try:
            ingester = MatchIngester(session)
            matches = ingester.ingest_matches(provider_matches)
            session.commit()
            return IngestionResult.create_success("match", len(matches))
        except Exception as e:
            session.rollback()
            return IngestionResult.create_error("match", str(e))
        finally:
            session.close()
    
    def ingest_provider_competitions(
        self,
        provider_competitions: List[ProviderCompetition]
    ) -> IngestionResult:
        """Ingest competitions from provider.
        
        Args:
            provider_competitions: List of normalized provider competitions
            
        Returns:
            IngestionResult with success status and counts
        """
        session = self._get_session()
        try:
            ingester = MetadataIngester(session)
            competitions = []
            for provider_comp in provider_competitions:
                comp = ingester.ingest_competition(provider_comp)
                competitions.append(comp)
            session.commit()
            return IngestionResult.create_success("competition", len(competitions))
        except Exception as e:
            session.rollback()
            return IngestionResult.create_error("competition", str(e))
        finally:
            session.close()
    
    def ingest_provider_teams(
        self,
        provider_teams: List[ProviderTeam]
    ) -> IngestionResult:
        """Ingest teams from provider.
        
        Args:
            provider_teams: List of normalized provider teams
            
        Returns:
            IngestionResult with success status and counts
        """
        session = self._get_session()
        try:
            ingester = MetadataIngester(session)
            teams = []
            for provider_team in provider_teams:
                team = ingester.ingest_team(provider_team)
                teams.append(team)
            session.commit()
            return IngestionResult.create_success("team", len(teams))
        except Exception as e:
            session.rollback()
            return IngestionResult.create_error("team", str(e))
        finally:
            session.close()
    
    def ingest_provider_players(
        self,
        provider_players: List[ProviderPlayer]
    ) -> IngestionResult:
        """Ingest players from provider.
        
        Args:
            provider_players: List of normalized provider players
            
        Returns:
            IngestionResult with success status and counts
        """
        session = self._get_session()
        try:
            ingester = MetadataIngester(session)
            players = []
            for provider_player in provider_players:
                player = ingester.ingest_player(provider_player)
                players.append(player)
            session.commit()
            return IngestionResult.create_success("player", len(players))
        except Exception as e:
            session.rollback()
            return IngestionResult.create_error("player", str(e))
        finally:
            session.close()
    
    def ingest_provider_standings(
        self,
        provider_standings: List[ProviderStanding]
    ) -> IngestionResult:
        """Ingest standings from provider.
        
        Args:
            provider_standings: List of normalized provider standings
            
        Returns:
            IngestionResult with success status and counts
        """
        session = self._get_session()
        try:
            ingester = MetadataIngester(session)
            standings = []
            for provider_standing in provider_standings:
                standing = ingester.ingest_standing(provider_standing)
                standings.append(standing)
            session.commit()
            return IngestionResult.create_success("standing", len(standings))
        except Exception as e:
            session.rollback()
            return IngestionResult.create_error("standing", str(e))
        finally:
            session.close()
    
    def ingest_provider_match_stats(
        self,
        provider_match_stats: List[ProviderMatchStats]
    ) -> IngestionResult:
        """Ingest match statistics from provider.
        
        Args:
            provider_match_stats: List of normalized provider match statistics
            
        Returns:
            IngestionResult with success status and counts
        """
        session = self._get_session()
        try:
            ingester = MatchIngester(session)
            statistics = []
            for provider_stats in provider_match_stats:
                stat = ingester.ingest_match_stats(provider_stats)
                statistics.append(stat)
            session.commit()
            return IngestionResult.create_success("match_statistic", len(statistics))
        except Exception as e:
            session.rollback()
            return IngestionResult.create_error("match_statistic", str(e))
        finally:
            session.close()
    
    def ingest_provider_live_match(
        self,
        live_match: ProviderLiveMatch
    ) -> IngestionResult:
        """Ingest a live match update.
        
        Args:
            live_match: Normalized provider live match
            
        Returns:
            IngestionResult with success status
        """
        session = self._get_session()
        try:
            ingester = LiveIngester(session)
            match = ingester.ingest_live_match(live_match)
            session.commit()
            return IngestionResult.create_success("live_match", 1)
        except Exception as e:
            session.rollback()
            return IngestionResult.create_error("live_match", str(e))
        finally:
            session.close()
    
    def ingest_provider_events(
        self,
        provider_events: List[ProviderMatchEvent]
    ) -> IngestionResult:
        """Ingest match events from provider.
        
        Args:
            provider_events: List of normalized provider match events
            
        Returns:
            IngestionResult with success status and counts
        """
        session = self._get_session()
        try:
            ingester = MatchIngester(session)
            events = []
            for provider_event in provider_events:
                event = ingester.ingest_match_event(provider_event)
                events.append(event)
            session.commit()
            return IngestionResult.create_success("match_event", len(events))
        except Exception as e:
            session.rollback()
            return IngestionResult.create_error("match_event", str(e))
        finally:
            session.close()
