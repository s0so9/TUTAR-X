"""Walk-forward experiment: ratings fitted on a goals/xG blend.

Training target for matches that have FotMob team xG (data/training/
fotmob_match_details.jsonl): alpha * goals + (1 - alpha) * xG; matches without
xG keep their goals. Every weekly fit sees only matches before the cutoff and
predicts the next 7 days; scoring is always against real goals, on the test
matches that have xG coverage (the leagues the blend can change). The trained
goal layer (config/goal_model.json) is applied to every variant alike.

Usage (from backend/): venv/Scripts/python.exe scripts/training/experiment_xg_ratings.py
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.prediction.goal_model import get_goal_layer  # noqa: E402
from app.prediction.team_ratings import DEFAULT_LOOKBACK_DAYS, GlobalPoissonRatings, domestic_groups  # noqa: E402
import train_goal_model as T  # noqa: E402


def load(db_path: str, details_path: str):
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    rows = con.execute(
        """select m.provider_id, m.home_team_id, m.away_team_id, m.home_score, m.away_score, m.scheduled_at,
                  m.competition_id, coalesce(c.name, '')
           from matches m left join competitions c on c.id = m.competition_id
           where m.status = 'FINISHED' and m.home_score is not null order by m.scheduled_at"""
    ).fetchall()
    con.close()
    xg = {}
    with open(details_path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("home_xg") is not None and r.get("away_xg") is not None:
                xg[str(r["match_provider_id"])] = (float(r["home_xg"]), float(r["away_xg"]))
    data = []
    for pid, h, a, hs, as_, at, cid, cname in rows:
        data.append({"pid": str(pid), "home": h, "away": a, "hs": hs, "as": as_,
                     "at": datetime.fromisoformat(at[:19]), "cid": cid, "cname": cname, "xg": xg.get(str(pid))})
    return data, len(xg)


def run(data, alpha, cutoffs, layer):
    preds = []
    for cut in cutoffs:
        train = [d for d in data if cut - timedelta(days=DEFAULT_LOOKBACK_DAYS) <= d["at"] < cut]
        test = [d for d in data if cut <= d["at"] < cut + timedelta(days=7) and d["xg"] is not None]
        if not test:
            continue
        hy = [alpha * d["hs"] + (1 - alpha) * d["xg"][0] if d["xg"] else d["hs"] for d in train]
        ay = [alpha * d["as"] + (1 - alpha) * d["xg"][1] if d["xg"] else d["as"] for d in train]
        groups = domestic_groups([d["home"] for d in train], [d["away"] for d in train],
                                 [d["cname"] for d in train], [d["cid"] for d in train])
        ratings = GlobalPoissonRatings().fit(
            [d["home"] for d in train], [d["away"] for d in train], hy, ay,
            [(cut - d["at"]).total_seconds() / 86400 for d in train], team_groups=groups)
        for d in test:
            lam = ratings.predict(d["home"], d["away"])
            if lam is None:
                continue
            lh, la = layer.adjust(lam.home, lam.away)
            preds.append({"lh": lh, "la": la, "hs": d["hs"], "as": d["as"], "at": d["at"], "pid": d["pid"]})
    return preds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="football_intelligence.db")
    ap.add_argument("--details", default="data/training/fotmob_match_details.jsonl")
    ap.add_argument("--start", default="2026-01-05")
    ap.add_argument("--end", default="2026-10-12")
    ap.add_argument("--alphas", default="1.0,0.6,0.4,0.2")
    ap.add_argument("--out", default="data/training/xg_experiment.json")
    args = ap.parse_args()

    data, n_xg = load(args.db, args.details)
    layer = get_goal_layer()
    cutoffs = []
    c = datetime.fromisoformat(args.start)
    while c < datetime.fromisoformat(args.end):
        cutoffs.append(c)
        c += timedelta(days=7)
    print(f"{len(data)} matches, {n_xg} with team xG, {len(cutoffs)} weekly cutoffs", flush=True)

    results = {}
    common = None
    runs = {}
    for alpha in [float(x) for x in args.alphas.split(",")]:
        t0 = time.time()
        preds = run(data, alpha, cutoffs, layer)
        runs[alpha] = {p["pid"]: p for p in preds}
        ids = set(runs[alpha])
        common = ids if common is None else common & ids
        print(f"alpha={alpha}: {len(preds)} predictions ({time.time() - t0:.0f}s)", flush=True)

    for alpha, by_id in runs.items():
        rows = [by_id[i] for i in sorted(common)]
        ev = T.evaluate(rows, np.array([r["lh"] for r in rows]), np.array([r["la"] for r in rows]),
                        layer.rho or 0.0, layer.nb_dispersion)
        results[str(alpha)] = {k: round(v, 4) for k, v in ev.items()}
        print(f"alpha={alpha} n={len(rows)} " + " ".join(
            f"{k}={results[str(alpha)][k]}" for k in ("1x2_logloss", "1x2_brier", "over25_logloss", "btts_logloss", "score_logloss")),
            flush=True)
    Path(args.out).write_text(json.dumps({"n_common": len(common), "results": results}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
