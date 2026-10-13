"""Tests for the calibration foundation module.

Covers:
- Brier score (perfect, poor, edge probabilities)
- Log loss binary (perfect, poor, edge, numeric stability)
- Log loss multiclass (1X2, perfect, poor, invalid)
- Reliability data generation (bins, edge cases)
- Calibration error / ECE (perfect, poor, empty)
- BinaryCalibrationResult evaluation
- Multiclass 1X2 evaluation
- Invalid probability inputs
- Empty datasets
- Insufficient sample size reporting
- Calibration scaler stubs (PlattScaler, IsotonicScaler)
"""

import math
import pytest
from typing import List, Tuple

from app.prediction.calibration import (
    brier_score,
    log_loss_binary,
    log_loss_multiclass,
    reliability_data,
    calibration_error,
    evaluate_binary,
    evaluate_1x2,
    PlattScaler,
    IsotonicScaler,
    BrierScoreResult,
    LogLossResult,
    ReliabilityData,
    CalibrationErrorResult,
    BinaryCalibrationResult,
    Multiclass1X2CalibrationResult,
    MIN_SAMPLES_FOR_CALIBRATION,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _perfect_binary(n: int = 50) -> Tuple[List[float], List[int]]:
    """Alternating perfect predictions: (1.0, 1), (0.0, 0), ..."""
    probs = []
    acts = []
    for i in range(n):
        if i % 2 == 0:
            probs.append(1.0)
            acts.append(1)
        else:
            probs.append(0.0)
            acts.append(0)
    return probs, acts


def _random_binary(n: int = 100, p: float = 0.5) -> Tuple[List[float], List[int]]:
    """Constant prediction with actual 50/50 outcomes."""
    probs = [p] * n
    acts = [1 if i % 2 == 0 else 0 for i in range(n)]
    return probs, acts


# ---------------------------------------------------------------------------
# Brier Score
# ---------------------------------------------------------------------------

class TestBrierScore:

    def test_perfect_prediction_brier_zero(self):
        """Perfect predictions → Brier score = 0."""
        probs, acts = _perfect_binary(50)
        result = brier_score(probs, acts)
        assert abs(result.brier_score) < 1e-9

    def test_worst_prediction_brier_one(self):
        """All predictions perfectly wrong → Brier score = 1."""
        probs = [0.0] * 20 + [1.0] * 20
        acts  = [1]  * 20 + [0]  * 20
        result = brier_score(probs, acts)
        assert abs(result.brier_score - 1.0) < 1e-9

    def test_random_50_50(self):
        """Constant p=0.5 with 50% outcomes → BS = 0.25."""
        probs = [0.5] * 100
        acts  = [1, 0] * 50
        result = brier_score(probs, acts)
        assert abs(result.brier_score - 0.25) < 1e-9

    def test_empty_dataset(self):
        result = brier_score([], [])
        assert math.isnan(result.brier_score)
        assert result.n_samples == 0

    def test_n_samples_recorded(self):
        probs, acts = _perfect_binary(30)
        result = brier_score(probs, acts)
        assert result.n_samples == 30

    def test_edge_probability_zero(self):
        result = brier_score([0.0], [0])
        assert abs(result.brier_score) < 1e-9

    def test_edge_probability_one(self):
        result = brier_score([1.0], [1])
        assert abs(result.brier_score) < 1e-9

    def test_edge_probability_zero_wrong(self):
        """P=0 but actual=1 → BS = 1."""
        result = brier_score([0.0], [1])
        assert abs(result.brier_score - 1.0) < 1e-9

    def test_invalid_probability_raises(self):
        with pytest.raises(ValueError):
            brier_score([1.5], [1])

    def test_invalid_probability_negative_raises(self):
        with pytest.raises(ValueError):
            brier_score([-0.1], [0])

    def test_invalid_outcome_raises(self):
        with pytest.raises(ValueError):
            brier_score([0.5], [2])

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError):
            brier_score([0.5, 0.6], [1])

    def test_is_reliable_flag(self):
        probs, acts = _perfect_binary(MIN_SAMPLES_FOR_CALIBRATION + 1)
        result = brier_score(probs, acts)
        assert result.is_reliable is True

    def test_not_reliable_small_sample(self):
        result = brier_score([0.5], [1])
        assert result.is_reliable is False

    def test_outcome_label_stored(self):
        result = brier_score([0.5], [1], outcome_label="home_win")
        assert result.outcome_label == "home_win"

    def test_known_value(self):
        """BS = ((0.7-1)^2 + (0.3-0)^2) / 2 = (0.09 + 0.09)/2 = 0.09"""
        probs = [0.7, 0.3]
        acts  = [1, 0]
        result = brier_score(probs, acts)
        assert abs(result.brier_score - 0.09) < 1e-9


