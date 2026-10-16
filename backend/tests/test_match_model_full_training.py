"""Full-data match model (scripts/training/train_match_model_full.py): synthetic data only.

Checks: the fit reaches a stationary point of its analytic-gradient objective, unknown feature values
become z = 0 plus an indicator (never an imputed number), standardised features are clipped, the
select stage never uses test rows (changing test labels changes nothing in the frozen choice) and the
final stage runs end to end (strict JSON, prediction files, deploy-criteria structure).
"""

from __future__ import annotations

import csv
import gzip
import json
import sys
from pathlib import Path

import numpy as np
import pytest

TRAINING_DIR = Path(__file__).resolve().parents[1] / "scripts" / "training"
sys.path.insert(0, str(TRAINING_DIR))

import train_match_model_full as F  # noqa: E402
import train_match_model as M  # noqa: E402

LAYER = {"m": 0.25, "a": 0.55, "b": 0.02, "rho": -0.02, "nb_dispersion": 200.0}


def write_layer(path: Path) -> None:
    path.write_text(json.dumps({"params": {**LAYER, "c": 1.0}}), encoding="utf-8")


def make_features(path: Path, test_goal_shift: int = 0, seed: int = 3) -> None:
    """Synthetic match_features_full.csv.gz: goals depend on the rating lambdas and on the XI delta."""
    rng = np.random.default_rng(seed)
    cols = ["match_id", "kickoff", "split", "competition_provider_id", "comp_type", "comp_is_euro", "home_team_id",
            "away_team_id", "lambda_home_raw", "lambda_away_raw", "y_home_goals", "y_away_goals", "value_log_ratio",
            "lineup_form"] + [f"{s}_{c}" for s in F.SIDES for c in F.SIDE_COLS]
    plan = [("train", 420), ("validation", 160), ("test", 120)]
    rows = []
    i = 0
    for split, n in plan:
        for j in range(n):
            i += 1
            euro = int(j % 6 == 0)
            lh, la = float(np.exp(rng.normal(0.3, 0.3))), float(np.exp(rng.normal(0.1, 0.3)))
            r = {"match_id": str(1000 + i), "kickoff": f"2023-0{1 + (i % 9)}-15T18:00:00", "split": split,
                 "competition_provider_id": "42" if euro else "47", "comp_type": "european" if euro else "league",
                 "comp_is_euro": euro, "home_team_id": "1", "away_team_id": "2", "lambda_home_raw": lh,
                 "lambda_away_raw": la, "lineup_form": ""}
            xi_h, xi_a = rng.normal(0, 0.13), rng.normal(0, 0.13)
            r["value_log_ratio"] = "" if j % 5 == 0 else rng.normal(0, 1.0)
            r.update({"home_xi_d_off": xi_h, "away_xi_d_off": xi_a, "home_xi_d_def": rng.normal(0, 0.05),
                      "away_xi_d_def": rng.normal(0, 0.05),
                      "home_unavail_off_w": "" if j % 4 == 0 else abs(rng.normal(0, 0.03)),
                      "away_unavail_off_w": "" if j % 4 == 0 else abs(rng.normal(0, 0.03)),
                      "home_unavail_def_w": "" if j % 4 == 0 else abs(rng.normal(0, 0.02)),
                      "away_unavail_def_w": "" if j % 4 == 0 else abs(rng.normal(0, 0.02)),
                      "home_xg_for_l5": rng.normal(1.4, 0.4), "away_xg_for_l5": rng.normal(1.4, 0.4),
                      "home_xg_against_l5": rng.normal(1.4, 0.4), "away_xg_against_l5": rng.normal(1.4, 0.4),
                      "home_ppg_l5": rng.uniform(0, 3), "away_ppg_l5": rng.uniform(0, 3)})
            r["y_home_goals"] = int(rng.poisson(lh * np.exp(0.8 * xi_h)))
            r["y_away_goals"] = int(rng.poisson(la * np.exp(0.8 * xi_a)))
            if split == "test":
                r["y_home_goals"] += test_goal_shift
            rows.append(r)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def args_for(tmp: Path, name: str, shift: int = 0):
    feats = tmp / f"features_{name}.csv.gz"
    make_features(feats, test_goal_shift=shift)
    write_layer(tmp / "layer_train.json")
    write_layer(tmp / "layer_trainval.json")
    return F.argparse.Namespace(
        stage="select", features=feats, goal_layer_train=tmp / "layer_train.json",
        goal_layer_trainval=tmp / "layer_trainval.json", frozen=tmp / f"frozen_{name}.json",
        report=tmp / f"report_{name}.json", candidate=tmp / f"candidate_{name}.json",
        pred_validation=tmp / f"pv_{name}.csv.gz", pred_test=tmp / f"pt_{name}.csv.gz",
        odds_current=tmp / "none1.csv", odds_history=tmp / "none2.csv", db=tmp / "none.db")


