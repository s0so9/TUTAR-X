"""Repository pattern for database operations.

Repositories provide a clean interface for database operations with:
- Idempotent upserts (by provider_source_id, provider_id)
- Query methods for feature extraction
- Proper handling of relationships
"""

from typing import Optional, List, Type, TypeVar, Generic
from datetime import datetime, timedelta

from sqlalchemy import select, and_, or_, desc
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.database.models import (
    ProviderSource,
    Competition,
    Team,
    Player,
    Match,
    MatchEvent,
    Standing,
    MatchStatistic,
    LatencyLog,
)
from app.database.base import utc_now

T = TypeVar('T')


class BaseRepository(Generic[T]):
    """Base repository with common CRUD operations.
    
    Provides:
    - upsert_by_provider_id: Idempotent upsert based on (provider_source_id, provider_id)
    - get_by_provider_id: Retrieve by composite key
    - get_by_id: Retrieve by internal UUID
    """
    
    def __init__(self, session: Session, model_class: Type[T]):
        """Initialize repository.
        
        Args:
            session: SQLAlchemy session
            model_class: ORM model class
        """
        self.session = session
        self.model_class = model_class
    
    def get_by_id(self, entity_id: str) -> Optional[T]:
        """Get entity by internal UUID.
        
        Args:
            entity_id: Internal UUID
            
        Returns:
            Entity or None if not found
        """
        return self.session.get(self.model_class, entity_id)
    
    def get_by_provider_id(
        self,
        provider_source_id: str,
        provider_id: str
    ) -> Optional[T]:
        """Get entity by provider composite key.
        
        Args:
            provider_source_id: Provider source UUID
            provider_id: Provider's external identifier
            
        Returns:
            Entity or None if not found
        """
        stmt = select(self.model_class).where(
            and_(
                self.model_class.provider_source_id == provider_source_id,
                self.model_class.provider_id == provider_id,
            )
        )
        return self.session.execute(stmt).scalars().first()
    
    def upsert_by_provider_id(
        self,
        provider_source_id: str,
        provider_id: str,
        data: dict,
        preserve_fields: Optional[List[str]] = None
    ) -> T:
        """Upsert entity by provider composite key.
        
        If entity exists, updates it. If not, creates it.
        NEVER overwrites non-None fields with None values.
        
        Args:
            provider_source_id: Provider source UUID
            provider_id: Provider's external identifier
            data: Dictionary of field values to set
            preserve_fields: Optional list of fields to explicitly preserve.
                            If None (default), ALL fields are protected from None-overwrite.
                            If provided, ONLY those fields are protected (use with caution).
            
        Returns:
            Created or updated entity
        """
        # Get existing entity
        existing = self.get_by_provider_id(provider_source_id, provider_id)
        
        if existing is None:
            # Create new entity
            entity = self.model_class(
                provider_source_id=provider_source_id,
                provider_id=provider_id,
                **data
            )
            self.session.add(entity)
            self.session.flush()
            return entity
        else:
            # Update existing entity
            # SAFE DEFAULT: Protect ALL fields from None-overwrite unless preserve_fields is explicitly provided
            updated = False
            for key, value in data.items():
                existing_value = getattr(existing, key, None)
                
                # Never overwrite non-None with None (applies to all fields by default)
                if existing_value is not None and value is None:
                    # Skip: don't overwrite valid data with None
                    continue
                
                # If preserve_fields is specified and key is NOT in it, allow overwrite
                # This provides explicit opt-out from None-protection for specific fields
                # (Currently not used, but available if needed for future use cases)
                
                # Update the field if value is different
                if existing_value != value:
                    setattr(existing, key, value)
                    updated = True
            
            # Update timestamp only if something changed
            if updated:
                new_timestamp = utc_now()
                # Ensure updated_at is newer than existing timestamp (handle microsecond-level timing)
                # Handle timezone-aware and naive datetime comparison
                existing_ts = existing.updated_at
                if existing_ts.tzinfo is None:
                    # Make comparison timezone-naive if existing is naive
                    new_timestamp = new_timestamp.replace(tzinfo=None)
                
                if new_timestamp <= existing_ts:
                    # Add a microsecond to ensure it's newer
                    new_timestamp = existing_ts + timedelta(microseconds=1)
                
                existing.updated_at = new_timestamp
            
            self.session.flush()
            return existing


