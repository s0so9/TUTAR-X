"""Stage B of the player-impact pipeline: match features, match model harness, results-table
walk-forward lambdas. Synthetic data only (no production DB, no network).

Leakage tests: features of a match must not change when data from after its kick-off is added
(later matches, later rating cutoffs, later results) or when the match's own outcome fields
(score, xG, player match stats) change.
"""

from __future__ import annotations

import copy
import csv
import gzip
import json
import math
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

TRAINING_DIR = Path(__file__).resolve().parents[1] / "scripts" / "training"
sys.path.insert(0, str(TRAINING_DIR))

import build_match_features as F  # noqa: E402
import train_goal_model as TG  # noqa: E402
import train_match_model as M  # noqa: E402
import walkforward_from_results as W  # noqa: E402


# ============================================================================ synthetic world
class IdentityLayer:
    def adjust(self, lh, la):
        return lh, la


TEAMS = ["11", "12", "13", "14"]
POS_IDS = [0, 1, 1, 1, 1, 2, 2, 2, 3, 3, 3, 1, 2, 3, 0, 2]   # usual positions of a team's 16 players


def _players(team: str, side: str, week: int, rng) -> list[dict]:
    base = int(team) * 100
    order = [(k + week) % 16 for k in range(16)]
    starters = sorted(order[:11])
    out = []
    for k in range(16):
        pid = base + k
        st = k in starters
        out.append({"player_id": pid, "name": f"P{pid}", "team_side": side, "team_provider_id": int(team),
                    "is_starter": st, "appeared": st, "position": None, "usual_position_id": POS_IDS[k],
                    "minutes_played": 90 if st else None, "rating": round(float(rng.uniform(6.0, 8.0)), 2) if st else None,
                    "market_value": 1_000_000 + 10_000 * k})
    return out


def make_records(n_weeks: int = 14, seed: int = 0, start: datetime = datetime(2025, 9, 6, 15, 0)) -> list[dict]:
    rng = np.random.default_rng(seed)
    recs = []
    for w in range(n_weeks):
        pairs = [("11", "12"), ("13", "14")] if w % 2 == 0 else [("13", "11"), ("14", "12")]
        for j, (h, a) in enumerate(pairs):
            kick = start + timedelta(days=7 * w, hours=2 * j)
            players = _players(h, "home", w, rng) + _players(a, "away", w, rng)
            unav = [{"player_id": int(h) * 100 + (w % 16), "name": "X", "team_side": "home", "type": "injury",
                     "expected_return": "Soon", "market_value": 2_000_000}]
            if w % 3 == 0:
                unav.append({"player_id": int(a) * 100 + 5, "name": "Y", "team_side": "away", "type": "suspension",
                             "expected_return": None, "market_value": None})
            recs.append({
                "match_provider_id": str(5000 + 2 * w + j), "scheduled_at": kick.isoformat() + ".000Z",
                "competition_provider_id": 47, "source_league_id": 47, "season": None,
                "home_team_provider_id": int(h), "away_team_provider_id": int(a),
                "home_score": int(rng.integers(0, 4)), "away_score": int(rng.integers(0, 3)), "awarded": False,
                "home_xg": round(float(rng.uniform(0.3, 2.5)), 2), "away_xg": round(float(rng.uniform(0.3, 2.0)), 2),
                "home_starters_market_value": 50_000_000 + 1_000_000 * w, "away_starters_market_value": 40_000_000,
                "players": players, "unavailable": unav,
            })
    return recs


def make_results(records: list[dict], extra: list[dict] = ()) -> list[dict]:
    out = [{"id": r["match_provider_id"], "comp": "47", "name": "Premier League", "at": F.parse_utc(r["scheduled_at"]),
            "home": str(r["home_team_provider_id"]), "away": str(r["away_team_provider_id"]),
            "hs": r["home_score"], "as": r["away_score"]} for r in records]
    out += list(extra)
    out.sort(key=lambda r: (r["at"], r["id"]))
    return out


def euro_result(mid: str, team: str, at: datetime, hs=1, as_=1) -> dict:
    return {"id": mid, "comp": "42", "name": "Champions League", "at": at, "home": team, "away": "99", "hs": hs, "as": as_}


