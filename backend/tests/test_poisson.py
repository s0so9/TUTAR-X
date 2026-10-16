"""Tests for Poisson prediction model.

This test suite verifies:
1. Poisson PMF correctness
2. Lambda edge cases
3. Scoreline matrix calculation
4. Market probability calculations (1X2, BTTS, Over/Under)
5. Truncation handling
6. Missing/invalid data handling
7. Deterministic behavior
"""

import pytest
import math
from app.prediction.poisson import PoissonModel, PoissonPrediction


class TestPoissonPMF:
    """Tests for Poisson probability mass function."""
    
    def test_poisson_pmf_zero_lambda(self):
        """Verify PMF with lambda=0 returns correct probabilities."""
        # When lambda=0, P(0) = 1.0, P(k>0) = 0.0
        assert PoissonModel._poisson_pmf(0, 0.0) == 1.0
        assert PoissonModel._poisson_pmf(1, 0.0) == 0.0
        assert PoissonModel._poisson_pmf(2, 0.0) == 0.0
    
    def test_poisson_pmf_known_values(self):
        """Verify PMF against known Poisson values."""
        # For lambda=1.5, P(k=0) ≈ 0.2231, P(k=1) ≈ 0.3347, P(k=2) ≈ 0.2510
        lambda_ = 1.5
        
        p0 = PoissonModel._poisson_pmf(0, lambda_)
        p1 = PoissonModel._poisson_pmf(1, lambda_)
        p2 = PoissonModel._poisson_pmf(2, lambda_)
        
        assert abs(p0 - 0.2231) < 0.001
        assert abs(p1 - 0.3347) < 0.001
        assert abs(p2 - 0.2510) < 0.001
    
    def test_poisson_pmf_sum_to_one(self):
        """Verify PMF probabilities sum close to 1 for reasonable range."""
        lambda_ = 2.5
        total = sum(PoissonModel._poisson_pmf(k, lambda_) for k in range(20))
        
        # Should be very close to 1.0
        assert abs(total - 1.0) < 0.001
    
    def test_poisson_pmf_high_lambda(self):
        """Verify PMF handles high lambda values."""
        lambda_ = 5.0
        
        # Should not raise error
        p = PoissonModel._poisson_pmf(5, lambda_)
        assert 0.0 <= p <= 1.0
        
        # Peak should be around lambda for high values
        p_at_lambda = PoissonModel._poisson_pmf(5, lambda_)
        p_at_lambda_minus_1 = PoissonModel._poisson_pmf(4, lambda_)
        p_at_lambda_plus_1 = PoissonModel._poisson_pmf(6, lambda_)
        
        # Peak should be at or near lambda
        assert p_at_lambda >= p_at_lambda_minus_1 or p_at_lambda >= p_at_lambda_plus_1


class TestPoissonModel:
    """Tests for PoissonModel class."""
    
    def test_model_initialization(self):
        """Verify model can be initialized."""
        model = PoissonModel(max_goals=10)
        assert model.max_goals == 10
    
    def test_model_invalid_max_goals(self):
        """Verify error raised for invalid max_goals."""
        with pytest.raises(ValueError, match="max_goals must be at least 1"):
            PoissonModel(max_goals=0)
    
    def test_predict_basic(self):
        """Verify basic prediction works."""
        model = PoissonModel(max_goals=5)
        prediction = model.predict_from_lambda(home_lambda=1.5, away_lambda=1.0)
        
        assert isinstance(prediction, PoissonPrediction)
        assert prediction.home_lambda == 1.5
        assert prediction.away_lambda == 1.0
        assert prediction.max_goals == 5
    
    def test_predict_negative_lambda_raises_error(self):
        """Verify negative lambda raises error."""
        model = PoissonModel()
        
        with pytest.raises(ValueError, match="home_lambda must be >= 0"):
            model.predict_from_lambda(home_lambda=-1.0, away_lambda=1.0)
        
        with pytest.raises(ValueError, match="away_lambda must be >= 0"):
            model.predict_from_lambda(home_lambda=1.0, away_lambda=-1.0)
    
    def test_goal_probabilities_length(self):
        """Verify goal probabilities have correct length."""
        model = PoissonModel(max_goals=10)
        prediction = model.predict_from_lambda(home_lambda=1.5, away_lambda=1.0)
        
        # Should have probabilities for 0 to max_goals (inclusive)
        assert len(prediction.home_goal_probabilities) == 11
        assert len(prediction.away_goal_probabilities) == 11
    
    def test_goal_probabilities_sum(self):
        """Verify goal probabilities sum close to 1."""
        model = PoissonModel(max_goals=10)
        prediction = model.predict_from_lambda(home_lambda=1.5, away_lambda=1.0)
        
        home_sum = sum(prediction.home_goal_probabilities)
        away_sum = sum(prediction.away_goal_probabilities)
        
        # Should be close to 1.0 (some mass beyond max_goals is truncated)
        assert home_sum > 0.99
        assert away_sum > 0.99


