"""Model comparison and evaluation foundation.

This module provides a structured layer for comparing prediction models
using backtest and calibration results.

Capabilities:
  - Compare accuracy, Brier score, log loss, calibration error
  - Model ranking with tie handling
  - Per-metric comparison
  - Ensemble vs individual model comparison
  - Sample-size-aware reliability flags
  - Missing metric handling (no crash if a metric is absent)
  - Structured result objects suitable for feeding:
      * Analytics / backtesting pages
      * AI Analyst (via AnalysisContext)
      * Model registry
      * Future automated model selection

Design constraints:
  - Never automatically declare a model "best" without sufficient sample size.
  - Never fabricate statistics.
  - Sample-size warnings are explicit and visible in comparison results.
  - All rankings are deterministic for identical inputs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_RELIABLE_SAMPLES = 30
"""Minimum number of predictions for a metric to be considered reliable."""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RankingMetric(str, Enum):
    """Metric used as the primary ranking criterion."""

    ACCURACY = "accuracy"
    BRIER_SCORE = "brier_score"
    LOG_LOSS = "log_loss"
    CALIBRATION_ERROR = "calibration_error"


class MetricDirection(str, Enum):
    """Whether a metric is better when higher or lower."""

    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


METRIC_DIRECTION: Dict[RankingMetric, MetricDirection] = {
    RankingMetric.ACCURACY:          MetricDirection.HIGHER_IS_BETTER,
    RankingMetric.BRIER_SCORE:       MetricDirection.LOWER_IS_BETTER,
    RankingMetric.LOG_LOSS:          MetricDirection.LOWER_IS_BETTER,
    RankingMetric.CALIBRATION_ERROR: MetricDirection.LOWER_IS_BETTER,
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ModelMetricSnapshot:
    """A single model's metric values at a point in time.

    All metric fields are Optional — missing metrics are represented as
    None and must not be imputed or fabricated.
    """

    model_id: str
    model_version: str
    model_type: str
    """String type tag (e.g. 'poisson', 'elo', 'ensemble')."""

    n_predictions: int
    """Sample size the metrics are based on."""

    # Core metrics
    accuracy: Optional[float] = None
    brier_score: Optional[float] = None
    log_loss: Optional[float] = None
    calibration_error: Optional[float] = None

    # Per-outcome accuracy
    home_win_accuracy: Optional[float] = None
    draw_accuracy: Optional[float] = None
    away_win_accuracy: Optional[float] = None

    # Ensemble flag
    is_ensemble: bool = False

    # Snapshot timestamp
    captured_at: datetime = field(default_factory=datetime.now)

    @property
    def is_reliable(self) -> bool:
        """Return True when the sample is large enough to trust metrics."""
        return self.n_predictions >= MIN_RELIABLE_SAMPLES

    def get_metric(self, metric: RankingMetric) -> Optional[float]:
        """Return the value for a given ranking metric."""
        return {
            RankingMetric.ACCURACY:          self.accuracy,
            RankingMetric.BRIER_SCORE:       self.brier_score,
            RankingMetric.LOG_LOSS:          self.log_loss,
            RankingMetric.CALIBRATION_ERROR: self.calibration_error,
        }[metric]


@dataclass
class MetricComparison:
    """Pairwise comparison of two models on a single metric."""

    metric: RankingMetric
    model_a_id: str
    model_b_id: str

    model_a_value: Optional[float]
    model_b_value: Optional[float]

    winner: Optional[str]
    """model_id of the better model, or None if tied / insufficient data."""

    is_tie: bool
    tie_threshold: float
    """Difference smaller than this is treated as a tie."""

    both_reliable: bool
    """True only when both models have sufficient sample size."""

    difference: Optional[float]
    """Absolute difference |A - B|, None if either value is missing."""


@dataclass
class ModelRanking:
    """A single model's position in the comparison ranking."""

    rank: int
    """1 = best. Ties share the same rank."""

    model_id: str
    model_version: str
    model_type: str
    is_ensemble: bool

    primary_metric: RankingMetric
    primary_metric_value: Optional[float]

    is_reliable: bool
    n_predictions: int

    reliability_warning: Optional[str] = None
    """Populated when sample size is insufficient."""


