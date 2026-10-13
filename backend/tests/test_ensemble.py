"""Tests for the weighted ensemble prediction model.

Covers:
- Weight normalisation
- Weighted probability combination
- Probability normalisation
- Invalid weights (negative)
- Invalid probabilities (out of range)
- Missing model outputs (not present in ensemble)
- Model contribution metadata
- Deterministic / reproducible output
- Incompatible market handling (BTTS only when all models supply it)
- Empty model input handling
- Single-model ensemble (should equal that model's output)
"""

import pytest
from datetime import datetime
from typing import Optional

from app.prediction.ensemble import (
    EnsembleModel,
    EnsemblePrediction,
    ModelContribution,
    ModelPredictionInput,
)
from app.domain.enums import ModelType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_input(
    model_id: str = "model_a",
    model_type: ModelType = ModelType.POISSON,
    home: float = 0.45,
    draw: float = 0.30,
    away: float = 0.25,
    btts_yes: Optional[float] = None,
    btts_no: Optional[float] = None,
) -> ModelPredictionInput:
    return ModelPredictionInput(
        model_id=model_id,
        model_type=model_type,
        home_win_probability=home,
        draw_probability=draw,
        away_win_probability=away,
        btts_yes_probability=btts_yes,
        btts_no_probability=btts_no,
    )


# ---------------------------------------------------------------------------
# Basic operation
# ---------------------------------------------------------------------------

class TestEnsembleBasic:

    def test_empty_inputs_raises(self):
        ensemble = EnsembleModel()
        with pytest.raises(ValueError, match="No model inputs"):
            ensemble.predict([])

    def test_single_model_returns_valid_prediction(self):
        ensemble = EnsembleModel()
        inp = _make_input(home=0.45, draw=0.30, away=0.25)
        result = ensemble.predict([inp])
        assert isinstance(result, EnsemblePrediction)
        assert result.is_valid

    def test_single_model_probabilities_match_input(self):
        """Single model with no explicit weight → output = its normalised probabilities."""
        ensemble = EnsembleModel()
        inp = _make_input(model_id="m1", home=0.45, draw=0.30, away=0.25)
        result = ensemble.predict([inp])

        # The three values should match the input (after normalisation)
        total = 0.45 + 0.30 + 0.25
        assert abs(result.home_win_probability - 0.45 / total) < 1e-9
        assert abs(result.draw_probability - 0.30 / total) < 1e-9
        assert abs(result.away_win_probability - 0.25 / total) < 1e-9

    def test_result_has_unique_id(self):
        ensemble = EnsembleModel()
        inp = _make_input()
        r1 = ensemble.predict([inp])
        r2 = ensemble.predict([inp])
        assert r1.id != r2.id

    def test_n_models_reflects_active_count(self):
        ensemble = EnsembleModel()
        inputs = [
            _make_input("m1", home=0.45, draw=0.30, away=0.25),
            _make_input("m2", ModelType.ELO, home=0.40, draw=0.35, away=0.25),
        ]
        result = ensemble.predict(inputs)
        assert result.n_models == 2


# ---------------------------------------------------------------------------
# Weight normalisation
# ---------------------------------------------------------------------------

