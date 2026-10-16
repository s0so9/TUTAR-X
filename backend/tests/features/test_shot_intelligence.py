"""Tests for shot intelligence calculator."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock

from app.features.shot_intelligence import (
    ShotIntelligenceMetrics,
    ShotIntelligenceCalculator,
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
    return ShotIntelligenceCalculator(
        session=mock_session,
        recent_window=5,
        min_matches=3,
        recency_decay=0.95
    )


def create_match_with_stats(
    match_id: str,
    home_team_id: str,
    away_team_id: str,
    scheduled_at: datetime,
    home_shots: int = None,
    away_shots: int = None,
    home_sot: int = None,
    away_sot: int = None,
    home_xg: float = None,
    away_xg: float = None
) -> MatchWithStatistics:
    """Helper to create MatchWithStatistics with shot data."""
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
        shots_total=home_shots,
        shots_on_target=home_sot,
        xg=home_xg
    )
    
    away_stats = TeamMatchStatistic(
        id=f"{match_id}_a",
        match_id=match_id,
        team_id=away_team_id,
        goals_scored=1,
        goals_conceded=1,
        shots_total=away_shots,
        shots_on_target=away_sot,
        xg=away_xg
    )
    
    return MatchWithStatistics(
        match=match,
        home_statistics=home_stats,
        away_statistics=away_stats
    )


class TestShotIntelligenceMetrics:
    """Test ShotIntelligenceMetrics dataclass."""
    
    def test_shot_metrics_structure(self):
        """Test that all coordinate-based metrics are None."""
        metrics = ShotIntelligenceMetrics(team_id="team_a")
        
        # UNAVAILABLE coordinate-based metrics should be None
        assert metrics.shots_inside_box_per_match is None
        assert metrics.box_shot_percentage is None
        assert metrics.big_chances_per_match is None
        assert metrics.non_penalty_xg_per_match is None


class TestShotIntelligenceCalculator:
    """Test ShotIntelligenceCalculator."""
    
    def test_calculate_with_shot_data(self, calculator):
        """Test shot metrics calculation with complete shot data."""
        matches = [
            create_match_with_stats(
                f"m{i}",
                "team_a",
                f"opp_{i}",
                datetime(2024, 1, i+1),
                home_shots=10 + i,
                away_shots=8,
                home_sot=4 + i,
                away_sot=3,
                home_xg=1.2 + i * 0.1,
                away_xg=0.8
            )
            for i in range(5)
        ]
        
        metrics = calculator.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=datetime(2024, 2, 1)
        )
        
        assert metrics.team_id == "team_a"
        assert metrics.shots_total_per_match is not None
        assert metrics.shots_on_target_per_match is not None
        assert metrics.xg_for_per_match is not None
        assert metrics.xg_per_shot is not None
        assert metrics.shot_on_target_rate is not None
        assert metrics.sample_size == 5
        assert metrics.matches_with_shot_data == 5
    
    def test_missing_shot_data(self, calculator):
        """Test shot metrics when shot data unavailable."""
        matches = [
            create_match_with_stats(
                f"m{i}",
                "team_a",
                f"opp_{i}",
                datetime(2024, 1, i+1),
                home_shots=None,  # No shot data
                away_shots=None,
                home_sot=None,
                away_sot=None,
                home_xg=None,
                away_xg=None
            )
            for i in range(5)
        ]
        
        metrics = calculator.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=datetime(2024, 2, 1)
        )
        
        # All shot metrics should be None
        assert metrics.shots_total_per_match is None
        assert metrics.shots_on_target_per_match is None
        assert metrics.xg_for_per_match is None
        assert metrics.xg_per_shot is None
        assert metrics.matches_with_shot_data == 0
    
    def test_calculate_with_missing_xg(self, calculator):
        """Test shot metrics when xG unavailable (xg_per_shot should be None)."""
        matches = [
            create_match_with_stats(
                f"m{i}",
                "team_a",
                f"opp_{i}",
                datetime(2024, 1, i+1),
                home_shots=10 + i,
                away_shots=8,
                home_sot=4 + i,
                away_sot=3,
                home_xg=None,  # No xG data
                away_xg=None
            )
            for i in range(5)
        ]
        
        metrics = calculator.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=datetime(2024, 2, 1)
        )
        
        # Shot metrics should be calculated
        assert metrics.shots_total_per_match is not None
        assert metrics.shots_on_target_per_match is not None
        
        # xG metrics should be None
        assert metrics.xg_for_per_match is None
        assert metrics.xg_per_shot is None
        assert metrics.matches_with_xg == 0
    
    def test_home_away_separation(self, calculator):
        """Test home/away shot separation."""
        # Create 3 home and 3 away matches
        home_matches = [
            create_match_with_stats(
                f"mh{i}",
                "team_a",  # home
                f"opp_{i}",
                datetime(2024, 1, i+1),
                home_shots=15,
                away_shots=8,
                home_sot=6,
                away_sot=3
            )
            for i in range(3)
        ]
        
        away_matches = [
            create_match_with_stats(
                f"ma{i}",
                f"opp_{i}",
                "team_a",  # away
                datetime(2024, 1, 10+i),
                home_shots=8,
                away_shots=12,
                home_sot=3,
                away_sot=5
            )
            for i in range(3)
        ]
        
        all_matches = home_matches + away_matches
        
        metrics = calculator.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=all_matches,
            before_datetime=datetime(2024, 2, 1)
        )
        
        # Should have home/away splits
        assert metrics.shots_home_per_match is not None
        assert metrics.shots_away_per_match is not None
        assert metrics.shots_on_target_home_per_match is not None
        assert metrics.shots_on_target_away_per_match is not None
        
        # Home should be ~15, away should be ~12
        assert 14 <= metrics.shots_home_per_match <= 16
        assert 11 <= metrics.shots_away_per_match <= 13
    
    def test_xg_per_shot_calculation(self, calculator):
        """Test xG per shot calculation."""
        matches = [
            create_match_with_stats(
                f"m{i}",
                "team_a",
                f"opp_{i}",
                datetime(2024, 1, i+1),
                home_shots=10,
                away_shots=8,
                home_sot=4,
                away_sot=3,
                home_xg=1.0,  # xG = 1.0, shots = 10 → xG/shot = 0.1
                away_xg=0.8
            )
            for i in range(5)
        ]
        
        metrics = calculator.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=datetime(2024, 2, 1)
        )
        
        # xG per shot should be approximately 0.1
        assert metrics.xg_per_shot is not None
        assert 0.08 <= metrics.xg_per_shot <= 0.12
    
    def test_shot_share_calculation(self, calculator):
        """Test shot dominance (shot share) calculation."""
        matches = [
            create_match_with_stats(
                f"m{i}",
                "team_a",
                f"opp_{i}",
                datetime(2024, 1, i+1),
                home_shots=15,  # Team A
                away_shots=5,   # Opponent
                home_sot=6,
                away_sot=2
            )
            for i in range(5)
        ]
        
        metrics = calculator.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=datetime(2024, 2, 1)
        )
        
        # Shot share = 15 / (15 + 5) = 0.75
        assert metrics.shot_share is not None
        assert 0.70 <= metrics.shot_share <= 0.80
    
    def test_recency_weighting(self, calculator):
        """Test that recency-weighted average differs from simple average."""
        matches = [
            create_match_with_stats(
                f"m{i}",
                "team_a",
                f"opp_{i}",
                datetime(2024, 1, i+1),
                home_shots=5 if i < 3 else 15,  # Low shots in early, high shots in recent
                away_shots=8,
                home_sot=2 if i < 3 else 6,
                away_sot=3
            )
            for i in range(5)
        ]
        
        metrics = calculator.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=datetime(2024, 2, 1)
        )
        
        # Simple average = (5+5+5+15+15)/5 = 9
        # Weighted average should be higher (recent matches weighted more)
        assert metrics.shots_total_per_match is not None
        assert metrics.shots_per_match_weighted is not None
        
        # Weighted should be higher than simple average
        assert metrics.shots_per_match_weighted > metrics.shots_total_per_match
    
    def test_temporal_filtering(self, calculator):
        """Test that calculator respects before_datetime filter."""
        matches = [
            create_match_with_stats(
                f"m{i}",
                "team_a",
                f"opp_{i}",
                datetime(2024, 1, i+1),
                home_shots=10,
                away_shots=8,
                home_sot=4,
                away_sot=3
            )
            for i in range(10)
        ]
        
        # Calculate with cutoff at day 6
        metrics = calculator.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=datetime(2024, 1, 6)
        )
        
        # Should only include first 5 matches (days 1-5, before day 6)
        assert metrics.sample_size == 5
    
    def test_coordinate_metrics_always_none(self, calculator):
        """Test that coordinate-based metrics are always None (UNAVAILABLE)."""
        matches = [
            create_match_with_stats(
                f"m{i}",
                "team_a",
                f"opp_{i}",
                datetime(2024, 1, i+1),
                home_shots=10,
                away_shots=8,
                home_sot=4,
                away_sot=3,
                home_xg=1.2,
                away_xg=0.8
            )
            for i in range(5)
        ]
        
        metrics = calculator.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=datetime(2024, 2, 1)
        )
        
        # Coordinate-based metrics should always be None
        assert metrics.shots_inside_box_per_match is None
        assert metrics.box_shot_percentage is None
        assert metrics.big_chances_per_match is None
        assert metrics.non_penalty_xg_per_match is None
    
    def test_get_raw_shot_counts(self, calculator):
        """Test get_raw_shot_counts helper method."""
        matches = [
            create_match_with_stats(
                f"m{i}",
                "team_a",
                f"opp_{i}",
                datetime(2024, 1, i+1),
                home_shots=10 + i,
                away_shots=8,
                home_sot=4 + i,
                away_sot=3
            )
            for i in range(5)
        ]
        
        shots_list, sot_list = calculator.get_raw_shot_counts(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=datetime(2024, 2, 1)
        )
        
        # Should return lists of raw counts
        assert len(shots_list) == 5
        assert len(sot_list) == 5
        
        # Shots should be [10, 11, 12, 13, 14]
        assert shots_list == [10.0, 11.0, 12.0, 13.0, 14.0]
        
        # SOT should be [4, 5, 6, 7, 8]
        assert sot_list == [4.0, 5.0, 6.0, 7.0, 8.0]
