"""Starting-XI market value and unavailable players from FotMob lineups.

The rating model only sees scores, so it cannot tell a dominant team in a
weak league from an elite squad (2026-10-13: Viking vs Bayern). FotMob's match
details carry the (predicted or confirmed) starting XI's total market value
and the list of injured/suspended players. Injured players are absent from the
predicted XI, so their loss already shows up in the starter value.

Adjustment (fitted by maximum likelihood on goals of 529 European cup matches,
2025-09 to 2026-09, on top of ratings whose league groups are keyed by
competition id; weekly refits, no look-ahead). Held-out 1X2 log loss on the
123 matches from 2026-03-01: ratings only 0.946, ratings + squad value 0.936
(β fitted on the earlier 406 matches: 0.034). β below is the full-sample fit.
Refitted 2026-10-13: the earlier 0.116 was fitted on name-grouped ratings and
partly compensated for unrelated leagues sharing one group strength.

    λ_home · exp(β·x),  λ_away · exp(−β·x),  x = ln(V_home / V_away)

Caveats: FotMob market values are current estimates (not as of each past
match), and past matches used confirmed line-ups while upcoming ones use
predicted line-ups. FotMob is an unofficial source; failures mean "no
adjustment", never an invented value.

Unavailable players are only reported before the match is finished. For
finished matches FotMob's ``unavailable`` list is mostly empty or absent
(checked 2026-10-13 on the last 8 finished UCL matches: 4 of 16 sides had no
key, the rest 0-1 players), so it is not the pre-match injury report. There,
and whenever the key is absent, ``unavailable`` is None ("no data"), never an
empty list read as "nobody missing". Confirmed pre-kickoff line-ups keep their
list (2026-10-13 Lens-Sporting: confirmed XI, 4 and 3 players listed).
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

SQUAD_VALUE_BETA = 0.048
# Within-league fixtures: fitted jointly with the lineup-form adjustment on
# 2,462 walk-forward domestic and cup matches (scripts/training/
# experiment_lineup_strength.py; held-out 894 matches, 1X2 log loss
# 0.9716 -> 0.9615 with both). The ratings already separate teams of one
# league, so the value signal is weaker there than across leagues.
SQUAD_VALUE_BETA_DOMESTIC = 0.0279
CACHE_TTL_SECONDS = 600
REQUEST_TIMEOUT_SECONDS = 6.0


@dataclass(frozen=True)
class UnavailablePlayer:
    name: Optional[str]
    reason: Optional[str]          # FotMob type, e.g. "injury", "suspension"
    expected_return: Optional[str]
    market_value: Optional[float]


@dataclass(frozen=True)
class TeamSquadInfo:
    team_name: Optional[str]
    starter_value: Optional[float]
    lineup_type: Optional[str]     # "predicted" before kickoff, otherwise confirmed
    # None = no usable injury/suspension data (key absent or match finished);
    # [] = FotMob reported nobody missing before the match.
    unavailable: Optional[List[UnavailablePlayer]] = None
    # FotMob team id and starting-XI player ids (predicted before kickoff),
    # used by the lineup-form adjustment (app.prediction.lineup_form).
    team_id: Optional[str] = None
    starter_ids: List[str] = field(default_factory=list)


_cache: Dict[str, Tuple[float, Optional[Tuple[TeamSquadInfo, TeamSquadInfo]]]] = {}
_lock = threading.Lock()


def _parse_unavailable(team: dict, match_finished: bool) -> Optional[List[UnavailablePlayer]]:
    """Unavailable players, or None when FotMob gives no usable pre-match list."""
    raw = team.get("unavailable")
    if match_finished or not isinstance(raw, list):
        return None
    unavailable = []
    for u in raw:
        info = u.get("unavailability") or {}
        unavailable.append(UnavailablePlayer(
            name=u.get("name"),
            reason=info.get("type"),
            expected_return=info.get("expectedReturn"),
            market_value=u.get("marketValue"),
        ))
    return unavailable


def _parse_side(team: dict, lineup_type: Optional[str], match_finished: bool = False) -> TeamSquadInfo:
    unavailable = _parse_unavailable(team, match_finished)
    value = team.get("totalStarterMarketValue")
    starters = [str(p["id"]) for p in team.get("starters") or [] if isinstance(p, dict) and p.get("id") is not None]
    return TeamSquadInfo(
        team_name=team.get("name"),
        starter_value=float(value) if value else None,
        lineup_type=lineup_type,
        unavailable=unavailable,
        team_id=str(team["id"]) if team.get("id") is not None else None,
        starter_ids=starters,
    )


def invalidate_squad_info(fotmob_match_id: str) -> None:
    """Drop the cached line-up of a match so the next prediction reads it again (used right
    before the headline picks are frozen: the line-up may have been published within the last
    CACHE_TTL_SECONDS)."""
    with _lock:
        _cache.pop(str(fotmob_match_id), None)


def fetch_squad_info(fotmob_match_id: str, base_url: str) -> Optional[Tuple[TeamSquadInfo, TeamSquadInfo]]:
    """(home, away) squad info for a FotMob match, cached; None when unavailable."""
    now = time.monotonic()
    with _lock:
        hit = _cache.get(fotmob_match_id)
        if hit and now - hit[0] < CACHE_TTL_SECONDS:
            return hit[1]
    result = None
    try:
        with httpx.Client(base_url=base_url.rstrip("/"), timeout=REQUEST_TIMEOUT_SECONDS,
                          follow_redirects=True) as client:
            response = client.get("/api/data/matchDetails", params={"matchId": fotmob_match_id})
            response.raise_for_status()
            payload = response.json() or {}
            lineup = (payload.get("content") or {}).get("lineup") or {}
            status = (payload.get("header") or {}).get("status") or {}
            finished = bool((payload.get("general") or {}).get("finished") or status.get("finished"))
        if lineup.get("homeTeam") and lineup.get("awayTeam"):
            lineup_type = lineup.get("lineupType")
            result = (
                _parse_side(lineup["homeTeam"], lineup_type, finished),
                _parse_side(lineup["awayTeam"], lineup_type, finished),
            )
    except Exception as e:
        logger.warning("FotMob lineup fetch failed for %s: %s", fotmob_match_id, e)
    with _lock:
        _cache[fotmob_match_id] = (now, result)
    return result


def squad_value_multipliers(
    home_value: Optional[float], away_value: Optional[float], beta: float = SQUAD_VALUE_BETA
) -> Optional[Tuple[float, float, float]]:
    """(home_multiplier, away_multiplier, log_ratio), or None without both values."""
    if not home_value or not away_value or home_value <= 0 or away_value <= 0:
        return None
    x = math.log(home_value / away_value)
    return math.exp(beta * x), math.exp(-beta * x), x
