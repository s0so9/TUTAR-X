"""Tests for common opponent intelligence calculator.

Tests:
- Common opponent discovery (zero, one, multiple)
- Performance comparison (points, xG, xGA, shots)
- Temporal validity (strict < enforcement, boundary conditions)
- Recency weighting application
- Context normalization (home/away matching)
- Confidence calculation (sample, recency, context factors)
- Signal strength determination (neutral, home_favored, away_favored)
- Statistical evidence threshold enforcement
- H2H vs common opponent separation
- Data quality handling (missing xG, missing shots, missing stats)
- Insufficient common opponents handling
"""

import pytest
from datetime import datetime, timedelta

from app.features.common_opponent_intelligence import (
    CommonOpponentMatch,
    CommonOpponentEvidence,
    CommonOpponentIntelligence,
    CommonOpponentCalculator,
)
from app.features.advanced_team_intelligence import MatchWithStatistics
from app.domain.match import Match
from app.domain.statistics import TeamMatchStatistic
from app.domain.enums import MatchStatus


def create_test_match(
    match_id: str,
    home_team_id: str,
    away_team_id: str,
    scheduled_at: datetime,
    home_score: int,
    away_score: int,
    home_xg: float = None,
    away_xg: float = None,
    home_shots: int = None,
    away_shots: int = None
) -> MatchWithStatistics:
    """Create test match with statistics."""
    match = Match(
        id=match_id,
        competition_id="comp_test",
        season_id="season_2023",
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        scheduled_at=scheduled_at,
        status=MatchStatus.FINISHED,
        home_score=home_score,
        away_score=away_score,
    )
    
    home_stats = TeamMatchStatistic(
        id=f"{match_id}_home",
        match_id=match_id,
        team_id=home_team_id,
        xg=home_xg,
        xg_against=away_xg,
        shots_total=home_shots,
    ) if home_xg is not None or home_shots is not None else None
    
    away_stats = TeamMatchStatistic(
        id=f"{match_id}_away",
        match_id=match_id,
        team_id=away_team_id,
        xg=away_xg,
        xg_against=home_xg,
        shots_total=away_shots,
    ) if away_xg is not None or away_shots is not None else None
    
    return MatchWithStatistics(
        match=match,
        home_statistics=home_stats,
        away_statistics=away_stats,
    )


@pytest.fixture
def calculator():
    """Create calculator with default settings."""
    return CommonOpponentCalculator(
        min_common_opponents=3,
        min_matches_per_opponent=1,
        recency_decay=0.95,
        min_confidence_threshold=0.5,
        min_differential_threshold=0.3
    )


