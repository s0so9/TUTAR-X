"""Weighted ensemble prediction model.

This module implements a clean ensemble abstraction that combines outputs
from multiple prediction models into a single weighted prediction.

Design principles:
- Common model interface via ModelPredictionInput
- Configurable per-model weights
- Automatic weight normalisation
- Strict probability validation (all values must be in [0, 1])
- Market compatibility validation (no silent merging of incompatible markets)
- Deterministic output for identical inputs and weights
- Model contribution metadata preserved in the output

Currently supported base models:
  - Poisson (via PredictionService / PoissonModel)
  - Elo (via EloRatingSystem)
  - Dixon-Coles (via DixonColesModel)

Do NOT add neural networks or external ML frameworks here.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Protocol

from app.domain.enums import ModelType


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_probability(value: float, label: str) -> None:
    """Raise ValueError if *value* is not in [0, 1]."""
    if not (0.0 <= value <= 1.0):
        raise ValueError(
            f"Invalid probability for '{label}': {value!r} "
            f"(must be in [0, 1])"
        )


def _validate_probabilities(probs: Dict[str, float], context: str) -> None:
    """Raise ValueError for any probability outside [0, 1]."""
    for key, value in probs.items():
        _validate_probability(value, f"{context}.{key}")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ModelPredictionInput:
    """A single model's prediction input to the ensemble.

    All probabilities must be normalised (sum ≈ 1.0 within each market).
    """

    model_id: str
    """Identifier for the source model."""

    model_type: ModelType
    """Type of the source model."""

    # 1X2 probabilities (required for the core ensemble)
    home_win_probability: float
    draw_probability: float
    away_win_probability: float

    # Optional extra markets (may be absent for some models)
    btts_yes_probability: Optional[float] = None
    btts_no_probability: Optional[float] = None

    # Extra metadata carried through to the ensemble result
    home_xg: Optional[float] = None
    away_xg: Optional[float] = None

    def validate(self) -> None:
        """Validate all probability fields.

        Raises:
            ValueError: If any probability is outside [0, 1].
        """
        _validate_probability(self.home_win_probability, "home_win_probability")
        _validate_probability(self.draw_probability, "draw_probability")
        _validate_probability(self.away_win_probability, "away_win_probability")

        if self.btts_yes_probability is not None:
            _validate_probability(self.btts_yes_probability, "btts_yes_probability")
        if self.btts_no_probability is not None:
            _validate_probability(self.btts_no_probability, "btts_no_probability")


@dataclass
class ModelContribution:
    """Records how a single model contributed to the ensemble output."""

    model_id: str
    model_type: ModelType
    weight: float
    """Normalised weight used in the combination."""

    original_weight: float
    """Raw weight provided before normalisation."""

    # The weighted contribution to the final probabilities
    home_win_contribution: float
    draw_contribution: float
    away_win_contribution: float


@dataclass
class EnsemblePrediction:
    """Result of the weighted ensemble combination."""

    id: str
    """Unique identifier for this ensemble prediction."""

    # Combined 1X2 probabilities
    home_win_probability: float
    draw_probability: float
    away_win_probability: float

    # Combined BTTS (only set if all contributing models provided it)
    btts_yes_probability: Optional[float] = None
    btts_no_probability: Optional[float] = None

    # Model contribution metadata
    model_contributions: List[ModelContribution] = field(default_factory=list)

    # Ensemble parameters
    n_models: int = 0
    total_weight: float = 0.0

    generated_at: datetime = field(default_factory=datetime.now)

    @property
    def is_valid(self) -> bool:
        """Return True if all core probabilities are valid."""
        probs = [
            self.home_win_probability,
            self.draw_probability,
            self.away_win_probability,
        ]
        return all(0.0 <= p <= 1.0 for p in probs)


# ---------------------------------------------------------------------------
# Ensemble engine
# ---------------------------------------------------------------------------

class EnsembleModel:
    """Weighted ensemble prediction model.

    Combines multiple model predictions using configurable weights.
    Weights are automatically normalised so they sum to 1.0.

    Usage:
        ensemble = EnsembleModel(
            weights={
                "poisson_v1": 0.5,
                "elo_v1":     0.3,
                "dc_v1":      0.2,
            }
        )
        result = ensemble.predict([
            ModelPredictionInput(
                model_id="poisson_v1",
                model_type=ModelType.POISSON,
                home_win_probability=0.45,
                draw_probability=0.30,
                away_win_probability=0.25,
            ),
            ...
        ])

    Rules:
    - All input probabilities must be in [0, 1].
    - At least one model must have a positive weight.
    - The ensemble will NOT silently combine models with incompatible
      markets: if only some models supply BTTS probabilities, the BTTS
      output will only be included if ALL active models supply it.
    - The output probabilities are normalised to exactly sum to 1.0.
    - Results are deterministic for identical inputs and weights.
    """

    MIN_WEIGHT = 0.0
    """Models with weight <= 0 are excluded from the ensemble."""

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """Initialise the ensemble model.

        Args:
            weights: Optional mapping of model_id → weight.
                     If None or empty, equal weights are applied to all
                     models supplied at prediction time.

        Raises:
            ValueError: If any weight is negative.
        """
        if weights is not None:
            for model_id, w in weights.items():
                if w < 0.0:
                    raise ValueError(
                        f"Weight for model '{model_id}' must be >= 0, got {w}"
                    )

        self.weights: Dict[str, float] = weights or {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(
        self,
        model_inputs: List[ModelPredictionInput],
    ) -> EnsemblePrediction:
        """Combine model predictions into a weighted ensemble.

        Args:
            model_inputs: Prediction inputs from each base model.
                          At least one must be provided.

        Returns:
            EnsemblePrediction with weighted-average probabilities.

        Raises:
            ValueError: If no models are provided, all weights are zero,
                        or any probability value is invalid.
        """
        if not model_inputs:
            raise ValueError("No model inputs provided to ensemble.")

        # Validate all inputs first (fail fast)
        for inp in model_inputs:
            inp.validate()

        # Resolve weights (use configured weights, fall back to equal)
        resolved_weights = self._resolve_weights(model_inputs)

        # Filter to active models (weight > 0)
        active_pairs: List[Tuple[ModelPredictionInput, float]] = [
            (inp, resolved_weights[inp.model_id])
            for inp in model_inputs
            if resolved_weights.get(inp.model_id, 0.0) > self.MIN_WEIGHT
        ]

        if not active_pairs:
            raise ValueError(
                "All models have zero weight; cannot produce ensemble prediction."
            )

        # Normalise weights among active models
        total_weight = sum(w for _, w in active_pairs)
        normalised_pairs: List[Tuple[ModelPredictionInput, float, float]] = [
            (inp, w / total_weight, w)
            for inp, w in active_pairs
        ]

        # Weighted combination – 1X2
        home_win = sum(inp.home_win_probability * nw for inp, nw, _ in normalised_pairs)
        draw = sum(inp.draw_probability * nw for inp, nw, _ in normalised_pairs)
        away_win = sum(inp.away_win_probability * nw for inp, nw, _ in normalised_pairs)

        # Final normalisation to guarantee exact sum = 1.0
        home_win, draw, away_win = self._normalise_1x2(home_win, draw, away_win)

        # BTTS: only include if ALL active models supply it
        btts_yes, btts_no = self._combine_btts(normalised_pairs)

        # Build contribution metadata
        contributions = [
            ModelContribution(
                model_id=inp.model_id,
                model_type=inp.model_type,
                weight=nw,
                original_weight=ow,
                home_win_contribution=inp.home_win_probability * nw,
                draw_contribution=inp.draw_probability * nw,
                away_win_contribution=inp.away_win_probability * nw,
            )
            for inp, nw, ow in normalised_pairs
        ]

        return EnsemblePrediction(
            id=f"ensemble_{uuid.uuid4().hex[:12]}",
            home_win_probability=home_win,
            draw_probability=draw,
            away_win_probability=away_win,
            btts_yes_probability=btts_yes,
            btts_no_probability=btts_no,
            model_contributions=contributions,
            n_models=len(active_pairs),
            total_weight=total_weight,
            generated_at=datetime.now(),
        )

    def add_weight(self, model_id: str, weight: float) -> None:
        """Add or update a model weight.

        Args:
            model_id: Model identifier.
            weight:   New weight value (must be >= 0).

        Raises:
            ValueError: If weight is negative.
        """
        if weight < 0.0:
            raise ValueError(
                f"Weight must be >= 0, got {weight} for model '{model_id}'"
            )
        self.weights[model_id] = weight

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_weights(
        self,
        model_inputs: List[ModelPredictionInput],
    ) -> Dict[str, float]:
        """Resolve effective weights for all supplied model inputs.

        - If the ensemble has a configured weight for a model, use it.
        - If the model has no configured weight, assign weight = 1.0
          (equal treatment of unknown models).
        """
        resolved: Dict[str, float] = {}
        for inp in model_inputs:
            resolved[inp.model_id] = self.weights.get(inp.model_id, 1.0)
        return resolved

    @staticmethod
    def _normalise_1x2(
        home_win: float,
        draw: float,
        away_win: float,
    ) -> Tuple[float, float, float]:
        """Normalise 1X2 probabilities to sum exactly to 1.0.

        Raises:
            ValueError: If all probabilities are zero.
        """
        total = home_win + draw + away_win
        if total <= 0.0:
            raise ValueError(
                "Cannot normalise: all 1X2 ensemble probabilities are zero."
            )
        return home_win / total, draw / total, away_win / total

    @staticmethod
    def _combine_btts(
        normalised_pairs: List[Tuple[ModelPredictionInput, float, float]],
    ) -> Tuple[Optional[float], Optional[float]]:
        """Combine BTTS probabilities across models.

        Returns (None, None) if any model does not supply BTTS probabilities.
        This prevents silent corruption by partial-market mixing.
        """
        btts_yes_values = [inp.btts_yes_probability for inp, _, _ in normalised_pairs]
        btts_no_values = [inp.btts_no_probability for inp, _, _ in normalised_pairs]

        if any(v is None for v in btts_yes_values) or any(v is None for v in btts_no_values):
            return None, None

        btts_yes = sum(
            v * nw
            for (inp, nw, _), v in zip(normalised_pairs, btts_yes_values)
        )
        btts_no = sum(
            v * nw
            for (inp, nw, _), v in zip(normalised_pairs, btts_no_values)
        )

        # Normalise BTTS
        total = btts_yes + btts_no
        if total > 0.0:
            btts_yes /= total
            btts_no /= total

        return btts_yes, btts_no


# ---------------------------------------------------------------------------
# Probability Calibration Interface (placeholder)
# ---------------------------------------------------------------------------

class ProbabilityCalibrator(ABC):
    """Abstract interface for probability calibration.
    
    Calibration adjusts raw model probabilities to match observed frequencies.
    This is essential for reliable confidence intervals and betting strategies.
    
    Usage:
        calibrator = IsotonicCalibrator()  # Example implementation
        calibrator.fit(predicted_probabilities, actual_outcomes)
        calibrated = calibrator.calibrate([0.45, 0.30, 0.25])
    
    Note: This is a placeholder interface. Implementations require historical
          match data with both predictions and outcomes.
    """
    
    @abstractmethod
    def fit(
        self,
        predicted_probabilities: List[List[float]],
        actual_outcomes: List[int]
    ) -> None:
        """Train calibrator on historical predictions and outcomes.
        
        Args:
            predicted_probabilities: List of [home_win, draw, away_win] predictions
            actual_outcomes: List of actual outcomes (0=home, 1=draw, 2=away)
        """
        pass
    
    @abstractmethod
    def calibrate(self, probabilities: List[float]) -> List[float]:
        """Calibrate a set of probabilities.
        
        Args:
            probabilities: Raw model probabilities [home_win, draw, away_win]
            
        Returns:
            Calibrated probabilities summing to 1.0
        """
        pass
    
    @abstractmethod
    def get_calibration_curve(self) -> Optional[Dict[str, List[float]]]:
        """Get calibration curve data for visualization.
        
        Returns:
            Dictionary with 'predicted' and 'observed' frequency lists, or None if not fitted
        """
        pass


# ---------------------------------------------------------------------------
# Backtesting Interface (placeholder)
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    """Result of a model backtest.
    
    Contains performance metrics computed from historical data.
    DO NOT fabricate these metrics without actual historical match outcomes.
    """
    
    n_matches: int
    """Number of matches in the backtest."""
    
    accuracy: Optional[float] = None
    """Proportion of correct 1X2 predictions (0.0-1.0)."""
    
    brier_score: Optional[float] = None
    """Brier score (lower is better, 0.0 = perfect)."""
    
    log_loss: Optional[float] = None
    """Logarithmic loss (lower is better)."""
    
    roi: Optional[float] = None
    """Return on investment if betting at market odds (can be negative)."""
    
    calibration_error: Optional[float] = None
    """Mean absolute calibration error."""
    
    coverage_start: Optional[datetime] = None
    """Start date of backtest period."""
    
    coverage_end: Optional[datetime] = None
    """End date of backtest period."""
    
    note: str = "Requires historical match data and outcomes"
    """Note about data requirements or limitations."""


class BacktestRunner(ABC):
    """Abstract interface for model backtesting.
    
    Backtesting evaluates model performance on historical data by:
    1. Generating predictions for past matches using only information
       available at the time
    2. Comparing predictions to actual outcomes
    3. Computing performance metrics
    
    Critical: Backtesting MUST prevent data leakage. Features for match M
              can only use data from before M's scheduled time.
    
    Usage:
        runner = RollingWindowBacktester(window_days=365)
        result = runner.run_backtest(historical_matches, model)
        print(f"Accuracy: {result.accuracy:.2%}")
    
    Note: This is a placeholder interface. Implementations require a database
          of historical matches with outcomes.
    """
    
    @abstractmethod
    def run_backtest(
        self,
        matches: List[any],  # List of Match entities with outcomes
        model: any,  # Model to test (must have predict method)
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> BacktestResult:
        """Run backtest on historical matches.
        
        Args:
            matches: Historical matches with known outcomes
            model: Model to evaluate
            start_date: Optional start of backtest period
            end_date: Optional end of backtest period
            
        Returns:
            BacktestResult with performance metrics
            
        Raises:
            ValueError: If matches have no outcomes or insufficient data
        """
        pass
    
    @abstractmethod
    def get_prediction_errors(self) -> Optional[List[Dict[str, any]]]:
        """Get detailed prediction errors from last backtest.
        
        Returns:
            List of per-match error details, or None if no backtest run yet
        """
        pass


# ---------------------------------------------------------------------------
# Ensemble Aggregation Interface (placeholder for future multi-model support)
# ---------------------------------------------------------------------------

class EnsembleAggregator(ABC):
    """Abstract interface for combining multiple model outputs.
    
    This interface supports more sophisticated ensemble strategies beyond
    simple weighted averaging:
    - Stacking (meta-model trained on base model outputs)
    - Dynamic weighting based on match context
    - Selective ensembling (use different models for different matches)
    
    The current EnsembleModel implements weighted averaging. Future
    implementations can use this interface for advanced strategies.
    
    Usage:
        aggregator = StackingAggregator(meta_model)
        aggregator.fit(training_data)
        result = aggregator.aggregate([model1_output, model2_output, ...])
    
    Note: This is a placeholder interface for future development.
    """
    
    @abstractmethod
    def aggregate(self, model_outputs: List[ModelPredictionInput]) -> EnsemblePrediction:
        """Combine multiple model predictions into an ensemble prediction.
        
        Args:
            model_outputs: Predictions from individual models
            
        Returns:
            Combined ensemble prediction
        """
        pass
    
    @abstractmethod
    def fit(self, training_data: List[Dict[str, any]]) -> None:
        """Train the aggregator on historical data (for learning-based strategies).
        
        Args:
            training_data: Historical matches with model predictions and outcomes
        """
        pass
    
    @abstractmethod
    def get_model_importances(self) -> Optional[Dict[str, float]]:
        """Get learned importance weights for each model.
        
        Returns:
            Dictionary mapping model_id to importance score, or None if not applicable
        """
        pass
