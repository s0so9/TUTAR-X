"""Train the goal-distribution layer on out-of-sample rating lambdas.

Input: data/training/walkforward_lambdas.csv (scripts/training/walkforward_dataset.py).
Time split: rows kicked off before --split are training, the rest are a held-out
test. Fits by maximum likelihood on training rows only:
  * goal scale: lambda_home * k_home, lambda_away * k_away
  * Dixon-Coles low-score correction rho
  * Negative-binomial dispersion r (variance = mu + mu^2 / r)
and reports log loss / Brier on the held-out rows for 1X2, Over/Under 2.5 and
both-teams-to-score, plus calibration tables. Writes the fitted parameters to
--out (JSON) with the evidence that justified them.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import poisson

MAX_GOALS = 10
G = np.arange(MAX_GOALS + 1)


def load(path: Path):
    rows = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({
                "at": datetime.fromisoformat(r["kickoff"]),
                "euro": r["is_euro"] == "1",
                "comp": r["competition_name"],
                "lh": float(r["lambda_home"]), "la": float(r["lambda_away"]),
                "hs": int(r["home_score"]), "as": int(r["away_score"]),
            })
    return rows


def nb_pmf(mu: np.ndarray, r: float) -> np.ndarray:
    """Negative-binomial pmf over 0..MAX_GOALS for each mu (rows)."""
    k = G[None, :]
    mu = mu[:, None]
    logp = gammaln(k + r) - gammaln(r) - gammaln(k + 1) + r * np.log(r / (r + mu)) + k * np.log(mu / (r + mu))
    return np.exp(logp)


def score_matrix(lh, la, rho=0.0, r=None):
    """Joint score probabilities, shape (n, 11, 11)."""
    if r is None:
        ph = poisson.pmf(G[None, :], lh[:, None])
        pa = poisson.pmf(G[None, :], la[:, None])
    else:
        ph = nb_pmf(lh, r)
        pa = nb_pmf(la, r)
    m = ph[:, :, None] * pa[:, None, :]
    if rho:
        tau = np.ones_like(m)
        tau[:, 0, 0] = 1 - lh * la * rho
        tau[:, 0, 1] = 1 + lh * rho
        tau[:, 1, 0] = 1 + la * rho
        tau[:, 1, 1] = 1 - rho
        m = m * np.clip(tau, 1e-6, None)
    m /= m.sum(axis=(1, 2), keepdims=True)
    return m


def markets(m):
    home = np.tril(m, -1).sum(axis=(1, 2))
    draw = np.trace(m, axis1=1, axis2=2)
    away = np.triu(m, 1).sum(axis=(1, 2))
    tot = G[:, None] + G[None, :]
    over25 = (m * (tot > 2.5)).sum(axis=(1, 2))
    over35 = (m * (tot > 3.5)).sum(axis=(1, 2))
    btts = m[:, 1:, 1:].sum(axis=(1, 2))
    return np.stack([home, draw, away], 1), over25, over35, btts


CURRENT_ENSEMBLE = [  # live pipeline before training: (weight, rho, nb dispersion)
    (0.3125, 0.0, None),    # Poisson
    (0.375, -0.13, None),   # Dixon-Coles, fixed rho
    (0.3125, 0.0, 20.0),    # Negative binomial, fixed dispersion
]


def mixture_matrix(lh, la, components):
    return sum(w * score_matrix(lh, la, rho, r) for w, rho, r in components)


def evaluate(rows, lh, la, rho=0.0, r=None, matrix=None):
    hs = np.array([x["hs"] for x in rows])
    as_ = np.array([x["as"] for x in rows])
    m = matrix if matrix is not None else score_matrix(lh, la, rho, r)
    p1x2, o25, o35, btts = markets(m)
    k = np.where(hs > as_, 0, np.where(hs == as_, 1, 2))
    eps = 1e-12
    out = {}
    out["1x2_logloss"] = float(-np.mean(np.log(np.clip(p1x2[np.arange(len(k)), k], eps, 1))))
    onehot = np.eye(3)[k]
    out["1x2_brier"] = float(np.mean(((p1x2 - onehot) ** 2).sum(1)))
    for name, p, y in (("over25", o25, (hs + as_) > 2.5), ("over35", o35, (hs + as_) > 3.5), ("btts", btts, (hs > 0) & (as_ > 0))):
        out[f"{name}_logloss"] = float(-np.mean(np.where(y, np.log(np.clip(p, eps, 1)), np.log(np.clip(1 - p, eps, 1)))))
        out[f"{name}_brier"] = float(np.mean((p - y) ** 2))
    cs = np.clip(hs, 0, MAX_GOALS), np.clip(as_, 0, MAX_GOALS)
    out["score_logloss"] = float(-np.mean(np.log(np.clip(m[np.arange(len(k)), cs[0], cs[1]], eps, 1))))
    out["mean_pred_total"] = float((lh + la).mean())
    out["mean_actual_total"] = float((hs + as_).mean())
    out["pred_draw_rate"] = float(p1x2[:, 1].mean())
    out["actual_draw_rate"] = float((k == 1).mean())
    out["pred_over25_rate"] = float(o25.mean())
    out["actual_over25_rate"] = float(((hs + as_) > 2.5).mean())
    out["pred_btts_rate"] = float(btts.mean())
    out["actual_btts_rate"] = float(((hs > 0) & (as_ > 0)).mean())
    return out


def calibration_table(rows, lh, la, rho, r, market="over25", bins=10):
    hs = np.array([x["hs"] for x in rows])
    as_ = np.array([x["as"] for x in rows])
    m = score_matrix(lh, la, rho, r)
    p1x2, o25, o35, btts = markets(m)
    if market == "over25":
        p, y = o25, (hs + as_) > 2.5
    elif market == "btts":
        p, y = btts, (hs > 0) & (as_ > 0)
    elif market == "draw":
        p, y = p1x2[:, 1], hs == as_
    else:
        p, y = p1x2[:, 0], hs > as_
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    table = []
    for i in range(bins):
        sel = (p >= edges[i]) & (p <= edges[i + 1]) if i == bins - 1 else (p >= edges[i]) & (p < edges[i + 1])
        if sel.sum():
            table.append({"pred": round(float(p[sel].mean()), 3), "actual": round(float(y[sel].mean()), 3), "n": int(sel.sum())})
    return table


def transform(lh, la, p):
    """Shrink total goals toward the training mean and scale supremacy, in log space.

    s = (ln lh + ln la)/2, d = (ln lh - ln la)/2
    s' = m + a (s - m) + b,  d' = c d;  lh' = e^(s'+d'), la' = e^(s'-d')
    Identity at a=1, b=0, c=1. Old-style k_home/k_away scales are applied first.
    """
    lh = lh * p.get("k_home", 1.0)
    la = la * p.get("k_away", 1.0)
    if "a" not in p:
        return lh, la
    s_ = (np.log(lh) + np.log(la)) / 2
    d = (np.log(lh) - np.log(la)) / 2
    s2 = p["m"] + p["a"] * (s_ - p["m"]) + p["b"]
    d2 = p["c"] * d
    return np.exp(s2 + d2), np.exp(s2 - d2)


def fit_shrink(rows):
    """ML fit of total shrinkage a, level b, supremacy scale c, rho and NB dispersion."""
    lh = np.array([x["lh"] for x in rows])
    la = np.array([x["la"] for x in rows])
    hs = np.clip(np.array([x["hs"] for x in rows]), 0, MAX_GOALS)
    as_ = np.clip(np.array([x["as"] for x in rows]), 0, MAX_GOALS)
    idx = np.arange(len(rows))
    m = float(np.mean((np.log(lh) + np.log(la)) / 2))

    def nll(theta):
        p = {"m": m, "a": theta[0], "b": theta[1], "c": theta[2]}
        lh2, la2 = transform(lh, la, p)
        mat = score_matrix(lh2, la2, theta[3], math.exp(theta[4]))
        return -np.sum(np.log(np.clip(mat[idx, hs, as_], 1e-12, 1)))

    theta0 = np.array([1.0, 0.0, 1.0, -0.03, math.log(50.0)])
    bounds = [(0.2, 1.5), (-0.3, 0.3), (0.5, 1.5), (-0.3, 0.3), (math.log(1.0), math.log(1000.0))]
    res = minimize(nll, theta0, method="L-BFGS-B", bounds=bounds)
    a, b, c, rho, lr = res.x
    return {"m": m, "a": float(a), "b": float(b), "c": float(c), "rho": float(rho),
            "nb_dispersion": float(math.exp(lr)), "train_nll_per_match": float(res.fun / len(rows))}


def fit(rows, family: str):
    """ML fit on goals for the chosen family; returns params dict."""
    lh = np.array([x["lh"] for x in rows])
    la = np.array([x["la"] for x in rows])
    hs = np.clip(np.array([x["hs"] for x in rows]), 0, MAX_GOALS)
    as_ = np.clip(np.array([x["as"] for x in rows]), 0, MAX_GOALS)
    idx = np.arange(len(rows))

    def nll(theta):
        kh, ka = math.exp(theta[0]), math.exp(theta[1])
        rho = theta[2] if family in ("dc", "nb_dc") else 0.0
        r = math.exp(theta[3]) if family in ("nb", "nb_dc") else None
        m = score_matrix(lh * kh, la * ka, rho, r)
        return -np.sum(np.log(np.clip(m[idx, hs, as_], 1e-12, 1)))

    theta0 = np.array([0.0, 0.0, -0.05, math.log(20.0)])
    bounds = [(-0.5, 0.5), (-0.5, 0.5), (-0.3, 0.3), (math.log(1.0), math.log(1000.0))]
    res = minimize(nll, theta0, method="L-BFGS-B", bounds=bounds)
    kh, ka = math.exp(res.x[0]), math.exp(res.x[1])
    return {
        "k_home": kh, "k_away": ka,
        "rho": float(res.x[2]) if family in ("dc", "nb_dc") else 0.0,
        "nb_dispersion": float(math.exp(res.x[3])) if family in ("nb", "nb_dc") else None,
        "train_nll_per_match": float(res.fun / len(rows)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/training/walkforward_lambdas.csv")
    ap.add_argument("--split", default="2026-07-01")
    ap.add_argument("--out", default="config/goal_model.json")
    args = ap.parse_args()

    rows = load(Path(args.data))
    split = datetime.fromisoformat(args.split)
    train = [x for x in rows if x["at"] < split]
    test = [x for x in rows if x["at"] >= split]
    print(f"rows={len(rows)} train={len(train)} test={len(test)} (split {args.split})")

    def arrays(rs, p):
        return transform(np.array([x["lh"] for x in rs]), np.array([x["la"] for x in rs]), p)

    candidates = {"poisson_raw": {"k_home": 1.0, "k_away": 1.0, "rho": 0.0, "nb_dispersion": None}}
    for fam in ("poisson", "dc", "nb", "nb_dc"):
        candidates[fam] = fit(train, fam)
        print(f"fitted {fam}: {json.dumps({k: round(v, 4) if isinstance(v, float) else v for k, v in candidates[fam].items()})}")
    candidates["shrink_nb_dc"] = fit_shrink(train)
    print(f"fitted shrink_nb_dc: {json.dumps({k: round(v, 4) for k, v in candidates['shrink_nb_dc'].items()})}")

    report = {}
    for subset_name, subset in (("test", test), ("test_euro", [x for x in test if x["euro"]])):
        if not subset:
            continue
        lh, la = arrays(subset, candidates["poisson_raw"])
        report.setdefault("ensemble_now", {})[subset_name] = evaluate(subset, lh, la, matrix=mixture_matrix(lh, la, CURRENT_ENSEMBLE))
    for name, p in candidates.items():
        for subset_name, subset in (("test", test), ("test_euro", [x for x in test if x["euro"]])):
            if not subset:
                continue
            lh, la = arrays(subset, p)
            report.setdefault(name, {})[subset_name] = evaluate(subset, lh, la, p["rho"], p["nb_dispersion"])
    keys = ["1x2_logloss", "over25_logloss", "over35_logloss", "btts_logloss", "score_logloss",
            "mean_pred_total", "mean_actual_total", "pred_draw_rate", "actual_draw_rate",
            "pred_over25_rate", "actual_over25_rate", "pred_btts_rate", "actual_btts_rate"]
    for subset_name in ("test", "test_euro"):
        print(f"\n== held-out {subset_name} ==")
        print("model".ljust(12) + "".join(k[:14].rjust(15) for k in keys))
        for name in ["ensemble_now", *candidates]:
            ev = report[name].get(subset_name)
            if ev:
                print(name.ljust(12) + "".join(f"{ev[k]:15.4f}" for k in keys))

    best = min(candidates, key=lambda n: report[n]["test"]["score_logloss"])
    p = candidates[best]
    lh, la = arrays(test, p)
    calib = {mk: calibration_table(test, lh, la, p["rho"], p["nb_dispersion"], mk) for mk in ("over25", "btts", "draw", "home")}
    lh0, la0 = arrays(test, candidates["poisson_raw"])
    calib_raw = {mk: calibration_table(test, lh0, la0, 0.0, None, mk) for mk in ("over25", "btts", "draw")}
    print(f"\nbest by held-out score log loss: {best}")
    for mk, t in calib.items():
        print(f"calibration ({best}) {mk}: {t}")
    for mk, t in calib_raw.items():
        print(f"calibration (raw) {mk}: {t}")

    out = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "data": args.data,
        "split": args.split,
        "n_train": len(train),
        "n_test": len(test),
        "chosen": best,
        "params": p,
        "held_out_metrics": report,
        "calibration_held_out": calib,
    }
    Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
