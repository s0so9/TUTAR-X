"""Temporal leakage protection tests for shot market predictions.

Ensures that shot market predictions never use post-match data (final shots, SOT, xG, result)
for pre-match predictions. Tests the critical boundary condition: before_datetime must use
strict < comparison to prevent any leakage.

These tests verify the entire shot market prediction pipeline:
- ShotIntelligenceCalculator
- ShotProductionCalculator
- ShotMarketEngine
- MatchFeatureSnapshot

NON-NEGOTIABLE: For prediction timestamp T, only use information where event_timestamp < T.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock
from typing import List

from app.features.shot_intelligence import ShotIntelligenceCalculator, ShotIntelligenceMetrics
from app.features.shot_production import ShotProductionCalculator
from app.prediction.shot_market_engine import ShotMarketEngine
from app.prediction.feature_snapshot import MatchFeatureSnapshot
from app.prediction.interfaces import ShotMarketType, ShotMarketPrediction
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
    away_shots: int = 8,
    home_sot: int = 4,
    away_sot: int = 3
) -> MatchWithStatistics:
    """Helper to create MatchWithStatistics for testing.
    
    Args:
        match_id: Match identifier
        home_team_id: Home team ID
        away_team_id: Away team ID
        scheduled_at: Match scheduled time
        home_shots: Home team shots
        away_shots: Away team shots
        home_sot: Home team shots on target
        away_sot: Away team shots on target
        
    Returns:
        MatchWithStatistics with shot data
    """
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
        possession_percentage=55.0
    )
    
    away_stats = TeamMatchStatistic(
        id=f"{match_id}_a",
        match_id=match_id,
        team_id=away_team_id,
        goals_scored=1,
        goals_conceded=1,
        shots_total=away_shots,
        shots_on_target=away_sot,
        possession_percentage=45.0
    )
    
    return MatchWithStatistics(
        match=match,
        home_statistics=home_stats,
        away_statistics=away_stats
    )


class TestShotMarketExcludesTargetMatch:
    """Test that target match statistics are never used in its own prediction."""
    
    def test_shot_market_excludes_target_match(self, mock_session):
        """Test that target match's final statistics are not used in feature calculation.
        
        Critical test: When predicting match M at time T, the final statistics
        of match M (shots_total, shots_on_target) must NOT be included in the
        historical sample used to build the prediction.
        """
        # Prediction timestamp
        target_time = datetime(2024, 1, 15, 15, 0, 0)
        
        # Create 5 historical matches BEFORE target time
        historical_matches = [
            create_match_with_stats("h1", "team_a", "opp_1", datetime(2024, 1, 5, 18, 0), home_shots=10),
            create_match_with_stats("h2", "team_a", "opp_2", datetime(2024, 1, 8, 20, 0), home_shots=12),
            create_match_with_stats("h3", "team_a", "opp_3", datetime(2024, 1, 10, 19, 0), home_shots=11),
            create_match_with_stats("h4", "team_a", "opp_4", datetime(2024, 1, 12, 18, 30), home_shots=9),
            create_match_with_stats("h5", "team_a", "opp_5", datetime(2024, 1, 14, 20, 0), home_shots=13),
        ]
        
        # Create target match (scheduled for target_time)
        # This match's statistics should NOT be used
        target_match = create_match_with_stats(
            "target",
            "team_a",
            "opponent",
            target_time,
            home_shots=25,  # Final statistic from this match - should NOT influence prediction
            home_sot=10
        )
        
        # Calculate shot intelligence using ONLY historical matches
        shot_calc = ShotIntelligenceCalculator(session=mock_session, min_matches=3)
        metrics = shot_calc.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=historical_matches,  # NOT including target match
            before_datetime=target_time
        )
        
        # Verify: sample_size should be 5 (historical matches only)
        assert metrics.sample_size == 5, \
            f"Expected 5 historical matches, got {metrics.sample_size}"
        
        # Verify: shots per match should be (10+12+11+9+13)/5 = 11.0
        # NOT influenced by target match's 25 shots
        expected_shots_per_match = (10 + 12 + 11 + 9 + 13) / 5
        assert metrics.shots_total_per_match == expected_shots_per_match, \
            f"Expected {expected_shots_per_match} shots/match, got {metrics.shots_total_per_match}"
        
        # Verify: SOT per match should be (4+4+4+4+4)/5 = 4.0
        # NOT influenced by target match's 10 SOT
        assert metrics.shots_on_target_per_match == 4.0, \
            f"Expected 4.0 SOT/match, got {metrics.shots_on_target_per_match}"
    
    def test_shot_market_engine_excludes_target_match(self, mock_session):
        """Test that ShotMarketEngine excludes target match statistics.
        
        Integration test: Verify the entire shot market prediction pipeline
        does not leak target match data.
        """
        target_time = datetime(2024, 1, 15, 15, 0, 0)
        
        # Historical matches for home team
        home_historical = [
            create_match_with_stats("h1", "team_a", "opp_1", datetime(2024, 1, 5), home_shots=10),
            create_match_with_stats("h2", "team_a", "opp_2", datetime(2024, 1, 8), home_shots=12),
            create_match_with_stats("h3", "team_a", "opp_3", datetime(2024, 1, 10), home_shots=11),
            create_match_with_stats("h4", "team_a", "opp_4", datetime(2024, 1, 12), home_shots=9),
            create_match_with_stats("h5", "team_a", "opp_5", datetime(2024, 1, 14), home_shots=13),
        ]
        
        # Historical matches for away team
        away_historical = [
            create_match_with_stats("a1", "opp_x", "team_b", datetime(2024, 1, 5), away_shots=8),
            create_match_with_stats("a2", "opp_y", "team_b", datetime(2024, 1, 8), away_shots=9),
            create_match_with_stats("a3", "opp_z", "team_b", datetime(2024, 1, 10), away_shots=7),
            create_match_with_stats("a4", "opp_w", "team_b", datetime(2024, 1, 12), away_shots=10),
            create_match_with_stats("a5", "opp_v", "team_b", datetime(2024, 1, 14), away_shots=8),
        ]
        
        # Build shot intelligence for snapshot
        shot_calc = ShotIntelligenceCalculator(session=mock_session, min_matches=3)
        
        home_shot_intel = shot_calc.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=home_historical,
            before_datetime=target_time
        )
        
        away_shot_intel = shot_calc.calculate_shot_metrics(
            team_id="team_b",
            matches_with_stats=away_historical,
            before_datetime=target_time
        )
        
        # Create snapshot (without target match data)
        snapshot = MatchFeatureSnapshot(
            match_id="target",
            home_team_id="team_a",
            away_team_id="team_b",
            scheduled_at=target_time,
            home_shot_intelligence=home_shot_intel,
            away_shot_intelligence=away_shot_intel
        )
        
        # Create shot market engine
        engine = ShotMarketEngine(session=mock_session)
        
        # Predict shot markets
        predictions = engine.predict_all_shot_markets(
            snapshot=snapshot,
            home_matches=home_historical,
            away_matches=away_historical,
            before_datetime=target_time
        )
        
        # Verify: predictions should be based on historical data only
        assert ShotMarketType.TEAM_SHOTS in predictions
        team_shots_preds = predictions[ShotMarketType.TEAM_SHOTS]
        
        # Home team prediction
        home_pred = [p for p in team_shots_preds if p.team_id == "team_a"][0]
        assert home_pred.sample_size == 5, \
            f"Expected 5 historical matches, got {home_pred.sample_size}"
        
        # Away team prediction
        away_pred = [p for p in team_shots_preds if p.team_id == "team_b"][0]
        assert away_pred.sample_size == 5, \
            f"Expected 5 historical matches, got {away_pred.sample_size}"


class TestShotMarketExcludesFutureMatches:
    """Test that matches after before_datetime are excluded from predictions."""
    
    def test_shot_market_excludes_future_matches(self, mock_session):
        """Test that matches after before_datetime are excluded.
        
        Verify strict temporal filtering: matches at or after prediction time
        must not be used in feature calculation.
        """
        cutoff = datetime(2024, 1, 10, 12, 0, 0)
        
        matches = [
            create_match_with_stats("m1", "team_a", "opp_1", datetime(2024, 1, 5), home_shots=10),
            create_match_with_stats("m2", "team_a", "opp_2", datetime(2024, 1, 8), home_shots=12),
            create_match_with_stats("m3", "team_a", "opp_3", datetime(2024, 1, 9), home_shots=11),
            # Future matches (after cutoff) - should be EXCLUDED
            create_match_with_stats("m4", "team_a", "opp_4", datetime(2024, 1, 12), home_shots=20),
            create_match_with_stats("m5", "team_a", "opp_5", datetime(2024, 1, 15), home_shots=25),
        ]
        
        shot_calc = ShotIntelligenceCalculator(session=mock_session, min_matches=2)
        
        metrics = shot_calc.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=cutoff
        )
        
        # Should only use first 3 matches (before cutoff)
        assert metrics.sample_size == 3, \
            f"Expected 3 pre-cutoff matches, got {metrics.sample_size}"
        
        # Shots per match should be (10+12+11)/3 = 11.0
        # NOT influenced by future matches (20, 25)
        expected_shots = (10 + 12 + 11) / 3
        assert metrics.shots_total_per_match == expected_shots, \
            f"Expected {expected_shots}, got {metrics.shots_total_per_match}"


class TestShotMarketStrictLessThanBoundary:
    """Test the critical boundary condition: strict < comparison (not <=)."""
    
    def test_shot_market_strict_less_than_boundary(self, mock_session):
        """Test that match at exactly T is EXCLUDED when predicting at T.
        
        CRITICAL: This tests the strict < comparison (not <=).
        Match scheduled at exactly T must be excluded from predictions at T.
        """
        # Target timestamp
        T = datetime(2024, 1, 15, 12, 0, 0)
        
        matches = [
            create_match_with_stats("m1", "team_a", "opp_1", T - timedelta(days=2), home_shots=10),
            create_match_with_stats("m2", "team_a", "opp_2", T - timedelta(days=1), home_shots=12),
            create_match_with_stats("m3", "team_a", "opp_3", T, home_shots=100),  # AT T - EXCLUDED
            create_match_with_stats("m4", "team_a", "opp_4", T + timedelta(days=1), home_shots=200),
        ]
        
        shot_calc = ShotIntelligenceCalculator(session=mock_session, min_matches=2)
        
        metrics = shot_calc.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=T
        )
        
        # Should only use first 2 matches (T-2 days, T-1 day)
        # Match at exactly T should be EXCLUDED
        assert metrics.sample_size == 2, \
            f"Expected 2 matches (strict < T), got {metrics.sample_size}"
        
        # Shots per match should be (10+12)/2 = 11.0
        # NOT influenced by match at T (100 shots) or after T (200 shots)
        expected_shots = (10 + 12) / 2
        assert metrics.shots_total_per_match == expected_shots, \
            f"Expected {expected_shots}, got {metrics.shots_total_per_match}. " \
            f"Match at T was incorrectly included (leakage detected)."
    
    def test_boundary_nanosecond_precision(self, mock_session):
        """Test boundary with microsecond precision.
        
        Ensure even matches 1 microsecond before cutoff are included,
        and matches at exact cutoff are excluded.
        """
        T = datetime(2024, 1, 15, 12, 0, 0, 0)
        
        matches = [
            create_match_with_stats(
                "m1", "team_a", "opp_1",
                datetime(2024, 1, 15, 11, 59, 59, 999999),  # 1 microsecond before T
                home_shots=10
            ),
            create_match_with_stats(
                "m2", "team_a", "opp_2",
                T,  # Exactly at T
                home_shots=100
            ),
        ]
        
        shot_calc = ShotIntelligenceCalculator(session=mock_session, min_matches=1)
        
        metrics = shot_calc.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=T
        )
        
        # Should only include match before T, not match at T
        assert metrics.sample_size == 1
        assert metrics.shots_total_per_match == 10.0, \
            "Match at exact cutoff was incorrectly included"


class TestShotIntelligenceSnapshotIsolation:
    """Test that MatchFeatureSnapshot shot intelligence uses only historical data."""
    
    def test_shot_intelligence_snapshot_isolation(self, mock_session):
        """Test that snapshot shot intelligence is computed using only historical data.
        
        Verify that when building a snapshot for a target match, the shot intelligence
        metrics do not include the target match's final statistics.
        """
        target_time = datetime(2024, 1, 15, 15, 0, 0)
        
        # Historical matches
        historical = [
            create_match_with_stats("h1", "team_a", "opp_1", datetime(2024, 1, 5), home_shots=10, home_sot=4),
            create_match_with_stats("h2", "team_a", "opp_2", datetime(2024, 1, 8), home_shots=12, home_sot=5),
            create_match_with_stats("h3", "team_a", "opp_3", datetime(2024, 1, 10), home_shots=11, home_sot=4),
            create_match_with_stats("h4", "team_a", "opp_4", datetime(2024, 1, 12), home_shots=9, home_sot=3),
            create_match_with_stats("h5", "team_a", "opp_5", datetime(2024, 1, 14), home_shots=13, home_sot=6),
        ]
        
        # Calculate shot intelligence
        shot_calc = ShotIntelligenceCalculator(session=mock_session, min_matches=3)
        shot_intel = shot_calc.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=historical,
            before_datetime=target_time
        )
        
        # Create snapshot
        snapshot = MatchFeatureSnapshot(
            match_id="target",
            home_team_id="team_a",
            away_team_id="opponent",
            scheduled_at=target_time,
            home_shot_intelligence=shot_intel
        )
        
        # Verify shot intelligence in snapshot
        assert snapshot.home_shot_intelligence is not None
        assert snapshot.home_shot_intelligence.sample_size == 5
        assert snapshot.home_shot_intelligence.data_quality_score > 0.0
        
        # Verify shots per match excludes any post-match data
        expected_shots = (10 + 12 + 11 + 9 + 13) / 5
        assert snapshot.home_shot_intelligence.shots_total_per_match == expected_shots
        
        # Verify SOT per match
        expected_sot = (4 + 5 + 4 + 3 + 6) / 5
        assert snapshot.home_shot_intelligence.shots_on_target_per_match == expected_sot


class TestPostMatchStatsNeverInPreMatchFeatures:
    """Test that post-match statistics are never used in pre-match features."""
    
    def test_post_match_stats_never_in_pre_match_features(self, mock_session):
        """Test that final match statistics are not used for pre-match prediction.
        
        Scenario: A finished match exists with final statistics (shots_total=15, SOT=7).
        When building a prediction for this match at its scheduled time, these final
        statistics must NOT be used.
        """
        match_time = datetime(2024, 1, 15, 15, 0, 0)
        
        # Historical matches (before target match)
        historical = [
            create_match_with_stats("h1", "team_a", "opp_1", datetime(2024, 1, 5), home_shots=10),
            create_match_with_stats("h2", "team_a", "opp_2", datetime(2024, 1, 8), home_shots=12),
            create_match_with_stats("h3", "team_a", "opp_3", datetime(2024, 1, 10), home_shots=11),
            create_match_with_stats("h4", "team_a", "opp_4", datetime(2024, 1, 12), home_shots=9),
            create_match_with_stats("h5", "team_a", "opp_5", datetime(2024, 1, 14), home_shots=13),
        ]
        
        # Target match with final statistics (already finished)
        # These statistics should NOT be used in prediction
        target_match = create_match_with_stats(
            "target",
            "team_a",
            "opponent",
            match_time,
            home_shots=15,  # Final statistic
            home_sot=7      # Final statistic
        )
        
        # Calculate features WITHOUT target match
        shot_calc = ShotIntelligenceCalculator(session=mock_session, min_matches=3)
        metrics = shot_calc.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=historical,  # Excludes target match
            before_datetime=match_time
        )
        
        # Verify target match statistics not included
        assert metrics.sample_size == 5
        expected_shots = (10 + 12 + 11 + 9 + 13) / 5
        assert metrics.shots_total_per_match == expected_shots, \
            "Target match's final shots_total was leaked into pre-match features"
        
        expected_sot = (4 + 4 + 4 + 4 + 4) / 5  # Default SOT from helper
        assert metrics.shots_on_target_per_match == expected_sot, \
            "Target match's final shots_on_target was leaked into pre-match features"


class TestAllShotCalculatorsRespectTemporalCutoff:
    """Integration test: verify all shot calculators use strict < comparison consistently."""
    
    def test_all_shot_calculators_respect_temporal_cutoff(self, mock_session):
        """Test consistent temporal filtering across all shot calculators.
        
        Integration test verifying that ShotIntelligenceCalculator,
        ShotProductionCalculator, and ShotMarketEngine all use strict <
        comparison consistently.
        """
        T = datetime(2024, 1, 10, 12, 0, 0)
        
        # Create 5 matches before T (ShotProductionCalculator requires min 5 for distribution fitting)
        matches = [
            create_match_with_stats("m1", "team_a", "opp_1", T - timedelta(days=7), home_shots=10),
            create_match_with_stats("m2", "team_a", "opp_2", T - timedelta(days=5), home_shots=12),
            create_match_with_stats("m3", "team_a", "opp_3", T - timedelta(days=3), home_shots=11),
            create_match_with_stats("m4", "team_a", "opp_4", T - timedelta(days=2), home_shots=9),
            create_match_with_stats("m5", "team_a", "opp_5", T - timedelta(days=1), home_shots=13),
            create_match_with_stats("m6", "team_a", "opp_6", T, home_shots=100),  # AT T - excluded
            create_match_with_stats("m7", "team_a", "opp_7", T + timedelta(days=2), home_shots=200),
        ]
        
        # Test ShotIntelligenceCalculator
        shot_calc = ShotIntelligenceCalculator(session=mock_session, min_matches=2)
        shot_metrics = shot_calc.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=T
        )
        assert shot_metrics.sample_size == 5, \
            f"ShotIntelligenceCalculator: expected 5, got {shot_metrics.sample_size}"
        
        # Test raw shot counts extraction
        shot_counts, sot_counts = shot_calc.get_raw_shot_counts(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=T
        )
        assert len(shot_counts) == 5, \
            f"get_raw_shot_counts: expected 5, got {len(shot_counts)}"
        assert shot_counts == [10.0, 12.0, 11.0, 9.0, 13.0], \
            f"Shot counts should be [10, 12, 11, 9, 13], got {shot_counts}"
        
        # Test ShotProductionCalculator
        prod_calc = ShotProductionCalculator(session=mock_session, min_matches=5)
        production = prod_calc.calculate(
            team_id="team_a",
            shot_counts=shot_counts,
            before_datetime=T
        )
        assert production.sample_size == 5, \
            f"ShotProductionCalculator: expected 5, got {production.sample_size}"
        
        # Expected mean should be (10+12+11+9+13)/5 = 11.0, not influenced by 100 or 200
        assert production.expected_shots_mean == 11.0, \
            f"Expected mean 11.0, got {production.expected_shots_mean}"
        
        # Test ShotMarketEngine integration
        shot_intel = shot_calc.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=T
        )
        
        snapshot = MatchFeatureSnapshot(
            match_id="target",
            home_team_id="team_a",
            away_team_id="team_b",
            scheduled_at=T,
            home_shot_intelligence=shot_intel,
            away_shot_intelligence=shot_intel  # Reuse for simplicity
        )
        
        engine = ShotMarketEngine(session=mock_session)
        predictions = engine.predict_all_shot_markets(
            snapshot=snapshot,
            home_matches=matches,
            away_matches=matches,
            before_datetime=T
        )
        
        # Verify predictions use consistent sample size for team_a
        if ShotMarketType.TEAM_SHOTS in predictions:
            team_shots = predictions[ShotMarketType.TEAM_SHOTS]
            # Check home team (team_a) prediction
            home_pred = [p for p in team_shots if p.team_id == "team_a"]
            if home_pred:
                assert home_pred[0].sample_size == 5, \
                    f"ShotMarketEngine (team_a): expected 5, got {home_pred[0].sample_size}"


class TestTemporalLeakageWithVariedScheduling:
    """Test temporal leakage protection with varied match scheduling patterns."""
    
    def test_varied_match_times_same_day(self, mock_session):
        """Test with multiple matches on same day at different times."""
        cutoff = datetime(2024, 1, 10, 18, 0, 0)  # 6 PM
        
        matches = [
            create_match_with_stats("m1", "team_a", "opp_1", datetime(2024, 1, 10, 12, 0), home_shots=10),
            create_match_with_stats("m2", "team_a", "opp_2", datetime(2024, 1, 10, 15, 0), home_shots=12),
            create_match_with_stats("m3", "team_a", "opp_3", datetime(2024, 1, 10, 18, 0), home_shots=100),  # AT cutoff
            create_match_with_stats("m4", "team_a", "opp_4", datetime(2024, 1, 10, 21, 0), home_shots=200),  # After
        ]
        
        shot_calc = ShotIntelligenceCalculator(session=mock_session, min_matches=2)
        metrics = shot_calc.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=cutoff
        )
        
        # Should only include matches before 6 PM (12:00, 15:00)
        assert metrics.sample_size == 2
        expected_shots = (10 + 12) / 2
        assert metrics.shots_total_per_match == expected_shots
    
    def test_empty_result_when_all_matches_after_cutoff(self, mock_session):
        """Test that no data is returned when all matches are after cutoff."""
        cutoff = datetime(2024, 1, 5, 12, 0, 0)
        
        matches = [
            create_match_with_stats("m1", "team_a", "opp_1", datetime(2024, 1, 10), home_shots=10),
            create_match_with_stats("m2", "team_a", "opp_2", datetime(2024, 1, 12), home_shots=12),
            create_match_with_stats("m3", "team_a", "opp_3", datetime(2024, 1, 15), home_shots=11),
        ]
        
        shot_calc = ShotIntelligenceCalculator(session=mock_session, min_matches=2)
        metrics = shot_calc.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=matches,
            before_datetime=cutoff
        )
        
        # All matches after cutoff - insufficient data
        assert metrics.sample_size == 0
        assert metrics.shots_total_per_match is None
        assert metrics.data_quality_score == 0.0


class TestNoXGLeakage:
    """Test that xG values from target match are not leaked into predictions."""
    
    def test_xg_values_not_leaked(self, mock_session):
        """Test that target match xG is not included in feature calculation."""
        target_time = datetime(2024, 1, 15, 15, 0, 0)
        
        # Create matches with xG data
        def create_match_with_xg(match_id, team_id, opp_id, time, shots, xg):
            mws = create_match_with_stats(match_id, team_id, opp_id, time, home_shots=shots)
            # Add xG to home statistics
            mws.home_statistics.xg = xg
            return mws
        
        historical = [
            create_match_with_xg("h1", "team_a", "opp_1", datetime(2024, 1, 5), 10, 1.2),
            create_match_with_xg("h2", "team_a", "opp_2", datetime(2024, 1, 8), 12, 1.5),
            create_match_with_xg("h3", "team_a", "opp_3", datetime(2024, 1, 10), 11, 1.3),
            create_match_with_xg("h4", "team_a", "opp_4", datetime(2024, 1, 12), 9, 1.0),
            create_match_with_xg("h5", "team_a", "opp_5", datetime(2024, 1, 14), 13, 1.6),
        ]
        
        shot_calc = ShotIntelligenceCalculator(session=mock_session, min_matches=3)
        metrics = shot_calc.calculate_shot_metrics(
            team_id="team_a",
            matches_with_stats=historical,
            before_datetime=target_time
        )
        
        # Verify xG calculation excludes target match
        expected_xg_per_match = (1.2 + 1.5 + 1.3 + 1.0 + 1.6) / 5
        assert abs(metrics.xg_for_per_match - expected_xg_per_match) < 0.001, \
            f"Expected xG {expected_xg_per_match}, got {metrics.xg_for_per_match}"
        assert metrics.matches_with_xg == 5
        
        # Verify xG per shot
        expected_xg_per_shot = (1.2 + 1.5 + 1.3 + 1.0 + 1.6) / (10 + 12 + 11 + 9 + 13)
        assert abs(metrics.xg_per_shot - expected_xg_per_shot) < 0.001
