"""Tests for Logistic Regression 1X2 prediction model.

Covers:
- Model initialization and parameter validation
- fit() with valid and invalid data
- predict() output structure and probability validity
- Train/predict strict separation
- Softmax output normalization
- Determinism with fixed seed
- Feature standardization (missing features imputed to mean)
- Label validation
- Unfitted model raises RuntimeError
- Compatibility with ensemble ModelPredictionInput
"""

import pytest
from typing import Dict, List, Optional, Tuple

from app.prediction.logistic_regression import (
    LogisticRegressionModel,
    LogisticRegressionPrediction,
    TrainingStats,
    OUTCOME_TO_LABEL,
    DEFAULT_FEATURE_KEYS,
)
from app.prediction.ensemble import ModelPredictionInput
from app.domain.enums import ModelType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simple_features(
    home_att: float = 1.5,
    away_att: float = 1.2,
    home_def: float = 1.1,
    away_def: float = 1.0,
) -> Dict[str, Optional[float]]:
    return {
        "home_attack_strength": home_att,
        "home_defense_strength": home_def,
        "away_attack_strength": away_att,
        "away_defense_strength": away_def,
    }


def _make_training_data(n: int = 60) -> List[Tuple[Dict, str]]:
    """Build a diverse training set with all three outcomes present."""
    labels = ["home_win", "draw", "away_win"]
    samples = []
    for i in range(n):
        label = labels[i % 3]
        if label == "home_win":
            features = _simple_features(home_att=2.0, away_att=0.8, home_def=0.7, away_def=1.5)
        elif label == "away_win":
            features = _simple_features(home_att=0.8, away_att=2.0, home_def=1.5, away_def=0.7)
        else:
            features = _simple_features(home_att=1.3, away_att=1.3, home_def=1.0, away_def=1.0)
        samples.append((features, label))
    return samples


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestLRInit:

    def test_default_init(self):
        m = LogisticRegressionModel()
        assert m.learning_rate == 0.01
        assert m.n_epochs == 200
        assert m.seed == 42
        assert m.is_fitted is False

    def test_custom_init(self):
        m = LogisticRegressionModel(
            learning_rate=0.05, n_epochs=100, l2_lambda=1e-3, seed=7
        )
        assert m.learning_rate == 0.05
        assert m.n_epochs == 100
        assert m.seed == 7

    def test_invalid_learning_rate(self):
        with pytest.raises(ValueError, match="learning_rate"):
            LogisticRegressionModel(learning_rate=0.0)

    def test_invalid_n_epochs(self):
        with pytest.raises(ValueError, match="n_epochs"):
            LogisticRegressionModel(n_epochs=0)

    def test_custom_feature_keys(self):
        keys = ["home_attack_strength", "away_attack_strength"]
        m = LogisticRegressionModel(feature_keys=keys)
        assert m.feature_keys == keys


# ---------------------------------------------------------------------------
# fit()
# ---------------------------------------------------------------------------

class TestLRFit:

    def test_fit_returns_self(self):
        m = LogisticRegressionModel(n_epochs=10, seed=42)
        samples = _make_training_data(30)
        result = m.fit(samples)
        assert result is m

    def test_fit_sets_is_fitted(self):
        m = LogisticRegressionModel(n_epochs=10, seed=42)
        m.fit(_make_training_data(30))
        assert m.is_fitted is True

    def test_fit_empty_raises(self):
        m = LogisticRegressionModel()
        with pytest.raises(ValueError, match="empty"):
            m.fit([])

    def test_fit_invalid_label_raises(self):
        m = LogisticRegressionModel()
        with pytest.raises(ValueError, match="Invalid label"):
            m.fit([(_simple_features(), "invalid_label")])

    def test_fit_single_sample_raises(self):
        m = LogisticRegressionModel()
        with pytest.raises(ValueError):
            m.fit([(_simple_features(), "home_win")])

    def test_fit_all_same_label(self):
        """Fitting with a single label should not crash (model may converge trivially)."""
        m = LogisticRegressionModel(n_epochs=10, seed=42)
        samples = [(_simple_features(), "home_win")] * 5
        # Should not raise — model can still be used, just poorly calibrated
        m.fit(samples)
        assert m.is_fitted

    def test_training_stats_populated_after_fit(self):
        m = LogisticRegressionModel(n_epochs=10, seed=42)
        m.fit(_make_training_data(30))
        assert m._training_stats is not None
        assert isinstance(m._training_stats, TrainingStats)
        assert m._training_stats.n_samples == 30

    def test_weights_populated_after_fit(self):
        m = LogisticRegressionModel(n_epochs=10, seed=42)
        m.fit(_make_training_data(30))
        assert m._weights is not None
        assert len(m._weights) == 3  # 3 classes


# ---------------------------------------------------------------------------
# predict()
# ---------------------------------------------------------------------------

