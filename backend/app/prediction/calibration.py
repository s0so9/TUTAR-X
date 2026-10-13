"""Probability calibration and evaluation foundation.

This module provides the foundational layer for evaluating and calibrating
probabilistic football predictions.  It is intentionally modular and
model-independent.

Implemented:
- Brier score (binary and multiclass)
- Log loss (binary and multiclass)
- Reliability data generation (for reliability diagrams)
- Expected Calibration Error (ECE)
- Binary probability evaluation abstraction
- Multiclass 1X2 evaluation

Abstraction stubs (not yet trained/fitted, ready for future extension):
- PlattScaler    — Platt-style sigmoid scaling (structure only)
- IsotonicScaler — Isotonic regression scaling (structure only)

Design constraints:
- No future data leakage.  Calibration metrics are computed from
  historical data only.  The caller is responsible for chronological
  ordering.
- Model-independent: metrics accept raw probability arrays, not
  model-specific objects.
- Handles edge cases: empty datasets, invalid probabilities (outside
  [0,1]), edge probabilities (exactly 0 or 1), insufficient sample sizes.

Mathematical definitions:
  Brier score (binary):   BS = mean((p_i - o_i)^2)
  Log loss (binary):      LL = -mean(o_i*log(p_i) + (1-o_i)*log(1-p_i))
  Multiclass log loss:    LL = -mean(sum_k(y_ik * log(p_ik)))
  ECE:                    ECE = sum_b(|B_b|/N * |acc_b - conf_b|)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOG_EPSILON = 1e-15
"""Small constant to avoid log(0) when probability = 0."""

MIN_SAMPLES_FOR_CALIBRATION = 30
"""Minimum sample count for a reliable calibration estimate."""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class BrierScoreResult:
    """Result of a Brier score calculation."""

    brier_score: float
    n_samples: int
    outcome_label: str = ""

    @property
    def is_reliable(self) -> bool:
        return self.n_samples >= MIN_SAMPLES_FOR_CALIBRATION


@dataclass
class LogLossResult:
    """Result of a log loss calculation."""

    log_loss: float
    n_samples: int
    outcome_label: str = ""

    @property
    def is_reliable(self) -> bool:
        return self.n_samples >= MIN_SAMPLES_FOR_CALIBRATION


@dataclass
class ReliabilityBin:
    """A single bin in a reliability diagram."""

    bin_lower: float
    bin_upper: float
    mean_predicted: float
    """Mean predicted probability in this bin."""
    fraction_positive: float
    """Fraction of positive outcomes in this bin (empirical probability)."""
    n_samples: int


@dataclass
class ReliabilityData:
    """Reliability diagram data for a single probability outcome."""

    bins: List[ReliabilityBin]
    n_samples: int
    n_bins: int
    outcome_label: str = ""

    @property
    def is_reliable(self) -> bool:
        return self.n_samples >= MIN_SAMPLES_FOR_CALIBRATION


@dataclass
class CalibrationErrorResult:
    """Expected Calibration Error (ECE) result."""

    ece: float
    """Expected Calibration Error (weighted average of bin errors)."""

    n_samples: int
    n_bins: int
    outcome_label: str = ""

    bins: List[ReliabilityBin] = field(default_factory=list)

    @property
    def is_reliable(self) -> bool:
        return self.n_samples >= MIN_SAMPLES_FOR_CALIBRATION


@dataclass
class BinaryCalibrationResult:
    """Full calibration evaluation for a binary probability estimate."""

    outcome_label: str
    brier: BrierScoreResult
    log_loss: LogLossResult
    reliability: ReliabilityData
    calibration_error: CalibrationErrorResult

    @property
    def is_well_calibrated(self) -> bool:
        """Heuristic: ECE < 0.05 suggests reasonable calibration."""
        if not self.calibration_error.is_reliable:
            return False
        return self.calibration_error.ece < 0.05


@dataclass
class Multiclass1X2CalibrationResult:
    """Calibration evaluation for 1X2 multiclass predictions."""

    home_win: BinaryCalibrationResult
    draw: BinaryCalibrationResult
    away_win: BinaryCalibrationResult

    multiclass_log_loss: LogLossResult
    n_samples: int


# ---------------------------------------------------------------------------
# Core metric functions
# ---------------------------------------------------------------------------

def brier_score(
    predicted_probs: List[float],
    actual_outcomes: List[int],
    outcome_label: str = "",
) -> BrierScoreResult:
    """Compute the Brier score for a binary probability series.

    Brier score = mean((p_i - o_i)^2)

    Lower is better.  Perfect calibration gives BS = 0.
    Random predictions (p=0.5 always) give BS = 0.25.

    Args:
        predicted_probs: Predicted probabilities in [0, 1].
        actual_outcomes: Observed outcomes (0 or 1).
        outcome_label:   Optional label for context.

    Returns:
        BrierScoreResult

    Raises:
        ValueError: If lists differ in length.
        ValueError: If any probability is outside [0, 1].
        ValueError: If any outcome is not 0 or 1.
    """
    _validate_inputs(predicted_probs, actual_outcomes)

    n = len(predicted_probs)
    if n == 0:
        return BrierScoreResult(
            brier_score=float("nan"), n_samples=0, outcome_label=outcome_label
        )

    bs = sum(
        (p - o) ** 2
        for p, o in zip(predicted_probs, actual_outcomes)
    ) / n

    return BrierScoreResult(brier_score=bs, n_samples=n, outcome_label=outcome_label)


def log_loss_binary(
    predicted_probs: List[float],
    actual_outcomes: List[int],
    outcome_label: str = "",
) -> LogLossResult:
    """Compute binary log loss.

    LL = -mean(o * log(p) + (1-o) * log(1-p))

    Lower is better.  Perfect predictions give LL → 0.
    Edge probabilities 0 and 1 are handled with a small epsilon to avoid
    log(0).

    Args:
        predicted_probs: Predicted probabilities in [0, 1].
        actual_outcomes: Observed outcomes (0 or 1).
        outcome_label:   Optional label.

    Returns:
        LogLossResult

    Raises:
        ValueError: If inputs are inconsistent.
    """
    _validate_inputs(predicted_probs, actual_outcomes)

    n = len(predicted_probs)
    if n == 0:
        return LogLossResult(
            log_loss=float("nan"), n_samples=0, outcome_label=outcome_label
        )

    total = 0.0
    for p, o in zip(predicted_probs, actual_outcomes):
        p_clipped = max(LOG_EPSILON, min(1.0 - LOG_EPSILON, p))
        total += o * math.log(p_clipped) + (1 - o) * math.log(1.0 - p_clipped)

    ll = -total / n
    return LogLossResult(log_loss=ll, n_samples=n, outcome_label=outcome_label)


def log_loss_multiclass(
    predicted_probs: List[List[float]],
    actual_outcomes: List[List[int]],
    outcome_label: str = "",
) -> LogLossResult:
    """Compute multiclass log loss.

    LL = -mean(sum_k(y_ik * log(p_ik)))

    Args:
        predicted_probs: List of probability vectors, each summing to ~1.
        actual_outcomes: List of one-hot vectors (one 1, rest 0).
        outcome_label:   Optional label.

    Returns:
        LogLossResult

    Raises:
        ValueError: If inputs are inconsistent.
    """
    if len(predicted_probs) != len(actual_outcomes):
        raise ValueError(
            f"predicted_probs and actual_outcomes must have the same length "
            f"({len(predicted_probs)} vs {len(actual_outcomes)})"
        )

    n = len(predicted_probs)
    if n == 0:
        return LogLossResult(
            log_loss=float("nan"), n_samples=0, outcome_label=outcome_label
        )

    # Validate class count consistency
    if predicted_probs and actual_outcomes:
        n_classes_pred = len(predicted_probs[0])
        n_classes_act = len(actual_outcomes[0])
        if n_classes_pred != n_classes_act:
            raise ValueError(
                f"Inconsistent number of classes: predicted={n_classes_pred}, "
                f"actual={n_classes_act}"
            )

    total = 0.0
    for probs, outcomes in zip(predicted_probs, actual_outcomes):
        for p, y in zip(probs, outcomes):
            if not (0.0 <= p <= 1.0):
                raise ValueError(f"Probability {p} is outside [0, 1]")
            if y not in (0, 1):
                raise ValueError(f"Outcome {y} must be 0 or 1")
            p_clipped = max(LOG_EPSILON, min(1.0 - LOG_EPSILON, p))
            total += y * math.log(p_clipped)

    ll = -total / n
    return LogLossResult(log_loss=ll, n_samples=n, outcome_label=outcome_label)


def reliability_data(
    predicted_probs: List[float],
    actual_outcomes: List[int],
    n_bins: int = 10,
    outcome_label: str = "",
) -> ReliabilityData:
    """Generate reliability diagram data.

    Bins predicted probabilities into *n_bins* equal-width bins and
    computes the mean predicted probability and empirical fraction of
    positive outcomes in each bin.

    Args:
        predicted_probs: Predicted probabilities in [0, 1].
        actual_outcomes: Observed outcomes (0 or 1).
        n_bins:          Number of calibration bins (default: 10).
        outcome_label:   Optional label.

    Returns:
        ReliabilityData with non-empty bins.

    Raises:
        ValueError: If inputs are inconsistent or n_bins < 1.
    """
    if n_bins < 1:
        raise ValueError(f"n_bins must be >= 1, got {n_bins}")

    _validate_inputs(predicted_probs, actual_outcomes)

    n = len(predicted_probs)
    if n == 0:
        return ReliabilityData(
            bins=[], n_samples=0, n_bins=n_bins, outcome_label=outcome_label
        )

    # Assign each sample to a bin
    bin_size = 1.0 / n_bins
    bin_preds: List[List[float]] = [[] for _ in range(n_bins)]
    bin_acts: List[List[int]] = [[] for _ in range(n_bins)]

    for p, o in zip(predicted_probs, actual_outcomes):
        bin_idx = min(int(p / bin_size), n_bins - 1)
        bin_preds[bin_idx].append(p)
        bin_acts[bin_idx].append(o)

    bins = []
    for i in range(n_bins):
        if not bin_preds[i]:
            continue  # Skip empty bins

        mean_pred = sum(bin_preds[i]) / len(bin_preds[i])
        frac_pos = sum(bin_acts[i]) / len(bin_acts[i])

        bins.append(ReliabilityBin(
            bin_lower=i * bin_size,
            bin_upper=(i + 1) * bin_size,
            mean_predicted=mean_pred,
            fraction_positive=frac_pos,
            n_samples=len(bin_preds[i]),
        ))

    return ReliabilityData(
        bins=bins, n_samples=n, n_bins=n_bins, outcome_label=outcome_label
    )


def calibration_error(
    predicted_probs: List[float],
    actual_outcomes: List[int],
    n_bins: int = 10,
    outcome_label: str = "",
) -> CalibrationErrorResult:
    """Compute the Expected Calibration Error (ECE).

    ECE = sum_b( |B_b| / N * |acc_b - conf_b| )

    where:
      B_b    = samples in bin b
      N      = total samples
      acc_b  = fraction positive in bin b  (empirical probability)
      conf_b = mean predicted probability in bin b

    Args:
        predicted_probs: Predicted probabilities.
        actual_outcomes: Observed outcomes (0 or 1).
        n_bins:          Number of bins.
        outcome_label:   Optional label.

    Returns:
        CalibrationErrorResult

    Raises:
        ValueError: If inputs are inconsistent.
    """
    rel = reliability_data(
        predicted_probs, actual_outcomes, n_bins=n_bins, outcome_label=outcome_label
    )

    n = rel.n_samples
    if n == 0:
        return CalibrationErrorResult(
            ece=float("nan"),
            n_samples=0,
            n_bins=n_bins,
            outcome_label=outcome_label,
            bins=[],
        )

    ece_value = sum(
        (b.n_samples / n) * abs(b.fraction_positive - b.mean_predicted)
        for b in rel.bins
    )

    return CalibrationErrorResult(
        ece=ece_value,
        n_samples=n,
        n_bins=n_bins,
        outcome_label=outcome_label,
        bins=rel.bins,
    )


# ---------------------------------------------------------------------------
# High-level evaluators
# ---------------------------------------------------------------------------

def evaluate_binary(
    predicted_probs: List[float],
    actual_outcomes: List[int],
    outcome_label: str = "",
    n_bins: int = 10,
) -> BinaryCalibrationResult:
    """Full calibration evaluation for a binary probability series.

    Args:
        predicted_probs: Predicted probabilities.
        actual_outcomes: Observed binary outcomes (0 or 1).
        outcome_label:   Label for the outcome being evaluated.
        n_bins:          Bins for reliability / ECE calculation.

    Returns:
        BinaryCalibrationResult
    """
    bs = brier_score(predicted_probs, actual_outcomes, outcome_label)
    ll = log_loss_binary(predicted_probs, actual_outcomes, outcome_label)
    rel = reliability_data(predicted_probs, actual_outcomes, n_bins=n_bins,
                           outcome_label=outcome_label)
    ce = calibration_error(predicted_probs, actual_outcomes, n_bins=n_bins,
                           outcome_label=outcome_label)

    return BinaryCalibrationResult(
        outcome_label=outcome_label,
        brier=bs,
        log_loss=ll,
        reliability=rel,
        calibration_error=ce,
    )


def evaluate_1x2(
    predicted_probs: List[Tuple[float, float, float]],
    actual_outcomes: List[str],
    n_bins: int = 10,
) -> Multiclass1X2CalibrationResult:
    """Evaluate calibration for 1X2 predictions.

    Args:
        predicted_probs: List of (home_win, draw, away_win) tuples.
                         Each tuple must sum approximately to 1.
        actual_outcomes: List of actual outcomes: "home", "draw", or "away".
        n_bins:          Bins for calibration metrics.

    Returns:
        Multiclass1X2CalibrationResult

    Raises:
        ValueError: If inputs have inconsistent lengths or invalid outcomes.
    """
    if len(predicted_probs) != len(actual_outcomes):
        raise ValueError(
            f"predicted_probs and actual_outcomes must have same length "
            f"({len(predicted_probs)} vs {len(actual_outcomes)})"
        )

    valid_outcomes = {"home", "draw", "away"}
    for o in actual_outcomes:
        if o not in valid_outcomes:
            raise ValueError(
                f"Invalid outcome '{o}'. Must be one of {valid_outcomes}"
            )

    n = len(predicted_probs)

    # Decompose into binary series
    home_probs = [p[0] for p in predicted_probs]
    draw_probs = [p[1] for p in predicted_probs]
    away_probs = [p[2] for p in predicted_probs]

    home_acts = [1 if o == "home" else 0 for o in actual_outcomes]
    draw_acts = [1 if o == "draw" else 0 for o in actual_outcomes]
    away_acts = [1 if o == "away" else 0 for o in actual_outcomes]

    home_cal = evaluate_binary(home_probs, home_acts, "home_win", n_bins=n_bins)
    draw_cal = evaluate_binary(draw_probs, draw_acts, "draw", n_bins=n_bins)
    away_cal = evaluate_binary(away_probs, away_acts, "away_win", n_bins=n_bins)

    # Multiclass log loss
    prob_vectors = [[p[0], p[1], p[2]] for p in predicted_probs]
    outcome_vectors = [
        [1 if o == "home" else 0, 1 if o == "draw" else 0, 1 if o == "away" else 0]
        for o in actual_outcomes
    ]
    multi_ll = log_loss_multiclass(prob_vectors, outcome_vectors, "1x2")

    return Multiclass1X2CalibrationResult(
        home_win=home_cal,
        draw=draw_cal,
        away_win=away_cal,
        multiclass_log_loss=multi_ll,
        n_samples=n,
    )


# ---------------------------------------------------------------------------
# Calibration scaler stubs (structure for future implementation)
# ---------------------------------------------------------------------------

class PlattScaler:
    """Platt-style sigmoid calibration scaler (structural stub).

    Applies a sigmoid transformation:
        p_cal = 1 / (1 + exp(A * f(x) + B))

    Parameters A and B are fitted via maximum likelihood on a held-out set.

    NOTE: This is a structural stub.  The fit() method is not yet
    implemented.  Do NOT use this class for actual calibration training
    until the fitting logic is implemented and validated.
    """

    def __init__(self) -> None:
        self.A: Optional[float] = None
        self.B: Optional[float] = None
        self._is_fitted: bool = False

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    def fit(
        self,
        raw_probs: List[float],
        actual_outcomes: List[int],
    ) -> "PlattScaler":
        """Fit Platt scaling parameters.

        NOT YET IMPLEMENTED.

        Raises:
            NotImplementedError: Always, until implemented.
        """
        raise NotImplementedError(
            "PlattScaler.fit() is not yet implemented. "
            "This is a structural stub for future calibration work."
        )

    def transform(self, raw_probs: List[float]) -> List[float]:
        """Apply fitted scaling to raw probabilities.

        Raises:
            RuntimeError: If scaler has not been fitted.
        """
        if not self._is_fitted:
            raise RuntimeError(
                "PlattScaler must be fitted before calling transform()."
            )
        return raw_probs  # pragma: no cover


class IsotonicScaler:
    """Isotonic regression calibration scaler (structural stub).

    Fits a non-decreasing step function to calibrate probabilities.

    NOTE: This is a structural stub.  The fit() method is not yet
    implemented.  Do NOT use this class for actual calibration training
    until the fitting logic is implemented and validated.
    """

    def __init__(self) -> None:
        self._bins: Optional[List[Tuple[float, float]]] = None
        self._is_fitted: bool = False

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    def fit(
        self,
        raw_probs: List[float],
        actual_outcomes: List[int],
    ) -> "IsotonicScaler":
        """Fit isotonic regression.

        NOT YET IMPLEMENTED.

        Raises:
            NotImplementedError: Always, until implemented.
        """
        raise NotImplementedError(
            "IsotonicScaler.fit() is not yet implemented. "
            "This is a structural stub for future calibration work."
        )

    def transform(self, raw_probs: List[float]) -> List[float]:
        """Apply fitted scaling to raw probabilities.

        Raises:
            RuntimeError: If scaler has not been fitted.
        """
        if not self._is_fitted:
            raise RuntimeError(
                "IsotonicScaler must be fitted before calling transform()."
            )
        return raw_probs  # pragma: no cover


# ---------------------------------------------------------------------------
# Internal validation
# ---------------------------------------------------------------------------

def _validate_inputs(
    predicted_probs: List[float],
    actual_outcomes: List[int],
) -> None:
    """Validate predicted probabilities and binary outcomes.

    Raises:
        ValueError: If lengths differ, any prob is outside [0,1],
                    or any outcome is not 0 or 1.
    """
    if len(predicted_probs) != len(actual_outcomes):
        raise ValueError(
            f"predicted_probs and actual_outcomes must have the same length "
            f"({len(predicted_probs)} vs {len(actual_outcomes)})"
        )

    for i, p in enumerate(predicted_probs):
        if not (0.0 <= p <= 1.0):
            raise ValueError(
                f"predicted_probs[{i}] = {p!r} is outside [0, 1]"
            )

    for i, o in enumerate(actual_outcomes):
        if o not in (0, 1):
            raise ValueError(
                f"actual_outcomes[{i}] = {o!r} must be 0 or 1"
            )
