"""Agreement of two walk-forward lambda files on their overlap (same cutoff, same match).

Used by the multi-season re-run (docs/training/2026-10-13-full-training.md, step 1) to compare
walkforward_lambdas_full_2022_2026.csv (all_results.db, FotMob ids) with the current-data files
(walkforward_lambdas_xg.csv / walkforward_lambdas_xg_2025h2.csv, production DB uuids, mapped to
FotMob ids through the production DB opened read-only).

The overlap is reported per cutoff period, because the current-data files were fitted on the
production DB, which starts 2025-07-01: with the 400-day rating look-back their early fits saw
far fewer matches than the multi-season fit, and the two fits only see the same window from
cutoff 2026-08-05 on (2025-07-01 + 400 days).

Usage (from backend/):
  venv/Scripts/python.exe scripts/training/compare_lambda_files.py \
      --new data/training/walkforward_lambdas_full_2022_2026.csv \
      --ref data/training/walkforward_lambdas_xg_2025h2.csv --ref data/training/walkforward_lambdas_xg.csv \
      --out data/training/walkforward_lambdas_full_check.json
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA = BACKEND_DIR / "data" / "training"
LOOKBACK_START_EQUAL = date(2026, 8, 5)     # 2025-07-01 + 400 days


def db_id_map(db: Path) -> dict[str, str]:
    if not db.exists():
        return {}
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        return {r[0]: str(r[1]) for r in con.execute("select id, provider_id from matches")}
    finally:
        con.close()


def read(paths: list[Path], id_map: dict[str, str]) -> dict[tuple[str, str], tuple[float, float, str]]:
    """(cutoff, FotMob match id) -> (lambda_home, lambda_away, competition provider id)."""
    out = {}
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                mid = r["match_id"]
                pid = id_map.get(mid) if "-" in mid else mid
                if not pid:
                    continue
                key = (r["cutoff"], pid)
                if key not in out:
                    out[key] = (float(r["lambda_home"]), float(r["lambda_away"]), r.get("competition_provider_id", ""))
    return out


def summarise(d: list[float]) -> dict:
    if not d:
        return {"n_lambdas": 0}
    d = sorted(d)
    return {"n_lambdas": len(d), "mean_abs_dlog_lambda": round(sum(d) / len(d), 5),
            "median_abs_dlog_lambda": round(d[len(d) // 2], 5),
            "p95_abs_dlog_lambda": round(d[int(0.95 * (len(d) - 1))], 5), "max_abs_dlog_lambda": round(d[-1], 5),
            "share_within_1pct": round(sum(x < 0.01 for x in d) / len(d), 4),
            "share_within_5pct": round(sum(x < 0.05 for x in d) / len(d), 4),
            "share_within_10pct": round(sum(x < 0.10 for x in d) / len(d), 4)}


def period_of(cutoff: str) -> str:
    c = date.fromisoformat(cutoff)
    if c < date(2026, 1, 1):
        return "2025-08..2025-12"
    if c < date(2026, 4, 1):
        return "2026-01..2026-03"
    if c < LOOKBACK_START_EQUAL:
        return "2026-04..2026-08-04"
    return "2026-08-05..2026-10 (same 400-day window)"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--new", type=Path, required=True)
    ap.add_argument("--ref", type=Path, action="append", required=True)
    ap.add_argument("--db", type=Path, default=BACKEND_DIR / "football_intelligence.db")
    ap.add_argument("--target-comps", default="47,87,55,54,53,57,61,40,71,122,42,73,10216")
    ap.add_argument("--out", type=Path, default=DATA / "walkforward_lambdas_full_check.json")
    args = ap.parse_args(argv)
    id_map = db_id_map(args.db)
    new = read([args.new], {})
    ref = read(args.ref, id_map)
    target = set(args.target_comps.split(","))
    per_period, per_period_t13 = defaultdict(list), defaultdict(list)
    per_cut = defaultdict(list)
    signed = defaultdict(list)
    only_ref = defaultdict(int)
    only_new = defaultdict(int)
    ref_cutoffs = {c for c, _ in ref}
    for key, (rh, ra, comp) in ref.items():
        v = new.get(key)
        if v is None:
            only_ref[period_of(key[0])] += 1
            continue
        dh, da = math.log(v[0] / rh), math.log(v[1] / ra)
        per_period[period_of(key[0])] += [abs(dh), abs(da)]
        per_cut[key[0]] += [abs(dh), abs(da)]
        signed[period_of(key[0])].append((dh + da) / 2)
        if comp in target or v[2] in target:
            per_period_t13[period_of(key[0])] += [abs(dh), abs(da)]
    for key in new:
        if key[0] in ref_cutoffs and key not in ref:
            only_new[period_of(key[0])] += 1
    rep = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "new": str(args.new), "reference": [str(p) for p in args.ref],
        "note": "reference files were fitted on the production DB (matches from 2025-07-01 only); the multi-season "
                "fit adds the history before 2025-07-01, so early cutoffs differ by construction. From cutoff "
                f"{LOOKBACK_START_EQUAL} both fits see the same 400-day window.",
        "per_period_all_competitions": {k: summarise(v) for k, v in sorted(per_period.items())},
        "per_period_target13": {k: summarise(v) for k, v in sorted(per_period_t13.items())},
        "mean_signed_dlog_total_per_period": {k: round(sum(v) / len(v), 5) for k, v in sorted(signed.items())},
        "only_in_reference": dict(only_ref), "only_in_new_at_reference_cutoffs": dict(only_new),
        "per_cutoff_mean_abs_dlog_lambda": {k: round(sum(v) / len(v), 5) for k, v in sorted(per_cut.items())},
    }
    tmp = args.out.with_name(args.out.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    os.replace(tmp, args.out)
    print(json.dumps({k: rep[k] for k in ("per_period_all_competitions", "per_period_target13",
                                          "only_in_reference", "only_in_new_at_reference_cutoffs")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
