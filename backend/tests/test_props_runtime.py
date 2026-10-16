"""Props (cards / corners / shots) runtime.

The config below is a SYNTHETIC TEST FIXTURE: made-up coefficients for made-up
team ids, never shown to users.
"""

import json
import math

import pytest
from scipy.stats import nbinom

from app.prediction.props_model import _parse, get_props_model

FIXTURE = {
    "version": "props_test_fixture",
    "trained_through": "2026-10-12T00:00:00Z",
    "stats": {
        "corners": {
            "distribution": "negbin", "dispersion": 12.0, "intercept": math.log(4.5), "home_advantage": 0.1,
            "competitions": {"42": 0.05},
            "teams": {"1": {"attack": 0.2, "concede": -0.1, "matches": 40}, "2": {"attack": -0.1, "concede": 0.15, "matches": 38}},
            "referees": {},
        },
        "yellow_cards": {
            "distribution": "negbin", "dispersion": 20.0, "intercept": math.log(2.0), "home_advantage": -0.05,
            "competitions": {},
            "teams": {"1": {"attack": 0.0, "concede": 0.0, "matches": 40}, "2": {"attack": 0.1, "concede": 0.0, "matches": 38}},
            "referees": {"Strict Ref (synthetic)": {"offset": 0.3, "matches": 25}},
        },
    },
    "lines": {"team_corners": [4.5], "total_corners": [9.5], "team_yellow_cards": [1.5], "total_yellow_cards": [3.5]},
    "team_recent": {"1": {"corners": {"for_last5": 6.2, "against_last5": 3.8, "n": 5}}},
}


def _model():
    return _parse(json.loads(json.dumps(FIXTURE)))


def _by_key(markets, key, scope):
    return next(m for m in markets if m["key"] == key and m["scope"] == scope)


def test_expected_counts_follow_the_formula():
    out = _model().predict("1", "2", "42", None, {"home": "Home", "away": "Away"})
    c = FIXTURE["stats"]["corners"]
    mu_h = math.exp(c["intercept"] + 0.05 + 0.1 + 0.2 + 0.15)
    mu_a = math.exp(c["intercept"] + 0.05 + -0.1 + -0.1)
    home = _by_key(out["markets"], "team_corners", "home")
    away = _by_key(out["markets"], "team_corners", "away")
    total = _by_key(out["markets"], "total_corners", "total")
    assert home["expected"] == pytest.approx(mu_h)
    assert away["expected"] == pytest.approx(mu_a)
    assert total["expected"] == pytest.approx(mu_h + mu_a)
    assert home["label_tr"] == "Home korner"


def test_over_probability_matches_negative_binomial():
    out = _model().predict("1", "2", "42", None, {"home": "Home", "away": "Away"})
    home = _by_key(out["markets"], "team_corners", "home")
    r, mu = 12.0, home["expected"]
    expected_over = 1 - nbinom.cdf(4, r, r / (r + mu))
    line = home["lines"][0]
    assert line["line"] == 4.5
    assert line["over"] == pytest.approx(expected_over, abs=1e-9)
    assert line["over"] + line["under"] == pytest.approx(1.0)


def test_total_is_convolution_of_both_sides():
    out = _model().predict("1", "2", "42", None, {"home": "Home", "away": "Away"})
    total = _by_key(out["markets"], "total_corners", "total")["lines"][0]
    r = 12.0
    mu_h = _by_key(out["markets"], "team_corners", "home")["expected"]
    mu_a = _by_key(out["markets"], "team_corners", "away")["expected"]
    under = sum(
        nbinom.pmf(i, r, r / (r + mu_h)) * nbinom.pmf(j, r, r / (r + mu_a)) for i in range(10) for j in range(10) if i + j <= 9
    )
    assert total["under"] == pytest.approx(under, abs=1e-9)


def test_referee_offset_raises_cards_and_unknown_team_is_flagged():
    m = _model()
    base = m.predict("1", "2", None, None, {"home": "H", "away": "A"})
    strict = m.predict("1", "2", None, "Strict Ref (synthetic)", {"home": "H", "away": "A"})
    b = _by_key(base["markets"], "total_yellow_cards", "total")["expected"]
    s = _by_key(strict["markets"], "total_yellow_cards", "total")["expected"]
    assert s == pytest.approx(b * math.exp(0.3))
    assert strict["referee_used"] is True and base["referee_used"] is False
    unknown = m.predict("1", "999", None, None, {"home": "H", "away": "A"})
    assert unknown["unknown_teams"] == ["999"]


def test_missing_config_disables_the_feature(tmp_path):
    assert get_props_model(tmp_path / "absent.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert get_props_model(bad) is None
    good = tmp_path / "good.json"
    good.write_text(json.dumps(FIXTURE), encoding="utf-8")
    assert get_props_model(good).version == "props_test_fixture"
