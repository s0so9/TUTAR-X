"""Poisson-based football match prediction model.

This module implements a foundational Poisson prediction model for football matches.
The Poisson distribution models the number of goals scored by each team independently.

Mathematical Foundation:
- P(X = k) = (λ^k * e^(-λ)) / k!
- where λ (lambda) is the expected goals parameter
- k is the number of goals

The model calculates:
1. Expected goals for home and away teams (lambda parameters)
2. Probability distribution for each team's goals (0 to max_goals)
3. Joint probability for all scorelines
4. Market probabilities (1X2, BTTS, Over/Under, Correct Score)
"""

import math
from datetime import datetime
from typing import Dict, Tuple, Optional, List, Any
from dataclasses import dataclass

from app.prediction.interfaces import (
    PredictionModel,
    ModelPrediction,
    ModelAvailability,
    PredictionModelMetadata,
)
from app.domain.enums import ModelType


def rating_lambdas_from_features(
    features: Dict[str, Optional[float]],
) -> Optional[Tuple[float, float]]:
    """(home, away) expected goals from global ratings, if both are present.

    Shared by the goal models so they all use the same rating-based lambdas
    (see app.prediction.team_ratings); None means fall back to raw averages.
    """
    home = features.get("home_lambda_rating")
    away = features.get("away_lambda_rating")
    if home is None or away is None or home <= 0 or away <= 0:
        return None
    return float(home), float(away)


@dataclass
class PoissonPrediction:
    """Result of Poisson prediction."""

    home_lambda: float
    away_lambda: float
    max_goals: int

    # Goal probabilities
    home_goal_probabilities: List[float]  # P(home scores 0), P(home scores 1), ...
    away_goal_probabilities: List[float]  # P(away scores 0), P(away scores 1), ...

    # Scoreline matrix
    scoreline_probabilities: Dict[Tuple[int, int], float]  # (home_goals, away_goals) -> probability

    # Market probabilities
    home_win_probability: float
    draw_probability: float
    away_win_probability: float

    btts_yes_probability: float
    btts_no_probability: float

    over_under_probabilities: Dict[float, Tuple[float, float]]  # line -> (over_prob, under_prob)

    # Top N correct scores
    top_scorelines: List[Tuple[Tuple[int, int], float]]  # [(scoreline, probability), ...]

    # Probability mass captured (should be close to 1.0)
    probability_mass_captured: float


