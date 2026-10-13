"""Unit tests for the FotMob results-history collector (parsing, season rules, DB build).

Every payload below is a SYNTHETIC TEST FIXTURE shaped like a FotMob /api/data/leagues response
(structure copied from real responses, values made up). It is not football data and is never
written to the dataset: the DB build runs in pytest's tmp_path.
"""

import gzip
import importlib.util
import json
import sqlite3
from collections import Counter
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "data_collection" / "collect_fotmob_history_results.py"
_spec = importlib.util.spec_from_file_location("collect_fotmob_history_results", _SCRIPT)
hist = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hist)

FAKE_LEAGUE = 999001  # not a real FotMob league id


def _status(finished=True, started=True, cancelled=False, awarded=False, score="2 - 1", short="FT", long_key="finished", utc="2024-08-10T14:00:00Z"):
    return {"utcTime": utc, "finished": finished, "started": started, "cancelled": cancelled, "awarded": awarded,
            "scoreStr": score, "reason": {"short": short, "longKey": long_key}}


def _match(mid, home, away, status, rnd="1"):
    return {"id": str(mid), "round": rnd, "roundName": rnd, "home": {"id": str(home), "name": f"Team {home} (fixture)"},
            "away": {"id": str(away), "name": f"Team {away} (fixture)"}, "status": status}


def _payload(season, matches, playoff=None, league=FAKE_LEAGUE, seasons=("2025/2026", "2024/2025", "2020/2021")):
    return {"details": {"id": league, "name": "Fixture League", "country": "XXX", "type": "league", "selectedSeason": season},
            "allAvailableSeasons": list(seasons), "fixtures": {"allMatches": matches}, "playoff": playoff}


def test_season_roles():
    assert hist.season_role("2021/2022") == "core"
    assert hist.season_role("2024/2025") == "core"
    assert hist.season_role("2025/2026") == "boundary"
    assert hist.season_role("2020/2021") is None
    assert hist.season_role("2026/2027") is None
    assert hist.season_role("2021") == "core"
    assert hist.season_role("2025") == "core"
    assert hist.season_role("2020") is None
    assert hist.season_role("2026") is None
    targets, unrec = hist.classify_seasons(["2026", "2025", "2021", "2020", "2022 Apertura"])
    assert targets == [("2021", "core"), ("2025", "core")]
    assert unrec == ["2022 Apertura"]


def test_status_and_score_rules():
    assert hist.derive_status(_status()) == "FINISHED"
    assert hist.derive_status(_status(awarded=True, short="AW", long_key="awarded_win")) == "AWARDED"
    assert hist.derive_status(_status(finished=False, started=False, cancelled=True, short="Canc", long_key="cancelled")) == "CANCELLED"
    assert hist.derive_status(_status(finished=False, started=False, cancelled=True, short="PP", long_key="postponed")) == "POSTPONED"
    assert hist.derive_status(_status(finished=False, started=False, score=None, short="", long_key="")) == "NOT_PLAYED"
    assert hist.derive_status(_status(finished=False, started=True, short="Ab", long_key="abandoned")) == "ABANDONED"
    # FotMob's real shape of an abandoned match: finished AND cancelled, reason Ab / aborted
    assert hist.derive_status(_status(finished=True, cancelled=True, score="1 - 1", short="Ab", long_key="aborted")) == "ABANDONED"
    assert hist.parse_score("2 - 1") == (2, 1)
    assert hist.parse_score(" 10-0 ") == (10, 0)
    assert hist.parse_score("2 - 1 (4 - 3)") == (None, None)
    assert hist.parse_score(None) == (None, None)
    assert hist.normalise_utc("2024-02-20T20:00:00.000Z") == "2024-02-20T20:00:00Z"
    assert hist.normalise_utc("garbage") is None