def test_fit_reaches_stationary_point(tmp_path):
    feats = tmp_path / "f.csv.gz"
    make_features(feats)
    rows = [r for r in F.load_rows(feats, ("train",))]
    D = F.Data(rows)
    lh, la = D.layered(LAYER)
    m = F.Model(F.Design(F.GROUPS, 100.0, 100.0, False)).fit(D, lh, la, LAYER["rho"], LAYER["nb_dispersion"])
    assert m.converged
    dz = m.design
    Xh, Xa = dz.matrices(D, lh, la)
    llh, lla = np.log(lh), np.log(la)

    def f(th):
        ll = M.score_loglik(llh + Xh @ th, lla + Xa @ th, D.hs, D.as_, m.rho, m.r)
        return -ll.sum() + 0.5 * np.sum(dz.pen * th * th)

    free = np.arange(4, len(m.theta))              # the four league recalibration terms are fixed at 0
    for j in free:
        e = np.zeros_like(m.theta)
        e[j] = 1e-5
        assert abs((f(m.theta + e) - f(m.theta - e)) / 2e-5) < 0.05
    assert np.all(m.theta[:4] == 0.0)


def test_missing_values_become_zero_plus_indicator_and_z_is_clipped(tmp_path):
    feats = tmp_path / "f.csv.gz"
    make_features(feats)
    rows = F.load_rows(feats, ("train",))[:50]
    rows[0]["home_xi_d_off"] = None             # unknown
    rows[1]["home_xi_d_off"] = 50.0             # absurd outlier
    D = F.Data(rows)
    lh, la = D.layered(LAYER)
    dz = F.Design(["xi"], 100.0, None, True).fit_stats(D, lh, la)
    Xh, _Xa = dz.matrices(D, lh, la)
    j = dz.names.index("xi_off_att")
    k = dz.names.index("xi_miss_att")
    assert Xh[0, j] == 0.0 and Xh[0, k] == 1.0
    assert Xh[1, j] == F.CLIP and Xh[1, k] == 0.0
    assert Xh[2, k] == 0.0


def test_select_never_uses_test_rows_and_final_runs(tmp_path):
    a1 = args_for(tmp_path, "a", shift=0)
    a2 = args_for(tmp_path, "b", shift=7)      # test labels changed: the frozen choice must not move
    assert F.select_stage(a1) == 0
    assert F.select_stage(a2) == 0
    f1, f2 = (json.loads(a.frozen.read_text(encoding="utf-8")) for a in (a1, a2))
    for k in ("groups", "l2", "l2_euro", "recal", "validation_score_logloss", "n_train", "n_validation", "trace"):
        if k == "trace":
            strip = lambda t: [{x: y for x, y in e.items() if x != "seconds"} for e in t]  # noqa: E731
            assert strip(f1[k]) == strip(f2[k])
        else:
            assert f1[k] == f2[k], k
    assert f1["n_train"] == 420 and f1["n_validation"] == 160

    assert F.final_stage(a1) == 0
    rep = json.loads(a1.report.read_text(encoding="utf-8"))         # strict JSON (no NaN)
    assert rep["rows"] == {"train": 420, "validation": 160, "test": 120}
    assert set(rep["deploy_criteria"]) >= {"a", "b", "c", "all_pass"}
    assert rep["test"]["segments"]["all"]["n"] == 120
    cand = json.loads(a1.candidate.read_text(encoding="utf-8"))
    assert cand["evaluated_model"]["fit_rows"]["n"] == 580 and cand["refit_all_rows"]["fit_rows"]["n"] == 700
    assert cand["evaluated_model"]["goal_layer"]["path"].endswith("layer_trainval.json")
    for p, n in ((a1.pred_validation, 160), (a1.pred_test, 120)):
        with gzip.open(p, "rt", encoding="utf-8", newline="") as fh:
            rd = list(csv.DictReader(fh))
        assert len(rd) == n
        for r in rd:
            for pre in ("base", "model"):
                assert abs(float(r[f"{pre}_p_home"]) + float(r[f"{pre}_p_draw"]) + float(r[f"{pre}_p_away"]) - 1) < 1e-4
    # a different test label set changes the test metrics (the test split is scored in `final` only)
    assert F.final_stage(a2) == 0
    rep2 = json.loads(a2.report.read_text(encoding="utf-8"))
    assert rep2["test"]["segments"]["all"]["1x2_logloss"]["model"] != rep["test"]["segments"]["all"]["1x2_logloss"]["model"]
    assert rep2["validation_fit_on_train"]["segments"]["all"] == rep["validation_fit_on_train"]["segments"]["all"]
