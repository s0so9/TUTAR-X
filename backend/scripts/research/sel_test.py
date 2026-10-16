"""Selective-prediction study, TEST stage: reads the frozen rules (data/research/sel_frozen_rules.json, written
after the design stage) and scores them ONCE on the test split (2026-02-01 .. 2026-10-12, 3,402 matches).

Also the descriptive curves at the fixed thresholds 0.70..0.90 and the agreement rules of the design stage,
the Learn-then-Test thresholds, the meta-model (refit on train + validation), and same-day kombine hit rates.
Writes data/research/sel_test.json.

Run (from backend/): OMP_NUM_THREADS=2 venv/Scripts/python.exe scripts/research/sel_test.py
"""

from __future__ import annotations

import json
import sys
from math import comb
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sel_common as C  # noqa: E402
from sel_design import (agreement, banko_summary, by_type, coverage_compare, curves, denom, flag_table,  # noqa: E402
                        oranli_summary, roi_real_odds, top_n_mask)


def kombine(d, idx, mask, ks=(2, 3, 4, 5)):
    """Same-day coupons of k picks: share of all k-combinations of a day's picks in which every pick landed
    (days weighted equally), vs the mean product of the model probabilities over the same combinations."""
    sel = mask & (idx >= 0)
    hit = C.take(d["Y"], idx)
    p = C.take(d["P"], idx)
    out = {}
    days = np.unique(d["date"][sel])
    for k in ks:
        obs, exp_, nd = [], [], 0
        for day in days:
            m = sel & (d["date"] == day)
            n = int(m.sum())
            if n < k:
                continue
            h = int(hit[m].sum())
            obs.append(comb(h, k) / comb(n, k))
            # elementary symmetric polynomial e_k(p) / C(n, k)
            e = np.zeros(k + 1)
            e[0] = 1.0
            for pi in p[m]:
                e[1:] = e[1:] + pi * e[:-1]
            exp_.append(e[k] / comb(n, k))
            nd += 1
        out[f"k{k}"] = {"days": nd, "all_hit_rate": round(float(np.mean(obs)), 4) if nd else None,
                        "model_expected": round(float(np.mean(exp_)), 4) if nd else None}
    return out


def ltt_eval(d, test, thr: float, hi: float = 0.95):
    b = C.banko_index(d["P"], thr, hi)
    return banko_summary(d, b, test)


def meta_test(d, base, tv, test, Cc=0.1):
    from sklearn.linear_model import LogisticRegression
    p = C.take(d["P"], base)
    hit = C.take(d["Y"], base).astype(int)
    lp = np.log(p / (1 - p))
    cols = [lp]
    for g in C.MARKETS.values():
        cols.append(np.isin(base, g).astype(float))
    for f in C.FLAGS:
        cols.append(d[f].astype(float))
    pk = np.clip(C.take(d["MK"], base), 1e-4, 1 - 1e-4)
    cols.append(np.where(np.isfinite(pk), np.log(pk / (1 - pk)) - lp, 0.0))
    cols.append(np.isfinite(pk).astype(float))
    pf = C.take(d["FR"], base)
    cols.append(np.where(np.isfinite(pf), pf - 0.5, 0.0))
    pe = C.take(d["EL"], base)
    cols.append(np.where(np.isfinite(pe), pe - p, 0.0))
    X = np.stack(cols, 1)
    fit = tv & (base >= 0)
    ev = test & (base >= 0)
    lr = LogisticRegression(C=Cc, max_iter=2000).fit(X[fit], hit[fit])
    q = lr.predict_proba(X[ev])[:, 1]
    pv, hv = p[ev], hit[ev]
    out = {"test_logloss_meta": round(float(-np.mean(hv * np.log(q) + (1 - hv) * np.log(1 - q))), 5),
           "test_logloss_raw_p": round(float(-np.mean(hv * np.log(pv) + (1 - hv) * np.log(1 - pv))), 5)}
    for frac in (0.10, 0.25, 0.5):
        n = int(round(frac * ev.sum()))
        om = np.argsort(-q, kind="stable")[:n]
        orw = np.argsort(-pv, kind="stable")[:n]
        out[f"top{int(frac * 100)}%"] = {"meta": C.rate_row(hv[om].astype(bool), pv[om]),
                                         "raw_p": C.rate_row(hv[orw].astype(bool), pv[orw])}
    return out