class TestCommonOpponentDiscovery:
    """Test common opponent identification."""
    
    def test_discover_zero_common_opponents(self, calculator):
        """No shared opponents → empty result."""
        reference_date = datetime(2024, 1, 15)
        
        # Home team played against Team C and D
        home_matches = [
            create_test_match("m1", "home", "team_c", reference_date - timedelta(days=10), 2, 1, 1.5, 0.8),
            create_test_match("m2", "home", "team_d", reference_date - timedelta(days=5), 1, 1, 1.0, 1.0),
        ]
        
        # Away team played against Team E and F
        away_matches = [
            create_test_match("m3", "team_e", "away", reference_date - timedelta(days=10), 1, 2, 0.9, 1.6),
            create_test_match("m4", "away", "team_f", reference_date - timedelta(days=5), 2, 0, 1.8, 0.5),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        assert result.n_common_opponents == 0
        assert len(result.common_opponent_ids) == 0
        assert result.home_avg_points_vs_common is None
        assert result.comparison_confidence == 0.0
        assert result.data_quality_score == 0.0
    
    def test_discover_one_common_opponent(self, calculator):
        """One shared opponent → identified correctly."""
        reference_date = datetime(2024, 1, 15)
        
        # Both teams played against Team X
        home_matches = [
            create_test_match("m1", "home", "team_x", reference_date - timedelta(days=10), 2, 1, 1.5, 0.8),
            create_test_match("m2", "home", "team_c", reference_date - timedelta(days=5), 1, 1, 1.0, 1.0),
        ]
        
        away_matches = [
            create_test_match("m3", "team_x", "away", reference_date - timedelta(days=8), 1, 2, 0.9, 1.6),
            create_test_match("m4", "away", "team_d", reference_date - timedelta(days=3), 2, 0, 1.8, 0.5),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        assert result.n_common_opponents == 1
        assert "team_x" in result.common_opponent_ids
        assert len(result.opponent_evidence) == 1
    
    def test_discover_multiple_common_opponents(self, calculator):
        """Multiple shared opponents → all identified."""
        reference_date = datetime(2024, 1, 15)
        
        # Both teams played against Team X, Y, Z
        home_matches = [
            create_test_match("m1", "home", "team_x", reference_date - timedelta(days=10), 2, 1, 1.5, 0.8),
            create_test_match("m2", "home", "team_y", reference_date - timedelta(days=8), 1, 1, 1.0, 1.0),
            create_test_match("m3", "home", "team_z", reference_date - timedelta(days=5), 3, 0, 2.2, 0.6),
        ]
        
        away_matches = [
            create_test_match("m4", "team_x", "away", reference_date - timedelta(days=9), 1, 2, 0.9, 1.6),
            create_test_match("m5", "away", "team_y", reference_date - timedelta(days=7), 2, 0, 1.8, 0.5),
            create_test_match("m6", "team_z", "away", reference_date - timedelta(days=4), 1, 1, 1.2, 1.1),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        assert result.n_common_opponents == 3
        assert set(result.common_opponent_ids) == {"team_x", "team_y", "team_z"}
        assert len(result.opponent_evidence) == 3
    
    def test_exclude_direct_h2h_from_common_opponents(self, calculator):
        """Direct H2H matches not counted as common opponent matches."""
        reference_date = datetime(2024, 1, 15)
        
        # Home team played against away team (H2H) and Team X
        home_matches = [
            create_test_match("m1", "home", "away", reference_date - timedelta(days=10), 2, 1, 1.5, 0.8),  # H2H
            create_test_match("m2", "home", "team_x", reference_date - timedelta(days=5), 1, 1, 1.0, 1.0),
        ]
        
        # Away team played against home team (H2H) and Team X
        away_matches = [
            create_test_match("m3", "home", "away", reference_date - timedelta(days=10), 2, 1, 1.5, 0.8),  # H2H
            create_test_match("m4", "team_x", "away", reference_date - timedelta(days=8), 1, 2, 0.9, 1.6),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        # Should only find Team X, not the H2H match
        assert result.n_common_opponents == 1
        assert "team_x" in result.common_opponent_ids
        assert "away" not in result.common_opponent_ids
        assert "home" not in result.common_opponent_ids


class TestTemporalValidity:
    """Test temporal leakage prevention."""
    
    def test_strict_temporal_cutoff_enforced(self, calculator):
        """Only matches with scheduled_at < before_datetime included."""
        reference_date = datetime(2024, 1, 15, 15, 0, 0)
        
        # Match before cutoff - included
        match_before = create_test_match(
            "m1", "home", "team_x", 
            datetime(2024, 1, 14, 15, 0, 0), 
            2, 1, 1.5, 0.8
        )
        
        # Match at cutoff - excluded (strict <)
        match_at = create_test_match(
            "m2", "home", "team_x",
            datetime(2024, 1, 15, 15, 0, 0),
            1, 1, 1.0, 1.0
        )
        
        # Match after cutoff - excluded
        match_after = create_test_match(
            "m3", "home", "team_x",
            datetime(2024, 1, 16, 15, 0, 0),
            3, 0, 2.2, 0.6
        )
        
        home_matches = [match_before, match_at, match_after]
        away_matches = [
            create_test_match("m4", "team_x", "away", datetime(2024, 1, 13, 15, 0, 0), 1, 2, 0.9, 1.6),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        # Should only find one common opponent match for home team (the one before cutoff)
        assert result.n_common_opponents == 1
        assert len(result.opponent_evidence) == 1
        assert len(result.opponent_evidence[0].home_team_matches) == 1
        assert result.opponent_evidence[0].home_team_matches[0].match_id == "m1"
    
    def test_boundary_condition_match_at_cutoff_excluded(self, calculator):
        """Match exactly at before_datetime excluded (strict <)."""
        reference_date = datetime(2024, 1, 15, 12, 0, 0)
        
        home_matches = [
            create_test_match("m1", "home", "team_x", reference_date, 2, 1, 1.5, 0.8),  # Exactly at cutoff
        ]
        
        away_matches = [
            create_test_match("m2", "team_x", "away", reference_date - timedelta(days=5), 1, 2, 0.9, 1.6),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        # Home team match at cutoff should be excluded, resulting in no common opponents
        # because away team has matches with team_x but home team's only match was excluded
        assert result.n_common_opponents == 0
        assert len(result.opponent_evidence) == 0
    
    def test_future_match_excluded(self, calculator):
        """Future matches never included in common opponent discovery."""
        reference_date = datetime(2024, 1, 15)
        
        home_matches = [
            create_test_match("m1", "home", "team_x", reference_date + timedelta(days=10), 2, 1, 1.5, 0.8),
        ]
        
        away_matches = [
            create_test_match("m2", "team_x", "away", reference_date - timedelta(days=5), 1, 2, 0.9, 1.6),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        # Home team's future match should be excluded
        assert result.n_common_opponents == 0


class TestPerformanceComparison:
    """Test performance comparison metrics."""
    
    def test_compare_points_vs_common_opponent(self, calculator):
        """Points comparison calculated correctly."""
        reference_date = datetime(2024, 1, 15)
        
        # Home team: 2 wins vs Team X = 3 points each
        home_matches = [
            create_test_match("m1", "home", "team_x", reference_date - timedelta(days=10), 2, 1, 1.5, 0.8),
            create_test_match("m2", "home", "team_x", reference_date - timedelta(days=5), 3, 0, 2.0, 0.5),
            create_test_match("m3", "home", "team_y", reference_date - timedelta(days=3), 1, 1, 1.0, 1.0),
            create_test_match("m4", "home", "team_z", reference_date - timedelta(days=2), 2, 0, 1.8, 0.7),
        ]
        
        # Away team: 1 loss vs Team X = 0 points
        away_matches = [
            create_test_match("m5", "team_x", "away", reference_date - timedelta(days=8), 2, 0, 1.6, 0.6),
            create_test_match("m6", "away", "team_y", reference_date - timedelta(days=4), 2, 1, 1.5, 0.9),
            create_test_match("m7", "team_z", "away", reference_date - timedelta(days=1), 1, 1, 1.0, 1.0),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        # Should find 3 common opponents
        assert result.n_common_opponents == 3
        
        # Home team should have better average points
        assert result.home_avg_points_vs_common is not None
        assert result.away_avg_points_vs_common is not None
        assert result.points_differential > 0  # Home team performed better
    
    def test_compare_xg_when_available(self, calculator):
        """xG comparison calculated when data available."""
        reference_date = datetime(2024, 1, 15)
        
        # Home team: high xG vs Team X
        home_matches = [
            create_test_match("m1", "home", "team_x", reference_date - timedelta(days=10), 2, 1, 2.0, 0.8),
            create_test_match("m2", "home", "team_y", reference_date - timedelta(days=5), 3, 0, 2.5, 0.5),
            create_test_match("m3", "home", "team_z", reference_date - timedelta(days=3), 1, 1, 1.5, 1.2),
        ]
        
        # Away team: lower xG vs Team X
        away_matches = [
            create_test_match("m4", "team_x", "away", reference_date - timedelta(days=8), 2, 1, 0.9, 1.5),
            create_test_match("m5", "away", "team_y", reference_date - timedelta(days=4), 1, 0, 1.0, 0.8),
            create_test_match("m6", "team_z", "away", reference_date - timedelta(days=2), 1, 1, 0.8, 1.0),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        assert result.home_avg_xg_vs_common is not None
        assert result.away_avg_xg_vs_common is not None
        assert result.xg_differential is not None
        assert result.xg_differential > 0  # Home team had higher xG
    
    def test_xg_comparison_none_when_unavailable(self, calculator):
        """xG comparison = None when xG data missing."""
        reference_date = datetime(2024, 1, 15)
        
        # Matches without xG data
        home_matches = [
            create_test_match("m1", "home", "team_x", reference_date - timedelta(days=10), 2, 1),
            create_test_match("m2", "home", "team_y", reference_date - timedelta(days=5), 1, 1),
            create_test_match("m3", "home", "team_z", reference_date - timedelta(days=3), 3, 0),
        ]
        
        away_matches = [
            create_test_match("m4", "team_x", "away", reference_date - timedelta(days=8), 1, 2),
            create_test_match("m5", "away", "team_y", reference_date - timedelta(days=4), 2, 0),
            create_test_match("m6", "team_z", "away", reference_date - timedelta(days=2), 1, 1),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        # Points comparison should work
        assert result.home_avg_points_vs_common is not None
        assert result.away_avg_points_vs_common is not None
        
        # But xG comparison should be None
        assert result.xg_differential is None
    
    def test_compare_shots_when_available(self, calculator):
        """Shots comparison calculated when data available."""
        reference_date = datetime(2024, 1, 15)
        
        home_matches = [
            create_test_match("m1", "home", "team_x", reference_date - timedelta(days=10), 2, 1, 1.5, 0.8, 15, 8),
            create_test_match("m2", "home", "team_y", reference_date - timedelta(days=5), 1, 1, 1.0, 1.0, 12, 10),
            create_test_match("m3", "home", "team_z", reference_date - timedelta(days=3), 3, 0, 2.2, 0.6, 18, 6),
        ]
        
        away_matches = [
            create_test_match("m4", "team_x", "away", reference_date - timedelta(days=8), 1, 2, 0.9, 1.6, 10, 14),
            create_test_match("m5", "away", "team_y", reference_date - timedelta(days=4), 2, 0, 1.8, 0.5, 14, 7),
            create_test_match("m6", "team_z", "away", reference_date - timedelta(days=2), 1, 1, 1.2, 1.1, 11, 11),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        assert result.home_avg_shots_vs_common is not None
        assert result.away_avg_shots_vs_common is not None
        assert result.shots_differential is not None
    
    def test_home_away_context_normalization(self, calculator):
        """Context match rate calculated (home vs home, away vs away)."""
        reference_date = datetime(2024, 1, 15)
        
        # Home team played home vs Team X
        home_matches = [
            create_test_match("m1", "home", "team_x", reference_date - timedelta(days=10), 2, 1, 1.5, 0.8),
        ]
        
        # Away team played away vs Team X (context mismatch)
        away_matches = [
            create_test_match("m2", "team_x", "away", reference_date - timedelta(days=8), 1, 2, 0.9, 1.6),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        # Context match rate should be tracked
        assert len(result.opponent_evidence) == 1
        evidence = result.opponent_evidence[0]
        # Home played at home (1), away played away (1) = 2/2 = 1.0 context match
        assert evidence.context_match_rate == 1.0


class TestRecencyWeighting:
    """Test recency weighting application."""
    
    def test_exponential_decay_applied(self, calculator):
        """Recent matches weighted higher than old matches."""
        reference_date = datetime(2024, 1, 15)
        
        # Recent match vs Team X (5 days ago)
        home_matches = [
            create_test_match("m1", "home", "team_x", reference_date - timedelta(days=5), 2, 1, 1.5, 0.8),
        ]
        
        # Old match vs Team X (60 days ago)
        away_matches = [
            create_test_match("m2", "team_x", "away", reference_date - timedelta(days=60), 1, 2, 0.9, 1.6),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        # Recent matches should have higher weights
        assert len(result.opponent_evidence) == 1
        evidence = result.opponent_evidence[0]
        assert evidence.avg_recency_weight > 0.5  # Reasonable recent weight
    
    def test_recency_factor_in_confidence(self, calculator):
        """Recency factor contributes to confidence calculation."""
        reference_date = datetime(2024, 1, 15)
        
        # All recent matches
        home_matches = [
            create_test_match("m1", "home", "team_x", reference_date - timedelta(days=5), 2, 1, 1.5, 0.8),
            create_test_match("m2", "home", "team_y", reference_date - timedelta(days=4), 1, 1, 1.0, 1.0),
            create_test_match("m3", "home", "team_z", reference_date - timedelta(days=3), 3, 0, 2.2, 0.6),
        ]
        
        away_matches = [
            create_test_match("m4", "team_x", "away", reference_date - timedelta(days=5), 1, 2, 0.9, 1.6),
            create_test_match("m5", "away", "team_y", reference_date - timedelta(days=4), 2, 0, 1.8, 0.5),
            create_test_match("m6", "team_z", "away", reference_date - timedelta(days=3), 1, 1, 1.2, 1.1),
        ]
        
        result_recent = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        # All old matches
        home_matches_old = [
            create_test_match("m7", "home", "team_x", reference_date - timedelta(days=180), 2, 1, 1.5, 0.8),
            create_test_match("m8", "home", "team_y", reference_date - timedelta(days=170), 1, 1, 1.0, 1.0),
            create_test_match("m9", "home", "team_z", reference_date - timedelta(days=160), 3, 0, 2.2, 0.6),
        ]
        
        away_matches_old = [
            create_test_match("m10", "team_x", "away", reference_date - timedelta(days=180), 1, 2, 0.9, 1.6),
            create_test_match("m11", "away", "team_y", reference_date - timedelta(days=170), 2, 0, 1.8, 0.5),
            create_test_match("m12", "team_z", "away", reference_date - timedelta(days=160), 1, 1, 1.2, 1.1),
        ]
        
        result_old = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches_old, away_matches_old, reference_date
        )
        
        # Recent matches should have higher confidence
        assert result_recent.comparison_confidence > result_old.comparison_confidence


class TestConfidenceCalculation:
    """Test confidence calculation formula."""
    
    def test_confidence_with_many_common_opponents(self, calculator):
        """Many common opponents (5+) → sample_factor = 1.0."""
        reference_date = datetime(2024, 1, 15)
        
        # 5 common opponents
        home_matches = [
            create_test_match("m1", "home", "team_a", reference_date - timedelta(days=10), 2, 1, 1.5, 0.8),
            create_test_match("m2", "home", "team_b", reference_date - timedelta(days=9), 1, 1, 1.0, 1.0),
            create_test_match("m3", "home", "team_c", reference_date - timedelta(days=8), 3, 0, 2.2, 0.6),
            create_test_match("m4", "home", "team_d", reference_date - timedelta(days=7), 2, 0, 1.8, 0.5),
            create_test_match("m5", "home", "team_e", reference_date - timedelta(days=6), 1, 1, 1.0, 1.0),
        ]
        
        away_matches = [
            create_test_match("m6", "team_a", "away", reference_date - timedelta(days=10), 1, 2, 0.9, 1.6),
            create_test_match("m7", "away", "team_b", reference_date - timedelta(days=9), 2, 0, 1.8, 0.5),
            create_test_match("m8", "team_c", "away", reference_date - timedelta(days=8), 1, 1, 1.2, 1.1),
            create_test_match("m9", "away", "team_d", reference_date - timedelta(days=7), 1, 1, 1.0, 1.0),
            create_test_match("m10", "team_e", "away", reference_date - timedelta(days=6), 0, 2, 0.7, 1.9),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        assert result.n_common_opponents == 5
        # Sample factor should be 1.0 (5/5)
        # Confidence should be relatively high
        assert result.comparison_confidence > 0.5
    
    def test_confidence_with_few_common_opponents(self, calculator):
        """Few common opponents (2) → sample_factor < 1.0."""
        reference_date = datetime(2024, 1, 15)
        
        # Only 2 common opponents (below min threshold of 3)
        home_matches = [
            create_test_match("m1", "home", "team_x", reference_date - timedelta(days=10), 2, 1, 1.5, 0.8),
            create_test_match("m2", "home", "team_y", reference_date - timedelta(days=5), 1, 1, 1.0, 1.0),
        ]
        
        away_matches = [
            create_test_match("m3", "team_x", "away", reference_date - timedelta(days=8), 1, 2, 0.9, 1.6),
            create_test_match("m4", "away", "team_y", reference_date - timedelta(days=4), 2, 0, 1.8, 0.5),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        assert result.n_common_opponents == 2
        # Insufficient common opponents → comparisons remain None
        assert result.home_avg_points_vs_common is None
    
    def test_confidence_formula_three_factors(self, calculator):
        """confidence = sample_factor * recency_factor * context_factor."""
        reference_date = datetime(2024, 1, 15)
        
        # 3 common opponents (sample_factor = 3/5 = 0.6)
        # Recent matches (recency_factor ~ 0.9+)
        # Perfect context match (context_factor = 1.0)
        home_matches = [
            create_test_match("m1", "home", "team_x", reference_date - timedelta(days=5), 2, 1, 1.5, 0.8),
            create_test_match("m2", "home", "team_y", reference_date - timedelta(days=4), 1, 1, 1.0, 1.0),
            create_test_match("m3", "home", "team_z", reference_date - timedelta(days=3), 3, 0, 2.2, 0.6),
        ]
        
        away_matches = [
            create_test_match("m4", "away", "team_x", reference_date - timedelta(days=5), 1, 2, 0.9, 1.6),
            create_test_match("m5", "away", "team_y", reference_date - timedelta(days=4), 2, 0, 1.8, 0.5),
            create_test_match("m6", "away", "team_z", reference_date - timedelta(days=3), 1, 1, 1.2, 1.1),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        assert result.n_common_opponents == 3
        # Confidence should reflect all three factors
        assert 0.0 < result.comparison_confidence <= 1.0


class TestSignalStrength:
    """Test signal strength determination."""
    
    def test_signal_neutral_when_small_differential(self, calculator):
        """Small differential (< 0.3) → neutral signal."""
        reference_date = datetime(2024, 1, 15)
        
        # Very similar performance vs common opponents
        home_matches = [
            create_test_match("m1", "home", "team_x", reference_date - timedelta(days=10), 1, 1, 1.0, 1.0),
            create_test_match("m2", "home", "team_y", reference_date - timedelta(days=8), 2, 1, 1.2, 0.9),
            create_test_match("m3", "home", "team_z", reference_date - timedelta(days=5), 1, 1, 1.1, 1.0),
        ]
        
        away_matches = [
            create_test_match("m4", "team_x", "away", reference_date - timedelta(days=9), 1, 1, 1.0, 1.0),
            create_test_match("m5", "away", "team_y", reference_date - timedelta(days=7), 1, 1, 0.9, 1.1),
            create_test_match("m6", "team_z", "away", reference_date - timedelta(days=4), 2, 1, 1.3, 1.0),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        assert result.signal_strength == "neutral"
    
    def test_signal_neutral_when_low_confidence(self, calculator):
        """Low confidence (< 0.5) → neutral signal even with differential."""
        reference_date = datetime(2024, 1, 15)
        
        # Only 1 common opponent (low sample size)
        # But significant differential in performance
        home_matches = [
            create_test_match("m1", "home", "team_x", reference_date - timedelta(days=10), 3, 0, 2.5, 0.5),
        ]
        
        away_matches = [
            create_test_match("m2", "team_x", "away", reference_date - timedelta(days=8), 0, 2, 0.6, 1.8),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        # Low confidence due to insufficient common opponents
        assert result.signal_strength == "neutral"
    
    def test_signal_home_favored_with_evidence(self, calculator):
        """Large positive differential + high confidence → home_favored."""
        reference_date = datetime(2024, 1, 15)
        
        # Home team: strong wins vs all common opponents
        home_matches = [
            create_test_match("m1", "home", "team_x", reference_date - timedelta(days=10), 3, 0, 2.5, 0.5),
            create_test_match("m2", "home", "team_y", reference_date - timedelta(days=8), 2, 0, 2.0, 0.6),
            create_test_match("m3", "home", "team_z", reference_date - timedelta(days=5), 3, 1, 2.2, 1.0),
            create_test_match("m4", "home", "team_a", reference_date - timedelta(days=4), 2, 0, 1.8, 0.4),
            create_test_match("m5", "home", "team_b", reference_date - timedelta(days=3), 1, 0, 1.5, 0.7),
        ]
        
        # Away team: losses vs all common opponents
        away_matches = [
            create_test_match("m6", "team_x", "away", reference_date - timedelta(days=9), 2, 0, 1.6, 0.8),
            create_test_match("m7", "team_y", "away", reference_date - timedelta(days=7), 1, 0, 1.2, 0.5),
            create_test_match("m8", "team_z", "away", reference_date - timedelta(days=4), 2, 1, 1.8, 1.2),
            create_test_match("m9", "team_a", "away", reference_date - timedelta(days=3), 1, 0, 0.9, 0.6),
            create_test_match("m10", "team_b", "away", reference_date - timedelta(days=2), 1, 0, 1.1, 0.8),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        # Should have strong home_favored signal
        assert result.n_common_opponents == 5
        assert result.points_differential > 0.5
        assert result.comparison_confidence > 0.7
        assert result.signal_strength == "home_favored"
    
    def test_signal_away_favored_with_evidence(self, calculator):
        """Large negative differential + high confidence → away_favored."""
        reference_date = datetime(2024, 1, 15)
        
        # Home team: losses vs all common opponents (playing at home)
        home_matches = [
            create_test_match("m1", "home", "team_x", reference_date - timedelta(days=10), 0, 2, 0.7, 1.5),
            create_test_match("m2", "home", "team_y", reference_date - timedelta(days=8), 0, 1, 0.5, 1.1),
            create_test_match("m3", "home", "team_z", reference_date - timedelta(days=5), 1, 2, 1.0, 1.6),
            create_test_match("m4", "home", "team_a", reference_date - timedelta(days=4), 0, 1, 0.6, 1.0),
            create_test_match("m5", "home", "team_b", reference_date - timedelta(days=3), 0, 1, 0.5, 0.9),
        ]
        
        # Away team: strong wins vs all common opponents (playing away)
        away_matches = [
            create_test_match("m6", "team_x", "away", reference_date - timedelta(days=9), 0, 3, 0.6, 2.5),
            create_test_match("m7", "team_y", "away", reference_date - timedelta(days=7), 0, 2, 0.5, 2.0),
            create_test_match("m8", "team_z", "away", reference_date - timedelta(days=4), 1, 3, 1.1, 2.3),
            create_test_match("m9", "team_a", "away", reference_date - timedelta(days=3), 0, 2, 0.6, 1.9),
            create_test_match("m10", "team_b", "away", reference_date - timedelta(days=2), 0, 1, 0.7, 1.6),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        # Should have strong away_favored signal
        assert result.n_common_opponents == 5
        assert result.points_differential < -0.5
        assert result.comparison_confidence > 0.7
        assert result.signal_strength == "away_favored"
    
    def test_no_naive_transitive_logic(self, calculator):
        """Never claim A > B from transitive logic alone."""
        # This test ensures we use confidence thresholds and don't make
        # naive claims like "A beat X, B lost to X → A > B"
        reference_date = datetime(2024, 1, 15)
        
        # Home team: 1 win vs Team X
        home_matches = [
            create_test_match("m1", "home", "team_x", reference_date - timedelta(days=10), 2, 1, 1.5, 0.8),
        ]
        
        # Away team: 1 loss vs Team X
        away_matches = [
            create_test_match("m2", "team_x", "away", reference_date - timedelta(days=8), 2, 0, 1.6, 0.6),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        # Despite home beating X and away losing to X,
        # confidence should be low (only 1 common opponent)
        # Signal should be neutral
        assert result.n_common_opponents == 1
        assert result.signal_strength == "neutral"  # Insufficient evidence


class TestInsufficientData:
    """Test handling of insufficient common opponent data."""
    
    def test_insufficient_common_opponents_returns_none(self, calculator):
        """Fewer than min_common_opponents → all comparisons = None."""
        reference_date = datetime(2024, 1, 15)
        
        # Only 2 common opponents (min is 3)
        home_matches = [
            create_test_match("m1", "home", "team_x", reference_date - timedelta(days=10), 2, 1, 1.5, 0.8),
            create_test_match("m2", "home", "team_y", reference_date - timedelta(days=5), 1, 1, 1.0, 1.0),
        ]
        
        away_matches = [
            create_test_match("m3", "team_x", "away", reference_date - timedelta(days=8), 1, 2, 0.9, 1.6),
            create_test_match("m4", "away", "team_y", reference_date - timedelta(days=4), 2, 0, 1.8, 0.5),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        assert result.n_common_opponents == 2
        # All aggregated comparisons should be None
        assert result.home_avg_points_vs_common is None
        assert result.away_avg_points_vs_common is None
        assert result.points_differential is None
        assert result.xg_differential is None
        assert result.comparison_confidence == 0.0
    
    def test_zero_common_opponents_returns_empty_result(self, calculator):
        """Zero common opponents → valid result with n=0, all comparisons None."""
        reference_date = datetime(2024, 1, 15)
        
        home_matches = [
            create_test_match("m1", "home", "team_a", reference_date - timedelta(days=10), 2, 1, 1.5, 0.8),
        ]
        
        away_matches = [
            create_test_match("m2", "team_b", "away", reference_date - timedelta(days=8), 1, 2, 0.9, 1.6),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        assert result.n_common_opponents == 0
        assert len(result.common_opponent_ids) == 0
        assert result.home_avg_points_vs_common is None
        assert result.comparison_confidence == 0.0
        assert result.data_quality_score == 0.0


class TestDataQuality:
    """Test data quality handling."""
    
    def test_missing_xg_handled_gracefully(self, calculator):
        """Missing xG → xg_differential = None, other metrics still calculated."""
        reference_date = datetime(2024, 1, 15)
        
        # Matches with basic data but no xG
        home_matches = [
            create_test_match("m1", "home", "team_x", reference_date - timedelta(days=10), 2, 1),
            create_test_match("m2", "home", "team_y", reference_date - timedelta(days=5), 1, 1),
            create_test_match("m3", "home", "team_z", reference_date - timedelta(days=3), 3, 0),
        ]
        
        away_matches = [
            create_test_match("m4", "team_x", "away", reference_date - timedelta(days=8), 1, 2),
            create_test_match("m5", "away", "team_y", reference_date - timedelta(days=4), 2, 0),
            create_test_match("m6", "team_z", "away", reference_date - timedelta(days=2), 1, 1),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        # Points comparison should work
        assert result.home_avg_points_vs_common is not None
        assert result.away_avg_points_vs_common is not None
        assert result.points_differential is not None
        
        # But xG comparison should be None
        assert result.xg_differential is None
    
    def test_missing_shots_handled_gracefully(self, calculator):
        """Missing shots → shots_differential = None, other metrics still calculated."""
        reference_date = datetime(2024, 1, 15)
        
        # Matches with xG but no shots
        home_matches = [
            create_test_match("m1", "home", "team_x", reference_date - timedelta(days=10), 2, 1, 1.5, 0.8),
            create_test_match("m2", "home", "team_y", reference_date - timedelta(days=5), 1, 1, 1.0, 1.0),
            create_test_match("m3", "home", "team_z", reference_date - timedelta(days=3), 3, 0, 2.2, 0.6),
        ]
        
        away_matches = [
            create_test_match("m4", "team_x", "away", reference_date - timedelta(days=8), 1, 2, 0.9, 1.6),
            create_test_match("m5", "away", "team_y", reference_date - timedelta(days=4), 2, 0, 1.8, 0.5),
            create_test_match("m6", "team_z", "away", reference_date - timedelta(days=2), 1, 1, 1.2, 1.1),
        ]
        
        result = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches, away_matches, reference_date
        )
        
        # xG and points should work
        assert result.xg_differential is not None
        assert result.points_differential is not None
        
        # But shots should be None (no shot data provided)
        assert result.shots_differential is None
    
    def test_data_quality_score_calculated(self, calculator):
        """data_quality_score reflects completeness of available metrics."""
        reference_date = datetime(2024, 1, 15)
        
        # Full data (5 opponents, all metrics)
        home_matches_full = [
            create_test_match("m1", "home", "team_a", reference_date - timedelta(days=10), 2, 1, 1.5, 0.8, 15, 10),
            create_test_match("m2", "home", "team_b", reference_date - timedelta(days=9), 1, 1, 1.0, 1.0, 12, 11),
            create_test_match("m3", "home", "team_c", reference_date - timedelta(days=8), 3, 0, 2.2, 0.6, 18, 8),
            create_test_match("m4", "home", "team_d", reference_date - timedelta(days=7), 2, 0, 1.8, 0.5, 14, 7),
            create_test_match("m5", "home", "team_e", reference_date - timedelta(days=6), 1, 1, 1.0, 1.0, 11, 12),
        ]
        
        away_matches_full = [
            create_test_match("m6", "team_a", "away", reference_date - timedelta(days=10), 1, 2, 0.9, 1.6, 10, 14),
            create_test_match("m7", "away", "team_b", reference_date - timedelta(days=9), 2, 0, 1.8, 0.5, 16, 7),
            create_test_match("m8", "team_c", "away", reference_date - timedelta(days=8), 1, 1, 1.2, 1.1, 12, 13),
            create_test_match("m9", "away", "team_d", reference_date - timedelta(days=7), 1, 1, 1.0, 1.0, 11, 10),
            create_test_match("m10", "team_e", "away", reference_date - timedelta(days=6), 0, 2, 0.7, 1.9, 9, 15),
        ]
        
        result_full = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches_full, away_matches_full, reference_date
        )
        
        # Limited data (1 opponent, only basic metrics)
        home_matches_limited = [
            create_test_match("m11", "home", "team_x", reference_date - timedelta(days=10), 2, 1),
        ]
        
        away_matches_limited = [
            create_test_match("m12", "team_x", "away", reference_date - timedelta(days=8), 1, 2),
        ]
        
        result_limited = calculator.calculate_common_opponent_intelligence(
            "home", "away", home_matches_limited, away_matches_limited, reference_date
        )
        
        # Full data should have higher quality score
        assert result_full.data_quality_score > result_limited.data_quality_score
        assert result_full.data_quality_score >= 0.8  # High quality
        assert result_limited.data_quality_score < 0.5  # Low quality


class TestCommonOpponentMatchStructure:
    """Test CommonOpponentMatch dataclass."""
    
    def test_common_opponent_match_structure(self):
        """Test CommonOpponentMatch dataclass fields."""
        match = CommonOpponentMatch(
            team_id="team_a",
            opponent_id="team_b",
            match_id="match_123",
            match_date=datetime(2024, 1, 10),
            is_home=True,
            competition_id="comp_test",
            result="win",
            goals_for=2,
            goals_against=1,
            goal_difference=1,
            points=3,
            xg=1.5,
            xga=0.8,
            shots=15,
            shots_on_target=8,
            possession=58.5,
            has_advanced_stats=True,
        )
        
        assert match.team_id == "team_a"
        assert match.opponent_id == "team_b"
        assert match.is_home is True
        assert match.result == "win"
        assert match.points == 3
        assert match.xg == 1.5
        assert match.has_advanced_stats is True
    
    def test_common_opponent_match_validation(self):
        """Test CommonOpponentMatch validation."""
        # Invalid result
        with pytest.raises(AssertionError):
            CommonOpponentMatch(
                team_id="team_a",
                opponent_id="team_b",
                match_id="match_123",
                match_date=datetime(2024, 1, 10),
                is_home=True,
                competition_id="comp_test",
                result="unknown",  # Invalid
                goals_for=2,
                goals_against=1,
                goal_difference=1,
                points=3,
            )
        
        # Invalid points
        with pytest.raises(AssertionError):
            CommonOpponentMatch(
                team_id="team_a",
                opponent_id="team_b",
                match_id="match_123",
                match_date=datetime(2024, 1, 10),
                is_home=True,
                competition_id="comp_test",
                result="win",
                goals_for=2,
                goals_against=1,
                goal_difference=1,
                points=5,  # Invalid
            )
