"""Props count models (props:train, 2026-10-14): negative-binomial models for yellow cards, corners, total shots,
shots on target (and fouls) with team attack / concede effects, competition-season level, home advantage and an
optional referee effect; time-decayed, ridge-penalised, refitted walk-forward; plus the simple-average baselines.

Model for one stat (log link, one observation per team side of a match):
    ln mu_home = b0 + h + L[comp, season] + A[home team] + D[away team] (+ R[referee])
    ln mu_away = b0     + L[comp, season] + A[away team] + D[home team] (+ R[referee])
    count ~ NegativeBinomial(mean mu, size r)          (var = mu + mu^2 / r; r fitted per stat)
Weights: 0.5 ** ((fit date - kick-off) / half_life_days).  Penalties: 0.5 * lam_att |A|^2 + 0.5 * lam_con |D|^2
+ 0.5 * lam_ref |R|^2 + 0.5 * lam_level * sum over consecutive seasons of a competition (L_k - L_{k-1})^2
(level mode "season"; one L per competition when the level penalty is off) + a tiny anchor ridge on L.
Everything is fitted by L-BFGS-B with the analytic gradient (value, gradient and size r in one vector).

No numbers are invented: a match whose stat FotMob did not send is not in that stat's fit / evaluation.
"""

from __future__ import annotations

import csv
import gzip
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
from scipy import sparse
from scipy.optimize import minimize, minimize_scalar
from scipy.special import betainc, digamma, gammaln

TRAINING_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TRAINING_DIR.parents[1]
DATA = BACKEND_DIR / "data" / "training"
DATASET_PATH = DATA / "props_match_stats.csv.gz"

STATS = ["yellow_cards", "corners", "total_shots", "shots_on_target", "fouls"]
REF_STATS = ("yellow_cards", "fouls")  # stats that may use a referee effect
EUROPEAN = {42, 73, 10216}

# market -> (stat, kind, lines).  kind: "team" (each side separately) or "total" (sum of the two sides)
MARKETS: dict[str, tuple[str, str, list[float]]] = {
    "total_yellow_cards": ("yellow_cards", "total", [2.5, 3.5, 4.5, 5.5]),
    "team_yellow_cards": ("yellow_cards", "team", [0.5, 1.5, 2.5]),
    "total_corners": ("corners", "total", [7.5, 8.5, 9.5, 10.5, 11.5]),
    "team_corners": ("corners", "team", [2.5, 3.5, 4.5, 5.5, 6.5]),
    "team_shots": ("total_shots", "team", [7.5, 9.5, 11.5, 13.5, 15.5]),
    "total_shots": ("total_shots", "total", [19.5, 21.5, 23.5, 25.5]),
    "team_shots_on_target": ("shots_on_target", "team", [2.5, 3.5, 4.5, 5.5]),
    "total_shots_on_target": ("shots_on_target", "total", [6.5, 7.5, 8.5, 9.5]),
}
# not part of the exported "lines"; evaluated separately because the specified lines of some markets sit in
# the lower tail (mean total shots ~ 26)
EXTRA_MARKETS: dict[str, tuple[str, str, list[float]]] = {
    "total_shots_high": ("total_shots", "total", [27.5, 29.5, 31.5]),
    "team_shots_high": ("total_shots", "team", [17.5, 19.5]),
    "total_corners_high": ("corners", "total", [12.5, 13.5]),
    "team_yellow_cards_high": ("yellow_cards", "team", [3.5]),
    "total_yellow_cards_low": ("yellow_cards", "total", [1.5, 6.5]),
    "total_fouls": ("fouls", "total", [20.5, 22.5, 24.5, 26.5, 28.5]),
    "team_fouls": ("fouls", "team", [9.5, 10.5, 11.5, 12.5, 13.5, 14.5]),
}
SHOTS_BREAK_COMP = 122  # Czech 1. Liga: before 2025-07-01 FotMob's total_shots has a different definition
SHOTS_BREAK_DATE = "2025-07-01"
TRAIN_END_MARGIN_DAYS = 0.125  # a match is used for a fit / baseline only if it kicked off >= 3 h before the cut
EPOCH = np.datetime64("1970-01-01T00:00:00")


