"""Model-vs-market conflict guard: implausibly large edges are not value."""

from app.prediction.market_analysis import ValueClassification, classify_value
from app.services.odds_service import (
    MAX_CREDIBLE_EDGE,
    MODEL_MARKET_CONFLICT,
    MarketOdds,
    OddsAvailability,
    OddsService,
    ValueAssessment,
)


def _odds(price: float) -> MarketOdds:
    return MarketOdds(
        market="HOME_WIN", selection="Home", odds=price, odds_timestamp=None,
        provider="manual_user_supplied", availability=OddsAvailability.AVAILABLE,
    )


def test_huge_edge_is_conflict_not_value():
    # 2026-10-13 Viking-Bayern: model 31% vs odds 26.0 (implied ~3.8%)
    va = ValueAssessment.from_market_odds("HOME_WIN", 0.31, _odds(26.0))
    assert va.value_classification == MODEL_MARKET_CONFLICT
    assert va.value_score == 0.0
    assert OddsService.calculate_value_contribution(va) == 0.0
    assert classify_value(0.31, 26.0) == ValueClassification.MODEL_MARKET_CONFLICT


def test_moderate_edge_still_value():
    # model 55% vs odds 2.0 (implied 50%): 5pp edge, EV +10%
    va = ValueAssessment.from_market_odds("HOME_WIN", 0.55, _odds(2.0))
    assert va.edge < MAX_CREDIBLE_EDGE
    assert va.value_classification == "VALUE"
    assert OddsService.calculate_value_contribution(va) > 0
    assert classify_value(0.55, 2.0) in (ValueClassification.VALUE, ValueClassification.LOW_VALUE)


def test_negative_edge_unaffected():
    va = ValueAssessment.from_market_odds("HOME_WIN", 0.30, _odds(2.0))
    assert va.value_classification == "NEGATIVE_VALUE"
    assert classify_value(0.30, 2.0) == ValueClassification.NO_VALUE


# ---------------------------------------------------------------------------
# Relative criterion: longshots (2026-10-13 Viking-Bayern, manual odds)
# ---------------------------------------------------------------------------

def test_longshot_ratio_is_conflict_even_under_absolute_gap():
    # Home p=0.104 @26.0 (implied 0.0385): gap 6.6pp < 8pp, but EV +170%
    va = ValueAssessment.from_market_odds("HOME_WIN", 0.104, _odds(26.0))
    assert va.edge < MAX_CREDIBLE_EDGE
    assert va.value_classification == MODEL_MARKET_CONFLICT
    assert OddsService.calculate_value_contribution(va) == 0.0
    assert classify_value(0.104, 26.0) == ValueClassification.MODEL_MARKET_CONFLICT
    # Draw p=0.137 @12.5 (implied 0.08): EV +71%
    assert ValueAssessment.from_market_odds("DRAW", 0.137, _odds(12.5)).value_classification == MODEL_MARKET_CONFLICT
    assert classify_value(0.137, 12.5) == ValueClassification.MODEL_MARKET_CONFLICT


def test_shared_helper_thresholds():
    from app.services.odds_service import is_model_market_conflict

    assert is_model_market_conflict(0.31, 1 / 26.0)          # absolute gap
    assert is_model_market_conflict(0.104, 1 / 26.0)         # ratio 2.7
    assert not is_model_market_conflict(0.55, 0.50)          # 5pp, ratio 1.1
    assert not is_model_market_conflict(0.12, 0.10)          # ratio 1.2
    assert not is_model_market_conflict(None, 0.5)
    assert not is_model_market_conflict(0.5, None)


# ---------------------------------------------------------------------------
# API comparison rows: conflict is never flagged as value
# ---------------------------------------------------------------------------

def _quote(market: str, price: float):
    from app.services.odds_service import CanonicalOddsQuote
    return CanonicalOddsQuote(market=market, odds=price, source="manual_user_supplied",
                              bookmaker_count=None, calculated_at=None)


def test_outcome_odds_fields_conflict_has_zero_value_score():
    from app.services.odds_service import outcome_odds_fields

    fields = outcome_odds_fields(0.671, _quote("AWAY_WIN", 2.45))
    assert fields["value_classification"] == MODEL_MARKET_CONFLICT
    assert fields["value_score"] == 0.0
    # Non-conflict rows keep their score
    ok = outcome_odds_fields(0.55, _quote("HOME_WIN", 2.0))
    assert ok["value_classification"] != MODEL_MARKET_CONFLICT
    assert ok["value_score"] > 0


