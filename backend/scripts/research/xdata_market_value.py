"""Research (2026-10-15, "additional data" study): how much would bookmaker odds at prediction time add?

Compares, on the same league matches, the production model's out-of-sample 1X2 / O-U 2.5 probabilities
(data/training/baseline_predictions_full.csv.gz) with de-vigged football-data.co.uk odds:
  * pre-closing ("p_pre_*"): football-data collects these "Friday afternoons for weekend games and Tuesday
    afternoons for midweek games" (football-data.co.uk notes.txt), i.e. roughly 1-3 days before kick-off and before
    line-ups: what a daily odds feed would give the app at its morning prediction;
  * closing ("p_close_*"): the last price before kick-off (needs a live feed + a re-run after line-ups).
And a logarithmic-pool blend (model + market), fitted on train+validation rows only and scored once on the test
split. Pick accuracy ("isabet") is reported at equal coverage: each source picks its own most confident matches.

No network. The DB is opened read-only (via calibration_common.load_closing_odds rules) only to translate
football-data db_match_id values into FotMob ids. Nothing is imputed: a match without odds is not used.

Run (from backend/):  OMP_NUM_THREADS=2 venv/Scripts/python.exe -I scripts/research/xdata_market_value.py
Output: data/research/xdata_market_value.json
"""
from __future__ import annotations

import csv
import gzip
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND / "scripts" / "training"))
import calibration_common as CC  # noqa: E402

OUT = BACKEND / "data" / "research" / "xdata_market_value.json"
EPS = 1e-12
B = 2000
SEED = 11


def fnum(s):
    return CC.fnum(s)


