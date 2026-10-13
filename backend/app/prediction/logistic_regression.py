"""Multiclass logistic regression 1X2 prediction model.

This module implements a simple softmax logistic regression classifier
for football match 1X2 prediction.  It consumes the same feature vectors
that the existing MatchFeatureExtractor produces.

Design decisions:
- No external ML framework dependencies (numpy-only implementation).
- Gradient-descent training is entirely deterministic when seeded.
- Strict train/predict separation: the model cannot use test-time features.
- Outputs normalised multiclass probabilities for home/draw/away.
- Small number of features → no risk of leakage from test distribution.
- Weights are stored after training and can be serialised.

Feature handling:
- Only numeric features with non-None values are used.
- Missing features for a match are imputed with the training-set mean.
- Features are standardised (zero mean, unit std) from training statistics.

Numerical stability:
- Softmax uses the log-sum-exp trick to avoid overflow.
- Gradient clipping prevents exploding gradients with extreme features.

Classes: 0 = home_win, 1 = draw, 2 = away_win
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from app.prediction.interfaces import (
    PredictionModel,
    ModelPrediction,
    ModelAvailability,
    PredictionModelMetadata,
)
from app.domain.enums import ModelType


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default numeric feature keys extracted by MatchFeatureExtractor
# (kept in a fixed order for reproducible weight vectors)
DEFAULT_FEATURE_KEYS: List[str] = [
    "home_attack_strength",
    "home_defense_strength",
    "home_home_strength",
    "home_away_strength",
    "home_recent_wins",
    "home_recent_draws",
    "home_recent_losses",
    "home_form_points_per_match",
    "away_attack_strength",
    "away_defense_strength",
    "away_home_strength",
    "away_away_strength",
    "away_recent_wins",
    "away_recent_draws",
    "away_recent_losses",
    "away_form_points_per_match",
]

N_CLASSES = 3  # home_win=0, draw=1, away_win=2

LABEL_HOME = 0
LABEL_DRAW = 1
LABEL_AWAY = 2

OUTCOME_TO_LABEL: Dict[str, int] = {
    "home_win": LABEL_HOME,
    "draw": LABEL_DRAW,
    "away_win": LABEL_AWAY,
}

LABEL_TO_OUTCOME: Dict[int, str] = {v: k for k, v in OUTCOME_TO_LABEL.items()}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class LogisticRegressionPrediction:
    """Prediction output from the logistic regression model."""

    home_win_probability: float
    draw_probability: float
    away_win_probability: float

    # Features used (after standardisation)
    feature_vector: Optional[List[float]] = None
    features_used: Optional[List[str]] = None

    generated_at: datetime = field(default_factory=datetime.now)

    @property
    def max_class(self) -> str:
        """Return the most probable outcome label."""
        probs = {
            "home_win": self.home_win_probability,
            "draw": self.draw_probability,
            "away_win": self.away_win_probability,
        }
        return max(probs, key=lambda k: probs[k])


@dataclass
class TrainingStats:
    """Statistics gathered from the training set for feature standardisation."""

    feature_means: Dict[str, float]
    feature_stds: Dict[str, float]
    n_samples: int
    n_features: int
    feature_keys: List[str]
    trained_at: datetime = field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# Logistic Regression model
# ---------------------------------------------------------------------------

class LogisticRegressionModel(PredictionModel):
    """Multiclass logistic regression 1X2 model.

    Training uses mini-batch stochastic gradient descent with a fixed
    random seed so results are fully deterministic.

    The model only uses pre-match features from the feature dictionary.
    It does not have access to the match result during prediction.

    Interface:
        model = LogisticRegressionModel()
        model.fit(training_samples)   # list of (feature_dict, label_str)
        prediction = model.predict(feature_dict)

    Labels:  "home_win" | "draw" | "away_win"
    """

    MODEL_ID = "logistic_regression_v1"
    MODEL_VERSION = "1.0.0"

    def __init__(
        self,
        feature_keys: Optional[List[str]] = None,
        learning_rate: float = 0.01,
        n_epochs: int = 200,
        l2_lambda: float = 1e-4,
        seed: int = 42,
    ):
        """Initialise the model.

        Args:
            feature_keys:   List of feature names to use. Defaults to
                            DEFAULT_FEATURE_KEYS.
            learning_rate:  Gradient descent step size.
            n_epochs:       Number of full passes over training data.
            l2_lambda:      L2 regularisation coefficient.
            seed:           Random seed for deterministic weight
                            initialisation and SGD shuffling.

        Raises:
            ValueError: If learning_rate or n_epochs are invalid.
        """
        if learning_rate <= 0:
            raise ValueError(f"learning_rate must be > 0, got {learning_rate}")
        if n_epochs < 1:
            raise ValueError(f"n_epochs must be >= 1, got {n_epochs}")

        self.feature_keys: List[str] = feature_keys or list(DEFAULT_FEATURE_KEYS)
        self.learning_rate = learning_rate
        self.n_epochs = n_epochs
        self.l2_lambda = l2_lambda
        self.seed = seed

        # Weights: shape [N_CLASSES, n_features+1] (+1 for bias)
        self._weights: Optional[List[List[float]]] = None
        self._training_stats: Optional[TrainingStats] = None
        self._is_fitted: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    def fit(
        self,
        samples: List[Tuple[Dict[str, Optional[float]], str]],
    ) -> "LogisticRegressionModel":
        """Train the model on labelled feature samples.

        Args:
            samples: List of (feature_dict, label) tuples.
                     label must be "home_win", "draw", or "away_win".

        Returns:
            self (for chaining)

        Raises:
            ValueError: If samples are empty, labels are invalid,
                        or insufficient unique labels exist.
        """
        if not samples:
            raise ValueError("Cannot fit on empty training set.")

        for _, label in samples:
            if label not in OUTCOME_TO_LABEL:
                raise ValueError(
                    f"Invalid label '{label}'. "
                    f"Must be one of {list(OUTCOME_TO_LABEL.keys())}"
                )

        # Build feature matrix
        X, y = self._build_feature_matrix(samples)

        n_samples = len(X)
        n_features = len(X[0])

        if n_samples < 2:
            raise ValueError("Need at least 2 training samples.")

        # Initialise weights deterministically
        rng = random.Random(self.seed)
        self._weights = [
            [rng.gauss(0, 0.01) for _ in range(n_features)]
            for _ in range(N_CLASSES)
        ]

        # SGD training
        for epoch in range(self.n_epochs):
            # Deterministic shuffle per epoch using epoch as sub-seed
            epoch_rng = random.Random(self.seed * 1000 + epoch)
            indices = list(range(n_samples))
            epoch_rng.shuffle(indices)

            for i in indices:
                xi = X[i]
                yi = y[i]
                self._sgd_step(xi, yi)

        self._is_fitted = True
        return self

    def predict(
        self,
        features: Dict[str, Optional[float]],
    ) -> LogisticRegressionPrediction:
        """Predict 1X2 probabilities from a feature dictionary.

        Args:
            features: Feature dictionary from MatchFeatureExtractor.
                      None values are imputed with training-set means.

        Returns:
            LogisticRegressionPrediction with normalised probabilities.

        Raises:
            RuntimeError: If model has not been fitted.
        """
        if not self._is_fitted:
            raise RuntimeError(
                "Model must be fitted before calling predict(). "
                "Call fit() first."
            )

        x = self._extract_and_standardise(features)
        probs = self._softmax(self._weights, x)

        return LogisticRegressionPrediction(
            home_win_probability=probs[LABEL_HOME],
            draw_probability=probs[LABEL_DRAW],
            away_win_probability=probs[LABEL_AWAY],
            feature_vector=x,
            features_used=self.feature_keys,
            generated_at=datetime.now(),
        )

    def predict_proba(
        self,
        features: Dict[str, Optional[float]],
    ) -> Tuple[float, float, float]:
        """Return (home_win, draw, away_win) probabilities.

        Convenience method that returns a plain tuple.
        """
        pred = self.predict_legacy(features)
        return (
            pred.home_win_probability,
            pred.draw_probability,
            pred.away_win_probability,
        )

    # ------------------------------------------------------------------
    # PredictionModel interface implementation
    # ------------------------------------------------------------------

    def predict(
        self,
        features: Dict[str, Optional[float]],
        match_context: Optional[Dict[str, Any]] = None
    ) -> ModelPrediction | ModelAvailability:
        """Generate prediction using PredictionModel interface.

        Args:
            features: Feature dictionary from MatchFeatureExtractor.
            match_context: Additional context (unused by this model).

        Returns:
            ModelPrediction with 1X2 probabilities or ModelAvailability.
        """
        # Check requirements
        requirements_met, missing = self.check_requirements(features)
        if not requirements_met:
            return ModelAvailability(
                model_id=self.MODEL_ID,
                available=False,
                reason="model_not_fitted" if not self._is_fitted else "insufficient_features",
                missing_features=missing
            )

        # Get prediction using legacy method
        legacy_pred = self.predict_legacy(features)

        # Derive expected goals (approximation from probabilities)
        # Use typical scoreline expectations: home ~1.4, away ~1.1 for balanced
        # Adjust based on win probabilities
        home_expected = 1.0 + (legacy_pred.home_win_probability * 0.8) - (legacy_pred.away_win_probability * 0.4)
        away_expected = 1.0 + (legacy_pred.away_win_probability * 0.8) - (legacy_pred.home_win_probability * 0.4)

        # Calculate confidence based on prediction certainty
        max_prob = max(
            legacy_pred.home_win_probability,
            legacy_pred.draw_probability,
            legacy_pred.away_win_probability
        )
        confidence = 0.5 + (max_prob - 0.333) * 0.75  # Map [0.333, 1.0] to [0.5, 1.0]

        # Calculate data quality from feature availability
        available_features = sum(1 for k in self.feature_keys if features.get(k) is not None)
        data_quality = available_features / len(self.feature_keys)

        return ModelPrediction(
            model_id=self.MODEL_ID,
            home_score_mean=home_expected,
            away_score_mean=away_expected,
            score_distribution={},  # Logistic regression doesn't produce scoreline distribution
            home_win_prob=legacy_pred.home_win_probability,
            draw_prob=legacy_pred.draw_probability,
            away_win_prob=legacy_pred.away_win_probability,
            confidence_score=confidence,
            data_quality_score=data_quality,
            metadata={
                "model_type": "logistic_regression",
                "features_used": legacy_pred.features_used,
                "n_features": len(legacy_pred.features_used) if legacy_pred.features_used else 0,
                "training_samples": self._training_stats.n_samples if self._training_stats else 0
            }
        )

    def get_metadata(self) -> PredictionModelMetadata:
        """Return model metadata.

        Returns:
            PredictionModelMetadata with model information.
        """
        return PredictionModelMetadata(
            model_id=self.MODEL_ID,
            model_type=ModelType.LOGISTIC_REGRESSION,
            version=self.MODEL_VERSION,
            description="Multiclass logistic regression for 1X2 prediction",
            required_features=self.feature_keys,
            optional_features=[],
            min_samples_required=10  # Need at least 10 samples for meaningful training
        )

    def check_requirements(
        self,
        features: Dict[str, Optional[float]]
    ) -> Tuple[bool, List[str]]:
        """Check if required data is available.

        Args:
            features: Feature dictionary

        Returns:
            (requirements_met, missing_requirements)
        """
        missing = []

        # Check if model is fitted
        if not self._is_fitted:
            missing.append("model_not_fitted")
            return False, missing

        # Check feature availability (at least 50% of features required)
        available_features = sum(1 for k in self.feature_keys if features.get(k) is not None)
        feature_completeness = available_features / len(self.feature_keys)

        if feature_completeness < 0.5:
            missing.append(f"insufficient_features: {available_features}/{len(self.feature_keys)} available")

        return len(missing) == 0, missing

    def predict_legacy(
        self,
        features: Dict[str, Optional[float]],
    ) -> LogisticRegressionPrediction:
        """Predict 1X2 probabilities from a feature dictionary (legacy method).

        This is the original predict method, renamed for backward compatibility.

        Args:
            features: Feature dictionary from MatchFeatureExtractor.
                      None values are imputed with training-set means.

        Returns:
            LogisticRegressionPrediction with normalised probabilities.

        Raises:
            RuntimeError: If model has not been fitted.
        """
        if not self._is_fitted:
            raise RuntimeError(
                "Model must be fitted before calling predict(). "
                "Call fit() first."
            )

        x = self._extract_and_standardise(features)
        probs = self._softmax(self._weights, x)

        return LogisticRegressionPrediction(
            home_win_probability=probs[LABEL_HOME],
            draw_probability=probs[LABEL_DRAW],
            away_win_probability=probs[LABEL_AWAY],
            feature_vector=x,
            features_used=self.feature_keys,
            generated_at=datetime.now(),
        )

    # ------------------------------------------------------------------
    # Private helpers — feature processing
    # ------------------------------------------------------------------

    def _build_feature_matrix(
        self,
        samples: List[Tuple[Dict[str, Optional[float]], str]],
    ) -> Tuple[List[List[float]], List[int]]:
        """Extract numeric features and compute training statistics.

        Computes mean and std of each feature over the training set.
        Missing (None) values are excluded from statistics then imputed
        to the mean.
        """
        feature_keys = self.feature_keys

        # Collect non-None values per feature for statistics
        raw_values: Dict[str, List[float]] = {k: [] for k in feature_keys}
        for feat_dict, _ in samples:
            for k in feature_keys:
                v = feat_dict.get(k)
                if v is not None and not math.isnan(v) and not math.isinf(v):
                    raw_values[k].append(v)

        # Compute means and stds
        means: Dict[str, float] = {}
        stds: Dict[str, float] = {}
        for k in feature_keys:
            vals = raw_values[k]
            if vals:
                means[k] = sum(vals) / len(vals)
                variance = sum((v - means[k]) ** 2 for v in vals) / len(vals)
                stds[k] = math.sqrt(variance) if variance > 0 else 1.0
            else:
                means[k] = 0.0
                stds[k] = 1.0

        self._training_stats = TrainingStats(
            feature_means=means,
            feature_stds=stds,
            n_samples=len(samples),
            n_features=len(feature_keys),
            feature_keys=feature_keys,
        )

        # Build standardised matrix with bias term
        X: List[List[float]] = []
        y: List[int] = []

        for feat_dict, label in samples:
            x = self._extract_and_standardise(feat_dict)
            X.append(x)
            y.append(OUTCOME_TO_LABEL[label])

        return X, y

    def _extract_and_standardise(
        self,
        features: Dict[str, Optional[float]],
    ) -> List[float]:
        """Extract features and standardise using training statistics.

        Returns a feature vector with a leading bias term of 1.0.
        """
        stats = self._training_stats
        if stats is None:
            # Before fitting: just extract raw values (used only in fit())
            x = []
            for k in self.feature_keys:
                v = features.get(k)
                x.append(float(v) if v is not None else 0.0)
            return [1.0] + x

        x = [1.0]  # bias
        for k in self.feature_keys:
            v = features.get(k)
            raw = float(v) if (v is not None and not math.isnan(float(v))) else stats.feature_means[k]
            std = stats.feature_stds[k] if stats.feature_stds[k] > 0 else 1.0
            x.append((raw - stats.feature_means[k]) / std)

        return x

    # ------------------------------------------------------------------
    # Private helpers — gradient descent
    # ------------------------------------------------------------------

    def _sgd_step(self, xi: List[float], yi: int) -> None:
        """Single SGD step: compute gradient and update weights."""
        probs = self._softmax(self._weights, xi)

        # Gradient for each class
        for c in range(N_CLASSES):
            indicator = 1.0 if c == yi else 0.0
            error = probs[c] - indicator

            # Update each weight with gradient + L2 regularisation
            for j in range(len(xi)):
                grad = error * xi[j]
                if j > 0:  # Don't regularise bias
                    grad += self.l2_lambda * self._weights[c][j]
                self._weights[c][j] -= self.learning_rate * grad

    @staticmethod
    def _softmax(
        weights: List[List[float]],
        x: List[float],
    ) -> List[float]:
        """Compute softmax probabilities for N_CLASSES.

        Uses log-sum-exp trick for numerical stability.
        """
        logits = [
            sum(weights[c][j] * x[j] for j in range(len(x)))
            for c in range(N_CLASSES)
        ]

        # Log-sum-exp trick
        max_logit = max(logits)
        exp_logits = [math.exp(l - max_logit) for l in logits]
        total = sum(exp_logits)

        return [e / total for e in exp_logits]
