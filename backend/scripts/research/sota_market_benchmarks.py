"""How good is the betting market on our football-data.co.uk leagues? (research, 2026-10-15)

Outputs backend/data/research/sota_market_benchmarks.json:
- accuracy / RPS / log loss / Brier of Pinnacle closing, Pinnacle pre-closing, market-average closing, by division
  group (top 5 leagues, all) and season;
- pre-closing -> closing improvement on the same rows (value of late information such as line-ups);
- proportional vs Shin de-vigging;
- calibration of Pinnacle closing by probability band per outcome (favourite-longshot bias, draws).

Run (from backend/): OMP_NUM_THREADS=2 venv/Scripts/python.exe scripts/research/sota_market_benchmarks.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sota_common as C  # noqa: E402


def main() -> None:
    rows = C.load_odds_rows()
    recs = []
    for r in rows:
        if r["_src"] == "history":
            ftr = r.get("FTR")
        else:
            ftr = r.get("FTR")
        y = C.result_index(ftr or "")
        if y is None:
            continue
        rec = {"div": r["division"], "season": r.get("season", ""), "y": y}
        for name, keys in (("ps_close", ("PSCH", "PSCD", "PSCA")), ("ps_pre", ("PSH", "PSD", "PSA")),
                           ("avg_close", ("AvgCH", "AvgCD", "AvgCA")), ("avg_pre", ("AvgH", "AvgD", "AvgA")),
                           ("b365_close", ("B365CH", "B365CD", "B365CA"))):
            o = C.odds_triplet(r, keys)
            rec[name] = o
        recs.append(rec)

    out: dict = {"n_rows_with_result": len(recs), "divisions": sorted({r["div"] for r in recs})}

    def block(sel, src, devig="prop"):
        P, Y = [], []
        for r in sel:
            o = r[src]
            if o is None:
                continue
            P.append(C.devig_prop(o) if devig == "prop" else C.devig_shin(o))
            Y.append(r["y"])
        if not P:
            return {"n": 0}
        return C.summary(np.array(P), np.array(Y))

    groups = {"top5": [r for r in recs if r["div"] in C.TOP5],
              "all": recs,
              "non_top5": [r for r in recs if r["div"] not in C.TOP5]}
    out["by_group"] = {g: {s: block(sel, s) for s in ("ps_close", "ps_pre", "avg_close", "b365_close")}
                       for g, sel in groups.items()}
    # per division (Pinnacle closing)
    bydiv = defaultdict(list)
    for r in recs:
        bydiv[r["div"]].append(r)
    out["by_division_ps_close"] = {d: block(sel, "ps_close") for d, sel in sorted(bydiv.items())}
    out["by_division_avg_close"] = {d: block(sel, "avg_close") for d, sel in sorted(bydiv.items())}
    # by season, top 5
    bys = defaultdict(list)
    for r in groups["top5"]:
        bys[r["season"]].append(r)
    out["top5_by_season_ps_close"] = {s: block(sel, "ps_close") for s, sel in sorted(bys.items())}

    # paired: pre-closing vs closing (Pinnacle), same rows
    for g, sel in groups.items():
        both = [r for r in sel if r["ps_close"] and r["ps_pre"]]
        if not both:
            continue
        Y = np.array([r["y"] for r in both])
        Pc = np.array([C.devig_prop(r["ps_close"]) for r in both])
        Pp = np.array([C.devig_prop(r["ps_pre"]) for r in both])
        out.setdefault("pre_vs_close_pinnacle", {})[g] = {
            "n": len(both), "close": C.summary(Pc, Y), "pre": C.summary(Pp, Y),
            "logloss_pre_minus_close": C.paired_ci(C.logloss(Pp, Y), C.logloss(Pc, Y)),
            "rps_pre_minus_close": C.paired_ci(C.rps(Pp, Y), C.rps(Pc, Y)),
            "mean_abs_prob_move_home": round(float(np.abs(Pc[:, 0] - Pp[:, 0]).mean()), 4)}

    # Shin vs proportional, Pinnacle closing and Bet365 closing (top 5 + all)
    for g in ("top5", "all"):
        for src in ("ps_close", "b365_close", "avg_close"):
            sel = [r for r in groups[g] if r[src]]
            Y = np.array([r["y"] for r in sel])
            Pp = np.array([C.devig_prop(r[src]) for r in sel])
            Ps = np.array([C.devig_shin(r[src]) for r in sel])
            ov = np.array([sum(1 / v for v in r[src]) - 1 for r in sel])
            out.setdefault("shin_vs_prop", {}).setdefault(g, {})[src] = {
                "n": len(sel), "mean_overround": round(float(ov.mean()), 4),
                "prop_logloss": round(float(C.logloss(Pp, Y).mean()), 5),
                "shin_logloss": round(float(C.logloss(Ps, Y).mean()), 5),
                "shin_minus_prop": C.paired_ci(C.logloss(Ps, Y), C.logloss(Pp, Y))}

    # calibration of Pinnacle closing (proportional devig), all rows, per outcome
    sel = [r for r in recs if r["ps_close"]]
    Y = np.array([r["y"] for r in sel])
    P = np.array([C.devig_prop(r["ps_close"]) for r in sel])
    bands = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0001]
    cal = {}
    for k, name in enumerate(("home", "draw", "away")):
        rowsk = []
        for lo, hi in zip(bands[:-1], bands[1:]):
            m = (P[:, k] >= lo) & (P[:, k] < hi)
            if m.sum() < 30:
                continue
            obs = float((Y[m] == k).mean())
            n = int(m.sum())
            se = (obs * (1 - obs) / n) ** 0.5
            rowsk.append({"band": f"{lo:.1f}-{min(hi, 1):.1f}", "n": n, "pred": round(float(P[m, k].mean()), 4),
                          "obs": round(obs, 4), "se": round(se, 4)})
        cal[name] = rowsk
    # favourite / longshot view: any outcome
    flat_p = P.reshape(-1)
    flat_o = (np.eye(3)[Y]).reshape(-1)
    fl = []
    for lo, hi in ((0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0001)):
        m = (flat_p >= lo) & (flat_p < hi)
        n = int(m.sum())
        obs = float(flat_o[m].mean())
        fl.append({"band": f"{lo:.1f}-{min(hi, 1):.1f}", "n": n, "pred": round(float(flat_p[m].mean()), 4),
                   "obs": round(obs, 4), "se": round((obs * (1 - obs) / n) ** 0.5, 4)})
    out["pinnacle_close_calibration"] = {"n_matches": int(len(Y)), "per_outcome": cal, "all_outcomes": fl}

    # how often does the draw become the market favourite; draw share when probabilities are close
    out["draw_facts_pinnacle_close"] = {
        "draw_is_argmax_share": round(float((P.argmax(1) == 1).mean()), 4),
        "max_draw_prob": round(float(P[:, 1].max()), 4),
        "actual_draw_rate": round(float((Y == 1).mean()), 4),
        "mean_pred_draw": round(float(P[:, 1].mean()), 4)}

    # share of matches whose market favourite >= threshold and hit rate
    fav = P.max(1)
    hit = P.argmax(1) == Y
    out["pinnacle_close_favourite_threshold"] = [
        {"thr": t, "coverage": round(float((fav >= t).mean()), 4), "n": int((fav >= t).sum()),
         "hit": round(float(hit[fav >= t].mean()), 4), "mean_pred": round(float(fav[fav >= t].mean()), 4)}
        for t in (0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9)]
    # double chance from the market
    dc = np.stack([P[:, 0] + P[:, 1], P[:, 1] + P[:, 2], P[:, 0] + P[:, 2]], 1)  # 1X, X2, 12
    dc_hit = np.stack([Y != 2, Y != 0, Y != 1], 1)
    best = dc.argmax(1)
    pb = dc.max(1)
    hb = dc_hit[np.arange(len(Y)), best]
    out["pinnacle_close_best_double_chance"] = [
        {"thr": t, "coverage": round(float((pb >= t).mean()), 4), "n": int((pb >= t).sum()),
         "hit": round(float(hb[pb >= t].mean()), 4), "mean_pred": round(float(pb[pb >= t].mean()), 4)}
        for t in (0.7, 0.8, 0.85, 0.9, 0.93)]

    C.OUT.mkdir(parents=True, exist_ok=True)
    path = C.OUT / "sota_market_benchmarks.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("n_rows_with_result", "by_group", "pre_vs_close_pinnacle", "shin_vs_prop",
                                          "draw_facts_pinnacle_close", "pinnacle_close_favourite_threshold",
                                          "pinnacle_close_best_double_chance")}, indent=1))
    print(json.dumps(out["pinnacle_close_calibration"]["all_outcomes"], indent=0))
    print(json.dumps(out["top5_by_season_ps_close"], indent=0))
    print("wrote", path)


if __name__ == "__main__":
    main()
