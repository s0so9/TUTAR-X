"""Shared helpers for the selective-prediction study (sel_*.py, 2026-10-15): which picks to SHOW so that the
shown Banko / Oranli picks hit as often as possible (accuracy vs coverage).

Research only: nothing in backend/app or backend/config is touched; the production DB is opened read-only
(sqlite URI mode=ro) only to map football-data `db_match_id` values to FotMob ids (same rule as
scripts/training/calibration_common.load_closing_odds). No network.

Inputs (all real data, nothing imputed; a missing value stays NaN / None and is reported as unknown):
  data/training/baseline_predictions_full.csv.gz  production model, out-of-sample, 19,985 rows with a prediction
  data/training/match_features_full.csv.gz        pre-kick-off features (last-5, rest, line-up, ...)
  data/external/football_data_history.csv          closing + pre-closing odds 2021/22..2025/26 (FotMob ids)
  data/external/football_data_matches.csv          closing (+ pre-closing) odds 2025-07.. (DB ids -> FotMob ids)
  data/history/all_results.db                      168k results for Elo / last-5 / schedule features
"""

from __future__ import annotations

import csv
import gzip
import json
import math
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

RESEARCH_DIR = Path(__file__).resolve().parent
BACKEND_DIR = RESEARCH_DIR.parents[1]
DATA = BACKEND_DIR / "data"
TRAINING = DATA / "training"
OUT = DATA / "research"
OUT.mkdir(parents=True, exist_ok=True)

Z90 = 1.6448536269514722
EURO_IDS = {"42", "73", "10216", "10611", "10613", "10615"}

# Candidate order = rail-row order of the app (headline_picks.candidates_from_prediction): ties -> first wins.
KEYS = ["HOME_WIN", "DRAW", "AWAY_WIN", "HOME_OR_DRAW", "HOME_OR_AWAY", "DRAW_OR_AWAY",
        "UNDER_1_5", "OVER_1_5", "UNDER_2_5", "OVER_2_5", "UNDER_3_5", "OVER_3_5", "BTTS_NO", "BTTS_YES"]
KIDX = {k: i for i, k in enumerate(KEYS)}
FAMILY = np.array([0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1])  # 0 = result (1X2 + DC), 1 = goals
SHORT = {"HOME_WIN": "MS1", "DRAW": "MSX", "AWAY_WIN": "MS2", "HOME_OR_DRAW": "1X", "HOME_OR_AWAY": "12",
         "DRAW_OR_AWAY": "X2", "UNDER_1_5": "1.5Alt", "OVER_1_5": "1.5Ust", "UNDER_2_5": "2.5Alt",
         "OVER_2_5": "2.5Ust", "UNDER_3_5": "3.5Alt", "OVER_3_5": "3.5Ust", "BTTS_NO": "KGYok",
         "BTTS_YES": "KGVar"}
# market groups (two-sided markets: the pick is the more likely side)
MARKETS = {
    "1X2_fav": [0, 1, 2],
    "double_chance": [3, 4, 5],
    "ou15": [6, 7],
    "ou25": [8, 9],
    "ou35": [10, 11],
    "btts": [12, 13],
}

BANKO_MIN_P, BANKO_MAX_P = 0.70, 0.95
ODDS_MIN_PRICE, ODDS_MIN_P = 1.60, 0.45


# ------------------------------------------------------------------------------------------ small utils
def fnum(s) -> float:
    if s is None or s == "":
        return float("nan")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def parse_dt(s: str) -> datetime:
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1]
    if "+" in s[10:]:
        s = s[: 10 + s[10:].index("+")]
    return datetime.fromisoformat(s)


def wilson(k: float, n: int, z: float = Z90) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    ph = k / n
    den = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return (c - h, c + h)


def clopper_pearson_upper(k_err: int, n: int, alpha: float = 0.1) -> float:
    """One-sided (1 - alpha) upper bound of an error rate."""
    from scipy.stats import beta
    if n == 0:
        return 1.0
    if k_err >= n:
        return 1.0
    return float(beta.ppf(1 - alpha, k_err + 1, n - k_err))


def rate_row(hit: np.ndarray, p: Optional[np.ndarray] = None, n_days: Optional[int] = None,
             n_matches: Optional[int] = None) -> dict:
    hit = np.asarray(hit, bool)
    n = int(hit.size)
    k = int(hit.sum())
    lo, hi = wilson(k, n)
    row = {"n": n, "hit": round(k / n, 4) if n else None, "ci90": [round(lo, 4), round(hi, 4)] if n else None}
    if p is not None and n:
        row["mean_p"] = round(float(np.mean(p)), 4)
    if n_days:
        row["per_day"] = round(n / n_days, 2)
    if n_matches:
        row["coverage"] = round(n / n_matches, 4)
    return row


