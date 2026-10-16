"""Shared helpers for the favourite-calibration study (2026-10-14): loading the production baseline
predictions, 1X2 metrics, Wilson intervals, paired bootstrap, favourite bands, closing-odds loader.

No network. The production DB is opened read-only (sqlite URI mode=ro) only to translate football-data
`db_match_id` values into FotMob match ids (same rule as train_match_model.load_odds).

Everything here works on the out-of-sample production probabilities of
data/training/baseline_predictions_full.csv.gz (the production model with the train-only goal layer);
nothing is invented: a row without a prediction or without a result is dropped, never imputed.
"""

from __future__ import annotations

import csv
import gzip
import json
import math
import sqlite3
import sys
from bisect import bisect_right
from pathlib import Path
from typing import Optional

import numpy as np

TRAINING_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TRAINING_DIR.parents[1]
DATA = BACKEND_DIR / "data" / "training"
sys.path.insert(0, str(TRAINING_DIR))
import train_goal_model as T  # noqa: E402  (score_matrix only; numpy / scipy)

BOOT_N = 2000
BOOT_SEED = 7
Z90 = 1.6448536269514722
EURO_IDS = {"42", "73", "10216", "10611", "10613", "10615"}
EPS = 1e-12
SPLITS = ("train", "validation", "test")

# league groups used only to describe the favourite's / underdog's domestic league
TOP5 = {"47": "Premier League", "87": "LaLiga", "55": "Serie A", "54": "Bundesliga", "53": "Ligue 1"}
LEAGUE_NAMES = {"47": "Premier League", "87": "LaLiga", "55": "Serie A", "54": "Bundesliga", "53": "Ligue 1",
                "57": "Eredivisie", "61": "Liga Portugal", "40": "Belgian Pro League", "71": "Super Lig",
                "122": "Czech 1. Liga", "48": "Championship", "59": "Eliteserien", "38": "Austrian Bundesliga",
                "64": "Scottish Premiership", "135": "Greek Super League", "46": "Danish Superligaen",
                "69": "Swiss Super League"}


def fnum(s) -> Optional[float]:
    if s is None or s == "":
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return None if math.isnan(v) else v


def load_layer(path: Path = DATA / "goal_layer_train_only.json") -> dict:
    p = json.loads(Path(path).read_text(encoding="utf-8"))["params"]
    return {k: float(p[k]) for k in ("rho", "nb_dispersion")}


# ------------------------------------------------------------------------------------------ loading
def load_baseline(path: Path = DATA / "baseline_predictions_full.csv.gz") -> dict:
    """Rows with status ok (a rating lambda, a prediction and a result). Arrays keyed by column."""
    cols = {k: [] for k in ("match_id", "kickoff", "split", "comp", "comp_type", "home_id", "away_id",
                            "mu_h", "mu_a", "ph", "pd", "pa", "hg", "ag")}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["status"] != "ok":
                continue
            cols["match_id"].append(r["match_id"])
            cols["kickoff"].append(r["kickoff"])
            cols["split"].append(r["split"])
            cols["comp"].append(r["competition_provider_id"])
            cols["comp_type"].append(r["comp_type"])
            cols["home_id"].append(r["home_team_id"])
            cols["away_id"].append(r["away_team_id"])
            cols["mu_h"].append(float(r["mu_home"]))
            cols["mu_a"].append(float(r["mu_away"]))
            cols["ph"].append(float(r["p_home"]))
            cols["pd"].append(float(r["p_draw"]))
            cols["pa"].append(float(r["p_away"]))
            cols["hg"].append(int(r["home_goals"]))
            cols["ag"].append(int(r["away_goals"]))
    d = {k: np.array(v) for k, v in cols.items()}
    for k in ("mu_h", "mu_a", "ph", "pd", "pa"):
        d[k] = d[k].astype(float)
    d["hg"] = d["hg"].astype(int)
    d["ag"] = d["ag"].astype(int)
    d["p"] = np.stack([d["ph"], d["pd"], d["pa"]], 1)
    d["y"] = np.where(d["hg"] > d["ag"], 0, np.where(d["hg"] == d["ag"], 1, 2))
    d["euro"] = np.array([c in EURO_IDS for c in d["comp"]])
    d["n"] = len(d["match_id"])
    return d


