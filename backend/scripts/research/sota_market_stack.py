"""Market-anchored stacking (research, 2026-10-15).

Question 1: starting from the PRE-closing market (odds collected before line-ups are known), does adding our model
and our line-up / squad features recover part of the pre-closing -> closing improvement?
Question 2: what "Banko" hit rates do the market and our model reach at the same thresholds on the same matches?

Protocol: multinomial logistic stacking, fit on train, regularisation chosen on validation, refit on
train+validation, test scored once. All inputs are pre-kick-off (line-up features use the announced XI, so they
are available ~1 h before kick-off, i.e. later than the pre-closing odds).

Run (from backend/): OMP_NUM_THREADS=2 venv/Scripts/python.exe scripts/research/sota_market_stack.py
Output: backend/data/research/sota_market_stack.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sota_common as C  # noqa: E402

LINEUP = ["value_log_ratio", "lineup_form", "home_xi_d_off", "home_xi_d_def", "away_xi_d_off", "away_xi_d_def",
          "home_xg_for_l5", "home_xg_against_l5", "away_xg_for_l5", "away_xg_against_l5"]


def main() -> None:
    feats = {r["match_id"]: r for r in C.read_csv_gz(C.DATA / "training" / "match_features_full.csv.gz")}
    preds = C.read_csv_gz(C.DATA / "training" / "baseline_predictions_full.csv.gz")
    odds = C.odds_by_fotmob_id(C.load_odds_rows())
    rows = []
    for p in preds:
        if p["split"] not in ("train", "validation", "test") or not p["p_home"] or p["result"] not in "HDA":
            continue
        o = odds.get(p["match_id"])
        if not o:
            continue
        pre = o.get("avg_pre") if o.get("avg_pre") is not None else o.get("ps_pre")
        close = o.get("close")
        if pre is None or close is None:
            continue
        f = feats.get(p["match_id"], {})
        x = [C.fnum(f.get(c)) for c in LINEUP]
        rows.append({"split": p["split"], "y": {"H": 0, "D": 1, "A": 2}[p["result"]],
                     "model": np.array([float(p["p_home"]), float(p["p_draw"]), float(p["p_away"])]),
                     "pre": pre, "close": close, "x": np.array([np.nan if v is None else v for v in x]),
                     "div": o["division"]})
    S = np.array([r["split"] for r in rows]); Y = np.array([r["y"] for r in rows])
    Lm = np.log(np.clip(np.array([r["model"] for r in rows]), 1e-9, 1))
    Lp = np.log(np.clip(np.array([r["pre"] for r in rows]), 1e-9, 1))
    Pc = np.array([r["close"] for r in rows])
    X = np.array([r["x"] for r in rows])
    miss = np.isnan(X).astype(float)
    Xf = np.nan_to_num(X, nan=0.0)
    tr, va, te = S == "train", S == "validation", S == "test"
    mu, sd = Xf[tr].mean(0), Xf[tr].std(0) + 1e-9
    Xz = (Xf - mu) / sd
    keep = miss[tr].std(0) > 0
    designs = {"A_pre_market_recal": Lp,
               "B_pre_market_plus_model": np.hstack([Lp, Lm]),
               "C_pre_market_plus_model_plus_lineup": np.hstack([Lp, Lm, Xz, miss[:, keep]])}
    out = {"n": {"train": int(tr.sum()), "validation": int(va.sum()), "test": int(te.sum())},
           "test_reference": {"pre_market_raw": C.summary(np.exp(Lp[te]), Y[te]),
                              "closing_market": C.summary(Pc[te], Y[te]),
                              "model": C.summary(np.exp(Lm[te]), Y[te])}}
    base_te = C.logloss(np.exp(Lp[te]), Y[te])
    close_te = C.logloss(Pc[te], Y[te])
    preds_te = {}
    for name, Z in designs.items():
        res = []
        for Cc in (0.001, 0.003, 0.01, 0.03, 0.1, 1.0):
            m = LogisticRegression(C=Cc, max_iter=5000).fit(Z[tr], Y[tr])
            res.append((float(C.logloss(m.predict_proba(Z[va]), Y[va]).mean()), Cc))
        res.sort()
        m = LogisticRegression(C=res[0][1], max_iter=5000).fit(Z[tr | va], Y[tr | va])
        P = m.predict_proba(Z[te])
        preds_te[name] = P
        out[name] = {"chosen_C": res[0][1], "val_logloss": round(res[0][0], 5),
                     "test": C.summary(P, Y[te]),
                     "test_minus_pre_market_logloss": C.paired_ci(C.logloss(P, Y[te]), base_te),
                     "test_minus_closing_market_logloss": C.paired_ci(C.logloss(P, Y[te]), close_te)}
        print(name, out[name]["test"], out[name]["test_minus_pre_market_logloss"],
              out[name]["test_minus_closing_market_logloss"], flush=True)
    out["closing_minus_pre_market_logloss_test"] = C.paired_ci(close_te, base_te)

    # Banko view on the same test matches: best of {1, X, 2, 1X, X2, 12} per match
    def best_pick(P):
        cand = np.hstack([P, np.stack([P[:, 0] + P[:, 1], P[:, 1] + P[:, 2], P[:, 0] + P[:, 2]], 1)])
        hit = np.stack([Y[te] == 0, Y[te] == 1, Y[te] == 2, Y[te] != 2, Y[te] != 0, Y[te] != 1], 1)
        k = cand.argmax(1)
        return cand.max(1), hit[np.arange(len(k)), k]

    bank = {}
    for name, P in (("model", np.exp(Lm[te])), ("closing_market", Pc[te]), ("pre_market", np.exp(Lp[te]))):
        pb, hb = best_pick(P)
        fav = P.max(1); fh = P.argmax(1) == Y[te]
        bank[name] = {"double_chance_or_1x2_best": [
            {"thr": t, "n": int((pb >= t).sum()), "coverage": round(float((pb >= t).mean()), 4),
             "hit": round(float(hb[pb >= t].mean()), 4) if (pb >= t).any() else None,
             "mean_pred": round(float(pb[pb >= t].mean()), 4) if (pb >= t).any() else None}
            for t in (0.75, 0.8, 0.85, 0.9)],
            "favourite_1x2": [
            {"thr": t, "n": int((fav >= t).sum()), "hit": round(float(fh[fav >= t].mean()), 4) if (fav >= t).any() else None,
             "mean_pred": round(float(fav[fav >= t].mean()), 4) if (fav >= t).any() else None}
            for t in (0.6, 0.7, 0.8)]}
    out["banko_test_same_matches"] = bank
    C.OUT.mkdir(parents=True, exist_ok=True)
    path = C.OUT / "sota_market_stack.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out["n"]), json.dumps(out["test_reference"]), json.dumps(out["closing_minus_pre_market_logloss_test"]))
    print(json.dumps(bank, indent=0))
    print("wrote", path)


if __name__ == "__main__":
    main()
