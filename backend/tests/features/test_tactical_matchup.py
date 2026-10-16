"""Tests for tactical matchup calculator."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock

from app.features.tactical_matchup import (
    TacticalProfile,
    TacticalMatchup,
    TacticalMatchupCalculator,
)
from app.features.advanced_team_intelligence import MatchWithStatistics
from app.domain.match import Match
from app.domain.statistics import TeamMatchStatistic
from app.domain.enums import MatchStatus, MatchOutcome


@pytest.fixture
def mock_session():
    """Create mock database session."""
    return Mock()


@pytest.fixture
def calculator(mock_session):
    """Create calculator instance."""
    return TacticalMatchupCalculator(
        session=mock_session,
        min_matches=5
    )


def create_match_with_stats(
    match_id: str,
    home_team_id: str,
    away_team_id: str,
    scheduled_at: datetime,
    home_possession: float = None,
    away_possession: float = None,
    home_shots: int = None,
    away_shots: int = None,
    home_sot: int = None,
    away_sot: int = None,
    home_tackles: int = None,
    away_tackles: int = None
) -> MatchWithStatistics:
    """Helper to create MatchWithStatistics with tactical data."""
    match = Match(
        id=match_id,
        competition_id="comp_1",
        season_id="season_2024",
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        scheduled_at=scheduled_at,
        status=MatchStatus.FINISHED,
        home_score=1,
        away_score=1,
        outcome=MatchOutcome.DRAW
    )
    
    home_stats = TeamMatchStatistic(
        id=f"{match_id}_h",
        match_id=match_id,
        team_id=home_team_id,
        goals_scored=1,
        goals_conceded=1,
        possession_percentage=home_possession,
        shots_total=home_shots,
        shots_on_target=home_sot,
        tackles=home_tackles
    )
    
    away_stats = TeamMatchStatistic(
        id=f"{match_id}_a",
        match_id=match_id,
        team_id=away_team_id,
        goals_scored=1,
        goals_conceded=1,
        possession_percentage=away_possession,
        shots_total=away_shots,
        shots_on_target=away_sot,
        tackles=away_tackles
    )
    
    return MatchWithStatistics(
        match=match,
        home_statistics=home_stats,
        away_statistics=away_stats
    )


class TestTacticalProfile:
    """Test TacticalProfile dataclass."""
    
    def test_tactical_profile_structure(self):
        """Test that all UNAVAILABLE metrics remain None."""
        profile = TacticalProfile(team_id="team_a")
        
        # UNAVAILABLE metrics should be None
        assert profile.ppda is None
        assert profile.field_tilt is None
        assert profile.progressive_passes_per_match is None
        assert profile.progressive_carries_per_match is None
        assert profile.box_entries_per_match is None
        assert profile.high_turnovers_per_match is None
        
        # AVAILABLE metrics default to None but can be calculated
        assert profile.possession_avg is None
        assert profile.shots_per_match is None


class TestTacticalMatchupCalculator:
    """Test TacticalMatchupCalculator."""
    
    def test_calculate_tactical_profile_with_full_data(self, calculator):
        """Test tactical profile calculation with complete data."""
        matches = [
            create_match_with_stats(
                f"m{i}",
                "team_a",
                f"opp_{i}",
                datetime(2024, 1, i+1),
                home_possession=55.0 + i,
                away_possession=45.0 - i,
                home_shots=12 + i,
                away_shots=8,
                home_sot=5 + i,
                away_sot=3,
                home_tackles=15,
                away_tackles=20
            )
            for i in range(6)
        ]
        
        profile = calculator.calculate_tactical_profile(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=datetime(2024, 2, 1)
        )
        
        assert profile.team_id == "team_a"
        assert profile.possession_avg is not None
        assert profile.shots_per_match is not None
        assert profile.shots_on_target_per_match is not None
        assert profile.shot_accuracy is not None
        assert profile.tackles_per_match is not None
        assert profile.sample_size == 6
    
    def test_ppda_always_none(self, calculator):
        """Test that PPDA is never calculated (UNAVAILABLE)."""
        matches = [
            create_match_with_stats(
                f"m{i}",
                "team_a",
                f"opp_{i}",
                datetime(2024, 1, i+1),
                home_possession=55.0,
                away_possession=45.0,
                home_shots=12,
                away_shots=8
            )
            for i in range(6)
        ]
        
        profile = calculator.calculate_tactical_profile(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=datetime(2024, 2, 1)
        )
        
        # PPDA should always be None (UNAVAILABLE)
        assert profile.ppda is None
    
    def test_field_tilt_always_none(self, calculator):
        """Test that Field Tilt is never calculated (UNAVAILABLE)."""
        matches = [
            create_match_with_stats(
                f"m{i}",
                "team_a",
                f"opp_{i}",
                datetime(2024, 1, i+1),
                home_possession=60.0,
                away_possession=40.0
            )
            for i in range(6)
        ]
        
        profile = calculator.calculate_tactical_profile(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=datetime(2024, 2, 1)
        )
        
        # Field Tilt should always be None (UNAVAILABLE)
        assert profile.field_tilt is None
    
    def test_advantage_bounded(self, calculator):
        """Test that all advantages are bounded to [-1, 1]."""
        home_profile = TacticalProfile(
            team_id="home",
            possession_avg=70.0,
            shots_per_match=20.0,
            shot_accuracy=0.5,
            defensive_actions_per_match=30.0,
            sample_size=10,
            data_quality_score=0.9
        )
        
        away_profile = TacticalProfile(
            team_id="away",
            possession_avg=30.0,
            shots_per_match=5.0,
            shot_accuracy=0.2,
            defensive_actions_per_match=10.0,
            sample_size=10,
            data_quality_score=0.9
        )
        
        matchup = calculator.calculate_matchup(home_profile, away_profile)
        
        # All advantages should be in [-1, 1]
        if matchup.possession_advantage is not None:
            assert -1.0 <= matchup.possession_advantage <= 1.0
        if matchup.shot_volume_advantage is not None:
            assert -1.0 <= matchup.shot_volume_advantage <= 1.0
        if matchup.shot_quality_advantage is not None:
            assert -1.0 <= matchup.shot_quality_advantage <= 1.0
        if matchup.defensive_intensity_advantage is not None:
            assert -1.0 <= matchup.defensive_intensity_advantage <= 1.0
        if matchup.overall_matchup_advantage is not None:
            assert -1.0 <= matchup.overall_matchup_advantage <= 1.0
    
    def test_none_metric_produces_none_advantage(self, calculator):
        """Test that if one team has None metric, advantage is None."""
        home_profile = TacticalProfile(
            team_id="home",
            possession_avg=None,  # Missing
            shots_per_match=15.0,
            sample_size=5,
            data_quality_score=0.5
        )
        
        away_profile = TacticalProfile(
            team_id="away",
            possession_avg=50.0,
            shots_per_match=10.0,
            sample_size=5,
            data_quality_score=0.5
        )
        
        matchup = calculator.calculate_matchup(home_profile, away_profile)
        
        # Possession advantage should be None (home missing possession data)
        assert matchup.possession_advantage is None
        
        # Shot advantage should be calculated (both have shots)
        assert matchup.shot_volume_advantage is not None
    
    def test_overall_advantage_from_available_only(self, calculator):
        """Test that overall advantage uses only non-None metrics."""
        home_profile = TacticalProfile(
            team_id="home",
            possession_avg=None,  # Missing
            shots_per_match=15.0,
            shot_accuracy=0.4,
            defensive_actions_per_match=None,  # Missing
            sample_size=5,
            data_quality_score=0.5
        )
        
        away_profile = TacticalProfile(
            team_id="away",
            possession_avg=None,  # Missing
            shots_per_match=10.0,
            shot_accuracy=0.3,
            defensive_actions_per_match=None,  # Missing
            sample_size=5,
            data_quality_score=0.5
        )
        
        matchup = calculator.calculate_matchup(home_profile, away_profile)
        
        # Overall should be calculated from shot_volume and shot_quality only
        assert matchup.overall_matchup_advantage is not None
        assert matchup.possession_advantage is None
        assert matchup.defensive_intensity_advantage is None
    
    def test_temporal_filtering(self, calculator):
        """Test that calculator respects before_datetime filter."""
        matches = [
            create_match_with_stats(
                f"m{i}",
                "team_a",
                f"opp_{i}",
                datetime(2024, 1, i+1),
                home_possession=55.0,
                away_possession=45.0
            )
            for i in range(10)
        ]
        
        # Calculate with cutoff at day 6
        profile = calculator.calculate_tactical_profile(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=datetime(2024, 1, 6)
        )
        
        # Should only include first 5 matches (days 1-5, before day 6)
        assert profile.sample_size == 5
    
    def test_available_metrics_list_populated(self, calculator):
        """Test that available_metrics list documents which metrics were used."""
        home_profile = TacticalProfile(
            team_id="home",
            possession_avg=55.0,
            shots_per_match=15.0,
            shot_accuracy=0.4,
            defensive_actions_per_match=20.0,
            sample_size=5,
            data_quality_score=0.8
        )
        
        away_profile = TacticalProfile(
            team_id="away",
            possession_avg=45.0,
            shots_per_match=10.0,
            shot_accuracy=0.3,
            defensive_actions_per_match=15.0,
            sample_size=5,
            data_quality_score=0.8
        )
        
        matchup = calculator.calculate_matchup(home_profile, away_profile)
        
        # available_metrics should list which advantages were calculated
        assert len(matchup.available_metrics) > 0
        assert "possession" in matchup.available_metrics
        assert "shot_volume" in matchup.available_metrics
        
        # unavailable_metrics should list UNAVAILABLE tactical metrics
        assert len(matchup.unavailable_metrics) > 0
        assert "ppda" in matchup.unavailable_metrics
        assert "field_tilt" in matchup.unavailable_metrics
