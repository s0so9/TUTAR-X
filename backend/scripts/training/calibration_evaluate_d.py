"""Round 2 test stage (2026-10-14): score the candidates frozen by calibration_fit_d.py on the test split.

READ THIS FIRST: round 1 (calibration_evaluate.py) already read the test split once, for the UEFA home-advantage
term. This is therefore a SECOND read of the same split. It scores only the pre-declared list written into
calibration_frozen_round2.json before this script exists as a result (the chosen candidate of the round-2 selection
rule + the best "uefa_offset" and "uefa_offset_home_h" cells); the deploy verdict uses the chosen candidate only, with
the same rule as round 1 (1X2 log loss CI upper bound < 0 overall or on UEFA, rest not worse).

Also written here (descriptive, never used for choosing):
  * persistence of club offsets (does past UEFA over-performance predict the next residual?) on train and validation;
  * the clubs with the largest / smallest offsets as of 2026-10-14;
  * an illustration for tonight's City - PSG (fotmob_6106254) and Villa - Fenerbahce (fotmob_6106284): the
    production probabilities of docs/live-tests/2026-10-14/snapshots_pre/ before / after every candidate (not tuned on them).

Outputs: data/training/calibration_test_results_round2.json and data/training/calibration_candidate.json (round-1
candidate kept as data/training/calibration_candidate_round1.json and nested under "round1").

Usage (from backend/):  venv/Scripts/python.exe scripts/training/calibration_evaluate_d.py
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calibration_common as C  # noqa: E402
import calibration_evaluate as E1  # noqa: E402
import calibration_fixes as F  # noqa: E402
import calibration_offset as O  # noqa: E402

FROZEN2 = C.DATA / "calibration_frozen_round2.json"
FROZEN1 = C.DATA / "calibration_frozen.json"
REPO = C.BACKEND_DIR.parent
SNAP = REPO / "docs" / "live-tests" / "2026-10-14" / "snapshots_pre"
AS_OF = "2026-10-14T19:00:00"
TONIGHT = {"fotmob_6106254": "Man City - PSG", "fotmob_6106284": "Aston Villa - Fenerbahce"}


def z_for(fix: dict, d_all: dict, xg: dict) -> np.ndarray | None:
    if fix["kind"] != "team_offset":
        return None
    cfg = fix["config"]
    return O.build_z(d_all, cfg["metric"], cfg["k"], cfg["half_life_days"], xg=xg)


def spec(fx: dict) -> dict:
    return {k: v for k, v in fx.items() if k not in ("x", "y")}


def persistence(d_nt: dict, xg: dict, metric: str, k: float, H) -> dict:
    """OLS slope of the next residual (home view, goal / xG difference) on z, per split (train, validation only)."""
    res = O.home_view_residual(d_nt, xg, metric)
    z = O.build_z(d_nt, metric, k, H, res_home=res)
    out = {}
    for nm in ("train", "validation"):
        m = d_nt["euro"] & (d_nt["split"] == nm) & np.isfinite(res)
        x, yv = z[m], res[m]
        sxx = float(((x - x.mean()) ** 2).sum())
        b = float(((x - x.mean()) * (yv - yv.mean())).sum() / sxx)
        resid = yv - yv.mean() - b * (x - x.mean())
        se = float(np.sqrt((resid ** 2).sum() / (len(x) - 2) / sxx))
        out[nm] = {"n": int(m.sum()), "slope": round(b, 4), "se": round(se, 4),
                   "ci90": [round(b - C.Z90 * se, 4), round(b + C.Z90 * se, 4)]}
    return out


def snapshot(mid: str) -> dict:
    j = json.loads((SNAP / f"{mid}.json").read_text(encoding="utf-8"))
    r = j["response"]
    return {"p": np.array([[r["home_win_probability"], r["draw_probability"], r["away_win_probability"]]]),
            "mu_h": np.array([r["home_xg"]]), "mu_a": np.array([r["away_xg"]]),
            "home_id": str(r["squad_info"]["home"]["team_id"]), "away_id": str(r["squad_info"]["away"]["team_id"]),
            "home": j["match"]["home_team"]["name"], "away": j["match"]["away_team"]["name"],
            "fetched_at": j["fetched_at_utc"]}


def main() -> int:
    if not FROZEN2.exists() or not FROZEN1.exists():
        raise SystemExit("run calibration_fit.py and calibration_fit_d.py first (the test is read only after freezing)")
    fr2 = json.loads(FROZEN2.read_text(encoding="utf-8"))
    layer = fr2["goal_layer"]
    chosen = fr2["chosen"]
    names = fr2["round2_test_read_list"]
    xg = O.load_xg()
    d_all = C.load_baseline()
    nt_mask = d_all["split"] != "test"
    d_nt = C.subset(d_all, nt_mask)
    te_mask = d_all["split"] == "test"
    te = C.subset(d_all, te_mask)
    P, y, euro = te["p"], te["y"], te["euro"]
    print(f"round-2 test read (second read of the split): {te['n']} rows (UEFA {int(euro.sum())}); candidates {names}; chosen {chosen}")

    res = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "note": "SECOND read of the test split (round 1 read it once for the UEFA home term)",
           "test_rows": te["n"], "test_uefa": int(euro.sum()), "chosen_by_round2_rule": chosen, "candidates": {}}
    all_fixes = fr2["candidates"]
    for nm in names:
        fix = all_fixes[nm]["fit_on_train"]
        z_all = z_for(fix, d_all, xg)
        z_te = None if z_all is None else z_all[te_mask]
        Pa = F.apply_fix(fix, P, te["mu_h"], te["mu_a"], euro, layer, z=z_te)
        assert np.allclose(Pa.sum(1), 1.0, atol=1e-6) and np.array_equal(Pa[~euro], P[~euro])
        block = {"fit_on_train": spec(fix), "n_params": all_fixes[nm]["n_params"],
                 "metrics": E1.metrics(P, Pa, y, euro),
                 "favourites_at_least": {"uefa": E1.thresholds(P, Pa, y, euro), "all": E1.thresholds(P, Pa, y, np.ones(te["n"], bool))}}
        if z_te is not None:
            block["z_uefa_test_sd"] = round(float(z_te[euro].std()), 4)
        if nm == chosen and fr2["chosen_refit_on_train_plus_validation"] is not None:
            rf = fr2["chosen_refit_on_train_plus_validation"]
            z_rf = z_for(rf, d_all, xg)
            Pr = F.apply_fix(rf, P, te["mu_h"], te["mu_a"], euro, layer, z=None if z_rf is None else z_rf[te_mask])
            block["refit_train_plus_validation"] = {"params": spec(rf), "metrics": E1.metrics(P, Pr, y, euro)}
        mp = block["metrics"]
        ov, tg = mp["all"]["logloss"], mp["uefa"]["logloss"]
        ok_o = ov.get("ci90") is not None and ov["ci90"][1] < 0
        ok_t = tg.get("ci90") is not None and tg["ci90"][1] < 0
        block["deploy_check"] = {"overall_ci_upper_below_0": bool(ok_o), "uefa_ci_upper_below_0": bool(ok_t),
                                 "rest_not_worse": bool(mp["league"]["logloss"]["diff"] <= 0),
                                 "deploy": bool((ok_o or ok_t) and mp["league"]["logloss"]["diff"] <= 0)}
        res["candidates"][nm] = block
        print(f"{nm:<22} params {spec(fix)}")
        for seg in ("all", "league", "uefa"):
            b = mp[seg]["logloss"]
            ci = b.get("ci90")
            print(f"   1X2 log loss {seg:<7} n={mp[seg]['n']:>5} before {b['before']:.5f} after {b['after']:.5f} diff "
                  f"{b['diff']:+.5f}" + (f" ({ci[0]:+.5f}, {ci[1]:+.5f})" if ci else ""))
        print("   deploy check:", block["deploy_check"])

    # ---- descriptive: persistence + offsets table + illustration
    pers = {f"{m}_k{int(k)}_H{h}": persistence(d_nt, xg, m, k, h) for m in O.METRICS for k, h in ((6.0, None), (6.0, 730.0))}
    res["persistence_train_validation"] = pers
    rep = fr2["representatives"]["uefa_offset_home_h"]["config"]
    off = O.offsets_as_of(d_all, rep["metric"], rep["k"], rep["half_life_days"], AS_OF, xg=xg)
    off_gd = O.offsets_as_of(d_all, "gd", 6.0, None, AS_OF, xg=xg)
    res["offsets_as_of_2026_10_14"] = {"config_of_uefa_offset_home_h_representative": rep, "table": off,
                                       "note": "offset = shrunk mean of (actual - model-expected) goal difference per UEFA "
                                               "match over the club's previous UEFA matches; data end 2026-10-12"}
    top = sorted(off_gd.items(), key=lambda kv: -kv[1]["offset"])
    res["offsets_gd_k6_nodecay_extremes"] = {"highest": top[:10], "lowest": top[-10:]}

    ill = {}
    cand_specs = {nm: c["fit_on_train"] for nm, c in json.loads(FROZEN1.read_text(encoding="utf-8"))["candidates"].items()
                  if c["fit_on_train"]["kind"] not in ("identity",) and "n_knots" not in c["fit_on_train"]}
    cand_specs.update({nm: all_fixes[nm]["fit_on_train"] for nm in ("uefa_offset", "uefa_offset_home_h")})
    for mid, label in TONIGHT.items():
        sn = snapshot(mid)
        rep_p = C.p1x2_from_mu(sn["mu_h"], sn["mu_a"], layer)
        row = {"label": label, "teams": [sn["home"], sn["away"]], "snapshot_fetched_at": sn["fetched_at"],
               "production_1x2_snapshot": [round(float(v), 4) for v in sn["p"][0]],
               "recomputed_from_mu_with_train_only_layer": [round(float(v), 4) for v in rep_p[0]],
               "mu": [round(float(sn["mu_h"][0]), 4), round(float(sn["mu_a"][0]), 4)], "after": {}}
        for nm, fx in cand_specs.items():
            fix = dict(fx)
            z = None
            if fix["kind"] == "team_offset":
                cfg = fix["config"]
                tab = O.offsets_as_of(d_all, cfg["metric"], cfg["k"], cfg["half_life_days"], AS_OF, xg=xg)
                oh, oa = tab.get(sn["home_id"], {}).get("offset", 0.0), tab.get(sn["away_id"], {}).get("offset", 0.0)
                z = np.array([oh - oa])
                row.setdefault("offsets", {})[nm] = {"home": oh, "away": oa,
                                                     "n_matches": [tab.get(sn["home_id"], {}).get("n_matches", 0),
                                                                   tab.get(sn["away_id"], {}).get("n_matches", 0)]}
            base = sn["p"]
            if fix["kind"] == "ratio_shrink" or fix["kind"] == "team_offset":
                # ratio-based fixes are evaluated against the same score model: compare with the recomputed baseline
                pa = F.apply_fix(fix, rep_p, sn["mu_h"], sn["mu_a"], np.array([True]), layer, z=z)
                shift = pa - rep_p
                after = base + shift          # apply the change to the production snapshot probabilities
            else:
                after = F.apply_fix(fix, base, sn["mu_h"], sn["mu_a"], np.array([True]), layer, z=z)
            row["after"][nm] = [round(float(v), 4) for v in after[0]]
        ill[mid] = row
    res["tonight_illustration"] = {"note": "illustration only, never used for tuning; 'after' of ratio-based candidates = "
                                           "snapshot probabilities + (fix(mu) - recomputed(mu)) so the production layer "
                                           "differences cancel; temperature / Platt are applied to the snapshot probabilities",
                                   "matches": ill}
    (C.DATA / "calibration_test_results_round2.json").write_text(json.dumps(res, indent=1), encoding="utf-8")

    # ---- final candidate JSON (round 1 nested)
    cand_path = C.DATA / "calibration_candidate.json"
    r1_path = C.DATA / "calibration_candidate_round1.json"
    if not r1_path.exists():
        shutil.copyfile(cand_path, r1_path)
    r1 = json.loads(r1_path.read_text(encoding="utf-8"))
    ch = res["candidates"][chosen]
    fr_ch = fr2["chosen_fit_on_train"]
    chosen_deploy = ch["deploy_check"]["deploy"]
    cmain = ch["metrics"]
    cand = {
        "name": f"{chosen}_round2",
        "status": "DRAFT / not deployed. Nothing under backend/app or backend/config was written; the lead decides.",
        "built_at": res["built_at"],
        "question": r1["question"],
        "test_reads": "The test split was read twice: round 1 (UEFA home term, `round1`) and round 2 (this block); "
                      "the round-2 list was frozen in calibration_frozen_round2.json before the read.",
        "applies_to": r1["applies_to"],
        "chosen_by_round2_rule": chosen,
        "formula": ("d = ln(mu_home / mu_away); d' = k * d + h (+ gamma * z for team_offset candidates, z = offset_home - "
                    "offset_away); mu_home' = (mu_home + mu_away) * e^d'/(1 + e^d'), mu_away' = (mu_home + mu_away) / (1 + e^d'); "
                    "1X2 = production score model at (mu_home', mu_away'). team offsets: calibration_offset.py docstring."),
        "parameters": {"chosen_train_fit_TESTED": spec(fr_ch),
                       "chosen_refit_train_plus_validation": None if fr2["chosen_refit_on_train_plus_validation"] is None
                       else spec(fr2["chosen_refit_on_train_plus_validation"]), "goal_layer": layer},
        "validation_choices_round2": {"best_by_validation": fr2["best_by_validation"],
                                      "tied_within_1se": fr2["tied_with_best_within_1se"], "trace": fr2["selection_trace"],
                                      "candidates": {nm: {"n_params": c["n_params"], "eligible": c["eligible"],
                                                          "fit_on_train": c["fit_on_train"],
                                                          "validation_logloss_diff": {k: c["validation"][k]["logloss_diff"]
                                                                                      for k in ("all", "league", "uefa")}}
                                                     for nm, c in fr2["candidates"].items()},
                                      "offset_grid_validation": fr2["offset_grid_validation"],
                                      "design_declared_before_any_d_number": fr2["design_declared_before_any_d_number"]},
        "test_round2": {nm: {"fit_on_train": b["fit_on_train"], "metrics": b["metrics"], "deploy_check": b["deploy_check"]}
                        for nm, b in res["candidates"].items()},
        "deploy_criteria": {**ch["deploy_check"], "candidate": chosen,
                            "rule": "1X2 log loss paired 90 % CI upper bound < 0 overall or on UEFA, and league not worse"},
        "round1": r1,
        "persistence_of_club_offsets": res["persistence_train_validation"],
        "tonight_illustration": res["tonight_illustration"],
        "recommendation": None,
    }
    u, o = cmain["uefa"]["logloss"], cmain["all"]["logloss"]
    if chosen_deploy:
        cand["recommendation"] = ("DEPLOY (UEFA matches only) the round-2 chosen candidate "
                                  f"{chosen}: test criterion met (UEFA {u['diff']:+.5f}, CI {u['ci90'][0]:+.5f} .. {u['ci90'][1]:+.5f}).")
    else:
        cand["recommendation"] = (
            f"DO NOT DEPLOY. Round-2 chosen candidate {chosen}: 1X2 log loss change on test UEFA {u['diff']:+.5f} "
            f"(90 % CI {u['ci90'][0]:+.5f} .. {u['ci90'][1]:+.5f}, n = {u['n']}), overall {o['diff']:+.5f} "
            f"({o['ci90'][0]:+.5f} .. {o['ci90'][1]:+.5f}); neither upper bound is below 0. Round 1 (UEFA home term) failed the "
            "same way. The per-club European offset (d) found no persistence of past over/under-performance on validation "
            "(fitted gamma ~ 0, no validation gain in any of 16 cells). No fix that lowers favourite probabilities was "
            "supported at any stage.")
    cand_path.write_text(json.dumps(cand, indent=1), encoding="utf-8")

    print("\npersistence of club offsets (OLS slope of next residual on z):")
    for k, v in pers.items():
        print(" ", k, v)
    print("\noffsets as of 2026-10-14 (gd, k=6, no decay) highest:", [(k, v['offset'], v['n_matches']) for k, v in top[:6]])
    print("lowest:", [(k, v['offset'], v['n_matches']) for k, v in top[-6:]])
    for mid, row in ill.items():
        print(f"\n{row['label']}: production {row['production_1x2_snapshot']} (recomputed {row['recomputed_from_mu_with_train_only_layer']}), mu {row['mu']}")
        for nm, v in row["after"].items():
            print(f"   {nm:<22} {v}")
        print("   offsets:", row.get("offsets"))
    print(f"\n-> {C.DATA / 'calibration_test_results_round2.json'}, {cand_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