def make_ratings(first: datetime, n: int) -> F.Ratings:
    rt = F.Ratings()
    for c in range(n):
        cut = (first + timedelta(days=7 * c)).date().isoformat()
        tab = {}
        for t in TEAMS:
            for k in range(16):
                pid = str(int(t) * 100 + k)
                tab[pid] = (0.01 * k - 0.05 + 0.001 * c, 0.02 - 0.002 * k, min(1.0, 0.1 * (k % 10)),
                            {0: "GK", 1: "DEF", 2: "MID", 3: "FWD"}[POS_IDS[k]])
        rt.table[cut] = tab
        rt.repl[cut] = {p: (-0.05, -0.02) for p in ("GK", "DEF", "MID", "FWD", "UNK")}
    rt.cutoffs = sorted(rt.table)
    rt.cutoff_dt = [datetime.fromisoformat(c) for c in rt.cutoffs]
    return rt


def write_jsonl(path: Path, records: list[dict]) -> Path:
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return path


def build(tmp_path: Path, records, results, ratings, name="d.jsonl", presence=None):
    recs, _ = F.read_details([write_jsonl(tmp_path / name, records)])
    lambdas = {r["match_provider_id"]: {"lh": 1.4, "la": 1.1, "cutoff": "x", "source": "s"} for r in records}
    pres = presence if presence is not None else {r["match_provider_id"]: (True, True) for r in records}
    rows = F.build_rows(F.Inputs(recs, lambdas, results, ratings, pres, IdentityLayer()))
    return {r["match_id"]: r for r in rows}


def features_only(row: dict, drop=()) -> dict:
    return {k: v for k, v in row.items() if not k.startswith("y_") and k not in ("details_source", *drop)}


# ============================================================================ feature leakage tests
def test_features_unchanged_when_post_kickoff_data_is_added(tmp_path):
    base_recs = make_records(n_weeks=10)
    rt = make_ratings(datetime(2025, 9, 1), 12)
    before = build(tmp_path, base_recs, make_results(base_recs), rt)

    # post-kick-off data: later matches (> 3 calendar days after the last kick-off), extra later
    # results incl. European ones, later rating cutoffs with different values, later line-ups
    more = make_records(n_weeks=16, seed=0)            # same first 10 weeks, 6 more weeks
    assert [r["match_provider_id"] for r in more[:20]] == [r["match_provider_id"] for r in base_recs]
    last_kick = max(F.parse_utc(r["scheduled_at"]) for r in base_recs)
    later = [r for r in more[20:]]
    assert min(F.parse_utc(r["scheduled_at"]) for r in later) > last_kick + timedelta(days=3)
    extra = [euro_result("9001", "11", last_kick + timedelta(days=5)),
             euro_result("9002", "12", last_kick + timedelta(days=20), hs=7, as_=0)]
    rt2 = make_ratings(datetime(2025, 9, 1), 20)
    for cut in rt2.cutoffs[12:]:                       # later cutoffs carry wildly different ratings
        rt2.table[cut] = {pid: (v[0] + 5, v[1] - 5, v[2], v[3]) for pid, v in rt2.table[cut].items()}
    after = build(tmp_path, base_recs + later, make_results(base_recs + later, extra), rt2, name="d2.jsonl")

    assert len(before) == 20
    for mid, row in before.items():
        assert features_only(row) == features_only(after[mid]), mid
    # the comparison is not vacuous: XI, absentee, form and rest features exist for late matches
    late = before["5019"]
    assert late["home_xi_d_off"] is not None and late["home_n_injury"] == 1
    assert late["home_xg_for_l5"] is not None and late["home_rest_days"] == pytest.approx(7.0, abs=0.1)