def day_cluster_boot(hit_a: np.ndarray, sel_a: np.ndarray, hit_b: np.ndarray, sel_b: np.ndarray,
                     days: np.ndarray, n_boot: int = 2000, seed: int = 7) -> dict:
    """Bootstrap (resampling match days) of hit-rate(A) - hit-rate(B) for two selection rules on the same
    matches. hit_* are per-match outcomes of the rule's pick (only read where sel_* is True)."""
    rng = np.random.default_rng(seed)
    ud, inv = np.unique(days, return_inverse=True)
    nd = len(ud)
    ka = np.bincount(inv, weights=(sel_a & hit_a).astype(float), minlength=nd)
    na = np.bincount(inv, weights=sel_a.astype(float), minlength=nd)
    kb = np.bincount(inv, weights=(sel_b & hit_b).astype(float), minlength=nd)
    nb = np.bincount(inv, weights=sel_b.astype(float), minlength=nd)
    point = ka.sum() / max(na.sum(), 1) - kb.sum() / max(nb.sum(), 1)
    diffs = np.empty(n_boot)
    for b in range(n_boot):
        w = np.bincount(rng.integers(0, nd, nd), minlength=nd)
        diffs[b] = (w @ ka) / max(w @ na, 1) - (w @ kb) / max(w @ nb, 1)
    return {"diff": round(float(point), 4), "ci90": [round(float(np.quantile(diffs, 0.05)), 4),
                                                      round(float(np.quantile(diffs, 0.95)), 4)]}


# ------------------------------------------------------------------------------------------ predictions
def load_preds(path: Path = TRAINING / "baseline_predictions_full.csv.gz") -> dict:
    """Rows with status ok. P (n, 14) candidate probabilities of the production model, Y (n, 14) outcomes."""
    rows = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["status"] != "ok":
                continue
            rows.append(r)
    d: dict = {}
    d["match_id"] = np.array([r["match_id"] for r in rows])
    d["kickoff"] = np.array([r["kickoff"] for r in rows])
    d["date"] = np.array([r["kickoff"][:10] for r in rows])
    d["split"] = np.array([r["split"] for r in rows])
    d["comp"] = np.array([r["competition_provider_id"] for r in rows])
    d["comp_type"] = np.array([r["comp_type"] for r in rows])
    d["home"] = np.array([r["home_team_id"] for r in rows])
    d["away"] = np.array([r["away_team_id"] for r in rows])
    for k in ("mu_home", "mu_away", "p_home", "p_draw", "p_away", "p_over15", "p_over25", "p_over35", "p_btts",
              "value_log_ratio", "lineup_form", "lambda_home_raw", "lambda_away_raw"):
        d[k] = np.array([fnum(r[k]) for r in rows])
    d["hg"] = np.array([int(r["home_goals"]) for r in rows])
    d["ag"] = np.array([int(r["away_goals"]) for r in rows])
    d["euro"] = np.isin(d["comp"], list(EURO_IDS))
    d["n"] = len(rows)
    d["P"] = candidate_probs(d["p_home"], d["p_draw"], d["p_away"], d["p_over15"], d["p_over25"],
                             d["p_over35"], d["p_btts"])
    d["Y"] = candidate_outcomes(d["hg"], d["ag"])
    return d


def candidate_probs(ph, pd, pa, o15, o25, o35, btts) -> np.ndarray:
    return np.stack([ph, pd, pa, ph + pd, ph + pa, pd + pa, 1 - o15, o15, 1 - o25, o25, 1 - o35, o35,
                     1 - btts, btts], 1)


def candidate_outcomes(hg: np.ndarray, ag: np.ndarray) -> np.ndarray:
    t = hg + ag
    return np.stack([hg > ag, hg == ag, hg < ag, hg >= ag, hg != ag, hg <= ag, t < 1.5, t > 1.5, t < 2.5,
                     t > 2.5, t < 3.5, t > 3.5, (hg == 0) | (ag == 0), (hg > 0) & (ag > 0)], 1)


def subset(d: dict, mask: np.ndarray) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, np.ndarray) and v.shape[:1] == (d["n"],):
            out[k] = v[mask]
        else:
            out[k] = v
    out["n"] = int(mask.sum())
    return out


