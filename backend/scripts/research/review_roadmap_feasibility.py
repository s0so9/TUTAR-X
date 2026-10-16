"""Feasibility review of docs/research/2026-10-15-accuracy-roadmap.md (research only, 2026-10-15).

Two questions the roadmap's timing claims depend on:

1. B1 / B5: the live headline tracker freezes picks only for the FEATURED competitions
   (backend/app/config.py featured_competition_ids = 47,87,55,54,53,57,61,40,71,122,42,73,10216),
   while the selective study [S] counted picks over 20 competitions. How many p >= 0.85 Bankos per
   CALENDAR day did the featured set produce on the test split, and how long would 300 tracked Bankos take?
2. C1: how many featured-competition matches are there per match day (request budget for an odds feed)?

Same rule as sel_common.banko_index (most likely of the 14 app candidates with lo <= p <= 0.95).
Inputs: data/training/baseline_predictions_full.csv.gz (production model, out-of-sample). No network,
no DB writes. Output: data/research/review_roadmap_feasibility.json
Run (from backend/): OMP_NUM_THREADS=2 venv/Scripts/python.exe scripts/research/review_roadmap_feasibility.py
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sel_common as s  # noqa: E402

FEATURED = {"47", "87", "55", "54", "53", "57", "61", "40", "71", "122", "42", "73", "10216"}
TARGET = 300


def summarise(d: dict, mask: np.ndarray, lo: float) -> dict:
    idx = s.banko_index(d["P"][mask], lo=lo)
    hit = s.take(d["Y"][mask], idx)
    sel = idx >= 0
    dates = d["date"][mask]
    days_with_matches = np.unique(dates)
    first, last = date.fromisoformat(min(dates)), date.fromisoformat(max(dates))
    cal_days = (last - first).days + 1
    n_pick = int(sel.sum())
    per_cal = n_pick / cal_days
    per_mday = n_pick / len(days_with_matches)
    # matches per match day (odds-feed request budget)
    _, counts = np.unique(dates, return_counts=True)
    return {
        "matches": int(mask.sum()),
        "window": [str(first), str(last)],
        "calendar_days": cal_days,
        "match_days": int(len(days_with_matches)),
        "bankos": n_pick,
        "hit_rate": round(float(hit[sel].mean()), 4) if n_pick else None,
        "bankos_per_match_day": round(per_mday, 2),
        "bankos_per_calendar_day": round(per_cal, 2),
        "calendar_days_to_300": round(TARGET / per_cal) if per_cal else None,
        "match_days_to_300": round(TARGET / per_mday) if per_mday else None,
        "matches_per_match_day": {
            "median": float(np.median(counts)),
            "p90": float(np.quantile(counts, 0.9)),
            "max": int(counts.max()),
        },
        "uefa_share_of_bankos": round(float(d["euro"][mask][sel].mean()), 4) if n_pick else None,
    }


def main() -> None:
    d = s.load_preds()
    test = d["split"] == "test"
    feat = np.isin(d["comp"], list(FEATURED))
    out = {
        "note": "Test split of baseline_predictions_full (production model, out-of-sample). Featured = "
                "headline-tracker competitions from backend/app/config.py. Banko rule = sel_common.banko_index.",
        "featured_ids": sorted(FEATURED),
        "test_all_20": {str(lo): summarise(d, test, lo) for lo in (0.70, 0.85, 0.90)},
        "test_featured_13": {str(lo): summarise(d, test & feat, lo) for lo in (0.70, 0.85, 0.90)},
        "test_featured_13_leagues_only": {str(lo): summarise(d, test & feat & ~d["euro"], lo)
                                          for lo in (0.85,)},
    }
    # in-season pace: featured matches and >= 0.85 Bankos per calendar month of the test split
    m = test & feat
    idx = s.banko_index(d["P"][m], lo=0.85)
    months = np.array([x[:7] for x in d["date"][m]])
    out["test_featured_13_by_month_0.85"] = {
        mo: {"matches": int((months == mo).sum()), "bankos": int(((months == mo) & (idx >= 0)).sum())}
        for mo in sorted(set(months.tolist()))
    }
    path = s.OUT / "review_roadmap_feasibility.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
