"""Does the model add information to the closing market? Logarithmic pooling.

p_blend ∝ p_market^w_mkt · p_model^w_mod (1X2, renormalised), fitted by
maximum likelihood on matches before --split, scored on the rest. If the
blend beats the market alone on held-out matches, the model carries
information the market lacks; the fitted weights say how much.

Usage (from backend/): venv/Scripts/python.exe scripts/training/fit_market_blend.py
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.prediction.goal_model import get_goal_layer  # noqa: E402
import train_goal_model as T  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lambdas", default="data/training/walkforward_lambdas_xg.csv")
    ap.add_argument("--odds", default="data/external/football_data_matches.csv")
    ap.add_argument("--split", default="2026-04-01")
    ap.add_argument("--out", default="data/training/market_blend.json")
    args = ap.parse_args()

    layer = get_goal_layer()
    lam = {}
    with open(args.lambdas, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            lam[r["match_id"]] = r
    rows = []
    with open(args.odds, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            m = lam.get(r.get("db_match_id") or "")
            if not m or r.get("db_score_agrees") != "1" or not r.get("p_close_home"):
                continue
            rows.append((m, [float(r["p_close_home"]), float(r["p_close_draw"]), float(r["p_close_away"])]))
    lh = np.array([layer.adjust(float(m["lambda_home"]), float(m["lambda_away"]))[0] for m, _ in rows])
    la = np.array([layer.adjust(float(m["lambda_home"]), float(m["lambda_away"]))[1] for m, _ in rows])
    pmod, _, _, _ = T.markets(T.score_matrix(lh, la, layer.rho or 0.0, layer.nb_dispersion))
    pmkt = np.array([p for _, p in rows])
    hs = np.array([int(m["home_score"]) for m, _ in rows]); as_ = np.array([int(m["away_score"]) for m, _ in rows])
    k = np.where(hs > as_, 0, np.where(hs == as_, 1, 2))
    at = np.array([datetime.fromisoformat(m["kickoff"]) for m, _ in rows])
    tr = at < datetime.fromisoformat(args.split)
    te = ~tr

    def blend(wm, wd, idx):
        logp = wm * np.log(pmkt[idx]) + wd * np.log(np.clip(pmod[idx], 1e-9, 1))
        logp -= logp.max(axis=1, keepdims=True)
        p = np.exp(logp)
        return p / p.sum(axis=1, keepdims=True)

    def ll(p, idx):
        return float(-np.mean(np.log(np.clip(p[np.arange(idx.sum()), k[idx]], 1e-12, 1))))

    res = minimize(lambda w: ll(blend(w[0], w[1], tr), tr), np.array([1.0, 0.0]), method="L-BFGS-B",
                   bounds=[(0, 2), (0, 2)])
    wm, wd = map(float, res.x)
    out = {
        "n_train": int(tr.sum()), "n_test": int(te.sum()), "split": args.split,
        "w_market": wm, "w_model": wd,
        "test_logloss": {
            "market": ll(pmkt[te], te),
            "model": ll(np.clip(pmod[te], 1e-12, 1), te),
            "blend": ll(blend(wm, wd, te), te),
        },
    }
    Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
