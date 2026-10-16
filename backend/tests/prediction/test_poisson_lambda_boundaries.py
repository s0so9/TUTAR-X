"""Test Poisson lambda estimation boundary conditions and semantic correctness."""

import pytest
from app.prediction.poisson import PoissonModel


class TestPoissonLambdaBoundaries:
    """Test lambda calculation handles edge cases correctly."""
    
    def test_zero_defense_conceded_means_strong_defense(self):
        """Test that zero goals conceded (strong defense) → low expected goals."""
        model = PoissonModel()
        
        # Attacker scoring 2 goals/match vs defender conceding 0 goals/match (perfect defense)
        lambda_strong_defense = model.estimate_lambda(
            team_attack_strength=2.0,
            opponent_defense_strength=0.0,  # Concedes zero = very strong defense
            venue_adjustment=1.0
        )
        
        # Should produce lambda = 2.0 * 0.0 * 1.0 = 0.0
        assert lambda_strong_defense == 0.0, "Zero goals conceded should give λ=0"
    
    def test_high_defense_conceded_means_weak_defense(self):
        """Test that high goals conceded (weak defense) → high expected goals."""
        model = PoissonModel()
        
        # Attacker scoring 2 goals/match vs defender conceding 2 goals/match (weak defense)
        lambda_weak_defense = model.estimate_lambda(
            team_attack_strength=2.0,
            opponent_defense_strength=2.0,  # Concedes many = weak defense
            venue_adjustment=1.0
        )
        
        # Should produce lambda = 2.0 * 2.0 * 1.0 = 4.0
        assert lambda_weak_defense == 4.0
    
    def test_defense_strength_monotonicity(self):
        """Test that increasing goals conceded monotonically increases λ."""
        model = PoissonModel()
        attack = 1.5
        
        lambda_0 = model.estimate_lambda(attack, 0.0, 1.0)
        lambda_05 = model.estimate_lambda(attack, 0.5, 1.0)
        lambda_1 = model.estimate_lambda(attack, 1.0, 1.0)
        lambda_2 = model.estimate_lambda(attack, 2.0, 1.0)
        
        # More goals conceded → easier to score against → higher λ
        assert lambda_0 < lambda_05 < lambda_1 < lambda_2
    
    def test_zero_attack_regardless_of_defense(self):
        """Test that zero attack strength always gives λ=0."""
        model = PoissonModel()
        
        lambda_vs_weak = model.estimate_lambda(0.0, 2.0, 1.0)
        lambda_vs_strong = model.estimate_lambda(0.0, 0.5, 1.0)
        
        assert lambda_vs_weak == 0.0
        assert lambda_vs_strong == 0.0
    
    def test_venue_adjustment_multiplier(self):
        """Test venue adjustment correctly multiplies λ."""
        model = PoissonModel()
        
        neutral = model.estimate_lambda(1.5, 1.0, 1.0)
        home_advantage = model.estimate_lambda(1.5, 1.0, 1.2)
        
        assert home_advantage == pytest.approx(neutral * 1.2)
    
    def test_negative_values_rejected(self):
        """Test that negative strength values are rejected."""
        model = PoissonModel()
        
        with pytest.raises(ValueError, match="team_attack_strength must be >= 0"):
            model.estimate_lambda(-1.0, 1.0, 1.0)
        
        with pytest.raises(ValueError, match="opponent_defense_strength must be >= 0"):
            model.estimate_lambda(1.0, -1.0, 1.0)
        
        with pytest.raises(ValueError, match="venue_adjustment must be >= 0"):
            model.estimate_lambda(1.0, 1.0, -0.5)
    
    def test_semantic_example_crystal_palace(self):
        """Test real-world example: Crystal Palace (strong defense) vs weak attack."""
        model = PoissonModel()
        
        # Weak attacker: scores 0.8 goals/match
        # Crystal Palace defense: concedes 0.5 goals/match (strong)
        lambda_vs_strong = model.estimate_lambda(
            team_attack_strength=0.8,
            opponent_defense_strength=0.5,
            venue_adjustment=1.0
        )
        
        # Expected: 0.8 * 0.5 = 0.4 goals
        assert lambda_vs_strong == 0.4
        
        # Same attacker vs weak defense: concedes 2.0 goals/match
        lambda_vs_weak = model.estimate_lambda(
            team_attack_strength=0.8,
            opponent_defense_strength=2.0,
            venue_adjustment=1.0
        )
        
        # Expected: 0.8 * 2.0 = 1.6 goals
        assert lambda_vs_weak == 1.6
        
        # Verify monotonicity: easier to score vs weak defense
        assert lambda_vs_weak > lambda_vs_strong
    
    def test_no_automatic_inversion(self):
        """Test that strong defense isn't automatically inverted (1/x)."""
        model = PoissonModel()
        
        # If code wrongly did 1/opponent_defense_strength for "strong defense":
        # Strong defense (0.5 conceded) would become 1/0.5 = 2.0 → wrong
        # This would make λ higher against strong defense (incorrect)
        
        attack = 1.5
        strong_defense_conceded = 0.5  # Concedes few goals = strong
        weak_defense_conceded = 2.0    # Concedes many goals = weak
        
        lambda_strong = model.estimate_lambda(attack, strong_defense_conceded, 1.0)
        lambda_weak = model.estimate_lambda(attack, weak_defense_conceded, 1.0)
        
        # Correct behavior: λ should be LOWER vs strong defense
        assert lambda_strong < lambda_weak, \
            "Lambda should be lower vs strong defense (low goals conceded)"
        
        assert lambda_strong == attack * strong_defense_conceded
        assert lambda_weak == attack * weak_defense_conceded
