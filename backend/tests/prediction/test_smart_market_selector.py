"""Tests for Smart Market Selector.

Validates the value-based BEST TIP selection logic including:
- Value assessment (edge, EV)
- Market competition (shots vs goals)
- PASS logic
- Reliability and uncertainty integration
- Scoring formula
"""

import pytest
from app.prediction.easy_matches import (
    SmartMarketSelector,
    SmartMarketSelectorConfig,
    MarketCandidate,
    BestTipResult,
    ValueStatus,
    CalibrationStatus,
)


class TestValueAssessment:
    """Test Scenario Group A: Value Assessment."""
    
    def test_high_probability_no_edge_not_selected(self):
        """Test 1: High probability + no edge → NOT selected.
        
        Over 1.5 at 86% prob with bookmaker odds 1.16 should NOT be selected
        when another market has positive edge.
        """
        selector = SmartMarketSelector()
        
        # Over 1.5: high prob, no edge
        over_15 = MarketCandidate(
            market_type="over_under",
            market_label="Over 1.5 Goals",
            outcome="over",
            threshold=1.5,
            model_probability=0.86,
            calibrated_probability=0.86,
            fair_odds=1.16,
            bookmaker_odds=1.16,
            implied_probability=0.862,  # 1/1.16
            edge=0.002,  # Almost zero edge
            expected_value=-0.0024,  # No value
            value_status=ValueStatus.NEUTRAL,
            reliability_score=0.70,
            uncertainty=0.30,
            data_quality=0.75,
            model_agreement=0.70,
            sample_size=50,
            calibration_status=CalibrationStatus.FITTED,
        )
        
        # Over 2.5: moderate prob, positive edge
        over_25 = MarketCandidate(
            market_type="over_under",
            market_label="Over 2.5 Goals",
            outcome="over",
            threshold=2.5,
            model_probability=0.60,
            calibrated_probability=0.60,
            fair_odds=1.67,
            bookmaker_odds=1.90,
            implied_probability=0.526,  # 1/1.90
            edge=0.074,  # Positive edge
            expected_value=0.14,  # 14% expected return
            value_status=ValueStatus.POSITIVE_VALUE,
            reliability_score=0.68,
            uncertainty=0.35,
            data_quality=0.75,
            model_agreement=0.70,
            sample_size=50,
            calibration_status=CalibrationStatus.FITTED,
        )
        
        result = selector.select_best_tip(
            match_id="test_1",
            candidates=[over_15, over_25],
        )
        
        assert not result.is_pass
        assert result.best_tip is not None
        assert result.best_tip.market_label == "Over 2.5 Goals"
        assert result.best_tip.edge > 0.05
        assert result.best_tip.composite_score > over_15.composite_score
    
    def test_positive_edge_wins_over_high_probability(self):
        """Test 2: Positive edge wins over high probability."""
        selector = SmartMarketSelector()
        
        # Home win: 0.65 prob, odds 1.80 (implied 0.556) → edge = 0.094
        home_win = MarketCandidate(
            market_type="match_result",
            market_label="Home Win",
            outcome="home",
            model_probability=0.65,
            calibrated_probability=0.65,
            fair_odds=1.54,
            bookmaker_odds=1.80,
            implied_probability=0.556,
            edge=0.094,
            expected_value=0.17,
            value_status=ValueStatus.POSITIVE_VALUE,
            reliability_score=0.72,
            uncertainty=0.30,
            data_quality=0.80,
            model_agreement=0.75,
            sample_size=60,
            calibration_status=CalibrationStatus.FITTED,
        )
        
        # Over 2.5: 0.70 prob, odds 1.43 (implied 0.699) → edge = 0.001
        over_25 = MarketCandidate(
            market_type="over_under",
            market_label="Over 2.5 Goals",
            outcome="over",
            threshold=2.5,
            model_probability=0.70,
            calibrated_probability=0.70,
            fair_odds=1.43,
            bookmaker_odds=1.43,
            implied_probability=0.699,
            edge=0.001,
            expected_value=0.001,
            value_status=ValueStatus.NEUTRAL,
            reliability_score=0.70,
            uncertainty=0.30,
            data_quality=0.80,
            model_agreement=0.75,
            sample_size=60,
            calibration_status=CalibrationStatus.FITTED,
        )
        
        result = selector.select_best_tip(
            match_id="test_2",
            candidates=[home_win, over_25],
        )
        
        assert not result.is_pass
        assert result.best_tip.market_label == "Home Win"
        assert result.best_tip.edge > 0.08
    
    def test_expected_value_calculation_correctness(self):
        """Test 3: Expected value calculation correctness."""
        selector = SmartMarketSelector()
        
        # prob=0.60, odds=2.0 → EV = 0.60 * 2.0 - 1 = 0.20
        candidate = MarketCandidate(
            market_type="match_result",
            market_label="Home Win",
            outcome="home",
            model_probability=0.60,
            calibrated_probability=0.60,
            fair_odds=1.67,
            bookmaker_odds=2.0,
            implied_probability=0.50,
            edge=0.10,
            expected_value=0.20,
            value_status=ValueStatus.POSITIVE_VALUE,
            reliability_score=0.75,
            uncertainty=0.25,
            data_quality=0.80,
            model_agreement=0.80,
            sample_size=50,
            calibration_status=CalibrationStatus.FITTED,
        )
        
        result = selector.select_best_tip(
            match_id="test_3",
            candidates=[candidate],
        )
        
        assert not result.is_pass
        assert result.best_tip.expected_value == pytest.approx(0.20)
        assert result.best_ev == pytest.approx(0.20)
    
    def test_value_status_unavailable_when_no_odds(self):
        """Test 4: Value status UNAVAILABLE when no bookmaker odds."""
        selector = SmartMarketSelector()
        
        # High probability pick without odds
        high_prob_no_odds = MarketCandidate(
            market_type="match_result",
            market_label="Home Win",
            outcome="home",
            model_probability=0.80,
            calibrated_probability=0.78,
            fair_odds=1.28,
            bookmaker_odds=None,
            implied_probability=None,
            edge=None,
            expected_value=None,
            value_status=ValueStatus.UNAVAILABLE,
            reliability_score=0.75,
            uncertainty=0.25,
            data_quality=0.80,
            model_agreement=0.80,
            sample_size=50,
            calibration_status=CalibrationStatus.FITTED,
        )
        
        # Medium probability pick without odds
        medium_prob_no_odds = MarketCandidate(
            market_type="over_under",
            market_label="Over 2.5 Goals",
            outcome="over",
            threshold=2.5,
            model_probability=0.60,
            calibrated_probability=0.58,
            fair_odds=1.72,
            bookmaker_odds=None,
            implied_probability=None,
            edge=None,
            expected_value=None,
            value_status=ValueStatus.UNAVAILABLE,
            reliability_score=0.70,
            uncertainty=0.30,
            data_quality=0.75,
            model_agreement=0.75,
            sample_size=45,
            calibration_status=CalibrationStatus.FITTED,
        )
        
        result = selector.select_best_tip(
            match_id="test_4",
            candidates=[high_prob_no_odds, medium_prob_no_odds],
        )
        
        # High probability should win despite no odds
        assert not result.is_pass
        assert result.best_tip.market_label == "Home Win"
        assert result.best_tip.value_status == ValueStatus.UNAVAILABLE
        assert result.best_edge is None


