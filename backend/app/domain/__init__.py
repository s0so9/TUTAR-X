"""Domain models module."""

# Base models
from app.domain.base import BaseEntity, DataQualityMetadata

# Enumerations
from app.domain.enums import (
    MatchStatus,
    MatchEventType,
    MatchOutcome,
    PredictionMarketType,
    ModelType,
    InjuryStatus,
    SuspensionType,
    DataSource,
)

# Core entities
from app.domain.entities import Competition, Season, Team, Player, Venue

# Match models
from app.domain.match import Match, MatchEvent, Lineup

# Statistics models
from app.domain.statistics import (
    PlayerMatchStatistic,
    TeamMatchStatistic,
    Standing,
)

# Availability models
from app.domain.availability import Injury, Suspension

# Odds models
from app.domain.odds import Odds

# Prediction models
from app.domain.prediction import (
    Prediction,
    PredictionMarket,
    Model,
    ModelVersion,
    ModelRun,
)

# Backtest models
from app.domain.backtest import Backtest, BacktestResult

# Live models
from app.domain.live import LiveMatchState, FeatureSnapshot

# Analysis models
from app.domain.analysis import AnalysisContext

__all__ = [
    # Base
    "BaseEntity",
    "DataQualityMetadata",
    # Enums
    "MatchStatus",
    "MatchEventType",
    "MatchOutcome",
    "PredictionMarketType",
    "ModelType",
    "InjuryStatus",
    "SuspensionType",
    "DataSource",
    # Entities
    "Competition",
    "Season",
    "Team",
    "Player",
    "Venue",
    # Match
    "Match",
    "MatchEvent",
    "Lineup",
    # Statistics
    "PlayerMatchStatistic",
    "TeamMatchStatistic",
    "Standing",
    # Availability
    "Injury",
    "Suspension",
    # Odds
    "Odds",
    # Prediction
    "Prediction",
    "PredictionMarket",
    "Model",
    "ModelVersion",
    "ModelRun",
    # Backtest
    "Backtest",
    "BacktestResult",
    # Live
    "LiveMatchState",
    "FeatureSnapshot",
    # Analysis
    "AnalysisContext",
]
