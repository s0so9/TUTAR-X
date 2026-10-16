"""Candidate (d), round 2 (2026-10-14): per-club "European offset", strictly as of kick-off.

For every UEFA match the production model has an expected goal difference mu_home - mu_away. A club's residual in a
past UEFA match is (actual - expected) from the club's point of view; the club's offset at kick-off t is the shrunk,
optionally time-decayed mean residual over its PREVIOUS UEFA matches only:

    o_team(t) = sum_j w_j * r_j / (sum_j w_j + k),   w_j = 1 or 0.5 ** ((t - t_j) / half_life),
    over the club's UEFA matches j with t_j <= t - 3 h (a match that has not finished is never used).

Residual metric "gd": r = (goals for - goals against) - (mu_team - mu_opponent).
Residual metric "xgd": r = (xG for - xG against) - (mu_team - mu_opponent); matches without xG are skipped (never
imputed). Only UEFA matches (competition ids 42 / 73 / 10216 and qualifiers) feed the offsets. z = o_home - o_away.
The offset enters the 1X2 as a shift of the log expected-goal ratio, d' = d + h + gamma * z (calibration_fixes).

No look-ahead: a match's own result and every later match are never used for that match (checked by
tests/test_calibration_candidate.py on synthetic data). xG values are labels of PAST matches only.
"""

from __future__ import annotations

import csv
import gzip
from pathlib import Path
from typing import Optional

import numpy as np

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calibration_common as C  # noqa: E402

GUARD_DAYS = 3.0 / 24.0  # a past match counts only if it started at least 3 hours before this kick-off

METRICS = ("gd", "xgd")
K_GRID = (3.0, 6.0, 12.0, 24.0)
HALF_LIFE_GRID = (None, 730.0)


def load_xg(path: Path = C.DATA / "match_features_full.csv.gz") -> dict:
    """match_id -> (home xG, away xG) for European matches; None when FotMob sent none (never imputed)."""
    out: dict = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["comp_type"] != "european":
                continue
            h, a = C.fnum(r["y_home_xg"]), C.fnum(r["y_away_xg"])
            out[r["match_id"]] = (h, a) if h is not None and a is not None else None
    return out


def day_numbers(kickoff) -> np.ndarray:
    return np.array([np.datetime64(k, "s").astype("int64") for k in kickoff], dtype=float) / 86400.0


def home_view_residual(d: dict, xg: Optional[dict], metric: str) -> np.ndarray:
    """(actual - expected) goal / xG difference from the home side's view; NaN when the metric is unavailable."""
    egd = d["mu_h"] - d["mu_a"]
    if metric == "gd":
        return (d["hg"] - d["ag"]) - egd
    if xg is None:
        raise ValueError("xgd needs the xG table")
    res = np.full(d["n"], np.nan)
    for i, m in enumerate(d["match_id"]):
        v = xg.get(m)
        if v is not None:
            res[i] = (v[0] - v[1]) - egd[i]
    return res


def _team_history(d: dict, res_home: np.ndarray, day: np.ndarray) -> dict:
    """team id -> (times, residuals from the team's view), UEFA rows with a finite residual, sorted by time."""
    hist: dict[str, list] = {}
    for i in np.where(d["euro"])[0]:
        if not np.isfinite(res_home[i]):
            continue
        hist.setdefault(d["home_id"][i], []).append((day[i], res_home[i]))
        hist.setdefault(d["away_id"][i], []).append((day[i], -res_home[i]))
    out = {}
    for t, v in hist.items():
        v.sort()
        out[t] = (np.array([x[0] for x in v]), np.array([x[1] for x in v]))
    return out


def team_offset(hist: dict, team: str, as_of_day: float, k: float, half_life: Optional[float]):
    """(offset, effective n, raw n) of ``team`` using only its matches that started <= as_of_day - 3 h."""
    v = hist.get(team)
    if v is None:
        return 0.0, 0.0, 0
    t, r = v
    m = t <= as_of_day - GUARD_DAYS
    if not m.any():
        return 0.0, 0.0, 0
    w = np.ones(int(m.sum())) if half_life is None else 0.5 ** ((as_of_day - t[m]) / half_life)
    n_eff = float(w.sum())
    return float((w * r[m]).sum() / (n_eff + k)), n_eff, int(m.sum())


def build_z(d: dict, metric: str, k: float, half_life: Optional[float], xg: Optional[dict] = None,
            res_home: Optional[np.ndarray] = None) -> np.ndarray:
    """z[i] = o_home - o_away as of the kick-off of row i (0 for rows that are not UEFA matches)."""
    day = day_numbers(d["kickoff"])
    if res_home is None:
        res_home = home_view_residual(d, xg, metric)
    hist = _team_history(d, res_home, day)
    z = np.zeros(d["n"])
    for i in np.where(d["euro"])[0]:
        oh = team_offset(hist, d["home_id"][i], day[i], k, half_life)[0]
        oa = team_offset(hist, d["away_id"][i], day[i], k, half_life)[0]
        z[i] = oh - oa
    return z


def offsets_as_of(d: dict, metric: str, k: float, half_life: Optional[float], as_of: str,
                  xg: Optional[dict] = None) -> dict:
    """Runtime table: team id -> {offset, n_effective, n_matches, last_match} using matches before ``as_of``."""
    day = day_numbers(d["kickoff"])
    res_home = home_view_residual(d, xg, metric)
    hist = _team_history(d, res_home, day)
    as_of_day = float(np.datetime64(as_of, "s").astype("int64")) / 86400.0
    out = {}
    for t, (times, _r) in hist.items():
        o, n_eff, n = team_offset(hist, t, as_of_day, k, half_life)
        if n:
            last = times[times <= as_of_day - GUARD_DAYS].max()
            out[t] = {"offset": round(o, 5), "n_effective": round(n_eff, 3), "n_matches": n,
                      "last_match": str(np.datetime64(int(round(last * 86400)), "s"))[:10]}
    return out
