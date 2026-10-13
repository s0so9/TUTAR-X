"""Tests for value-aware market selector (fixes OVER_0.5 dominance).

This test suite validates that the new selection logic correctly:
1. Prioritizes value (EV) over raw probability
2. Applies high base-rate protection to OVER_0.5
3. Selects markets based on calibrated_prob + edge + reliability
4. PASS when no value exists
5. Does not fabricate odds
"""

import pytest
from datetime import datetime
from app.prediction.market_selector import SmartMarketSelector, BestTip, PassDecision
from app.prediction.market_derivation import MarketProbabilities
from app.prediction.confidence_engine import ConfidenceAssessment, ConfidenceComponents


def make_market_probs(
    over_05: float = 0.95,
    over_15: float = 0.72,
    over_25: float = 0.53,
    btts_yes: float = 0.62,
    home_win: float = 0.48,
    draw: float = 0.28,
    away_win: float = 0.24
) -> MarketProbabilities:
    """Helper to create MarketProbabilities."""
    return MarketProbabilities(
        home_win=home_win,
        draw=draw,
        away_win=away_win,
        over_under={
            0.5: (over_05, 1 - over_05),
            1.5: (over_15, 1 - over_15),
            2.5: (over_25, 1 - over_25)
        },
        btts_yes=btts_yes,
        btts_no=1 - btts_yes,
        home_or_draw=home_win + draw,
        draw_or_away=draw + away_win,
        home_or_away=home_win + away_win,
        home_team_over={},
        away_team_over={}
    )


def make_confidence(
    overall: float = 0.70,
    agreement: float = 0.85,
    quality: float = 0.75
) -> ConfidenceAssessment:
    """Helper to create ConfidenceAssessment."""
    from app.prediction.confidence_engine import ConfidenceWeights

    # Determine confidence label
    if overall >= 0.7:
        label = "HIGH"
    elif overall >= 0.4:
        label = "MEDIUM"
    else:
        label = "LOW"

    return ConfidenceAssessment(
        overall_confidence=overall,
        confidence_label=label,
        components=ConfidenceComponents(
            model_agreement=agreement,
            data_quality=quality,
            sample_size_score=0.8,
            calibration_reliability=0.7,
            lineup_certainty=0.5,
            feature_stability=1.0
        ),
        weights=ConfidenceWeights(),
        component_breakdown={}
    )