def test_parse_season_scores_only_when_finished_and_bracket_only_matches():
    playoff = {"rounds": [{"stage": "final", "matchups": [{"matches": [
        {"matchId": 13, "home": {"id": 1, "name": "A"}, "away": {"id": 2, "name": "B"},
         "status": _status(score="0 - 0", short="Pen", long_key="afterpenalties", utc="2025-05-30T19:00:00.000Z")},
        {"matchId": 10, "home": {"id": 1}, "away": {"id": 2}, "status": _status()},  # already in allMatches
    ]}]}]}
    data = _payload("2024/2025", [
        _match(10, 1, 2, _status()),
        _match(10, 1, 2, _status()),  # repeated id inside allMatches
        _match(11, 3, 4, _status(finished=False, started=False, cancelled=True, score="1 - 1", short="Canc", long_key="cancelled")),
        _match(12, 5, 6, _status(awarded=True, score="3 - 0", short="AW", long_key="awarded_win")),
        _match(14, 7, 8, _status(finished=True, cancelled=True, score="1 - 1", short="Ab", long_key="aborted")),
    ], playoff=playoff)
    rows, stats = hist.parse_season(data, FAKE_LEAGUE, "2024/2025")
    by_id = {r["provider_id"]: r for r in rows}
    assert sorted(by_id) == [10, 11, 12, 13, 14]
    # the score at the moment of abandonment is not a result
    assert (by_id[14]["status"], by_id[14]["home_score"], by_id[14]["score_str"]) == ("ABANDONED", None, "1 - 1")
    assert stats["repeated_in_all_matches"] == 1 and stats["bracket_only"] == 1
    assert (by_id[10]["home_score"], by_id[10]["away_score"], by_id[10]["status"]) == (2, 1, "FINISHED")
    # a cancelled match never gets a score, even if scoreStr carries one
    assert (by_id[11]["home_score"], by_id[11]["away_score"], by_id[11]["status"]) == (None, None, "CANCELLED")
    assert (by_id[12]["home_score"], by_id[12]["awarded"], by_id[12]["status"]) == (3, 1, "AWARDED")
    assert by_id[13]["source"] == hist.SOURCE_BRACKET and by_id[13]["scheduled_at"] == "2025-05-30T19:00:00Z"


def test_response_problem_detects_season_fallback():
    data = _payload("2026/2027", [])
    assert hist.response_problem(data, FAKE_LEAGUE, "2024/2025") == "season_mismatch:2026/2027"
    assert hist.response_problem(data, FAKE_LEAGUE, None) is None
    assert hist.response_problem(data, 12345, None).startswith("league_mismatch")
    assert hist.response_problem({"error": "x"}, FAKE_LEAGUE, None) == "no_details"


def test_exclusion_rules():
    assert hist.exclusion_reason("Club Friendlies") == "club friendlies / friendlies"
    assert hist.exclusion_reason("Premier League U18") == "youth / U-xx"
    assert hist.exclusion_reason("Serie A Femminile") == "women's"
    assert hist.exclusion_reason("Premier League 2") == "reserve / B teams"
    assert hist.exclusion_reason("Challenger Pro League") is None
    assert hist.exclusion_reason("Premier League") is None
    assert hist.exclusion_reason("DFB Pokal") is None