# --------------------------------------------------------------------------------------------- dataset
@dataclass
class Dataset:
    """All matches sorted by kick-off. y[stat] is (n, 2) float (home, away) with NaN = not sent (missing)."""

    match_id: np.ndarray
    kick: np.ndarray  # datetime64[s]
    t: np.ndarray  # float days since 1970-01-01
    comp: np.ndarray
    season_key: np.ndarray
    home_id: np.ndarray
    away_id: np.ndarray
    referee: np.ndarray  # object ("" = not sent)
    y: dict
    valid: dict
    team_ids: np.ndarray = None
    home_idx: np.ndarray = None
    away_idx: np.ndarray = None
    comp_ids: np.ndarray = None
    comp_idx: np.ndarray = None
    level_keys: list = None
    level_idx: np.ndarray = None
    ref_names: list = None
    ref_idx: np.ndarray = None
    excluded: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.match_id)

    def day(self, iso: str) -> float:
        return float((np.datetime64(iso[:19]) - EPOCH) / np.timedelta64(1, "D"))


def _float_or_nan(v: str) -> float:
    return float("nan") if v in ("", None) else float(v)


def dataset_from_rows(rows: Iterable[dict]) -> Dataset:
    """rows: dicts with the CSV columns of props_build_dataset.py (strings or numbers)."""
    rows = sorted(rows, key=lambda r: (str(r["kickoff"]), str(r["match_id"])))
    n = len(rows)
    kick = np.array([str(r["kickoff"])[:19] for r in rows], dtype="datetime64[s]")
    t = (kick - EPOCH) / np.timedelta64(1, "D")
    years = kick.astype("datetime64[Y]").astype(int) + 1970
    months = kick.astype("datetime64[M]").astype(int) % 12 + 1
    season_key = np.where(months >= 7, years, years - 1).astype(int)
    comp = np.array([int(r["competition_id"]) for r in rows])
    home_id = np.array([int(r["home_team_id"]) for r in rows])
    away_id = np.array([int(r["away_team_id"]) for r in rows])
    referee = np.array([str(r.get("referee") or "") for r in rows], dtype=object)
    y, valid = {}, {}
    excluded: dict = {}
    for s in STATS:
        h = np.array([_float_or_nan(r.get(f"home_{s}", "")) for r in rows])
        a = np.array([_float_or_nan(r.get(f"away_{s}", "")) for r in rows])
        arr = np.stack([h, a], axis=1)
        ok = ~np.isnan(arr).any(axis=1)
        excluded[f"{s}_missing"] = int((~ok).sum())
        if s == "total_shots":  # structural break: different definition (excl. blocked shots), see report
            brk = (comp == SHOTS_BREAK_COMP) & (kick < np.datetime64(SHOTS_BREAK_DATE))
            excluded["total_shots_czech_pre_2025_07"] = int((ok & brk).sum())
            ok = ok & ~brk
        y[s] = arr
        valid[s] = ok
    ds = Dataset(np.array([str(r["match_id"]) for r in rows]), kick, np.asarray(t, dtype=float), comp, season_key,
                 home_id, away_id, referee, y, valid, excluded=excluded)
    _index(ds)
    return ds


def _index(ds: Dataset) -> None:
    ds.team_ids = np.unique(np.concatenate([ds.home_id, ds.away_id]))
    lookup = {int(x): i for i, x in enumerate(ds.team_ids)}
    ds.home_idx = np.array([lookup[int(x)] for x in ds.home_id], dtype=int)
    ds.away_idx = np.array([lookup[int(x)] for x in ds.away_id], dtype=int)
    ds.comp_ids = np.unique(ds.comp)
    cl = {int(x): i for i, x in enumerate(ds.comp_ids)}
    ds.comp_idx = np.array([cl[int(x)] for x in ds.comp], dtype=int)
    keys = sorted({(int(c), int(k)) for c, k in zip(ds.comp, ds.season_key)})
    ds.level_keys = keys
    kl = {k: i for i, k in enumerate(keys)}
    ds.level_idx = np.array([kl[(int(c), int(k))] for c, k in zip(ds.comp, ds.season_key)], dtype=int)
    names = sorted({str(x) for x in ds.referee if x})
    ds.ref_names = names
    rl = {x: i for i, x in enumerate(names)}
    ds.ref_idx = np.array([rl.get(str(x), -1) for x in ds.referee], dtype=int)


