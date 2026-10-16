"""Banko / Oranlı rule: parity with the frontend implementation.

The candidate and response fixtures are TEST FIXTURES (made-up probabilities) shared with the
frontend test (frontend/src/utils/__tests__/headlinePicks.test.ts): both implementations must give
exactly the picks written in frontend/src/utils/__tests__/headlinePicks.fixtures.json.
"""

import json
from pathlib import Path

import pytest

from app.prediction.headline_picks import (
    BANKO_MAX_P,
    BANKO_MIN_P,
    KNOWN_RULE_VERSIONS,
    ODDS_MIN_P,
    ODDS_MIN_PRICE,
    RULE_VERSION,
    TIER_BANKO_MIN_P,
    TIER_COK_GUCLU_MIN_P,
    PickCandidate,
    banko_tier,
    candidates_from_prediction,
    headline_picks_from_prediction,
    landed,
    pick_family,
    select_headline_picks,
    short_label,
)

FIXTURES_PATH = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "utils" / "__tests__" / "headlinePicks.fixtures.json"
)
FIXTURES = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))


def _candidate(spec: dict) -> PickCandidate:
    p = spec["probability"]
    odds = spec.get("odds")
    return PickCandidate(
        key=spec["key"],
        market_name=f"Mock {spec['key']}",
        outcome=spec["key"],
        probability=p,
        fair_odds=1 / p,
        odds=odds if isinstance(odds, (int, float)) and odds > 1 else None,
        odds_source=None,
        banko_eligible=spec.get("bankoEligible", True),
        source="match",
    )


def test_constants_match_the_frontend_rule():
    ts = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "utils" / "headlinePicks.ts").read_text(
        encoding="utf-8"
    )
    assert "RULE_VERSION = 'headline_v2';" in ts and RULE_VERSION == "headline_v2"
    assert "PREVIOUS_RULE_VERSION = 'headline_v1';" in ts and KNOWN_RULE_VERSIONS == ("headline_v1", "headline_v2")
    assert "BANKO_MIN_P = 0.7;" in ts and BANKO_MIN_P == 0.7
    assert "BANKO_MAX_P = 0.95;" in ts and BANKO_MAX_P == 0.95
    assert "TIER_BANKO_MIN_P = 0.85;" in ts and TIER_BANKO_MIN_P == 0.85
    assert "TIER_COK_GUCLU_MIN_P = 0.9;" in ts and TIER_COK_GUCLU_MIN_P == 0.9
    assert "ODDS_MIN_PRICE = 1.6;" in ts and ODDS_MIN_PRICE == 1.6
    assert "ODDS_MIN_P = 0.55;" in ts and ODDS_MIN_P == 0.55


@pytest.mark.parametrize("case", FIXTURES["candidate_cases"], ids=lambda c: c["name"])
def test_candidate_cases_match_the_frontend(case):
    picks = select_headline_picks([_candidate(c) for c in case["candidates"]])
    assert (picks.banko.key if picks.banko else None) == case["expected"]["banko"]
    assert (picks.oranli.key if picks.oranli else None) == case["expected"]["oranli"]
    assert picks.banko_tier == case["expected"]["banko_tier"]


@pytest.mark.parametrize("case", FIXTURES["response_cases"], ids=lambda c: c["name"])
def test_response_cases_match_the_frontend(case):
    teams = case["teams"]
    candidates = candidates_from_prediction(case["prediction"], teams["home"], teams["away"])
    assert [c.key for c in candidates] == case["expected_candidate_keys"]

    picks = select_headline_picks(candidates)
    assert picks.banko_tier == case["expected"]["banko_tier"]
    for kind in ("banko", "oranli"):
        expected = case["expected"][kind]
        actual = getattr(picks, kind)
        if expected is None:
            assert actual is None, kind
            continue
        assert actual is not None, kind
        assert actual.key == expected["key"]
        assert actual.outcome == expected["outcome"]
        assert actual.market_name == expected["market"]
        assert actual.odds == expected["odds"]


def test_pydantic_prediction_response_gives_the_same_picks():
    """The tracker works on MatchPredictionResponse objects, not only on dicts."""
    from app.api.v1.schemas import MatchPredictionResponse

    case = FIXTURES["response_cases"][0]
    body = dict(case["prediction"])
    body.update(match_id="fixture", home_xg=1.0, away_xg=1.0, is_development_data=False)
    # the schema requires every outcome field the fixture does not carry
    for market in body["market_analysis"]:
        for o in market["outcomes"]:
            o.setdefault("fair_odds", 2.0)
    response = MatchPredictionResponse(**body)
    from_object = headline_picks_from_prediction(response, "Home FC", "Away FC")
    from_dict = headline_picks_from_prediction(response.model_dump(), "Home FC", "Away FC")
    assert from_object.banko.key == from_dict.banko.key == case["expected"]["banko"]["key"]
    assert from_object.oranli.key == from_dict.oranli.key == case["expected"]["oranli"]["key"]


