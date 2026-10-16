"""Prediction versioning and immutable history tracking.

Tracks prediction evolution through match lifecycle stages:
- 7d_before: 7 days before match
- 24h_before: 24 hours before match
- lineup_confirmed: After lineups announced
- kickoff: At kickoff time
- live: During match (if live predictions enabled)

Once written, a prediction version is NEVER modified (immutable).

DATABASE REQUIREMENT:
The persistence layer MUST enforce a unique constraint on (match_id, stage)
to prevent concurrent processes from creating duplicate stage versions.
This is the final enforcement layer for immutability with concurrent writers.
"""

import copy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum
import uuid


class PredictionStage(str, Enum):
    """Match lifecycle stages for prediction versioning."""
    
    SEVEN_DAYS_BEFORE = "7d_before"
    TWENTY_FOUR_HOURS_BEFORE = "24h_before"
    LINEUP_CONFIRMED = "lineup_confirmed"
    KICKOFF = "kickoff"
    LIVE = "live"
    # Headline picks frozen shortly before kick-off (app/services/headline_tracking). One row per
    # pick, so they must be known to the enum or reading a match's versions would fail.
    HEADLINE_BANKO = "headline_banko"
    HEADLINE_ORANLI = "headline_oranli"


@dataclass
class PredictionVersion:
    """Immutable prediction version snapshot.
    
    Once created, a version's data cannot be modified. Updates create new versions.
    """
    
    # Version identification
    version_id: str
    """Unique version identifier (UUID)"""
    
    match_id: str
    """Match identifier"""
    
    stage: PredictionStage
    """Prediction stage in match lifecycle"""
    
    created_at: datetime
    """When this version was created (UTC)"""
    
    # Prediction data (immutable snapshot)
    prediction_data: Dict[str, Any]
    """Complete prediction output as JSON-serializable dict
    
    Structure:
    {
        "home_win_prob": float,
        "draw_prob": float,
        "away_win_prob": float,
        "home_xg": float,
        "away_xg": float,
        "markets": {...},
        "mensione_pick": {...},
        "confidence": {...},
        "player_impact": {...} or null,
        "tactical_matchup": {...} or null,
        "model_predictions": [...],
        "ensemble_metadata": {...}
    }
    """
    
    # Model metadata
    model_versions: Dict[str, str] = field(default_factory=dict)
    """Model versions used in this prediction: {model_id: version}"""
    
    # Data quality snapshot
    data_quality_score: float = 0.0
    """Data quality score at time of prediction [0, 1]"""
    
    confidence_score: float = 0.0
    """Overall confidence score [0, 1]"""
    
    # Metadata
    notes: List[str] = field(default_factory=list)
    """Any notes or warnings about this version"""
    
    # Frozen TUTAR X Pick (stored at prediction time for track record)
    selected_market: Optional[str] = None
    """Selected market identifier (e.g. 'HOME_WIN', 'OVER_2_5', 'BTTS_YES')"""
    
    selection_text: Optional[str] = None
    """Human-readable selection text (e.g. 'Home Win', 'Over 2.5 Goals')"""
    
    selection_probability: Optional[float] = None
    """Model probability at prediction time [0, 1]"""
    
    selection_confidence: Optional[float] = None
    """Confidence score at prediction time [0, 1]"""
    
    selection_odds: Optional[float] = None
    """Bookmaker odds at prediction time (if available)"""
    
    selection_fair_odds: Optional[float] = None
    """Fair odds calculated from model probability"""
    
    selection_edge: Optional[float] = None
    """Edge over bookmaker odds at prediction time (probability - implied_probability)"""
    
    value_classification: Optional[str] = None
    """Value classification: 'STRONG_VALUE', 'VALUE', 'NEUTRAL', 'NEGATIVE_VALUE'"""
    
    risk_level: Optional[str] = None
    """Risk level: 'LOW', 'MEDIUM', 'HIGH'"""
    
    # Result Tracking (populated after match settlement — FUTURE USE)
    actual_result: Optional[str] = None
    """Actual outcome: 'WON', 'LOST', 'PUSH', 'VOID'"""
    
    profit_loss: Optional[float] = None
    """Profit/loss in units (e.g. +0.85, -1.00)"""
    
    settled_at: Optional[datetime] = None
    """Timestamp when result was recorded"""
    
    def __post_init__(self):
        """Validate version after initialization."""
        if not self.version_id:
            raise ValueError("version_id cannot be empty")
        
        if not self.match_id:
            raise ValueError("match_id cannot be empty")
        
        if not isinstance(self.stage, PredictionStage):
            # Try to convert string to enum
            if isinstance(self.stage, str):
                self.stage = PredictionStage(self.stage)
            else:
                raise ValueError(f"stage must be PredictionStage, got {type(self.stage)}")
        
        if not (0.0 <= self.data_quality_score <= 1.0):
            raise ValueError(f"data_quality_score must be in [0, 1], got {self.data_quality_score}")
        
        if not (0.0 <= self.confidence_score <= 1.0):
            raise ValueError(f"confidence_score must be in [0, 1], got {self.confidence_score}")


