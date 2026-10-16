"""Tests for feature engineering module.

This test suite verifies that:
1. Feature calculations are deterministic
2. No data leakage occurs (future data not used)
3. Insufficient data is handled gracefully
4. All calculations are mathematically correct
"""

import pytest
from datetime import datetime, timedelta, date

from app.features import (
    TeamStrengthCalculator,
    FormCalculator,
    MatchFeatureExtractor,
    TeamHistoricalData,
    MatchContext,
)
from app.domain.match import Match
from app.domain.enums import MatchStatus, MatchOutcome
from app.domain.statistics import Standing
from app.providers import DevelopmentProvider


@pytest.fixture
def dev_provider():
    """Provide DevelopmentProvider instance."""
    return DevelopmentProvider()


@pytest.fixture
def sample_matches():
    """Create sample historical matches for testing."""
    today = date.today()
    base_time = datetime.combine(today, datetime.min.time())
    
    matches = [
        # Team A home wins
        Match(
            id="match_1",
            competition_id="comp_1",
            season_id="season_1",
            home_team_id="team_a",
            away_team_id="team_b",
            scheduled_at=base_time - timedelta(days=20),
            status=MatchStatus.FINISHED,
            home_score=2,
            away_score=0,
            outcome=MatchOutcome.HOME_WIN,
        ),
        # Team A away win
        Match(
            id="match_2",
            competition_id="comp_1",
            season_id="season_1",
            home_team_id="team_c",
            away_team_id="team_a",
            scheduled_at=base_time - timedelta(days=15),
            status=MatchStatus.FINISHED,
            home_score=1,
            away_score=3,
            outcome=MatchOutcome.AWAY_WIN,
        ),
        # Team A home draw
        Match(
            id="match_3",
            competition_id="comp_1",
            season_id="season_1",
            home_team_id="team_a",
            away_team_id="team_c",
            scheduled_at=base_time - timedelta(days=10),
            status=MatchStatus.FINISHED,
            home_score=1,
            away_score=1,
            outcome=MatchOutcome.DRAW,
        ),
        # Team A away loss
        Match(
            id="match_4",
            competition_id="comp_1",
            season_id="season_1",
            home_team_id="team_b",
            away_team_id="team_a",
            scheduled_at=base_time - timedelta(days=5),
            status=MatchStatus.FINISHED,
            home_score=2,
            away_score=1,
            outcome=MatchOutcome.HOME_WIN,
        ),
    ]
    return matches


