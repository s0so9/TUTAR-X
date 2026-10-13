"""Player impact engine - DETERMINISTIC, DATA-DRIVEN ONLY.

This module calculates lineup change effects using ONLY historical data.
NEVER fabricates player ratings or statistics.

Impact calculation:
- attacking_strength_adjustment: Based on absent players' historical xG contribution
- defensive_strength_adjustment: Based on absent defenders' historical xGA reduction
- expected_goals_adjustment: Combined xG impact
- prob_adjustments: Impact on match probabilities

If insufficient historical data: returns ModelAvailability explicitly.

The second part of this module (``PlayerImpactRatings``, below the legacy engine) reads
the as-of xG-RAPM player ratings trained by scripts/training/player_impact.py and gives
the offence/defence strength of a starting XI and its difference to the team's usual XI.
It is NOT wired into the live prediction pipeline yet (docs/training/player-impact-pipeline.md).
"""

from __future__ import annotations

import csv
import gzip
import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

from app.prediction.interfaces import ModelPrediction, ModelAvailability


@dataclass
class PlayerImpactData:
    """Historical impact data for a single player."""

    player_id: str
    player_name: str
    position: str

    # Historical statistics (REAL DATA ONLY)
    matches_played: int
    avg_xg_contribution: Optional[float] = None
    """Average xG contribution per 90 minutes"""

    avg_xa_contribution: Optional[float] = None
    """Average xA (expected assists) per 90 minutes"""

    avg_defensive_contribution: Optional[float] = None
    """Average defensive impact (xGA prevented) per 90 minutes"""

    minutes_played: int = 0

    @property
    def has_sufficient_data(self) -> bool:
        """Whether player has sufficient historical data."""
        return self.matches_played >= 5 and self.minutes_played >= 450


@dataclass
class TeamLineupImpact:
    """Impact of lineup changes for a team."""

    team_id: str

    # Absent players
    absent_players: List[PlayerImpactData]

    # Calculated impacts
    attacking_strength_delta: float = 0.0
    """Change in attacking strength (positive = stronger, negative = weaker)"""

    defensive_strength_delta: float = 0.0
    """Change in defensive strength (positive = stronger, negative = weaker)"""

    expected_goals_delta: float = 0.0
    """Net change in expected goals"""

    confidence: float = 1.0
    """Confidence in impact assessment [0, 1]"""

    data_sufficiency: str = "complete"
    """Data sufficiency: complete, partial, or insufficient"""


@dataclass
class PlayerImpactResult:
    """Result of player impact analysis."""

    home_team_impact: TeamLineupImpact
    away_team_impact: TeamLineupImpact

    adjusted_home_xg: float
    adjusted_away_xg: float

    prob_adjustments: Dict[str, float]
    """Adjustments to probabilities: {"home_win": +0.02, "draw": -0.01, "away_win": -0.01}"""

    overall_confidence: float
    """Overall confidence in player impact assessment [0, 1]"""


