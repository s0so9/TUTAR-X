"""As-of player impact ratings: xG-RAPM with a box-score prior (stage A, step 2).

Method and leakage guards: docs/training/player-impact-pipeline.md. In short:

For every cutoff date c (default every 7 days) the model is fitted ONLY on stints
(scripts/training/build_stints.py) of matches that kicked off strictly before c, with
exponential time decay (weight = stint minutes * 0.5 ** (age_days / half_life)). Box-score
features are computed from the same matches (details JSONL, kickoff < c).

xG-RAPM (weighted ridge regression). One row per stint and attacking direction:

  y = 90 * npxG_A / minutes                      (npxG per 90 of the attacking side A)
  y ~ mu + home + comp(c) + man_adv + lead/trail share
        [+ team_off(A) - team_def(D)]                     optional team intercepts
        + sum_{p in A on pitch} (z_p . g_off + d_off_p)   offence of A's players
        - sum_{q in D on pitch} (z_q . g_def + d_def_q)   defence of D's players

  z_p    = box-score prior features of player p as of c (shrunk npxG/90, xA/90, FotMob
           rating, log market value, market value missing, minutes share; standardised)
  g      = prior weights, fitted jointly (tiny ridge)  ->  prior_p = z_p . g
  d_p    = player deviations from the prior, ridge penalty lambda (tuned)

  offence_p = prior_off_p + d_off_p   (xG/90 the player adds to his side; + = better)
  defence_p = prior_def_p + d_def_p   (xG/90 the player removes from the opponent; + = better)

Opponent and league strength: the defending players enter every row, so the opponent is
adjusted for directly. League strength enters through the players: the prior carries the
market value (a cross-league quality scale) and European-cup matches tie the leagues
together; competition intercepts absorb each competition's scoring level. Team intercepts
(identifying players only from within-team line-up variation) are an option; the
time-forward validation of 2026-10-13 preferred the model WITHOUT them (team-intercept
models predicted next-period stint xG worse), so the default is lambda_team = 1e7 (off).

The ridge strength lambda, the half-life and lambda_team are tuned by time-forward
validation: fit before cutoff v, predict the stint xG rates of [v, v + window) and compare
the duration-weighted squared error with a team/intercept-only model and the prior-only
model.

Simple comparison metrics (as of c, same decay): shrunk npxG/90 + xA/90, minutes share of
the current team's last 10 matches, minutes-weighted FotMob rating.

Outputs:
  data/training/player_impact_asof.csv.gz   one row per (cutoff, player seen before cutoff)
  data/training/player_impact_meta.json     hyper-parameters, validation scores, prior weights,
                                            replacement levels per position and cutoff

Usage (from backend/):
  venv/Scripts/python.exe scripts/training/player_impact.py \
      --stints data/training/stints.jsonl.gz \
      --details data/training/fotmob_match_details.jsonl
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
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import LinearOperator, cg

BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "data" / "training"
DEFAULT_STINTS = DATA_DIR / "stints.jsonl.gz"
DEFAULT_DETAILS = DATA_DIR / "fotmob_match_details.jsonl"
DEFAULT_OUT = DATA_DIR / "player_impact_asof.csv.gz"
DEFAULT_META = DATA_DIR / "player_impact_meta.json"

POSITIONS = ("GK", "DEF", "MID", "FWD")
POSITION_ID = {0: "GK", 1: "DEF", 2: "MID", 3: "FWD"}
# No position dummies: every line-up has one goalkeeper and ten outfield players, so position
# constants are not identified (they trade off against the intercept) and would give goalkeepers
# arbitrary absolute values. Position still drives the shrinkage targets and replacement levels.
PRIOR_FEATURES = ("npxg90", "xa90", "rating", "log_market_value", "market_value_missing", "minutes_share")
FIXED_COLUMNS = ("intercept", "home", "man_adv", "lead_share", "trail_share")

SHRINK_MINUTES = 450.0        # box-score shrinkage: add 450 minutes of the position average
USUAL_TEAM_MATCHES = 10       # minutes share = share of the team's last 10 matches
FRINGE_MINUTES = 450.0        # replacement level = players with < 450 raw minutes before c
LAMBDA_FIXED = 1e-3           # intercept, home, man advantage, game state
LAMBDA_COMP = 10.0            # competition intercepts (light: only stabilises small competitions)
# Team intercepts. A team-level effect T costs lambda_team * T^2 as a team intercept but only
# about lambda_player * T^2 / 11 when spread over eleven regulars, so lambda_team must stay well
# below lambda_player / 11 for the intercepts (not the players) to absorb team level. A huge
# value switches team intercepts off (pure player model). Validation on 2026-10-13 (10 cutoffs,
# 28-day windows): off (1e7) < 1000 < 10 in prediction error, so the default is off.
LAMBDA_TEAM = 1e7
LAMBDA_PRIOR = 10.0           # prior weights g (dense columns, effectively unpenalised)
EPOCH = date(1970, 1, 1)


def to_day(iso: str) -> float:
    """ISO timestamp -> fractional days since 1970-01-01 (UTC)."""
    s = iso.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp() / 86400.0


def day_to_date(day: float) -> str:
    return (EPOCH + timedelta(days=int(math.floor(day + 1e-9)))).isoformat()


def date_to_day(d: str) -> float:
    return float((date.fromisoformat(d) - EPOCH).days)


# --------------------------------------------------------------------------- data

@dataclass
class Stints:
    match_id: np.ndarray        # str
    day: np.ndarray             # kickoff, days since epoch
    duration: np.ndarray
    comp: np.ndarray            # competition index
    home_team: np.ndarray       # team index
    away_team: np.ndarray
    target_home: np.ndarray     # npxG (or xG) of the home side in the stint
    target_away: np.ndarray
    man_adv: np.ndarray         # n_home - n_away
    lead_home: np.ndarray       # minutes with home leading
    trail_home: np.ndarray
    home_inc: sp.csr_matrix     # stints x players incidence (home side on pitch)
    away_inc: sp.csr_matrix
    player_ids: np.ndarray      # player index -> FotMob id
    team_ids: np.ndarray        # team index -> FotMob id
    comp_ids: np.ndarray        # comp index -> FotMob league id
    read_stats: dict = field(default_factory=dict)


def load_stints(paths: list[Path], target: str = "npxg", player_index: Optional[dict] = None) -> Stints:
    """Usable stints with xG from one or more stints files (first occurrence of (match, seg) wins)."""
    stats = Counter()
    seen = set()
    recs = []
    for path in paths:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    stats["unparsable_lines"] += 1
                    continue
                key = (r.get("match_id"), r.get("seg"))
                if key in seen:
                    stats["duplicate_stints"] += 1
                    continue
                seen.add(key)
                if not r.get("usable"):
                    stats["skipped_not_usable"] += 1
                    continue
                if not r.get("xg_available") or r.get(f"home_{target}") is None:
                    stats["skipped_no_xg"] += 1
                    continue
                if not r.get("duration") or r["duration"] <= 0:
                    stats["skipped_zero_duration"] += 1
                    continue
                recs.append(r)
    recs.sort(key=lambda r: (r["kickoff"], r["match_id"], r["seg"]))
    stats["stints"] = len(recs)
    stats["matches"] = len({r["match_id"] for r in recs})

    pidx = {} if player_index is None else dict(player_index)
    tidx: dict[int, int] = {}
    cidx: dict[int, int] = {}

    def idx(d: dict, key) -> int:
        if key not in d:
            d[key] = len(d)
        return d[key]

    n = len(recs)
    day = np.empty(n)
    dur = np.empty(n)
    comp = np.empty(n, dtype=np.int64)
    ht = np.empty(n, dtype=np.int64)
    at = np.empty(n, dtype=np.int64)
    th = np.empty(n)
    ta = np.empty(n)
    man = np.empty(n)
    lead = np.empty(n)
    trail = np.empty(n)
    h_ptr, h_idx, a_ptr, a_idx = [0], [], [0], []
    mids = []
    for i, r in enumerate(recs):
        day[i] = to_day(r["kickoff"])
        dur[i] = r["duration"]
        comp[i] = idx(cidx, r["competition_id"])
        ht[i] = idx(tidx, r["home_team_id"])
        at[i] = idx(tidx, r["away_team_id"])
        th[i] = r[f"home_{target}"]
        ta[i] = r[f"away_{target}"]
        man[i] = r["man_adv"]
        lead[i] = r["home_lead_minutes"]
        trail[i] = r["home_trail_minutes"]
        h_idx.extend(idx(pidx, p) for p in r["home_players"])
        a_idx.extend(idx(pidx, p) for p in r["away_players"])
        h_ptr.append(len(h_idx))
        a_ptr.append(len(a_idx))
        mids.append(r["match_id"])
    n_players = len(pidx)
    home_inc = sp.csr_matrix((np.ones(len(h_idx)), np.array(h_idx, dtype=np.int64), np.array(h_ptr)), shape=(n, n_players))
    away_inc = sp.csr_matrix((np.ones(len(a_idx)), np.array(a_idx, dtype=np.int64), np.array(a_ptr)), shape=(n, n_players))
    inv = lambda d: np.array([k for k, _ in sorted(d.items(), key=lambda kv: kv[1])])  # noqa: E731
    return Stints(np.array(mids), day, dur, comp, ht, at, th, ta, man, lead, trail, home_inc, away_inc,
                  inv(pidx), inv(tidx), inv(cidx), dict(stats))


@dataclass
class Appearances:
    """Per player-match box-score rows (appeared players), sorted by kickoff."""
    day: np.ndarray
    match_key: np.ndarray       # int index of the match
    player: np.ndarray          # player index (shared with Stints)
    team: np.ndarray            # FotMob team id
    minutes: np.ndarray
    match_minutes: np.ndarray   # 90, or 120 with extra time (largest minutes_played seen)
    npxg: np.ndarray            # nan = unknown (match without shot data)
    xa: np.ndarray
    rating: np.ndarray
    position: np.ndarray        # 0..3, -1 unknown
    market_value: np.ndarray    # nan unknown
    team_rank: np.ndarray       # k-th match of this team (0-based, chronological)
    team_idx: np.ndarray        # compact team index of the row
    team_days: list             # team index -> sorted kickoff days of the team's matches


def load_appearances(paths: list[Path], player_index: dict) -> tuple[Appearances, dict]:
    """Box-score rows from fotmob_match_details-style JSONL files.

    Zero rule (README_fotmob_details.md): FotMob omits npxG/xA for a player without a shot /
    chance. In a match with team xG (shot data), a player who appeared with stats gets 0 for an
    omitted npxG/xA; in a match without shot data both stay unknown (nan).
    """
    stats = Counter()
    seen = set()
    rows = []
    for path in paths:
        with open(path, "rb") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    mid = str(r["match_provider_id"])
                except (ValueError, KeyError, TypeError):
                    stats["unparsable_lines"] += 1
                    continue
                if mid in seen:
                    stats["duplicate_matches"] += 1
                    continue
                seen.add(mid)
                if r.get("awarded"):
                    continue
                has_xg = r.get("home_xg") is not None and r.get("away_xg") is not None
                players = r.get("players") or []
                mins = [p.get("minutes_played") for p in players if p.get("minutes_played") is not None]
                match_minutes = 120.0 if mins and max(mins) > 100 else 90.0
                kday = to_day(r["scheduled_at"])
                for p in players:
                    m = p.get("minutes_played")
                    if not m or m <= 0 or p.get("player_id") is None:
                        continue
                    stats_ok = bool(p.get("stats_available"))
                    npxg = p.get("npxg")
                    xa = p.get("xa")
                    if has_xg and stats_ok:
                        npxg = 0.0 if npxg is None else float(npxg)
                        xa = 0.0 if xa is None else float(xa)
                    else:
                        npxg = math.nan
                        xa = math.nan
                    rows.append((kday, mid, p["player_id"], p.get("team_provider_id"), float(m), match_minutes,
                                 npxg, xa, math.nan if p.get("rating") is None else float(p["rating"]),
                                 p.get("usual_position_id"), p.get("market_value")))
    rows.sort(key=lambda t: (t[0], t[1], t[2]))
    pidx = player_index
    match_keys: dict[str, int] = {}
    n = len(rows)
    out = {k: np.empty(n) for k in ("day", "minutes", "match_minutes", "npxg", "xa", "rating", "market_value")}
    player = np.empty(n, dtype=np.int64)
    team = np.empty(n, dtype=np.int64)
    pos = np.empty(n, dtype=np.int64)
    mkey = np.empty(n, dtype=np.int64)
    for i, (kday, mid, pid, tid, m, mm, npxg, xa, rating, upos, mv) in enumerate(rows):
        if pid not in pidx:
            pidx[pid] = len(pidx)
        if mid not in match_keys:
            match_keys[mid] = len(match_keys)
        out["day"][i] = kday
        out["minutes"][i] = m
        out["match_minutes"][i] = mm
        out["npxg"][i] = npxg
        out["xa"][i] = xa
        out["rating"][i] = rating
        out["market_value"][i] = float(mv) if mv else math.nan
        player[i] = pidx[pid]
        team[i] = -1 if tid is None else int(tid)
        pos[i] = upos if upos in POSITION_ID else -1
        mkey[i] = match_keys[mid]
    # chronological rank of each (team, match)
    tix: dict[int, int] = {}
    team_idx = np.empty(n, dtype=np.int64)
    for i in range(n):
        t = int(team[i])
        if t not in tix:
            tix[t] = len(tix)
        team_idx[i] = tix[t]
    team_matches: list[list] = [[] for _ in tix]
    seen_tm = set()
    for i in range(n):
        key = (team_idx[i], mkey[i])
        if key not in seen_tm:
            seen_tm.add(key)
            team_matches[team_idx[i]].append((out["day"][i], int(mkey[i])))
    rank_of = {}
    for t, lst in enumerate(team_matches):
        lst.sort()
        for k, (_d, m) in enumerate(lst):
            rank_of[(t, m)] = k
    team_rank = np.array([rank_of[(int(team_idx[i]), int(mkey[i]))] for i in range(n)], dtype=np.int64)
    team_days = [np.array([d for d, _ in lst]) for lst in team_matches]
    stats["appearances"] = n
    stats["matches"] = len(match_keys)
    return Appearances(out["day"], mkey, player, team, out["minutes"], out["match_minutes"], out["npxg"],
                       out["xa"], out["rating"], pos, out["market_value"], team_rank, team_idx,
                       team_days), dict(stats)


# --------------------------------------------------------------------------- box-score features

@dataclass
class BoxFeatures:
    known: np.ndarray            # bool per player index: appeared before the cutoff
    minutes: np.ndarray          # raw minutes before cutoff (all competitions)
    minutes_decayed: np.ndarray
    xg_minutes: np.ndarray       # raw minutes in matches with shot data
    n_apps: np.ndarray
    npxg90: np.ndarray
    xa90: np.ndarray
    rating: np.ndarray
    market_value: np.ndarray     # latest known (nan unknown)
    position: np.ndarray         # latest known usual position (-1 unknown)
    team: np.ndarray             # latest team (-1 unknown)
    minutes_share: np.ndarray
    Z: np.ndarray                # standardised prior features (n_players x F)
    z_mean: np.ndarray
    z_std: np.ndarray
    replacement_z: dict          # position -> feature vector of a fringe player


def box_features(app: Appearances, n_players: int, cutoff_day: float, half_life: float) -> BoxFeatures:
    m = app.day < cutoff_day
    w = np.power(0.5, (cutoff_day - app.day[m]) / half_life)
    pl = app.player[m]
    mins = app.minutes[m]
    bc = lambda v: np.bincount(pl, weights=v, minlength=n_players)  # noqa: E731
    minutes = bc(mins)
    minutes_dec = bc(w * mins)
    n_apps = np.bincount(pl, minlength=n_players).astype(float)
    known = n_apps > 0

    xg_ok = ~np.isnan(app.npxg[m])
    xg_min_dec = bc(w * mins * xg_ok)
    xg_minutes = bc(mins * xg_ok)
    npxg_sum = bc(np.where(xg_ok, w * app.npxg[m], 0.0))
    xa_sum = bc(np.where(xg_ok, w * app.xa[m], 0.0))
    r_ok = ~np.isnan(app.rating[m])
    rated_min = bc(w * mins * r_ok)
    rating_sum = bc(np.where(r_ok, w * mins * app.rating[m], 0.0))

    # latest row per player (rows are sorted by kickoff): position, market value, team
    rows = np.nonzero(m)[0]

    def latest(valid: np.ndarray) -> np.ndarray:
        last = np.full(n_players, -1, dtype=np.int64)
        r = rows[valid]
        np.maximum.at(last, app.player[r], r)
        return last

    last_pos = latest(app.position[rows] >= 0)
    position = np.where(last_pos >= 0, app.position[np.maximum(last_pos, 0)], -1)
    last_mv = latest(~np.isnan(app.market_value[rows]))
    market_value = np.where(last_mv >= 0, app.market_value[np.maximum(last_mv, 0)], np.nan)
    last_any = latest(np.ones(len(rows), dtype=bool))
    team = np.where(last_any >= 0, app.team[np.maximum(last_any, 0)], -1)

    # position-level averages for shrinkage (per minute)
    pos_rate_npxg, pos_rate_xa, pos_rating = {}, {}, {}
    for k in (-1, 0, 1, 2, 3):
        sel = known & ((position == k) if k >= 0 else np.ones(n_players, dtype=bool))
        pos_rate_npxg[k] = npxg_sum[sel].sum() / max(xg_min_dec[sel].sum(), 1e-9)
        pos_rate_xa[k] = xa_sum[sel].sum() / max(xg_min_dec[sel].sum(), 1e-9)
        pos_rating[k] = rating_sum[sel].sum() / max(rated_min[sel].sum(), 1e-9)
    prn = np.array([pos_rate_npxg[k] for k in position])
    prx = np.array([pos_rate_xa[k] for k in position])
    prr = np.array([pos_rating[k] for k in position])
    K = SHRINK_MINUTES
    npxg90 = 90.0 * (npxg_sum + K * prn) / (xg_min_dec + K)
    xa90 = 90.0 * (xa_sum + K * prx) / (xg_min_dec + K)
    rating = (rating_sum + K * prr) / (rated_min + K)

    # minutes share of the player's latest team over that team's last N matches before the cutoff
    n_before = np.array([int(np.searchsorted(d, cutoff_day, side="left")) for d in app.team_days], dtype=np.int64)
    ti = app.team_idx[rows]
    latest_team_idx = np.where(last_any >= 0, app.team_idx[np.maximum(last_any, 0)], -1)
    in_window = (app.team_rank[rows] >= n_before[ti] - USUAL_TEAM_MATCHES) & (ti == latest_team_idx[app.player[rows]])
    num = np.bincount(app.player[rows][in_window], weights=app.minutes[rows][in_window], minlength=n_players)
    nb = np.where(latest_team_idx >= 0, np.minimum(n_before[np.maximum(latest_team_idx, 0)], USUAL_TEAM_MATCHES), 0)
    share = np.where(nb > 0, num / (90.0 * np.maximum(nb, 1)), 0.0)
    share = np.clip(share, 0.0, 1.34)  # 120-minute matches can exceed 90 per match

    log_mv = np.log(np.where(np.isnan(market_value), np.nan, np.maximum(market_value, 1.0)))
    mv_missing = np.isnan(log_mv).astype(float)
    for k in (-1, 0, 1, 2, 3):
        sel = known & (position == k) & ~np.isnan(log_mv)
        fill = float(np.median(log_mv[sel])) if sel.any() else float(np.nanmedian(log_mv[known])) if np.any(~np.isnan(log_mv[known])) else 0.0
        log_mv = np.where(np.isnan(log_mv) & (position == k), fill, log_mv)
    raw = np.column_stack([npxg90, xa90, rating, log_mv, mv_missing, share])
    wts = np.where(known, minutes_dec, 0.0)
    if wts.sum() <= 0:
        wts = known.astype(float)
    mean = (raw[known] * wts[known, None]).sum(0) / max(wts[known].sum(), 1e-9)
    var = ((raw[known] - mean) ** 2 * wts[known, None]).sum(0) / max(wts[known].sum(), 1e-9)
    std = np.sqrt(np.maximum(var, 1e-12))
    Z = np.where(known[:, None], (raw - mean) / std, 0.0)

    replacement = {}
    fringe = known & (minutes < FRINGE_MINUTES)
    for k, name in [(-1, "UNK"), (0, "GK"), (1, "DEF"), (2, "MID"), (3, "FWD")]:
        sel = fringe & ((position == k) if k >= 0 else np.ones(n_players, dtype=bool))
        if sel.sum() < 5:
            sel = fringe
        replacement[name] = Z[sel].mean(0) if sel.any() else np.zeros(Z.shape[1])
    return BoxFeatures(known, minutes, minutes_dec, xg_minutes, n_apps, npxg90, xa90, rating, market_value,
                       position, team, share, Z, mean, std, replacement)


# --------------------------------------------------------------------------- model

@dataclass
class Layout:
    n_fixed: int
    n_comp: int
    n_team: int
    n_feat: int
    n_players: int

    @property
    def comp0(self): return self.n_fixed
    @property
    def toff0(self): return self.comp0 + self.n_comp
    @property
    def tdef0(self): return self.toff0 + self.n_team
    @property
    def goff0(self): return self.tdef0 + self.n_team
    @property
    def gdef0(self): return self.goff0 + self.n_feat
    @property
    def doff0(self): return self.gdef0 + self.n_feat
    @property
    def ddef0(self): return self.doff0 + self.n_players
    @property
    def n(self): return self.ddef0 + self.n_players


def design(st: Stints, sel: np.ndarray, Z: np.ndarray, lay: Layout, use_players: bool = True,
           use_prior: bool = True, use_teams: bool = True) -> sp.csr_matrix:
    """Design matrix of the selected stints: rows [home attacking ; away attacking]."""
    n = len(sel)
    dur = st.duration[sel]
    Hi = st.home_inc[sel]
    Ai = st.away_inc[sel]
    ones = np.ones(n)
    lead = st.lead_home[sel] / dur
    trail = st.trail_home[sel] / dur
    fixed = np.vstack([
        np.column_stack([ones, ones, st.man_adv[sel], lead, trail]),
        np.column_stack([ones, 0 * ones, -st.man_adv[sel], trail, lead]),
    ])
    blocks = [sp.csr_matrix(fixed)]
    rows2 = np.arange(2 * n)
    comp = np.concatenate([st.comp[sel], st.comp[sel]])
    blocks.append(sp.csr_matrix((np.ones(2 * n), (rows2, comp)), shape=(2 * n, lay.n_comp)))
    att = np.concatenate([st.home_team[sel], st.away_team[sel]])
    dfn = np.concatenate([st.away_team[sel], st.home_team[sel]])
    tval = 1.0 if use_teams else 0.0
    blocks.append(sp.csr_matrix((np.full(2 * n, tval), (rows2, att)), shape=(2 * n, lay.n_team)))
    blocks.append(sp.csr_matrix((np.full(2 * n, -tval), (rows2, dfn)), shape=(2 * n, lay.n_team)))
    pval = 1.0 if use_prior else 0.0
    zh = Hi @ Z
    za = Ai @ Z
    blocks.append(sp.csr_matrix(pval * np.vstack([zh, za])))
    blocks.append(sp.csr_matrix(-pval * np.vstack([za, zh])))
    if use_players:
        blocks.append(sp.vstack([Hi, Ai]).tocsr())
        blocks.append(-sp.vstack([Ai, Hi]).tocsr())
    else:
        empty = sp.csr_matrix((2 * n, lay.n_players))
        blocks += [empty, empty]
    return sp.hstack(blocks, format="csr")


def response(st: Stints, sel: np.ndarray) -> np.ndarray:
    dur = st.duration[sel]
    return np.concatenate([90.0 * st.target_home[sel] / dur, 90.0 * st.target_away[sel] / dur])


def penalties(lay: Layout, lam_player: float, lam_team: float) -> np.ndarray:
    lam = np.empty(lay.n)
    lam[:lay.n_fixed] = LAMBDA_FIXED
    lam[lay.comp0:lay.toff0] = LAMBDA_COMP
    lam[lay.toff0:lay.goff0] = lam_team
    lam[lay.goff0:lay.doff0] = LAMBDA_PRIOR
    lam[lay.doff0:] = lam_player
    return lam


def solve(X: sp.csr_matrix, y: np.ndarray, w: np.ndarray, lam: np.ndarray, x0: Optional[np.ndarray] = None,
          rtol: float = 1e-8, maxiter: int = 5000) -> tuple[np.ndarray, dict]:
    """Weighted ridge with per-column penalties: (X'WX + diag(lam)) b = X'Wy, Jacobi-preconditioned CG."""
    Xt = X.T.tocsr()
    b = Xt @ (w * y)
    diag = np.asarray(X.multiply(X).T @ w).ravel() + lam
    n = X.shape[1]
    A = LinearOperator((n, n), matvec=lambda v: Xt @ (w * (X @ v)) + lam * v, dtype=float)
    M = LinearOperator((n, n), matvec=lambda v: v / diag, dtype=float)
    it = [0]

    def cb(_xk):
        it[0] += 1

    beta, info = cg(A, b, x0=x0, rtol=rtol, maxiter=maxiter, M=M, callback=cb)
    resid = float(np.linalg.norm(A.matvec(beta) - b) / max(np.linalg.norm(b), 1e-300))
    return beta, {"cg_info": int(info), "iterations": it[0], "rel_residual": resid}


@dataclass
class Fit:
    cutoff_day: float
    beta: np.ndarray
    lay: Layout
    box: BoxFeatures
    train_sel: np.ndarray
    info: dict
    lam_player: float
    half_life: float
    lam_team: float


def fit_cutoff(st: Stints, app: Appearances, cutoff_day: float, lam_player: float, half_life: float,
               lookback_days: float, x0: Optional[np.ndarray] = None, mode: str = "full",
               lam_team: float = None, box: Optional[BoxFeatures] = None) -> Fit:
    """mode: full | prior_only (no player deviations) | team_only (no player terms at all)."""
    lam_team = LAMBDA_TEAM if lam_team is None else lam_team
    n_players = len(st.player_ids)
    if box is None:
        box = box_features(app, n_players, cutoff_day, half_life)
    sel = np.nonzero((st.day < cutoff_day) & (st.day >= cutoff_day - lookback_days))[0]
    lay = Layout(len(FIXED_COLUMNS), len(st.comp_ids), len(st.team_ids), box.Z.shape[1], n_players)
    X = design(st, sel, box.Z, lay, use_players=mode == "full", use_prior=mode != "team_only")
    y = response(st, sel)
    decay = np.power(0.5, (cutoff_day - st.day[sel]) / half_life)
    w = np.concatenate([st.duration[sel] * decay, st.duration[sel] * decay])
    lam = penalties(lay, lam_player, lam_team)
    beta, info = solve(X, y, w, lam, x0=x0)
    info.update({"rows": int(X.shape[0]), "stints": int(len(sel)), "columns": int(X.shape[1]), "nnz": int(X.nnz)})
    return Fit(cutoff_day, beta, lay, box, sel, info, lam_player, half_life, lam_team)


def player_values(fit: Fit) -> dict[str, np.ndarray]:
    lay, b, Z = fit.lay, fit.beta, fit.box.Z
    g_off = b[lay.goff0:lay.gdef0]
    g_def = b[lay.gdef0:lay.doff0]
    prior_off = Z @ g_off
    prior_def = Z @ g_def
    return {
        "prior_offence": prior_off, "prior_defence": prior_def,
        "offence": prior_off + b[lay.doff0:lay.ddef0], "defence": prior_def + b[lay.ddef0:lay.n],
        "g_off": g_off, "g_def": g_def,
    }


def replacement_levels(fit: Fit) -> dict:
    lay, b = fit.lay, fit.beta
    g_off = b[lay.goff0:lay.gdef0]
    g_def = b[lay.gdef0:lay.doff0]
    return {pos: {"offence": float(z @ g_off), "defence": float(z @ g_def)} for pos, z in fit.box.replacement_z.items()}


def predict(st: Stints, sel: np.ndarray, fit: Fit, positions: np.ndarray) -> np.ndarray:
    """Predicted y for stints `sel` from a fit at an earlier cutoff. Players unseen before the
    cutoff get the replacement-level prior features of their position (no deviation)."""
    Z = fit.box.Z.copy()
    unknown = ~fit.box.known
    for k, name in [(-1, "UNK"), (0, "GK"), (1, "DEF"), (2, "MID"), (3, "FWD")]:
        mask = unknown & (positions == k)
        if mask.any():
            Z[mask] = fit.box.replacement_z[name]
    X = design(st, sel, Z, fit.lay, use_players=True, use_prior=True)
    return X @ fit.beta


# --------------------------------------------------------------------------- validation

def first_positions(app: Appearances, n_players: int) -> np.ndarray:
    """Usual position of each player from his first appearance row (pre-match line-up info)."""
    pos = np.full(n_players, -1, dtype=np.int64)
    for i in range(len(app.day) - 1, -1, -1):  # earliest row wins
        if app.position[i] >= 0:
            pos[app.player[i]] = app.position[i]
    return pos


def config_key(hl: float, lam_team: float, mode: str, lam: Optional[float]) -> str:
    return f"hl{hl:g}_team{lam_team:g}_{mode}" + (f"_lam{lam:g}" if lam is not None else "")


def parse_config_key(key: str) -> dict:
    parts = key.split("_")
    out = {"half_life": float(parts[0][2:]), "lam_team": float(parts[1][4:])}
    if "_lam" in key:
        out["lam_player"] = float(key.split("_lam")[1])
    return out


def decomposed_predictions(st: Stints, sel: np.ndarray, fit: Fit, positions: np.ndarray,
                           pred_full: np.ndarray) -> dict[str, np.ndarray]:
    """Predictions of the full fit with parts of the player terms switched off (validation only).

    no_def_dev  : defence deviations d_def = 0 (defence = box-score prior only)
    no_off_dev  : offence deviations d_off = 0
    no_dev      : both deviations 0 (= the prior part of this fit)
    no_def      : no defence term at all (g_def = 0 and d_def = 0)
    Each variant is re-centred to the full prediction's weighted mean over the same rows (a
    constant computed from predictions only, never from outcomes), so the comparison measures how
    well the removed part separates players, not a level shift.
    """
    lay = fit.lay
    w = np.concatenate([st.duration[sel], st.duration[sel]])
    out = {}
    for name, zero_ranges in (("no_def_dev", [(lay.ddef0, lay.n)]),
                              ("no_off_dev", [(lay.doff0, lay.ddef0)]),
                              ("no_dev", [(lay.doff0, lay.n)]),
                              ("no_def", [(lay.gdef0, lay.doff0), (lay.ddef0, lay.n)])):
        b = fit.beta.copy()
        for a, z in zero_ranges:
            b[a:z] = 0.0
        alt = Fit(fit.cutoff_day, b, fit.lay, fit.box, fit.train_sel, fit.info, fit.lam_player, fit.half_life,
                  fit.lam_team)
        pred = predict(st, sel, alt, positions)
        pred = pred + float(np.sum(w * (pred_full - pred)) / max(np.sum(w), 1e-12))
        out[name] = pred
    return out


def time_forward_validation(st: Stints, app: Appearances, val_cutoffs: list[float], window_days: float,
                            lambdas: list[float], half_lives: list[float], team_lambdas: list[float],
                            lookback_days: float, log=None, decompose: bool = False) -> dict:
    """decompose=True adds, for every full fit, the error of the same fit with deviations / defence
    switched off (keys ``..._decomp-<variant>_lam<l>``; see decomposed_predictions)."""
    log = log or (lambda msg: print(msg, flush=True))
    positions = first_positions(app, len(st.player_ids))
    results = defaultdict(lambda: {"sse": 0.0, "w": 0.0, "per_cutoff": []})
    for c in val_cutoffs:
        test = np.nonzero((st.day >= c) & (st.day < c + window_days))[0]
        if len(test) == 0:
            continue
        y = response(st, test)
        w = np.concatenate([st.duration[test], st.duration[test]])
        for hl in half_lives:
            box = box_features(app, len(st.player_ids), c, hl)
            for lt in team_lambdas:
                configs = [("team_only", None), ("prior_only", None)] + [("full", lam) for lam in lambdas]
                x0 = None
                for mode, lam in configs:
                    t0 = time.time()
                    fit = fit_cutoff(st, app, c, lam if lam is not None else 1e12, hl, lookback_days,
                                     x0=x0 if mode == "full" else None, mode=mode, lam_team=lt, box=box)
                    if mode == "full":
                        x0 = fit.beta  # warm start for the next lambda (same layout)
                    pred = predict(st, test, fit, positions)
                    sse = float(np.sum(w * (y - pred) ** 2))
                    key = config_key(hl, lt, mode, lam)
                    res = results[key]
                    res["sse"] += sse
                    res["w"] += float(w.sum())
                    res["per_cutoff"].append({"cutoff": day_to_date(c), "wmse": round(sse / float(w.sum()), 6),
                                              "n_test_stints": int(len(test)), "cg_iter": fit.info["iterations"]})
                    log(f"  val {day_to_date(c)} {key}: wmse={sse / w.sum():.5f} it={fit.info['iterations']} "
                        f"({time.time() - t0:.1f}s)")
                    if decompose and mode == "full":
                        for vname, vpred in decomposed_predictions(st, test, fit, positions, pred).items():
                            vsse = float(np.sum(w * (y - vpred) ** 2))
                            vres = results[config_key(hl, lt, f"decomp-{vname}", lam)]
                            vres["sse"] += vsse
                            vres["w"] += float(w.sum())
                            vres["per_cutoff"].append({"cutoff": day_to_date(c),
                                                       "wmse": round(vsse / float(w.sum()), 6),
                                                       "n_test_stints": int(len(test))})
    out = {}
    for key, res in results.items():
        out[key] = {"wmse": res["sse"] / res["w"], "per_cutoff": res["per_cutoff"]}
    return out


# --------------------------------------------------------------------------- main

def cutoff_days(start: str, end: Optional[str], step: int, last_day: float) -> list[float]:
    d0 = date_to_day(start)
    stop = date_to_day(end) if end else math.floor(last_day) + 1.0
    out = []
    d = d0
    while d <= stop + 1e-9:
        out.append(d)
        d += step
    if out[-1] < stop - 1e-9:
        out.append(stop)
    return out


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def deviation_stats(vals: dict, known: np.ndarray, rapm_minutes: np.ndarray, min_minutes: float = 900.0) -> dict:
    """How far the fitted ratings move away from the box-score prior (deviation = rating - prior).

    sd over all known players and over "regulars" (>= ``min_minutes`` stint minutes in the fit
    window); ``dev_share_var`` = var(deviation) / var(rating) among the regulars."""
    out = {}
    reg = known & (rapm_minutes >= min_minutes)
    for side in ("offence", "defence"):
        dev = vals[side] - vals[f"prior_{side}"]
        out[f"sd_dev_{side}"] = round(float(np.std(dev[known])), 5) if known.any() else None
        if reg.sum() >= 2:
            out[f"sd_dev_{side}_regulars"] = round(float(np.std(dev[reg])), 5)
            out[f"sd_prior_{side}_regulars"] = round(float(np.std(vals[f"prior_{side}"][reg])), 5)
            out[f"sd_{side}_regulars"] = round(float(np.std(vals[side][reg])), 5)
            tot = float(np.var(vals[side][reg]))
            out[f"dev_share_var_{side}_regulars"] = round(float(np.var(dev[reg])) / tot, 4) if tot > 0 else None
    out["n_regulars"] = int(reg.sum())
    out["regulars_min_rapm_minutes"] = min_minutes
    return out


OUT_FIELDS = ["cutoff", "player_id", "team_id", "position", "minutes", "minutes_decayed", "xg_minutes",
              "rapm_minutes", "n_apps", "offence", "defence", "prior_offence", "prior_defence",
              "npxg90", "xa90", "xgxa90", "rating", "minutes_share", "market_value", "flags"]


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="As-of xG-RAPM player ratings with a box-score prior")
    ap.add_argument("--stints", action="append", type=Path)
    ap.add_argument("--details", action="append", type=Path)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--meta", type=Path, default=DEFAULT_META)
    ap.add_argument("--target", choices=("npxg", "xg"), default="npxg")
    ap.add_argument("--start", default="2025-09-01", help="first cutoff (YYYY-MM-DD)")
    ap.add_argument("--end", default=None, help="last cutoff (default: day after the last stint)")
    ap.add_argument("--step-days", type=int, default=7)
    ap.add_argument("--lookback-days", type=float, default=730.0)
    ap.add_argument("--lookbacks", default=None,
                    help="comma-separated look-back grid (days) for the tuning; the chosen one is used for the "
                         "cutoff fits (default: --lookback-days only). Validation keys get an 'lb<days>_' prefix "
                         "when more than one look-back is compared")
    ap.add_argument("--lambdas", default="4000,8000,16000,32000,64000")
    ap.add_argument("--half-lives", default="180,365")
    ap.add_argument("--team-lambdas", default="1000,1e7",
                    help="team-intercept ridge values to compare (1e7 = no team intercepts)")
    ap.add_argument("--val-start", default="2026-01-05")
    ap.add_argument("--val-end", default=None, help="last validation cutoff (default: 4 weeks before the data end)")
    ap.add_argument("--val-step-days", type=int, default=28)
    ap.add_argument("--val-window-days", type=float, default=28.0)
    ap.add_argument("--lambda", dest="fixed_lambda", type=float, default=None,
                    help="skip tuning: use this lambda (needs --half-life too)")
    ap.add_argument("--half-life", dest="fixed_half_life", type=float, default=None)
    ap.add_argument("--team-lambda", dest="fixed_team_lambda", type=float, default=LAMBDA_TEAM)
    ap.add_argument("--decompose", action="store_true",
                    help="validation: also score every full fit with deviations / defence switched off")
    args = ap.parse_args(argv)

    t_start = time.time()
    stint_paths = args.stints or [DEFAULT_STINTS]
    detail_paths = args.details or [DEFAULT_DETAILS]
    st = load_stints(stint_paths, args.target)
    pidx = {int(p): i for i, p in enumerate(st.player_ids)}
    app, app_stats = load_appearances(detail_paths, pidx)
    # players present only in the details (never in a usable xG stint) extend the index
    if len(pidx) > len(st.player_ids):
        extra = len(pidx) - len(st.player_ids)
        st.home_inc = sp.csr_matrix((st.home_inc.data, st.home_inc.indices, st.home_inc.indptr),
                                    shape=(st.home_inc.shape[0], len(pidx)))
        st.away_inc = sp.csr_matrix((st.away_inc.data, st.away_inc.indices, st.away_inc.indptr),
                                    shape=(st.away_inc.shape[0], len(pidx)))
        st.player_ids = np.array([k for k, _ in sorted(pidx.items(), key=lambda kv: kv[1])])
        print(f"{extra} players appear only in the details (no usable xG stint)", flush=True)
    print(f"stints {st.read_stats} | appearances {app_stats} | players {len(st.player_ids)} "
          f"teams {len(st.team_ids)} comps {len(st.comp_ids)} ({time.time() - t_start:.1f}s)", flush=True)

    last_day = float(st.day.max())
    lambdas = [float(x) for x in args.lambdas.split(",") if x]
    half_lives = [float(x) for x in args.half_lives.split(",") if x]
    team_lambdas = [float(x) for x in args.team_lambdas.split(",") if x]
    validation = {}
    best_key = None
    lookbacks = [float(x) for x in args.lookbacks.split(",") if x] if args.lookbacks else [args.lookback_days]
    lookback = args.lookback_days
    val_cutoffs = []
    if args.fixed_lambda is not None and args.fixed_half_life is not None:
        best_lam, best_hl, best_lt = args.fixed_lambda, args.fixed_half_life, args.fixed_team_lambda
        print(f"tuning skipped: lambda={best_lam} half_life={best_hl} team_lambda={best_lt} "
              f"lookback={lookback:g}", flush=True)
    else:
        val_end = date_to_day(args.val_end) if args.val_end else math.floor(last_day) + 1 - args.val_window_days
        d = date_to_day(args.val_start)
        while d <= val_end + 1e-9:
            val_cutoffs.append(d)
            d += args.val_step_days
        print(f"time-forward validation on {len(val_cutoffs)} cutoffs "
              f"({day_to_date(val_cutoffs[0])} .. {day_to_date(val_cutoffs[-1])}), window {args.val_window_days} d, "
              f"look-backs {lookbacks}", flush=True)
        for lb in lookbacks:
            res = time_forward_validation(st, app, val_cutoffs, args.val_window_days, lambdas, half_lives,
                                          team_lambdas, lb, decompose=args.decompose)
            prefix = f"lb{lb:g}_" if len(lookbacks) > 1 else ""
            validation.update({prefix + k: v for k, v in res.items()})
        full = {k: v for k, v in validation.items() if "_full_" in k}
        best_key = min(full, key=lambda k: full[k]["wmse"])
        rest = best_key
        if len(lookbacks) > 1:
            lb_part, rest = best_key.split("_", 1)
            lookback = float(lb_part[2:])
        else:
            lookback = lookbacks[0]
        chosen = parse_config_key(rest)
        best_lam, best_hl, best_lt = chosen["lam_player"], chosen["half_life"], chosen["lam_team"]
        print("validation wmse:", json.dumps({k: round(v["wmse"], 5) for k, v in sorted(validation.items())}),
              flush=True)
        print(f"chosen: {best_key} (lookback {lookback:g} d)", flush=True)

    cutoffs = cutoff_days(args.start, args.end, args.step_days, last_day)
    print(f"fitting {len(cutoffs)} cutoffs {day_to_date(cutoffs[0])} .. {day_to_date(cutoffs[-1])} "
          f"(lambda={best_lam:g}, half_life={best_hl:g}, team_lambda={best_lt:g}, lookback={lookback:g})", flush=True)
    # stream the rows into a gzip temp file (deterministic: mtime 0, no file name) and rename at the
    # end; the multi-season run writes millions of rows, which must not sit in memory as one string
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = args.out.with_name(args.out.name + f".tmp{os.getpid()}")
    raw_fh = open(tmp_out, "wb")
    gz_fh = gzip.GzipFile(filename="", mode="wb", fileobj=raw_fh, mtime=0, compresslevel=9)
    buf = io.TextIOWrapper(gz_fh, encoding="utf-8", newline="")
    wr = csv.writer(buf, lineterminator="\n")
    wr.writerow(OUT_FIELDS)
    per_cutoff = []
    n_rows = 0
    prev_beta = None
    for c in cutoffs:
        t0 = time.time()
        fit = fit_cutoff(st, app, c, best_lam, best_hl, lookback, x0=prev_beta, lam_team=best_lt)
        prev_beta = fit.beta
        vals = player_values(fit)
        box = fit.box
        rapm_minutes = np.asarray((st.home_inc[fit.train_sel].T @ st.duration[fit.train_sel])
                                  + (st.away_inc[fit.train_sel].T @ st.duration[fit.train_sel])).ravel()
        cut = day_to_date(c)
        for p in np.nonzero(box.known)[0]:
            flags = []
            if rapm_minutes[p] <= 0:
                flags.append("prior_only")
            if box.xg_minutes[p] <= 0:
                flags.append("no_xg_data")
            if np.isnan(box.market_value[p]):
                flags.append("market_value_missing")
            if box.position[p] < 0:
                flags.append("position_unknown")
            mv = box.market_value[p]
            wr.writerow([
                cut, int(st.player_ids[p]), int(box.team[p]), POSITION_ID.get(int(box.position[p]), ""),
                round(float(box.minutes[p]), 1), round(float(box.minutes_decayed[p]), 1),
                round(float(box.xg_minutes[p]), 1), round(float(rapm_minutes[p]), 1), int(box.n_apps[p]),
                f"{vals['offence'][p]:.5f}", f"{vals['defence'][p]:.5f}",
                f"{vals['prior_offence'][p]:.5f}", f"{vals['prior_defence'][p]:.5f}",
                f"{box.npxg90[p]:.4f}", f"{box.xa90[p]:.4f}", f"{box.npxg90[p] + box.xa90[p]:.4f}",
                f"{box.rating[p]:.4f}", f"{box.minutes_share[p]:.4f}",
                "" if np.isnan(mv) else int(mv), ";".join(flags),
            ])
            n_rows += 1
        lay = fit.lay
        b = fit.beta
        per_cutoff.append({
            "cutoff": cut, **fit.info, "players_rated": int(box.known.sum()),
            "fixed": {name: round(float(b[i]), 5) for i, name in enumerate(FIXED_COLUMNS)},
            "prior_weights_offence": {f: round(float(v), 5) for f, v in zip(PRIOR_FEATURES, vals["g_off"])},
            "prior_weights_defence": {f: round(float(v), 5) for f, v in zip(PRIOR_FEATURES, vals["g_def"])},
            "feature_mean": {f: round(float(v), 5) for f, v in zip(PRIOR_FEATURES, box.z_mean)},
            "feature_std": {f: round(float(v), 5) for f, v in zip(PRIOR_FEATURES, box.z_std)},
            "replacement_level": {k: {kk: round(vv, 5) for kk, vv in v.items()} for k, v in replacement_levels(fit).items()},
            "sd_offence": round(float(np.std(vals["offence"][box.known])), 5),
            "sd_defence": round(float(np.std(vals["defence"][box.known])), 5),
            **deviation_stats(vals, box.known, rapm_minutes),
            "seconds": round(time.time() - t0, 1),
        })
        print(f"cutoff {cut}: stints={fit.info['stints']} players={int(box.known.sum())} "
              f"cg_iter={fit.info['iterations']} resid={fit.info['rel_residual']:.1e} ({time.time() - t0:.1f}s)",
              flush=True)

    buf.flush()
    buf.detach()
    gz_fh.close()
    raw_fh.flush()
    os.fsync(raw_fh.fileno())
    raw_fh.close()
    os.replace(tmp_out, args.out)
    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": {"stints": [str(p) for p in stint_paths], "details": [str(p) for p in detail_paths]},
        "stints_read": st.read_stats, "appearances_read": app_stats,
        "target": args.target,
        "units": "offence/defence in xG per 90 minutes added (offence) or removed from the opponent (defence) "
                 "relative to an average player; + is better for both",
        "hyper_parameters": {
            "lambda_player": best_lam, "half_life_days": best_hl, "lambda_team": best_lt,
            "lookback_days": lookback,
            "lambda_fixed": LAMBDA_FIXED, "lambda_competition": LAMBDA_COMP,
            "lambda_prior_weights": LAMBDA_PRIOR, "shrink_minutes": SHRINK_MINUTES,
            "usual_team_matches_for_minutes_share": USUAL_TEAM_MATCHES, "fringe_minutes": FRINGE_MINUTES,
            "prior_features": list(PRIOR_FEATURES), "fixed_columns": list(FIXED_COLUMNS),
            "cutoffs": {"start": args.start, "end": day_to_date(cutoffs[-1]), "step_days": args.step_days,
                        "n": len(cutoffs)},
            "grid": {"lambdas": lambdas, "half_lives": half_lives, "team_lambdas": team_lambdas,
                     "lookbacks": lookbacks},
            "chosen_by_validation": best_key,
        },
        "validation": {
            "method": "fit on stints before cutoff v, predict stint npxG/90 of [v, v + window); duration-weighted "
                      "squared error (wmse); team_only = no player terms, prior_only = player priors without "
                      "deviations, full = prior + ridge deviations; team1e+07 = team intercepts switched off",
            "val_start": args.val_start, "val_step_days": args.val_step_days, "window_days": args.val_window_days,
            "val_cutoffs": [day_to_date(v) for v in val_cutoffs],
            "last_window_end": (day_to_date(val_cutoffs[-1] + args.val_window_days) if val_cutoffs else None),
            "wmse": {k: round(v["wmse"], 6) for k, v in sorted(validation.items())},
            "per_cutoff": {k: v["per_cutoff"] for k, v in sorted(validation.items())},
        },
        "per_cutoff": per_cutoff,
        "rows": n_rows,
        "seconds": round(time.time() - t_start, 1),
        "leakage_guards": [
            "every fit uses stints with kickoff < cutoff only",
            "box-score features (npxG/90, xA/90, rating, minutes share, market value, position) use details rows "
            "with kickoff < cutoff only",
            "validation predicts stints with kickoff >= cutoff from a fit at that cutoff",
            "players unseen before the cutoff get the replacement-level prior of their position",
        ],
    }
    _atomic_write(args.meta, json.dumps(meta, indent=1).encode("utf-8"))
    print(f"wrote {n_rows} rows -> {args.out}; meta -> {args.meta} ({time.time() - t_start:.0f}s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
