"""Our production model (out-of-sample, baseline_predictions_full) against the market, in the metrics the
literature uses (accuracy, RPS, log loss), plus a market + model logarithmic pool fitted on validation and
scored once on test. Research only (2026-10-15).

Run (from backend/): OMP_NUM_THREADS=2 venv/Scripts/python.exe scripts/research/sota_model_vs_market.py
Output: backend/data/research/sota_model_vs_market.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sota_common as C  # noqa: E402


def pool(logs: list[np.ndarray], w: np.ndarray, b: np.ndarray | None = None) -> np.ndarray:
    z = sum(wi * li for wi, li in zip(w, logs))
    if b is not None:
        z = z + np.array([0.0, b[0], b[1]])
    z = z - z.max(1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


def fit_pool(logs, y, with_bias=True):
    k = len(logs)

    def f(theta):
        w = theta[:k]
        b = theta[k:] if with_bias else None
        return C.logloss(pool(logs, w, b), y).mean()

    x0 = np.r_[np.ones(k) / k, np.zeros(2 if with_bias else 0)]
    r = minimize(f, x0, method="Nelder-Mead", options={"maxiter": 4000, "xatol": 1e-6, "fatol": 1e-8})
    return r.x


def main() -> None:
    preds = C.read_csv_gz(C.DATA / "training" / "baseline_predictions_full.csv.gz")
    odds = C.odds_by_fotmob_id(C.load_odds_rows())
    recs = []
    for r in preds:
        if r["split"] not in ("train", "validation", "test") or not r["p_home"] or r["result"] not in "HDA":
            continue
        y = {"H": 0, "D": 1, "A": 2}[r["result"]]
        o = odds.get(r["match_id"])
        recs.append({"id": r["match_id"], "split": r["split"], "comp": r["competition_provider_id"],
                     "euro": r["comp_type"] == "european", "y": y,
                     "p": np.array([float(r["p_home"]), float(r["p_draw"]), float(r["p_away"])]),
                     "o": o})
    out: dict = {"note": "model = production baseline (train-only goal layer, walk-forward lambdas, + value/form "
                         "shifts), out-of-sample; market = de-vigged (proportional) odds from football-data.co.uk"}

    # unrestricted model numbers per split
    for sp in ("train", "validation", "test"):
        sel = [r for r in recs if r["split"] == sp]
        P = np.array([r["p"] for r in sel]); Y = np.array([r["y"] for r in sel])
        out.setdefault("model_all_rows", {})[sp] = C.summary(P, Y)
        euro = [r for r in sel if r["euro"]]
        if euro:
            out.setdefault("model_european_rows", {})[sp] = C.summary(np.array([r["p"] for r in euro]),
                                                                       np.array([r["y"] for r in euro]))

    # same rows: model vs markets
    for sp in ("validation", "test"):
        for src in ("close", "ps_close", "ps_pre", "avg_pre"):
            sel = [r for r in recs if r["split"] == sp and r["o"] and r["o"].get(src) is not None]
            if not sel:
                continue
            Y = np.array([r["y"] for r in sel])
            Pm = np.array([r["p"] for r in sel]); Pk = np.array([r["o"][src] for r in sel])
            blk = {"n": len(sel), "model": C.summary(Pm, Y), "market": C.summary(Pk, Y),
                   "logloss_model_minus_market": C.paired_ci(C.logloss(Pm, Y), C.logloss(Pk, Y)),
                   "rps_model_minus_market": C.paired_ci(C.rps(Pm, Y), C.rps(Pk, Y))}
            # top 5 subset
            t5 = np.array([r["o"]["division"] in C.TOP5 for r in sel])
            if t5.any():
                blk["top5"] = {"n": int(t5.sum()), "model": C.summary(Pm[t5], Y[t5]),
                               "market": C.summary(Pk[t5], Y[t5])}
            out.setdefault("model_vs_market", {}).setdefault(sp, {})[src] = blk

    # logarithmic pool: fit on validation, score on test (pre-closing = information available when betting early)
    for src in ("ps_pre", "avg_pre", "close"):
        va = [r for r in recs if r["split"] == "validation" and r["o"] and r["o"].get(src) is not None]
        te = [r for r in recs if r["split"] == "test" and r["o"] and r["o"].get(src) is not None]
        if len(va) < 300 or len(te) < 300:
            continue
        def arr(sel):
            return (np.log(np.clip(np.array([r["p"] for r in sel]), 1e-9, 1)),
                    np.log(np.clip(np.array([r["o"][src] for r in sel]), 1e-9, 1)),
                    np.array([r["y"] for r in sel]))
        lm_v, lk_v, y_v = arr(va)
        lm_t, lk_t, y_t = arr(te)
        th = fit_pool([lm_v, lk_v], y_v, with_bias=True)
        th_m = fit_pool([lk_v], y_v, with_bias=True)  # market-only recalibration (FLB / draw correction)
        Pb = pool([lm_t, lk_t], th[:2], th[2:])
        Pk_re = pool([lk_t], th_m[:1], th_m[1:])
        Pk = np.exp(lk_t); Pm = np.exp(lm_t)
        out.setdefault("pool_fit_on_validation_test_once", {})[src] = {
            "n_validation": len(va), "n_test": len(te),
            "weights_model_market_bias_draw_away": [round(float(x), 4) for x in th],
            "market_only_recal_weight_bias": [round(float(x), 4) for x in th_m],
            "test": {"model": C.summary(Pm, y_t), "market": C.summary(Pk, y_t),
                     "market_recalibrated": C.summary(Pk_re, y_t), "pool": C.summary(Pb, y_t)},
            "pool_minus_market_logloss": C.paired_ci(C.logloss(Pb, y_t), C.logloss(Pk, y_t)),
            "pool_minus_market_recal_logloss": C.paired_ci(C.logloss(Pb, y_t), C.logloss(Pk_re, y_t)),
            "market_recal_minus_market_logloss": C.paired_ci(C.logloss(Pk_re, y_t), C.logloss(Pk, y_t))}

    C.OUT.mkdir(parents=True, exist_ok=True)
    path = C.OUT / "sota_model_vs_market.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1)[:12000])
    print("wrote", path)


if __name__ == "__main__":
    main()
