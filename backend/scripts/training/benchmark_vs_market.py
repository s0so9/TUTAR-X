"""Benchmark the model against bookmakers' closing odds, and backtest value bets.

Joins out-of-sample model lambdas (walk-forward, goals/xG ratings + the trained
goal layer) with football-data.co.uk closing odds (data/external/
football_data_matches.csv, matched to DB matches by db_match_id). Reports:
  * log loss / Brier of model vs margin-free closing probabilities (1X2, O/U 2.5);
  * a flat-stake backtest of the "value" rule at closing odds: bet an outcome when
    model_p * odds - 1 >= --min-ev and the model-market conflict guard passes
    (model - implied <= 8 points and model / implied <= 1.5), with a bootstrap 90% CI.
Closing odds are the hardest price to beat; a model without an edge here should
not be advertised as finding value. Lineup value/form adjustments are NOT included.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.prediction.goal_model import get_goal_layer  # noqa: E402
import train_goal_model as T  # noqa: E402


def f(x):
    try:
        v = float(x)
        return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lambdas", default="data/training/walkforward_lambdas_xg.csv")
    ap.add_argument("--odds", default="data/external/football_data_matches.csv")
    ap.add_argument("--min-ev", type=float, default=0.03)
    ap.add_argument("--out", default="data/training/benchmark_vs_market.json")
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
            odds = [f(r.get(k)) for k in ("PSCH", "PSCD", "PSCA")]
            if None in odds:
                odds = [f(r.get(k)) for k in ("AvgCH", "AvgCD", "AvgCA")]
            ou = [f(r.get("PC>2.5")), f(r.get("PC<2.5"))]
            if None in ou:
                ou = [f(r.get("AvgC>2.5")), f(r.get("AvgC<2.5"))]
            lh, la = layer.adjust(float(m["lambda_home"]), float(m["lambda_away"]))
            rows.append({
                "lh": lh, "la": la, "hs": int(m["home_score"]), "as": int(m["away_score"]),
                "mk1x2": [float(r["p_close_home"]), float(r["p_close_draw"]), float(r["p_close_away"])],
                "odds1x2": odds if None not in odds else None,
                "mkover": float(r["p_close_over25"]) if r.get("p_close_over25") else None,
                "oddsou": ou if None not in ou else None,
                "division": r["division"],
            })
    print(f"matched matches with closing odds: {len(rows)}")

    lh = np.array([x["lh"] for x in rows]); la = np.array([x["la"] for x in rows])
    mat = T.score_matrix(lh, la, layer.rho or 0.0, layer.nb_dispersion)
    p1x2, o25, _, _ = T.markets(mat)
    hs = np.array([x["hs"] for x in rows]); as_ = np.array([x["as"] for x in rows])
    k = np.where(hs > as_, 0, np.where(hs == as_, 1, 2))
    mk = np.array([x["mk1x2"] for x in rows])
    eps = 1e-12
    res = {"n": len(rows)}
    res["1x2_logloss_model"] = float(-np.mean(np.log(np.clip(p1x2[np.arange(len(k)), k], eps, 1))))
    res["1x2_logloss_market"] = float(-np.mean(np.log(np.clip(mk[np.arange(len(k)), k], eps, 1))))
    has_ou = np.array([x["mkover"] is not None for x in rows])
    y = (hs + as_) > 2.5
    mko = np.array([x["mkover"] if x["mkover"] is not None else 0.5 for x in rows])
    res["ou25_n"] = int(has_ou.sum())
    res["ou25_logloss_model"] = float(-np.mean(np.where(y, np.log(o25), np.log(1 - o25))[has_ou]))
    res["ou25_logloss_market"] = float(-np.mean(np.where(y, np.log(mko), np.log(1 - mko))[has_ou]))

    # Value-bet backtest at closing odds
    bets = []
    for i, x in enumerate(rows):
        cands = []
        if x["odds1x2"]:
            for j in range(3):
                cands.append((p1x2[i, j], x["odds1x2"][j], k[i] == j))
        if x["oddsou"]:
            cands.append((o25[i], x["oddsou"][0], bool(y[i])))
            cands.append((1 - o25[i], x["oddsou"][1], not bool(y[i])))
        for p, o, won in cands:
            implied = 1 / o
            if p * o - 1 >= args.min_ev and p - implied <= 0.08 and p / implied <= 1.5:
                bets.append(o - 1 if won else -1.0)
    bets = np.array(bets)
    if len(bets):
        rng = np.random.default_rng(7)
        boots = [rng.choice(bets, len(bets)).mean() for _ in range(2000)]
        res["value_bets"] = {"n": int(len(bets)), "roi": float(bets.mean()),
                             "roi_ci90": [float(np.percentile(boots, 5)), float(np.percentile(boots, 95))],
                             "min_ev": args.min_ev}
    Path(args.out).write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