def test_own_match_outcome_does_not_change_its_features(tmp_path):
    recs = make_records(n_weeks=8)
    rt = make_ratings(datetime(2025, 9, 1), 10)
    target = "5013"
    before = build(tmp_path, recs, make_results(recs), rt)
    recs2 = copy.deepcopy(recs)
    for r in recs2:
        if r["match_provider_id"] == target:
            r["home_score"], r["away_score"] = 9, 0
            r["home_xg"], r["away_xg"] = 6.5, 0.1
            for p in r["players"]:                     # post-match player stats
                p["rating"] = 10.0 if p["is_starter"] else 3.0
                p["minutes_played"] = 1 if p["is_starter"] else 89
    after = build(tmp_path, recs2, make_results(recs2), rt, name="d2.jsonl")
    assert features_only(before[target]) == features_only(after[target])
    assert after[target]["y_home_goals"] == 9          # labels do change
    # ... while a LATER match of the same team sees the changed result (sanity: the data is used)
    later = "5014"                                     # week 7: team 13 at home, its previous match is the target
    assert before[later]["home_gf_l5"] != after[later]["home_gf_l5"]
    assert before[later]["home_xg_for_l5"] != after[later]["home_xg_for_l5"]


def test_euro_after_flag_uses_schedule_only(tmp_path):
    recs = make_records(n_weeks=6)
    rt = make_ratings(datetime(2025, 9, 1), 8)
    last = recs[-2]                                    # home team 13 (week 5: pairs 13-11, 14-12)
    kick = F.parse_utc(last["scheduled_at"])
    team = str(last["home_team_provider_id"])
    base = build(tmp_path, recs, make_results(recs), rt)
    assert base[last["match_provider_id"]]["home_euro_after_3d"] == 0
    for hs, name in ((0, "a.jsonl"), (6, "b.jsonl")):  # result of the future European match is irrelevant
        res = make_results(recs, [euro_result("9100", team, kick + timedelta(days=3, hours=6), hs=hs)])
        row = build(tmp_path, recs, res, rt, name=name)[last["match_provider_id"]]
        assert row["home_euro_after_3d"] == 1
        assert features_only(row, drop=("home_euro_after_3d",)) == features_only(base[last["match_provider_id"]],
                                                                                drop=("home_euro_after_3d",))
    res = make_results(recs, [euro_result("9101", team, kick + timedelta(days=4, hours=1))])
    assert build(tmp_path, recs, res, rt, name="c.jsonl")[last["match_provider_id"]]["home_euro_after_3d"] == 0


def test_ratings_cutoff_strictly_before_kickoff():
    rt = make_ratings(datetime(2025, 9, 1), 3)
    assert rt.cutoff_before(datetime(2025, 9, 8, 0, 0)) == "2025-09-01"      # cutoff == kick-off: previous one
    assert rt.cutoff_before(datetime(2025, 9, 8, 0, 1)) == "2025-09-08"
    assert rt.cutoff_before(datetime(2025, 9, 1, 0, 0)) is None


def test_duplicate_fixture_and_own_id_excluded_from_history():
    at = datetime(2025, 10, 4, 15)
    res = [{"id": "1", "comp": "47", "name": "L", "at": at - timedelta(hours=1), "home": "11", "away": "12", "hs": 5, "as": 0},
           {"id": "2", "comp": "47", "name": "L", "at": at - timedelta(days=7), "home": "11", "away": "13", "hs": 1, "as": 1},
           {"id": "3", "comp": "47", "name": "L", "at": at - timedelta(minutes=30), "home": "11", "away": "12", "hs": 2, "as": 2}]
    tr = F.TeamResults(res)
    prev = tr.before("11", at, "1", "12")              # own id "1" and the same-pair duplicate "3" are skipped
    assert [t[1] for t in prev] == ["2"]


def test_unavailable_listing_null_vs_zero(tmp_path):
    recs = make_records(n_weeks=6)
    rt = make_ratings(datetime(2025, 9, 1), 8)
    mid = recs[-1]["match_provider_id"]
    pres = {r["match_provider_id"]: (True, True) for r in recs}
    pres[mid] = (True, False)                          # away key absent in the raw response
    row = build(tmp_path, recs, make_results(recs), rt, presence=pres)[mid]
    assert row["away_unavail_listed"] == 0 and row["away_n_injury"] is None and row["away_unavail_off_w"] is None
    assert row["home_unavail_listed"] == 1 and row["home_n_injury"] == 1
    pres[mid] = (True, True)
    recs2 = copy.deepcopy(recs)
    recs2[-1]["unavailable"] = [u for u in recs2[-1]["unavailable"] if u["team_side"] == "home"]
    row = build(tmp_path, recs2, make_results(recs2), rt, presence=pres, name="e.jsonl")[mid]
    assert row["away_n_injury"] == 0 and row["away_n_suspension"] == 0   # key sent, list empty -> 0


