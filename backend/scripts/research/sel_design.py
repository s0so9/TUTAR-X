"""Selective-prediction study, DESIGN stage: train + validation only (the test rows are dropped at load).

Computes, for the production model's out-of-sample probabilities:
  A. hit rate vs coverage per main market at thresholds 0.70 .. 0.90 (+ market-implied, Elo, form for reference)
  B. agreement rules (model + market / last-5 form / Elo, 2-of-3, 3-of-3) and whether they beat model-only
     picks at the SAME coverage (model-only = the same number of top-probability picks on the same rows)
  C. the app's Banko / Oranli rules and variants (thresholds, abstain on UEFA / early season / missing XI ...)
  D. uncertainty flags, a logistic meta-model for "does the banko land", risk-controlled thresholds (LTT)
Writes data/research/sel_design.json. Nothing here reads a test row.

Run (from backend/): OMP_NUM_THREADS=2 venv/Scripts/python.exe scripts/research/sel_design.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sel_common as C  # noqa: E402

T = [0.70, 0.75, 0.80, 0.85, 0.90]
SEG_DEF = {"all": None, "league": "league", "euro": "euro"}


def seg_mask(d, seg):
    if seg == "league":
        return ~d["euro"]
    if seg == "euro":
        return d["euro"]
    return np.ones(d["n"], bool)


def denom(d, mask):
    return int(mask.sum()), len(np.unique(d["date"][mask]))


# ------------------------------------------------------------------------------------------ A. curves
def curves(d, P, mask, extra_any=True):
    n_m, n_days = denom(d, mask)
    out = {}
    for mname, g in C.MARKETS.items():
        idx, p = C.group_pick(P, g)
        hit = C.take(d["Y"], idx)
        rows = []
        for t in T:
            sel = mask & (p >= t)
            rows.append({"thr": t, **C.rate_row(hit[sel], p[sel], n_days, n_m)})
        out[mname] = rows
    if extra_any:
        Pn = np.where(np.isfinite(P), P, -1)
        j = np.argmax(Pn, 1)
        p = Pn[np.arange(len(j)), j]
        hit = d["Y"][np.arange(len(j)), j]
        out["best_any_market"] = [{"thr": t, **C.rate_row(hit[mask & (p >= t)], p[mask & (p >= t)], n_days, n_m)}
                                  for t in T]
    return out


# ------------------------------------------------------------------------------------------ B. agreement
def top_n_mask(score, elig, n):
    s = np.where(elig & np.isfinite(score), score, -np.inf)
    order = np.argsort(-s, kind="stable")
    m = np.zeros(len(s), bool)
    m[order[:n]] = True
    return m & elig


def agreement(d, mask_name, elig, form_thr=0.6, conf_margin=0.0):
    """Per market group and threshold: model-only vs model + confirmers, with coverage-matched model-only."""
    res = {}
    n_m, n_days = denom(d, elig)
    for mname, g in C.MARKETS.items():
        idx, pm = C.group_pick(d["P"], g)
        hit = C.take(d["Y"], idx)
        pk = C.take(d["MK"], idx)
        pkp = C.take(d["MKpre"], idx)
        pf = C.take(d["FR"], idx)
        pe = C.take(d["EL"], idx)
        rows = []
        for t in T:
            base = elig & (pm >= t)
            K = pk >= t - conf_margin
            Kp = pkp >= t - conf_margin
            F = pf >= form_thr
            E = pe >= t - conf_margin
            has_k, has_e = np.isfinite(pk), np.isfinite(pe)
            rules = {"model": base, "model+market": base & K, "model+market_pre": base & Kp,
                     "model+form": base & F}
            if mname in ("1X2_fav", "double_chance"):
                rules["model+elo"] = base & E
                votes = K.astype(int) + F.astype(int) + E.astype(int)
                rules["model+2of3(market,form,elo)"] = base & (votes >= 2)
                rules["model+3of3"] = base & (votes == 3)
            else:
                rules["model+market+form"] = base & K & F
            row = {"thr": t}
            for rn, sel in rules.items():
                r = C.rate_row(hit[sel], pm[sel], n_days, n_m)
                if rn != "model" and r["n"] >= 20:
                    # same number of picks, chosen by model probability alone, on the same eligible rows
                    mo = top_n_mask(pm, elig, r["n"])
                    r["model_only_same_n"] = C.rate_row(hit[mo], pm[mo])
                    r["diff_vs_model_same_n"] = C.day_cluster_boot(hit, sel, hit, mo, d["date"])
                    if has_k[elig].all():
                        bl = top_n_mask((pm + pk) / 2, elig, r["n"])
                        r["blend_same_n"] = C.rate_row(hit[bl], pm[bl])
                        mk = top_n_mask(pk, elig, r["n"])
                        r["market_only_same_n"] = C.rate_row(hit[mk], pm[mk])
                row[rn] = r
            rows.append(row)
        res[mname] = rows
    return res


def coverage_compare(d, elig, scores: dict, coverages=(0.02, 0.05, 0.10, 0.20, 0.30)):
    """Hit rate at fixed coverage (fraction of eligible matches) per market group, the pick side = model side,
    ranked by each score (model p, market p, blend, min(model, market), ...)."""
    out = {}
    n_e = int(elig.sum())
    for mname, g in C.MARKETS.items():
        idx, pm = C.group_pick(d["P"], g)
        hit = C.take(d["Y"], idx)
        sc = {k: C.take(S, idx) if S.ndim == 2 else S for k, S in scores.items()}
        sc["model"] = pm
        rows = []
        for cov in coverages:
            n = int(round(cov * n_e))
            row = {"coverage": cov, "n": n}
            mo = top_n_mask(pm, elig, n)
            for k, s in sc.items():
                sel = top_n_mask(s, elig, n)
                row[k] = C.rate_row(hit[sel], pm[sel])
                if k != "model":
                    row[k]["diff_vs_model"] = C.day_cluster_boot(hit, sel, hit, mo, d["date"], n_boot=1000)
            rows.append(row)
        out[mname] = rows
    return out


# ------------------------------------------------------------------------------------------ C. banko / oranli
def banko_summary(d, idx, mask, n_m=None, n_days=None):
    if n_m is None:
        n_m, n_days = denom(d, mask)
    sel = mask & (idx >= 0)
    p = C.take(d["P"], idx)
    hit = C.take(d["Y"], idx)
    out = C.rate_row(hit[sel], p[sel], n_days, n_m)
    return out


def by_type(d, idx, mask):
    p = C.take(d["P"], idx)
    hit = C.take(d["Y"], idx)
    out = {}
    for j, k in enumerate(C.KEYS):
        sel = mask & (idx == j)
        if sel.sum():
            r = C.rate_row(hit[sel], p[sel])
            r["gap_obs_minus_pred"] = round(r["hit"] - r["mean_p"], 4)
            out[C.SHORT[k]] = r
    return out


def roi_real_odds(d, idx, mask):
    """ROI at average closing odds for picks whose market has a real price in the sources (1X2, O/U 2.5)."""
    O = np.full((d["n"], 14), np.nan)
    O[:, 0:3] = d["odds_c"]
    O[:, 8] = d["odds_c_ou"][:, 1]
    O[:, 9] = d["odds_c_ou"][:, 0]
    o = C.take(O, idx)
    hit = C.take(d["Y"], idx)
    sel = mask & (idx >= 0) & np.isfinite(o)
    if sel.sum() == 0:
        return {"n": 0}
    ret = np.where(hit[sel], o[sel] - 1, -1.0)
    return {"n": int(sel.sum()), "hit": round(float(hit[sel].mean()), 4), "mean_odds": round(float(o[sel].mean()), 3),
            "roi": round(float(ret.mean()), 4)}


def banko_variants(d):
    P = d["P"]
    base = C.banko_index(P)
    has_mk = np.all(np.isfinite(d["MK"]), axis=1)
    pk = C.take(d["MK"], base)
    pf = C.take(d["FR"], base)
    pe = C.take(d["EL"], base)
    V = {}
    for lo in (0.70, 0.75, 0.80, 0.85, 0.88, 0.90):
        V[f"lo{lo:.2f}"] = C.banko_index(P, lo=lo)
    V["lo0.70_cap0.99"] = C.banko_index(P, 0.70, 0.99)
    V["lo0.80_cap0.99"] = C.banko_index(P, 0.80, 0.99)
    V["lo0.85_cap0.99"] = C.banko_index(P, 0.85, 0.99)

    def drop(idx, m):
        x = idx.copy()
        x[m] = -1
        return x

    V["no_euro"] = drop(base, d["flag_euro"])
    V["no_early(md<=4)"] = drop(base, d["flag_early"])
    V["no_new_team"] = drop(base, d["flag_new_team"])
    V["no_lineup_missing"] = drop(base, d["flag_lineup_missing"])
    V["no_euro_no_early"] = drop(base, d["flag_euro"] | d["flag_early"])
    V["market_agree>=0.70(no odds->abstain)"] = drop(base, ~(pk >= 0.70))
    V["market_agree>=0.70(no odds->keep)"] = drop(base, np.isfinite(pk) & ~(pk >= 0.70))
    V["form_agree>=0.6"] = drop(base, ~(pf >= 0.6))
    V["elo_agree>=0.70(result picks only)"] = drop(base, (C.FAMILY[np.clip(base, 0, None)] == 0) & ~(pe >= 0.70))
    # result-family / goals-family only
    allowed_res = (C.FAMILY == 0)[None, :].repeat(d["n"], 0)
    V["result_family_only"] = C.banko_index(P, allowed=allowed_res)
    V["goals_family_only"] = C.banko_index(P, allowed=~allowed_res)
    # blend with market where odds exist
    B = np.where(np.isfinite(d["MK"]), (P + d["MK"]) / 2, P)
    V["blend_model_market_lo0.70"] = C.banko_index(B)
    V["blend_model_market_lo0.80"] = C.banko_index(B, lo=0.80)
    V["lo0.80_market_agree>=0.80(no odds->keep)"] = drop(C.banko_index(P, lo=0.80),
                                                        np.isfinite(C.take(d["MK"], C.banko_index(P, lo=0.80)))
                                                        & ~(C.take(d["MK"], C.banko_index(P, lo=0.80)) >= 0.80))
    return V, has_mk


def oranli_summary(d, banko, mask):
    n_m, n_days = denom(d, mask)
    o_fair = C.oranli_index(d["P"], banko)
    O = np.full((d["n"], 14), np.nan)
    O[:, 0:3] = d["odds_c"]
    O[:, 8] = d["odds_c_ou"][:, 1]
    O[:, 9] = d["odds_c_ou"][:, 0]
    o_priced = C.oranli_index(d["P"], banko, odds=O)
    out = {"fair_path": banko_summary(d, o_fair, mask, n_m, n_days), "fair_by_type": by_type(d, o_fair, mask)}
    out["fair_roi_where_real_odds"] = roi_real_odds(d, o_fair, mask)
    odds_rows = mask & np.isfinite(d["odds_c"][:, 0])
    out["priced_path_on_rows_with_odds"] = banko_summary(d, o_priced, odds_rows)
    out["priced_path_roi"] = roi_real_odds(d, o_priced, odds_rows)
    # variants: higher floor on p (fewer, likelier Oranli)
    for lo in (0.50, 0.55, 0.58):
        o = C.oranli_index(d["P"], banko, min_p=lo)
        out[f"fair_min_p{lo:.2f}"] = banko_summary(d, o, mask, n_m, n_days)
    # market-agree variant: market p for the pick >= 0.50
    pk = C.take(d["MK"], o_fair)
    o2 = o_fair.copy()
    o2[~(pk >= 0.5)] = -1
    out["fair_market_agree>=0.50(no odds->abstain)"] = banko_summary(d, o2, mask, n_m, n_days)
    return out


# ------------------------------------------------------------------------------------------ D. uncertainty
def flag_table(d, idx, mask):
    p = C.take(d["P"], idx)
    hit = C.take(d["Y"], idx)
    out = {}
    for f in C.FLAGS:
        for val in (True, False):
            sel = mask & (idx >= 0) & (d[f] == val)
            r = C.rate_row(hit[sel], p[sel])
            if r["n"]:
                r["gap_obs_minus_pred"] = round(r["hit"] - r["mean_p"], 4)
            out[f"{f}={int(val)}"] = r
    return out


def meta_design(d, idx):
    """Logistic meta-model P(banko lands | p, market type, flags, confirmers): fit on train, judge on validation."""
    from sklearn.linear_model import LogisticRegression
    p = C.take(d["P"], idx)
    hit = C.take(d["Y"], idx).astype(int)
    sel = idx >= 0

    def X_of(rows):
        lp = np.log(p / (1 - p))
        cols = [lp]
        for g in C.MARKETS.values():
            cols.append(np.isin(idx, g).astype(float))
        for f in C.FLAGS:
            cols.append(d[f].astype(float))
        pk = C.take(d["MK"], idx)
        cols.append(np.where(np.isfinite(pk), np.log(np.clip(pk, 1e-4, 1 - 1e-4) / (1 - np.clip(pk, 1e-4, 1 - 1e-4))) - lp, 0.0))
        cols.append(np.isfinite(pk).astype(float))
        pf = C.take(d["FR"], idx)
        cols.append(np.where(np.isfinite(pf), pf - 0.5, 0.0))
        pe = C.take(d["EL"], idx)
        cols.append(np.where(np.isfinite(pe), pe - p, 0.0))
        X = np.stack(cols, 1)
        return X[rows]

    tr = sel & (d["split"] == "train")
    va = sel & (d["split"] == "validation")
    out = {}
    for Cc in (0.01, 0.1, 1.0):
        lr = LogisticRegression(C=Cc, max_iter=2000)
        lr.fit(X_of(tr), hit[tr])
        q = lr.predict_proba(X_of(va))[:, 1]
        ll_meta = float(-np.mean(hit[va] * np.log(q) + (1 - hit[va]) * np.log(1 - q)))
        pv = p[va]
        ll_raw = float(-np.mean(hit[va] * np.log(pv) + (1 - hit[va]) * np.log(1 - pv)))
        # coverage-matched: top 25 / 50 % of validation bankos by meta prob vs by raw p
        rows = {}
        for frac in (0.25, 0.5):
            n = int(round(frac * va.sum()))
            om = np.argsort(-q, kind="stable")[:n]
            orw = np.argsort(-pv, kind="stable")[:n]
            rows[f"top{int(frac * 100)}%"] = {"meta": C.rate_row(hit[va][om].astype(bool), pv[om]),
                                              "raw_p": C.rate_row(hit[va][orw].astype(bool), pv[orw])}
        out[f"C={Cc}"] = {"val_logloss_meta": round(ll_meta, 5), "val_logloss_raw_p": round(ll_raw, 5),
                          "coef": [round(float(c), 4) for c in lr.coef_[0]], "intercept": round(float(lr.intercept_[0]), 4),
                          "coverage_matched": rows}
    out["feature_order"] = (["logit_p"] + [f"is_{m}" for m in C.MARKETS] + C.FLAGS +
                            ["market_logit_minus_model", "has_market", "form_rate-0.5", "elo_p-model_p"])
    return out


def ltt_threshold(p, hit, alpha, delta=0.1, grid=None):
    """Learn-then-Test, fixed-sequence: thresholds from high to low; keep lowering while H0 'error > alpha'
    is rejected at level delta (binomial tail). Returns the lowest certified threshold or None."""
    from scipy.stats import binom
    if grid is None:
        grid = np.round(np.arange(0.95, 0.695, -0.01), 2)
    chosen = None
    trace = []
    for t in grid:
        sel = p >= t
        n = int(sel.sum())
        if n < 50:  # start the sequence where there are enough picks (uses counts only, never labels)
            continue
        err = int((~hit[sel]).sum())
        pval = float(binom.cdf(err, n, alpha))  # P(X <= err | true error = alpha)
        trace.append({"thr": float(t), "n": n, "err_rate": round(err / n, 4), "p_value": round(pval, 5)})
        if pval <= delta:
            chosen = float(t)
        else:
            break
    return chosen, trace


def main() -> None:
    d = C.load_all(include_test=False)
    assert not np.any(d["split"] == "test")
    tv = np.ones(d["n"], bool)
    tr = d["split"] == "train"
    va = d["split"] == "validation"
    out = {"rows": {"train": int(tr.sum()), "validation": int(va.sum())},
           "days": {"train+validation": denom(d, tv)[1], "validation": denom(d, va)[1]}}

    # A. curves (model) by segment, and validation only
    out["A_model_curves"] = {seg: curves(d, d["P"], seg_mask(d, seg)) for seg in SEG_DEF}
    out["A_model_curves_validation"] = curves(d, d["P"], va)
    # reference: market, pre-closing market, Elo, form on rows with closing 1X2 + O/U 2.5
    odds_rows = np.all(np.isfinite(d["MK"]), axis=1) & np.all(np.isfinite(d["MKpre"]), axis=1)
    out["A_on_odds_rows"] = {"n_rows": int(odds_rows.sum()),
                             "model": curves(d, d["P"], odds_rows),
                             "market_close": curves(d, d["MK"], odds_rows),
                             "market_pre": curves(d, d["MKpre"], odds_rows),
                             "blend_model_close": curves(d, (d["P"] + d["MK"]) / 2, odds_rows)}
    out["A_elo_all"] = curves(d, d["EL"], tv, extra_any=False)
    out["A_form_all"] = curves(d, d["FR"], tv, extra_any=False)
    print("A done", flush=True)

    # B. agreement
    out["B_agreement_odds_rows"] = agreement(d, "odds_rows", odds_rows)
    out["B_agreement_all_rows_form_elo"] = agreement(d, "all", tv)
    out["B_agreement_odds_rows_form0.5"] = agreement(d, "odds_rows", odds_rows, form_thr=0.5)
    out["B_agreement_odds_rows_form0.7"] = agreement(d, "odds_rows", odds_rows, form_thr=0.7)
    out["B_coverage_compare_odds_rows"] = coverage_compare(
        d, odds_rows, {"market_close": d["MK"], "market_pre": d["MKpre"], "blend_close": (d["P"] + d["MK"]) / 2,
                       "blend_pre": (d["P"] + d["MKpre"]) / 2, "min_model_close": np.fmin(d["P"], d["MK"]),
                       "min_model_pre": np.fmin(d["P"], d["MKpre"])})
    out["B_coverage_compare_all_rows"] = coverage_compare(
        d, tv, {"min_model_form": np.fmin(d["P"], d["FR"]), "blend_model_form": (d["P"] + d["FR"]) / 2,
                "min_model_elo": np.fmin(d["P"], np.where(np.isfinite(d["EL"]), d["EL"], d["P"])),
                "blend_model_elo": (d["P"] + np.where(np.isfinite(d["EL"]), d["EL"], d["P"])) / 2})
    print("B done", flush=True)

    # C. banko / oranli
    base = C.banko_index(d["P"])
    C_out = {}
    for name, m in (("train+validation", tv), ("train", tr), ("validation", va)):
        C_out[name] = {"banko": banko_summary(d, base, m), "banko_by_type": by_type(d, base, m),
                       "banko_roi_where_real_odds": roi_real_odds(d, base, m),
                       "banko_league": banko_summary(d, base, m & ~d["euro"]),
                       "banko_euro": banko_summary(d, base, m & d["euro"]),
                       "oranli": oranli_summary(d, base, m)}
    V, _ = banko_variants(d)
    C_out["variants_train+validation"] = {k: banko_summary(d, v, tv) for k, v in V.items()}
    C_out["variants_validation"] = {k: banko_summary(d, v, va) for k, v in V.items()}
    C_out["variants_train"] = {k: banko_summary(d, v, tr) for k, v in V.items()}
    # banko calibration by probability band
    p = C.take(d["P"], base)
    hit = C.take(d["Y"], base)
    bands = [(0.70, 0.75), (0.75, 0.80), (0.80, 0.85), (0.85, 0.90), (0.90, 0.95001)]
    C_out["banko_bands"] = {s: {f"{lo:.2f}-{min(hi, 0.95):.2f}": C.rate_row(hit[m & (p >= lo) & (p < hi)],
                                                                            p[m & (p >= lo) & (p < hi)])
                                for lo, hi in bands} for s, m in (("train", tr), ("validation", va))}
    out["C_headline"] = C_out
    print("C done", flush=True)

    # D. uncertainty
    out["D_flags_banko"] = {s: flag_table(d, base, m) for s, m in (("train", tr), ("validation", va))}
    out["D_meta_model"] = meta_design(d, base)
    ltt = {}
    for cal_name, m in (("train+validation", tv), ("validation", va)):
        sel = m & (base >= 0)
        p_b = C.take(d["P"], base)[sel]
        h_b = C.take(d["Y"], base)[sel]
        for alpha in (0.10, 0.15, 0.20):
            t, trace = ltt_threshold(p_b, h_b, alpha)
            ltt[f"{cal_name}_alpha{alpha:.2f}"] = {"threshold": t, "trace_tail": trace[-4:]}
        # same for the 'best any market' score with the cap lifted to 0.99
        b99 = C.banko_index(d["P"], 0.70, 0.99)
        sel = m & (b99 >= 0)
        for alpha in (0.10, 0.15):
            t, trace = ltt_threshold(C.take(d["P"], b99)[sel], C.take(d["Y"], b99)[sel], alpha,
                                     grid=np.round(np.arange(0.99, 0.695, -0.01), 2))
            ltt[f"{cal_name}_cap0.99_alpha{alpha:.2f}"] = {"threshold": t, "trace_tail": trace[-4:]}
    out["D_ltt"] = ltt
    C.dump(out, "sel_design.json")
    print("wrote", C.OUT / "sel_design.json")


if __name__ == "__main__":
    main()
