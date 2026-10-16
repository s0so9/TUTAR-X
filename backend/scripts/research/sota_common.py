"""Shared loaders / metrics for the state-of-the-art research scripts (research only, 2026-10-15).

Reads only local files; the app DB is opened read-only (to map football-data `db_match_id` to FotMob ids).
Nothing here is used by the app.
"""
from __future__ import annotations

import csv
import gzip
import math
import sqlite3
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[2]
DATA = BACKEND / "data"
OUT = DATA / "research"
TOP5 = {"E0", "SP1", "D1", "I1", "F1"}


# ------------------------------------------------------------------ metrics (y: 0 home, 1 draw, 2 away)
def logloss(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    return -np.log(np.clip(p[np.arange(len(y)), y], 1e-12, 1))


def rps(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    o = np.zeros_like(p)
    o[np.arange(len(y)), y] = 1
    c1 = p[:, 0] - o[:, 0]
    c2 = p[:, 0] + p[:, 1] - o[:, 0] - o[:, 1]
    return 0.5 * (c1 ** 2 + c2 ** 2)


def brier(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    o = np.zeros_like(p)
    o[np.arange(len(y)), y] = 1
    return ((p - o) ** 2).sum(1)


def summary(p: np.ndarray, y: np.ndarray) -> dict:
    if len(y) == 0:
        return {"n": 0}
    return {"n": int(len(y)),
            "accuracy": round(float((p.argmax(1) == y).mean()), 4),
            "rps": round(float(rps(p, y).mean()), 5),
            "logloss": round(float(logloss(p, y).mean()), 5),
            "brier": round(float(brier(p, y).mean()), 5),
            "draw_pred_mean": round(float(p[:, 1].mean()), 4),
            "draw_actual": round(float((y == 1).mean()), 4),
            "draw_ever_argmax_share": round(float((p.argmax(1) == 1).mean()), 4)}


def paired_ci(a: np.ndarray, b: np.ndarray, n_boot: int = 2000, seed: int = 7) -> dict:
    """mean(a-b) with a 90 % paired bootstrap interval."""
    d = np.asarray(a) - np.asarray(b)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(n_boot, len(d)))
    m = d[idx].mean(1)
    return {"diff": round(float(d.mean()), 5), "ci90": [round(float(np.quantile(m, 0.05)), 5),
                                                        round(float(np.quantile(m, 0.95)), 5)]}


# ------------------------------------------------------------------ odds helpers
def _f(x):
    try:
        v = float(x)
        return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def odds_triplet(r: dict, keys: tuple[str, str, str]):
    o = [_f(r.get(k)) for k in keys]
    return None if any(v is None for v in o) else o


def devig_prop(o):
    q = np.array([1 / v for v in o])
    return q / q.sum()


def devig_shin(o, iters: int = 200):
    """Shin (1993) implied probabilities via the usual fixed-point iteration on z."""
    q = np.array([1 / v for v in o])
    B = q.sum()
    lo, hi = 0.0, 0.5  # bisection on the insider share z so that the probabilities sum to 1
    for _ in range(iters):
        z = (lo + hi) / 2
        p = (np.sqrt(z ** 2 + 4 * (1 - z) * q ** 2 / B) - z) / (2 * (1 - z))
        if p.sum() > 1:
            lo = z
        else:
            hi = z
    return p / p.sum()


def result_index(ftr: str):
    return {"H": 0, "D": 1, "A": 2}.get(ftr)


def load_odds_rows() -> list[dict]:
    """football_data_history.csv (2021/22-2025/26, 14 divisions, FotMob ids) + football_data_matches.csv rows not
    already in the history file (same division/date/home/away)."""
    rows = []
    seen = set()
    with open(DATA / "external" / "football_data_history.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("fotmob_awarded") == "1":
                continue
            r["_src"] = "history"
            key = (r["division"], r["date"], r["home"], r["away"])
            seen.add(key)
            rows.append(r)
    with open(DATA / "external" / "football_data_matches.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key = (r["division"], r["date"], r["home"], r["away"])
            if key in seen:
                continue
            seen.add(key)
            r["_src"] = "current"
            rows.append(r)
    return rows


def fotmob_id_map() -> dict[str, str]:
    db = BACKEND / "football_intelligence.db"
    if not db.exists():
        return {}
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        return {r[0]: str(r[1]) for r in con.execute("select id, provider_id from matches")}
    finally:
        con.close()


def odds_by_fotmob_id(rows: list[dict]) -> dict[str, dict]:
    """FotMob match id -> dict with Pinnacle closing / pre-closing and market-average closing (proportional devig),
    O/U 2.5 closing. Only rows whose score agrees with FotMob."""
    idm = fotmob_id_map()
    out: dict[str, dict] = {}
    for r in rows:
        if r["_src"] == "history":
            pid = r.get("fotmob_match_id") or ""
            ok = r.get("score_agrees") == "1"
        else:
            pid = idm.get(r.get("db_match_id") or "", "")
            ok = r.get("db_score_agrees") == "1"
        if not pid or not ok or pid in out:
            continue
        d = {"division": r["division"]}
        for name, keys in (("ps_close", ("PSCH", "PSCD", "PSCA")), ("ps_pre", ("PSH", "PSD", "PSA")),
                           ("avg_close", ("AvgCH", "AvgCD", "AvgCA")), ("avg_pre", ("AvgH", "AvgD", "AvgA"))):
            o = odds_triplet(r, keys)
            d[name] = devig_prop(o) if o else None
        if r.get("p_close_home"):
            d["close"] = np.array([float(r["p_close_home"]), float(r["p_close_draw"]), float(r["p_close_away"])])
        else:
            d["close"] = None
        if r.get("p_close_over25"):
            d["close_over25"] = float(r["p_close_over25"])
        out[pid] = d
    return out


def read_csv_gz(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fnum(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None