def test_unavailable_presence_reads_raw(tmp_path):
    body = {"content": {"lineup": {"homeTeam": {"unavailable": []}, "awayTeam": {"starters": []}}}}
    with gzip.open(tmp_path / "77.json.gz", "wb") as f:
        f.write(json.dumps(body).encode())
    assert F.unavailable_presence(tmp_path, "77") == (True, False)
    assert F.unavailable_presence(tmp_path, "78") is None


def test_read_details_skips_partial_line_and_awarded(tmp_path):
    recs = make_records(n_weeks=2)
    recs[1]["awarded"] = True
    p = write_jsonl(tmp_path / "d.jsonl", recs)
    with open(p, "a", encoding="utf-8") as f:
        f.write('{"match_provider_id": "1", "sched')       # partial last line of a growing file
    out, stats = F.read_details([p])
    assert len(out) == 3 and stats["unparsable_lines"] == 1 and stats["awarded_dropped"] == 1


def test_written_csv_roundtrip_keeps_nulls(tmp_path):
    recs = make_records(n_weeks=5)
    rows = list(build(tmp_path, recs, make_results(recs), make_ratings(datetime(2025, 9, 1), 6)).values())
    F.write_rows(tmp_path / "f.csv.gz", rows)
    with gzip.open(tmp_path / "f.csv.gz", "rt", encoding="utf-8") as f:
        back = list(csv.DictReader(f))
    assert len(back) == len(rows) and list(back[0].keys()) == F.COLUMNS
    first = back[0]
    assert first["home_xi_d_off"] == "" and first["home_usual_n"] == "0"    # unknown stays empty; 0 stays 0
    F.write_rows(tmp_path / "g.csv.gz", rows)
    assert (tmp_path / "f.csv.gz").read_bytes() == (tmp_path / "g.csv.gz").read_bytes()   # deterministic


# ============================================================================ match model harness
def synth_rows(n: int, beta: float, seed: int = 3, start=datetime(2025, 9, 1)) -> list[dict]:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        lh, la = rng.uniform(0.6, 2.4), rng.uniform(0.5, 2.0)
        xo_h, xo_a = rng.normal(0, 0.15), rng.normal(0, 0.15)
        mh, ma = lh * math.exp(beta * xo_h), la * math.exp(beta * xo_a)
        rows.append({"match_id": str(i), "at": start + timedelta(hours=6 * i), "lambda_home": lh, "lambda_away": la,
                     "hs": int(rng.poisson(mh)), "as": int(rng.poisson(ma)), "home_xi_d_off": xo_h, "away_xi_d_off": xo_a,
                     "home_xi_d_def": None if i % 7 == 0 else 0.0, "away_xi_d_def": 0.0, "comp_is_euro": 0,
                     "value_log_ratio": None, "lineup_form": None})
    return rows


def test_glm_recovers_known_effect():
    rows = synth_rows(4000, beta=1.5)
    m = M.GLMModel(["xi"], l2=1.0).fit(rows, rho0=0.0, r0=50.0)
    sd = m.design.stats["xi_off_att"][1]
    assert m.converged
    assert m.coefficients()["xi_off_att"] / sd == pytest.approx(1.5, abs=0.3)
    assert abs(m.coefficients()["c_home"]) < 0.1 and abs(m.coefficients()["alpha_loglam"]) < 0.15
    null = M.GLMModel(["xi"], l2=1.0).fit(synth_rows(4000, beta=0.0, seed=4), rho0=0.0, r0=50.0)
    assert abs(null.coefficients()["xi_off_att"]) < 0.05


