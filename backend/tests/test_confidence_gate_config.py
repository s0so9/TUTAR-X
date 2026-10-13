"""Tests for Fix #9: PredictionService confidence gate configuration.

Verifies that PredictionService properly initializes self.config with
min_sample_size, and that min_matches is configurable (not hardcoded).
"""
import pytest
from unittest.mock import Mock, MagicMock
from app.prediction.service import PredictionService


def test_prediction_service_initializes_config():
    """BUGFIX: PredictionService initializes self.config with min_sample_size."""
    provider_mock = Mock()

    service = PredictionService(
        provider=provider_mock,
        min_matches=2,
        min_sample_size=5
    )

    # Verify config exists and has correct value
    assert hasattr(service, 'config')
    assert hasattr(service.config, 'min_sample_size')
    assert service.config.min_sample_size == 5


def _mode_defaults():
    """Thresholds of the configured mode (production unless FI_IS_DEVELOPMENT)."""
    from app.config import settings
    from app.prediction.service import PredictionServiceConfig
    if settings.is_development:
        return PredictionServiceConfig.for_development()
    return PredictionServiceConfig.for_production()


def test_prediction_service_default_min_sample_size():
    """Without overrides, min_sample_size comes from the mode (prod 8 / dev 5).

    Previously a hardcoded default of 3 silently replaced production's 8.
    """
    provider_mock = Mock()

    service = PredictionService(provider=provider_mock)

    assert service.config.min_sample_size == _mode_defaults().min_sample_size


def test_prediction_service_configurable_min_matches():
    """BUGFIX: min_matches is configurable parameter (not hardcoded to 1)."""
    provider_mock = Mock()

    service = PredictionService(
        provider=provider_mock,
        min_matches=5  # Custom value
    )

    # Verify feature extractor was created with correct min_matches
    assert service.feature_extractor.min_matches == 5


def test_prediction_service_default_min_matches():
    """Without overrides, min_matches comes from the mode (prod 5 / dev 3)."""
    provider_mock = Mock()

    service = PredictionService(provider=provider_mock)

    assert service.feature_extractor.min_matches == _mode_defaults().min_matches
    assert service.config.min_matches == _mode_defaults().min_matches


def test_prediction_service_custom_both_params():
    """Both min_matches and min_sample_size can be customized."""
    provider_mock = Mock()

    service = PredictionService(
        provider=provider_mock,
        min_matches=4,
        min_sample_size=10
    )

    assert service.feature_extractor.min_matches == 4
    assert service.config.min_sample_size == 10


def test_confidence_gate_uses_config():
    """Confidence gate (_evaluate_withdrawal_conditions) uses self.config.min_sample_size."""
    provider_mock = Mock()

    service = PredictionService(
        provider=provider_mock,
        min_sample_size=7
    )

    # Create mock snapshot with data_quality
    snapshot_mock = Mock()
    snapshot_mock.data_quality = Mock()
    snapshot_mock.data_quality.total_matches = 5  # Below threshold

    # Create mock orchestration result
    orchestration_mock = Mock()
    orchestration_mock.successful_predictions = []

    # This should not raise AttributeError
    try:
        result = service._evaluate_withdrawal_conditions(
            snapshot=snapshot_mock,
            orchestration_result=orchestration_mock,
            confidence_assessment=Mock(overall_confidence=0.8),
            calibration_metadata={},
            correlation_id="test"
        )
        # Should return True (insufficient data)
        assert result is True
    except AttributeError as e:
        pytest.fail(f"AttributeError raised: {e}")
