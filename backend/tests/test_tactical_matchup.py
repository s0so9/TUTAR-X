"""Tests for tactical_matchup module - STRUCTURED FEATURES ONLY, NO LLM."""

import pytest
from datetime import datetime
from app.prediction.tactical_matchup import (
    TacticalMatchupEngine,
    TacticalProfile,
    TacticalMatchupResult,
)


class TestTacticalProfile:
    """Tests for TacticalProfile."""
    
    def test_profile_is_complete(self):
        """Test that complete profile is identified."""
        profile = TacticalProfile(
            team_id="team1",
            pressing_intensity=0.75,
            possession_tendency=0.60,
            transition_speed=0.80,
            build_up_style=0.55,
            matches_analyzed=20
        )
        
        assert profile.is_complete
    
    def test_profile_is_incomplete(self):
        """Test that incomplete profile is identified."""
        profile = TacticalProfile(
            team_id="team1",
            pressing_intensity=0.75,
            possession_tendency=None,  # Missing
            transition_speed=0.80,
            build_up_style=0.55
        )
        
        assert not profile.is_complete
    
    def test_profile_completeness_score(self):
        """Test completeness score calculation."""
        profile = TacticalProfile(
            team_id="team1",
            pressing_intensity=0.75,
            possession_tendency=0.60,
            transition_speed=None,  # Missing
            build_up_style=None  # Missing
        )
        
        assert profile.completeness_score == 0.5  # 2/4 dimensions