def _write(raw_dir, season, data):
    p = hist.cache_path(FAKE_LEAGUE, season, raw_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(gzip.compress(json.dumps(data).encode()))


def test_build_history_db_partitions_at_cutoff_and_records_duplicates(tmp_path):
    raw_dir = tmp_path / "raw"
    _write(raw_dir, "2024/2025", _payload("2024/2025", [
        _match(100, 1, 2, _status(utc="2025-05-01T18:00:00Z")),
        _match(101, 2, 1, _status(finished=False, started=False, score=None, short="PP", long_key="postponed", utc="2025-05-08T18:00:00Z")),
    ]))
    _write(raw_dir, "2025/2026", _payload("2025/2026", [
        _match(200, 1, 3, _status(utc="2025-06-28T18:00:00Z")),  # boundary season, before cutoff -> kept
        _match(201, 3, 1, _status(utc="2025-08-01T18:00:00Z")),  # after cutoff -> matches_after_cutoff
        _match(100, 1, 2, _status(utc="2025-05-01T18:00:00Z")),  # same id as in 2024/2025 -> duplicate
    ]))
    # 2020/2021 is not a target season: even if cached it must be ignored
    _write(raw_dir, "2020/2021", _payload("2020/2021", [_match(300, 1, 2, _status(utc="2021-05-01T18:00:00Z"))]))
    selection = [{"provider_id": FAKE_LEAGUE, "db_name": "Fixture League", "decision": "included", "group": "context",
                  "reason": "test", "n_db_finished": 0, "n_db_connected": 0, "n_connected_teams": 0}]
    out = tmp_path / "history.db"
    result = hist.build_history_db(selection, out, raw_dir)
    assert result["summary"]["matches"] == 3 and result["summary"]["matches_after_cutoff"] == 1
    conn = sqlite3.connect(out)
    rows = dict((r[0], r[1:]) for r in conn.execute(
        "SELECT provider_id, season, status, home_score, away_score, scheduled_at FROM matches"))
    assert rows[100] == ("2024/2025", "FINISHED", 2, 1, "2025-05-01T18:00:00Z")
    assert rows[101] == ("2024/2025", "POSTPONED", None, None, "2025-05-08T18:00:00Z")
    assert rows[200][0] == "2025/2026"
    assert [r[0] for r in conn.execute("SELECT provider_id FROM matches_after_cutoff")] == [201]
    assert conn.execute("SELECT provider_id, same_score FROM duplicate_match_ids").fetchall() == [(100, 1)]
    seasons = {r[0]: r[1:] for r in conn.execute("SELECT season, season_role, n_matches, n_after_cutoff FROM seasons")}
    assert seasons == {"2024/2025": ("core", 2, 0), "2025/2026": ("boundary", 1, 1)}
    assert conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0] == 3
    conn.close()
    # idempotent: a second build gives the same counts
    again = hist.build_history_db(selection, out, raw_dir)
    assert again["summary"] == result["summary"]


_BUILD = Path(__file__).resolve().parents[1] / "scripts" / "data_collection" / "build_all_results.py"
_bspec = importlib.util.spec_from_file_location("build_all_results", _BUILD)
build_all = importlib.util.module_from_spec(_bspec)
_bspec.loader.exec_module(build_all)


def _synthetic_production_db(path):
    """SYNTHETIC production-shaped DB (only the columns build_all_results reads; values made up)."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE competitions (id TEXT PRIMARY KEY, provider_id TEXT, name TEXT);
        CREATE TABLE teams (id TEXT PRIMARY KEY, provider_id TEXT, name TEXT);
        CREATE TABLE matches (id TEXT PRIMARY KEY, provider_id TEXT, competition_id TEXT, home_team_id TEXT,
                              away_team_id TEXT, scheduled_at TEXT, status TEXT, home_score INTEGER,
                              away_score INTEGER, home_xg REAL, away_xg REAL);
        """
    )
    conn.execute("INSERT INTO competitions VALUES ('comp-uuid', ?, 'Fixture League stage name')", (str(FAKE_LEAGUE),))
    conn.executemany("INSERT INTO teams VALUES (?,?,?)", [("t1", "1", "A"), ("t3", "3", "C"), ("t-bad", "-1", "Bad id")])
    conn.executemany("INSERT INTO matches VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
        ("m1", "201", "comp-uuid", "t3", "t1", "2025-08-01 18:00:00.000000", "FINISHED", 2, 1, 1.25, 0.5),
        ("m2", "202", "comp-uuid", "t1", "t-bad", "2025-08-08 18:00:00.000000", "FINISHED", 1, 0, None, None),
        ("m3", "203", "comp-uuid", "t1", "t-no-row", "2025-08-15 18:00:00.000000", "FINISHED", 0, 1, None, None),
    ])
    conn.commit()
    conn.close()