class TestTeamStrengthCalculator:
    """Tests for TeamStrengthCalculator."""
    
    def test_attack_strength_calculation(self, sample_matches):
        """Verify attack strength is calculated correctly."""
        calculator = TeamStrengthCalculator(min_matches=3)
        
        team_history = TeamHistoricalData(
            team_id="team_a",
            matches=sample_matches
        )
        
        # Team A scored: 2, 3, 1, 1 = 7 goals in 4 matches
        # Attack strength = 7 / 4 = 1.75
        attack_strength = calculator._calculate_team_strength(team_history)["attack_strength"]
        assert attack_strength == 1.75
    
    def test_defense_strength_calculation(self, sample_matches):
        """Verify defense strength is calculated correctly."""
        calculator = TeamStrengthCalculator(min_matches=3)
        
        team_history = TeamHistoricalData(
            team_id="team_a",
            matches=sample_matches
        )
        
        # Team A conceded: 0, 1, 1, 2 = 4 goals in 4 matches
        # Defense strength = 4 / 4 = 1.0
        defense_strength = calculator._calculate_team_strength(team_history)["defense_strength"]
        assert defense_strength == 1.0
    
    def test_insufficient_data_returns_none(self):
        """Verify None is returned when insufficient data exists."""
        calculator = TeamStrengthCalculator(min_matches=5)
        
        # Only 2 matches (less than minimum 5)
        team_history = TeamHistoricalData(
            team_id="team_a",
            matches=[
                Match(
                    id="m1",
                    competition_id="c1",
                    season_id="s1",
                    home_team_id="team_a",
                    away_team_id="team_b",
                    scheduled_at=datetime.now() - timedelta(days=7),
                    status=MatchStatus.FINISHED,
                    home_score=2,
                    away_score=1,
                    outcome=MatchOutcome.HOME_WIN,
                ),
                Match(
                    id="m2",
                    competition_id="c1",
                    season_id="s1",
                    home_team_id="team_b",
                    away_team_id="team_a",
                    scheduled_at=datetime.now() - timedelta(days=3),
                    status=MatchStatus.FINISHED,
                    home_score=0,
                    away_score=1,
                    outcome=MatchOutcome.AWAY_WIN,
                ),
            ]
        )
        
        features = calculator._calculate_team_strength(team_history)
        assert features["attack_strength"] is None
        assert features["defense_strength"] is None
    
    def test_home_away_strength_split(self, sample_matches):
        """Verify home and away strength are calculated separately."""
        calculator = TeamStrengthCalculator(min_matches=1)
        
        team_history = TeamHistoricalData(
            team_id="team_a",
            matches=sample_matches
        )
        
        features = calculator._calculate_team_strength(team_history)
        
        # Home strength should exist (2 home matches)
        assert features["home_strength"] is not None
        
        # Away strength should exist (2 away matches)
        assert features["away_strength"] is not None
    
    def test_goal_scoring_rate(self, sample_matches):
        """Verify goal scoring rate equals attack strength."""
        calculator = TeamStrengthCalculator(min_matches=3)
        
        team_history = TeamHistoricalData(
            team_id="team_a",
            matches=sample_matches
        )
        
        features = calculator._calculate_team_strength(team_history)
        assert features["goal_scoring_rate"] == features["attack_strength"]