class TestMarketCompetition:
    """Test Scenario Group B: Market Competition."""
    
    def test_shot_market_competes_with_goals(self):
        """Test 5: Shot market vs goal market competition."""
        selector = SmartMarketSelector()
        
        # Total Shots 20+: prob=0.68, odds=1.90, edge=0.15
        total_shots = MarketCandidate(
            market_type="shots",
            market_label="Total Shots Over 20+",
            outcome="over",
            threshold=20.0,
            model_probability=0.72,
            calibrated_probability=0.68,
            fair_odds=1.47,
            bookmaker_odds=1.90,
            implied_probability=0.526,
            edge=0.154,  # Strong edge
            expected_value=0.292,
            value_status=ValueStatus.POSITIVE_VALUE,
            reliability_score=0.72,
            uncertainty=0.30,
            data_quality=0.75,
            model_agreement=0.75,
            sample_size=55,
            calibration_status=CalibrationStatus.FITTED,
            distribution_type="NEGATIVE_BINOMIAL",
            expected_count=22.5,
        )
        
        # Over 2.5: prob=0.65, odds=1.50, edge=0.05
        over_25 = MarketCandidate(
            market_type="over_under",
            market_label="Over 2.5 Goals",
            outcome="over",
            threshold=2.5,
            model_probability=0.65,
            calibrated_probability=0.65,
            fair_odds=1.54,
            bookmaker_odds=1.50,
            implied_probability=0.667,
            edge=-0.017,  # Slight negative edge
            expected_value=-0.025,
            value_status=ValueStatus.NEGATIVE_VALUE,
            reliability_score=0.70,
            uncertainty=0.30,
            data_quality=0.75,
            model_agreement=0.75,
            sample_size=60,
            calibration_status=CalibrationStatus.FITTED,
        )
        
        result = selector.select_best_tip(
            match_id="test_5",
            candidates=[total_shots, over_25],
        )
        
        assert not result.is_pass
        assert result.best_tip.market_label == "Total Shots Over 20+"
        assert result.best_tip.edge > 0.10
    
    def test_low_odds_with_edge_accepted(self):
        """Test 6: Low-odds market with edge accepted."""
        selector = SmartMarketSelector()
        
        # Home win: prob=0.85, odds=1.25 (implied 0.80) → edge = 0.05
        home_win_low_odds = MarketCandidate(
            market_type="match_result",
            market_label="Home Win",
            outcome="home",
            model_probability=0.85,
            calibrated_probability=0.85,
            fair_odds=1.18,
            bookmaker_odds=1.25,
            implied_probability=0.80,
            edge=0.05,
            expected_value=0.0625,
            value_status=ValueStatus.POSITIVE_VALUE,
            reliability_score=0.80,
            uncertainty=0.20,
            data_quality=0.85,
            model_agreement=0.80,
            sample_size=70,
            calibration_status=CalibrationStatus.FITTED,
        )
        
        result = selector.select_best_tip(
            match_id="test_6",
            candidates=[home_win_low_odds],
        )
        
        assert not result.is_pass
        assert result.best_tip.bookmaker_odds == 1.25
        assert result.best_tip.edge > 0.04
    
    def test_high_odds_poor_calibration_rejected(self):
        """Test 7: High odds but poor calibration should lose."""
        selector = SmartMarketSelector()
        
        # Away win: high odds, poor calibration
        away_win = MarketCandidate(
            market_type="match_result",
            market_label="Away Win",
            outcome="away",
            model_probability=0.30,
            calibrated_probability=0.30,
            fair_odds=3.33,
            bookmaker_odds=4.0,
            implied_probability=0.25,
            edge=0.05,
            expected_value=0.20,
            value_status=ValueStatus.POSITIVE_VALUE,
            reliability_score=0.35,  # Poor reliability
            uncertainty=0.60,  # High uncertainty
            data_quality=0.50,
            model_agreement=0.50,
            sample_size=15,  # Low sample
            calibration_status=CalibrationStatus.NOT_FITTED,
        )
        
        # Home win: reliable low-odds pick
        home_win = MarketCandidate(
            market_type="match_result",
            market_label="Home Win",
            outcome="home",
            model_probability=0.70,
            calibrated_probability=0.70,
            fair_odds=1.43,
            bookmaker_odds=1.50,
            implied_probability=0.667,
            edge=0.033,
            expected_value=0.05,
            value_status=ValueStatus.POSITIVE_VALUE,
            reliability_score=0.75,
            uncertainty=0.25,
            data_quality=0.80,
            model_agreement=0.78,
            sample_size=60,
            calibration_status=CalibrationStatus.FITTED,
        )
        
        result = selector.select_best_tip(
            match_id="test_7",
            candidates=[away_win, home_win],
        )
        
        assert not result.is_pass
        assert result.best_tip.market_label == "Home Win"


