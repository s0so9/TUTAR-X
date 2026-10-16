"""Unit tests for scripts/data_collection/odds_common.py (odds validation, de-vig, mapping, FotMob GET, output).

All fixtures in this file are SYNTHETIC TEST DATA (invented prices and team lists written for the tests). They are
not football data and are never written to any dataset.
"""

import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "data_collection"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
import odds_common as oc  # noqa: E402  (the collectors import this same module object)

T0 = datetime(2026, 10, 15, 19, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------------------------------
# odds validation and de-vig
# --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value,expected",
    [("1.95", 1.95), ("1,95", 1.95), (2, 2.0), (1.01, 1.01), (" 3.40 ", 3.4)],
)
def test_parse_decimal_odds_valid(value, expected):
    assert oc.parse_decimal_odds(value) == pytest.approx(expected)


@pytest.mark.parametrize("value", [None, "", "abc", 1.0, "1.00", 0, -2.5, float("nan"), float("inf"), True, [1.9]])
def test_parse_decimal_odds_invalid_is_none_never_zero(value):
    assert oc.parse_decimal_odds(value) is None


def test_proportional_devig_exact_values():
    p = oc.devig_proportional([2.0, 3.5, 4.0])
    q = [0.5, 1 / 3.5, 0.25]
    s = sum(q)
    assert p == pytest.approx([x / s for x in q])
    assert sum(p) == pytest.approx(1.0)


def test_proportional_devig_double_chance_target_two():
    p = oc.devig_proportional([1.75, 1.32, 1.25], target=2.0)
    assert sum(p) == pytest.approx(2.0)


def test_shin_sums_to_one_and_z_in_range():
    p, z = oc.devig_shin([3.4, 3.6, 2.05])
    assert sum(p) == pytest.approx(1.0, abs=1e-9)
    assert 0.0 < z < 0.2
    assert all(0.0 < x < 1.0 for x in p)


def test_shin_matches_scipy_reference_implementation():
    """Same maths as scripts/research/xdata_devig.py (scipy brentq); pure-Python bisection must agree."""
    scipy_opt = pytest.importorskip("scipy.optimize")

    def reference(odds):
        q = [1 / o for o in odds]
        big_b = sum(q)

        def p_of(z):
            return [(math.sqrt(z * z + 4 * (1 - z) * x * x / big_b) - z) / (2 * (1 - z)) for x in q]

        z = scipy_opt.brentq(lambda z: sum(p_of(z)) - 1, 0.0, 0.5)
        p = p_of(z)
        s = sum(p)
        return [x / s for x in p], z

    for odds in ([3.4, 3.6, 2.05], [1.5, 4.0, 7.0], [1.91, 3.9, 3.5], [1.9, 1.9], [1.45, 2.65], [10.0, 5.0, 1.25]):
        p, z = oc.devig_shin(odds)
        p_ref, z_ref = reference(odds)
        assert z == pytest.approx(z_ref, abs=1e-9)
        assert p == pytest.approx(p_ref, abs=1e-9)


def test_shin_favourite_longshot_direction():
    """Shin moves probability from the long shot to the favourite compared with the proportional method."""
    odds = [1.5, 4.0, 7.0]
    prop = oc.devig_proportional(odds)
    shin, _ = oc.devig_shin(odds)
    assert shin[0] > prop[0]
    assert shin[2] < prop[2]


def test_shin_without_margin_is_proportional_and_z_zero():
    p, z = oc.devig_shin([2.0, 2.0])
    assert p == pytest.approx([0.5, 0.5])
    assert z == 0.0


def test_shin_two_way_symmetric():
    p, _ = oc.devig_shin([1.9, 1.9])
    assert p == pytest.approx([0.5, 0.5])


# --------------------------------------------------------------------------------------------------
# canonical markets
# --------------------------------------------------------------------------------------------------
def test_build_market_1x2():
    rec = oc.build_market("1x2", {"home": "3.40", "draw": "3.60", "away": "2.05"})
    assert rec["odds"] == {"home": 3.4, "draw": 3.6, "away": 2.05}
    assert rec["overround"] == pytest.approx(1 / 3.4 + 1 / 3.6 + 1 / 2.05, abs=1e-5)
    assert rec["margin"] == pytest.approx(rec["overround"] - 1, abs=1e-5)
    assert sum(rec["p_proportional"].values()) == pytest.approx(1.0, abs=1e-5)
    assert sum(rec["p_shin"].values()) == pytest.approx(1.0, abs=1e-5)
    assert 0 < rec["shin_z"] < 0.2