class TestValueAwareSelection:
    """Test value-aware selection logic."""

    def test_no_odds_still_works(self):
        """System should work without odds (no value contribution)."""
        selector = SmartMarketSelector()

        market_probs = make_market_probs(
            over_05=0.94,
            btts_yes=0.64
        )

        confidence = make_confidence()

        result = selector.evaluate_and_select(
            market_probs=market_probs,
            confidence_assessment=confidence,
            odds_data=None  # No odds
        )

        # Should select something (OVER_0.5 likely without odds)
        assert isinstance(result, BestTip)
        assert result.value_classification == "NO_ODDS"
        assert result.edge is None
        assert result.bookmaker_odds is None

    def test_over_05_high_prob_low_value_loses(self):
        """OVER_0.5 with high prob but low value should LOSE to better value market."""
        selector = SmartMarketSelector()

        market_probs = make_market_probs(
            over_05=0.95,   # Very high probability
            btts_yes=0.64,  # Moderate probability
            over_25=0.56    # Lower probability
        )

        confidence = make_confidence()

        # Odds that make OVER_0.5 poor value, BTTS good value
        odds_data = {
            'OVER_0_5': 1.05,   # Implied prob = 0.952, edge = -0.002 (NEGATIVE VALUE)
            'BTTS_YES': 1.72,   # Implied prob = 0.581, edge = +0.059 (GOOD VALUE)
            'OVER_2_5': 1.95    # Implied prob = 0.513, edge = +0.047 (GOOD VALUE)
        }

        result = selector.evaluate_and_select(
            market_probs=market_probs,
            confidence_assessment=confidence,
            odds_data=odds_data
        )

        # Should select BTTS or OVER_2.5, NOT OVER_0.5
        assert isinstance(result, BestTip)
        assert result.market in ['BTTS_YES', 'OVER_2_5']
        assert result.market != 'OVER_0_5', "OVER_0.5 should not win despite highest probability"

        # Selected market should have positive edge
        assert result.edge > 0.03, "Selected market should have meaningful edge"

    def test_over_05_with_good_value_wins(self):
        """OVER_0.5 with GOOD value should still be selectable."""
        selector = SmartMarketSelector()

        market_probs = make_market_probs(
            over_05=0.96,
            btts_yes=0.63
        )

        confidence = make_confidence()

        # Odds that make OVER_0.5 good value (credible edge, below 8pp)
        odds_data = {
            'OVER_0_5': 1.12,   # Implied prob = 0.893, edge = +0.067, EV = +7.5%
            'BTTS_YES': 1.60    # Implied prob = 0.625, edge = +0.005 (MINIMAL VALUE)
        }

        result = selector.evaluate_and_select(
            market_probs=market_probs,
            confidence_assessment=confidence,
            odds_data=odds_data
        )

        # OVER_0.5 should win when it has strong value
        assert isinstance(result, BestTip)
        assert result.market == 'OVER_0_5'
        assert result.edge > 0.05, "OVER_0.5 should have a clear edge"
        assert result.value_classification in ['STRONG_VALUE', 'VALUE']

    def test_pass_when_all_negative_value(self):
        """Should PASS when all markets have negative value."""
        selector = SmartMarketSelector(
            min_edge=0.0  # Require non-negative edge
        )

        market_probs = make_market_probs(
            over_05=0.93,
            btts_yes=0.61,
            over_25=0.54
        )

        confidence = make_confidence()

        # All odds show negative edge
        odds_data = {
            'OVER_0_5': 1.03,   # Implied = 0.971, edge = -0.041
            'BTTS_YES': 1.50,   # Implied = 0.667, edge = -0.057
            'OVER_2_5': 1.75    # Implied = 0.571, edge = -0.031
        }

        result = selector.evaluate_and_select(
            market_probs=market_probs,
            confidence_assessment=confidence,
            odds_data=odds_data
        )

        # Should PASS
        assert isinstance(result, PassDecision)
        assert result.pass_reason in ['negative_value', 'insufficient_value']

    def test_pass_when_insufficient_ev(self):
        """Should PASS when best EV is below threshold."""
        selector = SmartMarketSelector()

        market_probs = make_market_probs(
            over_05=0.92,
            btts_yes=0.60,
            over_25=0.52
        )

        confidence = make_confidence()

        # All markets have tiny positive edge but insufficient EV
        odds_data = {
            'OVER_0_5': 1.09,   # EV = 0.92 * 1.09 - 1 = 0.003 (0.3% - too small)
            'BTTS_YES': 1.68,   # EV = 0.60 * 1.68 - 1 = 0.008 (0.8% - too small)
            'OVER_2_5': 1.95    # EV = 0.52 * 1.95 - 1 = 0.014 (1.4% - too small)
        }

        result = selector.evaluate_and_select(
            market_probs=market_probs,
            confidence_assessment=confidence,
            odds_data=odds_data
        )

        # Should PASS due to insufficient value (all EV < 3%)
        assert isinstance(result, PassDecision)
        assert result.pass_reason == 'insufficient_value'

    def test_lower_probability_higher_value_wins(self):
        """Market with lower probability but higher value should win."""
        selector = SmartMarketSelector()

        market_probs = make_market_probs(
            over_05=0.94,   # Highest probability
            over_15=0.74,
            btts_yes=0.58,  # Lower probability
            home_win=0.52   # Even lower probability
        )

        confidence = make_confidence()

        # HOME_WIN has best value despite lowest probability
        odds_data = {
            'OVER_0_5': 1.06,   # EV = -0.003 (negative)
            'OVER_1_5': 1.38,   # EV = +0.021 (2.1%)
            'BTTS_YES': 1.78,   # EV = +0.032 (3.2%)
            'HOME_WIN': 2.20    # EV = +0.144 (14.4% - BEST)
        }

        result = selector.evaluate_and_select(
            market_probs=market_probs,
            confidence_assessment=confidence,
            odds_data=odds_data
        )

        # HOME_WIN should win despite lower probability
        assert isinstance(result, BestTip)
        assert result.market == 'HOME_WIN'
        assert result.probability < 0.95  # Lower than OVER_0.5
        assert result.expected_value > 0.10, "Should have strong EV"

    def test_confidence_still_matters(self):
        """Low confidence should still cause PASS even with good value."""
        selector = SmartMarketSelector(
            min_confidence=0.50  # Require at least 50% confidence
        )

        market_probs = make_market_probs()

        # Very low confidence
        confidence = make_confidence(
            overall=0.35,  # Below threshold
            agreement=0.40,
            quality=0.30
        )

        # Good odds/value available
        odds_data = {
            'BTTS_YES': 1.85,   # Good value
            'OVER_2_5': 2.10    # Good value
        }

        result = selector.evaluate_and_select(
            market_probs=market_probs,
            confidence_assessment=confidence,
            odds_data=odds_data
        )

        # Should PASS due to poor calibration/confidence
        assert isinstance(result, PassDecision)
        assert result.pass_reason == 'poor_calibration'