class TestLRPredict:

    def setup_method(self):
        self.model = LogisticRegressionModel(n_epochs=50, seed=42)
        self.model.fit(_make_training_data(60))

    def test_returns_prediction_object(self):
        result = self.model.predict_legacy(_simple_features())
        assert isinstance(result, LogisticRegressionPrediction)

    def test_probabilities_sum_to_one(self):
        result = self.model.predict_legacy(_simple_features())
        total = (result.home_win_probability +
                 result.draw_probability +
                 result.away_win_probability)
        assert abs(total - 1.0) < 1e-9

    def test_all_probabilities_in_range(self):
        result = self.model.predict_legacy(_simple_features())
        assert 0.0 <= result.home_win_probability <= 1.0
        assert 0.0 <= result.draw_probability <= 1.0
        assert 0.0 <= result.away_win_probability <= 1.0

    def test_predict_proba_returns_tuple(self):
        h, d, a = self.model.predict_proba(_simple_features())
        assert abs(h + d + a - 1.0) < 1e-9

    def test_unfitted_model_raises(self):
        m = LogisticRegressionModel()
        with pytest.raises(RuntimeError, match="fitted"):
            m.predict_legacy(_simple_features())

    def test_max_class_is_valid_label(self):
        result = self.model.predict_legacy(_simple_features())
        assert result.max_class in ("home_win", "draw", "away_win")

    def test_feature_vector_stored(self):
        result = self.model.predict_legacy(_simple_features())
        assert result.feature_vector is not None
        assert len(result.feature_vector) > 0

    def test_features_used_stored(self):
        result = self.model.predict_legacy(_simple_features())
        assert result.features_used is not None


# ---------------------------------------------------------------------------
# Missing features / imputation
# ---------------------------------------------------------------------------

class TestLRMissingFeatures:

    def test_none_feature_does_not_crash(self):
        """None feature values should be imputed with training mean."""
        m = LogisticRegressionModel(n_epochs=20, seed=42)
        m.fit(_make_training_data(30))
        features = {"home_attack_strength": None, "away_attack_strength": 1.2}
        result = m.predict_legacy(features)
        total = (result.home_win_probability +
                 result.draw_probability +
                 result.away_win_probability)
        assert abs(total - 1.0) < 1e-9

    def test_empty_feature_dict_does_not_crash(self):
        """All features missing → all imputed to means."""
        m = LogisticRegressionModel(n_epochs=20, seed=42)
        m.fit(_make_training_data(30))
        result = m.predict_legacy({})
        total = (result.home_win_probability +
                 result.draw_probability +
                 result.away_win_probability)
        assert abs(total - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestLRDeterminism:

    def test_same_seed_same_weights(self):
        """Two models with same seed produce identical weights after fitting."""
        samples = _make_training_data(40)
        m1 = LogisticRegressionModel(n_epochs=50, seed=42)
        m2 = LogisticRegressionModel(n_epochs=50, seed=42)
        m1.fit(samples)
        m2.fit(samples)
        for c in range(3):
            for j in range(len(m1._weights[c])):
                assert m1._weights[c][j] == m2._weights[c][j]

    def test_different_seed_different_weights(self):
        samples = _make_training_data(40)
        m1 = LogisticRegressionModel(n_epochs=50, seed=1)
        m2 = LogisticRegressionModel(n_epochs=50, seed=99)
        m1.fit(samples)
        m2.fit(samples)
        # At least one weight should differ
        any_diff = any(
            m1._weights[c][j] != m2._weights[c][j]
            for c in range(3)
            for j in range(len(m1._weights[c]))
        )
        assert any_diff

    def test_same_inputs_same_predictions(self):
        m = LogisticRegressionModel(n_epochs=50, seed=42)
        m.fit(_make_training_data(40))
        features = _simple_features()
        p1 = m.predict_legacy(features)
        p2 = m.predict_legacy(features)
        assert p1.home_win_probability == p2.home_win_probability
        assert p1.draw_probability == p2.draw_probability
        assert p1.away_win_probability == p2.away_win_probability


# ---------------------------------------------------------------------------
# Strict train/predict separation
# ---------------------------------------------------------------------------

class TestLRTrainPredictSeparation:

    def test_predict_uses_only_training_statistics(self):
        """Prediction should not change after seeing new data."""
        m = LogisticRegressionModel(n_epochs=30, seed=42)
        training = _make_training_data(30)
        m.fit(training)
        features = _simple_features()
        pred_before = m.predict_legacy(features)
        # Calling predict again with same features should give same result
        pred_after = m.predict_legacy(features)
        assert pred_before.home_win_probability == pred_after.home_win_probability

    def test_predictions_do_not_update_model(self):
        """predict() must be pure: it must not modify internal state."""
        m = LogisticRegressionModel(n_epochs=30, seed=42)
        m.fit(_make_training_data(30))
        weights_before = [list(row) for row in m._weights]
        m.predict(_simple_features())
        weights_after = [list(row) for row in m._weights]
        assert weights_before == weights_after


# ---------------------------------------------------------------------------
# Ensemble compatibility
# ---------------------------------------------------------------------------

class TestLREnsembleCompatibility:

    def test_prediction_feeds_ensemble(self):
        from app.prediction.ensemble import EnsembleModel

        m = LogisticRegressionModel(n_epochs=30, seed=42)
        m.fit(_make_training_data(30))
        pred = m.predict_legacy(_simple_features())

        inp = ModelPredictionInput(
            model_id="lr_v1",
            model_type=ModelType.LOGISTIC_REGRESSION,
            home_win_probability=pred.home_win_probability,
            draw_probability=pred.draw_probability,
            away_win_probability=pred.away_win_probability,
        )
        inp.validate()

        ensemble = EnsembleModel(weights={"lr_v1": 1.0})
        result = ensemble.predict([inp])
        total = (result.home_win_probability +
                 result.draw_probability +
                 result.away_win_probability)
        assert abs(total - 1.0) < 1e-9
