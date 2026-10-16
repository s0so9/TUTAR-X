"""Logistic Regression model training service.

Trains logistic regression model using historical match data with proper
temporal validation to prevent data leakage.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Optional
import pickle
import os
from pathlib import Path

from sqlalchemy.orm import Session
from app.database.models import Match, MatchStatus, MatchOutcome
from app.features.match_features import MatchFeatureExtractor
from app.prediction.logistic_regression import LogisticRegressionModel
from app.domain.match import Match as DomainMatch

logger = logging.getLogger(__name__)


class LogisticRegressionTrainer:
    """Trainer for LogisticRegression model using historical data."""
    
    def __init__(
        self, 
        session: Session,
        min_training_samples: int = 100,
        validation_split: float = 0.2,
        model_cache_path: Optional[str] = None  # Use default from model_paths if None
    ):
        """Initialize trainer.
        
        Args:
            session: Database session
            min_training_samples: Minimum samples needed for training
            validation_split: Fraction of data for validation
            model_cache_path: Path to save/load trained model
        """
        self.session = session
        self.min_training_samples = min_training_samples
        self.validation_split = validation_split
        self.model_cache_path = Path(model_cache_path)
        
        # Ensure cache directory exists
        self.model_cache_path.parent.mkdir(parents=True, exist_ok=True)
    
    def train_or_load_model(self) -> Optional[LogisticRegressionModel]:
        """Train new model or load cached one if available.
        
        Returns:
            Trained LogisticRegressionModel or None if insufficient data
        """
        # Try to load existing model first
        if self.model_cache_path.exists():
            try:
                model = self._load_cached_model()
                if model and model.is_fitted():
                    logger.info(f"Loaded cached logistic regression model from {self.model_cache_path}")
                    return model
            except Exception as e:
                logger.warning(f"Failed to load cached model: {e}")
        
        # Train new model
        logger.info("Training new logistic regression model")
        return self._train_new_model()
    
    def _load_cached_model(self) -> Optional[LogisticRegressionModel]:
        """Load model from cache file."""
        with open(self.model_cache_path, 'rb') as f:
            model_data = pickle.load(f)
        
        model = LogisticRegressionModel()
        model._weights = model_data['weights']
        model._training_stats = model_data.get('training_stats')
        model._is_fitted = model_data.get('is_fitted', True)
        model.feature_keys = model_data.get('feature_keys', model.feature_keys)
        
        return model
    
    def _save_model(self, model: LogisticRegressionModel) -> None:
        """Save trained model to cache."""
        model_data = {
            'weights': model._weights,
            'training_stats': model._training_stats,
            'is_fitted': model._is_fitted,
            'feature_keys': model.feature_keys,
            'trained_at': datetime.now().isoformat(),
        }
        
        with open(self.model_cache_path, 'wb') as f:
            pickle.dump(model_data, f)
        
        logger.info(f"Saved trained model to {self.model_cache_path}")
    
    def _train_new_model(self) -> Optional[LogisticRegressionModel]:
        """Train a new logistic regression model."""
        # Get finished matches with outcomes
        matches = self.session.query(Match).filter(
            Match.status == MatchStatus.FINISHED,
            Match.home_score.isnot(None),
            Match.away_score.isnot(None),
            Match.outcome.isnot(None)
        ).order_by(Match.scheduled_at).all()
        
        if len(matches) < self.min_training_samples:
            logger.warning(
                f"Insufficient training data: {len(matches)} matches, "
                f"need {self.min_training_samples}"
            )
            return None
        
        logger.info(f"Found {len(matches)} finished matches for training")
        
        # Prepare feature extractor with database session
        feature_extractor = MatchFeatureExtractor(
            provider=self.session,  # Using session as provider (will trigger minimal context)
            db_session=self.session
        )
        
        # Extract features and labels for all matches
        training_samples = []
        successful_extractions = 0
        
        for i, match in enumerate(matches):
            try:
                # Convert DB match to domain match
                domain_match = self._convert_db_to_domain_match(match)
                
                # Extract features (temporal safety ensured by feature extractor)
                features = feature_extractor.extract_features(domain_match)
                
                # Convert outcome to label
                label = self._outcome_to_label(match.outcome)
                if label:
                    training_samples.append((features, label))
                    successful_extractions += 1
                
                if (i + 1) % 100 == 0:
                    logger.info(f"Processed {i+1}/{len(matches)} matches")
                    
            except Exception as e:
                logger.warning(f"Failed to extract features for match {match.id}: {e}")
                continue
        
        if len(training_samples) < self.min_training_samples:
            logger.warning(
                f"Insufficient valid training samples: {len(training_samples)}, "
                f"need {self.min_training_samples}"
            )
            return None
        
        logger.info(f"Successfully extracted features for {successful_extractions} matches")
        
        # Split into train/validation
        split_idx = int(len(training_samples) * (1 - self.validation_split))
        train_samples = training_samples[:split_idx]
        val_samples = training_samples[split_idx:]
        
        logger.info(f"Training set: {len(train_samples)} samples")
        logger.info(f"Validation set: {len(val_samples)} samples")
        
        # Train model
        model = LogisticRegressionModel()
        
        try:
            model.fit(train_samples)
            logger.info("Model training completed successfully")
            
            # Validate model performance
            self._validate_model(model, val_samples)
            
            # Save trained model
            self._save_model(model)
            
            return model
            
        except Exception as e:
            logger.error(f"Model training failed: {e}", exc_info=True)
            return None
    
    def _convert_db_to_domain_match(self, db_match: Match) -> DomainMatch:
        """Convert database match to domain match."""
        return DomainMatch(
            id=db_match.id,
            competition_id=db_match.competition_id,
            season_id=db_match.season or "unknown",
            home_team_id=db_match.home_team_id,
            away_team_id=db_match.away_team_id,
            scheduled_at=db_match.scheduled_at,
            status=db_match.status.value if db_match.status else "unknown",
            home_score=db_match.home_score,
            away_score=db_match.away_score,
            venue=db_match.venue_name
        )
    
    def _outcome_to_label(self, outcome: MatchOutcome) -> Optional[str]:
        """Convert match outcome to training label."""
        if outcome == MatchOutcome.HOME_WIN:
            return "home_win"
        elif outcome == MatchOutcome.DRAW:
            return "draw"
        elif outcome == MatchOutcome.AWAY_WIN:
            return "away_win"
        return None
    
    def _validate_model(self, model: LogisticRegressionModel, val_samples: List[Tuple]) -> None:
        """Validate trained model on validation set."""
        if not val_samples:
            logger.warning("No validation samples available")
            return
        
        correct = 0
        total = len(val_samples)
        
        for features, true_label in val_samples:
            try:
                prediction = model.predict_legacy(features)
                predicted_label = self._prediction_to_label(prediction)
                
                if predicted_label == true_label:
                    correct += 1
                    
            except Exception as e:
                logger.warning(f"Validation prediction failed: {e}")
                continue
        
        accuracy = correct / total if total > 0 else 0.0
        logger.info(f"Validation accuracy: {accuracy:.3f} ({correct}/{total})")
    
    def _prediction_to_label(self, prediction) -> str:
        """Convert prediction probabilities to label."""
        if prediction.home_win >= prediction.draw and prediction.home_win >= prediction.away_win:
            return "home_win"
        elif prediction.draw >= prediction.away_win:
            return "draw"
        else:
            return "away_win"