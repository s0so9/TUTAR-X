"""Tests for canonical feature snapshot."""

import pytest
from datetime import datetime
from app.prediction.feature_snapshot import (
    MatchFeatureSnapshot,
    TeamStrengthMetrics,
    FormMetrics,
    PlayerAvailability,
    LeagueContext,
    TacticalContext,
    SourceProvenance,
    MarketInformation,
    LineupStatus,
    extract_feature_snapshot,
)
from app.prediction.data_quality import DataQualityReport, DataQualityCheck


class TestMatchFeatureSnapshot:
    """Test MatchFeatureSnapshot dataclass."""
    
    def test_minimal_snapshot_creation(self):
        """Test creating snapshot with minimal required fields."""
        snapshot = MatchFeatureSnapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
        )
        
        assert snapshot.match_id == "match_123"
        assert snapshot.home_team_id == "team_home"
        assert snapshot.away_team_id == "team_away"
        assert snapshot.home_strength is None
        assert snapshot.away_strength is None
        assert snapshot.data_quality_report is None
        assert snapshot.snapshot_version == "1.0.0"
    
    def test_full_snapshot_creation(self):
        """Test creating snapshot with all fields populated."""
        home_strength = TeamStrengthMetrics(
            goals_scored_per_match=1.8,
            xg_per_match=1.6,
            goals_conceded_per_match=1.2,
            xg_against_per_match=1.1,
            points_per_match=1.7,
            elo_rating=1650.0,
        )
        
        away_strength = TeamStrengthMetrics(
            goals_scored_per_match=1.5,
            xg_per_match=1.4,
            goals_conceded_per_match=1.3,
            xg_against_per_match=1.2,
            points_per_match=1.5,
            elo_rating=1580.0,
        )
        
        home_form = FormMetrics(
            wins=3,
            draws=1,
            losses=1,
            points=10,
            goals_for=8,
            goals_against=5,
            goal_difference=3,
            points_per_match=2.0,
            win_rate=0.6,
            clean_sheet_rate=0.4,
            matches_analyzed=5,
        )
        
        league_context = LeagueContext(
            competition_id="comp_1",
            competition_name="Premier League",
            season_id="2024",
            home_advantage_factor=1.3,
            league_average_goals=2.7,
        )
        
        snapshot = MatchFeatureSnapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
            home_team_name="Home FC",
            away_team_name="Away United",
            scheduled_at=datetime(2024, 1, 15, 15, 0),
            home_strength=home_strength,
            away_strength=away_strength,
            home_form=home_form,
            league_context=league_context,
        )
        
        assert snapshot.home_strength.goals_scored_per_match == 1.8
        assert snapshot.away_strength.elo_rating == 1580.0
        assert snapshot.home_form.wins == 3
        assert snapshot.league_context.home_advantage_factor == 1.3
    
    def test_to_dict_serialization(self):
        """Test converting snapshot to dictionary."""
        snapshot = MatchFeatureSnapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
            home_team_name="Home FC",
        )
        
        result = snapshot.to_dict()
        
        assert isinstance(result, dict)
        assert result["match_id"] == "match_123"
        assert result["home_team_name"] == "Home FC"
        assert "snapshot_version" in result
    
    def test_get_feature_dict_with_all_features(self):
        """Test extracting flat feature dictionary."""
        home_strength = TeamStrengthMetrics(
            goals_scored_per_match=1.8,
            xg_per_match=1.6,
            goals_conceded_per_match=1.2,
            elo_rating=1650.0,
        )
        
        home_form = FormMetrics(
            wins=3,
            points_per_match=2.0,
            win_rate=0.6,
            matches_analyzed=5,
        )
        
        league_context = LeagueContext(
            home_advantage_factor=1.3,
            league_average_goals=2.7,
        )
        
        data_quality_report = DataQualityReport(
            overall_score=0.85,
            checks=[],
            passed=5,
            failed=0,
        )
        
        snapshot = MatchFeatureSnapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
            home_strength=home_strength,
            home_form=home_form,
            league_context=league_context,
            data_quality_report=data_quality_report,
        )
        
        features = snapshot.get_feature_dict()
        
        assert features["home_goals_per_match"] == 1.8
        assert features["home_xg_per_match"] == 1.6
        assert features["home_elo"] == 1650.0
        assert features["home_form_wins"] == 3.0
        assert features["home_form_points_per_match"] == 2.0
        assert features["home_advantage"] == 1.3
        assert features["data_quality_score"] == 0.85
    
    def test_get_feature_dict_with_missing_data(self):
        """Test feature dict preserves None for missing data."""
        snapshot = MatchFeatureSnapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
        )
        
        features = snapshot.get_feature_dict()
        
        # Should return empty or minimal dict when no features available
        assert isinstance(features, dict)
        # None values should be preserved for unavailable features
        assert features.get("home_goals_per_match") is None
        assert features.get("away_xg_per_match") is None
    
    def test_validate_no_fabricated_data(self):
        """Test validation detects suspicious values."""
        home_strength = TeamStrengthMetrics(
            goals_scored_per_match=-1.0,  # Invalid negative
            xg_per_match=1.5,
        )
        
        snapshot = MatchFeatureSnapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
            home_strength=home_strength,
        )
        
        warnings = snapshot.validate_no_fabricated_data()
        
        assert len(warnings) > 0
        assert any("negative" in w.lower() for w in warnings)
    
    def test_none_preserved_for_unavailable_data(self):
        """Test that missing data remains None, not converted to 0 or defaults."""
        snapshot = MatchFeatureSnapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
        )
        
        # All optional fields should be None
        assert snapshot.home_strength is None
        assert snapshot.away_strength is None
        assert snapshot.home_form is None
        assert snapshot.away_form is None
        assert snapshot.league_context is None
        assert snapshot.market_info is None
        
        # Should not have any default values except required fields
        features = snapshot.get_feature_dict()
        assert features.get("home_goals_per_match") is None
        assert features.get("home_elo") is None