class TestScorelineMatrix:
    """Tests for scoreline probability matrix."""
    
    def test_scoreline_matrix_size(self):
        """Verify scoreline matrix has correct size."""
        model = PoissonModel(max_goals=5)
        prediction = model.predict_from_lambda(home_lambda=1.5, away_lambda=1.0)
        
        # Should have (max_goals+1) x (max_goals+1) entries
        assert len(prediction.scoreline_probabilities) == 36  # 6 x 6
    
    def test_scoreline_matrix_sum(self):
        """Verify scoreline probabilities sum close to 1."""
        model = PoissonModel(max_goals=10)
        prediction = model.predict_from_lambda(home_lambda=1.5, away_lambda=1.0)
        
        total = sum(prediction.scoreline_probabilities.values())
        
        # Should be close to 1.0
        assert total > 0.99
        assert prediction.probability_mass_captured == total
    
    def test_scoreline_independence(self):
        """Verify scoreline probabilities follow independence assumption."""
        model = PoissonModel(max_goals=10)
        prediction = model.predict_from_lambda(home_lambda=1.5, away_lambda=1.0)
        
        # P(home=1, away=2) should equal P(home=1) * P(away=2)
        joint_prob = prediction.scoreline_probabilities[(1, 2)]
        marginal_home = prediction.home_goal_probabilities[1]
        marginal_away = prediction.away_goal_probabilities[2]
        
        expected = marginal_home * marginal_away
        assert abs(joint_prob - expected) < 1e-10


class Test1X2Probabilities:
    """Tests for 1X2 (match result) probabilities."""
    
    def test_1x2_sum_to_one(self):
        """Verify 1X2 probabilities sum close to 1."""
        model = PoissonModel(max_goals=10)
        prediction = model.predict_from_lambda(home_lambda=2.0, away_lambda=1.0)
        
        total = (prediction.home_win_probability +
                prediction.draw_probability +
                prediction.away_win_probability)
        
        assert abs(total - 1.0) < 0.01
    
    def test_1x2_all_valid_probabilities(self):
        """Verify all 1X2 probabilities are between 0 and 1."""
        model = PoissonModel(max_goals=10)
        prediction = model.predict_from_lambda(home_lambda=1.5, away_lambda=1.5)
        
        assert 0.0 <= prediction.home_win_probability <= 1.0
        assert 0.0 <= prediction.draw_probability <= 1.0
        assert 0.0 <= prediction.away_win_probability <= 1.0
    
    def test_1x2_equal_lambdas_favors_draw(self):
        """Verify equal lambdas result in symmetric probabilities."""
        model = PoissonModel(max_goals=10)
        prediction = model.predict_from_lambda(home_lambda=1.5, away_lambda=1.5)
        
        # Home and away win probabilities should be equal
        assert abs(prediction.home_win_probability - prediction.away_win_probability) < 0.01
    
    def test_1x2_higher_home_lambda_favors_home(self):
        """Verify higher home lambda increases home win probability."""
        model = PoissonModel(max_goals=10)
        prediction = model.predict_from_lambda(home_lambda=2.5, away_lambda=1.0)
        
        # Home win should be more likely than away win
        assert prediction.home_win_probability > prediction.away_win_probability
        assert prediction.home_win_probability > prediction.draw_probability