@dataclass
class ComparisonResult:
    """Full comparison result across all provided models.

    Designed to be passed directly into AnalysisContext,
    the AI Analyst, or the model registry.
    """

    models: List[ModelMetricSnapshot]
    rankings: List[ModelRanking]
    pairwise: List[MetricComparison]

    primary_metric: RankingMetric
    n_models: int

    # The top-ranked model (None when no reliable model exists)
    best_model_id: Optional[str]
    best_is_reliable: bool

    # Warnings
    warnings: List[str]

    computed_at: datetime = field(default_factory=datetime.now)

    @property
    def has_reliable_winner(self) -> bool:
        return self.best_model_id is not None and self.best_is_reliable


# ---------------------------------------------------------------------------
# Comparison engine
# ---------------------------------------------------------------------------

class ModelComparator:
    """Compare and rank prediction models by evaluation metrics.

    Usage:
        comparator = ModelComparator(primary_metric=RankingMetric.BRIER_SCORE)
        result = comparator.compare(snapshots)

    No model is declared "best" without sufficient sample size.
    Rankings are always deterministic (sorted by (metric, model_id) for ties).
    """

    def __init__(
        self,
        primary_metric: RankingMetric = RankingMetric.BRIER_SCORE,
        tie_threshold: float = 1e-4,
        min_reliable: int = MIN_RELIABLE_SAMPLES,
    ):
        """Initialise the comparator.

        Args:
            primary_metric: Metric used for primary ranking.
            tie_threshold:  Differences smaller than this are ties.
            min_reliable:   Minimum predictions for reliability.
        """
        self.primary_metric = primary_metric
        self.tie_threshold = tie_threshold
        self.min_reliable = min_reliable

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compare(
        self,
        snapshots: List[ModelMetricSnapshot],
    ) -> ComparisonResult:
        """Compare all provided models and return ranked results.

        Args:
            snapshots: List of ModelMetricSnapshot objects.
                       May include both individual and ensemble models.

        Returns:
            ComparisonResult with rankings, pairwise comparisons,
            and warnings.
        """
        warnings: List[str] = []

        if not snapshots:
            return ComparisonResult(
                models=[],
                rankings=[],
                pairwise=[],
                primary_metric=self.primary_metric,
                n_models=0,
                best_model_id=None,
                best_is_reliable=False,
                warnings=["No models provided for comparison."],
            )

        # Warn on unreliable models
        for s in snapshots:
            if not s.is_reliable:
                warnings.append(
                    f"Model '{s.model_id}' has only {s.n_predictions} predictions "
                    f"(minimum {self.min_reliable} for reliable metrics). "
                    "Rankings involving this model may be misleading."
                )

        # Rank models
        rankings = self._rank(snapshots)

        # Pairwise comparisons
        pairwise = self._pairwise(snapshots)

        # Identify best model
        best_id: Optional[str] = None
        best_reliable = False

        if rankings:
            top = rankings[0]
            if top.primary_metric_value is not None:
                best_id = top.model_id
                best_reliable = top.is_reliable
            else:
                warnings.append(
                    f"Top-ranked model '{top.model_id}' has no value for "
                    f"'{self.primary_metric}'. No reliable winner identified."
                )

        if best_id is not None and not best_reliable:
            warnings.append(
                f"Best model '{best_id}' is based on insufficient sample size "
                f"({rankings[0].n_predictions} < {self.min_reliable}). "
                "Do not use this ranking for production decisions."
            )

        return ComparisonResult(
            models=list(snapshots),
            rankings=rankings,
            pairwise=pairwise,
            primary_metric=self.primary_metric,
            n_models=len(snapshots),
            best_model_id=best_id,
            best_is_reliable=best_reliable,
            warnings=warnings,
        )

    def compare_metric(
        self,
        snapshot_a: ModelMetricSnapshot,
        snapshot_b: ModelMetricSnapshot,
        metric: RankingMetric,
    ) -> MetricComparison:
        """Pairwise comparison of two models on a single metric."""
        val_a = snapshot_a.get_metric(metric)
        val_b = snapshot_b.get_metric(metric)
        both_reliable = snapshot_a.is_reliable and snapshot_b.is_reliable

        if val_a is None or val_b is None:
            return MetricComparison(
                metric=metric,
                model_a_id=snapshot_a.model_id,
                model_b_id=snapshot_b.model_id,
                model_a_value=val_a,
                model_b_value=val_b,
                winner=None,
                is_tie=False,
                tie_threshold=self.tie_threshold,
                both_reliable=both_reliable,
                difference=None,
            )

        diff = abs(val_a - val_b)
        is_tie = diff <= self.tie_threshold

        if is_tie:
            winner = None
        else:
            direction = METRIC_DIRECTION[metric]
            if direction == MetricDirection.HIGHER_IS_BETTER:
                winner = snapshot_a.model_id if val_a > val_b else snapshot_b.model_id
            else:
                winner = snapshot_a.model_id if val_a < val_b else snapshot_b.model_id

        return MetricComparison(
            metric=metric,
            model_a_id=snapshot_a.model_id,
            model_b_id=snapshot_b.model_id,
            model_a_value=val_a,
            model_b_value=val_b,
            winner=winner,
            is_tie=is_tie,
            tie_threshold=self.tie_threshold,
            both_reliable=both_reliable,
            difference=diff,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _rank(
        self,
        snapshots: List[ModelMetricSnapshot],
    ) -> List[ModelRanking]:
        """Rank models by the primary metric.

        Models without a primary metric value are ranked last.
        Ties share the same rank.  Tie-breaking uses model_id for
        determinism.
        """
        metric = self.primary_metric
        direction = METRIC_DIRECTION[metric]

        def sort_key(s: ModelMetricSnapshot) -> Tuple:
            val = s.get_metric(metric)
            if val is None:
                return (1, 0.0, s.model_id)  # Last
            if direction == MetricDirection.LOWER_IS_BETTER:
                return (0, val, s.model_id)
            else:
                return (0, -val, s.model_id)  # Negate so sort is ascending

        sorted_snapshots = sorted(snapshots, key=sort_key)

        rankings: List[ModelRanking] = []
        current_rank = 1

        for i, s in enumerate(sorted_snapshots):
            if i > 0:
                prev_val = sorted_snapshots[i - 1].get_metric(metric)
                curr_val = s.get_metric(metric)
                if prev_val is not None and curr_val is not None:
                    if abs(curr_val - prev_val) > self.tie_threshold:
                        current_rank = i + 1
                elif curr_val is None and prev_val is not None:
                    current_rank = i + 1

            warning = None
            if not s.is_reliable:
                warning = (
                    f"Insufficient sample size ({s.n_predictions} < {self.min_reliable})"
                )

            rankings.append(
                ModelRanking(
                    rank=current_rank,
                    model_id=s.model_id,
                    model_version=s.model_version,
                    model_type=s.model_type,
                    is_ensemble=s.is_ensemble,
                    primary_metric=metric,
                    primary_metric_value=s.get_metric(metric),
                    is_reliable=s.is_reliable,
                    n_predictions=s.n_predictions,
                    reliability_warning=warning,
                )
            )

        return rankings

    def _pairwise(
        self,
        snapshots: List[ModelMetricSnapshot],
    ) -> List[MetricComparison]:
        """Generate all pairwise comparisons on the primary metric."""
        comparisons: List[MetricComparison] = []
        n = len(snapshots)
        for i in range(n):
            for j in range(i + 1, n):
                comp = self.compare_metric(
                    snapshots[i], snapshots[j], self.primary_metric
                )
                comparisons.append(comp)
        return comparisons


# ---------------------------------------------------------------------------
# Snapshot builder helpers
# ---------------------------------------------------------------------------

def snapshot_from_backtest_metrics(
    metrics,  # BacktestMetrics
    model_type: str,
    is_ensemble: bool = False,
) -> ModelMetricSnapshot:
    """Convert a BacktestMetrics object to a ModelMetricSnapshot.

    Args:
        metrics:     BacktestMetrics from the backtesting engine.
        model_type:  String model type (e.g. 'poisson', 'elo').
        is_ensemble: True if the model is an ensemble.

    Returns:
        ModelMetricSnapshot ready for comparison.
    """
    return ModelMetricSnapshot(
        model_id=metrics.model_id,
        model_version=metrics.model_version,
        model_type=model_type,
        n_predictions=metrics.n_predictions,
        accuracy=metrics.accuracy,
        brier_score=metrics.brier_score,
        log_loss=metrics.log_loss,
        calibration_error=metrics.calibration_error,
        home_win_accuracy=metrics.home_win_accuracy,
        draw_accuracy=metrics.draw_accuracy,
        away_win_accuracy=metrics.away_win_accuracy,
        is_ensemble=is_ensemble,
    )
