"""Tests for Negative Binomial goal prediction model.

Covers:
- NB PMF correctness and known values
- Edge cases (mu=0, large k)
- Variance > mean property
- Poisson convergence (high dispersion)
- Model initialization validation
- Predict output structure and market validity
- 1X2 / BTTS / Over-Under normalization
- Determinism
- Compatibility with ensemble ModelPredictionInput interface
"""

import math
import pytest

from app.prediction.negative_binomial import NegativeBinomialModel, NegativeBinomialPrediction
from app.prediction.ensemble import ModelPredictionInput
from app.domain.enums import ModelType


class TestNBPMF:
    """Tests for the NB PMF computation."""

    def test_mu_zero_k_zero(self):
        m = NegativeBinomialModel(dispersion=10.0)
        assert m.nb_pmf(0, 0.0) == 1.0

    def test_mu_zero_k_positive(self):
        m = NegativeBinomialModel(dispersion=10.0)
        assert m.nb_pmf(1, 0.0) == 0.0
        assert m.nb_pmf(5, 0.0) == 0.0

    def test_pmf_non_negative(self):
        m = NegativeBinomialModel(dispersion=10.0)
        for k in range(15):
            assert m.nb_pmf(k, 1.5) >= 0.0

    def test_pmf_sum_near_one(self):
        """PMF over k=0..20 should be close to 1 for typical lambda."""
        m = NegativeBinomialModel(dispersion=10.0)
        total = sum(m.nb_pmf(k, 1.5) for k in range(20))
        assert abs(total - 1.0) < 0.01

    def test_pmf_mode_reasonable(self):
        """Mode should be near floor(mean) for typical params."""
        m = NegativeBinomialModel(dispersion=20.0)
        mu = 2.0
        probs = [m.nb_pmf(k, mu) for k in range(10)]
        mode_k = probs.index(max(probs))
        # Mode should be within 2 of the mean
        assert abs(mode_k - mu) <= 2

    def test_high_dispersion_approaches_poisson(self):
        """With very high dispersion, NB ≈ Poisson."""
        from app.prediction.poisson import PoissonModel
        nb = NegativeBinomialModel(dispersion=1000.0)
        pm = PoissonModel(max_goals=10)
        mu = 1.5

        nb_probs = [nb.nb_pmf(k, mu) for k in range(6)]
        p_pred = pm.predict_from_lambda(mu, 1.0)
        # Compare NB vs Poisson for home goals only
        for k in range(4):
            poisson_p = p_pred.home_goal_probabilities[k]
            assert abs(nb_probs[k] - poisson_p) < 0.01, \
                f"k={k}: NB={nb_probs[k]:.4f}, Poisson={poisson_p:.4f}"


class TestNBVariance:
    """Tests for the overdispersion property."""

    def test_variance_exceeds_mean(self):
        """NB variance must be >= mean for finite dispersion."""
        m = NegativeBinomialModel(dispersion=10.0)
        mu = 2.0
        var = m.variance(mu)
        assert var > mu

    def test_variance_converges_to_mean_at_high_dispersion(self):
        """With large r, variance → mean (Poisson)."""
        m = NegativeBinomialModel(dispersion=10000.0)
        mu = 1.5
        var = m.variance(mu)
        assert abs(var - mu) < 0.01

    def test_variance_formula(self):
        """Var = mu + mu^2/r."""
        m = NegativeBinomialModel(dispersion=5.0)
        mu = 2.0
        expected = mu + mu ** 2 / 5.0
        assert abs(m.variance(mu) - expected) < 1e-9

    def test_zero_mean_zero_variance(self):
        m = NegativeBinomialModel(dispersion=10.0)
        assert m.variance(0.0) == 0.0


class TestNBModelInit:
    """Tests for model initialization."""

    def test_default_init(self):
        m = NegativeBinomialModel()
        assert m.dispersion == NegativeBinomialModel.DEFAULT_DISPERSION
        assert m.max_goals == 10

    def test_custom_init(self):
        m = NegativeBinomialModel(dispersion=5.0, max_goals=8)
        assert m.dispersion == 5.0
        assert m.max_goals == 8

    def test_invalid_dispersion_zero(self):
        with pytest.raises(ValueError, match="dispersion"):
            NegativeBinomialModel(dispersion=0.0)

    def test_invalid_dispersion_negative(self):
        with pytest.raises(ValueError, match="dispersion"):
            NegativeBinomialModel(dispersion=-1.0)

    def test_invalid_max_goals(self):
        with pytest.raises(ValueError, match="max_goals"):
            NegativeBinomialModel(max_goals=0)