class TestBTTSProbabilities:
    """Tests for Both Teams To Score probabilities."""
    
    def test_btts_sum_to_one(self):
        """Verify BTTS probabilities sum close to 1."""
        model = PoissonModel(max_goals=10)
        prediction = model.predict_from_lambda(home_lambda=1.5, away_lambda=1.0)
        
        total = prediction.btts_yes_probability + prediction.btts_no_probability
        assert abs(total - 1.0) < 0.01
    
    def test_btts_all_valid_probabilities(self):
        """Verify BTTS probabilities are between 0 and 1."""
        model = PoissonModel(max_goals=10)
        prediction = model.predict_from_lambda(home_lambda=1.5, away_lambda=1.0)
        
        assert 0.0 <= prediction.btts_yes_probability <= 1.0
        assert 0.0 <= prediction.btts_no_probability <= 1.0
    
    def test_btts_low_lambda_favors_no(self):
        """Verify low lambdas increase BTTS No probability."""
        model = PoissonModel(max_goals=10)
        prediction = model.predict_from_lambda(home_lambda=0.5, away_lambda=0.5)
        
        # Low scoring match - less likely both teams score
        assert prediction.btts_no_probability > prediction.btts_yes_probability
    
    def test_btts_high_lambda_favors_yes(self):
        """Verify high lambdas increase BTTS Yes probability."""
        model = PoissonModel(max_goals=10)
        prediction = model.predict_from_lambda(home_lambda=2.5, away_lambda=2.0)
        
        # High scoring match - more likely both teams score
        assert prediction.btts_yes_probability > prediction.btts_no_probability


class TestOverUnderProbabilities:
    """Tests for Over/Under probabilities."""
    
    def test_over_under_common_lines(self):
        """Verify common lines are calculated."""
        model = PoissonModel(max_goals=10)
        prediction = model.predict_from_lambda(home_lambda=1.5, away_lambda=1.0)
        
        # Should have standard lines
        assert 0.5 in prediction.over_under_probabilities
        assert 1.5 in prediction.over_under_probabilities
        assert 2.5 in prediction.over_under_probabilities
        assert 3.5 in prediction.over_under_probabilities
    
    def test_over_under_sum_to_one(self):
        """Verify over and under probabilities sum close to 1."""
        model = PoissonModel(max_goals=10)
        prediction = model.predict_from_lambda(home_lambda=1.5, away_lambda=1.0)
        
        for line, (over_prob, under_prob) in prediction.over_under_probabilities.items():
            total = over_prob + under_prob
            assert abs(total - 1.0) < 0.01, f"Line {line}: {total}"
    
    def test_over_under_all_valid_probabilities(self):
        """Verify all over/under probabilities are between 0 and 1."""
        model = PoissonModel(max_goals=10)
        prediction = model.predict_from_lambda(home_lambda=1.5, away_lambda=1.0)
        
        for line, (over_prob, under_prob) in prediction.over_under_probabilities.items():
            assert 0.0 <= over_prob <= 1.0
            assert 0.0 <= under_prob <= 1.0
    
    def test_over_under_low_lambda_favors_under(self):
        """Verify low total lambda favors under."""
        model = PoissonModel(max_goals=10)
        prediction = model.predict_from_lambda(home_lambda=0.8, away_lambda=0.7)
        
        # Total expected goals = 1.5, should favor under 2.5
        over, under = prediction.over_under_probabilities[2.5]
        assert under > over
    
    def test_over_under_high_lambda_favors_over(self):
        """Verify high total lambda favors over."""
        model = PoissonModel(max_goals=10)
        prediction = model.predict_from_lambda(home_lambda=2.0, away_lambda=2.0)
        
        # Total expected goals = 4.0, should favor over 2.5
        over, under = prediction.over_under_probabilities[2.5]
        assert over > under


class TestCorrectScoreProbabilities:
    """Tests for correct score probabilities."""
    
    def test_top_scorelines_returned(self):
        """Verify top scorelines are returned."""
        model = PoissonModel(max_goals=10)
        prediction = model.predict_from_lambda(home_lambda=1.5, away_lambda=1.0)
        
        # Should return top scorelines
        assert len(prediction.top_scorelines) > 0
        assert len(prediction.top_scorelines) <= 10
    
    def test_top_scorelines_sorted(self):
        """Verify top scorelines are sorted by probability."""
        model = PoissonModel(max_goals=10)
        prediction = model.predict_from_lambda(home_lambda=1.5, away_lambda=1.0)
        
        # Should be sorted descending
        for i in range(len(prediction.top_scorelines) - 1):
            prob_i = prediction.top_scorelines[i][1]
            prob_i_plus_1 = prediction.top_scorelines[i + 1][1]
            assert prob_i >= prob_i_plus_1
    
    def test_top_scoreline_probabilities_valid(self):
        """Verify top scoreline probabilities are between 0 and 1."""
        model = PoissonModel(max_goals=10)
        prediction = model.predict_from_lambda(home_lambda=1.5, away_lambda=1.0)
        
        for scoreline, prob in prediction.top_scorelines:
            assert 0.0 <= prob <= 1.0
            assert isinstance(scoreline, tuple)
            assert len(scoreline) == 2


