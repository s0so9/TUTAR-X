"""Banko-style selection on validation+test league matches with closing and pre-closing odds (research, 2026-10-15):
best of {1,X,2,1X,X2,12} by source, and an agreement filter (model and market pick the same outcome, both >= thr).
Output: data/research/sota_banko_agreement.json"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sota_common as C  # noqa: E402

def cand(P):
    return np.hstack([P, np.stack([P[:, 0] + P[:, 1], P[:, 1] + P[:, 2], P[:, 0] + P[:, 2]], 1)])

def main():
    preds = C.read_csv_gz(C.DATA / "training" / "baseline_predictions_full.csv.gz")
    odds = C.odds_by_fotmob_id(C.load_odds_rows())
    M, K, Y, S = [], [], [], []
    for p in preds:
        if p["split"] not in ("validation", "test") or not p["p_home"] or p["result"] not in "HDA":
            continue
        o = odds.get(p["match_id"])
        if not o or o.get("close") is None:
            continue
        M.append([float(p["p_home"]), float(p["p_draw"]), float(p["p_away"])]); K.append(o["close"])
        Y.append({"H": 0, "D": 1, "A": 2}[p["result"]]); S.append(p["split"])
    M, K, Y, S = np.array(M), np.array(K), np.array(Y), np.array(S)
    hit = np.stack([Y == 0, Y == 1, Y == 2, Y != 2, Y != 0, Y != 1], 1)
    out = {}
    for sp in ("validation", "test", "both"):
        m = np.ones(len(Y), bool) if sp == "both" else S == sp
        cm, ck, h = cand(M[m]), cand(K[m]), hit[m]
        km, kk = cm.argmax(1), ck.argmax(1)
        pm, pk = cm.max(1), ck.max(1)
        hm, hk = h[np.arange(len(km)), km], h[np.arange(len(kk)), kk]
        rows = []
        for t in (0.8, 0.85, 0.9):
            agree = (km == kk) & (pm >= t) & (pk >= t)
            rows.append({"thr": t, "n_matches": int(m.sum()),
                         "model": {"n": int((pm >= t).sum()), "hit": round(float(hm[pm >= t].mean()), 4), "mean_p": round(float(pm[pm >= t].mean()), 4)},
                         "market": {"n": int((pk >= t).sum()), "hit": round(float(hk[pk >= t].mean()), 4), "mean_p": round(float(pk[pk >= t].mean()), 4)},
                         "agree_both": {"n": int(agree.sum()), "hit": round(float(hk[agree].mean()), 4) if agree.any() else None},
                         "model_only_not_market": {"n": int(((pm >= t) & ~(pk >= t)).sum()),
                                                   "hit": round(float(hm[(pm >= t) & ~(pk >= t)].mean()), 4) if ((pm >= t) & ~(pk >= t)).any() else None}})
        out[sp] = rows
    C.OUT.mkdir(parents=True, exist_ok=True)
    (C.OUT / "sota_banko_agreement.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for sp, rows in out.items():
        for r in rows:
            print(sp, json.dumps(r))

if __name__ == "__main__":
    main()