class TestNBPredict:
    """Tests for the predict() method output."""

    def setup_method(self):
        self.model = NegativeBinomialModel(dispersion=20.0, max_goals=10)

    def test_returns_prediction_object(self):
        result = self.model.predict_from_lambda(1.5, 1.1)
        assert isinstance(result, NegativeBinomialPrediction)

    def test_lambdas_stored(self):
        result = self.model.predict_from_lambda(1.5, 1.1)
        assert result.home_lambda == 1.5
        assert result.away_lambda == 1.1

    def test_dispersion_stored(self):
        result = self.model.predict_from_lambda(1.5, 1.1)
        assert result.dispersion == 20.0

    def test_negative_lambda_raises(self):
        with pytest.raises(ValueError, match="home_lambda"):
            self.model.predict_from_lambda(-0.1, 1.0)
        with pytest.raises(ValueError, match="away_lambda"):
            self.model.predict_from_lambda(1.0, -0.1)

    def test_zero_lambda_valid(self):
        result = self.model.predict_from_lambda(0.0, 1.5)
        assert result.home_goal_probabilities[0] == 1.0
        assert all(p < 1e-9 for p in result.home_goal_probabilities[1:])

    def test_goal_prob_length(self):
        result = self.model.predict_from_lambda(1.5, 1.1)
        assert len(result.home_goal_probabilities) == 11
        assert len(result.away_goal_probabilities) == 11

    def test_scoreline_matrix_size(self):
        result = self.model.predict_from_lambda(1.5, 1.1)
        assert len(result.scoreline_probabilities) == 121  # 11x11

    def test_scoreline_independence(self):
        """P(h=1, a=2) = P(home=1) * P(away=2)."""
        result = self.model.predict_from_lambda(1.5, 1.1)
        joint = result.scoreline_probabilities[(1, 2)]
        marginal = result.home_goal_probabilities[1] * result.away_goal_probabilities[2]
        assert abs(joint - marginal) < 1e-12


class TestNBMarkets:
    """Tests for market probability outputs."""

    def setup_method(self):
        self.model = NegativeBinomialModel(dispersion=20.0, max_goals=10)
        self.result = self.model.predict_from_lambda(1.5, 1.1)

    def test_1x2_sum_to_one(self):
        """1X2 probabilities must sum to exactly 1.0 after normalization."""
        total = (self.result.home_win_probability +
                 self.result.draw_probability +
                 self.result.away_win_probability)
        # After normalization, sum should be exactly 1.0 within floating-point precision
        assert abs(total - 1.0) < 1e-9, f"1X2 sum = {total:.15f}"

    def test_1x2_all_valid(self):
        assert 0 <= self.result.home_win_probability <= 1
        assert 0 <= self.result.draw_probability <= 1
        assert 0 <= self.result.away_win_probability <= 1

    def test_btts_sums_to_one(self):
        total = self.result.btts_yes_probability + self.result.btts_no_probability
        assert abs(total - 1.0) < 0.01

    def test_over_under_sums_per_line(self):
        for line, (over, under) in self.result.over_under_probabilities.items():
            assert abs(over + under - 1.0) < 0.01, f"Line {line}"

    def test_top_scorelines_sorted(self):
        probs = [p for _, p in self.result.top_scorelines]
        assert probs == sorted(probs, reverse=True)

    def test_probability_mass_near_one(self):
        assert self.result.probability_mass_captured > 0.95

    def test_higher_home_lambda_favors_home(self):
        result = self.model.predict_from_lambda(3.0, 0.5)
        assert result.home_win_probability > result.away_win_probability

    def test_equal_lambda_symmetric(self):
        result = self.model.predict_from_lambda(1.5, 1.5)
        assert abs(result.home_win_probability - result.away_win_probability) < 0.01

    def test_low_lambda_favors_under(self):
        result = self.model.predict_from_lambda(0.5, 0.5)
        over, under = result.over_under_probabilities[2.5]
        assert under > over

    def test_high_lambda_favors_over(self):
        result = self.model.predict_from_lambda(3.0, 3.0)
        over, under = result.over_under_probabilities[2.5]
        assert over > under


