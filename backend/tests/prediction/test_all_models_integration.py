"""Integration tests for all 7 prediction models.

Tests feature requirements, predictions, and ensemble integration.
"""

import pytest
from app.prediction.model_orchestrator import ModelOrchestrator
from app.prediction.feature_snapshot import MatchFeatureSnapshot, TeamStrengthMetrics, FormMetrics
from datetime import datetime


@pytest.fixture
def minimal_snapshot():
    """Create minimal snapshot with basic features."""
    return MatchFeatureSnapshot(
        match_id="test_match_001",
        home_team_id="team_home",
        away_team_id="team_away",
        home_team_name="Home Team",
        away_team_name="Away Team",
        scheduled_at=datetime(2026, 10, 10, 15, 0, 0),
        home_strength=TeamStrengthMetrics(
            goals_scored_per_match=1.5,
            goals_conceded_per_match=1.0,
            attack_strength=1.2,
            defense_strength=0.9,
            elo_rating=1600.0,
            xg_per_match=1.6,
        ),
        away_strength=TeamStrengthMetrics(
            goals_scored_per_match=1.2,
            goals_conceded_per_match=1.3,
            attack_strength=1.0,
            defense_strength=1.1,
            elo_rating=1550.0,
            xg_per_match=1.3,
        ),
        home_form=FormMetrics(
            wins=3,
            draws=1,
            losses=1,
            points=10,
            goals_for=7,
            goals_against=5,
            points_per_match=2.0,
            win_rate=0.6,
            matches_analyzed=5,
        ),
        away_form=FormMetrics(
            wins=2,
            draws=2,
            losses=1,
            points=8,
            goals_for=6,
            goals_against=5,
            points_per_match=1.6,
            win_rate=0.4,
            matches_analyzed=5,
        ),
    )


@pytest.fixture
def insufficient_data_snapshot():
    """Create snapshot with missing critical features."""
    return MatchFeatureSnapshot(
        match_id="test_match_002",
        home_team_id="team_home",
        away_team_id="team_away",
        home_team_name="Home Team",
        away_team_name="Away Team",
        scheduled_at=datetime(2026, 10, 10, 15, 0, 0),
        # Missing home_strength and away_strength
        home_strength=None,
        away_strength=None,
    )


class TestPoissonModel:
    """Test Poisson model."""
    
    def test_poisson_with_valid_features(self, minimal_snapshot):
        """Test Poisson model with valid features."""
        orchestrator = ModelOrchestrator()
        from app.prediction.poisson import PoissonModel
        poisson = PoissonModel()
        orchestrator.register_model(poisson)
        
        result = orchestrator.run_all(minimal_snapshot)
        
        assert result.total_models == 1
        assert len(result.successful_predictions) == 1
        assert len(result.unavailable_models) == 0
        assert len(result.failed_models) == 0
        
        pred = result.successful_predictions[0]
        assert pred.model_id == "poisson_v1"
        assert pred.prediction is not None
        assert 0 <= pred.prediction.home_win_prob <= 1
        assert 0 <= pred.prediction.draw_prob <= 1
        assert 0 <= pred.prediction.away_win_prob <= 1
        assert abs(sum([pred.prediction.home_win_prob, 
                       pred.prediction.draw_prob, 
                       pred.prediction.away_win_prob]) - 1.0) < 0.01
    
    def test_poisson_with_missing_features(self, insufficient_data_snapshot):
        """Test Poisson model returns unavailable with missing features."""
        orchestrator = ModelOrchestrator()
        from app.prediction.poisson import PoissonModel
        poisson = PoissonModel()
        orchestrator.register_model(poisson)
        
        result = orchestrator.run_all(insufficient_data_snapshot)
        
        assert result.total_models == 1
        assert len(result.successful_predictions) == 0
        assert len(result.unavailable_models) == 1
        
        unavail = result.unavailable_models[0]
        assert unavail.model_id == "poisson_v1"
        assert "home_goals_scored_avg" in unavail.availability.missing_features


