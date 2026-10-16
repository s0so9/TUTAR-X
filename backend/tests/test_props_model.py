"""Props count models (scripts/training/props_*.py): SYNTHETIC fixtures only (made-up teams, counts and referees,
generated from a seeded negative-binomial; never shown to users and never football data).

Checks: NB tail / convolution maths against scipy, missing stat is excluded (never 0), the ridge fit recovers
planted team effects, walk-forward predictions and baselines never use matches after the cut (leak tests), the
final-stage design for arbitrary rows equals the training design, the runtime-formula checker agrees with the
vectorised library code, and (when present) the exported candidate JSON has the agreed structure.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import nbinom

TRAINING_DIR = Path(__file__).resolve().parents[1] / "scripts" / "training"
sys.path.insert(0, str(TRAINING_DIR))

import props_check_runtime_formula as CK  # noqa: E402
import props_final as PF  # noqa: E402
import props_model as PM  # noqa: E402

N_TEAMS = 16
TRUE_R = {"corners": 12.0, "yellow_cards": 40.0, "total_shots": 20.0, "shots_on_target": 25.0, "fouls": 60.0}
TRUE_BASE = {"corners": 4.5, "yellow_cards": 2.0, "total_shots": 12.0, "shots_on_target": 4.0, "fouls": 11.0}


def make_rows(n_days: int = 500, seed: int = 3) -> tuple[list[dict], dict]:
    """SYNTHETIC rows with the columns of props_match_stats.csv.gz. Returns (rows, planted attack effects)."""
    rng = np.random.default_rng(seed)
    attack = rng.normal(0, 0.25, N_TEAMS)
    concede = rng.normal(0, 0.15, N_TEAMS)
    ref_off = {"SYNTHETIC REF A": 0.25, "SYNTHETIC REF B": -0.2, "SYNTHETIC REF C": 0.0}
    refs = list(ref_off)
    rows = []
    mid = 0
    start = np.datetime64("2023-08-01T15:00:00")
    for day in range(n_days):
        for _ in range(3):
            h, a = rng.choice(N_TEAMS, size=2, replace=False)
            comp = 47 if (h + a) % 2 == 0 else 87
            ref = refs[int(rng.integers(0, 3))]
            row = {"match_id": f"SYN{mid:06d}", "kickoff": str(start + np.timedelta64(day, "D") + np.timedelta64(int(rng.integers(0, 5)), "h")) + "Z",
                   "competition_id": comp, "home_team_id": 1000 + int(h), "away_team_id": 1000 + int(a), "referee": ref}
            mid += 1
            for s in PM.STATS:
                ro = ref_off[ref] if s in PM.REF_STATS else 0.0
                mu_h = TRUE_BASE[s] * math.exp(0.15 + attack[h] + concede[a] + ro)
                mu_a = TRUE_BASE[s] * math.exp(attack[a] + concede[h] + ro)
                r = TRUE_R[s]
                row[f"home_{s}"] = int(rng.negative_binomial(r, r / (r + mu_h)))
                row[f"away_{s}"] = int(rng.negative_binomial(r, r / (r + mu_a)))
            rows.append(row)
    return rows, {"attack": attack, "concede": concede}


@pytest.fixture(scope="module")
def synth():
    rows, truth = make_rows()
    return rows, truth, PM.dataset_from_rows(rows)


# ---------------------------------------------------------------------------------------------- maths
def test_nb_cdf_matches_scipy():
    mu, r = np.array([0.7, 3.2, 11.0]), 9.0
    for k in (0, 1, 4, 10):
        got = PM.nb_cdf(k, mu, r)
        want = nbinom.cdf(k, r, r / (r + mu))
        assert np.allclose(got, want, atol=1e-12)
    assert PM.nb_cdf(-1, 3.0, 5.0) == 0.0


def test_over_probs_team_and_total_against_brute_force():
    mu_h, mu_a, r = np.array([5.0, 2.1]), np.array([4.0, 6.3]), 11.0
    lines = [7.5, 9.5, 11.5]
    team = PM.over_probs(mu_h, mu_a, r, "team", lines)
    assert team.shape == (2, 2, 3)
    assert np.allclose(team[:, 0, 1], 1 - nbinom.cdf(9, r, r / (r + mu_h)))
    tot = PM.over_probs(mu_h, mu_a, r, "total", lines)
    k = np.arange(80)
    for i in range(2):
        pm = np.convolve(nbinom.pmf(k, r, r / (r + mu_h[i])), nbinom.pmf(k, r, r / (r + mu_a[i])))[:80]
        for j, L in enumerate(lines):
            assert tot[i, j] == pytest.approx(pm[int(L) + 1:].sum(), abs=1e-8)
    # r_total given -> NB of the summed mean
    tot_rt = PM.over_probs(mu_h, mu_a, r, "total", lines, 50.0)
    assert np.allclose(tot_rt[:, 0], 1 - nbinom.cdf(7, 50.0, 50.0 / (50.0 + mu_h + mu_a)))


def test_over_probability_decreases_with_line():
    p = PM.over_probs(np.array([4.0]), np.array([3.0]), 8.0, "total", [5.5, 6.5, 7.5, 8.5])
    assert np.all(np.diff(p[0]) < 0)
    assert np.all((p > 0) & (p < 1))


# ---------------------------------------------------------------------------------------------- dataset
def test_missing_stat_is_excluded_not_zero():
    rows, _ = make_rows(n_days=10)
    rows[0]["home_yellow_cards"] = ""  # FotMob did not send it -> not a zero
    rows[0]["away_yellow_cards"] = ""
    rows[1]["home_yellow_cards"] = 0   # a real 0-0 card match stays
    rows[1]["away_yellow_cards"] = 0
    ds = PM.dataset_from_rows(rows)
    i0 = int(np.flatnonzero(ds.match_id == rows[0]["match_id"])[0])
    i1 = int(np.flatnonzero(ds.match_id == rows[1]["match_id"])[0])
    assert not ds.valid["yellow_cards"][i0] and np.isnan(ds.y["yellow_cards"][i0]).all()
    assert ds.valid["yellow_cards"][i1] and (ds.y["yellow_cards"][i1] == 0).all()
    assert ds.excluded["yellow_cards_missing"] == 1
    assert ds.valid["corners"][i0]  # other stats of the same match are unaffected


def test_czech_shots_definition_break_is_excluded():
    rows, _ = make_rows(n_days=5)
    rows[0].update({"competition_id": PM.SHOTS_BREAK_COMP, "kickoff": "2025-01-10T15:00:00Z"})
    ds = PM.dataset_from_rows(rows)
    i0 = int(np.flatnonzero(ds.match_id == rows[0]["match_id"])[0])
    assert not ds.valid["total_shots"][i0] and ds.valid["corners"][i0]


# ---------------------------------------------------------------------------------------------- fit
def test_ridge_fit_recovers_planted_attack_effects(synth):
    _, truth, ds = synth
    des = PM.build_design(ds, "corners", level=False, ref=False, attack=True, concede=True, dom=False)
    cfg = PM.Config(half_life=1e9, lam_team=10.0)
    n = len(des.rows)
    fit = PM.fit_nb(des, n, np.ones(2 * n), PM.penalty_matrix(des, cfg), maxiter=2000)
    assert fit.converged
    est = fit.theta[des.sl["A"]]
    tid = {int(t): i for i, t in enumerate(ds.team_ids)}
    est_by_team = np.array([est[tid[1000 + k]] for k in range(N_TEAMS)])
    assert np.corrcoef(est_by_team, truth["attack"])[0, 1] > 0.9
    assert abs(fit.theta[1] - 0.15) < 0.06  # home advantage
    assert 5.0 < fit.r < 40.0  # planted size 12


def test_referee_effect_has_the_planted_sign(synth):
    _, _, ds = synth
    des = PM.build_design(ds, "yellow_cards", level=False, ref=True, attack=True, concede=True, dom=False)
    cfg = PM.Config(half_life=1e9, lam_team=20.0, lam_ref=5.0, use_ref=True)
    n = len(des.rows)
    fit = PM.fit_nb(des, n, np.ones(2 * n), PM.penalty_matrix(des, cfg), maxiter=2000)
    R = dict(zip(ds.ref_names, fit.theta[des.sl["R"]]))
    assert R["SYNTHETIC REF A"] > 0.1 > -0.1 > R["SYNTHETIC REF B"]
    assert abs(R["SYNTHETIC REF C"]) < 0.12


def test_decay_weights_half_life():
    w = PM.decay_weights(np.array([0.0, 100.0, 200.0]), 200.0, 100.0)
    assert np.allclose(w, [0.25, 0.5, 1.0])


# ---------------------------------------------------------------------------------------------- leakage
def test_walk_forward_ignores_labels_after_the_cut(synth):
    rows, _, ds = synth
    cfg = PM.Config(half_life=200.0, lam_team=30.0, use_ref=True)
    start = ds.day("2024-06-01")
    des = PM.build_design(ds, "yellow_cards", level=False, ref=True, attack=True, concede=True, dom=False)
    wf = PM.walk_forward(ds, des, cfg, start, start + 14.0, 14.0)
    assert wf.n_fits == 1 and len(wf.rows) > 20
    # scramble every label that kicked off from the start day on
    rows2 = [dict(r) for r in rows]
    rng = np.random.default_rng(99)
    for r in rows2:
        if r["kickoff"][:10] >= "2024-06-01":
            for s in PM.STATS:
                r[f"home_{s}"] = int(rng.integers(0, 30))
                r[f"away_{s}"] = int(rng.integers(0, 30))
    ds2 = PM.dataset_from_rows(rows2)
    des2 = PM.build_design(ds2, "yellow_cards", level=False, ref=True, attack=True, concede=True, dom=False)
    wf2 = PM.walk_forward(ds2, des2, cfg, start, start + 14.0, 14.0)
    assert np.array_equal(wf.rows, wf2.rows)
    assert np.allclose(wf.mu_h, wf2.mu_h, atol=1e-9) and np.allclose(wf.mu_a, wf2.mu_a, atol=1e-9)


def test_baselines_use_only_earlier_matches(synth):
    rows, _, ds = synth
    bl = PM.compute_baselines(ds, "corners")
    cut = ds.day("2024-09-01")
    rows2 = [dict(r) for r in rows]
    for r in rows2:
        if r["kickoff"][:10] >= "2024-09-01":
            r["home_corners"], r["away_corners"] = 99, 99
    bl2 = PM.compute_baselines(PM.dataset_from_rows(rows2), "corners")
    early = ds.t < cut
    for name in PM.BASELINE_NAMES:
        a, b = bl.means(name)
        a2, b2 = bl2.means(name)
        assert np.array_equal(a[early], a2[early], equal_nan=True) and np.array_equal(b[early], b2[early], equal_nan=True)
    late = ds.t >= cut + 3
    a, _ = bl.means("last5")
    a2, _ = bl2.means("last5")
    assert not np.allclose(a[late], a2[late], equal_nan=True)  # sanity: the scrambling does show up later


def test_last5_baseline_is_the_plain_mean_of_for_and_against(synth):
    _, _, ds = synth
    bl = PM.compute_baselines(ds, "corners")
    i = int(np.flatnonzero(ds.t > ds.day("2024-03-01"))[0])
    h, a, t = int(ds.home_idx[i]), int(ds.away_idx[i]), ds.t[i] - PM.TRAIN_END_MARGIN_DAYS

    def hist(team):
        out = []
        for j in np.flatnonzero((ds.t < t) & ds.valid["corners"]):
            if ds.home_idx[j] == team:
                out.append((ds.y["corners"][j, 0], ds.y["corners"][j, 1]))
            elif ds.away_idx[j] == team:
                out.append((ds.y["corners"][j, 1], ds.y["corners"][j, 0]))
        return out[-5:]

    f_home = np.mean([x[0] for x in hist(h)])
    a_away = np.mean([x[1] for x in hist(a)])
    got, _ = bl.means("last5")
    assert got[i] == pytest.approx((f_home + a_away) / 2)


# ---------------------------------------------------------------------------------------------- export / runtime formula
def test_final_stage_design_equals_training_design(synth):
    _, _, ds = synth
    for kw in ({"level": True, "ref": True, "dom": False}, {"level": False, "ref": False, "dom": True}):
        des = PM.build_design(ds, "yellow_cards", attack=True, concede=kw["dom"] is False, **kw)
        rows = des.rows[:60]
        Xp = PF.predict_design(ds, des, rows).toarray()
        assert np.allclose(Xp, des.X[:120].toarray())


def synthetic_candidate() -> dict:
    return {"version": "props_test_fixture", "lines": {k: v[2] for k, v in PM.MARKETS.items()},
            "stats": {
                "corners": {"dispersion": 11.0, "total_dispersion": None, "intercept": math.log(4.4), "home_advantage": 0.12,
                            "competitions": {"47": 0.05}, "teams": {"1": {"attack": 0.2, "concede": -0.1}, "2": {"attack": -0.1, "concede": 0.15}},
                            "referees": {}},
                "total_shots": {"dispersion": 18.0, "total_dispersion": 95.0, "intercept": math.log(12.0), "home_advantage": 0.1,
                                "competitions": {}, "teams": {"1": {"attack": 0.3, "concede": 0.0}, "2": {"attack": 0.0, "concede": 0.1}},
                                "referees": {}},
                "yellow_cards": {"dispersion": 500.0, "total_dispersion": None, "intercept": math.log(2.1), "home_advantage": -0.05,
                                 "competitions": {}, "teams": {"1": {"attack": 0.0, "concede": 0.0}},
                                 "referees": {"SYNTHETIC REF A": {"offset": 0.3, "matches": 30}}}}}


def test_runtime_formula_checker_agrees_with_library_and_flags_a_change():
    cand = synthetic_candidate()
    matches = []
    for comp, h, a, ref in ((47, 1, 2, "SYNTHETIC REF A"), (99, 2, 1, ""), (47, 1, 77777, "unknown ref")):
        m = {"match_id": "SYN", "competition_id": comp, "home_team_id": h, "away_team_id": a, "referee": ref, "mu": {}, "probs": {}}
        for stat, blk in cand["stats"].items():
            ct = blk["competitions"].get(str(comp), 0.0)
            th, ta = blk["teams"].get(str(h), {}), blk["teams"].get(str(a), {})
            ro = blk["referees"].get(ref, {}).get("offset", 0.0)
            mh = math.exp(blk["intercept"] + ct + blk["home_advantage"] + th.get("attack", 0) + ta.get("concede", 0) + ro)
            ma = math.exp(blk["intercept"] + ct + ta.get("attack", 0) + th.get("concede", 0) + ro)
            m["mu"][stat] = [mh, ma]
            for mk, (st, kind, lines) in PM.MARKETS.items():
                if st != stat:
                    continue
                p = PM.over_probs(np.array([mh]), np.array([ma]), blk["dispersion"], kind, lines, blk["total_dispersion"])
                m["probs"][mk] = [p[0, 0].tolist(), p[0, 1].tolist()] if kind == "team" else p[0].tolist()
        matches.append(m)
    res = CK.check(cand, {"matches": matches})
    assert res["n_comparisons"] == 3 * 6  # per match: corners 2 + shots 2 + yellow cards 2 markets
    assert max(res["max_abs_diff_prob"].values()) < 1e-9 and max(res["max_abs_diff_mu"].values()) < 1e-12
    cand["stats"]["corners"]["home_advantage"] += 0.05  # a different parameter must be detected
    bad = CK.check(cand, {"matches": matches})
    assert max(bad["max_abs_diff_prob"].values()) > 1e-3


# ---------------------------------------------------------------------------------------------- exported candidate (skipped when absent)
CAND = PM.DATA / "props_model_candidate.json"
REF = PM.DATA / "props_check_reference.json"


@pytest.mark.skipif(not (CAND.exists() and REF.exists()), reason="props_model_candidate.json not exported yet")
def test_exported_candidate_structure_and_runtime_formula():
    cand = json.loads(CAND.read_text(encoding="utf-8"))
    assert cand["version"] == "props_v1" and cand["trained_through"] and cand["fitted_on"] and cand["formula"]
    assert set(cand["lines"]) == set(PM.MARKETS) and all(cand["lines"][k] == v[2] for k, v in PM.MARKETS.items())
    for stat, blk in cand["stats"].items():
        assert stat in PM.STATS and blk["distribution"] == "negbin" and blk["dispersion"] > 0
        assert blk["teams"] and all(set(t) >= {"attack", "concede", "matches", "last_match"} for t in blk["teams"].values())
        assert all(math.isfinite(x) for x in (blk["intercept"], blk["home_advantage"]))
        if stat not in PM.REF_STATS:
            assert blk["referees"] == {}
    assert cand["team_recent"] and all("n" in v for t in cand["team_recent"].values() for v in t.values())
    assert "evaluation" in cand
    res = CK.check(cand, json.loads(REF.read_text(encoding="utf-8")))
    assert res["n_matches"] == 200 and max(res["max_abs_diff_prob"].values()) < 1e-6