class PoissonModel(PredictionModel):
    """Poisson-based football prediction model.

    This model assumes:
    1. Goals scored by each team follow independent Poisson distributions
    2. The expected goals (lambda) can be estimated from team strength features
    3. Match outcomes are determined by the joint goal distribution

    Limitations:
    - Assumes independence between home and away goals (simplification)
    - Does not account for correlation in low-scoring matches
    - Truncates distribution at max_goals
    """

    MODEL_ID = "poisson_v1"
    MODEL_VERSION = "1.0.0"

    def __init__(self, max_goals: int = 10):
        """Initialize Poisson model.

        Args:
            max_goals: Maximum goals to consider in distributions (default: 10)
                      Higher values capture more probability mass but increase computation

        Raises:
            ValueError: If max_goals < 1
        """
        if max_goals < 1:
            raise ValueError("max_goals must be at least 1")

        self.max_goals = max_goals

    # Backward compatibility: keep the original predict method for existing code
    def predict_from_lambda(
        self,
        home_lambda: float,
        away_lambda: float,
    ) -> PoissonPrediction:
        """Generate prediction for a match using Poisson model (legacy interface).

        This method preserves the original interface for backward compatibility.
        New code should use the predict() method with features dict.

        Args:
            home_lambda: Expected goals for home team (must be >= 0)
            away_lambda: Expected goals for away team (must be >= 0)

        Returns:
            PoissonPrediction with all probabilities

        Raises:
            ValueError: If lambda values are invalid
        """
        return self._predict_internal(home_lambda, away_lambda)

    def _calculate_goal_probabilities(self, lambda_: float) -> List[float]:
        """Calculate Poisson probability mass function for 0 to max_goals.

        Uses the Poisson PMF: P(X = k) = (λ^k * e^(-λ)) / k!

        Args:
            lambda_: Expected goals parameter

        Returns:
            List of probabilities [P(0 goals), P(1 goal), ..., P(max_goals)]
        """
        probabilities = []

        for k in range(self.max_goals + 1):
            prob = self._poisson_pmf(k, lambda_)
            probabilities.append(prob)

        return probabilities

    @staticmethod
    def _poisson_pmf(k: int, lambda_: float) -> float:
        """Calculate Poisson probability mass function.

        P(X = k) = (λ^k * e^(-λ)) / k!

        Args:
            k: Number of events (goals)
            lambda_: Expected number of events (expected goals)

        Returns:
            Probability of exactly k events
        """
        # Handle edge case: lambda = 0
        if lambda_ == 0:
            return 1.0 if k == 0 else 0.0

        # Calculate using logarithms for numerical stability
        # log(P(X = k)) = k * log(λ) - λ - log(k!)
        log_prob = k * math.log(lambda_) - lambda_ - math.lgamma(k + 1)
        return math.exp(log_prob)

    def _calculate_scoreline_probabilities(
        self,
        home_probs: List[float],
        away_probs: List[float],
    ) -> Dict[Tuple[int, int], float]:
        """Calculate joint probability for all scorelines.

        Assumes independence: P(home=i, away=j) = P(home=i) * P(away=j)

        Args:
            home_probs: Home team goal probabilities
            away_probs: Away team goal probabilities

        Returns:
            Dictionary mapping (home_goals, away_goals) to probability
        """
        scorelines = {}

        for home_goals in range(self.max_goals + 1):
            for away_goals in range(self.max_goals + 1):
                prob = home_probs[home_goals] * away_probs[away_goals]
                scorelines[(home_goals, away_goals)] = prob

        return scorelines

    @staticmethod
    def _calculate_1x2_probabilities(
        scoreline_probs: Dict[Tuple[int, int], float]
    ) -> Tuple[float, float, float]:
        """Calculate match result probabilities (1X2).

        Home win: home_goals > away_goals
        Draw: home_goals == away_goals
        Away win: home_goals < away_goals

        Args:
            scoreline_probs: Scoreline probability matrix

        Returns:
            (home_win_prob, draw_prob, away_win_prob)
        """
        home_win = 0.0
        draw = 0.0
        away_win = 0.0

        for (home_goals, away_goals), prob in scoreline_probs.items():
            if home_goals > away_goals:
                home_win += prob
            elif home_goals == away_goals:
                draw += prob
            else:  # home_goals < away_goals
                away_win += prob

        # Normalize to ensure sum = 1.0
        total = home_win + draw + away_win
        if total > 0:
            home_win /= total
            draw /= total
            away_win /= total

        return home_win, draw, away_win

    @staticmethod
    def _calculate_btts_probabilities(
        scoreline_probs: Dict[Tuple[int, int], float]
    ) -> Tuple[float, float]:
        """Calculate Both Teams To Score probabilities.

        BTTS Yes: Both teams score at least 1 goal
        BTTS No: At least one team scores 0 goals

        Args:
            scoreline_probs: Scoreline probability matrix

        Returns:
            (btts_yes_prob, btts_no_prob)
        """
        btts_yes = 0.0
        btts_no = 0.0

        for (home_goals, away_goals), prob in scoreline_probs.items():
            if home_goals >= 1 and away_goals >= 1:
                btts_yes += prob
            else:
                btts_no += prob

        return btts_yes, btts_no

    @staticmethod
    def _calculate_over_under_probabilities(
        scoreline_probs: Dict[Tuple[int, int], float]
    ) -> Dict[float, Tuple[float, float]]:
        """Calculate Over/Under probabilities for common lines.

        Args:
            scoreline_probs: Scoreline probability matrix

        Returns:
            Dictionary mapping line to (over_prob, under_prob)
            Lines: 0.5, 1.5, 2.5, 3.5, 4.5, 5.5
        """
        lines = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5]
        over_under = {}

        for line in lines:
            over = 0.0
            under = 0.0

            for (home_goals, away_goals), prob in scoreline_probs.items():
                total_goals = home_goals + away_goals

                if total_goals > line:
                    over += prob
                else:
                    under += prob

            over_under[line] = (over, under)

        return over_under

    @staticmethod
    def _get_top_scorelines(
        scoreline_probs: Dict[Tuple[int, int], float],
        n: int = 10
    ) -> List[Tuple[Tuple[int, int], float]]:
        """Get top N most likely scorelines.

        Args:
            scoreline_probs: Scoreline probability matrix
            n: Number of top scorelines to return

        Returns:
            List of (scoreline, probability) tuples, sorted by probability descending
        """
        sorted_scorelines = sorted(
            scoreline_probs.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return sorted_scorelines[:n]

    def estimate_lambda(
        self,
        team_attack_strength: float,
        opponent_defense_strength: float,
        venue_adjustment: float = 1.0,
    ) -> float:
        """CANONICAL lambda estimation method - single source of truth.

        Formula: λ = team_attack_strength × opponent_defense_strength × venue_adjustment

        Domain logic:
        - team_attack_strength: team's goals scored per match (higher = more attacking)
        - opponent_defense_strength: opponent's goals conceded per match (higher = weaker defense)
        - venue_adjustment: home advantage multiplier (typically 1.0 for away, 1.1-1.3 for home)

        Higher values in all three components → higher expected goals.
        This is the ONLY lambda formula; all call sites must use this method.

        Args:
            team_attack_strength: Goals scored per match by team (≥ 0)
            opponent_defense_strength: Goals conceded per match by opponent (≥ 0)
            venue_adjustment: Home advantage factor (default: 1.0 = neutral)

        Returns:
            Estimated lambda (expected goals, ≥ 0)

        Raises:
            ValueError: If any strength value is negative
        """
        if team_attack_strength < 0:
            raise ValueError(f"team_attack_strength must be >= 0, got {team_attack_strength}")
        if opponent_defense_strength < 0:
            raise ValueError(f"opponent_defense_strength must be >= 0, got {opponent_defense_strength}")
        if venue_adjustment < 0:
            raise ValueError(f"venue_adjustment must be >= 0, got {venue_adjustment}")

        # CANONICAL FORMULA: attack × defense_weakness × venue
        lambda_ = team_attack_strength * opponent_defense_strength * venue_adjustment

        return max(0.0, lambda_)  # Ensure non-negative

    # Backward compatibility alias - deprecated
    def estimate_lambda_from_features(
        self,
        team_attack_strength: float,
        opponent_defense_strength: float,
        venue_adjustment: float = 1.0,
    ) -> float:
        """DEPRECATED: Use estimate_lambda() instead.

        Kept for backward compatibility only.
        """
        return self.estimate_lambda(
            team_attack_strength=team_attack_strength,
            opponent_defense_strength=opponent_defense_strength,
            venue_adjustment=venue_adjustment
        )

    # ========================================================================
    # PredictionModel Interface Implementation
    # ========================================================================

    def predict(
        self,
        features: Dict[str, Optional[float]],
        match_context: Optional[Dict[str, Any]] = None
    ) -> ModelPrediction | ModelAvailability:
        """Generate prediction using the PredictionModel interface.

        Args:
            features: Feature dictionary from MatchFeatureExtractor
            match_context: Additional context (optional, not used by Poisson)

        Returns:
            ModelPrediction if successful, ModelAvailability if unable to predict
        """
        # Check requirements
        requirements_met, missing = self.check_requirements(features)
        if not requirements_met:
            return ModelAvailability(
                model_id=self.MODEL_ID,
                available=False,
                reason="insufficient_data",
                missing_features=missing
            )

        rating_lambdas = rating_lambdas_from_features(features)
        if rating_lambdas is not None:
            # Global attack/defence ratings: league-normalised, cross-league
            # comparable and include home advantage.
            home_lambda, away_lambda = rating_lambdas
        else:
            # Fallback: CANONICAL lambda estimation from raw averages
            # Home team expected goals: home attack vs away defense
            home_attack = features.get("home_goals_scored_avg", 0.0) or 0.0
            away_defense = features.get("away_goals_conceded_avg", 1.0) or 1.0  # Default to neutral
            home_lambda = self.estimate_lambda(
                team_attack_strength=home_attack,
                opponent_defense_strength=away_defense,
                venue_adjustment=1.0  # Can be enhanced with home advantage
            )

            # Away team expected goals: away attack vs home defense
            away_attack = features.get("away_goals_scored_avg", 0.0) or 0.0
            home_defense = features.get("home_goals_conceded_avg", 1.0) or 1.0  # Default to neutral
            away_lambda = self.estimate_lambda(
                team_attack_strength=away_attack,
                opponent_defense_strength=home_defense,
                venue_adjustment=1.0
            )

        # Validate lambdas
        if home_lambda < 0 or away_lambda < 0:
            return ModelAvailability(
                model_id=self.MODEL_ID,
                available=False,
                reason="invalid_features",
                missing_features=[]
            )

        # Generate prediction using existing internal method
        poisson_pred = self._predict_internal(home_lambda, away_lambda)

        # Convert to ModelPrediction
        # Build score distribution dict
        score_dist = {
            (h, a): prob
            for (h, a), prob in poisson_pred.scoreline_probabilities.items()
        }

        return ModelPrediction(
            model_id=self.MODEL_ID,
            home_score_mean=home_lambda,
            away_score_mean=away_lambda,
            score_distribution=score_dist,
            home_win_prob=poisson_pred.home_win_probability,
            draw_prob=poisson_pred.draw_probability,
            away_win_prob=poisson_pred.away_win_probability,
            confidence_score=self._calculate_confidence(features),
            data_quality_score=self._calculate_data_quality(features),
            metadata={
                "max_goals": self.max_goals,
                "probability_mass_captured": poisson_pred.probability_mass_captured,
                "top_scorelines": [
                    {"scoreline": f"{h}-{a}", "probability": p}
                    for (h, a), p in poisson_pred.top_scorelines[:5]
                ]
            }
        )

    def get_metadata(self) -> PredictionModelMetadata:
        """Return model metadata.

        Returns:
            PredictionModelMetadata with model information
        """
        return PredictionModelMetadata(
            model_id=self.MODEL_ID,
            model_type=ModelType.POISSON,
            version=self.MODEL_VERSION,
            description="Independent Poisson distribution for home and away goals",
            required_features=[
                "home_goals_scored_avg",
                "away_goals_scored_avg"
            ],
            optional_features=[
                "home_goals_conceded_avg",
                "away_goals_conceded_avg"
            ],
            min_samples_required=5
        )

    def check_requirements(
        self,
        features: Dict[str, Optional[float]]
    ) -> Tuple[bool, List[str]]:
        """Check if required data is available.

        Args:
            features: Feature dictionary

        Returns:
            (requirements_met, missing_requirements)
        """
        required = ["home_goals_scored_avg", "away_goals_scored_avg"]
        missing = [f for f in required if features.get(f) is None]

        return (len(missing) == 0, missing)

    def _calculate_confidence(self, features: Dict[str, Optional[float]]) -> float:
        """Calculate confidence score based on data availability.

        Args:
            features: Feature dictionary

        Returns:
            Confidence score between 0.0 and 1.0
        """
        # Base confidence
        confidence = 0.7

        # Increase if defense features available
        if features.get("home_goals_conceded_avg") is not None:
            confidence += 0.1
        if features.get("away_goals_conceded_avg") is not None:
            confidence += 0.1

        # Increase if additional context available
        if features.get("home_match_count", 0) >= 10:
            confidence += 0.05
        if features.get("away_match_count", 0) >= 10:
            confidence += 0.05

        return min(1.0, confidence)

    def _calculate_data_quality(self, features: Dict[str, Optional[float]]) -> float:
        """Calculate data quality score.

        Args:
            features: Feature dictionary

        Returns:
            Data quality score between 0.0 and 1.0
        """
        total_features = 4  # Core features we look for
        available = sum(
            1 for f in [
                "home_goals_scored_avg",
                "away_goals_scored_avg",
                "home_goals_conceded_avg",
                "away_goals_conceded_avg"
            ]
            if features.get(f) is not None
        )

        return available / total_features

    def _predict_internal(
        self,
        home_lambda: float,
        away_lambda: float,
    ) -> PoissonPrediction:
        """Internal prediction method (preserves backward compatibility).

        This is the original predict() method, renamed for internal use.

        Args:
            home_lambda: Expected goals for home team (must be >= 0)
            away_lambda: Expected goals for away team (must be >= 0)

        Returns:
            PoissonPrediction with all probabilities

        Raises:
            ValueError: If lambda values are invalid
        """
        # Validate inputs
        if home_lambda < 0:
            raise ValueError(f"home_lambda must be >= 0, got {home_lambda}")
        if away_lambda < 0:
            raise ValueError(f"away_lambda must be >= 0, got {away_lambda}")

        # Calculate goal probabilities for each team
        home_probs = self._calculate_goal_probabilities(home_lambda)
        away_probs = self._calculate_goal_probabilities(away_lambda)

        # Calculate scoreline matrix
        scoreline_probs = self._calculate_scoreline_probabilities(home_probs, away_probs)

        # Calculate market probabilities
        home_win, draw, away_win = self._calculate_1x2_probabilities(scoreline_probs)
        btts_yes, btts_no = self._calculate_btts_probabilities(scoreline_probs)
        over_under = self._calculate_over_under_probabilities(scoreline_probs)

        # Get top scorelines
        top_scorelines = self._get_top_scorelines(scoreline_probs, n=10)

        # Calculate probability mass captured
        total_prob = sum(scoreline_probs.values())

        return PoissonPrediction(
            home_lambda=home_lambda,
            away_lambda=away_lambda,
            max_goals=self.max_goals,
            home_goal_probabilities=home_probs,
            away_goal_probabilities=away_probs,
            scoreline_probabilities=scoreline_probs,
            home_win_probability=home_win,
            draw_probability=draw,
            away_win_probability=away_win,
            btts_yes_probability=btts_yes,
            btts_no_probability=btts_no,
            over_under_probabilities=over_under,
            top_scorelines=top_scorelines,
            probability_mass_captured=total_prob,
        )