def test_glm_gradient_matches_finite_differences():
    rng = np.random.default_rng(5)
    n = 200
    eh, ea = np.log(rng.uniform(0.4, 3, n)), np.log(rng.uniform(0.3, 2.5, n))
    hs, as_ = rng.poisson(np.exp(eh)), rng.poisson(np.exp(ea))
    ll, gh, ga = M.score_loglik(eh, ea, hs, as_, -0.08, 12.0, grad=True)
    ref = TG.score_matrix(np.exp(eh), np.exp(ea), -0.08, 12.0)
    assert np.allclose(ll, np.log(ref[np.arange(n), np.clip(hs, 0, 10), np.clip(as_, 0, 10)]))
    h = 1e-6
    fh = (M.score_loglik(eh + h, ea, hs, as_, -0.08, 12.0) - M.score_loglik(eh - h, ea, hs, as_, -0.08, 12.0)) / (2 * h)
    fa = (M.score_loglik(eh, ea + h, hs, as_, -0.08, 12.0) - M.score_loglik(eh, ea - h, hs, as_, -0.08, 12.0)) / (2 * h)
    assert np.allclose(gh, fh, atol=1e-6) and np.allclose(ga, fa, atol=1e-6)


def test_missing_indicator_and_zero_fill():
    rows = synth_rows(50, beta=0.0)
    d = M.Design(["xi"]).fit_stats(rows)
    Xh, Xa = d.matrices(rows)
    j_def = d.names.index("xi_def_def")          # home eq. uses the AWAY side's xi_d_def (always 0.0)
    j_miss_def_h = d.names.index("xi_miss_def")
    assert Xh[0, j_miss_def_h] == 0.0 and Xa[0, j_miss_def_h] == 1.0   # row 0: home_xi_d_def is None
    assert Xa[0, j_def] == 0.0


def test_baseline_reproduces_production_shift():
    prod = {"beta_value_cross_league": 0.048, "beta_value_domestic": 0.0279, "gamma_form": 0.2157,
            "rho": -0.02, "nb_dispersion": 50.0}
    rows = [{"lambda_home": 1.5, "lambda_away": 1.0, "value_log_ratio": 0.7, "lineup_form": 0.1, "comp_is_euro": 1},
            {"lambda_home": 1.5, "lambda_away": 1.0, "value_log_ratio": 0.7, "lineup_form": None, "comp_is_euro": 0},
            {"lambda_home": 1.5, "lambda_away": 1.0, "value_log_ratio": None, "lineup_form": None, "comp_is_euro": 0}]
    for r in rows:
        r.update(hs=1, **{"as": 1})
    mh, ma, rho, r = M.baseline_predict(rows, prod)
    s0 = 0.048 * 0.7 + 0.2157 * 0.1
    assert mh[0] == pytest.approx(1.5 * math.exp(s0)) and ma[0] == pytest.approx(math.exp(-s0))
    assert mh[1] == pytest.approx(1.5 * math.exp(0.0279 * 0.7))
    assert mh[2] == pytest.approx(1.5) and ma[2] == pytest.approx(1.0)   # missing -> no shift (as in production)


def test_time_split_boundaries():
    rows = synth_rows(10, beta=0.0, start=datetime(2026, 3, 31, 12))
    tr, va, te = M.split(rows, datetime(2026, 4, 1), datetime(2026, 4, 2), None, None)
    assert all(r["at"] < datetime(2026, 4, 1) for r in tr)
    assert all(datetime(2026, 4, 1) <= r["at"] < datetime(2026, 4, 2) for r in va)
    assert all(r["at"] >= datetime(2026, 4, 2) for r in te) and len(tr) + len(va) + len(te) == 10


def test_hgb_poisson_early_stopping_and_monotone_lambda():
    rows = synth_rows(1500, beta=1.0)
    tr, va = rows[:1000], rows[1000:]
    params = {"learning_rate": 0.1, "max_leaf_nodes": 4, "min_samples_leaf": 50, "l2_regularization": 0.0}
    m = M.HGBModel(params, ["xi"], "stacked").fit(tr, va)
    assert 1 <= m.n_iter["both"] <= 2000
    probe = [dict(va[0], lambda_home=x) for x in (0.5, 1.0, 2.0, 3.0)]
    mh, _ma = m.predict_mu(probe)
    assert np.all(np.diff(mh) >= -1e-12)               # monotonic constraint on log lambda


