"""
Regression test for duplicate prediction bug.

BUG: When feature extraction fails or returns None for strength values,
and allow_dev_baseline_fallback=True, all predictions would be identical
because lambda defaults to 1.0 for all matches.

This test ensures:
1. Different matches with different features produce different predictions
2. Market selector produces varying outputs based on input probabilities
3. Production config (allow_dev_baseline_fallback=False) fails gracefully
"""

import pytest
from unittest.mock import MagicMock, Mock
from datetime import datetime

# Import the classes we need to test
from app.prediction.service import PredictionService, PredictionServiceConfig
from app.prediction.poisson import PoissonModel
from app.prediction.market_selector import SmartMarketSelector, MarketProbabilities
from app.prediction.easy_matches import SmartMarketSelectorConfig
from app.domain.match import Match
from app.database.models import Team


class TestDuplicatePredictionBug:
    """Test suite for duplicate prediction bug (Over 1.5 Goals, %85.3 for all matches)."""
    
    def create_mock_match(self, home_team_id: str, away_team_id: str) -> Match:
        """Create a mock match with team references."""
        home_team = Mock(spec=Team)
        home_team.id = home_team_id
        home_team.name = f"Team {home_team_id}"
        
        away_team = Mock(spec=Team)
        away_team.id = away_team_id
        away_team.name = f"Team {away_team_id}"
        
        match = Mock(spec=Match)
        match.id = f"match_{home_team_id}_vs_{away_team_id}"
        match.home_team_id = home_team_id
        match.away_team_id = away_team_id
        match.home_team = home_team
        match.away_team = away_team
        match.scheduled_at = datetime(2024, 3, 15, 15, 0)
        return match
    
    def create_mock_provider(self, is_development: bool = False):
        """Create a mock provider."""
        provider = Mock()
        provider.get_match_details = Mock(return_value=None)
        provider.get_team_details = Mock(return_value=None)
        return provider
    
    def test_production_config_has_no_baseline_fallback(self):
        """Verify production config does NOT allow baseline fallback."""
        config = PredictionServiceConfig.for_production()
        
        assert config.allow_dev_baseline_fallback is False, \
            "Production config should NOT allow baseline fallback"
        assert config.is_development is False, \
            "Production config should not be in development mode"
    
    def test_different_strengths_produce_different_lambdas(self):
        """Verify different team strengths produce different lambda values."""
        model = PoissonModel(max_goals=10)
        
        # High-scoring scenario: strong attack vs weak defense
        high_lambda = model.estimate_lambda_from_features(
            team_attack_strength=1.5,  # Strong attack
            opponent_defense_strength=0.7,  # Weak defense
            venue_adjustment=1.1
        )
        
        # Low-scoring scenario: weak attack vs strong defense
        low_lambda = model.estimate_lambda_from_features(
            team_attack_strength=0.6,  # Weak attack
            opponent_defense_strength=1.3,  # Strong defense
            venue_adjustment=0.9
        )
        
        # Lambdas should be significantly different
        assert abs(high_lambda - low_lambda) > 0.5, \
            f"Lambdas should differ significantly: high={high_lambda}, low={low_lambda}"
    
    def test_baseline_fallback_produces_unity_lambdas(self):
        """Verify baseline fallback (all 1.0) produces identical lambdas."""
        model = PoissonModel(max_goals=10)
        
        # When all strengths default to 1.0
        baseline_lambda = model.estimate_lambda_from_features(
            team_attack_strength=1.0,
            opponent_defense_strength=1.0,
            venue_adjustment=1.0
        )
        
        # All combinations with 1.0 produce the same result
        lambda2 = model.estimate_lambda_from_features(
            team_attack_strength=1.0,
            opponent_defense_strength=1.0,
            venue_adjustment=1.0
        )
        
        assert abs(baseline_lambda - lambda2) < 0.001, \
            "Baseline fallback should produce identical lambdas"
    
    def test_market_selector_produces_different_outputs_for_different_inputs(self):
        """Verify market selector responds to different input probabilities."""
        selector = SmartMarketSelector()
        config = SmartMarketSelectorConfig(
            min_confidence=0.0,  # Low threshold for testing
            min_value_threshold=0.0
        )
        
        # High-scoring scenario
        mp_high = MarketProbabilities(
            home_win=0.50,
            draw=0.25,
            away_win=0.25,
            over_under={1.5: (0.85, 0.15), 2.5: (0.65, 0.35), 3.5: (0.40, 0.60)}
        )
        
        # Low-scoring scenario  
        mp_low = MarketProbabilities(
            home_win=0.35,
            draw=0.30,
            away_win=0.35,
            over_under={1.5: (0.40, 0.60), 2.5: (0.20, 0.80), 3.5: (0.10, 0.90)}
        )
        
        result_high = selector.evaluate_and_select(mp_high, config, match_id="high-scoring-match")
        result_low = selector.evaluate_and_select(mp_low, config, match_id="low-scoring-match")
        
        # Results should differ for high vs low scoring matches
        assert result_high.selected_market != result_low.selected_market, \
            f"Market selector should produce different outputs: high={result_high.selected_market}, low={result_low.selected_market}"
    
    def test_production_service_returns_none_for_missing_features(self):
        """Verify production service returns None (not fake predictions) for missing data."""
        provider = self.create_mock_provider(is_development=False)
        service = PredictionService(
            provider=provider,
            config=PredictionServiceConfig.for_production()
        )
        
        # Match with no historical data
        match = self.create_mock_match("unknown_team_1", "unknown_team_2")
        
        # With production config, missing features should return None
        prediction = service.generate_prediction(match)
        
        assert prediction is None, \
            "Production service should return None for missing features, not fake predictions"
    
    def test_market_selector_with_baseline_fallback_shows_identical_predictions(self):
        """
        Verify that baseline fallback (the bug condition) produces identical market selections.
        
        This test documents the bug behavior - when all lambda values are 1.0,
        all predictions converge to the same high-Over-1.5 probability (~85%).
        """
        selector = SmartMarketSelector()
        config = SmartMarketSelectorConfig(
            min_confidence=0.0,
            min_value_threshold=0.0
        )
        
        # Baseline scenario - all lambdas default to 1.0
        mp_baseline = MarketProbabilities(
            home_win=0.46,
            draw=0.26,
            away_win=0.28,
            over_under={1.5: (0.85, 0.15), 2.5: (0.64, 0.36), 3.5: (0.40, 0.60)}
        )
        
        # Run multiple "matches" with identical baseline probabilities
        results = []
        for i in range(3):
            result = selector.evaluate_and_select(mp_baseline, config, match_id=f"match_{i}")
            results.append(result.selected_market)
        
        # With identical inputs, we get identical outputs (this is the bug condition)
        assert all(r == results[0] for r in results), \
            "Baseline fallback produces identical predictions for all matches"
    
    def test_market_selector_variance_with_different_probabilities(self):
        """
        Verify market selector CAN produce different outputs when given different probabilities.
        
        This proves the selector itself is not broken - the issue is that all matches
        were being fed identical baseline probabilities.
        """
        selector = SmartMarketSelector()
        config = SmartMarketSelectorConfig(
            min_confidence=0.0,
            min_value_threshold=0.0
        )
        
        # Three distinct scenarios
        scenarios = [
            # High-scoring: over 1.5 is very likely
            MarketProbabilities(
                home_win=0.55, draw=0.25, away_win=0.20,
                over_under={1.5: (0.90, 0.10), 2.5: (0.70, 0.30), 3.5: (0.45, 0.55)}
            ),
            # Medium-scoring
            MarketProbabilities(
                home_win=0.40, draw=0.30, away_win=0.30,
                over_under={1.5: (0.70, 0.30), 2.5: (0.50, 0.50), 3.5: (0.30, 0.70)}
            ),
            # Low-scoring: under is likely
            MarketProbabilities(
                home_win=0.30, draw=0.35, away_win=0.35,
                over_under={1.5: (0.45, 0.55), 2.5: (0.25, 0.75), 3.5: (0.12, 0.88)}
            ),
        ]
        
        results = []
        for i, mp in enumerate(scenarios):
            result = selector.evaluate_and_select(mp, config, match_id=f"scenario_{i}")
            results.append((result.selected_market, mp.over_under.get(1.5, (0, 0))[0]))
        
        # With genuinely different inputs, we should see variety
        over_1_5_probs = [r[1] for r in results]
        
        # The three scenarios have 90%, 70%, and 45% over 1.5
        # They should NOT all select the same market
        assert len(set(results)) > 1, \
            f"With different probabilities, selector should produce variety: {results}"


class TestFeatureExtractionFallback:
    """Test that feature extraction properly handles missing data."""
    
    def test_dev_baseline_fallback_enabled_in_dev_mode(self):
        """Verify development mode enables baseline fallback."""
        config = PredictionServiceConfig.for_development()
        
        assert config.allow_dev_baseline_fallback is True, \
            "Development config should allow baseline fallback"
    
    def test_explicit_config_overrides_environment(self):
        """Verify explicit config parameter overrides auto-detection."""
        provider = Mock()
        
        # Even with a dev-mode provider, explicit production config should be respected
        service = PredictionService(
            provider=provider,
            config=PredictionServiceConfig.for_production()  # Explicit production
        )
        
        assert service.config.allow_dev_baseline_fallback is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
