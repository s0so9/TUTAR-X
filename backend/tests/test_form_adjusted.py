"""Tests for Form-Adjusted prediction model."""

import pytest
from app.prediction.form_adjusted import FormAdjustedModel
from app.prediction.poisson import PoissonModel
from app.prediction.interfaces import ModelPrediction, ModelAvailability
from app.domain.enums import ModelType


class TestFormAdjustedModel:
    """Test Form-Adjusted model wrapper."""

    def test_model_unavailable_when_base_unavailable(self):
        """Test that unavailability propagates from base model."""
        base_model = PoissonModel()
        form_model = FormAdjustedModel(base_model)

        # Insufficient features for Poisson
        features = {
            "home_form_score": 0.5,
            "away_form_score": -0.3,
        }

        result = form_model.predict(features)

        assert isinstance(result, ModelAvailability)
        assert not result.available
        assert "base_model_unavailable" in result.reason

    def test_model_unavailable_when_form_scores_missing(self):
        """Test that model returns unavailable when form scores missing."""
        base_model = PoissonModel()
        form_model = FormAdjustedModel(base_model, min_matches_for_form=5)

        # Base features present but no form scores
        features = {
            "home_goals_scored_avg": 1.5,
            "home_goals_conceded_avg": 1.0,
            "away_goals_scored_avg": 1.2,
            "away_goals_conceded_avg": 1.3,
            "home_form_matches_used": 3,  # Below minimum
            "away_form_matches_used": 4,  # Below minimum
        }

        result = form_model.predict(features)

        assert isinstance(result, ModelAvailability)
        assert not result.available

    def test_positive_form_increases_lambda(self):
        """Test that positive form score increases expected goals."""
        base_model = PoissonModel()
        form_model = FormAdjustedModel(base_model, form_weight=0.15)

        features = {
            "home_goals_scored_avg": 1.5,
            "home_goals_conceded_avg": 1.0,
            "away_goals_scored_avg": 1.2,
            "away_goals_conceded_avg": 1.3,
            "home_form_score": 0.8,  # Strong positive form
            "away_form_score": 0.0,  # Neutral form
            "home_form_matches_used": 5,
            "away_form_matches_used": 5,
        }

        # Get base prediction
        base_pred = base_model.predict(features)
        base_home_lambda = base_pred.home_score_mean

        # Get form-adjusted prediction
        form_pred = form_model.predict(features)

        assert isinstance(form_pred, ModelPrediction)
        # Positive form should increase home lambda
        assert form_pred.home_score_mean > base_home_lambda
        # Away form is neutral, so should be close to base
        assert abs(form_pred.away_score_mean - base_pred.away_score_mean) < 0.3

    def test_negative_form_decreases_lambda(self):
        """Test that negative form score decreases expected goals."""
        base_model = PoissonModel()
        form_model = FormAdjustedModel(base_model, form_weight=0.15)

        features = {
            "home_goals_scored_avg": 1.5,
            "home_goals_conceded_avg": 1.0,
            "away_goals_scored_avg": 1.2,
            "away_goals_conceded_avg": 1.3,
            "home_form_score": -0.7,  # Strong negative form
            "away_form_score": 0.0,
            "home_form_matches_used": 5,
            "away_form_matches_used": 5,
        }

        # Get base prediction
        base_pred = base_model.predict(features)
        base_home_lambda = base_pred.home_score_mean

        # Get form-adjusted prediction
        form_pred = form_model.predict(features)

        assert isinstance(form_pred, ModelPrediction)
        # Negative form should decrease home lambda
        assert form_pred.home_score_mean < base_home_lambda

    def test_form_weight_controls_adjustment_magnitude(self):
        """Test that form_weight parameter controls adjustment strength."""
        base_model = PoissonModel()

        features = {
            "home_goals_scored_avg": 1.5,
            "home_goals_conceded_avg": 1.0,
            "away_goals_scored_avg": 1.2,
            "away_goals_conceded_avg": 1.3,
            "home_form_score": 0.5,
            "away_form_score": 0.0,
            "home_form_matches_used": 5,
            "away_form_matches_used": 5,
        }

        # Low weight
        form_model_low = FormAdjustedModel(base_model, form_weight=0.05)
        pred_low = form_model_low.predict(features)

        # High weight
        form_model_high = FormAdjustedModel(base_model, form_weight=0.30)
        pred_high = form_model_high.predict(features)

        base_pred = base_model.predict(features)

        # Higher weight should give larger adjustment
        adjustment_low = abs(pred_low.home_score_mean - base_pred.home_score_mean)
        adjustment_high = abs(pred_high.home_score_mean - base_pred.home_score_mean)

        assert adjustment_high > adjustment_low

    def test_lambda_adjustment_formula(self):
        """Test the lambda adjustment formula."""
        base_model = PoissonModel()
        form_weight = 0.20
        form_model = FormAdjustedModel(base_model, form_weight=form_weight)

        features = {
            "home_goals_scored_avg": 2.0,
            "home_goals_conceded_avg": 1.0,
            "away_goals_scored_avg": 1.0,
            "away_goals_conceded_avg": 2.0,
            "home_form_score": 0.5,  # form_score
            "away_form_score": -0.5,
            "home_form_matches_used": 5,
            "away_form_matches_used": 5,
        }

        base_pred = base_model.predict(features)
        form_pred = form_model.predict(features)

        # Expected formula: lambda_adjusted = lambda_base * (1 + form_weight * form_score)
        expected_home = base_pred.home_score_mean * (1 + form_weight * 0.5)
        expected_away = base_pred.away_score_mean * (1 + form_weight * (-0.5))

        # Allow small tolerance for floating point and distribution recalculation
        assert abs(form_pred.home_score_mean - expected_home) < 0.1
        assert abs(form_pred.away_score_mean - expected_away) < 0.1

    def test_form_score_range_enforcement(self):
        """Test that form scores outside [-1, 1] are handled."""
        base_model = PoissonModel()
        form_model = FormAdjustedModel(base_model, form_weight=0.15)

        # Extreme form scores
        features = {
            "home_goals_scored_avg": 1.5,
            "home_goals_conceded_avg": 1.0,
            "away_goals_scored_avg": 1.2,
            "away_goals_conceded_avg": 1.3,
            "home_form_score": 1.0,  # Maximum
            "away_form_score": -1.0,  # Minimum
            "home_form_matches_used": 5,
            "away_form_matches_used": 5,
        }

        result = form_model.predict(features)

        assert isinstance(result, ModelPrediction)
        # Should produce valid prediction with extreme form
        assert result.home_score_mean > 0
        assert result.away_score_mean > 0
        assert 0 <= result.home_win_prob <= 1
        assert 0 <= result.draw_prob <= 1
        assert 0 <= result.away_win_prob <= 1

    def test_probabilities_sum_to_one(self):
        """Test that adjusted probabilities sum to 1.0."""
        base_model = PoissonModel()
        form_model = FormAdjustedModel(base_model)

        features = {
            "home_goals_scored_avg": 1.5,
            "home_goals_conceded_avg": 1.0,
            "away_goals_scored_avg": 1.2,
            "away_goals_conceded_avg": 1.3,
            "home_form_score": 0.3,
            "away_form_score": -0.2,
            "home_form_matches_used": 5,
            "away_form_matches_used": 5,
        }

        result = form_model.predict(features)

        assert isinstance(result, ModelPrediction)
        total_prob = result.home_win_prob + result.draw_prob + result.away_win_prob
        assert abs(total_prob - 1.0) < 0.001

    def test_metadata_includes_base_model_requirements(self):
        """Test that metadata includes base model requirements."""
        base_model = PoissonModel()
        form_model = FormAdjustedModel(base_model)

        metadata = form_model.get_metadata()

        assert metadata.model_id == "form_adjusted_v1"
        assert metadata.model_type == ModelType.FORM_ADJUSTED
        # Should include base model requirements plus form scores
        assert "home_form_score" in metadata.required_features
        assert "away_form_score" in metadata.required_features
        assert "home_goals_scored_avg" in metadata.required_features

    def test_check_requirements_validates_base_and_form(self):
        """Test that check_requirements validates both base and form requirements."""
        base_model = PoissonModel()
        form_model = FormAdjustedModel(base_model, min_matches_for_form=5)

        # Missing base features
        features = {
            "home_form_score": 0.5,
            "away_form_score": 0.3,
            "home_form_matches_used": 6,
            "away_form_matches_used": 6,
        }

        met, missing = form_model.check_requirements(features)

        assert not met
        assert len(missing) > 0
        # Should include missing base model features
        assert "home_goals_scored_avg" in missing or any("goals" in m for m in missing)

    def test_metadata_preserved_in_output(self):
        """Test that metadata about adjustment is preserved."""
        base_model = PoissonModel()
        form_model = FormAdjustedModel(base_model, form_weight=0.20)

        features = {
            "home_goals_scored_avg": 1.5,
            "home_goals_conceded_avg": 1.0,
            "away_goals_scored_avg": 1.2,
            "away_goals_conceded_avg": 1.3,
            "home_form_score": 0.4,
            "away_form_score": -0.3,
            "home_form_matches_used": 5,
            "away_form_matches_used": 5,
        }

        result = form_model.predict(features)

        assert isinstance(result, ModelPrediction)
        assert "base_model_id" in result.metadata
        assert "home_form_score" in result.metadata
        assert "away_form_score" in result.metadata
        assert "form_weight" in result.metadata
        assert result.metadata["form_adjustment_applied"] is True

    def test_minimum_lambda_enforced(self):
        """Test that lambdas don't go below minimum threshold."""
        base_model = PoissonModel()
        form_model = FormAdjustedModel(base_model, form_weight=0.50)  # High weight

        features = {
            "home_goals_scored_avg": 0.5,  # Low base
            "home_goals_conceded_avg": 1.0,
            "away_goals_scored_avg": 0.5,  # Low base
            "away_goals_conceded_avg": 1.3,
            "home_form_score": -0.9,  # Very bad form
            "away_form_score": -0.9,  # Very bad form
            "home_form_matches_used": 5,
            "away_form_matches_used": 5,
        }

        result = form_model.predict(features)

        assert isinstance(result, ModelPrediction)
        # Lambdas should be >= 0.1 (minimum threshold)
        assert result.home_score_mean >= 0.1
        assert result.away_score_mean >= 0.1


