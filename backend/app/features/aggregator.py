"""Feature aggregator for combining all feature calculations."""

from typing import Optional
from datetime import datetime
from dataclasses import dataclass, asdict
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.repository import MatchRepository
from app.features.database_extractor import DatabaseFeatureExtractor
from app.features.team_form import TeamFormFeatureCalculator, TeamFormFeatures
from app.features.attack_defence import AttackDefenceFeatureCalculator, AttackDefenceFeatures
from app.features.data_quality import DataQualityFeatureCalculator, DataQualityFeatures
from app.config import settings


class FeatureSet(BaseModel):
    """Complete feature set for a match."""
    
    match_id: str
    
    # Team form features
    home_form: Optional[dict] = None
    away_form: Optional[dict] = None
    
    # Attack/defence features
    attack_defence_home: Optional[dict] = None
    attack_defence_away: Optional[dict] = None
    
    # Data quality
    data_quality: Optional[dict] = None
    
    # Availability flag
    features_available: bool = False
    
    # Metadata
    calculated_at: datetime
    notes: Optional[list] = None
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "match_id": "match_123",
                "home_form": {"wins": 3, "draws": 1, "losses": 1},
                "away_form": {"wins": 2, "draws": 2, "losses": 1},
                "features_available": True,
                "calculated_at": "2024-01-15T15:30:00Z"
            }
        }


class FeatureAggregator:
    """Aggregate all feature calculations for a match.
    
    Coordinates feature extraction from database using historical data only.
    Ensures no data leakage by only using matches before the target match.
    """
    
    def __init__(
        self,
        session: Session,
        min_matches: int = None,
        form_window: int = None
    ):
        """Initialize feature aggregator.
        
        Args:
            session: SQLAlchemy session
            min_matches: Minimum matches for reliable features (from settings)
            form_window: Number of recent matches for form (from settings)
        """
        self.session = session
        self.min_matches = min_matches or settings.min_sample_size
        self.form_window = form_window or settings.team_form_window
        
        self.match_repo = MatchRepository(session)
        self.db_extractor = DatabaseFeatureExtractor(session)
        self.form_calculator = TeamFormFeatureCalculator(
            n=self.form_window,
            min_matches=self.min_matches
        )
        self.attack_defence_calculator = AttackDefenceFeatureCalculator(
            session=session,
            min_matches=self.min_matches
        )
        self.data_quality_calculator = DataQualityFeatureCalculator(
            min_sample_size=self.min_matches
        )
    
    def extract_features_for_match(self, match_id: str) -> FeatureSet:
        """Extract all features for a match.
        
        Args:
            match_id: Match database ID
            
        Returns:
            FeatureSet with all calculated features
        """
        # Get match
        match = self.match_repo.get_by_id(match_id)
        if not match:
            return FeatureSet(
                match_id=match_id,
                features_available=False,
                calculated_at=datetime.utcnow(),
                notes=["Match not found"]
            )
        
        # Get historical matches for both teams (before this match)
        home_matches = self.db_extractor.get_team_historical_matches(
            team_id=match.home_team_id,
            before_datetime=match.scheduled_at,
            limit=20,
            finished_only=True
        )
        
        away_matches = self.db_extractor.get_team_historical_matches(
            team_id=match.away_team_id,
            before_datetime=match.scheduled_at,
            limit=20,
            finished_only=True
        )
        
        # Calculate form features
        home_form = self.form_calculator.calculate_from_matches(
            matches=home_matches,
            team_id=match.home_team_id,
            before_datetime=match.scheduled_at
        )
        
        away_form = self.form_calculator.calculate_from_matches(
            matches=away_matches,
            team_id=match.away_team_id,
            before_datetime=match.scheduled_at
        )
        
        # Calculate attack/defence features
        attack_defence_home = self.attack_defence_calculator.calculate_from_matches(
            matches=home_matches,
            team_id=match.home_team_id,
            before_datetime=match.scheduled_at
        )
        
        attack_defence_away = self.attack_defence_calculator.calculate_from_matches(
            matches=away_matches,
            team_id=match.away_team_id,
            before_datetime=match.scheduled_at
        )
        
        # Calculate data quality
        data_quality = self.data_quality_calculator.calculate_confidence(
            home_form=home_form,
            away_form=away_form,
            home_attack_defence=attack_defence_home,
            away_attack_defence=attack_defence_away,
            data_freshness_seconds=None  # TODO: Calculate from match timestamp
        )
        
        # Determine if features are available
        features_available = (
            home_form.is_available and
            away_form.is_available and
            data_quality.feature_confidence >= 0.3
        )
        
        # Collect notes
        notes = []
        if not home_form.is_available:
            notes.append(f"Insufficient home team data ({home_form.sample_size} matches)")
        if not away_form.is_available:
            notes.append(f"Insufficient away team data ({away_form.sample_size} matches)")
        if not attack_defence_home.xg_per_match:
            notes.append("xG not available for home team")
        if not attack_defence_away.xg_per_match:
            notes.append("xG not available for away team")
        
        return FeatureSet(
            match_id=match_id,
            home_form=asdict(home_form) if home_form else None,
            away_form=asdict(away_form) if away_form else None,
            attack_defence_home=asdict(attack_defence_home) if attack_defence_home else None,
            attack_defence_away=asdict(attack_defence_away) if attack_defence_away else None,
            data_quality=asdict(data_quality) if data_quality else None,
            features_available=features_available,
            calculated_at=datetime.utcnow(),
            notes=notes if notes else None
        )
