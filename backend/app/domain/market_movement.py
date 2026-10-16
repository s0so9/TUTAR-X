"""Market movement tracking for odds changes over time.

This module provides structures for tracking odds movements across time.

CRITICAL RULES:
- Movement is ONLY calculated from actual timestamped odds records.
- Movement is NEVER fabricated or estimated.
- If previous odds do not exist, movement fields remain None.
- All odds must be validated as > 1.0.

Market movement is used to identify:
- Significant odds changes (sharp action)
- Market sentiment shifts
- Value opportunities created by movement
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

from pydantic import BaseModel, Field, field_validator


@dataclass
class OddsMovement:
    """Represents odds movement for a specific market outcome over time.
    
    Movement is calculated by comparing current odds to previous odds at an
    earlier timestamp. Movement fields are None when previous odds are unavailable.
    
    NEVER fabricate movement — all movement data must come from real timestamped
    odds records.
    """
    
    market_name: str
    """Market identifier (e.g., 'match_result', 'btts', 'over_under_2.5')."""
    
    selection_label: str
    """Selection within market (e.g., 'home', 'draw', 'away', 'over', 'under')."""
    
    bookmaker: str
    """Bookmaker/source providing these odds."""
    
    current_odds: float
    """Current odds value (must be > 1.0)."""
    
    previous_odds: Optional[float]
    """Previous odds value from earlier timestamp (must be > 1.0 if not None).
    None when no historical odds are available."""
    
    odds_change: Optional[float]
    """Absolute change: current_odds - previous_odds.
    None when previous_odds is None."""
    
    odds_change_percentage: Optional[float]
    """Percentage change: ((current_odds - previous_odds) / previous_odds) * 100.
    None when previous_odds is None."""
    
    movement_timestamp: datetime
    """Timestamp when current_odds were recorded."""
    
    previous_timestamp: Optional[datetime]
    """Timestamp when previous_odds were recorded.
    None when previous_odds is None."""
    
    def __post_init__(self):
        """Validate odds values."""
        if self.current_odds <= 1.0:
            raise ValueError(
                f"Invalid current_odds: {self.current_odds}. "
                f"Odds must be > 1.0."
            )
        
        if self.previous_odds is not None and self.previous_odds <= 1.0:
            raise ValueError(
                f"Invalid previous_odds: {self.previous_odds}. "
                f"Odds must be > 1.0."
            )
        
        # Validate consistency of movement fields
        if self.previous_odds is None:
            if self.odds_change is not None:
                raise ValueError(
                    "odds_change must be None when previous_odds is None"
                )
            if self.odds_change_percentage is not None:
                raise ValueError(
                    "odds_change_percentage must be None when previous_odds is None"
                )
            if self.previous_timestamp is not None:
                raise ValueError(
                    "previous_timestamp must be None when previous_odds is None"
                )


def calculate_odds_movement(
    current_odds: float,
    previous_odds: Optional[float]
) -> Tuple[Optional[float], Optional[float]]:
    """Calculate odds change and percentage change.
    
    Movement is only calculated when previous_odds is available.
    Returns (None, None) when previous_odds is None.
    
    Args:
        current_odds: Current odds value (must be > 1.0).
        previous_odds: Previous odds value (must be > 1.0 if not None).
                       None when no historical odds are available.
    
    Returns:
        Tuple of (odds_change, odds_change_percentage).
        Both are None when previous_odds is None.
    
    Raises:
        ValueError: If odds values are invalid (<= 1.0).
    
    Examples:
        >>> calculate_odds_movement(2.00, 1.80)
        (0.20, 11.11)
        
        >>> calculate_odds_movement(1.75, 2.00)
        (-0.25, -12.5)
        
        >>> calculate_odds_movement(2.00, None)
        (None, None)
    """
    # Validate current_odds
    if current_odds <= 1.0:
        raise ValueError(
            f"Invalid current_odds: {current_odds}. Odds must be > 1.0."
        )
    
    # If no previous odds, movement cannot be calculated
    if previous_odds is None:
        return (None, None)
    
    # Validate previous_odds
    if previous_odds <= 1.0:
        raise ValueError(
            f"Invalid previous_odds: {previous_odds}. Odds must be > 1.0."
        )
    
    # Calculate absolute change
    odds_change = current_odds - previous_odds
    
    # Calculate percentage change
    odds_change_percentage = (odds_change / previous_odds) * 100.0
    
    return (odds_change, odds_change_percentage)