def load_dataset(path: Path = DATASET_PATH) -> Dataset:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return dataset_from_rows(rows)


# --------------------------------------------------------------------------------------------- design / fit
@dataclass
class Design:
    """Sparse design of one stat for the valid matches (two rows per match: home side = 2k, away side = 2k+1)."""

    stat: str
    X: sparse.csr_matrix
    y: np.ndarray  # (2m,)
    t_obs: np.ndarray  # (2m,) days
    rows: np.ndarray  # (m,) dataset row of each match
    t_match: np.ndarray  # (m,)
    level_mode: bool
    use_ref: bool
    use_attack: bool
    use_concede: bool
    use_dom: bool
    sl: dict  # name -> slice of theta
    p: int
    Q: sparse.csr_matrix  # random-walk matrix of the level block (p x p)


def build_design(ds: Dataset, stat: str, level: bool = False, ref: bool = False, attack: bool = True,
                 concede: bool = True, dom: bool = False) -> Design:
    rows = np.flatnonzero(ds.valid[stat])
    m = len(rows)
    nT = len(ds.team_ids)
    nL = len(ds.level_keys) if level else len(ds.comp_ids)
    nR = len(ds.ref_names) if ref else 0
    sl, pos = {}, 0
    for name, size in (("b0", 1), ("h", 1), ("L", nL), ("A", nT if attack else 0), ("D", nT if concede else 0),
                       ("R", nR), ("S", nT if dom else 0)):
        sl[name] = slice(pos, pos + size)
        pos += size
    p = pos
    r_idx = np.arange(2 * m)
    hr, ar = 2 * np.arange(m), 2 * np.arange(m) + 1
    lev = (ds.level_idx if level else ds.comp_idx)[rows]
    cols, rws = [], []

    def add(rr, cc):
        rws.append(rr)
        cols.append(cc)

    add(r_idx, np.zeros(2 * m, dtype=int))  # b0
    add(hr, np.full(m, 1))  # h (home side only)
    add(hr, sl["L"].start + lev)
    add(ar, sl["L"].start + lev)
    if attack:
        add(hr, sl["A"].start + ds.home_idx[rows])
        add(ar, sl["A"].start + ds.away_idx[rows])
    if concede:
        add(hr, sl["D"].start + ds.away_idx[rows])
        add(ar, sl["D"].start + ds.home_idx[rows])
    if ref:
        rf = ds.ref_idx[rows]
        has = rf >= 0
        add(hr[has], sl["R"].start + rf[has])
        add(ar[has], sl["R"].start + rf[has])
    vals = [np.ones(len(r_)) for r_ in rws]
    if dom:  # dominance: +S[own team] - S[opponent] (zero-sum between the two sides of a match)
        add(hr, sl["S"].start + ds.home_idx[rows])
        vals.append(np.ones(m))
        add(hr, sl["S"].start + ds.away_idx[rows])
        vals.append(-np.ones(m))
        add(ar, sl["S"].start + ds.away_idx[rows])
        vals.append(np.ones(m))
        add(ar, sl["S"].start + ds.home_idx[rows])
        vals.append(-np.ones(m))
    ri, ci, vv = np.concatenate(rws), np.concatenate(cols), np.concatenate(vals)
    X = sparse.csr_matrix((vv, (ri, ci)), shape=(2 * m, p))
    yy = np.empty(2 * m)
    yy[0::2] = ds.y[stat][rows, 0]
    yy[1::2] = ds.y[stat][rows, 1]
    t_obs = np.repeat(ds.t[rows], 2)
    # random-walk penalty matrix across consecutive seasons of one competition (only in level mode)
    Q = sparse.lil_matrix((p, p))
    if level:
        by_comp: dict[int, list[tuple[int, int]]] = {}
        for i, (c, k) in enumerate(ds.level_keys):
            by_comp.setdefault(c, []).append((k, i))
        base = sl["L"].start
        for lst in by_comp.values():
            lst.sort()
            for (_, i0), (_, i1) in zip(lst[:-1], lst[1:]):
                a, b = base + i0, base + i1
                Q[a, a] += 1.0
                Q[b, b] += 1.0
                Q[a, b] -= 1.0
                Q[b, a] -= 1.0
    return Design(stat, X, yy, t_obs, rows, ds.t[rows], level, ref, attack, concede, dom, sl, p, Q.tocsr())


