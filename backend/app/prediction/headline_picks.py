"""The two headline picks of a match (Banko and Oranlı) - Python port of the frontend rule.

KEEP IN SYNC WITH THE FRONTEND:
  * frontend/src/utils/headlinePicks.ts            (selection rule, constants, tie-breaking, families)
  * frontend/src/components/match/rail/railModel.ts (buildRailRows: which markets are candidates, the
                                                    probability fallbacks, the Turkish labels)
Both implementations are tested against the SAME fixtures,
frontend/src/utils/__tests__/headlinePicks.fixtures.json (see tests/test_headline_picks.py and
frontend/src/utils/__tests__/headlinePicks.test.ts). Change the rule in both places, bump RULE_VERSION
and extend the fixtures; the tests fail when the two drift apart.

Rule "headline_v2" (owner, 2026-10-15; research: docs/research/2026-10-15-accuracy-roadmap.md, Paket 1):
  * Banko slot = the most likely candidate with 0.70 <= p <= 0.95 (above 95 % the market is barely
             priced, below 70 % it is not a banko). The slot carries a tier (banko_tier):
               "cok_guclu"  p >= 0.90
               "banko"      0.85 <= p < 0.90
               "guclu"      0.70 <= p < 0.85  (shown, but not called a banko)
  * Oranlı = among candidates of a DIFFERENT market family than the Banko slot pick, whatever its tier
             ("result" = 1X2 + double chance, "goals" = over/under lines + both teams to score), the most
             likely one that still pays: bookmaker odds >= 1.60 with p >= 0.55 and p * odds >= 1 when
             odds are known, otherwise a fair price 1 / p >= 1.60 with p >= 0.55. A priced candidate
             always wins over a fair one.
Rule "headline_v1" (2026-10-14) was the same without tiers and with the Oranlı floor p >= 0.45; its
frozen records keep rule_version "headline_v1".
Candidates are the main markets of the prediction response (match result, double chance, total goals
1.5 / 2.5 / 3.5, both teams to score). Probability = calibrated_probability, falling back to
model_probability. Pure functions: every number comes from the response, nothing is invented.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

RULE_VERSION = "headline_v2"
#: Rule versions whose frozen records exist and stay viewable (oldest first).
KNOWN_RULE_VERSIONS: Tuple[str, ...] = ("headline_v1", "headline_v2")

# Banko slot bounds (unchanged since headline_v1; research rule R0 in backend/scripts/research/sel_common.py).
BANKO_MIN_P = 0.7
BANKO_MAX_P = 0.95
# Tier floors. Test hit rates per band: backend/data/research/sel_test.json -> C_rules.banko_bands
# ("0.85-0.90": 0.8845, n 329; "0.90-0.95": 0.9317, n 161); rule R1 (>= 0.85) C_rules.all_test.R1_banko85
# 0.9 (n 490), rule R3 (>= 0.90) C_rules.all_test.R3_banko90 0.9317 (n 161).
TIER_BANKO_MIN_P = 0.85
TIER_COK_GUCLU_MIN_P = 0.9
ODDS_MIN_PRICE = 1.6
# Oranlı floor 0.45 -> 0.55: sel_test.json -> C_rules.oranli_current.fair_min_p0.55 (hit 0.6064, n 1758;
# family exclusion against the 0.70-0.95 Banko slot as here) vs C_rules.oranli_current.fair_path (0.5679).
ODDS_MIN_P = 0.55

TIER_COK_GUCLU = "cok_guclu"
TIER_BANKO = "banko"
TIER_GUCLU = "guclu"
#: Strongest first.
BANKO_TIERS: Tuple[str, ...] = (TIER_COK_GUCLU, TIER_BANKO, TIER_GUCLU)

_RESULT_KEYS = re.compile(r"(HOME_WIN|DRAW|AWAY_WIN|HOME_OR_DRAW|HOME_OR_AWAY|DRAW_OR_AWAY)")
_GOAL_LINE_KEYS = re.compile(r"(OVER|UNDER)_\d+_\d+")

GOAL_LINES: Tuple[float, ...] = (1.5, 2.5, 3.5)


@dataclass(frozen=True)
class PickCandidate:
    key: str
    market_name: str
    outcome: str
    probability: float
    #: 1 / probability
    fair_odds: float
    #: Bookmaker price when known
    odds: Optional[float] = None
    odds_source: Optional[str] = None
    banko_eligible: bool = True
    source: str = "match"


@dataclass(frozen=True)
class HeadlinePicks:
    banko: Optional[PickCandidate]
    oranli: Optional[PickCandidate]
    #: Tier of the Banko slot pick (banko_tier(banko.probability)); None without a banko.
    banko_tier: Optional[str] = None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def valid_probability(p: Any) -> bool:
    """Mirror of valid() in headlinePicks.ts: a finite number strictly between 0 and 1."""
    return _is_number(p) and 0 < p < 1


def banko_tier(p: Any) -> Optional[str]:
    """Tier of a Banko slot probability (bankoTier() of headlinePicks.ts): "cok_guclu" for p >= 0.90,
    "banko" for 0.85 <= p < 0.90, "guclu" for 0.70 <= p < 0.85; None outside the slot (0.70-0.95) or
    when p is not a number."""
    if not _is_number(p) or p < BANKO_MIN_P or p > BANKO_MAX_P:
        return None
    if p >= TIER_COK_GUCLU_MIN_P:
        return TIER_COK_GUCLU
    if p >= TIER_BANKO_MIN_P:
        return TIER_BANKO
    return TIER_GUCLU


def pick_family(key: str) -> str:
    """Market family: match result + double chance ("result"), goal lines + both teams to score
    ("goals"), anything else by its own key. Oranlı never comes from the banko's family."""
    if _RESULT_KEYS.fullmatch(key):
        return "result"
    if _GOAL_LINE_KEYS.fullmatch(key) or key.startswith("BTTS_"):
        return "goals"
    return key.split(":")[0]


