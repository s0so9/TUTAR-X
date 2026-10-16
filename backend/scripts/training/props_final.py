"""Props models: one-shot TEST evaluation of the frozen configuration + export (props:train, 2026-10-14).

Reads data/training/props_frozen.json (written by props_select.py from the validation split only) and then
  1. walk-forward predictions of every stat over the test split 2026-02-01..2026-10-12 (refit every 14 days, each fit
     uses only matches that kicked off >= 3 h before the fit date; hyper-parameters and NB sizes frozen on validation),
  2. the baselines (last-5, last-10, 365-day average, competition average) on the same rows, defined on the same
     "primary set" (both teams >= 5 matches with the stat in the previous 365 days, competition >= 30 matches),
  3. log loss of every O/U line, MAE, paired bootstrap (2,000 resamples of matches, seed 7, 90 % interval),
     calibration, confidence bands / "banko-like" counts, league vs European, referee effect, team-effect value,
  4. the deployment fit on ALL matches, export data/training/props_model_candidate.json, the check reference
     data/training/props_check_reference.json, props_model_report.json and props_predictions_test.csv.gz.

Usage (from backend/):
  venv/Scripts/python.exe scripts/training/props_final.py
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np

TRAINING_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TRAINING_DIR))
import props_model as PM  # noqa: E402
import props_select as PS  # noqa: E402

DATA = PM.DATA
TEST_START, TEST_END = "2026-02-01", "2026-10-13"  # end exclusive (last test kick-off day is 2026-10-12)
BOOT_N, BOOT_SEED = 2000, 7
MU_FLOOR = 0.05  # baseline means are floored here (a mean of exactly 0 has no NB likelihood); count reported
BANKO_THRESHOLDS = (0.80, 0.85)
CONF_EDGES = [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 1.0 + 1e-9]
MODEL_VERSION = "props_v1"
FORMULA = (
    "For a stat S with exported block B: mu_home = exp(B.intercept + B.competitions.get(competition_id, 0) + "
    "B.home_advantage + B.teams[home].attack + B.teams[away].concede + referee_offset); "
    "mu_away = exp(B.intercept + B.competitions.get(competition_id, 0) + B.teams[away].attack + B.teams[home].concede + "
    "referee_offset); referee_offset = B.referees.get(referee, {offset: 0}).offset (only stats whose referees block is "
    "not empty; 0 for an unknown or missing referee); an unknown team contributes 0 for attack and concede. "
    "Each side is NegativeBinomial with mean mu and size B.dispersion r (variance mu + mu^2 / r), P(X > line) = "
    "1 - P(X <= floor(line)). Team markets use one side. Total markets: if B.total_dispersion is null, the total is the "
    "exact convolution of the two NB sides (independence); otherwise the total is NB with mean mu_home + mu_away and "
    "size B.total_dispersion (this captures the home/away correlation of the counts). "
    "Team 'attack' / 'concede' already contain the dominance block (attack = A + S, concede = D - S). "
    "'competitions' is the competition level of the CURRENT season (the model keeps a random-walk level per "
    "competition and season when level mode is on, see hyperparameters.use_level). "
    "team_recent holds plain averages of the last 5 matches (for UI display only, not model inputs)."
)


def wilson(k: int, n: int, z: float = 1.6448536269514722) -> list:
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def r6(x, nd: int = 5):
    return None if x is None else round(float(x), nd)


# ---------------------------------------------------------------------------------------------- predictions
def make_cfg(d: dict) -> PM.Config:
    return PM.Config(**d)


def design_for(ds, stat: str, cfg: PM.Config) -> PM.Design:
    return PM.build_design(ds, stat, level=cfg.use_level, ref=cfg.use_ref, attack=cfg.use_attack,
                           concede=cfg.use_concede, dom=cfg.use_dom)


def run_wf(ds, stat: str, cfg: PM.Config, start: str, end: str) -> PM.WalkForward:
    return PM.walk_forward(ds, design_for(ds, stat, cfg), cfg, ds.day(start), ds.day(end), PS.STEP_DAYS)


def calibrate(ds, stat: str, cfg: PM.Config) -> dict:
    """Out-of-sample NB sizes of a configuration on the validation split (variants that were not selected)."""
    wf = run_wf(ds, stat, cfg, PS.VAL_START, PS.VAL_END)
    yh, ya = ds.y[stat][wf.rows, 0], ds.y[stat][wf.rows, 1]
    return {"r": PM.fit_dispersion(yh, ya, wf.mu_h, wf.mu_a), "r_total": PM.fit_total_dispersion(yh, ya, wf.mu_h, wf.mu_a)}


# ---------------------------------------------------------------------------------------------- evaluation helpers
def calib_table(p: np.ndarray, over: np.ndarray, bins: int = 10) -> dict:
    p, over = p.ravel(), over.ravel()
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    rows, ece = [], 0.0
    for b in range(bins):
        m = idx == b
        n = int(m.sum())
        if n:
            mp, orate = float(p[m].mean()), float(over[m].mean())
            ece += n / len(p) * abs(mp - orate)
        else:
            mp = orate = None
        rows.append({"lo": round(edges[b], 2), "hi": round(edges[b + 1], 2), "n": n, "mean_p": r6(mp), "observed": r6(orate)})
    return {"bins": rows, "ece": round(ece, 5), "n": int(len(p))}


def confidence_table(p: np.ndarray, over: np.ndarray) -> list:
    """Bands of the confidence of the predicted side q = max(p, 1 - p); hit = the predicted side happened."""
    p, over = p.ravel(), over.ravel()
    q = np.maximum(p, 1 - p)
    hit = np.where(p >= 0.5, over, ~over)
    out = []
    for lo, hi in zip(CONF_EDGES[:-1], CONF_EDGES[1:]):
        m = (q >= lo) & (q < hi)
        n = int(m.sum())
        out.append({"band": f"{lo:.2f}-{min(hi, 1.0):.2f}", "n": n, "hits": int(hit[m].sum()),
                    "hit_rate": r6(hit[m].mean()) if n else None, "mean_confidence": r6(q[m].mean()) if n else None,
                    "hit_ci90": wilson(int(hit[m].sum()), n)})
    return out


def banko_counts(me: PM.MarketEval, lines: list[float]) -> dict:
    """>= 0.80 / >= 0.85: how often the predicted side landed (per line, per side, and all lines together)."""
    p, over = me.p, me.over
    q = np.maximum(p, 1 - p)
    hit = np.where(p >= 0.5, over, ~over)
    res = {}
    for thr in BANKO_THRESHOLDS:
        m = q >= thr
        per_line = []
        for j, L in enumerate(lines):
            mj = m[:, j]
            n = int(mj.sum())
            n_over = int((mj & (p[:, j] >= 0.5)).sum())
            per_line.append({"line": L, "n": n, "hits": int(hit[mj, j].sum()), "n_over_calls": n_over,
                             "n_under_calls": n - n_over,
                             "hit_rate": r6(hit[mj, j].mean()) if n else None,
                             "mean_confidence": r6(q[mj, j].mean()) if n else None})
        n = int(m.sum())
        mids = np.unique(me.match_idx[np.any(m, axis=1)])
        res[f"{thr:.2f}"] = {"n": n, "hits": int(hit[m].sum()), "hit_rate": r6(hit[m].mean()) if n else None,
                             "hit_ci90": wilson(int(hit[m].sum()), n), "mean_confidence": r6(q[m].mean()) if n else None,
                             "n_matches_with_a_call": int(len(mids)), "per_line": per_line}
    return res


def boot(diff: np.ndarray) -> dict:
    if len(diff) < 5:
        return {"mean": None, "ci90": [None, None], "n": int(len(diff))}
    m, lo, hi = PM.paired_bootstrap(diff, BOOT_N, BOOT_SEED, 0.90)
    return {"mean": round(m, 5), "ci90": [round(lo, 5), round(hi, 5)], "n": int(len(diff))}


def pool_banko(banko_by_market: dict, thr: str) -> dict:
    n = sum(b[thr]["n"] for b in banko_by_market.values())
    h = sum(b[thr]["hits"] for b in banko_by_market.values())
    return {"n": n, "hits": h, "hit_rate": r6(h / n) if n else None, "hit_ci90": wilson(h, n)}


# ---------------------------------------------------------------------------------------------- main evaluation
def evaluate_stat(ds, stat: str, frozen_stat: dict, bl_disp: dict, wfs: dict, bl: PM.Baselines, log) -> dict:
    """wfs: method name -> WalkForward on the test rows (same rows for all). Returns the report block of one stat."""
    rows = wfs["model"].rows
    assert all(np.array_equal(w.rows, rows) for w in wfs.values())
    yh, ya = ds.y[stat][rows, 0], ds.y[stat][rows, 1]
    elig = bl.eligible()[rows]
    sel = np.flatnonzero(elig)
    is_euro = np.isin(ds.comp[rows], list(PM.EUROPEAN))
    methods: dict[str, dict] = {}
    floored = 0
    use_rt = frozen_stat["use_total_dispersion"]
    for name, w in wfs.items():
        r = frozen_stat["validation"]["r"] if name == "model" else w.r_cal["r"]
        rt = (frozen_stat["validation"]["r_total"] if name == "model" else w.r_cal["r_total"]) if use_rt else None
        methods[name] = {"mu_h": w.mu_h, "mu_a": w.mu_a, "r": r, "r_total": rt}
    for name in PM.BASELINE_NAMES:
        a, b = bl.means(name)
        mh, ma = a[rows], b[rows]
        floored += int(((mh[sel] < MU_FLOOR) | (ma[sel] < MU_FLOOR)).sum())
        methods[name] = {"mu_h": np.maximum(mh, MU_FLOOR), "mu_a": np.maximum(ma, MU_FLOOR),
                         "r": bl_disp[name], "r_total": None}
    block = {"n_test_rows": int(len(rows)), "n_primary": int(len(sel)), "n_european_primary": int(is_euro[sel].sum()),
             "baseline_mu_floored_rows": floored, "methods_r": {k: r6(v["r"], 3) for k, v in methods.items()},
             "model_r_total": r6(methods["model"]["r_total"], 3), "markets": {}, "stat_level": {}}
    # stat-level errors of the expected counts and NB log likelihood (primary set)
    stat_level = {}
    nll_match = {}
    for name, m in methods.items():
        tot_pred = m["mu_h"] + m["mu_a"]
        mae_team_match = (np.abs(yh - m["mu_h"]) + np.abs(ya - m["mu_a"])) / 2
        mae_total_match = np.abs((yh + ya) - tot_pred)
        nll = -(PM.nb_loglik(yh, m["mu_h"], m["r"]) + PM.nb_loglik(ya, m["mu_a"], m["r"])) / 2
        nll_match[name] = nll
        stat_level[name] = {"mae_team": r6(mae_team_match[sel].mean(), 4), "mae_total": r6(mae_total_match[sel].mean(), 4),
                            "nll_team": r6(nll[sel].mean(), 4), "_mae_team_match": mae_team_match,
                            "_mae_total_match": mae_total_match}
    out_stat = {}
    for name in methods:
        s = {k: v for k, v in stat_level[name].items() if not k.startswith("_")}
        if name != "model":
            s["mae_team_diff_model_minus_this"] = boot(stat_level["model"]["_mae_team_match"][sel] - stat_level[name]["_mae_team_match"][sel])
            s["mae_total_diff_model_minus_this"] = boot(stat_level["model"]["_mae_total_match"][sel] - stat_level[name]["_mae_total_match"][sel])
            s["nll_team_diff_model_minus_this"] = boot(nll_match["model"][sel] - nll_match[name][sel])
        out_stat[name] = s
    block["stat_level"] = out_stat
    # markets
    all_markets = {k: v for k, v in {**PM.MARKETS, **PM.EXTRA_MARKETS}.items() if v[0] == stat}
    for mk, (_, kind, lines) in all_markets.items():
        is_extra = mk in PM.EXTRA_MARKETS
        evals, mloss = {}, {}
        for name, m in methods.items():
            me = PM.market_eval(m["mu_h"][sel], m["mu_a"][sel], m["r"], yh[sel], ya[sel], kind, lines, m["r_total"])
            evals[name] = me
            mloss[name] = PM.match_loss(me)
        d = {"stat": stat, "kind": kind, "lines": lines, "n_matches": int(len(sel)), "extra_line_set": is_extra,
             "log_loss": {n: r6(mloss[n].mean(), 5) for n in methods},
             "log_loss_per_line": {n: [r6(x, 4) for x in evals[n].loss.mean(axis=0)] for n in methods},
             "base_rate_over": [r6(x, 4) for x in evals["model"].over.mean(axis=0)],
             "mean_p_over_model": [r6(x, 4) for x in evals["model"].p.mean(axis=0)]}
        d["diff_model_minus"] = {n: boot(mloss["model"] - mloss[n]) for n in methods if n != "model"}
        # league vs european (primary set)
        eu = is_euro[sel]
        d["league_vs_european"] = {}
        for label, msk in (("league", ~eu), ("european", eu)):
            if msk.sum() == 0:
                continue
            entry = {"n_matches": int(msk.sum()),
                     "log_loss": {n: r6(mloss[n][msk].mean(), 5) for n in ("model", "last5", "avg365", "comp")}}
            entry["diff_model_minus_last5"] = boot(mloss["model"][msk] - mloss["last5"][msk])
            entry["diff_model_minus_comp"] = boot(mloss["model"][msk] - mloss["comp"][msk])
            d["league_vs_european"][label] = entry
        # calibration + confidence bands + banko-like counts
        d["calibration_model"] = calib_table(evals["model"].p, evals["model"].over)
        d["calibration_last5"] = calib_table(evals["last5"].p, evals["last5"].over)
        d["confidence_bands"] = {n: confidence_table(evals[n].p, evals[n].over) for n in ("model", "last5", "avg365")}
        d["banko_like"] = {n: banko_counts(evals[n], lines) for n in ("model", "last5", "avg365")}
        block["markets"][mk] = d
    return block


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frozen", default=str(DATA / "props_frozen.json"))
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    t0 = time.time()

    def log(msg: str) -> None:
        print(f"[{time.time() - t0:6.0f}s] {msg}", flush=True)

    ds = PM.load_dataset()
    with open(args.frozen, encoding="utf-8") as f:
        frozen = json.load(f)
    stats = [s for s in PM.STATS if s in frozen["stats"] and (not args.only or s in args.only.split(","))]
    report: dict = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "test_period": [TEST_START, "2026-10-12"],
                    "frozen_file": os.path.basename(args.frozen), "stats": {}, "dataset": ds.excluded}
    T0, T1 = ds.day(TEST_START), ds.day(TEST_END)
    pred_rows = []
    deploy: dict = {}
    for stat in stats:
        fs = frozen["stats"][stat]
        cfg = make_cfg(fs["config"])
        log(f"[{stat}] frozen {PS.short(cfg)}")
        # determinism check: recompute the validation score of the frozen config
        wf_val = run_wf(ds, stat, cfg, PS.VAL_START, PS.VAL_END)
        val_score = PS.score_predictions(ds, stat, wf_val)
        assert abs(val_score["score"] - fs["validation"]["score"]) < 1e-7, (stat, val_score["score"], fs["validation"]["score"])
        wfs = {"model": run_wf(ds, stat, cfg, TEST_START, TEST_END)}
        wfs["model"].r_cal = {"r": fs["validation"]["r"], "r_total": fs["validation"]["r_total"]}
        # reference models for the report (same half-life, shrinkage; calibrated on validation only)
        variants = {"model_noteam": PM.Config(**{**asdict(cfg), "use_attack": False, "use_concede": False, "use_dom": False,
                                                 "half_life": cfg.half_life})}
        if cfg.use_ref:
            variants["model_noref"] = PM.Config(**{**asdict(cfg), "use_ref": False})
        for vname, vcfg in variants.items():
            w = run_wf(ds, stat, vcfg, TEST_START, TEST_END)
            w.r_cal = calibrate(ds, stat, vcfg)
            wfs[vname] = w
        bl = PM.compute_baselines(ds, stat)
        block = evaluate_stat(ds, stat, fs, fs["baseline_dispersion_validation"], wfs, bl, log)
        block["frozen_config"] = fs["config"]
        block["validation"] = fs["validation"]
        block["n_fits_test"] = wfs["model"].n_fits
        block["nonconverged_fits_test"] = wfs["model"].nonconverged
        block["variants_validation_dispersion"] = {k: {"r": r6(w.r_cal["r"], 3), "r_total": r6(w.r_cal["r_total"], 3)} for k, w in wfs.items() if k != "model"}
        report["stats"][stat] = block
        mdl = block["markets"]
        for mk, d in mdl.items():
            if d["extra_line_set"]:
                continue
            ll = d["log_loss"]
            df = d["diff_model_minus"]
            log(f"  {mk:<24} model {ll['model']:.4f} last5 {ll['last5']:.4f} ({df['last5']['mean']:+.4f} {df['last5']['ci90']}) "
                f"avg365 {ll['avg365']:.4f} comp {ll['comp']:.4f} ({df['comp']['mean']:+.4f} {df['comp']['ci90']})")
        # predictions file rows
        w = wfs["model"]
        for i, row in enumerate(w.rows):
            pred_rows.append([ds.match_id[row], stat, int(ds.comp[row]), int(ds.home_id[row]), int(ds.away_id[row]),
                              round(float(w.mu_h[i]), 6), round(float(w.mu_a[i]), 6), ds.y[stat][row, 0], ds.y[stat][row, 1],
                              int(bl.eligible()[row])] + [round(float(x[row]), 6) if not np.isnan(x[row]) else "" for nm in PM.BASELINE_NAMES for x in bl.means(nm)])
        # deployment: OOS dispersions from validation + test walk-forward predictions of the frozen config
        rows_all = np.concatenate([wf_val.rows, w.rows])
        mu_h_all = np.concatenate([wf_val.mu_h, w.mu_h])
        mu_a_all = np.concatenate([wf_val.mu_a, w.mu_a])
        yh_all, ya_all = ds.y[stat][rows_all, 0], ds.y[stat][rows_all, 1]
        deploy[stat] = {"r": PM.fit_dispersion(yh_all, ya_all, mu_h_all, mu_a_all),
                        "r_total": PM.fit_total_dispersion(yh_all, ya_all, mu_h_all, mu_a_all)}
    write_outputs(ds, frozen, report, pred_rows, deploy, stats, log)
    log("done")


# ---------------------------------------------------------------------------------------------- export
def deployment_fit(ds, stat: str, cfg: PM.Config, t_fit: float):
    des = design_for(ds, stat, cfg)
    n = len(des.rows)
    w = PM.decay_weights(des.t_obs, t_fit, cfg.half_life)
    P = PM.penalty_matrix(des, cfg)
    fit = PM.fit_nb(des, n, w, P, maxiter=2000)
    return des, fit


def effects_from_fit(ds, des: PM.Design, fit: PM.Fit, cfg: PM.Config) -> dict:
    th = fit.theta
    sl = des.sl
    nT = len(ds.team_ids)
    A = th[sl["A"]] if des.use_attack else np.zeros(nT)
    D = th[sl["D"]] if des.use_concede else np.zeros(nT)
    S = th[sl["S"]] if des.use_dom else np.zeros(nT)
    Lv = th[sl["L"]]
    if des.level_mode:
        latest: dict[int, tuple[int, int]] = {}
        for i, (c, k) in enumerate(ds.level_keys):
            if c not in latest or k > latest[c][0]:
                latest[c] = (k, i)
        comps = {int(c): float(Lv[i]) for c, (k, i) in latest.items()}
    else:
        comps = {int(c): float(Lv[i]) for i, c in enumerate(ds.comp_ids)}
    R = th[sl["R"]] if des.use_ref else np.zeros(0)
    return {"b0": float(th[0]), "h": float(th[1]), "comps": comps, "attack": A + S, "concede": D - S, "ref": R}


def team_recent(ds, stat: str) -> dict:
    """Plain last-5 averages (for / against) of each team from the valid matches of the dataset."""
    out: dict[int, dict] = {}
    vr = np.flatnonzero(ds.valid[stat])
    hist: dict[int, list] = {}
    for r in vr:
        hist.setdefault(int(ds.home_id[r]), []).append((ds.t[r], ds.y[stat][r, 0], ds.y[stat][r, 1]))
        hist.setdefault(int(ds.away_id[r]), []).append((ds.t[r], ds.y[stat][r, 1], ds.y[stat][r, 0]))
    for team, lst in hist.items():
        lst.sort()
        last = lst[-5:]
        out[team] = {"for_last5": round(float(np.mean([x[1] for x in last])), 4),
                     "against_last5": round(float(np.mean([x[2] for x in last])), 4), "n": len(last)}
    return out


def py_round(x: float, nd: int = 8) -> float:
    return round(float(x), nd)


def build_candidate(ds, frozen: dict, report: dict, deploy: dict, stats: list, log) -> tuple[dict, dict]:
    last_kick = str(ds.kick[-1]) + "Z"
    t_fit = float(ds.t[-1]) + 1.0
    cand: dict = {"version": MODEL_VERSION, "trained_through": last_kick,
                  "fitted_on": "train + validation + test = ALL matches 2022-08-01 .. " + last_kick[:10]
                               + " (deployment fit; the evaluation in 'evaluation' used only matches before each kick-off)",
                  "formula": FORMULA, "stats": {}, "team_recent": {}, "lines": {k: v[2] for k, v in PM.MARKETS.items()}}
    internal: dict = {}
    for stat in stats:
        fs = frozen["stats"][stat]
        cfg = make_cfg(fs["config"])
        des, fit = deployment_fit(ds, stat, cfg, t_fit)
        eff = effects_from_fit(ds, des, fit, cfg)
        log(f"[{stat}] deployment fit: {fit.iters} iterations, converged {fit.converged}, nll {fit.nll:.1f}, r_in_sample {fit.r:.2f}")
        rows = des.rows
        n_team: dict[int, int] = {}
        last: dict[int, np.datetime64] = {}
        for r in rows:
            for tid in (int(ds.home_id[r]), int(ds.away_id[r])):
                n_team[tid] = n_team.get(tid, 0) + 1
                if tid not in last or ds.kick[r] > last[tid]:
                    last[tid] = ds.kick[r]
        tidx = {int(t): i for i, t in enumerate(ds.team_ids)}
        teams = {str(t): {"attack": py_round(eff["attack"][tidx[t]]), "concede": py_round(eff["concede"][tidx[t]]),
                          "matches": n_team[t], "last_match": str(last[t])[:10]} for t in sorted(n_team)}
        referees = {}
        if des.use_ref:
            cnt: dict[int, int] = {}
            for r in rows:
                if ds.ref_idx[r] >= 0:
                    cnt[int(ds.ref_idx[r])] = cnt.get(int(ds.ref_idx[r]), 0) + 1
            referees = {ds.ref_names[i]: {"offset": py_round(eff["ref"][i]), "matches": cnt[i]} for i in sorted(cnt)}
        comp_counts = {int(c): int((ds.comp[rows] == c).sum()) for c in ds.comp_ids}
        block = {"distribution": "negbin", "dispersion": py_round(deploy[stat]["r"], 6),
                 "total_dispersion": (py_round(deploy[stat]["r_total"], 6) if fs["use_total_dispersion"] else None),
                 "intercept": py_round(eff["b0"]), "home_advantage": py_round(eff["h"]),
                 "competitions": {str(c): py_round(v) for c, v in sorted(eff["comps"].items()) if comp_counts.get(c, 0) > 0},
                 "teams": teams, "referees": referees,
                 "hyperparameters": {**fs["config"], "half_life_days": fs["config"]["half_life"],
                                     "dispersion_source": "out-of-sample maximum likelihood on validation + test walk-forward predictions (not the in-sample fit)",
                                     "in_sample_dispersion": py_round(fit.r, 4), "fit_date_days": t_fit,
                                     "n_matches_fitted": int(len(rows))}}
        cand["stats"][stat] = block
        internal[stat] = {"des": des, "fit": fit, "eff": eff, "block": block}
    # team_recent
    tr: dict[str, dict] = {}
    for stat in stats:
        for team, v in team_recent(ds, stat).items():
            tr.setdefault(str(team), {})[stat] = v
    cand["team_recent"] = tr
    return cand, internal


def write_outputs(ds, frozen: dict, report: dict, pred_rows: list, deploy: dict, stats: list, log) -> None:
    cand, internal = build_candidate(ds, frozen, report, deploy, stats, log)
    # compact evaluation block
    ev: dict = {"test_period": report["test_period"], "primary_set": (
        "test matches where both teams have >= 5 matches with the stat in the previous 365 days and the competition has "
        ">= 30 matches in the previous 365 days (the set on which last-5 / last-10 / 365-day-average / competition-average "
        "baselines are defined); all methods are scored on exactly these matches"),
        "bootstrap": {"resamples": BOOT_N, "seed": BOOT_SEED, "interval": "90 %", "unit": "match (paired)"},
        "validation_choices": {s: {"config": frozen["stats"][s]["config"], "score": r6(frozen["stats"][s]["validation"]["score"], 5),
                                   "mae": r6(frozen["stats"][s]["validation"]["mae"], 4),
                                   "use_total_dispersion": frozen["stats"][s]["use_total_dispersion"],
                                   "n_configs_evaluated": frozen["stats"][s]["n_configs_evaluated"]} for s in stats},
        "dataset_exclusions": ds.excluded, "markets": {}, "banko_like_pooled_main_markets": {}}
    bk_all = {"model": {}, "last5": {}, "avg365": {}}
    for stat in stats:
        blk = report["stats"][stat]
        for mk, d in blk["markets"].items():
            if d["extra_line_set"]:
                continue
            ev["markets"][mk] = {"n_matches": d["n_matches"], "log_loss": d["log_loss"],
                                 "diff_model_minus": d["diff_model_minus"],
                                 "league_vs_european": d["league_vs_european"]}
        ev.setdefault("stat_level", {})[stat] = blk["stat_level"]
    for n in bk_all:
        for thr in ("0.80", "0.85"):
            by = {mk: report["stats"][PM.MARKETS[mk][0]]["markets"][mk]["banko_like"][n] for mk in PM.MARKETS if PM.MARKETS[mk][0] in stats}
            ev["banko_like_pooled_main_markets"].setdefault(n, {})[thr] = pool_banko(by, thr)
    cand["evaluation"] = ev
    cov = json.load(open(DATA / "props_dataset_report.json", encoding="utf-8"))
    cand["evaluation"]["coverage"] = {"total": cov["coverage_total"], "missing_total": cov["stat_missing_total"],
                                      "by_competition": cov["coverage_by_competition"], "referee_read_status": cov["referee_read_status"]}
    # the check reference: 200 random test matches, probabilities from the vectorised library code
    T0 = ds.day(TEST_START)
    test_rows = np.flatnonzero(ds.t >= T0)
    rng = np.random.default_rng(7)
    pick = np.sort(rng.choice(test_rows, size=min(200, len(test_rows)), replace=False))
    ref: dict = {"description": "props_v1 check reference: mean and over-probabilities computed by the training code (design-matrix path, unrounded parameters) for 200 random test matches with the DEPLOYMENT fit. props_check_runtime_formula.py recomputes them from props_model_candidate.json with the documented formula.",
                 "seed": 7, "matches": []}
    for r in pick:
        entry = {"match_id": ds.match_id[r], "kickoff": str(ds.kick[r]) + "Z", "competition_id": int(ds.comp[r]),
                 "home_team_id": int(ds.home_id[r]), "away_team_id": int(ds.away_id[r]), "referee": str(ds.referee[r]),
                 "mu": {}, "probs": {}}
        ref["matches"].append(entry)
    for stat in stats:
        it = internal[stat]
        des, fit = it["des"], it["fit"]
        # design rows exist only for valid matches; build a design for the picked matches instead of reusing it
        Xp = predict_design(ds, des, pick, latest_level=True)
        eta = Xp @ fit.theta
        mu = np.exp(eta)
        mu_h, mu_a = mu[0::2], mu[1::2]
        for i, e in enumerate(ref["matches"]):
            e["mu"][stat] = [float(mu_h[i]), float(mu_a[i])]
        r = deploy[stat]["r"]
        rt = deploy[stat]["r_total"] if frozen["stats"][stat]["use_total_dispersion"] else None
        for mk, (st, kind, lines) in PM.MARKETS.items():
            if st != stat:
                continue
            p = PM.over_probs(mu_h, mu_a, r, kind, lines, rt)
            for i, e in enumerate(ref["matches"]):
                e["probs"][mk] = ([p[i, 0, :].tolist(), p[i, 1, :].tolist()] if kind == "team" else p[i].tolist())
    with open(DATA / "props_check_reference.json", "w", encoding="utf-8") as f:
        json.dump(ref, f)
    with open(DATA / "props_model_candidate.json", "w", encoding="utf-8") as f:
        json.dump(cand, f, ensure_ascii=False, allow_nan=False)
    with open(DATA / "props_model_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1, ensure_ascii=False, allow_nan=False)
    with gzip.open(DATA / "props_predictions_test.csv.gz", "wt", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["match_id", "stat", "competition_id", "home_team_id", "away_team_id", "mu_home", "mu_away", "y_home", "y_away",
                    "primary_set"] + [f"{nm}_{side}" for nm in PM.BASELINE_NAMES for side in ("mu_home", "mu_away")])
        w.writerows(pred_rows)
    log("wrote props_model_candidate.json, props_check_reference.json, props_model_report.json, props_predictions_test.csv.gz")


def predict_design(ds, des: PM.Design, rows: np.ndarray, latest_level: bool = False):
    """Design matrix (2 rows per match: home side, away side) for ARBITRARY dataset rows with the structure of `des`.
    latest_level: in level mode use the competition level of the LATEST season for every row (what the exported
    'competitions' block holds, i.e. the runtime rule), not the level of the row's own season."""
    from scipy import sparse
    m = len(rows)
    sl = des.sl
    hr, ar = 2 * np.arange(m), 2 * np.arange(m) + 1
    rws, cols, vals = [], [], []

    def add(rr, cc, vv=None):
        rws.append(rr)
        cols.append(cc)
        vals.append(np.ones(len(rr)) if vv is None else vv)

    add(np.arange(2 * m), np.zeros(2 * m, dtype=int))
    add(hr, np.full(m, 1))
    lev = (ds.level_idx if des.level_mode else ds.comp_idx)[rows]
    if latest_level and des.level_mode:
        latest: dict[int, tuple[int, int]] = {}
        for i, (c, k) in enumerate(ds.level_keys):
            if c not in latest or k > latest[c][0]:
                latest[c] = (k, i)
        lev = np.array([latest[int(c)][1] for c in ds.comp[rows]], dtype=int)
    add(hr, sl["L"].start + lev)
    add(ar, sl["L"].start + lev)
    if des.use_attack:
        add(hr, sl["A"].start + ds.home_idx[rows])
        add(ar, sl["A"].start + ds.away_idx[rows])
    if des.use_concede:
        add(hr, sl["D"].start + ds.away_idx[rows])
        add(ar, sl["D"].start + ds.home_idx[rows])
    if des.use_ref:
        rf = ds.ref_idx[rows]
        has = rf >= 0
        add(hr[has], sl["R"].start + rf[has])
        add(ar[has], sl["R"].start + rf[has])
    if des.use_dom:
        add(hr, sl["S"].start + ds.home_idx[rows])
        add(hr, sl["S"].start + ds.away_idx[rows], -np.ones(m))
        add(ar, sl["S"].start + ds.away_idx[rows])
        add(ar, sl["S"].start + ds.home_idx[rows], -np.ones(m))
    return sparse.csr_matrix((np.concatenate(vals), (np.concatenate(rws), np.concatenate(cols))), shape=(2 * m, des.p))


if __name__ == "__main__":
    main()