# ---------------------------------------------------------------------------
# Log Loss – binary
# ---------------------------------------------------------------------------

class TestLogLossBinary:

    def test_perfect_predictions_near_zero(self):
        """Nearly perfect predictions → low log loss."""
        probs = [0.999] * 50
        acts  = [1] * 50
        result = log_loss_binary(probs, acts)
        assert result.log_loss < 0.01

    def test_wrong_predictions_high_loss(self):
        """Consistently wrong predictions → high log loss."""
        probs = [0.001] * 50
        acts  = [1] * 50
        result = log_loss_binary(probs, acts)
        assert result.log_loss > 5.0

    def test_random_50_50_near_log2(self):
        """Constant p=0.5 with 50% outcomes → LL ≈ log(2) ≈ 0.693."""
        probs = [0.5] * 100
        acts  = [1, 0] * 50
        result = log_loss_binary(probs, acts)
        assert abs(result.log_loss - math.log(2)) < 0.01

    def test_empty_dataset(self):
        result = log_loss_binary([], [])
        assert math.isnan(result.log_loss)
        assert result.n_samples == 0

    def test_edge_probability_zero_no_crash(self):
        """log(0) is handled by epsilon — must not crash."""
        result = log_loss_binary([0.0], [1])
        assert result.log_loss > 0.0
        assert not math.isnan(result.log_loss)
        assert not math.isinf(result.log_loss)

    def test_edge_probability_one_no_crash(self):
        result = log_loss_binary([1.0], [0])
        assert result.log_loss > 0.0
        assert not math.isinf(result.log_loss)

    def test_invalid_probability_raises(self):
        with pytest.raises(ValueError):
            log_loss_binary([1.5], [1])

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError):
            log_loss_binary([0.5, 0.6], [1])

    def test_n_samples_recorded(self):
        probs, acts = _random_binary(40)
        result = log_loss_binary(probs, acts)
        assert result.n_samples == 40


# ---------------------------------------------------------------------------
# Log Loss – multiclass 1X2
# ---------------------------------------------------------------------------

class TestLogLossMulticlass:

    def test_perfect_predictions_near_zero(self):
        probs = [[1.0, 0.0, 0.0]] * 20
        acts  = [[1, 0, 0]] * 20
        result = log_loss_multiclass(probs, acts)
        assert result.log_loss < 0.001

    def test_random_thirds_near_log3(self):
        """Constant 1/3 each → LL ≈ log(3) ≈ 1.099."""
        probs = [[1/3, 1/3, 1/3]] * 90
        acts  = [[1,0,0]]*30 + [[0,1,0]]*30 + [[0,0,1]]*30
        result = log_loss_multiclass(probs, acts)
        assert abs(result.log_loss - math.log(3)) < 0.01

    def test_empty_dataset(self):
        result = log_loss_multiclass([], [])
        assert math.isnan(result.log_loss)

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError):
            log_loss_multiclass([[0.5, 0.3, 0.2]], [[1, 0, 0], [0, 1, 0]])

    def test_inconsistent_class_count_raises(self):
        with pytest.raises(ValueError):
            log_loss_multiclass([[0.5, 0.5]], [[1, 0, 0]])

    def test_invalid_probability_raises(self):
        with pytest.raises(ValueError):
            log_loss_multiclass([[1.5, 0.0, 0.0]], [[1, 0, 0]])

    def test_invalid_outcome_raises(self):
        with pytest.raises(ValueError):
            log_loss_multiclass([[0.5, 0.3, 0.2]], [[1, 0, 2]])


# ---------------------------------------------------------------------------
# Reliability data
# ---------------------------------------------------------------------------

