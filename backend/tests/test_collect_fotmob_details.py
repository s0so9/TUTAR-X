"""Unit tests for the FotMob match-details training collector parser.

The payload below is a SYNTHETIC TEST FIXTURE shaped like a FotMob matchDetails
response (structure copied from real responses, values made up for the test).
It is not football data and is never written to the dataset.
"""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "data_collection" / "collect_fotmob_details.py"
_spec = importlib.util.spec_from_file_location("collect_fotmob_details", _SCRIPT)
collector = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(collector)


def _stat(key, value):
    return {"key": key, "stat": {"value": value, "type": "integer"}}


def _fixture(with_xg=True, finished=True):
    top_stats = [{"title": "Ball possession", "key": "BallPossesion", "stats": [40, 60], "type": "graph"}]
    if with_xg:
        top_stats.append({"title": "Expected goals (xG)", "key": "expected_goals", "stats": ["0.94", "1.28"], "type": "text"})
    groups = [
        {"key": "top_stats", "stats": top_stats},
        # section header row: must be ignored (values always [null, null])
        {"key": "expected_goals", "stats": [{"key": "expected_goals", "stats": [None, None], "type": "title"}]},
    ]
    return {
        "general": {
            "matchId": "111", "leagueId": 900, "parentLeagueId": 47, "finished": finished,
            "matchTimeUTCDate": "2026-01-01T15:00:00.000Z",
            "homeTeam": {"id": 1, "name": "Home FC (fixture)"}, "awayTeam": {"id": 2, "name": "Away FC (fixture)"},
        },
        "header": {"teams": [{"id": 1, "score": 2}, {"id": 2, "score": 0}], "status": {"finished": finished}},
        "content": {
            "stats": {"Periods": {"All": {"stats": groups}}},
            "lineup": {
                "lineupType": "standard",
                "homeTeam": {
                    "id": 1, "formation": "4-3-3", "totalStarterMarketValue": 1000,
                    "starters": [
                        {"id": 10, "name": "Starter A", "positionId": 115, "usualPlayingPositionId": 3,
                         "marketValue": 500, "performance": {"rating": 7.7,
                                                             "substitutionEvents": [{"time": 80, "type": "subOut"}]}},
                    ],
                    "subs": [
                        {"id": 11, "name": "Sub B", "usualPlayingPositionId": 2,
                         "performance": {"substitutionEvents": [{"time": 80, "type": "subIn"}]}},
                        {"id": 12, "name": "Unused C", "usualPlayingPositionId": 1},
                    ],
                    "unavailable": [{"id": 13, "name": "Injured D", "unavailability": {"type": "injury", "expectedReturn": "Soon"}}],
                },
                "awayTeam": {"id": 2, "formation": None, "starters": [], "subs": []},
            },
            "playerStats": {
                "10": {"isGoalkeeper": False, "shotmap": [{}, {}], "stats": [{"key": "top_stats", "stats": {
                    "FotMob rating": _stat("rating_title", 7.67), "Minutes played": _stat("minutes_played", 80),
                    "Goals": _stat("goals", 1), "Assists": _stat("assists", 0),
                    "Expected goals (xG)": _stat("expected_goals", 0.4), "Total shots": _stat("total_shots", 2)}}]},
                # played, no shots: FotMob omits xG/shots keys -> must stay null, not 0
                "11": {"isGoalkeeper": False, "shotmap": [], "stats": [{"key": "top_stats", "stats": {
                    "Minutes played": _stat("minutes_played", 10), "Goals": _stat("goals", 0)}}]},
                "12": {"isGoalkeeper": False, "shotmap": []},
            },
        },
    }


META = {"match_provider_id": "111", "competition_provider_id": 47, "db_home_team_provider_id": 1,
        "db_away_team_provider_id": 2, "db_home_score": 2, "db_away_score": 0}


def test_parse_match_team_level_fields():
    rec = collector.parse_match(_fixture(), META, "2026-10-13T00:00:00+00:00")
    assert rec["home_xg"] == 0.94 and rec["away_xg"] == 1.28
    assert rec["home_score"] == 2 and rec["away_score"] == 0
    assert rec["source_league_id"] == 900 and rec["competition_provider_id"] == 47
    assert "expected_goals" in rec["team_stats"] and rec["team_stats"]["expected_goals"] == ["0.94", "1.28"]
    assert all(rec["db_check"].values())
    assert rec["unavailable"][0]["type"] == "injury"


def test_missing_team_xg_is_null_not_zero():
    rec = collector.parse_match(_fixture(with_xg=False), META, "x")
    assert rec["home_xg"] is None and rec["away_xg"] is None


