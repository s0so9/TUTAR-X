"""Live match data ingestion with out-of-order event handling."""

from sqlalchemy.orm import Session

from app.providers.models import ProviderLiveMatch
from app.database.repository import ProviderSourceRepository, MatchRepository
from app.database.models import Match


class LiveIngester:
    """Ingest live match updates."""
    
    def __init__(self, session: Session):
        """Initialize live ingester.
        
        Args:
            session: SQLAlchemy session
        """
        self.session = session
        self.provider_source_repo = ProviderSourceRepository(session)
        self.match_repo = MatchRepository(session)
    
    def ingest_live_match(self, live_match: ProviderLiveMatch) -> Match:
        """Ingest a live match update.
        
        Handles out-of-order events by checking minute ordering before updating.
        
        Args:
            live_match: Normalized provider live match
            
        Returns:
            Match database entity
        """
        provider_source = self.provider_source_repo.get_or_create_by_name(
            name=live_match.provider
        )
        
        # Get existing match
        existing_match = self.match_repo.get_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id=live_match.source_id
        )
        
        # Prepare live update data
        live_data = {
            "status": live_match.status,
            "minute": live_match.minute,
            "added_time": live_match.added_time,
            "home_score": live_match.home_score,
            "away_score": live_match.away_score,
            "last_provider_update": live_match.fetched_at,
        }
        
        # Handle out-of-order events: only update minute if it's later
        if existing_match and existing_match.minute is not None:
            if live_match.minute is not None:
                if live_match.minute < existing_match.minute:
                    # Out-of-order event: don't update minute
                    live_data.pop("minute", None)
                    live_data.pop("added_time", None)
        
        # Upsert match
        match = self.match_repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id=live_match.source_id,
            data=live_data,
            preserve_fields=[]  # Allow live updates to override
        )
        
        return match
