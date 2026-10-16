"""Tests for advanced team intelligence calculator."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock

from app.features.advanced_team_intelligence import (
    MatchWithStatistics,
    AdvancedTeamMetrics,
    AdvancedTeamIntelligenceCalculator,
)
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
    return AdvancedTeamIntelligenceCalculator(
        session=mock_session,
        recent_window=5,
        medium_window=10,
        season_window=38,
        min_matches=3
    )


def create_match(
    match_id: str,
    home_team_id: str,
    away_team_id: str,
    scheduled_at: datetime,
    status: MatchStatus = MatchStatus.FINISHED,
    home_score: int = 0,
    away_score: int = 0
) -> Match:
    """Helper to create a Match object."""
    return Match(
        id=match_id,
        competition_id="comp_1",
        season_id="season_2024",
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        scheduled_at=scheduled_at,
        status=status,
        home_score=home_score,
        away_score=away_score,
        outcome=MatchOutcome.HOME_WIN if home_score > away_score else (
            MatchOutcome.AWAY_WIN if away_score > home_score else MatchOutcome.DRAW
        )
    )


def create_team_stats(
    stats_id: str,
    match_id: str,
    team_id: str,
    xg: float = None,
    xg_against: float = None,
    shots_total: int = None,
    shots_on_target: int = None,
    possession_percentage: float = None
) -> TeamMatchStatistic:
    """Helper to create TeamMatchStatistic object."""
    return TeamMatchStatistic(
        id=stats_id,
        match_id=match_id,
        team_id=team_id,
        goals_scored=0,
        goals_conceded=0,
        xg=xg,
        xg_against=xg_against,
        shots_total=shots_total,
        shots_on_target=shots_on_target,
        possession_percentage=possession_percentage
    )


class TestMatchWithStatistics:
    """Test MatchWithStatistics wrapper."""
    
    def test_match_with_statistics_wrapper(self):
        """Test MatchWithStatistics correctly pairs Match with statistics."""
        match = create_match("m1", "team_a", "team_b", datetime(2024, 1, 1))
        home_stats = create_team_stats("s1", "m1", "team_a", xg=1.5)
        away_stats = create_team_stats("s2", "m1", "team_b", xg=0.8)
        
        mws = MatchWithStatistics(
            match=match,
            home_statistics=home_stats,
            away_statistics=away_stats
        )
        
        assert mws.match.id == "m1"
        assert mws.home_statistics.xg == 1.5
        assert mws.away_statistics.xg == 0.8
    
    def test_is_home_team(self):
        """Test is_home_team helper."""
        match = create_match("m1", "team_a", "team_b", datetime(2024, 1, 1))
        mws = MatchWithStatistics(match=match, home_statistics=None, away_statistics=None)
        
        assert mws.is_home_team("team_a") is True
        assert mws.is_home_team("team_b") is False
    
    def test_get_team_statistics(self):
        """Test get_team_statistics returns correct stats for team."""
        match = create_match("m1", "team_a", "team_b", datetime(2024, 1, 1))
        home_stats = create_team_stats("s1", "m1", "team_a", xg=1.5)
        away_stats = create_team_stats("s2", "m1", "team_b", xg=0.8)
        
        mws = MatchWithStatistics(
            match=match,
            home_statistics=home_stats,
            away_statistics=away_stats
        )
        
        assert mws.get_team_statistics("team_a").xg == 1.5
        assert mws.get_team_statistics("team_b").xg == 0.8
        assert mws.get_team_statistics("team_c") is None
    
    def test_is_finished(self):
        """Test is_finished correctly identifies finished matches."""
        match_finished = create_match("m1", "team_a", "team_b", datetime(2024, 1, 1), MatchStatus.FINISHED)
        match_scheduled = create_match("m2", "team_a", "team_b", datetime(2024, 1, 2), MatchStatus.SCHEDULED)
        
        mws_finished = MatchWithStatistics(match=match_finished, home_statistics=None, away_statistics=None)
        mws_scheduled = MatchWithStatistics(match=match_scheduled, home_statistics=None, away_statistics=None)
        
        assert mws_finished.is_finished() is True
        assert mws_scheduled.is_finished() is False


class TestAdvancedTeamMetrics:
    """Test AdvancedTeamMetrics dataclass structure."""
    
    def test_advanced_team_metrics_structure(self):
        """Test AdvancedTeamMetrics has all required Optional fields."""
        metrics = AdvancedTeamMetrics(team_id="team_a")
        
        # Check all fields exist and default to None
        assert metrics.team_id == "team_a"
        assert metrics.xg_for_per_match is None
        assert metrics.xg_against_per_match is None
        assert metrics.non_penalty_xg_per_match is None  # UNAVAILABLE
        assert metrics.shots_per_match is None
        assert metrics.shots_on_target_per_match is None
        assert metrics.shots_inside_box_per_match is None  # UNAVAILABLE
        assert metrics.xg_per_shot is None
        assert metrics.box_shot_percentage is None  # UNAVAILABLE
        assert metrics.big_chances_per_match is None  # UNAVAILABLE
        assert metrics.possession_avg is None
        assert metrics.field_tilt is None  # UNAVAILABLE
        assert metrics.progressive_passes_per_match is None  # UNAVAILABLE
        assert metrics.progressive_carries_per_match is None  # UNAVAILABLE
        assert metrics.ppda is None  # UNAVAILABLE
        assert metrics.high_turnovers_per_match is None  # UNAVAILABLE
        assert metrics.set_piece_xg_per_match is None  # UNAVAILABLE
        assert metrics.home_xg_for_per_match is None
        assert metrics.away_xg_for_per_match is None
        assert metrics.sample_size == 0
        assert metrics.data_quality_score == 0.0
        assert metrics.window_type == "recent"


class TestAdvancedTeamIntelligenceCalculator:
    """Test AdvancedTeamIntelligenceCalculator."""
    
    def test_calculate_with_available_data(self, calculator):
        """Test calculator correctly extracts available metrics from TeamMatchStatistic."""
        base_time = datetime(2024, 1, 1)
        
        # Create 5 finished matches with full statistics
        matches_with_stats = []
        for i in range(5):
            match = create_match(
                f"m{i}",
                "team_a",
                "team_b",
                base_time + timedelta(days=i*7),
                MatchStatus.FINISHED
            )
            home_stats = create_team_stats(
                f"s{i}_home",
                f"m{i}",
                "team_a",
                xg=1.5 + i*0.1,
                xg_against=0.8 + i*0.1,
                shots_total=10 + i,
                shots_on_target=5 + i,
                possession_percentage=55.0 + i
            )
            away_stats = create_team_stats(
                f"s{i}_away",
                f"m{i}",
                "team_b",
                xg=0.8 + i*0.1,
                xg_against=1.5 + i*0.1,
                shots_total=8 + i,
                shots_on_target=4 + i,
                possession_percentage=45.0 - i
            )
            matches_with_stats.append(
                MatchWithStatistics(match, home_stats, away_stats)
            )
        
        metrics = calculator.calculate_advanced_metrics(
            team_id="team_a",
            matches_with_stats=matches_with_stats,
            window_type="recent"
        )
        
        # Check available metrics are calculated
        assert metrics.xg_for_per_match is not None
        assert metrics.xg_against_per_match is not None
        assert metrics.shots_per_match is not None
        assert metrics.shots_on_target_per_match is not None
        assert metrics.xg_per_shot is not None
        assert metrics.possession_avg is not None
        
        # Check approximate values
        assert 1.4 < metrics.xg_for_per_match < 2.0
        assert 0.7 < metrics.xg_against_per_match < 1.3
        assert 10 < metrics.shots_per_match < 15
        assert 5 < metrics.shots_on_target_per_match < 10
        assert 54 < metrics.possession_avg < 58
        
        # Check provenance
        assert metrics.sample_size == 5
        assert metrics.matches_with_xg == 5
        assert metrics.matches_with_shots == 5
        assert metrics.matches_with_possession == 5
        assert metrics.data_quality_score > 0.5
    
    def test_calculate_with_missing_statistics(self, calculator):
        """Test calculator handles missing TeamMatchStatistic gracefully."""
        base_time = datetime(2024, 1, 1)
        
        # Create matches with missing statistics
        matches_with_stats = []
        for i in range(5):
            match = create_match(
                f"m{i}",
                "team_a",
                "team_b",
                base_time + timedelta(days=i*7),
                MatchStatus.FINISHED
            )
            # Only create stats for some matches
            home_stats = create_team_stats(
                f"s{i}_home",
                f"m{i}",
                "team_a",
                xg=1.5
            ) if i % 2 == 0 else None
            
            matches_with_stats.append(
                MatchWithStatistics(match, home_stats, None)
            )
        
        metrics = calculator.calculate_advanced_metrics(
            team_id="team_a",
            matches_with_stats=matches_with_stats,
            window_type="recent"
        )
        
        # Should still calculate with available data
        assert metrics.sample_size == 5
        # Only 3 matches have stats (i=0,2,4)
        assert metrics.matches_with_xg == 3
    
    def test_calculate_with_partial_data(self, calculator):
        """Test calculator with partial field availability."""
        base_time = datetime(2024, 1, 1)
        
        # Create matches with partial statistics (xG but no shots)
        matches_with_stats = []
        for i in range(5):
            match = create_match(
                f"m{i}",
                "team_a",
                "team_b",
                base_time + timedelta(days=i*7),
                MatchStatus.FINISHED
            )
            home_stats = create_team_stats(
                f"s{i}_home",
                f"m{i}",
                "team_a",
                xg=1.5,
                xg_against=0.8,
                shots_total=None,  # No shot data
                shots_on_target=None,
                possession_percentage=55.0
            )
            matches_with_stats.append(
                MatchWithStatistics(match, home_stats, None)
            )
        
        metrics = calculator.calculate_advanced_metrics(
            team_id="team_a",
            matches_with_stats=matches_with_stats,
            window_type="recent"
        )
        
        # xG and possession should be calculated
        assert metrics.xg_for_per_match == 1.5
        assert metrics.possession_avg == 55.0
        
        # Shots should be None (no data)
        assert metrics.shots_per_match is None
        assert metrics.shots_on_target_per_match is None
        assert metrics.xg_per_shot is None  # Can't calculate without shots
        
        # Provenance should reflect partial data
        assert metrics.matches_with_xg == 5
        assert metrics.matches_with_shots == 0
        assert metrics.matches_with_possession == 5
    
    def test_unavailable_metrics_remain_none(self, calculator):
        """Test UNAVAILABLE metrics always return None."""
        base_time = datetime(2024, 1, 1)
        
        matches_with_stats = []
        for i in range(5):
            match = create_match(
                f"m{i}",
                "team_a",
                "team_b",
                base_time + timedelta(days=i*7),
                MatchStatus.FINISHED
            )
            home_stats = create_team_stats(
                f"s{i}_home",
                f"m{i}",
                "team_a",
                xg=1.5
            )
            matches_with_stats.append(
                MatchWithStatistics(match, home_stats, None)
            )
        
        metrics = calculator.calculate_advanced_metrics(
            team_id="team_a",
            matches_with_stats=matches_with_stats,
            window_type="recent"
        )
        
        # All UNAVAILABLE metrics must be None
        assert metrics.non_penalty_xg_per_match is None
        assert metrics.shots_inside_box_per_match is None
        assert metrics.box_shot_percentage is None
        assert metrics.big_chances_per_match is None
        assert metrics.field_tilt is None
        assert metrics.progressive_passes_per_match is None
        assert metrics.progressive_carries_per_match is None
        assert metrics.ppda is None
        assert metrics.high_turnovers_per_match is None
        assert metrics.set_piece_xg_per_match is None
    
    def test_temporal_filtering_strict_less_than(self, calculator):
        """Test temporal filtering uses strict < comparison to prevent leakage."""
        base_time = datetime(2024, 1, 1)
        cutoff_time = datetime(2024, 1, 15, 15, 0, 0)  # 15th at 3pm
        
        # Create matches before and at cutoff time
        matches_with_stats = []
        
        # Match 1: Before cutoff (should be included)
        match1 = create_match("m1", "team_a", "team_b", datetime(2024, 1, 10), MatchStatus.FINISHED)
        stats1 = create_team_stats("s1", "m1", "team_a", xg=1.0)
        matches_with_stats.append(MatchWithStatistics(match1, stats1, None))
        
        # Match 2: Before cutoff (should be included)
        match2 = create_match("m2", "team_a", "team_b", datetime(2024, 1, 14), MatchStatus.FINISHED)
        stats2 = create_team_stats("s2", "m2", "team_a", xg=1.5)
        matches_with_stats.append(MatchWithStatistics(match2, stats2, None))
        
        # Match 3: Exactly at cutoff time (should be EXCLUDED - strict <)
        match3 = create_match("m3", "team_a", "team_b", cutoff_time, MatchStatus.FINISHED)
        stats3 = create_team_stats("s3", "m3", "team_a", xg=2.0)
        matches_with_stats.append(MatchWithStatistics(match3, stats3, None))
        
        # Match 4: After cutoff (should be excluded)
        match4 = create_match("m4", "team_a", "team_b", datetime(2024, 1, 20), MatchStatus.FINISHED)
        stats4 = create_team_stats("s4", "m4", "team_a", xg=2.5)
        matches_with_stats.append(MatchWithStatistics(match4, stats4, None))
        
        metrics = calculator.calculate_advanced_metrics(
            team_id="team_a",
            matches_with_stats=matches_with_stats,
            window_type="recent",
            before_datetime=cutoff_time
        )
        
        # Should only include 2 matches (m1, m2)
        # But since 2 < min_matches (3), returns minimal metrics
        assert metrics.sample_size == 2
        # Due to insufficient sample, metrics are not calculated
        assert metrics.xg_for_per_match is None
        assert metrics.data_quality_score == 0.0
    
    def test_temporal_filtering_with_sufficient_sample(self, calculator):
        """Test temporal filtering with sufficient sample after filtering."""
        base_time = datetime(2024, 1, 1)
        cutoff_time = datetime(2024, 1, 25, 15, 0, 0)  # 25th at 3pm
        
        # Create 5 matches before cutoff and 2 after
        matches_with_stats = []
        
        # 5 matches before cutoff
        for i in range(5):
            match = create_match(
                f"m_before_{i}",
                "team_a",
                "team_b",
                datetime(2024, 1, 5 + i*3),  # Days 5, 8, 11, 14, 17
                MatchStatus.FINISHED
            )
            stats = create_team_stats(f"s_before_{i}", f"m_before_{i}", "team_a", xg=1.0)
            matches_with_stats.append(MatchWithStatistics(match, stats, None))
        
        # Match exactly at cutoff (should be EXCLUDED)
        match_at = create_match("m_at", "team_a", "team_b", cutoff_time, MatchStatus.FINISHED)
        stats_at = create_team_stats("s_at", "m_at", "team_a", xg=10.0)  # High xG to detect inclusion
        matches_with_stats.append(MatchWithStatistics(match_at, stats_at, None))
        
        # 2 matches after cutoff
        for i in range(2):
            match = create_match(
                f"m_after_{i}",
                "team_a",
                "team_b",
                datetime(2024, 1, 26 + i*3),
                MatchStatus.FINISHED
            )
            stats = create_team_stats(f"s_after_{i}", f"m_after_{i}", "team_a", xg=10.0)
            matches_with_stats.append(MatchWithStatistics(match, stats, None))
        
        metrics = calculator.calculate_advanced_metrics(
            team_id="team_a",
            matches_with_stats=matches_with_stats,
            window_type="recent",
            before_datetime=cutoff_time
        )
        
        # Should include only 5 matches before cutoff
        assert metrics.sample_size == 5
        assert metrics.matches_with_xg == 5
        # Average should be 1.0 (not 10.0 if leakage occurred)
        assert metrics.xg_for_per_match == 1.0
    
    def test_home_away_split(self, calculator):
        """Test home/away venue splits calculated correctly."""
        base_time = datetime(2024, 1, 1)
        
        # Create home and away matches
        matches_with_stats = []
        
        # 3 home matches for team_a
        for i in range(3):
            match = create_match(
                f"m_home_{i}",
                "team_a",  # team_a is home
                "team_b",
                base_time + timedelta(days=i*7),
                MatchStatus.FINISHED
            )
            home_stats = create_team_stats(
                f"s_home_{i}",
                f"m_home_{i}",
                "team_a",
                xg=2.0  # Higher xG at home
            )
            matches_with_stats.append(
                MatchWithStatistics(match, home_stats, None)
            )
        
        # 3 away matches for team_a
        for i in range(3):
            match = create_match(
                f"m_away_{i}",
                "team_b",  # team_a is away
                "team_a",
                base_time + timedelta(days=(i+3)*7),
                MatchStatus.FINISHED
            )
            away_stats = create_team_stats(
                f"s_away_{i}",
                f"m_away_{i}",
                "team_a",
                xg=1.0  # Lower xG away
            )
            matches_with_stats.append(
                MatchWithStatistics(match, None, away_stats)
            )
        
        metrics = calculator.calculate_advanced_metrics(
            team_id="team_a",
            matches_with_stats=matches_with_stats,
            window_type="medium"
        )
        
        # Check venue splits
        assert metrics.home_xg_for_per_match == 2.0
        assert metrics.away_xg_for_per_match == 1.0
    
    def test_insufficient_sample_size(self, calculator):
        """Test calculator returns minimal metrics with insufficient sample."""
        base_time = datetime(2024, 1, 1)
        
        # Create only 2 matches (below min_matches=3)
        matches_with_stats = []
        for i in range(2):
            match = create_match(
                f"m{i}",
                "team_a",
                "team_b",
                base_time + timedelta(days=i*7),
                MatchStatus.FINISHED
            )
            home_stats = create_team_stats(
                f"s{i}_home",
                f"m{i}",
                "team_a",
                xg=1.5
            )
            matches_with_stats.append(
                MatchWithStatistics(match, home_stats, None)
            )
        
        metrics = calculator.calculate_advanced_metrics(
            team_id="team_a",
            matches_with_stats=matches_with_stats,
            window_type="recent"
        )
        
        # Should return metrics with zero values for insufficient data
        assert metrics.sample_size == 2
        assert metrics.xg_for_per_match is None
        assert metrics.data_quality_score == 0.0
    
    def test_data_quality_score(self, calculator):
        """Test data quality score calculation."""
        base_time = datetime(2024, 1, 1)
        
        # Full data scenario
        matches_full = []
        for i in range(5):
            match = create_match(
                f"m{i}",
                "team_a",
                "team_b",
                base_time + timedelta(days=i*7),
                MatchStatus.FINISHED
            )
            home_stats = create_team_stats(
                f"s{i}",
                f"m{i}",
                "team_a",
                xg=1.5,
                shots_total=10,
                possession_percentage=55.0
            )
            matches_full.append(
                MatchWithStatistics(match, home_stats, None)
            )
        
        metrics_full = calculator.calculate_advanced_metrics(
            team_id="team_a",
            matches_with_stats=matches_full,
            window_type="recent"
        )
        
        # Should have high data quality (all 3 key metrics available)
        assert metrics_full.data_quality_score > 0.6
        
        # Partial data scenario (only xG)
        matches_partial = []
        for i in range(5):
            match = create_match(
                f"m{i}",
                "team_a",
                "team_b",
                base_time + timedelta(days=i*7),
                MatchStatus.FINISHED
            )
            home_stats = create_team_stats(
                f"s{i}",
                f"m{i}",
                "team_a",
                xg=1.5,
                shots_total=None,  # Missing
                possession_percentage=None  # Missing
            )
            matches_partial.append(
                MatchWithStatistics(match, home_stats, None)
            )
        
        metrics_partial = calculator.calculate_advanced_metrics(
            team_id="team_a",
            matches_with_stats=matches_partial,
            window_type="recent"
        )
        
        # Should have lower data quality (only 1 of 3 metrics)
        assert metrics_partial.data_quality_score < metrics_full.data_quality_score
    
    def test_window_types(self, calculator):
        """Test different window types (recent/medium/season)."""
        base_time = datetime(2024, 1, 1)
        
        # Create 15 matches
        matches_with_stats = []
        for i in range(15):
            match = create_match(
                f"m{i}",
                "team_a",
                "team_b",
                base_time + timedelta(days=i*7),
                MatchStatus.FINISHED
            )
            home_stats = create_team_stats(
                f"s{i}",
                f"m{i}",
                "team_a",
                xg=1.0 + i*0.1  # Increasing xG over time
            )
            matches_with_stats.append(
                MatchWithStatistics(match, home_stats, None)
            )
        
        # Test recent window (last 5 matches)
        metrics_recent = calculator.calculate_advanced_metrics(
            team_id="team_a",
            matches_with_stats=matches_with_stats,
            window_type="recent"
        )
        assert metrics_recent.sample_size == 5
        assert metrics_recent.window_type == "recent"
        # Should use matches 10-14 (last 5)
        assert metrics_recent.xg_for_per_match > 2.0  # High xG (recent matches)
        
        # Test medium window (last 10 matches)
        metrics_medium = calculator.calculate_advanced_metrics(
            team_id="team_a",
            matches_with_stats=matches_with_stats,
            window_type="medium"
        )
        assert metrics_medium.sample_size == 10
        assert metrics_medium.window_type == "medium"
        # Should use matches 5-14 (last 10)
        assert metrics_medium.xg_for_per_match < metrics_recent.xg_for_per_match
        
        # Test season window (all 15 matches)
        metrics_season = calculator.calculate_advanced_metrics(
            team_id="team_a",
            matches_with_stats=matches_with_stats,
            window_type="season"
        )
        assert metrics_season.sample_size == 15
        assert metrics_season.window_type == "season"
        # Should use all matches (0-14)
        assert metrics_season.xg_for_per_match < metrics_medium.xg_for_per_match