class TestNBProbabilityNormalization:
    """Tests for 1X2 probability normalization with truncated distribution.
    
    The NB model uses a finite max_goals, creating a truncated distribution.
    The _calc_1x2 method must normalize probabilities to sum to exactly 1.0.
    """

    def test_normalization_with_small_floating_point_drift(self):
        """Test that normalization handles small floating-point errors."""
        model = NegativeBinomialModel(dispersion=20.0, max_goals=10)
        result = model.predict_from_lambda(1.5, 1.1)
        total = (result.home_win_probability + 
                 result.draw_probability + 
                 result.away_win_probability)
        assert abs(total - 1.0) < 1e-9, f"Sum = {total:.15f}"

    def test_normalization_with_high_expected_goals(self):
        """High expected goals cause more truncation, requiring normalization."""
        model = NegativeBinomialModel(dispersion=20.0, max_goals=10)
        # High lambdas → more probability mass beyond max_goals
        result = model.predict_from_lambda(3.5, 4.0)
        total = (result.home_win_probability + 
                 result.draw_probability + 
                 result.away_win_probability)
        assert abs(total - 1.0) < 1e-9, f"Sum = {total:.15f}"
        
        # All probabilities should still be valid
        assert 0.0 <= result.home_win_probability <= 1.0
        assert 0.0 <= result.draw_probability <= 1.0
        assert 0.0 <= result.away_win_probability <= 1.0

    def test_normalization_preserves_relative_ratios(self):
        """Normalization should preserve P(home) / P(draw) / P(away) ratios."""
        model = NegativeBinomialModel(dispersion=20.0, max_goals=8)
        result = model.predict_from_lambda(2.5, 2.8)
        
        # Calculate raw probabilities without normalization
        home_probs = [model.nb_pmf(k, 2.5) for k in range(9)]
        away_probs = [model.nb_pmf(k, 2.8) for k in range(9)]
        
        raw_home = raw_draw = raw_away = 0.0
        for h in range(9):
            for a in range(9):
                p = home_probs[h] * away_probs[a]
                if h > a:
                    raw_home += p
                elif h == a:
                    raw_draw += p
                else:
                    raw_away += p
        
        # Calculate expected ratios
        raw_total = raw_home + raw_draw + raw_away
        expected_home_ratio = raw_home / raw_total if raw_total > 0 else 0
        expected_draw_ratio = raw_draw / raw_total if raw_total > 0 else 0
        expected_away_ratio = raw_away / raw_total if raw_total > 0 else 0
        
        # Normalized probabilities should match expected ratios
        assert abs(result.home_win_probability - expected_home_ratio) < 1e-9
        assert abs(result.draw_probability - expected_draw_ratio) < 1e-9
        assert abs(result.away_win_probability - expected_away_ratio) < 1e-9

    def test_normalization_with_low_expected_goals(self):
        """Low expected goals should also normalize correctly."""
        model = NegativeBinomialModel(dispersion=20.0, max_goals=10)
        result = model.predict_from_lambda(0.5, 0.3)
        total = (result.home_win_probability + 
                 result.draw_probability + 
                 result.away_win_probability)
        assert abs(total - 1.0) < 1e-9, f"Sum = {total:.15f}"

    def test_normalization_with_extreme_dispersion(self):
        """Test with very low dispersion (high overdispersion)."""
        model = NegativeBinomialModel(dispersion=2.0, max_goals=10)
        result = model.predict_from_lambda(2.0, 2.5)
        total = (result.home_win_probability + 
                 result.draw_probability + 
                 result.away_win_probability)
        assert abs(total - 1.0) < 1e-9, f"Sum = {total:.15f}"

    def test_all_probabilities_finite_and_non_negative(self):
        """All output probabilities must be finite and non-negative."""
        model = NegativeBinomialModel(dispersion=20.0, max_goals=10)
        result = model.predict_from_lambda(2.5, 2.8)
        
        assert math.isfinite(result.home_win_probability)
        assert math.isfinite(result.draw_probability)
        assert math.isfinite(result.away_win_probability)
        
        assert result.home_win_probability >= 0.0
        assert result.draw_probability >= 0.0
        assert result.away_win_probability >= 0.0

    def test_regression_case_0_989078(self):
        """Regression test for the specific failure case that triggered this fix.
        
        Original error:
        home = 0.05030064179755271
        draw = 0.07329433089223003
        away = 0.8654828492854169
        sum = 0.989078
        
        This was caused by truncation without normalization.
        """
        # We don't know the exact lambda values that produced these probabilities,
        # but we can test that ANY lambda values produce properly normalized output
        model = NegativeBinomialModel(dispersion=20.0, max_goals=10)
        
        # Test multiple lambda combinations
        test_cases = [
            (0.5, 3.5),  # Heavily favoring away
            (2.5, 2.8),  # Close expected goals
            (3.0, 3.5),  # Higher expected goals
            (1.0, 5.0),  # Very asymmetric
        ]
        
        for home_lambda, away_lambda in test_cases:
            result = model.predict_from_lambda(home_lambda, away_lambda)
            total = (result.home_win_probability + 
                     result.draw_probability + 
                     result.away_win_probability)
            assert abs(total - 1.0) < 1e-9, \
                f"Lambda ({home_lambda}, {away_lambda}): sum = {total:.15f}"

    def test_model_prediction_interface_validation_passes(self):
        """Test that normalized probabilities pass ModelPrediction validation."""
        from app.prediction.interfaces import ModelPrediction
        
        model = NegativeBinomialModel(dispersion=20.0, max_goals=10)
        result = model.predict_from_lambda(2.5, 2.8)
        
        # This should NOT raise ValidationError
        model_pred = ModelPrediction(
            model_id="negative_binomial_v1",
            home_score_mean=2.5,
            away_score_mean=2.8,
            score_distribution=result.scoreline_probabilities,
            home_win_prob=result.home_win_probability,
            draw_prob=result.draw_probability,
            away_win_prob=result.away_win_probability,
            confidence_score=0.8,
            data_quality_score=0.9,
        )
        
        # Verify it passes validation
        total = (model_pred.home_win_prob + 
                 model_pred.draw_prob + 
                 model_pred.away_win_prob)
        assert abs(total - 1.0) < 0.001  # ModelPrediction tolerance


