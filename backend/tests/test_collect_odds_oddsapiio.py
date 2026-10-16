"""Tests for scripts/data_collection/collect_odds_oddsapiio.py (Odds-API.io v3).

Every response below is a SYNTHETIC TEST FIXTURE shaped after the vendor's OpenAPI document and quickstart examples
(events: id/home/away/date/league; odds/multi: bookmakers -> [{name: ML | Totals | Both Teams To Score | Double
Chance, odds: [...], updatedAt}]). Prices, teams and ids are invented. The collector has NOT been run against the live
service (no API key exists yet); these tests only prove the parsing, mapping, batching, quota and key-handling logic.
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
import collect_odds_oddsapiio as col  # noqa: E402

KEY = "SYNTHETIC-KEY-0123456789"
_REAL_CLIENT = httpx.Client  # the CLI test replaces httpx.Client (same module object), keep the real class for the mock
T0 = datetime(2026, 10, 15, 19, 0, tzinfo=timezone.utc)


def ml(home, draw, away, ts="2026-10-15T11:50:00Z"):
    return {"name": "ML", "odds": [{"home": home, "draw": draw, "away": away}], "updatedAt": ts}


def totals(*lines, key="hdp", ts="2026-10-15T11:51:00Z"):
    return {"name": "Totals", "odds": [{key: ln, "over": o, "under": u} for ln, o, u in lines], "updatedAt": ts}


def btts(yes, no):
    return {"name": "Both Teams To Score", "odds": [{"yes": yes, "no": no}], "updatedAt": "2026-10-15T11:52:00Z"}


def dc(x1, x12, x2):
    return {"name": "Double Chance", "odds": [{"1X": x1, "12": x12, "X2": x2}], "updatedAt": "2026-10-15T11:49:00Z"}


def full_book():
    return [
        ml("1.95", "3.55", "3.60"),
        totals((2.5, "1.80", "1.90"), (1.5, "1.25", "3.60"), (3.5, "2.90", "1.38"), (0.5, "1.05", "9.00")),
        btts("1.65", "2.10"),
        dc("1.25", "1.30", "1.75"),
        {"name": "ML HT", "odds": [{"home": "2.9", "draw": "2.1", "away": "4.5"}]},   # half-time variant must be ignored
    ]


def event(eid, home, away, minutes=0, league_slug="synthetic-league"):
    return {"id": eid, "sport": {"name": "Football", "slug": "football"}, "league": {"name": "Synthetic League", "slug": league_slug},
            "home": home, "away": away, "date": oc.iso_z(T0 + timedelta(minutes=minutes)), "status": "pending"}


def odds_event(eid, home, away, books):
    return {"id": eid, "home": home, "away": away, "date": oc.iso_z(T0), "status": "pending",
            "urls": {b: "https://example.invalid/secret-affiliate-link" for b in books}, "bookmakers": books}


def fx(mid, home, away, minutes=0):
    return oc.Fixture(match_id=mid, home=home, away=away, kickoff=T0 + timedelta(minutes=minutes), competition_id=73)


# --------------------------------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------------------------------
def test_parse_events_drops_incomplete_entries():
    raw = [event(1, "Alpha", "Beta"), {"id": 2, "home": "No", "away": "Date"}, {"home": "No", "away": "Id", "date": "2026-10-15T19:00:00Z"}, "junk"]
    out = col.parse_events(raw)
    assert [e.event_id for e in out] == [1] and out[0].kickoff == T0 and out[0].league == "synthetic-league"
    assert col.parse_events({"error": "x"}) == []


def test_parse_bookmaker_markets_full_book_and_ignores_half_time_and_untracked_lines():
    markets, rejected, updated = col.parse_bookmaker_markets(full_book())
    assert set(markets) == {"1x2", "ou_1.5", "ou_2.5", "ou_3.5", "btts", "double_chance"}
    assert rejected == {}
    assert markets["1x2"]["odds"] == {"home": 1.95, "draw": 3.55, "away": 3.6}
    assert markets["ou_2.5"]["odds"] == {"over": 1.8, "under": 1.9}
    assert markets["double_chance"]["odds"] == {"1x": 1.25, "12": 1.3, "x2": 1.75}
    assert updated == "2026-10-15T11:52:00Z"  # newest updatedAt of the markets read


def test_parse_totals_line_may_come_as_max():
    markets, _, _ = col.parse_bookmaker_markets([totals((2.5, "1.80", "1.90"), key="max")])
    assert markets["ou_2.5"]["odds"] == {"over": 1.8, "under": 1.9}


def test_parse_rejects_incomplete_or_implausible_markets_without_repairing():
    markets, rejected, _ = col.parse_bookmaker_markets([
        ml("1.95", None, "3.60"),                 # draw missing
        btts("1.02", "1.02"),                      # overround 1.96
        totals((2.5, "1.80", "abc")),              # under unreadable
        dc("1.25", "1.30", "1.75"),
    ])
    assert set(markets) == {"double_chance"}
    assert set(rejected) == {"1x2", "btts", "ou_2.5"}
    assert "draw" in rejected["1x2"]


def test_parse_event_odds_keeps_bookmakers_with_usable_markets_only():
    resp = odds_event(1, "Alpha", "Beta", {"Iddaa": full_book(), "Bet365": [ml("1.9", "3.6", "3.9")], "Empty": [], "Broken": [ml(None, None, None)]})
    parsed = {p["bookmaker"]: p for p in col.parse_event_odds(resp)}
    assert set(parsed) == {"Iddaa", "Bet365"}
    assert set(parsed["Bet365"]["markets"]) == {"1x2"}
    assert col.parse_event_odds({"bookmakers": None}) == [] and col.parse_event_odds("junk") == []


# --------------------------------------------------------------------------------------------------
# request budget
# --------------------------------------------------------------------------------------------------
def test_request_budget_cap_and_min_interval():
    sleeps, t = [], [100.0]
    b = col.RequestBudget(max_requests=2, min_interval=1.0, sleep=lambda s: sleeps.append(round(s, 3)), clock=lambda: t[0])
    b.before()
    t[0] += 0.25
    b.before()
    assert sleeps == [0.75]
    with pytest.raises(col.QuotaStop):
        b.before()
    assert b.used == 2


def test_api_get_errors_never_contain_the_key():
    def handler(request: httpx.Request):
        return httpx.Response(403, text=f"forbidden for {request.url}")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(col.OddsApiError) as ei:
            col.api_get(client, "/events", {"sport": "football"}, KEY, col.RequestBudget(min_interval=0))
    assert KEY not in str(ei.value) and "403" in str(ei.value)


def test_api_get_network_error_is_redacted():
    def handler(request: httpx.Request):
        raise httpx.ConnectError(f"cannot connect to {request.url}", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(col.OddsApiError) as ei:
            col.api_get(client, "/events", {}, KEY, col.RequestBudget(min_interval=0))
    assert KEY not in str(ei.value)


def test_api_get_429_is_quota_stop():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429, headers={"x-ratelimit-remaining": "0"}))) as client:
        with pytest.raises(col.QuotaStop):
            col.api_get(client, "/odds/multi", {}, KEY, col.RequestBudget(min_interval=0))


def test_selected_bookmakers_parses_names_and_swallows_failures():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[{"name": "Iddaa", "active": True}, "Bet365", {"x": 1}]))) as c:
        assert col.selected_bookmakers(c, KEY, col.RequestBudget(min_interval=0)) == ["Iddaa", "Bet365"]
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403, text="plan"))) as c:
        assert col.selected_bookmakers(c, KEY, col.RequestBudget(min_interval=0)) == []


# --------------------------------------------------------------------------------------------------
# collect() flow over a mock transport
# --------------------------------------------------------------------------------------------------
class Server:
    """Mock of the three endpoints; records requests."""

    def __init__(self, events, odds_by_event, fail_odds_after=None):
        self.events, self.odds_by_event, self.fail_odds_after = events, odds_by_event, fail_odds_after
        self.requests = []

    def __call__(self, request: httpx.Request):
        params = dict(request.url.params)
        self.requests.append((request.url.path, params))
        assert params.get("apiKey") == KEY  # key is sent as the documented query parameter
        if request.url.path.endswith("/events"):
            skip, limit = int(params.get("skip", 0)), int(params["limit"])
            assert params["sport"] == "football" and params["status"] == "pending"
            return httpx.Response(200, json=self.events[skip : skip + limit])
        if request.url.path.endswith("/odds/multi"):
            n_odds = sum(1 for p, _ in self.requests if p.endswith("/odds/multi"))
            if self.fail_odds_after is not None and n_odds > self.fail_odds_after:
                return httpx.Response(429, text="rate limit")
            ids = params["eventIds"].split(",")
            assert len(ids) <= 10
            return httpx.Response(200, json=[self.odds_by_event[i] for i in ids if i in self.odds_by_event], headers={"x-ratelimit-remaining": "88"})
        return httpx.Response(404)


def run(server, fixtures, bookmakers=("Iddaa", "Bet365"), max_requests=40):
    with httpx.Client(transport=httpx.MockTransport(server)) as client:
        budget = col.RequestBudget(max_requests=max_requests, min_interval=0)
        return col.collect(client, KEY, fixtures, list(bookmakers), budget, clock=lambda: T0 - timedelta(hours=7))


def test_collect_maps_by_names_and_kickoff_and_writes_snapshots():
    books = {"Iddaa": full_book(), "Bet365": [ml("1.91", "3.9", "3.5"), btts("1.44", "2.63")]}
    server = Server(
        events=[event(1001, "TSG 1899 Hoffenheim", "Besiktas JK"), event(1002, "Totally", "Different", minutes=0), event(1003, "RB Salzburg", "AC Milan", minutes=-135)],
        odds_by_event={"1001": odds_event(1001, "TSG 1899 Hoffenheim", "Besiktas JK", books), "1003": odds_event(1003, "RB Salzburg", "AC Milan", {"Iddaa": [ml("3.40", "3.60", "2.05")]})},
    )
    fixtures = [fx("6112353", "Hoffenheim", "Beşiktaş"), fx("6112294", "Salzburg", "Milan", minutes=-135), fx("777", "Nobody FC", "Nowhere United", minutes=-60)]
    snaps, report = run(server, fixtures)

    paths = [p.replace("/v3", "") for p, _ in server.requests]
    assert paths == ["/events", "/odds/multi"]  # one events page, ONE odds request for both mapped events
    multi = server.requests[1][1]
    assert multi["eventIds"] == "1001,1003" and multi["bookmakers"] == "Iddaa,Bet365"

    assert {s["fotmob_match_id"] for s in snaps} == {"6112353", "6112294"}
    iddaa = next(s for s in snaps if s["fotmob_match_id"] == "6112353" and s["bookmaker"] == "Iddaa")
    assert iddaa["source"] == "odds_api_io" and iddaa["region"] is None and iddaa["odds_type"] == "pre_match"
    assert iddaa["mapping"]["method"] == "teams+kickoff" and iddaa["mapping"]["confidence"] == 1.0 and iddaa["mapping"]["vendor_event_id"] == 1001
    assert set(iddaa["markets"]) == {"1x2", "ou_1.5", "ou_2.5", "ou_3.5", "btts", "double_chance"} and iddaa["missing_markets"] == []
    assert iddaa["odds_updated_at"] == "2026-10-15T11:52:00Z" and iddaa["seconds_to_kickoff"] == 7 * 3600
    bet365 = next(s for s in snaps if s["bookmaker"] == "Bet365")
    assert set(bet365["missing_markets"]) == {"double_chance", "ou_1.5", "ou_2.5", "ou_3.5"}

    assert [u["fotmob_match_id"] for u in report["unmapped"]] == ["777"] and "reason" in report["unmapped"][0]
    assert {m["fotmob_match_id"] for m in report["mapped"]} == {"6112353", "6112294"}
    assert report["ratelimit_remaining_header"] == "88" and report["requests_used"] == 2
    blob = json.dumps(snaps) + json.dumps(report)
    assert KEY not in blob and "secret-affiliate-link" not in blob  # no key, no vendor links in the data


def test_collect_batches_of_ten_events_per_odds_request():
    n = 12
    events = [event(2000 + i, f"Home {chr(65 + i)}{chr(65 + i)}", f"Away {chr(75 + i)}{chr(75 + i)}", minutes=i) for i in range(n)]
    fixtures = [fx(str(i), f"Home {chr(65 + i)}{chr(65 + i)}", f"Away {chr(75 + i)}{chr(75 + i)}", minutes=i) for i in range(n)]
    odds = {str(2000 + i): odds_event(2000 + i, "h", "a", {"Iddaa": [ml("2.0", "3.4", "3.6")]}) for i in range(n)}
    server = Server(events, odds)
    snaps, report = run(server, fixtures)
    multis = [p for path, p in server.requests if path.endswith("/odds/multi")]
    assert [len(m["eventIds"].split(",")) for m in multis] == [10, 2]
    assert len(snaps) == n and report["odds_requests"] == 2


def test_collect_event_without_odds_is_reported_not_invented():
    server = Server([event(1, "Alpha United", "Beta City")], {"1": odds_event(1, "Alpha United", "Beta City", {"Iddaa": []})})
    snaps, report = run(server, [fx("10", "Alpha United", "Beta City")])
    assert snaps == [] and report["no_odds_for_event"] == ["10"]


def test_collect_event_listing_paginates():
    events = [event(i, f"Club {i}x", f"Club {i}y", minutes=0) for i in range(5)]
    server = Server(events, {})
    with httpx.Client(transport=httpx.MockTransport(server)) as client:
        got = col.list_events(client, KEY, T0, T0, col.RequestBudget(min_interval=0), page_size=2)
    assert len(got) == 5 and [p["skip"] for _, p in server.requests] == ["0", "2", "4"]


def test_collect_stops_on_429_and_keeps_first_batch():
    n = 12
    events = [event(3000 + i, f"Home {chr(65 + i)}{chr(65 + i)}", f"Away {chr(75 + i)}{chr(75 + i)}", minutes=i) for i in range(n)]
    fixtures = [fx(str(i), f"Home {chr(65 + i)}{chr(65 + i)}", f"Away {chr(75 + i)}{chr(75 + i)}", minutes=i) for i in range(n)]
    odds = {str(3000 + i): odds_event(3000 + i, "h", "a", {"Iddaa": [ml("2.0", "3.4", "3.6")]}) for i in range(n)}
    snaps, report = run(Server(events, odds, fail_odds_after=1), fixtures)
    assert len(snaps) == 10 and "429" in report["stopped"]


def test_collect_request_cap_stops_cleanly():
    server = Server([event(1, "Alpha United", "Beta City")], {"1": odds_event(1, "Alpha United", "Beta City", {"Iddaa": [ml("2.0", "3.4", "3.6")]})})
    snaps, report = run(server, [fx("10", "Alpha United", "Beta City")], max_requests=1)
    assert snaps == [] and "cap" in report["stopped"]


def test_collect_nothing_to_do_makes_no_request():
    server = Server([], {})
    snaps, report = run(server, [])
    assert snaps == [] and server.requests == []


class _FastBudget(col.RequestBudget):
    def __init__(self, max_requests=40):
        super().__init__(max_requests=max_requests, min_interval=0)


# --------------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------------
def test_main_without_key_exits_5_and_explains(monkeypatch, capsys):
    monkeypatch.delenv("ODDS_API_IO_KEY", raising=False)
    monkeypatch.setattr(col.httpx, "Client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no client without a key")))
    assert col.main(["--date", "2026-10-15"]) == 5
    err = capsys.readouterr().err
    assert "ODDS_API_IO_KEY" in err and "odds-api.io" in err


def test_main_end_to_end_with_mock_service_writes_files_and_never_leaks_key(monkeypatch, tmp_path, capsys):
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    ko = now + timedelta(hours=3)
    day = {"leagues": [{"id": 943229, "primaryId": 73, "name": "Synthetic Europa", "matches": [
        {"id": 6112353, "home": {"id": 1, "name": "Hoffenheim"}, "away": {"id": 2, "name": "Beşiktaş"},
         "status": {"utcTime": ko.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "started": False, "finished": False, "cancelled": False}},
        {"id": 6112294, "home": {"id": 3, "name": "Salzburg"}, "away": {"id": 4, "name": "Milan"},
         "status": {"utcTime": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z"), "started": True, "finished": False, "cancelled": False}},
    ]}]}
    day_path = tmp_path / "day.json"
    day_path.write_text(json.dumps(day), encoding="utf-8")
    ev = {"id": 1001, "league": {"slug": "x"}, "home": "TSG 1899 Hoffenheim", "away": "Besiktas JK", "date": ko.strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "pending"}
    server = Server([ev], {"1001": odds_event(1001, "TSG 1899 Hoffenheim", "Besiktas JK", {"Iddaa": full_book(), "Bet365": [ml("1.91", "3.9", "3.5")]})})

    def handler(request: httpx.Request):
        if request.url.path.endswith("/bookmakers/selected"):
            assert request.url.params["apiKey"] == KEY
            return httpx.Response(200, json=[{"name": "Iddaa", "active": True}, {"name": "Bet365", "active": True}])
        return server(request)

    monkeypatch.setenv("ODDS_API_IO_KEY", KEY)
    monkeypatch.setattr(col.httpx, "Client", lambda *a, **k: _REAL_CLIENT(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(col, "RequestBudget", _FastBudget)  # no 0.6 s pauses in the test
    out = tmp_path / "odds" / "2026-10-15.jsonl"
    assert col.main(["--date", "2026-10-15", "--fixtures-json", str(day_path), "--out", str(out)]) == 0

    lines = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
    assert {x["bookmaker"] for x in lines} == {"Iddaa", "Bet365"} and {x["fotmob_match_id"] for x in lines} == {"6112353"}  # started match skipped
    run_report = json.loads(out.with_name("2026-10-15.oddsapiio_run.json").read_text(encoding="utf-8"))
    assert run_report["snapshots_written"] == 2 and run_report["bookmakers_requested"] == ["Iddaa", "Bet365"] and run_report["requests_used"] == 3
    everything = out.read_text(encoding="utf-8") + json.dumps(run_report) + capsys.readouterr().out
    assert KEY not in everything

