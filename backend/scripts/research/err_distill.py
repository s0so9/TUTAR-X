"""Research (2026-10-15): can the model's gap to the closing market be explained by pre-match information we already
have? (and three targeted pocket fixes)

1. Profile of the largest model-market disagreements (top KL decile) vs the rest (val+test).
2. Market distillation: ridge regression of the market-minus-model logit differences (supremacy u = ln pH/pA and
   draw v = ln pD - (ln pH + ln pA)/2) on pre-match features, fitted on TRAIN league rows with closing odds only
   (ridge strength chosen on an inner time split of train), then applied to every league row of validation and test
   (also rows without odds: Czech / Norway / Swiss) and scored against results. Compared with the same regression
   fitted to RESULTS (multinomial, same features) instead of the market.
3. Promoted-team adjustment: one shift (in u) for 'new team at home' and one for 'new team away', fitted on train.
4. League total-goal offsets for the goal markets: per-league ln-total multiplier (shrunk), fitted on train rows,
   scored on validation / test for O/U 2.5, BTTS and 1X2.

Run (from backend/):  OMP_NUM_THREADS=2 venv/Scripts/python.exe -I scripts/research/err_distill.py
Output: data/research/err_distill.json
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
from err_common import (EPS, LEAGUE_NAMES, RES, TRAIN, bin_ll, boot_ci, fnum, ll_rows, load_base, r5,  # noqa: E402
                        rps_rows)
from err_pockets import build_labels  # noqa: E402

OUT = RES / "err_distill.json"


def to_uv(P):
    lp = np.log(np.clip(P, EPS, 1))
    return lp[:, 0] - lp[:, 2], lp[:, 1] - 0.5 * (lp[:, 0] + lp[:, 2])


def from_uv(u, v):
    z = np.stack([u / 2, v, -u / 2], 1)
    z -= z.max(1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


def ridge(X, y, lam):
    p = X.shape[1]
    A = X.T @ X + lam * np.eye(p)
    A[0, 0] -= lam  # no penalty on the intercept
    return np.linalg.solve(A, X.T @ y)


def main() -> int:
    D = load_base()
    L = build_labels(D)
    P, y = D["P"], D["y"]
    n = D["n"]
    split = D["split"]
    tr, va, te = split == "train", split == "validation", split == "test"
    vt = va | te
    euro = D["is_euro"]
    lg = ~euro
    has = D["has_mk"]
    M = np.where(np.isnan(D["M"]), 1 / 3, D["M"])
    ll = ll_rows(P, y)
    llm = ll_rows(M, y)
    comp_name = np.array([LEAGUE_NAMES.get(c, c) for c in D["comp"]])
    R = {}

    # ------------------------------------------------------------------ features
    def col(name):
        return np.array([fnum(f.get(name)) if f else None for f in D["feat"]], dtype=object)

    def num(a):
        return np.array([np.nan if v is None else float(v) for v in a])

    feats = {}
    miss = {}

    def add(name, arr):
        arr = np.asarray(arr, float)
        m = np.isnan(arr)
        feats[name] = np.where(m, 0.0, arr)
        if m.any():
            miss[name + "_missing"] = m.astype(float)

    add("value_log_ratio", num(col("value_log_ratio")))
    add("lineup_form", num(col("lineup_form")))
    add("ppg_l5_diff", num(col("home_ppg_l5")) - num(col("away_ppg_l5")))
    add("gd_l5_diff", (num(col("home_gf_l5")) - num(col("home_ga_l5"))) - (num(col("away_gf_l5")) - num(col("away_ga_l5"))))
    add("xgd_l5_diff", (num(col("home_xg_for_l5")) - num(col("home_xg_against_l5")))
        - (num(col("away_xg_for_l5")) - num(col("away_xg_against_l5"))))
    rh, ra = num(col("home_rest_days")), num(col("away_rest_days"))
    add("rest_diff_cap10", np.minimum(rh, 10) - np.minimum(ra, 10))
    add("home_short_rest", (rh <= 3.5).astype(float))
    add("away_short_rest", (ra <= 3.5).astype(float))
    for k in ("home_euro_before_3d", "away_euro_before_3d", "home_euro_after_3d", "away_euro_after_3d"):
        add(k, num(col(k)))
    add("xi_off_diff", num(col("home_xi_d_off")) - num(col("away_xi_d_off")))
    add("xi_def_diff", num(col("home_xi_d_def")) - num(col("away_xi_d_def")))
    add("unavail_diff", (num(col("home_n_injury")) + num(col("home_n_suspension")))
        - (num(col("away_n_injury")) + num(col("away_n_suspension"))))
    add("league_hadv_dev", num(col("league_hadv_dev")))
    # side of the new team (computed as in err_details)
    from err_common import HIST_DB, load_results_db
    from err_pockets import season_key
    import sqlite3
    con = sqlite3.connect(f"file:{HIST_DB.as_posix()}?mode=ro", uri=True)
    cal = {str(c) for c, s in con.execute("select distinct competition_provider_id, season from results where season is not null")
           if s and "/" not in s}
    con.close()
    seen = defaultdict(set)
    for t, c, _se, h, a, _hs, _as in load_results_db():
        sk = season_key(t, c in cal)
        seen[(c, sk)].add(h)
        seen[(c, sk)].add(a)
    hn = np.zeros(n)
    an = np.zeros(n)
    for i in range(n):
        if L["new_team"][i] in ("one_new", "both_new"):
            c = D["comp"][i]
            prev = seen.get((c, season_key(D["kickoff"][i], c in cal) - 1), set())
            hn[i] = float(D["home"][i] not in prev)
            an[i] = float(D["away"][i] not in prev)
    add("home_new_team", hn)
    add("away_new_team", an)
    add("early_md1_6", (L["phase"] == "md01-06").astype(float))
    add("last4", (L["late"] == "last4").astype(float))
    add("derby_lt30km", (L["distance"] == "<30km").astype(float))
    u0, v0 = to_uv(P)
    add("model_u", u0)
    add("model_abs_u", np.abs(u0))
    add("model_ln_total", np.log(D["mu"].sum(1)))
    names = list(feats) + list(miss)
    X = np.column_stack([feats[k] for k in feats] + [miss[k] for k in miss])
    # standardise on train league rows
    mu_x = X[tr & lg].mean(0)
    sd_x = X[tr & lg].std(0)
    sd_x[sd_x == 0] = 1
    Xs = (X - mu_x) / sd_x
    comps = sorted(set(comp_name[lg]))
    C = np.column_stack([(comp_name == c).astype(float) for c in comps])
    Xf = np.column_stack([np.ones(n), Xs, C])
    fnames = ["intercept"] + names + [f"comp:{c}" for c in comps]

    # ------------------------------------------------------------------ 1. profile of top-KL decile
    sel = vt & has
    kl = np.full(n, np.nan)
    kl[has] = (M[has] * (np.log(np.clip(M[has], EPS, 1)) - np.log(np.clip(P[has], EPS, 1)))).sum(1)
    thr = np.nanquantile(kl[sel], 0.9)
    top = sel & (kl >= thr)
    rest = sel & (kl < thr)
    prof = {"n_top": int(top.sum()), "kl_threshold": r5(thr),
            "gap_top": r5((ll[top] - llm[top]).mean()), "gap_rest": r5((ll[rest] - llm[rest]).mean()),
            "share_of_total_gap_from_top": r5((ll[top] - llm[top]).sum() / (ll[sel] - llm[sel]).sum())}
    for k in ("new_team", "phase", "late", "euro_mid", "rest_diff", "distance", "lineup_info", "fav_band", "comp"):
        vals = sorted(set(L[k][sel]))
        prof[k] = {v: [r5((L[k][top] == v).mean()), r5((L[k][rest] == v).mean())] for v in vals}
    mu_m = (M[:, 0] - M[:, 2])
    mo_m = (P[:, 0] - P[:, 2])
    prof["mean_abs_h_minus_a_diff_top"] = r5(np.abs(mu_m[top] - mo_m[top]).mean())
    prof["draw_diff_top_model_minus_market"] = r5((P[top, 1] - M[top, 1]).mean())
    prof["draw_diff_rest_model_minus_market"] = r5((P[rest, 1] - M[rest, 1]).mean())
    # direction: does the model favour the team with the larger market value / better recent form than the market?
    sd_dir = mo_m - mu_m
    for fname in ("value_log_ratio", "lineup_form", "ppg_l5_diff", "xgd_l5_diff", "gd_l5_diff", "rest_diff_cap10", "model_u"):
        f = feats[fname]
        m_ok = sel & ~(miss.get(fname + "_missing", np.zeros(n)) > 0)
        prof[f"corr(model-market H-A, {fname})"] = r5(np.corrcoef(sd_dir[m_ok], f[m_ok])[0, 1])
    R["top_kl_profile"] = prof

    # ------------------------------------------------------------------ 2. market distillation
    um, vm = to_uv(M)
    tu, tv = um - u0, vm - v0
    fit_rows = tr & lg & has
    # inner time split for the ridge strength
    kick = np.array([t.toordinal() for t in D["kickoff"]])
    from datetime import datetime
    inner_cut = datetime(2024, 7, 1).toordinal()
    in_tr = fit_rows & (kick < inner_cut)
    in_va = fit_rows & (kick >= inner_cut)
    lam_res = {}
    best = None
    for lam in (1, 10, 100, 1000, 3000, 10000, 30000):
        bu = ridge(Xf[in_tr], tu[in_tr], lam)
        bv = ridge(Xf[in_tr], tv[in_tr], lam)
        Pq = from_uv(u0[in_va] + Xf[in_va] @ bu, v0[in_va] + Xf[in_va] @ bv)
        l_ = ll_rows(Pq, y[in_va]).mean()
        mse = ((Xf[in_va] @ bu - tu[in_va]) ** 2).mean()
        lam_res[str(lam)] = {"inner_val_ll_vs_results": r5(l_), "inner_val_mse_u": r5(mse)}
        if best is None or mse < best[1]:
            best = (lam, mse)
    lam = best[0]
    bu = ridge(Xf[fit_rows], tu[fit_rows], lam)
    bv = ridge(Xf[fit_rows], tv[fit_rows], lam)
    uh, vh = u0 + Xf @ bu, v0 + Xf @ bv
    Pd = P.copy()
    Pd[lg] = from_uv(uh[lg], vh[lg])
    dist = {"ridge_lambda": lam, "inner_split": lam_res, "n_fit": int(fit_rows.sum()),
            "inner_r2_u": None}
    # coefficients (per sd)
    dist["coef_u_top"] = sorted([[fnames[j], r5(bu[j])] for j in range(len(fnames))], key=lambda x: -abs(x[1]))[:15]
    dist["coef_v_top"] = sorted([[fnames[j], r5(bv[j])] for j in range(len(fnames))], key=lambda x: -abs(x[1]))[:15]
    r2u = 1 - ((tu[fit_rows] - Xf[fit_rows] @ bu) ** 2).mean() / tu[fit_rows].var()
    r2v = 1 - ((tv[fit_rows] - Xf[fit_rows] @ bv) ** 2).mean() / tv[fit_rows].var()
    dist["train_r2_u"], dist["train_r2_v"] = r5(r2u), r5(r2v)
    for nm, m in (("validation_league", va & lg), ("test_league", te & lg), ("valtest_league", vt & lg),
                  ("valtest_league_with_odds", vt & lg & has), ("valtest_league_no_odds", vt & lg & ~has)):
        d = ll_rows(Pd[m], y[m]) - ll[m]
        row = {"n": int(m.sum()), "ll_base": r5(ll[m].mean()), "ll_new": r5(ll_rows(Pd[m], y[m]).mean()),
               "diff": r5(d.mean()), "ci90": [r5(x) for x in boot_ci(d)],
               "rps_diff": r5((rps_rows(Pd[m], y[m]) - rps_rows(P[m], y[m])).mean()),
               "acc_base": r5((P[m].argmax(1) == y[m]).mean()), "acc_new": r5((Pd[m].argmax(1) == y[m]).mean())}
        mk = m & has
        if mk.sum():
            row["gap_base"] = r5((ll[mk] - llm[mk]).mean())
            row["gap_new"] = r5((ll_rows(Pd[mk], y[mk]) - llm[mk]).mean())
            row["share_of_gap_closed"] = r5(1 - row["gap_new"] / row["gap_base"])
        dist[nm] = row
    m = vt & lg & has
    for t in (0.6, 0.7, 0.75, 0.8):
        a = m & (Pd.max(1) >= t)
        b = m & (P.max(1) >= t)
        dist[f"fav>={t}_valtest_odds_rows"] = {"new_n": int(a.sum()), "new_hit": r5((Pd[a].argmax(1) == y[a]).mean()),
                                               "new_mean_p": r5(Pd[a].max(1).mean()),
                                               "base_n": int(b.sum()), "base_hit": r5((P[b].argmax(1) == y[b]).mean())}
    R["distillation"] = dist

    # same features fitted to RESULTS (multinomial on u/v shifts), train league rows (all, not only odds rows)
    rows_r = tr & lg

    def nll(beta):
        k = Xf.shape[1]
        a, b = beta[:k], beta[k:]
        Q = from_uv(u0[rows_r] + Xf[rows_r] @ a, v0[rows_r] + Xf[rows_r] @ b)
        reg = 0.5 * lam_r * ((a[1:] ** 2).sum() + (b[1:] ** 2).sum())
        return -np.log(np.clip(Q[np.arange(rows_r.sum()), y[rows_r]], EPS, 1)).sum() + reg

    res_out = {}
    for lam_r in (30.0, 300.0, 3000.0):
        r = minimize(nll, np.zeros(2 * Xf.shape[1]), method="L-BFGS-B", options={"maxiter": 500})
        k = Xf.shape[1]
        Pr = P.copy()
        Pr[lg] = from_uv(u0[lg] + Xf[lg] @ r.x[:k], v0[lg] + Xf[lg] @ r.x[k:])
        row = {}
        for nm, mm in (("validation_league", va & lg), ("test_league", te & lg), ("valtest_league", vt & lg)):
            d = ll_rows(Pr[mm], y[mm]) - ll[mm]
            row[nm] = {"diff": r5(d.mean()), "ci90": [r5(x) for x in boot_ci(d)]}
        res_out[str(lam_r)] = row
    R["results_fit_same_features"] = res_out

    # ------------------------------------------------------------------ 3. promoted-team shift (train)
    def shift_u(Pm, du, dv=0.0):
        uu, vv = to_uv(Pm)
        return from_uv(uu + du, vv + dv)

    prom = {}
    for side, fl in (("home_new", hn), ("away_new", an)):
        msel = tr & lg & (fl > 0) & ~((hn > 0) & (an > 0))
        r = minimize_scalar(lambda d: ll_rows(shift_u(P[msel], d), y[msel]).mean(), bounds=(-1, 1), method="bounded")
        prom[side + "_du_train"] = r5(float(r.x))
        prom[side + "_n_train"] = int(msel.sum())
    Pp = P.copy()
    for side, fl in (("home_new", hn), ("away_new", an)):
        mm = lg & (fl > 0) & ~((hn > 0) & (an > 0))
        Pp[mm] = shift_u(P[mm], prom[side + "_du_train"])
    for nm, mm in (("validation", va & lg), ("test", te & lg), ("valtest", vt & lg)):
        pocket = mm & ((hn > 0) ^ (an > 0))
        d = ll_rows(Pp[pocket], y[pocket]) - ll[pocket]
        prom[nm + "_pocket"] = {"n": int(pocket.sum()), "diff": r5(d.mean()), "ci90": [r5(x) for x in boot_ci(d)],
                                "overall_contrib": r5(d.sum() / mm.sum())}
    R["promoted_shift"] = prom

    # ------------------------------------------------------------------ 4. league total-goal offsets (goal markets)
    lp = json.loads((TRAIN / "goal_layer_train_only.json").read_text(encoding="utf-8"))["params"]
    rho, nbd = float(lp["rho"]), float(lp["nb_dispersion"])
    mu = D["mu"]
    hg, ag = np.minimum(D["hg"], 10), np.minimum(D["ag"], 10)

    G = T.G
    tot_grid = G[:, None] + G[None, :]

    def markets(mu_, idx_h, idx_a):
        out_o, out_b, out_p, out_s = [], [], [], []
        for i in range(0, len(mu_), 4000):
            m = T.score_matrix(mu_[i:i + 4000, 0], mu_[i:i + 4000, 1], rho, nbd)
            out_o.append((m * (tot_grid > 2.5)).sum(axis=(1, 2)))
            out_b.append(m[:, 1:, 1:].sum(axis=(1, 2)))
            out_p.append(np.stack([np.tril(m, -1).sum(axis=(1, 2)), np.trace(m, axis1=1, axis2=2),
                                   np.triu(m, 1).sum(axis=(1, 2))], 1))
            out_s.append(m[np.arange(len(m)), idx_h[i:i + 4000], idx_a[i:i + 4000]])
        return np.concatenate(out_o), np.concatenate(out_b), np.concatenate(out_p), np.concatenate(out_s)

    o_base, b_base, p_base, s_base = markets(mu, hg, ag)
    offs = {}
    k_shr = 200.0
    for c in sorted(set(comp_name)):
        sel_c = tr & (comp_name == c)
        if sel_c.sum() < 100:
            offs[c] = 0.0
            continue
        # Poisson-style closed form for ln multiplier on both means: sum goals / sum predicted, shrunk
        g_obs = (D["hg"][sel_c] + D["ag"][sel_c]).sum()
        g_pred = mu[sel_c].sum()
        n_c = sel_c.sum()
        raw = np.log(g_obs / g_pred)
        offs[c] = float(raw * n_c / (n_c + k_shr))
    mult = np.array([np.exp(offs[c]) for c in comp_name])
    mu2 = mu * mult[:, None]
    o_new, b_new, p_new, s_new = markets(mu2, hg, ag)
    o25, bt = D["over25"], D["btts"]
    tg = {"offsets_train": {k: r5(v) for k, v in offs.items()}, "shrink_pseudo_matches": k_shr}
    mo = D["M_ou25"]
    for nm, mm in (("validation", va), ("test", te), ("valtest", vt), ("valtest_league", vt & lg), ("valtest_uefa", vt & euro)):
        do = bin_ll(o_new[mm], o25[mm]) - bin_ll(o_base[mm], o25[mm])
        db = bin_ll(b_new[mm], bt[mm]) - bin_ll(b_base[mm], bt[mm])
        d1 = ll_rows(p_new[mm], D["y"][mm]) - ll_rows(p_base[mm], D["y"][mm])
        ds = -np.log(np.clip(s_new[mm], EPS, 1)) + np.log(np.clip(s_base[mm], EPS, 1))
        row = {"n": int(mm.sum()),
               "ou25_ll_base": r5(bin_ll(o_base[mm], o25[mm]).mean()), "ou25_diff": r5(do.mean()), "ou25_ci90": [r5(x) for x in boot_ci(do)],
               "btts_diff": r5(db.mean()), "btts_ci90": [r5(x) for x in boot_ci(db)],
               "1x2_diff": r5(d1.mean()), "1x2_ci90": [r5(x) for x in boot_ci(d1)],
               "score_diff": r5(ds.mean()), "score_ci90": [r5(x) for x in boot_ci(ds)]}
        mko = mm & ~np.isnan(mo)
        if mko.sum():
            row["ou25_on_odds_rows"] = {"n": int(mko.sum()), "market": r5(bin_ll(mo[mko], o25[mko]).mean()),
                                        "base": r5(bin_ll(o_base[mko], o25[mko]).mean()),
                                        "new": r5(bin_ll(o_new[mko], o25[mko]).mean())}
        tg[nm] = row
    R["league_total_offsets"] = tg

    OUT.write_text(json.dumps(R, indent=1), encoding="utf-8")
    print(json.dumps(R["top_kl_profile"]))
    print(json.dumps({k: v for k, v in R["distillation"].items() if k not in ("inner_split",)}))
    print(json.dumps(R["distillation"]["inner_split"]))
    print(json.dumps(R["results_fit_same_features"]))
    print(json.dumps(R["promoted_shift"]))
    print(json.dumps(R["league_total_offsets"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