class TestPassLogic:
    """Test Scenario Group C: PASS Logic."""
    
    def test_pass_no_positive_edge(self):
        """Test 8: PASS when no positive edge."""
        selector = SmartMarketSelector()
        
        candidates = [
            MarketCandidate(
                market_type="match_result",
                market_label="Home Win",
                outcome="home",
                model_probability=0.60,
                calibrated_probability=0.60,
                fair_odds=1.67,
                bookmaker_odds=1.55,
                implied_probability=0.645,
                edge=-0.045,  # Negative edge
                expected_value=-0.07,
                value_status=ValueStatus.NEGATIVE_VALUE,
                reliability_score=0.70,
                uncertainty=0.30,
                data_quality=0.75,
                model_agreement=0.75,
                sample_size=50,
                calibration_status=CalibrationStatus.FITTED,
            ),
            MarketCandidate(
                market_type="over_under",
                market_label="Over 2.5 Goals",
                outcome="over",
                threshold=2.5,
                model_probability=0.55,
                calibrated_probability=0.55,
                fair_odds=1.82,
                bookmaker_odds=1.75,
                implied_probability=0.571,
                edge=-0.021,
                expected_value=-0.037,
                value_status=ValueStatus.NEGATIVE_VALUE,
                reliability_score=0.68,
                uncertainty=0.32,
                data_quality=0.75,
                model_agreement=0.75,
                sample_size=50,
                calibration_status=CalibrationStatus.FITTED,
            ),
        ]
        
        result = selector.select_best_tip(
            match_id="test_8",
            candidates=candidates,
        )
        
        assert result.is_pass
        assert result.pass_reason == "NO_POSITIVE_EDGE"
        assert result.best_tip is None
    
    def test_pass_low_reliability(self):
        """Test 9: PASS when low reliability."""
        selector = SmartMarketSelector()
        
        candidates = [
            MarketCandidate(
                market_type="match_result",
                market_label="Home Win",
                outcome="home",
                model_probability=0.70,
                calibrated_probability=0.70,
                fair_odds=1.43,
                bookmaker_odds=1.60,
                implied_probability=0.625,
                edge=0.075,
                expected_value=0.12,
                value_status=ValueStatus.POSITIVE_VALUE,
                reliability_score=0.35,  # Low reliability
                uncertainty=0.50,
                data_quality=0.60,
                model_agreement=0.60,
                sample_size=20,
                calibration_status=CalibrationStatus.NOT_FITTED,
            ),
        ]
        
        result = selector.select_best_tip(
            match_id="test_9",
            candidates=candidates,
        )
        
        assert result.is_pass
        assert result.pass_reason == "LOW_RELIABILITY"
    
    def test_pass_high_uncertainty(self):
        """Test 10: PASS when high uncertainty."""
        selector = SmartMarketSelector()
        
        candidates = [
            MarketCandidate(
                market_type="match_result",
                market_label="Home Win",
                outcome="home",
                model_probability=0.60,
                calibrated_probability=0.60,
                fair_odds=1.67,
                bookmaker_odds=1.85,
                implied_probability=0.541,
                edge=0.059,
                expected_value=0.11,
                value_status=ValueStatus.POSITIVE_VALUE,
                reliability_score=0.50,
                uncertainty=0.75,  # High uncertainty
                data_quality=0.45,
                model_agreement=0.40,
                sample_size=25,
                calibration_status=CalibrationStatus.NOT_FITTED,
            ),
        ]
        
        result = selector.select_best_tip(
            match_id="test_10",
            candidates=candidates,
        )
        
        assert result.is_pass
        assert result.pass_reason == "HIGH_UNCERTAINTY"
    
    def test_pass_no_odds_low_confidence(self):
        """Test 11: PASS when no bookmaker odds and low confidence."""
        selector = SmartMarketSelector()
        
        candidates = [
            MarketCandidate(
                market_type="match_result",
                market_label="Home Win",
                outcome="home",
                model_probability=0.55,  # Low probability
                calibrated_probability=0.53,
                fair_odds=1.89,
                bookmaker_odds=None,
                implied_probability=None,
                edge=None,
                expected_value=None,
                value_status=ValueStatus.UNAVAILABLE,
                reliability_score=0.65,
                uncertainty=0.40,
                data_quality=0.70,
                model_agreement=0.70,
                sample_size=40,
                calibration_status=CalibrationStatus.FITTED,
            ),
        ]
        
        result = selector.select_best_tip(
            match_id="test_11",
            candidates=candidates,
        )
        
        assert result.is_pass
        assert result.pass_reason == "NO_BOOKMAKER_ODDS_AND_LOW_CONFIDENCE"


