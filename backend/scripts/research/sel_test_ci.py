"""Day-cluster bootstrap CI for the frozen meta-model comparison of sel_test.py (same frozen model: C = 0.1,
refit on train + validation; test bankos ranked by meta probability vs by raw p, top 10 / 25 / 50 %).
No new rule is chosen here; it only adds intervals to numbers already in sel_test.json.
Writes data/research/sel_test_ci.json.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sel_common as C  # noqa: E402


def main() -> None:
    from sklearn.linear_model import LogisticRegression
    d = C.load_all(include_test=True)
    test = d["split"] == "test"
    tv = ~test
    base = C.banko_index(d["P"])
    p = C.take(d["P"], base)
    hit = C.take(d["Y"], base)
    lp = np.log(p / (1 - p))
    cols = [lp] + [np.isin(base, g).astype(float) for g in C.MARKETS.values()] + [d[f].astype(float) for f in C.FLAGS]
    pk = np.clip(C.take(d["MK"], base), 1e-4, 1 - 1e-4)
    cols += [np.where(np.isfinite(pk), np.log(pk / (1 - pk)) - lp, 0.0), np.isfinite(pk).astype(float)]
    pf = C.take(d["FR"], base)
    pe = C.take(d["EL"], base)
    cols += [np.where(np.isfinite(pf), pf - 0.5, 0.0), np.where(np.isfinite(pe), pe - p, 0.0)]
    X = np.stack(cols, 1)
    fit = tv & (base >= 0)
    lr = LogisticRegression(C=0.1, max_iter=2000).fit(X[fit], hit[fit].astype(int))
    q = np.full(d["n"], np.nan)
    ev = test & (base >= 0)
    q[ev] = lr.predict_proba(X[ev])[:, 1]
    out = {}
    n_ev = int(ev.sum())
    for frac in (0.10, 0.25, 0.50):
        n = int(round(frac * n_ev))
        sm = np.zeros(d["n"], bool)
        sm[np.where(ev)[0][np.argsort(-q[ev], kind="stable")[:n]]] = True
        sr = np.zeros(d["n"], bool)
        sr[np.where(ev)[0][np.argsort(-p[ev], kind="stable")[:n]]] = True
        out[f"top{int(frac * 100)}%"] = {"n": n, "meta_hit": round(float(hit[sm].mean()), 4),
                                         "raw_hit": round(float(hit[sr].mean()), 4),
                                         "diff_meta_minus_raw": C.day_cluster_boot(hit, sm, hit, sr, d["date"]),
                                         "share_with_market_meta": round(float(np.isfinite(C.take(d["MK"], base))[sm].mean()), 4),
                                         "share_with_market_raw": round(float(np.isfinite(C.take(d["MK"], base))[sr].mean()), 4)}
    out["coef"] = dict(zip(["logit_p"] + [f"is_{m}" for m in C.MARKETS] + C.FLAGS +
                           ["market_logit_minus_model", "has_market", "form_rate-0.5", "elo_p-model_p"],
                           [round(float(c), 4) for c in lr.coef_[0]]))
    C.dump(out, "sel_test_ci.json")
    print(out)


if __name__ == "__main__":
    main()
