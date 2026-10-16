"""Tests for market-specific feature eligibility and selection."""

import pytest
from unittest.mock import Mock

from app.prediction.market_features import (
    MarketType,
    MARKET_FEATURE_ELIGIBILITY,
    MarketFeatureSelector,
    FeatureAvailabilityReport
)
from app.prediction.feature_snapshot import (
    MatchFeatureSnapshot,
    TeamStrengthMetrics,
    FormMetrics,
    LeagueContext,
    PlayerAvailability,
    TacticalContext
)


class TestMarketType:
    """Test MarketType enum."""
    
    def test_market_types_defined(self):
        """Test that all required market types are defined."""
        assert MarketType.MATCH_RESULT_1X2 == "1x2"
        assert MarketType.OVER_UNDER == "over_under"
        assert MarketType.BTTS == "btts"
        assert MarketType.DOUBLE_CHANCE == "double_chance"
        assert MarketType.HANDICAP == "handicap"
        assert MarketType.TEAM_SHOTS == "team_shots"
        assert MarketType.TEAM_SHOTS_ON_TARGET == "team_shots_on_target"
        assert MarketType.TOTAL_SHOTS == "total_shots"
        assert MarketType.TOTAL_SHOTS_ON_TARGET == "total_shots_on_target"


class TestMarketFeatureEligibility:
    """Test feature eligibility mappings."""
    
    def test_1x2_features_defined(self):
        """Test that 1X2 market has feature eligibility defined."""
        features = MARKET_FEATURE_ELIGIBILITY[MarketType.MATCH_RESULT_1X2]
        assert isinstance(features, list)
        assert len(features) > 0
        assert "home_goals_scored_per_match" in features
        assert "away_goals_scored_per_match" in features
        assert "home_elo_rating" in features
    
    def test_shot_market_features_defined(self):
        """Test that shot markets have appropriate features."""
        shot_features = MARKET_FEATURE_ELIGIBILITY[MarketType.TEAM_SHOTS]
        assert isinstance(shot_features, list)
        assert len(shot_features) > 0
        assert "home_shots_per_match" in shot_features or "away_shots_per_match" in shot_features
    
    def test_all_markets_have_eligibility(self):
        """Test that all market types have eligibility mappings."""
        for market_type in MarketType:
            assert market_type in MARKET_FEATURE_ELIGIBILITY
            features = MARKET_FEATURE_ELIGIBILITY[market_type]
            assert isinstance(features, list)


class TestMarketFeatureSelector:
    """Test MarketFeatureSelector."""
    
    def test_get_eligible_features_returns_dict(self):
        """Test that get_eligible_features returns dictionary."""
        selector = MarketFeatureSelector()
        
        # Create minimal snapshot
        snapshot = MatchFeatureSnapshot(
            match_id="test_match",
            home_team_id="home",
            away_team_id="away",
            home_strength=TeamStrengthMetrics(),
            away_strength=TeamStrengthMetrics(),
            home_form=FormMetrics(),
            away_form=FormMetrics(),
            league_context=LeagueContext(),
            home_player_availability=PlayerAvailability(),
            away_player_availability=PlayerAvailability(),
            tactical_context=TacticalContext()
        )
        
        result = selector.get_eligible_features(MarketType.MATCH_RESULT_1X2, snapshot)
        assert isinstance(result, dict)
    
    def test_feature_availability_report(self):
        """Test feature availability report generation."""
        selector = MarketFeatureSelector()
        
        # Create snapshot with some features
        home_strength = TeamStrengthMetrics(
            goals_scored_per_match=2.0,
            xg_per_match=1.8,
            elo_rating=1500.0
        )
        away_strength = TeamStrengthMetrics(
            goals_scored_per_match=1.5,
            xg_per_match=1.3
            # elo_rating missing
        )
        
        snapshot = MatchFeatureSnapshot(
            match_id="test_match",
            home_team_id="home",
            away_team_id="away",
            home_strength=home_strength,
            away_strength=away_strength,
            home_form=FormMetrics(),
            away_form=FormMetrics(),
            league_context=LeagueContext(),
            home_player_availability=PlayerAvailability(),
            away_player_availability=PlayerAvailability(),
            tactical_context=TacticalContext()
        )
        
        report = selector.get_feature_availability(MarketType.MATCH_RESULT_1X2, snapshot)
        
        assert isinstance(report, FeatureAvailabilityReport)
        assert report.market_type == MarketType.MATCH_RESULT_1X2
        assert report.eligible_feature_count > 0
        assert 0.0 <= report.availability_ratio <= 1.0
        assert isinstance(report.available_features, list)
        assert isinstance(report.unavailable_features, list)
    
    def test_feature_extraction_with_none_values(self):
        """Test that None values are preserved in feature extraction."""
        selector = MarketFeatureSelector()
        
        snapshot = MatchFeatureSnapshot(
            match_id="test_match",
            home_team_id="home",
            away_team_id="away",
            home_strength=TeamStrengthMetrics(),  # All None
            away_strength=TeamStrengthMetrics(),
            home_form=FormMetrics(),
            away_form=FormMetrics(),
            league_context=LeagueContext(),
            home_player_availability=PlayerAvailability(),
            away_player_availability=PlayerAvailability(),
            tactical_context=TacticalContext()
        )
        
        features = selector.get_eligible_features(MarketType.MATCH_RESULT_1X2, snapshot)
        
        # All features should be in dict but with None values
        assert "home_goals_scored_per_match" in features
        assert features["home_goals_scored_per_match"] is None
