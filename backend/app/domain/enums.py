"""Domain enumerations."""

from enum import Enum


class MatchStatus(str, Enum):
    """Match status enumeration."""

    SCHEDULED = "SCHEDULED"
    LIVE = "LIVE"
    HALF_TIME = "HALF_TIME"
    FINISHED = "FINISHED"
    POSTPONED = "POSTPONED"
    CANCELLED = "CANCELLED"
    SUSPENDED = "SUSPENDED"


class MatchEventType(str, Enum):
    """Match event type enumeration."""

    GOAL = "goal"
    OWN_GOAL = "own_goal"
    PENALTY = "penalty"
    YELLOW_CARD = "yellow_card"
    RED_CARD = "red_card"
    SUBSTITUTION = "substitution"
    VAR_DECISION = "var_decision"
    OFFSIDE = "offside"
    CORNER = "corner"
    FREE_KICK = "free_kick"


class MatchOutcome(str, Enum):
    """Match outcome enumeration."""

    HOME_WIN = "home_win"
    DRAW = "draw"
    AWAY_WIN = "away_win"


class PredictionMarketType(str, Enum):
    """Prediction market type enumeration."""

    MATCH_RESULT = "match_result"  # 1X2
    OVER_UNDER = "over_under"
    BTTS = "btts"  # Both Teams To Score
    OVER_2_5_AND_BTTS = "over_2_5_and_btts"  # Combined market: Over 2.5 goals AND both teams score
    DOUBLE_CHANCE = "double_chance"  # Phase 5: Double chance market (e.g., 1X, 12, X2)
    HANDICAP = "handicap"  # Phase 5: Handicap/Asian handicap market
    CORRECT_SCORE = "correct_score"
    TEAM_GOALS = "team_goals"
    TOTAL_GOALS = "total_goals"
    CORNERS = "corners"
    CARDS = "cards"
    PLAYER_MARKET = "player_market"


class ModelType(str, Enum):
    """Prediction model type enumeration."""

    POISSON = "poisson"
    NEGATIVE_BINOMIAL = "negative_binomial"
    DIXON_COLES = "dixon_coles"
    ELO = "elo"
    LOGISTIC_REGRESSION = "logistic_regression"
    FORM_ADJUSTED = "form_adjusted"
    RANDOM_FOREST = "random_forest"
    GRADIENT_BOOSTING = "gradient_boosting"
    NEURAL_NETWORK = "neural_network"
    MONTE_CARLO = "monte_carlo"
    ENSEMBLE = "ensemble"
    META_MODEL = "meta_model"


class InjuryStatus(str, Enum):
    """Player injury status enumeration."""

    DOUBTFUL = "doubtful"
    OUT = "out"
    RECOVERING = "recovering"
    FIT = "fit"


class SuspensionType(str, Enum):
    """Suspension type enumeration."""

    YELLOW_CARDS = "yellow_cards"
    RED_CARD = "red_card"
    DISCIPLINARY = "disciplinary"


class DataSource(str, Enum):
    """Data source enumeration."""

    DEVELOPMENT = "development"  # Mock/test data
    API_FOOTBALL = "api_football"
    MANUAL = "manual"
    CALCULATED = "calculated"