class PlayerImpactEngine:
    """DETERMINISTIC, DATA-DRIVEN player impact engine.

    NEVER fabricates player data.
    Returns ModelAvailability when data insufficient.
    """

    MIN_PLAYER_MATCHES = 5
    """Minimum matches for reliable player statistics"""

    MIN_PLAYER_MINUTES = 450
    """Minimum minutes (roughly 5 full matches)"""

    def __init__(self):
        """Initialize player impact engine."""
        pass

    def calculate_impact(
        self,
        base_prediction: ModelPrediction,
        home_absent_players: List[PlayerImpactData],
        away_absent_players: List[PlayerImpactData]
    ) -> PlayerImpactResult | ModelAvailability:
        """Calculate player impact on prediction.

        Args:
            base_prediction: Base prediction without player adjustments
            home_absent_players: List of absent home players with historical data
            away_absent_players: List of absent away players with historical data

        Returns:
            PlayerImpactResult or ModelAvailability if insufficient data
        """
        # Calculate home team impact
        home_impact = self._calculate_team_impact("home", home_absent_players)

        # Calculate away team impact
        away_impact = self._calculate_team_impact("away", away_absent_players)

        # Check data sufficiency
        if (home_impact.data_sufficiency == "insufficient" or
            away_impact.data_sufficiency == "insufficient"):
            return ModelAvailability(
                model_id="player_impact_v1",
                available=False,
                reason="insufficient_player_data",
                missing_features=[
                    f"Insufficient data for {len(home_absent_players)} home players, "
                    f"{len(away_absent_players)} away players"
                ]
            )

        # Apply impacts to expected goals
        adjusted_home_xg = base_prediction.home_score_mean + home_impact.expected_goals_delta
        adjusted_away_xg = base_prediction.away_score_mean + away_impact.expected_goals_delta

        # Ensure non-negative
        adjusted_home_xg = max(0.1, adjusted_home_xg)
        adjusted_away_xg = max(0.1, adjusted_away_xg)

        # Calculate probability adjustments
        prob_adjustments = self._calculate_probability_adjustments(
            base_prediction.home_score_mean,
            base_prediction.away_score_mean,
            adjusted_home_xg,
            adjusted_away_xg
        )

        # Overall confidence (lower if partial data)
        overall_confidence = min(home_impact.confidence, away_impact.confidence)
        if home_impact.data_sufficiency == "partial" or away_impact.data_sufficiency == "partial":
            overall_confidence *= 0.7

        return PlayerImpactResult(
            home_team_impact=home_impact,
            away_team_impact=away_impact,
            adjusted_home_xg=adjusted_home_xg,
            adjusted_away_xg=adjusted_away_xg,
            prob_adjustments=prob_adjustments,
            overall_confidence=overall_confidence
        )

    def _calculate_team_impact(
        self,
        team_side: str,
        absent_players: List[PlayerImpactData]
    ) -> TeamLineupImpact:
        """Calculate impact of absent players for a team.

        Args:
            team_side: "home" or "away"
            absent_players: List of absent players with historical data

        Returns:
            TeamLineupImpact
        """
        if not absent_players:
            return TeamLineupImpact(
                team_id=team_side,
                absent_players=[],
                attacking_strength_delta=0.0,
                defensive_strength_delta=0.0,
                expected_goals_delta=0.0,
                confidence=1.0,
                data_sufficiency="complete"
            )

        # Calculate impacts from historical data
        attacking_delta = 0.0
        defensive_delta = 0.0
        players_with_data = 0
        total_players = len(absent_players)

        for player in absent_players:
            if not player.has_sufficient_data:
                continue

            players_with_data += 1

            # Attacking contribution
            if player.avg_xg_contribution is not None:
                attacking_delta -= player.avg_xg_contribution

            if player.avg_xa_contribution is not None:
                attacking_delta -= player.avg_xa_contribution * 0.5  # xA worth ~50% of xG

            # Defensive contribution
            if player.avg_defensive_contribution is not None:
                defensive_delta -= player.avg_defensive_contribution

        # Determine data sufficiency
        if players_with_data == 0:
            data_sufficiency = "insufficient"
            confidence = 0.0
        elif players_with_data < total_players / 2:
            data_sufficiency = "partial"
            confidence = 0.5
        else:
            data_sufficiency = "complete"
            confidence = min(1.0, players_with_data / total_players)

        # Net expected goals impact
        # Attacking impact reduces goals scored
        # Defensive impact increases goals conceded (opponent scores more)
        expected_goals_delta = attacking_delta

        return TeamLineupImpact(
            team_id=team_side,
            absent_players=absent_players,
            attacking_strength_delta=attacking_delta,
            defensive_strength_delta=defensive_delta,
            expected_goals_delta=expected_goals_delta,
            confidence=confidence,
            data_sufficiency=data_sufficiency
        )

    def _calculate_probability_adjustments(
        self,
        base_home_xg: float,
        base_away_xg: float,
        adjusted_home_xg: float,
        adjusted_away_xg: float
    ) -> Dict[str, float]:
        """Calculate probability adjustments from xG changes.

        Uses simplified Poisson approximation to estimate probability shifts.

        Args:
            base_home_xg: Base home expected goals
            base_away_xg: Base away expected goals
            adjusted_home_xg: Adjusted home expected goals
            adjusted_away_xg: Adjusted away expected goals

        Returns:
            Dictionary with probability deltas
        """
        # Calculate approximate probability change
        # Simplified: ΔP(home win) ≈ (Δλ_home - Δλ_away) * scaling_factor

        home_xg_delta = adjusted_home_xg - base_home_xg
        away_xg_delta = adjusted_away_xg - base_away_xg

        # Empirical scaling factor (calibrated from historical data)
        scaling_factor = 0.15  # 1 xG change ≈ 15% probability change

        home_win_delta = (home_xg_delta - away_xg_delta) * scaling_factor
        away_win_delta = -(home_xg_delta - away_xg_delta) * scaling_factor
        draw_delta = -(home_win_delta + away_win_delta)

        # Bound adjustments to reasonable range
        home_win_delta = max(-0.15, min(0.15, home_win_delta))
        away_win_delta = max(-0.15, min(0.15, away_win_delta))
        draw_delta = max(-0.10, min(0.10, draw_delta))

        return {
            "home_win": home_win_delta,
            "draw": draw_delta,
            "away_win": away_win_delta
        }