class TestReliabilityUncertainty:
    """Test Scenario Group D: Reliability & Uncertainty."""
    
    def test_reliability_components_integration(self):
        """Test 12: Reliability components integration."""
        selector = SmartMarketSelector()
        
        # High reliability market
        high_reliability = MarketCandidate(
            market_type="match_result",
            market_label="Home Win",
            outcome="home",
            model_probability=0.65,
            calibrated_probability=0.65,
            fair_odds=1.54,
            bookmaker_odds=1.70,
            implied_probability=0.588,
            edge=0.062,
            expected_value=0.105,
            value_status=ValueStatus.POSITIVE_VALUE,
            reliability_score=0.85,  # High reliability
            brier_score=0.15,  # Low Brier = good
            hit_rate=0.78,
            uncertainty=0.20,
            data_quality=0.85,
            model_agreement=0.80,
            sample_size=80,
            calibration_status=CalibrationStatus.FITTED,
        )
        
        # Low reliability market
        low_reliability = MarketCandidate(
            market_type="over_under",
            market_label="Over 2.5 Goals",
            outcome="over",
            threshold=2.5,
            model_probability=0.68,
            calibrated_probability=0.68,
            fair_odds=1.47,
            bookmaker_odds=1.75,
            implied_probability=0.571,
            edge=0.109,  # Higher edge
            expected_value=0.19,  # Higher EV
            value_status=ValueStatus.POSITIVE_VALUE,
            reliability_score=0.45,  # Low reliability
            brier_score=0.35,  # High Brier = bad
            hit_rate=0.55,
            uncertainty=0.45,
            data_quality=0.60,
            model_agreement=0.60,
            sample_size=30,
            calibration_status=CalibrationStatus.NOT_FITTED,
        )
        
        result = selector.select_best_tip(
            match_id="test_12",
            candidates=[high_reliability, low_reliability],
        )
        
        # High reliability should win despite lower edge/EV
        assert not result.is_pass
        assert result.best_tip.market_label == "Home Win"
        assert result.best_tip.reliability_score > 0.80
    
    def test_uncertainty_penalty_application(self):
        """Test 13: High uncertainty reduces composite score."""
        selector = SmartMarketSelector()
        
        # Same market, different uncertainty levels
        low_uncertainty = MarketCandidate(
            market_type="match_result",
            market_label="Home Win",
            outcome="home",
            model_probability=0.65,
            calibrated_probability=0.65,
            fair_odds=1.54,
            bookmaker_odds=1.70,
            implied_probability=0.588,
            edge=0.062,
            expected_value=0.105,
            value_status=ValueStatus.POSITIVE_VALUE,
            reliability_score=0.75,
            uncertainty=0.20,  # Low uncertainty
            data_quality=0.80,
            model_agreement=0.80,
            sample_size=60,
            calibration_status=CalibrationStatus.FITTED,
        )
        
        high_uncertainty = MarketCandidate(
            market_type="over_under",
            market_label="Over 2.5 Goals",
            outcome="over",
            threshold=2.5,
            model_probability=0.65,
            calibrated_probability=0.65,
            fair_odds=1.54,
            bookmaker_odds=1.70,
            implied_probability=0.588,
            edge=0.062,
            expected_value=0.105,
            value_status=ValueStatus.POSITIVE_VALUE,
            reliability_score=0.75,
            uncertainty=0.65,  # High uncertainty
            data_quality=0.80,
            model_agreement=0.80,
            sample_size=60,
            calibration_status=CalibrationStatus.FITTED,
        )
        
        result = selector.select_best_tip(
            match_id="test_13",
            candidates=[low_uncertainty, high_uncertainty],
        )
        
        assert not result.is_pass
        assert low_uncertainty.composite_score > high_uncertainty.composite_score
        # Uncertainty penalty should be visible
        assert high_uncertainty.score_breakdown['uncertainty_penalty'] < low_uncertainty.score_breakdown['uncertainty_penalty']
    
    def test_model_agreement_bonus(self):
        """Test 14: High model agreement increases score."""
        selector = SmartMarketSelector()
        
        high_agreement = MarketCandidate(
            market_type="match_result",
            market_label="Home Win",
            outcome="home",
            model_probability=0.65,
            calibrated_probability=0.65,
            fair_odds=1.54,
            bookmaker_odds=1.70,
            implied_probability=0.588,
            edge=0.062,
            expected_value=0.105,
            value_status=ValueStatus.POSITIVE_VALUE,
            reliability_score=0.70,
            uncertainty=0.30,
            data_quality=0.75,
            model_agreement=0.90,  # High agreement
            sample_size=60,
            calibration_status=CalibrationStatus.FITTED,
        )
        
        low_agreement = MarketCandidate(
            market_type="over_under",
            market_label="Over 2.5 Goals",
            outcome="over",
            threshold=2.5,
            model_probability=0.65,
            calibrated_probability=0.65,
            fair_odds=1.54,
            bookmaker_odds=1.70,
            implied_probability=0.588,
            edge=0.062,
            expected_value=0.105,
            value_status=ValueStatus.POSITIVE_VALUE,
            reliability_score=0.70,
            uncertainty=0.30,
            data_quality=0.75,
            model_agreement=0.45,  # Low agreement
            sample_size=60,
            calibration_status=CalibrationStatus.FITTED,
        )
        
        result = selector.select_best_tip(
            match_id="test_14",
            candidates=[high_agreement, low_agreement],
        )
        
        assert not result.is_pass
        assert high_agreement.composite_score > low_agreement.composite_score


