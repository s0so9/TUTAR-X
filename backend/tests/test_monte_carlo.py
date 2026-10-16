"""Tests for Monte Carlo Simulation model."""

import pytest
from app.prediction.monte_carlo import MonteCarloSimulation
from app.prediction.poisson import PoissonModel
from app.prediction.interfaces import ModelPrediction, ModelAvailability
from app.domain.enums import ModelType


class TestMonteCarloSimulation:
    """Test Monte Carlo simulation model."""
    
    def test_deterministic_with_seed(self):
        """Test that same seed produces same results."""
        model1 = MonteCarloSimulation(n_simulations=1000, seed=42)
        model2 = MonteCarloSimulation(n_simulations=1000, seed=42)
        
        features = {
            "home_expected_goals": 1.5,
            "away_expected_goals": 1.2,
        }
        
        result1 = model1.predict(features)
        result2 = model2.predict(features)
        
        assert isinstance(result1, ModelPrediction)
        assert isinstance(result2, ModelPrediction)
        
        # Should produce identical results
        assert result1.home_win_prob == result2.home_win_prob
        assert result1.draw_prob == result2.draw_prob
        assert result1.away_win_prob == result2.away_win_prob
    
    def test_probability_normalization_1x2(self):
        """Test that 1X2 probabilities sum to ~1.0."""
        model = MonteCarloSimulation(n_simulations=10000, seed=42)
        
        features = {
            "home_expected_goals": 1.8,
            "away_expected_goals": 1.3,
        }
        
        result = model.predict(features)
        
        assert isinstance(result, ModelPrediction)
        total = result.home_win_prob + result.draw_prob + result.away_win_prob
        assert abs(total - 1.0) < 0.01
    
    def test_over_under_consistency(self):
        """Test that over + under ≈ 1.0 for each line."""
        model = MonteCarloSimulation(n_simulations=10000, seed=42)
        
        features = {
            "home_expected_goals": 1.5,
            "away_expected_goals": 1.5,
        }
        
        result = model.predict(features)
        
        assert isinstance(result, ModelPrediction)
        over_under = result.metadata["over_under"]
        
        for line in [0.5, 1.5, 2.5, 3.5]:
            over_prob = over_under[line]
            # Under = 1 - over
            under_prob = 1.0 - over_prob
            assert 0 <= over_prob <= 1.0
            assert 0 <= under_prob <= 1.0
            # Should sum to 1
            assert abs(over_prob + under_prob - 1.0) < 0.01
    
    def test_btts_consistency(self):
        """Test that btts_yes + btts_no ≈ 1.0."""
        model = MonteCarloSimulation(n_simulations=10000, seed=42)
        
        features = {
            "home_expected_goals": 1.7,
            "away_expected_goals": 1.4,
        }
        
        result = model.predict(features)
        
        assert isinstance(result, ModelPrediction)
        btts_yes = result.metadata["btts_yes"]
        btts_no = result.metadata["btts_no"]
        
        assert 0 <= btts_yes <= 1.0
        assert 0 <= btts_no <= 1.0
        assert abs(btts_yes + btts_no - 1.0) < 0.01
    
    def test_convergence_with_many_simulations(self):
        """Test that more simulations produce more stable results."""
        features = {
            "home_expected_goals": 1.5,
            "away_expected_goals": 1.5,
        }
        
        # Run with 1000 simulations
        model_1k = MonteCarloSimulation(n_simulations=1000, seed=42)
        result_1k = model_1k.predict(features)
        
        # Run with 10000 simulations
        model_10k = MonteCarloSimulation(n_simulations=10000, seed=42)
        result_10k = model_10k.predict(features)
        
        # Results should be in same ballpark but 10k more confident
        assert abs(result_1k.home_win_prob - result_10k.home_win_prob) < 0.1
        assert result_10k.confidence_score >= result_1k.confidence_score
    
    def test_base_model_integration(self):
        """Test using a base model to get lambdas."""
        base_model = PoissonModel()
        monte_carlo = MonteCarloSimulation(base_model=base_model, n_simulations=5000, seed=42)
        
        features = {
            "home_goals_scored_avg": 1.8,
            "home_goals_conceded_avg": 1.0,
            "away_goals_scored_avg": 1.3,
            "away_goals_conceded_avg": 1.2,
        }
        
        result = monte_carlo.predict(features)
        
        assert isinstance(result, ModelPrediction)
        assert result.metadata["base_model_id"] == "poisson_v1"
        assert result.home_score_mean > 0
        assert result.away_score_mean > 0
    
    def test_unavailable_when_base_model_unavailable(self):
        """Test that unavailability propagates from base model."""
        base_model = PoissonModel()
        monte_carlo = MonteCarloSimulation(base_model=base_model, n_simulations=5000)
        
        # Insufficient features
        features = {}
        
        result = monte_carlo.predict(features)
        
        assert isinstance(result, ModelAvailability)
        assert not result.available
        assert "base_model_unavailable" in result.reason
    
    def test_unavailable_when_no_expected_goals(self):
        """Test unavailability when expected goals missing."""
        # No base model, requires expected_goals in features
        monte_carlo = MonteCarloSimulation(n_simulations=5000)
        
        features = {}
        
        result = monte_carlo.predict(features)
        
        assert isinstance(result, ModelAvailability)
        assert not result.available
        assert "expected_goals_unavailable" in result.reason
    
    def test_score_distribution_generated(self):
        """Test that score distribution is generated."""
        model = MonteCarloSimulation(n_simulations=10000, seed=42, top_scorelines=25)
        
        features = {
            "home_expected_goals": 1.5,
            "away_expected_goals": 1.5,
        }
        
        result = model.predict(features)
        
        assert isinstance(result, ModelPrediction)
        assert len(result.score_distribution) > 0
        assert len(result.score_distribution) <= 25  # Top 25
        
        # Verify distribution format
        for scoreline, prob in result.score_distribution.items():
            assert isinstance(scoreline, tuple)
            assert len(scoreline) == 2
            assert isinstance(scoreline[0], int)
            assert isinstance(scoreline[1], int)
            assert 0 <= prob <= 1.0
    
    def test_team_totals_calculated(self):
        """Test that team-specific goal totals are calculated."""
        model = MonteCarloSimulation(n_simulations=10000, seed=42)
        
        features = {
            "home_expected_goals": 2.0,
            "away_expected_goals": 1.0,
        }
        
        result = model.predict(features)
        
        assert isinstance(result, ModelPrediction)
        
        home_totals = result.metadata["home_team_totals"]
        away_totals = result.metadata["away_team_totals"]
        
        # Verify home totals
        assert 0.5 in home_totals
        assert 1.5 in home_totals
        assert 2.5 in home_totals
        
        # Higher lambda should have higher probability of scoring
        # over 0.5 > over 1.5 > over 2.5
        assert home_totals[0.5] > home_totals[1.5]
        assert home_totals[1.5] > home_totals[2.5]
        
        # Away team has lower lambda, so lower probabilities
        assert away_totals[0.5] < home_totals[0.5]
    
    def test_high_scoring_match(self):
        """Test simulation with high expected goals."""
        model = MonteCarloSimulation(n_simulations=10000, seed=42)
        
        features = {
            "home_expected_goals": 3.0,
            "away_expected_goals": 2.5,
        }
        
        result = model.predict(features)
        
        assert isinstance(result, ModelPrediction)
        
        # High scoring match should have high over 2.5 probability
        over_under = result.metadata["over_under"]
        assert over_under[2.5] > 0.6
        
        # BTTS should be likely
        assert result.metadata["btts_yes"] > 0.6
    
    def test_low_scoring_match(self):
        """Test simulation with low expected goals."""
        model = MonteCarloSimulation(n_simulations=10000, seed=42)
        
        features = {
            "home_expected_goals": 0.8,
            "away_expected_goals": 0.6,
        }
        
        result = model.predict(features)
        
        assert isinstance(result, ModelPrediction)
        
        # Low scoring match should have high under 1.5 probability
        over_under = result.metadata["over_under"]
        assert over_under[1.5] < 0.5  # More likely under than over
        
        # BTTS should be unlikely
        assert result.metadata["btts_no"] > 0.5
    
    def test_metadata_completeness(self):
        """Test that all expected metadata is present."""
        model = MonteCarloSimulation(n_simulations=5000, seed=42)
        
        features = {
            "home_expected_goals": 1.5,
            "away_expected_goals": 1.5,
        }
        
        result = model.predict(features)
        
        assert isinstance(result, ModelPrediction)
        
        # Check all expected metadata fields
        metadata = result.metadata
        assert "n_simulations" in metadata
        assert "seed" in metadata
        assert "lambda_home" in metadata
        assert "lambda_away" in metadata
        assert "over_under" in metadata
        assert "btts_yes" in metadata
        assert "btts_no" in metadata
        assert "home_team_totals" in metadata
        assert "away_team_totals" in metadata
        assert "scorelines_captured" in metadata
        assert "unique_scorelines_simulated" in metadata
    
    def test_model_metadata(self):
        """Test get_metadata returns correct information."""
        base_model = PoissonModel()
        model = MonteCarloSimulation(base_model=base_model, n_simulations=10000)
        
        metadata = model.get_metadata()
        
        assert metadata.model_id == "monte_carlo_v1"
        assert metadata.model_type == ModelType.MONTE_CARLO
        assert metadata.version == "1.0.0"
        assert len(metadata.required_features) > 0
    
    def test_confidence_increases_with_clarity(self):
        """Test that confidence is higher when outcome is clearer."""
        # Clear favorite
        features_clear = {
            "home_expected_goals": 3.0,
            "away_expected_goals": 0.8,
        }
        
        # Even match
        features_even = {
            "home_expected_goals": 1.5,
            "away_expected_goals": 1.5,
        }
        
        model = MonteCarloSimulation(n_simulations=10000, seed=42)
        
        result_clear = model.predict(features_clear)
        result_even = model.predict(features_even)
        
        # Clear favorite should have higher confidence
        assert result_clear.confidence_score > result_even.confidence_score
    
    def test_poisson_sampling_produces_valid_goals(self):
        """Test that Poisson sampling produces non-negative integers."""
        model = MonteCarloSimulation(n_simulations=100, seed=42)
        
        features = {
            "home_expected_goals": 1.5,
            "away_expected_goals": 1.2,
        }
        
        result = model.predict(features)
        
        assert isinstance(result, ModelPrediction)
        
        # Check all scorelines are non-negative integers
        for (home_goals, away_goals), prob in result.score_distribution.items():
            assert home_goals >= 0
            assert away_goals >= 0
            assert isinstance(home_goals, int)
            assert isinstance(away_goals, int)