# =============================================================================
# As-of xG-RAPM player ratings (stage A of the player-impact pipeline)
# =============================================================================
#
# Ratings file: data/training/player_impact_asof.csv.gz written by
# scripts/training/player_impact.py, one row per (cutoff, player). A cutoff's ratings were
# fitted only on matches that kicked off before the cutoff date, so ratings of cutoff c may be
# used for any match on or after c. Units: xG per 90 minutes relative to an average player;
# offence = xG the player adds to his side, defence = xG he takes away from the opponent
# (positive is better for both).
#
# Players without a rating at that cutoff are NEVER silently treated as average: they get the
# replacement level of their position (mean of fringe players, < 450 minutes before the
# cutoff), and are listed in ``unknown_player_ids`` so the caller can see and judge it.

RAPM_RATINGS_PATH = Path(__file__).resolve().parents[2] / "data" / "training" / "player_impact_asof.csv.gz"
RAPM_META_PATH = RAPM_RATINGS_PATH.with_name("player_impact_meta.json")
RAPM_POSITIONS = ("GK", "DEF", "MID", "FWD")
RAPM_FRINGE_MINUTES = 450.0
DEFAULT_USUAL_LINEUPS = 10
MIN_USUAL_LINEUPS = 3

DateLike = Union[str, date, datetime]


@dataclass(frozen=True)
class PlayerRating:
    """One player's as-of rating (values exactly as stored in the ratings file)."""

    player_id: str
    team_id: Optional[str]
    position: Optional[str]
    offence: float
    defence: float
    prior_offence: float
    prior_defence: float
    minutes: float
    rapm_minutes: float
    flags: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PlayerContribution:
    player_id: str
    offence: float
    defence: float
    source: str                 # "rated" or "replacement:<position>"
    position: Optional[str]


@dataclass(frozen=True)
class XIStrength:
    """Sum of the players' offence and defence values (xG per 90 vs an average XI)."""

    cutoff: str
    offence: float
    defence: float
    n_players: int
    n_rated: int
    unknown_player_ids: Tuple[str, ...]
    contributions: Tuple[PlayerContribution, ...]
    flags: Tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        """True when every player has his own rating (no replacement level used)."""
        return not self.unknown_player_ids


@dataclass(frozen=True)
class XIComparison:
    """A given XI against the mean of the team's recent line-ups, both at the same rating cutoff.

    ``available`` is False (deltas None, ``reason`` set) when there are too few earlier
    line-ups to define the usual XI: insufficient data is reported, never filled in.
    """

    available: bool
    reason: Optional[str]
    xi: XIStrength
    usual_offence: Optional[float] = None
    usual_defence: Optional[float] = None
    offence_delta: Optional[float] = None
    defence_delta: Optional[float] = None
    n_usual_lineups: int = 0
    usual_unknown_share: Optional[float] = None
    flags: Tuple[str, ...] = ()


def _as_date(value: Optional[DateLike]) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _float(value: Optional[str]) -> Optional[float]:
    if value is None or value == "":
        return None
    out = float(value)
    return out if math.isfinite(out) else None