def test_market_eval_value_rule():
    rows = [{"match_id": "1", "hs": 2, "as": 0}, {"match_id": "2", "hs": 0, "as": 0}]
    pm = {"_p1x2": np.array([[0.6, 0.25, 0.15], [0.3, 0.3, 0.4]]), "_o25": np.array([0.4, 0.5])}
    odds = {"1": {"mk1x2": [0.5, 0.3, 0.2], "odds1x2": [1.9, 3.2, 5.0], "mkover": 0.5, "oddsou": None}}
    out = M.market_eval(rows, {"m": pm}, odds, 0.03, 50, 1)
    assert out["n"] == 1
    # home: 0.6*1.9-1 = 0.14 >= 0.03, 0.6-0.526 <= 0.08, ratio 1.14 <= 1.5 -> one winning bet at 1.9
    assert out["models"]["m"]["value_bets"]["n"] == 1 and out["models"]["m"]["value_bets"]["roi"] == pytest.approx(0.9)


# ============================================================================ walk-forward from the results table
RESULTS_SCHEMA = """CREATE TABLE results (match_provider_id INTEGER PRIMARY KEY, competition_provider_id INTEGER,
    competition_name TEXT, season TEXT, scheduled_at TEXT NOT NULL, home_team_provider_id INTEGER NOT NULL,
    away_team_provider_id INTEGER NOT NULL, home_score INTEGER NOT NULL, away_score INTEGER NOT NULL,
    home_xg REAL, away_xg REAL, awarded INTEGER, source TEXT NOT NULL, competition_in_history_scope INTEGER NOT NULL)"""
WALKFORWARD_HEADER = ["match_id", "kickoff", "cutoff", "competition_id", "competition_provider_id", "competition_name",
                      "is_euro", "home_team_id", "away_team_id", "home_matches", "away_matches",
                      "lambda_home", "lambda_away", "home_score", "away_score"]