class TestEdgeCases:
    """Test Scenario Group E: Edge Cases."""
    
    def test_multiple_shot_markets(self):
        """Test 15: Multiple shot thresholds available."""
        selector = SmartMarketSelector()
        
        candidates = [
            MarketCandidate(
                market_type="shots",
                market_label="Team Shots Over 15+",
                outcome="over",
                threshold=15.0,
                model_probability=0.70,
                calibrated_probability=0.70,
                fair_odds=1.43,
                bookmaker_odds=1.65,
                implied_probability=0.606,
                edge=0.094,
                expected_value=0.155,
                value_status=ValueStatus.POSITIVE_VALUE,
                reliability_score=0.70,
                uncertainty=0.30,
                data_quality=0.75,
                model_agreement=0.75,
                sample_size=50,
                calibration_status=CalibrationStatus.FITTED,
                distribution_type="NEGATIVE_BINOMIAL",
            ),
            MarketCandidate(
                market_type="shots",
                market_label="Team Shots Over 18+",
                outcome="over",
                threshold=18.0,
                model_probability=0.60,
                calibrated_probability=0.60,
                fair_odds=1.67,
                bookmaker_odds=2.0,
                implied_probability=0.50,
                edge=0.10,  # Higher edge
                expected_value=0.20,  # Higher EV
                value_status=ValueStatus.POSITIVE_VALUE,
                reliability_score=0.68,
                uncertainty=0.32,
                data_quality=0.75,
                model_agreement=0.75,
                sample_size=50,
                calibration_status=CalibrationStatus.FITTED,
                distribution_type="NEGATIVE_BINOMIAL",
            ),
        ]
        
        result = selector.select_best_tip(
            match_id="test_15",
            candidates=candidates,
        )
        
        assert not result.is_pass
        # 18+ should win due to higher edge/EV
        assert result.best_tip.threshold == 18.0
    
    def test_calibrated_probability_used(self):
        """Test 16: Selector must use calibrated_probability when available."""
        selector = SmartMarketSelector()
        
        candidate = MarketCandidate(
            market_type="match_result",
            market_label="Home Win",
            outcome="home",
            model_probability=0.70,  # Model says 70%
            calibrated_probability=0.65,  # Calibrated to 65%
            fair_odds=1.54,  # Should be 1/0.65 = 1.54
            bookmaker_odds=1.70,
            implied_probability=0.588,
            edge=0.062,  # 0.65 - 0.588
            expected_value=0.105,  # 0.65 * 1.70 - 1
            value_status=ValueStatus.POSITIVE_VALUE,
            reliability_score=0.75,
            uncertainty=0.30,
            data_quality=0.80,
            model_agreement=0.80,
            sample_size=60,
            calibration_status=CalibrationStatus.FITTED,
        )
        
        result = selector.select_best_tip(
            match_id="test_16",
            candidates=[candidate],
        )
        
        assert not result.is_pass
        # Fair odds should be based on calibrated probability
        assert candidate.fair_odds == pytest.approx(1.54, abs=0.01)
        # Edge should be based on calibrated probability
        assert candidate.edge == pytest.approx(0.062, abs=0.01)
    
    def test_empty_candidates_list(self):
        """Test 17: Handle empty candidates list gracefully."""
        selector = SmartMarketSelector()
        
        result = selector.select_best_tip(
            match_id="test_17",
            candidates=[],
        )
        
        assert result.is_pass
        assert result.pass_reason == "NO_CANDIDATES"
        assert result.best_tip is None
        assert len(result.all_candidates) == 0


