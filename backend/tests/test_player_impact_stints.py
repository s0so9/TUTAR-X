"""Tests for the stint builder and the xG-RAPM trainer (scripts/training/build_stints.py,
scripts/training/player_impact.py). Synthetic, clearly labelled TEST data only."""

from __future__ import annotations

import copy
import csv
import gzip
import json
import sys
from pathlib import Path

import numpy as np
import pytest

TRAINING_DIR = Path(__file__).resolve().parents[1] / "scripts" / "training"
sys.path.insert(0, str(TRAINING_DIR))

import build_stints as BS  # noqa: E402
import player_impact as PI  # noqa: E402

HOME, AWAY = 1, 2
HOME_STARTERS = list(range(101, 112))
AWAY_STARTERS = list(range(201, 212))


def _player_stat(team: int, xg: float) -> dict:
    return {"teamId": team, "stats": [{"stats": {"Expected goals (xG)": {"key": "expected_goals",
                                                                          "stat": {"value": xg}}}}]}


def synthetic_match() -> dict:
    """TEST DATA: a made-up match exercising HT subs, a same-minute goal, an own goal, a red card,
    stoppage time and a shoot-out kick."""
    events = [
        {"type": "Goal", "time": 30, "overloadTime": None, "isHome": True, "ownGoal": None, "newScore": [1, 0],
         "homeScore": 0, "awayScore": 0, "shotmapEvent": {"id": 9001}, "isPenaltyShootoutEvent": False},
        {"type": "AddedTime", "time": 45, "minutesAddedInput": 2},
        {"type": "Half", "time": 45, "halfStrShort": "HT"},
        {"type": "Substitution", "time": 46, "overloadTime": 0, "isHome": True, "homeScore": 1, "awayScore": 0,
         "swap": [{"id": "112"}, {"id": "101"}]},
        {"type": "Goal", "time": 55, "overloadTime": None, "isHome": False, "ownGoal": True, "newScore": [1, 1],
         "homeScore": 1, "awayScore": 0, "shotmapEvent": {"id": 9002}, "isPenaltyShootoutEvent": False},
        {"type": "Goal", "time": 60, "overloadTime": None, "isHome": True, "ownGoal": None, "newScore": [2, 1],
         "homeScore": 1, "awayScore": 1, "shotmapEvent": {"id": 9003}, "goalDescriptionKey": "penalty",
         "isPenaltyShootoutEvent": False},
        {"type": "Substitution", "time": 60, "overloadTime": 0, "isHome": False, "homeScore": 2, "awayScore": 1,
         "swap": [{"id": "212"}, {"id": "205"}]},
        {"type": "Card", "time": 70, "overloadTime": None, "isHome": False, "card": "Red", "playerId": 206,
         "homeScore": 2, "awayScore": 1},
        {"type": "Card", "time": 75, "overloadTime": None, "isHome": True, "card": "Red", "playerId": 113,
         "homeScore": 2, "awayScore": 1},  # red card for a bench player: not a line-up change
        {"type": "AddedTime", "time": 90, "minutesAddedInput": 3},
        {"type": "Half", "time": 90, "halfStrShort": "FT"},
    ]
    shots = [
        {"id": 9001, "teamId": HOME, "period": "FirstHalf", "min": 30, "minAdded": None, "expectedGoals": 0.4,
         "situation": "RegularPlay", "isOwnGoal": False, "eventType": "Goal"},
        {"id": 9004, "teamId": AWAY, "period": "FirstHalf", "min": 20, "minAdded": None, "expectedGoals": 0.5,
         "situation": "RegularPlay", "isOwnGoal": False, "eventType": "Miss"},
        {"id": 9002, "teamId": HOME, "period": "SecondHalf", "min": 55, "minAdded": None, "expectedGoals": None,
         "situation": "RegularPlay", "isOwnGoal": True, "eventType": "Goal"},
        {"id": 9003, "teamId": HOME, "period": "SecondHalf", "min": 60, "minAdded": None, "expectedGoals": 0.79,
         "situation": "Penalty", "isOwnGoal": False, "eventType": "Goal"},
        {"id": 9005, "teamId": HOME, "period": "SecondHalf", "min": 90, "minAdded": 2, "expectedGoals": 0.2,
         "situation": "RegularPlay", "isOwnGoal": False, "eventType": "AttemptSaved"},
        {"id": 9006, "teamId": AWAY, "period": "PenaltyShootout", "min": 120, "minAdded": None,
         "expectedGoals": 0.79, "situation": "Penalty", "isOwnGoal": False, "eventType": "Goal"},
    ]
    return {
        "general": {"homeTeam": {"id": HOME}, "awayTeam": {"id": AWAY}},
        "header": {"teams": [{"score": 2}, {"score": 1}], "status": {
            "halfs": {"firstHalfStarted": "01.01.2026 20:00:00", "firstHalfEnded": "01.01.2026 20:47:00",
                      "secondHalfStarted": "01.01.2026 21:02:00", "secondHalfEnded": "01.01.2026 21:50:00",
                      "firstExtraHalfStarted": "", "secondExtraHalfStarted": ""},
            "numberOfHomeRedCards": 0, "numberOfAwayRedCards": 1}},
        "content": {
            "lineup": {
                "homeTeam": {"id": HOME, "starters": [{"id": p} for p in HOME_STARTERS],
                             "subs": [{"id": 112}, {"id": 113}]},
                "awayTeam": {"id": AWAY, "starters": [{"id": p} for p in AWAY_STARTERS], "subs": [{"id": 212}]},
            },
            "matchFacts": {"events": {"events": events}},
            "shotmap": {"shots": shots},
            "stats": {"Periods": {"All": {"stats": [{"stats": [
                {"key": "expected_goals", "stats": ["1.39", "0.50"]},
                {"key": "expected_goals_non_penalty", "stats": ["0.60", "0.50"]},
            ]}]}}},
            "playerStats": {"103": _player_stat(HOME, 1.39), "204": _player_stat(AWAY, 0.5)},
        },
    }


