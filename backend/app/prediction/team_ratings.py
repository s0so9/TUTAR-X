"""Global attack/defence ratings fitted by penalised Poisson regression.

Model (Maher 1982 / Dixon-Coles 1997 style, without the low-score correction):

    log λ_home = μ + h + att[home] + dfn[away]
    log λ_away = μ     + att[away] + dfn[home]

``att`` is a team's attacking strength and ``dfn`` its defensive weakness, both
on a log scale relative to the global average. Ratings are fitted jointly on
every finished match in the database, so teams from different leagues become
comparable through the matches that connect those leagues (European cups,
qualifiers). The previous per-team approach multiplied raw goals-scored and
goals-conceded averages from each team's own league, which cannot tell a team
dominating a weak league from one dominating a strong league.

Fitting uses only matches strictly before a cutoff (no look-ahead), with
exponential time decay and an L2 penalty that shrinks teams with little data
toward the global average.
"""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Sequence, Tuple

import numpy as np
from scipy.optimize import minimize

logger = logging.getLogger(__name__)

# Defaults chosen by walk-forward log loss (13 cutoffs, Feb-May 2026 and
# Sep-Oct 2026, 18,697 matches incl. 196 European-cup matches); see
# docs/live-tests/2026-10-13-ucl.md. Revisit as history grows.
DEFAULT_HALF_LIFE_DAYS = 180.0
DEFAULT_L2_PENALTY = 5.0
DEFAULT_MIN_TEAM_MATCHES = 3
DEFAULT_LOOKBACK_DAYS = 400
DEFAULT_GROUP_L2_PENALTY = 1.0
USE_LEAGUE_GROUPS = True
# Weight of real goals in the rating target where team xG is known (1.0 = goals
# only). Chosen by scripts/training/experiment_xg_ratings.py: on 1,442
# walk-forward matches 0.5 beat goals-only on every market (1X2 log loss
# 0.9912 -> 0.9895, O/U 2.5 0.6704 -> 0.6684, BTTS 0.6795 -> 0.6779).
XG_GOAL_WEIGHT = 0.5
# Substrings (case-sensitive) of competition names that are never a team's
# domestic-league group: club and national-team competitions spanning several
# countries, friendlies and qualifiers. Competition.type/level/country are NULL
# in the database, so the name is the only signal.
#
# Domestic cups ("Cup", "FA Cup", "DFB Pokal", ...) are deliberately NOT
# excluded: keyed by competition id each is a single-country group, and the
# walk-forward check (14 cutoffs, 21,369 matches, 1X2 log loss) preferred
# keeping them: excluding them as well gave 1.0025 overall / 0.9666 on 218
# European-cup matches, keeping them 1.0021 / 0.9415 (grouping by name: 1.0030
# / 0.9850). Weekly test windows after each cutoff, fits strictly before it,
# default ratings settings; run 2026-10-13 on the local database.
NON_DOMESTIC_MARKERS = (
    "Champions League", "Europa League", "Conference League", "Friendl",
    "Qualif", "Nations League", "World Cup", "Super Cup",
    # Multi-country competitions not caught above
    "CAF", "CONCACAF", "Concacaf", "AFC ", "Libertadores", "Sudamericana",
    "Leagues Cup", "Europa Cup", "UEFA", "EURO", "Youth League",
)


def is_domestic_league_name(name: Optional[str]) -> bool:
    """False for empty names or names containing a NON_DOMESTIC_MARKERS entry."""
    if not name:
        return False
    return not any(marker in name for marker in NON_DOMESTIC_MARKERS)


@dataclass(frozen=True)
class MatchLambdas:
    """Expected goals for one fixture from the fitted ratings."""

    home: float
    away: float
    home_matches: int
    away_matches: int