class PlayerImpactRatings:
    """As-of player ratings of one cutoff, with XI strength helpers (not wired into live predictions)."""

    def __init__(self, cutoff: str, ratings: Dict[str, PlayerRating],
                 replacement: Dict[str, Tuple[float, float]], source: Optional[str] = None):
        if not ratings:
            raise ValueError("no player ratings for this cutoff")
        self.cutoff = cutoff
        self.ratings = ratings
        self.replacement = replacement
        self.source = source

    # ------------------------------------------------------------------ loading
    @staticmethod
    def available_cutoffs(path: Union[str, Path] = RAPM_RATINGS_PATH) -> List[str]:
        cutoffs = set()
        with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                cutoffs.add(row["cutoff"])
        return sorted(cutoffs)

    @classmethod
    def load(cls, path: Union[str, Path] = RAPM_RATINGS_PATH, as_of: Optional[DateLike] = None,
             meta_path: Optional[Union[str, Path]] = None) -> "PlayerImpactRatings":
        """Ratings of the latest cutoff on or before ``as_of`` (default: the latest cutoff).

        A cutoff c was fitted on matches before c, so it is safe for any match on or after c.
        Raises ValueError when the file has no cutoff on or before ``as_of``.
        """
        return _load_ratings(str(path), None if as_of is None else _as_date(as_of).isoformat(),
                             None if meta_path is None else str(meta_path))

    # ------------------------------------------------------------------ queries
    def get(self, player_id: Union[str, int]) -> Optional[PlayerRating]:
        return self.ratings.get(str(player_id))

    def contribution(self, player_id: Union[str, int], position: Optional[str] = None) -> PlayerContribution:
        pid = str(player_id)
        rating = self.ratings.get(pid)
        if rating is not None:
            return PlayerContribution(pid, rating.offence, rating.defence, "rated", rating.position)
        pos = position if position in RAPM_POSITIONS else "UNK"
        off, dfn = self.replacement.get(pos) or self.replacement["UNK"]
        return PlayerContribution(pid, off, dfn, f"replacement:{pos}", position)

    def xi_strength(self, player_ids: Sequence[Union[str, int]],
                    positions: Optional[Dict[str, str]] = None) -> XIStrength:
        """Offence/defence of a line-up. ``positions`` (player id -> GK/DEF/MID/FWD) is only used
        for players without a rating, to pick their replacement level."""
        ids = [str(p) for p in player_ids]
        if not ids:
            raise ValueError("empty line-up")
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate player ids in line-up")
        positions = {str(k): v for k, v in (positions or {}).items()}
        contribs = tuple(self.contribution(pid, positions.get(pid)) for pid in ids)
        unknown = tuple(c.player_id for c in contribs if c.source != "rated")
        flags = [] if len(ids) == 11 else [f"xi_size_{len(ids)}"]
        if unknown:
            flags.append("replacement_level_used")
        return XIStrength(
            cutoff=self.cutoff,
            offence=sum(c.offence for c in contribs),
            defence=sum(c.defence for c in contribs),
            n_players=len(ids),
            n_rated=len(ids) - len(unknown),
            unknown_player_ids=unknown,
            contributions=contribs,
            flags=tuple(flags),
        )

    def compare_to_usual(self, player_ids: Sequence[Union[str, int]],
                         recent_lineups: Sequence[Sequence[Union[str, int]]],
                         positions: Optional[Dict[str, str]] = None,
                         last_n: int = DEFAULT_USUAL_LINEUPS,
                         min_lineups: int = MIN_USUAL_LINEUPS) -> XIComparison:
        """Given XI minus the mean strength of the team's last ``last_n`` line-ups.

        ``recent_lineups`` must be the team's earlier starting XIs, most recent LAST, and must
        not include the match being predicted. Both sides are valued with this cutoff's
        ratings, so the difference reflects personnel, not rating drift.
        """
        xi = self.xi_strength(player_ids, positions)
        usable = [list(l) for l in recent_lineups if l][-last_n:] if last_n > 0 else []
        if len(usable) < min_lineups:
            return XIComparison(False, f"usual_xi_needs_{min_lineups}_lineups_has_{len(usable)}", xi,
                                n_usual_lineups=len(usable), flags=xi.flags)
        usual = [self.xi_strength(l, positions) for l in usable]
        u_off = sum(u.offence for u in usual) / len(usual)
        u_def = sum(u.defence for u in usual) / len(usual)
        n_players = sum(u.n_players for u in usual)
        unknown_share = sum(len(u.unknown_player_ids) for u in usual) / n_players if n_players else None
        flags = list(xi.flags)
        if unknown_share:
            flags.append("usual_xi_replacement_level_used")
        return XIComparison(True, None, xi, u_off, u_def, xi.offence - u_off, xi.defence - u_def,
                            len(usual), unknown_share, tuple(flags))


