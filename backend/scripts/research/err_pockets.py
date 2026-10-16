"""Research (2026-10-15): where does the production model lose accuracy? Pocket analysis.

For every pocket (competition, league vs UEFA, season phase, promoted teams, thin rating history, Euro midweek,
rest difference, derby distance, favourite band, ...) on validation+test (primary) and train (stability):
  1X2 log loss / RPS / Brier / top-pick accuracy, and on matches with closing odds the paired gap to the closing
  market (model - market, bootstrap 90 % CI), the gap to the pre-closing market, and two recoverable-error numbers:
  * UB  = (model LL - market LL) in the pocket x pocket share of odds rows  (replace model by market: upper bound)
  * EXC = excess of the pocket's gap over the average gap x share (what is special about this pocket)
  * RECAL = log-loss gain on validation+test of a 3-parameter pocket recalibration fitted on TRAIN rows of the
    pocket (P' ~ P^a * exp(b_H, 0, b_A)), minus the gain of the same recalibration fitted on all train rows
    (pocket-specific realistic gain; available without odds, so it also covers UEFA / Czech / Norway / Swiss).

Run (from backend/):  OMP_NUM_THREADS=2 venv/Scripts/python.exe -I scripts/research/err_pockets.py
Output: data/research/err_pockets.json (+ stdout summary)
"""
from __future__ import annotations

import json
import math
import sys
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parent))
from err_common import (EPS, LEAGUE_NAMES, RES, acc_rows, bin_ll, boot_ci, brier_rows, fnum, haversine,  # noqa: E402
                        ll_rows, load_base, load_results_db, r5, rps_rows)

OUT = RES / "err_pockets.json"


# ------------------------------------------------------------------ recalibration
def recal_apply(P, th):
    a, bh, ba = th
    z = a * np.log(np.clip(P, EPS, 1)) + np.array([bh, 0.0, ba])
    z -= z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def recal_fit(P, y):
    def f(th):
        Q = recal_apply(P, th)
        return -np.log(np.clip(Q[np.arange(len(y)), y], EPS, 1)).mean()
    r = minimize(f, np.array([1.0, 0.0, 0.0]), method="L-BFGS-B",
                 bounds=[(0.5, 2.0), (-1.0, 1.0), (-1.0, 1.0)])
    return r.x


# ------------------------------------------------------------------ derived pocket labels
def season_key(t: datetime, calendar: bool) -> int:
    if calendar:
        return t.year
    return t.year if t.month >= 7 else t.year - 1


