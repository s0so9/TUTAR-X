"""Tests for Shot Market Engine.

Tests shot market prediction with statistical distributions, threshold probabilities,
and proper handling of insufficient data scenarios.
"""

import pytest
from datetime import datetime, timedelta
from typing import List

from app.prediction.shot_market_engine import ShotMarketEngine
from app.prediction.feature_snapshot import MatchFeatureSnapshot
from app.prediction.interfaces import (
    ShotMarketType,
    ShotMarketPrediction,
    DistributionType
)
from app.features.shot_intelligence import ShotIntelligenceMetrics
from app.features.advanced_team_intelligence import MatchWithStatistics
from app.domain.match import Match
from app.domain.statistics import TeamMatchStatistic
from app.domain.enums import MatchStatus


def create_mock_match_with_stats(
    match_id: str,
    home_team_id: str,
    away_team_id: str,
    home_shots: int,
    away_shots: int,
    home_sot: int,
    away_sot: int,
    scheduled_at: datetime
) -> MatchWithStatistics:
    """Create mock MatchWithStatistics for testing."""
    match = Match(
        id=match_id,
        competition_id="test_comp",
        season_id="test_season",
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        scheduled_at=scheduled_at,
        status=MatchStatus.FINISHED
    )
    
    home_stats = TeamMatchStatistic(
        id=f"{match_id}_home_stats",
        match_id=match_id,
        team_id=home_team_id,
        shots_total=home_shots,
        shots_on_target=home_sot,
        goals_scored=0,
    )
    
    away_stats = TeamMatchStatistic(
        id=f"{match_id}_away_stats",
        match_id=match_id,
        team_id=away_team_id,
        shots_total=away_shots,
        shots_on_target=away_sot,
        goals_scored=0,
    )
    
    return MatchWithStatistics(
        match=match,
        home_statistics=home_stats,
        away_statistics=away_stats
    )


def create_poisson_data(mean: float, count: int, base_date: datetime, team_id: str = "team_home") -> List[MatchWithStatistics]:
    """Create shot data that follows Poisson distribution (variance ≈ mean)."""
    matches = []
    # For Poisson-like data, variance should be close to mean
    # We'll create data with small variance
    for i in range(count):
        shots = max(1, int(mean + (i % 3 - 1)))  # Alternates: mean-1, mean, mean+1
        sot = int(shots * 0.4)
        
        # Alternate between home and away matches for the team
        if i % 2 == 0:
            home_team = team_id
            away_team = f"opponent_{i}"
            home_shots_val = shots
            away_shots_val = shots
            home_sot_val = sot
            away_sot_val = sot
        else:
            home_team = f"opponent_{i}"
            away_team = team_id
            home_shots_val = shots
            away_shots_val = shots
            home_sot_val = sot
            away_sot_val = sot
        
        matches.append(create_mock_match_with_stats(
            match_id=f"match_{team_id}_{i}",
            home_team_id=home_team,
            away_team_id=away_team,
            home_shots=home_shots_val,
            away_shots=away_shots_val,
            home_sot=home_sot_val,
            away_sot=away_sot_val,
            scheduled_at=base_date - timedelta(days=count-i)
        ))
    
    return matches


def create_overdispersed_data(mean: float, count: int, base_date: datetime, team_id: str = "team_home") -> List[MatchWithStatistics]:
    """Create shot data that is overdispersed (variance > mean) for Negative Binomial."""
    matches = []
    # For overdispersed data, create high variance
    for i in range(count):
        if i % 3 == 0:
            shots = int(mean + 8)  # High
        elif i % 3 == 1:
            shots = int(mean - 4)  # Low
        else:
            shots = int(mean)  # Mean
        
        shots = max(1, shots)
        sot = int(shots * 0.4)
        
        # Alternate between home and away matches
        if i % 2 == 0:
            home_team = team_id
            away_team = f"opponent_{i}"
        else:
            home_team = f"opponent_{i}"
            away_team = team_id
        
        matches.append(create_mock_match_with_stats(
            match_id=f"match_{team_id}_{i}",
            home_team_id=home_team,
            away_team_id=away_team,
            home_shots=shots,
            away_shots=shots,
            home_sot=sot,
            away_sot=sot,
            scheduled_at=base_date - timedelta(days=count-i)
        ))
    
    return matches