# ------------------------------------------------------------------------------------------ pick rules
def banko_index(P: np.ndarray, lo: float = BANKO_MIN_P, hi: float = BANKO_MAX_P,
                allowed: Optional[np.ndarray] = None) -> np.ndarray:
    """Index of the most likely candidate with lo <= p <= hi (stable: first candidate wins a tie), -1 if none.
    ``allowed`` (14,) or (n, 14) bool restricts the candidate set."""
    ok = (P >= lo) & (P <= hi) & np.isfinite(P)
    if allowed is not None:
        ok &= allowed
    score = np.where(ok, P, -1.0)
    idx = np.argmax(score, axis=1)  # argmax returns the first max -> stable tie rule
    idx[score[np.arange(len(idx)), idx] < 0] = -1
    return idx


def oranli_index(P: np.ndarray, banko: np.ndarray, odds: Optional[np.ndarray] = None,
                 min_price: float = ODDS_MIN_PRICE, min_p: float = ODDS_MIN_P) -> np.ndarray:
    """headline_picks.select_headline_picks: other family than the banko; a priced candidate (odds >= 1.60,
    p >= 0.45, p * odds >= 1) wins over a fair one (1/p >= 1.60, p >= 0.45). -1 if none."""
    n = P.shape[0]
    bfam = np.where(banko >= 0, FAMILY[np.clip(banko, 0, None)], -1)
    other = FAMILY[None, :] != bfam[:, None]
    fair_ok = other & (P >= min_p) & (1.0 / np.clip(P, 1e-12, None) >= min_price) & np.isfinite(P)
    out = np.full(n, -1)
    if odds is not None:
        priced_ok = other & np.isfinite(odds) & (odds >= min_price) & (P >= min_p) & (P * np.nan_to_num(odds) >= 1)
        s = np.where(priced_ok, P, -1.0)
        j = np.argmax(s, axis=1)
        has = s[np.arange(n), j] >= 0
        out[has] = j[has]
    s = np.where(fair_ok, P, -1.0)
    j = np.argmax(s, axis=1)
    has = (s[np.arange(n), j] >= 0) & (out < 0)
    out[has] = j[has]
    out[(out >= 0) & (out == banko)] = -1
    return out