def test_build_all_results_union_and_unmappable_production_rows(tmp_path):
    """history (< cutoff, results only) UNION production (FotMob ids); a production row whose team id is -1
    or whose team uuid has no teams row is reported in `conflicts`, never silently dropped."""
    raw_dir = tmp_path / "raw"
    _write(raw_dir, "2024/2025", _payload("2024/2025", [
        _match(100, 1, 3, _status(utc="2025-05-01T18:00:00Z")),
        _match(101, 3, 1, _status(finished=False, started=False, cancelled=True, score=None, short="Can",
                                  long_key="cancelled", utc="2025-05-08T18:00:00Z")),
    ]))
    _write(raw_dir, "2025/2026", _payload("2025/2026", [_match(201, 3, 1, _status(utc="2025-08-01T18:00:00Z"))]))
    selection = [{"provider_id": FAKE_LEAGUE, "db_name": "Fixture League", "decision": "included", "group": "context",
                  "reason": "test", "n_db_finished": 0, "n_db_connected": 0, "n_connected_teams": 0}]
    history_db = tmp_path / "history.db"
    hist.build_history_db(selection, history_db, raw_dir)
    prod_db = tmp_path / "production.db"
    _synthetic_production_db(prod_db)
    out = tmp_path / "all_results.db"
    res = build_all.build(history_db, prod_db, tmp_path / "no_details.jsonl", out)
    conn = sqlite3.connect(out)
    rows = {r[0]: r[1:] for r in conn.execute(
        "SELECT match_provider_id, source, season, home_team_provider_id, away_team_provider_id, home_score,"
        " away_score, home_xg, awarded, competition_name, competition_in_history_scope FROM results")}
    assert sorted(rows) == [100, 201]  # the cancelled history match has no result
    assert rows[100] == ("history", "2024/2025", 1, 3, 2, 1, None, 0, "Fixture League", 1)
    assert rows[201] == ("production", "2025/2026", 3, 1, 2, 1, 1.25, 0, "Fixture League", 1)
    kinds = Counter(r[0] for r in conn.execute("SELECT kind FROM conflicts"))
    conn.close()
    assert kinds == Counter({"invalid_team_id": 2})
    assert res["stats"]["production_skipped_invalid_team_id"] == 2
    again = build_all.build(history_db, prod_db, tmp_path / "no_details.jsonl", out)
    assert again["n_results"] == res["n_results"] == 2


def test_prewindow_season_for_shifted_labels(tmp_path):
    """Super-cup style labelling: season "2021/2022" is played in January 2023, so the January 2022
    edition sits in "2020/2021"; only its in-window matches are kept."""
    raw_dir = tmp_path / "raw"
    seasons = ("2022/2023", "2021/2022", "2020/2021")
    _write(raw_dir, "2021/2022", _payload("2021/2022", [_match(500, 1, 2, _status(utc="2023-01-15T19:00:00Z"))], seasons=seasons))
    _write(raw_dir, "2022/2023", _payload("2022/2023", [_match(501, 1, 3, _status(utc="2024-01-14T19:00:00Z"))], seasons=seasons))
    _write(raw_dir, "2020/2021", _payload("2020/2021", [
        _match(498, 2, 3, _status(utc="2021-01-17T19:00:00Z")),  # before the window -> dropped
        _match(499, 2, 1, _status(utc="2022-01-16T19:00:00Z")),  # inside the window -> kept
    ], seasons=seasons))
    assert hist.prewindow_season(FAKE_LEAGUE, list(seasons), ["2021/2022", "2022/2023"], raw_dir) == "2020/2021"
    # a normal league whose first core season starts in August needs no pre-window season
    assert hist.previous_season_name("2021") == "2020" and hist.previous_season_name("2021/2022") == "2020/2021"
    selection = [{"provider_id": FAKE_LEAGUE, "db_name": "Fixture Cup", "decision": "included", "group": "context",
                  "reason": "test", "n_db_finished": 0, "n_db_connected": 0, "n_connected_teams": 0}]
    out = tmp_path / "history.db"
    hist.build_history_db(selection, out, raw_dir)
    conn = sqlite3.connect(out)
    assert sorted(r[0] for r in conn.execute("SELECT provider_id FROM matches")) == [499, 500, 501]
    assert conn.execute("SELECT season_role, n_matches, n_before_window FROM seasons WHERE season = '2020/2021'").fetchone() == ("prewindow", 1, 1)
    conn.close()