@dataclass
class Config:
    half_life: float = 365.0  # days; use 1e9 for "no decay"
    lam_team: float = 30.0  # ridge on attack
    con_mult: float = 1.0  # lam_concede = con_mult * lam_team
    lam_ref: float = 20.0
    lam_level: float = 1e4
    use_level: bool = False
    use_ref: bool = False
    use_attack: bool = True
    use_concede: bool = True
    use_dom: bool = False
    lam_dom: float = 30.0

    def key(self) -> tuple:
        return (self.use_level, self.use_ref, self.use_attack, self.use_concede, self.use_dom)


ANCHOR = 1e-3  # tiny ridge on the level block (fixes the gauge against the intercept)
LOGR_BOUNDS = (math.log(0.5), math.log(5000.0))


def penalty_matrix(des: Design, cfg: Config) -> sparse.csr_matrix:
    lam = np.zeros(des.p)
    lam[des.sl["L"]] = ANCHOR
    lam[des.sl["A"]] = cfg.lam_team
    lam[des.sl["D"]] = cfg.lam_team * cfg.con_mult
    lam[des.sl["R"]] = cfg.lam_ref
    lam[des.sl["S"]] = cfg.lam_dom
    P = sparse.diags(lam).tocsr()
    if des.level_mode:
        P = P + cfg.lam_level * des.Q
    return P.tocsr()


def nb_loglik(y: np.ndarray, mu: np.ndarray, r: float) -> np.ndarray:
    return (y * np.log(mu / (mu + r)) + r * np.log(r / (mu + r)) + gammaln(y + r) - gammaln(r) - gammaln(y + 1.0))


def nb_objective(z: np.ndarray, X, XT, y: np.ndarray, w: np.ndarray, P, W: float, fit_r: bool = True):
    """(value, gradient) of the penalised weighted NB negative log-likelihood divided by the total weight W.
    z = [theta, ln r]."""
    theta, lr = z[:-1], z[-1]
    r = math.exp(lr)
    eta = np.clip(X @ theta, -12.0, 8.0)
    mu = np.exp(eta)
    ll = nb_loglik(y, mu, r)
    Pt = P @ theta
    f = (-(w * ll).sum() + 0.5 * float(theta @ Pt)) / W
    g_eta = w * r * (y - mu) / (mu + r)
    g = (-(XT @ g_eta) + Pt) / W
    if fit_r:
        dll_dr = digamma(y + r) - digamma(r) + np.log(r / (mu + r)) + (mu - y) / (mu + r)
        g_lr = -float((w * dll_dr).sum()) * r / W
    else:
        g_lr = 0.0
    return f, np.concatenate([g, [g_lr]])


@dataclass
class Fit:
    theta: np.ndarray
    logr: float
    nll: float
    iters: int
    converged: bool

    @property
    def r(self) -> float:
        return float(math.exp(self.logr))