@pytest.mark.parametrize(
    "p,tier",
    [
        (0.7, "guclu"), (0.8499, "guclu"), (0.85, "banko"), (0.8999, "banko"), (0.9, "cok_guclu"),
        (0.95, "cok_guclu"), (0.6999, None), (0.951, None), (None, None), (float("nan"), None), (True, None),
    ],
)
def test_banko_tier_bounds(p, tier):
    assert banko_tier(p) == tier


def test_every_fixture_banko_carries_its_tier():
    """The tier always follows from the banko probability (also for frozen records, see report.py)."""
    for case in FIXTURES["candidate_cases"]:
        picks = select_headline_picks([_candidate(c) for c in case["candidates"]])
        assert picks.banko_tier == (banko_tier(picks.banko.probability) if picks.banko else None)


def test_families():
    for key in ("HOME_WIN", "DRAW", "AWAY_WIN", "HOME_OR_DRAW", "HOME_OR_AWAY", "DRAW_OR_AWAY"):
        assert pick_family(key) == "result"
    for key in ("OVER_1_5", "UNDER_3_5", "BTTS_YES", "BTTS_NO"):
        assert pick_family(key) == "goals"
    assert pick_family("total_yellow_cards:total:3.5:Üst") == "total_yellow_cards"
    assert pick_family("OVER_2_5\n") == "OVER_2_5\n"  # no regex end-of-line leniency (fullmatch)


def test_short_labels_follow_the_score_picks_script():
    assert short_label("HOME_WIN") == "MS 1"
    assert short_label("HOME_OR_DRAW") == "1X"
    assert short_label("HOME_OR_AWAY") == "12"
    assert short_label("OVER_2_5") == "2.5 Üst"
    assert short_label("UNDER_3_5") == "3.5 Alt"
    assert short_label("BTTS_YES") == "KG Var"


@pytest.mark.parametrize(
    "key,h,a,expected",
    [
        ("HOME_WIN", 2, 1, True), ("HOME_WIN", 1, 1, False),
        ("DRAW", 1, 1, True), ("DRAW", 2, 1, False),
        ("AWAY_WIN", 0, 1, True), ("AWAY_WIN", 1, 1, False),
        ("HOME_OR_DRAW", 1, 1, True), ("HOME_OR_DRAW", 0, 1, False),
        ("DRAW_OR_AWAY", 1, 1, True), ("DRAW_OR_AWAY", 2, 1, False),
        ("HOME_OR_AWAY", 2, 1, True), ("HOME_OR_AWAY", 0, 0, False),
        ("BTTS_YES", 1, 1, True), ("BTTS_YES", 2, 0, False),
        ("BTTS_NO", 2, 0, True), ("BTTS_NO", 1, 1, False),
        ("OVER_1_5", 1, 1, True), ("OVER_1_5", 1, 0, False),
        ("OVER_2_5", 2, 1, True), ("OVER_2_5", 1, 1, False),
        ("UNDER_2_5", 1, 1, True), ("UNDER_2_5", 2, 1, False),
        ("UNDER_3_5", 2, 1, True), ("UNDER_3_5", 2, 2, False),
        ("OVER_3_5", 2, 2, True), ("OVER_3_5", 2, 1, False),
    ],
)
def test_landed(key, h, a, expected):
    assert landed(key, h, a) is expected


def test_landed_rejects_unknown_keys():
    with pytest.raises(ValueError):
        landed("CORNERS_OVER_9_5", 1, 1)


def test_landed_reproduces_the_hand_scored_night_of_2026_10_14():
    """Final scores and the hand scoring of docs/live-tests/2026-10-14/results.md (system picks)."""
    night = [
        ("HOME_OR_DRAW", "OVER_2_5", 6, 0, True, True),   # Aston Villa - Fenerbahce
        ("HOME_OR_DRAW", "OVER_2_5", 2, 4, False, True),  # Man City - PSG
        ("OVER_1_5", "HOME_OR_DRAW", 1, 0, False, True),  # Bodo/Glimt - Dortmund
        ("OVER_1_5", "HOME_OR_DRAW", 3, 4, True, False),  # Roma - Real Madrid
        ("HOME_OR_AWAY", "BTTS_YES", 3, 2, True, True),   # Real Betis - Porto
        ("OVER_1_5", "HOME_OR_DRAW", 3, 1, True, True),   # Shakhtar - AEK
        ("DRAW_OR_AWAY", "OVER_3_5", 0, 3, True, False),  # Slovan Bratislava - Stuttgart
    ]
    banko_hits = oranli_hits = 0
    for banko, oranli, h, a, banko_ok, oranli_ok in night:
        assert landed(banko, h, a) is banko_ok
        assert landed(oranli, h, a) is oranli_ok
        banko_hits += landed(banko, h, a)
        oranli_hits += landed(oranli, h, a)
    assert (banko_hits, oranli_hits) == (5, 5)
