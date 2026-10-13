"""Chronological backtesting engine for football prediction models.

This module provides reusable infrastructure for evaluating prediction
models against historical data with strict chronological safety.

Responsibilities are explicitly separated:
  1. Data preparation  — ChronologicalSplitter
  2. Prediction        — BacktestPredictor protocol / adapter classes
  3. Result storage    — PredictionRecord
  4. Metric evaluation — uses existing calibration module
  5. Aggregation       — BacktestAggregator

Chronological safety guarantees:
  - Matches are sorted by scheduled_at before any processing.
  - Training data always precedes evaluation data in time.
  - No evaluation match appears in the training window.
  - Rolling and expanding window modes both enforce these rules.

No odds or ROI are fabricated. ROI calculation is deliberately absent
unless real historical odds are provided (not yet available).

Compatible models (via BacktestPredictor protocol):
  - PoissonModel
  - EloRatingSystem
  - DixonColesModel
  - NegativeBinomialModel
  - LogisticRegressionModel
  - EnsembleModel
  - Any callable producing (home_win, draw, away_win) probabilities
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Protocol, Tuple

from app.domain.match import Match
from app.domain.enums import MatchOutcome, MatchStatus
from app.prediction.calibration import (
    brier_score,
    log_loss_binary,
    log_loss_multiclass,
    calibration_error,
)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

# A predictor is any callable:
#   predict_fn(match, train_matches) -> (home_win_prob, draw_prob, away_win_prob)
PredictFn = Callable[[Match, List[Match]], Optional[Tuple[float, float, float]]]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PredictionRecord:
    """Single prediction + actual result for one match.

    This is the atomic unit of backtest output. All evaluation metrics
    can be re-derived from a list of PredictionRecords.
    """

    match_id: str
    model_id: str
    model_version: str

    predicted_at: datetime
    """Timestamp at which the prediction was computed (context only)."""

    actual_outcome: str
    """Actual result: 'home_win' | 'draw' | 'away_win'."""

    # Predicted 1X2 probabilities
    home_win_probability: float
    draw_probability: float
    away_win_probability: float

    # Per-outcome Brier components (computed on creation for convenience)
    brier_home: float = field(init=False)
    brier_draw: float = field(init=False)
    brier_away: float = field(init=False)

    # Optional: per-market metrics populated after the fact
    log_loss_contribution: Optional[float] = None

    def __post_init__(self) -> None:
        h = 1 if self.actual_outcome == "home_win" else 0
        d = 1 if self.actual_outcome == "draw" else 0
        a = 1 if self.actual_outcome == "away_win" else 0
        self.brier_home = (self.home_win_probability - h) ** 2
        self.brier_draw = (self.draw_probability - d) ** 2
        self.brier_away = (self.away_win_probability - a) ** 2


@dataclass
class WindowSplit:
    """A single train/test split produced by the splitter."""

    window_index: int
    train_matches: List[Match]
    test_matches: List[Match]

    @property
    def n_train(self) -> int:
        return len(self.train_matches)

    @property
    def n_test(self) -> int:
        return len(self.test_matches)


@dataclass
class BacktestMetrics:
    """Aggregate evaluation metrics for a completed backtest run."""

    model_id: str
    model_version: str

    n_predictions: int
    """Total predictions evaluated."""

    accuracy: Optional[float]
    """Fraction of correct most-probable-outcome predictions."""

    brier_score: Optional[float]
    """Multiclass Brier score (mean over home/draw/away)."""

    log_loss: Optional[float]
    """Multiclass log loss."""

    calibration_error: Optional[float]
    """Expected calibration error on home-win probabilities."""

    # Reliability: is the sample size sufficient for trust?
    is_reliable: bool

    # Breakdown by outcome
    home_win_accuracy: Optional[float] = None
    draw_accuracy: Optional[float] = None
    away_win_accuracy: Optional[float] = None

    # ROI — only populated when real historical odds are provided
    roi: Optional[float] = None
    roi_available: bool = False

    computed_at: datetime = field(default_factory=datetime.now)

    MIN_RELIABLE_SAMPLES = 30


@dataclass
class BacktestResult:
    """Full result of a backtest run."""

    model_id: str
    model_version: str
    window_mode: str
    """'rolling' or 'expanding'."""

    records: List[PredictionRecord]
    metrics: BacktestMetrics
    windows: List[WindowSplit]

    started_at: datetime
    completed_at: datetime

    @property
    def n_windows(self) -> int:
        return len(self.windows)


# ---------------------------------------------------------------------------
# Chronological splitter
# ---------------------------------------------------------------------------

class ChronologicalSplitter:
    """Splits a match list into chronological train/test windows.

    Both rolling and expanding window modes are supported.

    Chronological safety:
      - Input is always sorted by scheduled_at.
      - Test matches are strictly after all training matches.
      - No test match appears in the training window.

    Rolling window: fixed-size training window that advances.
    Expanding window: training window grows to include all past data.
    """

    def __init__(
        self,
        min_train: int = 10,
        test_size: int = 5,
        step_size: int = 5,
    ):
        """Initialise splitter.

        Args:
            min_train:  Minimum training matches required before
                        generating any test window.
            test_size:  Number of matches in each test window.
            step_size:  How many matches to advance per step.

        Raises:
            ValueError: If parameters are invalid.
        """
        if min_train < 1:
            raise ValueError(f"min_train must be >= 1, got {min_train}")
        if test_size < 1:
            raise ValueError(f"test_size must be >= 1, got {test_size}")
        if step_size < 1:
            raise ValueError(f"step_size must be >= 1, got {step_size}")

        self.min_train = min_train
        self.test_size = test_size
        self.step_size = step_size

    def rolling_windows(
        self,
        matches: List[Match],
        train_size: int,
    ) -> List[WindowSplit]:
        """Generate rolling-window splits.

        The training window has a fixed size (train_size) and advances
        by step_size at each iteration.

        Args:
            matches:    All finished matches (will be sorted internally).
            train_size: Fixed number of training matches per window.

        Returns:
            List of WindowSplit objects (may be empty if insufficient data).
        """
        if train_size < self.min_train:
            raise ValueError(
                f"train_size ({train_size}) must be >= min_train ({self.min_train})"
            )

        sorted_matches = self._sort(matches)
        n = len(sorted_matches)
        splits = []
        window_idx = 0
        start = 0

        while start + train_size + self.test_size <= n:
            train = sorted_matches[start : start + train_size]
            test = sorted_matches[
                start + train_size : start + train_size + self.test_size
            ]
            splits.append(
                WindowSplit(
                    window_index=window_idx,
                    train_matches=train,
                    test_matches=test,
                )
            )
            start += self.step_size
            window_idx += 1

        return splits

    def expanding_windows(
        self,
        matches: List[Match],
    ) -> List[WindowSplit]:
        """Generate expanding-window splits.

        The training window grows by step_size at each iteration.
        Training always starts from the first match.

        Args:
            matches: All finished matches (will be sorted internally).

        Returns:
            List of WindowSplit objects.
        """
        sorted_matches = self._sort(matches)
        n = len(sorted_matches)
        splits = []
        train_end = self.min_train
        window_idx = 0

        while train_end + self.test_size <= n:
            train = sorted_matches[:train_end]
            test = sorted_matches[train_end : train_end + self.test_size]
            splits.append(
                WindowSplit(
                    window_index=window_idx,
                    train_matches=train,
                    test_matches=test,
                )
            )
            train_end += self.step_size
            window_idx += 1

        return splits

    @staticmethod
    def _sort(matches: List[Match]) -> List[Match]:
        """Return matches sorted chronologically by scheduled_at."""
        return sorted(matches, key=lambda m: m.scheduled_at)


# ---------------------------------------------------------------------------
# Backtest runner
# ---------------------------------------------------------------------------

class BacktestRunner:
    """Runs a prediction model over a set of chronological windows.

    The runner calls the predict_fn for each test match, providing only
    the training matches that precede it.  No test match information is
    ever visible to the predictor.
    """

    def __init__(
        self,
        model_id: str,
        model_version: str = "1.0.0",
    ):
        """Initialise the runner.

        Args:
            model_id:      Identifier for the model being tested.
            model_version: Version string for audit purposes.
        """
        self.model_id = model_id
        self.model_version = model_version

    def run_windows(
        self,
        windows: List[WindowSplit],
        predict_fn: PredictFn,
    ) -> List[PredictionRecord]:
        """Run predictions over a list of pre-computed windows.

        For each test match in each window, the predict_fn receives:
          - The test match (with result fields available for evaluation
            after prediction, but the predictor must not use them).
          - The training matches (preceding the test match in time).

        Args:
            windows:    Pre-computed WindowSplit objects.
            predict_fn: Callable that takes (match, train_matches) and
                        returns Optional[(home_prob, draw_prob, away_prob)].

        Returns:
            List of PredictionRecord objects (one per successful prediction).
        """
        records: List[PredictionRecord] = []

        for window in windows:
            for test_match in window.test_matches:
                result = predict_fn(test_match, window.train_matches)
                if result is None:
                    continue  # Model could not predict (insufficient data)

                home_p, draw_p, away_p = result

                # Validate probabilities
                if not (0.0 <= home_p <= 1.0 and
                        0.0 <= draw_p <= 1.0 and
                        0.0 <= away_p <= 1.0):
                    continue  # Skip invalid predictions silently

                # Determine actual outcome
                actual = _match_outcome(test_match)
                if actual is None:
                    continue  # Match not finished

                record = PredictionRecord(
                    match_id=test_match.id,
                    model_id=self.model_id,
                    model_version=self.model_version,
                    predicted_at=datetime.now(),
                    actual_outcome=actual,
                    home_win_probability=home_p,
                    draw_probability=draw_p,
                    away_win_probability=away_p,
                )
                records.append(record)

        return records


# ---------------------------------------------------------------------------
# Metric aggregator
# ---------------------------------------------------------------------------

class BacktestAggregator:
    """Compute aggregate metrics from a list of PredictionRecords.

    All metrics use the existing calibration module to ensure consistency
    with the standalone evaluation layer.
    """

    def aggregate(
        self,
        records: List[PredictionRecord],
        model_id: str,
        model_version: str,
    ) -> BacktestMetrics:
        """Aggregate prediction records into BacktestMetrics.

        Args:
            records:       PredictionRecords from BacktestRunner.
            model_id:      Model identifier.
            model_version: Model version.

        Returns:
            BacktestMetrics with all calculable statistics.
        """
        n = len(records)

        if n == 0:
            return BacktestMetrics(
                model_id=model_id,
                model_version=model_version,
                n_predictions=0,
                accuracy=None,
                brier_score=None,
                log_loss=None,
                calibration_error=None,
                is_reliable=False,
            )

        # --- Accuracy ---
        correct = sum(
            1 for r in records
            if _most_probable_outcome(r) == r.actual_outcome
        )
        accuracy = correct / n

        # --- Multiclass Brier score ---
        # Mean of per-outcome Brier scores
        mean_brier = sum(
            (r.brier_home + r.brier_draw + r.brier_away) / 3.0
            for r in records
        ) / n

        # --- Multiclass log loss ---
        prob_vectors = [
            [r.home_win_probability, r.draw_probability, r.away_win_probability]
            for r in records
        ]
        outcome_vectors = [
            [
                1 if r.actual_outcome == "home_win" else 0,
                1 if r.actual_outcome == "draw" else 0,
                1 if r.actual_outcome == "away_win" else 0,
            ]
            for r in records
        ]
        ll_result = log_loss_multiclass(prob_vectors, outcome_vectors, "1x2_backtest")
        ll = ll_result.log_loss if not math.isnan(ll_result.log_loss) else None

        # --- ECE on home-win probabilities ---
        home_probs = [r.home_win_probability for r in records]
        home_acts = [1 if r.actual_outcome == "home_win" else 0 for r in records]
        ece_result = calibration_error(home_probs, home_acts, n_bins=10)
        ece = ece_result.ece if not math.isnan(ece_result.ece) else None

        # --- Per-outcome accuracy ---
        home_records = [r for r in records if r.actual_outcome == "home_win"]
        draw_records = [r for r in records if r.actual_outcome == "draw"]
        away_records = [r for r in records if r.actual_outcome == "away_win"]

        home_acc = _outcome_accuracy(home_records, "home_win") if home_records else None
        draw_acc = _outcome_accuracy(draw_records, "draw") if draw_records else None
        away_acc = _outcome_accuracy(away_records, "away_win") if away_records else None

        return BacktestMetrics(
            model_id=model_id,
            model_version=model_version,
            n_predictions=n,
            accuracy=accuracy,
            brier_score=mean_brier,
            log_loss=ll,
            calibration_error=ece,
            is_reliable=n >= BacktestMetrics.MIN_RELIABLE_SAMPLES,
            home_win_accuracy=home_acc,
            draw_accuracy=draw_acc,
            away_win_accuracy=away_acc,
            roi=None,
            roi_available=False,
        )


# ---------------------------------------------------------------------------
# High-level convenience function
# ---------------------------------------------------------------------------

def run_backtest(
    matches: List[Match],
    predict_fn: PredictFn,
    model_id: str,
    model_version: str = "1.0.0",
    mode: str = "expanding",
    min_train: int = 10,
    test_size: int = 5,
    step_size: int = 5,
    train_size: Optional[int] = None,
) -> BacktestResult:
    """Run a complete backtest and return aggregated results.

    Args:
        matches:       All finished historical matches.
        predict_fn:    Prediction callable.
        model_id:      Model identifier.
        model_version: Model version string.
        mode:          'rolling' or 'expanding'.
        min_train:     Minimum training samples for first window.
        test_size:     Matches per test window.
        step_size:     Advance between windows.
        train_size:    Fixed training window size (rolling mode only).

    Returns:
        BacktestResult with records, metrics, and window splits.

    Raises:
        ValueError: If mode is invalid or parameters conflict.
    """
    if mode not in ("rolling", "expanding"):
        raise ValueError(f"mode must be 'rolling' or 'expanding', got '{mode}'")

    started_at = datetime.now()

    # Only use finished matches
    finished = [
        m for m in matches
        if m.status == MatchStatus.FINISHED
        and m.home_score is not None
        and m.away_score is not None
    ]

    splitter = ChronologicalSplitter(
        min_train=min_train,
        test_size=test_size,
        step_size=step_size,
    )

    if mode == "rolling":
        effective_train_size = train_size if train_size is not None else min_train
        windows = splitter.rolling_windows(finished, train_size=effective_train_size)
    else:
        windows = splitter.expanding_windows(finished)

    runner = BacktestRunner(model_id=model_id, model_version=model_version)
    records = runner.run_windows(windows, predict_fn)

    aggregator = BacktestAggregator()
    metrics = aggregator.aggregate(records, model_id=model_id, model_version=model_version)

    completed_at = datetime.now()

    return BacktestResult(
        model_id=model_id,
        model_version=model_version,
        window_mode=mode,
        records=records,
        metrics=metrics,
        windows=windows,
        started_at=started_at,
        completed_at=completed_at,
    )


# ---------------------------------------------------------------------------
# Model adapters — bridge existing models to PredictFn interface
# ---------------------------------------------------------------------------

def poisson_predict_fn(
    home_attack: float = 1.5,
    away_attack: float = 1.2,
) -> PredictFn:
    """Return a PredictFn adapter for PoissonModel.

    Uses fixed lambda values when team-specific strength data is not
    available (e.g., teams with no historical data in the training set).
    In production, lambda should be derived from team strength features.
    """
    from app.prediction.poisson import PoissonModel

    model = PoissonModel(max_goals=10)

    def _predict(
        match: Match,
        train_matches: List[Match],
    ) -> Optional[Tuple[float, float, float]]:
        # Compute team-specific attack rates from training matches
        h_lam = _calc_attack_rate(match.home_team_id, train_matches) or home_attack
        a_lam = _calc_attack_rate(match.away_team_id, train_matches) or away_attack
        result = model.predict_from_lambda(h_lam, a_lam)
        return (
            result.home_win_probability,
            result.draw_probability,
            result.away_win_probability,
        )

    return _predict


def negative_binomial_predict_fn(
    dispersion: float = 20.0,
) -> PredictFn:
    """Return a PredictFn adapter for NegativeBinomialModel."""
    from app.prediction.negative_binomial import NegativeBinomialModel

    model = NegativeBinomialModel(dispersion=dispersion, max_goals=10)

    def _predict(
        match: Match,
        train_matches: List[Match],
    ) -> Optional[Tuple[float, float, float]]:
        h_lam = _calc_attack_rate(match.home_team_id, train_matches) or 1.5
        a_lam = _calc_attack_rate(match.away_team_id, train_matches) or 1.2
        result = model.predict_from_lambda(h_lam, a_lam)
        return (
            result.home_win_probability,
            result.draw_probability,
            result.away_win_probability,
        )

    return _predict


def elo_predict_fn(
    k_factor: float = 32.0,
    initial_rating: float = 1500.0,
    home_advantage: float = 100.0,
) -> PredictFn:
    """Return a PredictFn adapter for EloRatingSystem.

    The Elo system is re-built fresh from training matches each window
    to avoid state leakage between windows.
    """
    from app.prediction.elo import EloRatingSystem

    def _predict(
        match: Match,
        train_matches: List[Match],
    ) -> Optional[Tuple[float, float, float]]:
        sys = EloRatingSystem(
            k_factor=k_factor,
            initial_rating=initial_rating,
            home_advantage=home_advantage,
        )
        for m in sorted(train_matches, key=lambda x: x.scheduled_at):
            if (m.status == MatchStatus.FINISHED
                    and m.home_score is not None
                    and m.away_score is not None):
                sys.process_match(
                    match_id=m.id,
                    home_team_id=m.home_team_id,
                    away_team_id=m.away_team_id,
                    home_goals=m.home_score,
                    away_goals=m.away_score,
                    played_at=m.scheduled_at,
                )
        pred = sys.predict(match.home_team_id, match.away_team_id)
        return (
            pred.home_win_probability,
            pred.draw_probability,
            pred.away_win_probability,
        )

    return _predict


def logistic_regression_predict_fn(
    feature_extractor=None,
) -> PredictFn:
    """Return a PredictFn adapter for LogisticRegressionModel.

    Trains a fresh model on each window's training set.
    Features are derived from a simple home/away goal-rate calculation
    when no MatchFeatureExtractor is provided.
    """
    from app.prediction.logistic_regression import (
        LogisticRegressionModel,
        DEFAULT_FEATURE_KEYS,
    )

    def _predict(
        match: Match,
        train_matches: List[Match],
    ) -> Optional[Tuple[float, float, float]]:
        # Build training samples from training matches
        samples = _build_lr_samples(train_matches)
        if len(samples) < 5:
            return None

        model = LogisticRegressionModel(n_epochs=100, seed=42)
        try:
            model.fit(samples)
        except (ValueError, ZeroDivisionError):
            return None

        # Build feature dict for the test match from training data
        features = _build_lr_features(match, train_matches)
        pred = model.predict_legacy(features)
        return (
            pred.home_win_probability,
            pred.draw_probability,
            pred.away_win_probability,
        )

    return _predict


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _match_outcome(match: Match) -> Optional[str]:
    """Derive outcome string from match scores."""
    if match.home_score is None or match.away_score is None:
        return None
    if match.home_score > match.away_score:
        return "home_win"
    if match.home_score == match.away_score:
        return "draw"
    return "away_win"


def _most_probable_outcome(record: PredictionRecord) -> str:
    """Return the most probable outcome from a PredictionRecord."""
    probs = {
        "home_win": record.home_win_probability,
        "draw": record.draw_probability,
        "away_win": record.away_win_probability,
    }
    return max(probs, key=lambda k: probs[k])


def _outcome_accuracy(
    records: List[PredictionRecord],
    outcome: str,
) -> float:
    """Fraction of records where most probable outcome equals *outcome*."""
    if not records:
        return 0.0
    correct = sum(1 for r in records if _most_probable_outcome(r) == outcome)
    return correct / len(records)


def _calc_attack_rate(
    team_id: str,
    matches: List[Match],
    default: float = 1.5,
) -> Optional[float]:
    """Compute average goals scored per match from training data."""
    goals = []
    for m in matches:
        if m.status != MatchStatus.FINISHED:
            continue
        if m.home_team_id == team_id and m.home_score is not None:
            goals.append(m.home_score)
        elif m.away_team_id == team_id and m.away_score is not None:
            goals.append(m.away_score)
    if not goals:
        return None
    return sum(goals) / len(goals)


def _build_lr_samples(
    matches: List[Match],
) -> List[Tuple[Dict[str, Optional[float]], str]]:
    """Build (feature_dict, label) training samples from finished matches."""
    from app.prediction.logistic_regression import DEFAULT_FEATURE_KEYS

    # Compute team strength metrics from ALL training matches for each team
    team_goals_scored: Dict[str, List[float]] = {}
    team_goals_conceded: Dict[str, List[float]] = {}

    for m in matches:
        if m.status != MatchStatus.FINISHED or m.home_score is None:
            continue
        tid_h, tid_a = m.home_team_id, m.away_team_id
        team_goals_scored.setdefault(tid_h, []).append(float(m.home_score))
        team_goals_conceded.setdefault(tid_h, []).append(float(m.away_score))
        team_goals_scored.setdefault(tid_a, []).append(float(m.away_score))
        team_goals_conceded.setdefault(tid_a, []).append(float(m.home_score))

    def _avg(lst):
        return sum(lst) / len(lst) if lst else None

    samples = []
    for m in matches:
        if m.status != MatchStatus.FINISHED or m.home_score is None:
            continue
        outcome = _match_outcome(m)
        if outcome is None:
            continue

        features: Dict[str, Optional[float]] = {
            "home_attack_strength": _avg(team_goals_scored.get(m.home_team_id, [])),
            "home_defense_strength": _avg(team_goals_conceded.get(m.home_team_id, [])),
            "away_attack_strength": _avg(team_goals_scored.get(m.away_team_id, [])),
            "away_defense_strength": _avg(team_goals_conceded.get(m.away_team_id, [])),
        }
        samples.append((features, outcome))

    return samples


def _build_lr_features(
    match: Match,
    train_matches: List[Match],
) -> Dict[str, Optional[float]]:
    """Build feature dict for a prediction match from training data only."""
    team_goals_scored: Dict[str, List[float]] = {}
    team_goals_conceded: Dict[str, List[float]] = {}

    for m in train_matches:
        if m.status != MatchStatus.FINISHED or m.home_score is None:
            continue
        team_goals_scored.setdefault(m.home_team_id, []).append(float(m.home_score))
        team_goals_conceded.setdefault(m.home_team_id, []).append(float(m.away_score))
        team_goals_scored.setdefault(m.away_team_id, []).append(float(m.away_score))
        team_goals_conceded.setdefault(m.away_team_id, []).append(float(m.home_score))

    def _avg(lst):
        return sum(lst) / len(lst) if lst else None

    return {
        "home_attack_strength": _avg(team_goals_scored.get(match.home_team_id, [])),
        "home_defense_strength": _avg(team_goals_conceded.get(match.home_team_id, [])),
        "away_attack_strength": _avg(team_goals_scored.get(match.away_team_id, [])),
        "away_defense_strength": _avg(team_goals_conceded.get(match.away_team_id, [])),
    }