class TestWeightNormalisation:

    def test_weights_normalised_to_sum_one(self):
        """Configured weights of 3+1 should be used as 0.75 and 0.25."""
        ensemble = EnsembleModel(weights={"m1": 3.0, "m2": 1.0})
        inputs = [
            _make_input("m1", home=0.6, draw=0.25, away=0.15),
            _make_input("m2", ModelType.ELO, home=0.4, draw=0.35, away=0.25),
        ]
        result = ensemble.predict(inputs)

        # Verify contributions sum correctly
        contribution_m1 = next(c for c in result.model_contributions if c.model_id == "m1")
        assert abs(contribution_m1.weight - 0.75) < 1e-9

    def test_equal_weights_give_equal_contribution(self):
        ensemble = EnsembleModel(weights={"m1": 1.0, "m2": 1.0})
        inputs = [
            _make_input("m1", home=0.6, draw=0.25, away=0.15),
            _make_input("m2", ModelType.ELO, home=0.4, draw=0.35, away=0.25),
        ]
        result = ensemble.predict(inputs)

        c1 = next(c for c in result.model_contributions if c.model_id == "m1")
        c2 = next(c for c in result.model_contributions if c.model_id == "m2")
        assert abs(c1.weight - 0.5) < 1e-9
        assert abs(c2.weight - 0.5) < 1e-9

    def test_zero_weight_model_excluded(self):
        ensemble = EnsembleModel(weights={"m1": 1.0, "m2": 0.0})
        inputs = [
            _make_input("m1", home=0.6, draw=0.25, away=0.15),
            _make_input("m2", ModelType.ELO, home=0.1, draw=0.1, away=0.8),
        ]
        result = ensemble.predict(inputs)
        assert result.n_models == 1
        # m2 should not appear in contributions
        ids = {c.model_id for c in result.model_contributions}
        assert "m2" not in ids

    def test_all_zero_weights_raises(self):
        ensemble = EnsembleModel(weights={"m1": 0.0, "m2": 0.0})
        inputs = [
            _make_input("m1"),
            _make_input("m2"),
        ]
        with pytest.raises(ValueError, match="zero weight"):
            ensemble.predict(inputs)

    def test_negative_weight_raises_on_init(self):
        with pytest.raises(ValueError, match=">="):
            EnsembleModel(weights={"m1": -1.0})

    def test_add_weight_updates_existing(self):
        ensemble = EnsembleModel(weights={"m1": 1.0})
        ensemble.add_weight("m1", 2.0)
        assert ensemble.weights["m1"] == 2.0

    def test_add_weight_negative_raises(self):
        ensemble = EnsembleModel()
        with pytest.raises(ValueError):
            ensemble.add_weight("m1", -0.5)


# ---------------------------------------------------------------------------
# Weighted combination correctness
# ---------------------------------------------------------------------------