def build_labels(D):
    n = D["n"]
    res = load_results_db()
    # calendar-year competitions: all_results season strings without '/'
    import sqlite3
    from err_common import HIST_DB
    con = sqlite3.connect(f"file:{HIST_DB.as_posix()}?mode=ro", uri=True)
    cal = set()
    for c, s in con.execute("select distinct competition_provider_id, season from results where season is not null"):
        if s and "/" not in s:
            cal.add(str(c))
    con.close()
    team_comp_season = defaultdict(list)       # (comp, season, team) -> kickoffs
    comp_season_n = Counter()
    team_times = defaultdict(list)             # team -> kickoffs (all comps)
    for t, c, _se, h, a, _hs, _as in res:
        sk = season_key(t, c in cal)
        team_comp_season[(c, sk, h)].append(t)
        team_comp_season[(c, sk, a)].append(t)
        comp_season_n[(c, sk)] += 1
        team_times[h].append(t)
        team_times[a].append(t)
    for v in team_comp_season.values():
        v.sort()
    for v in team_times.values():
        v.sort()
    last_result = max(r[0] for r in res)

    L = defaultdict(list)
    # team home location (modal stadium coordinate of league home matches) for derby distance
    loc = defaultdict(Counter)
    city = defaultdict(Counter)
    for i in range(n):
        inf = D["info"][i]
        if D["is_euro"][i] or not inf:
            continue
        la, lo = fnum(inf.get("lat")), fnum(inf.get("lon"))
        if la is not None and lo is not None:
            loc[D["home"][i]][(round(la, 3), round(lo, 3))] += 1
        if inf.get("city"):
            city[D["home"][i]][inf["city"].strip().lower()] += 1
    home_loc = {t: c.most_common(1)[0][0] for t, c in loc.items()}
    home_city = {t: c.most_common(1)[0][0] for t, c in city.items()}

    for i in range(n):
        t = D["kickoff"][i]
        c = D["comp"][i]
        h, a = D["home"][i], D["away"][i]
        f = D["feat"][i]
        euro = bool(D["is_euro"][i])
        L["comp"].append(LEAGUE_NAMES.get(c, c))
        L["class"].append("UEFA" if euro else "league")
        # season phase (team match index in comp-season, from all_results)
        sk = season_key(t, c in cal)
        tcut = t - timedelta(hours=2)
        lh = team_comp_season.get((c, sk, h), [])
        la_ = team_comp_season.get((c, sk, a), [])
        ih = bisect_left(lh, tcut)
        ia = bisect_left(la_, tcut)
        md = max(ih, ia) + 1
        if euro:
            L["phase"].append("UEFA")
        elif md <= 6:
            L["phase"].append("md01-06")
        elif md <= 12:
            L["phase"].append("md07-12")
        else:
            L["phase"].append("md13+")
        # late season: last 4 matches of a completed comp-season (season over before the latest result date)
        if euro:
            L["late"].append("UEFA")
        else:
            seas_done = lh and la_ and max(lh[-1], la_[-1]) < last_result - timedelta(days=40)
            if not seas_done:
                L["late"].append("unknown(current season)")
            else:
                rem_h = len(lh) - ih - 1
                rem_a = len(la_) - ia - 1
                L["late"].append("last4" if min(rem_h, rem_a) <= 3 else "not_last4")
        # promoted / new to league
        if euro:
            L["new_team"].append("UEFA")
        else:
            prev_n = comp_season_n.get((c, sk - 1), 0)
            if prev_n < 50:
                L["new_team"].append("unknown(no prev season)")
            else:
                nh = len(team_comp_season.get((c, sk - 1, h), [])) == 0
                na = len(team_comp_season.get((c, sk - 1, a), [])) == 0
                if nh and na:
                    lab = "both_new"
                elif nh or na:
                    lab = "one_new"
                else:
                    lab = "none_new"
                L["new_team"].append(lab)
        # thin rating window (results in the 400 days before kick-off, any competition)
        def nwin(team):
            v = team_times.get(team, [])
            return bisect_left(v, tcut) - bisect_left(v, t - timedelta(days=400))
        m = min(nwin(h), nwin(a))
        L["window"].append("<20" if m < 20 else ("20-34" if m < 35 else ("35-49" if m < 50 else "50+")))
        # Euro midweek (league matches)
        if euro:
            L["euro_mid"].append("UEFA")
            L["euro_next"].append("UEFA")
        else:
            eb_h, eb_a = f.get("home_euro_before_3d"), f.get("away_euro_before_3d")
            if eb_h in ("", None) or eb_a in ("", None):
                L["euro_mid"].append("unknown")
            else:
                L["euro_mid"].append({("0", "0"): "none", ("1", "0"): "home_played_euro", ("0", "1"): "away_played_euro",
                                      ("1", "1"): "both_played_euro"}[(eb_h, eb_a)])
            ea_h, ea_a = f.get("home_euro_after_3d"), f.get("away_euro_after_3d")
            if ea_h in ("", None) or ea_a in ("", None):
                L["euro_next"].append("unknown")
            else:
                L["euro_next"].append({("0", "0"): "none", ("1", "0"): "home_euro_next", ("0", "1"): "away_euro_next",
                                       ("1", "1"): "both_euro_next"}[(ea_h, ea_a)])
        # rest difference (cap each side at 10 days)
        rh, ra = fnum(f.get("home_rest_days")), fnum(f.get("away_rest_days"))
        if rh is None or ra is None:
            L["rest_diff"].append("unknown")
            L["short_rest"].append("unknown")
        else:
            dd = min(rh, 10) - min(ra, 10)
            L["rest_diff"].append("home<=-3" if dd <= -3 else ("home-2..-1" if dd < 0 else ("0" if dd == 0 else (
                "home+1..+2" if dd < 3 else "home>=+3"))))
            sh, sa = rh <= 3.5, ra <= 3.5
            L["short_rest"].append("both<=3d" if sh and sa else ("home<=3d" if sh else ("away<=3d" if sa else "neither")))
        # derby distance
        if euro:
            L["distance"].append("UEFA")
            L["same_city"].append("UEFA")
        else:
            p1, p2 = home_loc.get(h), home_loc.get(a)
            if p1 is None or p2 is None:
                L["distance"].append("unknown")
            else:
                km = haversine(p1[0], p1[1], p2[0], p2[1])
                L["distance"].append("<30km" if km < 30 else ("30-150km" if km < 150 else ("150-500km" if km < 500 else ">=500km")))
            c1, c2 = home_city.get(h), home_city.get(a)
            L["same_city"].append("unknown" if not c1 or not c2 else ("same_city" if c1 == c2 else "different"))
        # model favourite band
        pf = D["P"][i].max()
        L["fav_band"].append("<.40" if pf < .40 else (".40-.50" if pf < .5 else (".50-.60" if pf < .6 else (
            ".60-.70" if pf < .7 else (".70-.80" if pf < .8 else ">=.80")))))
        L["fav_side"].append(["home_fav", "draw_fav", "away_fav"][int(D["P"][i].argmax())])
        # line-up information in the production model
        vm = f.get("value_log_ratio", "") == ""
        lm = f.get("lineup_form", "") == ""
        L["lineup_info"].append("both" if not vm and not lm else ("value_missing" if vm and not lm else (
            "form_missing" if lm and not vm else "both_missing")))
        L["month"].append(f"{t.month:02d}")
        L["half_year"].append(f"{t.year}H{1 if t.month <= 6 else 2}")
        L["weekday"].append("midweek(Tue-Thu)" if t.weekday() in (1, 2, 3) else "weekend/other")
    return {k: np.array(v) for k, v in L.items()}


