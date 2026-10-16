"""Database-backed prediction service for production use.

Extends the existing prediction service to use database features and
provide enhanced responses with provider metadata and latency information.
"""

from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.prediction.service import PredictionService
from app.features.aggregator import FeatureAggregator
from app.features.snapshot_cache import FeatureSnapshotCache
from app.latency.tracker import LatencyTracker
from app.database.repository import MatchRepository, LatencyLogRepository
from app.domain.prediction import Prediction
from app.domain.analysis import AnalysisContext


class DatabasePredictionService(PredictionService):
    """Enhanced prediction service using database features.
    
    Extends PredictionService with:
    - Database-backed feature extraction
    - Latency tracking
    - Provider metadata
    - Confidence scores
    """
    
    def __init__(
        self,
        provider,
        session: Optional[Session] = None,
        feature_aggregator: Optional[FeatureAggregator] = None,
        **kwargs
    ):
        """Initialize database prediction service.
        
        Args:
            provider: Data provider (for compatibility)
            session: SQLAlchemy session for database access
            feature_aggregator: Feature aggregator instance
            **kwargs: Additional arguments passed to parent
        """
        super().__init__(provider, **kwargs)
        self.session = session
        self.feature_aggregator = feature_aggregator
        
        if session:
            self.match_repo = MatchRepository(session)
            self.latency_log_repo = LatencyLogRepository(session)
        else:
            self.match_repo = None
            self.latency_log_repo = None
    
    def generate_prediction_with_db_features(
        self,
        match_db_id: str,
        latency_tracker: Optional[LatencyTracker] = None
    ) -> Optional[Prediction]:
        """Generate prediction using database features.
        
        Uses request-scoped feature cache to deduplicate expensive calculations.
        
        Args:
            match_db_id: Database match ID
            latency_tracker: Optional latency tracker
            
        Returns:
            Enhanced Prediction with confidence and metadata
        """
        if not self.session or not self.feature_aggregator:
            # Fall back to in-memory prediction
            return None
        
        # Create request-scoped feature cache
        feature_cache = FeatureSnapshotCache()
        
        # Pass cache to feature aggregator's engineer (if it exists)
        original_engineer = None
        if hasattr(self.feature_aggregator, 'advanced_engineer') and self.feature_aggregator.advanced_engineer:
            original_engineer = self.feature_aggregator.advanced_engineer
            # Create new engineer with cache
            from app.features.advanced_feature_engineering import AdvancedFeatureEngineer
            cached_engineer = AdvancedFeatureEngineer(
                create_interactions=original_engineer.create_interactions,
                interactions=original_engineer.interactions,
                feature_cache=feature_cache
            )
            self.feature_aggregator.advanced_engineer = cached_engineer
        
        try:
            # Get match from database
            match_db = self.match_repo.get_by_id(match_db_id)
            if not match_db:
                return None
            
            # Extract features
            feature_set = self.feature_aggregator.extract_features_for_match(match_db_id)
            
            if not feature_set.features_available:
                # Insufficient data for prediction
                return None
            
            # Convert database match to domain match (for compatibility with existing code)
            from app.domain.match import Match
            from app.domain.enums import MatchStatus
            
            domain_match = Match(
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
            
            # Generate prediction using parent method
            prediction = self.generate_prediction(domain_match)
            
            if prediction and feature_set.data_quality:
                # Enhance with confidence from data quality
                prediction.confidence = feature_set.data_quality.get('feature_confidence')
            
            return prediction
        
        finally:
            # Clear cache and restore original engineer
            feature_cache.clear()
            if original_engineer:
                self.feature_aggregator.advanced_engineer = original_engineer
    
    def build_enhanced_analysis_context(
        self,
        match_db_id: str,
        prediction: Optional[Prediction] = None,
        latency_tracker: Optional[LatencyTracker] = None
    ) -> AnalysisContext:
        """Build enhanced analysis context with database features.
        
        Args:
            match_db_id: Database match ID
            prediction: Generated prediction
            latency_tracker: Optional latency tracker
            
        Returns:
            Enhanced AnalysisContext with feature_set and latency
        """
        if not self.session or not self.feature_aggregator:
            # Fall back to in-memory context
            match_db = self.match_repo.get_by_id(match_db_id) if self.match_repo else None
            if not match_db:
                return None
            
            from app.domain.match import Match
            domain_match = Match(
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
            return self.build_analysis_context(domain_match, prediction)
        
        # Get match from database
        match_db = self.match_repo.get_by_id(match_db_id)
        if not match_db:
            return None
        
        # Extract features
        feature_set = self.feature_aggregator.extract_features_for_match(match_db_id)
        
        # Convert to domain match
        from app.domain.match import Match
        domain_match = Match(
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
        
        # Build base context
        context = self.build_analysis_context(domain_match, prediction)
        
        # Enhance context with database features (stored as dict in statistical_features)
        if feature_set.features_available:
            enhanced_features = context.statistical_features or {}
            
            # Add form features
            if feature_set.home_form:
                for key, value in feature_set.home_form.items():
                    enhanced_features[f"home_{key}"] = value
            
            if feature_set.away_form:
                for key, value in feature_set.away_form.items():
                    enhanced_features[f"away_{key}"] = value
            
            # Add attack/defence features
            if feature_set.attack_defence_home:
                for key, value in feature_set.attack_defence_home.items():
                    enhanced_features[f"home_attack_defence_{key}"] = value
            
            if feature_set.attack_defence_away:
                for key, value in feature_set.attack_defence_away.items():
                    enhanced_features[f"away_attack_defence_{key}"] = value
            
            context.statistical_features = enhanced_features
        
        # Add provider metadata if available
        if hasattr(context, 'provider_metadata'):
            context.provider_metadata = {
                'selected_provider': match_db.provider_source.name if match_db.provider_source else None,
                'fetched_at': match_db.provider_fetched_at,
                'source_updated_at': match_db.provider_updated_at,
            }
        
        # Add latency metrics if available
        if latency_tracker and hasattr(context, 'latency_metrics'):
            metrics = latency_tracker.track_api_response()
            context.latency_metrics = metrics.dict()
        
        # Add data quality notes
        if feature_set.notes:
            if context.missing_data_notes:
                context.missing_data_notes.extend(feature_set.notes)
            else:
                context.missing_data_notes = feature_set.notes
        
        return context
