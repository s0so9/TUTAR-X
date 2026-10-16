"""Test lambda calculation consistency across all code paths.

This test ensures that the CANONICAL lambda formula is used consistently
and produces the same result regardless of the call path.
"""

import pytest
from app.prediction.poisson import PoissonModel


class TestLambdaConsistency:
    """Test that lambda calculation is consistent across all methods."""
    
    def test_canonical_estimate_lambda_formula(self):
        """Test the canonical estimate_lambda method."""
        model = PoissonModel()
        
        # Test case: team scores 1.5 goals/match, opponent concedes 1.2 goals/match
        lambda_ = model.estimate_lambda(
            team_attack_strength=1.5,
            opponent_defense_strength=1.2,
            venue_adjustment=1.0
        )
        
        # Expected: 1.5 × 1.2 × 1.0 = 1.8
        assert abs(lambda_ - 1.8) < 1e-10, f"Expected 1.8, got {lambda_}"
    
    def test_canonical_with_home_advantage(self):
        """Test canonical formula with home advantage."""
        model = PoissonModel()
        
        lambda_ = model.estimate_lambda(
            team_attack_strength=1.5,
            opponent_defense_strength=1.2,
            venue_adjustment=1.2  # 20% home advantage
        )
        
        # Expected: 1.5 × 1.2 × 1.2 = 2.16
        assert abs(lambda_ - 2.16) < 1e-10, f"Expected 2.16, got {lambda_}"
    
    def test_backward_compatibility_alias(self):
        """Test that estimate_lambda_from_features calls canonical method."""
        model = PoissonModel()
        
        canonical = model.estimate_lambda(
            team_attack_strength=1.5,
            opponent_defense_strength=1.2,
            venue_adjustment=1.0
        )
        
        alias = model.estimate_lambda_from_features(
            team_attack_strength=1.5,
            opponent_defense_strength=1.2,
            venue_adjustment=1.0
        )
        
        assert canonical == alias, "Alias should call canonical method"
    
    def test_predict_uses_canonical_lambda(self):
        """Test that predict() method uses canonical lambda calculation."""
        model = PoissonModel()
        
        features = {
            "home_goals_scored_avg": 1.5,
            "away_goals_scored_avg": 1.3,
            "home_goals_conceded_avg": 1.1,
            "away_goals_conceded_avg": 1.2,
        }
        
        result = model.predict(features)
        
        # Manually calculate expected lambdas using canonical formula
        # Home lambda: home_attack × away_defense × venue
        expected_home_lambda = 1.5 * 1.2 * 1.0  # = 1.8
        # Away lambda: away_attack × home_defense × venue
        expected_away_lambda = 1.3 * 1.1 * 1.0  # = 1.43
        
        assert abs(result.home_score_mean - expected_home_lambda) < 1e-10, \
            f"Home lambda mismatch: expected {expected_home_lambda}, got {result.home_score_mean}"
        assert abs(result.away_score_mean - expected_away_lambda) < 1e-10, \
            f"Away lambda mismatch: expected {expected_away_lambda}, got {result.away_score_mean}"
    
    def test_lambda_consistency_across_multiple_calls(self):
        """Test that multiple calls with same inputs produce identical results."""
        model = PoissonModel()
        
        features = {
            "home_goals_scored_avg": 1.8,
            "away_goals_scored_avg": 1.4,
            "home_goals_conceded_avg": 1.0,
            "away_goals_conceded_avg": 1.3,
        }
        
        # Call predict multiple times
        results = [model.predict(features) for _ in range(5)]
        
        # All home lambdas should be identical
        home_lambdas = [r.home_score_mean for r in results]
        assert len(set(home_lambdas)) == 1, "Home lambda inconsistent across calls"
        
        # All away lambdas should be identical
        away_lambdas = [r.away_score_mean for r in results]
        assert len(set(away_lambdas)) == 1, "Away lambda inconsistent across calls"
    
    def test_edge_case_zero_attack(self):
        """Test lambda calculation with zero attack strength."""
        model = PoissonModel()
        
        lambda_ = model.estimate_lambda(
            team_attack_strength=0.0,
            opponent_defense_strength=1.5,
            venue_adjustment=1.2
        )
        
        # Expected: 0.0 × 1.5 × 1.2 = 0.0
        assert lambda_ == 0.0, f"Expected 0.0 for zero attack, got {lambda_}"
    
    def test_edge_case_zero_defense(self):
        """Test lambda calculation with zero defense strength (perfect defense)."""
        model = PoissonModel()
        
        lambda_ = model.estimate_lambda(
            team_attack_strength=2.0,
            opponent_defense_strength=0.0,  # Perfect defense (never concedes)
            venue_adjustment=1.0
        )
        
        # Expected: 2.0 × 0.0 × 1.0 = 0.0
        assert lambda_ == 0.0, f"Expected 0.0 vs perfect defense, got {lambda_}"
    
    def test_negative_values_raise_error(self):
        """Test that negative values raise ValueError."""
        model = PoissonModel()
        
        with pytest.raises(ValueError, match="team_attack_strength must be >= 0"):
            model.estimate_lambda(
                team_attack_strength=-1.0,
                opponent_defense_strength=1.0,
                venue_adjustment=1.0
            )
        
        with pytest.raises(ValueError, match="opponent_defense_strength must be >= 0"):
            model.estimate_lambda(
                team_attack_strength=1.0,
                opponent_defense_strength=-1.0,
                venue_adjustment=1.0
            )
        
        with pytest.raises(ValueError, match="venue_adjustment must be >= 0"):
            model.estimate_lambda(
                team_attack_strength=1.0,
                opponent_defense_strength=1.0,
                venue_adjustment=-0.5
            )
    
    def test_domain_logic_sanity(self):
        """Test that lambda increases with stronger attack and weaker defense."""
        model = PoissonModel()
        
        base_lambda = model.estimate_lambda(1.0, 1.0, 1.0)
        
        # Stronger attack → higher lambda
        stronger_attack = model.estimate_lambda(2.0, 1.0, 1.0)
        assert stronger_attack > base_lambda, "Stronger attack should increase lambda"
        
        # Weaker defense (higher conceding rate) → higher lambda
        weaker_defense = model.estimate_lambda(1.0, 2.0, 1.0)
        assert weaker_defense > base_lambda, "Weaker defense should increase lambda"
        
        # Home advantage → higher lambda
        home_advantage = model.estimate_lambda(1.0, 1.0, 1.3)
        assert home_advantage > base_lambda, "Home advantage should increase lambda"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