class TestScoringFormula:
    """Test scoring formula components."""
    
    def test_score_breakdown_populated(self):
        """Test that score breakdown is populated."""
        selector = SmartMarketSelector()
        
        candidate = MarketCandidate(
            market_type="match_result",
            market_label="Home Win",
            outcome="home",
            model_probability=0.65,
            calibrated_probability=0.65,
            fair_odds=1.54,
            bookmaker_odds=1.70,
            implied_probability=0.588,
            edge=0.062,
            expected_value=0.105,
            value_status=ValueStatus.POSITIVE_VALUE,
            reliability_score=0.75,
            uncertainty=0.30,
            data_quality=0.80,
            model_agreement=0.80,
            sample_size=60,
            calibration_status=CalibrationStatus.FITTED,
        )
        
        result = selector.select_best_tip(
            match_id="test_breakdown",
            candidates=[candidate],
        )
        
        assert not result.is_pass
        breakdown = result.best_tip.score_breakdown
        
        # Check all expected keys present in new architecture
        assert 'probability_conviction' in breakdown
        assert 'market_reliability' in breakdown  # Renamed from 'reliability'
        assert 'data_quality' in breakdown
        assert 'model_agreement' in breakdown
        assert 'edge_value' in breakdown  # Renamed from 'edge_bonus'
        assert 'ev_value' in breakdown  # Renamed from 'ev_bonus'
        assert 'calibration_validity' in breakdown  # Renamed from 'calibration_bonus'
        assert 'sample_size_bonus' in breakdown
        assert 'uncertainty_penalty' in breakdown
        assert 'no_odds_penalty' in breakdown
    
    def test_score_clamped_to_range(self):
        """Test that scores are clamped to 0-100."""
        selector = SmartMarketSelector()
        
        # Create a candidate with extreme negative penalties
        poor_candidate = MarketCandidate(
            market_type="match_result",
            market_label="Away Win",
            outcome="away",
            model_probability=0.52,  # Very low conviction
            calibrated_probability=0.52,
            fair_odds=1.92,
            bookmaker_odds=1.50,  # Poor odds
            implied_probability=0.667,
            edge=-0.147,  # Large negative edge
            expected_value=-0.22,
            value_status=ValueStatus.NEGATIVE_VALUE,
            reliability_score=0.30,  # Low reliability
            uncertainty=0.80,  # High uncertainty
            data_quality=0.40,
            model_agreement=0.40,
            sample_size=10,
            calibration_status=CalibrationStatus.NOT_FITTED,
        )
        
        result = selector.select_best_tip(
            match_id="test_clamp",
            candidates=[poor_candidate],
        )
        
        # Score should be >= 0
        assert poor_candidate.composite_score >= 0.0
        assert poor_candidate.composite_score <= 100.0