class TestTacticalMatchupEngine:
    """Tests for TacticalMatchupEngine - NO LLM, STRUCTURED ONLY."""
    
    def test_engine_with_complete_profiles(self):
        """Test engine with complete tactical profiles."""
        engine = TacticalMatchupEngine()
        
        home_profile = TacticalProfile(
            team_id="home",
            pressing_intensity=0.80,  # High press
            possession_tendency=0.70,  # Possession-based
            transition_speed=0.60,
            build_up_style=0.75,
            matches_analyzed=20
        )
        
        away_profile = TacticalProfile(
            team_id="away",
            pressing_intensity=0.40,  # Low press
            possession_tendency=0.30,  # Direct
            transition_speed=0.80,  # Fast transitions
            build_up_style=0.35,
            matches_analyzed=18
        )
        
        result = engine.analyze(home_profile, away_profile)
        
        assert isinstance(result, TacticalMatchupResult)
        assert result.confidence > 0
        assert result.advantage in ["HOME", "AWAY", "NEUTRAL"]
    
    def test_engine_identifies_home_advantage(self):
        """Test that engine correctly identifies home tactical advantage."""
        engine = TacticalMatchupEngine()
        
        # Home team superior on all dimensions
        home_profile = TacticalProfile(
            team_id="home",
            pressing_intensity=0.85,
            possession_tendency=0.80,
            transition_speed=0.75,
            build_up_style=0.80,
            matches_analyzed=25
        )
        
        away_profile = TacticalProfile(
            team_id="away",
            pressing_intensity=0.40,
            possession_tendency=0.35,
            transition_speed=0.45,
            build_up_style=0.40,
            matches_analyzed=20
        )
        
        result = engine.analyze(home_profile, away_profile)
        
        assert result.advantage == "HOME"
        assert result.home_advantage_score > 0.15
    
    def test_engine_identifies_away_advantage(self):
        """Test that engine correctly identifies away tactical advantage."""
        engine = TacticalMatchupEngine()
        
        home_profile = TacticalProfile(
            team_id="home",
            pressing_intensity=0.35,
            possession_tendency=0.30,
            transition_speed=0.40,
            build_up_style=0.35,
            matches_analyzed=20
        )
        
        # Away team superior on all dimensions
        away_profile = TacticalProfile(
            team_id="away",
            pressing_intensity=0.80,
            possession_tendency=0.75,
            transition_speed=0.80,
            build_up_style=0.75,
            matches_analyzed=22
        )
        
        result = engine.analyze(home_profile, away_profile)
        
        assert result.advantage == "AWAY"
        assert result.home_advantage_score < -0.15
    
    def test_engine_identifies_neutral_matchup(self):
        """Test that engine identifies neutral matchups."""
        engine = TacticalMatchupEngine()
        
        # Balanced teams
        home_profile = TacticalProfile(
            team_id="home",
            pressing_intensity=0.60,
            possession_tendency=0.55,
            transition_speed=0.58,
            build_up_style=0.57,
            matches_analyzed=20
        )
        
        away_profile = TacticalProfile(
            team_id="away",
            pressing_intensity=0.58,
            possession_tendency=0.53,
            transition_speed=0.60,
            build_up_style=0.55,
            matches_analyzed=18
        )
        
        result = engine.analyze(home_profile, away_profile)
        
        assert result.advantage == "NEUTRAL"
        assert -0.15 <= result.home_advantage_score <= 0.15
    
    def test_engine_returns_none_with_insufficient_data(self):
        """Test that engine returns None when data insufficient."""
        engine = TacticalMatchupEngine()
        
        # Only 1 dimension available (< 50% completeness)
        home_profile = TacticalProfile(
            team_id="home",
            pressing_intensity=0.70,
            possession_tendency=None,
            transition_speed=None,
            build_up_style=None,
            matches_analyzed=10
        )
        
        away_profile = TacticalProfile(
            team_id="away",
            pressing_intensity=0.60,
            possession_tendency=None,
            transition_speed=None,
            build_up_style=None,
            matches_analyzed=12
        )
        
        result = engine.analyze(home_profile, away_profile)
        
        assert result is None
    
    def test_engine_identifies_key_matchup(self):
        """Test that engine identifies the key tactical matchup."""
        engine = TacticalMatchupEngine()
        
        # Large pressing difference, small others
        home_profile = TacticalProfile(
            team_id="home",
            pressing_intensity=0.90,  # Very high
            possession_tendency=0.55,
            transition_speed=0.58,
            build_up_style=0.56,
            matches_analyzed=20
        )
        
        away_profile = TacticalProfile(
            team_id="away",
            pressing_intensity=0.30,  # Very low
            possession_tendency=0.53,
            transition_speed=0.57,
            build_up_style=0.54,
            matches_analyzed=18
        )
        
        result = engine.analyze(home_profile, away_profile)
        
        assert result.key_matchup == "pressing"
    
    def test_engine_calculates_dimension_advantages(self):
        """Test that per-dimension advantages are calculated."""
        engine = TacticalMatchupEngine()
        
        home_profile = TacticalProfile(
            team_id="home",
            pressing_intensity=0.80,
            possession_tendency=0.70,
            transition_speed=0.60,
            build_up_style=0.65,
            matches_analyzed=20
        )
        
        away_profile = TacticalProfile(
            team_id="away",
            pressing_intensity=0.50,
            possession_tendency=0.40,
            transition_speed=0.50,
            build_up_style=0.45,
            matches_analyzed=18
        )
        
        result = engine.analyze(home_profile, away_profile)
        
        assert len(result.dimension_advantages) == 4
        assert "pressing" in result.dimension_advantages
        assert "possession" in result.dimension_advantages
        assert "transition" in result.dimension_advantages
        assert "build_up" in result.dimension_advantages
    
    def test_engine_reduces_confidence_with_few_matches(self):
        """Test that confidence is reduced when few matches analyzed."""
        engine = TacticalMatchupEngine()
        
        home_profile = TacticalProfile(
            team_id="home",
            pressing_intensity=0.70,
            possession_tendency=0.65,
            transition_speed=0.60,
            build_up_style=0.68,
            matches_analyzed=3  # Very few matches
        )
        
        away_profile = TacticalProfile(
            team_id="away",
            pressing_intensity=0.50,
            possession_tendency=0.45,
            transition_speed=0.55,
            build_up_style=0.48,
            matches_analyzed=4  # Very few matches
        )
        
        result = engine.analyze(home_profile, away_profile)
        
        # Confidence should be reduced (< 50% after two 0.7 multipliers)
        assert result.confidence < 0.5
    
    def test_engine_generates_structured_explanation(self):
        """Test that engine generates structured explanation."""
        engine = TacticalMatchupEngine()
        
        home_profile = TacticalProfile(
            team_id="home",
            pressing_intensity=0.75,
            possession_tendency=0.60,
            transition_speed=0.65,
            build_up_style=0.62,
            matches_analyzed=20
        )
        
        away_profile = TacticalProfile(
            team_id="away",
            pressing_intensity=0.45,
            possession_tendency=0.40,
            transition_speed=0.50,
            build_up_style=0.42,
            matches_analyzed=18
        )
        
        result = engine.analyze(home_profile, away_profile)
        
        assert isinstance(result.explanation, str)
        assert len(result.explanation) > 0
        # Should mention tactical dimensions
        assert any(word in result.explanation.lower() for word in 
                  ["pressing", "possession", "transition", "build"])
    
    def test_engine_never_invents_tactical_analysis(self):
        """Test that engine NEVER invents conclusions without data."""
        engine = TacticalMatchupEngine()
        
        # No tactical data available
        home_profile = TacticalProfile(
            team_id="home",
            pressing_intensity=None,
            possession_tendency=None,
            transition_speed=None,
            build_up_style=None,
            matches_analyzed=0
        )
        
        away_profile = TacticalProfile(
            team_id="away",
            pressing_intensity=None,
            possession_tendency=None,
            transition_speed=None,
            build_up_style=None,
            matches_analyzed=0
        )
        
        result = engine.analyze(home_profile, away_profile)
        
        # Should return None, NOT fabricate an analysis
        assert result is None
