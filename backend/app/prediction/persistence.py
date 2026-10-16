"""Prediction persistence service.

Handles database storage for:
- Prediction versions (immutable history)
- Track record results
- Change attributions
"""

from typing import Dict, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.prediction.prediction_version import PredictionVersion, PredictionStage
from app.prediction.track_record import PredictionResult


class PredictionPersistenceService:
    """Persistence service for prediction data.
    
    Handles CRUD operations for:
    - Prediction versions
    - Track record results
    - Change attributions
    
    Uses SQLAlchemy ORM for database access.
    """
    
    def __init__(self, session: Session):
        """Initialize persistence service.
        
        Args:
            session: SQLAlchemy session
        """
        self.session = session
    
    # ===== Prediction Version Operations =====
    
    def save_version(self, version: PredictionVersion) -> None:
        """Save prediction version to database.
        
        Args:
            version: PredictionVersion to save
        """
        # Import here to avoid circular dependency
        from app.database.models import PredictionVersionDB
        
        # Convert to database model
        db_version = PredictionVersionDB(
            id=version.version_id,
            match_id=version.match_id,
            stage=version.stage.value,
            created_at=version.created_at,
            prediction_data=version.prediction_data,
            model_versions=version.model_versions,
            data_quality_score=version.data_quality_score,
            confidence_score=version.confidence_score,
            notes=version.notes if version.notes else [],
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
            # Settlement fields (None at creation)
            actual_result=version.actual_result,
            profit_loss=version.profit_loss,
            settled_at=version.settled_at,
        )
        
        self.session.add(db_version)
        self.session.commit()
    
    def get_versions(self, match_id: str) -> List[PredictionVersion]:
        """Get all prediction versions for a match.
        
        Args:
            match_id: Match identifier
        
        Returns:
            List of PredictionVersion
        """
        from app.database.models import PredictionVersionDB
        
        db_versions = (
            self.session.query(PredictionVersionDB)
            .filter(PredictionVersionDB.match_id == match_id)
            .order_by(PredictionVersionDB.created_at)
            .all()
        )
        
        return [self._to_domain_version(v) for v in db_versions]
    
    def get_version_by_id(self, version_id: str) -> Optional[PredictionVersion]:
        """Get specific prediction version.
        
        Args:
            version_id: Version identifier
        
        Returns:
            PredictionVersion or None
        """
        from app.database.models import PredictionVersionDB
        
        db_version = (
            self.session.query(PredictionVersionDB)
            .filter(PredictionVersionDB.id == version_id)
            .first()
        )
        
        return self._to_domain_version(db_version) if db_version else None
    
    def delete_version(self, version_id: str) -> bool:
        """Delete prediction version.
        
        Args:
            version_id: Version identifier
        
        Returns:
            True if deleted, False if not found
        """
        from app.database.models import PredictionVersionDB
        
        db_version = (
            self.session.query(PredictionVersionDB)
            .filter(PredictionVersionDB.id == version_id)
            .first()
        )
        
        if db_version:
            self.session.delete(db_version)
            self.session.commit()
            return True
        
        return False
    
    def _to_domain_version(self, db_version) -> PredictionVersion:
        """Convert database model to domain model.
        
        Args:
            db_version: Database PredictionVersionDB
        
        Returns:
            Domain PredictionVersion
        """
        return PredictionVersion(
            version_id=db_version.id,
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
            settled_at=db_version.settled_at,
        )
    
    # ===== Track Record Operations =====
    
    def save_track_record(self, result: PredictionResult) -> None:
        """Save prediction result to track record.
        
        Args:
            result: PredictionResult to save
        """
        from app.database.models import TrackRecordDB
        
        # Convert to database model
        db_record = TrackRecordDB(
            prediction_version_id=result.prediction_version_id,
            match_id=result.match_id,
            predicted_home_win=result.predicted_home_win,
            predicted_draw=result.predicted_draw,
            predicted_away_win=result.predicted_away_win,
            actual_outcome=result.actual_outcome.value,
            actual_home_score=result.actual_home_score,
            actual_away_score=result.actual_away_score,
            prediction_timestamp=result.prediction_timestamp,
            match_timestamp=result.match_timestamp,
            over_2_5_predicted=result.over_2_5_predicted,
            over_2_5_actual=result.over_2_5_actual,
            btts_predicted=result.btts_predicted,
            btts_actual=result.btts_actual,
            home_odds=result.home_odds,
            draw_odds=result.draw_odds,
            away_odds=result.away_odds,
            league_id=result.league_id,
            model_id=result.model_id,
            stage=result.stage
        )
        
        self.session.add(db_record)
        self.session.commit()
    
    def get_track_record(self, filters: Dict) -> List[PredictionResult]:
        """Get track record with filters.
        
        Args:
            filters: Filter dict (league_id, model_id, stage, date_from, date_to)
        
        Returns:
            List of PredictionResult
        """
        from app.database.models import TrackRecordDB
        
        query = self.session.query(TrackRecordDB)
        
        # Apply filters
        if "league_id" in filters:
            query = query.filter(TrackRecordDB.league_id == filters["league_id"])
        
        if "model_id" in filters:
            query = query.filter(TrackRecordDB.model_id == filters["model_id"])
        
        if "stage" in filters:
            query = query.filter(TrackRecordDB.stage == filters["stage"])
        
        if "date_from" in filters:
            query = query.filter(TrackRecordDB.prediction_timestamp >= filters["date_from"])
        
        if "date_to" in filters:
            query = query.filter(TrackRecordDB.prediction_timestamp <= filters["date_to"])
        
        db_records = query.all()
        
        return [self._to_domain_result(r) for r in db_records]
    
    def _to_domain_result(self, db_record) -> PredictionResult:
        """Convert database model to domain model.
        
        Args:
            db_record: Database TrackRecordDB
        
        Returns:
            Domain PredictionResult
        """
        from app.prediction.track_record import PredictionOutcome
        
        return PredictionResult(
            prediction_version_id=db_record.prediction_version_id,
            match_id=db_record.match_id,
            predicted_home_win=db_record.predicted_home_win,
            predicted_draw=db_record.predicted_draw,
            predicted_away_win=db_record.predicted_away_win,
            actual_outcome=PredictionOutcome(db_record.actual_outcome),
            actual_home_score=db_record.actual_home_score,
            actual_away_score=db_record.actual_away_score,
            prediction_timestamp=db_record.prediction_timestamp,
            match_timestamp=db_record.match_timestamp,
            over_2_5_predicted=db_record.over_2_5_predicted,
            over_2_5_actual=db_record.over_2_5_actual,
            btts_predicted=db_record.btts_predicted,
            btts_actual=db_record.btts_actual,
            home_odds=db_record.home_odds,
            draw_odds=db_record.draw_odds,
            away_odds=db_record.away_odds,
            league_id=db_record.league_id,
            model_id=db_record.model_id,
            stage=db_record.stage
        )
