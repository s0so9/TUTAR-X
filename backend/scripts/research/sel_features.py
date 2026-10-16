"""Per-match confirmer / uncertainty features for the selective-prediction study (no look-ahead).

For every row of baseline_predictions_full.csv.gz (status ok) computes, from data/history/all_results.db
(read-only) using only results scheduled STRICTLY BEFORE the kick-off:

  * a simple Elo (World-Football-Elo style: K x goal-difference multiplier, home advantage HFA, new team =
    20th percentile of the current ratings of its competition's teams of the last 365 days, else 1500),
    run over the in-history-scope competitions only (same competition set in every period), friendlies,
    awarded results and the production_vs_fixture_status conflict ids excluded. K / HFA are chosen on the
    TRAIN split only (ordered-logit 1X2 log loss of the Elo difference, logit fitted on train rows).
  * last-5 form from all competitive results (friendlies / awarded / conflicts excluded, like the feature
    file): per team W/D/L, goals for/against, and how many of the 5 had >1.5 / >2.5 / >3.5 goals and BTTS.
  * uncertainty: competitive results in the previous 400 days (rating window), results in the same
    competition in the previous 365 days ("new to the league" proxy), match number within the
    competition-season (season labels of all_results.db; unlabeled production rows get a label by a
    >= 45-day gap rule), days since the previous competitive match.

Output: data/research/sel_features.csv.gz (+ sel_elo_report.json). Missing = empty, never 0.
Run (from backend/): OMP_NUM_THREADS=2 venv/Scripts/python.exe scripts/research/sel_features.py
"""

from __future__ import annotations

import csv
import gzip
import sqlite3
import sys
import time
from bisect import bisect_left
from collections import defaultdict, deque
from datetime import timedelta
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sel_common as C  # noqa: E402

RESULTS_DB = C.DATA / "history" / "all_results.db"


def read_results():
    con = sqlite3.connect(f"file:{RESULTS_DB.as_posix()}?mode=ro", uri=True)
    try:
        bad = {r[0] for r in con.execute(
            "select match_provider_id from conflicts where kind = 'production_vs_fixture_status' "
            "and match_provider_id is not null")}
        rows = con.execute(
            "select match_provider_id, competition_provider_id, coalesce(competition_name,''), season, scheduled_at, "
            "home_team_provider_id, away_team_provider_id, home_score, away_score, competition_in_history_scope "
            "from results where awarded is not 1").fetchall()
    finally:
        con.close()
    out = []
    for mid, cp, cname, season, at, h, a, hs, as_, scope in rows:
        if mid in bad or "Friendl" in cname or hs is None or as_ is None:
            continue
        out.append({"id": str(mid), "comp": str(cp), "season": season, "at": C.parse_dt(at), "home": str(h),
                    "away": str(a), "hs": int(hs), "as": int(as_), "scope": int(scope)})
    out.sort(key=lambda r: (r["at"], r["id"]))
    # season labels: keep given labels; unlabeled rows continue the competition's last label unless the
    # competition had no match for >= 45 days (then a new season starts)
    last = {}
    for r in out:
        c = r["comp"]
        prev = last.get(c)
        if r["season"] is not None:
            lab = r["season"]
        elif prev is None:
            lab = "u0"
        else:
            lab = prev[1] if (r["at"] - prev[0]).days < 45 else prev[1] + "+"
        r["season_lab"] = lab
        last[c] = (r["at"], lab)
    return out


def gd_mult(gd: int) -> float:
    gd = abs(gd)
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    return (11 + gd) / 8