def make_results_db(path: Path, mutate_after: datetime = None, seed: int = 0) -> Path:
    rng = np.random.default_rng(seed)
    teams = list(range(100, 110))
    rows, mid = [], 1
    day = datetime(2022, 1, 1, 15)
    while day < datetime(2022, 12, 31):
        perm = rng.permutation(teams)
        for h, a in zip(perm[::2], perm[1::2]):
            hs, as_ = int(rng.poisson(1.5)), int(rng.poisson(1.1))
            if mutate_after is not None and day >= mutate_after:
                hs, as_ = 9, 0
            awarded = 1 if mid == 7 else (None if mid % 5 == 0 else 0)
            rows.append((mid, 47, "Premier League", "2022/2023", day.strftime("%Y-%m-%dT%H:%M:%SZ"), int(h), int(a),
                         30 if awarded == 1 else hs, as_, None, None, awarded, "history", 1))
            mid += 1
        day += timedelta(days=3)
    con = sqlite3.connect(path)
    con.execute(RESULTS_SCHEMA)
    con.executemany("insert into results values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return path


def test_walkforward_from_results_columns_and_no_lookahead(tmp_path):
    db1 = make_results_db(tmp_path / "r1.db")
    out1 = tmp_path / "l1.csv"
    assert W.main(["--results", str(db1), "--start", "2022-06-06", "--end", "2022-07-04", "--workers", "1",
                   "--out", str(out1)]) == 0
    with open(out1, encoding="utf-8") as f:
        rows1 = list(csv.DictReader(f))
    assert list(rows1[0].keys()) == WALKFORWARD_HEADER
    assert rows1 and all(r["kickoff"] >= r["cutoff"] for r in rows1)
    assert all(datetime.fromisoformat(r["kickoff"]) < datetime.fromisoformat(r["cutoff"]) + timedelta(days=7) for r in rows1)
    # results after 2022-06-20 replaced by absurd scores: predictions for cutoffs <= 2022-06-20 must not change
    db2 = make_results_db(tmp_path / "r2.db", mutate_after=datetime(2022, 6, 20))
    out2 = tmp_path / "l2.csv"
    W.main(["--results", str(db2), "--start", "2022-06-06", "--end", "2022-07-04", "--workers", "2", "--out", str(out2)])
    with open(out2, encoding="utf-8") as f:
        rows2 = list(csv.DictReader(f))
    early1 = [(r["match_id"], r["lambda_home"], r["lambda_away"]) for r in rows1 if r["cutoff"] <= "2022-06-20"]
    early2 = [(r["match_id"], r["lambda_home"], r["lambda_away"]) for r in rows2 if r["cutoff"] <= "2022-06-20"]
    assert early1 and early1 == early2
    late1 = {r["match_id"]: r["lambda_home"] for r in rows1 if r["cutoff"] > "2022-06-20"}
    late2 = {r["match_id"]: r["lambda_home"] for r in rows2 if r["cutoff"] > "2022-06-20"}
    assert late1 != late2                                # the later fits do see the changed results
    meta = json.loads(out1.with_suffix(".meta.json").read_text(encoding="utf-8"))
    assert meta["load_stats"]["dropped_awarded"] == 1    # awarded = 1 dropped, awarded NULL kept


def test_walkforward_from_results_uses_production_rating_code(tmp_path):
    db = make_results_db(tmp_path / "r.db")
    data, _ = W.load_results(db)
    cutoff = datetime(2022, 9, 5)
    rows = W.fit_and_predict(data, cutoff, 7)
    from app.prediction.team_ratings import GlobalPoissonRatings, domestic_groups
    train = [d for d in data if cutoff - timedelta(days=400) <= d["at"] < cutoff]
    groups = domestic_groups([d["home"] for d in train], [d["away"] for d in train],
                             [d["comp_name"] for d in train], [d["comp_id"] for d in train])
    ref = GlobalPoissonRatings().fit([d["home"] for d in train], [d["away"] for d in train],
                                     [d["hs"] for d in train], [d["as"] for d in train],
                                     [(cutoff - d["at"]).total_seconds() / 86400 for d in train], team_groups=groups)
    lam = ref.predict(rows[0][7], rows[0][8])
    assert float(rows[0][11]) == pytest.approx(lam.home, abs=1e-5) and float(rows[0][12]) == pytest.approx(lam.away, abs=1e-5)


def test_details_xg_fill_and_alias(tmp_path):
    db = make_results_db(tmp_path / "r.db")
    con = sqlite3.connect(db)
    con.execute("update results set home_team_provider_id = 959006 where match_provider_id = 3")
    con.commit()
    con.close()
    p = write_jsonl(tmp_path / "x.jsonl", [{"match_provider_id": "4", "home_xg": 1.2, "away_xg": None},
                                          {"match_provider_id": "5", "home_xg": 0.4, "away_xg": 2.0}])
    data, stats = W.load_results(db, extra_xg=W.read_details_xg([p]))
    by = {d["id"]: d for d in data}
    assert by["5"]["hxg"] == 0.4 and by["5"]["axg"] == 2.0
    assert by["4"]["hxg"] is None                        # one side missing -> no xG (nothing imputed)
    assert by["3"]["home"] == "6500" and stats["aliased_team_ids"] == 1


def test_glm_without_recalibration_keeps_production_level():
    rows = synth_rows(1500, beta=1.0, seed=6)
    m = M.GLMModel(["xi"], l2=1.0, recal=False).fit(rows, rho0=-0.02, r0=50.0)
    c = m.coefficients()
    assert c["c_home"] == 0.0 and c["c_away"] == 0.0 and c["alpha_loglam"] == 0.0
    assert m.rho == pytest.approx(-0.02) and m.r == pytest.approx(50.0)
    assert c["xi_off_att"] > 0.05


def test_goal_layer_refit_identity_on_untransformed_rows():
    rows = synth_rows(3000, beta=0.0, seed=8)
    for r in rows:
        r["lambda_home_raw"], r["lambda_away_raw"] = r["lambda_home"], r["lambda_away"]
    p = M.goal_layer_from_train(rows)
    assert p["n_rows"] == 3000 and p["a"] == pytest.approx(1.0, abs=0.2) and abs(p["b"]) < 0.1
    out = M.apply_goal_layer(rows[:3], {"m": 0.2, "a": 1.0, "b": 0.0, "c": 1.0})
    assert out[0]["lambda_home"] == pytest.approx(rows[0]["lambda_home"])