class TestFormCalculator:
    """Tests for FormCalculator."""
    
    def test_recent_wins_calculation(self, sample_matches):
        """Verify recent wins are calculated correctly."""
        calculator = FormCalculator(recent_matches=4, min_matches=3)
        
        team_history = TeamHistoricalData(
            team_id="team_a",
            matches=sample_matches
        )
        
        # Team A: 2 wins (home win, away win), 1 draw, 1 loss in 4 matches
        features = calculator._calculate_team_form(team_history)
        assert features["recent_wins"] == 2.0
    
    def test_recent_draws_calculation(self, sample_matches):
        """Verify recent draws are calculated correctly."""
        calculator = FormCalculator(recent_matches=4, min_matches=3)
        
        team_history = TeamHistoricalData(
            team_id="team_a",
            matches=sample_matches
        )
        
        features = calculator._calculate_team_form(team_history)
        assert features["recent_draws"] == 1.0
    
    def test_recent_losses_calculation(self, sample_matches):
        """Verify recent losses are calculated correctly."""
        calculator = FormCalculator(recent_matches=4, min_matches=3)
        
        team_history = TeamHistoricalData(
            team_id="team_a",
            matches=sample_matches
        )
        
        features = calculator._calculate_team_form(team_history)
        assert features["recent_losses"] == 1.0
    
    def test_recent_points_calculation(self, sample_matches):
        """Verify recent points are calculated correctly."""
        calculator = FormCalculator(recent_matches=4, min_matches=3)
        
        team_history = TeamHistoricalData(
            team_id="team_a",
            matches=sample_matches
        )
        
        # 2 wins (6 points) + 1 draw (1 point) = 7 points
        features = calculator._calculate_team_form(team_history)
        assert features["recent_points"] == 7.0
    
    def test_recent_goals_scored(self, sample_matches):
        """Verify recent goals scored calculation."""
        calculator = FormCalculator(recent_matches=4, min_matches=3)
        
        team_history = TeamHistoricalData(
            team_id="team_a",
            matches=sample_matches
        )
        
        # Team A scored: 2, 3, 1, 1 = 7 goals
        features = calculator._calculate_team_form(team_history)
        assert features["recent_goals_scored"] == 7.0
    
    def test_recent_goals_conceded(self, sample_matches):
        """Verify recent goals conceded calculation."""
        calculator = FormCalculator(recent_matches=4, min_matches=3)
        
        team_history = TeamHistoricalData(
            team_id="team_a",
            matches=sample_matches
        )
        
        # Team A conceded: 0, 1, 1, 2 = 4 goals
        features = calculator._calculate_team_form(team_history)
        assert features["recent_goals_conceded"] == 4.0
    
    def test_recent_averages(self, sample_matches):
        """Verify average calculations."""
        calculator = FormCalculator(recent_matches=4, min_matches=3)
        
        team_history = TeamHistoricalData(
            team_id="team_a",
            matches=sample_matches
        )
        
        features = calculator._calculate_team_form(team_history)
        
        # 7 goals scored / 4 matches = 1.75
        assert features["recent_avg_goals_scored"] == 1.75
        
        # 4 goals conceded / 4 matches = 1.0
        assert features["recent_avg_goals_conceded"] == 1.0
    
    def test_points_per_match(self, sample_matches):
        """Verify points per match calculation."""
        calculator = FormCalculator(recent_matches=4, min_matches=3)
        
        team_history = TeamHistoricalData(
            team_id="team_a",
            matches=sample_matches
        )
        
        features = calculator._calculate_team_form(team_history)
        
        # 7 points / 4 matches = 1.75
        assert features["form_points_per_match"] == 1.75
    
    def test_win_rate_calculation(self, sample_matches):
        """Verify win rate calculation."""
        calculator = FormCalculator(min_matches=3)
        
        team_history = TeamHistoricalData(
            team_id="team_a",
            matches=sample_matches
        )
        
        # 2 wins out of 4 matches = 0.5
        win_rate = calculator.calculate_win_rate(team_history)
        assert win_rate == 0.5
    
    def test_form_string_generation(self, sample_matches):
        """Verify form string (e.g., WWDL) is generated correctly."""
        calculator = FormCalculator(min_matches=3)
        
        team_history = TeamHistoricalData(
            team_id="team_a",
            matches=sample_matches
        )
        
        form = calculator.calculate_form_string(team_history, n=4)
        # Chronological: W (home), W (away), D (home), L (away)
        assert form == "WWDL"


