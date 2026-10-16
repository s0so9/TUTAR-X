"""League context manager for league-aware prediction parameters.

This module provides league-specific parameters like scoring environment,
home advantage, and draw tendency.

Features:
- Hierarchical fallback (specific league → competition family → global defaults)
- Bayesian shrinkage for small samples (blend league-specific with global)
- Pre-seeded global defaults
- League-specific values updated from historical data
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class LeagueProfile:
    """League-specific parameters for predictions."""
    
    league_id: str
    league_name: str
    
    # Scoring environment
    scoring_environment: float
    """Average goals per game in this league"""
    
    home_advantage_factor: float
    """Home advantage multiplier (typical: 1.2-1.4)"""
    
    draw_tendency: float
    """Draw probability baseline (typical: 0.25-0.30)"""
    
    # Data quality
    matches_analyzed: int = 0
    """Number of matches used to calculate these parameters"""
    
    confidence: float = 1.0
    """Confidence in parameters [0, 1] based on sample size"""
    
    # Competition family (for fallback)
    competition_family: Optional[str] = None
    """e.g., "top_5_european", "lower_european", "south_american", etc."""


class LeagueContextManager:
    """Manager for league-aware prediction parameters.
    
    Provides league-specific parameters with hierarchical fallback
    and Bayesian shrinkage for leagues with small sample sizes.
    """
    
    # Global defaults (based on aggregate football data)
    GLOBAL_DEFAULTS = {
        "scoring_environment": 2.7,  # Average goals per game globally
        "home_advantage_factor": 1.3,  # 30% home advantage
        "draw_tendency": 0.27,  # 27% of matches end in draws
    }
    
    # Competition family defaults
    FAMILY_DEFAULTS = {
        "top_5_european": {
            "scoring_environment": 2.75,
            "home_advantage_factor": 1.28,
            "draw_tendency": 0.26,
        },
        "lower_european": {
            "scoring_environment": 2.60,
            "home_advantage_factor": 1.32,
            "draw_tendency": 0.28,
        },
        "south_american": {
            "scoring_environment": 2.55,
            "home_advantage_factor": 1.40,  # Stronger home advantage
            "draw_tendency": 0.25,
        },
        "asian": {
            "scoring_environment": 2.65,
            "home_advantage_factor": 1.30,
            "draw_tendency": 0.27,
        },
    }
    
    MIN_MATCHES_FOR_RELIABILITY = 100
    """Minimum matches for full confidence in league-specific parameters"""
    
    def __init__(self):
        """Initialize league context manager."""
        self.league_profiles: Dict[str, LeagueProfile] = {}
        self._initialize_default_leagues()
    
    def _initialize_default_leagues(self) -> None:
        """Initialize profiles for major leagues with default parameters."""
        # Top 5 European leagues
        major_leagues = {
            "premier_league": ("Premier League", "top_5_european"),
            "la_liga": ("La Liga", "top_5_european"),
            "bundesliga": ("Bundesliga", "top_5_european"),
            "serie_a": ("Serie A", "top_5_european"),
            "ligue_1": ("Ligue 1", "top_5_european"),
        }
        
        for league_id, (league_name, family) in major_leagues.items():
            defaults = self.FAMILY_DEFAULTS.get(family, self.GLOBAL_DEFAULTS)
            self.league_profiles[league_id] = LeagueProfile(
                league_id=league_id,
                league_name=league_name,
                scoring_environment=defaults["scoring_environment"],
                home_advantage_factor=defaults["home_advantage_factor"],
                draw_tendency=defaults["draw_tendency"],
                matches_analyzed=0,  # Will be updated from historical data
                confidence=0.5,  # Default confidence until updated
                competition_family=family
            )
    
    def get_league_profile(self, league_id: str) -> LeagueProfile:
        """Get league profile with hierarchical fallback.
        
        Fallback order:
        1. Specific league profile (if exists)
        2. Competition family defaults
        3. Global defaults
        
        Args:
            league_id: League identifier
            
        Returns:
            LeagueProfile (either specific or default)
        """
        # Try specific league
        if league_id in self.league_profiles:
            profile = self.league_profiles[league_id]
            
            # Apply Bayesian shrinkage if sample size small
            if profile.matches_analyzed < self.MIN_MATCHES_FOR_RELIABILITY:
                return self._apply_shrinkage(profile)
            
            return profile
        
        # Fallback to global defaults
        return LeagueProfile(
            league_id=league_id,
            league_name="Unknown League",
            scoring_environment=self.GLOBAL_DEFAULTS["scoring_environment"],
            home_advantage_factor=self.GLOBAL_DEFAULTS["home_advantage_factor"],
            draw_tendency=self.GLOBAL_DEFAULTS["draw_tendency"],
            matches_analyzed=0,
            confidence=0.3,  # Low confidence for unknown league
            competition_family=None
        )
    
    def update_league_profile(
        self,
        league_id: str,
        league_name: str,
        scoring_environment: float,
        home_advantage_factor: float,
        draw_tendency: float,
        matches_analyzed: int,
        competition_family: Optional[str] = None
    ) -> None:
        """Update league profile with historical data.
        
        Args:
            league_id: League identifier
            league_name: League name
            scoring_environment: Calculated avg goals per game
            home_advantage_factor: Calculated home advantage
            draw_tendency: Calculated draw probability
            matches_analyzed: Number of matches in sample
            competition_family: Competition family for fallback
        """
        # Calculate confidence based on sample size
        confidence = self._calculate_confidence(matches_analyzed)
        
        self.league_profiles[league_id] = LeagueProfile(
            league_id=league_id,
            league_name=league_name,
            scoring_environment=scoring_environment,
            home_advantage_factor=home_advantage_factor,
            draw_tendency=draw_tendency,
            matches_analyzed=matches_analyzed,
            confidence=confidence,
            competition_family=competition_family
        )
    
    def _apply_shrinkage(self, profile: LeagueProfile) -> LeagueProfile:
        """Apply Bayesian shrinkage to blend league-specific with defaults.
        
        For small samples, blend league-specific estimates with global/family defaults
        using Wilson score interval approach.
        
        Args:
            profile: League profile with small sample
            
        Returns:
            Shrunk profile blended with defaults
        """
        n = profile.matches_analyzed
        
        # Calculate shrinkage weight (0 = all default, 1 = all league-specific)
        # Uses sigmoid: weight = n / (n + k) where k ≈ MIN_MATCHES
        k = self.MIN_MATCHES_FOR_RELIABILITY
        weight = n / (n + k)
        
        # Get defaults (family or global)
        if profile.competition_family and profile.competition_family in self.FAMILY_DEFAULTS:
            defaults = self.FAMILY_DEFAULTS[profile.competition_family]
        else:
            defaults = self.GLOBAL_DEFAULTS
        
        # Blend parameters
        shrunk_scoring = (
            weight * profile.scoring_environment +
            (1 - weight) * defaults["scoring_environment"]
        )
        
        shrunk_home_adv = (
            weight * profile.home_advantage_factor +
            (1 - weight) * defaults["home_advantage_factor"]
        )
        
        shrunk_draw = (
            weight * profile.draw_tendency +
            (1 - weight) * defaults["draw_tendency"]
        )
        
        # Return shrunk profile
        return LeagueProfile(
            league_id=profile.league_id,
            league_name=profile.league_name,
            scoring_environment=shrunk_scoring,
            home_advantage_factor=shrunk_home_adv,
            draw_tendency=shrunk_draw,
            matches_analyzed=profile.matches_analyzed,
            confidence=profile.confidence,
            competition_family=profile.competition_family
        )
    
    def _calculate_confidence(self, matches_analyzed: int) -> float:
        """Calculate confidence in league parameters based on sample size.
        
        Uses sigmoid function to map sample size to confidence [0, 1].
        
        Args:
            matches_analyzed: Number of matches in sample
            
        Returns:
            Confidence score [0, 1]
        """
        # Sigmoid: confidence = 1 / (1 + exp(-k * (n - n0)))
        n0 = self.MIN_MATCHES_FOR_RELIABILITY  # Inflection point
        k = 0.02  # Steepness (gentler curve for matches)
        
        confidence = 1.0 / (1.0 + math.exp(-k * (matches_analyzed - n0)))
        
        return confidence
    
    def get_all_league_ids(self) -> list[str]:
        """Get list of all known league IDs.
        
        Returns:
            List of league IDs
        """
        return list(self.league_profiles.keys())
    
    def get_leagues_by_family(self, family: str) -> list[LeagueProfile]:
        """Get all leagues in a competition family.
        
        Args:
            family: Competition family identifier
            
        Returns:
            List of LeagueProfile objects in that family
        """
        return [
            profile for profile in self.league_profiles.values()
            if profile.competition_family == family
        ]
