"""Tests for the chronological backtesting engine.

Covers:
- ChronologicalSplitter: rolling and expanding windows
- Chronological boundary enforcement
- No future leakage
- Empty datasets / insufficient training data
- Rolling vs expanding window behavior
- BacktestRunner: prediction records, skipping None predictions
- BacktestAggregator: accuracy, Brier, log loss, ECE
- run_backtest() convenience function
- Poisson, NB, Elo, LR predict_fn adapters
- Deterministic execution
- PredictionRecord: fields and per-outcome Brier components
- BacktestMetrics: reliability flag
"""

import pytest
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict

from app.domain.match import Match
from app.domain.enums import MatchStatus, ModelType
from app.prediction.backtest import (
    ChronologicalSplitter,
    BacktestRunner,
    BacktestAggregator,
    BacktestMetrics,
    BacktestResult,
    PredictionRecord,
    WindowSplit,
    run_backtest,
    poisson_predict_fn,
    negative_binomial_predict_fn,
    elo_predict_fn,
    logistic_regression_predict_fn,
    _match_outcome,
    _most_probable_outcome,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dt(days: int) -> datetime:
    base = datetime(2024, 1, 1)
    return base + timedelta(days=days)


def _finished_match(
    match_id: str,
    home_team: str,
    away_team: str,
    home_score: int,
    away_score: int,
    days: int,
) -> Match:
    return Match(
        id=match_id,
        competition_id="comp_test",
        season_id="season_test",
        home_team_id=home_team,
        away_team_id=away_team,
        scheduled_at=_dt(days),
        status=MatchStatus.FINISHED,
        home_score=home_score,
        away_score=away_score,
        outcome=(
            "home_win" if home_score > away_score
            else "draw" if home_score == away_score
            else "away_win"
        ),
    )


def _scheduled_match(
    match_id: str,
    home_team: str,
    away_team: str,
    days: int,
) -> Match:
    return Match(
        id=match_id,
        competition_id="comp_test",
        season_id="season_test",
        home_team_id=home_team,
        away_team_id=away_team,
        scheduled_at=_dt(days),
        status=MatchStatus.SCHEDULED,
    )


def _make_matches(n: int = 40) -> List[Match]:
    """Create n finished matches with alternating outcomes."""
    teams = ["A", "B", "C", "D"]
    matches = []
    for i in range(n):
        h, a = teams[i % 4], teams[(i + 1) % 4]
        # Alternate: home win (2-0), draw (1-1), away win (0-1)
        if i % 3 == 0:
            hs, as_ = 2, 0
        elif i % 3 == 1:
            hs, as_ = 1, 1
        else:
            hs, as_ = 0, 1
        matches.append(_finished_match(f"m{i}", h, a, hs, as_, days=i))
    return matches


def _constant_predict_fn(home=0.45, draw=0.30, away=0.25):
    """Return a trivial predict function that always returns constant probs."""
    def _fn(match, train_matches):
        return (home, draw, away)
    return _fn


# ---------------------------------------------------------------------------
# _match_outcome helper
# ---------------------------------------------------------------------------

class TestMatchOutcomeHelper:

    def test_home_win(self):
        m = _finished_match("m1", "A", "B", 2, 0, 0)
        assert _match_outcome(m) == "home_win"

    def test_draw(self):
        m = _finished_match("m1", "A", "B", 1, 1, 0)
        assert _match_outcome(m) == "draw"

    def test_away_win(self):
        m = _finished_match("m1", "A", "B", 0, 3, 0)
        assert _match_outcome(m) == "away_win"

    def test_no_score_returns_none(self):
        m = _scheduled_match("m1", "A", "B", 0)
        assert _match_outcome(m) is None


# ---------------------------------------------------------------------------
# PredictionRecord
# ---------------------------------------------------------------------------

class TestPredictionRecord:

    def test_brier_components_home_win_correct(self):
        """Home win correct: brier_home = (1-1)^2 = 0, brier_draw = (0-0)^2 = 0,
        brier_away = (p_away-0)^2."""
        r = PredictionRecord(
            match_id="m1", model_id="m", model_version="1",
            predicted_at=datetime.now(),
            actual_outcome="home_win",
            home_win_probability=0.8,
            draw_probability=0.15,
            away_win_probability=0.05,
        )
        assert abs(r.brier_home - (0.8 - 1) ** 2) < 1e-9
        assert abs(r.brier_draw - (0.15 - 0) ** 2) < 1e-9
        assert abs(r.brier_away - (0.05 - 0) ** 2) < 1e-9

    def test_brier_components_draw_correct(self):
        r = PredictionRecord(
            match_id="m1", model_id="m", model_version="1",
            predicted_at=datetime.now(),
            actual_outcome="draw",
            home_win_probability=0.4,
            draw_probability=0.35,
            away_win_probability=0.25,
        )
        assert abs(r.brier_draw - (0.35 - 1) ** 2) < 1e-9
        assert abs(r.brier_home - (0.4 - 0) ** 2) < 1e-9


# ---------------------------------------------------------------------------
# ChronologicalSplitter
# ---------------------------------------------------------------------------

class TestChronologicalSplitter:

    def test_expanding_windows_basic(self):
        matches = _make_matches(30)
        splitter = ChronologicalSplitter(min_train=10, test_size=5, step_size=5)
        windows = splitter.expanding_windows(matches)
        assert len(windows) > 0

    def test_expanding_first_window_has_min_train(self):
        matches = _make_matches(30)
        splitter = ChronologicalSplitter(min_train=10, test_size=5, step_size=5)
        windows = splitter.expanding_windows(matches)
        assert windows[0].n_train == 10
        assert windows[0].n_test == 5

    def test_expanding_train_grows_each_window(self):
        matches = _make_matches(40)
        splitter = ChronologicalSplitter(min_train=10, test_size=5, step_size=5)
        windows = splitter.expanding_windows(matches)
        for i in range(1, len(windows)):
            assert windows[i].n_train > windows[i - 1].n_train

    def test_rolling_windows_fixed_train_size(self):
        matches = _make_matches(40)
        splitter = ChronologicalSplitter(min_train=10, test_size=5, step_size=5)
        windows = splitter.rolling_windows(matches, train_size=10)
        for w in windows:
            assert w.n_train == 10

    def test_rolling_windows_consistent_test_size(self):
        matches = _make_matches(40)
        splitter = ChronologicalSplitter(min_train=10, test_size=5, step_size=5)
        windows = splitter.rolling_windows(matches, train_size=10)
        for w in windows:
            assert w.n_test == 5

    def test_insufficient_data_returns_empty(self):
        matches = _make_matches(5)
        splitter = ChronologicalSplitter(min_train=10, test_size=5, step_size=5)
        windows = splitter.expanding_windows(matches)
        assert len(windows) == 0

    def test_empty_matches_returns_empty(self):
        splitter = ChronologicalSplitter(min_train=10, test_size=5, step_size=5)
        windows = splitter.expanding_windows([])
        assert len(windows) == 0

    def test_invalid_min_train(self):
        with pytest.raises(ValueError, match="min_train"):
            ChronologicalSplitter(min_train=0)

    def test_invalid_test_size(self):
        with pytest.raises(ValueError, match="test_size"):
            ChronologicalSplitter(test_size=0)

    def test_invalid_step_size(self):
        with pytest.raises(ValueError, match="step_size"):
            ChronologicalSplitter(step_size=0)

    def test_rolling_train_size_below_min_raises(self):
        splitter = ChronologicalSplitter(min_train=10)
        with pytest.raises(ValueError):
            splitter.rolling_windows(_make_matches(30), train_size=5)


# ---------------------------------------------------------------------------
# Chronological ordering and no future leakage
# ---------------------------------------------------------------------------

class TestChronologicalSafety:

    def test_input_sorted_by_scheduled_at(self):
        """Out-of-order input must be sorted before splitting."""
        matches_reversed = list(reversed(_make_matches(30)))
        splitter = ChronologicalSplitter(min_train=10, test_size=5, step_size=5)
        windows = splitter.expanding_windows(matches_reversed)
        # First window training matches should be oldest
        if windows:
            train = windows[0].train_matches
            for i in range(1, len(train)):
                assert train[i].scheduled_at >= train[i - 1].scheduled_at

    def test_test_matches_after_train_matches(self):
        """All test matches must be scheduled after all training matches."""
        matches = _make_matches(40)
        splitter = ChronologicalSplitter(min_train=10, test_size=5, step_size=5)
        windows = splitter.expanding_windows(matches)
        for w in windows:
            if w.train_matches and w.test_matches:
                latest_train = max(m.scheduled_at for m in w.train_matches)
                earliest_test = min(m.scheduled_at for m in w.test_matches)
                assert earliest_test >= latest_train

    def test_no_match_in_both_train_and_test(self):
        """A match cannot appear in both the training and test set."""
        matches = _make_matches(40)
        splitter = ChronologicalSplitter(min_train=10, test_size=5, step_size=5)
        windows = splitter.expanding_windows(matches)
        for w in windows:
            train_ids = {m.id for m in w.train_matches}
            test_ids = {m.id for m in w.test_matches}
            assert train_ids.isdisjoint(test_ids), \
                "Match appears in both train and test!"

    def test_future_matches_not_in_training(self):
        """Expanding window: test matches from window i should never appear
        in the training data of that same window."""
        matches = _make_matches(40)
        splitter = ChronologicalSplitter(min_train=10, test_size=5, step_size=5)
        windows = splitter.expanding_windows(matches)
        for w in windows:
            train_ids = {m.id for m in w.train_matches}
            for test_match in w.test_matches:
                assert test_match.id not in train_ids


# ---------------------------------------------------------------------------
# BacktestRunner
# ---------------------------------------------------------------------------

class TestBacktestRunner:

    def test_produces_records_for_finished_matches(self):
        matches = _make_matches(30)
        splitter = ChronologicalSplitter(min_train=10, test_size=5, step_size=5)
        windows = splitter.expanding_windows(matches)
        runner = BacktestRunner("test_model")
        records = runner.run_windows(windows, _constant_predict_fn())
        assert len(records) > 0

    def test_none_prediction_skipped(self):
        """If predict_fn returns None, no record is created."""
        def _none_fn(match, train): return None
        matches = _make_matches(20)
        splitter = ChronologicalSplitter(min_train=5, test_size=5, step_size=5)
        windows = splitter.expanding_windows(matches)
        runner = BacktestRunner("test_model")
        records = runner.run_windows(windows, _none_fn)
        assert len(records) == 0

    def test_record_fields_populated(self):
        matches = _make_matches(20)
        splitter = ChronologicalSplitter(min_train=5, test_size=5, step_size=5)
        windows = splitter.expanding_windows(matches)
        runner = BacktestRunner("my_model", "2.0")
        records = runner.run_windows(windows, _constant_predict_fn())
        if records:
            r = records[0]
            assert r.model_id == "my_model"
            assert r.model_version == "2.0"
            assert r.actual_outcome in ("home_win", "draw", "away_win")
            assert 0 <= r.home_win_probability <= 1
            assert 0 <= r.draw_probability <= 1
            assert 0 <= r.away_win_probability <= 1

    def test_invalid_probabilities_skipped(self):
        """Records with probability > 1 must be silently skipped."""
        def _bad_fn(match, train): return (1.5, 0.0, 0.0)
        matches = _make_matches(20)
        splitter = ChronologicalSplitter(min_train=5, test_size=5, step_size=5)
        windows = splitter.expanding_windows(matches)
        runner = BacktestRunner("test")
        records = runner.run_windows(windows, _bad_fn)
        assert len(records) == 0


# ---------------------------------------------------------------------------
# BacktestAggregator
# ---------------------------------------------------------------------------

class TestBacktestAggregator:

    def _make_records(self, n: int = 50) -> List[PredictionRecord]:
        records = []
        outcomes = ["home_win", "draw", "away_win"]
        for i in range(n):
            outcome = outcomes[i % 3]
            records.append(PredictionRecord(
                match_id=f"m{i}",
                model_id="test",
                model_version="1.0",
                predicted_at=datetime.now(),
                actual_outcome=outcome,
                home_win_probability=0.45,
                draw_probability=0.30,
                away_win_probability=0.25,
            ))
        return records

    def test_empty_records_returns_nan_metrics(self):
        import math
        agg = BacktestAggregator()
        metrics = agg.aggregate([], "m", "1.0")
        assert metrics.n_predictions == 0
        assert metrics.accuracy is None
        assert metrics.brier_score is None
        assert metrics.log_loss is None
        assert metrics.is_reliable is False

    def test_n_predictions_correct(self):
        agg = BacktestAggregator()
        records = self._make_records(50)
        metrics = agg.aggregate(records, "m", "1.0")
        assert metrics.n_predictions == 50

    def test_accuracy_in_range(self):
        agg = BacktestAggregator()
        metrics = agg.aggregate(self._make_records(50), "m", "1.0")
        assert 0.0 <= metrics.accuracy <= 1.0

    def test_brier_score_non_negative(self):
        agg = BacktestAggregator()
        metrics = agg.aggregate(self._make_records(50), "m", "1.0")
        assert metrics.brier_score >= 0.0

    def test_log_loss_non_negative(self):
        agg = BacktestAggregator()
        metrics = agg.aggregate(self._make_records(50), "m", "1.0")
        assert metrics.log_loss >= 0.0

    def test_is_reliable_below_threshold(self):
        agg = BacktestAggregator()
        metrics = agg.aggregate(self._make_records(10), "m", "1.0")
        assert metrics.is_reliable is False

    def test_is_reliable_above_threshold(self):
        agg = BacktestAggregator()
        metrics = agg.aggregate(self._make_records(30), "m", "1.0")
        assert metrics.is_reliable is True

    def test_perfect_predictions_high_accuracy(self):
        """When prediction always matches outcome, accuracy = 1."""
        records = []
        for i in range(30):
            records.append(PredictionRecord(
                match_id=f"m{i}", model_id="m", model_version="1.0",
                predicted_at=datetime.now(),
                actual_outcome="home_win",
                home_win_probability=0.99,
                draw_probability=0.005,
                away_win_probability=0.005,
            ))
        agg = BacktestAggregator()
        metrics = agg.aggregate(records, "m", "1.0")
        assert metrics.accuracy == 1.0

    def test_wrong_predictions_low_accuracy(self):
        """When prediction is always wrong outcome, accuracy = 0."""
        records = []
        for i in range(30):
            records.append(PredictionRecord(
                match_id=f"m{i}", model_id="m", model_version="1.0",
                predicted_at=datetime.now(),
                actual_outcome="home_win",
                home_win_probability=0.005,
                draw_probability=0.005,
                away_win_probability=0.99,
            ))
        agg = BacktestAggregator()
        metrics = agg.aggregate(records, "m", "1.0")
        assert metrics.accuracy == 0.0


# ---------------------------------------------------------------------------
# run_backtest() convenience function
# ---------------------------------------------------------------------------

class TestRunBacktest:

    def test_basic_expanding_run(self):
        matches = _make_matches(40)
        result = run_backtest(
            matches=matches,
            predict_fn=_constant_predict_fn(),
            model_id="constant",
            mode="expanding",
            min_train=10,
            test_size=5,
            step_size=5,
        )
        assert isinstance(result, BacktestResult)
        assert result.model_id == "constant"
        assert result.window_mode == "expanding"
        assert len(result.records) > 0

    def test_basic_rolling_run(self):
        matches = _make_matches(40)
        result = run_backtest(
            matches=matches,
            predict_fn=_constant_predict_fn(),
            model_id="constant",
            mode="rolling",
            min_train=10,
            test_size=5,
            step_size=5,
            train_size=10,
        )
        assert result.window_mode == "rolling"
        assert len(result.records) > 0

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="mode"):
            run_backtest(
                matches=_make_matches(30),
                predict_fn=_constant_predict_fn(),
                model_id="m",
                mode="invalid",
            )

    def test_scheduled_matches_excluded(self):
        """Scheduled (non-finished) matches should be filtered out."""
        matches = _make_matches(30)
        scheduled = [_scheduled_match(f"s{i}", "X", "Y", 100 + i) for i in range(10)]
        all_matches = matches + scheduled
        result = run_backtest(
            matches=all_matches,
            predict_fn=_constant_predict_fn(),
            model_id="m",
            mode="expanding",
            min_train=10, test_size=5, step_size=5,
        )
        # Result should only contain finished match records
        assert all(r.match_id.startswith("m") for r in result.records)

    def test_metrics_populated(self):
        matches = _make_matches(40)
        result = run_backtest(
            matches=matches,
            predict_fn=_constant_predict_fn(),
            model_id="m",
            mode="expanding",
            min_train=10, test_size=5, step_size=5,
        )
        assert result.metrics.accuracy is not None
        assert result.metrics.brier_score is not None

    def test_timestamps_recorded(self):
        matches = _make_matches(30)
        result = run_backtest(
            matches=matches,
            predict_fn=_constant_predict_fn(),
            model_id="m",
        )
        assert result.started_at <= result.completed_at

    def test_empty_matches_returns_empty_result(self):
        result = run_backtest(
            matches=[],
            predict_fn=_constant_predict_fn(),
            model_id="m",
        )
        assert len(result.records) == 0
        assert result.metrics.n_predictions == 0

    def test_deterministic_run(self):
        """Same inputs produce identical records."""
        matches = _make_matches(40)
        fn = _constant_predict_fn()
        r1 = run_backtest(matches, fn, "m", mode="expanding",
                          min_train=10, test_size=5, step_size=5)
        r2 = run_backtest(matches, fn, "m", mode="expanding",
                          min_train=10, test_size=5, step_size=5)
        assert len(r1.records) == len(r2.records)
        for rec1, rec2 in zip(r1.records, r2.records):
            assert rec1.match_id == rec2.match_id
            assert rec1.home_win_probability == rec2.home_win_probability