class TestMatchFeatureExtractor:
    """Tests for MatchFeatureExtractor."""
    
    def test_feature_extraction_with_development_data(self, dev_provider):
        """Verify features can be extracted from development provider."""
        extractor = MatchFeatureExtractor(dev_provider, min_matches=1)
        
        # Get a match to extract features for
        matches = dev_provider.get_matches()
        # Use a future match to ensure historical data exists
        future_matches = [m for m in matches if m.status == MatchStatus.SCHEDULED]
        
        if future_matches:
            match = future_matches[0]
            features = extractor.extract_features(match)
            
            # Verify features dictionary exists and contains expected keys
            assert isinstance(features, dict)
            assert "match_id" in features
            assert "home_team_id" in features
            assert "away_team_id" in features
    
    def test_no_data_leakage(self, dev_provider):
        """Verify future matches are not used in feature calculation."""
        extractor = MatchFeatureExtractor(dev_provider, min_matches=1)
        
        # Get all matches sorted by date
        all_matches = dev_provider.get_matches()
        all_matches.sort(key=lambda m: m.scheduled_at)
        
        if len(all_matches) >= 2:
            # Use the earliest match
            early_match = all_matches[0]
            
            # Extract features
            context = extractor._build_match_context(early_match)
            
            # Verify no matches after target match are included
            for match in context.home_team_history.matches:
                assert match.scheduled_at < early_match.scheduled_at
                assert match.id != early_match.id
            
            for match in context.away_team_history.matches:
                assert match.scheduled_at < early_match.scheduled_at
                assert match.id != early_match.id
    
    def test_chronological_ordering(self, dev_provider):
        """Verify matches are ordered chronologically."""
        extractor = MatchFeatureExtractor(dev_provider, min_matches=1)
        
        matches = dev_provider.get_matches()
        if matches:
            match = matches[0]
            context = extractor._build_match_context(match)
            
            # Check home team matches are chronologically ordered
            home_matches = context.home_team_history.matches
            for i in range(len(home_matches) - 1):
                assert home_matches[i].scheduled_at <= home_matches[i + 1].scheduled_at
            
            # Check away team matches are chronologically ordered
            away_matches = context.away_team_history.matches
            for i in range(len(away_matches) - 1):
                assert away_matches[i].scheduled_at <= away_matches[i + 1].scheduled_at
    
    def test_deterministic_calculation(self, dev_provider):
        """Verify repeated feature extraction produces identical results."""
        extractor = MatchFeatureExtractor(dev_provider, min_matches=1)
        
        matches = dev_provider.get_matches()
        if matches:
            match = matches[0]
            
            # Extract features twice
            features1 = extractor.extract_features(match)
            features2 = extractor.extract_features(match)
            
            # Verify identical results
            assert features1.keys() == features2.keys()
            for key in features1:
                assert features1[key] == features2[key]
    
    def test_data_sufficiency_check(self, dev_provider):
        """Verify data sufficiency checking works."""
        extractor = MatchFeatureExtractor(dev_provider, min_matches=3)
        
        matches = dev_provider.get_matches()
        if matches:
            match = matches[0]
            sufficiency = extractor.check_data_sufficiency(match)
            
            # Verify structure
            assert "home_sufficient" in sufficiency
            assert "away_sufficient" in sufficiency
            assert "both_sufficient" in sufficiency
            assert "home_match_count" in sufficiency
            assert "away_match_count" in sufficiency
            assert "min_required" in sufficiency
            
            # Verify types
            assert isinstance(sufficiency["home_sufficient"], bool)
            assert isinstance(sufficiency["away_sufficient"], bool)
            assert isinstance(sufficiency["both_sufficient"], bool)
            assert isinstance(sufficiency["home_match_count"], int)
            assert isinstance(sufficiency["away_match_count"], int)
    
    def test_feature_summary_generation(self, dev_provider):
        """Verify feature summary can be generated."""
        extractor = MatchFeatureExtractor(dev_provider, min_matches=1)
        
        matches = dev_provider.get_matches()
        if matches:
            match = matches[0]
            features = extractor.extract_features(match)
            summary = extractor.get_feature_summary(features)
            
            # Verify summary structure
            assert "match_info" in summary
            assert "home_strength" in summary
            assert "away_strength" in summary
            assert "home_form" in summary
            assert "away_form" in summary
            assert "data_availability" in summary


