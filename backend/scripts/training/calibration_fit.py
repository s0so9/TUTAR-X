"""Select stage of the favourite-calibration study (2026-10-14): fit the candidate fixes on TRAIN, choose on
VALIDATION only, write the frozen choice. The test split is never loaded here (rows with split == "test" are
dropped immediately after reading); calibration_evaluate.py reads it once, after this file exists.

Candidates (calibration_fixes.py): identity; temperature (one global T / T_league + T_uefa / UEFA only);
ratio shrink for UEFA (k, h-only, k + h); favourite-probability recalibration (logit-linear, all / UEFA only;
isotonic comparator).

Selection rule (fixed before the test is read):
  1. For every candidate: validation 1X2 log loss overall, league, UEFA vs the production probabilities
     (paired per-match differences, 2,000 resamples, seed 7).
  2. Eligible = validation point estimate of the change in league AND in UEFA log loss <= +0.0003
     (never worsen a subset) .
  3. Best = lowest validation overall log loss among eligible. One-standard-error rule: every eligible candidate
     whose paired difference to the best is within 1 SE is "tied"; the tied candidate with the fewest parameters
     wins (ties: UEFA-only scope before all matches, then the lower validation loss). The identity candidate
     (0 parameters) takes part: if the best candidate does not beat "no change" by more than 1 SE, no fix is chosen.
  4. The chosen structure is refitted on TRAIN + VALIDATION as a deployment option (scored on test in the same
     single test read, never used for choosing).

Usage (from backend/):  venv/Scripts/python.exe scripts/training/calibration_fit.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calibration_common as C  # noqa: E402
import calibration_fixes as F  # noqa: E402

TOLERANCE = 0.0003


def fit_candidates(d: dict, layer: dict) -> dict:
    """Fit every candidate on the rows of ``d`` (all rows are train rows here). Returns name -> fix spec."""
    p, y, mu_h, mu_a, euro = d["p"], d["y"], d["mu_h"], d["mu_a"], d["euro"]
    fits = {"identity": {"kind": "identity", "scope": "none"}}
    fits["temp_all"] = {"kind": "temperature", "scope": "all", "T": F.fit_temperature(p, y)}
    fits["temp_split"] = {"kind": "temperature", "scope": "split", "T_league": F.fit_temperature(p[~euro], y[~euro]),
                          "T_uefa": F.fit_temperature(p[euro], y[euro])}
    fits["temp_uefa"] = {"kind": "temperature", "scope": "uefa", "T_uefa": F.fit_temperature(p[euro], y[euro])}
    pe, ye, mhe, mae = p[euro], y[euro], mu_h[euro], mu_a[euro]
    kh = F.fit_ratio_shrink(pe, mhe, mae, ye, layer, free_k=True, free_h=False)
    fits["uefa_shrink_k"] = {"kind": "ratio_shrink", "scope": "uefa", "free_k": True, "free_h": False, **kh}
    hh = F.fit_ratio_shrink(pe, mhe, mae, ye, layer, free_k=False, free_h=True)
    fits["uefa_home_h"] = {"kind": "ratio_shrink", "scope": "uefa", "free_k": False, "free_h": True, **hh}
    kh2 = F.fit_ratio_shrink(pe, mhe, mae, ye, layer, free_k=True, free_h=True)
    fits["uefa_shrink_k_h"] = {"kind": "ratio_shrink", "scope": "uefa", "free_k": True, "free_h": True, **kh2}
    fits["fav_platt_all"] = {"kind": "fav_platt", "scope": "all", **F.fit_platt_fav(p, y)}
    fits["fav_platt_uefa"] = {"kind": "fav_platt", "scope": "uefa", **F.fit_platt_fav(pe, ye)}
    fits["fav_isotonic_all"] = {"kind": "fav_isotonic", "scope": "all", **F.fit_isotonic_fav(p, y)}
    return fits


def score_candidate(fix: dict, d: dict, layer: dict) -> dict:
    p2 = F.apply_fix(fix, d["p"], d["mu_h"], d["mu_a"], d["euro"], layer, z=d.get("z"))
    y = d["y"]
    base_l = C.logloss(d["p"], y)
    new_l = C.logloss(p2, y)
    base_b = C.brier(d["p"], y)
    new_b = C.brier(p2, y)
    euro = d["euro"]
    out = {"p": p2}
    for nm, m in (("all", np.ones(len(y), bool)), ("league", ~euro), ("uefa", euro)):
        out[nm] = {"n": int(m.sum()), "logloss_before": float(base_l[m].mean()), "logloss_after": float(new_l[m].mean()),
                   "logloss_diff": C.paired_boot(new_l[m] - base_l[m]), "brier_diff": C.paired_boot(new_b[m] - base_b[m])}
    out["per_match_diff"] = new_l - base_l
    return out


def rnd(x, k=5):
    return None if x is None else round(float(x), k)


def select_candidate(fits: dict, scored: dict):
    """The pre-declared selection rule (module docstring). Sets scored[nm]["eligible"]; returns
    (best, tied, chosen, trace)."""
    eligible = []
    for nm, s in scored.items():
        ok = s["league"]["logloss_diff"]["mean"] <= TOLERANCE and s["uefa"]["logloss_diff"]["mean"] <= TOLERANCE
        s["eligible"] = bool(ok)
        if ok:
            eligible.append(nm)
    best = min(eligible, key=lambda n: scored[n]["all"]["logloss_after"])
    dbest = scored[best]["per_match_diff"]
    tied = []
    trace = []
    for nm in eligible:
        dd = scored[nm]["per_match_diff"] - dbest
        se = float(dd.std(ddof=1) / np.sqrt(len(dd)))
        gap = float(dd.mean())
        is_tied = gap <= se
        trace.append({"candidate": nm, "params": F.n_params(fits[nm]),
                      "val_overall_logloss": rnd(scored[nm]["all"]["logloss_after"]),
                      "gap_to_best": rnd(gap), "se_gap": rnd(se), "tied_with_best": bool(is_tied)})
        if is_tied:
            tied.append(nm)
    scope_rank = {"none": 0, "uefa": 1, "split": 2, "all": 3}
    chosen = min(tied, key=lambda n: (F.n_params(fits[n]), scope_rank[fits[n]["scope"]],
                                      scored[n]["all"]["logloss_after"]))
    return best, tied, chosen, trace


def main() -> int:
    t0 = time.time()
    layer = C.load_layer()
    d_all = C.load_baseline()
    d_all = C.subset(d_all, d_all["split"] != "test")  # test rows are never used by this stage
    tr = C.subset(d_all, d_all["split"] == "train")
    va = C.subset(d_all, d_all["split"] == "validation")
    print(f"train {tr['n']} (UEFA {int(tr['euro'].sum())}), validation {va['n']} (UEFA {int(va['euro'].sum())})")

    fits = fit_candidates(tr, layer)
    scored = {nm: score_candidate(fx, va, layer) for nm, fx in fits.items()}
    train_scored = {nm: score_candidate(fx, tr, layer) for nm, fx in fits.items()}

    # ---- selection
    best, tied, chosen, trace = select_candidate(fits, scored)
    print(f"best by validation overall log loss: {best}; tied within 1 SE: {tied}; chosen: {chosen}")

    # ---- deployment refit of the chosen structure on train + validation (not used for choosing)
    refit = None
    if chosen != "identity":
        tv = C.subset(d_all, np.ones(d_all["n"], bool))
        refit = fit_candidates(tv, layer)[chosen]

    # ---- descriptive diagnostics (train / validation only; NOT used for the choice)
    diagnostics = {"temperature_sweep": {}, "uefa_home_h_by_period": {}, "uefa_home_h_by_competition": {}}
    for nm, dd in (("train", tr), ("validation", va)):
        sweep = []
        for T in (0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.20, 1.30):
            ll = C.logloss(F.temperature(dd["p"], T), dd["y"])
            sweep.append({"T": T, "all": rnd(ll.mean()), "league": rnd(ll[~dd["euro"]].mean()),
                          "uefa": rnd(ll[dd["euro"]].mean())})
        diagnostics["temperature_sweep"][nm] = sweep
    periods = {"2022-08..2023-06": ("2022-08-01", "2023-07-01"), "2023-07..2024-06": ("2023-07-01", "2024-07-01"),
               "2024-07..2025-06": ("2024-07-01", "2025-07-01"),
               "2025-07..2026-01 (validation)": ("2025-07-01", "2026-02-01")}
    for lab, (a, b) in periods.items():
        m = d_all["euro"] & (d_all["kickoff"] >= a) & (d_all["kickoff"] < b)
        if m.sum() >= 30:
            r = F.fit_ratio_shrink(d_all["p"][m], d_all["mu_h"][m], d_all["mu_a"][m], d_all["y"][m], layer, False, True)
            diagnostics["uefa_home_h_by_period"][lab] = {"n": int(m.sum()), "h": rnd(r["h"], 4)}
    for cid, nmc in (("42", "Champions League"), ("73", "Europa League"), ("10216", "Conference League")):
        m = d_all["euro"] & (d_all["comp"] == cid)
        r = F.fit_ratio_shrink(d_all["p"][m], d_all["mu_h"][m], d_all["mu_a"][m], d_all["y"][m], layer, False, True)
        diagnostics["uefa_home_h_by_competition"][nmc] = {"n": int(m.sum()), "h": rnd(r["h"], 4)}

    # ---- report
    def pack(s):
        return {k: s[k] for k in ("all", "league", "uefa")}
    rows = {}
    for nm, fx in fits.items():
        spec = {k: v for k, v in fx.items() if k not in ("x", "y")}
        if "x" in fx:
            spec["n_knots"] = len(fx["x"])
        rows[nm] = {"fit_on_train": spec, "n_params": F.n_params(fx), "eligible": scored[nm]["eligible"],
                    "validation": pack(scored[nm]), "train_in_sample": {k: train_scored[nm][k]["logloss_diff"]["mean"]
                                                                       for k in ("all", "league", "uefa")}}
    frozen = {
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stage": "select (fit on train, choose on validation; test not read)",
        "splits_used": {"train": tr["n"], "train_uefa": int(tr["euro"].sum()), "validation": va["n"],
                        "validation_uefa": int(va["euro"].sum())},
        "selection_rule": __doc__.split("Selection rule")[1].split("Usage")[0].strip(),
        "tolerance_subset_worsening": TOLERANCE,
        "best_by_validation": best, "tied_with_best_within_1se": tied, "chosen": chosen,
        "chosen_fit_on_train": fits[chosen],
        "chosen_refit_on_train_plus_validation": refit,
        "selection_trace": trace,
        "candidates": rows,
        "diagnostics_not_used_for_choice": diagnostics,
        "bootstrap": {"resamples": C.BOOT_N, "seed": C.BOOT_SEED, "ci": "90 % percentile, paired per-match differences"},
        "goal_layer": layer,
    }
    path = C.DATA / "calibration_frozen.json"
    path.write_text(json.dumps(frozen, indent=1), encoding="utf-8")

    print(f"\n{'candidate':<20}{'#par':>5} {'elig':>5} {'val all':>9} {'d all (CI90)':>30} {'d league':>11} {'d UEFA (CI90)':>30}")
    for nm in fits:
        s = scored[nm]

        def f(b):
            ci = b.get("ci90")
            return f"{b['mean']:+.5f} ({ci[0]:+.5f},{ci[1]:+.5f})" if ci else f"{b['mean']:+.5f}"
        print(f"{nm:<20}{F.n_params(fits[nm]):>5} {str(s['eligible']):>5} {s['all']['logloss_after']:>9.5f} "
              f"{f(s['all']['logloss_diff']):>30} {s['league']['logloss_diff']['mean']:>+11.5f} "
              f"{f(s['uefa']['logloss_diff']):>30}")
    print("\nfitted parameters (train):")
    for nm, fx in fits.items():
        print(" ", nm, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in fx.items() if k not in ("x", "y")})
    print("\ntemperature sweep (log loss; T > 1 flattens):")
    for nm, sw in diagnostics["temperature_sweep"].items():
        for r in sw:
            print(" ", nm, r)
    print("UEFA home term h by period:", diagnostics["uefa_home_h_by_period"])
    print("UEFA home term h by competition:", diagnostics["uefa_home_h_by_competition"])
    print("\nselection trace:")
    for t in trace:
        print(" ", t)
    print(f"\nchosen: {chosen}; refit(train+val): "
          f"{ {k: (round(v, 4) if isinstance(v, float) else v) for k, v in (refit or {}).items() if k not in ('x', 'y')} }")
    print(f"-> {path} ({time.time() - t0:.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
