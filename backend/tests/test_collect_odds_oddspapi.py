"""Tests for scripts/data_collection/collect_odds_oddspapi.py (OddsPapi v4).

Every response below is a SYNTHETIC TEST FIXTURE shaped after the vendor's public documentation (oddspapi.io/us/docs:
/v4/markets, /v4/fixtures, /v4/odds-by-tournaments). Ids, prices and teams are invented; the market ids 101 / 104 / 106 follow
the documentation's examples, the others are made up for the tests. The collector has NOT been run against the live service
(no API key exists yet): these tests only prove classification, parsing, mapping, quota and key-handling logic.
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
import collect_odds_oddspapi as col  # noqa: E402

KEY = "SYNTHETIC-PAPI-KEY-987654321"
_REAL_CLIENT = httpx.Client  # the CLI test replaces httpx.Client (same module object), keep the real class for the mock
T0 = datetime(2026, 10, 15, 19, 0, tzinfo=timezone.utc)


def mkt(mid, name, outcomes, mtype="other", handicap=0, period="fulltime", prop=False):
    return {"marketId": mid, "marketLength": len(outcomes), "marketName": name, "playerProp": prop, "sportId": 10, "handicap": handicap,
            "period": period, "marketType": mtype, "outcomes": [{"outcomeId": oid, "outcomeName": n} for oid, n in outcomes]}


def markets_list():
    return [
        mkt(101, "Full Time Result", [(101, "1"), (102, "X"), (103, "2")], mtype="1x2"),
        mkt(104, "Both Teams To Score", [(104, "Yes"), (105, "No")], mtype="totals"),
        mkt(106, "Over Under Full Time", [(106, "Over"), (107, "Under")], mtype="totals", handicap=0.5),
        mkt(1010, "Over Under Full Time", [(1010, "Over"), (1011, "Under")], mtype="totals", handicap=1.5),
        mkt(1008, "Over Under Full Time", [(1008, "Over"), (1009, "Under")], mtype="totals", handicap=2.5),
        mkt(1012, "Over Under Full Time", [(1012, "Over"), (1013, "Under")], mtype="totals", handicap=3.5),
        mkt(1014, "Over Under Full Time", [(1014, "Over"), (1015, "Under")], mtype="totals", handicap=4.5),
        mkt(1020, "Double Chance", [(1020, "1X"), (1021, "12"), (1022, "X2")]),
        mkt(2001, "Over Under 1st Half", [(2001, "Over"), (2002, "Under")], handicap=1.5, period="1sthalf"),
        mkt(2003, "Team Total Home", [(2003, "Over"), (2004, "Under")], handicap=1.5),
        mkt(2005, "Anytime Scorer", [(2005, "Yes"), (2006, "No")], prop=True),
        mkt(2007, "Asian Handicap", [(2007, "Home"), (2008, "Away")], handicap=-0.5),
        mkt(2009, "Both Teams To Score 1st Half", [(2009, "Yes"), (2010, "No")], period="1sthalf"),
    ]


def outcome(price, active=True, changed="2026-10-15T11:55:00.000+00:00"):
    return {"players": {"0": {"active": active, "betslip": None, "bookmakerOutcomeId": "x", "changedAt": changed, "limit": 5000, "playerName": None, "price": price, "exchangeMeta": {}}}}


def market_block(prices: dict, active=True):
    return {"bookmakerMarketId": "synthetic", "marketActive": active, "outcomes": {str(oid): outcome(p) if not isinstance(p, dict) else p for oid, p in prices.items()}}


def book_full():
    return {"bookmakerIsActive": True, "bookmakerFixtureId": "1", "fixturePath": "https://example.invalid/x", "suspended": False, "markets": {
        "101": market_block({101: 1.95, 102: 3.55, 103: 3.60}),
        "104": market_block({104: 1.65, 105: 2.10}),
        "106": market_block({106: 1.02, 107: 12.0}),  # 0.5 line: not tracked, ignored
        "1010": market_block({1010: 1.25, 1011: 3.60}),
        "1008": market_block({1008: 1.80, 1009: 1.90}),
        "1012": market_block({1012: 2.90, 1013: 1.38}),
        "1020": market_block({1020: 1.25, 1021: 1.30, 1022: 1.75}),
        "9999": market_block({9999: 2.0, 10000: 2.0}),  # not in /markets: ignored
    }}


def fixture_row(fid, home, away, minutes=0, tournament=7):
    return {"fixtureId": fid, "participant1Id": 1, "participant2Id": 2, "sportId": 10, "tournamentId": tournament, "statusId": 0, "hasOdds": True,
            "startTime": oc.iso_z(T0 + timedelta(minutes=minutes)).replace("Z", ".000Z"), "participant1Name": home, "participant2Name": away}


def fx(mid, home, away, minutes=0):
    return oc.Fixture(match_id=mid, home=home, away=away, kickoff=T0 + timedelta(minutes=minutes), competition_id=73)


# --------------------------------------------------------------------------------------------------
# classification and parsing
# --------------------------------------------------------------------------------------------------
def test_classify_markets_picks_only_the_full_time_markets_we_use():
    cls = col.classify_markets(markets_list())
    names = {mid: c for mid, (c, _) in cls.items()}
    assert names == {101: "1x2", 104: "btts", 1010: "ou_1.5", 1008: "ou_2.5", 1012: "ou_3.5", 1020: "double_chance"}
    assert cls[101][1] == {101: "home", 102: "draw", 103: "away"}
    assert cls[1020][1] == {1020: "1x", 1021: "12", 1022: "x2"}
    assert cls[1012][1] == {1012: "over", 1013: "under"}
    # "Both Teams To Score" contains the word "Teams": it must still be classified, the 1st-half variant must not
    assert 2009 not in cls and 2001 not in cls and 2003 not in cls and 2005 not in cls and 2007 not in cls and 106 not in cls and 1014 not in cls


def test_classify_markets_ignores_garbage_and_incomplete_outcome_sets():
    assert col.classify_markets({"error": "x"}) == {}
    bad = [mkt(101, "Full Time Result", [(101, "1"), (102, "X")], mtype="1x2"), mkt(104, "Both Teams To Score", [(104, "Yes"), (105, "Maybe")]), "junk", {"marketId": "x"}]
    assert col.classify_markets(bad) == {}


def test_classify_markets_first_market_of_a_kind_wins():
    dup = [mkt(300, "Over Under Full Time", [(300, "Over"), (301, "Under")], handicap=2.5), mkt(200, "Over Under Full Time", [(200, "Over"), (201, "Under")], handicap=2.5)]
    assert list(col.classify_markets(dup)) == [200]  # lowest marketId


def test_parse_fixtures_names_kickoff_and_tournament():
    out = col.parse_fixtures([fixture_row("id1", "Hoffenheim", "Besiktas"), {"fixtureId": "id2", "participant1Name": "A"}, "junk"])
    assert len(out) == 1 and out[0].event_id == "id1" and out[0].kickoff == T0 and out[0].league == "7"


def test_parse_bookmaker_odds_full_book():
    cls = col.classify_markets(markets_list())
    markets, rejected, updated = col.parse_bookmaker_odds(book_full(), cls)
    assert set(markets) == {"1x2", "btts", "ou_1.5", "ou_2.5", "ou_3.5", "double_chance"} and rejected == {}
    assert markets["1x2"]["odds"] == {"home": 1.95, "draw": 3.55, "away": 3.6}
    assert markets["ou_2.5"]["odds"] == {"over": 1.8, "under": 1.9}
    assert updated == "2026-10-15T11:55:00.000+00:00"


def test_parse_bookmaker_odds_inactive_price_inactive_market_and_suspended_book():
    cls = col.classify_markets(markets_list())
    book = book_full()
    book["markets"]["101"]["outcomes"]["102"] = outcome(3.55, active=False)   # draw price suspended -> 1x2 incomplete
    book["markets"]["104"]["marketActive"] = False
    markets, rejected, _ = col.parse_bookmaker_odds(book, cls)
    assert "1x2" not in markets and "btts" not in markets
    assert "draw" in rejected["1x2"] and rejected["btts"] == "market inactive"
    assert {"ou_2.5", "double_chance"} <= set(markets)
    markets, rejected, _ = col.parse_bookmaker_odds({**book_full(), "suspended": True}, cls)
    assert markets == {} and "suspended" in rejected["_bookmaker"]


def test_parse_fixture_odds_drops_bookmakers_without_usable_markets():
    cls = col.classify_markets(markets_list())
    row = {"fixtureId": "id1", "bookmakerOdds": {"pinnacle": book_full(), "bet365": {"suspended": False, "markets": {}}, "bad": "junk"}}
    parsed = col.parse_fixture_odds(row, cls)
    assert [p["bookmaker"] for p in parsed] == ["pinnacle"]
    assert col.parse_fixture_odds(None, cls) == []


# --------------------------------------------------------------------------------------------------
# markets cache
# --------------------------------------------------------------------------------------------------
def test_load_markets_uses_cache_and_only_bills_once(tmp_path):
    calls = []

    def handler(request: httpx.Request):
        calls.append(request.url.path)
        return httpx.Response(200, json=markets_list())

    cache = tmp_path / "markets.json"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        b = col.RequestBudget(min_interval=0)
        first = col.load_markets(client, KEY, b, cache)
        second = col.load_markets(client, KEY, b, cache)
    assert first == second and calls == ["/v4/markets"] and b.used == 1


def test_load_markets_refreshes_a_stale_cache(tmp_path):
    cache = tmp_path / "markets.json"
    cache.write_text("[]", encoding="utf-8")
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=markets_list()))) as client:
        b = col.RequestBudget(min_interval=0)
        col.load_markets(client, KEY, b, cache, now=cache.stat().st_mtime + col.MARKETS_CACHE_MAX_AGE_S + 10)
    assert b.used == 1 and len(json.loads(cache.read_text(encoding="utf-8"))) == len(markets_list())


# --------------------------------------------------------------------------------------------------
# collect() over a mock transport
# --------------------------------------------------------------------------------------------------
class Server:
    def __init__(self, fixtures_rows, odds_rows, fail_odds=False):
        self.fixtures_rows, self.odds_rows, self.fail_odds = fixtures_rows, odds_rows, fail_odds
        self.requests = []

    def __call__(self, request: httpx.Request):
        params = dict(request.url.params)
        self.requests.append((request.url.path.replace("/v4", ""), params))
        assert params.get("apiKey") == KEY
        path = request.url.path.replace("/v4", "")
        if path == "/markets":
            return httpx.Response(200, json=markets_list())
        if path == "/fixtures":
            assert params["sportId"] == "10" and params["statusId"] == "0" and params["hasOdds"] == "true"
            return httpx.Response(200, json=self.fixtures_rows)
        if path == "/odds-by-tournaments":
            if self.fail_odds:
                return httpx.Response(429, text="slow down")
            return httpx.Response(200, json=self.odds_rows)
        return httpx.Response(404)


def run(server, fixtures, tmp_path, bookmakers=("pinnacle", "bet365"), max_requests=10):
    with httpx.Client(transport=httpx.MockTransport(server)) as client:
        budget = col.RequestBudget(max_requests=max_requests, min_interval=0)
        return col.collect(client, KEY, fixtures, list(bookmakers), budget, markets_cache=tmp_path / "m.json", clock=lambda: T0 - timedelta(hours=7))


def test_collect_end_to_end_maps_by_names_and_writes_snapshots(tmp_path):
    odds_rows = [
        {"fixtureId": "idA", "tournamentId": 7, "bookmakerOdds": {"pinnacle": book_full(), "bet365": {"suspended": False, "markets": {"101": market_block({101: 1.91, 102: 3.9, 103: 3.5})}}}},
        {"fixtureId": "idOther", "tournamentId": 7, "bookmakerOdds": {"pinnacle": book_full()}},
    ]
    server = Server([fixture_row("idA", "TSG Hoffenheim", "Besiktas JK", tournament=7), fixture_row("idB", "Somebody", "Else", tournament=9)], odds_rows)
    fixtures = [fx("6112353", "Hoffenheim", "Beşiktaş"), fx("999", "Unknown FC", "Nowhere United", minutes=-30)]
    snaps, report = run(server, fixtures, tmp_path)

    assert [p for p, _ in server.requests] == ["/markets", "/fixtures", "/odds-by-tournaments"]
    odds_params = server.requests[2][1]
    assert odds_params["tournamentIds"] == "7" and odds_params["bookmakers"] == "pinnacle,bet365"  # only the tournament of a MAPPED fixture
    assert {s["bookmaker"] for s in snaps} == {"pinnacle", "bet365"} and {s["fotmob_match_id"] for s in snaps} == {"6112353"}
    pin = next(s for s in snaps if s["bookmaker"] == "pinnacle")
    assert pin["source"] == "oddspapi" and pin["mapping"]["method"] == "teams+kickoff" and pin["mapping"]["vendor_event_id"] == "idA"
    assert pin["missing_markets"] == [] and pin["odds_updated_at"] == "2026-10-15T11:55:00.000+00:00" and pin["seconds_to_kickoff"] == 7 * 3600
    assert set(next(s for s in snaps if s["bookmaker"] == "bet365")["missing_markets"]) == {"btts", "double_chance", "ou_1.5", "ou_2.5", "ou_3.5"}
    assert [u["fotmob_match_id"] for u in report["unmapped"]] == ["999"]
    assert report["requests_used"] == 3 and report["markets_classified"]["1x2"] == 101
    assert KEY not in json.dumps(snaps) + json.dumps(report) and "example.invalid" not in json.dumps(snaps)  # no key, no vendor links


def test_collect_fixture_without_odds_is_reported_not_invented(tmp_path):
    server = Server([fixture_row("idA", "Alpha United", "Beta City")], [{"fixtureId": "idA", "tournamentId": 7, "bookmakerOdds": {}}])
    snaps, report = run(server, [fx("10", "Alpha United", "Beta City")], tmp_path)
    assert snaps == [] and report["no_odds_for_fixture"] == ["10"]


def test_collect_stops_on_429_and_reports_it(tmp_path):
    server = Server([fixture_row("idA", "Alpha United", "Beta City")], [], fail_odds=True)
    snaps, report = run(server, [fx("10", "Alpha United", "Beta City")], tmp_path)
    assert snaps == [] and "429" in report["stopped"]


def test_collect_request_cap_protects_the_free_monthly_quota(tmp_path):
    server = Server([fixture_row("idA", "Alpha United", "Beta City")], [])
    snaps, report = run(server, [fx("10", "Alpha United", "Beta City")], tmp_path, max_requests=2)
    assert snaps == [] and "cap" in report["stopped"] and len(server.requests) == 2


def test_collect_rejects_a_window_of_48_hours_or_more(tmp_path):
    server = Server([], [])
    with pytest.raises(col.OddsPapiError):
        run(server, [fx("1", "A", "B"), fx("2", "C", "D", minutes=48 * 60)], tmp_path)
    assert server.requests == []


def test_collect_nothing_to_do_makes_no_request(tmp_path):
    server = Server([], [])
    assert run(server, [], tmp_path)[0] == [] and server.requests == []


def test_vendor_errors_never_contain_the_key():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401, text=f"bad key in {r.url}"))) as client:
        with pytest.raises(col.OddsPapiError) as ei:
            col.api_get(client, "/markets", {}, KEY, col.RequestBudget(min_interval=0))
    assert KEY not in str(ei.value) and "401" in str(ei.value)


# --------------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------------
def test_main_without_key_exits_5_and_explains(monkeypatch, capsys):
    monkeypatch.delenv("ODDSPAPI_API_KEY", raising=False)
    monkeypatch.setattr(col.httpx, "Client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no client without a key")))
    assert col.main(["--date", "2026-10-15"]) == 5
    err = capsys.readouterr().err
    assert "ODDSPAPI_API_KEY" in err and "oddspapi.io" in err


def test_main_rejects_more_than_three_bookmakers(monkeypatch):
    monkeypatch.setenv("ODDSPAPI_API_KEY", KEY)
    assert col.main(["--bookmakers", "a,b,c,d"]) == 1


def test_main_end_to_end_with_mock_service(monkeypatch, tmp_path, capsys):
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    ko = now + timedelta(hours=3)
    day = {"leagues": [{"id": 943229, "primaryId": 73, "name": "Synthetic Europa", "matches": [
        {"id": 6112353, "home": {"id": 1, "name": "Hoffenheim"}, "away": {"id": 2, "name": "Beşiktaş"},
         "status": {"utcTime": ko.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "started": False, "finished": False, "cancelled": False}}]}]}
    day_path = tmp_path / "day.json"
    day_path.write_text(json.dumps(day), encoding="utf-8")
    row = fixture_row("idA", "TSG Hoffenheim", "Besiktas JK")
    row["startTime"] = ko.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    server = Server([row], [{"fixtureId": "idA", "tournamentId": 7, "bookmakerOdds": {"pinnacle": book_full()}}])

    monkeypatch.setenv("ODDSPAPI_API_KEY", KEY)
    monkeypatch.setattr(col.httpx, "Client", lambda *a, **k: _REAL_CLIENT(transport=httpx.MockTransport(server)))
    monkeypatch.setattr(col, "RequestBudget", lambda max_requests=8, min_interval=1.1: oc.RequestBudget(max_requests=max_requests, min_interval=0))
    out = tmp_path / "odds" / "2026-10-15.jsonl"
    cache = tmp_path / "cache.json"
    assert col.main(["--date", "2026-10-15", "--fixtures-json", str(day_path), "--bookmakers", "pinnacle", "--out", str(out), "--markets-cache", str(cache)]) == 0
    assert cache.exists()  # /v4/markets cached next to the test output, never in the repo's data/odds
    lines = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 1 and lines[0]["bookmaker"] == "pinnacle" and lines[0]["fotmob_match_id"] == "6112353"
    run_report = json.loads(out.with_name("2026-10-15.oddspapi_run.json").read_text(encoding="utf-8"))
    assert run_report["snapshots_written"] == 1 and run_report["requests_used"] == 3
    assert KEY not in out.read_text(encoding="utf-8") + json.dumps(run_report) + capsys.readouterr().out