def load_odds() -> dict:
    """FotMob id -> dict(close=[h,d,a]|None, pre=[...]|None, close_o25, pre_o25). Same acceptance rules as
    calibration_common.load_closing_odds (score agrees, not awarded, first source wins)."""
    id_map = {}
    con = sqlite3.connect(f"file:{(BACKEND / 'football_intelligence.db').as_posix()}?mode=ro", uri=True)
    try:
        id_map = {r[0]: str(r[1]) for r in con.execute("select id, provider_id from matches")}
    finally:
        con.close()
    out = {}

    def rec(r):
        def tri(prefix):
            v = [fnum(r.get(f"{prefix}_home")), fnum(r.get(f"{prefix}_draw")), fnum(r.get(f"{prefix}_away"))]
            return v if all(x is not None for x in v) else None
        def ou_from_raw(pairs):
            # same rule as the football-data build: first complete pair, proportional de-vig
            for o, u in pairs:
                a, b = fnum(r.get(o)), fnum(r.get(u))
                if a and b and a > 1 and b > 1:
                    return (1 / a) / (1 / a + 1 / b)
            return None
        pre_o25 = fnum(r.get("p_pre_over25"))
        if pre_o25 is None:
            pre_o25 = ou_from_raw([("P>2.5", "P<2.5"), ("Avg>2.5", "Avg<2.5"), ("B365>2.5", "B365<2.5")])
        return {"close": tri("p_close"), "pre": tri("p_pre"), "close_o25": fnum(r.get("p_close_over25")),
                "pre_o25": pre_o25, "close_src": r.get("close_1x2_source"),
                "pre_src": r.get("pre_1x2_source")}

    with open(BACKEND / "data" / "external" / "football_data_matches.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pid = id_map.get(r.get("db_match_id") or "")
            if pid and r.get("db_score_agrees") == "1" and pid not in out:
                out[pid] = rec(r)
    with open(BACKEND / "data" / "external" / "football_data_history.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pid = r.get("fotmob_match_id") or ""
            if pid and r.get("score_agrees") == "1" and r.get("fotmob_awarded") != "1" and pid not in out:
                out[pid] = rec(r)
    return out


def load_o25() -> dict:
    o = {}
    with gzip.open(CC.DATA / "baseline_predictions_full.csv.gz", "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["status"] == "ok" and r["p_over25"]:
                o[r["match_id"]] = float(r["p_over25"])
    return o


# ------------------------------------------------------------------ pooling
def pool3(params, lp_list):
    w = params[:len(lp_list)]
    c = np.array([params[-2], params[-1], 0.0])
    z = sum(wi * lp for wi, lp in zip(w, lp_list)) + c
    z -= z.max(1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


def fit_pool3(p_list, y):
    lps = [np.log(np.clip(p, EPS, 1)) for p in p_list]
    x0 = np.r_[np.ones(len(lps)) / len(lps), 0.0, 0.0]

    def nll(t):
        q = pool3(t, lps)
        return -np.log(np.clip(q[np.arange(len(y)), y], EPS, 1)).mean()
    r = minimize(nll, x0, method="L-BFGS-B")
    return r.x


def logit(p):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return np.log(p / (1 - p))


def fit_pool2(p_list, y):
    X = np.stack([logit(p) for p in p_list], 1)

    def nll(t):
        z = X @ t[:-1] + t[-1]
        q = 1 / (1 + np.exp(-z))
        return -np.mean(y * np.log(np.clip(q, EPS, 1)) + (1 - y) * np.log(np.clip(1 - q, EPS, 1)))
    r = minimize(nll, np.r_[np.ones(X.shape[1]) / X.shape[1], 0.0], method="L-BFGS-B")
    return r.x


def apply_pool2(t, p_list):
    X = np.stack([logit(p) for p in p_list], 1)
    return 1 / (1 + np.exp(-(X @ t[:-1] + t[-1])))


# ------------------------------------------------------------------ metrics
def ll3(p, y):
    return -np.log(np.clip(p[np.arange(len(y)), y], EPS, 1))


def ll2(p, y):
    return -(y * np.log(np.clip(p, EPS, 1)) + (1 - y) * np.log(np.clip(1 - p, EPS, 1)))


def boot_diff(d):
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(d), size=(B, len(d)))
    b = d[idx].mean(1)
    return {"mean": round(float(d.mean()), 5), "ci90": [round(float(np.quantile(b, .05)), 5),
                                                         round(float(np.quantile(b, .95)), 5)]}


def picks_1x2(p):
    return p.argmax(1), p.max(1)


def picks_dc(p):
    dc = np.stack([p[:, 0] + p[:, 1], p[:, 1] + p[:, 2], p[:, 0] + p[:, 2]], 1)  # 1X, X2, 12
    return dc.argmax(1), dc.max(1)


def hit_dc(pick, y):
    # 1X wins unless away; X2 wins unless home; 12 wins unless draw
    return np.where(pick == 0, y != 2, np.where(pick == 1, y != 0, y != 1))


def coverage_table(conf: dict, hit: dict, fracs=(0.05, 0.10, 0.20, 0.30, 0.50, 1.0), ref="model"):
    """Hit rate of each source's top-f most confident picks; bootstrap 90% CI of (source - ref)."""
    n = len(next(iter(conf.values())))
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, n, size=(1000, n))
    out = []
    for f in fracs:
        k = max(1, int(round(f * n)))
        row = {"coverage": f, "k": k}
        tops = {}
        for s in conf:
            order = np.argsort(-conf[s], kind="stable")[:k]
            tops[s] = order
            row[s] = {"hit": round(float(hit[s][order].mean()), 4),
                      "mean_conf": round(float(conf[s][order].mean()), 4),
                      "min_conf": round(float(conf[s][order].min()), 4)}
        for s in conf:
            if s == ref:
                continue
            bs = []
            for ii in idx:
                kk = max(1, int(round(f * len(ii))))
                a = ii[np.argsort(-conf[s][ii], kind="stable")[:kk]]
                b = ii[np.argsort(-conf[ref][ii], kind="stable")[:kk]]
                bs.append(hit[s][a].mean() - hit[ref][b].mean())
            row[f"{s}_minus_{ref}"] = {"mean": round(float(hit[s][tops[s]].mean() - hit[ref][tops[ref]].mean()), 4),
                                       "ci90": [round(float(np.quantile(bs, .05)), 4),
                                                round(float(np.quantile(bs, .95)), 4)]}
        out.append(row)
    return out


def threshold_table(conf: dict, hit: dict, thrs=(0.60, 0.70, 0.75, 0.80, 0.85)):
    out = []
    for t in thrs:
        row = {"threshold": t}
        for s in conf:
            sel = conf[s] >= t
            n = int(sel.sum())
            row[s] = {"n": n, "hit": round(float(hit[s][sel].mean()), 4) if n else None,
                      "mean_conf": round(float(conf[s][sel].mean()), 4) if n else None}
        out.append(row)
    return out


def main() -> int:
    d = CC.load_baseline()
    odds = load_odds()
    o25 = load_o25()
    mid = d["match_id"]
    has_pre = np.array([m in odds and odds[m]["pre"] is not None for m in mid])
    has_close = np.array([m in odds and odds[m]["close"] is not None for m in mid])
    both = has_pre & has_close
    res = {"inputs": {"baseline_rows": int(d["n"]), "with_close_1x2": int(has_close.sum()),
                      "with_pre_1x2": int(has_pre.sum()), "with_both": int(both.sum())},
           "note": "pre-closing = football-data odds collected Friday afternoon (weekend) / Tuesday afternoon "
                   "(midweek); closing = last price. League matches only (no European odds in the sources). "
                   "Model = production model out-of-sample (baseline_predictions_full.csv.gz). Blend weights "
                   "fitted on train+validation rows only; all metrics on the test split."}
    split = d["split"]
    fit = both & np.isin(split, ["train", "validation"])
    te = both & (split == "test")
    y = d["y"]
    P = {"model": d["p"],
         "pre": np.array([odds[m]["pre"] if b else [np.nan] * 3 for m, b in zip(mid, both)], float),
         "close": np.array([odds[m]["close"] if b else [np.nan] * 3 for m, b in zip(mid, both)], float)}
    for k in ("pre", "close"):
        P[k] = P[k] / P[k].sum(1, keepdims=True)
    # blends (fit on fit rows)
    t_pre = fit_pool3([P["model"][fit], P["pre"][fit]], y[fit])
    t_close = fit_pool3([P["model"][fit], P["close"][fit]], y[fit])
    lp = lambda k: np.log(np.clip(P[k], EPS, 1))  # noqa: E731
    P["blend_model_pre"] = np.full_like(P["model"], np.nan)
    P["blend_model_pre"][both] = pool3(t_pre, [lp("model")[both], lp("pre")[both]])
    P["blend_model_close"] = np.full_like(P["model"], np.nan)
    P["blend_model_close"][both] = pool3(t_close, [lp("model")[both], lp("close")[both]])
    res["blend_1x2"] = {"fit_rows": int(fit.sum()), "test_rows": int(te.sum()),
                        "model_pre": {"w_model": round(float(t_pre[0]), 4), "w_market": round(float(t_pre[1]), 4),
                                      "c_home": round(float(t_pre[2]), 4), "c_draw": round(float(t_pre[3]), 4)},
                        "model_close": {"w_model": round(float(t_close[0]), 4),
                                        "w_market": round(float(t_close[1]), 4)}}
    yt = y[te]
    L = {k: ll3(P[k][te], yt) for k in P}
    res["test_1x2_logloss"] = {k: round(float(v.mean()), 5) for k, v in L.items()}
    res["test_1x2_diffs"] = {f"{a}_minus_model": boot_diff(L[a] - L["model"]) for a in L if a != "model"}
    res["test_1x2_diffs"]["close_minus_pre"] = boot_diff(L["close"] - L["pre"])
    res["test_1x2_diffs"]["blend_model_pre_minus_pre"] = boot_diff(L["blend_model_pre"] - L["pre"])
    # O/U 2.5
    ou_ok = np.array([m in odds and odds[m]["pre_o25"] is not None and odds[m]["close_o25"] is not None
                      and m in o25 for m in mid])
    fit2, te2 = ou_ok & np.isin(split, ["train", "validation"]), ou_ok & (split == "test")
    yo = ((d["hg"] + d["ag"]) > 2.5).astype(float)
    Q = {"model": np.array([o25.get(m, np.nan) for m in mid]),
         "pre": np.array([odds[m]["pre_o25"] if ok else np.nan for m, ok in zip(mid, ou_ok)], float),
         "close": np.array([odds[m]["close_o25"] if ok else np.nan for m, ok in zip(mid, ou_ok)], float)}
    s2 = fit_pool2([Q["model"][fit2], Q["pre"][fit2]], yo[fit2])
    Q["blend_model_pre"] = np.full(len(mid), np.nan)
    Q["blend_model_pre"][ou_ok] = apply_pool2(s2, [Q["model"][ou_ok], Q["pre"][ou_ok]])
    LO = {k: ll2(Q[k][te2], yo[te2]) for k in Q}
    res["test_ou25"] = {"fit_rows": int(fit2.sum()), "test_rows": int(te2.sum()),
                        "blend_params": [round(float(x), 4) for x in s2],
                        "logloss": {k: round(float(v.mean()), 5) for k, v in LO.items()},
                        "diffs": {f"{a}_minus_model": boot_diff(LO[a] - LO["model"]) for a in LO if a != "model"}}
    # pick accuracy at equal coverage (test)
    srcs = ["model", "pre", "close", "blend_model_pre"]
    conf1, hit1, confd, hitd = {}, {}, {}, {}
    for s in srcs:
        pk, cf = picks_1x2(P[s][te])
        conf1[s], hit1[s] = cf, (pk == yt).astype(float)
        pk2, cf2 = picks_dc(P[s][te])
        confd[s], hitd[s] = cf2, hit_dc(pk2, yt).astype(float)
    res["picks_1x2_by_coverage"] = coverage_table(conf1, hit1)
    res["picks_double_chance_by_coverage"] = coverage_table(confd, hitd)
    res["picks_1x2_by_threshold"] = threshold_table(conf1, hit1)
    res["picks_double_chance_by_threshold"] = threshold_table(confd, hitd, thrs=(0.75, 0.80, 0.85, 0.90))
    confo, hito = {}, {}
    yot = yo[te2]
    for s in srcs:
        q = Q[s][te2]
        side = q >= 0.5
        confo[s] = np.where(side, q, 1 - q)
        hito[s] = (side == (yot == 1)).astype(float)
    res["picks_ou25_by_coverage"] = coverage_table(confo, hito)
    res["picks_ou25_by_threshold"] = threshold_table(confo, hito, thrs=(0.60, 0.65, 0.70))
    # all splits (no fitted blend): model vs pre-closing vs closing on every league match with both odds.
    # The model rows are walk-forward out-of-sample for the ratings (see README); more matches -> tighter CIs.
    yb = y[both]
    La = {k: ll3(P[k][both], yb) for k in ("model", "pre", "close")}
    allres = {"n": int(both.sum()), "logloss": {k: round(float(v.mean()), 5) for k, v in La.items()},
              "pre_minus_model": boot_diff(La["pre"] - La["model"]),
              "close_minus_pre": boot_diff(La["close"] - La["pre"])}
    c1, h1, c2, h2 = {}, {}, {}, {}
    for s_ in ("model", "pre", "close"):
        pk, cf = picks_1x2(P[s_][both])
        c1[s_], h1[s_] = cf, (pk == yb).astype(float)
        pk2, cf2 = picks_dc(P[s_][both])
        c2[s_], h2[s_] = cf2, hit_dc(pk2, yb).astype(float)
    allres["picks_1x2_by_coverage"] = coverage_table(c1, h1)
    allres["picks_double_chance_by_coverage"] = coverage_table(c2, h2)
    allres["picks_1x2_by_threshold"] = threshold_table(c1, h1)
    allres["picks_double_chance_by_threshold"] = threshold_table(c2, h2, thrs=(0.75, 0.80, 0.85, 0.90))
    comp = d["comp"][both]
    bycomp = {}
    for c in sorted(set(comp)):
        m = comp == c
        if m.sum() < 300:
            continue
        bycomp[CC.LEAGUE_NAMES.get(c, c)] = {"n": int(m.sum()),
                                            "model": round(float(La["model"][m].mean()), 5),
                                            "pre": round(float(La["pre"][m].mean()), 5),
                                            "pre_minus_model": boot_diff(La["pre"][m] - La["model"][m])}
    allres["by_competition"] = bycomp
    res["all_splits_model_vs_market"] = allres
    print("ALL SPLITS", json.dumps({k: allres[k] for k in ("n", "logloss", "pre_minus_model", "close_minus_pre")}))
    for name in ("picks_1x2_by_coverage", "picks_double_chance_by_coverage"):
        print(name)
        for row in allres[name]:
            print(" ", row["coverage"], row["k"], {s_: row[s_]["hit"] for s_ in ("model", "pre", "close")},
                  {k: v for k, v in row.items() if k.endswith("_minus_model")})
    for name in ("picks_1x2_by_threshold", "picks_double_chance_by_threshold"):
        print(name)
        for row in allres[name]:
            print(" ", row["threshold"], {s_: (row[s_]["n"], row[s_]["hit"]) for s_ in ("model", "pre", "close")})
    # agreement: how often do model and pre-closing market pick the same 1X2 side on test?
    res["test_pick_agreement_model_vs_pre"] = round(float((P["model"][te].argmax(1) == P["pre"][te].argmax(1)).mean()), 4)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("inputs", "blend_1x2", "test_1x2_logloss", "test_1x2_diffs")}, indent=1))
    print(json.dumps(res["test_ou25"], indent=1))
    for name in ("picks_1x2_by_coverage", "picks_double_chance_by_coverage", "picks_ou25_by_coverage"):
        print(name)
        for row in res[name]:
            print(" ", row["coverage"], row["k"], {s: row[s]["hit"] for s in srcs},
                  {k: v for k, v in row.items() if k.endswith("_minus_model")})
    for name in ("picks_1x2_by_threshold", "picks_double_chance_by_threshold", "picks_ou25_by_threshold"):
        print(name)
        for row in res[name]:
            print(" ", row["threshold"], {s: (row[s]["n"], row[s]["hit"]) for s in srcs})
    print("agreement", res["test_pick_agreement_model_vs_pre"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