def replacement_from_rows(rows: Sequence[PlayerRating],
                          fringe_minutes: float = RAPM_FRINGE_MINUTES) -> Dict[str, Tuple[float, float]]:
    """Replacement level per position: mean offence/defence of fringe players (< fringe_minutes).

    Used when the meta file is absent; the training script stores the same quantity per cutoff
    (computed from its prior weights) in player_impact_meta.json.
    """
    out: Dict[str, Tuple[float, float]] = {}
    fringe = [r for r in rows if r.minutes < fringe_minutes]
    pool_all = fringe or list(rows)
    for pos in RAPM_POSITIONS + ("UNK",):
        pool = [r for r in fringe if r.position == pos] if pos != "UNK" else pool_all
        if len(pool) < 5:
            pool = pool_all
        out[pos] = (sum(r.offence for r in pool) / len(pool), sum(r.defence for r in pool) / len(pool))
    return out


@lru_cache(maxsize=8)
def _load_ratings(path: str, as_of: Optional[str], meta_path: Optional[str]) -> PlayerImpactRatings:
    # one pass, keeping only the rows of the latest eligible cutoff seen so far
    cutoff: Optional[str] = None
    first_cutoff: Optional[str] = None
    kept: List[List[str]] = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        col = {name: k for k, name in enumerate(header)}
        ci = col["cutoff"]
        for row in reader:
            c = row[ci]
            if first_cutoff is None or c < first_cutoff:
                first_cutoff = c
            if as_of is not None and c > as_of:
                continue
            if cutoff is None or c > cutoff:
                cutoff, kept = c, [row]
            elif c == cutoff:
                kept.append(row)
    if cutoff is None:
        raise ValueError(f"no rating cutoff on or before {as_of} in {path} (first: {first_cutoff})")

    def get(row: List[str], name: str) -> Optional[str]:
        k = col.get(name)
        return row[k] if k is not None and k < len(row) else None

    ratings: Dict[str, PlayerRating] = {}
    for row in kept:
        offence, defence = _float(get(row, "offence")), _float(get(row, "defence"))
        if offence is None or defence is None:
            continue  # never invent a value for a malformed row
        pid = get(row, "player_id")
        ratings[pid] = PlayerRating(
            player_id=pid,
            team_id=get(row, "team_id") or None,
            position=get(row, "position") or None,
            offence=offence,
            defence=defence,
            prior_offence=_float(get(row, "prior_offence")) or 0.0,
            prior_defence=_float(get(row, "prior_defence")) or 0.0,
            minutes=_float(get(row, "minutes")) or 0.0,
            rapm_minutes=_float(get(row, "rapm_minutes")) or 0.0,
            flags=tuple(x for x in (get(row, "flags") or "").split(";") if x),
        )
    replacement = None
    mpath = Path(meta_path) if meta_path else Path(path).with_name("player_impact_meta.json")
    try:
        meta = json.loads(mpath.read_text(encoding="utf-8"))
        for entry in meta.get("per_cutoff") or []:
            if entry.get("cutoff") == cutoff and entry.get("replacement_level"):
                replacement = {pos: (float(v["offence"]), float(v["defence"]))
                               for pos, v in entry["replacement_level"].items()}
                break
    except (OSError, ValueError, KeyError, TypeError):
        replacement = None
    if not replacement or "UNK" not in replacement:
        replacement = replacement_from_rows(list(ratings.values()))
    return PlayerImpactRatings(cutoff, ratings, replacement, source=path)
