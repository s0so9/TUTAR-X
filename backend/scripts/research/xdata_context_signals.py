"""Research (2026-10-15, "additional data" study): do cheap context signals add anything on top of the production
model? Groups tested (each alone, then all together), all known before kick-off:

  rest     rest-day difference, short rest (<= 3 days), matches in the last 14 days, European match 3 days
           before / after (columns already in match_features_full.csv.gz)
  travel   log(1 + km) from the away team's usual home venue to the venue; "home team not at its usual venue"
  altitude venue elevation minus the away team's home-venue elevation (km; Open-Meteo elevation API)
  turf     artificial-turf venue while the away team's usual home venue is grass
  coach    head coach changed in the last 5 team matches (home / away; coach ids from the FotMob line-up)
  referee  referee identity (penalised effects on total goals and on home-minus-away goals)
  weather  kick-off hour temperature / precipitation / wind (Open-Meteo ERA5 archive; matches since 2025-07-01)

Method. Offsets = production model means (mu_home, mu_away of baseline_predictions_full.csv.gz, out-of-sample).
ln E[home goals] = ln mu_h + x'theta_h, ln E[away goals] = ln mu_a + x'theta_a (penalised Poisson, analytic
gradient). Probabilities from the production score model (NB x Dixon-Coles, train-only goal layer). Protocol as the
project's training runs: fit on train, choose the L2 strength on validation, refit on train+validation, score the
test split once (paired bootstrap, 2,000 resamples, 90 % CI; negative = the signal helps). Weather exists only from
2025-07-01: fitted on validation, scored on test, fixed L2. Missing values -> 0 plus a missing indicator.

Run (from backend/):  OMP_NUM_THREADS=2 venv/Scripts/python.exe -I scripts/research/xdata_context_signals.py
Output: data/research/xdata_context_signals.json
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND / "scripts" / "training"))
import calibration_common as CC  # noqa: E402
import train_goal_model as T  # noqa: E402

RES = BACKEND / "data" / "research"
OUT = RES / "xdata_context_signals.json"
EPS = 1e-12


def fnum(s):
    return CC.fnum(s)


def hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(h)))


# ------------------------------------------------------------------ data
def load_all():
    d = CC.load_baseline()
    with gzip.open(CC.DATA / "baseline_predictions_full.csv.gz", "rt", encoding="utf-8", newline="") as f:
        o25 = {r["match_id"]: float(r["p_over25"]) for r in csv.DictReader(f) if r["status"] == "ok"}
    d["o25_file"] = np.array([o25[m] for m in d["match_id"]])
    with gzip.open(CC.DATA / "match_features_full.csv.gz", "rt", encoding="utf-8", newline="") as f:
        feats = {r["match_id"]: r for r in csv.DictReader(f)}
    with open(RES / "xdata_match_context.csv", encoding="utf-8") as f:
        ctx = {r["match_id"]: r for r in csv.DictReader(f)}
    elev = {}
    if (RES / "xdata_elevation.csv").exists():
        with open(RES / "xdata_elevation.csv", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["elevation_m"]:
                    elev[(float(r["lat"]), float(r["lon"]))] = float(r["elevation_m"])
    wx = {}
    if (RES / "xdata_weather_at_kickoff.csv").exists():
        with open(RES / "xdata_weather_at_kickoff.csv", encoding="utf-8") as f:
            wx = {r["match_id"]: r for r in csv.DictReader(f)}
    return d, feats, ctx, elev, wx


def build_features(d, feats, ctx, elev, wx):
    n = d["n"]
    mid = d["match_id"]
    groups: dict[str, dict[str, np.ndarray]] = defaultdict(dict)
    info = {}

    # ---- rest (feature file)
    def col(name):
        return np.array([fnum(feats.get(m, {}).get(name)) if m in feats else None for m in mid], dtype=object)
    hr, ar = col("home_rest_days"), col("away_rest_days")
    miss = np.array([a is None or b is None for a, b in zip(hr, ar)])
    hrf = np.array([min(float(x), 10.0) if x is not None else 0.0 for x in hr])
    arf = np.array([min(float(x), 10.0) if x is not None else 0.0 for x in ar])
    g = groups["rest"]
    g["rest_diff"] = np.where(miss, 0.0, hrf - arf)
    g["home_short"] = np.where(miss, 0.0, (hrf <= 3).astype(float))
    g["away_short"] = np.where(miss, 0.0, (arf <= 3).astype(float))
    for side in ("home", "away"):
        n14 = col(f"{side}_n_matches_14d")
        g[f"{side}_n14"] = np.array([float(x) if x is not None else 0.0 for x in n14])
        for k in ("euro_before_3d", "euro_after_3d"):
            v = col(f"{side}_{k}")
            g[f"{side}_{k}"] = np.array([float(x) if x is not None else 0.0 for x in v])
    g["rest_missing"] = miss.astype(float)
    info["rest_missing_share"] = round(float(miss.mean()), 4)

    # ---- venues: each team's usual home venue (mode of its home-match coordinates) and surface
    home_venues = defaultdict(Counter)
    home_surface = defaultdict(Counter)
    for r in ctx.values():
        if r["lat"] and r["home_team_id"]:
            k = (round(float(r["lat"]), 3), round(float(r["lon"]), 3))
            home_venues[r["home_team_id"]][k] += 1
            if r["surface"]:
                home_surface[r["home_team_id"]][r["surface"]] += 1
    team_home = {t: c.most_common(1)[0][0] for t, c in home_venues.items()}
    team_surface = {t: c.most_common(1)[0][0] for t, c in home_surface.items()}
    # FotMob team ids of each baseline row come from the context file (baseline uses DB/FotMob ids that match ctx)
    dist, neutral, alt, turf = (np.zeros(n) for _ in range(4))
    m_dist, m_alt, m_turf = (np.ones(n) for _ in range(3))
    for i, m in enumerate(mid):
        r = ctx.get(m)
        if not r or not r["lat"]:
            continue
        v = (round(float(r["lat"]), 3), round(float(r["lon"]), 3))
        ah, hh = team_home.get(r["away_team_id"]), team_home.get(r["home_team_id"])
        if ah is not None and hh is not None:
            dist[i] = math.log1p(hav(ah, v))
            neutral[i] = float(hav(hh, v) > 50.0)
            m_dist[i] = 0.0
            ev, ea = elev.get(v), elev.get(ah)
            if ev is not None and ea is not None:
                alt[i] = (ev - ea) / 1000.0
                m_alt[i] = 0.0
        sa = team_surface.get(r["away_team_id"])
        if r["surface"] and sa:
            turf[i] = float(r["surface"] == "artificial turf" and sa == "grass")
            m_turf[i] = 0.0
    groups["travel"] = {"log1p_km": dist, "home_not_at_usual_venue": neutral, "travel_missing": m_dist}
    groups["altitude"] = {"alt_diff_km": alt, "alt_missing": m_alt}
    groups["turf"] = {"turf_venue_vs_grass_team": turf, "turf_missing": m_turf}
    info["travel_known_share"] = round(float(1 - m_dist.mean()), 4)
    info["altitude_abs_diff_ge_0.5km"] = int((np.abs(alt) >= 0.5).sum())
    info["altitude_abs_diff_ge_1km"] = int((np.abs(alt) >= 1.0).sum())
    info["turf_flag_n"] = int(turf.sum())
    info["neutral_flag_n"] = int(neutral.sum())
    info["median_away_travel_km"] = round(float(np.median(np.expm1(dist[m_dist == 0]))), 1)

    # ---- coach change (only information before the match: previous team match in our data)
    team_hist = defaultdict(list)
    for r in ctx.values():
        for side in ("home", "away"):
            t, c = r[f"{side}_team_id"], r[f"{side}_coach_id"]
            if t and r["kickoff"]:
                team_hist[t].append((r["kickoff"], r["match_id"], c))
    since_change = {}  # (team, match_id) -> matches since last observed coach change (1 = first match)
    for t, h in team_hist.items():
        h.sort()
        last_c, cnt, prev_k = None, None, None
        for k, m, c in h:
            if not c:
                since_change[(t, m)] = None
                continue
            gap = None if prev_k is None else (dt.datetime.fromisoformat(k[:19]) -
                                               dt.datetime.fromisoformat(prev_k[:19])).days
            if last_c is None or gap is None or gap > 60:
                cnt = None  # unknown history: never call it a change
            elif c != last_c:
                cnt = 1
            elif cnt is not None:
                cnt += 1
            since_change[(t, m)] = cnt
            last_c, prev_k = c, k
    hc, ac, mc = np.zeros(n), np.zeros(n), np.ones(n)
    for i, m in enumerate(mid):
        r = ctx.get(m)
        if not r:
            continue
        a = since_change.get((r["home_team_id"], m))
        b = since_change.get((r["away_team_id"], m))
        mc[i] = 0.0
        hc[i] = float(a is not None and a <= 5)
        ac[i] = float(b is not None and b <= 5)
    groups["coach"] = {"home_new_coach_le5": hc, "away_new_coach_le5": ac}
    info["coach_changes_flagged_home"] = int(hc.sum())
    info["coach_changes_flagged_away"] = int(ac.sum())
    info["coach_first_match_events"] = int(sum(1 for v in since_change.values() if v == 1))

    # ---- referee ids
    refs = np.array([(ctx.get(m) or {}).get("referee", "") for m in mid], dtype=object)
    info["referee_known_share"] = round(float(np.mean(refs != "")), 4)

    # ---- weather
    W = {}
    have = np.zeros(n, bool)
    temp, prec, wind = np.zeros(n), np.zeros(n), np.zeros(n)
    for i, m in enumerate(mid):
        r = wx.get(m)
        if not r or r["temperature_2m"] == "" or r["precip_2h"] == "" or r["wind_speed_10m"] == "":
            continue
        have[i] = True
        temp[i], prec[i], wind[i] = float(r["temperature_2m"]), float(r["precip_2h"]), float(r["wind_speed_10m"])
    W["heavy_rain_2h_ge_4mm"] = np.where(have, (prec >= 4.0).astype(float), 0.0)
    W["rain_2h_ge_1mm"] = np.where(have, (prec >= 1.0).astype(float), 0.0)
    W["wind_ge_30kmh"] = np.where(have, (wind >= 30.0).astype(float), 0.0)
    W["temp_ge_28c"] = np.where(have, (temp >= 28.0).astype(float), 0.0)
    W["temp_le_2c"] = np.where(have, (temp <= 2.0).astype(float), 0.0)
    groups["weather"] = W
    info["weather_rows"] = int(have.sum())
    info["weather_counts"] = {k: int(v.sum()) for k, v in W.items()}
    return groups, refs, have, info


# ------------------------------------------------------------------ penalised Poisson with offsets
def fit_poisson(Xh, Xa, oh, oa, yh, ya, lam):
    k = Xh.shape[1]

    def f(t):
        th, ta = t[:k], t[k:]
        eh, ea = oh + Xh @ th, oa + Xa @ ta
        mh, ma = np.exp(eh), np.exp(ea)
        nll = (mh - yh * eh).sum() + (ma - ya * ea).sum() + 0.5 * lam * (t @ t)
        gh = Xh.T @ (mh - yh) + lam * th
        ga = Xa.T @ (ma - ya) + lam * ta
        return nll, np.r_[gh, ga]
    r = minimize(f, np.zeros(2 * k), jac=True, method="L-BFGS-B", options={"maxiter": 2000})
    return r.x[:k], r.x[k:]


def probs(mh, ma, layer):
    out1, o25 = np.empty((len(mh), 3)), np.empty(len(mh))
    for i in range(0, len(mh), 4000):
        m = T.score_matrix(mh[i:i + 4000], ma[i:i + 4000], layer["rho"], layer["nb_dispersion"])
        p, ov, _, _ = T.markets(m)
        out1[i:i + 4000], o25[i:i + 4000] = p, ov
    return out1, o25


def ll3(p, y):
    return -np.log(np.clip(p[np.arange(len(y)), y], EPS, 1))


def ll2(p, y):
    return -(y * np.log(np.clip(p, EPS, 1)) + (1 - y) * np.log(np.clip(1 - p, EPS, 1)))


def boot(dl):
    return CC.paired_boot(dl)


def rnd(x, k=5):
    return None if x is None else round(float(x), k)


def design(groups, names, refs, ref_vocab):
    cols, labels = [], []
    for gname in names:
        if gname == "referee":
            continue
        for k, v in groups[gname].items():
            cols.append(v)
            labels.append(f"{gname}.{k}")
    X = np.stack(cols, 1) if cols else np.zeros((len(refs), 0))
    if "referee" in names:
        R = np.zeros((len(refs), len(ref_vocab)))
        for i, r in enumerate(refs):
            j = ref_vocab.get(r)
            if j is not None:
                R[i, j] = 1.0
        # referee effect on total goals (+ on both) and on home-minus-away (+ home, - away)
        Xh = np.c_[X, R, R]
        Xa = np.c_[X, R, -R]
        labels = labels + [f"ref_total:{r}" for r in ref_vocab] + [f"ref_hadv:{r}" for r in ref_vocab]
        return Xh, Xa, labels
    return X, X, labels


def standardise(Xh, Xa, fit_mask):
    mu = Xh[fit_mask].mean(0)
    sd = Xh[fit_mask].std(0)
    sd[sd == 0] = 1.0
    binary = np.all(np.isin(Xh[fit_mask], (0.0, 1.0, -1.0)), axis=0)
    mu[binary] = 0.0
    sd[binary] = 1.0
    return (Xh - mu) / sd, (Xa - mu) / sd


def evaluate(d, layer, Xh, Xa, fit, sel_fit, sel_val, test, lams, base_p, base_o, fixed_lam=None):
    yh, ya = d["hg"].astype(float), d["ag"].astype(float)
    oh, oa = np.log(d["mu_h"]), np.log(d["mu_a"])
    y3 = d["y"]
    yo = ((d["hg"] + d["ag"]) > 2.5).astype(float)
    Xh, Xa = standardise(Xh, Xa, fit)
    sel = {}
    if fixed_lam is None:
        for lam in lams:
            th, ta = fit_poisson(Xh[sel_fit], Xa[sel_fit], oh[sel_fit], oa[sel_fit], yh[sel_fit], ya[sel_fit], lam)
            mh, ma = np.exp(oh[sel_val] + Xh[sel_val] @ th), np.exp(oa[sel_val] + Xa[sel_val] @ ta)
            p, _ = probs(mh, ma, layer)
            sel[lam] = float(ll3(p, y3[sel_val]).mean())
        lam = min(sel, key=sel.get)
    else:
        lam = fixed_lam
    th, ta = fit_poisson(Xh[fit], Xa[fit], oh[fit], oa[fit], yh[fit], ya[fit], lam)
    mh, ma = np.exp(oh[test] + Xh[test] @ th), np.exp(oa[test] + Xa[test] @ ta)
    p, o = probs(mh, ma, layer)
    d1 = ll3(p, y3[test]) - ll3(base_p[test], y3[test])
    d2 = ll2(o, yo[test]) - ll2(base_o[test], yo[test])
    tot_pred = (mh + ma).mean()
    return {"lambda": lam, "validation_1x2_by_lambda": {str(k): round(v, 5) for k, v in sel.items()},
            "test_n": int(test.sum()),
            "test_1x2_logloss_base": rnd(ll3(base_p[test], y3[test]).mean()),
            "test_1x2_logloss_with": rnd(ll3(p, y3[test]).mean()),
            "test_1x2_diff": {k: (rnd(v) if not isinstance(v, list) else [rnd(x) for x in v])
                              for k, v in boot(d1).items()},
            "test_ou25_diff": {k: (rnd(v) if not isinstance(v, list) else [rnd(x) for x in v])
                               for k, v in boot(d2).items()},
            "test_mean_total_goals": {"base": rnd((d["mu_h"][test] + d["mu_a"][test]).mean(), 4),
                                      "with": rnd(tot_pred, 4),
                                      "actual": rnd((d["hg"][test] + d["ag"][test]).mean(), 4)},
            "_theta": (th, ta)}


def main() -> int:
    d, feats, ctx, elev, wx = load_all()
    layer = CC.load_layer()
    groups, refs, have_wx, info = build_features(d, feats, ctx, elev, wx)
    split = d["split"]
    tr, va, te = split == "train", split == "validation", split == "test"
    trva = tr | va
    base_p, base_o = probs(d["mu_h"], d["mu_a"], layer)
    check = float(np.abs(base_p - d["p"]).max())
    res = {"info": info, "check_max_abs_diff_recomputed_vs_file_1x2": round(check, 6),
           "check_max_abs_diff_recomputed_vs_file_o25": round(float(np.abs(base_o - d["o25_file"]).max()), 6),
           "groups": {}}
    lams = [1.0, 10.0, 100.0, 1000.0, 10000.0]
    # referee vocab: referees with >= 10 matches in the fitting rows (train for selection; train+val for final)
    def vocab(mask):
        c = Counter(refs[mask])
        c.pop("", None)
        return {r: i for i, r in enumerate(sorted(r for r, k in c.items() if k >= 10))}

    plans = [["rest"], ["travel"], ["altitude"], ["turf"], ["coach"], ["referee"],
             ["rest", "travel", "altitude", "turf", "coach", "referee"]]
    for names in plans:
        key = "+".join(names)
        rv_sel = vocab(tr)
        rv_fin = vocab(trva)
        # selection pass uses the train vocabulary; final pass the train+val vocabulary
        Xh_s, Xa_s, _ = design(groups, names, refs, rv_sel)
        Xh_f, Xa_f, labels = design(groups, names, refs, rv_fin)
        # choose lambda with train vocab, then evaluate with the final vocab at that lambda
        e_sel = evaluate(d, layer, Xh_s, Xa_s, tr, tr, va, va, lams, base_p, base_o)
        e = evaluate(d, layer, Xh_f, Xa_f, trva, trva, te, te, lams, base_p, base_o, fixed_lam=e_sel["lambda"])
        e["validation_1x2_by_lambda"] = e_sel["validation_1x2_by_lambda"]
        e["validation_1x2_base"] = rnd(ll3(base_p[va], d["y"][va]).mean())
        th, ta = e.pop("_theta")
        if "referee" not in names:
            e["coef_per_sd_home_eq"] = {l: rnd(v, 4) for l, v in zip(labels, th)}
            e["coef_per_sd_away_eq"] = {l: rnd(v, 4) for l, v in zip(labels, ta)}
        else:
            k0 = len(labels) - 2 * len(rv_fin)
            rt, rh = th[k0:k0 + len(rv_fin)], th[k0 + len(rv_fin):]
            e["referees_in_vocab"] = len(rv_fin)
            e["referee_effect_sd"] = {"total_goals_log": rnd(rt.std(), 4), "home_adv_log": rnd(rh.std(), 4)}
            if k0:
                e["coef_per_sd_home_eq"] = {l: rnd(v, 4) for l, v in zip(labels[:k0], th[:k0])}
                e["coef_per_sd_away_eq"] = {l: rnd(v, 4) for l, v in zip(labels[:k0], ta[:k0])}
        res["groups"][key] = e
        print(key, json.dumps({k: e[k] for k in ("lambda", "test_n", "test_1x2_diff", "test_ou25_diff")}))
    # weather: fit on validation rows with weather, score test rows with weather
    if info["weather_rows"] > 500:
        fitw, tew = va & have_wx, te & have_wx
        # placebo / control: kick-off month bands (weather is seasonal, so a "weather" gain could be a calendar
        # effect such as stale early-season ratings). Same rows, same fits.
        months = np.array([int(k[5:7]) for k in d["kickoff"]])
        cal = {f"month_{a}_{b}": ((months >= a) & (months <= b)).astype(float)
               for a, b in ((7, 8), (9, 10), (11, 12), (1, 2), (3, 4))}
        Xw = np.stack(list(groups["weather"].values()), 1)
        Xc = np.stack(list(cal.values()), 1)
        names_w, names_c = list(groups["weather"]), list(cal)
        out = {}
        for variant, X, names_ in (("weather", Xw, names_w), ("calendar_only", Xc, names_c),
                                   ("weather_plus_calendar", np.c_[Xw, Xc], names_w + names_c)):
            out[variant] = {}
            for lam in (10.0, 100.0, 1000.0):
                e = evaluate(d, layer, X, X, fitw, fitw, tew, tew, lams, base_p, base_o, fixed_lam=lam)
                th, ta = e.pop("_theta")
                e["coef_home_eq"] = {k: rnd(v, 4) for k, v in zip(names_, th)}
                e["coef_away_eq"] = {k: rnd(v, 4) for k, v in zip(names_, ta)}
                e["fit_rows"] = int(fitw.sum())
                out[variant][str(lam)] = e
                print("weather-fit", variant, lam, int(fitw.sum()), e["test_n"], json.dumps(e["test_1x2_diff"]),
                      json.dumps(e["test_ou25_diff"]))
        res["groups"]["weather"] = {"note": "fitted on validation rows with weather, scored on test rows with weather;"
                                            " three fixed L2 strengths shown (no selection on test); calendar_only"
                                            " is the placebo control", "by_variant_lambda": out}
        # descriptive: actual minus model total goals by weather bucket (all rows with weather)
        resid = (d["hg"] + d["ag"]) - (d["mu_h"] + d["mu_a"])
        desc = {}
        for k, v in groups["weather"].items():
            on = have_wx & (v == 1)
            off = have_wx & (v == 0)
            if on.sum() >= 20:
                diff = resid[on].mean() - resid[off].mean()
                se = math.sqrt(resid[on].var() / on.sum() + resid[off].var() / off.sum())
                desc[k] = {"n_on": int(on.sum()), "resid_on": rnd(resid[on].mean(), 3),
                           "resid_off": rnd(resid[off].mean(), 3), "diff": rnd(diff, 3), "se": rnd(se, 3)}
        res["groups"]["weather"]["total_goal_residual_by_bucket"] = desc
        print("weather", json.dumps(desc))
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({"info": info, "check": res["check_max_abs_diff_recomputed_vs_file_1x2"],
                      "check_o25": res["check_max_abs_diff_recomputed_vs_file_o25"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
