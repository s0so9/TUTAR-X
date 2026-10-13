"""Match model: fit and evaluate on time splits (stage B, steps 3 and 4).

Input: data/training/match_features.csv.gz (build_match_features.py). Rows with a rating lambda
and a result. Time splits are arguments: train = kickoff < --train-end, validation =
[--train-end, --val-end), test = kickoff >= --val-end (optionally < --test-end).

Models
  (a) baseline = production: rating lambda + goal layer, squad value (beta 0.048 European /
      0.0279 domestic, app/prediction/squad_value.py) and lineup form (gamma of
      config/player_form.json) as supremacy shifts; missing value/form = no shift (as in
      production); Dixon-Coles rho + NB dispersion of config/goal_model.json.
  (b) L2-penalised Poisson-type adjustment of log lambda_home / log lambda_away:
        log mu_side = log lambda_side + c_side + alpha (log lambda_side - m) + sum_k beta_k z_k(side)
      z = standardised features from the attacking side's / defending side's perspective, a
      missing-value indicator per feature block (missing raw value -> z = 0). Fitted by maximum
      likelihood of the exact score under the Dixon-Coles / negative-binomial score model of
      train_goal_model.py (rho and NB dispersion fitted jointly), analytic gradient.
      L2 strength chosen on validation; feature groups pruned by backward elimination on
      validation ("b_selected").
  (c) HistGradientBoostingRegressor(loss="poisson") on goals, log lambda as a feature, monotonic
      constraints where the direction is known, early stopping on the validation set; one
      stacked model (side rows + is_home) or two separate models, chosen on validation; rho / NB
      dispersion of its score model fitted on validation predictions.
Hyper-parameters use validation only. The chosen models are refitted on train + validation and
the test set is scored once at the end: 1X2 log loss / Brier, O/U 2.5, BTTS, exact score,
calibration tables, paired bootstrap 90 % CIs of the difference vs the baseline, and for test
matches with closing odds: model vs market log loss and the flat-stake value-bet backtest of
benchmark_vs_market.py.

Usage (from backend/):
  venv/Scripts/python.exe scripts/training/train_match_model.py
  venv/Scripts/python.exe scripts/training/train_match_model.py --features data/training/match_features_all.csv.gz \
      --train-end 2025-07-01 --val-end 2026-01-01 --out data/training/match_model_report_all.json \
      --candidate data/training/match_model_candidate_all.json
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln

BACKEND_DIR = Path(__file__).resolve().parents[2]
TRAINING_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TRAINING_DIR))
import train_goal_model as T  # noqa: E402

DATA = BACKEND_DIR / "data"
MAX_GOALS = T.MAX_GOALS
G = np.arange(MAX_GOALS + 1, dtype=float)
SIDES = ("home", "away")
REST_CLIP = (2.0, 10.0)

# ----------------------------------------------------------------------------- feature terms
# (name, group, kind, per-side or match column, transform)
#   kind "att": the scoring side's own column; "def": the conceding side's column;
#        "signed": home-minus-away match column, + in the home equation and - in the away one;
#        "both": the same match column in both equations.
TERMS = [
    ("value_att", "value", "signed", "value_log_ratio", None),
    ("form_att", "form_prod", "signed", "lineup_form", None),
    ("xi_off_att", "xi", "att", "xi_d_off", None),
    ("xi_def_def", "xi", "def", "xi_d_def", None),
    ("unav_off_att", "absent", "att", "unavail_off_w", None),
    ("unav_def_def", "absent", "def", "unavail_def_w", None),
    ("inj_att", "absent", "att", "n_injury", None),
    ("inj_def", "absent", "def", "n_injury", None),
    ("susp_att", "absent", "att", "n_suspension", None),
    ("susp_def", "absent", "def", "n_suspension", None),
    ("xgf_att", "form", "att", "xg_for_l5", None),
    ("xga_def", "form", "def", "xg_against_l5", None),
    ("ppg_att", "form", "att", "ppg_l5", None),
    ("ppg_def", "form", "def", "ppg_l5", None),
    ("rest_att", "rest", "att", "rest_days", "clip"),
    ("rest_def", "rest", "def", "rest_days", "clip"),
    ("n14_att", "rest", "att", "n_matches_14d", None),
    ("n14_def", "rest", "def", "n_matches_14d", None),
    ("eb_att", "rest", "att", "euro_before_3d", None),
    ("eb_def", "rest", "def", "euro_before_3d", None),
    ("ea_att", "rest", "att", "euro_after_3d", None),
    ("ea_def", "rest", "def", "euro_after_3d", None),
    ("euro", "context", "both", "comp_is_euro", None),
    ("hadv", "context", "signed", "league_hadv_dev", None),
]
# missing-value indicators (1 = the block's value is unknown for that side / match)
MISSING = [
    ("value_miss", "value", "both", "value_log_ratio"),
    ("form_miss", "form_prod", "both", "lineup_form"),
    ("xi_miss_att", "xi", "att", "xi_d_off"),
    ("xi_miss_def", "xi", "def", "xi_d_def"),
    ("unav_miss_att", "absent", "att", "n_injury"),
    ("unav_miss_def", "absent", "def", "n_injury"),
    ("xgl5_miss_att", "form", "att", "xg_for_l5"),
    ("xgl5_miss_def", "form", "def", "xg_against_l5"),
]
GROUPS = ["value", "form_prod", "xi", "absent", "form", "rest", "context"]
# HGB: per-side raw columns from the attacking (att) and defending (def) side
HGB_SIDE_COLS = ["xi_d_off", "xi_d_def", "unavail_off_w", "unavail_def_w", "n_injury", "n_suspension",
                 "xg_for_l5", "xg_against_l5", "ppg_l5", "rest_days", "n_matches_14d", "euro_before_3d",
                 "euro_after_3d"]
HGB_SIDE_GROUP = {"xi_d_off": "xi", "xi_d_def": "xi", "unavail_off_w": "absent", "unavail_def_w": "absent",
                  "n_injury": "absent", "n_suspension": "absent", "xg_for_l5": "form", "xg_against_l5": "form",
                  "ppg_l5": "form", "rest_days": "rest", "n_matches_14d": "rest", "euro_before_3d": "rest",
                  "euro_after_3d": "rest"}
HGB_MONOTONE = {"loglam_att": 1, "value_att": 1, "att_xi_d_off": 1, "def_xi_d_def": -1,
                "att_unavail_off_w": -1, "def_unavail_def_w": 1}


# ============================================================================ data
def fnum(s: str) -> Optional[float]:
    if s is None or s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_rows(path: Path) -> list[dict]:
    rows = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["lambda_home"] == "" or r["y_home_goals"] == "" or r["y_away_goals"] == "":
                continue
            x = {"match_id": r["match_id"], "at": datetime.fromisoformat(r["kickoff"]),
                 "comp": r["competition_provider_id"], "comp_type": r["comp_type"],
                 "hs": int(float(r["y_home_goals"])), "as": int(float(r["y_away_goals"]))}
            for k, v in r.items():
                if k in ("match_id", "kickoff", "competition_provider_id", "comp_type", "competition_name",
                         "season", "home_team_id", "away_team_id", "details_source", "lambda_source",
                         "lambda_cutoff", "ratings_cutoff", "source_league_id"):
                    continue
                x[k] = fnum(v)
            rows.append(x)
    rows.sort(key=lambda x: (x["at"], x["match_id"]))
    return rows


def side_col(row: dict, eq: str, kind: str, col: str) -> Optional[float]:
    """Raw value of a term for the equation of side ``eq`` (home / away goals)."""
    other = "away" if eq == "home" else "home"
    if kind == "att":
        return row.get(f"{eq}_{col}")
    if kind == "def":
        return row.get(f"{other}_{col}")
    v = row.get(col)
    if kind == "signed" and v is not None and eq == "away":
        return -v
    return v


def transform(v: Optional[float], how: Optional[str]) -> Optional[float]:
    if v is None:
        return None
    if how == "clip":
        return min(max(v, REST_CLIP[0]), REST_CLIP[1])
    return v


# ============================================================================ (b) design + likelihood
class Design:
    """Standardisation statistics (fitted on training rows) and design matrices."""

    def __init__(self, groups: list[str]):
        self.groups = list(groups)
        self.terms = [t for t in TERMS if t[1] in groups]
        self.missing = [m for m in MISSING if m[1] in groups]
        self.names = ["c_home", "c_away", "alpha_loglam"] + [t[0] for t in self.terms] + [m[0] for m in self.missing]
        self.penalised = np.array([False, False, False] + [True] * (len(self.terms) + len(self.missing)))
        self.stats: dict = {}
        self.m_loglam = 0.0

    def fit_stats(self, rows: list[dict]) -> "Design":
        ll = [math.log(r[f"lambda_{s}"]) for r in rows for s in SIDES]
        self.m_loglam = float(np.mean(ll))
        for name, _g, kind, col, how in self.terms:
            vals = [transform(side_col(r, s, kind, col), how) for r in rows for s in SIDES]
            vals = np.array([v for v in vals if v is not None], dtype=float)
            if len(vals) < 2:
                self.stats[name] = (0.0, 1.0)
                continue
            mu = 0.0 if kind == "signed" else float(vals.mean())
            sd = float(np.sqrt(np.mean((vals - mu) ** 2)))
            self.stats[name] = (mu, sd if sd > 1e-9 else 1.0)
        return self

    def matrices(self, rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
        k = len(self.names)
        out = []
        for eq in SIDES:
            X = np.zeros((len(rows), k))
            X[:, 0 if eq == "home" else 1] = 1.0
            X[:, 2] = [math.log(r[f"lambda_{eq}"]) - self.m_loglam for r in rows]
            for j, (name, _g, kind, col, how) in enumerate(self.terms):
                mu, sd = self.stats[name]
                for i, r in enumerate(rows):
                    v = transform(side_col(r, eq, kind, col), how)
                    if v is not None:
                        X[i, 3 + j] = (v - mu) / sd
            off = 3 + len(self.terms)
            for j, (_name, _g, kind, col) in enumerate(self.missing):
                for i, r in enumerate(rows):
                    X[i, off + j] = 1.0 if side_col(r, eq, kind, col) is None else 0.0
            out.append(X)
        return out[0], out[1]


def log_nb(mu: np.ndarray, r: float) -> np.ndarray:
    k = G[None, :]
    m = mu[:, None]
    return gammaln(k + r) - gammaln(r) - gammaln(k + 1) + r * np.log(r / (r + m)) + k * np.log(m / (r + m))


def score_loglik(eh: np.ndarray, ea: np.ndarray, hs: np.ndarray, as_: np.ndarray, rho: float, r: float,
                 grad: bool = False):
    """Per-match log P(score) under NB marginals x Dixon-Coles tau, truncated to 0..MAX_GOALS and
    renormalised exactly like train_goal_model.score_matrix; optional d/d eta_home, d/d eta_away."""
    mh, ma = np.exp(eh), np.exp(ea)
    n = len(eh)
    ph, pa = np.exp(log_nb(mh, r)), np.exp(log_nb(ma, r))
    P = ph[:, :, None] * pa[:, None, :]
    tau = np.ones((n, 4))
    tau[:, 0] = 1 - mh * ma * rho
    tau[:, 1] = 1 + mh * rho      # (0, 1)
    tau[:, 2] = 1 + ma * rho      # (1, 0)
    tau[:, 3] = 1 - rho           # (1, 1)
    tc = np.clip(tau, 1e-6, None)
    P[:, 0, 0] *= tc[:, 0]
    P[:, 0, 1] *= tc[:, 1]
    P[:, 1, 0] *= tc[:, 2]
    P[:, 1, 1] *= tc[:, 3]
    Z = P.sum(axis=(1, 2))
    idx = np.arange(n)
    x, y = np.clip(hs, 0, MAX_GOALS), np.clip(as_, 0, MAX_GOALS)
    pobs = P[idx, x, y]
    ll = np.log(np.clip(pobs / Z, 1e-300, None))
    if not grad:
        return ll
    active = tau > 1e-6
    dh = r * (G[None, :] - mh[:, None]) / (r + mh[:, None])        # dlog NB(i)/d eta_h
    da = r * (G[None, :] - ma[:, None]) / (r + ma[:, None])
    # dlog tau / d eta (zero where the clip is active)
    t00h = np.where(active[:, 0], -mh * ma * rho / tc[:, 0], 0.0)
    t01h = np.where(active[:, 1], mh * rho / tc[:, 1], 0.0)
    t00a = t00h
    t10a = np.where(active[:, 2], ma * rho / tc[:, 2], 0.0)
    W = P / Z[:, None, None]
    Eh = (W.sum(axis=2) * dh).sum(1) + W[:, 0, 0] * t00h + W[:, 0, 1] * t01h
    Ea = (W.sum(axis=1) * da).sum(1) + W[:, 0, 0] * t00a + W[:, 1, 0] * t10a
    oh = dh[idx, x] + np.where((x == 0) & (y == 0), t00h, 0.0) + np.where((x == 0) & (y == 1), t01h, 0.0)
    oa = da[idx, y] + np.where((x == 0) & (y == 0), t00a, 0.0) + np.where((x == 1) & (y == 0), t10a, 0.0)
    return ll, oh - Eh, oa - Ea


def fit_glm(lh, la, Xh, Xa, hs, as_, penalised, l2, rho0, r0, theta0=None, recal=True):
    """MAP fit of theta (+ rho, log r). Returns theta, rho, r, train nll, converged.

    The first three columns of X are the recalibration terms (home / away intercepts, scale of
    log lambda). With recal=False they are fixed at 0 and rho / NB dispersion at rho0 / r0 (the
    production goal layer's values): only the feature coefficients are fitted."""
    k = Xh.shape[1]
    llh, lla = np.log(lh), np.log(la)
    pen = penalised.astype(float)

    def obj(p):
        th, rho, lr = p[:k], p[k], p[k + 1]
        r = math.exp(lr)
        eh, ea = llh + Xh @ th, lla + Xa @ th
        ll, gh, ga = score_loglik(eh, ea, hs, as_, rho, r, grad=True)
        f = -ll.sum() + 0.5 * l2 * np.sum(pen * th * th)
        g = np.empty_like(p)
        g[:k] = -(Xh.T @ gh + Xa.T @ ga) + l2 * pen * th
        for j, h in (((k, 1e-5), (k + 1, 1e-4)) if recal else ()):
            pp, pm = p.copy(), p.copy()
            pp[j] += h
            pm[j] -= h
            fp = -score_loglik(llh + Xh @ th, lla + Xa @ th, hs, as_, pp[k], math.exp(pp[k + 1])).sum()
            fm = -score_loglik(llh + Xh @ th, lla + Xa @ th, hs, as_, pm[k], math.exp(pm[k + 1])).sum()
            g[j] = (fp - fm) / (2 * h)
        if not recal:
            g[k:] = 0.0
        return f, g

    p0 = np.concatenate([np.zeros(k) if theta0 is None else theta0, [rho0, math.log(r0)]])
    if recal:
        bounds = [(None, None)] * k + [(-0.3, 0.3), (0.0, math.log(1000.0))]
    else:
        bounds = [(0.0, 0.0)] * 3 + [(None, None)] * (k - 3) + [(rho0, rho0), (math.log(r0), math.log(r0))]
    res = minimize(obj, p0, jac=True, method="L-BFGS-B", bounds=bounds, options={"maxiter": 2000})
    th, rho, r = res.x[:k], float(res.x[k]), float(math.exp(res.x[k + 1]))
    nll = float(-score_loglik(llh + Xh @ th, lla + Xa @ th, hs, as_, rho, r).sum())
    return th, rho, r, nll, bool(res.success)


class GLMModel:
    def __init__(self, groups: list[str], l2: float, recal: bool = True):
        self.design = Design(groups)
        self.l2 = l2
        self.recal = recal
        self.theta = None
        self.rho = None
        self.r = None
        self.converged = None

    def fit(self, rows: list[dict], rho0: float, r0: float) -> "GLMModel":
        self.design.fit_stats(rows)
        Xh, Xa = self.design.matrices(rows)
        lh, la, hs, as_ = arrays(rows)
        self.theta, self.rho, self.r, self.train_nll, self.converged = fit_glm(
            lh, la, Xh, Xa, hs, as_, self.design.penalised, self.l2, rho0, r0, recal=self.recal)
        return self

    def predict(self, rows: list[dict]):
        Xh, Xa = self.design.matrices(rows)
        lh, la, _hs, _as = arrays(rows)
        return lh * np.exp(Xh @ self.theta), la * np.exp(Xa @ self.theta), self.rho, self.r

    def coefficients(self) -> dict:
        return {n: round(float(c), 6) for n, c in zip(self.design.names, self.theta)}


def arrays(rows):
    return (np.array([r["lambda_home"] for r in rows]), np.array([r["lambda_away"] for r in rows]),
            np.array([r["hs"] for r in rows]), np.array([r["as"] for r in rows]))


# ============================================================================ (a) baseline
def production_params() -> dict:
    from app.prediction.goal_model import get_goal_layer
    from app.prediction.lineup_form import get_lineup_form
    from app.prediction.squad_value import SQUAD_VALUE_BETA, SQUAD_VALUE_BETA_DOMESTIC
    layer = get_goal_layer()
    form = get_lineup_form()
    return {"beta_value_cross_league": SQUAD_VALUE_BETA, "beta_value_domestic": SQUAD_VALUE_BETA_DOMESTIC,
            "gamma_form": form.gamma if form is not None else 0.0,
            "rho": layer.rho or 0.0, "nb_dispersion": layer.nb_dispersion,
            "goal_layer": {"m": layer.m, "a": layer.a, "b": layer.b, "trained": layer.trained}}


def baseline_predict(rows: list[dict], prod: dict):
    lh, la, _hs, _as = arrays(rows)
    shift = np.zeros(len(rows))
    for i, r in enumerate(rows):
        v, f = r.get("value_log_ratio"), r.get("lineup_form")
        beta = prod["beta_value_cross_league"] if r.get("comp_is_euro") == 1 else prod["beta_value_domestic"]
        if v is not None:
            shift[i] += beta * v
        if f is not None:
            shift[i] += prod["gamma_form"] * f
    return lh * np.exp(shift), la * np.exp(-shift), prod["rho"], prod["nb_dispersion"]


# ============================================================================ (c) gradient boosting
def hgb_matrix(rows: list[dict], groups: list[str], stacked_eq: Optional[str] = None):
    """Feature matrix from the attacking side's perspective; NaN = unknown. Returns (X, names, y)."""
    names = ["loglam_att", "loglam_def"]
    if stacked_eq is None:
        names.append("is_home")
    if "value" in groups:
        names.append("value_att")
    if "form_prod" in groups:
        names.append("form_att")
    side_cols = [c for c in HGB_SIDE_COLS if HGB_SIDE_GROUP[c] in groups]
    names += [f"att_{c}" for c in side_cols] + [f"def_{c}" for c in side_cols]
    if "context" in groups:
        names += ["euro", "hadv"]
    eqs = SIDES if stacked_eq is None else (stacked_eq,)
    X = np.full((len(rows) * len(eqs), len(names)), np.nan)
    y = np.zeros(len(rows) * len(eqs))
    for e, eq in enumerate(eqs):
        other = "away" if eq == "home" else "home"
        for i, r in enumerate(rows):
            row = []
            row += [math.log(r[f"lambda_{eq}"]), math.log(r[f"lambda_{other}"])]
            if stacked_eq is None:
                row.append(1.0 if eq == "home" else 0.0)
            if "value" in groups:
                row.append(side_col(r, eq, "signed", "value_log_ratio"))
            if "form_prod" in groups:
                row.append(side_col(r, eq, "signed", "lineup_form"))
            row += [r.get(f"{eq}_{c}") for c in side_cols] + [r.get(f"{other}_{c}") for c in side_cols]
            if "context" in groups:
                row += [r.get("comp_is_euro"), side_col(r, eq, "signed", "league_hadv_dev")]
            X[e * len(rows) + i] = [np.nan if v is None else v for v in row]
            y[e * len(rows) + i] = r["hs"] if eq == "home" else r["as"]
    return X, names, y


class HGBModel:
    def __init__(self, params: dict, groups: list[str], structure: str):
        self.params = dict(params)
        self.groups = list(groups)
        self.structure = structure          # "stacked" or "separate"
        self.models = {}
        self.n_iter = {}
        self.rho = None
        self.r = None

    def _new(self, names, max_iter, early):
        from sklearn.ensemble import HistGradientBoostingRegressor
        mono = [HGB_MONOTONE.get(n, 0) for n in names]
        return HistGradientBoostingRegressor(
            loss="poisson", learning_rate=self.params["learning_rate"], max_leaf_nodes=self.params["max_leaf_nodes"],
            min_samples_leaf=self.params["min_samples_leaf"], l2_regularization=self.params["l2_regularization"],
            max_iter=max_iter, monotonic_cst=mono, early_stopping=early, n_iter_no_change=30,
            scoring="loss", random_state=0)

    def _parts(self, rows):
        if self.structure == "stacked":
            return {"both": hgb_matrix(rows, self.groups)}
        return {eq: hgb_matrix(rows, self.groups, stacked_eq=eq) for eq in SIDES}

    def fit(self, train: list[dict], val: Optional[list[dict]] = None, n_iter: Optional[dict] = None):
        tr = self._parts(train)
        va = self._parts(val) if val else None
        for key, (X, names, y) in tr.items():
            if n_iter is None:
                # early stopping on the validation set, then the iteration with the lowest validation
                # Poisson deviance (sklearn keeps the trailing no-improvement iterations otherwise);
                # boosting is deterministic, so a refit with max_iter=best equals the truncated model
                m = self._new(names, 2000, True)
                Xv, yv = va[key][0], va[key][2]
                m.fit(X, y, X_val=Xv, y_val=yv)
                dev = [float(np.mean(p - yv * np.log(np.clip(p, 1e-12, None)))) for p in m.staged_predict(Xv)]
                best = int(np.argmin(dev)) + 1
                m = self._new(names, best, False)
                m.fit(X, y)
                self.n_iter[key] = best
            else:
                m = self._new(names, n_iter[key], False)
                m.fit(X, y)
                self.n_iter[key] = int(n_iter[key])
            self.models[key] = m
            self.names = names
        return self

    def predict_mu(self, rows: list[dict]):
        parts = self._parts(rows)
        if self.structure == "stacked":
            X, _n, _y = parts["both"]
            p = self.models["both"].predict(X)
            return p[:len(rows)], p[len(rows):]
        return self.models["home"].predict(parts["home"][0]), self.models["away"].predict(parts["away"][0])

    def predict(self, rows):
        mh, ma = self.predict_mu(rows)
        return mh, ma, self.rho, self.r


def fit_score_params(mh, ma, hs, as_, rho0, r0):
    """ML rho and NB dispersion for fixed means (2 parameters)."""
    eh, ea = np.log(np.clip(mh, 1e-6, None)), np.log(np.clip(ma, 1e-6, None))

    def f(p):
        return -score_loglik(eh, ea, hs, as_, p[0], math.exp(p[1])).sum()

    res = minimize(f, np.array([rho0, math.log(r0)]), method="L-BFGS-B",
                   bounds=[(-0.3, 0.3), (0.0, math.log(1000.0))])
    return float(res.x[0]), float(math.exp(res.x[1]))


# ============================================================================ evaluation
def per_match(rows, mh, ma, rho, r) -> dict:
    hs = np.array([x["hs"] for x in rows])
    as_ = np.array([x["as"] for x in rows])
    m = T.score_matrix(np.asarray(mh, float), np.asarray(ma, float), rho, r)
    p1x2, o25, _o35, btts = T.markets(m)
    k = np.where(hs > as_, 0, np.where(hs == as_, 1, 2))
    eps = 1e-12
    y25 = (hs + as_) > 2.5
    yb = (hs > 0) & (as_ > 0)
    cs = np.clip(hs, 0, MAX_GOALS), np.clip(as_, 0, MAX_GOALS)
    return {
        "1x2_logloss": -np.log(np.clip(p1x2[np.arange(len(k)), k], eps, 1)),
        "1x2_brier": ((p1x2 - np.eye(3)[k]) ** 2).sum(1),
        "over25_logloss": -np.where(y25, np.log(np.clip(o25, eps, 1)), np.log(np.clip(1 - o25, eps, 1))),
        "over25_brier": (o25 - y25) ** 2,
        "btts_logloss": -np.where(yb, np.log(np.clip(btts, eps, 1)), np.log(np.clip(1 - btts, eps, 1))),
        "btts_brier": (btts - yb) ** 2,
        "score_logloss": -np.log(np.clip(m[np.arange(len(k)), cs[0], cs[1]], eps, 1)),
        "_p1x2": p1x2, "_o25": o25, "_btts": btts, "_k": k, "_y25": y25, "_yb": yb,
        "_mh": np.asarray(mh, float), "_ma": np.asarray(ma, float),
    }


METRICS = ["1x2_logloss", "1x2_brier", "over25_logloss", "over25_brier", "btts_logloss", "btts_brier", "score_logloss"]


def summary(pm: dict, rows) -> dict:
    out = {k: round(float(pm[k].mean()), 5) for k in METRICS}
    hs = np.array([x["hs"] for x in rows])
    as_ = np.array([x["as"] for x in rows])
    out.update(n=len(rows), mean_pred_total=round(float((pm["_mh"] + pm["_ma"]).mean()), 4),
               mean_actual_total=round(float((hs + as_).mean()), 4),
               pred_home_rate=round(float(pm["_p1x2"][:, 0].mean()), 4),
               actual_home_rate=round(float((pm["_k"] == 0).mean()), 4),
               pred_draw_rate=round(float(pm["_p1x2"][:, 1].mean()), 4),
               actual_draw_rate=round(float((pm["_k"] == 1).mean()), 4))
    return out


def bootstrap_diff(pm: dict, ref: dict, n_boot: int, seed: int) -> dict:
    n = len(pm["1x2_logloss"])
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    out = {}
    for k in METRICS:
        d = pm[k] - ref[k]
        boots = d[idx].mean(1)
        out[k] = {"mean": round(float(d.mean()), 5),
                  "ci90": [round(float(np.quantile(boots, 0.05)), 5), round(float(np.quantile(boots, 0.95)), 5)],
                  "p_boot_ge_0": round(float((boots >= 0).mean()), 4)}
    return out


def calibration(pm: dict, bins: int = 10) -> dict:
    out = {}
    for name, p, y in (("home", pm["_p1x2"][:, 0], pm["_k"] == 0), ("draw", pm["_p1x2"][:, 1], pm["_k"] == 1),
                       ("away", pm["_p1x2"][:, 2], pm["_k"] == 2), ("over25", pm["_o25"], pm["_y25"]),
                       ("btts", pm["_btts"], pm["_yb"])):
        order = np.argsort(p, kind="stable")
        tab = []
        for chunk in np.array_split(order, bins):
            if len(chunk):
                tab.append({"pred": round(float(p[chunk].mean()), 4), "actual": round(float(y[chunk].mean()), 4),
                            "n": int(len(chunk))})
        out[name] = tab
    return out


def fodds(x) -> Optional[float]:
    try:
        v = float(x)
        return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def load_odds(current: Optional[Path], history: Optional[Path], db: Optional[Path]) -> dict:
    """FotMob match id -> closing market (benchmark_vs_market.py columns and preference order)."""
    out = {}
    id_map = {}
    if db is not None and Path(db).exists():
        con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
        try:
            id_map = {r[0]: str(r[1]) for r in con.execute("select id, provider_id from matches")}
        finally:
            con.close()

    def parse(r):
        odds = [fodds(r.get(k)) for k in ("PSCH", "PSCD", "PSCA")]
        if None in odds:
            odds = [fodds(r.get(k)) for k in ("AvgCH", "AvgCD", "AvgCA")]
        ou = [fodds(r.get("PC>2.5")), fodds(r.get("PC<2.5"))]
        if None in ou:
            ou = [fodds(r.get("AvgC>2.5")), fodds(r.get("AvgC<2.5"))]
        return {"mk1x2": [float(r["p_close_home"]), float(r["p_close_draw"]), float(r["p_close_away"])],
                "odds1x2": odds if None not in odds else None,
                "mkover": float(r["p_close_over25"]) if r.get("p_close_over25") else None,
                "oddsou": ou if None not in ou else None}

    if current is not None and Path(current).exists():
        with open(current, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                pid = id_map.get(r.get("db_match_id") or "")
                if pid and r.get("db_score_agrees") == "1" and r.get("p_close_home") and pid not in out:
                    out[pid] = parse(r)
    if history is not None and Path(history).exists():
        with open(history, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                pid = r.get("fotmob_match_id") or ""
                if (pid and r.get("score_agrees") == "1" and r.get("fotmob_awarded") != "1"
                        and r.get("p_close_home") and pid not in out):
                    out[pid] = parse(r)
    return out


def market_eval(rows, preds: dict, odds: dict, min_ev: float, n_boot: int, seed: int) -> dict:
    sel = [i for i, r in enumerate(rows) if r["match_id"] in odds]
    if not sel:
        return {"n": 0}
    sub = [rows[i] for i in sel]
    hs = np.array([r["hs"] for r in sub])
    as_ = np.array([r["as"] for r in sub])
    k = np.where(hs > as_, 0, np.where(hs == as_, 1, 2))
    y = (hs + as_) > 2.5
    mk = np.array([odds[r["match_id"]]["mk1x2"] for r in sub])
    has_ou = np.array([odds[r["match_id"]]["mkover"] is not None for r in sub])
    mko = np.array([odds[r["match_id"]]["mkover"] or 0.5 for r in sub])
    out = {"n": len(sub), "n_ou25": int(has_ou.sum()),
           "market_1x2_logloss": round(float(-np.mean(np.log(mk[np.arange(len(k)), k]))), 5),
           "market_ou25_logloss": (round(float(-np.mean(np.where(y, np.log(mko), np.log(1 - mko))[has_ou])), 5)
                                   if has_ou.any() else None), "models": {}}
    for name, pm in preds.items():
        p1x2 = pm["_p1x2"][sel]
        o25 = pm["_o25"][sel]
        res = {"1x2_logloss": round(float(-np.mean(np.log(np.clip(p1x2[np.arange(len(k)), k], 1e-12, 1)))), 5),
               "ou25_logloss": (round(float(-np.mean(np.where(y, np.log(o25), np.log(1 - o25))[has_ou])), 5)
                                if has_ou.any() else None)}
        bets = []
        for i, r in enumerate(sub):
            o = odds[r["match_id"]]
            cands = []
            if o["odds1x2"]:
                cands += [(p1x2[i, j], o["odds1x2"][j], k[i] == j) for j in range(3)]
            if o["oddsou"]:
                cands += [(o25[i], o["oddsou"][0], bool(y[i])), (1 - o25[i], o["oddsou"][1], not bool(y[i]))]
            for p, od, won in cands:
                implied = 1 / od
                if p * od - 1 >= min_ev and p - implied <= 0.08 and p / implied <= 1.5:
                    bets.append(od - 1 if won else -1.0)
        bets = np.array(bets)
        if len(bets):
            rng = np.random.default_rng(seed)
            boots = [rng.choice(bets, len(bets)).mean() for _ in range(n_boot)]
            res["value_bets"] = {"n": int(len(bets)), "roi": round(float(bets.mean()), 4),
                                 "roi_ci90": [round(float(np.percentile(boots, 5)), 4),
                                              round(float(np.percentile(boots, 95)), 4)], "min_ev": min_ev}
        else:
            res["value_bets"] = {"n": 0, "min_ev": min_ev}
        out["models"][name] = res
    return out


# ============================================================================ selection helpers
def val_score(model_pred, rows) -> tuple[float, dict]:
    mh, ma, rho, r = model_pred
    pm = per_match(rows, mh, ma, rho, r)
    return float(pm["score_logloss"].mean()), pm


def choose_l2(train, val, groups, grid, prod) -> tuple[float, bool, list]:
    """L2 strength and the recalibration switch (intercepts + log-lambda scale + refitted rho / NB),
    chosen jointly by validation exact-score log loss."""
    trace = []
    best = None
    for recal in (False, True):
        for l2 in grid:
            m = GLMModel(groups, l2, recal).fit(train, prod["rho"], prod["nb_dispersion"])
            s, pm = val_score(m.predict(val), val)
            trace.append({"recal": recal, "l2": l2, "val_score_logloss": round(s, 5),
                          "val_1x2_logloss": round(float(pm["1x2_logloss"].mean()), 5), "converged": m.converged})
            print(f"  recal={recal!s:5} l2={l2:<8g} val score={s:.5f} 1x2={pm['1x2_logloss'].mean():.5f}", flush=True)
            if best is None or s < best[0] - 1e-7:
                best = (s, l2, recal)
    return best[1], best[2], trace


def backward_elimination(train, val, l2, recal, prod) -> tuple[list[str], list]:
    groups = list(GROUPS)
    cur, _ = val_score(GLMModel(groups, l2, recal).fit(train, prod["rho"], prod["nb_dispersion"]).predict(val), val)
    trace = [{"groups": list(groups), "val_score_logloss": round(cur, 5)}]
    while groups:
        trials = []
        for g in groups:
            gs = [x for x in groups if x != g]
            s, _ = val_score(GLMModel(gs, l2, recal).fit(train, prod["rho"], prod["nb_dispersion"]).predict(val), val)
            trials.append((s, g))
        s, g = min(trials)
        trace.append({"tried": {gg: round(ss, 5) for ss, gg in trials}})
        if s < cur - 1e-6:
            groups.remove(g)
            cur = s
            trace.append({"removed": g, "groups": list(groups), "val_score_logloss": round(cur, 5)})
            print(f"  removed {g}: val score {cur:.5f}", flush=True)
        else:
            break
    return groups, trace


def goal_layer_from_train(train: list[dict]) -> dict:
    """The production goal layer (fit_goal_layer.fit_layer: a, b around m, c = 1, rho, NB dispersion)
    refitted on raw lambdas of the given rows only, for the no-look-ahead baseline
    (config/goal_model.json was fitted on lambda rows that include the validation and test periods)."""
    import fit_goal_layer as FG
    rs = [{"lh": r["lambda_home_raw"], "la": r["lambda_away_raw"], "hs": r["hs"], "as": r["as"]} for r in train
          if r.get("lambda_home_raw") and r.get("lambda_away_raw")]
    p = FG.fit_layer(rs)
    p["n_rows"] = len(rs)
    return p


def apply_goal_layer(rows: list[dict], p: dict) -> list[dict]:
    """Copies of rows whose lambda_home / lambda_away come from raw lambdas through layer p."""
    lh = np.array([r["lambda_home_raw"] for r in rows])
    la = np.array([r["lambda_away_raw"] for r in rows])
    s_ = (np.log(lh) + np.log(la)) / 2
    d = (np.log(lh) - np.log(la)) / 2
    s2 = p["m"] + p["a"] * (s_ - p["m"]) + p["b"]
    out = []
    for r, h, a in zip(rows, np.exp(s2 + d), np.exp(s2 - d)):
        x = dict(r)
        x["lambda_home"], x["lambda_away"] = float(h), float(a)
        out.append(x)
    return out


def hgb_grid(full: bool) -> list[dict]:
    lrs = [0.03, 0.06] if full else [0.05]
    leaves = [4, 8, 16] if full else [4, 8]
    msl = [50, 150] if full else [100]
    l2s = [0.0, 10.0] if full else [1.0]
    return [{"learning_rate": a, "max_leaf_nodes": b, "min_samples_leaf": c, "l2_regularization": d}
            for a in lrs for b in leaves for c in msl for d in l2s]


# ============================================================================ main
def split(rows, train_end, val_end, test_end, start):
    tr = [r for r in rows if (start is None or r["at"] >= start) and r["at"] < train_end]
    va = [r for r in rows if train_end <= r["at"] < val_end]
    te = [r for r in rows if r["at"] >= val_end and (test_end is None or r["at"] < test_end)]
    return tr, va, te


def coverage_counts(rows) -> dict:
    def share(f):
        return round(sum(1 for r in rows if f(r)) / max(len(rows), 1), 4)
    return {"n": len(rows), "first": rows[0]["at"].isoformat() if rows else None,
            "last": rows[-1]["at"].isoformat() if rows else None,
            "euro": sum(1 for r in rows if r.get("comp_is_euro") == 1),
            "share_value": share(lambda r: r.get("value_log_ratio") is not None),
            "share_lineup_form": share(lambda r: r.get("lineup_form") is not None),
            "share_xi_both": share(lambda r: r.get("home_xi_d_off") is not None and r.get("away_xi_d_off") is not None),
            "share_unavail_both": share(lambda r: r.get("home_n_injury") is not None and r.get("away_n_injury") is not None),
            "share_xg_l5_both": share(lambda r: r.get("home_xg_for_l5") is not None and r.get("away_xg_for_l5") is not None)}


def glm_candidate(model: GLMModel, label: str) -> dict:
    d = model.design
    terms = []
    for j, (name, group, kind, col, how) in enumerate(d.terms):
        mu, sd = d.stats[name]
        c = float(model.theta[3 + j])
        terms.append({"name": name, "group": group, "kind": kind, "column": col,
                      "home_equation_source": side_source("home", kind, col),
                      "away_equation_source": side_source("away", kind, col),
                      "transform": f"clip to [{REST_CLIP[0]}, {REST_CLIP[1]}] days" if how == "clip" else None,
                      "mean": round(mu, 6), "sd": round(sd, 6), "coef_per_sd": round(c, 6),
                      "coef_per_unit": round(c / sd, 6), "missing_rule": "missing value -> term 0 (plus indicator)"})
    off = 3 + len(d.terms)
    miss = [{"name": name, "group": group, "kind": kind, "column": col,
             "definition": f"1 when {side_source('home', kind, col)} (home eq.) / {side_source('away', kind, col)} "
                           f"(away eq.) is unknown",
             "coef": round(float(model.theta[off + j]), 6)} for j, (name, group, kind, col) in enumerate(d.missing)]
    return {"label": label, "groups": d.groups, "l2": model.l2, "recalibration_terms": model.recal,
            "formula": "log mu_side = log lambda_side + c_side + alpha_loglam * (log lambda_side - m_loglam) "
                       "+ sum_terms coef_per_sd * (x - mean) / sd + sum_missing coef * indicator; "
                       "lambda_side = walk-forward rating lambda after the production goal layer",
            "c_home": round(float(model.theta[0]), 6), "c_away": round(float(model.theta[1]), 6),
            "alpha_loglam": round(float(model.theta[2]), 6), "m_loglam": round(d.m_loglam, 6),
            "terms": terms, "missing_indicators": miss,
            "score_model": {"family": "negative binomial marginals x Dixon-Coles tau, 0..10 goals, renormalised",
                            "rho": round(model.rho, 6), "nb_dispersion": round(model.r, 4)},
            "converged": model.converged}


def side_source(eq: str, kind: str, col: str) -> str:
    other = "away" if eq == "home" else "home"
    if kind == "att":
        return f"{eq}_{col}"
    if kind == "def":
        return f"{other}_{col}"
    if kind == "signed":
        return col if eq == "home" else f"-{col}"
    return col


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="match model training / evaluation harness (stage B)")
    ap.add_argument("--features", type=Path, default=DATA / "training" / "match_features.csv.gz")
    ap.add_argument("--start", default=None, help="earliest training kickoff (optional)")
    ap.add_argument("--train-end", default="2026-04-01")
    ap.add_argument("--val-end", default="2026-07-01")
    ap.add_argument("--test-end", default=None)
    ap.add_argument("--l2-grid", default="1,10,30,100,300,1000,3000,10000")
    ap.add_argument("--hgb-grid", choices=("small", "full"), default="full")
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20261013)
    ap.add_argument("--min-ev", type=float, default=0.03)
    ap.add_argument("--odds-current", type=Path, default=DATA / "external" / "football_data_matches.csv")
    ap.add_argument("--odds-history", type=Path, default=DATA / "external" / "football_data_history.csv")
    ap.add_argument("--db", type=Path, default=BACKEND_DIR / "football_intelligence.db")
    ap.add_argument("--out", type=Path, default=DATA / "training" / "match_model_report.json")
    ap.add_argument("--candidate", type=Path, default=DATA / "training" / "match_model_candidate.json")
    ap.add_argument("--note", default=None, help="free-text note stored in the report (e.g. run history)")
    args = ap.parse_args(argv)
    t0 = time.time()

    rows = load_rows(args.features)
    start = datetime.fromisoformat(args.start) if args.start else None
    train_end, val_end = datetime.fromisoformat(args.train_end), datetime.fromisoformat(args.val_end)
    test_end = datetime.fromisoformat(args.test_end) if args.test_end else None
    train, val, test = split(rows, train_end, val_end, test_end, start)
    prod = production_params()
    print(f"rows {len(rows)}: train {len(train)}, val {len(val)}, test {len(test)}", flush=True)
    report = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "inputs": {"features": str(args.features), "start": args.start, "train_end": args.train_end,
                         "val_end": args.val_end, "test_end": args.test_end, "seed": args.seed,
                         "bootstrap": args.bootstrap},
              "note": args.note,
              "production_params": prod,
              "splits": {"train": coverage_counts(train), "validation": coverage_counts(val), "test": coverage_counts(test)},
              "selection": {}, "ablations_validation": {}}

    # ---------------------------------------------------------------- validation: (b)
    grid = [float(x) for x in args.l2_grid.split(",")]
    print("(b) L2 grid x recalibration switch on validation, all groups", flush=True)
    l2, recal, l2_trace = choose_l2(train, val, GROUPS, grid, prod)
    report["selection"]["glm_l2"] = {"chosen_l2": l2, "chosen_recal": recal, "trace": l2_trace}
    print(f"(b) chosen l2={l2} recal={recal}; backward elimination of feature groups on validation", flush=True)
    sel_groups, be_trace = backward_elimination(train, val, l2, recal, prod)
    report["selection"]["glm_backward_elimination"] = {"chosen_groups": sel_groups, "trace": be_trace}

    def glm(groups, rows_):
        return GLMModel(groups, l2, recal).fit(rows_, prod["rho"], prod["nb_dispersion"])

    # ---------------------------------------------------------------- ablations (validation only)
    base_val = per_match(val, *baseline_predict(val, prod))
    abl = {"baseline_production": summary(base_val, val)}
    full_m = glm(GROUPS, train)
    full_val = per_match(val, *full_m.predict(val))
    nof_m = glm([], train)
    nof_val = per_match(val, *nof_m.predict(val))
    abl["glm_no_features"] = {**summary(nof_val, val), "coefficients": nof_m.coefficients(),
                              "vs_baseline": bootstrap_diff(nof_val, base_val, args.bootstrap, args.seed)}
    abl["glm_full"] = {**summary(full_val, val), "coefficients": full_m.coefficients(),
                       "vs_no_features": bootstrap_diff(full_val, nof_val, args.bootstrap, args.seed),
                       "vs_baseline": bootstrap_diff(full_val, base_val, args.bootstrap, args.seed)}
    for g in GROUPS:
        m_only = glm([g], train)
        pm_only = per_match(val, *m_only.predict(val))
        m_wo = glm([x for x in GROUPS if x != g], train)
        pm_wo = per_match(val, *m_wo.predict(val))
        abl[f"glm_only_{g}"] = {**summary(pm_only, val), "coefficients": m_only.coefficients(),
                                "vs_no_features": bootstrap_diff(pm_only, nof_val, args.bootstrap, args.seed)}
        abl[f"glm_full_without_{g}"] = {**summary(pm_wo, val),
                                        "vs_full": bootstrap_diff(pm_wo, full_val, args.bootstrap, args.seed)}
        print(f"  ablation {g}: only {abl[f'glm_only_{g}']['score_logloss']:.5f}  without "
              f"{abl[f'glm_full_without_{g}']['score_logloss']:.5f}  (full {abl['glm_full']['score_logloss']:.5f}, "
              f"no features {abl['glm_no_features']['score_logloss']:.5f})", flush=True)
    report["ablations_validation"]["glm"] = abl

    # ---------------------------------------------------------------- validation: (c)
    print("(c) HGB grid on validation", flush=True)
    hgb_trace = []
    best = None
    for structure in ("stacked", "separate"):
        for params in hgb_grid(args.hgb_grid == "full"):
            m = HGBModel(params, GROUPS, structure).fit(train, val)
            mh, ma = m.predict_mu(val)
            s, pm = val_score((mh, ma, prod["rho"], prod["nb_dispersion"]), val)
            hgb_trace.append({"structure": structure, **params, "n_iter": m.n_iter, "val_score_logloss": round(s, 5),
                              "val_1x2_logloss": round(float(pm["1x2_logloss"].mean()), 5)})
            if best is None or s < best[0] - 1e-7:
                best = (s, structure, params, dict(m.n_iter))
    print(f"  best HGB: {best}", flush=True)
    _s, hgb_structure, hgb_params, hgb_iter = best
    hgb_val_model = HGBModel(hgb_params, GROUPS, hgb_structure).fit(train, val)
    mh, ma = hgb_val_model.predict_mu(val)
    vh, va_ = np.array([r["hs"] for r in val]), np.array([r["as"] for r in val])
    hgb_rho, hgb_r = fit_score_params(mh, ma, vh, va_, prod["rho"], prod["nb_dispersion"])
    hgb_val_pm = per_match(val, mh, ma, hgb_rho, hgb_r)
    report["selection"]["hgb"] = {"chosen": {"structure": hgb_structure, **hgb_params, "n_iter": hgb_iter,
                                             "rho_fitted_on_validation": round(hgb_rho, 5),
                                             "nb_dispersion_fitted_on_validation": round(hgb_r, 3)},
                                  "trace": hgb_trace}
    habl = {"hgb_full": {**summary(hgb_val_pm, val), "vs_baseline": bootstrap_diff(hgb_val_pm, base_val, args.bootstrap, args.seed)}}
    for g in GROUPS:
        m = HGBModel(hgb_params, [x for x in GROUPS if x != g], hgb_structure).fit(train, val)
        a, b = m.predict_mu(val)
        pm = per_match(val, a, b, hgb_rho, hgb_r)
        habl[f"hgb_full-{g}"] = {**summary(pm, val), "n_iter": m.n_iter,
                                 "vs_hgb_full": bootstrap_diff(pm, hgb_val_pm, args.bootstrap, args.seed)}
        print(f"  HGB without {g}: {habl[f'hgb_full-{g}']['score_logloss']:.5f} (full {habl['hgb_full']['score_logloss']:.5f})", flush=True)
    report["ablations_validation"]["hgb"] = habl

    # ---------------------------------------------------------------- refit on train + validation, score test ONCE
    trval = train + val
    final = {"glm_no_features": glm([], trval), "glm_full": glm(GROUPS, trval), "glm_selected": glm(sel_groups, trval)}
    hgb_final = HGBModel(hgb_params, GROUPS, hgb_structure).fit(trval, n_iter=hgb_iter)
    hgb_final.rho, hgb_final.r = hgb_rho, hgb_r
    # no-look-ahead variant of the baseline: goal layer refitted on train + validation rows only
    gl_tv = goal_layer_from_train(trval)
    report["goal_layer_train_validation_only"] = gl_tv
    preds = {}
    test_report = {}
    if test:
        preds["baseline_production"] = per_match(test, *baseline_predict(test, prod))
        prod_tv = dict(prod, rho=gl_tv["rho"], nb_dispersion=gl_tv["nb_dispersion"])
        preds["baseline_goal_layer_refit_no_lookahead"] = per_match(
            test, *baseline_predict(apply_goal_layer(test, gl_tv), prod_tv))
        for name, m in final.items():
            preds[name] = per_match(test, *m.predict(test))
        preds["hgb"] = per_match(test, *hgb_final.predict(test))
        base = preds["baseline_production"]
        for name, pm in preds.items():
            entry = {"all": summary(pm, test)}
            if name != "baseline_production":
                entry["vs_baseline"] = bootstrap_diff(pm, base, args.bootstrap, args.seed)
            for ct in ("league", "european"):
                idx = [i for i, r in enumerate(test) if (r.get("comp_is_euro") == 1) == (ct == "european")]
                if len(idx) >= 30:
                    sub = {k: v[idx] for k, v in pm.items()}
                    entry[ct] = summary(sub, [test[i] for i in idx])
                    if name != "baseline_production":
                        bsub = {k: v[idx] for k, v in base.items()}
                        entry[f"{ct}_vs_baseline"] = bootstrap_diff(sub, bsub, args.bootstrap, args.seed)
            entry["calibration"] = calibration(pm)
            test_report[name] = entry
            print(f"TEST {name:40s} " + " ".join(f"{k}={entry['all'][k]:.4f}" for k in METRICS), flush=True)
        odds = load_odds(args.odds_current, args.odds_history, args.db)
        report["test_market"] = market_eval(test, preds, odds, args.min_ev, args.bootstrap, args.seed)
        print("market:", json.dumps({k: v for k, v in report["test_market"].items() if k != "models"}), flush=True)
    report["test"] = test_report
    report["final_models"] = {name: {"coefficients": m.coefficients(), "rho": m.rho, "nb_dispersion": m.r,
                                     "converged": m.converged, "groups": m.design.groups, "l2": l2, "recal": recal}
                              for name, m in final.items()}
    report["final_models"]["hgb"] = {"structure": hgb_structure, **hgb_params, "n_iter": hgb_iter,
                                     "rho": hgb_rho, "nb_dispersion": hgb_r, "features": hgb_final.names,
                                     "monotonic": {k: v for k, v in HGB_MONOTONE.items() if k in hgb_final.names}}

    # ---------------------------------------------------------------- candidate config draft (not production)
    all_rows = train + val + test
    refit_all = glm(sel_groups, all_rows)
    cand = {
        "status": "DRAFT - not wired into production; written by scripts/training/train_match_model.py",
        "built_at": report["built_at"],
        "features_file": str(args.features),
        "feature_definitions": "data/training/README_match_features.md (columns), build_match_features.py (code)",
        "chosen_by": "validation exact-score log loss (L2 grid x recalibration switch, backward elimination of "
                     "feature groups)",
        "l2": l2, "recalibration_terms": recal,
        "splits": report["inputs"],
        "evaluated_model": glm_candidate(final["glm_selected"], "fitted on train + validation, scored once on test"),
        "refit_all_rows": glm_candidate(refit_all, f"same specification refitted on all {len(all_rows)} rows "
                                                   "(for production use after review; not evaluated)"),
        "test_result": {k: test_report[k]["all"] for k in ("baseline_production", "glm_selected")} if test else None,
        "test_vs_baseline": test_report.get("glm_selected", {}).get("vs_baseline"),
        "baseline_definition": prod,
    }
    report["seconds"] = round(time.time() - t0, 1)
    for path, obj in ((args.out, report), (args.candidate, cand)):
        tmp = path.with_name(path.name + f".tmp{os.getpid()}")
        tmp.write_text(json.dumps(obj, indent=1, default=float), encoding="utf-8")
        os.replace(tmp, path)
    print(f"-> {args.out}, {args.candidate} ({report['seconds']} s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