def run_elo(results, K: float, HFA: float, init_pct: float = 20.0, default: float = 1500.0):
    """Pre-match (Rh, Ra, n_h, n_a) per result id (in-scope results only)."""
    R: dict[str, float] = {}
    N: dict[str, int] = defaultdict(int)
    comp_teams: dict[str, dict[str, object]] = defaultdict(dict)  # comp -> team -> last date seen
    pre = {}
    for r in results:
        if not r["scope"]:
            continue
        c = r["comp"]
        for t in (r["home"], r["away"]):
            if t not in R:
                ct = comp_teams[c]
                cutoff = r["at"] - timedelta(days=365)
                vals = [R[x] for x, d in ct.items() if d >= cutoff and x in R]
                R[t] = float(np.percentile(vals, init_pct)) if len(vals) >= 6 else default
        rh, ra = R[r["home"]], R[r["away"]]
        pre[r["id"]] = (rh, ra, N[r["home"]], N[r["away"]])
        we = 1.0 / (10 ** (-(rh + HFA - ra) / 400) + 1)
        w = 1.0 if r["hs"] > r["as"] else (0.5 if r["hs"] == r["as"] else 0.0)
        delta = K * gd_mult(r["hs"] - r["as"]) * (w - we)
        R[r["home"]] = rh + delta
        R[r["away"]] = ra - delta
        N[r["home"]] += 1
        N[r["away"]] += 1
        comp_teams[c][r["home"]] = r["at"]
        comp_teams[c][r["away"]] = r["at"]
    return pre


def ordered_logit_fit(x: np.ndarray, y: np.ndarray):
    """P(away) = s(c1 - b x), P(away or draw) = s(c2 - b x); y 0 home, 1 draw, 2 away."""
    def probs(th, x):
        b, c1, dc = th
        c2 = c1 + np.exp(dc)
        s1 = 1 / (1 + np.exp(-(c1 - b * x)))
        s2 = 1 / (1 + np.exp(-(c2 - b * x)))
        return np.stack([1 - s2, s2 - s1, s1], 1)

    def nll(th):
        p = probs(th, x)
        return -np.mean(np.log(np.clip(p[np.arange(len(y)), y], 1e-12, None)))

    res = minimize(nll, np.array([0.005, -0.6, -0.3]), method="Nelder-Mead",
                   options={"xatol": 1e-7, "fatol": 1e-9, "maxiter": 5000})
    return res.x, res.fun, probs