def subset(d: dict, mask: np.ndarray) -> dict:
    out = {}
    for k, v in d.items():
        out[k] = v[mask] if isinstance(v, np.ndarray) and len(v) == d["n"] else v
    out["n"] = int(mask.sum())
    return out


def team_league_lookup(features: Path = DATA / "match_features_full.csv.gz"):
    """team id -> sorted list of (kickoff, comp id) of its DOMESTIC league matches in the feature file
    (comp_type == league). A UEFA match is assigned the team's league of the nearest earlier domestic match
    (else the nearest later one); a team with no domestic match in the file (clubs of leagues that are not
    collected) has no league: it is reported as "not covered", never guessed."""
    hist: dict[str, list] = {}
    with gzip.open(features, "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["comp_type"] != "league":
                continue
            for t in (r["home_team_id"], r["away_team_id"]):
                hist.setdefault(t, []).append((r["kickoff"], r["competition_provider_id"]))
    for t in hist:
        hist[t].sort()
    keys = {t: [x[0] for x in v] for t, v in hist.items()}

    def lookup(team: str, kickoff: str) -> Optional[str]:
        v = hist.get(team)
        if not v:
            return None
        i = bisect_right(keys[team], kickoff)
        return v[i - 1][1] if i > 0 else v[0][1]

    return lookup


def league_group(comp: Optional[str]) -> str:
    if comp is None:
        return "not covered"
    if comp == "47":
        return "Premier League"
    if comp in TOP5:
        return "other top-5 league"
    return "other covered league"


# ------------------------------------------------------------------------------------------ metrics
def logloss(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    return -np.log(np.clip(p[np.arange(len(y)), y], EPS, 1.0))


def brier(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    return ((p - np.eye(3)[y]) ** 2).sum(1)


def wilson(k: float, n: int, z: float = Z90) -> tuple[float, float]:
    """Wilson score interval (default 90 %) for a binomial rate."""
    if n == 0:
        return (float("nan"), float("nan"))
    ph = k / n
    den = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def paired_boot(diff: np.ndarray, n_boot: int = BOOT_N, seed: int = BOOT_SEED) -> dict:
    """Mean of per-match differences (after - before) with a 90 % percentile bootstrap interval."""
    n = len(diff)
    if n == 0:
        return {"n": 0}
    out = {"n": int(n), "mean": float(diff.mean())}
    if n >= 20:
        idx = np.random.default_rng(seed).integers(0, n, size=(n_boot, n))
        b = diff[idx].mean(1)
        out["ci90"] = [float(np.quantile(b, 0.05)), float(np.quantile(b, 0.95))]
    return out


FAV_BANDS = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0001]


def band_label(lo: float, hi: float) -> str:
    if lo == 0.0:
        return f"<{hi:.2f}"
    if hi > 1:
        return f">={lo:.2f}"
    return f"{lo:.2f}-{hi:.2f}"


def fav_table(p: np.ndarray, y: np.ndarray, bands=FAV_BANDS) -> list[dict]:
    """Calibration of the favourite's (argmax) win probability: n, mean predicted, observed hit rate, Wilson 90 %."""
    pf = p.max(1)
    hit = p.argmax(1) == y
    rows = []
    for lo, hi in zip(bands[:-1], bands[1:]):
        sel = (pf >= lo) & (pf < hi)
        n = int(sel.sum())
        if n == 0:
            rows.append({"band": band_label(lo, hi), "n": 0})
            continue
        k = int(hit[sel].sum())
        lo_ci, hi_ci = wilson(k, n)
        rows.append({"band": band_label(lo, hi), "n": n, "mean_pred": round(float(pf[sel].mean()), 4),
                     "observed": round(k / n, 4), "ci90": [round(lo_ci, 4), round(hi_ci, 4)],
                     "gap": round(float(pf[sel].mean()) - k / n, 4)})
    return rows


def fav_ge(p: np.ndarray, y: np.ndarray, thr: float) -> dict:
    pf = p.max(1)
    sel = pf >= thr
    n = int(sel.sum())
    if n == 0:
        return {"threshold": thr, "n": 0}
    k = int((p.argmax(1)[sel] == y[sel]).sum())
    lo, hi = wilson(k, n)
    return {"threshold": thr, "n": n, "mean_pred": round(float(pf[sel].mean()), 4), "observed": round(k / n, 4),
            "ci90": [round(lo, 4), round(hi, 4)]}


def summary_row(p: np.ndarray, y: np.ndarray) -> dict:
    n = len(y)
    if n == 0:
        return {"n": 0}
    return {"n": n, "logloss": round(float(logloss(p, y).mean()), 5), "brier": round(float(brier(p, y).mean()), 5),
            "mean_fav_pred": round(float(p.max(1).mean()), 4),
            "fav_hit": round(float((p.argmax(1) == y).mean()), 4),
            "pred_home": round(float(p[:, 0].mean()), 4), "act_home": round(float((y == 0).mean()), 4),
            "pred_draw": round(float(p[:, 1].mean()), 4), "act_draw": round(float((y == 1).mean()), 4),
            "pred_away": round(float(p[:, 2].mean()), 4), "act_away": round(float((y == 2).mean()), 4)}


# ------------------------------------------------------------------------------------------ odds
def load_closing_odds(db: Path = BACKEND_DIR / "football_intelligence.db",
                      current: Path = BACKEND_DIR / "data" / "external" / "football_data_matches.csv",
                      history: Path = BACKEND_DIR / "data" / "external" / "football_data_history.csv") -> dict:
    """FotMob match id -> de-vigged closing 1X2 [home, draw, away] (p_close_*; Pinnacle closing, else market
    average, else Bet365 closing: chosen upstream in the football-data build). League matches only; there are
    no European closing odds in the sources. Same acceptance rules as train_match_model.load_odds."""
    id_map: dict[str, str] = {}
    if Path(db).exists():
        con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
        try:
            id_map = {r[0]: str(r[1]) for r in con.execute("select id, provider_id from matches")}
        finally:
            con.close()
    out: dict[str, list] = {}
    if Path(current).exists():
        with open(current, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                pid = id_map.get(r.get("db_match_id") or "")
                if pid and r.get("db_score_agrees") == "1" and r.get("p_close_home") and pid not in out:
                    out[pid] = [float(r["p_close_home"]), float(r["p_close_draw"]), float(r["p_close_away"])]
    if Path(history).exists():
        with open(history, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                pid = r.get("fotmob_match_id") or ""
                if (pid and r.get("score_agrees") == "1" and r.get("fotmob_awarded") != "1"
                        and r.get("p_close_home") and pid not in out):
                    out[pid] = [float(r["p_close_home"]), float(r["p_close_draw"]), float(r["p_close_away"])]
    return out


# ------------------------------------------------------------------------------------------ probabilities from mu
def p1x2_from_mu(mu_h: np.ndarray, mu_a: np.ndarray, layer: dict, chunk: int = 5000) -> np.ndarray:
    """1X2 probabilities of the production score model (NB x Dixon-Coles, scores 0..10)."""
    out = np.empty((len(mu_h), 3))
    for i in range(0, len(mu_h), chunk):
        m = T.score_matrix(np.asarray(mu_h[i:i + chunk], float), np.asarray(mu_a[i:i + chunk], float),
                           layer["rho"], layer["nb_dispersion"])
        out[i:i + chunk, 0] = np.tril(m, -1).sum(axis=(1, 2))
        out[i:i + chunk, 1] = np.trace(m, axis1=1, axis2=2)
        out[i:i + chunk, 2] = np.triu(m, 1).sum(axis=(1, 2))
    return out
