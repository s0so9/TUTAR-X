"""Trained goal layer applied on top of the global rating lambdas.

Fitted by scripts/training/fit_goal_layer.py on out-of-sample rating
predictions (config/goal_model.json, with its held-out validation). Raw rating
lambdas spread total goals too far from the average: matches predicted to be
low-scoring produced more goals than predicted and vice versa. The layer
shrinks the total toward the mean in log space and leaves the home/away
supremacy unchanged:

    s = (ln λh + ln λa) / 2,  d = (ln λh − ln λa) / 2
    s' = m + a (s − m) + b,   λh' = e^(s' + d),  λa' = e^(s' − d)

It also provides the fitted Dixon-Coles rho and negative-binomial dispersion.
A missing or unreadable config means the identity layer (no change).
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "goal_model.json"


@dataclass(frozen=True)
class GoalLayer:
    m: float = 0.0
    a: float = 1.0
    b: float = 0.0
    rho: Optional[float] = None
    nb_dispersion: Optional[float] = None
    trained: bool = False

    def adjust(self, lambda_home: float, lambda_away: float) -> Tuple[float, float]:
        if not self.trained or lambda_home <= 0 or lambda_away <= 0:
            return lambda_home, lambda_away
        s = (math.log(lambda_home) + math.log(lambda_away)) / 2
        d = (math.log(lambda_home) - math.log(lambda_away)) / 2
        s2 = self.m + self.a * (s - self.m) + self.b
        return math.exp(s2 + d), math.exp(s2 - d)


@lru_cache(maxsize=1)
def get_goal_layer(path: Path = CONFIG_PATH) -> GoalLayer:
    try:
        params = json.loads(path.read_text(encoding="utf-8"))["params"]
        layer = GoalLayer(
            m=float(params["m"]),
            a=float(params["a"]),
            b=float(params["b"]),
            rho=float(params["rho"]) if params.get("rho") is not None else None,
            nb_dispersion=float(params["nb_dispersion"]) if params.get("nb_dispersion") else None,
            trained=True,
        )
        if not (0.0 < layer.a <= 1.5 and -1.0 < (layer.rho or 0.0) < 1.0):
            raise ValueError(f"implausible goal-layer parameters: {params}")
        return layer
    except FileNotFoundError:
        logger.warning("Goal layer config not found at %s; using identity layer", path)
    except Exception as e:
        logger.error("Goal layer config unreadable (%s); using identity layer", e)
    return GoalLayer()