class PredictionVersionManager:
    """Manages prediction versioning and immutable history.
    
    Features:
    - Immutable version storage (no updates after creation)
    - Stage-based versioning
    - Complete version history retrieval
    - Duplicate stage detection (optional overwrite)
    
    Versions are persisted through PredictionPersistenceService.
    """
    
    def __init__(self, persistence_service=None):
        """Initialize version manager.
        
        Args:
            persistence_service: Optional PredictionPersistenceService for database storage
        """
        self.persistence_service = persistence_service
        # In-memory storage for testing (fallback if no persistence)
        self._memory_store: Dict[str, List[PredictionVersion]] = {}
    
    def create_version(
        self,
        match_id: str,
        stage: PredictionStage,
        prediction_data: Dict[str, Any],
        model_versions: Optional[Dict[str, str]] = None,
        data_quality_score: float = 0.0,
        confidence_score: float = 0.0,
        notes: Optional[List[str]] = None,
        allow_stage_overwrite: bool = False,
        mensione_pick: Optional[Any] = None
    ) -> PredictionVersion:
        """Create new prediction version.
        
        Args:
            match_id: Match identifier
            stage: Prediction stage
            prediction_data: Complete prediction output
            model_versions: Model versions used
            data_quality_score: Data quality score
            confidence_score: Confidence score
            notes: Optional notes
            allow_stage_overwrite: If True, allow multiple versions for same stage
            mensione_pick: Optional TUTAR X pick data (BestTip or PassDecision dict, parameter name kept for backward compatibility)
        
        Returns:
            Created PredictionVersion
        
        Raises:
            ValueError: If stage already exists and allow_stage_overwrite=False,
                       or if database constraint violation occurs
        """
        # Check for existing version at this stage
        if not allow_stage_overwrite:
            existing = self.get_version_by_stage(match_id, stage)
            if existing:
                raise ValueError(
                    f"Version already exists for match {match_id} at stage {stage.value}. "
                    f"Set allow_stage_overwrite=True to create duplicate."
                )
        
        # Create version
        version = PredictionVersion(
            version_id=str(uuid.uuid4()),
            match_id=match_id,
            stage=stage,
            created_at=datetime.utcnow(),
            prediction_data=copy.deepcopy(prediction_data),  # Deep copy to ensure immutability
            model_versions=model_versions or {},
            data_quality_score=data_quality_score,
            confidence_score=confidence_score,
            notes=notes or []
        )
        
        # Populate frozen pick fields from tutar_x_pick (mensione_pick parameter) if provided
        if mensione_pick is not None:
            if isinstance(mensione_pick, dict):
                # BestTip dict has 'market' key; PassDecision dict has 'pass_decision': True
                if mensione_pick.get('pass_decision') is not True and 'market' in mensione_pick:
                    # BestTip: populate frozen pick fields
                    version.selected_market = mensione_pick.get('market')
                    version.selection_text = mensione_pick.get('selection')
                    version.selection_probability = mensione_pick.get('probability')
                    version.selection_confidence = mensione_pick.get('confidence')
                    version.selection_odds = mensione_pick.get('bookmaker_odds')
                    version.selection_fair_odds = mensione_pick.get('fair_odds')
                    version.selection_edge = mensione_pick.get('edge')
                    version.value_classification = mensione_pick.get('value_classification')
                    version.risk_level = mensione_pick.get('risk_level')
                # PassDecision: leave frozen pick fields as None (no selection was made)
        
        # Persist version
        if self.persistence_service:
            try:
                self.persistence_service.save_version(version)
            except Exception as e:
                # Handle database-level unique constraint violations
                # This catches concurrent writers that passed the check above
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in ['unique', 'constraint', 'duplicate', 'integrity']):
                    raise ValueError(
                        f"Database constraint violation: version already exists for "
                        f"match {match_id} at stage {stage.value}. "
                        f"Another process created this version concurrently."
                    ) from e
                # Re-raise other exceptions
                raise
        else:
            # Fallback to in-memory
            if match_id not in self._memory_store:
                self._memory_store[match_id] = []
            self._memory_store[match_id].append(version)
        
        return version
    
    def get_versions(self, match_id: str) -> List[PredictionVersion]:
        """Get all prediction versions for a match.
        
        Args:
            match_id: Match identifier
        
        Returns:
            List of PredictionVersion ordered by created_at (oldest first)
        """
        if self.persistence_service:
            versions = self.persistence_service.get_versions(match_id)
        else:
            versions = self._memory_store.get(match_id, [])
        
        # Sort by creation time
        versions.sort(key=lambda v: v.created_at)
        
        return versions
    
    def get_latest_version(self, match_id: str) -> Optional[PredictionVersion]:
        """Get most recent prediction version for a match.
        
        Args:
            match_id: Match identifier
        
        Returns:
            Latest PredictionVersion or None if no versions exist
        """
        versions = self.get_versions(match_id)
        return versions[-1] if versions else None
    
    def get_version_by_id(self, version_id: str) -> Optional[PredictionVersion]:
        """Get specific prediction version by ID.
        
        Args:
            version_id: Version identifier
        
        Returns:
            PredictionVersion or None if not found
        """
        if self.persistence_service:
            return self.persistence_service.get_version_by_id(version_id)
        else:
            # Memory store fallback
            for match_versions in self._memory_store.values():
                for version in match_versions:
                    if version.version_id == version_id:
                        return version
            return None
    
    def get_version_by_stage(
        self,
        match_id: str,
        stage: PredictionStage
    ) -> Optional[PredictionVersion]:
        """Get prediction version for specific stage.
        
        If multiple versions exist for the stage, returns the latest.
        
        Args:
            match_id: Match identifier
            stage: Prediction stage
        
        Returns:
            PredictionVersion for stage or None if not found
        """
        versions = self.get_versions(match_id)
        stage_versions = [v for v in versions if v.stage == stage]
        
        return stage_versions[-1] if stage_versions else None
    
    def get_version_evolution(self, match_id: str) -> List[Dict[str, Any]]:
        """Get simplified version evolution for match.
        
        Returns compact representation of how prediction evolved over time.
        
        Args:
            match_id: Match identifier
        
        Returns:
            List of dicts with stage, timestamp, key metrics
        """
        versions = self.get_versions(match_id)
        
        evolution = []
        for version in versions:
            pred_data = version.prediction_data
            
            evolution.append({
                "stage": version.stage.value,
                "created_at": version.created_at.isoformat(),
                "home_win_prob": pred_data.get("home_win_prob"),
                "draw_prob": pred_data.get("draw_prob"),
                "away_win_prob": pred_data.get("away_win_prob"),
                "mensione_pick": pred_data.get("mensione_pick", {}).get("pick_market") if pred_data.get("mensione_pick") else None,
                "confidence": version.confidence_score
            })
        
        return evolution
    
    def delete_version(self, version_id: str) -> bool:
        """Delete a specific version.
        
        WARNING: This violates immutability principle. Use only for:
        - Testing/development cleanup
        - GDPR/legal compliance
        - Correcting serious errors
        
        Args:
            version_id: Version identifier to delete
        
        Returns:
            True if deleted, False if not found
        """
        if self.persistence_service:
            return self.persistence_service.delete_version(version_id)
        else:
            # In-memory deletion
            for match_id, versions in self._memory_store.items():
                for i, version in enumerate(versions):
                    if version.version_id == version_id:
                        del self._memory_store[match_id][i]
                        return True
            return False
    
    def settle_prediction(
        self,
        version_id: str,
        provider: 'FootballDataProvider',
        stake: float = 1.0
    ) -> Optional[PredictionVersion]:
        """Settle a prediction with actual match result.
        
        Args:
            version_id: Version identifier to settle
            provider: Football data provider for fetching results
            stake: Betting stake in units (default: 1.0)
        
        Returns:
            Updated PredictionVersion with settlement data
        
        Raises:
            ValueError: If version not found, already settled, or result not available
        """
        from app.prediction.result_ingestion import ResultIngestionService
        from app.prediction.settlement import SettlementEngine
        
        # Get version
        version = self.get_version_by_id(version_id) if self.persistence_service else None
        
        if version is None:
            # Try memory store
            for match_versions in self._memory_store.values():
                for v in match_versions:
                    if v.version_id == version_id:
                        version = v
                        break
                if version:
                    break
        
        if version is None:
            raise ValueError(f"Version {version_id} not found")
        
        # Check if already settled
        if version.actual_result is not None:
            raise ValueError(f"Version {version_id} is already settled: {version.actual_result}")
        
        # Check if version has frozen pick
        if version.selected_market is None or version.selection_text is None or version.selection_odds is None:
            raise ValueError(
                f"Version {version_id} has no frozen pick data. "
                f"Cannot settle predictions without selected_market, selection_text, and selection_odds."
            )
        
        # Fetch match result
        ingestion = ResultIngestionService(provider)
        match_result = ingestion.get_match_result(version.match_id)
        
        if match_result is None:
            raise ValueError(f"Match {version.match_id} not found in provider")
        
        if not match_result.is_settleable():
            raise ValueError(
                f"Match {version.match_id} is not settleable: "
                f"status={match_result.status}"
            )
        
        # Settle prediction
        engine = SettlementEngine(stake=stake)
        outcome, profit_loss = engine.settle_prediction(
            selected_market=version.selected_market,
            selection_text=version.selection_text,
            selection_odds=version.selection_odds,
            match_result=match_result
        )
        
        # Update version (create new object to maintain immutability principle)
        settled_version = PredictionVersion(
            version_id=version.version_id,
            match_id=version.match_id,
            stage=version.stage,
            created_at=version.created_at,
            prediction_data=version.prediction_data,
            model_versions=version.model_versions,
            data_quality_score=version.data_quality_score,
            confidence_score=version.confidence_score,
            notes=version.notes,
            # Frozen pick fields (unchanged)
            selected_market=version.selected_market,
            selection_text=version.selection_text,
            selection_probability=version.selection_probability,
            selection_confidence=version.selection_confidence,
            selection_odds=version.selection_odds,
            selection_fair_odds=version.selection_fair_odds,
            selection_edge=version.selection_edge,
            value_classification=version.value_classification,
            risk_level=version.risk_level,
            # Settlement fields (NEW)
            actual_result=outcome.value,
            profit_loss=profit_loss,
            settled_at=datetime.utcnow()
        )
        
        # Persist settlement
        if self.persistence_service:
            # Update database record (ONLY settlement fields)
            from app.database.models import PredictionVersionDB
            db_version = self.persistence_service.session.query(PredictionVersionDB).filter(
                PredictionVersionDB.id == version_id
            ).first()
            
            if db_version:
                db_version.actual_result = outcome.value
                db_version.profit_loss = profit_loss
                db_version.settled_at = settled_version.settled_at
                self.persistence_service.session.commit()
        else:
            # Update memory store
            for match_id, versions in self._memory_store.items():
                for i, v in enumerate(versions):
                    if v.version_id == version_id:
                        self._memory_store[match_id][i] = settled_version
                        break
        
        return settled_version
    
    def get_settled_picks_by_market(
        self,
        market_type: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[PredictionVersion]:
        """Get all settled picks for a specific market type.
        
        Args:
            market_type: Market identifier (e.g. 'HOME_WIN', 'OVER_2_5', 'BTTS_YES')
            start_date: Optional start date filter (settled_at >= start_date)
            end_date: Optional end date filter (settled_at <= end_date)
        
        Returns:
            List of settled PredictionVersion objects for the market
        """
        if self.persistence_service:
            from app.database.models import PredictionVersionDB
            
            query = self.persistence_service.session.query(PredictionVersionDB).filter(
                PredictionVersionDB.actual_result.isnot(None),  # Only settled
                PredictionVersionDB.selected_market.isnot(None)  # Only with picks
            )
            
            # Filter by market type (flexible matching)
            market_upper = market_type.upper()
            query = query.filter(
                PredictionVersionDB.selected_market.ilike(f'%{market_upper}%')
            )
            
            # Date filtering
            if start_date:
                query = query.filter(PredictionVersionDB.settled_at >= start_date)
            
            if end_date:
                query = query.filter(PredictionVersionDB.settled_at <= end_date)
            
            # Order by settlement date
            query = query.order_by(PredictionVersionDB.settled_at.desc())
            
            db_versions = query.all()
            
            return [self.persistence_service._to_domain_version(v) for v in db_versions]
        else:
            # Memory store fallback
            settled = []
            for match_versions in self._memory_store.values():
                for version in match_versions:
                    # Check if settled
                    if version.actual_result is None or version.selected_market is None:
                        continue
                    
                    # Check market match
                    if market_type.upper() not in version.selected_market.upper():
                        continue
                    
                    # Check date filters
                    if start_date and version.settled_at < start_date:
                        continue
                    
                    if end_date and version.settled_at > end_date:
                        continue
                    
                    settled.append(version)
            
            # Sort by settlement date
            settled.sort(key=lambda v: v.settled_at, reverse=True)
            
            return settled