# ------------------------------------------------------------------ summaries
def summarize(D, base, mask, glob_th, recal_ok=True):
    """base: dict of per-row metric arrays. mask over the evaluation rows (val+test)."""
    out = {"n": int(mask.sum())}
    if out["n"] == 0:
        return out
    y = D["y"][mask]
    out["ll"] = r5(base["ll"][mask].mean())
    out["rps"] = r5(base["rps"][mask].mean())
    out["brier"] = r5(base["br"][mask].mean())
    out["acc"] = r5(base["acc"][mask].mean())
    out["pred_draw"] = r5(D["P"][mask, 1].mean())
    out["obs_draw"] = r5((y == 1).mean())
    out["pred_home"] = r5(D["P"][mask, 0].mean())
    out["obs_home"] = r5((y == 0).mean())
    mm = mask & D["has_mk"]
    out["n_mk"] = int(mm.sum())
    if mm.sum() >= 20:
        g = base["ll"][mm] - base["llm"][mm]
        out["ll_model_mk"] = r5(base["ll"][mm].mean())
        out["ll_market"] = r5(base["llm"][mm].mean())
        out["ll_market_pow"] = r5(base["llmp"][mm].mean())
        out["gap"] = r5(g.mean())
        out["gap_ci90"] = [r5(v) for v in boot_ci(g)]
        out["rps_gap"] = r5((base["rps"][mm] - base["rpsm"][mm]).mean())
        out["acc_model_mk"] = r5(base["acc"][mm].mean())
        out["acc_market"] = r5(base["accm"][mm].mean())
        out["mk_draw"] = r5(D["M"][mm, 1].mean())
        out["mk_home"] = r5(D["M"][mm, 0].mean())
        pm = mm & ~np.isnan(D["Mpre"][:, 0])
        if pm.sum() >= 20:
            out["n_pre"] = int(pm.sum())
            out["gap_pre"] = r5((base["ll"][pm] - base["llpre"][pm]).mean())
            out["gap_close_same_rows"] = r5((base["ll"][pm] - base["llm"][pm]).mean())
    return out


