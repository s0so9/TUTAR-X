"""Test stage of the favourite-calibration study (2026-10-14): read the TEST split ONCE, with the fix frozen by
calibration_fit.py (data/training/calibration_frozen.json), and write the candidate JSON.

The script refuses to run without the frozen file. It scores the chosen structure with its TRAIN-fitted
parameters (primary, as tested) and, for information, with the train + validation refit (declared in the frozen
file before the test was read; never used for choosing). Nothing else is scored on test.

Outputs
  data/training/calibration_test_results.json   all test numbers (before / after, CIs, tables)
  data/training/calibration_candidate.json      the candidate: formula, parameters, validation choices, test
                                                results, deploy recommendation (DRAFT; nothing in app/ or config/ is written)

Deploy rule (written before the test was read): deploy only if the paired 90 % bootstrap CI of the change in
1X2 log loss (after - before) has its upper bound < 0 overall OR on the subset the fix targets, AND the rest of
the matches is not worse (point estimate of the change <= 0).

Usage (from backend/):  venv/Scripts/python.exe scripts/training/calibration_evaluate.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calibration_common as C  # noqa: E402
import calibration_fixes as F  # noqa: E402

FROZEN = C.DATA / "calibration_frozen.json"


def rnd(x, k=5):
    return None if x is None else round(float(x), k)


def paired_block(before: np.ndarray, after: np.ndarray) -> dict:
    if len(before) == 0:
        return {"n": 0}
    d = after - before
    b = C.paired_boot(d)
    out = {"n": b["n"], "before": rnd(before.mean()), "after": rnd(after.mean()), "diff": rnd(b["mean"])}
    if "ci90" in b:
        out["ci90"] = [rnd(b["ci90"][0]), rnd(b["ci90"][1])]
    return out


def metrics(Pb: np.ndarray, Pa: np.ndarray, y: np.ndarray, euro: np.ndarray) -> dict:
    out = {}
    lb, la = C.logloss(Pb, y), C.logloss(Pa, y)
    bb, ba = C.brier(Pb, y), C.brier(Pa, y)
    for nm, m in (("all", np.ones(len(y), bool)), ("league", ~euro), ("uefa", euro)):
        out[nm] = {"n": int(m.sum()), "logloss": paired_block(lb[m], la[m]), "brier": paired_block(bb[m], ba[m])}
    return out


def fav_block(Pb, Pa, y, mask):
    return {"before": C.fav_table(Pb[mask], y[mask]), "after": C.fav_table(Pa[mask], y[mask])}


def thresholds(Pb, Pa, y, mask) -> dict:
    out = {}
    for thr in (0.60, 0.70, 0.80, 0.85, 0.90):
        e = {"before": C.fav_ge(Pb[mask], y[mask], thr), "after": C.fav_ge(Pa[mask], y[mask], thr)}
        # the matches that were >= thr before: what happened to their probability
        sel = mask & (Pb.max(1) >= thr)
        if sel.sum():
            e["same_matches_before_ge_thr"] = {
                "n": int(sel.sum()), "observed": rnd((Pb[sel].argmax(1) == y[sel]).mean(), 4),
                "mean_pred_before": rnd(Pb[sel].max(1).mean(), 4), "mean_pred_after_same_outcome":
                    rnd(Pa[sel][np.arange(sel.sum()), Pb[sel].argmax(1)].mean(), 4)}
        out[f"ge_{thr:.2f}"] = e
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="test stage of the favourite-calibration study")
    ap.add_argument("--split", default="test", help="split to score; anything but 'test' is a mechanics check "
                                                    "(e.g. validation) and needs a different --outdir")
    ap.add_argument("--outdir", type=Path, default=C.DATA)
    args = ap.parse_args(argv)
    if args.split != "test" and Path(args.outdir).resolve() == C.DATA.resolve():
        raise SystemExit("a mechanics check on another split must write to a different --outdir")
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    if not FROZEN.exists():
        raise SystemExit(f"{FROZEN} missing: run calibration_fit.py first (the test is read only after freezing)")
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    chosen = frozen["chosen"]
    if chosen == "identity":
        raise SystemExit("frozen choice is 'identity': no fix to evaluate")
    layer = frozen["goal_layer"]
    fix = frozen["chosen_fit_on_train"]
    fix_refit = frozen["chosen_refit_on_train_plus_validation"]

    d = C.load_baseline()
    te = C.subset(d, d["split"] == args.split)
    P, y, euro = te["p"], te["y"], te["euro"]
    n = te["n"]
    print(f"test rows {n} (UEFA {int(euro.sum())}); fix {chosen}: "
          f"{ {k: v for k, v in fix.items() if k not in ('x', 'y')} }")
    Pa = F.apply_fix(fix, P, te["mu_h"], te["mu_a"], euro, layer)
    Pr = F.apply_fix(fix_refit, P, te["mu_h"], te["mu_a"], euro, layer)
    assert np.allclose(Pa[~euro], P[~euro]) or fix["scope"] != "uefa"
    assert np.allclose(Pa.sum(1), 1.0)

    lookup = C.team_league_lookup()
    fav = P.argmax(1)
    fav_team = np.where(fav == 0, te["home_id"], te["away_id"])
    fav_grp = np.array([C.league_group(lookup(fav_team[i], te["kickoff"][i])) for i in range(n)])
    home_fav_b = P.argmax(1) == 0

    res = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "fix": chosen,
           "test_rows": int(n), "test_uefa": int(euro.sum()), "test_range": [min(te["kickoff"].tolist()), max(te["kickoff"].tolist())],
           "primary_params_train_fit": {k: v for k, v in fix.items() if k not in ("x", "y")},
           "refit_params_train_plus_validation": {k: v for k, v in fix_refit.items() if k not in ("x", "y")}}
    res["metrics_primary"] = metrics(P, Pa, y, euro)
    res["metrics_refit"] = metrics(P, Pr, y, euro)

    # ---- 1X2 shares: before / after (UEFA)
    def shares(Pq, m):
        return {"pred_home": rnd(Pq[m][:, 0].mean(), 4), "pred_draw": rnd(Pq[m][:, 1].mean(), 4),
                "pred_away": rnd(Pq[m][:, 2].mean(), 4), "act_home": rnd((y[m] == 0).mean(), 4),
                "act_draw": rnd((y[m] == 1).mean(), 4), "act_away": rnd((y[m] == 2).mean(), 4)}
    res["shares_uefa"] = {"before": shares(P, euro), "after": shares(Pa, euro)}
    res["shares_league"] = {"before": shares(P, ~euro), "after": shares(Pa, ~euro)}

    # ---- calibration tables before / after
    allm = np.ones(n, bool)
    res["calibration"] = {
        "all": fav_block(P, Pa, y, allm), "league": fav_block(P, Pa, y, ~euro), "uefa": fav_block(P, Pa, y, euro),
        "uefa_home_favourite_before": fav_block(P, Pa, y, euro & home_fav_b),
        "uefa_away_favourite_before": fav_block(P, Pa, y, euro & ~home_fav_b),
        "uefa_premier_league_favourite": fav_block(P, Pa, y, euro & (fav_grp == "Premier League")),
        "uefa_other_favourite": fav_block(P, Pa, y, euro & (fav_grp != "Premier League"))}
    res["favourites_at_least"] = {"all": thresholds(P, Pa, y, allm), "league": thresholds(P, Pa, y, ~euro),
                                  "uefa": thresholds(P, Pa, y, euro)}
    res["uefa_by_competition"] = {}
    for cid, nm in (("42", "Champions League"), ("73", "Europa League"), ("10216", "Conference League")):
        m = euro & (te["comp"] == cid)
        if m.sum():
            res["uefa_by_competition"][nm] = {"n": int(m.sum()),
                                              "logloss": paired_block(C.logloss(P[m], y[m]), C.logloss(Pa[m], y[m])),
                                              "brier": paired_block(C.brier(P[m], y[m]), C.brier(Pa[m], y[m]))}

    # ---- goal markets are not changed by the ratio change (total goals held): check on the UEFA rows
    if fix["kind"] == "ratio_shrink":
        mh2, ma2 = F.ratio_shrink_mu(te["mu_h"][euro], te["mu_a"][euro], fix["k"], fix["h"])
        import train_goal_model as T
        mb = T.markets(T.score_matrix(te["mu_h"][euro], te["mu_a"][euro], layer["rho"], layer["nb_dispersion"]))
        ma = T.markets(T.score_matrix(mh2, ma2, layer["rho"], layer["nb_dispersion"]))
        res["goal_markets_check_uefa"] = {
            "max_abs_change_over25": rnd(np.abs(mb[1] - ma[1]).max(), 6), "mean_abs_change_over25": rnd(np.abs(mb[1] - ma[1]).mean(), 6),
            "max_abs_change_btts": rnd(np.abs(mb[3] - ma[3]).max(), 6), "mean_abs_change_btts": rnd(np.abs(mb[3] - ma[3]).mean(), 6),
            "max_abs_total_change": rnd(np.abs((mh2 + ma2) - (te["mu_h"][euro] + te["mu_a"][euro])).max(), 9)}
        # informational: the other score-model outputs on the UEFA rows if mu' replaced mu everywhere
        sb = T.score_matrix(te["mu_h"][euro], te["mu_a"][euro], layer["rho"], layer["nb_dispersion"])
        sa = T.score_matrix(mh2, ma2, layer["rho"], layer["nb_dispersion"])
        hg, ag = te["hg"][euro], te["ag"][euro]
        tot_g = hg + ag
        ix = np.arange(len(hg))

        def other_losses(sm, mk):
            o25 = np.clip(mk[1], 1e-12, 1 - 1e-12)
            bt = np.clip(mk[3], 1e-12, 1 - 1e-12)
            return {"over25": -np.where(tot_g > 2.5, np.log(o25), np.log(1 - o25)),
                    "btts": -np.where((hg > 0) & (ag > 0), np.log(bt), np.log(1 - bt)),
                    "score": -np.log(np.clip(sm[ix, np.clip(hg, 0, 10), np.clip(ag, 0, 10)], 1e-12, 1.0))}
        lo_b, lo_a = other_losses(sb, mb), other_losses(sa, ma)
        res["goal_markets_check_uefa"]["logloss_if_mu_replaced_everywhere"] = {
            k: paired_block(lo_b[k], lo_a[k]) for k in ("over25", "btts", "score")}
        dp = Pa[euro] - P[euro]
        res["uefa_probability_shift"] = {"mean_home": rnd(dp[:, 0].mean(), 4), "mean_draw": rnd(dp[:, 1].mean(), 4),
                                         "mean_away": rnd(dp[:, 2].mean(), 4),
                                         "max_abs_home": rnd(np.abs(dp[:, 0]).max(), 4)}

    # ---- league matches with closing odds: unchanged by a UEFA-only fix (model vs market, test, before)
    odds = C.load_closing_odds()
    have = np.array([m in odds for m in te["match_id"]]) & ~euro
    if have.any():
        mk = np.array([odds[m] for m in te["match_id"][have]])
        mk = mk / mk.sum(1, keepdims=True)
        res["league_test_closing_market"] = {
            "n": int(have.sum()), "market_logloss": rnd(C.logloss(mk, y[have]).mean()),
            "model_logloss_before": rnd(C.logloss(P[have], y[have]).mean()),
            "model_logloss_after": rnd(C.logloss(Pa[have], y[have]).mean()),
            "model_fav_mean": rnd(P[have].max(1).mean(), 4), "market_same_outcome_mean": rnd(
                mk[np.arange(have.sum()), P[have].argmax(1)].mean(), 4),
            "observed_fav_hit": rnd((P[have].argmax(1) == y[have]).mean(), 4)}
    res["bootstrap"] = {"resamples": C.BOOT_N, "seed": C.BOOT_SEED, "ci": "90 % percentile, paired per-match differences, "
                                                                           "resampled within each subset"}

    # ---- deploy verdict
    scope = fix["scope"]
    mp = res["metrics_primary"]
    targeted = "uefa" if scope == "uefa" else "all"
    rest = "league" if scope == "uefa" else None
    ov = mp["all"]["logloss"]
    tg = mp[targeted]["logloss"]
    ok_overall = ov.get("ci90") is not None and ov["ci90"][1] < 0
    ok_target = tg.get("ci90") is not None and tg["ci90"][1] < 0
    rest_diff = mp[rest]["logloss"]["diff"] if rest else None
    rest_ok = True if rest is None else (rest_diff <= 0)
    if scope != "uefa":  # a global fix must not worsen either subset
        rest_ok = mp["league"]["logloss"]["diff"] <= 0 and mp["uefa"]["logloss"]["diff"] <= 0
    deploy = bool((ok_overall or ok_target) and rest_ok)
    verdict = {"rule": __doc__.split("Deploy rule")[1].split("Usage")[0].strip(),
               "overall_ci_upper_below_0": bool(ok_overall), "targeted_subset": targeted,
               "targeted_ci_upper_below_0": bool(ok_target), "rest_not_worse": bool(rest_ok),
               "rest_diff": rest_diff, "deploy": deploy}
    res["deploy_verdict"] = verdict
    (outdir / "calibration_test_results.json").write_text(json.dumps(res, indent=1), encoding="utf-8")

    # ---- candidate JSON
    h = fix.get("h")
    cand = {
        "name": "uefa_home_advantage_v1" if chosen == "uefa_home_h" else chosen,
        "status": "DRAFT / not deployed. Nothing under backend/app or backend/config was written; the lead decides.",
        "built_at": res["built_at"],
        "question": "Is the production 1X2 model over-confident on favourites (Aston Villa 59 % v Fenerbahce, "
                    "Man City 66 % v PSG)? See docs/training/2026-10-14-favourite-calibration.md.",
        "data": {"predictions": "backend/data/training/baseline_predictions_full.csv.gz (production model, "
                                "out-of-sample, train-only goal layer)",
                 "splits": {"train": "2022-08-01..2025-06-30", "validation": "2025-07-01..2026-01-31",
                            "test": "2026-02-01..2026-10-12"},
                 "n": {"train": frozen["splits_used"]["train"], "train_uefa": frozen["splits_used"]["train_uefa"],
                       "validation": frozen["splits_used"]["validation"],
                       "validation_uefa": frozen["splits_used"]["validation_uefa"],
                       "test": res["test_rows"], "test_uefa": res["test_uefa"]}},
        "applies_to": {
            "matches": "UEFA club competition matches only: competition_provider_id 42 (Champions League), "
                       "73 (Europa League), 10216 (Conference League)",
            "not_evaluated": "qualifying rounds 10611 / 10613 / 10615 (0 rows in the data) and neutral-venue "
                             "matches (finals, Super Cup): do not apply the home term there",
            "league_matches": "unchanged (identity)"} if scope == "uefa" else {"matches": "all"},
        "formula": ("Input: the production expected goals mu_home, mu_away of a UEFA match (after the production "
                    "squad-value and line-up-form shifts) and the production score model (negative binomial "
                    "dispersion r = goal_layer.nb_dispersion, Dixon-Coles rho = goal_layer.rho, scores 0..10).\n"
                    "  d  = ln(mu_home / mu_away)\n  d' = k * d + h            (k = 1: no shrink; h = home-advantage term)\n"
                    "  mu_home' = (mu_home + mu_away) * e^d' / (1 + e^d')\n"
                    "  mu_away' = (mu_home + mu_away) / (1 + e^d')\n"
                    "The expected total goals is unchanged. 1X2 = the production score model evaluated at "
                    "(mu_home', mu_away'). Other markets: use mu' with the same score model (the total is unchanged, "
                    "so O/U and BTTS move only through the score model's goal correlation; see goal_markets_check_uefa)."
                    ) if fix["kind"] == "ratio_shrink" else str(fix),
        "parameters": {"train_fit_TESTED": {k: v for k, v in fix.items() if k not in ("x", "y")},
                       "refit_train_plus_validation": {k: v for k, v in fix_refit.items() if k not in ("x", "y")},
                       "goal_layer": layer},
        "validation_choices": {
            "selection_rule": frozen["selection_rule"], "chosen": chosen,
            "best_by_validation": frozen["best_by_validation"], "tied_within_1se": frozen["tied_with_best_within_1se"],
            "trace": frozen["selection_trace"],
            "candidates_validation": {nm: {"n_params": c["n_params"], "eligible": c["eligible"],
                                           "fit_on_train": c["fit_on_train"],
                                           "validation_logloss_diff": {k: c["validation"][k]["logloss_diff"]
                                                                       for k in ("all", "league", "uefa")}}
                                      for nm, c in frozen["candidates"].items()},
            "diagnostics": frozen["diagnostics_not_used_for_choice"]},
        "test": {"read_once": True, "metrics_train_fit": res["metrics_primary"], "metrics_refit": res["metrics_refit"],
                 "shares_uefa": res["shares_uefa"], "favourites_at_least": res["favourites_at_least"],
                 "calibration": res["calibration"], "goal_markets_check_uefa": res.get("goal_markets_check_uefa"),
                 "uefa_probability_shift": res.get("uefa_probability_shift")},
        "deploy_criteria": verdict,
        "recommendation": None,
    }
    if deploy:
        cand["recommendation"] = ("DEPLOY for UEFA matches (ids 42 / 73 / 10216) only, with the train-fitted h "
                                  f"= {h:.4f} (or the train + validation refit h = {fix_refit.get('h'):.4f}). The test "
                                  "criterion is met, but NOTE THE DIRECTION: the term raises the home side in UEFA matches "
                                  "(the model under-rates UEFA home teams); it does not lower favourites.")
    else:
        u = mp["uefa"]["logloss"]
        o = mp["all"]["logloss"]
        cand["recommendation"] = (
            "DO NOT DEPLOY. The pre-declared test criterion is not met: 1X2 log loss change (after - before) "
            f"UEFA {u['diff']:+.5f} (90 % CI {u['ci90'][0]:+.5f} .. {u['ci90'][1]:+.5f}, n = {u['n']}), "
            f"overall {o['diff']:+.5f} (90 % CI {o['ci90'][0]:+.5f} .. {o['ci90'][1]:+.5f}); neither upper bound is below 0. "
            "The fix that validation chose (a UEFA home-advantage term, which RAISES the home side) did not hold "
            "out of sample. No fix that lowers favourite probabilities was supported at any stage: the diagnosis on "
            "train + validation found no over-confidence on favourites (league favourites win more often than "
            "predicted, slope > 1; UEFA slope ~ 1), the UEFA ratio shrink was rejected on validation, and flattening "
            "the 1X2 (T > 1) worsens train and validation log loss.")
    try:
        dg = json.loads((C.DATA / "calibration_diagnosis.json").read_text(encoding="utf-8"))
        cand["diagnosis_summary_train_plus_validation"] = {
            "file": "backend/data/training/calibration_diagnosis.json",
            "league_calibration_slope": dg["league"]["calibration_fit"], "uefa_calibration_slope": dg["uefa"]["calibration_fit"],
            "league_fav_ge_0.70": dg["league"]["fav_ge_0.70"], "uefa_fav_ge_0.70": dg["uefa"]["fav_ge_0.70"],
            "uefa_premier_league_favourite_ge_0.60": dg["uefa_favourite_pl_vs_non_pl_ge_0.6"]["Premier League favourite"],
            "uefa_other_favourite_ge_0.60": dg["uefa_favourite_pl_vs_non_pl_ge_0.6"]["other favourite"],
            "league_with_closing_odds": {k: dg["league_matches_with_closing_odds"][k] for k in
                                         ("n", "model_calibration_fit", "market_calibration_fit")}}
    except (OSError, KeyError, ValueError):
        pass
    (outdir / "calibration_candidate.json").write_text(json.dumps(cand, indent=1), encoding="utf-8")

    # ---- print
    def line(lab, b):
        ci = b.get("ci90")
        return (f"{lab:<22} n={b['n']:>5} before {b['before']:.5f} after {b['after']:.5f} "
                f"diff {b['diff']:+.5f} " + (f"({ci[0]:+.5f}, {ci[1]:+.5f})" if ci else ""))
    for nm in ("all", "league", "uefa"):
        print(line(f"1X2 log loss {nm}", {**mp[nm]["logloss"], "n": mp[nm]["n"]}))
    for nm in ("all", "league", "uefa"):
        print(line(f"1X2 Brier    {nm}", {**mp[nm]["brier"], "n": mp[nm]["n"]}))
    print("refit params:")
    for nm in ("all", "league", "uefa"):
        print(line(f"1X2 log loss {nm}", {**res["metrics_refit"][nm]["logloss"], "n": mp[nm]["n"]}))
    print("shares UEFA:", res["shares_uefa"])
    print("goal markets check:", res.get("goal_markets_check_uefa"))
    print("verdict:", {k: v for k, v in verdict.items() if k != "rule"})
    for seg in ("all", "uefa"):
        print(f"\nfavourites at least ({seg}):")
        for k, v in res["favourites_at_least"][seg].items():
            print(" ", k, "before", v["before"], "after", v["after"])
    for seg in ("uefa", "uefa_premier_league_favourite"):
        print(f"\ncalibration {seg} before / after")
        for b, a in zip(res["calibration"][seg]["before"], res["calibration"][seg]["after"]):
            print("  ", b, "|", a)
    print(f"\n-> {outdir / 'calibration_test_results.json'}, {outdir / 'calibration_candidate.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
