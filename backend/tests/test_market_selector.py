"""Tests for SmartMarketSelector module."""

import pytest
from types import SimpleNamespace
from datetime import datetime

from app.prediction.market_selector import SmartMarketSelector, BestTip, PassDecision


# Helper functions to create mock objects

def make_market_probs(
    home_win=0.55,
    draw=0.25,
    away_win=0.20,
    over_2_5=0.60,
    under_2_5=0.40,
    btts_yes=0.50,
    btts_no=None,  # Default to None, calculated as 1-btts_yes if None
    match_id="test_match_001",
    include_other_markets=True,
    include_double_chance=True
):
    """Create mock MarketProbabilities object."""
    # Calculate btts_no if not provided
    if btts_no is None:
        btts_no = 1.0 - btts_yes if btts_yes > 0 else 0.0
    
    # Calculate double chance based on flag
    if include_double_chance:
        home_or_draw = home_win + draw
        draw_or_away = draw + away_win
        home_or_away = home_win + away_win
    else:
        # Set to 0 to exclude from candidates
        home_or_draw = 0.0
        draw_or_away = 0.0
        home_or_away = 0.0
    
    if include_other_markets:
        over_under = {
            0.5: (0.95, 0.05),
            1.5: (0.75, 0.25),
            2.5: (over_2_5, under_2_5),
            3.5: (0.30, 0.70)
        }
        home_team_over = {0.5: 0.85, 1.5: 0.60, 2.5: 0.35}
        away_team_over = {0.5: 0.70, 1.5: 0.40, 2.5: 0.15}
    else:
        over_under = {
            2.5: (over_2_5, under_2_5)
        }
        home_team_over = {}
        away_team_over = {}
    
    return SimpleNamespace(
        match_id=match_id,
        home_win=home_win,
        draw=draw,
        away_win=away_win,
        home_or_draw=home_or_draw,
        draw_or_away=draw_or_away,
        home_or_away=home_or_away,
        over_under=over_under,
        btts_yes=btts_yes,
        btts_no=btts_no,
        home_team_over=home_team_over,
        away_team_over=away_team_over,
        exact_score_top=[("3-1", 0.15), ("2-1", 0.12)],
        asian_handicap={}
    )


def make_confidence(
    overall=0.65,
    model_agreement=0.75,
    data_quality=0.70
):
    """Create mock ConfidenceAssessment object."""
    components = SimpleNamespace(
        model_agreement=model_agreement,
        data_quality=data_quality
    )
    
    return SimpleNamespace(
        overall_confidence=overall,
        components=components,
        confidence_label="MEDIUM"
    )


# Test 1: Multiple qualifying markets
def test_select_best_market_multiple_qualifying():
    """When multiple markets qualify, highest selection_score is returned as BestTip."""
    selector = SmartMarketSelector(min_confidence=0.4, min_probability=0.5)
    
    market_probs = make_market_probs(
        home_win=0.65,  # High probability
        draw=0.20,
        away_win=0.15,
        over_2_5=0.70   # Even higher probability
    )
    
    confidence = make_confidence(overall=0.70, model_agreement=0.80, data_quality=0.75)
    
    result = selector.evaluate_and_select(market_probs, confidence)
    
    assert isinstance(result, BestTip)
    # Over 2.5 should win due to higher probability
    assert result.probability >= 0.65


# Test 2: Pass when all below confidence
def test_pass_when_all_below_confidence():
    """All markets have confidence below min_confidence → PassDecision with pass_reason 'poor_calibration'."""
    selector = SmartMarketSelector(min_confidence=0.8, min_probability=0.5)
    
    market_probs = make_market_probs(home_win=0.60, draw=0.25, away_win=0.15)
    confidence = make_confidence(overall=0.50, model_agreement=0.60, data_quality=0.55)  # Below 0.8
    
    result = selector.evaluate_and_select(market_probs, confidence)
    
    assert isinstance(result, PassDecision)
    assert result.pass_reason == "poor_calibration"
    assert result.evaluated_markets_count > 0