class TestDataLeakagePrevention:
    """Specific tests for data leakage prevention."""
    
    def test_target_match_excluded(self):
        """Verify target match itself is not included in historical data."""
        today = date.today()
        base_time = datetime.combine(today, datetime.min.time())
        
        matches = [
            Match(
                id="target",
                competition_id="c1",
                season_id="s1",
                home_team_id="team_a",
                away_team_id="team_b",
                scheduled_at=base_time,
                status=MatchStatus.SCHEDULED,
            ),
            Match(
                id="past",
                competition_id="c1",
                season_id="s1",
                home_team_id="team_a",
                away_team_id="team_c",
                scheduled_at=base_time - timedelta(days=7),
                status=MatchStatus.FINISHED,
                home_score=2,
                away_score=1,
                outcome=MatchOutcome.HOME_WIN,
            ),
        ]
        
        # Mock provider that returns our test matches
        class MockProvider:
            def get_matches(self, **kwargs):
                return matches
            
            def get_standings(self, **kwargs):
                raise NotImplementedError()
        
        extractor = MatchFeatureExtractor(MockProvider(), min_matches=1)
        target_match = matches[0]
        
        context = extractor._build_match_context(target_match)
        
        # Verify target match is not in historical data
        all_historical_ids = [m.id for m in context.home_team_history.matches]
        all_historical_ids.extend([m.id for m in context.away_team_history.matches])
        
        assert "target" not in all_historical_ids
        assert "past" in all_historical_ids
    
    def test_future_matches_excluded(self):
        """Verify matches after target match are excluded."""
        today = date.today()
        base_time = datetime.combine(today, datetime.min.time())
        
        matches = [
            Match(
                id="past",
                competition_id="c1",
                season_id="s1",
                home_team_id="team_a",
                away_team_id="team_b",
                scheduled_at=base_time - timedelta(days=7),
                status=MatchStatus.FINISHED,
                home_score=1,
                away_score=0,
                outcome=MatchOutcome.HOME_WIN,
            ),
            Match(
                id="target",
                competition_id="c1",
                season_id="s1",
                home_team_id="team_a",
                away_team_id="team_c",
                scheduled_at=base_time,
                status=MatchStatus.SCHEDULED,
            ),
            Match(
                id="future",
                competition_id="c1",
                season_id="s1",
                home_team_id="team_a",
                away_team_id="team_b",
                scheduled_at=base_time + timedelta(days=7),
                status=MatchStatus.SCHEDULED,
            ),
        ]
        
        class MockProvider:
            def get_matches(self, **kwargs):
                return matches
            
            def get_standings(self, **kwargs):
                raise NotImplementedError()
        
        extractor = MatchFeatureExtractor(MockProvider(), min_matches=1)
        target_match = matches[1]
        
        context = extractor._build_match_context(target_match)
        
        # Verify only past match is in historical data
        all_historical_ids = [m.id for m in context.home_team_history.matches]
        
        assert "past" in all_historical_ids
        assert "target" not in all_historical_ids
        assert "future" not in all_historical_ids


class TestInsufficientDataHandling:
    """Tests for handling insufficient historical data."""
    
    def test_no_historical_matches_returns_none(self):
        """Verify None is returned when no historical matches exist."""
        calculator = TeamStrengthCalculator(min_matches=3)
        
        team_history = TeamHistoricalData(
            team_id="new_team",
            matches=[]
        )
        
        features = calculator._calculate_team_strength(team_history)
        
        # All features should be None
        assert features["attack_strength"] is None
        assert features["defense_strength"] is None
        assert features["home_strength"] is None
        assert features["away_strength"] is None
    
    def test_insufficient_recent_matches_returns_none(self):
        """Verify None for form when insufficient recent matches."""
        calculator = FormCalculator(recent_matches=5, min_matches=5)
        
        # Only 2 matches (less than minimum 5)
        team_history = TeamHistoricalData(
            team_id="team_a",
            matches=[
                Match(
                    id="m1",
                    competition_id="c1",
                    season_id="s1",
                    home_team_id="team_a",
                    away_team_id="team_b",
                    scheduled_at=datetime.now() - timedelta(days=7),
                    status=MatchStatus.FINISHED,
                    home_score=2,
                    away_score=1,
                    outcome=MatchOutcome.HOME_WIN,
                ),
                Match(
                    id="m2",
                    competition_id="c1",
                    season_id="s1",
                    home_team_id="team_b",
                    away_team_id="team_a",
                    scheduled_at=datetime.now() - timedelta(days=3),
                    status=MatchStatus.FINISHED,
                    home_score=0,
                    away_score=1,
                    outcome=MatchOutcome.AWAY_WIN,
                ),
            ]
        )
        
        features = calculator._calculate_team_form(team_history)
        
        # All features should be None
        assert features["recent_wins"] is None
        assert features["recent_points"] is None
        assert features["recent_avg_goals_scored"] is None