def test_player_fields_and_null_semantics():
    rec = collector.parse_match(_fixture(), META, "x")
    by_id = {p["player_id"]: p for p in rec["players"]}
    a, b, c = by_id[10], by_id[11], by_id[12]
    assert a["rating"] == 7.67 and a["rating_source"] == "playerStats"
    assert a["minutes_played"] == 80 and a["goals"] == 1 and a["assists"] == 0
    assert a["xg"] == 0.4 and a["shots"] == 2 and a["shotmap_count"] == 2
    assert a["is_starter"] and a["position"] == "FWD" and a["position_id"] == 115 and a["sub_out_minute"] == 80
    # played without shots: source omits the keys -> null (never invented as 0)
    assert b["appeared"] and b["sub_in_minute"] == 80 and b["goals"] == 0
    assert b["xg"] is None and b["shots"] is None and b["rating"] is None and b["shotmap_count"] == 0
    # unused substitute: no stats at all
    assert not c["appeared"] and not c["stats_available"] and c["minutes_played"] is None


def test_unfinished_match_is_rejected():
    with pytest.raises(collector.ParseError):
        collector.parse_match(_fixture(finished=False), META, "x")


def test_parse_competitions_sets():
    assert collector.parse_competitions("A")[:2] == [47, 87]
    combined = collector.parse_competitions("A,B,47")
    assert len(combined) == len(set(combined)) == 20


def test_resume_reads_done_ids_and_tolerates_partial_line(tmp_path):
    out = tmp_path / "o.jsonl"
    out.write_text('{"match_provider_id": "1"}\n{"match_provider_id": "2"}\n{"match_prov', encoding="utf-8")
    assert collector.read_done_ids(out) == {"1", "2"}


# --------------------------------------------------------------------------
# Fixture-list source (--source fixtures). The league payload below is a
# SYNTHETIC TEST FIXTURE shaped like a FotMob /api/data/leagues response
# (structure copied from real responses, ids/teams/scores made up for the test).
# --------------------------------------------------------------------------


def _fixture_match(mid, utc, finished=True, cancelled=False, awarded=False, score="1 - 0"):
    return {
        "id": str(mid), "round": "1",
        "home": {"id": "1", "name": "Home FC (fixture)"}, "away": {"id": "2", "name": "Away FC (fixture)"},
        "status": {"utcTime": utc, "finished": finished, "started": finished, "cancelled": cancelled,
                   "awarded": awarded, "scoreStr": score if finished else None},
    }


def _league_fixture(selected="2024/2025", league_id=47):
    return {
        "details": {"id": league_id, "name": "Fixture League (synthetic)", "country": "XXX", "selectedSeason": selected},
        "allAvailableSeasons": ["2025/2026", "2024/2025"],
        "fixtures": {"allMatches": [
            _fixture_match(3, "2025-01-03T15:00:00Z"),
            _fixture_match(1, "2025-01-01T15:00:00Z", score="2 - 0"),
            _fixture_match(2, "2025-01-02T15:00:00Z", finished=False, cancelled=True),
            _fixture_match(4, "2025-01-04T15:00:00Z", awarded=True, score="3 - 0"),
            _fixture_match(5, "2025-06-01T15:00:00Z", finished=False),
            _fixture_match(1, "2025-01-01T15:00:00Z", score="2 - 0"),  # listed twice
        ]},
    }


def _history_meta(mid="111", awarded=False):
    return {"match_provider_id": mid, "competition_provider_id": 47, "season": "2024/2025", "source": "fixtures",
            "fixture_utc_time": "2025-01-01T15:00:00Z", "fixture_home_team_provider_id": 1,
            "fixture_away_team_provider_id": 2, "fixture_score_str": "2 - 0", "fixture_awarded": awarded}


def test_parse_fixture_list_keeps_finished_not_cancelled_and_flags_awarded():
    metas, summary = collector.parse_fixture_list(_league_fixture(), 47, "2024/2025")
    # sorted by kick-off; cancelled (2), unfinished (5) and the repeated id (1) are dropped
    assert [m["match_provider_id"] for m in metas] == ["1", "3", "4"]
    assert summary == {"listed": 6, "kept": 3, "awarded": 1, "cancelled": 1, "not_finished": 1,
                       "duplicates": 1, "no_id": 0}
    by_id = {m["match_provider_id"]: m for m in metas}
    assert by_id["4"]["fixture_awarded"] is True and by_id["1"]["fixture_awarded"] is False
    assert by_id["1"]["fixture_home_team_provider_id"] == 1 and by_id["1"]["fixture_away_team_provider_id"] == 2
    assert by_id["1"]["fixture_score_str"] == "2 - 0" and by_id["1"]["fixture_utc_time"] == "2025-01-01T15:00:00Z"
    assert all(m["competition_provider_id"] == 47 and m["season"] == "2024/2025" and m["source"] == "fixtures"
               for m in metas)


