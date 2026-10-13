"""Does the starting XI's RAPM strength vs the usual XI explain goals beyond the rating lambda?

Stage A, step 4 of the player-impact pipeline (docs/training/player-impact-pipeline.md).

Rows: matches of data/training/walkforward_lambdas_xg.csv (out-of-sample rating lambdas,
weekly cutoffs; optionally more lambda files, e.g. walkforward_lambdas_xg_2025h2.csv) that
have FotMob line-ups in the details JSONL. Lambdas pass through the trained goal layer
(config/goal_model.json), exactly as in experiment_lineup_strength.py.

Features per match (no information from the match itself or later, except its starting
XIs, which are known before kick-off):
  * RAPM ratings of the latest cutoff c <= kickoff (fitted on matches before c);
  * XI strength O, D of each side = sum of the starters' offence / defence; unrated players get
    the replacement level of their position;
  * usual XI = mean strength of the team's last N (10) starting XIs before this kickoff, valued
    with the SAME cutoff c (difference = personnel, not rating drift); needs >= 3 line-ups;
  * dO, dD = XI minus usual.
  rapm_split:  log lh += k (dO_home - dD_away),  log la += k (dO_away - dD_home)
  rapm_net:    supremacy s = k ((dO_h + dD_h) - (dO_a + dD_a)) / 2;  lh e^s, la e^-s
  rapm_prior_*: the same with the prior part of the ratings only (no RAPM deviations)
  simple metrics (mean over the XI minus usual, as supremacy): shrunk npxG+xA per 90, minutes
  share, shrunk FotMob rating (all from the ratings file, same cutoff rule)
  production: value = ln(V_home / V_away) of the starters' market value, form = FotMob-rating XI
  quality vs usual (re-implemented from experiment_lineup_strength.py and checked against it)

Coefficients are fitted by maximum likelihood on goals of matches before --split and scored on
the rest (1X2 / over 2.5 / BTTS / exact-score log loss). Paired bootstrap of the held-out 1X2
log-loss difference gives a confidence interval.

Usage (from backend/):
  venv/Scripts/python.exe scripts/training/experiment_xi_impact.py
  venv/Scripts/python.exe scripts/training/experiment_xi_impact.py \
      --lambdas data/training/walkforward_lambdas_xg_2025h2.csv --lambdas data/training/walkforward_lambdas_xg.csv \
      --out data/training/xi_impact_experiment_extended.json
"""

from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import json
import math
import os
import sqlite3
import sys
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.optimize import minimize
from scipy.stats import chi2

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.prediction.goal_model import get_goal_layer  # noqa: E402
import train_goal_model as T  # noqa: E402

DATA = BACKEND_DIR / "data" / "training"
# production lineup-form definition (experiment_lineup_strength.py / build_player_form.py)
FORM_MIN_PRIOR_MINUTES = 180
FORM_USUAL_WINDOW = 10
FORM_MIN_KNOWN = 7
POSITION_ID = {0: "GK", 1: "DEF", 2: "MID", 3: "FWD"}
FRINGE_MINUTES = 450.0


# --------------------------------------------------------------------------- inputs

def read_details(paths: list[Path]) -> list[dict]:
    seen, out = set(), []
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
                    continue
                if mid in seen or r.get("awarded"):
                    continue
                seen.add(mid)
                out.append(r)
    out.sort(key=lambda r: (r["scheduled_at"], str(r["match_provider_id"])))
    return out


