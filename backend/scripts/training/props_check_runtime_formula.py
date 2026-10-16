"""Check that props_model_candidate.json + the documented prediction rule reproduce the training code's probabilities.

props_final.py writes data/training/props_check_reference.json: for 200 random TEST matches the means and the O/U
probabilities of every market, computed by the training code (sparse design matrix, unrounded parameters) with the
deployment fit.  This script recomputes the same numbers from ONLY the exported JSON, with the formula text of
props_model_candidate.json written out by hand (scipy.stats.nbinom, np.convolve), i.e. it is an independent
implementation of what the runtime has to do.  It prints the max absolute difference per market.

    mu_home = exp(intercept + competitions.get(comp, 0) + home_advantage + teams[home].attack + teams[away].concede + ref)
    mu_away = exp(intercept + competitions.get(comp, 0) + teams[away].attack + teams[home].concede + ref)
    each side NB(mean mu, size dispersion); P(X > line) = 1 - P(X <= floor(line))
    total: convolution of the two sides, or (when total_dispersion is not null) NB(mu_home + mu_away, total_dispersion)

Usage (from backend/):  venv/Scripts/python.exe scripts/training/props_check_runtime_formula.py [--tol 1e-6]
Exit code 0 when the max abs diff over all markets <= tol, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.stats import nbinom

DATA = Path(__file__).resolve().parents[2] / "data" / "training"

# market -> (stat, kind); the lines come from the candidate JSON ("lines")
MARKET_STAT = {
    "total_yellow_cards": ("yellow_cards", "total"),
    "team_yellow_cards": ("yellow_cards", "team"),
    "total_corners": ("corners", "total"),
    "team_corners": ("corners", "team"),
    "team_shots": ("total_shots", "team"),
    "total_shots": ("total_shots", "total"),
    "team_shots_on_target": ("shots_on_target", "team"),
    "total_shots_on_target": ("shots_on_target", "total"),
}


def side_means(block: dict, comp: int, home: int, away: int, referee: str) -> tuple[float, float]:
    """The prediction rule of the JSON: unknown competition / team / referee -> 0 effect."""
    teams = block["teams"]
    th, ta = teams.get(str(home), {}), teams.get(str(away), {})
    comp_off = block["competitions"].get(str(comp), 0.0)
    ref_off = block["referees"].get(referee, {}).get("offset", 0.0) if referee else 0.0
    base = block["intercept"] + comp_off + ref_off
    mu_h = math.exp(base + block["home_advantage"] + th.get("attack", 0.0) + ta.get("concede", 0.0))
    mu_a = math.exp(base + ta.get("attack", 0.0) + th.get("concede", 0.0))
    return mu_h, mu_a


def nb_sf(k: int, mu: float, r: float) -> float:
    """P(X > k) for NB(mean mu, size r): scipy parameterisation n = r, p = r / (r + mu)."""
    return float(nbinom.sf(k, r, r / (r + mu)))


def team_over(mu: float, r: float, lines: list[float]) -> list[float]:
    return [nb_sf(int(math.floor(L)), mu, r) for L in lines]


def total_over(mu_h: float, mu_a: float, r: float, r_total, lines: list[float]) -> list[float]:
    ks = [int(math.floor(L)) for L in lines]
    if r_total is not None:
        return [nb_sf(k, mu_h + mu_a, r_total) for k in ks]
    K = max(ks) + 1
    grid = np.arange(K)
    ph = nbinom.pmf(grid, r, r / (r + mu_h))
    pa = nbinom.pmf(grid, r, r / (r + mu_a))
    cdf = np.cumsum(np.convolve(ph, pa)[:K])
    return [float(1.0 - cdf[k]) for k in ks]


def check(candidate: dict, reference: dict) -> dict:
    lines = candidate["lines"]
    diffs: dict[str, float] = {}
    mu_diff: dict[str, float] = {}
    n_cmp = 0
    for m in reference["matches"]:
        for stat, blk in candidate["stats"].items():  # every exported stat (also those without a listed market, e.g. fouls)
            if stat in m["mu"]:
                mu_h, mu_a = side_means(blk, m["competition_id"], m["home_team_id"], m["away_team_id"], m.get("referee", ""))
                mu_diff[stat] = max(mu_diff.get(stat, 0.0), abs(mu_h - m["mu"][stat][0]), abs(mu_a - m["mu"][stat][1]))
        for mk, (stat, kind) in MARKET_STAT.items():
            if stat not in candidate["stats"] or mk not in m["probs"]:
                continue
            blk = candidate["stats"][stat]
            mu_h, mu_a = side_means(blk, m["competition_id"], m["home_team_id"], m["away_team_id"], m.get("referee", ""))
            ref_mu = m["mu"][stat]
            mu_diff[stat] = max(mu_diff.get(stat, 0.0), abs(mu_h - ref_mu[0]), abs(mu_a - ref_mu[1]))
            r = blk["dispersion"]
            if kind == "team":
                got = [team_over(mu_h, r, lines[mk]), team_over(mu_a, r, lines[mk])]
                d = max(abs(a - b) for row_g, row_r in zip(got, m["probs"][mk]) for a, b in zip(row_g, row_r))
            else:
                got = total_over(mu_h, mu_a, r, blk.get("total_dispersion"), lines[mk])
                d = max(abs(a - b) for a, b in zip(got, m["probs"][mk]))
            diffs[mk] = max(diffs.get(mk, 0.0), d)
            n_cmp += 1
    return {"max_abs_diff_prob": diffs, "max_abs_diff_mu": mu_diff, "n_matches": len(reference["matches"]), "n_comparisons": n_cmp}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default=str(DATA / "props_model_candidate.json"))
    ap.add_argument("--reference", default=str(DATA / "props_check_reference.json"))
    ap.add_argument("--tol", type=float, default=1e-6)
    args = ap.parse_args()
    with open(args.candidate, encoding="utf-8") as f:
        candidate = json.load(f)
    with open(args.reference, encoding="utf-8") as f:
        reference = json.load(f)
    res = check(candidate, reference)
    print(f"matches: {res['n_matches']}, comparisons (match x market): {res['n_comparisons']}")
    for mk, d in res["max_abs_diff_prob"].items():
        print(f"  {mk:<24} max |dp| = {d:.2e}")
    for st, d in res["max_abs_diff_mu"].items():
        print(f"  mu {st:<21} max |dmu| = {d:.2e}")
    worst = max(list(res["max_abs_diff_prob"].values()) + list(res["max_abs_diff_mu"].values()) + [0.0])
    ok = worst <= args.tol and res["n_comparisons"] > 0
    print(f"max abs diff over everything: {worst:.2e}  ->  {'OK' if ok else 'MISMATCH'} (tol {args.tol:g})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