def test_parse_fixture_list_rejects_other_season_or_league():
    with pytest.raises(collector.LeagueSeasonError):
        collector.parse_fixture_list(_league_fixture(selected="2025/2026"), 47, "2024/2025")
    with pytest.raises(collector.LeagueSeasonError):
        collector.parse_fixture_list(_league_fixture(league_id=87), 47, "2024/2025")
    with pytest.raises(collector.LeagueSeasonError):
        collector.parse_fixture_list({"details": {"selectedSeason": "2024/2025"}}, 47, "2024/2025")


def test_league_cache_path_seasons_and_target13():
    assert collector.league_cache_path(Path("c"), 47, "2024/2025").name == "47_2024-2025.json.gz"
    assert collector.league_cache_path(Path("c"), 59, "2024").name == "59_2024.json.gz"
    assert collector.parse_seasons("2024/2025, 2023/2024,2024/2025,2024") == ["2024/2025", "2023/2024", "2024"]
    with pytest.raises(ValueError):
        collector.parse_seasons("24/25")
    t13 = collector.parse_competitions("TARGET13")
    assert len(t13) == len(set(t13)) == 13 and {47, 87, 55, 54, 53, 57, 61, 40, 71, 122, 42, 73, 10216} == set(t13)
    assert collector.parse_competitions("target13,48")[-1] == 48


def test_score_from_fixture_string():
    assert collector._score_from_str("2 - 1") == (2, 1)
    assert collector._score_from_str("(4) 1 - 1 (3)") == (None, None)  # not compared, never guessed
    assert collector._score_from_str(None) == (None, None)


def test_history_record_has_season_and_null_db_check():
    rec = collector.parse_match(_fixture(), _history_meta(), "x")
    keys = list(rec.keys())
    assert rec["season"] == "2024/2025" and keys.index("season") == keys.index("competition_provider_id") + 1
    assert rec["db_check"] is None and rec["competition_provider_id"] == 47 and rec["awarded"] is False
    # same parsed values as the db source apart from season/db_check
    db_rec = collector.parse_match(_fixture(), META, "x")
    assert {k: v for k, v in rec.items() if k not in ("season", "db_check")} == {
        k: v for k, v in db_rec.items() if k != "db_check"}
    # an awarded match in the fixture list is flagged even when the details header does not say so
    assert collector.parse_match(_fixture(), _history_meta(awarded=True), "x")["awarded"] is True


def test_cli_defaults_per_source():
    db = collector.parse_args(["--base-url", "http://unused"])
    assert db.source == "db" and Path(db.output) == collector.DEFAULT_OUT and Path(db.errors) == collector.DEFAULT_ERR
    assert db.concurrency == 3 and db.delay == 0.3 and db.reuse_raw is False
    fx = collector.parse_args(["--source", "fixtures", "--base-url", "http://unused", "--concurrency", "5",
                               "--delay", "0.1"])
    assert Path(fx.output) == collector.DEFAULT_HISTORY_OUT and Path(fx.errors) == collector.DEFAULT_HISTORY_ERR
    assert fx.concurrency == 2 and fx.delay == 0.4 and fx.reuse_raw is True
    assert fx.seasons_list == ["2024/2025", "2023/2024", "2022/2023"]


def test_atomic_write_leaves_no_temp_file(tmp_path):
    target = tmp_path / "1.json.gz"
    collector._atomic_write_bytes(target, b"first")
    collector._atomic_write_bytes(target, b"second")
    assert target.read_bytes() == b"second" and [p.name for p in tmp_path.iterdir()] == ["1.json.gz"]


def _write_gz_json(path, obj):
    import gzip
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(obj).encode("utf-8")))


def _details_for(mid):
    payload = _fixture()
    payload["general"]["matchId"] = str(mid)
    return payload


