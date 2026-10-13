"""Fit the production goal layer and record its validation evidence.

Method (validated on a time split in train_goal_model.py): shrink total goals
toward the mean in log space (a, b), keep the home/away supremacy unchanged
(c = 1), Dixon-Coles low-score correction rho, negative-binomial dispersion r.
Step 1 fits on rows before --split and scores the held-out rows; step 2 refits
on every row for production. Writes config/goal_model.json.

Usage (from backend/): venv/Scripts/python.exe scripts/training/fit_goal_layer.py
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parent))
import train_goal_model as T  # noqa: E402


def fit_layer(rows):
    lh = np.array([x["lh"] for x in rows])
    la = np.array([x["la"] for x in rows])
    hs = np.clip(np.array([x["hs"] for x in rows]), 0, T.MAX_GOALS)
    as_ = np.clip(np.array([x["as"] for x in rows]), 0, T.MAX_GOALS)
    idx = np.arange(len(rows))
    m = float(np.mean((np.log(lh) + np.log(la)) / 2))

    def nll(t):
        p = {"m": m, "a": t[0], "b": t[1], "c": 1.0}
        l1, l2 = T.transform(lh, la, p)
        mat = T.score_matrix(l1, l2, t[2], math.exp(t[3]))
        return -np.sum(np.log(np.clip(mat[idx, hs, as_], 1e-12, 1)))

    res = minimize(
        nll, np.array([1.0, 0.0, -0.03, math.log(50.0)]), method="L-BFGS-B",
        bounds=[(0.2, 1.5), (-0.3, 0.3), (-0.3, 0.3), (0.0, math.log(1000.0))],
    )
    return {"m": m, "a": float(res.x[0]), "b": float(res.x[1]), "c": 1.0,
            "rho": float(res.x[2]), "nb_dispersion": float(math.exp(res.x[3]))}


def score(rows, p):
    lh = np.array([x["lh"] for x in rows])
    la = np.array([x["la"] for x in rows])
    l1, l2 = T.transform(lh, la, p) if p else (lh, la)
    return T.evaluate(rows, l1, l2, p.get("rho", 0.0) if p else 0.0, p.get("nb_dispersion") if p else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/training/walkforward_lambdas.csv")
    ap.add_argument("--split", default="2026-07-01")
    ap.add_argument("--out", default="config/goal_model.json")
    args = ap.parse_args()

    rows = T.load(Path(args.data))
    split = datetime.fromisoformat(args.split)
    train = [x for x in rows if x["at"] < split]
    test = [x for x in rows if x["at"] >= split]

    validation_params = fit_layer(train)
    held_out = {"raw": score(test, {}), "goal_layer": score(test, validation_params)}
    production = fit_layer(rows)

    keep = ("1x2_logloss", "1x2_brier", "over25_logloss", "over25_brier", "over35_logloss",
            "btts_logloss", "btts_brier", "score_logloss", "mean_pred_total", "mean_actual_total")
    out = {
        "description": "Goal layer over global team ratings: log-space total-goal shrinkage "
                       "(a, b around m), supremacy unchanged (c = 1), Dixon-Coles rho, NB dispersion.",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "data": args.data,
        "n_rows": len(rows),
        "params": production,
        "validation": {
            "split": args.split, "n_train": len(train), "n_test": len(test),
            "params_fitted_on_train": validation_params,
            "held_out_test": {k: {m: round(v[m], 4) for m in keep} for k, v in held_out.items()},
        },
    }
    Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