def fit_nb(des: Design, n_match: int, w_match_obs: np.ndarray, P: sparse.csr_matrix,
           theta0: Optional[np.ndarray] = None, logr0: Optional[float] = None, maxiter: int = 400,
           fit_r: bool = True) -> Fit:
    """Penalised weighted NB maximum likelihood on the first n_match matches of the design.

    w_match_obs: weights of the 2*n_match observation rows.
    """
    m2 = 2 * n_match
    X = des.X[:m2]
    y = des.y[:m2]
    w = w_match_obs
    W = float(w.sum())
    if W <= 0:
        raise ValueError("no weight")
    if theta0 is None:
        theta0 = np.zeros(des.p)
        theta0[0] = math.log(max(float((w * y).sum() / W), 1e-3))
    z0 = np.concatenate([theta0, [logr0 if logr0 is not None else math.log(10.0)]])
    XT = X.T.tocsr()

    def fg(z):
        return nb_objective(z, X, XT, y, w, P, W, fit_r)

    bounds = [(None, None)] * des.p + [LOGR_BOUNDS if fit_r else (z0[-1], z0[-1])]
    res = minimize(fg, z0, jac=True, method="L-BFGS-B", bounds=bounds,
                   options={"maxiter": maxiter, "maxfun": maxiter * 2, "ftol": 1e-12, "gtol": 1e-7})
    return Fit(res.x[:-1], float(res.x[-1]), float(res.fun * W), int(res.nit), bool(res.success))


def decay_weights(t_obs: np.ndarray, t_fit: float, half_life: float) -> np.ndarray:
    return np.power(0.5, np.maximum(t_fit - t_obs, 0.0) / half_life)


@dataclass
class WalkForward:
    """Predictions for dataset rows (in time order) from refits every `step` days."""

    rows: np.ndarray  # dataset rows
    mu_h: np.ndarray
    mu_a: np.ndarray
    r: np.ndarray
    fit_date: np.ndarray  # fit date of each prediction (days)
    n_fits: int
    last_fit: Optional[Fit] = None
    nonconverged: int = 0


def walk_forward(ds: Dataset, des: Design, cfg: Config, start: float, end: float, step: float = 14.0,
                 maxiter: int = 400) -> WalkForward:
    """Refit every `step` days from `start` (days since epoch); predict the matches in [fit date, fit date + step)
    from a fit that used only matches that kicked off before fit date - 3 h."""
    P = penalty_matrix(des, cfg)
    tm = des.t_match
    out_rows, out_mu_h, out_mu_a, out_r, out_fd = [], [], [], [], []
    theta, logr = None, None
    nfit, nonconv = 0, 0
    last = None
    t_fit = start
    while t_fit < end:
        n_train = int(np.searchsorted(tm, t_fit - TRAIN_END_MARGIN_DAYS, side="left"))
        lo = int(np.searchsorted(tm, t_fit, side="left"))
        hi = int(np.searchsorted(tm, min(t_fit + step, end), side="left"))
        if hi > lo and n_train >= 50:
            w = decay_weights(des.t_obs[: 2 * n_train], t_fit, cfg.half_life)
            fit = fit_nb(des, n_train, w, P, theta, logr, maxiter=maxiter)
            theta, logr = fit.theta, fit.logr
            nfit += 1
            nonconv += 0 if fit.converged else 1
            last = fit
            eta = des.X[2 * lo: 2 * hi] @ theta
            mu = np.exp(np.clip(eta, -12.0, 8.0))
            out_rows.append(des.rows[lo:hi])
            out_mu_h.append(mu[0::2])
            out_mu_a.append(mu[1::2])
            out_r.append(np.full(hi - lo, fit.r))
            out_fd.append(np.full(hi - lo, t_fit))
        t_fit += step
    cat = (lambda L: np.concatenate(L) if L else np.array([]))
    return WalkForward(cat(out_rows).astype(int), cat(out_mu_h), cat(out_mu_a), cat(out_r), cat(out_fd), nfit, last,
                       nonconv)


# --------------------------------------------------------------------------------------------- distributions
def nb_cdf(k, mu, r):
    """P(X <= k) for X ~ NB(mean mu, size r); k may be an array (broadcast); k < 0 -> 0."""
    k = np.asarray(k, dtype=float)
    mu = np.asarray(mu, dtype=float)
    r = np.asarray(r, dtype=float)
    p = r / (r + mu)
    out = betainc(r, np.maximum(k, 0.0) + 1.0, p)
    return np.where(k < 0, 0.0, out)