def production_features(records: list[dict]) -> dict[str, dict]:
    """XI value and XI form exactly as experiment_lineup_strength.lineup_features (merged records)."""
    player_sum = defaultdict(float)
    player_min = defaultdict(float)
    team_q = defaultdict(lambda: deque(maxlen=FORM_USUAL_WINDOW))
    out = {}
    for r in records:
        sides = {"home": [], "away": []}
        for p in r.get("players") or []:
            if p.get("is_starter") and p.get("team_side") in sides:
                sides[p["team_side"]].append(p)
        q = {}
        for side, starters in sides.items():
            vals = [player_sum[p["player_id"]] / player_min[p["player_id"]]
                    for p in starters if player_min[p["player_id"]] >= FORM_MIN_PRIOR_MINUTES]
            q[side] = float(np.mean(vals)) if len(vals) >= FORM_MIN_KNOWN else None
        th, ta = str(r["home_team_provider_id"]), str(r["away_team_provider_id"])
        uh = float(np.mean(team_q[th])) if len(team_q[th]) >= 3 else None
        ua = float(np.mean(team_q[ta])) if len(team_q[ta]) >= 3 else None
        form = None
        if None not in (q["home"], q["away"], uh, ua):
            form = (q["home"] - uh) - (q["away"] - ua)
        vh, va = r.get("home_starters_market_value"), r.get("away_starters_market_value")
        value = math.log(vh / va) if vh and va else None
        out[str(r["match_provider_id"])] = {"form": form, "value": value}
        if q["home"] is not None:
            team_q[th].append(q["home"])
        if q["away"] is not None:
            team_q[ta].append(q["away"])
        for p in r.get("players") or []:
            if p.get("rating") is not None and p.get("minutes_played"):
                player_sum[p["player_id"]] += float(p["rating"]) * float(p["minutes_played"])
                player_min[p["player_id"]] += float(p["minutes_played"])
    return out


METRIC_COLS = ("offence", "defence", "prior_offence", "prior_defence", "xgxa90", "minutes_share", "rating")


def read_ratings(path: Path, meta_path: Optional[Path]) -> tuple[list[str], dict, dict]:
    """cutoff -> {player_id: tuple(METRIC_COLS)} and cutoff -> {position: replacement tuple}."""
    by_cut: dict[str, dict] = defaultdict(dict)
    fringe: dict[str, dict] = defaultdict(lambda: defaultdict(list))
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            vals = tuple(float(row[k]) for k in METRIC_COLS)
            by_cut[row["cutoff"]][row["player_id"]] = vals
            if float(row["minutes"]) < FRINGE_MINUTES:
                fringe[row["cutoff"]][row["position"] or "UNK"].append(vals)
                fringe[row["cutoff"]]["*"].append(vals)
    meta_repl = {}
    if meta_path and meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        for e in meta.get("per_cutoff") or []:
            meta_repl[e["cutoff"]] = e.get("replacement_level") or {}
    repl: dict[str, dict] = {}
    for cut, groups in fringe.items():
        allv = np.array(groups["*"])
        repl[cut] = {}
        for pos in ("GK", "DEF", "MID", "FWD", "UNK"):
            pool = np.array(groups[pos]) if len(groups.get(pos, [])) >= 5 else allv
            vals = list(pool.mean(0))
            m = meta_repl.get(cut, {}).get(pos)
            if m:  # the training script's own replacement level for the RAPM columns
                vals[0], vals[1] = m["offence"], m["defence"]
            repl[cut][pos] = tuple(vals)
    return sorted(by_cut), by_cut, repl


def db_id_map(db_path: Path) -> dict[str, str]:
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        return {r[0]: str(r[1]) for r in con.execute("select id, provider_id from matches")}
    finally:
        con.close()


# --------------------------------------------------------------------------- features

