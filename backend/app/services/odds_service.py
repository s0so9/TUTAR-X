"""Odds service for İddaa integration and value calculations.

Provides utilities for:
- Implied probability calculation
- Edge calculation (model prob - implied prob)
- Expected value calculation
- Temporal validation
- Odds normalization

Critical: Never fabricates odds. Returns None when unavailable.
"""

import logging
import re
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

_logger = logging.getLogger(__name__)


class OddsAvailability(str, Enum):
    """Odds availability status."""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    STALE = "stale"
    FUTURE = "future"  # Odds timestamp is after prediction timestamp (leakage)


@dataclass
class MarketOdds:
    """Odds for a specific market selection."""
    
    market: str          # "OVER_0_5", "BTTS_YES", "HOME_WIN", etc.
    selection: str       # Human-readable selection
    odds: Optional[float]           # Decimal odds (None if unavailable)
    odds_timestamp: Optional[datetime]  # When odds were published
    provider: Optional[str]         # "iddaa", "development", etc.
    availability: OddsAvailability
    
    @property
    def implied_probability(self) -> Optional[float]:
        """Calculate implied probability from odds.
        
        Returns:
            Implied probability [0, 1] or None if odds unavailable
        """
        if self.odds is None or self.odds <= 0:
            return None
        return 1.0 / self.odds
    
    def calculate_edge(self, model_probability: float) -> Optional[float]:
        """Calculate probability edge.
        
        Edge = Model Probability - Implied Probability
        
        Positive edge suggests model sees value.
        Negative edge suggests overpriced market.
        
        Args:
            model_probability: Calibrated model probability [0, 1]
            
        Returns:
            Edge in probability points or None if odds unavailable
        """
        implied = self.implied_probability
        if implied is None:
            return None
        return model_probability - implied
    
    def calculate_expected_value(self, model_probability: float) -> Optional[float]:
        """Calculate expected value.
        
        EV = (Model Probability × Odds) - 1
        
        Positive EV suggests profitable bet in long run.
        
        Args:
            model_probability: Calibrated model probability [0, 1]
            
        Returns:
            Expected value (e.g., 0.08 = 8% EV) or None if odds unavailable
        """
        if self.odds is None or self.odds <= 0:
            return None
        return (model_probability * self.odds) - 1.0
    
    def is_valid_for_timestamp(self, prediction_timestamp: datetime) -> bool:
        """Validate odds are not from the future (temporal leakage check).
        
        Args:
            prediction_timestamp: When prediction is being made
            
        Returns:
            True if odds_timestamp <= prediction_timestamp
        """
        if self.odds_timestamp is None:
            # No timestamp = assume valid (conservative)
            return True
        
        return self.odds_timestamp <= prediction_timestamp


MODEL_MARKET_CONFLICT = "MODEL_MARKET_CONFLICT"
"""Classification for model-vs-market gaps too large to be credible value."""

MAX_CREDIBLE_EDGE = 0.08
"""Largest model-minus-implied probability gap still treated as possible value.

Heuristic guard, not a fitted threshold: against liquid markets, gaps beyond ~8
percentage points almost always mean the model lacks information. On
2026-10-13 the unguarded selector labelled a 31% Viking win (market 4%) as
STRONG_VALUE with +706% EV.
"""

MAX_CREDIBLE_PROBABILITY_RATIO = 1.5
"""Largest model/implied probability ratio still treated as possible value.

Heuristic guard, not a fitted threshold. The absolute gap above cannot catch
longshots: a 10.4% model probability against odds 26.0 (implied 3.8%) is only
6.6pp apart but claims +170% EV. A ratio of 1.5 equals an EV of +50% against
the quoted odds; it only bites when the implied probability is below ~16%,
where MAX_CREDIBLE_EDGE is too coarse.
"""


def is_model_market_conflict(
    model_probability: Optional[float], implied_probability: Optional[float]
) -> bool:
    """True when the model sits implausibly far above the market.

    Shared by ValueAssessment (selector) and market_analysis.classify_value
    (API comparison rows), so both apply the same absolute and relative
    criteria. Missing inputs are never a conflict.
    """
    if model_probability is None or implied_probability is None or implied_probability <= 0:
        return False
    if model_probability - implied_probability > MAX_CREDIBLE_EDGE:
        return True
    return model_probability / implied_probability > MAX_CREDIBLE_PROBABILITY_RATIO