def take(M: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """M[i, idx[i]] (NaN / False where idx == -1)."""
    v = M[np.arange(len(idx)), np.clip(idx, 0, None)]
    if v.dtype == bool:
        return np.where(idx >= 0, v, False)
    return np.where(idx >= 0, v, np.nan)


# ------------------------------------------------------------------------------------------ odds
def load_odds(db: Path = BACKEND_DIR / "football_intelligence.db") -> dict:
    """FotMob match id -> dict(close=[h,d,a], close_ou=[over, under], pre=[h,d,a], pre_ou=[o,u],
    odds_c=[H,D,A] average-closing decimal odds (else Pinnacle, else Bet365), odds_c_ou=[O,U]).
    De-vigged probabilities are proportional (p_close_* of the football-data build). Same acceptance rules
    as calibration_common.load_closing_odds (score agrees, not awarded). League matches only."""
    id_map: dict[str, str] = {}
    if Path(db).exists():
        con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
        try:
            id_map = {r[0]: str(r[1]) for r in con.execute("select id, provider_id from matches")}
        finally:
            con.close()

    def first(r, groups):
        for g in groups:
            v = [fnum(r.get(c)) for c in g]
            if all(np.isfinite(v)) and all(x > 1 for x in v):
                return v
        return [float("nan")] * len(groups[0])

    def devig(v):
        if not all(np.isfinite(v)):
            return [float("nan")] * len(v)
        inv = [1 / x for x in v]
        s = sum(inv)
        return [x / s for x in inv]

    def rec(r):
        o = {
            "close": [fnum(r.get("p_close_home")), fnum(r.get("p_close_draw")), fnum(r.get("p_close_away"))],
            "close_ou": [fnum(r.get("p_close_over25")), fnum(r.get("p_close_under25"))],
            "pre": [fnum(r.get("p_pre_home")), fnum(r.get("p_pre_draw")), fnum(r.get("p_pre_away"))],
            "odds_c": first(r, [("AvgCH", "AvgCD", "AvgCA"), ("PSCH", "PSCD", "PSCA"), ("B365CH", "B365CD", "B365CA")]),
            "odds_c_ou": first(r, [("AvgC>2.5", "AvgC<2.5"), ("PC>2.5", "PC<2.5"), ("B365C>2.5", "B365C<2.5")]),
        }
        if r.get("p_pre_over25") not in (None, ""):
            o["pre_ou"] = [fnum(r.get("p_pre_over25")), fnum(r.get("p_pre_under25"))]
        else:
            o["pre_ou"] = devig(first(r, [("P>2.5", "P<2.5"), ("Avg>2.5", "Avg<2.5"), ("B365>2.5", "B365<2.5")]))
        return o

    out: dict[str, dict] = {}
    cur = DATA / "external" / "football_data_matches.csv"
    with open(cur, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pid = id_map.get(r.get("db_match_id") or "")
            if pid and r.get("db_score_agrees") == "1" and r.get("p_close_home") and pid not in out:
                out[pid] = rec(r)
    hist = DATA / "external" / "football_data_history.csv"
    with open(hist, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pid = r.get("fotmob_match_id") or ""
            if (pid and r.get("score_agrees") == "1" and r.get("fotmob_awarded") != "1"
                    and r.get("p_close_home") and pid not in out):
                out[pid] = rec(r)
    return out


def attach_odds(d: dict, odds: dict) -> None:
    """Adds arrays mk_close (n,3), mk_close_ou (n,2: over, under), mk_pre (n,3), mk_pre_ou (n,2),
    odds_c (n,3), odds_c_ou (n,2); NaN when unknown."""
    n = d["n"]
    for k, w in (("close", 3), ("close_ou", 2), ("pre", 3), ("pre_ou", 2), ("odds_c", 3), ("odds_c_ou", 2)):
        a = np.full((n, w), np.nan)
        for i, mid in enumerate(d["match_id"]):
            o = odds.get(mid)
            if o is not None:
                a[i] = o[k]
        d["mk_" + k if not k.startswith("odds") else k] = a


# ------------------------------------------------------------------------------------------ market-implied goals
_GRID = None


def _grid(rho: float = -0.015749686176397125):
    """(lh, la) grid 0.05..5.0 step 0.025 under Poisson x Dixon-Coles (rho of the production goal layer)
    -> [p_home, p_away, p_over25] keys and all candidate probabilities."""
    global _GRID
    if _GRID is not None:
        return _GRID
    from scipy.stats import poisson
    g = np.arange(0, 11)
    lv = np.arange(0.05, 5.0001, 0.025)
    LH, LA = np.meshgrid(lv, lv, indexing="ij")
    lh, la = LH.ravel(), LA.ravel()
    ph = poisson.pmf(g[None, :], lh[:, None])
    pa = poisson.pmf(g[None, :], la[:, None])
    m = ph[:, :, None] * pa[:, None, :]
    tau = np.ones_like(m)
    tau[:, 0, 0] = 1 - lh * la * rho
    tau[:, 0, 1] = 1 + lh * rho
    tau[:, 1, 0] = 1 + la * rho
    tau[:, 1, 1] = 1 - rho
    m = m * tau
    m /= m.sum(axis=(1, 2), keepdims=True)
    tot = g[:, None] + g[None, :]
    home = np.tril(m, -1).sum(axis=(1, 2))
    draw = np.trace(m, axis1=1, axis2=2)
    away = np.triu(m, 1).sum(axis=(1, 2))
    o15 = (m * (tot > 1.5)).sum(axis=(1, 2))
    o25 = (m * (tot > 2.5)).sum(axis=(1, 2))
    o35 = (m * (tot > 3.5)).sum(axis=(1, 2))
    btts = m[:, 1:, 1:].sum(axis=(1, 2))
    _GRID = {"lh": lh, "la": la, "home": home, "draw": draw, "away": away, "o15": o15, "o25": o25,
             "o35": o35, "btts": btts}
    return _GRID


def market_candidates(mk1x2: np.ndarray, mkou: np.ndarray) -> np.ndarray:
    """(n, 14) market-implied candidate probabilities. 1X2 and double chance come straight from the de-vigged
    1X2; the goal lines and BTTS come from the Poisson x Dixon-Coles (lh, la) grid point that best fits the
    de-vigged [home, away, over 2.5] (nearest neighbour, equal weights). NaN where the inputs are missing
    (goal candidates need the O/U 2.5 price)."""
    from scipy.spatial import cKDTree
    G = _grid()
    n = mk1x2.shape[0]
    out = np.full((n, 14), np.nan)
    ok1 = np.all(np.isfinite(mk1x2), axis=1)
    ph, pd, pa = mk1x2[:, 0], mk1x2[:, 1], mk1x2[:, 2]
    out[ok1, 0], out[ok1, 1], out[ok1, 2] = ph[ok1], pd[ok1], pa[ok1]
    out[ok1, 3], out[ok1, 4], out[ok1, 5] = (ph + pd)[ok1], (ph + pa)[ok1], (pd + pa)[ok1]
    ok2 = ok1 & np.isfinite(mkou[:, 0])
    if ok2.any():
        tree = cKDTree(np.stack([G["home"], G["away"], G["o25"]], 1))
        _, j = tree.query(np.stack([ph[ok2], pa[ok2], mkou[ok2, 0]], 1))
        o25 = mkou[ok2, 0]  # keep the market's own O/U 2.5
        out[ok2, 6], out[ok2, 7] = 1 - G["o15"][j], G["o15"][j]
        out[ok2, 8], out[ok2, 9] = 1 - o25, o25
        out[ok2, 10], out[ok2, 11] = 1 - G["o35"][j], G["o35"][j]
        out[ok2, 12], out[ok2, 13] = 1 - G["btts"][j], G["btts"][j]
    return out


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if not math.isfinite(f) else f
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    return o


def dump(obj, name: str) -> Path:
    p = OUT / name
    p.write_text(json.dumps(_clean(obj), indent=1, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return p


# ------------------------------------------------------------------------------------------ everything joined
def load_all(include_test: bool) -> dict:
    """Predictions (+ market-implied, Elo, last-5 form candidate probabilities and uncertainty flags).
    include_test=False drops the test rows right after loading (design scripts never see them)."""
    d = load_preds()
    if not include_test:
        d = subset(d, d["split"] != "test")
    attach_odds(d, load_odds())
    d["MK"] = market_candidates(d["mk_close"], d["mk_close_ou"])
    d["MKpre"] = market_candidates(d["mk_pre"], d["mk_pre_ou"])
    feats = {}
    with gzip.open(OUT / "sel_features.csv.gz", "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            feats[r["match_id"]] = r
    n = d["n"]

    def col(name):
        return np.array([fnum(feats.get(m, {}).get(name)) for m in d["match_id"]])

    eh, ed, ea = col("elo_p_home"), col("elo_p_draw"), col("elo_p_away")
    nan = np.full(n, np.nan)
    d["EL"] = np.stack([eh, ed, ea, eh + ed, eh + ea, ed + ea] + [nan] * 8, 1)
    F = {s: {c: col(f"{s}_{c}") for c in ("n5", "w", "d", "l", "o15", "o25", "o35", "btts", "n400", "comp365",
                                          "season_md", "rest")} for s in ("h", "a")}
    h, a = F["h"], F["a"]
    ok = (h["n5"] >= 3) & (a["n5"] >= 3) & np.isfinite(h["w"]) & np.isfinite(a["w"])
    hw, hd, hl = h["w"] / h["n5"], h["d"] / h["n5"], h["l"] / h["n5"]
    aw, ad, al = a["w"] / a["n5"], a["d"] / a["n5"], a["l"] / a["n5"]
    fh, fd, fa = (hw + al) / 2, (hd + ad) / 2, (hl + aw) / 2
    nn = h["n5"] + a["n5"]
    o15, o25, o35 = (h["o15"] + a["o15"]) / nn, (h["o25"] + a["o25"]) / nn, (h["o35"] + a["o35"]) / nn
    bt = (h["btts"] + a["btts"]) / nn
    FR = np.stack([fh, fd, fa, fh + fd, fh + fa, fd + fa, 1 - o15, o15, 1 - o25, o25, 1 - o35, o35, 1 - bt, bt], 1)
    FR[~ok] = np.nan
    d["FR"] = FR
    league = ~d["euro"]
    d["flag_euro"] = d["euro"].copy()
    d["flag_early"] = (np.fmin(h["season_md"], a["season_md"]) <= 4)
    d["flag_new_team"] = league & (np.fmin(h["comp365"], a["comp365"]) < 10)
    d["flag_few_matches"] = np.fmin(h["n400"], a["n400"]) < 25
    d["flag_lineup_missing"] = ~np.isfinite(d["lineup_form"])  # no line-up-form signal (production: no XI yet)
    d["flag_value_missing"] = ~np.isfinite(d["value_log_ratio"])  # FotMob sent no XI market value
    d["flag_long_rest"] = np.fmax(h["rest"], a["rest"]) > 20
    d["season_md_min"] = np.fmin(h["season_md"], a["season_md"])
    return d


FLAGS = ["flag_euro", "flag_early", "flag_new_team", "flag_few_matches", "flag_lineup_missing", "flag_value_missing",
         "flag_long_rest"]


def group_pick(P: np.ndarray, g: list) -> tuple[np.ndarray, np.ndarray]:
    """Most likely side within a market group: (candidate index, probability). NaN rows -> (-1, nan)."""
    sub = P[:, g]
    ok = np.all(np.isfinite(sub), axis=1)
    j = np.argmax(np.where(np.isfinite(sub), sub, -1), axis=1)
    idx = np.where(ok, np.array(g)[j], -1)
    return idx, np.where(ok, sub[np.arange(len(j)), j], np.nan)