class TestReliabilityData:

    def test_bins_have_correct_count(self):
        probs, acts = _random_binary(200, p=0.5)
        result = reliability_data(probs, acts, n_bins=10)
        # All bins within [0,1] should be covered with 200 samples at p=0.5
        assert len(result.bins) > 0

    def test_all_bin_probabilities_in_range(self):
        probs, acts = _random_binary(200, p=0.5)
        result = reliability_data(probs, acts, n_bins=10)
        for b in result.bins:
            assert 0.0 <= b.mean_predicted <= 1.0
            assert 0.0 <= b.fraction_positive <= 1.0

    def test_empty_dataset(self):
        result = reliability_data([], [])
        assert len(result.bins) == 0
        assert result.n_samples == 0

    def test_invalid_n_bins_raises(self):
        with pytest.raises(ValueError, match="n_bins"):
            reliability_data([0.5], [1], n_bins=0)

    def test_single_sample(self):
        result = reliability_data([0.8], [1], n_bins=10)
        assert result.n_samples == 1
        assert len(result.bins) == 1

    def test_perfect_calibration_bins(self):
        """Predict prob=0.0 for all 0s and 1.0 for all 1s."""
        probs = [0.0] * 50 + [1.0] * 50
        acts  = [0]   * 50 + [1]   * 50
        result = reliability_data(probs, acts, n_bins=10)
        for b in result.bins:
            # fraction_positive should equal mean_predicted
            assert abs(b.fraction_positive - b.mean_predicted) < 0.01

    def test_n_samples_matches_total(self):
        probs, acts = _random_binary(80)
        result = reliability_data(probs, acts, n_bins=10)
        assert result.n_samples == 80

    def test_outcome_label_stored(self):
        result = reliability_data([0.5], [1], outcome_label="draw")
        assert result.outcome_label == "draw"


# ---------------------------------------------------------------------------
# Calibration Error (ECE)
# ---------------------------------------------------------------------------

class TestCalibrationError:

    def test_perfect_calibration_near_zero(self):
        """Perfect calibration → ECE ≈ 0."""
        probs = [0.0] * 50 + [1.0] * 50
        acts  = [0]   * 50 + [1]   * 50
        result = calibration_error(probs, acts, n_bins=10)
        assert result.ece < 0.05

    def test_poor_calibration_high_ece(self):
        """Confidently wrong predictions → high ECE."""
        probs = [0.9] * 100
        acts  = [0]   * 100
        result = calibration_error(probs, acts, n_bins=10)
        assert result.ece > 0.5

    def test_empty_dataset(self):
        result = calibration_error([], [])
        assert math.isnan(result.ece)
        assert result.n_samples == 0

    def test_n_samples_recorded(self):
        probs, acts = _random_binary(60)
        result = calibration_error(probs, acts, n_bins=10)
        assert result.n_samples == 60

    def test_ece_non_negative(self):
        probs, acts = _random_binary(100)
        result = calibration_error(probs, acts, n_bins=10)
        assert result.ece >= 0.0

    def test_ece_at_most_one(self):
        """ECE is a weighted average of absolute errors, each in [0,1]."""
        probs, acts = _random_binary(100)
        result = calibration_error(probs, acts, n_bins=10)
        assert result.ece <= 1.0

    def test_is_reliable_flag(self):
        probs, acts = _random_binary(MIN_SAMPLES_FOR_CALIBRATION + 10)
        result = calibration_error(probs, acts)
        assert result.is_reliable is True

    def test_not_reliable_small_sample(self):
        result = calibration_error([0.5], [1])
        assert result.is_reliable is False


# ---------------------------------------------------------------------------
# evaluate_binary
# ---------------------------------------------------------------------------

