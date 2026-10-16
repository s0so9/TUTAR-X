"""Research (2026-10-15, "additional data" study): descriptive check of travel distance in European-cup matches.

The favourite-calibration study (docs/training/2026-10-14-favourite-calibration.md) found the production model
under-states home advantage in UEFA matches on train+validation, but a home-advantage term failed on test. Is the
residual home advantage related to how far the away team travelled? Descriptive only (no model is fitted):
mean of (actual home-minus-away goals) - (model mu_home - mu_away) by away-travel distance band, per split group.
Distances: haversine km from the away team's usual home venue (mode of its home-match coordinates in the FotMob
raw cache) to the venue (data/research/xdata_match_context.csv).

Run (from backend/):  OMP_NUM_THREADS=2 venv/Scripts/python.exe -I scripts/research/xdata_uefa_travel.py
Output: data/research/xdata_uefa_travel.json
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND / "scripts" / "training"))
import calibration_common as CC  # noqa: E402

RES = BACKEND / "data" / "research"
OUT = RES / "xdata_uefa_travel.json"


def hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(h)))


def main() -> int:
    d = CC.load_baseline()
    with open(RES / "xdata_match_context.csv", encoding="utf-8") as f:
        ctx = {r["match_id"]: r for r in csv.DictReader(f)}
    hv = defaultdict(Counter)
    for r in ctx.values():
        if r["lat"]:
            hv[r["home_team_id"]][(round(float(r["lat"]), 3), round(float(r["lon"]), 3))] += 1
    home = {t: c.most_common(1)[0][0] for t, c in hv.items()}
    km = np.full(d["n"], np.nan)
    for i, m in enumerate(d["match_id"]):
        r = ctx.get(m)
        if r and r["lat"] and r["away_team_id"] in home:
            km[i] = hav(home[r["away_team_id"]], (float(r["lat"]), float(r["lon"])))
    resid = (d["hg"] - d["ag"]) - (d["mu_h"] - d["mu_a"])
    bands = [(0, 300), (300, 1000), (1000, 2000), (2000, 20000)]
    out = {}
    for label, mask in (("uefa_train_val", d["euro"] & np.isin(d["split"], ["train", "validation"])),
                        ("uefa_test", d["euro"] & (d["split"] == "test")),
                        ("league_all", ~d["euro"])):
        rows = []
        for lo, hi in bands:
            sel = mask & (km >= lo) & (km < hi)
            n = int(sel.sum())
            if n == 0:
                rows.append({"km": f"{lo}-{hi}", "n": 0})
                continue
            se = float(resid[sel].std(ddof=1) / math.sqrt(n)) if n > 1 else None
            rows.append({"km": f"{lo}-{hi}", "n": n, "mean_resid_goal_diff": round(float(resid[sel].mean()), 3),
                         "se": None if se is None else round(se, 3)})
        out[label] = rows
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
