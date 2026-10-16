"""Does gradient boosting on our rating features (the 2017/2023 Soccer Prediction Challenge recipe: GBT on
rating features) beat the production Poisson model, alone or stacked on it? Research only (2026-10-15).

Protocol: fit on train, choose settings on validation (1X2 log loss), refit on train+validation with the chosen
settings and number of trees, score the test split ONCE. Baseline = production out-of-sample 1X2
(baseline_predictions_full.csv.gz).

Run (from backend/): OMP_NUM_THREADS=2 venv/Scripts/python.exe scripts/research/sota_gbm_experiment.py
Output: backend/data/research/sota_gbm_experiment.json
"""
from __future__ import annotations

import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sota_common as C  # noqa: E402

SIDE = ["xi_d_off", "xi_d_def", "xg_for_l5", "xg_against_l5", "ppg_l5", "gf_l5", "ga_l5", "rest_days",
        "n_matches_14d", "euro_before_3d", "euro_after_3d", "n_injury", "n_suspension", "unavail_off_w",
        "unavail_def_w"]
GLOBAL = ["value_log_ratio", "lineup_form", "comp_is_euro", "league_hadv", "league_hadv_dev"]


def build():
    feats = {r["match_id"]: r for r in C.read_csv_gz(C.DATA / "training" / "match_features_full.csv.gz")}
    preds = C.read_csv_gz(C.DATA / "training" / "baseline_predictions_full.csv.gz")
    X, LP, Y, S = [], [], [], []
    names = ["ln_lam_h", "ln_lam_a", "lam_diff", "lam_sum"] + GLOBAL + [f"{s}_{c}" for s in ("home", "away")
                                                                       for c in SIDE]
    for p in preds:
        if p["split"] not in ("train", "validation", "test") or not p["p_home"] or p["result"] not in "HDA":
            continue
        f = feats.get(p["match_id"])
        if f is None:
            continue
        lh, la = C.fnum(f["lambda_home"]), C.fnum(f["lambda_away"])
        if not lh or not la:
            continue
        row = [math.log(lh), math.log(la), math.log(lh) - math.log(la), lh + la]
        for g in GLOBAL:
            v = C.fnum(f.get(g))
            row.append(np.nan if v is None else v)
        for s in ("home", "away"):
            for c in SIDE:
                v = C.fnum(f.get(f"{s}_{c}"))
                row.append(np.nan if v is None else v)
        X.append(row)
        LP.append(np.log(np.clip([float(p["p_home"]), float(p["p_draw"]), float(p["p_away"])], 1e-9, 1)))
        Y.append({"H": 0, "D": 1, "A": 2}[p["result"]])
        S.append(p["split"])
    return np.array(X, float), np.array(LP), np.array(Y), np.array(S), names


def hgb(params, n_iter):
    return HistGradientBoostingClassifier(learning_rate=params["lr"], max_leaf_nodes=params["leaves"],
                                          min_samples_leaf=params["msl"], l2_regularization=params["l2"],
                                          max_iter=n_iter, early_stopping=False, random_state=0)


def staged_best(model, Xtr, ytr, Xva, yva):
    model.fit(Xtr, ytr)
    best = (9.0, 0)
    for i, P in enumerate(model.staged_predict_proba(Xva), start=1):
        ll = float(C.logloss(P, yva).mean())
        if ll < best[0]:
            best = (ll, i)
    return best


def main() -> None:
    X, LP, Y, S, names = build()
    tr, va, te = S == "train", S == "validation", S == "test"
    Pbase = np.exp(LP)
    out = {"n": {"train": int(tr.sum()), "validation": int(va.sum()), "test": int(te.sum())}, "features": names,
           "baseline": {"validation": C.summary(Pbase[va], Y[va]), "test": C.summary(Pbase[te], Y[te])}}

    grid = [dict(lr=lr, leaves=lv, msl=ms, l2=l2) for lr, lv, ms, l2 in
            itertools.product((0.03,), (7, 15), (100, 400), (1.0, 10.0))]
    variants = {"gbm_features": X, "gbm_features_plus_baseline_logp": np.hstack([X, LP])}
    for vname, XX in variants.items():
        sel = []
        for g in grid:
            ll, it = staged_best(hgb(g, 600), XX[tr], Y[tr], XX[va], Y[va])
            sel.append({"params": g, "val_logloss": round(ll, 5), "n_iter": it})
        sel.sort(key=lambda d: d["val_logloss"])
        best = sel[0]
        m = hgb(best["params"], max(best["n_iter"], 1))
        m.fit(XX[tr | va], Y[tr | va])
        P = m.predict_proba(XX[te])
        out[vname] = {"validation_grid_top3": sel[:3], "chosen": best,
                      "test": C.summary(P, Y[te]),
                      "test_minus_baseline_logloss": C.paired_ci(C.logloss(P, Y[te]), C.logloss(Pbase[te], Y[te])),
                      "test_minus_baseline_rps": C.paired_ci(C.rps(P, Y[te]), C.rps(Pbase[te], Y[te]))}
        print(vname, best, out[vname]["test"], out[vname]["test_minus_baseline_logloss"], flush=True)

    # simple stacking: multinomial logistic regression on the baseline log-probabilities + standardised features
    Xf = np.nan_to_num(X, nan=0.0)
    miss = np.isnan(X).astype(float)
    mu, sd = Xf[tr].mean(0), Xf[tr].std(0) + 1e-9
    Z = np.hstack([LP, (Xf - mu) / sd, miss[:, miss[tr].std(0) > 0]])
    res = []
    for Cc in (0.001, 0.003, 0.01, 0.03, 0.1):
        lr = LogisticRegression(C=Cc, max_iter=3000)
        lr.fit(Z[tr], Y[tr])
        res.append((float(C.logloss(lr.predict_proba(Z[va]), Y[va]).mean()), Cc))
    res.sort()
    lr = LogisticRegression(C=res[0][1], max_iter=3000).fit(Z[tr | va], Y[tr | va])
    P = lr.predict_proba(Z[te])
    out["logit_stack"] = {"validation": [{"C": c, "val_logloss": round(l, 5)} for l, c in res],
                          "test": C.summary(P, Y[te]),
                          "test_minus_baseline_logloss": C.paired_ci(C.logloss(P, Y[te]), C.logloss(Pbase[te], Y[te])),
                          "test_minus_baseline_rps": C.paired_ci(C.rps(P, Y[te]), C.rps(Pbase[te], Y[te]))}
    print("logit_stack", res[0], out["logit_stack"]["test"], out["logit_stack"]["test_minus_baseline_logloss"])

    C.OUT.mkdir(parents=True, exist_ok=True)
    path = C.OUT / "sota_gbm_experiment.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("baseline", out["baseline"])
    print("wrote", path)


if __name__ == "__main__":
    main()
