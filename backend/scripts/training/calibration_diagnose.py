"""Favourite-calibration diagnosis of the production 1X2 model (2026-10-14).

Question (owner): "big teams (Aston Villa, Man City) are rated too strongly". Is the production 1X2 model
systematically over-confident on favourites, and where?

Data: data/training/baseline_predictions_full.csv.gz (production model, out-of-sample, train-only goal layer).
Only the TRAIN and VALIDATION splits are read here (2022-08-01 .. 2026-01-31); the test split is not touched
(it is read once, after the fix is frozen, by calibration_evaluate.py).

Tables (favourite = the 1X2 outcome with the largest probability; no draw is ever the favourite in this data):
  * calibration of the favourite's win probability by band, with Wilson 90 % intervals of the observed rate
    - all / league / UEFA, home / away favourite, UEFA by competition, UEFA by the favourite's domestic league
  * calibration intercept / slope (logistic regression of "favourite won" on logit(p_fav)); slope < 1 = over-confident
  * league matches with closing odds: model vs de-vigged closing market for the same outcome
Output: data/training/calibration_diagnosis.json and a text report on stdout.

Usage (from backend/):  venv/Scripts/python.exe scripts/training/calibration_diagnose.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calibration_common as C  # noqa: E402


def logit(p):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return np.log(p / (1 - p))


def platt(pf: np.ndarray, hit: np.ndarray, iters: int = 50) -> dict:
    """Logistic regression  hit ~ a + b * logit(pf)  (Newton / IRLS); b < 1 means over-confident."""
    n = len(pf)
    if n < 30:
        return {"n": n}
    x = logit(pf)
    X = np.stack([np.ones(n), x], 1)
    w = np.array([0.0, 1.0])
    for _ in range(iters):
        z = X @ w
        mu = 1 / (1 + np.exp(-z))
        g = X.T @ (hit - mu)
        H = (X * (mu * (1 - mu))[:, None]).T @ X + 1e-9 * np.eye(2)
        step = np.linalg.solve(H, g)
        w = w + step
        if np.abs(step).max() < 1e-10:
            break
    mu = 1 / (1 + np.exp(-(X @ w)))
    cov = np.linalg.inv((X * (mu * (1 - mu))[:, None]).T @ X + 1e-9 * np.eye(2))
    se = np.sqrt(np.diag(cov))
    return {"n": n, "intercept": round(float(w[0]), 4), "slope": round(float(w[1]), 4),
            "slope_ci90": [round(float(w[1] - C.Z90 * se[1]), 4), round(float(w[1] + C.Z90 * se[1]), 4)]}


def gap_block(pf: np.ndarray, hit: np.ndarray, thr: float = 0.0) -> dict:
    """mean predicted - observed for favourites with p_fav >= thr (positive = over-confident), 90 % bootstrap CI."""
    sel = pf >= thr
    n = int(sel.sum())
    if n == 0:
        return {"threshold": thr, "n": 0}
    diff = pf[sel] - hit[sel].astype(float)
    b = C.paired_boot(diff)
    lo, hi = C.wilson(int(hit[sel].sum()), n)
    return {"threshold": thr, "n": n, "mean_pred": round(float(pf[sel].mean()), 4),
            "observed": round(float(hit[sel].mean()), 4), "observed_ci90": [round(lo, 4), round(hi, 4)],
            "gap_pred_minus_obs": round(b["mean"], 4),
            "gap_ci90": [round(b["ci90"][0], 4), round(b["ci90"][1], 4)] if "ci90" in b else None}


def segment(p: np.ndarray, y: np.ndarray) -> dict:
    pf = p.max(1)
    hit = p.argmax(1) == y
    return {"summary": C.summary_row(p, y), "bands": C.fav_table(p, y), "calibration_fit": platt(pf, hit),
            "gap_all": gap_block(pf, hit, 0.0), "gap_ge_0.60": gap_block(pf, hit, 0.60),
            "gap_ge_0.70": gap_block(pf, hit, 0.70), "fav_ge_0.70": C.fav_ge(p, y, 0.70),
            "fav_ge_0.80": C.fav_ge(p, y, 0.80)}


def print_bands(title: str, seg: dict) -> None:
    s = seg["summary"]
    cf = seg["calibration_fit"]
    print(f"\n{title}  (n={s.get('n', 0)}, 1X2 log loss {s.get('logloss')}, fav hit {s.get('fav_hit')}, "
          f"slope {cf.get('slope')} {cf.get('slope_ci90')})")
    print(f"  {'band':>10} {'n':>6} {'pred':>7} {'obs':>7} {'90% CI':>16} {'gap':>7}")
    for b in seg["bands"]:
        if b["n"] == 0:
            continue
        print(f"  {b['band']:>10} {b['n']:>6} {b['mean_pred']:>7.3f} {b['observed']:>7.3f} "
              f"[{b['ci90'][0]:.3f},{b['ci90'][1]:.3f}] {b['gap']:>+7.3f}")


def main() -> int:
    d = C.load_baseline()
    keep = d["split"] != "test"
    d = C.subset(d, keep)
    lookup = C.team_league_lookup()
    fav_idx = d["p"].argmax(1)
    fav_is_home = fav_idx == 0
    fav_team = np.where(fav_is_home, d["home_id"], d["away_id"])
    dog_team = np.where(fav_is_home, d["away_id"], d["home_id"])
    n = d["n"]
    fav_comp = [lookup(fav_team[i], d["kickoff"][i]) for i in range(n)]
    dog_comp = [lookup(dog_team[i], d["kickoff"][i]) for i in range(n)]
    fav_grp = np.array([C.league_group(c) for c in fav_comp])
    dog_grp = np.array([C.league_group(c) for c in dog_comp])
    euro = d["euro"]
    P, Y = d["p"], d["y"]

    out = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "data": "baseline_predictions_full.csv.gz, splits train + validation only (test not read)",
           "n_rows": int(n), "n_uefa": int(euro.sum()),
           "note": "favourite = argmax of the production 1X2 probabilities; hit = favourite won; intervals are Wilson 90 %"}

    def seg(mask):
        return segment(P[mask], Y[mask])

    # ---- 1. league vs UEFA, by split
    out["all"] = seg(np.ones(n, bool))
    out["league"] = seg(~euro)
    out["uefa"] = seg(euro)
    out["uefa_train"] = seg(euro & (d["split"] == "train"))
    out["uefa_validation"] = seg(euro & (d["split"] == "validation"))
    out["league_train"] = seg(~euro & (d["split"] == "train"))
    out["league_validation"] = seg(~euro & (d["split"] == "validation"))
    # ---- 2. home / away favourite
    out["by_side"] = {}
    for nm, ms in (("league", ~euro), ("uefa", euro)):
        for side, sm in (("home_favourite", fav_is_home), ("away_favourite", ~fav_is_home)):
            out["by_side"][f"{nm}_{side}"] = seg(ms & sm)
    # ---- 3. UEFA by competition
    names = {"42": "Champions League", "73": "Europa League", "10216": "Conference League"}
    out["uefa_by_competition"] = {names[c]: seg(euro & (d["comp"] == c)) for c in names}
    # ---- 4. UEFA by the favourite's domestic league
    out["uefa_by_fav_league"] = {g: seg(euro & (fav_grp == g)) for g in
                                 ("Premier League", "other top-5 league", "other covered league", "not covered")}
    out["uefa_by_fav_league_home_only"] = {g: seg(euro & (fav_grp == g) & fav_is_home) for g in
                                           ("Premier League", "other top-5 league", "other covered league",
                                            "not covered")}
    out["uefa_pl_favourite_by_opponent"] = {g: seg(euro & (fav_grp == "Premier League") & (dog_grp == g)) for g in
                                            ("other top-5 league", "other covered league", "not covered")}
    out["uefa_favourite_pl_vs_non_pl_ge_0.6"] = {
        "Premier League favourite": gap_block(P.max(1)[euro & (fav_grp == "Premier League")],
                                              (P.argmax(1) == Y)[euro & (fav_grp == "Premier League")], 0.6),
        "other favourite": gap_block(P.max(1)[euro & (fav_grp != "Premier League")],
                                     (P.argmax(1) == Y)[euro & (fav_grp != "Premier League")], 0.6)}
    # league fav by domestic league (is any league an outlier?)
    comps = sorted(set(d["comp"][~euro]))
    out["league_by_competition"] = {C.LEAGUE_NAMES.get(c, c): segment(P[(d["comp"] == c)], Y[(d["comp"] == c)])
                                    for c in comps if (d["comp"] == c).sum() >= 200}

    # ---- 5. closing market (league matches that have odds)
    odds = C.load_closing_odds()
    have = np.array([m in odds for m in d["match_id"]])
    sel = have & ~euro
    mk = np.array([odds[m] for m in d["match_id"][sel]])
    mk = mk / mk.sum(1, keepdims=True)
    Pm, Ym = P[sel], Y[sel]
    pf_m = Pm.max(1)
    fav_m = Pm.argmax(1)
    mk_on_fav = mk[np.arange(len(fav_m)), fav_m]
    hit_m = fav_m == Ym
    mkt = {"n": int(sel.sum()),
           "model": C.summary_row(Pm, Ym), "market": C.summary_row(mk, Ym),
           "model_fav_bands_vs_market": [], "market_fav_calibration": C.fav_table(mk, Ym)}
    for lo, hi in zip(C.FAV_BANDS[:-1], C.FAV_BANDS[1:]):
        s = (pf_m >= lo) & (pf_m < hi)
        if s.sum() == 0:
            continue
        diff = pf_m[s] - mk_on_fav[s]
        b = C.paired_boot(diff)
        kk = int(hit_m[s].sum())
        wl, wh = C.wilson(kk, int(s.sum()))
        mkt["model_fav_bands_vs_market"].append({
            "band": C.band_label(lo, hi), "n": int(s.sum()), "model_mean": round(float(pf_m[s].mean()), 4),
            "market_mean_same_outcome": round(float(mk_on_fav[s].mean()), 4),
            "observed": round(kk / int(s.sum()), 4), "observed_ci90": [round(wl, 4), round(wh, 4)],
            "model_minus_market": round(b["mean"], 4),
            "model_minus_market_ci90": [round(b["ci90"][0], 4), round(b["ci90"][1], 4)] if "ci90" in b else None})
    mkt["model_calibration_fit"] = platt(pf_m, hit_m)
    mkt["market_calibration_fit"] = platt(mk.max(1), mk.argmax(1) == Ym)
    out["league_matches_with_closing_odds"] = mkt
    out["_bootstrap"] = {"resamples": C.BOOT_N, "seed": C.BOOT_SEED}

    # ---- print
    for key in ("all", "league", "uefa", "uefa_train", "uefa_validation"):
        print_bands(key.upper(), out[key])
    for k, v in out["by_side"].items():
        print_bands(k, v)
    for k, v in out["uefa_by_competition"].items():
        print_bands("UEFA " + k, v)
    for k, v in out["uefa_by_fav_league"].items():
        print_bands("UEFA fav league = " + k, v)
    for k, v in out["uefa_by_fav_league_home_only"].items():
        print_bands("UEFA HOME fav league = " + k, v)
    for k, v in out["uefa_pl_favourite_by_opponent"].items():
        print_bands("UEFA PL favourite vs " + k, v)
    print("\nUEFA favourite >= 0.60, PL vs other:", json.dumps(out["uefa_favourite_pl_vs_non_pl_ge_0.6"], indent=1))
    for k, v in out["league_by_competition"].items():
        s = v["summary"]
        print(f"  league {k:>22}: n={s['n']:>5} ll={s['logloss']} fav pred {s['mean_fav_pred']} hit {s['fav_hit']} "
              f"slope {v['calibration_fit'].get('slope')}")
    print("\nCLOSING MARKET (league):", json.dumps({k: mkt[k] for k in ("n", "model", "market",
                                                                       "model_calibration_fit",
                                                                       "market_calibration_fit")}, indent=1))
    for b in mkt["model_fav_bands_vs_market"]:
        print("  ", b)
    path = C.DATA / "calibration_diagnosis.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\n-> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