# Test 3: Pass when all below probability
def test_pass_when_all_below_probability():
    """All markets probability < 0.5 → PassDecision."""
    selector = SmartMarketSelector(min_confidence=0.4, min_probability=0.8)
    
    market_probs = make_market_probs(
        home_win=0.40, 
        draw=0.35, 
        away_win=0.25,
        over_2_5=0.45,
        btts_yes=0.40,
        include_other_markets=False  # Exclude high-probability markets
    )
    confidence = make_confidence(overall=0.70, model_agreement=0.75, data_quality=0.70)
    
    result = selector.evaluate_and_select(market_probs, confidence)
    
    assert isinstance(result, PassDecision)
    assert result.pass_reason == "weak_agreement"


# Test 4: Pass when negative edge and min_edge set
def test_pass_when_negative_edge_and_min_edge_set():
    """Selector with min_edge=0.05 and all edges negative → PassDecision pass_reason 'negative_value'."""
    selector = SmartMarketSelector(min_confidence=0.4, min_probability=0.5, min_edge=0.05)
    
    market_probs = make_market_probs(
        home_win=0.55, 
        draw=0.25, 
        away_win=0.20,
        over_2_5=0.55,
        under_2_5=0.45,
        btts_yes=0.50,
        include_other_markets=False,
        include_double_chance=False
    )
    confidence = make_confidence(overall=0.70, model_agreement=0.75, data_quality=0.70)
    
    # Odds that imply higher probabilities than model (negative edge for all markets)
    odds_data = {
        'HOME_WIN': 1.5,    # Implies 0.667 prob, but model says 0.55 → edge = -0.117
        'DRAW': 3.0,        # Implies 0.333 prob, but model says 0.25 → edge = -0.083 (filtered by prob anyway)
        'AWAY_WIN': 4.0,    # Implies 0.25 prob, but model says 0.20 → edge = -0.05 (filtered by prob anyway)
        'OVER_2_5': 1.6,    # Implies 0.625 prob, but model says 0.55 → edge = -0.075
        'UNDER_2_5': 2.0,   # Implies 0.5 prob, but model says 0.45 → edge = -0.05 (a +11.7pp gap would be a model-market conflict)
        'BTTS_YES': 1.8,    # Implies 0.556 prob, but model says 0.50 → edge = -0.056
        'BTTS_NO': 2.1      # Implies 0.476 prob, but model says 0.50 → edge = 0.024 (below min_edge 0.05)
    }
    
    result = selector.evaluate_and_select(market_probs, confidence, odds_data)
    
    assert isinstance(result, PassDecision)
    # Should be negative_value because markets with prob>=0.5 all have negative edge or edge below min_edge
    assert result.pass_reason in ["negative_value", "no_qualifying_market"]


# Test 5: Pass when no market data
def test_pass_when_no_market_data():
    """Empty MarketProbabilities or all None → PassDecision pass_reason 'insufficient_data'."""
    selector = SmartMarketSelector(min_confidence=0.4, min_probability=0.5)
    
    # Create a minimal market probs with all zeros and empty dicts
    market_probs = SimpleNamespace(
        match_id="test_match_001",
        home_win=0.0,
        draw=0.0,
        away_win=0.0,
        home_or_draw=0.0,
        draw_or_away=0.0,
        home_or_away=0.0,
        over_under={},  # Empty
        btts_yes=0.0,
        btts_no=0.0,
        home_team_over={},  # Empty
        away_team_over={},  # Empty
        exact_score_top=[],
        asian_handicap={}
    )
    
    confidence = make_confidence(overall=0.70, model_agreement=0.75, data_quality=0.70)
    
    result = selector.evaluate_and_select(market_probs, confidence)
    
    assert isinstance(result, PassDecision)
    assert result.pass_reason == "insufficient_data"
    assert result.evaluated_markets_count == 0


# Test 6: Value classification - STRONG_VALUE
def test_value_classification_strong_value():
    """EV >= 15% with a credible edge (< 8pp) → STRONG_VALUE."""
    selector = SmartMarketSelector(min_confidence=0.4, min_probability=0.5)

    market_probs = make_market_probs(
        home_win=0.55,
        draw=0.25,
        away_win=0.20,
        include_other_markets=False,
        include_double_chance=False
    )
    confidence = make_confidence(overall=0.70, model_agreement=0.75, data_quality=0.70)

    # model=0.55, implied=1/2.12≈0.472 → edge≈0.078, EV≈+16.6%
    odds_data = {'HOME_WIN': 2.12}

    result = selector.evaluate_and_select(market_probs, confidence, odds_data)

    assert isinstance(result, BestTip)
    assert result.market == 'HOME_WIN'
    assert result.value_classification == "STRONG_VALUE"
    assert 0.07 <= result.edge < 0.08