_BASE_FEATURES = {
    "home_goals_scored_avg": 1.5,
    "home_goals_conceded_avg": 1.0,
    "away_goals_scored_avg": 1.2,
    "away_goals_conceded_avg": 1.3,
    "home_form_matches_used": 5,
    "away_form_matches_used": 5,
}


def test_points_per_match_is_centred_not_used_raw():
    """The pipeline feeds points per match (0-3); 1.5 ppm must mean no adjustment."""
    from app.prediction.form_adjusted import centred_form_score

    assert centred_form_score({"home_form_points_per_match": 1.5, "home_form_score": 1.5}, "home") == 0.0
    assert centred_form_score({"home_form_points_per_match": 3.0, "home_form_score": 3.0}, "home") == 1.0
    assert centred_form_score({"home_form_points_per_match": 0.0, "home_form_score": 0.0}, "home") == -1.0
    assert centred_form_score({"home_form_score": 0.4}, "home") == 0.4
    assert centred_form_score({"home_form_score": 2.5}, "home") == 1.0  # clipped
    assert centred_form_score({}, "home") is None

    base = PoissonModel().predict(dict(_BASE_FEATURES))
    features = dict(_BASE_FEATURES, home_form_score=1.5, away_form_score=1.5,
                    home_form_points_per_match=1.5, away_form_points_per_match=1.5)
    result = FormAdjustedModel(PoissonModel()).predict(features)
    assert isinstance(result, ModelPrediction)
    assert result.home_score_mean == pytest.approx(base.home_score_mean)
    assert result.away_score_mean == pytest.approx(base.away_score_mean)


def test_form_model_stays_out_when_rating_lambdas_present():
    """Rating lambdas already weight recent matches; form would double count."""
    features = dict(_BASE_FEATURES, home_form_score=2.0, away_form_score=2.2,
                    home_form_points_per_match=2.0, away_form_points_per_match=2.2,
                    home_lambda_rating=1.07, away_lambda_rating=2.96)
    result = FormAdjustedModel(PoissonModel()).predict(features)
    assert isinstance(result, ModelAvailability)
    assert result.available is False
    assert result.reason == "recency_already_in_rating_lambdas"
