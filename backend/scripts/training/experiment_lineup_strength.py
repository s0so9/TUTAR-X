"""Walk-forward experiment: does the starting XI's form add information?

For each match with FotMob line-ups (data/training/fotmob_match_details.jsonl):
  * XI value  v = ln(V_home / V_away), V = starters' market value (the production
    squad-value signal, beta fitted on European cups only so far);
  * XI form   q = (Q_home - U_home) - (Q_away - U_away), where Q is the mean of
    the starters' minutes-weighted FotMob rating over their matches BEFORE this
    kickoff and U the team's average Q over its previous line-ups (so q measures
    a weaker/stronger XI than usual: injuries, rotation, suspensions).
Out-of-sample rating lambdas come from data/training/walkforward_lambdas.csv,
passed through the trained goal layer. Supremacy is adjusted in log space:
d' = d + beta*v/2... fitted by maximum likelihood on matches before --split and
scored on the rest against real goals.

Usage (from backend/): venv/Scripts/python.exe scripts/training/experiment_lineup_strength.py
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import sys
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.prediction.goal_model import get_goal_layer  # noqa: E402
import train_goal_model as T  # noqa: E402

MIN_PRIOR_MINUTES = 180
USUAL_WINDOW = 10


def lineup_features(details_path: str):
    records = []
    with open(details_path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            records.append(r)
    records.sort(key=lambda r: r["scheduled_at"])

    player_sum = defaultdict(float)   # rating * minutes
    player_min = defaultdict(float)
    team_q = defaultdict(lambda: deque(maxlen=USUAL_WINDOW))
    out = {}
    for r in records:
        sides = {"home": [], "away": []}
        for p in r.get("players") or []:
            if p.get("is_starter") and p.get("team_side") in sides:
                sides[p["team_side"]].append(p)
        q = {}
        for side, starters in sides.items():
            vals = [player_sum[p["player_id"]] / player_min[p["player_id"]]
                    for p in starters if player_min[p["player_id"]] >= MIN_PRIOR_MINUTES]
            q[side] = float(np.mean(vals)) if len(vals) >= 7 else None   # need most of the XI known
        team_h, team_a = str(r["home_team_provider_id"]), str(r["away_team_provider_id"])
        usual_h = float(np.mean(team_q[team_h])) if len(team_q[team_h]) >= 3 else None
        usual_a = float(np.mean(team_q[team_a])) if len(team_q[team_a]) >= 3 else None
        form = None
        if None not in (q["home"], q["away"], usual_h, usual_a):
            form = (q["home"] - usual_h) - (q["away"] - usual_a)
        vh, va = r.get("home_starters_market_value"), r.get("away_starters_market_value")
        value = math.log(vh / va) if vh and va else None
        out[str(r["match_provider_id"])] = {"form": form, "value": value}
        # update histories AFTER computing this match's features (no look-ahead)
        if q["home"] is not None:
            team_q[team_h].append(q["home"])
        if q["away"] is not None:
            team_q[team_a].append(q["away"])
        for p in r.get("players") or []:
            if p.get("rating") is not None and p.get("minutes_played"):
                player_sum[p["player_id"]] += float(p["rating"]) * float(p["minutes_played"])
                player_min[p["player_id"]] += float(p["minutes_played"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="football_intelligence.db")
    ap.add_argument("--details", default="data/training/fotmob_match_details.jsonl")
    ap.add_argument("--lambdas", default="data/training/walkforward_lambdas.csv")
    ap.add_argument("--split", default="2026-07-01")
    ap.add_argument("--out", default="data/training/lineup_experiment.json")
    args = ap.parse_args()

    feats = lineup_features(args.details)
    con = sqlite3.connect(f"file:{Path(args.db).as_posix()}?mode=ro", uri=True)
    id_to_pid = dict(con.execute("select id, provider_id from matches"))
    con.close()
    layer = get_goal_layer()

    rows = []
    with open(args.lambdas, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pid = str(id_to_pid.get(r["match_id"]))
            fe = feats.get(pid)
            if not fe or fe["form"] is None or fe["value"] is None:
                continue
            lh, la = layer.adjust(float(r["lambda_home"]), float(r["lambda_away"]))
            rows.append({"lh": lh, "la": la, "hs": int(r["home_score"]), "as": int(r["away_score"]),
                         "at": datetime.fromisoformat(r["kickoff"]), "form": fe["form"], "value": fe["value"]})
    split = datetime.fromisoformat(args.split)
    train = [x for x in rows if x["at"] < split]
    test = [x for x in rows if x["at"] >= split]
    print(f"rows with both features: {len(rows)} (train {len(train)}, test {len(test)})")

    def apply(rs, beta, gamma):
        lh = np.array([x["lh"] for x in rs]); la = np.array([x["la"] for x in rs])
        shift = beta * np.array([x["value"] for x in rs]) + gamma * np.array([x["form"] for x in rs])
        return lh * np.exp(shift), la * np.exp(-shift)

    def nll(theta, rs, use):
        beta = theta[0] if "value" in use else 0.0
        gamma = theta[1] if "form" in use else 0.0
        lh, la = apply(rs, beta, gamma)
        hs = np.clip(np.array([x["hs"] for x in rs]), 0, T.MAX_GOALS)
        as_ = np.clip(np.array([x["as"] for x in rs]), 0, T.MAX_GOALS)
        m = T.score_matrix(lh, la, layer.rho or 0.0, layer.nb_dispersion)
        return -np.sum(np.log(np.clip(m[np.arange(len(rs)), hs, as_], 1e-12, 1)))

    report = {}
    for name, use in (("ratings_only", ()), ("value", ("value",)), ("form", ("form",)), ("value+form", ("value", "form"))):
        if use:
            res = minimize(lambda t: nll(t, train, use), np.zeros(2), method="L-BFGS-B", bounds=[(-1, 1), (-3, 3)])
            beta = float(res.x[0]) if "value" in use else 0.0
            gamma = float(res.x[1]) if "form" in use else 0.0
        else:
            beta = gamma = 0.0
        lh, la = apply(test, beta, gamma)
        ev = T.evaluate(test, lh, la, layer.rho or 0.0, layer.nb_dispersion)
        report[name] = {"beta_value": round(beta, 4), "gamma_form": round(gamma, 4),
                        **{k: round(ev[k], 4) for k in ("1x2_logloss", "1x2_brier", "over25_logloss", "btts_logloss", "score_logloss")}}
        print(name, report[name], flush=True)
    Path(args.out).write_text(json.dumps({"n_train": len(train), "n_test": len(test), "results": report}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