class TestDixonColesModel:
    """Test Dixon-Coles model."""
    
    def test_dixon_coles_with_valid_features(self, minimal_snapshot):
        """Test Dixon-Coles model with valid features."""
        orchestrator = ModelOrchestrator()
        from app.prediction.dixon_coles import DixonColesModel
        from app.prediction.poisson import PoissonModel
        
        poisson = PoissonModel()
        dixon_coles = DixonColesModel(poisson_model=poisson)
        orchestrator.register_model(dixon_coles)
        
        result = orchestrator.run_all(minimal_snapshot)
        
        assert len(result.successful_predictions) == 1
        pred = result.successful_predictions[0]
        assert pred.model_id == "dixon_coles_v1"


class TestNegativeBinomialModel:
    """Test Negative Binomial model."""
    
    def test_negative_binomial_with_valid_features(self, minimal_snapshot):
        """Test Negative Binomial model with valid features."""
        orchestrator = ModelOrchestrator()
        from app.prediction.negative_binomial import NegativeBinomialModel
        
        nb = NegativeBinomialModel()
        orchestrator.register_model(nb)
        
        result = orchestrator.run_all(minimal_snapshot)
        
        assert len(result.successful_predictions) == 1
        pred = result.successful_predictions[0]
        assert pred.model_id == "negative_binomial_v1"


class TestFormAdjustedModel:
    """Test Form Adjusted model."""
    
    def test_form_adjusted_with_valid_features(self, minimal_snapshot):
        """Test Form Adjusted model with valid features."""
        orchestrator = ModelOrchestrator()
        from app.prediction.form_adjusted import FormAdjustedModel
        from app.prediction.poisson import PoissonModel
        
        poisson = PoissonModel()
        form_adj = FormAdjustedModel(base_model=poisson)
        orchestrator.register_model(form_adj)
        
        result = orchestrator.run_all(minimal_snapshot)
        
        assert len(result.successful_predictions) == 1
        pred = result.successful_predictions[0]
        assert pred.model_id == "form_adjusted_v1"


class TestEloModel:
    """Test Elo model."""
    
    def test_elo_with_valid_ratings(self, minimal_snapshot):
        """Test Elo model with valid ratings."""
        orchestrator = ModelOrchestrator()
        from app.prediction.elo import EloModel
        
        elo = EloModel()
        orchestrator.register_model(elo)
        
        result = orchestrator.run_all(minimal_snapshot)
        
        # Elo should work since we have elo_rating in TeamStrengthMetrics
        assert len(result.successful_predictions) == 1
        pred = result.successful_predictions[0]
        assert pred.model_id == "elo_v1"
    
    def test_elo_without_ratings(self, insufficient_data_snapshot):
        """Test Elo model without ratings returns unavailable."""
        orchestrator = ModelOrchestrator()
        from app.prediction.elo import EloModel
        
        elo = EloModel()
        orchestrator.register_model(elo)
        
        result = orchestrator.run_all(insufficient_data_snapshot)
        
        assert len(result.successful_predictions) == 0
        assert len(result.unavailable_models) == 1


class TestMonteCarloModel:
    """Test Monte Carlo model."""
    
    def test_monte_carlo_with_xg_data(self, minimal_snapshot):
        """Test Monte Carlo with xG data available."""
        orchestrator = ModelOrchestrator()
        from app.prediction.monte_carlo import MonteCarloSimulation
        
        # Monte Carlo should work with xg_per_match in TeamStrengthMetrics
        mc = MonteCarloSimulation(n_simulations=1000)
        orchestrator.register_model(mc)
        
        result = orchestrator.run_all(minimal_snapshot)
        
        # Should succeed since we have xg_per_match which maps to home_expected_goals
        assert len(result.successful_predictions) == 1
        pred = result.successful_predictions[0]
        assert pred.model_id == "monte_carlo_v1"