class TestEvaluateBinary:

    def test_returns_binary_calibration_result(self):
        probs, acts = _random_binary(50)
        result = evaluate_binary(probs, acts, "home_win")
        assert isinstance(result, BinaryCalibrationResult)

    def test_all_components_populated(self):
        probs, acts = _random_binary(50)
        result = evaluate_binary(probs, acts, "draw")
        assert result.brier is not None
        assert result.log_loss is not None
        assert result.reliability is not None
        assert result.calibration_error is not None

    def test_outcome_label_propagated(self):
        probs, acts = _random_binary(50)
        result = evaluate_binary(probs, acts, "away_win")
        assert result.outcome_label == "away_win"
        assert result.brier.outcome_label == "away_win"

    def test_empty_dataset_does_not_crash(self):
        result = evaluate_binary([], [], "home_win")
        assert math.isnan(result.brier.brier_score)
        assert math.isnan(result.log_loss.log_loss)

    def test_well_calibrated_flag_perfect(self):
        """With enough perfectly calibrated data → is_well_calibrated."""
        probs = [0.0] * (MIN_SAMPLES_FOR_CALIBRATION // 2) + \
                [1.0] * (MIN_SAMPLES_FOR_CALIBRATION // 2)
        acts  = [0]   * (MIN_SAMPLES_FOR_CALIBRATION // 2) + \
                [1]   * (MIN_SAMPLES_FOR_CALIBRATION // 2)
        result = evaluate_binary(probs, acts, "home_win")
        assert result.is_well_calibrated is True

    def test_not_well_calibrated_poor_predictions(self):
        probs = [0.95] * 50
        acts  = [0]    * 50
        result = evaluate_binary(probs, acts, "home_win")
        assert result.is_well_calibrated is False


# ---------------------------------------------------------------------------
# evaluate_1x2
# ---------------------------------------------------------------------------

class TestEvaluate1X2:

    def _make_1x2_data(self, n: int = 90):
        """Equal split of home/draw/away outcomes with uniform predictions."""
        probs = [(0.45, 0.30, 0.25)] * n
        acts  = (["home"] * (n // 3) +
                 ["draw"] * (n // 3) +
                 ["away"] * (n - 2 * (n // 3)))
        return probs, acts

    def test_returns_multiclass_result(self):
        probs, acts = self._make_1x2_data()
        result = evaluate_1x2(probs, acts)
        assert isinstance(result, Multiclass1X2CalibrationResult)

    def test_all_components_populated(self):
        probs, acts = self._make_1x2_data()
        result = evaluate_1x2(probs, acts)
        assert result.home_win is not None
        assert result.draw is not None
        assert result.away_win is not None
        assert result.multiclass_log_loss is not None

    def test_n_samples_recorded(self):
        probs, acts = self._make_1x2_data(90)
        result = evaluate_1x2(probs, acts)
        assert result.n_samples == 90

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError):
            evaluate_1x2([(0.45, 0.30, 0.25)], ["home", "draw"])

    def test_invalid_outcome_raises(self):
        with pytest.raises(ValueError, match="Invalid outcome"):
            evaluate_1x2([(0.45, 0.30, 0.25)], ["home_win"])

    def test_empty_dataset(self):
        result = evaluate_1x2([], [])
        assert result.n_samples == 0
        assert math.isnan(result.multiclass_log_loss.log_loss)

    def test_perfect_predictions_low_log_loss(self):
        """Perfect predictions → multiclass log loss near 0."""
        probs = [(1.0, 0.0, 0.0)] * 30
        acts  = ["home"] * 30
        result = evaluate_1x2(probs, acts)
        assert result.multiclass_log_loss.log_loss < 0.001

    def test_poor_predictions_high_log_loss(self):
        probs = [(0.01, 0.01, 0.98)] * 30
        acts  = ["home"] * 30
        result = evaluate_1x2(probs, acts)
        assert result.multiclass_log_loss.log_loss > 3.0

    def test_binary_components_valid(self):
        probs, acts = self._make_1x2_data(90)
        result = evaluate_1x2(probs, acts)
        for cal in [result.home_win, result.draw, result.away_win]:
            assert cal.brier.n_samples == 90
            assert cal.log_loss.n_samples == 90


# ---------------------------------------------------------------------------
# Edge probability handling
# ---------------------------------------------------------------------------

class TestEdgeProbabilities:

    def test_all_zeros_brier(self):
        probs = [0.0] * 20
        acts  = [0]   * 20
        result = brier_score(probs, acts)
        assert abs(result.brier_score) < 1e-9

    def test_all_ones_brier(self):
        probs = [1.0] * 20
        acts  = [1]   * 20
        result = brier_score(probs, acts)
        assert abs(result.brier_score) < 1e-9

    def test_zero_probability_log_loss_no_inf(self):
        """log(0) must not produce inf or nan."""
        result = log_loss_binary([0.0], [0])
        assert not math.isinf(result.log_loss)
        assert not math.isnan(result.log_loss)

    def test_one_probability_log_loss_no_inf(self):
        result = log_loss_binary([1.0], [1])
        assert not math.isinf(result.log_loss)
        assert not math.isnan(result.log_loss)


# ---------------------------------------------------------------------------
# Calibration scaler stubs
# ---------------------------------------------------------------------------

class TestCalibrationScalerStubs:

    def test_platt_scaler_is_not_fitted_initially(self):
        scaler = PlattScaler()
        assert scaler.is_fitted is False

    def test_platt_scaler_fit_raises_not_implemented(self):
        scaler = PlattScaler()
        with pytest.raises(NotImplementedError, match="not yet implemented"):
            scaler.fit([0.5, 0.6], [1, 0])

    def test_platt_scaler_transform_raises_before_fit(self):
        scaler = PlattScaler()
        with pytest.raises(RuntimeError, match="fitted"):
            scaler.transform([0.5])

    def test_isotonic_scaler_is_not_fitted_initially(self):
        scaler = IsotonicScaler()
        assert scaler.is_fitted is False

    def test_isotonic_scaler_fit_raises_not_implemented(self):
        scaler = IsotonicScaler()
        with pytest.raises(NotImplementedError, match="not yet implemented"):
            scaler.fit([0.5, 0.6], [1, 0])

    def test_isotonic_scaler_transform_raises_before_fit(self):
        scaler = IsotonicScaler()
        with pytest.raises(RuntimeError, match="fitted"):
            scaler.transform([0.5])
