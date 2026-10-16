"""Data quality feature calculations."""

from typing import Optional
from dataclasses import dataclass
from datetime import datetime

from app.features.team_form import TeamFormFeatures
from app.features.attack_defence import AttackDefenceFeatures


@dataclass
class DataQualityFeatures:
    """Data quality and confidence metrics."""
    
    # Sample sizes
    sample_size_home: int = 0
    sample_size_away: int = 0
    
    # Data availability
    xg_available_home: bool = False
    xg_available_away: bool = False
    
    # Data freshness
    data_freshness_seconds: Optional[int] = None
    
    # Missing data ratio (0.0 = no missing, 1.0 = all missing)
    missing_field_ratio: float = 0.0
    
    # Provider availability
    provider_available: bool = True
    
    # Overall confidence score (0.0-1.0)
    feature_confidence: float = 0.0
    
    # Notes
    notes: Optional[str] = None


class DataQualityFeatureCalculator:
    """Calculate data quality metrics."""
    
    def __init__(self, min_sample_size: int = 3):
        """Initialize calculator.
        
        Args:
            min_sample_size: Minimum matches for reliable features
        """
        self.min_sample_size = min_sample_size
    
    def calculate_confidence(
        self,
        home_form: TeamFormFeatures,
        away_form: TeamFormFeatures,
        home_attack_defence: Optional[AttackDefenceFeatures] = None,
        away_attack_defence: Optional[AttackDefenceFeatures] = None,
        data_freshness_seconds: Optional[int] = None
    ) -> DataQualityFeatures:
        """Calculate data quality and confidence metrics.
        
        Args:
            home_form: Home team form features
            away_form: Away team form features
            home_attack_defence: Home team attack/defence features
            away_attack_defence: Away team attack/defence features
            data_freshness_seconds: Age of data in seconds
            
        Returns:
            DataQualityFeatures with confidence score
        """
        # Sample sizes
        sample_size_home = home_form.sample_size
        sample_size_away = away_form.sample_size
        
        # xG availability
        xg_available_home = False
        xg_available_away = False
        if home_attack_defence:
            xg_available_home = (home_attack_defence.xg_per_match is not None)
        if away_attack_defence:
            xg_available_away = (away_attack_defence.xg_per_match is not None)
        
        # Calculate confidence score (0.0-1.0)
        confidence = 0.0
        
        # Sample size component (40% weight)
        min_sample = min(sample_size_home, sample_size_away)
        if min_sample >= self.min_sample_size:
            sample_score = min(1.0, min_sample / 10.0)  # Max out at 10 matches
            confidence += 0.4 * sample_score
        
        # Data availability component (30% weight)
        availability_score = 0.0
        if home_form.is_available and away_form.is_available:
            availability_score = 1.0
        confidence += 0.3 * availability_score
        
        # xG availability component (20% weight)
        xg_score = 0.0
        if xg_available_home and xg_available_away:
            xg_score = 1.0
        elif xg_available_home or xg_available_away:
            xg_score = 0.5
        confidence += 0.2 * xg_score
        
        # Data freshness component (10% weight)
        freshness_score = 1.0
        if data_freshness_seconds is not None:
            # Penalize if data is very old (> 7 days)
            if data_freshness_seconds > 7 * 24 * 3600:
                freshness_score = 0.5
            elif data_freshness_seconds > 30 * 24 * 3600:
                freshness_score = 0.2
        confidence += 0.1 * freshness_score
        
        # Calculate missing field ratio
        total_fields = 10  # Simplified count
        missing_fields = 0
        if not home_form.is_available:
            missing_fields += 2
        if not away_form.is_available:
            missing_fields += 2
        if not xg_available_home:
            missing_fields += 1
        if not xg_available_away:
            missing_fields += 1
        
        missing_field_ratio = missing_fields / total_fields
        
        # Generate notes
        notes = []
        if sample_size_home < self.min_sample_size:
            notes.append(f"Insufficient home team data ({sample_size_home} matches)")
        if sample_size_away < self.min_sample_size:
            notes.append(f"Insufficient away team data ({sample_size_away} matches)")
        if not xg_available_home and not xg_available_away:
            notes.append("xG data not available")
        
        notes_str = "; ".join(notes) if notes else None
        
        return DataQualityFeatures(
            sample_size_home=sample_size_home,
            sample_size_away=sample_size_away,
            xg_available_home=xg_available_home,
            xg_available_away=xg_available_away,
            data_freshness_seconds=data_freshness_seconds,
            missing_field_ratio=missing_field_ratio,
            provider_available=True,
            feature_confidence=confidence,
            notes=notes_str
        )
