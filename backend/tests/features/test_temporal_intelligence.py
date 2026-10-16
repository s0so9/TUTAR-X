"""Tests for temporal intelligence feature calculations.

Tests:
- Temporal weighting structure
- Regime change structure and detection
- Exponential weighting calculation
- Statistical regime detection
- Manager change UNAVAILABLE (detected_by never 'external_data')
- Form trend detection (improving/declining/stable)
- Temporal validity enforcement
- Post-regime form calculation
- Insufficient matches handling
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock

from app.features.temporal_intelligence import (
    TemporalWeighting,
    RegimeChange,
    TemporalIntelligenceMetrics,
    TemporalIntelligenceCalculator,
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
    away_xg: float = None
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
        shots_total=10,
    )
    
    away_stats = TeamMatchStatistic(
        id=f"{match_id}_away",
        match_id=match_id,
        team_id=away_team_id,
        xg=away_xg,
        xg_against=home_xg,
        shots_total=8,
    )
    
    return MatchWithStatistics(
        match=match,
        home_statistics=home_stats,
        away_statistics=away_stats,
    )


def test_temporal_weighting_structure():
    """Test TemporalWeighting dataclass structure."""
    weighting = TemporalWeighting(method="exponential", decay_factor=0.95)
    
    assert weighting.method == "exponential"
    assert weighting.decay_factor == 0.95
    assert weighting.halflife_matches is None


def test_temporal_weighting_halflife_calculation():
    """Test decay_factor calculation from halflife."""
    weighting = TemporalWeighting(method="exponential", halflife_matches=5)
    
    # decay_factor should be calculated as 0.5^(1/5)
    expected_decay = 0.5 ** (1.0 / 5.0)
    assert abs(weighting.decay_factor - expected_decay) < 0.001


def test_regime_change_structure():
    """Test RegimeChange dataclass structure."""
    regime_change = RegimeChange(
        event_type="statistical_shift",
        event_date=datetime(2023, 10, 1),
        detected_by="statistical",
        confidence=0.75,
        description="Performance decline detected"
    )
    
    assert regime_change.event_type == "statistical_shift"
    assert regime_change.detected_by == "statistical"
    assert regime_change.confidence == 0.75
    assert not regime_change.is_verified_external()


def test_regime_change_is_verified_external():
    """Test is_verified_external method."""
    # Statistical detection - not verified external
    statistical = RegimeChange(
        event_type="statistical_shift",
        event_date=datetime.now(),
        detected_by="statistical",
        confidence=0.7
    )
    assert not statistical.is_verified_external()
    
    # External data (future) - verified external
    external = RegimeChange(
        event_type="manager_change",
        event_date=datetime.now(),
        detected_by="external_data",
        confidence=0.95
    )
    assert external.is_verified_external()
    
    # Manual (future) - verified external
    manual = RegimeChange(
        event_type="tactical_shift",
        event_date=datetime.now(),
        detected_by="manual",
        confidence=0.90
    )
    assert manual.is_verified_external()


def test_temporal_intelligence_metrics_structure():
    """Test TemporalIntelligenceMetrics dataclass structure."""
    metrics = TemporalIntelligenceMetrics(
        team_id="team_test",
        recent_form_weighted=1.8,
        recent_xg_weighted=1.5,
        form_trend="improving",
        form_acceleration=0.15,
        sample_size=10
    )
    
    assert metrics.team_id == "team_test"
    assert metrics.recent_form_weighted == 1.8
    assert metrics.form_trend == "improving"
    assert metrics.sample_size == 10


def test_exponential_weighting_calculation():
    """Test exponential weighting calculation."""
    session = Mock()
    calculator = TemporalIntelligenceCalculator(
        session,
        weighting=TemporalWeighting(method="exponential", decay_factor=0.9)
    )
    
    # Create matches with varying results (chronologically ordered)
    base_date = datetime(2023, 10, 1)
    matches = [
        # Oldest matches (losses)
        create_test_match("m1", "team_test", "team_opp1", base_date, 0, 2, 0.8, 2.1),
        create_test_match("m2", "team_test", "team_opp2", base_date + timedelta(days=7), 0, 1, 1.0, 1.5),
        # Middle matches (draws)
        create_test_match("m3", "team_test", "team_opp3", base_date + timedelta(days=14), 1, 1, 1.3, 1.2),
        create_test_match("m4", "team_test", "team_opp4", base_date + timedelta(days=21), 2, 2, 1.8, 1.7),
        # Recent matches (wins)
        create_test_match("m5", "team_test", "team_opp5", base_date + timedelta(days=28), 3, 1, 2.3, 1.0),
        create_test_match("m6", "team_test", "team_opp6", base_date + timedelta(days=35), 2, 0, 2.0, 0.8),
    ]
    
    metrics = calculator.calculate_temporal_metrics("team_test", matches)
    
    # Verify metrics calculated
    assert metrics.recent_form_weighted is not None
    assert metrics.recent_xg_weighted is not None
    
    # Recent wins should be weighted more heavily
    # Expected: weighted average should be > unweighted average
    # Unweighted: (0 + 0 + 1 + 1 + 3 + 3) / 6 = 1.33 points/match
    # Weighted should be higher due to recent wins
    assert metrics.recent_form_weighted > 1.5
    
    # Recent xG should also be higher
    assert metrics.recent_xg_weighted > 1.5


def test_statistical_regime_detection():
    """Test statistical regime-change detection."""
    session = Mock()
    calculator = TemporalIntelligenceCalculator(
        session,
        regime_detection_enabled=True
    )
    
    # Create matches with clear performance shift
    base_date = datetime(2023, 10, 1)
    matches = [
        # Poor form period (5 matches - losses/draws)
        create_test_match("m1", "team_test", "team_opp1", base_date, 0, 2),
        create_test_match("m2", "team_test", "team_opp2", base_date + timedelta(days=7), 1, 1),
        create_test_match("m3", "team_test", "team_opp3", base_date + timedelta(days=14), 0, 1),
        create_test_match("m4", "team_test", "team_opp4", base_date + timedelta(days=21), 1, 2),
        create_test_match("m5", "team_test", "team_opp5", base_date + timedelta(days=28), 0, 0),
        # Good form period (5 matches - wins)
        create_test_match("m6", "team_test", "team_opp6", base_date + timedelta(days=35), 3, 0),
        create_test_match("m7", "team_test", "team_opp7", base_date + timedelta(days=42), 2, 1),
        create_test_match("m8", "team_test", "team_opp8", base_date + timedelta(days=49), 3, 1),
        create_test_match("m9", "team_test", "team_opp9", base_date + timedelta(days=56), 2, 0),
        create_test_match("m10", "team_test", "team_opp10", base_date + timedelta(days=63), 3, 0),
    ]
    
    metrics = calculator.calculate_temporal_metrics("team_test", matches)
    
    # Should detect regime change
    assert len(metrics.recent_regime_changes) > 0
    
    # Verify regime change properties
    regime_change = metrics.recent_regime_changes[0]
    assert regime_change.detected_by == "statistical"
    assert regime_change.event_type == "statistical_shift"
    assert regime_change.confidence > 0.5
    assert "improvement" in regime_change.description.lower()


def test_manager_change_unavailable():
    """Test that detected_by is never 'external_data' in current implementation.
    
    CRITICAL: Manager/coach change data UNAVAILABLE.
    """
    session = Mock()
    calculator = TemporalIntelligenceCalculator(session, regime_detection_enabled=True)
    
    # Create matches
    base_date = datetime(2023, 10, 1)
    matches = [
        create_test_match("m1", "team_test", "team_opp1", base_date + timedelta(days=i*7), 
                         1 if i < 5 else 3, 0)
        for i in range(10)
    ]
    
    metrics = calculator.calculate_temporal_metrics("team_test", matches)
    
    # Verify all detected regime changes are statistical
    for regime_change in metrics.recent_regime_changes:
        assert regime_change.detected_by == "statistical"
        assert not regime_change.is_verified_external()


def test_detected_by_field_always_statistical():
    """Test that RegimeChange.detected_by is always 'statistical' when auto-detected."""
    session = Mock()
    calculator = TemporalIntelligenceCalculator(session, regime_detection_enabled=True)
    
    base_date = datetime(2023, 10, 1)
    matches = [
        create_test_match("m1", "team_test", "team_opp1", base_date, 0, 2),
        create_test_match("m2", "team_test", "team_opp2", base_date + timedelta(days=7), 0, 1),
        create_test_match("m3", "team_test", "team_opp3", base_date + timedelta(days=14), 1, 1),
        create_test_match("m4", "team_test", "team_opp4", base_date + timedelta(days=21), 0, 1),
        create_test_match("m5", "team_test", "team_opp5", base_date + timedelta(days=28), 0, 0),
        create_test_match("m6", "team_test", "team_opp6", base_date + timedelta(days=35), 3, 0),
        create_test_match("m7", "team_test", "team_opp7", base_date + timedelta(days=42), 3, 1),
        create_test_match("m8", "team_test", "team_opp8", base_date + timedelta(days=49), 2, 0),
    ]
    
    detected = calculator.detect_regime_changes("team_test", matches)
    
    # All auto-detected changes must be statistical
    for change in detected:
        assert change.detected_by == "statistical"
        assert change.event_type == "statistical_shift"


def test_form_trend_detection():
    """Test form trend classification (improving/declining/stable)."""
    session = Mock()
    calculator = TemporalIntelligenceCalculator(session)
    
    # Test improving form
    base_date = datetime(2023, 10, 1)
    improving_matches = [
        create_test_match("m1", "team_test", "team_opp1", base_date + timedelta(days=i*7), 
                         min(i, 3), 0)  # Scores improve: 0, 1, 2, 3, 3, 3
        for i in range(6)
    ]
    
    metrics = calculator.calculate_temporal_metrics("team_test", improving_matches)
    assert metrics.form_trend == "improving"
    assert metrics.form_acceleration is not None
    assert metrics.form_acceleration > 0
    
    # Test declining form
    declining_matches = [
        create_test_match("m1", "team_test", "team_opp1", base_date + timedelta(days=i*7), 
                         max(3 - i, 0), 1)  # Scores decline: 3, 2, 1, 0, 0, 0
        for i in range(6)
    ]
    
    metrics = calculator.calculate_temporal_metrics("team_test", declining_matches)
    assert metrics.form_trend == "declining"
    assert metrics.form_acceleration < 0
    
    # Test stable form
    stable_matches = [
        create_test_match("m1", "team_test", "team_opp1", base_date + timedelta(days=i*7), 
                         1, 1)  # All draws
        for i in range(6)
    ]
    
    metrics = calculator.calculate_temporal_metrics("team_test", stable_matches)
    assert metrics.form_trend == "stable"
    assert abs(metrics.form_acceleration) < 0.1


def test_temporal_validity():
    """Test temporal validity enforcement with before_datetime."""
    session = Mock()
    calculator = TemporalIntelligenceCalculator(session)
    
    base_date = datetime(2023, 10, 1)
    cutoff_date = base_date + timedelta(days=35)
    
    matches = [
        create_test_match("m1", "team_test", "team_opp1", base_date, 2, 0, 1.8, 0.9),
        create_test_match("m2", "team_test", "team_opp2", base_date + timedelta(days=7), 1, 1, 1.3, 1.2),
        create_test_match("m3", "team_test", "team_opp3", base_date + timedelta(days=14), 3, 0, 2.1, 0.8),
        create_test_match("m4", "team_test", "team_opp4", base_date + timedelta(days=21), 2, 1, 1.9, 1.4),
        create_test_match("m5", "team_test", "team_opp5", base_date + timedelta(days=28), 1, 2, 1.2, 1.8),
        # These should be excluded (at or after cutoff)
        create_test_match("m6", "team_test", "team_opp6", cutoff_date, 3, 0, 2.3, 0.7),
        create_test_match("m7", "team_test", "team_opp7", cutoff_date + timedelta(days=7), 2, 0, 2.0, 0.9),
    ]
    
    # Calculate with temporal cutoff
    metrics = calculator.calculate_temporal_metrics("team_test", matches, before_datetime=cutoff_date)
    
    # Should only use first 5 matches (before cutoff)
    assert metrics.sample_size == 5
    
    # Verify metrics exist
    assert metrics.recent_form_weighted is not None


def test_strict_less_than_comparison():
    """Test that before_datetime uses strict < comparison (not <=)."""
    session = Mock()
    calculator = TemporalIntelligenceCalculator(session)
    
    cutoff_date = datetime(2023, 10, 15, 15, 0, 0)
    
    matches = [
        create_test_match("m1", "team_test", "team_opp1", cutoff_date - timedelta(days=14), 2, 0),
        create_test_match("m2", "team_test", "team_opp2", cutoff_date - timedelta(days=7), 1, 1),
        # Match exactly at cutoff - should be EXCLUDED
        create_test_match("m3", "team_test", "team_opp3", cutoff_date, 3, 0),
        create_test_match("m4", "team_test", "team_opp4", cutoff_date + timedelta(days=7), 2, 1),
    ]
    
    metrics = calculator.calculate_temporal_metrics("team_test", matches, before_datetime=cutoff_date)
    
    # Should only include 2 matches (strictly before cutoff)
    assert metrics.sample_size == 2


def test_post_regime_form_calculation():
    """Test post-regime form calculation."""
    session = Mock()
    calculator = TemporalIntelligenceCalculator(session, regime_detection_enabled=True)
    
    base_date = datetime(2023, 10, 1)
    regime_date = base_date + timedelta(days=35)
    
    matches = [
        # Poor form before regime change
        create_test_match("m1", "team_test", "team_opp1", base_date, 0, 2),
        create_test_match("m2", "team_test", "team_opp2", base_date + timedelta(days=7), 1, 1),
        create_test_match("m3", "team_test", "team_opp3", base_date + timedelta(days=14), 0, 1),
        create_test_match("m4", "team_test", "team_opp4", base_date + timedelta(days=21), 0, 0),
        create_test_match("m5", "team_test", "team_opp5", base_date + timedelta(days=28), 1, 2),
        # Good form after regime change (at regime_date)
        create_test_match("m6", "team_test", "team_opp6", regime_date, 3, 0),
        create_test_match("m7", "team_test", "team_opp7", regime_date + timedelta(days=7), 2, 1),
        create_test_match("m8", "team_test", "team_opp8", regime_date + timedelta(days=14), 3, 1),
        create_test_match("m9", "team_test", "team_opp9", regime_date + timedelta(days=21), 2, 0),
    ]
    
    metrics = calculator.calculate_temporal_metrics("team_test", matches)
    
    # Should calculate post-regime form
    if len(metrics.recent_regime_changes) > 0:
        assert metrics.post_regime_form is not None
        # Post-regime form should be higher (wins vs losses before)
        assert metrics.post_regime_form > 2.0  # Average > 2 points/match


def test_insufficient_matches():
    """Test handling of insufficient match sample."""
    session = Mock()
    calculator = TemporalIntelligenceCalculator(session, min_matches=5)
    
    base_date = datetime(2023, 10, 1)
    matches = [
        create_test_match("m1", "team_test", "team_opp1", base_date, 2, 0),
        create_test_match("m2", "team_test", "team_opp2", base_date + timedelta(days=7), 1, 1),
        # Only 2 matches - insufficient
    ]
    
    metrics = calculator.calculate_temporal_metrics("team_test", matches)
    
    # Should return metrics with None values
    assert metrics.team_id == "team_test"
    assert metrics.sample_size == 2
    assert metrics.recent_form_weighted is None
    assert metrics.recent_xg_weighted is None
    assert metrics.form_trend is None


def test_regime_detection_disabled():
    """Test that regime detection can be disabled."""
    session = Mock()
    calculator = TemporalIntelligenceCalculator(
        session,
        regime_detection_enabled=False
    )
    
    base_date = datetime(2023, 10, 1)
    matches = [
        create_test_match("m1", "team_test", "team_opp1", base_date + timedelta(days=i*7), 
                         0 if i < 5 else 3, 0 if i >= 5 else 2)
        for i in range(10)
    ]
    
    metrics = calculator.calculate_temporal_metrics("team_test", matches)
    
    # Should not detect regime changes
    assert len(metrics.recent_regime_changes) == 0
    assert metrics.post_regime_form is None


def test_known_regime_changes_integration():
    """Test integration with known_regime_changes parameter (future capability)."""
    session = Mock()
    calculator = TemporalIntelligenceCalculator(session, regime_detection_enabled=False)
    
    base_date = datetime(2023, 10, 1)
    regime_date = base_date + timedelta(days=28)
    
    matches = [
        create_test_match("m1", "team_test", "team_opp1", base_date + timedelta(days=i*7), 
                         2, 1)
        for i in range(8)
    ]
    
    # Provide external regime change (future capability)
    known_change = RegimeChange(
        event_type="manager_change",
        event_date=regime_date,
        detected_by="external_data",
        confidence=0.95,
        description="New manager appointed"
    )
    
    metrics = calculator.calculate_temporal_metrics(
        "team_test", 
        matches,
        known_regime_changes=[known_change]
    )
    
    # Should include the known regime change
    assert len(metrics.recent_regime_changes) == 1
    assert metrics.recent_regime_changes[0].detected_by == "external_data"
    assert metrics.recent_regime_changes[0].is_verified_external()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
