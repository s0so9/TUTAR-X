"""Tests for walk-forward evaluation infrastructure.

These tests verify the evaluation framework using synthetic data.
Real walk-forward evaluation requires historical match database.
"""

import pytest
from datetime import datetime, timedelta
from typing import List

from app.domain.match import Match
from app.domain.enums import MatchStatus
from app.prediction.walk_forward import (
    FeatureConfiguration,
    FeatureGroup,
    WalkForwardEvaluator,
    WalkForwardMetrics,
    PipelinePredictionRecord,
    RecordStatus,
    compare_configurations,
)


class TestFeatureConfiguration:
    """Test feature configuration creation."""
    
    def test_baseline_configuration(self):
        """Test baseline configuration creation."""
        config = FeatureConfiguration.baseline()
        assert config.name == "baseline"
        assert FeatureGroup.BASELINE in config.enabled_groups
        assert len(config.enabled_groups) == 1
    
    def test_incremental_configuration(self):
        """Test incremental configuration creation."""
        config = FeatureConfiguration.incremental(FeatureGroup.OPPONENT_ADJUSTMENT)
        assert config.name == "baseline_plus_opponent_adjustment"
        assert FeatureGroup.BASELINE in config.enabled_groups
        assert FeatureGroup.OPPONENT_ADJUSTMENT in config.enabled_groups
        assert len(config.enabled_groups) == 2
    
    def test_full_advanced_configuration(self):
        """Test full advanced configuration creation."""
        config = FeatureConfiguration.full_advanced()
        assert config.name == "full_advanced"
        assert len(config.enabled_groups) == len(FeatureGroup)


class TestWalkForwardEvaluator:
    """Test walk-forward evaluator (with synthetic data)."""
    
    @pytest.fixture
    def synthetic_matches(self) -> List[Match]:
        """Create synthetic finished matches."""
        matches = []
        base_date = datetime(2024, 1, 1)
        
        for i in range(50):
            match = Match(
                id=f"match_{i}",
                competition_id="test_league",
                season_id="2024",
                home_team_id=f"team_{i % 10}",
                away_team_id=f"team_{(i + 1) % 10}",
                scheduled_at=base_date + timedelta(days=i),
                status=MatchStatus.FINISHED,
                home_score=i % 3,
                away_score=(i + 1) % 3
            )
            matches.append(match)
        
        return matches
    
    def test_evaluator_initialization(self, mock_session):
        """Test evaluator can be initialized."""
        evaluator = WalkForwardEvaluator(
            session=mock_session,
            min_train=10,
            test_size=5,
            step_size=5
        )
        assert evaluator.min_train == 10
        assert evaluator.test_size == 5
        assert evaluator.step_size == 5
    
    def test_insufficient_data_returns_empty_metrics(self, mock_session):
        """Test handling of insufficient data."""
        evaluator = WalkForwardEvaluator(session=mock_session, min_train=100)
        
        # Only 5 matches - insufficient
        small_sample = [
            Match(
                id=f"m{i}",
                competition_id="test",
                season_id="2024",
                home_team_id="h",
                away_team_id="a",
                scheduled_at=datetime(2024, 1, i + 1),
                status=MatchStatus.FINISHED,
                home_score=1,
                away_score=0
            )
            for i in range(5)
        ]
        
        config = FeatureConfiguration.baseline()
        records, metrics = evaluator.evaluate_configuration(small_sample, config)
        
        assert len(records) == 0
        assert metrics.n_predictions == 0
        assert not metrics.is_reliable
    
    def test_evaluation_produces_records(self, mock_session, synthetic_matches):
        """Test evaluation produces prediction records.
        
        Note: This will produce empty/None records due to missing
        feature infrastructure, but verifies no crashes.
        """
        evaluator = WalkForwardEvaluator(
            session=mock_session,
            min_train=10,
            test_size=5,
            step_size=5
        )
        
        config = FeatureConfiguration.baseline()
        
        # This will return empty due to missing feature extraction
        # but should not crash
        records, metrics = evaluator.evaluate_configuration(synthetic_matches, config)
        
        # With missing infrastructure, records will be empty
        assert isinstance(records, list)
        assert isinstance(metrics, WalkForwardMetrics)
        assert metrics.config_name == "baseline"


class TestPipelinePredictionRecord:
    """Test pipeline prediction record."""
    
    def test_record_computes_metrics(self):
        """Test prediction record computes Brier and log loss."""
        record = PipelinePredictionRecord(
            match_id="test",
            predicted_at=datetime.now(),
            actual_outcome="home_win",
            actual_home_score=2,
            actual_away_score=0,
            feature_config="baseline",
            record_status=RecordStatus.SUCCESS,
            models_available=7,
            models_successful=7,
            model_outputs={},
            ensemble_home_win=0.7,
            ensemble_draw=0.2,
            ensemble_away_win=0.1,
            model_agreement=0.8,
            calibrated_home_win=0.65,
            calibrated_draw=0.25,
            calibrated_away_win=0.10,
            calibration_status="fitted",
            confidence_score=0.75,
            confidence_label="HIGH",
            uncertainty_score=0.3,
            uncertainty_label="LOW",
            model_disagreement=0.2,
            selected_market="HOME_WIN",
            selection_probability=0.65,
            selection_confidence=0.75,
            is_pass=False,
            pass_reason=None,
            features_available={},
            data_quality_score=0.8
        )
        
        # Brier scores should be computed
        assert 0.0 <= record.brier_score_ensemble <= 1.0
        assert 0.0 <= record.brier_score_calibrated <= 1.0
        
        # Log loss should be computed
        assert record.log_loss_ensemble > 0.0
        assert record.log_loss_calibrated > 0.0
    
    def test_brier_score_perfect_prediction(self):
        """Test Brier score for perfect prediction."""
        record = PipelinePredictionRecord(
            match_id="test",
            predicted_at=datetime.now(),
            actual_outcome="home_win",
            actual_home_score=2,
            actual_away_score=0,
            feature_config="baseline",
            record_status=RecordStatus.SUCCESS,
            models_available=7,
            models_successful=7,
            model_outputs={},
            ensemble_home_win=1.0,
            ensemble_draw=0.0,
            ensemble_away_win=0.0,
            model_agreement=1.0,
            calibrated_home_win=1.0,
            calibrated_draw=0.0,
            calibrated_away_win=0.0,
            calibration_status="fitted",
            confidence_score=0.95,
            confidence_label="HIGH",
            uncertainty_score=0.1,
            uncertainty_label="LOW",
            model_disagreement=0.0,
            selected_market="HOME_WIN",
            selection_probability=1.0,
            selection_confidence=0.95,
            is_pass=False,
            pass_reason=None,
            features_available={},
            data_quality_score=1.0
        )
        
        # Perfect prediction should have Brier score = 0
        assert record.brier_score_ensemble == 0.0
        assert record.brier_score_calibrated == 0.0


