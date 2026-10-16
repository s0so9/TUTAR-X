"""Shared loader for the error-analysis research (2026-10-15): where does the production 1X2 / goal model lose accuracy?

Inputs (all read-only):
  data/training/baseline_predictions_full.csv.gz  production model, out-of-sample (walk-forward ratings, train-only goal layer)
  data/training/match_features_full.csv.gz       pre-kick-off features (rest days, Euro midweek flags, form, ...)
  data/external/football_data_matches.csv         closing / pre-closing odds 2025-07+ (db_match_id -> FotMob id via DB, mode=ro)
  data/external/football_data_history.csv         closing / pre-closing odds 2021/22..2025/26 (FotMob ids)
  data/research/err_match_info.csv                round / stadium / referee from the raw FotMob cache (err_extract_raw.py)
  data/history/all_results.db                     168k results (promoted teams, matches in the rating window)

Nothing is imputed: a missing value stays None / NaN and the row drops out of that particular analysis.
Odds: proportional de-vig (the p_close_* / p_pre_* columns as built upstream), plus a power de-vig recomputed here
from the raw closing odds (Pinnacle closing, else market-average closing, else Bet365 closing) as a sensitivity check.
"""
from __future__ import annotations

import csv
import gzip
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[2]
TRAIN = BACKEND / "data" / "training"
EXT = BACKEND / "data" / "external"
RES = BACKEND / "data" / "research"
DB = BACKEND / "football_intelligence.db"
HIST_DB = BACKEND / "data" / "history" / "all_results.db"

EURO_IDS = {"42", "73", "10216", "10611", "10613", "10615"}
LEAGUE_NAMES = {"47": "Premier League", "87": "LaLiga", "55": "Serie A", "54": "Bundesliga", "53": "Ligue 1",
                "57": "Eredivisie", "61": "Liga Portugal", "40": "Belgian Pro League", "71": "Super Lig",
                "122": "Czech 1. Liga", "48": "Championship", "59": "Eliteserien", "38": "Austrian Bundesliga",
                "64": "Scottish Premiership", "135": "Greek Super League", "46": "Danish Superligaen",
                "69": "Swiss Super League", "42": "Champions League", "73": "Europa League",
                "10216": "Conference League"}
EPS = 1e-12


def fnum(s):
    if s is None or s == "":
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return None if math.isnan(v) else v


def _odds(x):
    v = fnum(x)
    return v if (v is not None and v > 1.0) else None


def power_devig(odds: list[float]) -> list[float]:
    """Power method: p_i = (1/o_i)^k with k such that sum p_i = 1 (bisection)."""
    q = np.array([1.0 / o for o in odds])
    lo, hi = 0.5, 3.0
    for _ in range(80):
        k = (lo + hi) / 2
        s = (q ** k).sum()
        if s > 1:
            lo = k
        else:
            hi = k
    p = q ** ((lo + hi) / 2)
    return list(p / p.sum())


def _close_triplet(r):
    for a, b, c in (("PSCH", "PSCD", "PSCA"), ("AvgCH", "AvgCD", "AvgCA"), ("B365CH", "B365CD", "B365CA")):
        t = [_odds(r.get(a)), _odds(r.get(b)), _odds(r.get(c))]
        if all(t):
            return t, a[:-1]
    return None, None


