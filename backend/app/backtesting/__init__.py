"""Backtesting infrastructure for TUTAR X prediction models.

This module provides walk-forward validation and historical evaluation
to measure prediction accuracy and calibration on real historical data.
"""

from app.backtesting.walk_forward import (
    WalkForwardValidator,
    EvaluationMetrics,
    VariantResults,
    ShotMarketVariant,
    TemporalLeakageError,
)

__all__ = [
    "WalkForwardValidator",
    "EvaluationMetrics",
    "VariantResults",
    "ShotMarketVariant",
    "TemporalLeakageError",
]