def nb_pmf_grid(mu, r, K: int) -> np.ndarray:
    """(n, K) pmf of NB(mu_i, r_i) at 0..K-1."""
    mu = np.asarray(mu, dtype=float).reshape(-1, 1)
    r = np.broadcast_to(np.asarray(r, dtype=float).reshape(-1, 1), mu.shape)
    k = np.arange(K, dtype=float).reshape(1, -1)
    logp = (gammaln(k + r) - gammaln(r) - gammaln(k + 1.0) + r * np.log(r / (r + mu)) + k * np.log(mu / (r + mu)))
    return np.exp(logp)


def total_cdf_grid(mu_h, mu_a, r, K: int) -> np.ndarray:
    """(n, K): P(X_h + X_a <= k), k = 0..K-1, independent NB(mu_h, r) and NB(mu_a, r), exact convolution
    (support truncated at K-1, which is exact for all k < K)."""
    ph = nb_pmf_grid(mu_h, r, K)
    pa = nb_pmf_grid(mu_a, r, K)
    ca = np.cumsum(pa, axis=1)
    out = np.empty_like(ph)
    for k in range(K):
        out[:, k] = (ph[:, : k + 1] * ca[:, k::-1]).sum(axis=1) if k else ph[:, 0] * ca[:, 0]
    return np.clip(out, 0.0, 1.0)


def over_probs(mu_h, mu_a, r, kind: str, lines: list[float], r_total: Optional[float] = None):
    """P(count > line). team -> (n, 2, nlines) (home side, away side); total -> (n, nlines).
    total: exact convolution of two independent NB(mu, r) unless r_total is given, then NB(mu_h + mu_a, r_total)."""
    lines_k = [int(math.floor(L)) for L in lines]  # X > L  <=>  X > floor(L) for half-integer lines
    r = np.asarray(r, dtype=float)
    if kind == "team":
        res = np.empty((len(mu_h), 2, len(lines)))
        for j, k in enumerate(lines_k):
            res[:, 0, j] = 1.0 - nb_cdf(k, mu_h, r)
            res[:, 1, j] = 1.0 - nb_cdf(k, mu_a, r)
        return res
    if r_total is not None:
        mu_t = np.asarray(mu_h, dtype=float) + np.asarray(mu_a, dtype=float)
        return np.stack([1.0 - nb_cdf(k, mu_t, r_total) for k in lines_k], axis=1)
    K = max(lines_k) + 1
    grid = total_cdf_grid(mu_h, mu_a, r, K)
    return np.stack([1.0 - grid[:, k] for k in lines_k], axis=1)


# --------------------------------------------------------------------------------------------- baselines
@dataclass
class Baselines:
    """Per dataset row: team histories (before kick-off - 3 h, within 365 days) and competition averages."""

    n: dict  # 'h','a' -> number of matches in the 365-day window
    f5: dict
    a5: dict
    f10: dict
    a10: dict
    f365: dict
    a365: dict
    comp_home: np.ndarray
    comp_away: np.ndarray
    comp_n: np.ndarray

    def eligible(self, min_team: int = 5, min_comp: int = 30) -> np.ndarray:
        return (self.n["h"] >= min_team) & (self.n["a"] >= min_team) & (self.comp_n >= min_comp)

    def means(self, name: str) -> tuple[np.ndarray, np.ndarray]:
        if name == "last5":
            return ((self.f5["h"] + self.a5["a"]) / 2, (self.f5["a"] + self.a5["h"]) / 2)
        if name == "last10":
            return ((self.f10["h"] + self.a10["a"]) / 2, (self.f10["a"] + self.a10["h"]) / 2)
        if name == "avg365":
            return ((self.f365["h"] + self.a365["a"]) / 2, (self.f365["a"] + self.a365["h"]) / 2)
        if name == "comp":
            return self.comp_home, self.comp_away
        raise KeyError(name)


BASELINE_NAMES = ["last5", "last10", "avg365", "comp"]
WINDOW_DAYS = 365.0