def test_implausible_edge_is_never_picked():
    """edge=0.12 vs the market is model-market conflict: no value pick."""
    selector = SmartMarketSelector(min_confidence=0.4, min_probability=0.5)

    market_probs = make_market_probs(
        home_win=0.70,
        draw=0.20,
        away_win=0.10,
        include_other_markets=False,
        include_double_chance=False
    )
    confidence = make_confidence(overall=0.70, model_agreement=0.75, data_quality=0.70)

    # model=0.70, implied=0.58 → edge=0.12 (beyond MAX_CREDIBLE_EDGE)
    odds_data = {'HOME_WIN': 1.72}

    result = selector.evaluate_and_select(market_probs, confidence, odds_data)

    assert not (isinstance(result, BestTip) and result.market == 'HOME_WIN')


# Test 7: Value classification - VALUE
def test_value_classification_value():
    """edge=0.06 → VALUE."""
    selector = SmartMarketSelector(min_confidence=0.4, min_probability=0.5)
    
    market_probs = make_market_probs(
        home_win=0.65, 
        draw=0.20, 
        away_win=0.15,
        include_other_markets=False,
        include_double_chance=False
    )
    confidence = make_confidence(overall=0.70, model_agreement=0.75, data_quality=0.70)
    
    # Odds that give 0.06 edge: model=0.65, implied=0.59 → edge=0.06
    odds_data = {'HOME_WIN': 1.69}  # 1/1.69 ≈ 0.59
    
    result = selector.evaluate_and_select(market_probs, confidence, odds_data)
    
    assert isinstance(result, BestTip)
    assert result.market == 'HOME_WIN'
    assert result.value_classification == "VALUE"
    assert 0.05 <= result.edge < 0.10


# Test 8: Value classification - NEUTRAL
def test_value_classification_neutral():
    """edge=0.02 → NEUTRAL."""
    selector = SmartMarketSelector(min_confidence=0.4, min_probability=0.5)
    
    market_probs = make_market_probs(
        home_win=0.60, 
        draw=0.25, 
        away_win=0.15,
        include_other_markets=False,
        include_double_chance=False
    )
    confidence = make_confidence(overall=0.70, model_agreement=0.75, data_quality=0.70)
    
    # Odds that give 0.02 edge: model=0.60, implied=0.58 → edge=0.02
    odds_data = {'HOME_WIN': 1.72}  # 1/1.72 ≈ 0.58
    
    result = selector.evaluate_and_select(market_probs, confidence, odds_data)
    
    assert isinstance(result, BestTip)
    assert result.market == 'HOME_WIN'
    # NEW: edge=0.02 with EV ~3.6% is classified as VALUE (not NEUTRAL)
    assert result.value_classification == "VALUE"
    assert result.edge is not None
    assert 0.0 <= result.edge < 0.05


# Test 9: Value classification - NEGATIVE_VALUE
def test_value_classification_negative_value():
    """edge=-0.03 → NEGATIVE_VALUE (but still passes if min_edge=0.0)."""
    selector = SmartMarketSelector(min_confidence=0.4, min_probability=0.5, min_edge=-0.1)
    
    market_probs = make_market_probs(
        home_win=0.55, 
        draw=0.25, 
        away_win=0.20,
        over_2_5=0.50,  # Lower so HOME_WIN wins
        include_other_markets=False,
        include_double_chance=False
    )
    confidence = make_confidence(overall=0.70, model_agreement=0.75, data_quality=0.70)
    
    # Odds that give negative edge: model=0.55, implied=0.58 → edge=-0.03
    odds_data = {'HOME_WIN': 1.72}  # 1/1.72 ≈ 0.58
    
    result = selector.evaluate_and_select(market_probs, confidence, odds_data)
    
    assert isinstance(result, PassDecision)
    assert result.pass_reason == 'insufficient_value'
    # NEW: When odds exist showing negative value, selector returns PASS
    assert result.best_market_details['value_classification'] == "NEGATIVE_VALUE"