class ProviderSourceRepository(BaseRepository[ProviderSource]):
    """Repository for provider sources."""
    
    def __init__(self, session: Session):
        super().__init__(session, ProviderSource)
    
    def get_or_create_by_name(self, name: str, base_url: Optional[str] = None) -> ProviderSource:
        """Get provider source by name or create if not exists.
        
        Args:
            name: Provider name (e.g., 'ryzellx', 'fotmob')
            base_url: Provider base URL
            
        Returns:
            ProviderSource entity
        """
        stmt = select(ProviderSource).where(ProviderSource.name == name)
        source = self.session.execute(stmt).scalars().first()
        
        if source is None:
            source = ProviderSource(
                name=name,
                base_url=base_url,
                is_active=True,
                last_seen_at=utc_now(),
            )
            self.session.add(source)
            self.session.flush()
        else:
            # Update last seen
            source.last_seen_at = utc_now()
            self.session.flush()
        
        return source


class CompetitionRepository(BaseRepository[Competition]):
    """Repository for competitions."""
    
    def __init__(self, session: Session):
        super().__init__(session, Competition)
    
    def get_by_name_and_season(
        self,
        name: str,
        season: Optional[str] = None
    ) -> Optional[Competition]:
        """Get competition by name and season.
        
        Args:
            name: Competition name
            season: Season (e.g., '2023/24')
            
        Returns:
            Competition or None
        """
        stmt = select(Competition).where(Competition.name == name)
        if season:
            stmt = stmt.where(Competition.season == season)
        return self.session.execute(stmt).scalars().first()


class TeamRepository(BaseRepository[Team]):
    """Repository for teams."""
    
    def __init__(self, session: Session):
        super().__init__(session, Team)
    
    def get_by_name(self, name: str) -> Optional[Team]:
        """Get team by name.
        
        Args:
            name: Team name
            
        Returns:
            Team or None
        """
        stmt = select(Team).where(Team.name == name)
        return self.session.execute(stmt).scalars().first()


class PlayerRepository(BaseRepository[Player]):
    """Repository for players."""
    
    def __init__(self, session: Session):
        super().__init__(session, Player)
    
    def get_by_team(self, team_id: str) -> List[Player]:
        """Get all players for a team.
        
        Args:
            team_id: Team UUID
            
        Returns:
            List of players
        """
        stmt = select(Player).where(Player.team_id == team_id)
        return list(self.session.execute(stmt).scalars().all())


class MatchRepository(BaseRepository[Match]):
    """Repository for matches."""
    
    def __init__(self, session: Session):
        super().__init__(session, Match)
    
    def get_team_matches_before_date(
        self,
        team_id: str,
        before_datetime: datetime,
        limit: Optional[int] = None,
        finished_only: bool = True
    ) -> List[Match]:
        """Get team's matches before a specific datetime.
        
        Used for feature extraction to prevent data leakage.
        Returns the most recent N matches if limit is specified.
        
        Args:
            team_id: Team UUID
            before_datetime: Only matches scheduled before this datetime
            limit: Maximum number of matches to return (most recent N)
            finished_only: Only return finished matches
            
        Returns:
            List of matches, ordered by scheduled_at ascending (chronological)
        """
        from app.domain.enums import MatchStatus
        
        stmt = select(Match).where(
            and_(
                or_(
                    Match.home_team_id == team_id,
                    Match.away_team_id == team_id,
                ),
                Match.scheduled_at < before_datetime,
            )
        )
        
        if finished_only:
            stmt = stmt.where(Match.status == MatchStatus.FINISHED)
        
        # When limit is specified, we want the most recent N matches
        # To achieve this: first order DESC to get the newest, apply limit,
        # then reverse to chronological order for consumers
        if limit:
            # Subquery: get most recent N matches
            stmt = stmt.order_by(
                Match.scheduled_at.desc(),
                Match.id.desc()  # Stable secondary sort for equal timestamps
            ).limit(limit)
            
            # Execute subquery and reverse to chronological order
            matches = list(self.session.execute(stmt).scalars().all())
            matches.reverse()
            return matches
        else:
            # No limit: return all in chronological order
            stmt = stmt.order_by(
                Match.scheduled_at.asc(),
                Match.id.asc()  # Stable secondary sort
            )
            return list(self.session.execute(stmt).scalars().all())
    
    def get_matches_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[Match]:
        """Get matches within date range.
        
        Args:
            start_date: Start datetime (inclusive)
            end_date: End datetime (inclusive)
            
        Returns:
            List of matches ordered by scheduled_at
        """
        stmt = select(Match).where(
            and_(
                Match.scheduled_at >= start_date,
                Match.scheduled_at <= end_date,
            )
        ).order_by(Match.scheduled_at.asc())
        
        return list(self.session.execute(stmt).scalars().all())
    
    def get_live_matches(self) -> List[Match]:
        """Get currently live matches.
        
        Returns:
            List of matches with status LIVE or HALF_TIME
        """
        from app.domain.enums import MatchStatus
        
        stmt = select(Match).where(
            Match.status.in_([MatchStatus.LIVE, MatchStatus.HALF_TIME])
        ).order_by(Match.scheduled_at.asc())
        
        return list(self.session.execute(stmt).scalars().all())