def load_odds() -> dict:
    """FotMob match id -> dict(close=[h,d,a] proportional, close_pow=[...] power, pre=[...], ou=[p_over25 close],
    ou_pre, src). Same acceptance rules as calibration_common.load_closing_odds (score must agree)."""
    id_map = {}
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        id_map = {r[0]: str(r[1]) for r in con.execute("select id, provider_id from matches")}
    finally:
        con.close()
    out: dict[str, dict] = {}

    def rec(r):
        d = {"close": None, "close_pow": None, "pre": None, "ou": None, "ou_pre": None,
             "src": r.get("close_1x2_source") or "", "overround": fnum(r.get("close_1x2_overround"))}
        if r.get("p_close_home"):
            d["close"] = [float(r["p_close_home"]), float(r["p_close_draw"]), float(r["p_close_away"])]
        t, _ = _close_triplet(r)
        if t:
            d["close_pow"] = power_devig(t)
        if r.get("p_pre_home"):
            d["pre"] = [float(r["p_pre_home"]), float(r["p_pre_draw"]), float(r["p_pre_away"])]
        if r.get("p_close_over25"):
            d["ou"] = float(r["p_close_over25"])
        if r.get("p_pre_over25"):
            d["ou_pre"] = float(r["p_pre_over25"])
        return d

    with open(EXT / "football_data_matches.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pid = id_map.get(r.get("db_match_id") or "")
            if pid and r.get("db_score_agrees") == "1" and r.get("p_close_home") and pid not in out:
                out[pid] = rec(r)
    with open(EXT / "football_data_history.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pid = r.get("fotmob_match_id") or ""
            if (pid and r.get("score_agrees") == "1" and r.get("fotmob_awarded") != "1"
                    and r.get("p_close_home") and pid not in out):
                out[pid] = rec(r)
    return out


def load_info() -> dict:
    p = RES / "err_match_info.csv"
    out = {}
    if p.exists():
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out[r["match_id"]] = r
    return out


def load_features() -> dict:
    out = {}
    with gzip.open(TRAIN / "match_features_full.csv.gz", "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["match_id"]] = r
    return out


def load_results_db():
    """List of (kickoff datetime, comp id, season, home id, away id, hs, as) of non-awarded results."""
    con = sqlite3.connect(f"file:{HIST_DB.as_posix()}?mode=ro", uri=True)
    try:
        rows = con.execute("select scheduled_at, competition_provider_id, season, home_team_provider_id, "
                           "away_team_provider_id, home_score, away_score, coalesce(awarded,0) from results").fetchall()
    finally:
        con.close()
    out = []
    for s, c, se, h, a, hs, as_, aw in rows:
        if aw:
            continue
        try:
            t = datetime.fromisoformat(s.replace("Z", "").split(".")[0])
        except ValueError:
            continue
        out.append((t, str(c), se or "", str(h), str(a), hs, as_))
    out.sort()
    return out


def load_base(with_features=True, with_odds=True, with_info=True):
    """Rows of the production baseline with status ok, as a dict of numpy arrays + list fields."""
    rows = []
    with gzip.open(TRAIN / "baseline_predictions_full.csv.gz", "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if not r["status"].endswith(":ok") and r["status"] != "ok":
                continue
            rows.append(r)
    feats = load_features() if with_features else {}
    odds = load_odds() if with_odds else {}
    info = load_info() if with_info else {}
    n = len(rows)
    D = {"n": n}
    D["match_id"] = [r["match_id"] for r in rows]
    D["split"] = np.array([r["split"] for r in rows])
    D["comp"] = np.array([r["competition_provider_id"] for r in rows])
    D["comp_type"] = np.array([r["comp_type"] for r in rows])
    D["home"] = np.array([r["home_team_id"] for r in rows])
    D["away"] = np.array([r["away_team_id"] for r in rows])
    D["kickoff"] = [datetime.fromisoformat(r["kickoff"]) for r in rows]
    D["P"] = np.array([[float(r["p_home"]), float(r["p_draw"]), float(r["p_away"])] for r in rows])
    D["mu"] = np.array([[float(r["mu_home"]), float(r["mu_away"])] for r in rows])
    D["lam_raw"] = np.array([[float(r["lambda_home_raw"]), float(r["lambda_away_raw"])] for r in rows])
    D["p_over25"] = np.array([float(r["p_over25"]) for r in rows])
    D["p_btts"] = np.array([float(r["p_btts"]) for r in rows])
    D["hg"] = np.array([int(r["home_goals"]) for r in rows])
    D["ag"] = np.array([int(r["away_goals"]) for r in rows])
    res = {"H": 0, "D": 1, "A": 2}
    D["y"] = np.array([res[r["result"]] for r in rows])
    D["over25"] = np.array([int(r["over25"]) for r in rows])
    D["btts"] = np.array([int(r["btts"]) for r in rows])
    D["is_euro"] = np.isin(D["comp"], list(EURO_IDS))
    mk = np.full((n, 3), np.nan)
    mkp = np.full((n, 3), np.nan)
    pre = np.full((n, 3), np.nan)
    ou = np.full(n, np.nan)
    src = []
    for i, mid in enumerate(D["match_id"]):
        o = odds.get(mid)
        if o:
            if o["close"]:
                mk[i] = o["close"]
            if o["close_pow"]:
                mkp[i] = o["close_pow"]
            if o["pre"]:
                pre[i] = o["pre"]
            if o["ou"] is not None:
                ou[i] = o["ou"]
            src.append(o["src"])
        else:
            src.append("")
    D["M"] = mk
    D["Mpow"] = mkp
    D["Mpre"] = pre
    D["M_ou25"] = ou
    D["odds_src"] = np.array(src)
    D["has_mk"] = ~np.isnan(mk[:, 0])
    D["feat"] = [feats.get(m, {}) for m in D["match_id"]]
    D["info"] = [info.get(m, {}) for m in D["match_id"]]
    return D


# ------------------------------------------------------------------ metrics (per-row arrays)
def ll_rows(P, y):
    return -np.log(np.clip(P[np.arange(len(y)), y], EPS, 1))


def rps_rows(P, y):
    O = np.zeros_like(P)
    O[np.arange(len(y)), y] = 1
    c1 = P[:, 0] - O[:, 0]
    c2 = (P[:, 0] + P[:, 1]) - (O[:, 0] + O[:, 1])
    return 0.5 * (c1 ** 2 + c2 ** 2)


def brier_rows(P, y):
    O = np.zeros_like(P)
    O[np.arange(len(y)), y] = 1
    return ((P - O) ** 2).sum(axis=1)


def acc_rows(P, y):
    return (P.argmax(axis=1) == y).astype(float)


def bin_ll(p, y):
    p = np.clip(p, EPS, 1 - EPS)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def boot_ci(x, n_boot=2000, seed=7, q=(5, 95)):
    """Bootstrap CI of the mean of per-row values x (paired differences are passed as x = a - b)."""
    x = np.asarray(x, float)
    if len(x) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n_boot, len(x)))
    m = x[idx].mean(axis=1)
    return (float(np.percentile(m, q[0])), float(np.percentile(m, q[1])))


def r5(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), 5)


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
