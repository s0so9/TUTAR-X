"""Database-backed feature extraction for production use.

This module extends the existing feature extraction to use persisted
database data instead of in-memory provider data.
"""

from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.database.repository import MatchRepository, TeamRepository, StandingRepository
from app.database.models import Match as MatchDB, Team as TeamDB, Standing as StandingDB
from app.domain.match import Match
from app.domain.entities import Team
from app.domain.enums import MatchStatus


class DatabaseFeatureExtractor:
    """Extract features from database for a specific match.
    
    Ensures no data leakage by only using historical data before the match.
    """
    
    def __init__(self, session: Session):
        """Initialize database feature extractor.
        
        Args:
            session: SQLAlchemy session
        """
        self.session = session
        self.match_repo = MatchRepository(session)
        self.team_repo = TeamRepository(session)
        self.standing_repo = StandingRepository(session)
    
    def get_team_historical_matches(
        self,
        team_id: str,
        before_datetime: datetime,
        limit: int = 10,
        finished_only: bool = True
    ) -> List[MatchDB]:
        """Get team's historical matches before a specific datetime.
        
        This prevents data leakage by only returning matches that occurred
        before the target match.
        
        Args:
            team_id: Team database ID
            before_datetime: Only matches scheduled before this datetime
            limit: Maximum number of matches to return
            finished_only: Only return finished matches
            
        Returns:
            List of Match database entities, ordered chronologically
        """
        return self.match_repo.get_team_matches_before_date(
            team_id=team_id,
            before_datetime=before_datetime,
            limit=limit,
            finished_only=finished_only
        )
    
    def get_team_standing(
        self,
        competition_id: str,
        season: str,
        team_id: str
    ) -> Optional[StandingDB]:
        """Get team's standing in a competition.
        
        Args:
            competition_id: Competition database ID
            season: Season string
            team_id: Team database ID
            
        Returns:
            Standing or None if not available
        """
        return self.standing_repo.get_team_standing(
            competition_id=competition_id,
            season=season,
            team_id=team_id
        )
    
    def convert_db_match_to_domain(self, match_db: MatchDB) -> Match:
        """Convert database Match to domain Match.
        
        Args:
            match_db: Database Match entity
            
        Returns:
            Domain Match object
        """
        return Match(
            id=match_db.id,
            home_team_id=match_db.home_team_id,
            away_team_id=match_db.away_team_id,
            competition_id=match_db.competition_id or "unknown",
            season_id=match_db.season or "unknown",
            scheduled_at=match_db.scheduled_at,
            status=match_db.status,
            home_score=match_db.home_score,
            away_score=match_db.away_score,
            outcome=match_db.outcome,
        )