def compute_baselines(ds: Dataset, stat: str) -> Baselines:
    n_rows = ds.n
    valid = ds.valid[stat]
    yv = ds.y[stat]
    res = {k: {"h": np.full(n_rows, np.nan), "a": np.full(n_rows, np.nan)} for k in ("f5", "a5", "f10", "a10", "f365",
                                                                                      "a365")}
    nwin = {"h": np.zeros(n_rows, dtype=int), "a": np.zeros(n_rows, dtype=int)}
    # team histories from valid matches (both sides present)
    vr = np.flatnonzero(valid)
    team_hist: dict[int, tuple] = {}
    ids = np.concatenate([ds.home_idx[vr], ds.away_idx[vr]])
    tt = np.concatenate([ds.t[vr], ds.t[vr]])
    ff = np.concatenate([yv[vr, 0], yv[vr, 1]])
    aa = np.concatenate([yv[vr, 1], yv[vr, 0]])
    order = np.lexsort((tt, ids))
    ids, tt, ff, aa = ids[order], tt[order], ff[order], aa[order]
    bounds = np.flatnonzero(np.diff(ids)) + 1
    for seg in np.split(np.arange(len(ids)), bounds):
        if len(seg) == 0:
            continue
        team_hist[int(ids[seg[0]])] = (tt[seg], np.concatenate([[0.0], np.cumsum(ff[seg])]),
                                       np.concatenate([[0.0], np.cumsum(aa[seg])]))
    for side, tidx in (("h", ds.home_idx), ("a", ds.away_idx)):
        for team in np.unique(tidx):
            hist = team_hist.get(int(team))
            q_rows = np.flatnonzero(tidx == team)
            if hist is None:
                continue
            times, cf, ca = hist
            q = ds.t[q_rows] - TRAIN_END_MARGIN_DAYS
            hi = np.searchsorted(times, q, side="left")
            lo = np.searchsorted(times, q - WINDOW_DAYS, side="left")
            cnt = hi - lo
            nwin[side][q_rows] = cnt
            for k, (fk, ak) in ((5, ("f5", "a5")), (10, ("f10", "a10"))):
                lo_k = np.maximum(lo, hi - k)
                c = hi - lo_k
                with np.errstate(invalid="ignore", divide="ignore"):
                    res[fk][side][q_rows] = np.where(c > 0, (cf[hi] - cf[lo_k]) / np.maximum(c, 1), np.nan)
                    res[ak][side][q_rows] = np.where(c > 0, (ca[hi] - ca[lo_k]) / np.maximum(c, 1), np.nan)
            with np.errstate(invalid="ignore", divide="ignore"):
                res["f365"][side][q_rows] = np.where(cnt > 0, (cf[hi] - cf[lo]) / np.maximum(cnt, 1), np.nan)
                res["a365"][side][q_rows] = np.where(cnt > 0, (ca[hi] - ca[lo]) / np.maximum(cnt, 1), np.nan)
    # competition averages (home and away counts separately) over the previous 365 days
    comp_home = np.full(n_rows, np.nan)
    comp_away = np.full(n_rows, np.nan)
    comp_n = np.zeros(n_rows, dtype=int)
    for c in np.unique(ds.comp):
        vrc = vr[ds.comp[vr] == c]
        times = ds.t[vrc]
        ch = np.concatenate([[0.0], np.cumsum(yv[vrc, 0])])
        ca2 = np.concatenate([[0.0], np.cumsum(yv[vrc, 1])])
        q_rows = np.flatnonzero(ds.comp == c)
        q = ds.t[q_rows] - TRAIN_END_MARGIN_DAYS
        hi = np.searchsorted(times, q, side="left")
        lo = np.searchsorted(times, q - WINDOW_DAYS, side="left")
        cnt = hi - lo
        comp_n[q_rows] = cnt
        with np.errstate(invalid="ignore", divide="ignore"):
            comp_home[q_rows] = np.where(cnt > 0, (ch[hi] - ch[lo]) / np.maximum(cnt, 1), np.nan)
            comp_away[q_rows] = np.where(cnt > 0, (ca2[hi] - ca2[lo]) / np.maximum(cnt, 1), np.nan)
    return Baselines(nwin, res["f5"], res["a5"], res["f10"], res["a10"], res["f365"], res["a365"], comp_home,
                     comp_away, comp_n)