class TestLogisticRegressionModel:
    """Test Logistic Regression model."""
    
    def test_logistic_regression_not_fitted(self, minimal_snapshot):
        """Test Logistic Regression returns unavailable when not fitted."""
        orchestrator = ModelOrchestrator()
        from app.prediction.logistic_regression import LogisticRegressionModel
        
        lr = LogisticRegressionModel()
        orchestrator.register_model(lr)
        
        result = orchestrator.run_all(minimal_snapshot)
        
        # Should be unavailable since model is not fitted
        assert len(result.successful_predictions) == 0
        assert len(result.unavailable_models) == 1
        
        unavail = result.unavailable_models[0]
        assert unavail.model_id == "logistic_regression_v1"
        assert "model_not_fitted" in str(unavail.availability.reason)


class TestAllModelsIntegration:
    """Test all models together."""
    
    def test_default_orchestrator_with_all_models(self, minimal_snapshot):
        """Test default orchestrator with all 7 models."""
        orchestrator = ModelOrchestrator.create_default_registry()
        
        result = orchestrator.run_all(minimal_snapshot)
        
        # Expect 7 models total
        assert result.total_models == 7
        
        # Check which models succeeded
        successful_ids = [p.model_id for p in result.successful_predictions]
        unavailable_ids = [p.model_id for p in result.unavailable_models]
        
        # Expected to succeed: Poisson, Dixon-Coles, Negative Binomial, Form Adjusted, Elo, Monte Carlo
        # Expected unavailable: Logistic Regression (not fitted)
        
        print(f"\nSuccessful: {successful_ids}")
        print(f"Unavailable: {unavailable_ids}")
        print(f"Failed: {[p.model_id for p in result.failed_models]}")
        
        # At minimum, basic models should work
        assert "poisson_v1" in successful_ids
        assert "dixon_coles_v1" in successful_ids
        assert "negative_binomial_v1" in successful_ids
        assert "form_adjusted_v1" in successful_ids
        
        # Logistic regression should be unavailable (not fitted)
        assert "logistic_regression_v1" in unavailable_ids
        
        # No models should fail with exceptions
        assert len(result.failed_models) == 0
    
    def test_feature_snapshot_provides_correct_aliases(self, minimal_snapshot):
        """Test that feature snapshot provides all required aliases."""
        features = minimal_snapshot.get_feature_dict()
        
        # Check Poisson aliases
        assert "home_goals_scored_avg" in features
        assert "away_goals_scored_avg" in features
        assert features["home_goals_scored_avg"] == 1.5
        assert features["away_goals_scored_avg"] == 1.2
        
        # Check Elo aliases
        assert "elo_home" in features
        assert "elo_away" in features
        assert features["elo_home"] == 1600.0
        assert features["elo_away"] == 1550.0
        
        # Check Monte Carlo aliases
        assert "home_expected_goals" in features
        assert "away_expected_goals" in features
        assert features["home_expected_goals"] == 1.6
        assert features["away_expected_goals"] == 1.3
        
        # Check Form Adjusted aliases
        assert "home_form_score" in features
        assert "away_form_score" in features
        assert features["home_form_score"] == 2.0
        assert features["away_form_score"] == 1.6


class TestEnsembleIntegration:
    """Test ensemble combining multiple models."""
    
    def test_ensemble_combines_successful_models(self, minimal_snapshot):
        """Test ensemble integration combines successful predictions."""
        from app.prediction.model_orchestrator import EnsembleIntegration
        
        orchestrator = ModelOrchestrator.create_default_registry()
        result = orchestrator.run_all(minimal_snapshot)
        
        # Create ensemble integration
        ensemble = EnsembleIntegration.create_default()
        
        # Combine predictions
        combined = ensemble.combine_predictions(result)
        
        # Should produce a valid prediction
        from app.prediction.interfaces import ModelPrediction
        assert isinstance(combined, ModelPrediction)
        assert combined.model_id == "ensemble_v1"
        assert 0 <= combined.home_win_prob <= 1
        assert 0 <= combined.draw_prob <= 1
        assert 0 <= combined.away_win_prob <= 1
        assert abs(sum([combined.home_win_prob, combined.draw_prob, combined.away_win_prob]) - 1.0) < 0.01