class GlobalPoissonRatings:
    """Penalised Poisson attack/defence ratings over all teams."""

    def __init__(
        self,
        half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
        l2_penalty: float = DEFAULT_L2_PENALTY,
        min_team_matches: int = DEFAULT_MIN_TEAM_MATCHES,
        group_l2_penalty: float = DEFAULT_GROUP_L2_PENALTY,
    ):
        self.half_life_days = half_life_days
        self.l2_penalty = l2_penalty
        self.group_l2_penalty = group_l2_penalty
        self.min_team_matches = min_team_matches
        self.mu: Optional[float] = None
        self.home_adv: Optional[float] = None
        self.team_index: Dict[str, int] = {}
        self.att: Optional[np.ndarray] = None
        self.dfn: Optional[np.ndarray] = None
        self.match_counts: Optional[np.ndarray] = None
        self.n_matches_fitted = 0

    def fit(
        self,
        home_ids: Sequence[str],
        away_ids: Sequence[str],
        home_goals: Sequence[int],
        away_goals: Sequence[int],
        ages_days: Sequence[float],
        team_groups: Optional[Dict[str, str]] = None,
    ) -> "GlobalPoissonRatings":
        """Fit ratings. ``ages_days`` is how long before the cutoff each match was played.

        ``team_groups`` optionally maps team -> group (its domestic league). Each
        team's rating is then group effect + team deviation; the group effect is
        penalised less, so a league's strength is learned from *all* of its
        teams' cross-league matches instead of each team's handful.
        """
        if len(home_ids) == 0:
            raise ValueError("Cannot fit ratings without matches")

        teams = sorted(set(home_ids) | set(away_ids))
        self.team_index = {t: i for i, t in enumerate(teams)}
        n = len(teams)
        groups = team_groups or {}
        group_names = sorted({groups[t] for t in teams if t in groups})
        group_index = {g: i for i, g in enumerate(group_names)}
        # Teams without a group get their own singleton slot (index G), whose
        # effect is pinned to zero.
        n_groups = len(group_names)
        tg = np.array([group_index.get(groups.get(t), n_groups) for t in teams], dtype=np.int64)
        hi = np.fromiter((self.team_index[t] for t in home_ids), dtype=np.int64, count=len(home_ids))
        ai = np.fromiter((self.team_index[t] for t in away_ids), dtype=np.int64, count=len(away_ids))
        yh = np.asarray(home_goals, dtype=float)
        ya = np.asarray(away_goals, dtype=float)
        w = np.power(0.5, np.asarray(ages_days, dtype=float) / self.half_life_days)
        reg = self.l2_penalty
        reg_group = self.group_l2_penalty

        def unpack(theta: np.ndarray):
            mu, h = theta[0], theta[1]
            a_dev, d_dev = theta[2:2 + n], theta[2 + n:2 + 2 * n]
            ga = np.append(theta[2 + 2 * n:2 + 2 * n + n_groups], 0.0)
            gd = np.append(theta[2 + 2 * n + n_groups:], 0.0)
            return mu, h, a_dev, d_dev, ga, gd

        def objective(theta: np.ndarray) -> Tuple[float, np.ndarray]:
            mu, h, a_dev, d_dev, ga, gd = unpack(theta)
            att = a_dev + ga[tg]
            dfn = d_dev + gd[tg]
            eta_h = mu + h + att[hi] + dfn[ai]
            eta_a = mu + att[ai] + dfn[hi]
            lam_h, lam_a = np.exp(eta_h), np.exp(eta_a)
            nll = np.sum(w * (lam_h - yh * eta_h)) + np.sum(w * (lam_a - ya * eta_a))
            nll += 0.5 * reg * (a_dev @ a_dev + d_dev @ d_dev)
            nll += 0.5 * reg_group * (ga[:-1] @ ga[:-1] + gd[:-1] @ gd[:-1])
            r_h = w * (lam_h - yh)
            r_a = w * (lam_a - ya)
            g_att = np.bincount(hi, r_h, n) + np.bincount(ai, r_a, n)
            g_dfn = np.bincount(ai, r_h, n) + np.bincount(hi, r_a, n)
            grad = np.empty_like(theta)
            grad[0] = r_h.sum() + r_a.sum()
            grad[1] = r_h.sum()
            grad[2:2 + n] = g_att + reg * a_dev
            grad[2 + n:2 + 2 * n] = g_dfn + reg * d_dev
            grad[2 + 2 * n:2 + 2 * n + n_groups] = np.bincount(tg, g_att, n_groups + 1)[:-1] + reg_group * ga[:-1]
            grad[2 + 2 * n + n_groups:] = np.bincount(tg, g_dfn, n_groups + 1)[:-1] + reg_group * gd[:-1]
            return nll, grad

        mean_goals = max((yh.sum() + ya.sum()) / (2 * len(yh)), 1e-3)
        theta0 = np.zeros(2 + 2 * n + 2 * n_groups)
        theta0[0] = math.log(mean_goals)
        result = minimize(objective, theta0, jac=True, method="L-BFGS-B", options={"maxiter": 1000})
        if not result.success:
            logger.warning("Rating fit did not fully converge: %s", result.message)

        mu, h, a_dev, d_dev, ga, gd = unpack(result.x)
        self.mu, self.home_adv = float(mu), float(h)
        self.att = a_dev + ga[tg]
        self.dfn = d_dev + gd[tg]
        self.match_counts = np.bincount(hi, minlength=n) + np.bincount(ai, minlength=n)
        self.n_matches_fitted = len(yh)
        return self

    def team_matches(self, team_id: str) -> int:
        idx = self.team_index.get(team_id)
        return 0 if idx is None or self.match_counts is None else int(self.match_counts[idx])

    def predict(self, home_id: str, away_id: str, neutral: bool = False) -> Optional[MatchLambdas]:
        """Expected goals for a fixture, or None when either team has too little data."""
        if self.att is None:
            return None
        hm, am = self.team_matches(home_id), self.team_matches(away_id)
        if hm < self.min_team_matches or am < self.min_team_matches:
            return None
        h, a = self.team_index[home_id], self.team_index[away_id]
        adv = 0.0 if neutral else self.home_adv
        lam_h = math.exp(self.mu + adv + self.att[h] + self.dfn[a])
        lam_a = math.exp(self.mu + self.att[a] + self.dfn[h])
        return MatchLambdas(home=lam_h, away=lam_a, home_matches=hm, away_matches=am)


