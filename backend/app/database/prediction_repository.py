"""Database repository for prediction versions.

Handles CRUD operations for prediction_versions table.
"""
from datetime import datetime
from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.orm import Session
from app.database.models import PredictionVersionDB
from app.prediction.prediction_version import PredictionVersion, PredictionStage
import json
import uuid


class PredictionVersionRepository:
    """Repository for prediction version database operations."""
    
    def __init__(self, session: Session):
        """Initialize repository.
        
        Args:
            session: SQLAlchemy database session
        """
        self.session = session
    
    def save(self, version: PredictionVersion) -> PredictionVersionDB:
        """Save prediction version to database.
        
        Args:
            version: PredictionVersion to save
            
        Returns:
            Saved database model
            
        Raises:
            IntegrityError: If unique constraint violated (match_id + stage)
        """
        # Convert UUID to string for SQLite compatibility
        version_id = version.version_id
        if not isinstance(version_id, str):
            version_id = str(version_id)
        
        db_version = PredictionVersionDB(
            id=version_id,  # Store as string in BaseModel
            match_id=version.match_id,
            stage=version.stage.value,
            created_at=version.created_at,
            prediction_data=version.prediction_data,  # JSON column
            model_versions=version.model_versions or {},  # JSON column
            data_quality_score=version.data_quality_score,
            confidence_score=version.confidence_score,
            notes=version.notes or [],
            # Frozen pick fields
            selected_market=version.selected_market,
            selection_text=version.selection_text,
            selection_probability=version.selection_probability,
            selection_confidence=version.selection_confidence,
            selection_odds=version.selection_odds,
            selection_fair_odds=version.selection_fair_odds,
            selection_edge=version.selection_edge,
            value_classification=version.value_classification,
            risk_level=version.risk_level,
            # Settlement fields (PredictionVersion uses 'actual_result', DB uses same)
            actual_result=version.actual_result,
            profit_loss=version.profit_loss,
            settled_at=version.settled_at
        )
        
        self.session.add(db_version)
        self.session.flush()  # Flush to catch constraint violations
        
        return db_version
    
    def get_by_match(self, match_id: str) -> List[PredictionVersionDB]:
        """Get all versions for a match.
        
        Args:
            match_id: Match identifier
            
        Returns:
            List of prediction versions ordered by created_at
        """
        stmt = (
            select(PredictionVersionDB)
            .where(PredictionVersionDB.match_id == match_id)
            .order_by(PredictionVersionDB.created_at.asc())
        )
        
        result = self.session.execute(stmt)
        return list(result.scalars().all())
    
    def get_by_id(self, version_id: str) -> Optional[PredictionVersionDB]:
        """Get version by ID.
        
        Args:
            version_id: Version UUID string
            
        Returns:
            PredictionVersionDB or None
        """
        # BaseModel uses string ID
        stmt = select(PredictionVersionDB).where(
            PredictionVersionDB.id == version_id
        )
        
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    def get_by_stage(
        self,
        match_id: str,
        stage: PredictionStage
    ) -> List[PredictionVersionDB]:
        """Get versions for specific match and stage.
        
        Args:
            match_id: Match identifier
            stage: Prediction stage
            
        Returns:
            List of matching versions (may be multiple if stage_overwrite used)
        """
        stmt = (
            select(PredictionVersionDB)
            .where(
                and_(
                    PredictionVersionDB.match_id == match_id,
                    PredictionVersionDB.stage == stage.value
                )
            )
            .order_by(PredictionVersionDB.created_at.desc())
        )
        
        result = self.session.execute(stmt)
        return list(result.scalars().all())
    
    def delete(self, version_id: str) -> bool:
        """Delete version by ID.
        
        Args:
            version_id: Version UUID string
            
        Returns:
            True if deleted, False if not found
        """
        db_version = self.get_by_id(version_id)
        if db_version:
            self.session.delete(db_version)
            self.session.flush()
            return True
        return False
    
    def get_settled_picks_by_market(
        self,
        market_type: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[PredictionVersionDB]:
        """Get settled prediction picks for a market type.
        
        Args:
            market_type: Market type filter
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            List of settled versions with selected_market matching filter
        """
        conditions = [
            PredictionVersionDB.selected_market == market_type,
            PredictionVersionDB.actual_result.isnot(None),  # Settled
        ]
        
        if start_date:
            conditions.append(PredictionVersionDB.settled_at >= start_date)
        if end_date:
            conditions.append(PredictionVersionDB.settled_at <= end_date)
        
        stmt = (
            select(PredictionVersionDB)
            .where(and_(*conditions))
            .order_by(PredictionVersionDB.settled_at.desc())
        )
        
        result = self.session.execute(stmt)
        return list(result.scalars().all())
    
    @staticmethod
    def to_domain(db_version: PredictionVersionDB) -> PredictionVersion:
        """Convert database model to domain model.
        
        Args:
            db_version: Database model
            
        Returns:
            PredictionVersion domain model
        """
        return PredictionVersion(
            version_id=str(db_version.id),
            match_id=db_version.match_id,
            stage=PredictionStage(db_version.stage),
            created_at=db_version.created_at,
            prediction_data=db_version.prediction_data,
            model_versions=db_version.model_versions or {},
            data_quality_score=db_version.data_quality_score,
            confidence_score=db_version.confidence_score,
            notes=db_version.notes or [],
            # Frozen pick fields
            selected_market=db_version.selected_market,
            selection_text=db_version.selection_text,
            selection_probability=db_version.selection_probability,
            selection_confidence=db_version.selection_confidence,
            selection_odds=db_version.selection_odds,
            selection_fair_odds=db_version.selection_fair_odds,
            selection_edge=db_version.selection_edge,
            value_classification=db_version.value_classification,
            risk_level=db_version.risk_level,
            # Settlement fields
            actual_result=db_version.actual_result,
            profit_loss=db_version.profit_loss,
            settled_at=db_version.settled_at
        )
