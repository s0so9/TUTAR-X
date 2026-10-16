"""Props models: hyper-parameter selection on the VALIDATION split only (props:train, 2026-10-14).

Splits: train 2022-08-01..2025-06-30, validation 2025-07-01..2026-01-31, test 2026-02-01..2026-10-12 (never read here:
walk-forward fits only use matches that kicked off before the fit date, and predictions are made for validation rows).

For every stat a greedy search (score = mean over the stat's O/U markets of the log loss of walk-forward predictions,
refit every 14 days; the NB size is the out-of-sample maximum-likelihood size of the same predictions):
  1. grid half-life x ridge on team effects
  2. keep an extra effect only if it lowers the validation score by >= MIN_GAIN: dominance block, competition-season
     level (random walk), concede / attack effect on-off + ratio, referee effect (cards, fouls)
  3. local refinement of half-life / ridge, 4. decision on the NB-total dispersion (r_total) for total markets.
Writes data/training/props_frozen.json (the frozen configuration, trace and the validation-fitted dispersions of the
model and of the baselines).

Usage (from backend/):
  venv/Scripts/python.exe scripts/training/props_select.py [--workers 6] [--stats yellow_cards,corners,...]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import numpy as np

TRAINING_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TRAINING_DIR))
import props_model as PM  # noqa: E402

OUT = PM.DATA / "props_frozen.json"
TRAIN_START, VAL_START, VAL_END = "2022-08-01", "2025-07-01", "2026-02-01"  # VAL_END exclusive
STEP_DAYS = 14.0
MIN_GAIN = 0.0003
HALF_LIVES = [60.0, 120.0, 240.0, 480.0, 1e9]
LAM_TEAMS = [3.0, 10.0, 30.0, 100.0, 300.0]


def markets_of(stat: str) -> dict:
    """The O/U markets that score a stat (fouls: the extra fouls markets; they are not exported lines)."""
    src = {k: v for k, v in PM.MARKETS.items() if v[0] == stat}
    if not src:
        src = {k: v for k, v in PM.EXTRA_MARKETS.items() if v[0] == stat}
    return src


def score_predictions(ds, stat: str, wf: PM.WalkForward) -> dict:
    rows = wf.rows
    yh, ya = ds.y[stat][rows, 0], ds.y[stat][rows, 1]
    r = PM.fit_dispersion(yh, ya, wf.mu_h, wf.mu_a)
    rt = PM.fit_total_dispersion(yh, ya, wf.mu_h, wf.mu_a)
    ls, ls_rt = [], []
    for _, (_, kind, lines) in markets_of(stat).items():
        ls.append(PM.market_eval(wf.mu_h, wf.mu_a, r, yh, ya, kind, lines).loss.mean())
        ls_rt.append(PM.market_eval(wf.mu_h, wf.mu_a, r, yh, ya, kind, lines, r_total=rt).loss.mean()
                     if kind == "total" else ls[-1])
    nll = -PM.nb_loglik(np.concatenate([yh, ya]), np.concatenate([wf.mu_h, wf.mu_a]), r).mean()
    mae = float(np.abs(np.concatenate([yh - wf.mu_h, ya - wf.mu_a])).mean())
    return {"score": float(np.mean(ls)), "score_rt": float(np.mean(ls_rt)), "r": r, "r_total": rt, "nll": float(nll),
            "mae": mae, "n": int(len(rows)), "n_fits": wf.n_fits, "nonconverged": wf.nonconverged}


# ------------------------------------------------------------------ worker side
_DS = None
_DES: dict = {}


def _init() -> None:
    global _DS
    _DS = PM.load_dataset()


def get_design(stat: str, cfg: PM.Config) -> PM.Design:
    key = (stat,) + cfg.key()
    if key not in _DES:
        _DES[key] = PM.build_design(_DS, stat, level=cfg.use_level, ref=cfg.use_ref, attack=cfg.use_attack,
                                    concede=cfg.use_concede, dom=cfg.use_dom)
    return _DES[key]


def _task(args):
    stat, cfgd = args
    cfg = PM.Config(**cfgd)
    t0 = time.time()
    des = get_design(stat, cfg)
    wf = PM.walk_forward(_DS, des, cfg, _DS.day(VAL_START), _DS.day(VAL_END), STEP_DAYS)
    res = score_predictions(_DS, stat, wf)
    res["seconds"] = round(time.time() - t0, 1)
    return stat, cfgd, res


# ------------------------------------------------------------------ driver
def short(cfg: PM.Config) -> str:
    parts = [f"H={cfg.half_life:g}", f"lam={cfg.lam_team:g}"]
    if cfg.con_mult != 1.0:
        parts.append(f"conx{cfg.con_mult:g}")
    if not cfg.use_attack:
        parts.append("noAtt")
    if not cfg.use_concede:
        parts.append("noCon")
    if cfg.use_dom:
        parts.append(f"dom{cfg.lam_dom:g}")
    if cfg.use_level:
        parts.append(f"lvl{cfg.lam_level:g}")
    if cfg.use_ref:
        parts.append(f"ref{cfg.lam_ref:g}")
    return " ".join(parts)


def select_stat(ex, stat: str, log) -> dict:
    trace: list[dict] = []

    def run(cfgs: list[PM.Config], stage: str) -> list[tuple[PM.Config, dict]]:
        out = []
        for _, cfgd, res in ex.map(_task, [(stat, asdict(c)) for c in cfgs]):
            c = PM.Config(**cfgd)
            out.append((c, res))
            trace.append({"stage": stage, "config": cfgd, **res})
            log(f"  [{stat}] {stage:<10} {short(c):<46} score {res['score']:.5f} (rt {res['score_rt']:.5f}) "
                f"mae {res['mae']:.3f} r {res['r']:.1f} {res['seconds']}s nonconv {res['nonconverged']}")
        return out

    # reference rows (not candidates): competition level + home advantage only
    run([PM.Config(half_life=1e9, use_attack=False, use_concede=False)], "ref-comp")
    # 1. grid
    grid = run([PM.Config(half_life=h, lam_team=l) for h in HALF_LIVES for l in LAM_TEAMS], "grid")
    best_cfg, best = min(grid, key=lambda x: x[1]["score"])
    log(f"[{stat}] grid best: {short(best_cfg)} {best['score']:.5f}")

    def try_variants(variants: list[PM.Config], stage: str, cur_cfg, cur):
        res = run(variants, stage)
        c, r = min(res, key=lambda x: x[1]["score"])
        if r["score"] <= cur["score"] - MIN_GAIN:
            log(f"[{stat}] {stage}: adopt {short(c)} ({cur['score']:.5f} -> {r['score']:.5f})")
            return c, r
        log(f"[{stat}] {stage}: keep {short(cur_cfg)} (best variant {r['score']:.5f} vs {cur['score']:.5f})")
        return cur_cfg, cur

    def rep(c, **kw):
        d = asdict(c)
        d.update(kw)
        return PM.Config(**d)

    # 2. extra effects
    best_cfg, best = try_variants([rep(best_cfg, use_dom=True, lam_dom=l) for l in (10.0, 30.0, 100.0)], "dominance",
                                  best_cfg, best)
    best_cfg, best = try_variants([rep(best_cfg, use_level=True, lam_level=l) for l in (1e2, 1e3, 1e4)], "level",
                                  best_cfg, best)
    best_cfg, best = try_variants(
        [rep(best_cfg, con_mult=0.3), rep(best_cfg, con_mult=3.0), rep(best_cfg, use_concede=False),
         rep(best_cfg, use_attack=False)], "att-con", best_cfg, best)
    if stat in PM.REF_STATS:
        best_cfg, best = try_variants([rep(best_cfg, use_ref=True, lam_ref=l) for l in (5.0, 20.0, 80.0, 320.0)],
                                      "referee", best_cfg, best)
    # 3. local refinement (two rounds)
    for rnd in range(2):
        hs = [h for h in HALF_LIVES]
        i = hs.index(best_cfg.half_life) if best_cfg.half_life in hs else 0
        nb = []
        for h in {hs[max(i - 1, 0)], hs[min(i + 1, len(hs) - 1)], best_cfg.half_life}:
            for l in (best_cfg.lam_team / 3.0, best_cfg.lam_team, best_cfg.lam_team * 3.0):
                if (h, l) != (best_cfg.half_life, best_cfg.lam_team):
                    nb.append(rep(best_cfg, half_life=h, lam_team=l))
        if best_cfg.use_ref:
            nb += [rep(best_cfg, lam_ref=best_cfg.lam_ref / 3.0), rep(best_cfg, lam_ref=best_cfg.lam_ref * 3.0)]
        if best_cfg.use_level:
            nb += [rep(best_cfg, lam_level=best_cfg.lam_level / 3.0), rep(best_cfg, lam_level=best_cfg.lam_level * 3.0)]
        if best_cfg.use_dom:
            nb += [rep(best_cfg, lam_dom=best_cfg.lam_dom / 3.0), rep(best_cfg, lam_dom=best_cfg.lam_dom * 3.0)]
        new_cfg, new = try_variants(nb, f"refine{rnd + 1}", best_cfg, best)
        if new_cfg == best_cfg:
            break
        best_cfg, best = new_cfg, new
    # 4. NB-total dispersion decision (only the markets of "total" kind change)
    use_rt = bool(best["score_rt"] <= best["score"] - 0.0010)
    log(f"[{stat}] FROZEN {short(best_cfg)} score {best['score']:.5f}; r {best['r']:.2f}; r_total {best['r_total']:.2f} "
        f"(NB-total {'used' if use_rt else 'not used'}: {best['score']:.5f} -> {best['score_rt']:.5f})")
    return {"config": asdict(best_cfg), "validation": best, "use_total_dispersion": use_rt,
            "n_configs_evaluated": len(trace), "trace": trace}


def baseline_dispersions(ds, stat: str) -> dict:
    """Out-of-sample NB sizes of the baselines, fitted on the validation rows where all baselines are defined."""
    v0, v1 = ds.day(VAL_START), ds.day(VAL_END)
    bl = PM.compute_baselines(ds, stat)
    sel = np.flatnonzero(ds.valid[stat] & (ds.t >= v0) & (ds.t < v1) & bl.eligible())
    yh, ya = ds.y[stat][sel, 0], ds.y[stat][sel, 1]
    out = {"n_rows": int(len(sel))}
    for name in PM.BASELINE_NAMES:
        a, b = bl.means(name)
        out[name] = PM.fit_dispersion(yh, ya, a[sel], b[sel])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--stats", default=",".join(PM.STATS))
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    stats = args.stats.split(",")
    t0 = time.time()

    def log(msg: str) -> None:
        print(f"[{time.time() - t0:7.0f}s] {msg}", flush=True)

    ds = PM.load_dataset()
    frozen = {"split": {"train": [TRAIN_START, VAL_START], "validation": [VAL_START, VAL_END],
                        "test_not_read": ["2026-02-01", "2026-10-12"]},
              "step_days": STEP_DAYS, "min_gain": MIN_GAIN, "stats": {}}
    with ProcessPoolExecutor(max_workers=args.workers, initializer=_init) as ex:
        for stat in stats:
            frozen["stats"][stat] = select_stat(ex, stat, log)
            frozen["stats"][stat]["baseline_dispersion_validation"] = baseline_dispersions(ds, stat)
            with open(args.out, "w", encoding="utf-8") as f:  # incremental save
                json.dump(frozen, f, indent=1)
    log("done")


if __name__ == "__main__":
    main()
