"""Candidate calibration fixes for the production 1X2 probabilities (2026-10-14), their fitters and one
`apply_fix` entry point used by the select / evaluate stages, the candidate JSON and the unit test.

All fixes act on the production 1X2 probabilities p = (home, draw, away) of one match; nothing else changes
(goal markets are not touched; the ratio shrink keeps the expected total goals).

  temperature   p'_i  proportional to  p_i ** (1 / T)       T > 1 flattens, T < 1 sharpens, T = 1 identity.
                scope "all": one T for every match; scope "split": T_league for league matches and T_uefa for
                UEFA matches; scope "uefa": T_uefa for UEFA matches, league matches unchanged.
  ratio_shrink  UEFA matches only. d = ln(mu_home / mu_away); d' = k * d + h; the total mu_home + mu_away is
                kept: mu_home' = total * e^d' / (1 + e^d'), mu_away' = total / (1 + e^d'); the 1X2 probabilities
                are recomputed with the production score model (negative binomial x Dixon-Coles, scores 0..10).
                k < 1 pulls the two sides together, h > 0 adds home advantage (log-ratio units).
  fav_platt     favourite = the outcome with the largest probability, q = its probability.
                logit(q') = a + b * logit(q); the other two outcomes keep their ratio:
                p'_j = p_j * (1 - q') / (1 - q).  scope "all" or "uefa" (UEFA matches only).
  team_offset   UEFA matches only (round 2, candidate (d)). z = offset_home - offset_away, where a club's offset is the
                shrunk mean of (actual - model-expected) goal (or xG) difference over its PREVIOUS UEFA matches
                (calibration_offset.py). d' = d + h + gamma * z, total goals kept, 1X2 recomputed as for ratio_shrink.
  fav_isotonic  q' = isotonic(q) (monotone step function fitted on the fitting rows), the other two outcomes
                rescaled as above; scope "all". Comparator only (many degrees of freedom).

Fitters minimise the 1X2 log loss of the fitting rows (for fav_platt / fav_isotonic that equals the binary
log loss of "favourite won" plus a constant, so the binary fit is exact).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.optimize import minimize, minimize_scalar

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calibration_common as C  # noqa: E402

EPS = 1e-12


# ------------------------------------------------------------------------------------------ primitives
def renorm_log(logp: np.ndarray) -> np.ndarray:
    z = logp - logp.max(1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


def temperature(p: np.ndarray, T) -> np.ndarray:
    """p_i ** (1/T), renormalised; T may be a scalar or a per-row array."""
    T = np.asarray(T, float)
    if T.ndim == 0:
        T = np.full(len(p), float(T))
    return renorm_log(np.log(np.clip(p, EPS, 1.0)) / T[:, None])


def logit(q):
    q = np.clip(q, 1e-9, 1 - 1e-9)
    return np.log(q / (1 - q))


def inv_logit(z):
    return 1.0 / (1.0 + np.exp(-z))


def set_favourite(p: np.ndarray, q_new: np.ndarray) -> np.ndarray:
    """Replace the favourite's probability by q_new; the other two outcomes keep their ratio."""
    fav = p.argmax(1)
    q = p[np.arange(len(p)), fav]
    out = p * ((1.0 - q_new) / np.clip(1.0 - q, EPS, None))[:, None]
    out[np.arange(len(p)), fav] = q_new
    return out


def fav_platt(p: np.ndarray, a: float, b: float) -> np.ndarray:
    q = p.max(1)
    return set_favourite(p, np.clip(inv_logit(a + b * logit(q)), 1e-6, 1 - 1e-6))


def fav_isotonic(p: np.ndarray, xs, ys) -> np.ndarray:
    q = p.max(1)
    q_new = np.interp(q, np.asarray(xs, float), np.asarray(ys, float))
    return set_favourite(p, np.clip(q_new, 1e-6, 1 - 1e-6))


def ratio_shrink_mu(mu_h: np.ndarray, mu_a: np.ndarray, k: float, h: float) -> tuple[np.ndarray, np.ndarray]:
    d = np.log(mu_h) - np.log(mu_a)
    d2 = k * d + h
    tot = mu_h + mu_a
    w = inv_logit(d2)
    return tot * w, tot * (1.0 - w)


def ratio_shrink(p: np.ndarray, mu_h: np.ndarray, mu_a: np.ndarray, euro: np.ndarray, k: float, h: float,
                 layer: dict) -> np.ndarray:
    """1X2 after the ratio shrink for UEFA matches (euro True); other rows keep p."""
    out = p.copy()
    if euro.any():
        m2h, m2a = ratio_shrink_mu(mu_h[euro], mu_a[euro], k, h)
        out[euro] = C.p1x2_from_mu(m2h, m2a, layer)
    return out


# ------------------------------------------------------------------------------------------ apply
def apply_fix(fix: dict, p: np.ndarray, mu_h: np.ndarray, mu_a: np.ndarray, euro: np.ndarray,
              layer: dict, z: Optional[np.ndarray] = None) -> np.ndarray:
    """Calibrated 1X2 probabilities for the rows given. ``fix`` is a candidate-spec dict (see module doc);
    ``z`` (one value per row; only the UEFA rows are read) is needed by kind "team_offset"."""
    kind = fix["kind"]
    if kind == "identity":
        return p.copy()
    if kind == "team_offset":
        if z is None:
            raise ValueError("team_offset needs z (home offset - away offset) per row")
        out = p.copy()
        if euro.any():
            d = np.log(mu_h[euro]) - np.log(mu_a[euro]) + fix.get("h", 0.0) + fix["gamma"] * np.asarray(z)[euro]
            tot = mu_h[euro] + mu_a[euro]
            w = inv_logit(d)
            out[euro] = C.p1x2_from_mu(tot * w, tot * (1.0 - w), layer)
        return out
    if kind == "temperature":
        scope = fix["scope"]
        if scope == "all":
            return temperature(p, fix["T"])
        if scope == "split":
            T = np.where(euro, fix["T_uefa"], fix["T_league"])
            return temperature(p, T)
        if scope == "uefa":
            out = p.copy()
            if euro.any():
                out[euro] = temperature(p[euro], fix["T_uefa"])
            return out
        raise ValueError(scope)
    if kind == "ratio_shrink":
        return ratio_shrink(p, mu_h, mu_a, euro, fix["k"], fix["h"], layer)
    if kind in ("fav_platt", "fav_isotonic"):
        def one(pp):
            return fav_platt(pp, fix["a"], fix["b"]) if kind == "fav_platt" else fav_isotonic(pp, fix["x"], fix["y"])
        if fix["scope"] == "all":
            return one(p)
        out = p.copy()
        if euro.any():
            out[euro] = one(p[euro])
        return out
    raise ValueError(kind)