def xi_features(records: list[dict], cutoffs: list[str], ratings: dict, repl: dict, usual_n: int,
                min_usual: int) -> dict[str, dict]:
    """Per match: XI-minus-usual deltas of every metric column, per side (home/away)."""
    team_hist: dict[int, list] = defaultdict(list)   # team -> [(kickoff, starters, positions)]
    for r in records:
        for side, team in (("home", r["home_team_provider_id"]), ("away", r["away_team_provider_id"])):
            starters = [p for p in r.get("players") or [] if p.get("is_starter") and p.get("team_side") == side]
            if starters:
                team_hist[team].append((r["scheduled_at"], [str(p["player_id"]) for p in starters],
                                        {str(p["player_id"]): POSITION_ID.get(p.get("usual_position_id"), "UNK")
                                         for p in starters}))
    for lst in team_hist.values():
        lst.sort(key=lambda t: t[0])
    keys = {t: [k for k, _s, _p in lst] for t, lst in team_hist.items()}

    def strength(cut: str, ids: list[str], pos: dict) -> tuple[np.ndarray, int]:
        tab, rp = ratings[cut], repl[cut]
        tot = np.zeros(len(METRIC_COLS))
        unknown = 0
        for pid in ids:
            v = tab.get(pid)
            if v is None:
                unknown += 1
                v = rp.get(pos.get(pid, "UNK")) or rp["UNK"]
            tot += np.asarray(v)
        return tot, unknown

    out = {}
    for r in records:
        kick = r["scheduled_at"]
        kday = kick[:10]
        i = bisect.bisect_right(cutoffs, kday) - 1
        if i < 0:
            continue
        cut = cutoffs[i]
        feats = {"cutoff": cut}
        ok = True
        for side, team in (("home", r["home_team_provider_id"]), ("away", r["away_team_provider_id"])):
            starters = [p for p in r.get("players") or [] if p.get("is_starter") and p.get("team_side") == side]
            if len(starters) != 11:
                ok = False
                break
            ids = [str(p["player_id"]) for p in starters]
            pos = {str(p["player_id"]): POSITION_ID.get(p.get("usual_position_id"), "UNK") for p in starters}
            j = bisect.bisect_left(keys[team], kick)          # lineups strictly before this kickoff
            prev = team_hist[team][max(0, j - usual_n):j]
            if len(prev) < min_usual:
                ok = False
                break
            xi, unk = strength(cut, ids, pos)
            usual = np.zeros(len(METRIC_COLS))
            unk_usual = 0
            n_usual_players = 0
            for _k, pids, ppos in prev:
                s, u = strength(cut, pids, ppos)
                usual += s / len(pids) * 11.0      # scale to an 11-man XI
                unk_usual += u
                n_usual_players += len(pids)
            usual /= len(prev)
            d = xi - usual
            for k, col in enumerate(METRIC_COLS):
                feats[f"{side}_d_{col}"] = float(d[k])
            feats[f"{side}_unknown"] = unk
            feats[f"{side}_usual_unknown_share"] = unk_usual / max(n_usual_players, 1)
        if ok:
            out[str(r["match_provider_id"])] = feats
    return out


# --------------------------------------------------------------------------- models