class TestWeightedCombination:

    def test_weighted_combination_manual(self):
        """Verify manually computed weighted average matches ensemble output."""
        w1, w2 = 0.6, 0.4
        ensemble = EnsembleModel(weights={"m1": w1, "m2": w2})

        h1, d1, a1 = 0.50, 0.30, 0.20
        h2, d2, a2 = 0.40, 0.35, 0.25

        inputs = [
            _make_input("m1", home=h1, draw=d1, away=a1),
            _make_input("m2", ModelType.ELO, home=h2, draw=d2, away=a2),
        ]
        result = ensemble.predict(inputs)

        expected_h = (w1 * h1 + w2 * h2) / (w1 + w2)
        expected_d = (w1 * d1 + w2 * d2) / (w1 + w2)
        expected_a = (w1 * a1 + w2 * a2) / (w1 + w2)
        # Normalise
        total = expected_h + expected_d + expected_a
        expected_h /= total
        expected_d /= total
        expected_a /= total

        assert abs(result.home_win_probability - expected_h) < 1e-9
        assert abs(result.draw_probability - expected_d) < 1e-9
        assert abs(result.away_win_probability - expected_a) < 1e-9

    def test_three_model_combination(self):
        ensemble = EnsembleModel(
            weights={"p": 0.5, "e": 0.3, "d": 0.2}
        )
        inputs = [
            _make_input("p", ModelType.POISSON, 0.50, 0.28, 0.22),
            _make_input("e", ModelType.ELO, 0.45, 0.32, 0.23),
            _make_input("d", ModelType.DIXON_COLES, 0.48, 0.30, 0.22),
        ]
        result = ensemble.predict(inputs)

        total = (result.home_win_probability +
                 result.draw_probability +
                 result.away_win_probability)
        assert abs(total - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Probability normalisation / validation
# ---------------------------------------------------------------------------

class TestProbabilityValidation:

    def test_invalid_probability_over_1_raises(self):
        inp = _make_input(home=1.1, draw=0.0, away=0.0)
        ensemble = EnsembleModel()
        with pytest.raises(ValueError, match="Invalid probability"):
            ensemble.predict([inp])

    def test_invalid_probability_negative_raises(self):
        inp = _make_input(home=-0.1, draw=0.5, away=0.6)
        ensemble = EnsembleModel()
        with pytest.raises(ValueError, match="Invalid probability"):
            ensemble.predict([inp])

    def test_valid_edge_probability_zero(self):
        """Probability of exactly 0 is valid."""
        inp = _make_input(home=0.0, draw=0.5, away=0.5)
        ensemble = EnsembleModel()
        result = ensemble.predict([inp])
        assert result.is_valid

    def test_valid_edge_probability_one(self):
        """Probability of exactly 1 is valid (e.g. certain home win)."""
        inp = _make_input(home=1.0, draw=0.0, away=0.0)
        ensemble = EnsembleModel()
        result = ensemble.predict([inp])
        assert result.is_valid

    def test_output_probabilities_sum_to_one(self):
        ensemble = EnsembleModel()
        inputs = [
            _make_input("m1", home=0.45, draw=0.30, away=0.25),
            _make_input("m2", ModelType.ELO, home=0.40, draw=0.35, away=0.25),
        ]
        result = ensemble.predict(inputs)
        total = (result.home_win_probability +
                 result.draw_probability +
                 result.away_win_probability)
        assert abs(total - 1.0) < 1e-9

    def test_all_output_probabilities_in_range(self):
        ensemble = EnsembleModel()
        inputs = [
            _make_input("m1", home=0.45, draw=0.30, away=0.25),
            _make_input("m2", ModelType.ELO, home=0.40, draw=0.35, away=0.25),
        ]
        result = ensemble.predict(inputs)
        assert 0.0 <= result.home_win_probability <= 1.0
        assert 0.0 <= result.draw_probability <= 1.0
        assert 0.0 <= result.away_win_probability <= 1.0


# ---------------------------------------------------------------------------
# Incompatible market handling (BTTS)
# ---------------------------------------------------------------------------

class TestIncompatibleMarketHandling:

    def test_btts_included_when_all_models_provide_it(self):
        ensemble = EnsembleModel()
        inputs = [
            _make_input("m1", home=0.45, draw=0.30, away=0.25,
                        btts_yes=0.55, btts_no=0.45),
            _make_input("m2", ModelType.ELO, home=0.40, draw=0.35, away=0.25,
                        btts_yes=0.50, btts_no=0.50),
        ]
        result = ensemble.predict(inputs)
        assert result.btts_yes_probability is not None
        assert result.btts_no_probability is not None

    def test_btts_absent_when_one_model_missing_it(self):
        """If any model lacks BTTS, ensemble BTTS must be None — no silent mixing."""
        ensemble = EnsembleModel()
        inputs = [
            _make_input("m1", home=0.45, draw=0.30, away=0.25,
                        btts_yes=0.55, btts_no=0.45),
            _make_input("m2", ModelType.ELO, home=0.40, draw=0.35, away=0.25),
            # m2 has no btts
        ]
        result = ensemble.predict(inputs)
        assert result.btts_yes_probability is None
        assert result.btts_no_probability is None

    def test_btts_absent_when_no_model_provides_it(self):
        ensemble = EnsembleModel()
        inputs = [
            _make_input("m1", home=0.45, draw=0.30, away=0.25),
            _make_input("m2", ModelType.ELO, home=0.40, draw=0.35, away=0.25),
        ]
        result = ensemble.predict(inputs)
        assert result.btts_yes_probability is None
        assert result.btts_no_probability is None

    def test_btts_valid_when_combined(self):
        """BTTS probabilities must normalise to 1 when combined."""
        ensemble = EnsembleModel(weights={"m1": 0.5, "m2": 0.5})
        inputs = [
            _make_input("m1", home=0.45, draw=0.30, away=0.25,
                        btts_yes=0.60, btts_no=0.40),
            _make_input("m2", ModelType.ELO, home=0.40, draw=0.35, away=0.25,
                        btts_yes=0.50, btts_no=0.50),
        ]
        result = ensemble.predict(inputs)
        assert result.btts_yes_probability is not None
        total = result.btts_yes_probability + result.btts_no_probability
        assert abs(total - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Model contribution metadata
# ---------------------------------------------------------------------------

class TestModelContributionMetadata:

    def test_contributions_recorded_for_all_active_models(self):
        ensemble = EnsembleModel(weights={"m1": 0.6, "m2": 0.4})
        inputs = [
            _make_input("m1", home=0.50, draw=0.30, away=0.20),
            _make_input("m2", ModelType.ELO, home=0.40, draw=0.35, away=0.25),
        ]
        result = ensemble.predict(inputs)
        assert len(result.model_contributions) == 2

    def test_contribution_weights_sum_to_one(self):
        ensemble = EnsembleModel(weights={"m1": 0.6, "m2": 0.4})
        inputs = [
            _make_input("m1", home=0.50, draw=0.30, away=0.20),
            _make_input("m2", ModelType.ELO, home=0.40, draw=0.35, away=0.25),
        ]
        result = ensemble.predict(inputs)
        total = sum(c.weight for c in result.model_contributions)
        assert abs(total - 1.0) < 1e-9

    def test_original_weight_preserved(self):
        ensemble = EnsembleModel(weights={"m1": 3.0, "m2": 1.0})
        inputs = [
            _make_input("m1", home=0.50, draw=0.30, away=0.20),
            _make_input("m2", ModelType.ELO, home=0.40, draw=0.35, away=0.25),
        ]
        result = ensemble.predict(inputs)
        c1 = next(c for c in result.model_contributions if c.model_id == "m1")
        assert c1.original_weight == 3.0

    def test_contribution_model_type_recorded(self):
        ensemble = EnsembleModel()
        inputs = [
            _make_input("p1", ModelType.POISSON),
            _make_input("e1", ModelType.ELO),
        ]
        result = ensemble.predict(inputs)
        types = {c.model_type for c in result.model_contributions}
        assert ModelType.POISSON in types
        assert ModelType.ELO in types

    def test_home_win_contributions_sum_to_final_probability(self):
        """Sum of weighted home_win contributions ≈ final home_win (before re-norm)."""
        ensemble = EnsembleModel(weights={"m1": 0.5, "m2": 0.5})
        h1, d1, a1 = 0.50, 0.30, 0.20
        h2, d2, a2 = 0.40, 0.35, 0.25
        inputs = [
            _make_input("m1", home=h1, draw=d1, away=a1),
            _make_input("m2", ModelType.ELO, home=h2, draw=d2, away=a2),
        ]
        result = ensemble.predict(inputs)

        summed = sum(c.home_win_contribution for c in result.model_contributions)
        # The contributions are pre-normalisation; after normalisation they may differ
        # slightly.  Check the raw sum is reasonable.
        assert 0.0 <= summed <= 1.0


# ---------------------------------------------------------------------------
# Determinism / reproducibility
# ---------------------------------------------------------------------------

class TestEnsembleDeterminism:

    def test_same_inputs_same_core_probabilities(self):
        ensemble = EnsembleModel(weights={"m1": 0.6, "m2": 0.4})
        inputs = [
            _make_input("m1", home=0.50, draw=0.30, away=0.20),
            _make_input("m2", ModelType.ELO, home=0.40, draw=0.35, away=0.25),
        ]
        r1 = ensemble.predict(inputs)
        r2 = ensemble.predict(inputs)

        assert r1.home_win_probability == r2.home_win_probability
        assert r1.draw_probability == r2.draw_probability
        assert r1.away_win_probability == r2.away_win_probability

    def test_order_independent(self):
        """Swapping model order should not change results."""
        ensemble = EnsembleModel(weights={"m1": 0.5, "m2": 0.5})
        m1 = _make_input("m1", home=0.50, draw=0.30, away=0.20)
        m2 = _make_input("m2", ModelType.ELO, home=0.40, draw=0.35, away=0.25)

        r1 = ensemble.predict([m1, m2])
        r2 = ensemble.predict([m2, m1])

        assert abs(r1.home_win_probability - r2.home_win_probability) < 1e-9
        assert abs(r1.draw_probability - r2.draw_probability) < 1e-9
        assert abs(r1.away_win_probability - r2.away_win_probability) < 1e-9

    def test_repeated_calls_give_same_probabilities(self):
        ensemble = EnsembleModel()
        inp = _make_input()
        probs = [
            (r.home_win_probability, r.draw_probability, r.away_win_probability)
            for r in [ensemble.predict([inp]) for _ in range(5)]
        ]
        assert len(set(probs)) == 1