class TestHighBaseRateProtection:
    """Test high base-rate market protection."""

    def test_over_05_penalty_without_value(self):
        """OVER_0.5 should receive penalty when no odds/value."""
        from app.services.odds_service import OddsService, ValueAssessment

        # No odds case
        value_no_odds = ValueAssessment(
            market="OVER_0_5",
            model_probability=0.95,
            fair_odds=1.05,
            bookmaker_odds=None,
            implied_probability=None,
            edge=None,
            expected_value=None,
            value_classification="NO_ODDS",
            value_score=0.0
        )

        base_score = 0.80
        adjusted = OddsService.apply_high_base_rate_protection(
            market="OVER_0_5",
            probability=0.95,
            value_assessment=value_no_odds,
            base_selection_score=base_score
        )

        # Should receive penalty
        assert adjusted < base_score
        assert adjusted == base_score * 0.80  # 20% penalty

    def test_over_05_no_penalty_with_value(self):
        """OVER_0.5 should NOT receive penalty when good value."""
        from app.services.odds_service import OddsService, ValueAssessment

        # Good value case
        value_good = ValueAssessment(
            market="OVER_0_5",
            model_probability=0.95,
            fair_odds=1.05,
            bookmaker_odds=1.25,
            implied_probability=0.80,
            edge=0.15,
            expected_value=0.1875,  # 18.75% EV
            value_classification="STRONG_VALUE",
            value_score=1.0
        )

        base_score = 0.80
        adjusted = OddsService.apply_high_base_rate_protection(
            market="OVER_0_5",
            probability=0.95,
            value_assessment=value_good,
            base_selection_score=base_score
        )

        # Should NOT receive penalty
        assert adjusted == base_score

    def test_btts_no_penalty(self):
        """Non-high-base-rate markets should never receive penalty."""
        from app.services.odds_service import OddsService, ValueAssessment

        value_neutral = ValueAssessment(
            market="BTTS_YES",
            model_probability=0.62,
            fair_odds=1.61,
            bookmaker_odds=None,
            implied_probability=None,
            edge=None,
            expected_value=None,
            value_classification="NO_ODDS",
            value_score=0.0
        )

        base_score = 0.75
        adjusted = OddsService.apply_high_base_rate_protection(
            market="BTTS_YES",
            probability=0.62,
            value_assessment=value_neutral,
            base_selection_score=base_score
        )

        # Should NOT receive penalty
        assert adjusted == base_score


class TestOddsService:
    """Test odds service utilities."""

    def test_implied_probability(self):
        """Test implied probability calculation."""
        from app.services.odds_service import MarketOdds, OddsAvailability

        market_odds = MarketOdds(
            market="BTTS_YES",
            selection="Both Teams to Score",
            odds=1.72,
            odds_timestamp=datetime.utcnow(),
            provider="iddaa",
            availability=OddsAvailability.AVAILABLE
        )

        implied = market_odds.implied_probability
        assert implied == pytest.approx(1.0 / 1.72, rel=1e-6)
        assert implied == pytest.approx(0.5814, rel=1e-3)

    def test_edge_calculation(self):
        """Test edge calculation."""
        from app.services.odds_service import MarketOdds, OddsAvailability

        market_odds = MarketOdds(
            market="HOME_WIN",
            selection="Home Win",
            odds=2.20,
            odds_timestamp=datetime.utcnow(),
            provider="iddaa",
            availability=OddsAvailability.AVAILABLE
        )

        model_prob = 0.52
        edge = market_odds.calculate_edge(model_prob)

        implied = 1.0 / 2.20  # 0.4545
        expected_edge = model_prob - implied  # 0.52 - 0.4545 = 0.0655

        assert edge == pytest.approx(expected_edge, rel=1e-4)
        assert edge > 0  # Positive edge

    def test_expected_value_calculation(self):
        """Test EV calculation."""
        from app.services.odds_service import MarketOdds, OddsAvailability

        market_odds = MarketOdds(
            market="OVER_2_5",
            selection="Over 2.5 Goals",
            odds=2.10,
            odds_timestamp=datetime.utcnow(),
            provider="iddaa",
            availability=OddsAvailability.AVAILABLE
        )

        model_prob = 0.56
        ev = market_odds.calculate_expected_value(model_prob)

        expected_ev = (model_prob * 2.10) - 1.0  # (0.56 * 2.10) - 1 = 0.176

        assert ev == pytest.approx(expected_ev, rel=1e-4)
        assert ev > 0.15  # Strong positive EV

    def test_no_odds_returns_none(self):
        """Test that missing odds return None for metrics."""
        from app.services.odds_service import MarketOdds, OddsAvailability

        market_odds = MarketOdds(
            market="BTTS_YES",
            selection="Both Teams to Score",
            odds=None,  # No odds
            odds_timestamp=None,
            provider=None,
            availability=OddsAvailability.UNAVAILABLE
        )

        assert market_odds.implied_probability is None
        assert market_odds.calculate_edge(0.62) is None
        assert market_odds.calculate_expected_value(0.62) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