def select_headline_picks(candidates: Sequence[PickCandidate]) -> HeadlinePicks:
    """selectHeadlinePicks of headlinePicks.ts (stable sort, first match wins on ties)."""
    by_p = sorted(candidates, key=lambda c: c.probability, reverse=True)
    banko = next(
        (c for c in by_p if c.banko_eligible and BANKO_MIN_P <= c.probability <= BANKO_MAX_P),
        None,
    )
    banko_family = pick_family(banko.key) if banko else None
    other_family = [c for c in by_p if pick_family(c.key) != banko_family]

    priced = [
        c
        for c in other_family
        if c.odds is not None
        and c.odds >= ODDS_MIN_PRICE
        and c.probability >= ODDS_MIN_P
        and c.probability * c.odds >= 1
    ]
    fair = [c for c in other_family if c.fair_odds >= ODDS_MIN_PRICE and c.probability >= ODDS_MIN_P]
    oranli = priced[0] if priced else (fair[0] if fair else None)
    if oranli is not None and banko is not None and oranli.key == banko.key:
        oranli = None
    return HeadlinePicks(banko=banko, oranli=oranli, banko_tier=banko_tier(banko.probability) if banko else None)


# ----------------------------------------------------------------------------------------------
# Candidates from a prediction response (railModel.ts buildRailRows + headlinePicks.ts matchCandidates)
# ----------------------------------------------------------------------------------------------


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _model_probability(outcome: Any) -> Optional[float]:
    """modelProbability(): calibrated_probability ?? model_probability, null when not a finite number."""
    if outcome is None:
        return None
    p = _get(outcome, "calibrated_probability")
    if p is None:
        p = _get(outcome, "model_probability")
    return float(p) if _is_number(p) else None


def _find_market(markets: Optional[Sequence[Any]], market_type: str, line: Optional[float] = None) -> Any:
    for m in markets or []:
        if _get(m, "market_type") == market_type and (line is None or _get(m, "line") == line):
            return m
    return None


def _find_outcome(market: Any, test) -> Any:
    if market is None:
        return None
    for o in _get(market, "outcomes") or []:
        label = _get(o, "label")
        if isinstance(label, str) and test(label.strip().lower()):
            return o
    return None


def _real_odds(outcome: Any) -> Optional[float]:
    odds = _get(outcome, "real_odds")
    return float(odds) if _is_number(odds) and odds > 1 else None


def _candidate(
    source: Any,
    key: str,
    market_name: str,
    outcome_name: str,
    fallback: Optional[float] = None,
) -> Optional[PickCandidate]:
    """toOutcome() + matchCandidates(): None when the probability is missing or not in (0, 1)."""
    p = _model_probability(source)
    if p is None:
        p = fallback
    if not valid_probability(p):
        return None
    bookmaker = _get(source, "bookmaker")
    return PickCandidate(
        key=key,
        market_name=market_name,
        outcome=outcome_name,
        probability=float(p),
        fair_odds=1 / float(p),
        odds=_real_odds(source),
        odds_source=bookmaker if isinstance(bookmaker, str) else None,
        banko_eligible=True,
        source="match",
    )


def _top_level(prediction: Any, name: str) -> Optional[float]:
    value = _get(prediction, name)
    return float(value) if _is_number(value) else None


def labels_for(key: str, home_team: str, away_team: str) -> Tuple[str, str]:
    """(market name, outcome text) exactly as the match page prints them (railModel.ts)."""
    fixed = {
        "HOME_WIN": ("Maç Sonucu", f"{home_team} kazanır"),
        "DRAW": ("Maç Sonucu", "Beraberlik"),
        "AWAY_WIN": ("Maç Sonucu", f"{away_team} kazanır"),
        "HOME_OR_DRAW": ("Çifte Şans", f"1X ({home_team} veya beraberlik)"),
        "HOME_OR_AWAY": ("Çifte Şans", "12 (beraberlik olmaz)"),
        "DRAW_OR_AWAY": ("Çifte Şans", f"X2 (beraberlik veya {away_team})"),
        "BTTS_NO": ("Karşılıklı Gol", "KG Yok"),
        "BTTS_YES": ("Karşılıklı Gol", "KG Var"),
    }
    if key in fixed:
        return fixed[key]
    m = re.fullmatch(r"(OVER|UNDER)_(\d+)_(\d+)", key)
    if m is None:
        raise ValueError(f"unknown selection key: {key!r}")
    line = f"{float(m.group(2) + '.' + m.group(3)):.1f}"
    return f"Alt/Üst {line} Gol", f"{'Üst' if m.group(1) == 'OVER' else 'Alt'} {line}"