class TestConfigurableThresholds:
    """Test configurable thresholds."""
    
    def test_custom_best_tip_threshold(self):
        """Test custom best_tip_threshold."""
        config = SmartMarketSelectorConfig(
            best_tip_threshold=70.0,  # Higher threshold
        )
        selector = SmartMarketSelector(config=config)
        
        candidate = MarketCandidate(
            market_type="match_result",
            market_label="Home Win",
            outcome="home",
            model_probability=0.65,
            calibrated_probability=0.65,
            fair_odds=1.54,
            bookmaker_odds=1.70,
            implied_probability=0.588,
            edge=0.062,
            expected_value=0.105,
            value_status=ValueStatus.POSITIVE_VALUE,
            reliability_score=0.70,
            uncertainty=0.30,
            data_quality=0.75,
            model_agreement=0.75,
            sample_size=50,
            calibration_status=CalibrationStatus.FITTED,
        )
        
        result = selector.select_best_tip(
            match_id="test_custom_threshold",
            candidates=[candidate],
        )
        
        # With best_tip_threshold=70.0, score of ~61 should result in PASS
        # Score is between pass_threshold (40) and best_tip_threshold (70)
        assert result.is_pass
        assert result.pass_reason in ["LOW_COMPOSITE_SCORE", "INSUFFICIENT_CONFIDENCE"]