class TestShotMarketEngine:
    """Test suite for ShotMarketEngine."""
    
    def test_predict_all_shot_markets_with_complete_data(self):
        """Test predict_all_shot_markets returns all market types with complete data."""
        base_date = datetime(2024, 1, 15)
        
        # Create sufficient matches for both teams (Poisson-like)
        home_matches = create_poisson_data(mean=12.0, count=10, base_date=base_date, team_id="team_home")
        away_matches = create_poisson_data(mean=14.0, count=10, base_date=base_date, team_id="team_away")
        
        # Create snapshot with shot intelligence
        snapshot = MatchFeatureSnapshot(
            match_id="test_match",
            home_team_id="team_home",
            away_team_id="team_away",
            home_shot_intelligence=ShotIntelligenceMetrics(team_id="team_home"),
            away_shot_intelligence=ShotIntelligenceMetrics(team_id="team_away"),
        )
        
        engine = ShotMarketEngine(session=None)
        
        results = engine.predict_all_shot_markets(
            snapshot=snapshot,
            home_matches=home_matches,
            away_matches=away_matches,
            before_datetime=base_date
        )
        
        # Should have all market types
        assert ShotMarketType.TEAM_SHOTS in results
        assert ShotMarketType.TEAM_SHOTS_ON_TARGET in results
        assert ShotMarketType.TOTAL_SHOTS in results
        
        # Team shots should have home and away predictions
        assert len(results[ShotMarketType.TEAM_SHOTS]) == 2
        assert len(results[ShotMarketType.TEAM_SHOTS_ON_TARGET]) == 2
        assert len(results[ShotMarketType.TOTAL_SHOTS]) == 1
    
    def test_team_shots_thresholds_present(self):
        """Test team shots predictions include all required thresholds."""
        base_date = datetime(2024, 1, 15)
        home_matches = create_poisson_data(mean=12.0, count=10, base_date=base_date, team_id="team_home")
        away_matches = create_poisson_data(mean=14.0, count=10, base_date=base_date, team_id="team_away")
        
        snapshot = MatchFeatureSnapshot(
            match_id="test_match",
            home_team_id="team_home",
            away_team_id="team_away",
            home_shot_intelligence=ShotIntelligenceMetrics(team_id="team_home"),
            away_shot_intelligence=ShotIntelligenceMetrics(team_id="team_away"),
        )
        
        engine = ShotMarketEngine(session=None)
        results = engine.predict_all_shot_markets(
            snapshot=snapshot,
            home_matches=home_matches,
            away_matches=away_matches,
            before_datetime=base_date
        )
        
        home_pred = results[ShotMarketType.TEAM_SHOTS][0]
        
        # Check thresholds
        thresholds = [t.threshold for t in home_pred.thresholds]
        assert 10 in thresholds
        assert 12 in thresholds
        assert 15 in thresholds
        assert 18 in thresholds
        assert 20 in thresholds
        
        # All thresholds should have probabilities
        for threshold in home_pred.thresholds:
            assert threshold.over_probability is not None
            assert 0.0 <= threshold.over_probability <= 1.0
    
    def test_sot_thresholds_present(self):
        """Test SOT predictions include all required thresholds."""
        base_date = datetime(2024, 1, 15)
        home_matches = create_poisson_data(mean=12.0, count=10, base_date=base_date, team_id="team_home")
        away_matches = create_poisson_data(mean=14.0, count=10, base_date=base_date, team_id="team_away")
        
        snapshot = MatchFeatureSnapshot(
            match_id="test_match",
            home_team_id="team_home",
            away_team_id="team_away",
            home_shot_intelligence=ShotIntelligenceMetrics(team_id="team_home"),
            away_shot_intelligence=ShotIntelligenceMetrics(team_id="team_away"),
        )
        
        engine = ShotMarketEngine(session=None)
        results = engine.predict_all_shot_markets(
            snapshot=snapshot,
            home_matches=home_matches,
            away_matches=away_matches,
            before_datetime=base_date
        )
        
        home_sot_pred = results[ShotMarketType.TEAM_SHOTS_ON_TARGET][0]
        
        # Check SOT thresholds
        thresholds = [t.threshold for t in home_sot_pred.thresholds]
        assert 3 in thresholds
        assert 4 in thresholds
        assert 5 in thresholds
        assert 6 in thresholds
        
        # All thresholds should have probabilities
        for threshold in home_sot_pred.thresholds:
            assert threshold.over_probability is not None
            assert 0.0 <= threshold.over_probability <= 1.0
    
    def test_total_shots_thresholds_present(self):
        """Test total shots predictions include all required thresholds."""
        base_date = datetime(2024, 1, 15)
        home_matches = create_poisson_data(mean=12.0, count=10, base_date=base_date, team_id="team_home")
        away_matches = create_poisson_data(mean=14.0, count=10, base_date=base_date, team_id="team_away")
        
        snapshot = MatchFeatureSnapshot(
            match_id="test_match",
            home_team_id="team_home",
            away_team_id="team_away",
            home_shot_intelligence=ShotIntelligenceMetrics(team_id="team_home"),
            away_shot_intelligence=ShotIntelligenceMetrics(team_id="team_away"),
        )
        
        engine = ShotMarketEngine(session=None)
        results = engine.predict_all_shot_markets(
            snapshot=snapshot,
            home_matches=home_matches,
            away_matches=away_matches,
            before_datetime=base_date
        )
        
        total_pred = results[ShotMarketType.TOTAL_SHOTS][0]
        
        # Check total shots thresholds
        thresholds = [t.threshold for t in total_pred.thresholds]
        assert 20 in thresholds
        assert 22 in thresholds
        assert 25 in thresholds
        assert 30 in thresholds
        
        # All thresholds should have probabilities
        for threshold in total_pred.thresholds:
            assert threshold.over_probability is not None
            assert 0.0 <= threshold.over_probability <= 1.0
    
    def test_poisson_distribution_selected(self):
        """Test Poisson distribution selected when variance ≈ mean."""
        base_date = datetime(2024, 1, 15)
        
        # Create Poisson-like data (variance ≈ mean)
        home_matches = create_poisson_data(mean=12.0, count=10, base_date=base_date, team_id="team_home")
        away_matches = create_poisson_data(mean=14.0, count=10, base_date=base_date, team_id="team_away")
        
        snapshot = MatchFeatureSnapshot(
            match_id="test_match",
            home_team_id="team_home",
            away_team_id="team_away",
            home_shot_intelligence=ShotIntelligenceMetrics(team_id="team_home"),
            away_shot_intelligence=ShotIntelligenceMetrics(team_id="team_away"),
        )
        
        engine = ShotMarketEngine(session=None)
        results = engine.predict_all_shot_markets(
            snapshot=snapshot,
            home_matches=home_matches,
            away_matches=away_matches,
            before_datetime=base_date
        )
        
        home_pred = results[ShotMarketType.TEAM_SHOTS][0]
        
        # Should select Poisson distribution
        assert home_pred.distribution_model == DistributionType.POISSON
        
        # Verify variance ≤ mean (or close)
        assert home_pred.variance is not None
        assert home_pred.expected_value is not None
        # Allow some tolerance for Poisson (variance should be close to mean)
        assert home_pred.variance <= home_pred.expected_value + 2.0
    
    def test_negative_binomial_selected(self):
        """Test Negative Binomial selected when variance > mean."""
        base_date = datetime(2024, 1, 15)
        
        # Create overdispersed data (variance >> mean)
        home_matches = create_overdispersed_data(mean=12.0, count=10, base_date=base_date, team_id="team_home")
        away_matches = create_overdispersed_data(mean=14.0, count=10, base_date=base_date, team_id="team_away")
        
        snapshot = MatchFeatureSnapshot(
            match_id="test_match",
            home_team_id="team_home",
            away_team_id="team_away",
            home_shot_intelligence=ShotIntelligenceMetrics(team_id="team_home"),
            away_shot_intelligence=ShotIntelligenceMetrics(team_id="team_away"),
        )
        
        engine = ShotMarketEngine(session=None)
        results = engine.predict_all_shot_markets(
            snapshot=snapshot,
            home_matches=home_matches,
            away_matches=away_matches,
            before_datetime=base_date
        )
        
        home_pred = results[ShotMarketType.TEAM_SHOTS][0]
        
        # Should select Negative Binomial distribution
        assert home_pred.distribution_model == DistributionType.NEGATIVE_BINOMIAL
        
        # Verify variance > mean
        assert home_pred.variance is not None
        assert home_pred.expected_value is not None
        assert home_pred.variance > home_pred.expected_value
    
    def test_insufficient_data_returns_unavailable(self):
        """Test insufficient data returns available=False with unavailability_reason."""
        base_date = datetime(2024, 1, 15)
        
        # Create only 2 matches (insufficient for distribution fitting)
        home_matches = create_poisson_data(mean=12.0, count=2, base_date=base_date, team_id="team_home")
        away_matches = create_poisson_data(mean=14.0, count=2, base_date=base_date, team_id="team_away")
        
        snapshot = MatchFeatureSnapshot(
            match_id="test_match",
            home_team_id="team_home",
            away_team_id="team_away",
            home_shot_intelligence=ShotIntelligenceMetrics(team_id="team_home"),
            away_shot_intelligence=ShotIntelligenceMetrics(team_id="team_away"),
        )
        
        engine = ShotMarketEngine(session=None)
        results = engine.predict_all_shot_markets(
            snapshot=snapshot,
            home_matches=home_matches,
            away_matches=away_matches,
            before_datetime=base_date
        )
        
        home_pred = results[ShotMarketType.TEAM_SHOTS][0]
        
        # Should be unavailable
        assert home_pred.available is False
        assert home_pred.unavailability_reason is not None
        assert "insufficient" in home_pred.unavailability_reason.lower()
        
        # Distribution should be UNAVAILABLE
        assert home_pred.distribution_model == DistributionType.UNAVAILABLE
    
    def test_shot_intelligence_absent_returns_empty_dict(self):
        """Test when shot intelligence absent from snapshot, returns empty dict (not crash)."""
        base_date = datetime(2024, 1, 15)
        home_matches = create_poisson_data(mean=12.0, count=10, base_date=base_date, team_id="team_home")
        away_matches = create_poisson_data(mean=14.0, count=10, base_date=base_date, team_id="team_away")
        
        # Snapshot WITHOUT shot intelligence
        snapshot = MatchFeatureSnapshot(
            match_id="test_match",
            home_team_id="team_home",
            away_team_id="team_away",
            home_shot_intelligence=None,  # Missing
            away_shot_intelligence=None,  # Missing
        )
        
        engine = ShotMarketEngine(session=None)
        results = engine.predict_all_shot_markets(
            snapshot=snapshot,
            home_matches=home_matches,
            away_matches=away_matches,
            before_datetime=base_date
        )
        
        # Should return empty dict
        assert results == {}
    
    def test_distribution_parameters_populated(self):
        """Test distribution parameters (expected_value, variance, sample_size) populated."""
        base_date = datetime(2024, 1, 15)
        home_matches = create_poisson_data(mean=12.0, count=10, base_date=base_date, team_id="team_home")
        away_matches = create_poisson_data(mean=14.0, count=10, base_date=base_date, team_id="team_away")
        
        snapshot = MatchFeatureSnapshot(
            match_id="test_match",
            home_team_id="team_home",
            away_team_id="team_away",
            home_shot_intelligence=ShotIntelligenceMetrics(team_id="team_home"),
            away_shot_intelligence=ShotIntelligenceMetrics(team_id="team_away"),
        )
        
        engine = ShotMarketEngine(session=None)
        results = engine.predict_all_shot_markets(
            snapshot=snapshot,
            home_matches=home_matches,
            away_matches=away_matches,
            before_datetime=base_date
        )
        
        home_pred = results[ShotMarketType.TEAM_SHOTS][0]
        
        # Check parameters are populated
        assert home_pred.expected_value is not None
        assert home_pred.variance is not None
        assert home_pred.sample_size > 0
        assert home_pred.data_quality_score >= 0.0
        
        # Verify expected_value is reasonable (around 12.0)
        assert 10.0 <= home_pred.expected_value <= 14.0
        
        # Verify variance is positive
        assert home_pred.variance > 0.0
    
    def test_no_matches_data_returns_empty_dict(self):
        """Test when no matches data provided, returns empty dict."""
        snapshot = MatchFeatureSnapshot(
            match_id="test_match",
            home_team_id="team_home",
            away_team_id="team_away",
            home_shot_intelligence=ShotIntelligenceMetrics(team_id="team_home"),
            away_shot_intelligence=ShotIntelligenceMetrics(team_id="team_away"),
        )
        
        engine = ShotMarketEngine(session=None)
        
        # No matches data
        results = engine.predict_all_shot_markets(
            snapshot=snapshot,
            home_matches=None,
            away_matches=None,
            before_datetime=datetime.now()
        )
        
        assert results == {}
    
    def test_threshold_probabilities_decrease_with_threshold(self):
        """Test threshold probabilities decrease as threshold increases."""
        base_date = datetime(2024, 1, 15)
        home_matches = create_poisson_data(mean=15.0, count=10, base_date=base_date, team_id="team_home")
        away_matches = create_poisson_data(mean=15.0, count=10, base_date=base_date, team_id="team_away")
        
        snapshot = MatchFeatureSnapshot(
            match_id="test_match",
            home_team_id="team_home",
            away_team_id="team_away",
            home_shot_intelligence=ShotIntelligenceMetrics(team_id="team_home"),
            away_shot_intelligence=ShotIntelligenceMetrics(team_id="team_away"),
        )
        
        engine = ShotMarketEngine(session=None)
        results = engine.predict_all_shot_markets(
            snapshot=snapshot,
            home_matches=home_matches,
            away_matches=away_matches,
            before_datetime=base_date
        )
        
        home_pred = results[ShotMarketType.TEAM_SHOTS][0]
        
        # Sort thresholds by threshold value
        sorted_thresholds = sorted(home_pred.thresholds, key=lambda t: t.threshold)
        
        # Probabilities should generally decrease
        for i in range(len(sorted_thresholds) - 1):
            curr_prob = sorted_thresholds[i].over_probability
            next_prob = sorted_thresholds[i + 1].over_probability
            
            # P(X > T1) >= P(X > T2) when T1 < T2
            assert curr_prob >= next_prob, \
                f"Probability should decrease: P(X>{sorted_thresholds[i].threshold})={curr_prob} >= P(X>{sorted_thresholds[i+1].threshold})={next_prob}"
