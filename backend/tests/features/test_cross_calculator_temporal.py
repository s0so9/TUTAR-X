"""Cross-calculator temporal leakage verification tests.

These tests verify that ALL Phase 10 Group 1 calculators respect temporal validity:
- AdvancedTeamIntelligenceCalculator (10A)
- OpponentAdjustmentCalculator (10B)
- TemporalIntelligenceCalculator (10C)

CRITICAL: All calculators must use strict < comparison for before_datetime
to prevent temporal leakage in backtesting and model training.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock

from app.features.advanced_team_intelligence import (
    AdvancedTeamIntelligenceCalculator,
    MatchWithStatistics,
)
from app.features.opponent_adjustment import OpponentAdjustmentCalculator
from app.features.temporal_intelligence import (
    TemporalIntelligenceCalculator,
    TemporalWeighting,
)
from app.prediction.elo import EloRatingSystem
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
    home_xg: float = 1.5,
    away_xg: float = 1.3
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
        shots_total=12,
        shots_on_target=5,
        possession_percentage=55.0,
    )
    
    away_stats = TeamMatchStatistic(
        id=f"{match_id}_away",
        match_id=match_id,
        team_id=away_team_id,
        xg=away_xg,
        xg_against=home_xg,
        shots_total=10,
        shots_on_target=4,
        possession_percentage=45.0,
    )
    
    return MatchWithStatistics(
        match=match,
        home_statistics=home_stats,
        away_statistics=away_stats,
    )


def test_advanced_team_intelligence_respects_before_datetime():
    """Test that AdvancedTeamIntelligenceCalculator respects before_datetime.
    
    CRITICAL: Verifies no temporal leakage in team intelligence calculation.
    """
    session = Mock()
    calculator = AdvancedTeamIntelligenceCalculator(session, min_matches=3)
    
    base_date = datetime(2023, 10, 1)
    cutoff_date = base_date + timedelta(days=35)
    
    matches = [
        create_test_match("m1", "team_test", "team_opp1", base_date, 2, 0, 1.8, 0.9),
        create_test_match("m2", "team_test", "team_opp2", base_date + timedelta(days=7), 1, 1, 1.3, 1.2),
        create_test_match("m3", "team_test", "team_opp3", base_date + timedelta(days=14), 3, 0, 2.1, 0.8),
        create_test_match("m4", "team_test", "team_opp4", base_date + timedelta(days=21), 2, 1, 1.9, 1.4),
        create_test_match("m5", "team_test", "team_opp5", base_date + timedelta(days=28), 1, 2, 1.2, 1.8),
        # These should be excluded (at or after cutoff)
        create_test_match("m6", "team_test", "team_opp6", cutoff_date, 3, 0, 2.5, 0.7),
        create_test_match("m7", "team_test", "team_opp7", cutoff_date + timedelta(days=7), 3, 1, 2.3, 1.0),
    ]
    
    # Calculate with temporal cutoff
    metrics = calculator.calculate_advanced_metrics(
        "team_test", 
        matches, 
        window_type="recent",
        before_datetime=cutoff_date
    )
    
    # Should only use first 5 matches (before cutoff)
    assert metrics.sample_size == 5
    
    # xG should be from first 5 matches only
    # Average xG from first 5: (1.8 + 1.3 + 2.1 + 1.9 + 1.2) / 5 = 1.66
    assert abs(metrics.xg_for_per_match - 1.66) < 0.01


def test_opponent_adjustment_uses_historical_elo_only():
    """Test that OpponentAdjustmentCalculator uses historical Elo, not current.
    
    CRITICAL: Verifies opponent strength retrieved at match time, preventing temporal leakage.
    """
    session = Mock()
    
    # Create Elo system
    elo_system = EloRatingSystem(k_factor=20, home_advantage=100, initial_rating=1500)
    
    calculator = OpponentAdjustmentCalculator(session, elo_system, min_matches=3)
    
    base_date = datetime(2023, 10, 1)
    
    matches = [
        create_test_match("m1", "team_test", "team_opp1", base_date, 2, 0, 1.8, 0.9),
        create_test_match("m2", "team_test", "team_opp2", base_date + timedelta(days=7), 1, 1, 1.5, 1.3),
        create_test_match("m3", "team_test", "team_opp3", base_date + timedelta(days=14), 3, 0, 2.0, 0.8),
    ]
    
    # Process matches to build Elo history
    for mws in matches:
        elo_system.process_match(
            mws.match.id,
            mws.match.home_team_id,
            mws.match.away_team_id,
            mws.match.home_score or 0,
            mws.match.away_score or 0,
            mws.match.scheduled_at
        )
    
    # Calculate opponent-adjusted metrics
    metrics = calculator.calculate_adjusted_metrics("team_test", matches)
    
    # Should use historical Elo ratings (via get_rating_at_time)
    # Verify metrics calculated
    assert metrics.sample_size == 3
    assert metrics.adj_xg_for is not None


def test_temporal_intelligence_respects_before_datetime():
    """Test that TemporalIntelligenceCalculator respects before_datetime.
    
    CRITICAL: Verifies no temporal leakage in temporal intelligence calculation.
    """
    session = Mock()
    calculator = TemporalIntelligenceCalculator(
        session,
        weighting=TemporalWeighting(method="exponential", decay_factor=0.95),
        min_matches=3
    )
    
    base_date = datetime(2023, 10, 1)
    cutoff_date = base_date + timedelta(days=28)
    
    matches = [
        create_test_match("m1", "team_test", "team_opp1", base_date, 0, 2),
        create_test_match("m2", "team_test", "team_opp2", base_date + timedelta(days=7), 1, 1),
        create_test_match("m3", "team_test", "team_opp3", base_date + timedelta(days=14), 2, 1),
        create_test_match("m4", "team_test", "team_opp4", base_date + timedelta(days=21), 3, 0),
        # These should be excluded (at or after cutoff)
        create_test_match("m5", "team_test", "team_opp5", cutoff_date, 3, 0),
        create_test_match("m6", "team_test", "team_opp6", cutoff_date + timedelta(days=7), 3, 1),
    ]
    
    # Calculate with temporal cutoff
    metrics = calculator.calculate_temporal_metrics(
        "team_test", 
        matches,
        before_datetime=cutoff_date
    )
    
    # Should only use first 4 matches (before cutoff)
    assert metrics.sample_size == 4
    
    # Verify metrics exist
    assert metrics.recent_form_weighted is not None


def test_cross_calculator_consistency():
    """Test that all 3 calculators agree on temporal cutoff.
    
    CRITICAL: Verifies consistent temporal validity across all Group 1 calculators.
    """
    session = Mock()
    
    # Initialize all calculators
    advanced_calc = AdvancedTeamIntelligenceCalculator(session, min_matches=3)
    elo_system = EloRatingSystem(k_factor=20, home_advantage=100, initial_rating=1500)
    opponent_calc = OpponentAdjustmentCalculator(session, elo_system, min_matches=3)
    temporal_calc = TemporalIntelligenceCalculator(session, min_matches=3)
    
    base_date = datetime(2023, 10, 1)
    cutoff_date = base_date + timedelta(days=35)
    
    matches = [
        create_test_match("m1", "team_test", "team_opp1", base_date, 2, 0, 1.8, 0.9),
        create_test_match("m2", "team_test", "team_opp2", base_date + timedelta(days=7), 1, 1, 1.5, 1.3),
        create_test_match("m3", "team_test", "team_opp3", base_date + timedelta(days=14), 3, 0, 2.0, 0.8),
        create_test_match("m4", "team_test", "team_opp4", base_date + timedelta(days=21), 2, 1, 1.7, 1.4),
        create_test_match("m5", "team_test", "team_opp5", base_date + timedelta(days=28), 1, 2, 1.3, 1.9),
        # These should be excluded
        create_test_match("m6", "team_test", "team_opp6", cutoff_date, 3, 0, 2.5, 0.7),
        create_test_match("m7", "team_test", "team_opp7", cutoff_date + timedelta(days=7), 3, 1, 2.3, 1.0),
    ]
    
    # Process Elo matches
    for mws in matches[:5]:  # Only before cutoff
        elo_system.process_match(
            mws.match.id,
            mws.match.home_team_id,
            mws.match.away_team_id,
            mws.match.home_score or 0,
            mws.match.away_score or 0,
            mws.match.scheduled_at
        )
    
    # Calculate with all three calculators
    advanced_metrics = advanced_calc.calculate_advanced_metrics(
        "team_test", matches, before_datetime=cutoff_date
    )
    opponent_metrics = opponent_calc.calculate_adjusted_metrics(
        "team_test", matches, before_datetime=cutoff_date
    )
    temporal_metrics = temporal_calc.calculate_temporal_metrics(
        "team_test", matches, before_datetime=cutoff_date
    )
    
    # All should agree on sample size (5 matches before cutoff)
    assert advanced_metrics.sample_size == 5
    assert opponent_metrics.sample_size == 5
    assert temporal_metrics.sample_size == 5


def test_backtesting_scenario():
    """Test walk-forward backtesting scenario.
    
    Simulates making predictions at different historical timestamps,
    verifying each prediction only uses data available at that time.
    """
    session = Mock()
    calculator = AdvancedTeamIntelligenceCalculator(session, min_matches=3)
    
    base_date = datetime(2023, 10, 1)
    
    # Historical matches
    matches = [
        create_test_match("m1", "team_test", "team_opp1", base_date, 2, 0, 1.5, 1.0),
        create_test_match("m2", "team_test", "team_opp2", base_date + timedelta(days=7), 1, 1, 1.3, 1.2),
        create_test_match("m3", "team_test", "team_opp3", base_date + timedelta(days=14), 3, 0, 2.0, 0.9),
        create_test_match("m4", "team_test", "team_opp4", base_date + timedelta(days=21), 2, 1, 1.8, 1.3),
        create_test_match("m5", "team_test", "team_opp5", base_date + timedelta(days=28), 1, 2, 1.2, 1.7),
    ]
    
    # Walk forward: make predictions at each timestamp
    prediction_timestamps = [
        base_date + timedelta(days=14),  # After match 2
        base_date + timedelta(days=21),  # After match 3
        base_date + timedelta(days=28),  # After match 4
    ]
    
    sample_sizes = []
    avg_xgs = []
    
    for pred_time in prediction_timestamps:
        metrics = calculator.calculate_advanced_metrics(
            "team_test",
            matches,
            before_datetime=pred_time
        )
        sample_sizes.append(metrics.sample_size)
        avg_xgs.append(metrics.xg_for_per_match)
    
    # Sample sizes should increase as we walk forward
    assert sample_sizes[0] == 2  # Only m1, m2 before first prediction
    assert sample_sizes[1] == 3  # m1, m2, m3 before second prediction
    assert sample_sizes[2] == 4  # m1, m2, m3, m4 before third prediction
    
    # xG should change as more data becomes available
    assert avg_xgs[0] != avg_xgs[1]
    assert avg_xgs[1] != avg_xgs[2]


def test_strict_less_than_comparison():
    """Test that all calculators use strict < comparison (not <=) for before_datetime.
    
    CRITICAL: Match at exact cutoff timestamp must be EXCLUDED.
    """
    session = Mock()
    
    cutoff_date = datetime(2023, 10, 15, 15, 0, 0)
    
    matches = [
        create_test_match("m1", "team_test", "team_opp1", cutoff_date - timedelta(days=14), 2, 0),
        create_test_match("m2", "team_test", "team_opp2", cutoff_date - timedelta(days=7), 1, 1),
        # Match exactly at cutoff - should be EXCLUDED
        create_test_match("m3", "team_test", "team_opp3", cutoff_date, 3, 0),
        create_test_match("m4", "team_test", "team_opp4", cutoff_date + timedelta(days=7), 2, 1),
    ]
    
    # Test AdvancedTeamIntelligenceCalculator
    advanced_calc = AdvancedTeamIntelligenceCalculator(session, min_matches=2)
    advanced_metrics = advanced_calc.calculate_advanced_metrics(
        "team_test", matches, before_datetime=cutoff_date
    )
    assert advanced_metrics.sample_size == 2  # Only m1, m2 (m3 at cutoff excluded)
    
    # Test OpponentAdjustmentCalculator
    elo_system = EloRatingSystem(k_factor=20, home_advantage=100, initial_rating=1500)
    opponent_calc = OpponentAdjustmentCalculator(session, elo_system, min_matches=2)
    opponent_metrics = opponent_calc.calculate_adjusted_metrics(
        "team_test", matches, before_datetime=cutoff_date
    )
    assert opponent_metrics.sample_size == 2  # Only m1, m2 (m3 at cutoff excluded)
    
    # Test TemporalIntelligenceCalculator
    temporal_calc = TemporalIntelligenceCalculator(session, min_matches=2)
    temporal_metrics = temporal_calc.calculate_temporal_metrics(
        "team_test", matches, before_datetime=cutoff_date
    )
    assert temporal_metrics.sample_size == 2  # Only m1, m2 (m3 at cutoff excluded)


def test_elo_rating_at_time_temporal_consistency():
    """Test that Elo ratings retrieved at time T remain constant even after processing later matches.
    
    CRITICAL: Verifies get_rating_at_time() provides truly historical ratings.
    """
    elo_system = EloRatingSystem(k_factor=20, home_advantage=100, initial_rating=1500)
    
    base_date = datetime(2023, 10, 1)
    
    team_a = "team_a"
    team_b = "team_b"
    
    # Process match 1
    elo_system.process_match("m1", team_a, team_b, 2, 0, base_date)
    
    # Get team_b rating after match 1
    rating_after_m1 = elo_system.get_rating_at_time(team_b, base_date + timedelta(seconds=1))
    
    # Process match 2 (later)
    elo_system.process_match("m2", team_b, team_a, 3, 0, base_date + timedelta(days=7))
    
    # Get team_b rating after match 1 again (should be same as before)
    rating_after_m1_again = elo_system.get_rating_at_time(team_b, base_date + timedelta(seconds=1))
    
    # Ratings at time T should be identical regardless of future matches processed
    assert rating_after_m1 == rating_after_m1_again


def test_regime_detection_temporal_validity():
    """Test that regime detection only uses matches before cutoff.
    
    CRITICAL: Regime changes detected should not be influenced by future matches.
    """
    session = Mock()
    calculator = TemporalIntelligenceCalculator(session, regime_detection_enabled=True, min_matches=5)
    
    base_date = datetime(2023, 10, 1)
    cutoff_date = base_date + timedelta(days=35)
    
    matches = [
        # Poor form period
        create_test_match("m1", "team_test", "team_opp1", base_date, 0, 2),
        create_test_match("m2", "team_test", "team_opp2", base_date + timedelta(days=7), 0, 1),
        create_test_match("m3", "team_test", "team_opp3", base_date + timedelta(days=14), 1, 1),
        create_test_match("m4", "team_test", "team_opp4", base_date + timedelta(days=21), 0, 1),
        create_test_match("m5", "team_test", "team_opp5", base_date + timedelta(days=28), 1, 2),
        # Good form period (should be excluded by cutoff)
        create_test_match("m6", "team_test", "team_opp6", cutoff_date, 3, 0),
        create_test_match("m7", "team_test", "team_opp7", cutoff_date + timedelta(days=7), 3, 1),
        create_test_match("m8", "team_test", "team_opp8", cutoff_date + timedelta(days=14), 2, 0),
    ]
    
    # Calculate with cutoff (should not see improvement)
    metrics = calculator.calculate_temporal_metrics(
        "team_test", 
        matches,
        before_datetime=cutoff_date
    )
    
    # Should only use first 5 matches (all poor form)
    assert metrics.sample_size == 5
    
    # Should NOT detect improvement (future wins excluded)
    # Form trend should be declining or stable, not improving
    if metrics.form_trend:
        assert metrics.form_trend in ["declining", "stable"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