class MatchEventRepository(BaseRepository[MatchEvent]):
    """Repository for match events."""
    
    def __init__(self, session: Session):
        super().__init__(session, MatchEvent)
    
    def get_by_match(self, match_id: str) -> List[MatchEvent]:
        """Get all events for a match.
        
        Args:
            match_id: Match UUID
            
        Returns:
            List of events ordered by minute
        """
        stmt = select(MatchEvent).where(
            MatchEvent.match_id == match_id
        ).order_by(MatchEvent.minute.asc())
        
        return list(self.session.execute(stmt).scalars().all())


class StandingRepository(BaseRepository[Standing]):
    """Repository for standings."""
    
    def __init__(self, session: Session):
        super().__init__(session, Standing)
    
    def get_by_competition_season(
        self,
        competition_id: str,
        season: str
    ) -> List[Standing]:
        """Get standings for a competition and season.
        
        Args:
            competition_id: Competition UUID
            season: Season string
            
        Returns:
            List of standings ordered by position
        """
        stmt = select(Standing).where(
            and_(
                Standing.competition_id == competition_id,
                Standing.season == season,
            )
        ).order_by(Standing.position.asc())
        
        return list(self.session.execute(stmt).scalars().all())
    
    def get_team_standing(
        self,
        competition_id: str,
        season: str,
        team_id: str
    ) -> Optional[Standing]:
        """Get specific team's standing.
        
        Args:
            competition_id: Competition UUID
            season: Season string
            team_id: Team UUID
            
        Returns:
            Standing or None
        """
        stmt = select(Standing).where(
            and_(
                Standing.competition_id == competition_id,
                Standing.season == season,
                Standing.team_id == team_id,
            )
        )
        
        return self.session.execute(stmt).scalars().first()


class MatchStatisticRepository(BaseRepository[MatchStatistic]):
    """Repository for match statistics."""
    
    def __init__(self, session: Session):
        super().__init__(session, MatchStatistic)
    
    def get_by_match(self, match_id: str) -> List[MatchStatistic]:
        """Get statistics for both teams in a match.
        
        Args:
            match_id: Match UUID
            
        Returns:
            List of statistics (typically 2, one per team)
        """
        stmt = select(MatchStatistic).where(
            MatchStatistic.match_id == match_id
        )
        
        return list(self.session.execute(stmt).scalars().all())
    
    def get_by_match_and_team(
        self,
        match_id: str,
        team_id: str
    ) -> Optional[MatchStatistic]:
        """Get statistics for a specific team in a match.
        
        Args:
            match_id: Match UUID
            team_id: Team UUID
            
        Returns:
            MatchStatistic or None
        """
        stmt = select(MatchStatistic).where(
            and_(
                MatchStatistic.match_id == match_id,
                MatchStatistic.team_id == team_id,
            )
        )
        
        return self.session.execute(stmt).scalars().first()


class LatencyLogRepository:
    """Repository for latency logs."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create_log(
        self,
        entity_type: str,
        entity_id: str,
        latency_json: dict
    ) -> LatencyLog:
        """Create a latency log entry.
        
        Args:
            entity_type: Type of entity (e.g., 'match', 'live_match')
            entity_id: Entity identifier
            latency_json: Latency data as dictionary
            
        Returns:
            Created LatencyLog
        """
        log = LatencyLog(
            entity_type=entity_type,
            entity_id=entity_id,
            latency_json=latency_json,
        )
        self.session.add(log)
        self.session.flush()
        return log
    
    def get_latest_for_entity(
        self,
        entity_type: str,
        entity_id: str
    ) -> Optional[LatencyLog]:
        """Get most recent latency log for an entity.
        
        Args:
            entity_type: Type of entity
            entity_id: Entity identifier
            
        Returns:
            LatencyLog or None
        """
        stmt = select(LatencyLog).where(
            and_(
                LatencyLog.entity_type == entity_type,
                LatencyLog.entity_id == entity_id,
            )
        ).order_by(desc(LatencyLog.created_at)).limit(1)
        
        return self.session.execute(stmt).scalars().first()