@dataclass
class ValueAssessment:
    """Value assessment for a market candidate."""
    
    market: str
    model_probability: float
    fair_odds: float
    
    # Bookmaker data
    bookmaker_odds: Optional[float]
    implied_probability: Optional[float]
    
    # Value metrics
    edge: Optional[float]              # Probability edge
    expected_value: Optional[float]    # EV percentage
    
    # Classification
    value_classification: str  # "STRONG_VALUE", "VALUE", "NEUTRAL", "NEGATIVE_VALUE", "NO_ODDS"
    value_score: float         # 0.0-1.0 score for use in selection
    
    @staticmethod
    def from_market_odds(
        market: str,
        model_probability: float,
        market_odds: Optional[MarketOdds]
    ) -> "ValueAssessment":
        """Create value assessment from market odds.
        
        Args:
            market: Market identifier
            model_probability: Calibrated model probability
            market_odds: MarketOdds or None
            
        Returns:
            ValueAssessment with calculated metrics
        """
        # Calculate fair odds
        fair_odds = 1.0 / model_probability if model_probability > 0 else 0.0
        
        # If no odds available
        if market_odds is None or market_odds.odds is None:
            return ValueAssessment(
                market=market,
                model_probability=model_probability,
                fair_odds=fair_odds,
                bookmaker_odds=None,
                implied_probability=None,
                edge=None,
                expected_value=None,
                value_classification="NO_ODDS",
                value_score=0.0  # No value contribution without odds
            )
        
        # Calculate value metrics
        implied_prob = market_odds.implied_probability
        edge = market_odds.calculate_edge(model_probability)
        expected_value = market_odds.calculate_expected_value(model_probability)
        
        # Classify value
        if expected_value >= 0.15:  # EV >= 15%
            value_classification = "STRONG_VALUE"
            value_score = 1.0
        elif expected_value >= 0.08:  # EV >= 8%
            value_classification = "VALUE"
            value_score = 0.7
        elif expected_value >= 0.03:  # EV >= 3%
            value_classification = "VALUE"
            value_score = 0.4
        elif expected_value >= 0.0:  # EV >= 0%
            value_classification = "NEUTRAL"
            value_score = 0.1
        else:  # Negative EV
            value_classification = "NEGATIVE_VALUE"
            value_score = 0.0

        # A model probability far above the market's is far more likely to be
        # model error (missing information such as squad quality) than value.
        if is_model_market_conflict(model_probability, implied_prob):
            value_classification = MODEL_MARKET_CONFLICT
            value_score = 0.0

        return ValueAssessment(
            market=market,
            model_probability=model_probability,
            fair_odds=fair_odds,
            bookmaker_odds=market_odds.odds,
            implied_probability=implied_prob,
            edge=edge,
            expected_value=expected_value,
            value_classification=value_classification,
            value_score=value_score
        )