# ------------------------------------------------------------------------------------------ fitters
def fit_temperature(p: np.ndarray, y: np.ndarray, lo: float = 0.5, hi: float = 2.0) -> float:
    r = minimize_scalar(lambda T: C.logloss(temperature(p, T), y).mean(), bounds=(lo, hi), method="bounded",
                        options={"xatol": 1e-6})
    return float(r.x)


def fit_ratio_shrink(p: np.ndarray, mu_h: np.ndarray, mu_a: np.ndarray, y: np.ndarray, layer: dict,
                     free_k: bool, free_h: bool) -> dict:
    """Fit (k, h) of the ratio shrink on UEFA rows (``p`` unused except for the row count; all rows are UEFA)."""
    def loss(th):
        k = th[0] if free_k else 1.0
        h = th[-1] if free_h else 0.0
        m2h, m2a = ratio_shrink_mu(mu_h, mu_a, k, h)
        return float(C.logloss(C.p1x2_from_mu(m2h, m2a, layer), y).mean())
    x0 = [1.0] * free_k + [0.0] * free_h
    if len(x0) == 1:
        lo, hi = (0.3, 1.7) if free_k else (-1.0, 1.0)
        r = minimize_scalar(lambda t: loss([t]), bounds=(lo, hi), method="bounded", options={"xatol": 1e-5})
        th = [float(r.x)]
    else:
        r = minimize(loss, x0, method="Nelder-Mead", options={"xatol": 1e-5, "fatol": 1e-9, "maxiter": 400})
        th = [float(v) for v in r.x]
    return {"k": th[0] if free_k else 1.0, "h": th[-1] if free_h else 0.0}


def fit_offset(mu_h: np.ndarray, mu_a: np.ndarray, z: np.ndarray, y: np.ndarray, layer: dict,
               free_h: bool) -> dict:
    """gamma (and h when free_h) of d' = d + h + gamma * z on UEFA rows, by 1X2 log loss."""
    d0 = np.log(mu_h) - np.log(mu_a)
    tot = mu_h + mu_a

    def loss(th):
        g = th[0]
        h = th[1] if free_h else 0.0
        w = inv_logit(d0 + h + g * z)
        return float(C.logloss(C.p1x2_from_mu(tot * w, tot * (1.0 - w), layer), y).mean())
    if free_h:
        r = minimize(loss, [0.0, 0.0], method="Nelder-Mead", options={"xatol": 1e-5, "fatol": 1e-9, "maxiter": 400})
        return {"gamma": float(r.x[0]), "h": float(r.x[1])}
    r = minimize_scalar(lambda g: loss([g]), bounds=(-1.0, 4.0), method="bounded", options={"xatol": 1e-5})
    return {"gamma": float(r.x), "h": 0.0}


def fit_platt_fav(p: np.ndarray, y: np.ndarray) -> dict:
    """a, b of logit(q') = a + b logit(q) on the favourite's win indicator (= exact 1X2 log-loss fit)."""
    q = p.max(1)
    hit = (p.argmax(1) == y).astype(float)
    x = logit(q)

    def nll(th):
        z = th[0] + th[1] * x
        # numerically stable binary log loss
        return float(np.mean(np.logaddexp(0, z) - hit * z))

    def grad(th):
        mu = inv_logit(th[0] + th[1] * x)
        r = mu - hit
        return np.array([r.mean(), (r * x).mean()])

    r = minimize(nll, [0.0, 1.0], jac=grad, method="L-BFGS-B")
    return {"a": float(r.x[0]), "b": float(r.x[1])}


def fit_isotonic_fav(p: np.ndarray, y: np.ndarray) -> dict:
    from sklearn.isotonic import IsotonicRegression
    q = p.max(1)
    hit = (p.argmax(1) == y).astype(float)
    ir = IsotonicRegression(y_min=1e-4, y_max=1 - 1e-4, increasing=True, out_of_bounds="clip")
    ir.fit(q, hit)
    xs = np.asarray(ir.X_thresholds_, float)
    ys = np.asarray(ir.y_thresholds_, float)
    return {"x": [float(v) for v in xs], "y": [float(v) for v in ys]}


def n_params(fix: dict) -> int:
    k = fix["kind"]
    if k == "identity":
        return 0
    if k == "temperature":
        return 2 if fix["scope"] == "split" else 1
    if k == "ratio_shrink":
        return (1 if fix.get("free_k", True) else 0) + (1 if fix.get("free_h", False) else 0)
    if k == "team_offset":   # gamma (+ h) and the tuned hyper-parameters: shrinkage k, half-life on/off, metric
        return 1 + (1 if fix.get("free_h") else 0) + 3
    if k == "fav_platt":
        return 2
    if k == "fav_isotonic":
        return len(fix["x"])
    raise ValueError(k)