class TestCompareConfigurations:
    """Test configuration comparison."""
    
    def test_comparison_computes_deltas(self):
        """Test comparison computes delta metrics."""
        baseline = WalkForwardMetrics(
            config_name="baseline",
            n_predictions=50,
            n_pass=10,
            coverage=0.8,
            accuracy_ensemble=0.55,
            brier_ensemble=0.25,
            log_loss_ensemble=0.8,
            calibration_error_ensemble=0.1,
            accuracy_calibrated=0.57,
            brier_calibrated=0.23,
            log_loss_calibrated=0.75,
            calibration_error_calibrated=0.08,
            avg_models_available=7.0,
            avg_model_agreement=0.7,
            avg_model_disagreement=0.3,
            avg_confidence=0.6,
            avg_uncertainty=0.4,
            high_confidence_count=15,
            high_uncertainty_count=10,
            avg_data_quality=0.7,
            pass_reasons={}
        )
        
        advanced = WalkForwardMetrics(
            config_name="advanced",
            n_predictions=50,
            n_pass=8,
            coverage=0.84,
            accuracy_ensemble=0.58,
            brier_ensemble=0.22,
            log_loss_ensemble=0.75,
            calibration_error_ensemble=0.08,
            accuracy_calibrated=0.60,
            brier_calibrated=0.20,
            log_loss_calibrated=0.70,
            calibration_error_calibrated=0.06,
            avg_models_available=7.0,
            avg_model_agreement=0.75,
            avg_model_disagreement=0.25,
            avg_confidence=0.65,
            avg_uncertainty=0.35,
            high_confidence_count=20,
            high_uncertainty_count=8,
            avg_data_quality=0.75,
            pass_reasons={}
        )
        
        comparison = compare_configurations(baseline, advanced)
        
        # Improvements (positive = better)
        assert comparison.brier_improvement > 0  # Lower Brier is better
        assert comparison.log_loss_improvement > 0  # Lower log loss is better
        assert comparison.accuracy_improvement > 0  # Higher accuracy is better
        assert comparison.calibration_improvement > 0  # Lower calibration error is better
    
    def test_comparison_with_none_values(self):
        """Test comparison handles None values gracefully."""
        baseline = WalkForwardMetrics(
            config_name="baseline",
            n_predictions=10,  # Below reliable threshold
            n_pass=5,
            coverage=0.5,
            accuracy_ensemble=None,
            brier_ensemble=None,
            log_loss_ensemble=None,
            calibration_error_ensemble=None,
            accuracy_calibrated=None,
            brier_calibrated=None,
            log_loss_calibrated=None,
            calibration_error_calibrated=None,
            avg_models_available=5.0,
            avg_model_agreement=0.5,
            avg_model_disagreement=0.5,
            avg_confidence=0.5,
            avg_uncertainty=0.5,
            high_confidence_count=2,
            high_uncertainty_count=3,
            avg_data_quality=0.5,
            pass_reasons={}
        )
        
        advanced = WalkForwardMetrics(
            config_name="advanced",
            n_predictions=10,
            n_pass=4,
            coverage=0.6,
            accuracy_ensemble=None,
            brier_ensemble=None,
            log_loss_ensemble=None,
            calibration_error_ensemble=None,
            accuracy_calibrated=None,
            brier_calibrated=None,
            log_loss_calibrated=None,
            calibration_error_calibrated=None,
            avg_models_available=5.0,
            avg_model_agreement=0.6,
            avg_model_disagreement=0.4,
            avg_confidence=0.55,
            avg_uncertainty=0.45,
            high_confidence_count=3,
            high_uncertainty_count=2,
            avg_data_quality=0.55,
            pass_reasons={}
        )
        
        comparison = compare_configurations(baseline, advanced)
        
        # All improvements should be None
        assert comparison.brier_improvement is None
        assert comparison.log_loss_improvement is None
        assert comparison.accuracy_improvement is None
        assert comparison.calibration_improvement is None


@pytest.fixture
def mock_session():
    """Mock database session for testing."""
    class MockSession:
        def query(self, *args, **kwargs):
            return self
        
        def filter(self, *args, **kwargs):
            return self
        
        def all(self):
            return []
        
        def first(self):
            return None
        
        def count(self):
            return 0
    
    return MockSession()