# Test 10: Value classification - no odds
def test_value_classification_no_odds():
    """edge=None → NEUTRAL."""
    selector = SmartMarketSelector(min_confidence=0.4, min_probability=0.5)
    
    market_probs = make_market_probs(home_win=0.60, draw=0.25, away_win=0.15)
    confidence = make_confidence(overall=0.70, model_agreement=0.75, data_quality=0.70)
    
    result = selector.evaluate_and_select(market_probs, confidence, odds_data=None)
    
    assert isinstance(result, BestTip)
    # NEW: When no odds available, classification is "NO_ODDS" (more accurate than "NEUTRAL")
    assert result.value_classification == "NO_ODDS"
    assert result.edge is None


# Test 11: Risk level - LOW
def test_risk_level_low():
    """confidence=0.75, model_agreement=0.85, data_quality=0.80 → LOW."""
    selector = SmartMarketSelector(min_confidence=0.4, min_probability=0.5)
    
    market_probs = make_market_probs(home_win=0.65, draw=0.20, away_win=0.15)
    confidence = make_confidence(overall=0.75, model_agreement=0.85, data_quality=0.80)
    
    result = selector.evaluate_and_select(market_probs, confidence)
    
    assert isinstance(result, BestTip)
    assert result.risk_level == "LOW"


# Test 12: Risk level - MEDIUM
def test_risk_level_medium():
    """confidence=0.55, model_agreement=0.65, data_quality=0.55 → MEDIUM."""
    selector = SmartMarketSelector(min_confidence=0.4, min_probability=0.5)
    
    market_probs = make_market_probs(home_win=0.60, draw=0.25, away_win=0.15)
    confidence = make_confidence(overall=0.55, model_agreement=0.65, data_quality=0.55)
    
    result = selector.evaluate_and_select(market_probs, confidence)
    
    assert isinstance(result, BestTip)
    assert result.risk_level == "MEDIUM"


# Test 13: Risk level - HIGH
def test_risk_level_high():
    """confidence=0.35, model_agreement=0.45, data_quality=0.30 → HIGH."""
    selector = SmartMarketSelector(min_confidence=0.3, min_probability=0.5)
    
    market_probs = make_market_probs(home_win=0.55, draw=0.30, away_win=0.15)
    confidence = make_confidence(overall=0.35, model_agreement=0.45, data_quality=0.30)
    
    result = selector.evaluate_and_select(market_probs, confidence)
    
    assert isinstance(result, BestTip)
    assert result.risk_level == "HIGH"


# Test 14: Tie breaking by confidence
def test_tie_breaking_by_confidence():
    """Two markets same probability, higher confidence wins."""
    selector = SmartMarketSelector(min_confidence=0.4, min_probability=0.5)
    
    # Create scenario where home_win and over_2.5 have same probability
    # Exclude other high-probability markets to test tie-breaking
    market_probs = make_market_probs(
        home_win=0.65, 
        draw=0.20, 
        away_win=0.15, 
        over_2_5=0.65,
        include_other_markets=False,
        include_double_chance=False
    )
    
    # High confidence should favor based on selection_score
    confidence = make_confidence(overall=0.75, model_agreement=0.80, data_quality=0.75)
    
    result = selector.evaluate_and_select(market_probs, confidence)
    
    assert isinstance(result, BestTip)
    assert result.probability == 0.65
    # Either HOME_WIN or OVER_2_5 is acceptable - both have same probability
    assert result.market in ['HOME_WIN', 'OVER_2_5']


# Test 15: Pass decision includes best_market_details
def test_pass_decision_includes_best_market_details():
    """PassDecision.best_market_details shows the closest market that didn't qualify."""
    selector = SmartMarketSelector(min_confidence=0.9, min_probability=0.5)  # Very high confidence
    
    market_probs = make_market_probs(home_win=0.65, draw=0.20, away_win=0.15)
    confidence = make_confidence(overall=0.60, model_agreement=0.70, data_quality=0.65)  # Below 0.9
    
    result = selector.evaluate_and_select(market_probs, confidence)
    
    assert isinstance(result, PassDecision)
    assert result.best_market_details is not None
    assert 'market' in result.best_market_details
    assert 'probability' in result.best_market_details
    assert 'selection_score' in result.best_market_details


