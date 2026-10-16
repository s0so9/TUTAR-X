"""Closing-market quality on Over/Under 2.5 (research, 2026-10-15). Pinnacle closing (PC>2.5/PC<2.5),
proportional de-vig; football_data_history + current rows (deduplicated). Output: data/research/sota_ou_market.json"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sota_common as C  # noqa: E402

def main():
    P, Y, T5 = [], [], []
    for r in C.load_odds_rows():
        o, u = C._f(r.get("PC>2.5")), C._f(r.get("PC<2.5"))
        if not o or not u or not r.get("FTHG") or not r.get("FTAG"):
            continue
        q = np.array([1 / o, 1 / u]); q = q / q.sum()
        P.append(q[0]); Y.append(int(int(r["FTHG"]) + int(r["FTAG"]) > 2)); T5.append(r["division"] in C.TOP5)
    P, Y, T5 = np.array(P), np.array(Y), np.array(T5)
    def s(m):
        p, y = P[m], Y[m]
        ll = -(y * np.log(p) + (1 - y) * np.log(1 - p)).mean()
        cal = []
        for lo, hi in ((0, .4), (.4, .5), (.5, .6), (.6, .7), (.7, 1.01)):
            k = (p >= lo) & (p < hi)
            if k.sum() >= 30:
                cal.append({"band": f"{lo}-{min(hi,1)}", "n": int(k.sum()), "pred": round(float(p[k].mean()), 4), "obs": round(float(y[k].mean()), 4)})
        best = np.maximum(p, 1 - p); hit = np.where(p >= .5, y == 1, y == 0)
        return {"n": int(m.sum()), "logloss": round(float(ll), 5), "accuracy": round(float(hit.mean()), 4),
                "over_rate": round(float(y.mean()), 4), "mean_pred_over": round(float(p.mean()), 4),
                "share_best_side_ge_0.65": round(float((best >= .65).mean()), 4),
                "hit_best_side_ge_0.65": round(float(hit[best >= .65].mean()), 4) if (best >= .65).any() else None,
                "calibration": cal}
    out = {"all": s(np.ones(len(P), bool)), "top5": s(T5)}
    C.OUT.mkdir(parents=True, exist_ok=True)
    (C.OUT / "sota_ou_market.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))

if __name__ == "__main__":
    main()