def shifts(rows: list[dict], spec: dict, theta: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Log-lambda shifts of the home and away side for a variant spec and coefficients theta."""
    sh = np.zeros(len(rows))
    sa = np.zeros(len(rows))
    for k, (kind, name) in enumerate(spec["terms"]):
        c = theta[k]
        if kind == "sup":          # supremacy feature, already home-minus-away
            x = np.array([r[name] for r in rows])
            sh += c * x
            sa -= c * x
        elif kind == "sup_xi":     # (home delta - away delta) of an XI metric (mean per player)
            x = np.array([(r[f"home_d_{name}"] - r[f"away_d_{name}"]) / 11.0 for r in rows])
            sh += c * x
            sa -= c * x
        elif kind == "split":      # RAPM split: attack of a side vs defence of the other
            o, d = name
            sh += c * np.array([r[f"home_d_{o}"] - r[f"away_d_{d}"] for r in rows])
            sa += c * np.array([r[f"away_d_{o}"] - r[f"home_d_{d}"] for r in rows])
        elif kind == "net":        # RAPM net supremacy
            o, d = name
            x = np.array([((r[f"home_d_{o}"] + r[f"home_d_{d}"]) - (r[f"away_d_{o}"] + r[f"away_d_{d}"])) / 2
                          for r in rows])
            sh += c * x
            sa -= c * x
    return sh, sa


def match_logprob(rows, spec, theta, layer):
    lh = np.array([r["lh"] for r in rows])
    la = np.array([r["la"] for r in rows])
    sh, sa = shifts(rows, spec, theta)
    m = T.score_matrix(lh * np.exp(sh), la * np.exp(sa), layer.rho or 0.0, layer.nb_dispersion)
    hs = np.clip(np.array([r["hs"] for r in rows]), 0, T.MAX_GOALS)
    as_ = np.clip(np.array([r["as"] for r in rows]), 0, T.MAX_GOALS)
    return np.log(np.clip(m[np.arange(len(rows)), hs, as_], 1e-12, 1)), lh * np.exp(sh), la * np.exp(sa), m


def fit_variant(train, spec, layer):
    k = len(spec["terms"])
    if k == 0:
        return np.zeros(0), 0.0
    res = minimize(lambda t: -np.sum(match_logprob(train, spec, t, layer)[0]), np.zeros(k),
                   method="L-BFGS-B", bounds=spec["bounds"])
    return res.x, float(res.fun)


def per_match_1x2_logloss(rows, m):
    p1x2, _o25, _o35, _btts = T.markets(m)
    hs = np.array([r["hs"] for r in rows])
    as_ = np.array([r["as"] for r in rows])
    k = np.where(hs > as_, 0, np.where(hs == as_, 1, 2))
    return -np.log(np.clip(p1x2[np.arange(len(rows)), k], 1e-12, 1))


VARIANTS = {
    "ratings_only": {"terms": [], "bounds": []},
    "value": {"terms": [("sup", "value")], "bounds": [(-1, 1)]},
    "form": {"terms": [("sup", "form")], "bounds": [(-3, 3)]},
    "value+form": {"terms": [("sup", "value"), ("sup", "form")], "bounds": [(-1, 1), (-3, 3)]},
    "rapm_split": {"terms": [("split", ("offence", "defence"))], "bounds": [(-10, 10)]},
    "rapm_net": {"terms": [("net", ("offence", "defence"))], "bounds": [(-10, 10)]},
    "rapm_prior_split": {"terms": [("split", ("prior_offence", "prior_defence"))], "bounds": [(-10, 10)]},
    "metric_xgxa90": {"terms": [("sup_xi", "xgxa90")], "bounds": [(-20, 20)]},
    "metric_minutes_share": {"terms": [("sup_xi", "minutes_share")], "bounds": [(-20, 20)]},
    "metric_rating": {"terms": [("sup_xi", "rating")], "bounds": [(-20, 20)]},
    "value+rapm_split": {"terms": [("sup", "value"), ("split", ("offence", "defence"))],
                         "bounds": [(-1, 1), (-10, 10)]},
    "value+form+rapm_split": {"terms": [("sup", "value"), ("sup", "form"), ("split", ("offence", "defence"))],
                              "bounds": [(-1, 1), (-3, 3), (-10, 10)]},
    "value+form+rapm_net": {"terms": [("sup", "value"), ("sup", "form"), ("net", ("offence", "defence"))],
                            "bounds": [(-1, 1), (-3, 3), (-10, 10)]},
    "value+form+metric_minutes_share": {"terms": [("sup", "value"), ("sup", "form"), ("sup_xi", "minutes_share")],
                                        "bounds": [(-1, 1), (-3, 3), (-20, 20)]},
}
PRODUCTION_ONLY = ("ratings_only", "value", "form", "value+form")


def evaluate_set(train, test, names, layer, n_boot, seed):
    out = {}
    per_match = {}
    fitted = {}
    for name in names:
        spec = VARIANTS[name]
        theta, train_nll = fit_variant(train, spec, layer)
        _lp, lh, la, m = match_logprob(test, spec, theta, layer)
        ev = T.evaluate(test, lh, la, layer.rho or 0.0, layer.nb_dispersion)
        per_match[name] = per_match_1x2_logloss(test, m)
        fitted[name] = train_nll
        out[name] = {
            "coefficients": {f"{kind}:{nm if isinstance(nm, str) else '/'.join(nm)}": round(float(c), 4)
                             for (kind, nm), c in zip(spec["terms"], theta)},
            "train_nll_per_match": round(train_nll / max(len(train), 1), 5) if spec["terms"] else None,
            **{k: round(ev[k], 4) for k in ("1x2_logloss", "1x2_brier", "over25_logloss", "btts_logloss",
                                            "score_logloss")},
        }
    if "ratings_only" in names:
        base_nll = -np.sum(match_logprob(train, VARIANTS["ratings_only"], np.zeros(0), layer)[0])
        for name in names:
            if VARIANTS[name]["terms"]:
                lr = 2 * (base_nll - fitted[name])
                out[name]["train_lr_vs_ratings_only"] = round(float(lr), 3)
                out[name]["train_lr_p_value"] = float(f"{chi2.sf(max(lr, 0.0), len(VARIANTS[name]['terms'])):.3g}")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(test), size=(n_boot, len(test))) if len(test) else None
    for name in names:
        for ref in ("ratings_only", "value+form"):
            if ref not in per_match or name == ref:
                continue
            d = per_match[name] - per_match[ref]
            boots = d[idx].mean(1) if idx is not None else np.array([0.0])
            out[name][f"delta_1x2_vs_{ref}"] = {
                "mean": round(float(d.mean()), 5),
                "ci90": [round(float(np.quantile(boots, 0.05)), 5), round(float(np.quantile(boots, 0.95)), 5)],
                "p_boot_le_0": round(float((boots <= 0).mean()), 3),
            }
    return out


# --------------------------------------------------------------------------- main

def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="XI strength vs usual XI on top of walk-forward rating lambdas")
    ap.add_argument("--ratings", type=Path, default=DATA / "player_impact_asof.csv.gz")
    ap.add_argument("--meta", type=Path, default=DATA / "player_impact_meta.json")
    ap.add_argument("--details", action="append", type=Path)
    ap.add_argument("--lambdas", action="append", type=Path)
    ap.add_argument("--db", type=Path, default=BACKEND_DIR / "football_intelligence.db")
    ap.add_argument("--split", default="2026-07-01")
    ap.add_argument("--usual-n", type=int, default=10)
    ap.add_argument("--min-usual", type=int, default=3)
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20261013)
    ap.add_argument("--out", type=Path, default=DATA / "xi_impact_experiment.json")
    args = ap.parse_args(argv)
    t0 = time.time()

    details = args.details or [DATA / "fotmob_match_details.jsonl"]
    lambda_files = args.lambdas or [DATA / "walkforward_lambdas_xg.csv"]
    records = read_details(details)
    prod = production_features(records)
    cutoffs, ratings, repl = read_ratings(args.ratings, args.meta)
    xi = xi_features(records, cutoffs, ratings, repl, args.usual_n, args.min_usual)
    id_map = db_id_map(args.db)
    layer = get_goal_layer()
    print(f"details {len(records)} matches, rating cutoffs {len(cutoffs)} ({cutoffs[0]}..{cutoffs[-1]}), "
          f"XI features {len(xi)}", flush=True)

    rows, seen = [], set()
    for path in lambda_files:
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                pid = id_map.get(r["match_id"])
                if pid is None or pid in seen or pid not in prod:
                    continue
                seen.add(pid)
                lh, la = layer.adjust(float(r["lambda_home"]), float(r["lambda_away"]))
                row = {"pid": pid, "lh": lh, "la": la, "hs": int(r["home_score"]), "as": int(r["away_score"]),
                       "at": datetime.fromisoformat(r["kickoff"]), "is_euro": r.get("is_euro") == "1",
                       **prod[pid]}
                if pid in xi:
                    row.update(xi[pid])
                    row["has_xi"] = True
                else:
                    row["has_xi"] = False
                rows.append(row)
    split = datetime.fromisoformat(args.split)
    has_prod = [r for r in rows if r["form"] is not None and r["value"] is not None]
    common = [r for r in has_prod if r["has_xi"]]

    def tt(rs):
        return [r for r in rs if r["at"] < split], [r for r in rs if r["at"] >= split]

    report = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": {"ratings": str(args.ratings), "details": [str(p) for p in details],
                   "lambdas": [str(p) for p in lambda_files], "split": args.split,
                   "usual_n": args.usual_n, "min_usual": args.min_usual,
                   "goal_layer": {"a": layer.a, "b": layer.b, "rho": layer.rho, "nb_dispersion": layer.nb_dispersion}},
        "rows": {"with_lineups": len(rows), "with_value_and_form": len(has_prod), "common": len(common)},
    }
    tr, te = tt(has_prod)
    report["production_replication"] = {"n_train": len(tr), "n_test": len(te),
                                        "results": evaluate_set(tr, te, PRODUCTION_ONLY, layer, args.bootstrap,
                                                                args.seed)}
    print("replication", json.dumps({k: v["1x2_logloss"] for k, v in
                                     report["production_replication"]["results"].items()}), len(tr), len(te),
          flush=True)
    tr, te = tt(common)
    if common:
        f_split = np.array([r["home_d_offence"] - r["away_d_defence"] for r in common]
                           + [r["away_d_offence"] - r["home_d_defence"] for r in common])
        unk = np.array([r["home_unknown"] + r["away_unknown"] for r in common])
        report["feature_summary"] = {
            "rapm_split_feature_xg90": {"sd": round(float(f_split.std()), 4),
                                        "p05": round(float(np.quantile(f_split, 0.05)), 4),
                                        "p95": round(float(np.quantile(f_split, 0.95)), 4)},
            "matches_with_unrated_starter_pct": round(float((unk > 0).mean() * 100), 1),
            "unrated_starters_per_match_mean": round(float(unk.mean()), 3),
            "usual_xi_unrated_share_mean": round(float(np.mean([r["home_usual_unknown_share"] for r in common]
                                                               + [r["away_usual_unknown_share"] for r in common])), 4),
            "rating_age_days_mean": round(float(np.mean([(r["at"].date() - datetime.fromisoformat(r["cutoff"]).date()).days
                                                         for r in common])), 2),
        }
    report["common_rows"] = {"n_train": len(tr), "n_test": len(te),
                             "test_unknown_starters_per_side": round(float(np.mean(
                                 [r["home_unknown"] + r["away_unknown"] for r in te]) / 2), 3) if te else None,
                             "results": evaluate_set(tr, te, list(VARIANTS), layer, args.bootstrap, args.seed)}
    for name, res in report["common_rows"]["results"].items():
        print(f"{name:34s} 1x2={res['1x2_logloss']:.4f} score={res['score_logloss']:.4f} "
              f"coef={res['coefficients']} d_vs_ratings={res.get('delta_1x2_vs_ratings_only', {}).get('ci90')}",
              flush=True)
    euro_tr = [r for r in tr if r["is_euro"]]
    euro_te = [r for r in te if r["is_euro"]]
    if len(euro_te) >= 30:
        report["common_rows_euro_only"] = {"n_train": len(euro_tr), "n_test": len(euro_te),
                                           "results": evaluate_set(euro_tr, euro_te, ["ratings_only", "value+form",
                                                                                      "rapm_split", "value+form+rapm_split"],
                                                                   layer, args.bootstrap, args.seed)}
    report["seconds"] = round(time.time() - t0, 1)
    tmp = args.out.with_name(args.out.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(report, indent=1), encoding="utf-8")
    os.replace(tmp, args.out)
    print(f"-> {args.out} ({report['seconds']} s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
