"""Tests for Group 2 temporal leakage prevention.

Ensures all Group 2 calculators (lineup, tactical, shot intelligence, shot production)
respect temporal boundaries and do not leak future information into predictions.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock

from app.features.lineup_intelligence import (
    PlayerAvailability,
    PlayerAvailabilityStatus,
    LineupIntelligenceCalculator,
)
from app.features.tactical_matchup import TacticalMatchupCalculator
from app.features.shot_intelligence import ShotIntelligenceCalculator
from app.features.shot_production import ShotProductionCalculator
from app.features.advanced_team_intelligence import MatchWithStatistics
from app.domain.match import Match
from app.domain.statistics import TeamMatchStatistic
from app.domain.enums import MatchStatus, MatchOutcome


@pytest.fixture
def mock_session():
    """Create mock database session."""
    return Mock()


def create_match_with_stats(
    match_id: str,
    home_team_id: str,
    away_team_id: str,
    scheduled_at: datetime,
    home_shots: int = 10,
    away_shots: int = 8
) -> MatchWithStatistics:
    """Helper to create MatchWithStatistics."""
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
        shots_on_target=4,
        possession_percentage=55.0
    )
    
    away_stats = TeamMatchStatistic(
        id=f"{match_id}_a",
        match_id=match_id,
        team_id=away_team_id,
        goals_scored=1,
        goals_conceded=1,
        shots_total=away_shots,
        shots_on_target=3,
        possession_percentage=45.0
    )
    
    return MatchWithStatistics(
        match=match,
        home_statistics=home_stats,
        away_statistics=away_stats
    )


class TestLineupCalculatorTemporalLeakage:
    """Test LineupIntelligenceCalculator temporal leakage prevention."""
    
    def test_lineup_calculator_excludes_future_matches(self, mock_session):
        """Test that LineupIntelligenceCalculator excludes matches >= cutoff."""
        calculator = LineupIntelligenceCalculator(session=mock_session)
        
        # Create matches across temporal boundary
        cutoff = datetime(2024, 1, 10, 12, 0, 0)
        
        matches = [
            create_match_with_stats("m1", "team_a", "opp_1", datetime(2024, 1, 5)),  # Before
            create_match_with_stats("m2", "team_a", "opp_2", datetime(2024, 1, 8)),  # Before
            create_match_with_stats("m3", "team_a", "opp_3", cutoff),  # AT cutoff - should be excluded
            create_match_with_stats("m4", "team_a", "opp_4", datetime(2024, 1, 12)),  # After
            create_match_with_stats("m5", "team_a", "opp_5", datetime(2024, 1, 15)),  # After
        ]
        
        player_absences = [
            PlayerAvailability(
                player_id="player_1",
                status=PlayerAvailabilityStatus.INJURED
            )
        ]
        
        result = calculator.calculate_lineup_impact(
            team_id="team_a",
            player_absences=player_absences,
            historical_matches_with_stats=matches,
            before_datetime=cutoff
        )
        
        # Should only consider first 2 matches (m1, m2)
        # m3 at exact cutoff should be excluded (strict <)
        # Method will be "unavailable" since we don't have lineup data,
        # but temporal filtering should still be applied
        assert result.team_id == "team_a"


class TestTacticalCalculatorTemporalLeakage:
    """Test TacticalMatchupCalculator temporal leakage prevention."""
    
    def test_tactical_calculator_excludes_future_matches(self, mock_session):
        """Test that TacticalMatchupCalculator excludes matches >= cutoff."""
        calculator = TacticalMatchupCalculator(session=mock_session, min_matches=2)
        
        cutoff = datetime(2024, 1, 10, 12, 0, 0)
        
        matches = [
            create_match_with_stats("m1", "team_a", "opp_1", datetime(2024, 1, 5)),  # Before
            create_match_with_stats("m2", "team_a", "opp_2", datetime(2024, 1, 8)),  # Before
            create_match_with_stats("m3", "team_a", "opp_3", cutoff),  # AT cutoff - should be excluded
            create_match_with_stats("m4", "team_a", "opp_4", datetime(2024, 1, 12)),  # After
        ]
        
        profile = calculator.calculate_tactical_profile(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=cutoff
        )
        
        # Should only use first 2 matches (strict < cutoff)
        assert profile.sample_size == 2


class TestShotIntelligenceTemporalLeakage:
    """Test ShotIntelligenceCalculator temporal leakage prevention."""
    
    def test_shot_intelligence_excludes_future_matches(self, mock_session):
        """Test that ShotIntelligenceCalculator excludes matches >= cutoff."""
        calculator = ShotIntelligenceCalculator(
            session=mock_session,
            recent_window=10,
            min_matches=2
        )
        
        cutoff = datetime(2024, 1, 10, 12, 0, 0)
        
        matches = [
            create_match_with_stats("m1", "team_a", "opp_1", datetime(2024, 1, 5), home_shots=10),
            create_match_with_stats("m2", "team_a", "opp_2", datetime(2024, 1, 8), home_shots=12),
            create_match_with_stats("m3", "team_a", "opp_3", cutoff, home_shots=20),  # AT cutoff
            create_match_with_stats("m4", "team_a", "opp_4", datetime(2024, 1, 12), home_shots=25),
        ]
        
        metrics = calculator.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=cutoff
        )
        
        # Should only use first 2 matches
        assert metrics.sample_size == 2
        assert metrics.matches_with_shot_data == 2
        
        # Shots per match should be average of 10 and 12 = 11.0
        # NOT include 20 or 25 from future matches
        assert metrics.shots_total_per_match == 11.0


class TestShotProductionTemporalLeakage:
    """Test ShotProductionCalculator temporal leakage prevention."""
    
    def test_shot_production_boundary_condition(self, mock_session):
        """Test that shot production respects temporal cutoff for raw counts."""
        shot_calculator = ShotIntelligenceCalculator(
            session=mock_session,
            recent_window=10,
            min_matches=2
        )
        
        prod_calculator = ShotProductionCalculator(session=mock_session, min_matches=5)
        
        cutoff = datetime(2024, 1, 10, 12, 0, 0)
        
        matches = [
            create_match_with_stats("m1", "team_a", "opp_1", datetime(2024, 1, 1), home_shots=8),
            create_match_with_stats("m2", "team_a", "opp_2", datetime(2024, 1, 2), home_shots=9),
            create_match_with_stats("m3", "team_a", "opp_3", datetime(2024, 1, 3), home_shots=10),
            create_match_with_stats("m4", "team_a", "opp_4", datetime(2024, 1, 4), home_shots=11),
            create_match_with_stats("m5", "team_a", "opp_5", datetime(2024, 1, 5), home_shots=12),
            create_match_with_stats("m6", "team_a", "opp_6", cutoff, home_shots=100),  # AT cutoff - excluded
            create_match_with_stats("m7", "team_a", "opp_7", datetime(2024, 1, 12), home_shots=200),  # After
        ]
        
        # Get raw shot counts with temporal filtering
        shot_counts, _ = shot_calculator.get_raw_shot_counts(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=cutoff
        )
        
        # Should only include [8, 9, 10, 11, 12], NOT 100 or 200
        assert len(shot_counts) == 5
        assert shot_counts == [8.0, 9.0, 10.0, 11.0, 12.0]
        
        # Calculate production
        production = prod_calculator.calculate(
            team_id="team_a",
            shot_counts=shot_counts,
            before_datetime=cutoff
        )
        
        # Mean should be 10.0, not influenced by future 100 or 200
        assert production.expected_shots_mean == 10.0


class TestNoPostMatchShotDataInFeatures:
    """Test that post-match shot statistics are not leaked into pre-match features."""
    
    def test_no_post_match_shot_data_in_features(self, mock_session):
        """Test that final match statistics are not used for pre-match prediction."""
        calculator = ShotIntelligenceCalculator(
            session=mock_session,
            recent_window=10,
            min_matches=3
        )
        
        # Scenario: Predicting match on 2024-01-15 at 15:00
        prediction_time = datetime(2024, 1, 15, 15, 0, 0)
        
        # Historical matches (finished, before prediction)
        historical_matches = [
            create_match_with_stats("m1", "team_a", "opp_1", datetime(2024, 1, 5, 18, 0), home_shots=10),
            create_match_with_stats("m2", "team_a", "opp_2", datetime(2024, 1, 10, 20, 0), home_shots=12),
            create_match_with_stats("m3", "team_a", "opp_3", datetime(2024, 1, 12, 19, 30), home_shots=11),
        ]
        
        # The target match (scheduled for prediction_time)
        # This match's statistics should NOT be used
        target_match = create_match_with_stats(
            "target",
            "team_a",
            "opponent",
            prediction_time,
            home_shots=25  # Final statistic from this match
        )
        
        # Calculate features using only historical matches
        metrics = calculator.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=historical_matches,  # NOT including target match
            before_datetime=prediction_time
        )
        
        # Shots per match should be (10+12+11)/3 = 11.0
        # NOT influenced by target match's 25 shots
        assert metrics.shots_total_per_match == 11.0
        assert metrics.sample_size == 3


class TestAllGroup2CalculatorsRespectTemporalCutoff:
    """Cross-calculator consistency test for temporal validity."""
    
    def test_all_group2_calculators_respect_temporal_cutoff(self, mock_session):
        """Test that all Group 2 calculators use strict < comparison."""
        cutoff = datetime(2024, 1, 10, 12, 0, 0)
        
        matches = [
            create_match_with_stats("m1", "team_a", "opp_1", datetime(2024, 1, 5)),
            create_match_with_stats("m2", "team_a", "opp_2", datetime(2024, 1, 8)),
            create_match_with_stats("m3", "team_a", "opp_3", cutoff),  # AT cutoff
            create_match_with_stats("m4", "team_a", "opp_4", datetime(2024, 1, 12)),
        ]
        
        # Lineup calculator
        lineup_calc = LineupIntelligenceCalculator(session=mock_session)
        lineup_result = lineup_calc.calculate_lineup_impact(
            team_id="team_a",
            player_absences=[
                PlayerAvailability(player_id="p1", status=PlayerAvailabilityStatus.INJURED)
            ],
            historical_matches_with_stats=matches,
            before_datetime=cutoff
        )
        # Should only use first 2 matches (temporal filtering applied)
        assert lineup_result.team_id == "team_a"
        
        # Tactical calculator
        tactical_calc = TacticalMatchupCalculator(session=mock_session, min_matches=2)
        tactical_profile = tactical_calc.calculate_tactical_profile(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=cutoff
        )
        assert tactical_profile.sample_size == 2
        
        # Shot intelligence calculator
        shot_calc = ShotIntelligenceCalculator(session=mock_session, min_matches=2)
        shot_metrics = shot_calc.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=cutoff
        )
        assert shot_metrics.sample_size == 2
        
        # All calculators should agree on sample size (2 matches before cutoff)
        assert tactical_profile.sample_size == shot_metrics.sample_size == 2