def candidates_from_prediction(prediction: Any, home_team: str, away_team: str) -> List[PickCandidate]:
    """Candidates in the order of the rail rows (this order decides ties):
    1, X, 2; 1X, 12, X2; Alt/Üst 1.5, 2.5, 3.5 (Alt first); KG Yok, KG Var.

    ``prediction`` is a prediction response as dict or pydantic object (MatchPredictionResponse).
    """
    markets = _get(prediction, "market_analysis")
    out: List[Optional[PickCandidate]] = []

    def add(source: Any, key: str, fallback: Optional[float] = None) -> None:
        market_name, outcome = labels_for(key, home_team, away_team)
        out.append(_candidate(source, key, market_name, outcome, fallback))

    result = _find_market(markets, "match_result")
    add(_find_outcome(result, lambda l: l == "home"), "HOME_WIN", _top_level(prediction, "home_win_probability"))
    add(_find_outcome(result, lambda l: l == "draw"), "DRAW", _top_level(prediction, "draw_probability"))
    add(_find_outcome(result, lambda l: l == "away"), "AWAY_WIN", _top_level(prediction, "away_win_probability"))

    dc = _find_market(markets, "double_chance")
    if dc is not None:
        # Double-chance outcomes have no top-level fallback (as in buildRailRows).
        add(_find_outcome(dc, lambda l: l == "1x"), "HOME_OR_DRAW")
        add(_find_outcome(dc, lambda l: l == "12"), "HOME_OR_AWAY")
        add(_find_outcome(dc, lambda l: l == "x2"), "DRAW_OR_AWAY")

    for line in GOAL_LINES:
        suffix = str(line).replace(".", "_")
        market = _find_market(markets, f"OVER_UNDER_{suffix}", line)
        if market is None:
            continue
        add(_find_outcome(market, lambda l: l.startswith("under")), f"UNDER_{suffix}")
        add(_find_outcome(market, lambda l: l.startswith("over")), f"OVER_{suffix}")

    btts = _find_market(markets, "btts")
    yes_fallback = _top_level(prediction, "btts_probability")
    add(_find_outcome(btts, lambda l: l == "no"), "BTTS_NO", None if yes_fallback is None else 1 - yes_fallback)
    add(_find_outcome(btts, lambda l: l == "yes"), "BTTS_YES", yes_fallback)
    return [c for c in out if c is not None]


def headline_picks_from_prediction(prediction: Any, home_team: str, away_team: str) -> HeadlinePicks:
    return select_headline_picks(candidates_from_prediction(prediction, home_team, away_team))


# ----------------------------------------------------------------------------------------------
# Labels and settlement helpers shared by the tracker and the API
# ----------------------------------------------------------------------------------------------

_SHORT_LABELS: Dict[str, str] = {
    "HOME_WIN": "MS 1", "DRAW": "MS X", "AWAY_WIN": "MS 2",
    "HOME_OR_DRAW": "1X", "HOME_OR_AWAY": "12", "DRAW_OR_AWAY": "X2",
    "BTTS_YES": "KG Var", "BTTS_NO": "KG Yok",
}


def short_label(key: str) -> str:
    """Compact Turkish label of a market key for tables ("1X", "2.5 Üst", "KG Var")."""
    if key in _SHORT_LABELS:
        return _SHORT_LABELS[key]
    m = re.fullmatch(r"(OVER|UNDER)_(\d+)_(\d+)", key)
    if m:
        return f"{m.group(2)}.{m.group(3)} {'Üst' if m.group(1) == 'OVER' else 'Alt'}"
    return key


def landed(key: str, home_goals: int, away_goals: int) -> bool:
    """Did the selection come true on this final score? Same logic as
    docs/live-tests/2026-10-14/score_picks.py (full-time score, 90 minutes)."""
    h, a = home_goals, away_goals
    if key == "HOME_WIN":
        return h > a
    if key == "DRAW":
        return h == a
    if key == "AWAY_WIN":
        return h < a
    if key == "HOME_OR_DRAW":
        return h >= a
    if key == "DRAW_OR_AWAY":
        return h <= a
    if key == "HOME_OR_AWAY":
        return h != a
    if key == "BTTS_YES":
        return h > 0 and a > 0
    if key == "BTTS_NO":
        return h == 0 or a == 0
    m = re.fullmatch(r"(OVER|UNDER)_(\d+)_(\d+)", key)
    if m is None:
        raise ValueError(f"unknown selection key: {key!r}")
    line = float(f"{m.group(2)}.{m.group(3)}")
    return (h + a > line) if m.group(1) == "OVER" else (h + a < line)
