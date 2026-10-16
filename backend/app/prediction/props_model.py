"""Cards, corners and shots ("props") for a match from the trained count models.

Config: ``backend/config/props_model.json`` (written from
``backend/data/training/props_model_candidate.json`` after the audit; see
docs/training/2026-10-14-props-model.md). Absent or invalid config -> disabled.

Per stat (yellow_cards, corners, total_shots, shots_on_target):
    mu_home = exp(c + comp + h + attack[home] + concede[away] + referee)
    mu_away = exp(c + comp + attack[away] + concede[home] + referee)
Counts are negative binomial with the stat's dispersion r (var = mu + mu^2 / r);
match totals are the convolution of the two sides (independence). Unknown
teams/referees/competitions contribute 0 (the competition mean) and are flagged.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.stats import nbinom

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "props_model.json"

# stat key in the config -> (team market key, total market key, Turkish noun)
STAT_MARKETS = {
    "yellow_cards": ("team_yellow_cards", "total_yellow_cards", "sarı kart", "Kartlar"),
    "corners": ("team_corners", "total_corners", "korner", "Kornerler"),
    "total_shots": ("team_shots", "total_shots", "şut", "Şutlar"),
    "shots_on_target": ("team_shots_on_target", "total_shots_on_target", "isabetli şut", "Şutlar"),
}
MAX_COUNT = 80


@dataclass
class StatModel:
    key: str
    dispersion: float
    total_dispersion: Optional[float]
    intercept: float
    home_advantage: float
    competitions: dict
    teams: dict
    referees: dict

    def mus(self, home: str, away: str, competition: Optional[str], referee: Optional[str]):
        comp = float(self.competitions.get(str(competition), 0.0)) if competition is not None else 0.0
        ref = 0.0
        if referee and self.referees:
            entry = self.referees.get(referee)
            if isinstance(entry, dict):
                ref = float(entry.get("offset", 0.0))
        th, ta = self.teams.get(str(home)) or {}, self.teams.get(str(away)) or {}
        base = self.intercept + comp + ref
        mu_h = math.exp(base + self.home_advantage + float(th.get("attack", 0.0)) + float(ta.get("concede", 0.0)))
        mu_a = math.exp(base + float(ta.get("attack", 0.0)) + float(th.get("concede", 0.0)))
        return mu_h, mu_a

    def pmf(self, mu: float, size: Optional[float] = None, max_count: int = MAX_COUNT) -> np.ndarray:
        r = self.dispersion if size is None else size
        k = np.arange(max_count + 1)
        if not math.isfinite(r) or r > 1e6:
            from scipy.stats import poisson

            return poisson.pmf(k, mu)
        return nbinom.pmf(k, r, r / (r + mu))


@dataclass
class PropsModel:
    version: str
    trained_through: Optional[str]
    stats: dict[str, StatModel]
    lines: dict[str, list[float]]
    team_recent: dict = field(default_factory=dict)

    def known_team(self, stat: str, team: str) -> bool:
        return str(team) in self.stats[stat].teams

    def predict(self, home: str, away: str, competition: Optional[str], referee: Optional[str], names: dict) -> dict:
        markets = []
        unknown_teams = set()
        referee_used = False
        for stat, (team_key, total_key, noun, group) in STAT_MARKETS.items():
            model = self.stats.get(stat)
            if model is None:
                continue
            for t in (home, away):
                if str(t) not in model.teams:
                    unknown_teams.add(str(t))
            if referee and model.referees and referee in model.referees:
                referee_used = True
            mu_h, mu_a = model.mus(home, away, competition, referee)
            p_h, p_a = model.pmf(mu_h), model.pmf(mu_a)
            if model.total_dispersion:
                # the two sides' counts are correlated: the total has its own NB size
                p_tot = model.pmf(mu_h + mu_a, size=model.total_dispersion, max_count=2 * MAX_COUNT)
            else:
                p_tot = np.convolve(p_h, p_a)[: 2 * MAX_COUNT + 1]
            for side, mu, pmf in (("home", mu_h, p_h), ("away", mu_a, p_a)):
                markets.append(
                    _market(team_key, f"{names[side]} {noun}", group, side, mu, pmf, self.lines.get(team_key, []))
                )
            markets.append(
                _market(total_key, f"Toplam {noun}", group, "total", mu_h + mu_a, p_tot, self.lines.get(total_key, []))
            )
        return {
            "markets": markets,
            "unknown_teams": sorted(unknown_teams),
            "referee_used": referee_used,
        }


# Audit 2026-10-14: cards beat simple averages only barely (doubtful 0-0 card data in two
# leagues) and total corners almost never reaches 0.80, so they are never labelled banko.
NOT_BANKO = {"team_yellow_cards", "total_yellow_cards", "total_corners"}


def _market(key: str, label: str, group: str, scope: str, expected: float, pmf: np.ndarray, lines: list[float]) -> dict:
    cdf = np.cumsum(pmf)
    total_mass = float(cdf[-1]) or 1.0
    out_lines = []
    for line in lines:
        k = int(math.floor(line))
        under = float(cdf[k]) / total_mass if k < len(cdf) else 1.0
        out_lines.append({"line": line, "over": max(0.0, min(1.0, 1.0 - under)), "under": max(0.0, min(1.0, under))})
    return {
        "key": key,
        "label_tr": label,
        "group": group,
        "scope": scope,
        "expected": expected,
        "lines": out_lines,
        "banko_eligible": key not in NOT_BANKO,
    }


def _parse(raw: dict) -> PropsModel:
    stats = {}
    for key, s in (raw.get("stats") or {}).items():
        if key not in STAT_MARKETS:
            continue
        r = float(s.get("dispersion", float("inf")))
        if not (r > 0):
            raise ValueError(f"bad dispersion for {key}")
        td = s.get("total_dispersion")
        stats[key] = StatModel(
            key=key,
            dispersion=r,
            total_dispersion=float(td) if td not in (None, 0) else None,
            intercept=float(s["intercept"]),
            home_advantage=float(s.get("home_advantage", 0.0)),
            competitions={str(k): float(v) for k, v in (s.get("competitions") or {}).items()},
            teams={str(k): v for k, v in (s.get("teams") or {}).items() if isinstance(v, dict)},
            referees={str(k): v for k, v in (s.get("referees") or {}).items() if isinstance(v, dict)},
        )
    if not stats:
        raise ValueError("no usable stats")
    return PropsModel(
        version=str(raw.get("version") or "props"),
        trained_through=raw.get("trained_through"),
        stats=stats,
        lines={k: [float(x) for x in v] for k, v in (raw.get("lines") or {}).items()},
        team_recent=raw.get("team_recent") or {},
    )


_CACHE: dict[tuple[str, float], Optional[PropsModel]] = {}


def get_props_model(path: Path = CONFIG_PATH) -> Optional[PropsModel]:
    """The deployed model, re-read when the config file changes (no restart needed)."""
    try:
        mtime = Path(path).stat().st_mtime
    except (FileNotFoundError, OSError):
        return None
    key = (str(path), mtime)
    if key in _CACHE:
        return _CACHE[key]
    try:
        model: Optional[PropsModel] = _parse(json.loads(Path(path).read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 - a broken config disables the feature, never fakes numbers
        logger.exception("props model config unusable: %s", path)
        model = None
    _CACHE.clear()
    _CACHE[key] = model
    return model