def test_endpoint_market_builder_never_flags_conflict_as_value():
    from app.api.v1.endpoints.matches import _build_odds_aware_market

    # 2026-10-13 Lens-Sporting model probabilities and manual odds
    market = _build_odds_aware_market(
        market_type="match_result",
        line=None,
        outcome_specs=[
            ("Home", 0.1571, "HOME_WIN"),
            ("Draw", 0.1721, "DRAW"),
            ("Away", 0.6708, "AWAY_WIN"),
        ],
        odds_quotes={
            "HOME_WIN": _quote("HOME_WIN", 2.70),
            "DRAW": _quote("DRAW", 3.55),
            "AWAY_WIN": _quote("AWAY_WIN", 2.45),
        },
    )
    away = next(c for c in market.bookmaker_comparison if c.label == "Away")
    assert away.value_classification == MODEL_MARKET_CONFLICT
    assert away.has_value_flag is False
    assert away.value_score == 0.0
    away_outcome = next(o for o in market.outcomes if o.label == "Away")
    assert away_outcome.value_score == 0.0


def test_market_analyzer_comparison_never_flags_conflict_as_value():
    from app.prediction.market_analysis import MarketAnalyser, MarketOutcome

    analyzer = MarketAnalyser()
    outcomes = [MarketOutcome("home", 0.104, None), MarketOutcome("away", 0.75, None)]
    comparison, _ = analyzer._build_comparison(outcomes, {"home": 26.0, "away": 1.2}, ["home", "away"])
    home = next(c for c in comparison if c.label == "home")
    assert home.value_classification == ValueClassification.MODEL_MARKET_CONFLICT
    assert home.has_value_flag is False
    assert home.value_score == 0.0


# ---------------------------------------------------------------------------
# Selector: conflicts propagate through correlated market families
# ---------------------------------------------------------------------------

def _lens_sporting_inputs():
    from app.prediction.market_derivation import MarketProbabilities
    from tests.test_market_selector_value_aware import make_confidence

    # 2026-10-13 Lens-Sporting (fotmob_6106414): model output and manual odds
    home, draw, away = 0.1571, 0.1721, 0.6708
    probs = MarketProbabilities(
        home_win=home, draw=draw, away_win=away,
        home_or_draw=home + draw, draw_or_away=draw + away, home_or_away=home + away,
        over_under={2.5: (0.7466, 0.2534), 3.5: (0.5529, 0.4471)},
        btts_yes=0.6642, btts_no=0.3358,
        home_team_over={}, away_team_over={},
    )
    odds = {
        "HOME_WIN": 2.70, "DRAW": 3.55, "AWAY_WIN": 2.45,
        "HOME_OR_DRAW": 1.52, "HOME_OR_AWAY": 1.30, "DRAW_OR_AWAY": 1.45,
        "OVER_2_5": 1.60, "UNDER_2_5": 2.30, "OVER_3_5": 2.55, "UNDER_3_5": 1.48,
        "BTTS_YES": 1.48, "BTTS_NO": 2.45,
    }
    return probs, odds, make_confidence(overall=0.64, agreement=0.72, quality=0.93)


def test_double_chance_on_conflicting_1x2_is_not_selected():
    from app.prediction.market_selector import SmartMarketSelector, BestTip

    probs, odds, confidence = _lens_sporting_inputs()
    selector = SmartMarketSelector()
    candidates = selector._build_candidates(probs, 0.64, 0.72, 0.93, odds)
    by_market = {c["market"]: c for c in candidates}
    # HOME_OR_AWAY = HOME_WIN + AWAY_WIN rests on the conflicting AWAY_WIN
    assert by_market["AWAY_WIN"]["value_classification"] == MODEL_MARKET_CONFLICT
    assert by_market["HOME_OR_AWAY"]["value_classification"] == MODEL_MARKET_CONFLICT
    assert by_market["HOME_OR_AWAY"].get("family_conflict") is True
    # Goals family: OVER_2_5 and OVER_3_5 are conflicts, so BTTS is marked too
    assert by_market["BTTS_YES"]["value_classification"] == MODEL_MARKET_CONFLICT

    # Both families are conflicted and there are no shot markets: PASS.
    result = selector.evaluate_and_select(probs, confidence, odds_data=odds, match_id="fotmob_6106414")
    assert not isinstance(result, BestTip)
    assert result.pass_reason == "model_market_conflict"


def test_family_propagation_leaves_unrelated_families_alone():
    from app.prediction.market_selector import propagate_family_conflicts

    candidates = [
        {"market": "AWAY_WIN", "value_classification": MODEL_MARKET_CONFLICT},
        {"market": "HOME_OR_DRAW", "value_classification": "NEGATIVE_VALUE"},
        {"market": "OVER_2_5", "value_classification": "VALUE"},
        {"market": "HOME_SHOTS_OVER_10_5", "value_classification": "NO_ODDS"},
    ]
    propagate_family_conflicts(candidates)
    assert candidates[1]["value_classification"] == MODEL_MARKET_CONFLICT
    assert candidates[2]["value_classification"] == "VALUE"
    assert candidates[3]["value_classification"] == "NO_ODDS"