def main() -> None:
    t0 = time.time()
    d = C.load_preds()
    res = read_results()
    print(f"results {len(res)} ({sum(r['scope'] for r in res)} in scope), preds {d['n']}", flush=True)
    y1x2 = np.where(d["hg"] > d["ag"], 0, np.where(d["hg"] == d["ag"], 1, 2))
    tr = d["split"] == "train"
    va = d["split"] == "validation"

    # ---------------------------------------------------------------- Elo grid on train
    grid = []
    best = None
    for K in (15.0, 20.0, 25.0, 30.0, 40.0):
        for HFA in (50.0, 70.0, 90.0):
            pre = run_elo(res, K, HFA)
            have = np.array([m in pre for m in d["match_id"]])
            x = np.array([pre[m][0] + HFA - pre[m][1] if m in pre else np.nan for m in d["match_id"]])
            m_tr = tr & have
            th, ll_tr, probs = ordered_logit_fit(x[m_tr], y1x2[m_tr])
            m_va = va & have
            pv = probs(th, x[m_va])
            ll_va = float(-np.mean(np.log(pv[np.arange(m_va.sum()), y1x2[m_va]])))
            grid.append({"K": K, "HFA": HFA, "train_ll": round(float(ll_tr), 5), "val_ll": round(ll_va, 5),
                         "coverage": round(float(have.mean()), 4)})
            print(grid[-1], flush=True)
            if best is None or ll_tr < best[0]:
                best = (ll_tr, K, HFA, th)
    _, K, HFA, th = best
    pre = run_elo(res, K, HFA)
    x = np.array([pre[m][0] + HFA - pre[m][1] if m in pre else np.nan for m in d["match_id"]])
    _, _, probs = ordered_logit_fit(np.array([0.0]), np.array([0]))
    pe = probs(th, np.nan_to_num(x))
    pe[~np.isfinite(x)] = np.nan
    ll = {}
    for s in ("train", "validation", "test"):
        m = (d["split"] == s) & np.isfinite(x)
        ll[s] = {"elo": round(float(-np.mean(np.log(pe[m][np.arange(m.sum()), y1x2[m]]))), 5),
                 "model": round(float(-np.mean(np.log(np.stack([d["p_home"], d["p_draw"], d["p_away"]], 1)[m][
                     np.arange(m.sum()), y1x2[m]]))), 5), "n": int(m.sum())}
    C.dump({"chosen": {"K": K, "HFA": HFA, "ordered_logit": [float(v) for v in th]}, "grid": grid,
            "logloss_1x2_by_split": ll,
            "note": "test log loss is descriptive only; K/HFA and the logit were chosen/fitted on train"},
           "sel_elo_report.json")
    print("elo chosen", K, HFA, ll, flush=True)

    # ---------------------------------------------------------------- form + uncertainty (all competitive results)
    team_hist: dict[str, list] = defaultdict(list)  # team -> list of (at, gf, ga, comp, season_lab)
    for r in res:
        team_hist[r["home"]].append((r["at"], r["hs"], r["as"], r["comp"], r["season_lab"]))
        team_hist[r["away"]].append((r["at"], r["as"], r["hs"], r["comp"], r["season_lab"]))
    team_times = {t: [h[0] for h in v] for t, v in team_hist.items()}
    season_of = {r["id"]: r["season_lab"] for r in res}

    def team_feats(team: str, ko, comp: str, season_lab):
        hist = team_hist.get(team, [])
        i = bisect_left(team_times.get(team, []), ko)  # results strictly before kick-off
        prev = hist[:i]
        last5 = prev[-5:]
        f = {}
        f["n5"] = len(last5)
        if len(last5) >= 3:
            gf = np.array([h[1] for h in last5])
            ga = np.array([h[2] for h in last5])
            tot = gf + ga
            f.update({"w": int((gf > ga).sum()), "d": int((gf == ga).sum()), "l": int((gf < ga).sum()),
                      "gf": float(gf.mean()), "ga": float(ga.mean()), "o15": int((tot > 1.5).sum()),
                      "o25": int((tot > 2.5).sum()), "o35": int((tot > 3.5).sum()),
                      "btts": int(((gf > 0) & (ga > 0)).sum())})
        lo400 = ko - timedelta(days=400)
        lo365 = ko - timedelta(days=365)
        f["n400"] = sum(1 for h in prev if h[0] >= lo400)
        f["comp365"] = sum(1 for h in prev if h[0] >= lo365 and h[3] == comp)
        f["season_md"] = (sum(1 for h in prev if h[3] == comp and h[4] == season_lab) + 1
                          if season_lab is not None else None)
        f["rest"] = (ko - prev[-1][0]).total_seconds() / 86400 if prev else None
        return f

    cols = ["match_id", "elo_h", "elo_a", "elo_n_h", "elo_n_a", "elo_diff", "elo_p_home", "elo_p_draw",
            "elo_p_away"]
    side_cols = ["n5", "w", "d", "l", "gf", "ga", "o15", "o25", "o35", "btts", "n400", "comp365", "season_md",
                 "rest"]
    cols += [f"{s}_{c}" for s in ("h", "a") for c in side_cols]
    out_rows = []
    for i in range(d["n"]):
        mid = d["match_id"][i]
        ko = C.parse_dt(d["kickoff"][i])
        comp = d["comp"][i]
        lab = season_of.get(mid)
        row = {"match_id": mid}
        if mid in pre:
            rh, ra, nh, na = pre[mid]
            row.update({"elo_h": round(rh, 2), "elo_a": round(ra, 2), "elo_n_h": nh, "elo_n_a": na,
                        "elo_diff": round(rh + HFA - ra, 2), "elo_p_home": round(float(pe[i, 0]), 5),
                        "elo_p_draw": round(float(pe[i, 1]), 5), "elo_p_away": round(float(pe[i, 2]), 5)})
        for s, team in (("h", d["home"][i]), ("a", d["away"][i])):
            f = team_feats(team, ko, comp, lab)
            for c in side_cols:
                v = f.get(c)
                row[f"{s}_{c}"] = "" if v is None else (round(v, 3) if isinstance(v, float) else v)
        out_rows.append(row)
    path = C.OUT / "sel_features.csv.gz"
    with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in out_rows:
            w.writerow({c: r.get(c, "") for c in cols})
    print(f"wrote {path} rows {len(out_rows)} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
