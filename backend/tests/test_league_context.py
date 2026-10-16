"""Tests for league_context module."""

import pytest
from app.prediction.league_context import (
    LeagueContextManager,
    LeagueProfile,
)


class TestLeagueContextManager:
    """Tests for LeagueContextManager."""
    
    def test_manager_initialization(self):
        """Test manager initialization with default leagues."""
        manager = LeagueContextManager()
        
        # Should have major leagues pre-seeded
        assert "premier_league" in manager.league_profiles
        assert "la_liga" in manager.league_profiles
        assert "bundesliga" in manager.league_profiles
    
    def test_get_league_profile_for_known_league(self):
        """Test getting profile for known league."""
        manager = LeagueContextManager()
        
        profile = manager.get_league_profile("premier_league")
        
        assert isinstance(profile, LeagueProfile)
        assert profile.league_id == "premier_league"
        assert profile.scoring_environment > 0
        assert profile.home_advantage_factor > 1.0
    
    def test_get_league_profile_for_unknown_league(self):
        """Test getting profile for unknown league (fallback to global defaults)."""
        manager = LeagueContextManager()
        
        profile = manager.get_league_profile("unknown_league")
        
        assert isinstance(profile, LeagueProfile)
        assert profile.league_id == "unknown_league"
        # Should use global defaults
        assert profile.scoring_environment == manager.GLOBAL_DEFAULTS["scoring_environment"]
        assert profile.confidence < 0.5  # Low confidence for unknown
    
    def test_update_league_profile(self):
        """Test updating league profile with historical data."""
        manager = LeagueContextManager()
        
        manager.update_league_profile(
            league_id="test_league",
            league_name="Test League",
            scoring_environment=3.0,
            home_advantage_factor=1.35,
            draw_tendency=0.28,
            matches_analyzed=150,
            competition_family="lower_european"
        )
        
        profile = manager.get_league_profile("test_league")
        
        assert profile.scoring_environment == 3.0
        assert profile.home_advantage_factor == 1.35
        assert profile.draw_tendency == 0.28
        assert profile.matches_analyzed == 150
    
    def test_bayesian_shrinkage_with_small_sample(self):
        """Test Bayesian shrinkage for leagues with small sample size."""
        manager = LeagueContextManager()
        
        # Update with small sample (20 matches)
        manager.update_league_profile(
            league_id="small_league",
            league_name="Small League",
            scoring_environment=4.0,  # Very high (unusual)
            home_advantage_factor=1.8,  # Very high (unusual)
            draw_tendency=0.10,  # Very low (unusual)
            matches_analyzed=20,  # Small sample
            competition_family="lower_european"
        )
        
        profile = manager.get_league_profile("small_league")
        
        # Should be shrunk toward defaults (not use raw values)
        assert profile.scoring_environment < 4.0
        assert profile.home_advantage_factor < 1.8
        assert profile.draw_tendency > 0.10
    
    def test_no_shrinkage_with_large_sample(self):
        """Test that no shrinkage applied with large sample size."""
        manager = LeagueContextManager()
        
        # Update with large sample (200 matches)
        manager.update_league_profile(
            league_id="large_league",
            league_name="Large League",
            scoring_environment=3.2,
            home_advantage_factor=1.25,
            draw_tendency=0.29,
            matches_analyzed=200,  # Large sample
            competition_family="top_5_european"
        )
        
        profile = manager.get_league_profile("large_league")
        
        # Should use league-specific values (minimal shrinkage)
        assert profile.scoring_environment == pytest.approx(3.2, abs=0.05)
        assert profile.home_advantage_factor == pytest.approx(1.25, abs=0.02)
    
    def test_confidence_calculation(self):
        """Test confidence score increases with sample size."""
        manager = LeagueContextManager()
        
        manager.update_league_profile(
            league_id="league_small",
            league_name="Small",
            scoring_environment=2.7,
            home_advantage_factor=1.3,
            draw_tendency=0.27,
            matches_analyzed=30
        )
        
        manager.update_league_profile(
            league_id="league_large",
            league_name="Large",
            scoring_environment=2.7,
            home_advantage_factor=1.3,
            draw_tendency=0.27,
            matches_analyzed=150
        )
        
        profile_small = manager.get_league_profile("league_small")
        profile_large = manager.get_league_profile("league_large")
        
        assert profile_large.confidence > profile_small.confidence
    
    def test_hierarchical_fallback_to_family(self):
        """Test fallback to competition family defaults."""
        manager = LeagueContextManager()
        
        # Add league with family but no historical data
        manager.update_league_profile(
            league_id="new_league",
            league_name="New League",
            scoring_environment=2.8,
            home_advantage_factor=1.32,
            draw_tendency=0.26,
            matches_analyzed=40,  # Will trigger shrinkage
            competition_family="top_5_european"
        )
        
        profile = manager.get_league_profile("new_league")
        
        # Should blend with family defaults (not global)
        family_defaults = manager.FAMILY_DEFAULTS["top_5_european"]
        # Value should be between league-specific and family default
        assert (
            min(2.8, family_defaults["scoring_environment"]) <=
            profile.scoring_environment <=
            max(2.8, family_defaults["scoring_environment"])
        )
    
    def test_get_all_league_ids(self):
        """Test getting all known league IDs."""
        manager = LeagueContextManager()
        
        league_ids = manager.get_all_league_ids()
        
        assert isinstance(league_ids, list)
        assert len(league_ids) > 0
        assert "premier_league" in league_ids
    
    def test_get_leagues_by_family(self):
        """Test getting leagues by competition family."""
        manager = LeagueContextManager()
        
        top_5_leagues = manager.get_leagues_by_family("top_5_european")
        
        assert len(top_5_leagues) == 5  # PL, La Liga, Bundesliga, Serie A, Ligue 1
        assert all(profile.competition_family == "top_5_european" 
                  for profile in top_5_leagues)
    
    def test_confidence_sigmoid_inflection_point(self):
        """Test that confidence sigmoid has correct inflection point."""
        manager = LeagueContextManager()
        
        # At MIN_MATCHES_FOR_RELIABILITY (100), confidence should be ~0.5
        manager.update_league_profile(
            league_id="test",
            league_name="Test",
            scoring_environment=2.7,
            home_advantage_factor=1.3,
            draw_tendency=0.27,
            matches_analyzed=100
        )
        
        profile = manager.get_league_profile("test")
        
        # Confidence at inflection point should be around 0.5
        assert 0.45 <= profile.confidence <= 0.55
    
    def test_global_defaults_are_reasonable(self):
        """Test that global defaults are reasonable for football."""
        manager = LeagueContextManager()
        
        defaults = manager.GLOBAL_DEFAULTS
        
        # Check ranges are plausible
        assert 2.0 <= defaults["scoring_environment"] <= 3.5
        assert 1.1 <= defaults["home_advantage_factor"] <= 1.5
        assert 0.20 <= defaults["draw_tendency"] <= 0.35
    
    def test_family_defaults_cover_major_regions(self):
        """Test that family defaults cover major football regions."""
        manager = LeagueContextManager()
        
        families = manager.FAMILY_DEFAULTS
        
        assert "top_5_european" in families
        assert "lower_european" in families
        assert "south_american" in families
        assert "asian" in families
