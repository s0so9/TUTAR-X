"""Backtesting domain models."""

from datetime import datetime, date
from typing import Optional, Dict
from pydantic import BaseModel, Field

from app.domain.enums import PredictionMarketType


class Backtest(BaseModel):
    """Backtesting configuration and metadata."""

    id: str = Field(..., description="Backtest identifier")
    model_id: str = Field(..., description="Model identifier")
    name: str = Field(..., description="Backtest name")
    
    # Period
    start_date: date = Field(..., description="Backtest start date")
    end_date: date = Field(..., description="Backtest end date")
    
    # Configuration
    market_types: list[PredictionMarketType] = Field(
        default_factory=list, description="Markets to test"
    )
    competitions: Optional[list[str]] = Field(
        None, description="Competition IDs to include"
    )
    
    # Execution
    created_at: datetime = Field(..., description="Backtest creation timestamp")
    started_at: Optional[datetime] = Field(None, description="Execution start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Execution completion timestamp")
    
    status: str = Field("pending", description="Backtest status (pending, running, completed, failed)")
    
    class Config:
        """Pydantic configuration."""

        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "backtest_123",
                "model_id": "model_poisson_v1",
                "name": "Poisson Q4 2023 Test",
                "start_date": "2023-10-01",
                "end_date": "2023-12-31",
                "market_types": ["match_result", "over_under"],
                "created_at": "2026-10-01T00:00:00",
                "status": "completed",
            }
        }


class BacktestResult(BaseModel):
    """Backtest results and performance metrics."""

    id: str = Field(..., description="Result identifier")
    backtest_id: str = Field(..., description="Backtest identifier")
    market_type: PredictionMarketType = Field(..., description="Market type")
    
    # Sample size
    total_predictions: int = Field(0, ge=0, description="Total predictions made")
    total_matches: int = Field(0, ge=0, description="Total matches analyzed")
    
    # Accuracy metrics
    accuracy: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Overall accuracy"
    )
    precision: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Precision"
    )
    recall: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Recall"
    )
    f1_score: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="F1 score"
    )
    
    # Probabilistic metrics
    brier_score: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Brier score (lower is better)"
    )
    log_loss: Optional[float] = Field(
        None, ge=0.0, description="Log loss (lower is better)"
    )
    
    # Calibration
    calibration_error: Optional[float] = Field(
        None, ge=0.0, description="Calibration error"
    )
    calibration_bins: Optional[Dict[str, float]] = Field(
        None, description="Calibration bin data"
    )
    
    # Financial metrics (if odds available)
    roi: Optional[float] = Field(None, description="Return on investment")
    profit_loss: Optional[float] = Field(None, description="Profit/loss")
    total_staked: Optional[float] = Field(None, ge=0.0, description="Total amount staked")
    
    # Streaks
    max_winning_streak: Optional[int] = Field(None, ge=0, description="Longest winning streak")
    max_losing_streak: Optional[int] = Field(None, ge=0, description="Longest losing streak")
    
    # Distribution
    outcome_distribution: Optional[Dict[str, int]] = Field(
        None, description="Actual outcome distribution"
    )
    predicted_distribution: Optional[Dict[str, int]] = Field(
        None, description="Predicted outcome distribution"
    )
    
    class Config:
        """Pydantic configuration."""

        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "result_123",
                "backtest_id": "backtest_123",
                "market_type": "match_result",
                "total_predictions": 380,
                "total_matches": 380,
                "accuracy": 0.52,
                "brier_score": 0.245,
                "log_loss": 0.98,
                "calibration_error": 0.03,
            }
        }