def test_from_raw_and_coverage_for_fixture_source(tmp_path, capsys):
    import json

    leagues, raw = tmp_path / "leagues", tmp_path / "raw"
    _write_gz_json(collector.league_cache_path(leagues, 47, "2024/2025"), _league_fixture())
    for mid in ("1", "4"):  # match 3 has no raw response -> stays missing
        _write_gz_json(raw / f"{mid}.json.gz", _details_for(mid))
    out, err = tmp_path / "hist.jsonl", tmp_path / "hist_err.jsonl"
    argv = ["--source", "fixtures", "--seasons", "2024/2025", "--competitions", "47", "--base-url", "http://unused",
            "--leagues-dir", str(leagues), "--raw-dir", str(raw), "--output", str(out), "--errors", str(err)]
    assert collector.main(argv + ["--from-raw"]) == 0
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["match_provider_id"] for r in rows] == ["1", "4"]
    assert all(r["season"] == "2024/2025" and r["db_check"] is None for r in rows)
    assert [r["awarded"] for r in rows] == [False, True]
    # re-running skips ids already in the output (resumable)
    assert collector.main(argv + ["--from-raw"]) == 0
    assert len(out.read_text(encoding="utf-8").splitlines()) == 2

    capsys.readouterr()
    assert collector.main(argv + ["--coverage"]) == 0
    table = capsys.readouterr().out
    first_row = next(line for line in table.splitlines() if line.startswith("| 47 |"))
    cells = [c.strip() for c in first_row.strip("|").split("|")]
    # id, name, season, fixture list, collected, missing, error ids, line-ups, ratings, team xG, player xG,
    # unavailable, awarded, rated appearances, avg players, mismatch
    assert cells[2] == "2024/2025" and cells[3] == "3" and cells[4] == "2" and cells[5] == "1"
    assert cells[7] == "100.0%" and cells[12] == "1"
    # match 4: fixture list says 3 - 0, its details payload says 2 - 0 -> exactly one mismatch reported
    assert cells[15] == "1"
    assert "Duplicate match ids in the output: 0" in table


# --------------------------------------------------------------------------
# Politeness / stop rules of the HTTP layer. Offline: httpx.MockTransport
# answers (SYNTHETIC responses), the shared limiter is replaced by stubs so the
# real limiter state file is never touched, and sleeps are skipped.
# --------------------------------------------------------------------------


def _offline_http(monkeypatch):
    import asyncio

    calls = {"acquire": 0, "report_429": []}

    async def fake_acquire(*_a, **_k):
        calls["acquire"] += 1

    real_sleep = asyncio.sleep

    async def no_sleep(_seconds):
        await real_sleep(0)

    monkeypatch.setattr(collector.fotmob_rate, "acquire_async", fake_acquire)
    monkeypatch.setattr(collector.fotmob_rate, "report_429", lambda s: calls["report_429"].append(s))
    monkeypatch.setattr(collector.asyncio, "sleep", no_sleep)
    return calls


def _run_fetch(responses):
    import asyncio

    import httpx

    seq = iter(responses)

    async def go():
        transport = httpx.MockTransport(lambda request: next(seq))
        async with httpx.AsyncClient(transport=transport, base_url="http://mock.invalid") as client:
            return await collector.fetch_json(client, "/api/x", {}, collector.Throttle(), 3)

    return asyncio.run(go())


def test_fetch_429_is_reported_to_shared_limiter_and_retried(monkeypatch):
    import httpx

    calls = _offline_http(monkeypatch)
    data, raw, kind, _detail, attempts = _run_fetch(
        [httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, json={"ok": 1})])
    assert data == {"ok": 1} and kind is None and attempts == 2
    assert calls["report_429"] == [7.0] and calls["acquire"] == 2  # limiter before EVERY request
    _run_fetch([httpx.Response(429), httpx.Response(200, json={})])
    assert calls["report_429"] == [7.0, 60.0]  # no Retry-After -> 60 s


def test_fetch_stops_on_403_and_challenge_page(monkeypatch):
    import httpx

    _offline_http(monkeypatch)
    assert _run_fetch([httpx.Response(403)])[2] == "blocked_http_403"
    assert _run_fetch([httpx.Response(200, html="<html>Just a moment...</html>")])[2] == "blocked_challenge"
    assert _run_fetch([httpx.Response(503, headers={"cf-mitigated": "challenge"})])[2] == "blocked_challenge"
    assert {"blocked_http_403", "blocked_challenge"} == collector.BLOCKED_KINDS


def test_shared_limiter_lock_error_is_retried_not_skipped(monkeypatch):
    import asyncio

    _offline_http(monkeypatch)
    attempts = {"n": 0}

    async def flaky_acquire(*_a, **_k):
        attempts["n"] += 1
        if attempts["n"] < 3:  # Windows mkdir/rmdir race of the limiter's lock directory
            raise PermissionError(5, "Access is denied (simulated)")

    monkeypatch.setattr(collector.fotmob_rate, "acquire_async", flaky_acquire)
    asyncio.run(collector._acquire_shared_slot())
    assert attempts["n"] == 3