class TestTruncation:
    """Tests for handling finite max_goals truncation."""
    
    def test_probability_mass_captured_reported(self):
        """Verify probability mass captured is reported."""
        model = PoissonModel(max_goals=5)
        prediction = model.predict_from_lambda(home_lambda=1.5, away_lambda=1.0)
        
        # Should be less than 1.0 due to truncation
        assert 0.0 < prediction.probability_mass_captured <= 1.0
    
    def test_low_max_goals_captures_less_mass(self):
        """Verify lower max_goals captures less probability mass."""
        model_low = PoissonModel(max_goals=3)
        model_high = PoissonModel(max_goals=10)
        
        pred_low = model_low.predict_from_lambda(home_lambda=3.0, away_lambda=3.0)
        pred_high = model_high.predict_from_lambda(home_lambda=3.0, away_lambda=3.0)
        
        # Higher max_goals should capture more mass
        assert pred_high.probability_mass_captured > pred_low.probability_mass_captured
    
    def test_high_max_goals_near_complete_mass(self):
        """Verify high max_goals captures nearly all probability mass."""
        model = PoissonModel(max_goals=15)
        prediction = model.predict_from_lambda(home_lambda=1.5, away_lambda=1.0)
        
        # Should capture >99.9% of mass
        assert prediction.probability_mass_captured > 0.999


class TestMissingAndInvalidData:
    """Tests for handling missing and invalid data."""
    
    def test_zero_lambda_valid(self):
        """Verify lambda=0 is handled correctly."""
        model = PoissonModel(max_goals=5)
        prediction = model.predict_from_lambda(home_lambda=0.0, away_lambda=1.0)
        
        # Home should have P(0 goals) = 1.0
        assert prediction.home_goal_probabilities[0] == 1.0
        
        # All scorelines should have home=0
        for (h, a), prob in prediction.scoreline_probabilities.items():
            if h > 0:
                assert prob < 1e-10  # Essentially zero
    
    def test_feature_estimation_negative_raises_error(self):
        """Verify negative strength values raise error."""
        model = PoissonModel()
        
        with pytest.raises(ValueError, match="Strength values must be non-negative"):
            model.estimate_lambda_from_features(
                team_attack_strength=-1.0,
                opponent_defense_strength=1.0
            )


class TestDeterminism:
    """Tests for deterministic behavior."""
    
    def test_same_inputs_same_outputs(self):
        """Verify same inputs produce identical outputs."""
        model = PoissonModel(max_goals=10)
        
        pred1 = model.predict_from_lambda(home_lambda=1.5, away_lambda=1.0)
        pred2 = model.predict_from_lambda(home_lambda=1.5, away_lambda=1.0)
        
        # All probabilities should be identical
        assert pred1.home_win_probability == pred2.home_win_probability
        assert pred1.draw_probability == pred2.draw_probability
        assert pred1.away_win_probability == pred2.away_win_probability
        assert pred1.btts_yes_probability == pred2.btts_yes_probability
        
        # Scoreline probabilities should be identical
        assert pred1.scoreline_probabilities == pred2.scoreline_probabilities
    
    def test_no_randomness(self):
        """Verify model contains no random elements."""
        model = PoissonModel(max_goals=10)
        
        # Run same prediction 10 times
        predictions = [
            model.predict_from_lambda(home_lambda=1.8, away_lambda=1.2)
            for _ in range(10)
        ]
        
        # All should be identical
        for pred in predictions[1:]:
            assert pred.home_win_probability == predictions[0].home_win_probability
            assert pred.draw_probability == predictions[0].draw_probability


class TestLambdaEstimation:
    """Tests for lambda estimation from features."""
    
    def test_lambda_estimation_basic(self):
        """Verify basic lambda estimation works."""
        model = PoissonModel()
        
        lambda_ = model.estimate_lambda_from_features(
            team_attack_strength=1.5,
            opponent_defense_strength=1.2,
            venue_adjustment=1.1
        )
        
        assert lambda_ >= 0.0
    
    def test_lambda_estimation_non_negative(self):
        """Verify lambda estimation always returns non-negative."""
        model = PoissonModel()
        
        lambda_ = model.estimate_lambda_from_features(
            team_attack_strength=0.0,
            opponent_defense_strength=0.0
        )
        
        assert lambda_ >= 0.0