def main() -> None:
    frozen_path = C.OUT / "sel_frozen_rules.json"
    if not frozen_path.exists():
        raise SystemExit("frozen rules missing: run the design stage and freeze first")
    F = json.loads(frozen_path.read_text(encoding="utf-8"))
    R = F["rules"]
    d = C.load_all(include_test=True)
    test = d["split"] == "test"
    tv = (d["split"] == "train") | (d["split"] == "validation")
    n_m, n_days = denom(d, test)
    out = {"frozen_at_utc": F["frozen_at_utc"], "test_rows": n_m, "test_days": n_days,
           "test_rows_euro": int((test & d["euro"]).sum())}
    P = d["P"]

    # ------------------------------------------------ A. curves
    out["A_model_curves"] = {"all": curves(d, P, test), "league": curves(d, P, test & ~d["euro"]),
                             "euro": curves(d, P, test & d["euro"])}
    odds_rows = test & np.all(np.isfinite(d["MK"]), axis=1) & np.all(np.isfinite(d["MKpre"]), axis=1)
    out["A_on_odds_rows"] = {"n_rows": int(odds_rows.sum()), "days": denom(d, odds_rows)[1],
                             "model": curves(d, P, odds_rows), "market_close": curves(d, d["MK"], odds_rows),
                             "market_pre": curves(d, d["MKpre"], odds_rows),
                             "blend_model_close": curves(d, (P + d["MK"]) / 2, odds_rows)}
    out["A_elo"] = curves(d, d["EL"], test, extra_any=False)
    out["A_form"] = curves(d, d["FR"], test, extra_any=False)
    print("A", flush=True)

    # ------------------------------------------------ B. agreement
    out["B_agreement_odds_rows"] = agreement(d, "odds_rows", odds_rows)
    out["B_agreement_all_rows_form_elo"] = agreement(d, "all", test)
    out["B_coverage_compare_odds_rows"] = coverage_compare(
        d, odds_rows, {"market_close": d["MK"], "market_pre": d["MKpre"], "blend_close": (P + d["MK"]) / 2,
                       "blend_pre": (P + d["MKpre"]) / 2, "min_model_close": np.fmin(P, d["MK"])})
    out["B_coverage_compare_all_rows"] = coverage_compare(
        d, test, {"min_model_form": np.fmin(P, d["FR"]),
                  "min_model_elo": np.fmin(P, np.where(np.isfinite(d["EL"]), d["EL"], P))})
    print("B", flush=True)

    # ------------------------------------------------ C. rules
    base = C.banko_index(P, R["R0_current_banko"]["lo"], R["R0_current_banko"]["hi"])
    rules = {"R0_current_banko": base}
    for name in ("R1_banko85", "R2_banko88", "R3_banko90"):
        rules[name] = C.banko_index(P, R[name]["lo"], R[name]["hi"])
    for a in ("alpha0.08", "alpha0.10", "alpha0.12", "alpha0.15"):
        rules[f"R4_ltt_{a}(thr {R['R4_ltt'][a]})"] = C.banko_index(P, R["R4_ltt"][a], 0.95)

    def drop(idx, m):
        x = idx.copy()
        x[m] = -1
        return x

    rules["R0_no_euro"] = drop(base, d["flag_euro"])
    rules["R0_no_early"] = drop(base, d["flag_early"])
    rules["R0_no_euro_no_early"] = drop(base, d["flag_euro"] | d["flag_early"])
    r1 = rules["R1_banko85"]
    rules["R1_no_euro_no_early"] = drop(r1, d["flag_euro"] | d["flag_early"])
    C_out = {"all_test": {}, "by_type": {}, "league": {}, "euro": {}, "roi_real_odds": {}}
    for k, idx in rules.items():
        C_out["all_test"][k] = banko_summary(d, idx, test, n_m, n_days)
        C_out["league"][k] = banko_summary(d, idx, test & ~d["euro"])
        C_out["euro"][k] = banko_summary(d, idx, test & d["euro"])
        C_out["roi_real_odds"][k] = roi_real_odds(d, idx, test)
    for k in ("R0_current_banko", "R1_banko85", "R3_banko90"):
        C_out["by_type"][k] = by_type(d, rules[k], test)
    # odds rows: model vs market-confirmed vs blend
    odds1 = test & np.all(np.isfinite(d["MK"]), axis=1)
    no, nd_o = denom(d, odds1)
    B = (P + d["MK"]) / 2
    both = C.banko_index(P, 0.85).copy()
    both[~(C.take(d["MK"], both) >= 0.85)] = -1
    odds_rules = {"R1_model85_on_odds_rows": C.banko_index(P, 0.85), "R5a_model_and_market85": both,
                  "R5b_blend85": C.banko_index(B, 0.85), "R5c_blend88": C.banko_index(B, 0.88),
                  "market_only85": C.banko_index(d["MK"], 0.85), "R0_on_odds_rows": base}
    bfull = C.banko_index(P, 0.0, 0.95)
    pb = C.take(P, bfull)
    hb = C.take(d["Y"], bfull)
    oo = {"rows": no, "days": nd_o}
    for k, idx in odds_rules.items():
        sel = odds1 & (idx >= 0)
        r = C.rate_row(C.take(d["Y"], idx)[sel], C.take(P, idx)[sel], nd_o, no)
        r["mean_market_p"] = round(float(np.nanmean(C.take(d["MK"], idx)[sel])), 4) if sel.any() else None
        if k not in ("R1_model85_on_odds_rows", "R0_on_odds_rows") and r["n"] >= 20:
            mo = top_n_mask(pb, odds1 & (bfull >= 0), r["n"])
            r["model_same_n"] = C.rate_row(hb[mo], pb[mo])
            r["diff_vs_model_same_n"] = C.day_cluster_boot(C.take(d["Y"], idx), sel, hb, mo, d["date"])
        oo[k] = r
    C_out["odds_rows"] = oo
    # Oranli
    C_out["oranli_current"] = oranli_summary(d, base, test)
    C_out["oranli_with_R1_banko"] = oranli_summary(d, r1, test)
    # bands of the current banko
    p0 = C.take(P, base)
    h0 = C.take(d["Y"], base)
    bands = [(0.70, 0.75), (0.75, 0.80), (0.80, 0.85), (0.85, 0.90), (0.90, 0.95001)]
    C_out["banko_bands"] = {f"{lo:.2f}-{min(hi, 0.95):.2f}": C.rate_row(h0[test & (p0 >= lo) & (p0 < hi)],
                                                                      p0[test & (p0 >= lo) & (p0 < hi)])
                            for lo, hi in bands}
    # per competition, R1
    comp = {}
    for c in np.unique(d["comp"][test]):
        m = test & (d["comp"] == c)
        r = banko_summary(d, r1, m)
        r["matches"] = int(m.sum())
        comp[c] = r
    C_out["per_comp_R1"] = comp
    # monthly stability, R0 and R1
    months = sorted(set(k[:7] for k in d["date"][test]))
    C_out["monthly"] = {mo: {"R0": banko_summary(d, base, test & (np.char.startswith(d["date"], mo))),
                             "R1": banko_summary(d, r1, test & (np.char.startswith(d["date"], mo)))}
                        for mo in months}
    out["C_rules"] = C_out
    print("C", flush=True)

    # ------------------------------------------------ D. flags / meta
    out["D_flags_R0"] = flag_table(d, base, test)
    out["D_flags_R1"] = flag_table(d, r1, test)
    out["D_meta_model"] = meta_test(d, base, tv, test)
    # ------------------------------------------------ E. kombine
    out["E_kombine"] = {k: kombine(d, rules[k], test) for k in ("R0_current_banko", "R1_banko85", "R3_banko90")}
    C.dump(out, "sel_test.json")
    print("wrote", C.OUT / "sel_test.json")


if __name__ == "__main__":
    main()
