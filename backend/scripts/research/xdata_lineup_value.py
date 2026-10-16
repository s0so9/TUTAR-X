"""Research (2026-10-15, "additional data" study): what is the confirmed starting XI worth in the production model?

The production model multiplies the rating means by exp(+-(shift_value + shift_form)), where both shifts are computed
from the *announced starting XI* (starters' market value ratio, starters' FotMob form vs the usual XI). Removing the
two shifts gives the "no line-up" prediction (rating + goal layer only). Both versions use the same NB x Dixon-Coles
score model (train-only goal layer). Scored on validation and test (paired bootstrap, 90 % CI; negative = the XI
layer helps). Caveat (docs/training/2026-10-14-full-training.md): beta / gamma of the shifts were fitted on
Jan-Jun 2026, which overlaps the test split, so the test gain is if anything optimistic.

Run (from backend/):  OMP_NUM_THREADS=2 venv/Scripts/python.exe -I scripts/research/xdata_lineup_value.py
Output: data/research/xdata_lineup_value.json
"""
from __future__ import annotations

import csv
import gzip
import json
import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND / "scripts" / "training"))
import calibration_common as CC  # noqa: E402
import train_goal_model as T  # noqa: E402

OUT = BACKEND / "data" / "research" / "xdata_lineup_value.json"


def main() -> int:
    rows = []
    with gzip.open(CC.DATA / "baseline_predictions_full.csv.gz", "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["status"] == "ok":
                rows.append(r)
    lay = CC.load_layer()
    split = np.array([r["split"] for r in rows])
    lh = np.array([float(r["lambda_home_layer"]) for r in rows])
    la = np.array([float(r["lambda_away_layer"]) for r in rows])
    mh = np.array([float(r["mu_home"]) for r in rows])
    ma = np.array([float(r["mu_away"]) for r in rows])
    hg = np.array([int(r["home_goals"]) for r in rows])
    ag = np.array([int(r["away_goals"]) for r in rows])
    has_shift = np.array([bool(r["shift_value"] or r["shift_form"]) for r in rows])
    y = np.where(hg > ag, 0, np.where(hg == ag, 1, 2))
    yo = ((hg + ag) > 2.5).astype(float)

    def pr(a, b):
        p1, po = np.empty((len(a), 3)), np.empty(len(a))
        for i in range(0, len(a), 4000):
            m = T.score_matrix(a[i:i + 4000], b[i:i + 4000], lay["rho"], lay["nb_dispersion"])
            p, o, _, _ = T.markets(m)
            p1[i:i + 4000], po[i:i + 4000] = p, o
        return p1, po

    p_with, o_with = pr(mh, ma)
    p_wo, o_wo = pr(lh, la)
    res = {"note": __doc__.split("\n\n")[1].replace("\n", " ")}
    for sp in ("validation", "test"):
        sel = (split == sp) & has_shift
        l_w = CC.logloss(p_with[sel], y[sel])
        l_o = CC.logloss(p_wo[sel], y[sel])
        ou_w = -(yo[sel] * np.log(o_with[sel]) + (1 - yo[sel]) * np.log(1 - o_with[sel]))
        ou_o = -(yo[sel] * np.log(o_wo[sel]) + (1 - yo[sel]) * np.log(1 - o_wo[sel]))
        fav_w = p_with[sel].max(1) >= 0.70
        fav_o = p_wo[sel].max(1) >= 0.70
        res[sp] = {"n": int(sel.sum()),
                   "1x2_logloss_with_xi_layer": round(float(l_w.mean()), 5),
                   "1x2_logloss_without": round(float(l_o.mean()), 5),
                   "1x2_diff_with_minus_without": CC.paired_boot(l_w - l_o),
                   "ou25_diff_with_minus_without": CC.paired_boot(ou_w - ou_o),
                   "fav_ge_0.70_with": {"n": int(fav_w.sum()),
                                        "hit": round(float((p_with[sel].argmax(1) == y[sel])[fav_w].mean()), 4)},
                   "fav_ge_0.70_without": {"n": int(fav_o.sum()),
                                           "hit": round(float((p_wo[sel].argmax(1) == y[sel])[fav_o].mean()), 4)},
                   "mean_abs_shift": round(float(np.abs(np.log(mh[sel] / lh[sel])).mean()), 4)}
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
