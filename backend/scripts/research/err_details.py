"""Research (2026-10-15): detailed error analysis of the production model (draws, home advantage, goal markets,
model-vs-market disagreement deciles, accuracy bands, direction of the error in the weak pockets, UEFA stability).

Every fix tested here is fitted on TRAIN rows only and evaluated on validation and test (never chosen on them).
Run (from backend/):  OMP_NUM_THREADS=2 venv/Scripts/python.exe -I scripts/research/err_details.py
Output: data/research/err_details.json (+ stdout)
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import minimize, minimize_scalar

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "training"))
import train_goal_model as T  # noqa: E402
from err_common import (EPS, LEAGUE_NAMES, RES, TRAIN, acc_rows, bin_ll, boot_ci, ll_rows, load_base, r5,  # noqa: E402
                        rps_rows)
from err_pockets import build_labels  # noqa: E402

OUT = RES / "err_details.json"


def layer():
    p = json.loads((TRAIN / "goal_layer_train_only.json").read_text(encoding="utf-8"))["params"]
    return float(p["rho"]), float(p["nb_dispersion"])


def mats(mu, rho, nb, chunk=4000):
    out = np.empty((len(mu), 11, 11))
    for i in range(0, len(mu), chunk):
        out[i:i + chunk] = T.score_matrix(mu[i:i + chunk, 0], mu[i:i + chunk, 1], rho, nb)
    return out


def p1x2(m):
    return np.stack([np.tril(m, -1).sum(axis=(1, 2)), np.trace(m, axis1=1, axis2=2), np.triu(m, 1).sum(axis=(1, 2))], 1)


def main() -> int:
    D = load_base()
    rho, nb = layer()
    P, y = D["P"], D["y"]
    split = D["split"]
    tr = split == "train"
    vt = (split == "validation") | (split == "test")
    va, te = split == "validation", split == "test"
    euro = D["is_euro"]
    lg = ~euro
    has = D["has_mk"]
    M = np.where(np.isnan(D["M"]), 1 / 3, D["M"])
    ll = ll_rows(P, y)
    llm = ll_rows(M, y)
    comp_name = np.array([LEAGUE_NAMES.get(c, c) for c in D["comp"]])
    R = {}

    # ------------------------------------------------------------ A. accuracy bands
    def band(p):
        return np.select([p < .4, p < .5, p < .6, p < .7, p < .8, p < .9], ["<.40", ".40-.50", ".50-.60", ".60-.70",
                                                                             ".70-.80", ".80-.90"], ">=.90")
    acc = acc_rows(P, y)
    accm = acc_rows(M, y)
    A = {"overall": {}, "model_band_valtest": {}, "matched_valtest": {}}
    for nm, m in (("train", tr), ("validation", va), ("test", te), ("valtest", vt), ("valtest_league", vt & lg),
                  ("valtest_uefa", vt & euro)):
        A["overall"][nm] = {"n": int(m.sum()), "acc_top_pick": r5(acc[m].mean()), "ll": r5(ll[m].mean()),
                            "rps": r5(rps_rows(P[m], y[m]).mean())}
    mb = band(P.max(axis=1))
    for b in ["<.40", ".40-.50", ".50-.60", ".60-.70", ".70-.80", ".80-.90", ">=.90"]:
        for nm, m in (("valtest", vt), ("train", tr)):
            mm = m & (mb == b)
            A["model_band_valtest" if nm == "valtest" else "model_band_train"] = A.get(
                "model_band_valtest" if nm == "valtest" else "model_band_train", {})
            A["model_band_valtest" if nm == "valtest" else "model_band_train"][b] = {
                "n": int(mm.sum()), "share": r5(mm.sum() / m.sum()), "mean_p_fav": r5(P[mm].max(axis=1).mean()) if mm.sum() else None,
                "hit": r5(acc[mm].mean()) if mm.sum() else None}
    # matched rows: model vs market by each one's own band
    mk_b = band(M.max(axis=1))
    mvt = vt & has
    A["matched_valtest"]["all"] = {"n": int(mvt.sum()), "acc_model": r5(acc[mvt].mean()), "acc_market": r5(accm[mvt].mean()),
                                   "top_pick_agree": r5((P[mvt].argmax(1) == M[mvt].argmax(1)).mean())}
    for b in ["<.40", ".40-.50", ".50-.60", ".60-.70", ".70-.80", ".80-.90", ">=.90"]:
        m1 = mvt & (mb == b)
        m2 = mvt & (mk_b == b)
        A["matched_valtest"][b] = {"model_n": int(m1.sum()), "model_mean_p": r5(P[m1].max(1).mean()) if m1.sum() else None,
                                   "model_hit": r5(acc[m1].mean()) if m1.sum() else None,
                                   "market_n": int(m2.sum()), "market_mean_p": r5(M[m2].max(1).mean()) if m2.sum() else None,
                                   "market_hit": r5(accm[m2].mean()) if m2.sum() else None}
    # threshold view (banko-like)
    thr = {}
    for t in (0.6, 0.65, 0.7, 0.75, 0.8):
        m1 = mvt & (P.max(1) >= t)
        m2 = mvt & (M.max(1) >= t)
        thr[str(t)] = {"model_n": int(m1.sum()), "model_hit": r5(acc[m1].mean()) if m1.sum() else None,
                       "model_mean_p": r5(P[m1].max(1).mean()) if m1.sum() else None,
                       "market_n": int(m2.sum()), "market_hit": r5(accm[m2].mean()) if m2.sum() else None,
                       "market_mean_p": r5(M[m2].max(1).mean()) if m2.sum() else None}
    A["threshold_matched_valtest"] = thr
    R["accuracy"] = A

    # ------------------------------------------------------------ B. draws
    Bd = {"by_comp": {}, "by_balance": {}, "by_total": {}, "calib_model": {}, "calib_market": {}, "scores": {}, "fixes": {}}
    for c in sorted(set(comp_name)):
        row = {}
        for nm, m in (("valtest", vt), ("train", tr)):
            mm = m & (comp_name == c)
            mk = mm & has
            row[nm] = {"n": int(mm.sum()), "pred": r5(P[mm, 1].mean()), "obs": r5((y[mm] == 1).mean()),
                       "n_mk": int(mk.sum()), "pred_on_mk": r5(P[mk, 1].mean()) if mk.sum() else None,
                       "mk": r5(M[mk, 1].mean()) if mk.sum() else None, "obs_on_mk": r5((y[mk] == 1).mean()) if mk.sum() else None}
        Bd["by_comp"][c] = row
    bal = np.abs(P[:, 0] - P[:, 2])
    bb = np.select([bal < .1, bal < .2, bal < .35, bal < .5], ["<.10", ".10-.20", ".20-.35", ".35-.50"], ">=.50")
    tot = D["mu"].sum(1)
    tb = np.select([tot < 2.3, tot < 2.6, tot < 2.9, tot < 3.2], ["<2.3", "2.3-2.6", "2.6-2.9", "2.9-3.2"], ">=3.2")
    for key, lab, order in (("by_balance", bb, ["<.10", ".10-.20", ".20-.35", ".35-.50", ">=.50"]),
                            ("by_total", tb, ["<2.3", "2.3-2.6", "2.6-2.9", "2.9-3.2", ">=3.2"])):
        for b in order:
            row = {}
            for nm, m in (("valtest_league", vt & lg), ("train_league", tr & lg), ("valtest_uefa", vt & euro),
                          ("train_uefa", tr & euro)):
                mm = m & (lab == b)
                mk = mm & has
                row[nm] = {"n": int(mm.sum()), "pred": r5(P[mm, 1].mean()) if mm.sum() else None,
                           "obs": r5((y[mm] == 1).mean()) if mm.sum() else None,
                           "n_mk": int(mk.sum()), "mk": r5(M[mk, 1].mean()) if mk.sum() else None,
                           "pred_on_mk": r5(P[mk, 1].mean()) if mk.sum() else None,
                           "obs_on_mk": r5((y[mk] == 1).mean()) if mk.sum() else None}
            Bd[key][b] = row
    for key, src in (("calib_model", P[:, 1]), ("calib_market", M[:, 1])):
        cb = np.select([src < .15, src < .20, src < .25, src < .30], ["<.15", ".15-.20", ".20-.25", ".25-.30"], ">=.30")
        for b in ["<.15", ".15-.20", ".20-.25", ".25-.30", ">=.30"]:
            row = {}
            for nm, m in (("valtest_mk", vt & has), ("train_mk", tr & has), ("valtest_all", vt), ("train_all", tr)):
                if key == "calib_market" and not nm.endswith("_mk"):
                    continue
                mm = m & (cb == b)
                row[nm] = {"n": int(mm.sum()), "pred": r5(src[mm].mean()) if mm.sum() else None,
                           "obs": r5((y[mm] == 1).mean()) if mm.sum() else None}
            Bd[key][b] = row
    # exact scores
    mat = mats(D["mu"], rho, nb)
    hg, ag = D["hg"], D["ag"]
    for s in ((0, 0), (1, 1), (2, 2), (1, 0), (0, 1), (2, 1), (1, 2), (2, 0), (0, 2)):
        row = {}
        for nm, m in (("valtest_league", vt & lg), ("train_league", tr & lg), ("valtest_uefa", vt & euro)):
            row[nm] = {"pred": r5(mat[m, s[0], s[1]].mean()), "obs": r5(((hg[m] == s[0]) & (ag[m] == s[1])).mean())}
        Bd["scores"][f"{s[0]}-{s[1]}"] = row
    # draw fixes, fitted on train league rows, evaluated on val/test league rows
    def diag_infl(m, th):
        q = m.copy()
        idx = np.arange(11)
        q[:, idx, idx] *= np.exp(th)
        q /= q.sum(axis=(1, 2), keepdims=True)
        return q

    trl = tr & lg
    mtr = mat[trl]
    hi_, ai_ = np.minimum(hg[trl], 10), np.minimum(ag[trl], 10)

    def score_nll(th):
        q = diag_infl(mtr, th)
        return -np.log(np.clip(q[np.arange(len(q)), hi_, ai_], EPS, 1)).mean()

    r1 = minimize_scalar(score_nll, bounds=(-0.3, 0.5), method="bounded")
    th_diag = float(r1.x)
    # 1X2-likelihood draw intercept on train league rows
    def draw_shift(Pm, d):
        Q = Pm.copy()
        Q[:, 1] *= np.exp(d)
        return Q / Q.sum(1, keepdims=True)
    r2 = minimize_scalar(lambda d: ll_rows(draw_shift(P[trl], d), y[trl]).mean(), bounds=(-0.5, 0.5), method="bounded")
    d_glob = float(r2.x)
    fx = {"diag_inflation_theta_train": r5(th_diag), "draw_intercept_train": r5(d_glob)}
    Pdiag = p1x2(diag_infl(mat, th_diag))
    Pd = draw_shift(P, d_glob)
    # per-league draw intercept (train), shrunk: d_l = argmin on train rows of league + 50-match pseudo prior at d_glob
    Pdl = P.copy()
    d_l = {}
    for c in sorted(set(comp_name[lg])):
        sel = trl & (comp_name == c)
        if sel.sum() < 100:
            d_l[c] = d_glob
        else:
            k = 300.0
            rr = minimize_scalar(lambda d: ll_rows(draw_shift(P[sel], d), y[sel]).sum() + k * (d - d_glob) ** 2,
                                 bounds=(-0.6, 0.6), method="bounded")
            d_l[c] = float(rr.x)
        mm = comp_name == c
        Pdl[mm] = draw_shift(P[mm], d_l[c])
    fx["draw_intercept_by_league_train"] = {k: r5(v) for k, v in d_l.items()}
    for nm, m in (("validation_league", va & lg), ("test_league", te & lg), ("valtest_league", vt & lg)):
        row = {"n": int(m.sum()), "ll_base": r5(ll[m].mean())}
        for key, Q in (("diag_inflation", Pdiag), ("draw_intercept", Pd), ("draw_intercept_by_league", Pdl)):
            d = ll_rows(Q[m], y[m]) - ll[m]
            row[key] = {"diff": r5(d.mean()), "ci90": [r5(v) for v in boot_ci(d)], "pred_draw": r5(Q[m, 1].mean())}
        row["obs_draw"] = r5((y[m] == 1).mean())
        mk = m & has
        if mk.sum():
            row["on_market_rows"] = {"n": int(mk.sum()), "gap_base": r5((ll[mk] - llm[mk]).mean()),
                                     "gap_draw_intercept": r5((ll_rows(Pd[mk], y[mk]) - llm[mk]).mean()),
                                     "gap_draw_by_league": r5((ll_rows(Pdl[mk], y[mk]) - llm[mk]).mean())}
        fx[nm] = row
    # UEFA draw intercept (train UEFA)
    tre = tr & euro
    r3 = minimize_scalar(lambda d: ll_rows(draw_shift(P[tre], d), y[tre]).mean(), bounds=(-0.6, 0.6), method="bounded")
    fx["uefa_draw_intercept_train"] = r5(float(r3.x))
    Pu = draw_shift(P, float(r3.x))
    for nm, m in (("validation_uefa", va & euro), ("test_uefa", te & euro)):
        d = ll_rows(Pu[m], y[m]) - ll[m]
        fx[nm] = {"n": int(m.sum()), "diff": r5(d.mean()), "ci90": [r5(v) for v in boot_ci(d)],
                  "pred_draw_base": r5(P[m, 1].mean()), "pred_draw_new": r5(Pu[m, 1].mean()), "obs_draw": r5((y[m] == 1).mean())}
    fx["uefa_train_draw"] = {"pred": r5(P[tre, 1].mean()), "obs": r5((y[tre] == 1).mean()), "n": int(tre.sum())}
    Bd["fixes"] = fx
    R["draws"] = Bd

    # ------------------------------------------------------------ C. home advantage
    H = {"by_comp": {}, "by_half_year_league": {}, "fix": {}}
    gd = hg - ag
    egd = D["mu"][:, 0] - D["mu"][:, 1]
    hy = np.array([f"{t.year}H{1 if t.month <= 6 else 2}" for t in D["kickoff"]])
    for c in sorted(set(comp_name)):
        row = {}
        for nm, m in (("valtest", vt), ("train", tr)):
            mm = m & (comp_name == c)
            mk = mm & has
            row[nm] = {"n": int(mm.sum()), "pred_home": r5(P[mm, 0].mean()), "obs_home": r5((y[mm] == 0).mean()),
                       "pred_away": r5(P[mm, 2].mean()), "obs_away": r5((y[mm] == 2).mean()),
                       "pred_gd": r5(egd[mm].mean()), "obs_gd": r5(gd[mm].mean()),
                       "n_mk": int(mk.sum()), "mk_home": r5(M[mk, 0].mean()) if mk.sum() else None,
                       "mk_away": r5(M[mk, 2].mean()) if mk.sum() else None,
                       "pred_home_on_mk": r5(P[mk, 0].mean()) if mk.sum() else None,
                       "obs_home_on_mk": r5((y[mk] == 0).mean()) if mk.sum() else None}
        H["by_comp"][c] = row
    for h in sorted(set(hy)):
        mm = lg & (hy == h)
        mk = mm & has
        H["by_half_year_league"][h] = {"n": int(mm.sum()), "pred_home": r5(P[mm, 0].mean()), "obs_home": r5((y[mm] == 0).mean()),
                                       "pred_gd": r5(egd[mm].mean()), "obs_gd": r5(gd[mm].mean()),
                                       "mk_home": r5(M[mk, 0].mean()) if mk.sum() else None,
                                       "pred_home_on_mk": r5(P[mk, 0].mean()) if mk.sum() else None,
                                       "obs_home_on_mk": r5((y[mk] == 0).mean()) if mk.sum() else None}
    # per-league goal-level home shift (train), shrunk to 0 with k = 300 pseudo-matches
    def shifted(mu, dlt):
        mu2 = mu.copy()
        mu2[:, 0] *= np.exp(dlt)
        mu2[:, 1] *= np.exp(-dlt)
        return p1x2(mats(mu2, rho, nb))
    Ph = P.copy()
    dl = {}
    for c in sorted(set(comp_name)):
        sel = tr & (comp_name == c)
        if sel.sum() < 100:
            dl[c] = 0.0
            continue
        grid = np.arange(-0.15, 0.1501, 0.01)
        obj = [ll_rows(shifted(D["mu"][sel], g), y[sel]).sum() + 300 * g ** 2 for g in grid]
        dl[c] = float(grid[int(np.argmin(obj))])
        mm = comp_name == c
        Ph[mm] = shifted(D["mu"][mm], dl[c])
    H["fix"]["home_shift_by_comp_train"] = {k: r5(v) for k, v in dl.items()}
    for nm, m in (("validation", va), ("test", te), ("valtest", vt), ("valtest_league", vt & lg), ("valtest_uefa", vt & euro)):
        d = ll_rows(Ph[m], y[m]) - ll[m]
        H["fix"][nm] = {"n": int(m.sum()), "diff": r5(d.mean()), "ci90": [r5(v) for v in boot_ci(d)]}
    R["home_advantage"] = H

    # ------------------------------------------------------------ D. goal markets
    G = {"ou25_by_comp": {}, "btts_by_comp": {}, "ou25_calib": {}, "btts_calib": {}, "total_by_comp": {}}
    po, pb = D["p_over25"], D["p_btts"]
    o25, bt = D["over25"], D["btts"]
    mo = D["M_ou25"]
    hasou = ~np.isnan(mo)
    for c in sorted(set(comp_name)):
        sel_tr = tr & (comp_name == c)
        base_o = o25[sel_tr].mean() if sel_tr.sum() >= 50 else np.nan
        base_b = bt[sel_tr].mean() if sel_tr.sum() >= 50 else np.nan
        mm = vt & (comp_name == c)
        mk = mm & hasou
        G["ou25_by_comp"][c] = {"n": int(mm.sum()), "pred": r5(po[mm].mean()), "obs": r5(o25[mm].mean()),
                                "ll_model": r5(bin_ll(po[mm], o25[mm]).mean()),
                                "ll_train_rate": r5(bin_ll(np.full(mm.sum(), base_o), o25[mm]).mean()) if not np.isnan(base_o) else None,
                                "n_mk": int(mk.sum()), "mk": r5(mo[mk].mean()) if mk.sum() else None,
                                "ll_model_on_mk": r5(bin_ll(po[mk], o25[mk]).mean()) if mk.sum() else None,
                                "ll_market": r5(bin_ll(mo[mk], o25[mk]).mean()) if mk.sum() else None,
                                "gap": r5((bin_ll(po[mk], o25[mk]) - bin_ll(mo[mk], o25[mk])).mean()) if mk.sum() else None}
        G["btts_by_comp"][c] = {"n": int(mm.sum()), "pred": r5(pb[mm].mean()), "obs": r5(bt[mm].mean()),
                                "ll_model": r5(bin_ll(pb[mm], bt[mm]).mean()),
                                "ll_train_rate": r5(bin_ll(np.full(mm.sum(), base_b), bt[mm]).mean()) if not np.isnan(base_b) else None}
        G["total_by_comp"][c] = {"valtest_pred": r5(tot[mm].mean()), "valtest_obs": r5((hg + ag)[mm].mean()),
                                 "train_pred": r5(tot[sel_tr].mean()), "train_obs": r5((hg + ag)[sel_tr].mean())}
    mk = vt & hasou
    G["ou25_overall_valtest"] = {"n": int(vt.sum()), "ll_model": r5(bin_ll(po[vt], o25[vt]).mean()), "pred": r5(po[vt].mean()),
                                 "obs": r5(o25[vt].mean()), "n_mk": int(mk.sum()),
                                 "ll_model_on_mk": r5(bin_ll(po[mk], o25[mk]).mean()), "ll_market": r5(bin_ll(mo[mk], o25[mk]).mean())}
    G["btts_overall_valtest"] = {"n": int(vt.sum()), "ll_model": r5(bin_ll(pb[vt], bt[vt]).mean()), "pred": r5(pb[vt].mean()),
                                 "obs": r5(bt[vt].mean()), "ll_const_train_rate": r5(bin_ll(np.full(vt.sum(), bt[tr].mean()), bt[vt]).mean())}
    for key, p, yy in (("ou25_calib", po, o25), ("btts_calib", pb, bt)):
        edges = [0, .35, .45, .5, .55, .6, .65, .75, 1.01]
        for lo, hi in zip(edges[:-1], edges[1:]):
            mm = vt & (p >= lo) & (p < hi)
            row = {"n": int(mm.sum()), "pred": r5(p[mm].mean()) if mm.sum() else None, "obs": r5(yy[mm].mean()) if mm.sum() else None}
            if key == "ou25_calib":
                k2 = mm & hasou
                row["mk_on_same_rows"] = r5(mo[k2].mean()) if k2.sum() else None
                row["obs_on_mk_rows"] = r5(yy[k2].mean()) if k2.sum() else None
            G[key][f"{lo:.2f}-{hi:.2f}"] = row
    R["goal_markets"] = G

    # ------------------------------------------------------------ E. disagreement deciles (val+test, odds rows)
    E = {"directional": [], "magnitude_kl": [], "top_pick": {}}
    sel = vt & has
    Pm, Mm, ym = P[sel], M[sel], y[sel]
    llp, llq = ll[sel], llm[sel]
    sd = (Pm[:, 0] - Pm[:, 2]) - (Mm[:, 0] - Mm[:, 2])
    qs = np.quantile(sd, np.linspace(0, 1, 11))
    for k in range(10):
        mm = (sd >= qs[k]) & (sd <= qs[k + 1] if k == 9 else sd < qs[k + 1])
        E["directional"].append({"decile": k + 1, "n": int(mm.sum()), "delta_range": [r5(qs[k]), r5(qs[k + 1])],
                                 "model_h_minus_a": r5((Pm[mm, 0] - Pm[mm, 2]).mean()),
                                 "market_h_minus_a": r5((Mm[mm, 0] - Mm[mm, 2]).mean()),
                                 "obs_h_minus_a": r5(((ym[mm] == 0).astype(float) - (ym[mm] == 2)).mean()),
                                 "model_draw": r5(Pm[mm, 1].mean()), "market_draw": r5(Mm[mm, 1].mean()),
                                 "obs_draw": r5((ym[mm] == 1).mean()),
                                 "ll_model": r5(llp[mm].mean()), "ll_market": r5(llq[mm].mean()),
                                 "gap": r5((llp[mm] - llq[mm]).mean()), "gap_ci90": [r5(v) for v in boot_ci(llp[mm] - llq[mm])]})
    kl = (Mm * (np.log(np.clip(Mm, EPS, 1)) - np.log(np.clip(Pm, EPS, 1)))).sum(1)
    qk = np.quantile(kl, np.linspace(0, 1, 11))
    for k in range(10):
        mm = (kl >= qk[k]) & (kl <= qk[k + 1] if k == 9 else kl < qk[k + 1])
        E["magnitude_kl"].append({"decile": k + 1, "n": int(mm.sum()), "kl_range": [r5(qk[k]), r5(qk[k + 1])],
                                  "ll_model": r5(llp[mm].mean()), "ll_market": r5(llq[mm].mean()),
                                  "gap": r5((llp[mm] - llq[mm]).mean()), "gap_ci90": [r5(v) for v in boot_ci(llp[mm] - llq[mm])],
                                  "acc_model": r5((Pm[mm].argmax(1) == ym[mm]).mean()),
                                  "acc_market": r5((Mm[mm].argmax(1) == ym[mm]).mean())})
    dis = Pm.argmax(1) != Mm.argmax(1)
    E["top_pick"] = {"n": int(sel.sum()), "n_disagree": int(dis.sum()), "share_disagree": r5(dis.mean()),
                     "model_pick_won": int((Pm[dis].argmax(1) == ym[dis]).sum()),
                     "market_pick_won": int((Mm[dis].argmax(1) == ym[dis]).sum()),
                     "neither_won": int(((Pm[dis].argmax(1) != ym[dis]) & (Mm[dis].argmax(1) != ym[dis])).sum()),
                     "acc_when_agree": r5((Pm[~dis].argmax(1) == ym[~dis]).mean())}
    # same on train for stability
    selt = tr & has
    Pt, Mt, yt = P[selt], M[selt], y[selt]
    dist = Pt.argmax(1) != Mt.argmax(1)
    E["top_pick_train"] = {"n": int(selt.sum()), "n_disagree": int(dist.sum()),
                           "model_pick_won": int((Pt[dist].argmax(1) == yt[dist]).sum()),
                           "market_pick_won": int((Mt[dist].argmax(1) == yt[dist]).sum())}
    sdt = (Pt[:, 0] - Pt[:, 2]) - (Mt[:, 0] - Mt[:, 2])
    qt = np.quantile(sdt, [0, .1, .9, 1])
    lo_ = sdt < qt[1]
    hi_ = sdt >= qt[2]
    E["directional_train_extremes"] = {
        "decile1": {"n": int(lo_.sum()), "model": r5((Pt[lo_, 0] - Pt[lo_, 2]).mean()), "market": r5((Mt[lo_, 0] - Mt[lo_, 2]).mean()),
                    "obs": r5(((yt[lo_] == 0).astype(float) - (yt[lo_] == 2)).mean())},
        "decile10": {"n": int(hi_.sum()), "model": r5((Pt[hi_, 0] - Pt[hi_, 2]).mean()), "market": r5((Mt[hi_, 0] - Mt[hi_, 2]).mean()),
                     "obs": r5(((yt[hi_] == 0).astype(float) - (yt[hi_] == 2)).mean())}}
    # slope: regress outcome (H-A) on model and market (OLS) for val+test: who carries the information
    Xo = np.column_stack([np.ones(sel.sum()), Pm[:, 0] - Pm[:, 2], Mm[:, 0] - Mm[:, 2]])
    yo = (ym == 0).astype(float) - (ym == 2)
    beta, *_ = np.linalg.lstsq(Xo, yo, rcond=None)
    E["ols_h_minus_a_on_model_and_market_valtest"] = [r5(b) for b in beta]
    R["disagreement"] = E

    # ------------------------------------------------------------ F. direction of error in weak pockets
    L = build_labels(D)
    F = {}

    def side_view(mask, side):
        """side 0 = home perspective, 2 = away perspective: mean model p(win), market p(win), obs."""
        mk = mask & has
        return {"n": int(mask.sum()), "model_win": r5(P[mask, side].mean()), "obs_win": r5((y[mask] == side).mean()),
                "model_draw": r5(P[mask, 1].mean()), "obs_draw": r5((y[mask] == 1).mean()),
                "n_mk": int(mk.sum()), "model_win_on_mk": r5(P[mk, side].mean()) if mk.sum() else None,
                "market_win": r5(M[mk, side].mean()) if mk.sum() else None,
                "obs_win_on_mk": r5((y[mk] == side).mean()) if mk.sum() else None,
                "gap": r5((ll[mk] - llm[mk]).mean()) if mk.sum() >= 20 else None}

    # promoted / new team perspective (one_new rows)
    import sqlite3  # noqa: F401
    newp = {}
    for nm, m in (("valtest", vt), ("train", tr)):
        one = m & (L["new_team"] == "one_new")
        # which side is new? recompute via labels of single-side: use team-in-previous-season test through phase helper
        newp[nm] = one
    # identify the new side: rebuild quickly from all_results
    from err_common import load_results_db
    from err_pockets import season_key
    res = load_results_db()
    import sqlite3 as sq
    from err_common import HIST_DB
    con = sq.connect(f"file:{HIST_DB.as_posix()}?mode=ro", uri=True)
    cal = {str(c) for c, s in con.execute("select distinct competition_provider_id, season from results where season is not null")
           if s and "/" not in s}
    con.close()
    seen = defaultdict(set)
    for t, c, _se, h, a, _hs, _as in res:
        sk = season_key(t, c in cal)
        seen[(c, sk)].add(h)
        seen[(c, sk)].add(a)
    new_side = np.full(D["n"], -1)
    for i in range(D["n"]):
        if L["new_team"][i] != "one_new":
            continue
        c = D["comp"][i]
        sk = season_key(D["kickoff"][i], c in cal)
        prev = seen.get((c, sk - 1), set())
        new_side[i] = 0 if D["home"][i] not in prev else 2
    early = np.array([p in ("md01-06", "md07-12") for p in L["phase"]])
    for nm, m in (("valtest", vt), ("train", tr)):
        for side, sname in ((0, "new_team_at_home"), (2, "new_team_away")):
            for ph, pm in (("md<=12", early), ("md>12", ~early)):
                F[f"promoted|{nm}|{sname}|{ph}"] = side_view(m & (new_side == side) & pm, side)
    for nm, m in (("valtest", vt), ("train", tr)):
        F[f"away_fav|{nm}"] = side_view(m & (L["fav_side"] == "away_fav"), 2)
        F[f"home_fav|{nm}"] = side_view(m & (L["fav_side"] == "home_fav"), 0)
        F[f"same_city|{nm}|home_view"] = side_view(m & (L["same_city"] == "same_city"), 0)
        F[f"distance<30|{nm}|home_view"] = side_view(m & (L["distance"] == "<30km"), 0)
        F[f"home_rest<=-3|{nm}|home_view"] = side_view(m & (L["rest_diff"] == "home<=-3"), 0)
        F[f"home_rest>=+3|{nm}|home_view"] = side_view(m & (L["rest_diff"] == "home>=+3"), 0)
        F[f"away_played_euro|{nm}|away_view"] = side_view(m & (L["euro_mid"] == "away_played_euro"), 2)
        F[f"home_played_euro|{nm}|home_view"] = side_view(m & (L["euro_mid"] == "home_played_euro"), 0)
        F[f"last4|{nm}|home_view"] = side_view(m & (L["late"] == "last4"), 0)
        for b in (".70-.80", ">=.80", ".50-.60"):
            mm = m & (L["fav_band"] == b)
            fav = P[mm].argmax(1)
            mk = mm & has
            favk = P[mk].argmax(1)
            F[f"fav_band{b}|{nm}"] = {"n": int(mm.sum()), "model_p_fav": r5(P[mm].max(1).mean()),
                                      "obs_fav_win": r5((y[mm] == fav).mean()), "n_mk": int(mk.sum()),
                                      "model_p_fav_on_mk": r5(P[mk].max(1).mean()) if mk.sum() else None,
                                      "market_p_same_outcome": r5(M[mk][np.arange(mk.sum()), favk].mean()) if mk.sum() else None,
                                      "obs_on_mk": r5((y[mk] == favk).mean()) if mk.sum() else None}
    R["pocket_direction"] = F

    # ------------------------------------------------------------ G. UEFA recalibration stability (train fit -> val, test)
    from err_pockets import recal_apply, recal_fit
    th = recal_fit(P[tr & euro], y[tr & euro])
    Gu = {"theta_train": [r5(t) for t in th]}
    for nm, m in (("validation", va & euro), ("test", te & euro)):
        d = ll_rows(recal_apply(P[m], th), y[m]) - ll[m]
        Gu[nm] = {"n": int(m.sum()), "diff": r5(d.mean()), "ci90": [r5(v) for v in boot_ci(d)],
                  "pred": [r5(v) for v in P[m].mean(0)], "obs": [r5((y[m] == k).mean()) for k in range(3)]}
    Gu["train_pred_obs"] = {"pred": [r5(v) for v in P[tr & euro].mean(0)], "obs": [r5((y[tr & euro] == k).mean()) for k in range(3)]}
    for c in ("Champions League", "Europa League", "Conference League"):
        for nm, m in (("train", tr), ("validation", va), ("test", te)):
            mm = m & (comp_name == c)
            Gu[f"{c}|{nm}"] = {"n": int(mm.sum()), "ll": r5(ll[mm].mean()), "acc": r5(acc[mm].mean()),
                               "pred": [r5(v) for v in P[mm].mean(0)], "obs": [r5((y[mm] == k).mean()) for k in range(3)]}
    R["uefa"] = Gu

    OUT.write_text(json.dumps(R, indent=1), encoding="utf-8")
    print(json.dumps(R, indent=None)[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
