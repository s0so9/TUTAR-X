"""Favourite-calibration study (scripts/training/calibration_*.py): SYNTHETIC test data only.

Every probability, score and outcome in this file is randomly generated test data (numpy seeds below); none of
it is football data and none of it is used for any decision. The tests check the mathematics of the candidate
fixes (temperature, UEFA ratio shrink / home term, favourite recalibration), that the fitters recover known
parameters from simulated outcomes, that the test split is kept out of the select stage, and the structure of
the candidate JSON written by calibration_evaluate.py (when that file exists in the repository).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

TRAINING_DIR = Path(__file__).resolve().parents[1] / "scripts" / "training"
sys.path.insert(0, str(TRAINING_DIR))

import calibration_common as C  # noqa: E402
import calibration_fixes as F  # noqa: E402

LAYER = {"rho": -0.0157, "nb_dispersion": 1000.0}  # SYNTHETIC-test layer, same magnitude as the production one


def synthetic_probs(n: int, seed: int = 1) -> np.ndarray:
    """SYNTHETIC 1X2 probabilities (not football data): a favourite between 0.40 and 0.85, a draw 0.15..0.30."""
    rng = np.random.default_rng(seed)
    fav = rng.uniform(0.40, 0.85, n)
    draw = rng.uniform(0.15, 0.30, n) * (1 - fav) / 0.5
    draw = np.minimum(draw, 0.9 * (1 - fav))
    dog = 1 - fav - draw
    home_fav = rng.random(n) < 0.6
    p = np.where(home_fav[:, None], np.stack([fav, draw, dog], 1), np.stack([dog, draw, fav], 1))
    return p / p.sum(1, keepdims=True)


def sample_outcomes(p: np.ndarray, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    u = rng.random(len(p))[:, None]
    return (u > np.cumsum(p, 1)).sum(1).clip(0, 2)


# ----------------------------------------------------------------------------- temperature
def test_temperature_identity_and_direction():
    p = synthetic_probs(200)
    assert np.allclose(F.temperature(p, 1.0), p)
    sharp, flat = F.temperature(p, 0.8), F.temperature(p, 1.25)
    assert np.allclose(sharp.sum(1), 1) and np.allclose(flat.sum(1), 1)
    assert (sharp.max(1) >= p.max(1) - 1e-12).all()      # T < 1 sharpens
    assert (flat.max(1) <= p.max(1) + 1e-12).all()       # T > 1 flattens
    assert (sharp.argmax(1) == p.argmax(1)).all() and (flat.argmax(1) == p.argmax(1)).all()


def test_temperature_scopes_leave_league_rows_unchanged():
    p = synthetic_probs(60)
    euro = np.arange(60) % 3 == 0
    mu = np.full(60, 1.3)
    out = F.apply_fix({"kind": "temperature", "scope": "uefa", "T_uefa": 1.4}, p, mu, mu, euro, LAYER)
    assert np.array_equal(out[~euro], p[~euro]) and not np.allclose(out[euro], p[euro])
    out = F.apply_fix({"kind": "temperature", "scope": "split", "T_league": 0.9, "T_uefa": 1.4}, p, mu, mu, euro, LAYER)
    assert np.allclose(out[~euro], F.temperature(p[~euro], 0.9)) and np.allclose(out[euro], F.temperature(p[euro], 1.4))


# ----------------------------------------------------------------------------- ratio shrink / home term
def test_ratio_shrink_keeps_total_and_is_identity_at_k1_h0():
    rng = np.random.default_rng(2)
    mh, ma = rng.uniform(0.4, 3.0, 50), rng.uniform(0.4, 3.0, 50)
    m2h, m2a = F.ratio_shrink_mu(mh, ma, 1.0, 0.0)
    assert np.allclose(m2h, mh) and np.allclose(m2a, ma)
    for k, h in ((0.7, 0.0), (1.0, 0.2), (0.8, -0.1)):
        a, b = F.ratio_shrink_mu(mh, ma, k, h)
        assert np.allclose(a + b, mh + ma)                                   # total goals unchanged
        assert np.allclose(np.log(a / b), k * np.log(mh / ma) + h)           # the stated formula
    a, b = F.ratio_shrink_mu(mh, ma, 0.5, 0.0)
    assert (np.abs(np.log(a / b)) <= np.abs(np.log(mh / ma)) + 1e-12).all()  # k < 1 pulls the sides together


def test_ratio_shrink_apply_fix_only_touches_uefa_rows_and_matches_score_model():
    rng = np.random.default_rng(3)
    mh, ma = rng.uniform(0.5, 2.5, 40), rng.uniform(0.5, 2.5, 40)
    p = C.p1x2_from_mu(mh, ma, LAYER)
    euro = np.arange(40) % 4 == 0
    fix = {"kind": "ratio_shrink", "scope": "uefa", "k": 0.9, "h": 0.15}
    out = F.apply_fix(fix, p, mh, ma, euro, LAYER)
    assert np.array_equal(out[~euro], p[~euro])
    a, b = F.ratio_shrink_mu(mh[euro], ma[euro], 0.9, 0.15)
    assert np.allclose(out[euro], C.p1x2_from_mu(a, b, LAYER))
    assert np.allclose(out.sum(1), 1, atol=1e-9)
    # a positive home term (k = 1) raises the home win probability and lowers the away one of every UEFA row
    pure = F.apply_fix({"kind": "ratio_shrink", "scope": "uefa", "k": 1.0, "h": 0.15}, p, mh, ma, euro, LAYER)
    assert (pure[euro][:, 0] > p[euro][:, 0]).all() and (pure[euro][:, 2] < p[euro][:, 2]).all()


# ----------------------------------------------------------------------------- favourite recalibration
def test_fav_platt_identity_ratio_preserved_and_normalised():
    p = synthetic_probs(300)
    assert np.allclose(F.fav_platt(p, 0.0, 1.0), p, atol=1e-7)
    out = F.fav_platt(p, -0.3, 0.8)
    assert np.allclose(out.sum(1), 1)
    fav = p.argmax(1)
    i = np.arange(len(p))                       # the two non-favourite outcomes keep their ratio
    o1 = (fav + 1) % 3
    o2 = (fav + 2) % 3
    assert np.allclose(out[i, o1] / out[i, o2], p[i, o1] / p[i, o2])


def test_isotonic_fav_is_monotone_and_normalised():
    p = synthetic_probs(3000, seed=5)
    y = sample_outcomes(p, seed=6)
    spec = F.fit_isotonic_fav(p, y)
    assert np.all(np.diff(spec["y"]) >= -1e-12) and np.all(np.diff(spec["x"]) > 0)
    out = F.fav_isotonic(p, spec["x"], spec["y"])
    assert np.allclose(out.sum(1), 1)


# ----------------------------------------------------------------------------- fitters recover known parameters
def test_fit_temperature_recovers_known_temperature():
    p = synthetic_probs(40000, seed=7)             # SYNTHETIC "model" probabilities
    truth = F.temperature(p, 1.3)                  # reality is flatter than the model: model over-confident
    y = sample_outcomes(truth, seed=8)
    T = F.fit_temperature(p, y)
    assert 1.15 < T < 1.45


def test_fit_platt_recovers_known_recalibration():
    p = synthetic_probs(40000, seed=9)
    q = p.max(1)
    hit_p = F.inv_logit(0.2 + 0.8 * F.logit(q))
    rng = np.random.default_rng(10)
    hit = rng.random(len(p)) < hit_p
    fav = p.argmax(1)
    other = (fav + 1 + (rng.random(len(p)) < 0.5)) % 3
    y = np.where(hit, fav, other)
    fit = F.fit_platt_fav(p, y)
    assert abs(fit["a"] - 0.2) < 0.12 and abs(fit["b"] - 0.8) < 0.12


def test_fit_home_term_recovers_known_shift():
    rng = np.random.default_rng(11)
    mh, ma = rng.uniform(0.6, 2.4, 6000), rng.uniform(0.6, 2.4, 6000)   # SYNTHETIC expected goals
    true_h = 0.25
    a, b = F.ratio_shrink_mu(mh, ma, 1.0, true_h)
    y = sample_outcomes(C.p1x2_from_mu(a, b, LAYER), seed=12)
    fit = F.fit_ratio_shrink(C.p1x2_from_mu(mh, ma, LAYER), mh, ma, y, LAYER, free_k=False, free_h=True)
    assert fit["k"] == 1.0 and abs(fit["h"] - true_h) < 0.09


def test_fit_on_calibrated_probabilities_finds_no_change():
    p = synthetic_probs(40000, seed=13)
    y = sample_outcomes(p, seed=14)                # outcomes drawn from the model itself: nothing to fix
    assert abs(F.fit_temperature(p, y) - 1.0) < 0.06
    fit = F.fit_platt_fav(p, y)
    assert abs(fit["a"]) < 0.08 and abs(fit["b"] - 1.0) < 0.08


# ----------------------------------------------------------------------------- statistics helpers
def test_wilson_and_bootstrap_helpers():
    lo, hi = C.wilson(50, 100)
    assert lo < 0.5 < hi and abs((lo + hi) / 2 - 0.5) < 0.01
    assert C.wilson(0, 0)[0] != C.wilson(0, 0)[0]            # NaN for n = 0
    d = np.random.default_rng(15).normal(-0.01, 0.1, 500)
    a, b = C.paired_boot(d), C.paired_boot(d)
    assert a == b                                            # fixed seed 7: reproducible
    assert a["ci90"][0] < a["mean"] < a["ci90"][1] and a["n"] == 500
    assert C.paired_boot(np.array([]))["n"] == 0


def test_fav_table_counts_and_bands():
    p = synthetic_probs(1000, seed=16)
    y = sample_outcomes(p, seed=17)
    rows = C.fav_table(p, y)
    assert sum(r["n"] for r in rows) == 1000
    assert C.fav_ge(p, y, 0.7)["n"] == int((p.max(1) >= 0.7).sum())


# ----------------------------------------------------------------------------- the test split stays out of the select stage
def test_load_baseline_drops_rows_without_prediction_and_split_filter(tmp_path):
    import csv
    import gzip
    cols = ["match_id", "kickoff", "split", "competition_provider_id", "comp_type", "home_team_id", "away_team_id",
            "status", "mu_home", "mu_away", "p_home", "p_draw", "p_away", "home_goals", "away_goals"]
    rows = []
    for i in range(9):                                       # SYNTHETIC rows
        split = ("train", "validation", "test")[i % 3]
        rows.append([str(i), "2025-01-01T00:00:00", split, "42" if i % 2 else "47", "european" if i % 2 else "league",
                     "1", "2", "ok" if i != 4 else "no_lambda", "1.4", "1.1", "0.45", "0.27", "0.28", "2", "1"])
    path = tmp_path / "synthetic_baseline.csv.gz"
    with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    d = C.load_baseline(path)
    assert d["n"] == 8                                       # the 'no_lambda' row is dropped, never imputed
    keep = C.subset(d, d["split"] != "test")
    assert set(keep["split"]) == {"train", "validation"}
    assert keep["n"] == int((d["split"] != "test").sum())


def test_evaluate_refuses_without_frozen_file(tmp_path, monkeypatch):
    import calibration_evaluate as E
    monkeypatch.setattr(E, "FROZEN", tmp_path / "missing_frozen.json")
    with pytest.raises(SystemExit):
        E.main(["--split", "test", "--outdir", str(tmp_path)])
    with pytest.raises(SystemExit):                          # a non-test mechanics check may not write into data/training
        E.main(["--split", "validation"])


# ----------------------------------------------------------------------------- candidate (d): club offsets (SYNTHETIC UEFA table)
import calibration_offset as O  # noqa: E402


def synthetic_uefa_table(seed: int = 21, n: int = 240) -> dict:
    """SYNTHETIC UEFA matches between 8 fake clubs (ids "t0".."t7"), one match per day-slot; not football data."""
    rng = np.random.default_rng(seed)
    teams = [f"t{i}" for i in range(8)]
    home, away = [], []
    for _ in range(n):
        a, b = rng.choice(8, 2, replace=False)
        home.append(teams[a])
        away.append(teams[b])
    day = np.arange(n) * 2.0 + 18000.0                         # a match every two days
    kick = [str(np.datetime64(int(x * 86400), "s")) for x in day]
    mu_h, mu_a = rng.uniform(0.8, 2.2, n), rng.uniform(0.6, 1.8, n)
    hg, ag = rng.poisson(mu_h), rng.poisson(mu_a)
    return {"n": n, "euro": np.ones(n, bool), "home_id": np.array(home), "away_id": np.array(away),
            "kickoff": np.array(kick), "match_id": np.array([f"m{i}" for i in range(n)]), "mu_h": mu_h, "mu_a": mu_a,
            "hg": hg.astype(int), "ag": ag.astype(int)}


def test_offset_has_no_look_ahead():
    d = synthetic_uefa_table()
    z = O.build_z(d, "gd", 6.0, None)
    cut = 120
    # change the match itself and everything after it: offsets of row `cut` and before must not move
    d2 = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in d.items()}
    d2["hg"][cut:] += 3
    d2["ag"][cut:] = 0
    z2 = O.build_z(d2, "gd", 6.0, None)
    assert np.allclose(z[:cut + 1], z2[:cut + 1])             # row `cut` itself included: its own result is not used
    assert not np.allclose(z[cut + 1:], z2[cut + 1:])         # later rows do see the earlier change
    # a match that kicked off less than 3 hours before is not used
    d3 = synthetic_uefa_table(seed=22, n=4)
    d3["home_id"][:] = ["a", "a", "a", "b"]
    d3["away_id"][:] = ["c", "c", "c", "a"]
    d3["kickoff"] = np.array(["2026-01-01T12:00:00", "2026-01-01T12:00:00", "2026-01-01T12:00:00", "2026-01-01T13:00:00"])
    zz = O.build_z(d3, "gd", 6.0, None)
    assert np.all(zz == 0.0)                                  # all previous matches are < 3 h old: no information


def test_offset_shrinkage_and_decay_math():
    d = synthetic_uefa_table(seed=23, n=60)
    res = O.home_view_residual(d, None, "gd")
    day = O.day_numbers(d["kickoff"])
    hist = O._team_history(d, res, day)
    team = d["home_id"][0]
    t_last = day.max() + 1.0
    o, n_eff, n = O.team_offset(hist, team, t_last, k=5.0, half_life=None)
    times, r = hist[team]
    assert n == len(r) and abs(n_eff - len(r)) < 1e-12 and abs(o - r.sum() / (len(r) + 5.0)) < 1e-12
    o_far, _, _ = O.team_offset(hist, team, t_last, k=1e9, half_life=None)
    assert abs(o_far) < 1e-6                                  # a huge shrinkage pulls every offset to 0
    od, n_eff_d, _ = O.team_offset(hist, team, t_last, k=5.0, half_life=30.0)
    assert n_eff_d < n_eff                                    # decay reduces the effective sample
    assert O.team_offset(hist, "unknown_club", t_last, 5.0, None) == (0.0, 0.0, 0)


def test_xgd_metric_skips_matches_without_xg():
    d = synthetic_uefa_table(seed=24, n=30)
    xg = {m: (1.0, 0.5) for m in d["match_id"]}
    xg[d["match_id"][3]] = None                               # FotMob sent no xG: skipped, never imputed
    res = O.home_view_residual(d, xg, "xgd")
    assert np.isnan(res[3]) and np.isfinite(np.delete(res, 3)).all()
    assert np.isclose(res[0], (1.0 - 0.5) - (d["mu_h"][0] - d["mu_a"][0]))


def test_team_offset_fix_formula_and_recovery():
    rng = np.random.default_rng(25)
    n = 6000
    mh, ma = rng.uniform(0.6, 2.4, n), rng.uniform(0.6, 2.4, n)
    z = rng.normal(0.0, 0.4, n)                               # SYNTHETIC offsets
    p = C.p1x2_from_mu(mh, ma, LAYER)
    fix = {"kind": "team_offset", "scope": "uefa", "gamma": 0.3, "h": 0.1}
    out = F.apply_fix(fix, p, mh, ma, np.ones(n, bool), LAYER, z=z)
    d2 = np.log(mh / ma) + 0.1 + 0.3 * z
    w = 1 / (1 + np.exp(-d2))
    assert np.allclose(out, C.p1x2_from_mu((mh + ma) * w, (mh + ma) * (1 - w), LAYER))
    with pytest.raises(ValueError):
        F.apply_fix(fix, p, mh, ma, np.ones(n, bool), LAYER)  # z is required
    y = sample_outcomes(out, seed=26)
    fit = F.fit_offset(mh, ma, z, y, LAYER, free_h=True)
    assert abs(fit["gamma"] - 0.3) < 0.15 and abs(fit["h"] - 0.1) < 0.08


# ----------------------------------------------------------------------------- candidate JSON (real output file, structure only)
CANDIDATE = Path(__file__).resolve().parents[1] / "data" / "training" / "calibration_candidate.json"


def _strict(path: Path) -> dict:
    def bad(x):
        raise ValueError(f"non-strict JSON constant {x}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=bad)


def _check_ratio_formula(fix: dict, layer: dict) -> None:
    mh, ma = np.array([1.8]), np.array([0.9])
    p = C.p1x2_from_mu(mh, ma, layer)
    out = F.apply_fix(fix, p, mh, ma, np.array([True]), layer)
    d2 = fix["k"] * np.log(1.8 / 0.9) + fix["h"]
    w = 1 / (1 + np.exp(-d2))
    exp = C.p1x2_from_mu(np.array([2.7 * w]), np.array([2.7 * (1 - w)]), layer)
    assert np.allclose(out, exp)


@pytest.mark.skipif(not CANDIDATE.exists(), reason="calibration_candidate.json not generated yet")
def test_candidate_json_structure_and_deploy_rule():
    c = _strict(CANDIDATE)
    for key in ("name", "status", "formula", "parameters", "validation_choices_round2", "test_round2", "deploy_criteria",
                "round1", "recommendation", "tonight_illustration", "chosen_by_round2_rule"):
        assert key in c
    # round 1 (UEFA home term, first test read) keeps its structure and follows the written deploy rule
    r1 = c["round1"]
    assert r1["test"]["read_once"] is True
    dc1 = r1["deploy_criteria"]
    ov1 = r1["test"]["metrics_train_fit"]["all"]["logloss"]
    tg1 = r1["test"]["metrics_train_fit"]["uefa"]["logloss"]
    assert dc1["deploy"] is bool((ov1["ci90"][1] < 0 or tg1["ci90"][1] < 0) and dc1["rest_not_worse"])
    assert r1["recommendation"].startswith("DEPLOY" if dc1["deploy"] else "DO NOT DEPLOY")
    f1 = r1["parameters"]["train_fit_TESTED"]
    if f1["kind"] == "ratio_shrink":
        _check_ratio_formula(f1, r1["parameters"]["goal_layer"])
    # round 2: the verdict of the chosen candidate follows the same rule
    ch = c["chosen_by_round2_rule"]
    b = c["test_round2"][ch]
    ov, tg = b["metrics"]["all"]["logloss"], b["metrics"]["uefa"]["logloss"]
    rest_ok = b["metrics"]["league"]["logloss"]["diff"] <= 0
    assert c["deploy_criteria"]["deploy"] is bool((ov["ci90"][1] < 0 or tg["ci90"][1] < 0) and rest_ok)
    assert c["recommendation"].startswith("DEPLOY" if c["deploy_criteria"]["deploy"] else "DO NOT DEPLOY")
    f2 = c["parameters"]["chosen_train_fit_TESTED"]
    if f2["kind"] == "ratio_shrink":
        _check_ratio_formula(f2, c["parameters"]["goal_layer"])
    assert set(c["tonight_illustration"]["matches"]) == {"fotmob_6106254", "fotmob_6106284"}
