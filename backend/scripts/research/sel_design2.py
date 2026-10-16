"""Selective-prediction study, DESIGN stage 2 (train + validation only; test rows dropped at load).

Follow-up checks before freezing the rules:
  1. composition + calibration by candidate type of the high-threshold Banko (p >= 0.85 / 0.90)
  2. hit rate per competition of the p >= 0.85 Banko (heterogeneity)
  3. on rows with closing odds: Banko by model vs by blend (model + market)/2 vs by market vs model AND market,
     each against model-only picks at the same number of picks
  4. Banko without the '12' (no draw) candidate
  5. Learn-then-Test threshold certification, sequence started where >= 300 picks (counts only)
Writes data/research/sel_design2.json.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sel_common as C  # noqa: E402
from sel_design import banko_summary, by_type, denom, ltt_threshold, top_n_mask  # noqa: E402


def ltt_n300(p, hit, alpha, delta=0.1, top=0.95):
    from scipy.stats import binom
    grid = np.round(np.arange(top, 0.695, -0.01), 2)
    chosen, trace, started = None, [], False
    for t in grid:
        sel = p >= t
        n = int(sel.sum())
        if not started and n < 300:
            continue
        started = True
        err = int((~hit[sel]).sum())
        pval = float(binom.cdf(err, n, alpha))
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
    tr, va = d["split"] == "train", d["split"] == "validation"
    out = {}
    P = d["P"]

    # 1. composition / calibration by type
    for lo in (0.85, 0.90):
        b = C.banko_index(P, lo=lo)
        out[f"by_type_lo{lo:.2f}"] = {"train": by_type(d, b, tr), "validation": by_type(d, b, va)}
        # euro vs league
        out[f"seg_lo{lo:.2f}"] = {s: banko_summary(d, b, m) for s, m in
                                  (("league_tv", ~d["euro"]), ("euro_tv", d["euro"]),
                                   ("league_val", va & ~d["euro"]), ("euro_val", va & d["euro"]))}

    # 2. per competition, lo 0.85
    b85 = C.banko_index(P, lo=0.85)
    comp = {}
    for c in np.unique(d["comp"]):
        m = d["comp"] == c
        r = banko_summary(d, b85, m)
        r["matches"] = int(m.sum())
        comp[c] = r
    out["per_comp_lo0.85_tv"] = comp

    # 3. odds rows: model / blend / market / both
    odds = np.all(np.isfinite(d["MK"]), axis=1)
    n_m, n_days = denom(d, odds)
    B = (P + d["MK"]) / 2
    res = {}
    for lo in (0.80, 0.85, 0.88, 0.90):
        rules = {
            "model": C.banko_index(P, lo=lo),
            "blend": C.banko_index(B, lo=lo),
            "market": C.banko_index(d["MK"], lo=lo),
        }
        bm = C.banko_index(P, lo=lo)
        both = bm.copy()
        both[~(C.take(d["MK"], bm) >= lo)] = -1
        rules["model_and_market"] = both
        row = {}
        for k, idx in rules.items():
            sel = odds & (idx >= 0)
            hit = C.take(d["Y"], idx)
            pm = C.take(P, idx)
            r = C.rate_row(hit[sel], pm[sel], n_days, n_m)
            r["mean_market_p"] = round(float(np.nanmean(C.take(d["MK"], idx)[sel])), 4) if sel.any() else None
            if k != "model" and r["n"] >= 20:
                # model-only Banko with the same number of picks: rank matches by the model's best banko p
                bfull = C.banko_index(P, lo=0.0, hi=0.95)
                pb = C.take(P, bfull)
                mo = top_n_mask(pb, odds & (bfull >= 0), r["n"])
                hit_mo = C.take(d["Y"], bfull)
                r["model_same_n"] = C.rate_row(hit_mo[mo], pb[mo])
                r["diff_vs_model_same_n"] = C.day_cluster_boot(hit, sel, hit_mo, mo, d["date"])
            row[k] = r
        res[f"lo{lo:.2f}"] = row
    out["odds_rows_banko"] = {"rows": n_m, "days": n_days, "by_threshold": res}

    # 4. without '12'
    allowed = np.ones(14, bool)
    allowed[C.KIDX["HOME_OR_AWAY"]] = False
    for lo in (0.70, 0.85):
        b = C.banko_index(P, lo=lo, allowed=allowed[None, :].repeat(d["n"], 0))
        out[f"no12_lo{lo:.2f}"] = {"tv": banko_summary(d, b, tv), "val": banko_summary(d, b, va)}

    # 5. LTT
    ltt = {}
    for cal, m in (("train+validation", tv), ("validation", va)):
        for cap in (0.95, 0.99):
            b = C.banko_index(P, 0.0, cap)
            sel = m & (b >= 0)
            p_b, h_b = C.take(P, b)[sel], C.take(d["Y"], b)[sel]
            for alpha in (0.08, 0.10, 0.12, 0.15):
                t, trace = ltt_n300(p_b, h_b, alpha, top=cap)
                ltt[f"{cal}_cap{cap}_alpha{alpha}"] = {"threshold": t, "trace_head": trace[:2], "trace_tail": trace[-3:]}
    out["ltt_n300"] = ltt
    C.dump(out, "sel_design2.json")
    print("wrote", C.OUT / "sel_design2.json")


if __name__ == "__main__":
    main()
