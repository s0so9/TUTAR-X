"""'Oranli' ceiling (research, 2026-10-15): per match, the most likely outcome among {1,X,2,1X,X2,12} whose
de-vigged closing price is >= 1.60 (market p <= 0.625), chosen by the market or by our model (model p used to rank,
only outcomes with market p <= 0.625 allowed). Validation+test league matches with closing odds.
Output: data/research/sota_oranli_ceiling.json"""
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
    M, K, Y = [], [], []
    for p in preds:
        if p["split"] not in ("validation", "test") or not p["p_home"] or p["result"] not in "HDA":
            continue
        o = odds.get(p["match_id"])
        if not o or o.get("close") is None:
            continue
        M.append([float(p["p_home"]), float(p["p_draw"]), float(p["p_away"])]); K.append(o["close"])
        Y.append({"H": 0, "D": 1, "A": 2}[p["result"]])
    M, K, Y = np.array(M), np.array(K), np.array(Y)
    hit = np.stack([Y == 0, Y == 1, Y == 2, Y != 2, Y != 0, Y != 1], 1)
    cm, ck = cand(M), cand(K)
    allowed = ck <= 1 / 1.60
    out = {"n_matches": int(len(Y))}
    for name, rank in (("market_ranked", ck), ("model_ranked", cm)):
        r = np.where(allowed, rank, -1)
        k = r.argmax(1)
        ok = allowed[np.arange(len(k)), k]
        h = hit[np.arange(len(k)), k][ok]
        pk = ck[np.arange(len(k)), k][ok]
        out[name] = {"n": int(ok.sum()), "hit": round(float(h.mean()), 4), "mean_market_p": round(float(pk.mean()), 4),
                     "mean_fair_odds": round(float((1 / pk).mean()), 3),
                     "flat_stake_return_at_fair_odds": round(float((h / pk).mean() - 1), 4)}
    (C.OUT / "sota_oranli_ceiling.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))

if __name__ == "__main__":
    main()
