"""Market value classification engine.

This module provides value classification based on market edge (model_probability - implied_probability).
Value classification is derived from calculated market edge, never fabricated.

Key principles:
- Value classification is only performed when real bookmaker odds are available.
- Market edge must be calculated from model probability and actual implied probability.
- Classifications are threshold-based and deterministic.
- Missing odds result in UNAVAILABLE classification, never fabricated.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ValueClassification(str, Enum):
    """Value classification based on market edge thresholds.
    
    Market edge = model_probability - implied_probability
    
    Positive edge means the model believes the outcome is more likely
    than the bookmaker's odds suggest (potential value).
    
    Thresholds:
    - STRONG_VALUE: edge >= 10% (significant value opportunity)
    - VALUE: edge >= 5% (moderate value opportunity)
    - NEUTRAL: edge >= 0% (fair or slight value)
    - NEGATIVE_VALUE: edge < 0% (bookmaker overvalues outcome)
    - UNAVAILABLE: edge is None (no real odds available)
    """
    
    STRONG_VALUE = "strong_value"
    VALUE = "value"
    NEUTRAL = "neutral"
    NEGATIVE_VALUE = "negative_value"
    UNAVAILABLE = "unavailable"


def classify_value(market_edge: Optional[float]) -> ValueClassification:
    """Classify value based on market edge.
    
    Market edge = model_probability - implied_probability
    
    Classification thresholds:
    - None → UNAVAILABLE (no real odds available)
    - >= 0.10 → STRONG_VALUE (10% or more edge)
    - >= 0.05 → VALUE (5% to 10% edge)
    - >= 0.0 → NEUTRAL (0% to 5% edge)
    - < 0.0 → NEGATIVE_VALUE (negative edge, bookmaker overvalues)
    
    Args:
        market_edge: Market edge in probability units (e.g., 0.05 = 5%).
                     None when real bookmaker odds are unavailable.
    
    Returns:
        ValueClassification enum value.
    
    Examples:
        >>> classify_value(0.12)  # 12% edge
        ValueClassification.STRONG_VALUE
        
        >>> classify_value(0.07)  # 7% edge
        ValueClassification.VALUE
        
        >>> classify_value(0.02)  # 2% edge
        ValueClassification.NEUTRAL
        
        >>> classify_value(-0.03)  # Negative edge
        ValueClassification.NEGATIVE_VALUE
        
        >>> classify_value(None)  # No odds available
        ValueClassification.UNAVAILABLE
    """
    if market_edge is None:
        return ValueClassification.UNAVAILABLE
    
    if market_edge >= 0.10:
        return ValueClassification.STRONG_VALUE
    elif market_edge >= 0.05:
        return ValueClassification.VALUE
    elif market_edge >= 0.0:
        return ValueClassification.NEUTRAL
    else:
        return ValueClassification.NEGATIVE_VALUE


@dataclass
class MarketValueAssessment:
    """Complete value assessment for a single market outcome.
    
    Aggregates model probability, real bookmaker odds, implied probability,
    market edge, and resulting value classification.
    
    All fields are explicitly tracked to maintain distinction between:
    - Model probability (from prediction engine)
    - Implied probability (from bookmaker odds)
    - Market edge (difference between the two)
    
    This structure is only created when real bookmaker odds are available.
    """
    
    market_name: str
    """Market identifier (e.g., 'match_result', 'btts', 'over_under_2.5')."""
    
    model_probability: float
    """Model-derived probability for this outcome."""
    
    real_odds: Optional[float]
    """Real bookmaker odds (None when unavailable, never fabricated)."""
    
    implied_probability: Optional[float]
    """Implied probability from real_odds (None when unavailable)."""
    
    market_edge: Optional[float]
    """Market edge: model_probability - implied_probability (None when unavailable)."""
    
    value_classification: ValueClassification
    """Value classification based on market_edge thresholds."""
    
    bookmaker: Optional[str]
    """Bookmaker/source providing odds (None when unavailable)."""