def test_build_market_missing_or_invalid_outcome_returns_none():
    assert oc.build_market("1x2", {"home": "3.40", "draw": None, "away": "2.05"}) is None
    assert oc.build_market("btts", {"yes": "1.5"}) is None
    assert oc.build_market("btts", {"yes": "abc", "no": "2.4"}) is None


def test_build_market_rejects_implausible_overround_instead_of_repairing():
    assert oc.build_market("1x2", {"home": 3.0, "draw": 3.5, "away": 4.0}) is None  # overround 0.869 (arbitrage / bad parse)
    assert oc.build_market("btts", {"yes": 1.05, "no": 1.05}) is None  # overround 1.90


def test_build_market_double_chance_sums_to_two_and_has_no_shin():
    rec = oc.build_market("double_chance", {"1x": 1.75, "x2": 1.25, "12": 1.32})
    assert rec["p_shin"] is None and rec["shin_z"] is None
    assert sum(rec["p_proportional"].values()) == pytest.approx(2.0, abs=1e-5)
    assert rec["overround"] == pytest.approx((1 / 1.75 + 1 / 1.25 + 1 / 1.32) / 2, abs=1e-5)
    assert "devig_note" in rec


def test_canonical_missing_lists_absent_markets():
    assert set(oc.canonical_missing({"1x2": {}, "btts": {}})) == {"double_chance", "ou_1.5", "ou_2.5", "ou_3.5"}
    assert oc.canonical_missing({k: {} for k in oc.MARKETS}) == []


@pytest.mark.parametrize("line,name", [(2.5, "ou_2.5"), ("2.50", "ou_2.5"), (1.5, "ou_1.5"), ("3.5", "ou_3.5"), (0.5, None), ("x", None), (None, None)])
def test_ou_market_name(line, name):
    assert oc.ou_market_name(line) == name


# --------------------------------------------------------------------------------------------------
# team names and mapping
# --------------------------------------------------------------------------------------------------
def test_normalize_and_similarity():
    assert oc.normalize_team("TSG 1899 Hoffenheim") == "hoffenheim"
    assert oc.normalize_team("Beşiktaş JK") == "besiktas"
    assert oc.team_similarity("Milan", "AC Milan") == 1.0
    assert oc.team_similarity("Sparta Prague", "Sparta Praha") == 1.0
    assert oc.team_similarity("Lech Poznań", "Lech Poznan") == 1.0
    assert oc.team_similarity("Inter", "Inter Milan") == pytest.approx(0.85)  # subset names are never "equal"
    assert oc.team_similarity("Ajax", "Celtic") < 0.5
    assert oc.team_similarity("", "Celtic") == 0.0


def _fx(mid, home, away, minutes=0):
    return oc.Fixture(match_id=mid, home=home, away=away, kickoff=T0 + timedelta(minutes=minutes), competition_id=73)


def _ev(eid, home, away, minutes=0):
    return oc.EventLite(event_id=eid, home=home, away=away, kickoff=T0 + timedelta(minutes=minutes), league="synthetic-league")


def test_mapping_exact_variants_and_confidence():
    fixtures = [_fx("1", "Hoffenheim", "Beşiktaş"), _fx("2", "Salzburg", "Milan", minutes=-135)]
    events = [_ev(901, "TSG 1899 Hoffenheim", "Besiktas JK"), _ev(902, "RB Salzburg", "AC Milan", minutes=-135), _ev(903, "Somebody", "Else")]
    mapped, unmapped = oc.map_events_to_fixtures(fixtures, events)
    assert set(mapped) == {"1", "2"} and unmapped == []
    ev1, conf1, evidence1 = mapped["1"]
    assert ev1.event_id == 901 and conf1 == 1.0 and "kickoff_diff_min=0" in evidence1
    assert mapped["2"][0].event_id == 902 and mapped["2"][1] >= 0.8


def test_mapping_kickoff_too_far_is_unmapped():
    mapped, unmapped = oc.map_events_to_fixtures([_fx("1", "Alpha United", "Beta City")], [_ev(1, "Alpha United", "Beta City", minutes=20)])
    assert mapped == {} and "within 15 min" in unmapped[0]["reason"] and "best_candidate" not in unmapped[0]