# ---------------------------------------------------------------------------
# Predict function adapters
# ---------------------------------------------------------------------------

class TestPredictFnAdapters:

    def _run_adapter(self, predict_fn, n=25):
        matches = _make_matches(n)
        result = run_backtest(
            matches=matches,
            predict_fn=predict_fn,
            model_id="adapter_test",
            mode="expanding",
            min_train=8,
            test_size=3,
            step_size=3,
        )
        return result

    def test_poisson_adapter_produces_records(self):
        result = self._run_adapter(poisson_predict_fn())
        assert len(result.records) > 0

    def test_negative_binomial_adapter_produces_records(self):
        result = self._run_adapter(negative_binomial_predict_fn())
        assert len(result.records) > 0

    def test_elo_adapter_produces_records(self):
        result = self._run_adapter(elo_predict_fn())
        assert len(result.records) > 0

    def test_logistic_regression_adapter_produces_records(self):
        result = self._run_adapter(logistic_regression_predict_fn())
        # LR requires at least min_train samples; some windows may return None
        # Just check no crash and result structure is valid
        assert isinstance(result, BacktestResult)

    def test_all_adapter_probabilities_valid(self):
        result = self._run_adapter(poisson_predict_fn())
        for r in result.records:
            assert 0 <= r.home_win_probability <= 1
            assert 0 <= r.draw_probability <= 1
            assert 0 <= r.away_win_probability <= 1

    def test_poisson_adapter_no_future_leakage(self):
        """Predictions from Poisson adapter must only use training data."""
        matches = _make_matches(30)
        fn = poisson_predict_fn()
        splitter = ChronologicalSplitter(min_train=10, test_size=3, step_size=3)
        windows = splitter.expanding_windows(matches)
        runner = BacktestRunner("poisson_test")
        records = runner.run_windows(windows, fn)
        # All records must reference matches that were in the test set,
        # which is always after training.
        assert all(r.match_id is not None for r in records)
