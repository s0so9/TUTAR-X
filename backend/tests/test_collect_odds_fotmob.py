"""Tests for scripts/data_collection/collect_odds_fotmob.py.

Payloads built by ``_payload`` are SYNTHETIC TEST FIXTURES: the structure (persistentKey, odds.oddsTabMarkets[].markets[]
with header / headerTranslationKey / selections[name, oddsDecimal, value]) is copied from real FotMob ``matchOdds``
answers recorded on 2026-10-15, the prices and team names are invented. One extra test reads a REAL recorded answer
(backend/data/research/odds_samples/raw_matchodds_2026-10-15/) and is skipped when that folder is absent.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "data_collection"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
import odds_common as oc  # noqa: E402
import collect_odds_fotmob as col  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
REAL_RAW = BACKEND / "data" / "research" / "odds_samples" / "raw_matchodds_2026-10-15"
NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
KICKOFF = datetime(2026, 10, 15, 19, 0, tzinfo=timezone.utc)


def _sel(name, odds, value=None):
    return {"name": name, "oddsDecimal": odds, "oddsAmerican": "+100", "oddsFraction": "1/1", "couponKey": None, "team": None, "value": value, "link": "https://example.invalid/synthetic"}


def _market(header, key, sels):
    return {"header": header, "headerTranslationKey": key, "selections": sels, "fotMobMarketTypeId": {"translationKey": key}}


def _payload(provider="Synthetic_Germany", markets=None, odds_type="PreMatch", provider_id="171"):
    markets = markets if markets is not None else []
    return {
        "persistentKey": provider,
        "providerId": provider_id,
        "promoText": {"text": "synthetic"},
        "odds": {
            "matchfactMarkets": markets[:1],
            "oddsTabMarkets": [{"category": "Oddstab", "markets": markets}],
            "oddsType": odds_type,
            "provider": {"id": int(provider_id)},
            "resolvedOddsMarket": None,
        },
        "restrictions": {"country": "DEU"},
    }


def tipico_style():
    """One combined over/under market ("Under 2.5" / "Over 2.5"), double chance 1x / x2 / 12."""
    return _payload("Synthetic_Germany", [
        _market("1x2", "who_will_win", [_sel("1", "3.40"), _sel("x", "3.60"), _sel("2", "2.05")]),
        _market("Next to score", "who_will_score_next", [_sel("1", "2.25"), _sel("x", "13.00"), _sel("2", "1.70")]),
        _market("Total goals over/under", "odds_goals_over_under", [_sel("Under 2.5", "2.40"), _sel("Over 2.5", "1.55")]),
        _market("Both teams to score", "both_score", [_sel("No", "2.40"), _sel("Yes", "1.50")]),
        _market("Double chance", "double_chance", [_sel("1x", "1.75"), _sel("x2", "1.25"), _sel("12", "1.32")]),
    ])


def onexbet_style():
    """Separate over/under markets per line ("Over/Under 2.5": Over / Under), double chance 1X / 12 / 2X."""
    return _payload("Synthetic_Spain", [
        _market("Match Result", "who_will_win", [_sel("1", "3.68"), _sel("x", "3.78"), _sel("2", "2.02")]),
        _market("Both Teams To Score", "both_score", [_sel("Yes", "1.53"), _sel("No", "2.37")]),
        _market("Over/Under 2.5", "odds_goals_over_under", [_sel("Over", "1.67"), _sel("Under", "2.32")]),
        _market("Over/Under 3.5", "odds_goals_over_under", [_sel("Over", "2.47"), _sel("Under", "1.49")]),
        _market("Over/Under 1.5", "odds_goals_over_under", [_sel("Over", "1.17"), _sel("Under", "4.50")]),
        _market("Double Chance", "double_chance", [_sel("1X", "1.85"), _sel("12", "1.30"), _sel("2X", "1.31")]),
    ], provider_id="449")


def bet365_style(home="Alpha", away="Beta"):
    """No over/under and no double chance; Draw No Bet carries the team names."""
    return _payload("Synthetic_Bet365", [
        _market("Full Time Result", "who_will_win", [_sel("1", "1.91"), _sel("x", "3.90"), _sel("2", "3.50")]),
        _market("Handicap Result", "odds_handicap_x_y", [_sel("1", "3.25", "-1"), _sel("x", "4.33", "+1"), _sel("2", "1.83", "+1")]),
        _market("Draw No Bet", "odds_draw_no_bet", [_sel(home, "1.44"), _sel(away, "2.63")]),
        _market("Both Teams to Score", "both_score", [_sel("Yes", "1.44"), _sel("No", "2.63")]),
    ], provider_id="23")


def fixture(mid="6112353", home="Alpha", away="Beta", **kw):
    return oc.Fixture(match_id=mid, home=home, away=away, kickoff=KICKOFF, competition_id=73, **kw)


# --------------------------------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------------------------------
def test_parse_combined_over_under_and_double_chance_names():
    p = col.parse_fotmob_match_odds(tipico_style())
    assert p["provider"] == "Synthetic_Germany" and p["provider_id"] == "171" and p["odds_type"] == "PreMatch"
    m = p["markets"]
    assert set(m) == {"1x2", "btts", "double_chance", "ou_2.5"}
    assert m["1x2"]["odds"] == {"home": 3.4, "draw": 3.6, "away": 2.05}
    assert m["ou_2.5"]["odds"] == {"over": 1.55, "under": 2.4}
    assert m["btts"]["odds"] == {"yes": 1.5, "no": 2.4}
    assert m["double_chance"]["odds"] == {"1x": 1.75, "12": 1.32, "x2": 1.25}
    assert "who_will_score_next" in p["headers_seen"]  # market we do not use is only listed, never parsed


def test_parse_separate_lines_and_2x_alias():
    m = col.parse_fotmob_match_odds(onexbet_style())["markets"]
    assert set(m) == {"1x2", "btts", "double_chance", "ou_1.5", "ou_2.5", "ou_3.5"}
    assert m["ou_1.5"]["odds"] == {"over": 1.17, "under": 4.5}
    assert m["ou_3.5"]["odds"] == {"over": 2.47, "under": 1.49}
    assert m["double_chance"]["odds"] == {"1x": 1.85, "12": 1.3, "x2": 1.31}  # "2X" read as x2


def test_parse_missing_markets_are_absent_not_zero():
    p = col.parse_fotmob_match_odds(bet365_style())
    assert set(p["markets"]) == {"1x2", "btts"}
    snap, notes = col.snapshot_from_payload(fixture(), "ESP", bet365_style(), NOW)
    assert set(snap["missing_markets"]) == {"double_chance", "ou_1.5", "ou_2.5", "ou_3.5"}
    assert "ou_2.5" not in snap["markets"]


def test_parse_rejects_incomplete_market_and_lists_reason():
    payload = _payload("Synthetic_X", [
        _market("1x2", "who_will_win", [_sel("1", "2.0"), _sel("x", "3.5"), _sel("2", None)]),
        _market("Both teams to score", "both_score", [_sel("Yes", "1.9"), _sel("No", "1.9")]),
        _market("Over/Under 2.5", "odds_goals_over_under", [_sel("Over", "1.9")]),  # Under missing
        _market("Over/Under 0.5", "odds_goals_over_under", [_sel("Over", "1.05"), _sel("Under", "9.0")]),  # untracked line
    ])
    p = col.parse_fotmob_match_odds(payload)
    assert set(p["markets"]) == {"btts"}
    assert "1x2" in p["markets_rejected"] and "ou_2.5" in p["markets_rejected"]
    assert "ou_0.5" not in p["markets_rejected"] and "ou_0.5" not in p["markets"]


def test_first_market_of_a_kind_wins_over_duplicates():
    payload = _payload("Synthetic_X", [
        _market("1x2", "who_will_win", [_sel("1", "2.0"), _sel("x", "3.5"), _sel("2", "4.0")]),
        _market("1x2 again", "who_will_win", [_sel("1", "9.0"), _sel("x", "9.0"), _sel("2", "9.0")]),
    ])
    assert col.parse_fotmob_match_odds(payload)["markets"]["1x2"]["odds"]["home"] == 2.0


# --------------------------------------------------------------------------------------------------
# identity check and snapshot
# --------------------------------------------------------------------------------------------------
def test_team_name_check_verified_mismatch_not_available():
    fx = fixture(home="Hoffenheim", away="Beşiktaş")
    assert col.check_team_names(fx, ["Hoffenheim", "Besiktas JK"])[0] == "verified"
    assert col.check_team_names(fx, ["Liverpool", "Chelsea"])[0] == "mismatch"
    assert col.check_team_names(fx, ["Beşiktaş", "Hoffenheim"])[0] == "mismatch"  # swapped
    assert col.check_team_names(fx, None)[0] == "not_available"


def test_snapshot_is_pre_match_keyed_by_fotmob_id_with_provider_and_region():
    snap, notes = col.snapshot_from_payload(fixture(), "DEU", tipico_style(), NOW)
    assert snap["source"] == "fotmob_matchodds" and snap["bookmaker"] == "Synthetic_Germany" and snap["region"] == "DEU"
    assert snap["fotmob_match_id"] == "6112353" and snap["odds_type"] == "pre_match" and snap["provider_id"] == "171"
    assert snap["mapping"]["method"] == "fotmob_match_id" and snap["mapping"]["confidence"] == 1.0
    assert snap["mapping"]["team_name_check"] == "not_available"
    assert snap["seconds_to_kickoff"] == 7 * 3600
    assert sum(snap["markets"]["1x2"]["p_shin"].values()) == pytest.approx(1.0, abs=1e-5)
    assert "link" not in json.dumps(snap)  # no affiliate / tracking links are stored


def test_snapshot_skipped_when_team_names_mismatch_or_not_prematch_or_empty():
    snap, notes = col.snapshot_from_payload(fixture(home="Gamma", away="Delta"), "ESP", bet365_style("Alpha", "Beta"), NOW)
    assert snap is None and "do not match" in notes["skipped"]
    snap, notes = col.snapshot_from_payload(fixture(), "DEU", _payload("Synthetic_X", [_market("1x2", "who_will_win", [_sel("1", "2.0"), _sel("x", "3.5"), _sel("2", "4.0")])], odds_type="Live"), NOW)
    assert snap is None and "not PreMatch" in notes["skipped"]
    snap, notes = col.snapshot_from_payload(fixture(), "DEU", _payload("Synthetic_X", []), NOW)
    assert snap is None and "no usable canonical market" in notes["skipped"]


def test_snapshot_verified_when_draw_no_bet_names_match():
    snap, _ = col.snapshot_from_payload(fixture(home="Alpha", away="Beta"), "ESP", bet365_style("Alpha", "Beta"), NOW)
    assert snap["mapping"]["team_name_check"] == "verified"


# --------------------------------------------------------------------------------------------------
# fixture selection
# --------------------------------------------------------------------------------------------------
def test_select_fixtures_pre_match_only_and_window():
    fixtures = [
        fixture("1"),
        fixture("2", started=True),
        fixture("3", finished=True),
        fixture("4", cancelled=True),
        oc.Fixture("5", "A", "B", NOW - timedelta(minutes=5)),                 # kick-off in the past
        oc.Fixture("6", "A", "B", NOW + timedelta(hours=40)),                  # beyond the window
    ]
    assert [f.match_id for f in col.select_fixtures(fixtures, NOW, hours_ahead=36, match_ids=None, max_matches=None)] == ["1"]
    assert [f.match_id for f in col.select_fixtures(fixtures, NOW, hours_ahead=48, match_ids=None, max_matches=None)] == ["1", "6"]
    assert col.select_fixtures(fixtures, NOW, hours_ahead=48, match_ids={"6"}, max_matches=None)[0].match_id == "6"
    assert len(col.select_fixtures(fixtures, NOW, hours_ahead=48, match_ids=None, max_matches=1)) == 1


# --------------------------------------------------------------------------------------------------
# collect() over a mock transport
# --------------------------------------------------------------------------------------------------
class _Limiter:
    def __init__(self):
        self.acquired, self.cooldowns = 0, []

    def acquire(self):
        self.acquired += 1

    def report_429(self, seconds):
        self.cooldowns.append(seconds)


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_collect_follows_provider_redirect_with_limiter_per_hop_and_records_no_odds_country():
    seen = []

    def handler(request: httpx.Request):
        seen.append(str(request.url))
        q = dict(request.url.params)
        if q.get("ccode3") == "TUR":
            return httpx.Response(200, content=b"null", headers={"content-type": "application/json; charset=utf-8"})  # FotMob: literal JSON null = no odds
        if "bettingProvider" not in q:
            return httpx.Response(307, headers={"location": f"/api/data/matchOdds?matchId={q['matchId']}&ccode3={q['ccode3']}&bettingProvider=Synthetic_Germany"})
        return httpx.Response(200, json=tipico_style())

    lim = _Limiter()
    with _client(handler) as client:
        snaps, report = col.collect(client, [fixture()], ["DEU", "TUR"], limiter=lim, clock=lambda: NOW)
    assert len(snaps) == 1 and snaps[0]["region"] == "DEU"
    assert report["no_odds"] == [{"match_id": "6112353", "country": "TUR"}]
    assert report["providers_seen"] == {"DEU": ["Synthetic_Germany"]}
    assert lim.acquired == len(seen) == 3  # DEU: 2 hops, TUR: 1; limiter before EVERY request


def test_collect_pin_adds_betting_provider_parameter():
    seen = []

    def handler(request: httpx.Request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=tipico_style())

    with _client(handler) as client:
        col.collect(client, [fixture()], ["DEU"], pins={"DEU": "Tipico_Germany"}, limiter=_Limiter(), clock=lambda: NOW)
    assert seen == [{"matchId": "6112353", "ccode3": "DEU", "bettingProvider": "Tipico_Germany"}]


def test_collect_stops_on_403_and_never_continues():
    calls = []

    def handler(request: httpx.Request):
        calls.append(1)
        return httpx.Response(403, text="forbidden")

    with _client(handler) as client, pytest.raises(oc.FotmobBlocked):
        col.collect(client, [fixture("1"), fixture("2")], ["DEU", "AUT"], limiter=_Limiter(), clock=lambda: NOW)
    assert len(calls) == 1


def test_collect_429_reports_cooldown_to_shared_limiter():
    lim = _Limiter()

    def handler(request: httpx.Request):
        return httpx.Response(429, headers={"retry-after": "75"}, text="slow down")

    with _client(handler) as client, pytest.raises(oc.FotmobRateLimited):
        col.collect(client, [fixture()], ["DEU"], limiter=lim, clock=lambda: NOW)
    assert lim.cooldowns == [75.0]


def test_collect_other_errors_are_logged_and_skipped():
    def handler(request: httpx.Request):
        if request.url.params["ccode3"] == "AUT":
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json=tipico_style())

    with _client(handler) as client:
        snaps, report = col.collect(client, [fixture()], ["AUT", "DEU"], limiter=_Limiter(), clock=lambda: NOW)
    assert len(snaps) == 1 and len(report["errors"]) == 1 and report["errors"][0]["country"] == "AUT"


def test_collect_writes_raw_answers_when_requested(tmp_path):
    def handler(request: httpx.Request):
        return httpx.Response(200, json=tipico_style())

    with _client(handler) as client:
        col.collect(client, [fixture()], ["DEU"], limiter=_Limiter(), raw_dir=tmp_path, clock=lambda: NOW)
    saved = json.loads((tmp_path / "fotmob_matchOdds_6112353_DEU.json").read_text(encoding="utf-8"))
    assert saved["persistentKey"] == "Synthetic_Germany"


# --------------------------------------------------------------------------------------------------
# CLI gate and offline mode
# --------------------------------------------------------------------------------------------------
def test_main_refuses_without_the_terms_risk_flag_and_makes_no_request(monkeypatch, capsys):
    def boom(*a, **k):
        raise AssertionError("no HTTP client may be created without --accept-fotmob-terms-risk")

    monkeypatch.setattr(col.httpx, "Client", boom)
    assert col.main(["--date", "2026-10-15"]) == 3
    assert "robots.txt" in capsys.readouterr().err


def _day_json(path: Path, started=False):
    payload = {"leagues": [{"id": 943229, "primaryId": 73, "name": "Synthetic Europa", "matches": [
        {"id": 6112353, "home": {"id": 1, "name": "Alpha"}, "away": {"id": 2, "name": "Beta"},
         "status": {"utcTime": "2026-10-15T19:00:00.000Z", "started": started, "finished": False, "cancelled": False}}]}]}
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_offline_from_raw_parses_recorded_answers_without_network(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "fotmob_matchOdds_6112353_DEU.json").write_text(json.dumps(tipico_style()), encoding="utf-8")
    (raw / "fotmob_matchOdds_6112353_ESP.json").write_text(json.dumps(bet365_style("Alpha", "Beta")), encoding="utf-8")
    (raw / "fotmob_matchOdds_999_DEU.json").write_text(json.dumps(tipico_style()), encoding="utf-8")  # not in the fixture list
    (raw / "fotmob_matchOdds_6112353_TUR.json").write_text("null", encoding="utf-8")
    (raw / "notes.txt").write_text("ignored", encoding="utf-8")
    fx = tmp_path / "day.json"
    _day_json(fx)
    out = tmp_path / "out" / "2026-10-15.jsonl"

    def boom(*a, **k):
        raise AssertionError("offline mode must not touch the network")

    monkeypatch.setattr(col.httpx, "Client", boom)
    assert col.main(["--date", "2026-10-15", "--from-raw", str(raw), "--fixtures-json", str(fx), "--out", str(out)]) == 0
    lines = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
    assert sorted(x["region"] for x in lines) == ["DEU", "ESP"]
    assert all(x["fetched_at_source"] == "raw file modification time" for x in lines)
    run = json.loads(out.with_name("2026-10-15.fotmob_run.json").read_text(encoding="utf-8"))
    assert run["mode"] == "offline_from_raw" and run["snapshots_written"] == 2 and len(run["no_odds"]) == 1 and len(run["skipped"]) == 1


def test_offline_from_raw_skips_started_fixture(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "fotmob_matchOdds_6112353_DEU.json").write_text(json.dumps(tipico_style()), encoding="utf-8")
    fx = tmp_path / "day.json"
    _day_json(fx, started=True)
    fixtures = oc.parse_fotmob_matches_payload(json.loads(fx.read_text(encoding="utf-8")), [73])
    snaps, report = col.collect_from_raw(raw, fixtures)
    assert snaps == [] and "already started" in report["skipped"][0]["skipped"]


# --------------------------------------------------------------------------------------------------
# REAL recorded answer (2026-10-15, Salzburg - Milan, DEU / Tipico)
# --------------------------------------------------------------------------------------------------
@pytest.mark.skipif(not (REAL_RAW / "fotmob_matchOdds_6112294_DEU.json").exists(), reason="recorded sample not present")
def test_real_recorded_tipico_answer_parses_to_the_prices_on_screen():
    payload = json.loads((REAL_RAW / "fotmob_matchOdds_6112294_DEU.json").read_text(encoding="utf-8"))
    p = col.parse_fotmob_match_odds(payload)
    assert p["provider"] == "Tipico_Germany" and p["odds_type"] == "PreMatch"
    assert p["markets"]["1x2"]["odds"] == {"home": 3.4, "draw": 3.6, "away": 2.05}
    assert p["markets"]["ou_2.5"]["odds"] == {"over": 1.55, "under": 2.4}
    assert p["markets"]["btts"]["odds"] == {"yes": 1.5, "no": 2.4}
    assert p["markets"]["double_chance"]["odds"] == {"1x": 1.75, "12": 1.32, "x2": 1.25}
    assert p["markets"]["1x2"]["overround"] == pytest.approx(1.0597, abs=1e-4)


@pytest.mark.skipif(not (REAL_RAW / "fotmob_matchOdds_6112294_ESP.json").exists(), reason="recorded sample not present")
def test_real_recorded_1xbet_answer_has_all_three_total_lines():
    payload = json.loads((REAL_RAW / "fotmob_matchOdds_6112294_ESP.json").read_text(encoding="utf-8"))
    p = col.parse_fotmob_match_odds(payload)
    assert p["provider"] == "1xBet_Spain"
    assert {"ou_1.5", "ou_2.5", "ou_3.5", "double_chance", "btts", "1x2"} <= set(p["markets"])