# ---------------------------------------------------------------------------
# Database-backed, per-day cached access
# ---------------------------------------------------------------------------

_cache: Dict[Tuple[str, str], GlobalPoissonRatings] = {}
_cache_lock = threading.Lock()


def _day_start_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    moment = moment.astimezone(timezone.utc)
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


def domestic_groups(
    home_ids: Sequence[str],
    away_ids: Sequence[str],
    competition_names: Sequence[Optional[str]],
    competition_ids: Optional[Sequence[Optional[str]]] = None,
) -> Dict[str, str]:
    """Map each team to its most frequent domestic-league competition.

    Groups are keyed by ``competition_ids`` when given: competition names are
    not unique (14 competitions are called "Premier League", Germany's and
    Austria's top flights are both "Bundesliga"), so keying by name would
    merge unrelated leagues into one group strength. The name is only used to
    skip multi-country competitions, qualifiers and friendlies (see
    NON_DOMESTIC_MARKERS). Without ids the name is the key.
    """
    keys = competition_ids if competition_ids is not None else competition_names
    counts: Dict[str, Dict[str, int]] = {}
    for h, a, name, key in zip(home_ids, away_ids, competition_names, keys):
        if key is None or not is_domestic_league_name(name):
            continue
        key = str(key)
        for team in (h, a):
            team_counts = counts.setdefault(team, {})
            team_counts[key] = team_counts.get(key, 0) + 1
    return {team: max(c, key=c.get) for team, c in counts.items() if c}


def fit_ratings_from_db(db_session, cutoff: datetime, **kwargs) -> Optional[GlobalPoissonRatings]:
    """Fit ratings on finished matches scheduled strictly before ``cutoff``."""
    from app.database.models import Competition as DBCompetition
    from app.database.models import Match as DBMatch
    from app.domain.enums import MatchStatus

    cutoff_naive = cutoff.astimezone(timezone.utc).replace(tzinfo=None)
    since = cutoff_naive - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    rows = (
        db_session.query(
            DBMatch.home_team_id, DBMatch.away_team_id,
            DBMatch.home_score, DBMatch.away_score, DBMatch.scheduled_at,
            DBCompetition.name, DBMatch.competition_id,
            DBMatch.home_xg, DBMatch.away_xg,
        )
        .outerjoin(DBCompetition, DBCompetition.id == DBMatch.competition_id)
        .filter(
            DBMatch.status == MatchStatus.FINISHED,
            DBMatch.scheduled_at < cutoff_naive,
            DBMatch.scheduled_at >= since,
            DBMatch.home_score.isnot(None),
            DBMatch.away_score.isnot(None),
        )
        .all()
    )
    if not rows:
        return None
    ages = []
    for r in rows:
        played = r.scheduled_at
        if played.tzinfo is not None:
            played = played.astimezone(timezone.utc).replace(tzinfo=None)
        ages.append(max((cutoff_naive - played).total_seconds() / 86400.0, 0.0))
    home_ids = [r[0] for r in rows]
    away_ids = [r[1] for r in rows]
    groups = (
        domestic_groups(home_ids, away_ids, [r[5] for r in rows], [r[6] for r in rows])
        if USE_LEAGUE_GROUPS else None
    )
    w = XG_GOAL_WEIGHT

    def target(goals, xg):
        # Goals/xG blend where FotMob xG exists; goals alone otherwise.
        return goals if xg is None or w >= 1.0 else w * goals + (1.0 - w) * float(xg)

    return GlobalPoissonRatings(**kwargs).fit(
        home_ids,
        away_ids,
        [target(r[2], r[7]) for r in rows],
        [target(r[3], r[8]) for r in rows],
        ages,
        team_groups=groups,
    )


def get_ratings_for_match_day(db_session, kickoff: datetime) -> Optional[GlobalPoissonRatings]:
    """Ratings fitted on everything before the kickoff day (UTC), cached per day.

    Using the day start as cutoff means all fixtures on the same day share one
    fit and no same-day result can leak into another same-day prediction.
    """
    cutoff = _day_start_utc(kickoff)
    key = (str(db_session.get_bind().url), cutoff.date().isoformat())
    with _cache_lock:
        cached = _cache.get(key)
    if cached is not None:
        return cached
    ratings = fit_ratings_from_db(db_session, cutoff)
    if ratings is not None:
        with _cache_lock:
            _cache[key] = ratings
        logger.info(
            "Fitted global ratings for %s: %d matches, %d teams, home_adv=%.3f",
            cutoff.date(), ratings.n_matches_fitted, len(ratings.team_index), ratings.home_adv,
        )
    return ratings