def test_mapping_lists_unmapped_with_reasons_and_never_guesses():
    fixtures = [
        _fx("2", "Gamma Rovers", "Delta Athletic", minutes=-300),   # swapped at vendor
        _fx("3", "Epsilon Town", "Zeta Wanderers", minutes=-200),   # vendor names too different
        _fx("4", "Omega Albion", "Sigma Orient", minutes=-100),     # no vendor event at all
    ]
    events = [
        _ev(2, "Delta Athletic", "Gamma Rovers", minutes=-300),
        _ev(3, "Epsilon Town", "Qqqq Zzzz", minutes=-200),
    ]
    mapped, unmapped = oc.map_events_to_fixtures(fixtures, events)
    assert mapped == {}
    reasons = {u["fotmob_match_id"]: u["reason"] for u in unmapped}
    assert "swapped" in reasons["2"]
    assert "below the name-similarity threshold" in reasons["3"]
    assert "within 15 min" in reasons["4"]
    swapped = next(u for u in unmapped if u["fotmob_match_id"] == "2")
    assert swapped["best_candidate"]["event_id"] == 2


def test_mapping_ambiguous_two_events_for_one_fixture():
    fixtures = [_fx("1", "Alpha United", "Beta City")]
    events = [_ev(1, "Alpha United", "Beta City", minutes=1), _ev(2, "Alpha United", "Beta City", minutes=3)]
    mapped, unmapped = oc.map_events_to_fixtures(fixtures, events)
    assert mapped == {} and "ambiguous" in unmapped[0]["reason"]


def test_mapping_ambiguous_one_event_for_two_fixtures():
    fixtures = [_fx("1", "Alpha United", "Beta City"), _fx("2", "Alpha United", "Beta City", minutes=2)]
    events = [_ev(1, "Alpha United", "Beta City")]
    mapped, unmapped = oc.map_events_to_fixtures(fixtures, events)
    assert mapped == {} and {u["fotmob_match_id"] for u in unmapped} == {"1", "2"}
    assert all("ambiguous" in u["reason"] for u in unmapped)


def test_mapping_kickoff_diff_between_5_and_15_minutes_lowers_confidence():
    mapped, _ = oc.map_events_to_fixtures([_fx("1", "Alpha United", "Beta City")], [_ev(1, "Alpha United", "Beta City", minutes=10)])
    assert mapped["1"][1] == pytest.approx(0.95)


# --------------------------------------------------------------------------------------------------
# FotMob day list and GET
# --------------------------------------------------------------------------------------------------
def _day_payload():
    def match(mid, home, away, utc, started=False):
        return {"id": mid, "home": {"id": mid * 10, "name": home}, "away": {"id": mid * 10 + 1, "name": away},
                "status": {"utcTime": utc, "started": started, "finished": False, "cancelled": False}}
    return {
        "leagues": [
            {"id": 943229, "primaryId": 73, "name": "Synthetic Europa", "matches": [
                match(1, "Alpha", "Beta", "2026-10-15T19:00:00.000Z"),
                match(2, "Gamma", "Delta", "2026-10-15T16:45:00.000Z", started=True),
                {"id": 3, "home": {"id": 1, "name": "No"}, "away": {"id": 2, "name": "Kickoff"}, "status": {}},
            ]},
            {"id": 55, "primaryId": 55, "name": "Synthetic Serie", "matches": [match(4, "Eps", "Zeta", "2026-10-15T18:45:00.000Z")]},
            {"id": 999, "primaryId": 999, "name": "Not featured", "matches": [match(5, "Eta", "Theta", "2026-10-15T19:00:00.000Z")]},
        ]
    }


def test_parse_fotmob_matches_payload_filters_featured_and_flags():
    fixtures = oc.parse_fotmob_matches_payload(_day_payload(), [73, 55])
    assert [f.match_id for f in fixtures] == ["2", "4", "1"]  # sorted by kick-off
    by = {f.match_id: f for f in fixtures}
    assert by["2"].started is True and by["1"].started is False
    assert by["1"].kickoff == datetime(2026, 10, 15, 19, 0, tzinfo=timezone.utc)
    assert by["1"].competition_id == 73 and by["1"].home == "Alpha"
    assert "3" not in by and "5" not in by  # no kick-off / not featured


class _Resp:
    def __init__(self, status, text="", headers=None):
        self.status_code, self.text, self.headers = status, text, headers or {}


class _Client:
    def __init__(self, responses):
        self.responses, self.urls = list(responses), []

    def get(self, url, headers=None, follow_redirects=None):
        assert follow_redirects is False  # redirects are followed by hand so the limiter runs before each hop
        self.urls.append(url)
        return self.responses.pop(0)


class _Limiter:
    def __init__(self):
        self.acquired, self.cooldowns = 0, []

    def acquire(self):
        self.acquired += 1

    def report_429(self, seconds):
        self.cooldowns.append(seconds)


JSON = {"content-type": "application/json; charset=utf-8"}