class OddsService:
    """Service for odds retrieval and value calculations."""
    
    @staticmethod
    def get_market_odds(
        odds_data: Optional[Dict[str, float]],
        market: str,
        provider: str = "unknown",
        odds_timestamp: Optional[datetime] = None
    ) -> Optional[MarketOdds]:
        """Get odds for a specific market.
        
        Args:
            odds_data: Dict mapping market -> odds (e.g., {"OVER_0_5": 1.05})
            market: Market identifier
            provider: Odds provider name
            odds_timestamp: When odds were published
            
        Returns:
            MarketOdds or None if unavailable
        """
        if odds_data is None or market not in odds_data:
            return MarketOdds(
                market=market,
                selection=market,
                odds=None,
                odds_timestamp=None,
                provider=None,
                availability=OddsAvailability.UNAVAILABLE
            )
        
        odds_value = odds_data[market]
        
        if odds_value is None or odds_value <= 0:
            return MarketOdds(
                market=market,
                selection=market,
                odds=None,
                odds_timestamp=odds_timestamp,
                provider=provider,
                availability=OddsAvailability.UNAVAILABLE
            )
        
        return MarketOdds(
            market=market,
            selection=market,
            odds=odds_value,
            odds_timestamp=odds_timestamp,
            provider=provider,
            availability=OddsAvailability.AVAILABLE
        )
    
    @staticmethod
    def calculate_value_contribution(
        value_assessment: ValueAssessment,
        use_conservative_thresholds: bool = True
    ) -> float:
        """Calculate value contribution to selection score.
        
        This replaces the old tiny edge bonus with meaningful value scoring.
        
        Args:
            value_assessment: ValueAssessment for the market
            use_conservative_thresholds: If True, requires higher EV for contribution
            
        Returns:
            Value contribution [0.0, 0.30] for selection score
        """
        if value_assessment.expected_value is None:
            # No odds = no value contribution
            return 0.0
        if value_assessment.value_classification == MODEL_MARKET_CONFLICT:
            return 0.0
        
        ev = value_assessment.expected_value
        
        if use_conservative_thresholds:
            # Conservative: require meaningful EV
            if ev >= 0.15:  # EV >= 15%
                return 0.30  # Maximum value contribution
            elif ev >= 0.08:  # EV >= 8%
                return 0.20
            elif ev >= 0.05:  # EV >= 5%
                return 0.12
            elif ev >= 0.03:  # EV >= 3%
                return 0.06
            else:
                return 0.0  # Insufficient value
        else:
            # Aggressive: accept lower EV
            if ev >= 0.08:
                return 0.30
            elif ev >= 0.05:
                return 0.20
            elif ev >= 0.03:
                return 0.12
            elif ev >= 0.01:
                return 0.06
            else:
                return 0.0
    
    @staticmethod
    def apply_high_base_rate_protection(
        market: str,
        probability: float,
        value_assessment: ValueAssessment,
        base_selection_score: float
    ) -> float:
        """Apply protection against trivial high base-rate markets.
        
        High base-rate markets (OVER_0.5, HOME_OR_AWAY) should not win by default.
        They need to show actual value to be selected.
        
        Args:
            market: Market identifier
            probability: Model probability
            value_assessment: Value assessment for this market
            base_selection_score: Selection score before protection
            
        Returns:
            Adjusted selection score (may be penalized)
        """
        # Define high base-rate markets
        HIGH_BASE_RATE_MARKETS = {
            'OVER_0_5',
            'HOME_OR_AWAY',
            'UNDER_6_5',  # Trivially likely
        }
        
        if market not in HIGH_BASE_RATE_MARKETS:
            # Not a high base-rate market
            return base_selection_score
        
        # High base-rate market: check if it has genuine value
        if value_assessment.expected_value is not None:
            ev = value_assessment.expected_value
            
            if ev >= 0.05:  # EV >= 5%
                # Good value, no penalty
                return base_selection_score
            elif ev >= 0.0:  # Positive but low EV
                # Moderate penalty
                return base_selection_score * 0.85
            else:  # Negative EV
                # Strong penalty
                return base_selection_score * 0.60
        else:
            # No odds available, moderate penalty for high base-rate
            # (We don't know if it has value, so penalize conservatively)
            return base_selection_score * 0.80
    
    @staticmethod
    def validate_temporal_boundary(
        odds_timestamp: Optional[datetime],
        prediction_timestamp: datetime
    ) -> bool:
        """Validate odds are not from the future (leakage check).
        
        Args:
            odds_timestamp: When odds were published
            prediction_timestamp: When prediction is being made
            
        Returns:
            True if valid (odds_timestamp <= prediction_timestamp)
        """
        if odds_timestamp is None:
            # No timestamp = cannot validate, assume valid (conservative)
            return True
        
        return odds_timestamp <= prediction_timestamp