def synthetic_meta() -> dict:
    minutes = {p: 90 for p in HOME_STARTERS + AWAY_STARTERS}
    minutes.update({101: 46, 112: 44, 205: 60, 212: 30, 206: 70})
    return {"match_id": "T1", "kickoff": "2026-01-01T20:00:00.000Z", "competition_id": 47,
            "home_team_id": HOME, "away_team_id": AWAY, "minutes": minutes}


class TestBuildStints:
    def test_segments_boundaries_and_clock(self):
        rows, val = BS.build_match(synthetic_match(), synthetic_meta())
        # H1 47 min and H2 48 min from the half timestamps; HT sub on the break, sub at 60' and red at 70'
        assert [(r["start"], r["end"]) for r in rows] == [(0.0, 47.0), (47.0, 61.0), (61.0, 71.0), (71.0, 95.0)]
        assert val["h1_length_source"] == "timestamps" and val["match_length"] == 95.0
        assert [r["end_reason"] for r in rows] == ["substitution", "substitution", "red_card", "full_time"]
        assert 101 in rows[0]["home_players"] and 101 not in rows[1]["home_players"]
        assert 112 in rows[1]["home_players"]
        assert rows[3]["n_away"] == 10 and rows[3]["man_adv"] == 1
        assert all(r["n_home"] == 11 for r in rows)  # bench red card ignored
        assert val["red_cards_ignored"] == 1

    def test_xg_goals_own_goal_penalty_and_shootout(self):
        rows, val = BS.build_match(synthetic_match(), synthetic_meta())
        assert [r["home_xg"] for r in rows] == [0.4, 0.79, 0.0, 0.2]
        assert [r["home_npxg"] for r in rows] == [0.4, 0.0, 0.0, 0.2]
        assert [r["away_xg"] for r in rows] == [0.5, 0.0, 0.0, 0.0]   # shoot-out kick excluded
        # own goal credited to the away side (benefiting team), never as xG
        assert [r["away_goals"] for r in rows] == [0, 1, 0, 0]
        # the 60' goal happened before the 60' substitution (the sub event's score includes it)
        assert [r["home_goals"] for r in rows] == [1, 1, 0, 0]
        assert [r["home_np_goals"] for r in rows] == [1, 0, 0, 0]
        assert val["goals_moved_before_change"] == 1
        assert val["goals_ok"] and val["xg_check"] == "pass" and val["shootout_shots_skipped"] == 1
        assert rows[2]["score_start"] == [2, 1]

    def test_validation_flags_and_game_state(self):
        rows, val = BS.build_match(synthetic_match(), synthetic_meta())
        assert val["lineup_ok"] and val["minutes_ok"] and val["usable"] and val["passed"]
        seg0 = rows[0]
        assert seg0["level_minutes"] == pytest.approx(29.5) and seg0["home_lead_minutes"] == pytest.approx(17.5)
        for r in rows:
            assert r["home_lead_minutes"] + r["level_minutes"] + r["home_trail_minutes"] == pytest.approx(r["duration"])

    def test_announced_added_time_when_timestamps_missing(self):
        raw = synthetic_match()
        raw["header"]["status"]["halfs"] = {}
        rows, val = BS.build_match(raw, synthetic_meta())
        assert val["h1_length_source"] == "announced" and val["h2_length_source"] == "announced"
        assert val["match_length"] == 95.0

    def test_no_shotmap_means_unknown_xg_not_zero(self):
        raw = synthetic_match()
        del raw["content"]["shotmap"]
        del raw["content"]["stats"]
        rows, val = BS.build_match(raw, synthetic_meta())
        assert all(r["home_xg"] is None and r["away_npxg"] is None for r in rows)
        assert val["xg_check"] == "n/a" and val["goals_ok"]

    def test_inconsistent_substitution_is_flagged(self):
        raw = synthetic_match()
        raw["content"]["matchFacts"]["events"]["events"][3]["swap"] = [{"id": "112"}, {"id": "999"}]
        rows, val = BS.build_match(raw, synthetic_meta())
        assert not val["lineup_ok"] and not val["usable"]
        assert "home_sub_off_not_on_pitch" in val["lineup_issues"]

    def test_shot_vs_stats_xg_classification(self):
        raw = synthetic_match()
        raw["content"]["shotmap"]["shots"][1]["expectedGoals"] = 0.9   # shotmap differs, stats agree
        _rows, val = BS.build_match(raw, synthetic_meta())
        assert val["xg_check"] == "fail_shot_values_differ"

    def test_cli_reads_jsonl_list_and_skips_bad_raw(self, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        with gzip.open(raw_dir / "T1.json.gz", "wt", encoding="utf-8") as f:
            json.dump(synthetic_match(), f)
        (raw_dir / "T2.json.gz").write_bytes(b"\x1f\x8b\x08partial")       # truncated gzip
        details = tmp_path / "details.jsonl"
        base = {"scheduled_at": "2026-01-01T20:00:00.000Z", "competition_provider_id": 47,
                "home_team_provider_id": HOME, "away_team_provider_id": AWAY, "players": []}
        with open(details, "w", encoding="utf-8") as f:
            f.write(json.dumps({**base, "match_provider_id": "T1"}) + "\n")
            f.write(json.dumps({**base, "match_provider_id": "T2"}) + "\n")
            f.write(json.dumps({**base, "match_provider_id": "T3"}) + "\n")   # raw file missing
            f.write('{"match_provider_id": "T4", "sched')                     # partial last line
        out = tmp_path / "stints.jsonl.gz"
        rc = BS.main(["--details", str(details), "--raw-dir", str(raw_dir), "--out", str(out),
                      "--validation-out", str(tmp_path / "v.csv"), "--report", str(tmp_path / "r.json"),
                      "--workers", "1"])
        assert rc == 0
        report = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
        assert report["skipped_matches"] == {"raw_unreadable": 1, "raw_missing": 1}
        assert report["read"]["jsonl_unparsable_lines"] == 1
        with gzip.open(out, "rt", encoding="utf-8") as f:
            assert len(f.readlines()) == 4


# --------------------------------------------------------------------------- RAPM trainer

def _write_synthetic_rapm_inputs(tmp_path: Path, star_effect: float = 0.6, late_extreme: bool = False):
    """TEST DATA: 40 synthetic matches between two teams; home player 1001 (the 'star') is on the
    pitch in half of the stints and raises his side's npxG rate by `star_effect` per 90."""
    rng = np.random.default_rng(7)
    home = list(range(1001, 1012))
    bench = 1012
    away = list(range(2001, 2012))
    stints = []
    details = []
    for m in range(40):
        day = f"2026-01-{(m % 28) + 1:02d}T15:00:00Z" if m < 28 else f"2026-02-{m - 27:02d}T15:00:00Z"
        on_home_first = home
        on_home_second = [bench] + home[1:]
        for seg, (players, start, end) in enumerate(((on_home_first, 0.0, 45.0), (on_home_second, 45.0, 95.0))):
            dur = end - start
            rate = 1.2 + (star_effect if 1001 in players else 0.0)
            hx = float(rng.gamma(4.0, rate * dur / 90 / 4.0))
            ax = float(rng.gamma(4.0, 1.2 * dur / 90 / 4.0))
            stints.append({
                "match_id": f"M{m}", "kickoff": day, "competition_id": 99, "home_team_id": 1, "away_team_id": 2,
                "seg": seg, "start": start, "end": end, "duration": dur, "home_players": players,
                "away_players": away, "n_home": 11, "n_away": 11, "man_adv": 0, "xg_available": True,
                "home_xg": hx, "away_xg": ax, "home_npxg": hx, "away_npxg": ax, "home_goals": 0, "away_goals": 0,
                "home_lead_minutes": 0.0, "level_minutes": dur, "home_trail_minutes": 0.0, "usable": True,
            })
        players = ([{"player_id": p, "team_provider_id": 1, "minutes_played": 45 if p in (1001, bench) else 90,
                     "npxg": 0.1, "xa": 0.05, "rating": 7.0, "usual_position_id": 3 if p == 1001 else 2,
                     "market_value": 1_000_000, "stats_available": True} for p in home + [bench]]
                   + [{"player_id": p, "team_provider_id": 2, "minutes_played": 90, "npxg": 0.1, "xa": 0.05,
                       "rating": 6.8, "usual_position_id": 1, "market_value": 900_000, "stats_available": True}
                      for p in away])
        details.append({"match_provider_id": f"M{m}", "scheduled_at": day, "home_xg": 1.0, "away_xg": 1.0,
                        "players": players})
    if late_extreme:   # a stint AFTER the cutoffs used below, with an absurd value
        late = copy.deepcopy(stints[0])
        late.update({"match_id": "LATE", "kickoff": "2026-03-20T15:00:00Z", "home_npxg": 50.0, "home_xg": 50.0})
        stints.append(late)
        details.append({**details[0], "match_provider_id": "LATE", "scheduled_at": "2026-03-20T15:00:00Z"})
    sp = tmp_path / "stints.jsonl.gz"
    with gzip.open(sp, "wt", encoding="utf-8") as f:
        for s in stints:
            f.write(json.dumps(s) + "\n")
    dp = tmp_path / "details.jsonl"
    with open(dp, "w", encoding="utf-8") as f:
        for d in details:
            f.write(json.dumps(d) + "\n")
    return sp, dp


def _run_trainer(tmp_path: Path, sp: Path, dp: Path, tag: str) -> list[dict]:
    out = tmp_path / f"ratings_{tag}.csv.gz"
    meta = tmp_path / f"meta_{tag}.json"
    rc = PI.main(["--stints", str(sp), "--details", str(dp), "--out", str(out), "--meta", str(meta),
                  "--start", "2026-02-01", "--end", "2026-03-01", "--step-days", "28",
                  "--lambda", "50", "--half-life", "365", "--team-lambda", "1e7"])
    assert rc == 0
    with gzip.open(out, "rt", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class TestRapmTrainer:
    def test_star_player_gets_higher_offence(self, tmp_path):
        sp, dp = _write_synthetic_rapm_inputs(tmp_path)
        rows = _run_trainer(tmp_path, sp, dp, "a")
        last = {r["player_id"]: r for r in rows if r["cutoff"] == "2026-03-01"}
        assert float(last["1001"]["offence"]) - float(last["1012"]["offence"]) > 0.2
        assert {r["cutoff"] for r in rows} == {"2026-02-01", "2026-03-01"}

    def test_no_look_ahead(self, tmp_path):
        sp, dp = _write_synthetic_rapm_inputs(tmp_path)
        a = _run_trainer(tmp_path, sp, dp, "a")
        other = tmp_path / "with_late_stint"
        other.mkdir()
        sp2, dp2 = _write_synthetic_rapm_inputs(other, late_extreme=True)
        b = _run_trainer(tmp_path, sp2, dp2, "b")
        key = lambda rs: {(r["cutoff"], r["player_id"]): (r["offence"], r["defence"]) for r in rs}  # noqa: E731
        assert key(a) == key(b)   # a stint after the last cutoff changes nothing

    def test_minutes_share_and_flags(self, tmp_path):
        sp, dp = _write_synthetic_rapm_inputs(tmp_path)
        rows = _run_trainer(tmp_path, sp, dp, "a")
        r = {x["player_id"]: x for x in rows if x["cutoff"] == "2026-03-01"}
        assert float(r["1002"]["minutes_share"]) == pytest.approx(1.0)
        assert float(r["1001"]["minutes_share"]) == pytest.approx(0.5)
        assert r["1002"]["flags"] == ""
