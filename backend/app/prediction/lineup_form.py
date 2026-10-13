"""Lineup-form adjustment: is today's starting XI stronger or weaker than usual?

Uses config/player_form.json (scripts/training/build_player_form.py): each
player's minutes-weighted FotMob rating from collected matches, each team's
usual XI quality, and gamma fitted walk-forward
(scripts/training/experiment_lineup_strength.py). For a fixture with a
(predicted or confirmed) line-up:

    q = (Q_home − U_home) − (Q_away − U_away),  shift = gamma · q
    λ_home · e^shift,  λ_away · e^−shift

Q is the mean rating of the starters with enough prior minutes (at least
``min_known_starters`` of them), U the team's usual XI quality. Any missing
piece means no adjustment (None), never a guessed value.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, Sequence

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "player_form.json"


class LineupForm:
    def __init__(self, gamma: float, players: Dict[str, float], usual: Dict[str, float], min_known: int):
        self.gamma = gamma
        self.players = players
        self.usual = usual
        self.min_known = min_known

    def xi_quality(self, starter_ids: Sequence[str]) -> Optional[float]:
        known = [self.players[pid] for pid in starter_ids if pid in self.players]
        if len(known) < self.min_known:
            return None
        return sum(known) / len(known)

    def shift(self, home_team: Optional[str], home_xi: Sequence[str],
              away_team: Optional[str], away_xi: Sequence[str]) -> Optional[float]:
        if not home_team or not away_team:
            return None
        qh, qa = self.xi_quality(home_xi), self.xi_quality(away_xi)
        uh, ua = self.usual.get(home_team), self.usual.get(away_team)
        if None in (qh, qa, uh, ua):
            return None
        return self.gamma * ((qh - uh) - (qa - ua))


@lru_cache(maxsize=1)
def get_lineup_form(path: Path = CONFIG_PATH) -> Optional[LineupForm]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        gamma = float(data["gamma_form"])
        if not (0.0 <= gamma <= 1.0):
            raise ValueError(f"implausible gamma_form {gamma}")
        return LineupForm(gamma, data["players"], data["teams_usual_xi"], int(data.get("min_known_starters", 7)))
    except FileNotFoundError:
        logger.info("Lineup-form config not found at %s; adjustment disabled", path)
    except Exception as e:
        logger.error("Lineup-form config unreadable (%s); adjustment disabled", e)
    return None