class TestTeamStrengthMetrics:
    """Test TeamStrengthMetrics dataclass."""
    
    def test_all_none_by_default(self):
        """Test all metrics are None by default."""
        metrics = TeamStrengthMetrics()
        
        assert metrics.goals_scored_per_match is None
        assert metrics.xg_per_match is None
        assert metrics.goals_conceded_per_match is None
        assert metrics.elo_rating is None
    
    def test_partial_metrics(self):
        """Test can set some metrics while leaving others None."""
        metrics = TeamStrengthMetrics(
            goals_scored_per_match=1.8,
            elo_rating=1650.0,
        )
        
        assert metrics.goals_scored_per_match == 1.8
        assert metrics.elo_rating == 1650.0
        assert metrics.xg_per_match is None
        assert metrics.goals_conceded_per_match is None


class TestFormMetrics:
    """Test FormMetrics dataclass."""
    
    def test_all_none_by_default(self):
        """Test all metrics are None by default."""
        form = FormMetrics()
        
        assert form.wins is None
        assert form.draws is None
        assert form.points_per_match is None
        assert form.matches_analyzed is None


class TestPlayerAvailability:
    """Test PlayerAvailability dataclass."""
    
    def test_default_unavailable(self):
        """Test lineup status defaults to unavailable."""
        availability = PlayerAvailability()
        
        assert availability.lineup_status == LineupStatus.UNAVAILABLE
        assert availability.injuries == []
        assert availability.suspensions == []
        assert availability.has_key_player_absences is None
    
    def test_with_injuries(self):
        """Test recording injuries."""
        availability = PlayerAvailability(
            lineup_status=LineupStatus.PARTIAL,
            injuries=[
                {"player": "Player A", "type": "hamstring"},
                {"player": "Player B", "type": "ankle"},
            ],
            has_key_player_absences=True,
        )
        
        assert availability.lineup_status == LineupStatus.PARTIAL
        assert len(availability.injuries) == 2
        assert availability.has_key_player_absences is True


class TestExtractFeatureSnapshot:
    """Test extract_feature_snapshot factory function."""
    
    def test_minimal_extraction(self):
        """Test extracting snapshot with minimal data."""
        snapshot = extract_feature_snapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
        )
        
        assert snapshot.match_id == "match_123"
        assert snapshot.home_team_id == "team_home"
        assert snapshot.away_team_id == "team_away"
    
    def test_extraction_with_feature_set(self):
        """Test extracting snapshot from FeatureSet."""
        # Mock feature set
        class MockFeatureSet:
            home_form = {
                'wins': 3,
                'draws': 1,
                'losses': 1,
                'points': 10,
                'goals_for': 8,
                'goals_against': 5,
                'points_per_match': 2.0,
                'win_rate': 0.6,
                'sample_size': 5,
            }
            away_form = {
                'wins': 2,
                'draws': 2,
                'losses': 1,
                'points': 8,
                'sample_size': 5,
            }
            attack_defence_home = {
                'goals_per_match': 1.6,
                'xg_per_match': 1.5,
                'goals_conceded_per_match': 1.0,
            }
            attack_defence_away = {
                'goals_per_match': 1.4,
                'xg_per_match': 1.3,
                'goals_conceded_per_match': 1.1,
            }
        
        feature_set = MockFeatureSet()
        
        snapshot = extract_feature_snapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
            feature_set=feature_set,
        )
        
        assert snapshot.home_form is not None
        assert snapshot.home_form.wins == 3
        assert snapshot.home_form.matches_analyzed == 5
        
        assert snapshot.away_form is not None
        assert snapshot.away_form.wins == 2
        
        assert snapshot.home_strength is not None
        assert snapshot.home_strength.goals_scored_per_match == 1.6
        
        assert snapshot.away_strength is not None
        assert snapshot.away_strength.xg_per_match == 1.3
    
    def test_extraction_with_market_info(self):
        """Test extracting snapshot with market odds."""
        market_info = MarketInformation(
            bookmaker_odds={"home_win": 2.1, "draw": 3.4, "away_win": 3.2},
            bookmaker_name="Bet365",
            implied_home_win=0.45,
            implied_draw=0.28,
            implied_away_win=0.27,
        )
        
        snapshot = extract_feature_snapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
            market_info=market_info,
        )
        
        assert snapshot.market_info is not None
        assert snapshot.market_info.bookmaker_name == "Bet365"
        assert snapshot.market_info.bookmaker_odds["home_win"] == 2.1
