"""Full-data match model (train:lean, 2026-10-14): one penalised Poisson-type model, one report.

Input: data/training/match_features_full.csv.gz (build_match_features.py, 2022-08 .. 2026-10, split
column filled: train 2022-08-01..2025-06-30, validation 2025-07-01..2026-01-31, test
2026-02-01..2026-10-12). Rows with a rating lambda and a result.

Model (per match, both sides):
    s = (ln L_h + ln L_a) / 2 - m_s            (total level, centred on the fitting rows)
    d = (ln L_h - ln L_a) / 2                  (rating difference)
    ln mu_h = ln L_h + c_h + a_s s + a_d d  + E_h + sum_k beta_k z_k(home eq.)
    ln mu_a = ln L_a + c_a + a_s s - a_d d  + E_a + sum_k beta_k z_k(away eq.)
  L = walk-forward rating lambda through the goal layer (train-only layer while selecting, train+val
  layer for the deployed fit), E = European block (UEFA matches only; penalised deviations from the
  league terms): e_h, e_a (intercepts), e_s (total scale), e_d (rating-difference scale), e_v (value).
  z = standardised features (mean / sd of the fitting rows, clipped to +-4, missing -> 0 plus a
  missing indicator per block). Groups: value (starters' value log ratio), xi (XI vs usual XI,
  RAPM offence of own / defence of opponent), absent (rating loss of players on FotMob's
  unavailable list, weighted by minutes share - list membership only, expected_return is never
  used), form (last-5 xG for / against and points). The exact score is modelled as NB x
  Dixon-Coles (train_goal_model.score_matrix); fitted by penalised maximum likelihood (analytic
  gradient), rho / NB dispersion refitted for fixed means.

Stages (test rows are never loaded in `select`):
  select  fit on train, score validation: l2, l2_euro, recalibration switch and feature groups chosen
          on validation exact-score log loss; writes the frozen configuration.
  final   read the frozen configuration; fit on train + validation (train+val goal layer), score the
          test split once, paired bootstrap (2,000, seed 7) vs the production baseline, closing-odds
          comparison, deploy criteria, candidate JSON, prediction files; then a refit on all rows
          (train + validation + test) for deployment (not evaluated).

Usage (from backend/):
  venv/Scripts/python.exe scripts/training/train_match_model_full.py --stage select
  venv/Scripts/python.exe scripts/training/train_match_model_full.py --stage final
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.optimize import minimize

TRAINING_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TRAINING_DIR.parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TRAINING_DIR))
import train_goal_model as T  # noqa: E402
import train_match_model as M  # noqa: E402  (score_loglik, fit_score_params, load_odds, per_match)
import baseline_predictions as BP  # noqa: E402  (production baseline, losses, calibration)

DATA = BACKEND_DIR / "data" / "training"
SIDES = ("home", "away")
SPLITS = ("train", "validation", "test")
BOOT_N = 2000
BOOT_SEED = 7
CLIP = 4.0
MAX_GOALS = T.MAX_GOALS
GROUPS = ["value", "xi", "absent", "form"]
SIDE_COLS = ["xi_d_off", "xi_d_def", "unavail_off_w", "unavail_def_w", "xg_for_l5", "xg_against_l5", "ppg_l5"]
L2_GRID = [300.0, 1000.0, 3000.0, 10000.0, 30000.0]
L2E_GRID = [30.0, 300.0, 3000.0, 30000.0]

# (name, group, kind, column, definition)
#   att: the scoring side's own column; def: the conceding side's column;
#   signed: home-minus-away match column, + in the home equation and - in the away one.
TERMS = [
    ("value", "value", "signed", "value_log_ratio",
     "ln(home starters' market value / away starters' market value); + for the home equation, - for the away one"),
    ("xi_off_att", "xi", "att", "xi_d_off",
     "scoring side's XI offence rating (sum of its 11 starters, xG/90) minus its usual XI's (last <= 10 line-ups, "
     "same ratings cutoff)"),
    ("xi_def_def", "xi", "def", "xi_d_def",
     "conceding side's XI defence rating minus its usual XI's (+ = better defence than usual)"),
    ("unav_off_att", "absent", "att", "unavail_off_w",
     "sum over the scoring side's listed-unavailable rated players of share x (offence - replacement level), "
     "share = minutes share of the team's last 10 matches"),
    ("unav_def_def", "absent", "def", "unavail_def_w",
     "same for the conceding side's listed-unavailable players' defence rating"),
    ("xgf_att", "form", "att", "xg_for_l5", "scoring side's mean xG for over its last 5 matches with xG (>= 3)"),
    ("xga_def", "form", "def", "xg_against_l5", "conceding side's mean xG against over its last 5 matches with xG"),
    ("ppg_att", "form", "att", "ppg_l5", "scoring side's points per game over its last 5 competitive results (>= 3)"),
    ("ppg_def", "form", "def", "ppg_l5", "conceding side's points per game over its last 5 competitive results"),
]
MISSING = [  # (name, group, kind, column): indicator = 1 when the raw value is unknown
    ("value_miss", "value", "both", "value_log_ratio"),
    ("xi_miss_att", "xi", "att", "xi_d_off"),
    ("xi_miss_def", "xi", "def", "xi_d_def"),
    ("unav_miss_att", "absent", "att", "unavail_off_w"),
    ("unav_miss_def", "absent", "def", "unavail_def_w"),
    ("xgl5_miss_att", "form", "att", "xg_for_l5"),
    ("xgl5_miss_def", "form", "def", "xg_against_l5"),
]


# ============================================================================ data
def fnum(s) -> Optional[float]:
    if s is None or s == "":
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return None if math.isnan(v) else v


SKIPPED: dict = {}      # rows of the features file that are not used, by reason; filled by load_rows


def load_rows(path: Path, splits) -> list[dict]:
    rows = []
    SKIPPED.clear()
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["split"] not in splits:
                if "test" in splits or r["split"] != "test":      # the select stage does not count test rows
                    k = f"{r['split'] or 'none'}: outside train / validation / test"
                    SKIPPED[k] = SKIPPED.get(k, 0) + 1
                continue
            if r["lambda_home_raw"] == "" or r["lambda_away_raw"] == "" or r["y_home_goals"] == "" \
                    or r["y_away_goals"] == "":
                k = f"{r['split']}: no rating lambda or no result"
                SKIPPED[k] = SKIPPED.get(k, 0) + 1
                continue
            x = {"match_id": r["match_id"], "kickoff": r["kickoff"], "split": r["split"],
                 "competition_provider_id": r["competition_provider_id"], "comp_type": r["comp_type"],
                 "home_team_id": r["home_team_id"], "away_team_id": r["away_team_id"],
                 "euro": 1 if r["comp_is_euro"] == "1" else 0,
                 "lambda_home_raw": float(r["lambda_home_raw"]), "lambda_away_raw": float(r["lambda_away_raw"]),
                 "hs": int(float(r["y_home_goals"])), "as": int(float(r["y_away_goals"])),
                 "value_log_ratio": fnum(r["value_log_ratio"]), "lineup_form": fnum(r["lineup_form"])}
            for s in SIDES:
                for c in SIDE_COLS:
                    x[f"{s}_{c}"] = fnum(r[f"{s}_{c}"])
            rows.append(x)
    rows.sort(key=lambda x: (x["kickoff"], x["match_id"]))
    return rows


class Data:
    """Column arrays of a row set (NaN = unknown)."""

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.n = len(rows)
        self.hs = np.array([r["hs"] for r in rows])
        self.as_ = np.array([r["as"] for r in rows])
        self.euro = np.array([r["euro"] for r in rows], dtype=float)
        self.lh_raw = np.array([r["lambda_home_raw"] for r in rows])
        self.la_raw = np.array([r["lambda_away_raw"] for r in rows])
        names = ["value_log_ratio"] + [f"{s}_{c}" for s in SIDES for c in SIDE_COLS]
        self.cols = {k: np.array([np.nan if r[k] is None else r[k] for r in rows]) for k in names}

    def layered(self, layer: dict) -> tuple[np.ndarray, np.ndarray]:
        return BP.apply_layer(self.lh_raw, self.la_raw, layer)


def raw_term(D: Data, eq: str, kind: str, col: str) -> np.ndarray:
    other = "away" if eq == "home" else "home"
    if kind == "att":
        return D.cols[f"{eq}_{col}"]
    if kind == "def":
        return D.cols[f"{other}_{col}"]
    v = D.cols[col]
    return v if (kind == "both" or eq == "home") else -v


# ============================================================================ design + fit
class Design:
    """Column layout, standardisation statistics and design matrices of one configuration."""

    def __init__(self, groups: list[str], l2: float, l2_euro: Optional[float], recal: bool):
        self.groups, self.l2, self.l2_euro, self.recal = list(groups), float(l2), l2_euro, bool(recal)
        self.terms = [t for t in TERMS if t[1] in groups]
        self.missing = [m for m in MISSING if m[1] in groups]
        self.names = ["c_home", "c_away", "alpha_total", "alpha_diff"]
        pen = [0.0] * 4
        if l2_euro is not None:
            self.names += ["e_home", "e_away", "e_total", "e_diff"] + (["e_value"] if "value" in groups else [])
            pen += [l2_euro] * (len(self.names) - 4)
        self.n_base = len(self.names)
        self.names += [t[0] for t in self.terms] + [m[0] for m in self.missing]
        pen += [self.l2] * (len(self.terms) + len(self.missing))
        self.pen = np.array(pen)
        self.stats: dict = {}
        self.m_s = 0.0

    def fit_stats(self, D: Data, lh: np.ndarray, la: np.ndarray) -> "Design":
        self.m_s = float(np.mean((np.log(lh) + np.log(la)) / 2))
        for name, _g, kind, col, _def in self.terms:
            v = np.concatenate([raw_term(D, "home", kind, col), raw_term(D, "away", kind, col)])
            v = v[~np.isnan(v)]
            if len(v) < 2:
                self.stats[name] = (0.0, 1.0)
                continue
            mu = 0.0 if kind == "signed" else float(v.mean())
            sd = float(np.sqrt(np.mean((v - mu) ** 2)))
            self.stats[name] = (mu, sd if sd > 1e-9 else 1.0)
        return self

    def z(self, D: Data, eq: str, term) -> np.ndarray:
        name, _g, kind, col, _def = term
        mu, sd = self.stats[name]
        v = (raw_term(D, eq, kind, col) - mu) / sd
        return np.where(np.isnan(v), 0.0, np.clip(v, -CLIP, CLIP))

    def matrices(self, D: Data, lh: np.ndarray, la: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        s = (np.log(lh) + np.log(la)) / 2 - self.m_s
        d = (np.log(lh) - np.log(la)) / 2
        out = []
        for eq, sign in (("home", 1.0), ("away", -1.0)):
            X = np.zeros((D.n, len(self.names)))
            X[:, 0 if eq == "home" else 1] = 1.0
            X[:, 2] = s
            X[:, 3] = sign * d
            if self.l2_euro is not None:
                X[:, 4 if eq == "home" else 5] = D.euro
                X[:, 6] = D.euro * s
                X[:, 7] = D.euro * sign * d
                if "value" in self.groups:
                    X[:, 8] = D.euro * self.z(D, eq, TERMS[0])
            for j, term in enumerate(self.terms):
                X[:, self.n_base + j] = self.z(D, eq, term)
            off = self.n_base + len(self.terms)
            for j, (_n, _g, kind, col) in enumerate(self.missing):
                X[:, off + j] = np.isnan(raw_term(D, eq, kind, col)).astype(float)
            out.append(X)
        return out[0], out[1]

    def bounds(self) -> list:
        b = [(None, None)] * len(self.names)
        if not self.recal:
            b[0] = b[1] = b[2] = b[3] = (0.0, 0.0)
        return b


def fit_theta(llh, lla, Xh, Xa, hs, as_, pen, bounds, rho, r, theta0):
    def obj(th):
        ll, gh, ga = M.score_loglik(llh + Xh @ th, lla + Xa @ th, hs, as_, rho, r, grad=True)
        f = -ll.sum() + 0.5 * np.sum(pen * th * th)
        g = -(Xh.T @ gh + Xa.T @ ga) + pen * th
        return f, g

    res = minimize(obj, theta0, jac=True, method="L-BFGS-B", bounds=bounds,
                   options={"maxiter": 1500, "maxcor": 30, "ftol": 1e-11, "gtol": 1e-6})
    return res.x, bool(res.success), float(res.fun)


class Model:
    def __init__(self, design: Design):
        self.design = design
        self.theta = None
        self.rho = None
        self.r = None
        self.converged = None

    def fit(self, D: Data, lh, la, rho0: float, r0: float) -> "Model":
        dz = self.design
        dz.fit_stats(D, lh, la)
        Xh, Xa = dz.matrices(D, lh, la)
        llh, lla = np.log(lh), np.log(la)
        th = np.zeros(len(dz.names))
        rho, r = rho0, r0
        th, ok, _f = fit_theta(llh, lla, Xh, Xa, D.hs, D.as_, dz.pen, dz.bounds(), rho, r, th)
        if dz.recal:        # refit the score model for the fitted means, then the coefficients once more
            rho, r = M.fit_score_params(lh * np.exp(Xh @ th), la * np.exp(Xa @ th), D.hs, D.as_, rho, r)
            th, ok, _f = fit_theta(llh, lla, Xh, Xa, D.hs, D.as_, dz.pen, dz.bounds(), rho, r, th)
        self.theta, self.rho, self.r, self.converged = th, float(rho), float(r), ok
        return self

    def predict(self, D: Data, lh, la):
        Xh, Xa = self.design.matrices(D, lh, la)
        return lh * np.exp(Xh @ self.theta), la * np.exp(Xa @ self.theta)


# ============================================================================ evaluation helpers
def P_from_mu(rows: list[dict], mh: np.ndarray, ma: np.ndarray, rho: float, r: float) -> dict:
    """Probability arrays with the schema of baseline_predictions.predict (without top scores)."""
    n = len(mh)
    p1x2 = np.empty((n, 3))
    o15, o25, o35, btts, p00, et, score_p = (np.empty(n) for _ in range(7))
    tot = BP.G[:, None] + BP.G[None, :]
    hs = np.clip([x["hs"] for x in rows], 0, MAX_GOALS)
    as_ = np.clip([x["as"] for x in rows], 0, MAX_GOALS)
    for i in range(0, n, 20000):
        j = min(n, i + 20000)
        m = T.score_matrix(np.asarray(mh[i:j], float), np.asarray(ma[i:j], float), rho, r)
        p1x2[i:j, 0] = np.tril(m, -1).sum(axis=(1, 2))
        p1x2[i:j, 1] = np.trace(m, axis1=1, axis2=2)
        p1x2[i:j, 2] = np.triu(m, 1).sum(axis=(1, 2))
        o15[i:j] = (m * (tot > 1.5)).sum(axis=(1, 2))
        o25[i:j] = (m * (tot > 2.5)).sum(axis=(1, 2))
        o35[i:j] = (m * (tot > 3.5)).sum(axis=(1, 2))
        btts[i:j] = m[:, 1:, 1:].sum(axis=(1, 2))
        p00[i:j] = m[:, 0, 0]
        et[i:j] = (m * tot).sum(axis=(1, 2))
        score_p[i:j] = m[np.arange(j - i), hs[i:j], as_[i:j]]
    return {"mh": np.asarray(mh, float), "ma": np.asarray(ma, float), "p1x2": p1x2, "o15": o15, "o25": o25,
            "o35": o35, "btts": btts, "p00": p00, "et": et, "score_p": score_p}


def baseline_P(rows: list[dict], layer: dict, coef: dict) -> dict:
    return BP.predict(rows, layer, coef)


def losses(rows, P) -> dict:
    return BP.per_match_losses(rows, P, np.arange(len(rows)))


KEYS = ["1x2_logloss", "1x2_brier", "over25_logloss", "btts_logloss", "score_logloss"]


def quick(rows, mh, ma, rho, r) -> dict:
    pm = M.per_match(rows, mh, ma, rho, r)
    eu = np.array([x["euro"] == 1 for x in rows])
    return {"score": float(pm["score_logloss"].mean()), "1x2": float(pm["1x2_logloss"].mean()),
            "ou25": float(pm["over25_logloss"].mean()), "btts": float(pm["btts_logloss"].mean()),
            "1x2_euro": float(pm["1x2_logloss"][eu].mean()) if eu.any() else None,
            "1x2_league": float(pm["1x2_logloss"][~eu].mean()), "score_euro": float(pm["score_logloss"][eu].mean())
            if eu.any() else None}


def paired(Lb: dict, Lm: dict, sel: np.ndarray, seed: int = BOOT_SEED, n_boot: int = BOOT_N) -> dict:
    """Paired comparison model (Lm) vs reference (Lb) on the rows ``sel``: means and bootstrap CI of the difference."""
    n = int(sel.sum())
    out = {"n": n}
    if n == 0:
        return out
    idx = np.random.default_rng(seed).integers(0, n, size=(n_boot, n)) if n >= 20 else None
    for k in KEYS:
        b, m = Lb[k][sel], Lm[k][sel]
        e = {"reference": round(float(b.mean()), 5), "model": round(float(m.mean()), 5),
             "diff": round(float((m - b).mean()), 5)}
        if idx is not None:
            bs = (m - b)[idx].mean(1)
            e["ci90"] = [round(float(np.quantile(bs, 0.05)), 5), round(float(np.quantile(bs, 0.95)), 5)]
        out[k] = e
    return out


def hit_rate_block(L: dict, sel: np.ndarray, seed: int = BOOT_SEED) -> dict:
    """Favourite (max 1X2 probability) hit rate for matches with pf >= thr, with a bootstrap CI."""
    p, k = L["_p"], L["_k"]
    pf = p.max(1)
    hit = (p.argmax(1) == k)
    out = {}
    for thr in (0.6, 0.7, 0.8, 0.85, 0.9):
        m = sel & (pf >= thr)
        n = int(m.sum())
        if n == 0:
            out[f"ge_{thr:.2f}"] = {"n": 0}
            continue
        e = {"n": n, "hit_rate": round(float(hit[m].mean()), 4), "mean_pred": round(float(pf[m].mean()), 4)}
        if n >= 20:
            idx = np.random.default_rng(seed).integers(0, n, size=(BOOT_N, n))
            bs = hit[m][idx].mean(1)
            e["hit_ci90"] = [round(float(np.quantile(bs, 0.05)), 4), round(float(np.quantile(bs, 0.95)), 4)]
        out[f"ge_{thr:.2f}"] = e
    return out


def segment_masks(rows, Lb: dict, Lm: dict) -> dict:
    eu = np.array([x["euro"] == 1 for x in rows])
    return {"all": np.ones(len(rows), bool), "league": ~eu, "european": eu,
            "model_fav_ge_0.70": Lm["_p"].max(1) >= 0.70, "baseline_fav_ge_0.70": Lb["_p"].max(1) >= 0.70}


def fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (float, np.floating)):
        return "" if math.isnan(v) else f"{float(v):.6f}".rstrip("0").rstrip(".") if v != 0 else "0"
    return str(v)


# ============================================================================ select stage
def select_stage(args) -> int:
    t0 = time.time()
    rows_all = load_rows(args.features, ("train", "validation"))     # test rows are not loaded
    tr = [r for r in rows_all if r["split"] == "train"]
    va = [r for r in rows_all if r["split"] == "validation"]
    Dtr, Dva = Data(tr), Data(va)
    layer = BP.load_layer(args.goal_layer_train)
    coef = BP.production_coefficients()
    lh_tr, la_tr = Dtr.layered(layer)
    lh_va, la_va = Dva.layered(layer)
    print(f"train {len(tr)} validation {len(va)} (european: {int(Dtr.euro.sum())} / {int(Dva.euro.sum())}) "
          f"[{time.time() - t0:.0f}s]", flush=True)

    Pb = baseline_P(va, layer, coef)
    base = quick(va, Pb["mh"], Pb["ma"], layer["rho"], layer["nb_dispersion"])
    print("baseline validation:", {k: (round(v, 5) if v is not None else None) for k, v in base.items()}, flush=True)

    trace, cache = [], {}

    def trial(groups, l2, l2e, recal, label) -> float:
        key = (tuple(groups), l2, l2e, recal)
        if key in cache:
            return cache[key]["score"]
        t1 = time.time()
        m = Model(Design(groups, l2, l2e, recal)).fit(Dtr, lh_tr, la_tr, layer["rho"], layer["nb_dispersion"])
        mh, ma = m.predict(Dva, lh_va, la_va)
        q = quick(va, mh, ma, m.rho, m.r)
        rec = {"label": label, "groups": list(groups), "l2": l2, "l2_euro": l2e, "recal": recal,
               **{k: (round(v, 5) if v is not None else None) for k, v in q.items()},
               "converged": m.converged, "seconds": round(time.time() - t1, 1)}
        cache[key] = rec
        trace.append(rec)
        print(f"  {label:34} groups={','.join(groups) or '-':26} l2={l2:<7g} l2e={l2e!s:<7} recal={recal!s:5} "
              f"score={q['score']:.5f} 1x2={q['1x2']:.5f} euro1x2={q['1x2_euro']:.5f} ou={q['ou25']:.5f} "
              f"[{rec['seconds']}s]", flush=True)
        return q["score"]

    # S0 references (reported, not selected)
    trial([], 1.0, None, True, "ref: recalibration only")
    trial([], 1.0, 1000.0, True, "ref: recalibration + euro block")
    # S1: l2 (euro block tied to the same strength) and recalibration switch, all groups
    best = None
    for recal in (True, False):
        for l2 in L2_GRID:
            s = trial(GROUPS, l2, l2, recal, "S1 l2 x recal (euro tied)")
            if best is None or s < best[0] - 1e-7:
                best = (s, l2, recal)
    _s, l2, recal = best
    # S2: euro block strength (None = no euro terms)
    best_e = (cache[(tuple(GROUPS), l2, l2, recal)]["score"], l2)
    for l2e in [None] + L2E_GRID:
        s = trial(GROUPS, l2, l2e, recal, "S2 euro block")
        if s < best_e[0] - 1e-7:
            best_e = (s, l2e)
    l2e = best_e[1]
    # S3: backward elimination of feature groups
    groups = list(GROUPS)
    cur = trial(groups, l2, l2e, recal, "S3 start")
    while groups:
        trials = [(trial([x for x in groups if x != g], l2, l2e, recal, f"S3 without {g}"), g) for g in groups]
        s, g = min(trials)
        if s < cur - 1e-6:
            groups.remove(g)
            cur = s
            print(f"  -> removed {g}: validation score {cur:.5f}", flush=True)
        else:
            break
    # S4: re-tune l2 and the euro block for the final groups
    best = (cur, l2)
    for v in L2_GRID:
        s = trial(groups, v, l2e if l2e is not None else None, recal, "S4 l2")
        if s < best[0] - 1e-7:
            best = (s, v)
    l2 = best[1]
    best = (cache[(tuple(groups), l2, l2e, recal)]["score"], l2e)
    for v in [None] + L2E_GRID:
        s = trial(groups, l2, v, recal, "S4 euro block")
        if s < best[0] - 1e-7:
            best = (s, v)
    l2e = best[1]
    final_score = cache[(tuple(groups), l2, l2e, recal)]["score"]

    frozen = {"frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "selected_on": "validation 2025-07-01..2026-01-31 exact-score log loss (model fitted on train "
                             "2022-08-01..2025-06-30, train-only goal layer)",
              "groups": groups, "l2": l2, "l2_euro": l2e, "recal": recal, "clip": CLIP,
              "validation_score_logloss": final_score,
              "baseline_validation": {k: (round(v, 5) if v is not None else None) for k, v in base.items()},
              "features_file": str(args.features), "goal_layer_train_only": str(args.goal_layer_train),
              "goal_layer_trainval": str(args.goal_layer_trainval), "n_train": len(tr), "n_validation": len(va),
              "trace": trace, "seconds": round(time.time() - t0, 1)}
    args.frozen.write_text(json.dumps(frozen, indent=1), encoding="utf-8")
    print(f"frozen: groups={groups} l2={l2} l2_euro={l2e} recal={recal} validation score {final_score:.5f} "
          f"-> {args.frozen} ({frozen['seconds']} s)", flush=True)
    return 0


# ============================================================================ final stage
def model_doc(m: Model, label: str, layer_path: str, layer: dict, fit_rows: dict) -> dict:
    d = m.design
    th = m.theta
    terms = []
    for j, (name, group, kind, col, definition) in enumerate(d.terms):
        mu, sd = d.stats[name]
        c = float(th[d.n_base + j])
        terms.append({"name": name, "group": group, "kind": kind, "column": col, "definition": definition,
                      "home_equation_source": _source("home", kind, col), "away_equation_source": _source("away", kind, col),
                      "mean": round(mu, 6), "sd": round(sd, 6), "clip_z": CLIP, "coef_per_sd": round(c, 6),
                      "coef_per_unit": round(c / sd, 6),
                      "missing_rule": "unknown raw value -> z = 0 (plus the missing indicator)"})
    off = d.n_base + len(d.terms)
    miss = [{"name": n, "group": g, "kind": k, "column": c,
             "definition": f"1 when {_source('home', k, c)} (home equation) / {_source('away', k, c)} (away equation) "
                           f"is unknown, else 0", "coef": round(float(th[off + j]), 6)}
            for j, (n, g, k, c) in enumerate(d.missing)]
    doc = {"label": label, "fit_rows": fit_rows, "groups": d.groups, "l2": d.l2, "l2_euro": d.l2_euro,
           "recalibration_terms": d.recal,
           "goal_layer": {"path": layer_path, "params": {k: layer[k] for k in ("m", "a", "b", "rho", "nb_dispersion")},
                          "apply": "s' = m + a (s - m) + b on the log total, supremacy unchanged; L = exp(s' +- d)"},
           "recalibration": {"c_home": round(float(th[0]), 6), "c_away": round(float(th[1]), 6),
                             "alpha_total": round(float(th[2]), 6), "alpha_diff": round(float(th[3]), 6),
                             "m_s": round(d.m_s, 6)},
           "terms": terms, "missing_indicators": miss,
           "score_model": {"family": "negative binomial marginals x Dixon-Coles tau, scores 0..10, renormalised",
                           "rho": round(m.rho, 6), "nb_dispersion": round(m.r, 4)},
           "converged": m.converged}
    if d.l2_euro is not None:
        doc["european"] = {"applies_to": "competition ids 42, 73, 10216 and qualifiers 10611, 10613, 10615 "
                                         "(comp_type european)",
                           "penalised_deviations_from_league_terms": {n: round(float(th[4 + j]), 6)
                                                                      for j, n in enumerate(d.names[4:d.n_base])}}
    return doc


def rel(path) -> str:
    """Path relative to backend/ with forward slashes (portable in the candidate JSON)."""
    try:
        return Path(path).resolve().relative_to(BACKEND_DIR).as_posix()
    except ValueError:
        return str(path)


def _source(eq: str, kind: str, col: str) -> str:
    other = "away" if eq == "home" else "home"
    if kind == "att":
        return f"{eq}_{col}"
    if kind == "def":
        return f"{other}_{col}"
    if kind == "signed":
        return col if eq == "home" else f"-{col}"
    return col


def write_predictions(path: Path, rows, Pb, Pm, fit_on: str) -> None:
    cols = ["match_id", "kickoff", "split", "competition_provider_id", "comp_type", "home_team_id", "away_team_id",
            "home_goals", "away_goals", "result"]
    for pre in ("base", "model"):
        cols += [f"{pre}_mu_home", f"{pre}_mu_away", f"{pre}_p_home", f"{pre}_p_draw", f"{pre}_p_away",
                 f"{pre}_p_over15", f"{pre}_p_over25", f"{pre}_p_over35", f"{pre}_p_btts"]
    cols += ["model_fit_on"]
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    with open(tmp, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            with io.TextIOWrapper(gz, encoding="utf-8", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(cols)
                for i, r in enumerate(rows):
                    res = "H" if r["hs"] > r["as"] else ("D" if r["hs"] == r["as"] else "A")
                    vals = [r["match_id"], r["kickoff"], r["split"], r["competition_provider_id"], r["comp_type"],
                            r["home_team_id"], r["away_team_id"], r["hs"], r["as"], res]
                    for P in (Pb, Pm):
                        vals += [P["mh"][i], P["ma"][i], P["p1x2"][i, 0], P["p1x2"][i, 1], P["p1x2"][i, 2],
                                 P["o15"][i], P["o25"][i], P["o35"][i], P["btts"][i]]
                    vals.append(fit_on)
                    w.writerow([fmt(v) for v in vals])
    os.replace(tmp, path)


def split_report(rows, Pb, Pm, with_cal: bool) -> dict:
    Lb, Lm = losses(rows, Pb), losses(rows, Pm)
    masks = segment_masks(rows, Lb, Lm)
    out = {"n": len(rows), "segments": {}}
    for name, sel in masks.items():
        out["segments"][name] = paired(Lb, Lm, sel)
    out["favourite_hit_rates"] = {"model": hit_rate_block(Lm, np.ones(len(rows), bool)),
                                  "baseline": hit_rate_block(Lb, np.ones(len(rows), bool)),
                                  "model_european": hit_rate_block(Lm, masks["european"]),
                                  "baseline_european": hit_rate_block(Lb, masks["european"])}
    if with_cal:
        idx = np.arange(len(rows))
        out["calibration"] = {"model": BP.calibration(Lm, Pm, idx), "baseline": BP.calibration(Lb, Pb, idx)}
        eu = masks["european"]
        if eu.any():
            out["calibration_european"] = {
                "model": BP.calibration({k: v[eu] for k, v in Lm.items()}, Pm, idx[eu]),
                "baseline": BP.calibration({k: v[eu] for k, v in Lb.items()}, Pb, idx[eu])}
    out["mean_total_goals"] = {"model": round(float((Pm["mh"] + Pm["ma"]).mean()), 4),
                               "baseline": round(float((Pb["mh"] + Pb["ma"]).mean()), 4),
                               "actual": round(float((Lm["_hs"] + Lm["_as"]).mean()), 4)}
    out["_L"] = (Lb, Lm)
    return out


def market_block(rows, Pb, Pm, Pb2, odds: dict) -> dict:
    sel = [i for i, r in enumerate(rows) if r["match_id"] in odds]
    if not sel:
        return {"n": 0}
    sel = np.array(sel)
    sub = [rows[i] for i in sel]
    hs = np.array([r["hs"] for r in sub])
    as_ = np.array([r["as"] for r in sub])
    k = np.where(hs > as_, 0, np.where(hs == as_, 1, 2))
    y = (hs + as_) > 2.5
    mk = np.array([odds[r["match_id"]]["mk1x2"] for r in sub])
    has_ou = np.array([odds[r["match_id"]]["mkover"] is not None for r in sub])
    mko = np.array([odds[r["match_id"]]["mkover"] if odds[r["match_id"]]["mkover"] is not None else 0.5 for r in sub])
    eu = np.array([r["euro"] == 1 for r in sub])
    eps = 1e-12
    ll = {"market": -np.log(np.clip(mk[np.arange(len(k)), k], eps, 1))}
    ou = {"market": -np.where(y, np.log(mko), np.log(1 - mko))}
    for name, P in (("model", Pm), ("baseline", Pb), ("baseline_trainval_layer", Pb2)):
        p = P["p1x2"][sel]
        ll[name] = -np.log(np.clip(p[np.arange(len(k)), k], eps, 1))
        o = np.clip(P["o25"][sel], eps, 1 - eps)
        ou[name] = -np.where(y, np.log(o), np.log(1 - o))

    def cmp(a, b, arr, mask) -> dict:
        d = (arr[a] - arr[b])[mask]
        n = len(d)
        if n == 0:
            return {"n": 0, "note": "no closing odds for this subset in the sources"}
        e = {"n": n, "mean_a": round(float(arr[a][mask].mean()), 5), "mean_b": round(float(arr[b][mask].mean()), 5),
             "diff_a_minus_b": round(float(d.mean()), 5)}
        if n >= 20:
            idx = np.random.default_rng(BOOT_SEED).integers(0, n, size=(BOOT_N, n))
            bs = d[idx].mean(1)
            e["ci90"] = [round(float(np.quantile(bs, 0.05)), 5), round(float(np.quantile(bs, 0.95)), 5)]
        return e

    out = {"n": len(sub), "n_ou25": int(has_ou.sum()), "n_european": int(eu.sum()),
           "note": "closing odds de-vigged (p_close_*), football_data_matches.csv via db_match_id and "
                   "football_data_history.csv via fotmob_match_id, test split only; diff = a - b, negative = a better"}
    allm = np.ones(len(sub), bool)
    for seg, m1, m2 in (("all", allm, has_ou), ("league", ~eu, has_ou & ~eu), ("european", eu, has_ou & eu)):
        blk = {}
        for a, b in (("model", "market"), ("baseline", "market"), ("model", "baseline")):
            blk[f"1x2_{a}_vs_{b}"] = cmp(a, b, ll, m1)
            blk[f"ou25_{a}_vs_{b}"] = cmp(a, b, ou, m2)
        out[seg] = blk
    return out


def final_stage(args) -> int:
    t0 = time.time()
    frozen = json.loads(args.frozen.read_text(encoding="utf-8"))
    groups, l2, l2e, recal = frozen["groups"], frozen["l2"], frozen["l2_euro"], frozen["recal"]
    rows_all = load_rows(args.features, SPLITS)
    by = {s: [r for r in rows_all if r["split"] == s] for s in SPLITS}
    layer_tr = BP.load_layer(args.goal_layer_train)
    layer_tv = BP.load_layer(args.goal_layer_trainval)
    coef = BP.production_coefficients()
    print(f"frozen: groups={groups} l2={l2} l2_euro={l2e} recal={recal}; rows "
          f"{ {s: len(v) for s, v in by.items()} } [{time.time() - t0:.0f}s]", flush=True)

    report = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "frozen": {
        k: frozen[k] for k in ("groups", "l2", "l2_euro", "recal", "clip", "frozen_at", "selected_on")},
        "rows": {s: len(v) for s, v in by.items()}, "rows_not_used": dict(SKIPPED),
        "european_rows": {s: int(sum(r["euro"] for r in v)) for s, v in by.items()},
        "bootstrap": {"resamples": BOOT_N, "seed": BOOT_SEED, "ci": "90 % percentile, paired (model - reference)"},
        "baseline": {"description": "production model: rating lambda + goal layer + squad value beta 0.048 (UEFA) / "
                                    "0.0279 + lineup form gamma 0.2157 (missing term = no shift)",
                     "goal_layer_train_only": layer_tr, "coefficients": coef}}

    # ---------------------------------------------------------------- validation (model fitted on train only)
    Dtr, Dva, Dte = Data(by["train"]), Data(by["validation"]), Data(by["test"])
    lh, la = Dtr.layered(layer_tr)
    m_tr = Model(Design(groups, l2, l2e, recal)).fit(Dtr, lh, la, layer_tr["rho"], layer_tr["nb_dispersion"])
    lhv, lav = Dva.layered(layer_tr)
    mhv, mav = m_tr.predict(Dva, lhv, lav)
    Pm_val = P_from_mu(by["validation"], mhv, mav, m_tr.rho, m_tr.r)
    Pb_val = baseline_P(by["validation"], layer_tr, coef)
    rv = split_report(by["validation"], Pb_val, Pm_val, with_cal=False)
    rv.pop("_L")
    report["validation_fit_on_train"] = rv
    write_predictions(args.pred_validation, by["validation"], Pb_val, Pm_val, "train")
    print("validation done", flush=True)

    # ---------------------------------------------------------------- final fit on train + validation
    tv_rows = by["train"] + by["validation"]
    Dtv = Data(tv_rows)
    lh2, la2 = Dtv.layered(layer_tv)
    m_tv = Model(Design(groups, l2, l2e, recal)).fit(Dtv, lh2, la2, layer_tv["rho"], layer_tv["nb_dispersion"])
    lht, lat = Dte.layered(layer_tv)
    mht, mat = m_tv.predict(Dte, lht, lat)
    te = by["test"]
    Pm = P_from_mu(te, mht, mat, m_tv.rho, m_tv.r)
    Pb = baseline_P(te, layer_tr, coef)          # specified baseline: train-only goal layer
    Pb2 = baseline_P(te, layer_tv, coef)         # control: same (train + validation) goal layer as the model
    rt = split_report(te, Pb, Pm, with_cal=True)
    Lb, Lm = rt.pop("_L")
    rt2 = split_report(te, Pb2, Pm, with_cal=False)
    rt2.pop("_L")
    report["test"] = rt
    report["test_vs_baseline_trainval_layer"] = {"note": "control: baseline uses the train+validation goal layer "
                                                         "like the deployed model", "segments": rt2["segments"]}
    # by-competition table (model vs baseline, no CI)
    comps = np.array([r["competition_provider_id"] for r in te])
    bycomp = {}
    for c in sorted(set(comps), key=lambda c: -int((comps == c).sum())):
        s = comps == c
        bycomp[c] = {"n": int(s.sum()), "1x2_baseline": round(float(Lb["1x2_logloss"][s].mean()), 5),
                     "1x2_model": round(float(Lm["1x2_logloss"][s].mean()), 5)}
    report["test"]["by_competition_1x2"] = bycomp

    # ---------------------------------------------------------------- market (test rows with closing odds)
    odds = M.load_odds(args.odds_current, args.odds_history, args.db)
    report["test_market"] = market_block(te, Pb, Pm, Pb2, odds)
    write_predictions(args.pred_test, te, Pb, Pm, "train+validation")
    print("test scored once", flush=True)

    # ---------------------------------------------------------------- deploy criteria
    seg = rt["segments"]
    a = seg["all"]["1x2_logloss"]
    e = seg["european"]["1x2_logloss"] if seg["european"]["n"] else None
    o = seg["all"]["over25_logloss"]
    ca = {"rule": "test 1X2 log loss paired 90 % CI upper bound < 0", "diff": a["diff"], "ci90": a.get("ci90"),
          "pass": bool(a.get("ci90") and a["ci90"][1] < 0)}
    cb = {"rule": "European test subset not worse: mean diff <= 0 (CI shown)",
          "diff": e["diff"] if e else None, "ci90": e.get("ci90") if e else None, "n": seg["european"]["n"],
          "pass": bool(e and e["diff"] <= 0)}
    cc = {"rule": "O/U 2.5 log loss not worse beyond the CI: CI lower bound <= 0 (not significantly worse)",
          "diff": o["diff"], "ci90": o.get("ci90"), "pass": bool(o.get("ci90") and o["ci90"][0] <= 0)}
    seg2 = rt2["segments"]
    control = {"1x2_all": seg2["all"]["1x2_logloss"], "1x2_european": seg2["european"]["1x2_logloss"],
               "ou25_all": seg2["all"]["over25_logloss"]}
    crit = {"a": ca, "b": cb, "c": cc, "all_pass": bool(ca["pass"] and cb["pass"] and cc["pass"]),
            "control_vs_baseline_with_trainval_goal_layer": control}
    report["deploy_criteria"] = crit
    print("criteria:", json.dumps({k: crit[k] for k in ("a", "b", "c", "all_pass")}), flush=True)

    # ---------------------------------------------------------------- refit on all rows (deployment, not evaluated)
    all_rows = tv_rows + te
    Dall = Data(all_rows)
    lh3, la3 = Dall.layered(layer_tv)
    m_all = Model(Design(groups, l2, l2e, recal)).fit(Dall, lh3, la3, layer_tv["rho"], layer_tv["nb_dispersion"])
    cand = {
        "format": "match_model_candidate_full/v1",
        "status": "DRAFT candidate - nothing in backend/config/ was written; deploy only if deploy_criteria.all_pass "
                  "and the integration (app/features/match_model_features.py, lead) is verified",
        "built_at": report["built_at"],
        "splits": {"train": "2022-08-01..2025-06-30", "validation": "2025-07-01..2026-01-31",
                   "test": "2026-02-01..2026-10-12 (scored once)"},
        "selected_on_validation": {"groups": groups, "l2": l2, "l2_euro": l2e, "recal": recal, "clip_z": CLIP},
        "equation": ("L_side = goal layer (data/training/goal_layer_trainval.json) applied to the walk-forward rating "
                     "lambdas. s = (ln L_h + ln L_a)/2 - m_s, d = (ln L_h - ln L_a)/2. "
                     "ln mu_h = ln L_h + c_home + alpha_total*s + alpha_diff*d + [european: e_home + e_total*s + "
                     "e_diff*d + e_value*z_value] + sum coef_per_sd * z + sum missing coef * indicator; "
                     "ln mu_a = ln L_a + c_away + alpha_total*s - alpha_diff*d + [european: e_away + e_total*s - "
                     "e_diff*d - e_value*z_value] + the same terms from the away side's view (att/def swapped, "
                     "signed terms negated). z = clip((x - mean)/sd, -4, 4); unknown x -> z = 0 and indicator 1. "
                     "Score probabilities: NB(nb_dispersion) x Dixon-Coles(rho) on 0..10 x 0..10 with mu_h, mu_a."),
        "european_definition": "competition_provider_id in 42 (UCL), 73 (UEL), 10216 (UECL), 10611, 10613, 10615 "
                               "(qualifiers); match_features comp_is_euro = 1",
        "ratings": {"asof_file": "data/training/player_impact_asof_all.csv.gz (2-weekly cutoffs 2022-09-05..2026-10-14; "
                                 "a match uses the latest cutoff strictly before kick-off)",
                    "meta_file": "data/training/player_impact_all_meta.json",
                    "runtime_export": "data/training/player_impact_latest.json (cutoff 2026-10-14; "
                                      "player id -> offence, defence, rapm_minutes, prior_only)",
                    "usual_xi": "mean over the team's previous <= 10 line-ups (>= 3) valued at the same cutoff, scaled "
                                "to 11 players; unrated starters get the replacement level of their position"},
        "feature_source": "scripts/training/build_match_features.py (column definitions: "
                          "data/training/README_match_features.md, README_match_features_full.md)",
        "missing_rules": {"general": "unknown raw value -> z = 0 plus a missing indicator per block; never imputed",
                          "unavailable_list": "unavail_* are unknown when FotMob sent no `unavailable` key; "
                                              "expected_return is never read",
                          "value": "value_log_ratio unknown when either side's starters' value is missing"},
        "evaluated_model": model_doc(m_tv, "fitted on train + validation (goal layer train+val); scored on test once",
                                     rel(args.goal_layer_trainval), layer_tv,
                                     {"n": len(tv_rows), "from": "2022-08-01", "to": "2026-01-31"}),
        "refit_all_rows": model_doc(m_all, "same configuration refitted on train + validation + test (deployment; "
                                           "not evaluated)", rel(args.goal_layer_trainval), layer_tv,
                                    {"n": len(all_rows), "from": "2022-08-01", "to": "2026-10-12"}),
        "deploy_criteria": crit,
        "test_summary": {k: report["test"]["segments"][k] for k in ("all", "league", "european")},
        "test_market_summary": {k: report["test_market"].get(k) for k in ("n", "n_ou25", "all", "european")},
        "report_file": rel(args.report),
    }
    # the evaluated model's own fit with the train-only goal layer (validation numbers) for reference
    cand["validation_model"] = model_doc(m_tr, "fitted on train only (goal layer train-only); validation scoring",
                                         rel(args.goal_layer_train), layer_tr,
                                         {"n": len(by["train"]), "from": "2022-08-01", "to": "2025-06-30"})
    args.candidate.write_text(json.dumps(cand, indent=1, allow_nan=False), encoding="utf-8")
    report["seconds"] = round(time.time() - t0, 1)
    args.report.write_text(json.dumps(report, indent=1, allow_nan=False), encoding="utf-8")
    print(f"-> {args.report}, {args.candidate}, predictions ({report['seconds']} s)", flush=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="full-data match model (select on validation, test once)")
    ap.add_argument("--stage", choices=("select", "final"), required=True)
    ap.add_argument("--features", type=Path, default=DATA / "match_features_full.csv.gz")
    ap.add_argument("--goal-layer-train", type=Path, default=DATA / "goal_layer_train_only.json")
    ap.add_argument("--goal-layer-trainval", type=Path, default=DATA / "goal_layer_trainval.json")
    ap.add_argument("--frozen", type=Path, default=DATA / "match_model_full_frozen.json")
    ap.add_argument("--report", type=Path, default=DATA / "match_model_full_report.json")
    ap.add_argument("--candidate", type=Path, default=DATA / "match_model_candidate_full.json")
    ap.add_argument("--pred-validation", type=Path, default=DATA / "match_model_predictions_validation.csv.gz")
    ap.add_argument("--pred-test", type=Path, default=DATA / "match_model_predictions_test.csv.gz")
    ap.add_argument("--odds-current", type=Path, default=BACKEND_DIR / "data" / "external" / "football_data_matches.csv")
    ap.add_argument("--odds-history", type=Path, default=BACKEND_DIR / "data" / "external" / "football_data_history.csv")
    ap.add_argument("--db", type=Path, default=BACKEND_DIR / "football_intelligence.db")
    args = ap.parse_args(argv)
    return select_stage(args) if args.stage == "select" else final_stage(args)


if __name__ == "__main__":
    sys.exit(main())