def main() -> int:
    D = load_base()
    n = D["n"]
    P, y = D["P"], D["y"]
    M = np.where(np.isnan(D["M"]), 1 / 3, D["M"])
    Mp = np.where(np.isnan(D["Mpow"]), 1 / 3, D["Mpow"])
    Mpre = np.where(np.isnan(D["Mpre"]), 1 / 3, D["Mpre"])
    base = {"ll": ll_rows(P, y), "rps": rps_rows(P, y), "br": brier_rows(P, y), "acc": acc_rows(P, y),
            "llm": ll_rows(M, y), "llmp": ll_rows(Mp, y), "rpsm": rps_rows(M, y), "accm": acc_rows(M, y),
            "llpre": ll_rows(Mpre, y)}
    labels = build_labels(D)
    split = D["split"]
    is_tr = split == "train"
    is_vt = (split == "validation") | (split == "test")

    glob_th = recal_fit(P[is_tr], y[is_tr])
    Pg = recal_apply(P, glob_th)
    llg = ll_rows(Pg, y)

    report = {"built_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
              "rows": n, "rows_with_closing_odds": int(D["has_mk"].sum()),
              "global_recal_train": [r5(v) for v in glob_th],
              "global_recal_gain_valtest": r5(llg[is_vt].mean() - base["ll"][is_vt].mean()),
              "overall": {}, "dims": {}}
    for nm, m in (("valtest", is_vt), ("train", is_tr), ("test", split == "test"), ("validation", split == "validation")):
        report["overall"][nm] = summarize(D, base, m, glob_th)
    N_vt = int(is_vt.sum())
    N_vt_mk = int((is_vt & D["has_mk"]).sum())
    gap_all = report["overall"]["valtest"]["gap"]

    pocket_rank = []
    for dim, lab in labels.items():
        rows = {}
        for v in sorted(set(lab)):
            mv = lab == v
            s_vt = summarize(D, base, is_vt & mv, glob_th)
            s_tr = summarize(D, base, is_tr & mv, glob_th)
            # pocket recalibration fitted on train rows of the pocket
            rec = None
            ntr = int((is_tr & mv).sum())
            if ntr >= 150 and s_vt["n"] >= 50:
                th = recal_fit(P[is_tr & mv], y[is_tr & mv])
                Pq = recal_apply(P[is_vt & mv], th)
                lq = ll_rows(Pq, y[is_vt & mv])
                d_p = lq - base["ll"][is_vt & mv]
                d_g = lq - llg[is_vt & mv]
                rec = {"theta": [r5(t) for t in th], "gain_vs_raw": r5(d_p.mean()), "gain_vs_raw_ci90": [r5(t) for t in boot_ci(d_p)],
                       "gain_vs_global_recal": r5(d_g.mean()), "gain_vs_global_ci90": [r5(t) for t in boot_ci(d_g)]}
            rows[v] = {"valtest": s_vt, "train": s_tr, "pocket_recal": rec}
            share_vt = s_vt["n"] / N_vt
            ub = exc = None
            if s_vt.get("gap") is not None:
                share_mk = s_vt["n_mk"] / N_vt_mk
                ub = s_vt["gap"] * share_mk
                exc = (s_vt["gap"] - gap_all) * share_mk
            pocket_rank.append({"dim": dim, "pocket": v, "n_vt": s_vt["n"], "share_vt": r5(share_vt),
                                "n_mk": s_vt.get("n_mk"), "gap": s_vt.get("gap"), "gap_ci90": s_vt.get("gap_ci90"),
                                "gap_train": s_tr.get("gap"),
                                "ub_contrib": r5(ub), "excess_contrib": r5(exc),
                                "recal_gain_pocket": rec["gain_vs_raw"] if rec else None,
                                "recal_gain_beyond_global": rec["gain_vs_global_recal"] if rec else None,
                                "recal_contrib": r5(rec["gain_vs_global_recal"] * share_vt) if rec else None,
                                "ll": s_vt.get("ll"), "acc": s_vt.get("acc"), "ll_train": s_tr.get("ll")})
        report["dims"][dim] = rows
    report["pocket_rank_by_excess"] = sorted([p for p in pocket_rank if p["excess_contrib"] is not None],
                                             key=lambda p: -p["excess_contrib"])
    report["pocket_rank_by_recal"] = sorted([p for p in pocket_rank if p["recal_contrib"] is not None],
                                            key=lambda p: p["recal_contrib"])
    report["meta"] = {"N_valtest": N_vt, "N_valtest_with_odds": N_vt_mk, "gap_valtest_all": gap_all,
                      "definitions": {
                          "gap": "model 1X2 log loss - closing market log loss (proportional de-vig), paired, val+test rows with odds",
                          "ub_contrib": "gap x share of odds rows: LL points (over all odds rows) recovered if the model were replaced by the market in this pocket",
                          "excess_contrib": "(pocket gap - average gap) x share: how much of the total gap is specific to this pocket",
                          "recal_contrib": "pocket recalibration (fit on train pocket rows) gain beyond the global recalibration, x share of val+test rows (negative = gain)",
                          "phase": "matchday = max(team match index in comp-season)+1 from all_results.db",
                          "new_team": "team had no result in the same competition the previous season (promoted / relegated in)",
                          "window": "min over both teams of results (any competition) in the 400 days before kick-off",
                          "distance": "haversine between both clubs' modal league home-stadium coordinates (FotMob raw infoBox)"}}
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")

    # stdout summary
    print("overall:", json.dumps(report["overall"]["valtest"]))
    print("train  :", json.dumps(report["overall"]["train"]))
    print("global recal", report["global_recal_train"], "gain valtest", report["global_recal_gain_valtest"])
    for dim, rows in report["dims"].items():
        print(f"\n== {dim}")
        for v, r in rows.items():
            s, t = r["valtest"], r["train"]
            rc = r["pocket_recal"]
            print(f"  {v:28s} n={s['n']:5d} ll={s.get('ll')} rps={s.get('rps')} acc={s.get('acc')} "
                  f"draw p/o={s.get('pred_draw')}/{s.get('obs_draw')} | mk n={s.get('n_mk')} gap={s.get('gap')} "
                  f"ci={s.get('gap_ci90')} gap_pre={s.get('gap_pre')} mkdraw={s.get('mk_draw')} | train n={t['n']} "
                  f"ll={t.get('ll')} gap={t.get('gap')} | recal={rc['gain_vs_raw'] if rc else None}/"
                  f"{rc['gain_vs_global_recal'] if rc else None}")
    print("\nTop excess pockets:")
    for p in report["pocket_rank_by_excess"][:15]:
        print("  ", json.dumps(p))
    print("\nTop recal pockets:")
    for p in report["pocket_rank_by_recal"][:15]:
        print("  ", json.dumps(p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