# ---------------------------------------------------------------------------
# AverageMarketOdds rows -> flat canonical odds dict
# ---------------------------------------------------------------------------
#
# Storage convention (shared by The Odds API updater in
# app/services/odds_updater_service.py and the manual loader in
# scripts/load_manual_odds.py):
#
#   market_key  market_point  outcome_name
#   ----------  ------------  -------------------------------------------
#   "h2h"           None          home team name | away team name | "Draw"
#   "totals"        2.5 (line)    "Over" | "Under"
#   "btts"          None          "Yes" | "No"
#   "double_chance" None          "1X" | "12" | "X2"
#
# Prediction-pipeline consumers (SmartMarketSelector via
# OddsService.get_market_odds, endpoint market analysis) expect a FLAT dict
# keyed by canonical market identifiers, e.g.
#   {"HOME_WIN": 1.22, "DRAW": 5.8, "AWAY_WIN": 12.5,
#    "OVER_2_5": 1.5, "UNDER_2_5": 2.5, "BTTS_YES": 2.1, "BTTS_NO": 1.65,
#    "HOME_OR_DRAW": 1.05, "HOME_OR_AWAY": 1.12, "DRAW_OR_AWAY": 4.2}
# The helpers below perform that conversion. They never fabricate odds:
# rows that cannot be mapped unambiguously are skipped.

# Source label for odds typed in by the user (not fetched from a bookmaker
# API, not verified by the system).
MANUAL_ODDS_SOURCE = "manual_user_supplied"
# Source label for averages computed by OddsUpdaterService from The Odds API.
ODDS_API_AVERAGE_SOURCE = "the_odds_api_average"

MANUAL_EVENT_ID_PREFIX = f"{MANUAL_ODDS_SOURCE}:"

H2H_MARKET_KEY = "h2h"
TOTALS_MARKET_KEY = "totals"
BTTS_MARKET_KEY = "btts"
DOUBLE_CHANCE_MARKET_KEY = "double_chance"

# Double chance outcome names -> canonical SmartMarketSelector keys.
# Explicit bookmaker prices only; never derived from 1X2 (margins differ).
_DOUBLE_CHANCE_OUTCOMES = {
    "1x": "HOME_OR_DRAW",
    "12": "HOME_OR_AWAY",
    "x2": "DRAW_OR_AWAY",
}

_DRAW_NAMES = {"draw", "x", "tie", "beraberlik"}
_HOME_ALIASES = {"home", "1"}
_AWAY_ALIASES = {"away", "2"}
_OVER_NAMES = {"over", "ust"}
_UNDER_NAMES = {"under", "alt"}
_YES_NAMES = {"yes", "var", "evet"}
_NO_NAMES = {"no", "yok", "hayir"}

# Club-form tokens that carry no identity information.
_CLUB_TOKENS = {
    "fc", "cf", "sc", "ac", "ssc", "rc", "fk", "sk", "jk", "as", "afc",
    "cd", "ud", "sv", "bk", "club", "de", "the",
}

_MIN_TEAM_SIMILARITY = 0.5
_STRONG_TEAM_SIMILARITY = 0.8


def manual_provider_event_id(match_id: str) -> str:
    """Provider event id used for manually supplied odds of a match."""
    return f"{MANUAL_EVENT_ID_PREFIX}{match_id}"


def line_suffix(point: float) -> str:
    """Canonical line suffix: 2.5 -> "2_5", 3 -> "3_0".

    Mirrors SmartMarketSelector, which builds keys with
    ``f"OVER_{line}".replace(".", "_")`` for float lines.
    """
    return str(float(point)).replace(".", "_")


def _strip_accents(text: str) -> str:
    # Turkish dotless/dotted i are not decomposed into ASCII by NFKD
    text = text.replace("ı", "i").replace("İ", "I")
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_outcome_text(text: Optional[str]) -> str:
    """Lowercase, accent-free, punctuation-free text."""
    if not text:
        return ""
    cleaned = _strip_accents(str(text)).lower()
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _team_tokens(name: Optional[str]) -> set:
    return {t for t in normalize_outcome_text(name).split() if t not in _CLUB_TOKENS}