class TestNBDeterminism:
    """Tests for deterministic output."""

    def test_same_inputs_same_outputs(self):
        m = NegativeBinomialModel(dispersion=15.0, max_goals=10)
        r1 = m.predict_from_lambda(1.5, 1.1)
        r2 = m.predict_from_lambda(1.5, 1.1)
        assert r1.home_win_probability == r2.home_win_probability
        assert r1.draw_probability == r2.draw_probability
        assert r1.away_win_probability == r2.away_win_probability
        assert r1.scoreline_probabilities == r2.scoreline_probabilities

    def test_different_dispersion_different_output(self):
        """Different dispersion must produce different probabilities."""
        m_low = NegativeBinomialModel(dispersion=2.0)
        m_high = NegativeBinomialModel(dispersion=100.0)
        r_low = m_low.predict_from_lambda(1.5, 1.1)
        r_high = m_high.predict_from_lambda(1.5, 1.1)
        # They should differ (overdispersion effect)
        assert r_low.draw_probability != r_high.draw_probability


class TestNBEnsembleCompatibility:
    """Tests for compatibility with the ensemble ModelPredictionInput interface."""

    def test_can_create_model_prediction_input(self):
        m = NegativeBinomialModel()
        result = m.predict_from_lambda(1.5, 1.1)
        inp = ModelPredictionInput(
            model_id="nb_v1",
            model_type=ModelType.NEGATIVE_BINOMIAL,
            home_win_probability=result.home_win_probability,
            draw_probability=result.draw_probability,
            away_win_probability=result.away_win_probability,
            btts_yes_probability=result.btts_yes_probability,
            btts_no_probability=result.btts_no_probability,
        )
        inp.validate()  # Must not raise

    def test_ensemble_with_poisson_and_nb(self):
        """Ensemble combining Poisson and NB must produce valid output."""
        from app.prediction.poisson import PoissonModel
        from app.prediction.ensemble import EnsembleModel

        pm = PoissonModel(max_goals=10)
        nb = NegativeBinomialModel(dispersion=20.0)

        pr = pm.predict_from_lambda(1.5, 1.1)
        nr = nb.predict_from_lambda(1.5, 1.1)

        ensemble = EnsembleModel(weights={"poisson": 0.6, "nb": 0.4})
        result = ensemble.predict([
            ModelPredictionInput(
                model_id="poisson",
                model_type=ModelType.POISSON,
                home_win_probability=pr.home_win_probability,
                draw_probability=pr.draw_probability,
                away_win_probability=pr.away_win_probability,
            ),
            ModelPredictionInput(
                model_id="nb",
                model_type=ModelType.NEGATIVE_BINOMIAL,
                home_win_probability=nr.home_win_probability,
                draw_probability=nr.draw_probability,
                away_win_probability=nr.away_win_probability,
            ),
        ])
        total = (result.home_win_probability +
                 result.draw_probability +
                 result.away_win_probability)
        assert abs(total - 1.0) < 1e-9