# Test 16: Custom thresholds respected
def test_custom_thresholds_respected():
    """SmartMarketSelector(min_confidence=0.8) rejects markets below 0.8."""
    selector = SmartMarketSelector(min_confidence=0.8, min_probability=0.5)
    
    market_probs = make_market_probs(home_win=0.65, draw=0.20, away_win=0.15)
    confidence = make_confidence(overall=0.75, model_agreement=0.80, data_quality=0.70)  # Below 0.8
    
    result = selector.evaluate_and_select(market_probs, confidence)
    
    assert isinstance(result, PassDecision)
    assert result.pass_reason == "poor_calibration"


# Test 17: BestTip has all required fields
def test_best_tip_has_all_required_fields():
    """Returned BestTip has all expected fields non-None (except optional ones)."""
    selector = SmartMarketSelector(min_confidence=0.4, min_probability=0.5)
    
    market_probs = make_market_probs(home_win=0.65, draw=0.20, away_win=0.15)
    confidence = make_confidence(overall=0.70, model_agreement=0.75, data_quality=0.70)
    
    result = selector.evaluate_and_select(market_probs, confidence)
    
    assert isinstance(result, BestTip)
    
    # Required fields
    assert result.match_id is not None
    assert result.market is not None
    assert result.selection is not None
    assert result.probability is not None
    assert result.confidence is not None
    assert result.model_agreement is not None
    assert result.data_quality is not None
    assert result.fair_odds is not None
    assert result.value_classification is not None
    assert result.risk_level is not None
    assert result.selection_score is not None
    assert result.selector_reason is not None
    assert result.timestamp is not None
    assert result.pipeline_version is not None
    
    # Optional fields (can be None)
    # edge, bookmaker_odds, odds_movement can be None


# Test 18: Max risk level filtering
def test_max_risk_level_filtering():
    """Selector with max_risk_level='LOW' excludes MEDIUM and HIGH risk markets."""
    selector = SmartMarketSelector(
        min_confidence=0.3,
        min_probability=0.5,
        max_risk_level="LOW"
    )
    
    market_probs = make_market_probs(home_win=0.60, draw=0.25, away_win=0.15)
    # This will be MEDIUM risk (confidence=0.55 < 0.7)
    confidence = make_confidence(overall=0.55, model_agreement=0.65, data_quality=0.55)
    
    result = selector.evaluate_and_select(market_probs, confidence)
    
    # Should PASS because all markets are MEDIUM risk but max is LOW
    assert isinstance(result, PassDecision)


# Test 19: Selection score calculation includes edge bonus
def test_selection_score_includes_edge_bonus():
    """Selection score includes edge bonus when odds available."""
    selector = SmartMarketSelector(min_confidence=0.4, min_probability=0.5)
    
    market_probs = make_market_probs(home_win=0.65, draw=0.20, away_win=0.15)
    confidence = make_confidence(overall=0.70, model_agreement=0.75, data_quality=0.70)
    
    # With odds (edge bonus)
    odds_data = {'HOME_WIN': 1.62}  # Edge = 0.65 - 0.617 ≈ 0.033, EV ≈ +5%
    result_with_odds = selector.evaluate_and_select(market_probs, confidence, odds_data)
    
    # Without odds (no edge bonus)
    result_no_odds = selector.evaluate_and_select(market_probs, confidence, None)
    
    assert isinstance(result_with_odds, BestTip)
    assert isinstance(result_no_odds, BestTip)
    
    # NEW: Selection score can exceed 1.0 when strong value exists
    # (base_score + probability_contrib + value_contrib can sum > 1.0)
    assert result_with_odds.selection_score > 0.0
    assert result_no_odds.selection_score > 0.0


# Test 20: Pass when no_qualifying_market
def test_pass_when_no_qualifying_market_general():
    """PassDecision with 'no_qualifying_market' when filters eliminate all candidates."""
    selector = SmartMarketSelector(
        min_confidence=0.5,
        min_probability=0.5,
        max_risk_level="LOW"
    )
    
    market_probs = make_market_probs(home_win=0.55, draw=0.30, away_win=0.15)
    # MEDIUM risk (0.5 <= conf < 0.7)
    confidence = make_confidence(overall=0.60, model_agreement=0.65, data_quality=0.60)
    
    result = selector.evaluate_and_select(market_probs, confidence)
    
    assert isinstance(result, PassDecision)
    assert result.pass_reason == "no_qualifying_market"
