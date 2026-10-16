"""Tests for shot production calculator."""

import pytest
from datetime import datetime
from unittest.mock import Mock
import math

from app.features.shot_production import (
    ShotProduction,
    ShotProductionCalculator,
)


@pytest.fixture
def mock_session():
    """Create mock database session."""
    return Mock()


@pytest.fixture
def calculator(mock_session):
    """Create calculator instance."""
    return ShotProductionCalculator(
        session=mock_session,
        min_matches=5
    )


class TestShotProduction:
    """Test ShotProduction dataclass."""
    
    def test_shot_production_structure(self):
        """Test ShotProduction dataclass structure."""
        prod = ShotProduction(team_id="team_a")
        
        # All probability fields should be None by default
        assert prod.over_10_shots_prob is None
        assert prod.over_12_shots_prob is None
        assert prod.over_15_shots_prob is None
        assert prod.over_3_sot_prob is None
        assert prod.over_4_sot_prob is None


class TestShotProductionCalculator:
    """Test ShotProductionCalculator."""
    
    def test_poisson_selection(self, calculator):
        """Test Poisson selection when variance ≤ mean."""
        # Create equidispersed shot counts (variance ≈ mean)
        # For Poisson with λ=10, variance = mean = 10
        shot_counts = [8.0, 9.0, 10.0, 11.0, 12.0, 10.0]  # mean ≈ 10, variance ≈ 2
        
        production = calculator.calculate(
            team_id="team_a",
            shot_counts=shot_counts
        )
        
        assert production.shots_distribution_model == "poisson"
        assert production.expected_shots_mean is not None
        assert production.poisson_lambda_shots is not None
        assert production.nb_r_shots is None  # NegBin params should be None
        assert production.nb_p_shots is None
    
    def test_negbin_selection(self, calculator):
        """Test Negative Binomial selection when variance > mean."""
        # Create overdispersed shot counts (variance > mean)
        shot_counts = [2.0, 5.0, 8.0, 15.0, 20.0, 25.0]  # mean ≈ 12.5, variance ≈ 75
        
        production = calculator.calculate(
            team_id="team_a",
            shot_counts=shot_counts
        )
        
        assert production.shots_distribution_model == "negative_binomial"
        assert production.expected_shots_mean is not None
        assert production.nb_r_shots is not None
        assert production.nb_p_shots is not None
        assert production.poisson_lambda_shots is None  # Poisson params should be None
    
    def test_negbin_parameters(self, calculator):
        """Test Negative Binomial parameter calculation."""
        # Overdispersed data
        shot_counts = [5.0, 10.0, 15.0, 20.0, 25.0, 30.0]
        
        production = calculator.calculate(
            team_id="team_a",
            shot_counts=shot_counts
        )
        
        if production.shots_distribution_model == "negative_binomial":
            assert production.nb_r_shots > 0
            assert 0 < production.nb_p_shots < 1
            
            # Verify relationship: p = r / (r + μ)
            mu = production.expected_shots_mean
            r = production.nb_r_shots
            p = production.nb_p_shots
            
            expected_p = r / (r + mu)
            assert abs(p - expected_p) < 0.01
    
    def test_over_threshold_probability(self, calculator):
        """Test P(X > T) calculation."""
        # Use consistent shot counts
        shot_counts = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]  # mean ≈ 12.5
        
        production = calculator.calculate(
            team_id="team_a",
            shot_counts=shot_counts
        )
        
        # All threshold probabilities should be valid
        assert production.over_10_shots_prob is not None
        assert 0.0 <= production.over_10_shots_prob <= 1.0
        
        assert production.over_12_shots_prob is not None
        assert 0.0 <= production.over_12_shots_prob <= 1.0
        
        # Higher thresholds should have lower probabilities
        assert production.over_10_shots_prob >= production.over_12_shots_prob
        assert production.over_12_shots_prob >= production.over_15_shots_prob
        assert production.over_15_shots_prob >= production.over_18_shots_prob
    
    def test_insufficient_sample_returns_none(self, calculator):
        """Test that insufficient sample returns None for all probabilities."""
        # Only 3 matches (< MIN_MATCHES_FOR_DISTRIBUTION = 5)
        shot_counts = [10.0, 12.0, 14.0]
        
        production = calculator.calculate(
            team_id="team_a",
            shot_counts=shot_counts
        )
        
        assert production.shots_distribution_model == "none"
        assert production.over_10_shots_prob is None
        assert production.over_12_shots_prob is None
        assert production.over_15_shots_prob is None
    
    def test_total_shots_distribution(self, calculator):
        """Test total shots (home + away) distribution calculation."""
        home_shot_counts = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
        away_shot_counts = [8.0, 9.0, 10.0, 11.0, 12.0, 13.0]
        
        production = calculator.calculate_total(
            home_shot_counts=home_shot_counts,
            away_shot_counts=away_shot_counts
        )
        
        # Total mean should be approximately sum of means
        # home_mean ≈ 12.5, away_mean ≈ 10.5, total ≈ 23
        assert production.expected_total_shots_mean is not None
        assert 22.0 <= production.expected_total_shots_mean <= 24.0
        
        # Total threshold probabilities should be calculated
        assert production.total_over_20_prob is not None
        assert production.total_over_22_prob is not None
        
        # Probabilities should be valid and decreasing
        assert 0.0 <= production.total_over_20_prob <= 1.0
        assert production.total_over_20_prob >= production.total_over_22_prob
        assert production.total_over_22_prob >= production.total_over_25_prob
    
    def test_zero_mean_returns_none(self, calculator):
        """Test that zero or negative mean returns None."""
        # All zeros
        shot_counts = [0.0, 0.0, 0.0, 0.0, 0.0]
        
        production = calculator.calculate(
            team_id="team_a",
            shot_counts=shot_counts
        )
        
        # Should return "none" distribution
        assert production.shots_distribution_model == "none"
    
    def test_sot_distribution_separate(self, calculator):
        """Test that SOT distribution is calculated separately."""
        shot_counts = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
        sot_counts = [3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
        
        production = calculator.calculate(
            team_id="team_a",
            shot_counts=shot_counts,
            sot_counts=sot_counts
        )
        
        # Both shots and SOT distributions should be calculated
        assert production.shots_distribution_model != "none"
        assert production.sot_distribution_model != "none"
        
        # SOT threshold probabilities should be calculated
        assert production.over_3_sot_prob is not None
        assert production.over_4_sot_prob is not None
        assert production.over_5_sot_prob is not None
        
        # SOT probabilities should be decreasing
        assert production.over_3_sot_prob >= production.over_4_sot_prob
        assert production.over_4_sot_prob >= production.over_5_sot_prob
    
    def test_data_quality_score(self, calculator):
        """Test data quality score calculation."""
        # Small sample
        shot_counts_small = [10.0, 11.0, 12.0, 13.0, 14.0]
        production_small = calculator.calculate(
            team_id="team_a",
            shot_counts=shot_counts_small
        )
        
        # Large sample
        shot_counts_large = [10.0 + i for i in range(15)]
        production_large = calculator.calculate(
            team_id="team_a",
            shot_counts=shot_counts_large
        )
        
        # Larger sample should have higher data quality
        assert production_large.data_quality_score > production_small.data_quality_score
        
        # Uncertainty should be inverse of quality
        assert production_large.uncertainty_score < production_small.uncertainty_score
    
    def test_fit_distribution_helper(self, calculator):
        """Test _fit_distribution helper method."""
        # Test Poisson case (variance ≈ mean)
        poisson_values = [8.0, 9.0, 10.0, 11.0, 12.0]
        model, mu, var, r, p = calculator._fit_distribution(poisson_values)
        
        assert model == "poisson"
        assert mu is not None
        assert var is not None
        assert r is None  # NegBin params should be None for Poisson
        assert p is None
        
        # Test NegBin case (variance > mean)
        negbin_values = [2.0, 5.0, 10.0, 20.0, 30.0]
        model, mu, var, r, p = calculator._fit_distribution(negbin_values)
        
        assert model == "negative_binomial"
        assert mu is not None
        assert var is not None
        assert r is not None
        assert p is not None
        assert r > 0
        assert 0 < p < 1
    
    def test_threshold_probability_helper(self, calculator):
        """Test _threshold_probability helper method."""
        # Test Poisson
        prob_poisson = calculator._threshold_probability(
            threshold=10,
            model="poisson",
            mu=12.0
        )
        
        assert prob_poisson is not None
        assert 0.0 <= prob_poisson <= 1.0
        
        # Test NegBin
        prob_negbin = calculator._threshold_probability(
            threshold=10,
            model="negative_binomial",
            mu=12.0,
            nb_r=5.0,
            nb_p=0.294  # p = r/(r+mu) = 5/(5+12) ≈ 0.294
        )
        
        assert prob_negbin is not None
        assert 0.0 <= prob_negbin <= 1.0
    
    def test_invalid_parameters_return_none(self, calculator):
        """Test that invalid parameters return None."""
        # Empty list
        model, mu, var, r, p = calculator._fit_distribution([])
        assert model is None
        
        # Single value
        model, mu, var, r, p = calculator._fit_distribution([10.0])
        assert model is None
        
        # Negative values
        model, mu, var, r, p = calculator._fit_distribution([-1.0, -2.0, -3.0, -4.0, -5.0])
        assert model is None