def team_name_similarity(name_a: Optional[str], name_b: Optional[str]) -> float:
    """Similarity in [0, 1] between two team names (case/diacritics tolerant)."""
    a = normalize_outcome_text(name_a)
    b = normalize_outcome_text(name_b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    tokens_a = _team_tokens(name_a)
    tokens_b = _team_tokens(name_b)
    if tokens_a and tokens_b:
        if tokens_a == tokens_b:
            return 1.0
        jaccard = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
        text_a = " ".join(sorted(tokens_a))
        text_b = " ".join(sorted(tokens_b))
    else:
        jaccard = 0.0
        text_a, text_b = a, b
    ratio = SequenceMatcher(None, text_a, text_b).ratio()
    return max(jaccard, ratio)


def team_names_share_identity(name_a: Optional[str], name_b: Optional[str]) -> bool:
    """True when two team names share an identifying token.

    Token-level check (not character similarity): a common token, a common
    leading prefix of at least 3 characters ("Man Utd" / "Manchester United",
    "Wolves" / "Wolverhampton"), or an acronym ("PSG" / "Paris Saint Germain").
    Used to reject h2h assignments by elimination between unrelated clubs
    whose character-level similarity happens to be moderate
    (e.g. "Fenerbahce" / "Barcelona").
    """
    tokens_a = _team_tokens(name_a)
    tokens_b = _team_tokens(name_b)
    if not tokens_a or not tokens_b:
        return False
    if tokens_a & tokens_b:
        return True
    for ta in tokens_a:
        for tb in tokens_b:
            if min(len(ta), len(tb)) >= 3 and ta[:3] == tb[:3]:
                return True

    def acronym(name: Optional[str]) -> str:
        return "".join(
            t[0] for t in normalize_outcome_text(name).split() if t and t not in _CLUB_TOKENS
        )

    for single, other in ((tokens_a, name_b), (tokens_b, name_a)):
        if len(single) == 1:
            token = next(iter(single))
            other_acronym = acronym(other)
            if len(token) >= 2 and len(other_acronym) >= 2 and token == other_acronym:
                return True
    return False


def map_h2h_outcome_names(
    outcome_names: List[str],
    home_team_name: Optional[str],
    away_team_name: Optional[str],
) -> Dict[str, str]:
    """Map h2h outcome names to HOME_WIN / DRAW / AWAY_WIN.

    Returns:
        Dict outcome_name -> canonical key. Names that cannot be assigned
        unambiguously are omitted (never guessed).
    """
    mapping: Dict[str, str] = {}
    team_outcomes: List[str] = []

    for name in dict.fromkeys(outcome_names):  # de-duplicate, keep order
        norm = normalize_outcome_text(name)
        if norm in _DRAW_NAMES:
            mapping[name] = "DRAW"
        elif norm in _HOME_ALIASES:
            mapping[name] = "HOME_WIN"
        elif norm in _AWAY_ALIASES:
            mapping[name] = "AWAY_WIN"
        else:
            team_outcomes.append(name)

    if not team_outcomes or not (home_team_name or away_team_name):
        return mapping

    def score(name: str, team: Optional[str]) -> float:
        return team_name_similarity(name, team) if team else 0.0

    def assignment_is_credible(pairs: List[tuple]) -> bool:
        # pairs: [(outcome_name, assigned_team_name), ...] for both outcomes.
        # Both names must resemble their assigned team. A weaker name may
        # only follow by elimination when the other is a near-certain match
        # AND it still shares an identifying token (or 3-letter prefix /
        # acronym) with its assigned team, so an unrelated club such as
        # "Fenerbahce" is never assigned to "Barcelona".
        scores = [score(name, team) for name, team in pairs]
        if min(scores) >= _MIN_TEAM_SIMILARITY:
            return True
        if max(scores) < _STRONG_TEAM_SIMILARITY:
            return False
        weak_name, weak_team = pairs[scores.index(min(scores))]
        return team_names_share_identity(weak_name, weak_team)

    if len(team_outcomes) == 2:
        first, second = team_outcomes
        direct_pairs = [(first, home_team_name), (second, away_team_name)]
        swapped_pairs = [(first, away_team_name), (second, home_team_name)]
        direct = sum(score(n, t) for n, t in direct_pairs)
        swapped = sum(score(n, t) for n, t in swapped_pairs)
        if direct > swapped and assignment_is_credible(direct_pairs):
            mapping[first], mapping[second] = "HOME_WIN", "AWAY_WIN"
        elif swapped > direct and assignment_is_credible(swapped_pairs):
            mapping[first], mapping[second] = "AWAY_WIN", "HOME_WIN"
        else:
            _logger.warning(
                "Ambiguous h2h outcome names %s for %s vs %s - skipped",
                team_outcomes, home_team_name, away_team_name,
            )
    else:
        for name in team_outcomes:
            s_home = score(name, home_team_name)
            s_away = score(name, away_team_name)
            if s_home >= _MIN_TEAM_SIMILARITY and s_home > s_away:
                key = "HOME_WIN"
            elif s_away >= _MIN_TEAM_SIMILARITY and s_away > s_home:
                key = "AWAY_WIN"
            else:
                _logger.warning("Unmapped h2h outcome name %r - skipped", name)
                continue
            if key in mapping.values():
                _logger.warning("Duplicate h2h mapping for %s (%r) - skipped", key, name)
                continue
            mapping[name] = key

    return mapping


@dataclass(frozen=True)
class CanonicalOddsQuote:
    """A single canonical market price derived from AverageMarketOdds rows."""

    market: str                       # canonical key, e.g. "HOME_WIN", "OVER_2_5"
    odds: float                       # decimal odds
    source: str                       # MANUAL_ODDS_SOURCE or ODDS_API_AVERAGE_SOURCE
    bookmaker_count: Optional[int]
    calculated_at: Optional[datetime]


def odds_row_source(row: Any) -> str:
    """Return the source label of an AverageMarketOdds-like row."""
    event_id = getattr(row, "provider_event_id", None) or ""
    bookmakers = getattr(row, "bookmakers", None) or []
    if event_id.startswith(MANUAL_EVENT_ID_PREFIX) or MANUAL_ODDS_SOURCE in bookmakers:
        return MANUAL_ODDS_SOURCE
    return ODDS_API_AVERAGE_SOURCE


def _row_canonical_key(row: Any, h2h_mapping: Dict[str, str]) -> Optional[str]:
    market_key = normalize_outcome_text(getattr(row, "market_key", None))
    outcome = getattr(row, "outcome_name", None)
    norm_outcome = normalize_outcome_text(outcome)
    point = getattr(row, "market_point", None)

    if market_key == H2H_MARKET_KEY:
        return h2h_mapping.get(outcome)
    if market_key == TOTALS_MARKET_KEY:
        if point is None:
            return None
        if norm_outcome in _OVER_NAMES:
            return f"OVER_{line_suffix(point)}"
        if norm_outcome in _UNDER_NAMES:
            return f"UNDER_{line_suffix(point)}"
        return None
    if market_key == BTTS_MARKET_KEY:
        if norm_outcome in _YES_NAMES:
            return "BTTS_YES"
        if norm_outcome in _NO_NAMES:
            return "BTTS_NO"
        return None
    if market_key == normalize_outcome_text(DOUBLE_CHANCE_MARKET_KEY):
        return _DOUBLE_CHANCE_OUTCOMES.get(norm_outcome.replace(" ", ""))
    return None


def _sort_timestamp(value: Optional[datetime]) -> float:
    if value is None:
        return float("-inf")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def build_canonical_odds_quotes(
    rows: List[Any],
    home_team_name: Optional[str],
    away_team_name: Optional[str],
) -> Dict[str, CanonicalOddsQuote]:
    """Convert AverageMarketOdds rows into canonical quotes.

    Rows with unknown markets, unmappable outcome names or invalid prices
    (<= 1.0) are skipped. When several rows resolve to the same canonical
    key, the most recently calculated one wins.
    """
    if not rows:
        return {}

    # h2h outcome names are mapped per provider event, so rows from several
    # sources (manual + The Odds API) with different team spellings are each
    # mapped on their own; the most recent row per canonical key then wins.
    h2h_names_by_event: Dict[str, List[str]] = {}
    for r in rows:
        if (
            normalize_outcome_text(getattr(r, "market_key", None)) == H2H_MARKET_KEY
            and getattr(r, "outcome_name", None)
        ):
            event = getattr(r, "provider_event_id", None) or ""
            h2h_names_by_event.setdefault(event, []).append(r.outcome_name)
    h2h_mappings = {
        event: map_h2h_outcome_names(names, home_team_name, away_team_name)
        for event, names in h2h_names_by_event.items()
    }

    quotes: Dict[str, CanonicalOddsQuote] = {}
    for row in sorted(rows, key=lambda r: _sort_timestamp(getattr(r, "calculated_at", None))):
        event = getattr(row, "provider_event_id", None) or ""
        key = _row_canonical_key(row, h2h_mappings.get(event, {}))
        if key is None:
            continue
        price = getattr(row, "average_odds", None)
        if isinstance(price, bool) or not isinstance(price, (int, float)) or price <= 1.0:
            continue
        quotes[key] = CanonicalOddsQuote(
            market=key,
            odds=float(price),
            source=odds_row_source(row),
            bookmaker_count=getattr(row, "bookmaker_count", None),
            calculated_at=getattr(row, "calculated_at", None),
        )
    return quotes


def load_canonical_odds_quotes(
    db: Any,
    match_ids: List[str],
    home_team_id: Optional[str] = None,
    away_team_id: Optional[str] = None,
) -> Dict[str, CanonicalOddsQuote]:
    """Load AverageMarketOdds rows for a match and convert them to canonical quotes.

    Rows are matched either by ``match_id`` (canonical matches.id written by
    OddsUpdaterService, or the API path id) or by the manual provider event id
    written by scripts/load_manual_odds.py (whose match_id may be NULL when
    the fixture is not stored in the matches table).

    Team names (needed to map h2h outcome names) come from the teams table.
    """
    from sqlalchemy import or_
    from app.database.models import AverageMarketOdds, Team as DBTeam

    ids = [mid for mid in dict.fromkeys(match_ids) if mid]
    if db is None or not ids:
        return {}

    rows = db.query(AverageMarketOdds).filter(
        or_(
            AverageMarketOdds.match_id.in_(ids),
            AverageMarketOdds.provider_event_id.in_([manual_provider_event_id(mid) for mid in ids]),
        )
    ).all()
    if not rows:
        return {}

    team_names: Dict[str, str] = {}
    team_ids = [tid for tid in (home_team_id, away_team_id) if tid]
    if team_ids:
        for team in db.query(DBTeam).filter(DBTeam.id.in_(team_ids)).all():
            team_names[team.id] = team.name

    return build_canonical_odds_quotes(
        rows,
        team_names.get(home_team_id) if home_team_id else None,
        team_names.get(away_team_id) if away_team_id else None,
    )


def canonicalize_average_odds(
    rows: List[Any],
    home_team_name: Optional[str],
    away_team_name: Optional[str],
) -> Dict[str, float]:
    """Flat canonical odds dict ({"HOME_WIN": 1.22, ...}) from AverageMarketOdds rows."""
    return {
        key: quote.odds
        for key, quote in build_canonical_odds_quotes(rows, home_team_name, away_team_name).items()
    }


def outcome_odds_fields(
    probability: Optional[float],
    quote: Optional[CanonicalOddsQuote],
) -> Dict[str, Any]:
    """Odds/value fields for one market outcome (MarketOutcomeResponse kwargs).

    All values are None when the quote or probability is unavailable, so
    missing odds stay explicitly missing (never 0).

    Sign conventions follow app.prediction.market_analysis:
      market_edge = implied_probability - model_probability (negative = value)
      expected_value = model_probability * odds - 1
    """
    from app.prediction import market_analysis as ma

    empty: Dict[str, Any] = {
        "real_odds": None,
        "implied_probability": None,
        "market_edge": None,
        "bookmaker": None,
        "odds_timestamp": None,
        "expected_value": None,
        "expected_value_percent": None,
        "value_classification": None,
        "value_score": None,
    }
    if quote is None or probability is None or not (0.0 <= probability <= 1.0):
        return empty
    try:
        classification = ma.classify_value(probability, quote.odds)
        return {
            "real_odds": quote.odds,
            "implied_probability": ma.implied_probability_from_odds(quote.odds),
            "market_edge": ma.edge(probability, quote.odds),
            "bookmaker": quote.source,
            "odds_timestamp": quote.calculated_at,
            "expected_value": ma.expected_value(probability, quote.odds),
            "expected_value_percent": ma.expected_value_percentage(probability, quote.odds),
            "value_classification": classification.value,
            # A model-market conflict is never value, so it carries no value score.
            "value_score": (
                0.0 if classification == ma.ValueClassification.MODEL_MARKET_CONFLICT
                else ma.calculate_value_score(probability, quote.odds)
            ),
        }
    except ValueError:
        return empty
