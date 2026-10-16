"""Elo rating system for football match prediction.

The Elo rating system assigns a numeric strength rating to each team
and updates those ratings after each match result.

Mathematical foundation:
  Expected score (win probability):
    E_A = 1 / (1 + 10^((R_B - R_A) / 400))

  Rating update after a match:
    R_A_new = R_A + K * (S_A - E_A)
    where:
      K  = K-factor (controls rating sensitivity)
      S_A = actual score (1.0 = win, 0.5 = draw, 0.0 = loss)
      E_A = expected score before the match

Home advantage is applied by adding a fixed bonus to the home team's
effective rating before calculating expected scores.  It does NOT
modify the stored ratings so the adjustment remains explicit and
configurable.

No future data leakage: ratings are updated strictly in chronological
order and the state at any point in time reflects only past matches.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from app.prediction.interfaces import (
    PredictionModel,
    ModelPrediction,
    ModelAvailability,
    PredictionModelMetadata,
)
from app.domain.enums import ModelType


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EloRatingState:
    """Snapshot of Elo ratings at a point in time."""

    ratings: Dict[str, float]
    """Current Elo ratings keyed by team_id."""

    matches_processed: int = 0
    """Total number of matches processed."""

    last_updated: Optional[datetime] = None
    """Timestamp of the most recently processed match."""

    def get_rating(self, team_id: str, default: float = 1500.0) -> float:
        """Return current rating for a team, or *default* if unknown."""
        return self.ratings.get(team_id, default)

    def copy(self) -> "EloRatingState":
        """Return a deep copy of this state."""
        return EloRatingState(
            ratings=dict(self.ratings),
            matches_processed=self.matches_processed,
            last_updated=self.last_updated,
        )


@dataclass
class EloMatchResult:
    """Result of updating Elo ratings for a single match."""

    match_id: str
    home_team_id: str
    away_team_id: str

    home_rating_before: float
    away_rating_before: float

    home_expected: float
    """Expected score for home team before the match."""
    away_expected: float
    """Expected score for away team before the match."""

    home_actual: float
    """Actual match score: 1.0 win / 0.5 draw / 0.0 loss."""
    away_actual: float

    home_rating_after: float
    away_rating_after: float

    home_rating_change: float
    away_rating_change: float

    k_factor: float
    home_advantage: float
    played_at: datetime


@dataclass
class EloPrediction:
    """Prediction derived from Elo ratings for an upcoming match."""

    home_team_id: str
    away_team_id: str

    home_rating: float
    away_rating: float

    # Probabilities
    home_win_probability: float
    draw_probability: float
    away_win_probability: float

    # Parameters used
    home_advantage: float
    draw_probability_method: str = "Elo+draw_adjustment"

    # Metadata
    generated_at: datetime = field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# Core Elo calculator
# ---------------------------------------------------------------------------

class EloCalculator:
    """Low-level Elo calculation helpers (stateless, deterministic).

    These are pure functions wrapped in a class for namespace organisation.
    They do not store any rating state.
    """

    @staticmethod
    def expected_score(rating_a: float, rating_b: float) -> float:
        """Calculate expected score for team A against team B.

        E_A = 1 / (1 + 10^((R_B - R_A) / 400))

        Args:
            rating_a: Current Elo rating of team A.
            rating_b: Current Elo rating of team B.

        Returns:
            Expected score in [0, 1].  Values close to 1 mean A is much
            stronger; values close to 0 mean B is much stronger.
        """
        return 1.0 / (1.0 + math.pow(10.0, (rating_b - rating_a) / 400.0))

    @staticmethod
    def new_rating(
        current_rating: float,
        expected_score: float,
        actual_score: float,
        k_factor: float,
    ) -> float:
        """Compute new rating after a match.

        R_new = R_old + K * (S - E)

        Args:
            current_rating: Rating before the match.
            expected_score: Expected score before the match.
            actual_score:   Actual result (1.0 win, 0.5 draw, 0.0 loss).
            k_factor:       Sensitivity constant.

        Returns:
            Updated rating.
        """
        return current_rating + k_factor * (actual_score - expected_score)

    @staticmethod
    def outcome_to_score(
        home_goals: int,
        away_goals: int,
    ) -> Tuple[float, float]:
        """Convert match scoreline to Elo scores.

        Returns:
            (home_score, away_score) where each value is 1.0/0.5/0.0.
        """
        if home_goals > away_goals:
            return 1.0, 0.0
        if home_goals == away_goals:
            return 0.5, 0.5
        return 0.0, 1.0

    @staticmethod
    def draw_probability(
        home_expected: float,
        away_expected: float,
        draw_base: float = 0.25,
        draw_scale: float = 0.5,
    ) -> float:
        """Estimate draw probability from Elo expected scores.

        Uses a simple draw model: draws are more likely when teams are
        evenly matched.  The closer the expected scores to 0.5 each,
        the higher the draw probability.

        The model is:
            balance = 1 - |E_home - E_away|   (1 when equal, 0 when max diff)
            draw_prob = draw_base + draw_scale * (balance - 0.5) * 2
                      = draw_base + draw_scale * (2*balance - 1)
        Clipped to [0.05, 0.40].

        Args:
            home_expected: Elo expected score for home team.
            away_expected: Elo expected score for away team.
            draw_base:     Base draw probability when teams are equal.
            draw_scale:    Scaling factor.

        Returns:
            Estimated draw probability.
        """
        balance = 1.0 - abs(home_expected - away_expected)
        draw_prob = draw_base + draw_scale * (2.0 * balance - 1.0)
        return max(0.05, min(0.40, draw_prob))


# ---------------------------------------------------------------------------
# Elo rating system
# ---------------------------------------------------------------------------

class EloRatingSystem:
    """Elo rating system that maintains team ratings over time.

    This class is the main stateful component.  It processes historical
    matches chronologically, updating ratings after each match.

    Design decisions:
    - Ratings are stored per team_id.
    - New teams start at `initial_rating` on their first match.
    - Home advantage is applied to expected-score calculation only; it
      does not modify stored ratings, so it is always explicit.
    - Chronological order must be maintained by the caller when processing
      batches of historical matches.
    """

    def __init__(
        self,
        k_factor: float = 32.0,
        initial_rating: float = 1500.0,
        home_advantage: float = 100.0,
    ):
        """Initialise the rating system.

        Args:
            k_factor:        Rating sensitivity (higher = faster changes).
                             Typical values: 20-40 for club football.
            initial_rating:  Starting rating for new/unknown teams.
            home_advantage:  Elo points added to home team's effective
                             rating when computing expected scores.
                             100 points ≈ ~14 percentage points extra
                             win probability for an average home team.
        """
        if k_factor <= 0:
            raise ValueError(f"k_factor must be positive, got {k_factor}")
        if initial_rating <= 0:
            raise ValueError(
                f"initial_rating must be positive, got {initial_rating}"
            )
        if home_advantage < 0:
            raise ValueError(
                f"home_advantage must be >= 0, got {home_advantage}"
            )

        self.k_factor = k_factor
        self.initial_rating = initial_rating
        self.home_advantage = home_advantage

        self._ratings: Dict[str, float] = {}
        self._history: List[EloMatchResult] = []
        self._matches_processed: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_rating(self, team_id: str) -> float:
        """Return current rating for a team.

        Returns `initial_rating` for unknown teams.
        """
        return self._ratings.get(team_id, self.initial_rating)

    def get_rating_at_time(self, team_id: str, at_timestamp: datetime) -> float:
        """Return historical rating for a team at a specific timestamp.
        
        Reconstructs the team's rating as it was at at_timestamp by finding
        the last processed match before that timestamp.
        
        CRITICAL TEMPORAL VALIDITY: This method ensures opponent adjustments
        use historical ratings, preventing temporal leakage.
        
        Args:
            team_id: Team identifier
            at_timestamp: The timestamp at which to retrieve the rating
            
        Returns:
            The team's Elo rating as it was at at_timestamp.
            Returns initial_rating if no matches found before at_timestamp.
            
        Algorithm:
            1. Find last match in self._history where:
               - played_at < at_timestamp
               - Either home_team_id or away_team_id == team_id
            2. Return rating_after from that match
            3. If no matches found, return initial_rating
        """
        from datetime import timezone
        
        # Ensure at_timestamp is timezone-aware
        if at_timestamp.tzinfo is None:
            at_timestamp = at_timestamp.replace(tzinfo=timezone.utc)
        
        # Find the last match involving this team before at_timestamp
        last_match_result = None
        
        for match_result in self._history:
            # Ensure match played_at is timezone-aware
            played_at = match_result.played_at
            if played_at.tzinfo is None:
                played_at = played_at.replace(tzinfo=timezone.utc)
            
            # Skip matches at or after the cutoff timestamp
            if played_at >= at_timestamp:
                continue
            
            # Check if this match involves the team
            if match_result.home_team_id == team_id:
                last_match_result = match_result
            elif match_result.away_team_id == team_id:
                last_match_result = match_result
        
        # If we found a match, return the rating after that match
        if last_match_result is not None:
            if last_match_result.home_team_id == team_id:
                return last_match_result.home_rating_after
            else:  # away_team_id == team_id
                return last_match_result.away_rating_after
        
        # No matches found before at_timestamp, return initial rating
        return self.initial_rating

    def get_state(self) -> EloRatingState:
        """Return a snapshot of the current rating state."""
        return EloRatingState(
            ratings=dict(self._ratings),
            matches_processed=self._matches_processed,
            last_updated=(
                self._history[-1].played_at if self._history else None
            ),
        )

    def process_match(
        self,
        match_id: str,
        home_team_id: str,
        away_team_id: str,
        home_goals: int,
        away_goals: int,
        played_at: datetime,
    ) -> EloMatchResult:
        """Update ratings based on a completed match result.

        IMPORTANT: Matches must be processed in strictly chronological
        order to prevent future data leakage.

        Args:
            match_id:      Unique identifier for the match.
            home_team_id:  Home team identifier.
            away_team_id:  Away team identifier.
            home_goals:    Goals scored by home team.
            away_goals:    Goals scored by away team.
            played_at:     When the match was played.

        Returns:
            EloMatchResult describing the rating changes.

        Raises:
            ValueError: If goals are negative.
        """
        if home_goals < 0 or away_goals < 0:
            raise ValueError(
                f"Goals cannot be negative: home={home_goals}, away={away_goals}"
            )

        # Ratings before the match
        home_rating_before = self.get_rating(home_team_id)
        away_rating_before = self.get_rating(away_team_id)

        # Apply home advantage to effective ratings for expected score
        home_effective = home_rating_before + self.home_advantage
        away_effective = away_rating_before

        # Expected scores
        home_expected = EloCalculator.expected_score(home_effective, away_effective)
        away_expected = EloCalculator.expected_score(away_effective, home_effective)

        # Actual scores
        home_actual, away_actual = EloCalculator.outcome_to_score(
            home_goals, away_goals
        )

        # New ratings
        home_rating_after = EloCalculator.new_rating(
            home_rating_before, home_expected, home_actual, self.k_factor
        )
        away_rating_after = EloCalculator.new_rating(
            away_rating_before, away_expected, away_actual, self.k_factor
        )

        # Persist
        self._ratings[home_team_id] = home_rating_after
        self._ratings[away_team_id] = away_rating_after
        self._matches_processed += 1

        result = EloMatchResult(
            match_id=match_id,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_rating_before=home_rating_before,
            away_rating_before=away_rating_before,
            home_expected=home_expected,
            away_expected=away_expected,
            home_actual=home_actual,
            away_actual=away_actual,
            home_rating_after=home_rating_after,
            away_rating_after=away_rating_after,
            home_rating_change=home_rating_after - home_rating_before,
            away_rating_change=away_rating_after - away_rating_before,
            k_factor=self.k_factor,
            home_advantage=self.home_advantage,
            played_at=played_at,
        )

        self._history.append(result)
        return result

    def process_matches_chronologically(
        self,
        matches: List[Dict],
    ) -> List[EloMatchResult]:
        """Process a batch of matches in chronological order.

        Args:
            matches: List of dicts with keys:
                     match_id, home_team_id, away_team_id,
                     home_goals, away_goals, played_at (datetime).

        Returns:
            List of EloMatchResult objects.

        Raises:
            ValueError: If a match is missing required fields.
        """
        required_keys = {
            "match_id", "home_team_id", "away_team_id",
            "home_goals", "away_goals", "played_at",
        }

        for m in matches:
            missing = required_keys - set(m.keys())
            if missing:
                raise ValueError(
                    f"Match dict missing required keys: {missing}"
                )

        # Sort chronologically to enforce no-future-leakage
        sorted_matches = sorted(matches, key=lambda m: m["played_at"])

        results = []
        for m in sorted_matches:
            result = self.process_match(
                match_id=m["match_id"],
                home_team_id=m["home_team_id"],
                away_team_id=m["away_team_id"],
                home_goals=m["home_goals"],
                away_goals=m["away_goals"],
                played_at=m["played_at"],
            )
            results.append(result)

        return results

    def get_history(self) -> List[EloMatchResult]:
        """Return full history of processed match results."""
        return list(self._history)

    def reset(self) -> None:
        """Reset all ratings and history to initial state."""
        self._ratings.clear()
        self._history.clear()
        self._matches_processed = 0

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(
        self,
        home_team_id: str,
        away_team_id: str,
    ) -> EloPrediction:
        """Generate win/draw/loss probabilities from current Elo ratings.

        The draw probability is estimated from the closeness of the two
        teams' expected scores.  Home and away win probabilities are
        derived by distributing the remaining probability proportionally.

        Args:
            home_team_id: Home team identifier.
            away_team_id: Away team identifier.

        Returns:
            EloPrediction with normalised probabilities.
        """
        home_rating = self.get_rating(home_team_id)
        away_rating = self.get_rating(away_team_id)

        # Apply home advantage for expected scores
        home_effective = home_rating + self.home_advantage
        away_effective = away_rating

        home_expected = EloCalculator.expected_score(home_effective, away_effective)
        away_expected = EloCalculator.expected_score(away_effective, home_effective)

        # Estimate draw probability
        draw_prob = EloCalculator.draw_probability(home_expected, away_expected)

        # Distribute remaining probability proportionally to expected scores
        remaining = 1.0 - draw_prob
        total_expected = home_expected + away_expected  # always ~1.0

        if total_expected > 0:
            home_win_prob = remaining * (home_expected / total_expected)
            away_win_prob = remaining * (away_expected / total_expected)
        else:
            home_win_prob = remaining / 2.0
            away_win_prob = remaining / 2.0

        # Normalise to ensure exact sum = 1.0
        total = home_win_prob + draw_prob + away_win_prob
        home_win_prob /= total
        draw_prob /= total
        away_win_prob /= total

        return EloPrediction(
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_rating=home_rating,
            away_rating=away_rating,
            home_win_probability=home_win_prob,
            draw_probability=draw_prob,
            away_win_probability=away_win_prob,
            home_advantage=self.home_advantage,
            generated_at=datetime.now(),
        )


# ---------------------------------------------------------------------------
# PredictionModel interface wrapper
# ---------------------------------------------------------------------------

class EloModel(PredictionModel):
    """Elo prediction model implementing PredictionModel interface.
    
    This wraps the EloRatingSystem to provide the standard prediction interface.
    The Elo ratings must be maintained externally and passed via features.
    """
    
    MODEL_ID = "elo_v1"
    MODEL_VERSION = "1.0.0"
    
    def __init__(
        self,
        k_factor: float = 32.0,
        initial_rating: float = 1500.0,
        home_advantage: float = 100.0,
    ):
        """Initialize Elo model.
        
        Args:
            k_factor: Rating sensitivity
            initial_rating: Starting rating for unknown teams
            home_advantage: Elo points added to home team for prediction
        """
        self.rating_system = EloRatingSystem(
            k_factor=k_factor,
            initial_rating=initial_rating,
            home_advantage=home_advantage
        )
    
    def predict(
        self,
        features: Dict[str, Optional[float]],
        match_context: Optional[Dict[str, Any]] = None
    ) -> ModelPrediction | ModelAvailability:
        """Generate prediction using Elo ratings.
        
        Args:
            features: Feature dictionary (expects elo_home, elo_away)
            match_context: Additional context with home_team_id, away_team_id
        
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
        
        # Get Elo ratings from features or match context
        home_rating = features.get("elo_home")
        away_rating = features.get("elo_away")
        
        # If not in features, try to get from rating system using team IDs
        if home_rating is None or away_rating is None:
            if not match_context or "home_team_id" not in match_context or "away_team_id" not in match_context:
                return ModelAvailability(
                    model_id=self.MODEL_ID,
                    available=False,
                    reason="missing_team_ratings",
                    missing_features=["elo_home", "elo_away"]
                )
            
            home_team_id = match_context["home_team_id"]
            away_team_id = match_context["away_team_id"]
            
            home_rating = self.rating_system.get_rating(home_team_id)
            away_rating = self.rating_system.get_rating(away_team_id)
        
        # Generate Elo prediction
        # Create temporary Elo system with these ratings
        temp_system = EloRatingSystem(
            k_factor=self.rating_system.k_factor,
            initial_rating=self.rating_system.initial_rating,
            home_advantage=self.rating_system.home_advantage
        )
        
        # Set the ratings manually
        temp_system._ratings["home"] = home_rating
        temp_system._ratings["away"] = away_rating
        
        elo_pred = temp_system.predict("home", "away")
        
        # Convert to score distribution
        # Elo doesn't natively produce score distributions, so we derive from probabilities
        # Use a simple approximation: distribute probabilities across common scorelines
        score_dist = self._derive_score_distribution(
            elo_pred.home_win_probability,
            elo_pred.draw_probability,
            elo_pred.away_win_probability
        )
        
        # Estimate expected goals from Elo ratings
        # Simple heuristic: higher rating difference = more goals
        rating_diff = home_rating - away_rating + self.rating_system.home_advantage
        home_xg = 1.5 + (rating_diff / 400.0)  # Rough approximation
        away_xg = 1.5 - (rating_diff / 400.0)
        home_xg = max(0.5, min(3.5, home_xg))
        away_xg = max(0.5, min(3.5, away_xg))
        
        return ModelPrediction(
            model_id=self.MODEL_ID,
            home_score_mean=home_xg,
            away_score_mean=away_xg,
            score_distribution=score_dist,
            home_win_prob=elo_pred.home_win_probability,
            draw_prob=elo_pred.draw_probability,
            away_win_prob=elo_pred.away_win_probability,
            confidence_score=self._calculate_confidence(home_rating, away_rating),
            data_quality_score=self._calculate_data_quality(features),
            metadata={
                "home_rating": home_rating,
                "away_rating": away_rating,
                "rating_difference": home_rating - away_rating,
                "home_advantage": self.rating_system.home_advantage,
                "k_factor": self.rating_system.k_factor
            }
        )
    
    def get_metadata(self) -> PredictionModelMetadata:
        """Return model metadata."""
        return PredictionModelMetadata(
            model_id=self.MODEL_ID,
            model_type=ModelType.ELO,
            version=self.MODEL_VERSION,
            description="Elo rating-based match outcome prediction",
            required_features=["elo_home", "elo_away"],
            optional_features=[],
            min_samples_required=0  # Elo can work with initial ratings
        )
    
    def check_requirements(
        self, 
        features: Dict[str, Optional[float]]
    ) -> Tuple[bool, List[str]]:
        """Check if required data is available."""
        # Elo ratings can come from features or be looked up
        # We'll be flexible here - if ratings aren't in features, we'll try match_context
        has_ratings = (
            features.get("elo_home") is not None and 
            features.get("elo_away") is not None
        )
        
        if not has_ratings:
            return (False, ["elo_home", "elo_away"])
        
        return (True, [])
    
    def _derive_score_distribution(
        self,
        home_win_prob: float,
        draw_prob: float,
        away_win_prob: float
    ) -> Dict[Tuple[int, int], float]:
        """Derive approximate score distribution from 1X2 probabilities.
        
        This is a simplified approximation since Elo doesn't natively produce
        score distributions.
        """
        dist = {}
        
        # Common draws
        dist[(0, 0)] = draw_prob * 0.25
        dist[(1, 1)] = draw_prob * 0.35
        dist[(2, 2)] = draw_prob * 0.25
        dist[(3, 3)] = draw_prob * 0.15
        
        # Common home wins
        dist[(1, 0)] = home_win_prob * 0.20
        dist[(2, 0)] = home_win_prob * 0.15
        dist[(2, 1)] = home_win_prob * 0.25
        dist[(3, 0)] = home_win_prob * 0.10
        dist[(3, 1)] = home_win_prob * 0.15
        dist[(3, 2)] = home_win_prob * 0.10
        dist[(4, 1)] = home_win_prob * 0.05
        
        # Common away wins
        dist[(0, 1)] = away_win_prob * 0.20
        dist[(0, 2)] = away_win_prob * 0.15
        dist[(1, 2)] = away_win_prob * 0.25
        dist[(0, 3)] = away_win_prob * 0.10
        dist[(1, 3)] = away_win_prob * 0.15
        dist[(2, 3)] = away_win_prob * 0.10
        dist[(1, 4)] = away_win_prob * 0.05
        
        return dist
    
    def _calculate_confidence(self, home_rating: float, away_rating: float) -> float:
        """Calculate confidence based on rating quality."""
        # Higher confidence if ratings are far from initial (more games played)
        initial = self.rating_system.initial_rating
        home_diff = abs(home_rating - initial)
        away_diff = abs(away_rating - initial)
        
        # Normalize to 0-1 range (assume 300 rating points = high confidence)
        home_conf = min(1.0, home_diff / 300.0)
        away_conf = min(1.0, away_diff / 300.0)
        
        return (home_conf + away_conf) / 2.0
    
    def _calculate_data_quality(self, features: Dict[str, Optional[float]]) -> float:
        """Calculate data quality score."""
        if features.get("elo_home") is not None and features.get("elo_away") is not None:
            return 1.0
        return 0.0

