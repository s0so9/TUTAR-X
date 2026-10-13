"""Tests for global attack/defence ratings (app.prediction.team_ratings)."""

import numpy as np
import pytest

from app.prediction.poisson import rating_lambdas_from_features
from app.prediction.team_ratings import GlobalPoissonRatings, domestic_groups


def _round_robin(strengths, rounds=6, seed=0):
    """Synthetic league: goals ~ Poisson(exp(base + att_home - def_away) * home_adv)."""
    rng = np.random.default_rng(seed)
    teams = list(strengths)
    home, away, hg, ag, ages = [], [], [], [], []
    for r in range(rounds):
        for h in teams:
            for a in teams:
                if h == a:
                    continue
                lh = np.exp(0.2 + strengths[h] - strengths[a]) * 1.2
                la = np.exp(0.2 + strengths[a] - strengths[h])
                home.append(h); away.append(a)
                hg.append(int(rng.poisson(lh))); ag.append(int(rng.poisson(la)))
                ages.append(float(r))
    return home, away, hg, ag, ages


def test_stronger_team_gets_higher_expected_goals():
    data = _round_robin({"strong": 0.6, "mid": 0.0, "weak": -0.6})
    ratings = GlobalPoissonRatings(l2_penalty=1.0).fit(*data)
    strong_home = ratings.predict("strong", "weak")
    weak_home = ratings.predict("weak", "strong")
    assert strong_home.home > strong_home.away
    assert weak_home.away > weak_home.home
    # A stronger defence lowers the opponent's expected goals (regression for the
    # old attack / opponent-conceded inversion).
    assert ratings.predict("mid", "strong").home < ratings.predict("mid", "weak").home


def test_home_advantage_is_learned():
    data = _round_robin({"a": 0.0, "b": 0.0, "c": 0.0, "d": 0.0}, rounds=20)
    ratings = GlobalPoissonRatings(l2_penalty=1.0).fit(*data)
    assert ratings.home_adv > 0


def test_teams_with_too_few_matches_are_unavailable():
    ratings = GlobalPoissonRatings(min_team_matches=3).fit(
        ["a", "a", "a", "x"], ["b", "b", "b", "a"], [1, 2, 0, 1], [0, 1, 1, 1], [1, 2, 3, 4]
    )
    assert ratings.predict("a", "b") is not None
    assert ratings.predict("x", "a") is None  # x played once
    assert ratings.predict("unknown", "a") is None


def test_league_groups_transfer_cross_league_evidence():
    # Two leagues of equal internal balance; league A teams beat league B teams
    # in every cross-league match. With groups, a league-A team that never
    # played abroad still comes out ahead of a league-B team.
    home, away, hg, ag, ages = [], [], [], [], []
    for lg in ("A", "B"):
        d = _round_robin({f"{lg}{i}": 0.0 for i in range(4)}, rounds=4, seed=1 if lg == "A" else 2)
        for x in zip(*d):
            home.append(x[0]); away.append(x[1]); hg.append(x[2]); ag.append(x[3]); ages.append(x[4])
    for i in range(1, 4):
        for _ in range(4):
            home.append(f"A{i}"); away.append(f"B{i}"); hg.append(3); ag.append(0); ages.append(1.0)
            home.append(f"B{i}"); away.append(f"A{i}"); hg.append(0); ag.append(2); ages.append(1.0)
    comps = ["League A" if h.startswith("A") and a.startswith("A") else
             "League B" if h.startswith("B") and a.startswith("B") else "Champions League"
             for h, a in zip(home, away)]
    groups = domestic_groups(home, away, comps)
    assert groups["A0"] == "League A" and groups["B0"] == "League B"
    ratings = GlobalPoissonRatings(l2_penalty=5.0, group_l2_penalty=0.5).fit(
        home, away, hg, ag, ages, team_groups=groups
    )
    lam = ratings.predict("A0", "B0")  # neither played cross-league
    assert lam.home > lam.away * 1.5


def test_rating_lambdas_from_features():
    assert rating_lambdas_from_features({"home_lambda_rating": 1.4, "away_lambda_rating": 0.9}) == (1.4, 0.9)
    assert rating_lambdas_from_features({"home_lambda_rating": None, "away_lambda_rating": 0.9}) is None
    assert rating_lambdas_from_features({}) is None


def test_fit_requires_matches():
    with pytest.raises(ValueError):
        GlobalPoissonRatings().fit([], [], [], [], [])


def test_domestic_groups_key_by_competition_id_not_name():
    # Germany's and Austria's top flights are both called "Bundesliga" in the
    # database; they must not share one group strength.
    home = ["bayern", "sturm", "caf_side"]
    away = ["dortmund", "salzburg", "bayern"]
    names = ["Bundesliga", "Bundesliga", "CAF Confederation Cup"]
    ids = ["comp_de", "comp_at", "comp_caf"]
    groups = domestic_groups(home, away, names, ids)
    assert groups["bayern"] == "comp_de" and groups["dortmund"] == "comp_de"
    assert groups["sturm"] == "comp_at" and groups["salzburg"] == "comp_at"
    # Multi-country competitions are never a team's domestic group
    assert "caf_side" not in groups


def test_multi_country_competitions_are_not_domestic():
    from app.prediction.team_ratings import is_domestic_league_name

    for name in ("UEFA Women's Europa Cup", "CAF Confederation Cup", "CONCACAF Champions Cup",
                 "Copa Libertadores Grp. D", "Copa Sudamericana Knockout Round Play-offs",
                 "Leagues Cup Final Stage", "AFC Champions League Two", "EURO U19",
                 "Champions League", "Club Friendlies", "World Cup Qualification UEFA 2nd Round",
                 None, ""):
        assert not is_domestic_league_name(name), name
    # Domestic leagues and single-country cups stay eligible (cups are kept on
    # walk-forward evidence; see NON_DOMESTIC_MARKERS)
    for name in ("Bundesliga", "Premier League", "Serie A", "Super Lig", "Eredivisie",
                 "FA Cup", "DFB Pokal", "Copa del Rey", "Cup"):
        assert is_domestic_league_name(name), name
