"""Summary of the multi-season player-impact run (2026-10-14): how far the ratings move away from
the box-score prior, and whether defence separates better than in the 1.25-season run.

Inputs (read only): the new ratings / meta files and, for comparison, the 1.25-season run of
2026-10-13 (player_impact_asof.csv.gz, player_impact_meta.json). Output: player_impact_all_summary.json.

1. Spread at the latest cutoff of each run (same definitions for both files): sd of offence /
   defence, sd of the deviation from the prior (rating - prior), var(deviation) / var(rating)
   among regulars (>= 900 stint minutes in the fit window), correlation of the new and old
   ratings for players in both files.
2. Time-forward validation inside the training period (meta ``validation``): duration-weighted
   squared error of stint npxG/90 for the chosen configuration and its decompositions per
   look-back (456 d ~ 1.25 seasons, 730 d, 1095 d). Defence term value = WMSE(no defence term) -
   WMSE(full); defence deviation value = WMSE(defence = prior only) - WMSE(full). Positive = the
   part improves the prediction.

Usage (from backend/): venv/Scripts/python.exe scripts/training/player_impact_run_summary.py
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import sys
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[2] / "data" / "training"
REGULAR_MIN = 900.0


def last_block(path: Path, cutoff: str | None = None) -> tuple[str, list[dict]]:
    rows, last = [], None
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            c = r["cutoff"]
            if cutoff is not None:
                if c == cutoff:
                    rows.append(r)
                continue
            if last is None or c > last:
                last, rows = c, []
            if c == last:
                rows.append(r)
    return (cutoff or last), rows


def spread(rows: list[dict]) -> dict:
    off = np.array([float(r["offence"]) for r in rows])
    dfn = np.array([float(r["defence"]) for r in rows])
    poff = np.array([float(r["prior_offence"]) for r in rows])
    pdef = np.array([float(r["prior_defence"]) for r in rows])
    rm = np.array([float(r["rapm_minutes"]) for r in rows])
    reg = rm >= REGULAR_MIN
    out = {"players": len(rows), "regulars": int(reg.sum()), "regulars_min_rapm_minutes": REGULAR_MIN,
           "prior_only_players": int((rm <= 0).sum())}
    for name, v, p in (("offence", off, poff), ("defence", dfn, pdef)):
        dev = v - p
        out[name] = {
            "sd_all": round(float(v.std()), 5), "sd_regulars": round(float(v[reg].std()), 5),
            "sd_prior_regulars": round(float(p[reg].std()), 5),
            "sd_deviation_all": round(float(dev.std()), 5), "sd_deviation_regulars": round(float(dev[reg].std()), 5),
            "mean_abs_deviation_regulars": round(float(np.abs(dev[reg]).mean()), 5),
            "p95_abs_deviation_regulars": round(float(np.quantile(np.abs(dev[reg]), 0.95)), 5),
            "deviation_var_share_regulars": round(float(dev[reg].var() / v[reg].var()), 4) if v[reg].var() > 0 else None,
            "sd_regulars_over_sd_prior_regulars": round(float(v[reg].std() / p[reg].std()), 4) if p[reg].std() > 0 else None,
        }
    return out


def correlation(new: list[dict], old: list[dict]) -> dict:
    o = {r["player_id"]: r for r in old}
    common = [(r, o[r["player_id"]]) for r in new if r["player_id"] in o
              and float(r["rapm_minutes"]) >= REGULAR_MIN and float(o[r["player_id"]]["rapm_minutes"]) >= REGULAR_MIN]
    out = {"regulars_in_both": len(common)}
    for k in ("offence", "defence"):
        a = np.array([float(x[k]) for x, _ in common])
        b = np.array([float(y[k]) for _, y in common])
        out[f"corr_{k}"] = round(float(np.corrcoef(a, b)[0, 1]), 4) if len(common) > 2 else None
    return out


def validation_decomposition(meta: dict) -> dict:
    wmse = meta["validation"]["wmse"]
    hp = meta["hyper_parameters"]
    out = {}
    pat = re.compile(r"^(lb[\d.]+_)?hl([\d.]+)_team([\de+.]+)_(full|decomp-[a-z_]+)_lam([\d.e+]+)$")
    by_lb: dict = {}
    for k, v in wmse.items():
        m = pat.match(k)
        if not m:
            continue
        lb = (m.group(1) or "lb%g_" % hp["lookback_days"])[2:-1]
        by_lb.setdefault(lb, {}).setdefault((m.group(2), m.group(5)), {})[m.group(4)] = v
    base = {}
    for k, v in wmse.items():
        m = re.match(r"^(lb[\d.]+_)?hl([\d.]+)_team[\de+.]+_(team_only|prior_only)$", k)
        if m:
            lb = (m.group(1) or "lb%g_" % hp["lookback_days"])[2:-1]
            base.setdefault(lb, {}).setdefault(m.group(2), {})[m.group(3)] = v
    chosen_hl, chosen_lam = f"{hp['half_life_days']:g}", f"{hp['lambda_player']:g}"
    for lb, cfgs in sorted(by_lb.items(), key=lambda kv: float(kv[0])):
        best = min(((hl, lam) for (hl, lam), d in cfgs.items() if "full" in d), key=lambda c: cfgs[c]["full"])
        res = {}
        for label, cfg in (("at_chosen_config", (chosen_hl, chosen_lam)), ("at_own_best", best)):
            d = cfgs.get(cfg)
            if not d or "full" not in d:
                continue
            full = d["full"]
            e = {"half_life": float(cfg[0]), "lambda": float(cfg[1]), "wmse_full": round(full, 6)}
            for part, key in (("defence_term", "decomp-no_def"), ("defence_deviation", "decomp-no_def_dev"),
                              ("offence_deviation", "decomp-no_off_dev"), ("all_deviations", "decomp-no_dev")):
                if key in d:
                    e[f"value_of_{part}"] = round(d[key] - full, 6)
                    e[f"value_of_{part}_pct"] = round(100 * (d[key] - full) / full, 4)
            b = base.get(lb, {}).get(cfg[0], {})
            for k2 in ("team_only", "prior_only"):
                if k2 in b:
                    e[f"wmse_{k2}"] = round(b[k2], 6)
                    e[f"full_vs_{k2}_pct"] = round(100 * (full - b[k2]) / b[k2], 4)
            res[label] = e
        out[f"lookback_{lb}"] = res
    return out


def per_window_defence(meta: dict) -> dict:
    """Per validation window: does the defence deviation help (chosen config, each look-back)?"""
    hp = meta["hyper_parameters"]
    per = meta["validation"]["per_cutoff"]
    out = {}
    for k in per:
        m = re.match(r"^(lb([\d.]+)_)?hl([\d.]+)_team[\de+.]+_full_lam([\d.e+]+)$", k)
        if not m or float(m.group(3)) != hp["half_life_days"] or float(m.group(4)) != hp["lambda_player"]:
            continue
        lb = m.group(2) or f"{hp['lookback_days']:g}"
        full = {e["cutoff"]: e["wmse"] for e in per[k]}
        nd = {e["cutoff"]: e["wmse"] for e in per.get(k.replace("_full_", "_decomp-no_def_dev_"), [])}
        ndt = {e["cutoff"]: e["wmse"] for e in per.get(k.replace("_full_", "_decomp-no_def_"), [])}
        out[f"lookback_{lb}"] = {
            "windows": len(full),
            "defence_deviation_helps_in": sum(1 for c in full if c in nd and nd[c] > full[c]),
            "defence_term_helps_in": sum(1 for c in full if c in ndt and ndt[c] > full[c]),
        }
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ratings", type=Path, default=DATA / "player_impact_asof_all.csv.gz")
    ap.add_argument("--meta", type=Path, default=DATA / "player_impact_all_meta.json")
    ap.add_argument("--old-ratings", type=Path, default=DATA / "player_impact_asof.csv.gz")
    ap.add_argument("--old-meta", type=Path, default=DATA / "player_impact_meta.json")
    ap.add_argument("--out", type=Path, default=DATA / "player_impact_all_summary.json")
    args = ap.parse_args(argv)
    meta = json.loads(args.meta.read_text(encoding="utf-8"))
    old_meta = json.loads(args.old_meta.read_text(encoding="utf-8"))
    cut_new, new = last_block(args.ratings)
    cut_old, old = last_block(args.old_ratings)
    # the new run at the old run's last cutoff date is not available (2-week grid); use the
    # nearest new cutoff on or before it for an extra like-for-like line
    new_cuts = sorted({e["cutoff"] for e in meta["per_cutoff"]})
    near = max(c for c in new_cuts if c <= cut_old)
    _c, new_near = last_block(args.ratings, near) if near != cut_new else (near, new)
    per = {e["cutoff"]: e for e in meta["per_cutoff"]}
    trajectory = [{"cutoff": c, "players": per[c]["players_rated"], "stints": per[c]["stints"],
                   "sd_offence": per[c]["sd_offence"], "sd_defence": per[c]["sd_defence"],
                   **{k: per[c].get(k) for k in ("sd_dev_offence_regulars", "sd_dev_defence_regulars",
                                                 "dev_share_var_offence_regulars", "dev_share_var_defence_regulars",
                                                 "n_regulars")}}
                  for c in sorted(set(new_cuts[::13]) | {new_cuts[-1]})]
    out = {
        "new_run": {"ratings": args.ratings.name, "hyper_parameters": meta["hyper_parameters"],
                    "latest_cutoff": cut_new, "spread_latest": spread(new),
                    "nearest_cutoff_to_old_latest": near, "spread_at_nearest": spread(new_near)},
        "old_run_1_25_seasons": {"ratings": args.old_ratings.name, "hyper_parameters": {
            k: old_meta["hyper_parameters"].get(k) for k in ("lambda_player", "half_life_days", "lookback_days")},
            "latest_cutoff": cut_old, "spread_latest": spread(old)},
        "rating_correlation_new_vs_old_regulars": correlation(new_near, old),
        "validation_inside_training_period": {
            "val_cutoffs": meta["validation"].get("val_cutoffs"),
            "last_window_end": meta["validation"].get("last_window_end"),
            "decomposition_by_lookback": validation_decomposition(meta),
            "defence_per_window": per_window_defence(meta)},
        "trajectory": trajectory,
    }
    args.out.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
