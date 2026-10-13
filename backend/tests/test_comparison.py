"""Tests for the model comparison and evaluation layer.

Covers:
- ModelMetricSnapshot: creation, is_reliable flag, get_metric
- ModelComparator: ranking, pairwise comparisons, tie handling
- Missing metric handling (None values)
- Sample-size awareness (no "best" declared for unreliable models)
- Ensemble vs individual model flagging
- Deterministic ranking
- ComparisonResult structure
- snapshot_from_backtest_metrics helper
- RankingMetric direction (lower/higher is better)
"""

import pytest
from datetime import datetime
from typing import Optional

from app.prediction.comparison import (
    ModelComparator,
    ModelMetricSnapshot,
    ComparisonResult,
    MetricComparison,
    ModelRanking,
    RankingMetric,
    MetricDirection,
    METRIC_DIRECTION,
    snapshot_from_backtest_metrics,
    MIN_RELIABLE_SAMPLES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _snap(
    model_id: str = "model_a",
    model_type: str = "poisson",
    n: int = 100,
    accuracy: Optional[float] = 0.50,
    brier: Optional[float] = 0.22,
    log_loss: Optional[float] = 1.10,
    ece: Optional[float] = 0.08,
    is_ensemble: bool = False,
) -> ModelMetricSnapshot:
    return ModelMetricSnapshot(
        model_id=model_id,
        model_version="1.0",
        model_type=model_type,
        n_predictions=n,
        accuracy=accuracy,
        brier_score=brier,
        log_loss=log_loss,
        calibration_error=ece,
        is_ensemble=is_ensemble,
    )


# ---------------------------------------------------------------------------
# ModelMetricSnapshot
# ---------------------------------------------------------------------------

class TestModelMetricSnapshot:

    def test_is_reliable_above_threshold(self):
        s = _snap(n=MIN_RELIABLE_SAMPLES + 1)
        assert s.is_reliable is True

    def test_is_reliable_at_threshold(self):
        s = _snap(n=MIN_RELIABLE_SAMPLES)
        assert s.is_reliable is True

    def test_is_reliable_below_threshold(self):
        s = _snap(n=MIN_RELIABLE_SAMPLES - 1)
        assert s.is_reliable is False

    def test_get_metric_accuracy(self):
        s = _snap(accuracy=0.55)
        assert s.get_metric(RankingMetric.ACCURACY) == 0.55

    def test_get_metric_brier(self):
        s = _snap(brier=0.22)
        assert s.get_metric(RankingMetric.BRIER_SCORE) == 0.22

    def test_get_metric_log_loss(self):
        s = _snap(log_loss=1.10)
        assert s.get_metric(RankingMetric.LOG_LOSS) == 1.10

    def test_get_metric_ece(self):
        s = _snap(ece=0.07)
        assert s.get_metric(RankingMetric.CALIBRATION_ERROR) == 0.07

    def test_get_metric_none(self):
        s = _snap(brier=None)
        assert s.get_metric(RankingMetric.BRIER_SCORE) is None

    def test_ensemble_flag(self):
        s = _snap(is_ensemble=True)
        assert s.is_ensemble is True

    def test_non_ensemble_flag(self):
        s = _snap(is_ensemble=False)
        assert s.is_ensemble is False


# ---------------------------------------------------------------------------
# RankingMetric directions
# ---------------------------------------------------------------------------

class TestMetricDirections:

    def test_accuracy_higher_is_better(self):
        assert METRIC_DIRECTION[RankingMetric.ACCURACY].value == "higher_is_better"

    def test_brier_lower_is_better(self):
        assert METRIC_DIRECTION[RankingMetric.BRIER_SCORE].value == "lower_is_better"

    def test_log_loss_lower_is_better(self):
        assert METRIC_DIRECTION[RankingMetric.LOG_LOSS].value == "lower_is_better"

    def test_ece_lower_is_better(self):
        assert METRIC_DIRECTION[RankingMetric.CALIBRATION_ERROR].value == "lower_is_better"


# ---------------------------------------------------------------------------
# ModelComparator — basic ranking
# ---------------------------------------------------------------------------

class TestModelComparatorRanking:

    def test_empty_snapshots(self):
        comp = ModelComparator()
        result = comp.compare([])
        assert result.n_models == 0
        assert result.best_model_id is None
        assert len(result.warnings) > 0

    def test_single_model(self):
        comp = ModelComparator()
        result = comp.compare([_snap("m1")])
        assert result.n_models == 1
        assert len(result.rankings) == 1
        assert result.rankings[0].rank == 1

    def test_best_model_is_lowest_brier(self):
        """With BRIER_SCORE metric, lower is better."""
        comp = ModelComparator(primary_metric=RankingMetric.BRIER_SCORE)
        snapshots = [
            _snap("poisson", brier=0.25),
            _snap("elo", brier=0.20),     # best
            _snap("dc", brier=0.22),
        ]
        result = comp.compare(snapshots)
        assert result.best_model_id == "elo"

    def test_best_model_is_highest_accuracy(self):
        comp = ModelComparator(primary_metric=RankingMetric.ACCURACY)
        snapshots = [
            _snap("m1", accuracy=0.48),
            _snap("m2", accuracy=0.55),   # best
            _snap("m3", accuracy=0.51),
        ]
        result = comp.compare(snapshots)
        assert result.best_model_id == "m2"

    def test_rankings_are_sorted_correctly_brier(self):
        comp = ModelComparator(primary_metric=RankingMetric.BRIER_SCORE)
        snapshots = [
            _snap("m1", brier=0.30),
            _snap("m2", brier=0.20),
            _snap("m3", brier=0.25),
        ]
        result = comp.compare(snapshots)
        # Rank 1 should be lowest brier (m2=0.20)
        assert result.rankings[0].model_id == "m2"
        assert result.rankings[0].rank == 1

    def test_rank_3_models_no_tie(self):
        comp = ModelComparator(primary_metric=RankingMetric.BRIER_SCORE)
        snapshots = [
            _snap("m1", brier=0.30),
            _snap("m2", brier=0.20),
            _snap("m3", brier=0.25),
        ]
        result = comp.compare(snapshots)
        ranks = {r.model_id: r.rank for r in result.rankings}
        assert ranks["m2"] == 1
        assert ranks["m3"] == 2
        assert ranks["m1"] == 3


# ---------------------------------------------------------------------------
# Tie handling
# ---------------------------------------------------------------------------

class TestTieHandling:

    def test_ties_share_same_rank(self):
        comp = ModelComparator(
            primary_metric=RankingMetric.BRIER_SCORE,
            tie_threshold=0.01,
        )
        snapshots = [
            _snap("m1", brier=0.200),
            _snap("m2", brier=0.201),  # within threshold of m1
            _snap("m3", brier=0.250),
        ]
        result = comp.compare(snapshots)
        # m1 and m2 should share rank 1
        rank_map = {r.model_id: r.rank for r in result.rankings}
        assert rank_map["m1"] == rank_map["m2"]
        assert rank_map["m3"] > rank_map["m1"]

    def test_pairwise_tie_winner_is_none(self):
        comp = ModelComparator(
            primary_metric=RankingMetric.BRIER_SCORE,
            tie_threshold=0.01,
        )
        a = _snap("m1", brier=0.200)
        b = _snap("m2", brier=0.201)
        comp_result = comp.compare_metric(a, b, RankingMetric.BRIER_SCORE)
        assert comp_result.is_tie is True
        assert comp_result.winner is None

    def test_pairwise_clear_winner(self):
        comp = ModelComparator(primary_metric=RankingMetric.BRIER_SCORE)
        a = _snap("m1", brier=0.20)
        b = _snap("m2", brier=0.30)
        comp_result = comp.compare_metric(a, b, RankingMetric.BRIER_SCORE)
        assert comp_result.winner == "m1"
        assert comp_result.is_tie is False

    def test_pairwise_higher_accuracy_wins(self):
        comp = ModelComparator(primary_metric=RankingMetric.ACCURACY)
        a = _snap("m1", accuracy=0.55)
        b = _snap("m2", accuracy=0.48)
        comp_result = comp.compare_metric(a, b, RankingMetric.ACCURACY)
        assert comp_result.winner == "m1"


# ---------------------------------------------------------------------------
# Missing metrics
# ---------------------------------------------------------------------------

class TestMissingMetrics:

    def test_missing_primary_metric_ranked_last(self):
        comp = ModelComparator(primary_metric=RankingMetric.BRIER_SCORE)
        snapshots = [
            _snap("m1", brier=0.25),
            _snap("m2", brier=None),   # missing
        ]
        result = comp.compare(snapshots)
        rank_map = {r.model_id: r.rank for r in result.rankings}
        assert rank_map["m1"] < rank_map["m2"]

    def test_missing_metric_pairwise_winner_none(self):
        comp = ModelComparator(primary_metric=RankingMetric.BRIER_SCORE)
        a = _snap("m1", brier=0.25)
        b = _snap("m2", brier=None)
        result = comp.compare_metric(a, b, RankingMetric.BRIER_SCORE)
        assert result.winner is None
        assert result.difference is None

    def test_both_missing_both_tied_rank(self):
        comp = ModelComparator(primary_metric=RankingMetric.BRIER_SCORE)
        snapshots = [
            _snap("m1", brier=None),
            _snap("m2", brier=None),
        ]
        result = comp.compare(snapshots)
        # Both should be at the same rank since both have None
        assert result.rankings[0].rank == result.rankings[1].rank


# ---------------------------------------------------------------------------
# Sample size awareness
# ---------------------------------------------------------------------------

class TestSampleSizeAwareness:

    def test_unreliable_model_has_warning(self):
        comp = ModelComparator()
        small = _snap("m1", n=5)
        result = comp.compare([small])
        assert any("m1" in w for w in result.warnings)

    def test_best_with_insufficient_data_has_warning(self):
        comp = ModelComparator(primary_metric=RankingMetric.BRIER_SCORE)
        small = _snap("m1", n=5, brier=0.10)  # best metric but unreliable
        large = _snap("m2", n=100, brier=0.25)
        result = comp.compare([small, large])
        assert result.best_model_id == "m1"
        assert result.best_is_reliable is False
        assert any("m1" in w for w in result.warnings)

    def test_reliable_model_no_warning(self):
        comp = ModelComparator()
        large = _snap("m1", n=MIN_RELIABLE_SAMPLES + 10)
        result = comp.compare([large])
        assert all("m1" not in w for w in result.warnings)

    def test_has_reliable_winner_false_when_unreliable(self):
        comp = ModelComparator(primary_metric=RankingMetric.BRIER_SCORE)
        small = _snap("m1", n=5, brier=0.10)
        result = comp.compare([small])
        assert result.has_reliable_winner is False

    def test_has_reliable_winner_true_when_reliable(self):
        comp = ModelComparator(primary_metric=RankingMetric.BRIER_SCORE)
        large = _snap("m1", n=100, brier=0.20)
        result = comp.compare([large])
        assert result.has_reliable_winner is True


# ---------------------------------------------------------------------------
# Ensemble vs individual comparison
# ---------------------------------------------------------------------------

class TestEnsembleComparison:

    def test_ensemble_flag_preserved_in_ranking(self):
        comp = ModelComparator(primary_metric=RankingMetric.BRIER_SCORE)
        snapshots = [
            _snap("poisson", is_ensemble=False, brier=0.25),
            _snap("ensemble_v1", is_ensemble=True, brier=0.22),
        ]
        result = comp.compare(snapshots)
        ranking_map = {r.model_id: r for r in result.rankings}
        assert ranking_map["ensemble_v1"].is_ensemble is True
        assert ranking_map["poisson"].is_ensemble is False

    def test_ensemble_can_win(self):
        comp = ModelComparator(primary_metric=RankingMetric.BRIER_SCORE)
        snapshots = [
            _snap("poisson", is_ensemble=False, brier=0.25),
            _snap("ensemble_v1", is_ensemble=True, brier=0.20),
        ]
        result = comp.compare(snapshots)
        assert result.best_model_id == "ensemble_v1"

    def test_individual_can_beat_ensemble(self):
        comp = ModelComparator(primary_metric=RankingMetric.BRIER_SCORE)
        snapshots = [
            _snap("poisson", is_ensemble=False, brier=0.18),
            _snap("ensemble_v1", is_ensemble=True, brier=0.22),
        ]
        result = comp.compare(snapshots)
        assert result.best_model_id == "poisson"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestComparisonDeterminism:

    def test_same_inputs_same_rankings(self):
        comp = ModelComparator(primary_metric=RankingMetric.BRIER_SCORE)
        snapshots = [
            _snap("m1", brier=0.25),
            _snap("m2", brier=0.20),
            _snap("m3", brier=0.22),
        ]
        r1 = comp.compare(snapshots)
        r2 = comp.compare(snapshots)
        for ra, rb in zip(r1.rankings, r2.rankings):
            assert ra.model_id == rb.model_id
            assert ra.rank == rb.rank

    def test_order_independent(self):
        """Reversing input order should produce the same ranking."""
        comp = ModelComparator(primary_metric=RankingMetric.BRIER_SCORE)
        snapshots = [
            _snap("m1", brier=0.25),
            _snap("m2", brier=0.20),
            _snap("m3", brier=0.22),
        ]
        r1 = comp.compare(snapshots)
        r2 = comp.compare(list(reversed(snapshots)))
        ranks1 = {r.model_id: r.rank for r in r1.rankings}
        ranks2 = {r.model_id: r.rank for r in r2.rankings}
        assert ranks1 == ranks2


# ---------------------------------------------------------------------------
# snapshot_from_backtest_metrics
# ---------------------------------------------------------------------------

class TestSnapshotFromBacktestMetrics:

    def _make_metrics(self, model_id="m1", n=50):
        from app.prediction.backtest import BacktestMetrics
        return BacktestMetrics(
            model_id=model_id,
            model_version="1.0",
            n_predictions=n,
            accuracy=0.50,
            brier_score=0.23,
            log_loss=1.05,
            calibration_error=0.07,
            is_reliable=n >= 30,
        )

    def test_converts_correctly(self):
        metrics = self._make_metrics(n=50)
        snap = snapshot_from_backtest_metrics(metrics, model_type="poisson")
        assert snap.model_id == "m1"
        assert snap.model_type == "poisson"
        assert snap.n_predictions == 50
        assert snap.accuracy == 0.50
        assert snap.brier_score == 0.23
        assert snap.log_loss == 1.05
        assert snap.calibration_error == 0.07
        assert snap.is_ensemble is False

    def test_ensemble_flag_set(self):
        metrics = self._make_metrics(n=50)
        snap = snapshot_from_backtest_metrics(metrics, model_type="ensemble", is_ensemble=True)
        assert snap.is_ensemble is True

    def test_is_reliable_matches(self):
        metrics_small = self._make_metrics(n=10)
        snap = snapshot_from_backtest_metrics(metrics_small, "poisson")
        assert snap.is_reliable is False

        metrics_large = self._make_metrics(n=100)
        snap = snapshot_from_backtest_metrics(metrics_large, "poisson")
        assert snap.is_reliable is True