def fit_dispersion(y_h: np.ndarray, y_a: np.ndarray, mu_h: np.ndarray, mu_a: np.ndarray) -> float:
    """Maximum-likelihood NB size r for fixed means (used for baselines)."""
    y = np.concatenate([y_h, y_a])
    mu = np.maximum(np.concatenate([mu_h, mu_a]), 1e-6)

    def nll(lr):
        return -float(nb_loglik(y, mu, math.exp(lr)).sum())

    res = minimize_scalar(nll, bounds=LOGR_BOUNDS, method="bounded", options={"xatol": 1e-4})
    return float(math.exp(res.x))


def fit_total_dispersion(y_h: np.ndarray, y_a: np.ndarray, mu_h: np.ndarray, mu_a: np.ndarray) -> float:
    """Maximum-likelihood NB size r_total of the match total around mu_h + mu_a (captures the home/away correlation)."""
    y = np.asarray(y_h, dtype=float) + np.asarray(y_a, dtype=float)
    mu = np.maximum(np.asarray(mu_h, dtype=float) + np.asarray(mu_a, dtype=float), 1e-6)

    def nll(lr):
        return -float(nb_loglik(y, mu, math.exp(lr)).sum())

    res = minimize_scalar(nll, bounds=LOGR_BOUNDS, method="bounded", options={"xatol": 1e-4})
    return float(math.exp(res.x))


# --------------------------------------------------------------------------------------------- evaluation
def clip_p(p: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    return np.clip(p, eps, 1.0 - eps)


@dataclass
class MarketEval:
    """Per observation (team: 2n rows = home side then away side; total: n rows) x lines."""

    p: np.ndarray  # P(over)
    over: np.ndarray  # bool outcome
    loss: np.ndarray  # log loss of the over/under call
    match_idx: np.ndarray  # index (0..n-1) of the match each observation belongs to
    n_match: int


def market_eval(mu_h, mu_a, r, y_h, y_a, kind: str, lines: list[float],
                r_total: Optional[float] = None) -> MarketEval:
    n = len(mu_h)
    p = over_probs(mu_h, mu_a, r, kind, lines, r_total)
    L = np.asarray(lines).reshape(1, -1)
    if kind == "team":
        pp = np.concatenate([p[:, 0, :], p[:, 1, :]], axis=0)
        yy = np.concatenate([y_h, y_a]).reshape(-1, 1)
        midx = np.concatenate([np.arange(n), np.arange(n)])
    else:
        pp = p
        yy = (y_h + y_a).reshape(-1, 1)
        midx = np.arange(n)
    over = yy > L
    pc = clip_p(pp)
    loss = -np.where(over, np.log(pc), np.log(1.0 - pc))
    return MarketEval(pp, over, loss, midx, n)


def match_loss(me: MarketEval) -> np.ndarray:
    """(n_match,) loss per match = mean over observations of the match and lines."""
    per_obs = me.loss.mean(axis=1)
    return np.bincount(me.match_idx, weights=per_obs, minlength=me.n_match) / np.bincount(me.match_idx,
                                                                                        minlength=me.n_match)


def paired_bootstrap(diff: np.ndarray, n_boot: int = 2000, seed: int = 7, level: float = 0.90) -> tuple:
    """Mean of per-match differences with a paired (match-level) bootstrap interval."""
    rng = np.random.default_rng(seed)
    n = len(diff)
    means = np.empty(n_boot)
    chunk = 250
    for s in range(0, n_boot, chunk):
        e = min(n_boot, s + chunk)
        idx = rng.integers(0, n, size=(e - s, n))
        means[s:e] = diff[idx].mean(axis=1)
    a = (1 - level) / 2
    return float(diff.mean()), float(np.quantile(means, a)), float(np.quantile(means, 1 - a))