def test_fotmob_get_follows_redirect_with_limiter_before_every_hop():
    lim = _Limiter()
    client = _Client([_Resp(307, "", {"location": "/api/data/matchOdds?matchId=1&ccode3=DEU&bettingProvider=X_Y"}), _Resp(200, '{"a": 1}', JSON)])
    assert oc.fotmob_get(client, "/api/data/matchOdds?matchId=1&ccode3=DEU", limiter=lim) == {"a": 1}
    assert lim.acquired == 2
    assert client.urls[1] == "https://www.fotmob.com/api/data/matchOdds?matchId=1&ccode3=DEU&bettingProvider=X_Y"


def test_fotmob_get_null_and_204_mean_no_data():
    lim = _Limiter()
    assert oc.fotmob_get(_Client([_Resp(200, "null", JSON)]), "/x", limiter=lim) is None
    assert oc.fotmob_get(_Client([_Resp(204, "", JSON)]), "/x", limiter=lim) is None


def test_fotmob_get_429_reports_cooldown_and_raises():
    lim = _Limiter()
    with pytest.raises(oc.FotmobRateLimited):
        oc.fotmob_get(_Client([_Resp(429, "", {"retry-after": "42"})]), "/x", limiter=lim)
    assert lim.cooldowns == [42.0]


def test_fotmob_get_403_and_challenge_stop_the_run():
    with pytest.raises(oc.FotmobBlocked):
        oc.fotmob_get(_Client([_Resp(403, "forbidden")]), "/x", limiter=_Limiter())
    with pytest.raises(oc.FotmobBlocked):
        oc.fotmob_get(_Client([_Resp(200, "<html>Just a moment...</html>", {"content-type": "text/html"})]), "/x", limiter=_Limiter())


def test_fotmob_get_other_html_and_errors_are_plain_errors():
    with pytest.raises(RuntimeError):
        oc.fotmob_get(_Client([_Resp(200, "<html>hello</html>", {"content-type": "text/html"})]), "/x", limiter=_Limiter())
    with pytest.raises(RuntimeError):
        oc.fotmob_get(_Client([_Resp(500, "boom", JSON)]), "/x", limiter=_Limiter())


def test_fetch_fotmob_fixtures_uses_compact_date():
    lim = _Limiter()
    client = _Client([_Resp(200, json.dumps(_day_payload()), JSON)])
    fixtures = oc.fetch_fotmob_fixtures(client, "2026-10-15", [73], limiter=lim)
    assert client.urls == ["https://www.fotmob.com/api/data/matches?date=20261015"]
    assert [f.match_id for f in fixtures] == ["2", "1"]


# --------------------------------------------------------------------------------------------------
# misc
# --------------------------------------------------------------------------------------------------
def test_redact_removes_api_key_in_urls_and_literals():
    msg = "GET https://api.example.test/v3/events?sport=football&apiKey=SECRET123&limit=5 failed (SECRET123)"
    out = oc.redact(msg, "SECRET123")
    assert "SECRET123" not in out and "apiKey=***" in out


def test_append_jsonl_roundtrip_utf8(tmp_path):
    path = tmp_path / "sub" / "x.jsonl"
    assert oc.append_jsonl(path, [{"team": "Beşiktaş", "n": 1}]) == 1
    assert oc.append_jsonl(path, [{"team": "Lech Poznań", "n": 2}, {"n": 3}]) == 2
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["n"] for x in lines] == [1, 2, 3]
    assert "Beşiktaş" in lines[0]  # not ASCII-escaped


def test_parse_utc_variants():
    assert oc.parse_utc("2026-10-15T19:00:00.000Z") == T0
    assert oc.parse_utc("2026-10-15T22:00:00+03:00") == T0
    assert oc.parse_utc(int(T0.timestamp() * 1000)) == T0
    assert oc.parse_utc("garbage") is None and oc.parse_utc(None) is None


def test_build_snapshot_fields():
    fx = _fx("42", "Alpha", "Beta")
    markets = {"btts": oc.build_market("btts", {"yes": 1.5, "no": 2.5})}
    snap = oc.build_snapshot(fixture=fx, source="synthetic_source", bookmaker="Synthetic Book", markets=markets,
                             fetched_at=T0 - timedelta(hours=2), mapping={"method": "test", "confidence": 1.0}, region="DEU")
    assert snap["schema"] == "odds_snapshot_v1" and snap["fotmob_match_id"] == "42"
    assert snap["seconds_to_kickoff"] == 7200 and snap["is_closing"] is False and snap["odds_type"] == "pre_match"
    assert snap["fetched_at"] == "2026-10-15T17:00:00Z" and snap["match"]["kickoff_utc"] == "2026-10-15T19:00:00Z"
    assert set(snap["missing_markets"]) == {"1x2", "double_chance", "ou_1.5", "ou_2.5", "ou_3.5"}
    json.dumps(snap)  # serialisable
