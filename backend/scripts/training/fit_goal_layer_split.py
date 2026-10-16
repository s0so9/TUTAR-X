"""Goal layer refitted on the fixed training split only (full multi-season run, 2026-10-14).

Same model and fitting code as fit_goal_layer.py (``fit_layer``: log-space total-goal shrinkage
a, b around the mean m, supremacy unchanged c = 1, Dixon-Coles rho, negative-binomial
dispersion), but fitted on the walk-forward rating lambdas of a time window only, so that
evaluation periods are never used for the fit:

  train-only   kickoff in [--train-start, --train-end)   -> goal_layer_train_only.json  (evaluation)
  train + val  kickoff in [--train-start, --val-end)     -> goal_layer_trainval.json    (deployment refit)

The production layer (config/goal_model.json) was fitted on every row of
walkforward_lambdas_xg.csv (2025-07 .. 2026-10), i.e. including the validation and test periods
of the fixed split; it is read here only to report its (in-sample) validation numbers.

Rows: every row of the lambdas file (all competitions, as production did). Validation metrics
are reported on all validation rows and on the subset of matches present in the details files
(the rows the match model is evaluated on). The output JSON keeps the ``params`` layout of
config/goal_model.json, so ``app.prediction.goal_model.get_goal_layer(path)`` can read it.
Nothing in backend/config/ is written. No network requests.

Usage (from backend/):
  venv/Scripts/python.exe scripts/training/fit_goal_layer_split.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

TRAINING_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TRAINING_DIR.parents[1]
sys.path.insert(0, str(TRAINING_DIR))
import fit_goal_layer as FG  # noqa: E402
import train_goal_model as T  # noqa: E402

DATA = BACKEND_DIR / "data" / "training"
KEEP = ("1x2_logloss", "1x2_brier", "over25_logloss", "over25_brier", "over35_logloss", "btts_logloss",
        "btts_brier", "score_logloss", "mean_pred_total", "mean_actual_total", "pred_draw_rate", "actual_draw_rate")
ID_RE = re.compile(rb'"match_provider_id":\s*"?(\d+)')


def details_ids(paths: list[Path]) -> set[str]:
    out = set()
    for p in paths:
        with open(p, "rb") as f:
            for line in f:
                m = ID_RE.search(line[:200])
                if m:
                    out.add(m.group(1).decode())
    return out


def load_rows(path: Path) -> list[dict]:
    """train_goal_model.load plus the match id (FotMob id in the multi-season lambdas file)."""
    import csv
    rows = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({"id": r["match_id"], "at": datetime.fromisoformat(r["kickoff"]),
                         "euro": r["is_euro"] == "1", "comp": r["competition_provider_id"],
                         "lh": float(r["lambda_home"]), "la": float(r["lambda_away"]),
                         "hs": int(r["home_score"]), "as": int(r["away_score"])})
    return rows


def score(rows: list[dict], p: dict) -> dict:
    if not rows:
        return {}
    ev = FG.score(rows, p)
    return {k: round(float(ev[k]), 5) for k in KEEP if k in ev}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="goal layer fitted on the fixed training split only")
    ap.add_argument("--data", type=Path, default=DATA / "walkforward_lambdas_full_2022_2026.csv")
    ap.add_argument("--details", action="append", type=Path)
    ap.add_argument("--train-start", default="2022-08-01")
    ap.add_argument("--train-end", default="2025-07-01", help="exclusive")
    ap.add_argument("--val-end", default="2026-02-01", help="exclusive")
    ap.add_argument("--production", type=Path, default=BACKEND_DIR / "config" / "goal_model.json")
    ap.add_argument("--out-train", type=Path, default=DATA / "goal_layer_train_only.json")
    ap.add_argument("--out-trainval", type=Path, default=DATA / "goal_layer_trainval.json")
    args = ap.parse_args(argv)
    t0 = time.time()

    details = args.details or [DATA / "fotmob_match_details.jsonl", DATA / "fotmob_match_details_history.jsonl"]
    det_ids = details_ids(details)
    rows = load_rows(args.data)
    t_start, t_end, v_end = (datetime.fromisoformat(x) for x in (args.train_start, args.train_end, args.val_end))
    train = [r for r in rows if t_start <= r["at"] < t_end]
    val = [r for r in rows if t_end <= r["at"] < v_end]
    trainval = train + val
    val_det = [r for r in val if r["id"] in det_ids]
    val_euro = [r for r in val_det if r["comp"] in ("42", "73", "10216")]
    print(f"rows {len(rows)}: train {len(train)}, validation {len(val)} ({len(val_det)} details matches), "
          f"details ids {len(det_ids)} [{time.time() - t0:.0f}s]", flush=True)

    p_train = FG.fit_layer(train)
    print(f"train-only layer: {p_train} [{time.time() - t0:.0f}s]", flush=True)
    p_trainval = FG.fit_layer(trainval)
    print(f"train+val layer: {p_trainval} [{time.time() - t0:.0f}s]", flush=True)
    # diagnostic only (not used downstream): the same layer fitted on the details matches of train
    train_det = [r for r in train if r["id"] in det_ids]
    p_train_det = FG.fit_layer(train_det)
    print(f"train-only layer, details matches only (diagnostic): {p_train_det} [{time.time() - t0:.0f}s]",
          flush=True)

    prod = None
    if args.production.exists():
        prod = json.loads(args.production.read_text(encoding="utf-8"))["params"]

    def val_block(p):
        return {"all_rows": score(val, p), "details_matches": score(val_det, p), "details_european": score(val_euro, p)}

    validation = {
        "raw_lambdas": val_block({}),
        "train_only_layer": val_block(p_train),
        "train_only_layer_details_fit (diagnostic)": val_block(p_train_det),
    }
    if prod:
        validation["production_layer_in_sample (config/goal_model.json)"] = val_block(prod)
    common = {
        "description": "Goal layer over global team ratings (fit_goal_layer.fit_layer): log-space total-goal "
                       "shrinkage (a, b around m), supremacy unchanged (c = 1), Dixon-Coles rho, NB dispersion. "
                       "Same model as config/goal_model.json, refitted on a time window of the multi-season "
                       "walk-forward lambdas only.",
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data": str(args.data.relative_to(BACKEND_DIR)) if args.data.is_relative_to(BACKEND_DIR) else str(args.data),
        "rows_used": "every row of the lambdas file in the window (all competitions, as production; awarded "
                     "results and the 19 production_vs_fixture_status conflicts were already dropped when the "
                     "lambdas file was built)",
        "splits": {"train": [args.train_start, args.train_end], "validation": [args.train_end, args.val_end],
                   "note": "intervals are [start, end) on kickoff (naive UTC)"},
        "validation_metrics": {
            "rows": {"all": len(val), "details_matches": len(val_det), "details_european": len(val_euro)},
            "by_layer": validation,
            "note": "validation rows are out of sample for the train-only layer; the production layer was fitted "
                    "on rows that include this period (in-sample, shown for comparison only)",
        },
        "diagnostic_train_only_details_fit": {**p_train_det, "n_rows": len(train_det)},
    }
    outs = [(args.out_train, p_train, len(train), "train-only (evaluation: use for every validation / test metric)"),
            (args.out_trainval, p_trainval, len(trainval),
             "train + validation (deployment refit; not evaluated on validation, which it contains)")]
    for path, p, n, role in outs:
        doc = {"role": role, "params": p, "n_rows": n, **common}
        tmp = path.with_name(path.name + f".tmp{os.getpid()}")
        tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        os.replace(tmp, path)
        print(f"-> {path}", flush=True)
    print(json.dumps(validation, indent=1))
    print(f"done in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
