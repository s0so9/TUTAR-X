"""Round 2 select stage (2026-10-14): candidate (d), the per-club European offset, alongside (a)-(c).

Added at the coordinator's request AFTER round 1 had already read the test split once (the UEFA home-advantage term of
calibration_fit.py failed there). What this means for the evidence:
  * the idea behind (d) comes from club-level over/under-performance computed on ALL UEFA matches 2022-08..2026-10, i.e. it
    includes the test period; the design (metrics, shrinkage grid, decay grid) is declared below and was fixed before
    any (d) number was computed, and nothing in this stage reads the test split (rows with split == "test" are dropped);
  * the final test read (calibration_evaluate_d.py) is therefore a SECOND read of the test split and is reported as such.

Candidates added to the round-1 list (fit_candidates of calibration_fit.py, unchanged):
  uefa_offset          d' = d + gamma * z                 (1 fitted parameter + 3 tuned hyper-parameters)
  uefa_offset_home_h   d' = d + h + gamma * z             (2 fitted parameters + 3 tuned hyper-parameters)
Hyper-parameters (grid, validation only): residual metric {gd, xgd}; shrinkage k in {3, 6, 12, 24}; half-life {none, 730 d}.
gamma (and h) are fitted on TRAIN UEFA rows; for each grid cell the validation overall 1X2 log loss is computed; the best
cell of each family is the representative. The pre-declared round-1 selection rule (calibration_fit.select_candidate:
eligible = no subset worse than +0.0003, best by validation overall log loss, one-standard-error rule, fewest parameters)
then picks among ALL candidates, with n_params counting gamma, h and the three tuned hyper-parameters.
Output: data/training/calibration_frozen_round2.json (includes the list of candidates the round-2 test read will score).

Usage (from backend/):  venv/Scripts/python.exe scripts/training/calibration_fit_d.py
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
import calibration_fit as R1  # noqa: E402
import calibration_offset as O  # noqa: E402


def offset_fix(cfg: dict, params: dict, free_h: bool) -> dict:
    return {"kind": "team_offset", "scope": "uefa", "free_h": free_h, "config": cfg, **params}


def main() -> int:
    t0 = time.time()
    layer = C.load_layer()
    d_all = C.load_baseline()
    d_all = C.subset(d_all, d_all["split"] != "test")  # test rows are never used by this stage
    xg = O.load_xg()
    is_tr = d_all["split"] == "train"
    is_va = d_all["split"] == "validation"
    tr = C.subset(d_all, is_tr)
    va = C.subset(d_all, is_va)
    euro_tr = tr["euro"]

    # ---- round-1 candidates, refit exactly as before
    fits = R1.fit_candidates(tr, layer)
    scored = {nm: R1.score_candidate(fx, va, layer) for nm, fx in fits.items()}

    # ---- (d) grid
    grid = []
    reps = {}
    for metric in O.METRICS:
        res_home = O.home_view_residual(d_all, xg, metric)
        for k in O.K_GRID:
            for H in O.HALF_LIFE_GRID:
                cfg = {"metric": metric, "k": k, "half_life_days": H}
                z_all = O.build_z(d_all, metric, k, H, res_home=res_home)
                ztr, zva = z_all[is_tr], z_all[is_va]
                row = {"config": cfg, "z_sd_uefa_train": round(float(ztr[euro_tr].std()), 4)}
                for fam, free_h in (("uefa_offset", False), ("uefa_offset_home_h", True)):
                    par = F.fit_offset(tr["mu_h"][euro_tr], tr["mu_a"][euro_tr], ztr[euro_tr], tr["y"][euro_tr],
                                       layer, free_h)
                    fx = offset_fix(cfg, par, free_h)
                    vv = dict(va, z=zva)
                    s = R1.score_candidate(fx, vv, layer)
                    row[fam] = {"params": {k2: round(v, 5) for k2, v in par.items()},
                                "val_overall_logloss": round(s["all"]["logloss_after"], 5),
                                "val_diff_overall": R1.rnd(s["all"]["logloss_diff"]["mean"]),
                                "val_diff_uefa": R1.rnd(s["uefa"]["logloss_diff"]["mean"]),
                                "val_diff_uefa_ci90": [R1.rnd(x) for x in s["uefa"]["logloss_diff"].get("ci90", [None, None])]}
                    if fam not in reps or s["all"]["logloss_after"] < reps[fam]["s"]["all"]["logloss_after"]:
                        reps[fam] = {"fix": fx, "s": s, "z_all": z_all}
                grid.append(row)
    for fam, r in reps.items():
        fits[fam] = r["fix"]
        scored[fam] = r["s"]

    best, tied, chosen, trace = R1.select_candidate(fits, scored)
    print(f"best by validation overall log loss: {best}; tied within 1 SE: {tied}; chosen: {chosen}")

    # ---- refit of the chosen structure on train + validation (deployment option, not used for choosing)
    refit = None
    if chosen != "identity":
        tv = C.subset(d_all, np.ones(d_all["n"], bool))
        if fits[chosen]["kind"] == "team_offset":
            cfg = fits[chosen]["config"]
            z_tv = O.build_z(d_all, cfg["metric"], cfg["k"], cfg["half_life_days"], xg=xg)
            par = F.fit_offset(tv["mu_h"][tv["euro"]], tv["mu_a"][tv["euro"]], z_tv[tv["euro"]], tv["y"][tv["euro"]],
                               layer, fits[chosen]["free_h"])
            refit = offset_fix(cfg, par, fits[chosen]["free_h"])
        else:
            refit = R1.fit_candidates(tv, layer)[chosen]

    def spec(fx):
        return {k: v for k, v in fx.items() if k not in ("x", "y")}
    rows = {}
    for nm, fx in fits.items():
        s = scored[nm]
        rows[nm] = {"fit_on_train": spec(fx), "n_params": F.n_params(fx), "eligible": s["eligible"],
                    "validation": {k: s[k] for k in ("all", "league", "uefa")}}
    frozen = {
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stage": "round 2 select (fit on train, choose on validation; test not read by this stage)",
        "note": "round 1 (calibration_frozen.json) had already read the test split once when this round was added; "
                "the round-2 test read is a second read.",
        "tolerance_subset_worsening": R1.TOLERANCE,
        "best_by_validation": best, "tied_with_best_within_1se": tied, "chosen": chosen,
        "chosen_fit_on_train": fits[chosen], "chosen_refit_on_train_plus_validation": refit,
        "round2_test_read_list": sorted({chosen, "uefa_offset", "uefa_offset_home_h"} - {"identity"}),
        "selection_trace": trace,
        "candidates": rows,
        "offset_grid_validation": grid,
        "representatives": {fam: {"config": r["fix"]["config"], "params": {k: r["fix"][k] for k in ("gamma", "h")}}
                            for fam, r in reps.items()},
        "design_declared_before_any_d_number": {"metrics": list(O.METRICS), "k_grid": list(O.K_GRID),
                                                "half_life_grid": list(O.HALF_LIFE_GRID),
                                                "guard": "past match must have started >= 3 h before kick-off"},
        "bootstrap": {"resamples": C.BOOT_N, "seed": C.BOOT_SEED},
        "goal_layer": layer,
    }
    path = C.DATA / "calibration_frozen_round2.json"
    path.write_text(json.dumps(frozen, indent=1), encoding="utf-8")

    def f(b):
        ci = b.get("ci90")
        return f"{b['mean']:+.5f} ({ci[0]:+.5f},{ci[1]:+.5f})" if ci else f"{b['mean']:+.5f}"
    print(f"\n{'candidate':<22}{'#par':>5} {'elig':>5} {'val all':>9} {'d all (CI90)':>30} {'d UEFA (CI90)':>30}")
    for nm in fits:
        s = scored[nm]
        print(f"{nm:<22}{F.n_params(fits[nm]):>5} {str(s['eligible']):>5} {s['all']['logloss_after']:>9.5f} "
              f"{f(s['all']['logloss_diff']):>30} {f(s['uefa']['logloss_diff']):>30}")
    print("\n(d) grid: validation overall log loss (baseline 0.98801)")
    for g in grid:
        c = g["config"]
        print(f"  {c['metric']:>3} k={c['k']:>4} H={str(c['half_life_days']):>6} z_sd={g['z_sd_uefa_train']:.3f} | "
              f"offset gamma={g['uefa_offset']['params']['gamma']:+.3f} val={g['uefa_offset']['val_overall_logloss']:.5f} "
              f"uefa_d={g['uefa_offset']['val_diff_uefa']:+.5f} | +h gamma={g['uefa_offset_home_h']['params']['gamma']:+.3f} "
              f"h={g['uefa_offset_home_h']['params']['h']:+.3f} val={g['uefa_offset_home_h']['val_overall_logloss']:.5f} "
              f"uefa_d={g['uefa_offset_home_h']['val_diff_uefa']:+.5f}")
    print("\nrepresentatives:", json.dumps(frozen["representatives"]))
    print("\nselection trace:")
    for t in trace:
        print(" ", t)
    print(f"\nchosen: {chosen}; refit: {refit if refit is None else {k: v for k, v in refit.items() if k not in ('x', 'y')}}")
    print(f"test-read list: {frozen['round2_test_read_list']}\n-> {path} ({time.time() - t0:.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
