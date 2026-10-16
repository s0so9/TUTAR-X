"""Prediction persistence service.

Implements PredictionPersistenceService interface for database-backed storage.
"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database.prediction_repository import PredictionVersionRepository
from app.prediction.prediction_version import PredictionVersion, PredictionStage


class PredictionPersistenceService:
    """Database-backed prediction persistence service.
    
    This service implements the persistence interface expected by
    PredictionVersionManager, providing database storage for prediction versions.
    """
    
    def __init__(self, session: Session):
        """Initialize persistence service.
        
        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self.repository = PredictionVersionRepository(session)
    
    def save_version(self, version: PredictionVersion) -> None:
        """Save prediction version to database.
        
        Args:
            version: PredictionVersion to save
            
        Raises:
            ValueError: If unique constraint violated (wrapped IntegrityError)
        """
        try:
            self.repository.save(version)
            self.session.commit()
        except IntegrityError as e:
            self.session.rollback()
            # Re-raise as ValueError for PredictionVersionManager
            raise ValueError(
                f"Cannot save version: unique constraint violation. "
                f"Match {version.match_id} at stage {version.stage.value} already exists."
            ) from e
        except Exception as e:
            self.session.rollback()
            raise
    
    def get_versions(self, match_id: str) -> List[PredictionVersion]:
        """Get all versions for a match.
        
        Args:
            match_id: Match identifier
            
        Returns:
            List of PredictionVersion ordered by created_at
        """
        db_versions = self.repository.get_by_match(match_id)
        return [self.repository.to_domain(db_v) for db_v in db_versions]
    
    def get_version_by_id(self, version_id: str) -> Optional[PredictionVersion]:
        """Get version by ID.
        
        Args:
            version_id: Version UUID
            
        Returns:
            PredictionVersion or None
        """
        db_version = self.repository.get_by_id(version_id)
        return self.repository.to_domain(db_version) if db_version else None
    
    def get_version_by_stage(
        self,
        match_id: str,
        stage: PredictionStage
    ) -> Optional[PredictionVersion]:
        """Get version for specific stage (latest if multiple).
        
        Args:
            match_id: Match identifier
            stage: Prediction stage
            
        Returns:
            Latest PredictionVersion for stage or None
        """
        db_versions = self.repository.get_by_stage(match_id, stage)
        return self.repository.to_domain(db_versions[0]) if db_versions else None
    
    def delete_version(self, version_id: str) -> bool:
        """Delete version by ID.
        
        Args:
            version_id: Version UUID
            
        Returns:
            True if deleted, False if not found
        """
        try:
            result = self.repository.delete(version_id)
            self.session.commit()
            return result
        except Exception as e:
            self.session.rollback()
            raise
    
    def get_settled_picks_by_market(
        self,
        market_type: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[PredictionVersion]:
        """Get settled prediction picks for a market type.
        
        Args:
            market_type: Market type filter
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            List of settled PredictionVersion
        """
        db_versions = self.repository.get_settled_picks_by_market(
            market_type=market_type,
            start_date=start_date,
            end_date=end_date
        )
        return [self.repository.to_domain(db_v) for db_v in db_versions]
