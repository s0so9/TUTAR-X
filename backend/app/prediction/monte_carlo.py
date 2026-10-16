"""Monte Carlo Simulation for match outcome prediction.

Generates match outcome distributions through repeated Poisson sampling,
deriving comprehensive market probabilities from simulation results.
"""

import random
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from app.prediction.interfaces import (
    PredictionModel,
    ModelPrediction,
    ModelAvailability,
    PredictionModelMetadata,
)
from app.domain.enums import ModelType


class MonteCarloSimulation(PredictionModel):
    """Monte Carlo simulation-based prediction model.
    
    Generates match predictions by running thousands of simulated matches
    using Poisson distributions for goal scoring.
    
    Algorithm:
    1. Get expected goals (lambdas) from base model or features
    2. Run n_simulations independent match simulations
    3. For each simulation:
       - Draw home_goals ~ Poisson(lambda_home)
       - Draw away_goals ~ Poisson(lambda_away)
       - Record scoreline
    4. Derive probabilities from simulation frequencies
    
    Markets derived:
    - 1X2 (home/draw/away)
    - Correct score (top 25 scorelines)
    - Over/Under (0.5, 1.5, 2.5, 3.5)
    - BTTS (both teams to score yes/no)
    - Team totals (home/away over 0.5, 1.5, 2.5)
    """
    
    MODEL_ID = "monte_carlo_v1"
    MODEL_VERSION = "1.0.0"
    
    def __init__(
        self,
        base_model: Optional[PredictionModel] = None,
        n_simulations: int = 10000,
        seed: Optional[int] = None,
        top_scorelines: int = 25
    ):
        """Initialize Monte Carlo simulation model.
        
        Args:
            base_model: Optional base model to get lambdas from
                       If None, uses lambdas from features directly
            n_simulations: Number of simulations to run (default: 10000)
            seed: Random seed for reproducibility (None = non-deterministic)
            top_scorelines: Number of top scorelines to include (default: 25)
        """
        self.base_model = base_model
        self.n_simulations = n_simulations
        self.seed = seed
        self.top_scorelines = top_scorelines
    
    def predict(
        self,
        features: Dict[str, Optional[float]],
        match_context: Optional[Dict[str, Any]] = None
    ) -> ModelPrediction | ModelAvailability:
        """Generate Monte Carlo simulation-based prediction.
        
        Args:
            features: Feature dictionary
            match_context: Additional context
        
        Returns:
            ModelPrediction with simulation-derived probabilities or ModelAvailability
        """
        # Get lambdas from base model or features
        if self.base_model is not None:
            # Check base model requirements first
            base_met, base_missing = self.base_model.check_requirements(features)
            if not base_met:
                return ModelAvailability(
                    model_id=self.MODEL_ID,
                    available=False,
                    reason=f"base_model_unavailable: insufficient_data",
                    missing_features=base_missing
                )
            base_prediction = self.base_model.predict(features, match_context)
            
            if isinstance(base_prediction, ModelAvailability):
                return ModelAvailability(
                    model_id=self.MODEL_ID,
                    available=False,
                    reason=f"base_model_unavailable: {base_prediction.reason}",
                    missing_features=base_prediction.missing_features
                )
            
            lambda_home = base_prediction.home_score_mean
            lambda_away = base_prediction.away_score_mean
            base_model_id = base_prediction.model_id
        else:
            # Use lambdas directly from features
            lambda_home = features.get("home_expected_goals")
            lambda_away = features.get("away_expected_goals")
            
            if lambda_home is None or lambda_away is None:
                return ModelAvailability(
                    model_id=self.MODEL_ID,
                    available=False,
                    reason="expected_goals_unavailable",
                    missing_features=["home_expected_goals", "away_expected_goals"]
                )
            
            base_model_id = "features"
        
        # Run simulation
        simulation_results = self._run_simulation(lambda_home, lambda_away)
        
        # Calculate probabilities from simulation results
        scoreline_counts = simulation_results["scoreline_counts"]
        total_sims = self.n_simulations
        
        # Score distribution (top N scorelines)
        scoreline_probs = {
            scoreline: count / total_sims
            for scoreline, count in scoreline_counts.items()
        }
        
        # Sort by probability and take top N
        top_scorelines = dict(
            sorted(scoreline_probs.items(), key=lambda x: x[1], reverse=True)[:self.top_scorelines]
        )
        
        # 1X2 probabilities
        home_wins = simulation_results["home_wins"]
        draws = simulation_results["draws"]
        away_wins = simulation_results["away_wins"]
        
        home_win_prob = home_wins / total_sims
        draw_prob = draws / total_sims
        away_win_prob = away_wins / total_sims
        
        # Over/Under probabilities
        over_under = {
            line: simulation_results["over_under"][line] / total_sims
            for line in [0.5, 1.5, 2.5, 3.5]
        }
        
        # BTTS probabilities
        btts_yes = simulation_results["btts_yes"] / total_sims
        btts_no = simulation_results["btts_no"] / total_sims
        
        # Team totals
        home_totals = {
            line: simulation_results["home_totals"][line] / total_sims
            for line in [0.5, 1.5, 2.5]
        }
        away_totals = {
            line: simulation_results["away_totals"][line] / total_sims
            for line in [0.5, 1.5, 2.5]
        }
        
        # Calculate confidence based on simulation convergence
        confidence = self._calculate_confidence(simulation_results, total_sims)
        
        # Data quality from number of simulations
        data_quality = min(1.0, total_sims / 10000.0)
        
        return ModelPrediction(
            model_id=self.MODEL_ID,
            home_score_mean=lambda_home,
            away_score_mean=lambda_away,
            score_distribution=top_scorelines,
            home_win_prob=home_win_prob,
            draw_prob=draw_prob,
            away_win_prob=away_win_prob,
            confidence_score=confidence,
            data_quality_score=data_quality,
            metadata={
                "base_model_id": base_model_id,
                "n_simulations": self.n_simulations,
                "seed": self.seed,
                "lambda_home": lambda_home,
                "lambda_away": lambda_away,
                "over_under": over_under,
                "btts_yes": btts_yes,
                "btts_no": btts_no,
                "home_team_totals": home_totals,
                "away_team_totals": away_totals,
                "scorelines_captured": len(top_scorelines),
                "unique_scorelines_simulated": len(scoreline_counts)
            }
        )
    
    def _run_simulation(
        self,
        lambda_home: float,
        lambda_away: float
    ) -> Dict[str, Any]:
        """Run Monte Carlo simulation.
        
        Args:
            lambda_home: Expected home goals
            lambda_away: Expected away goals
        
        Returns:
            Dict with simulation results
        """
        # Use local RNG instance for reproducibility without global state pollution
        if self.seed is not None:
            rng = random.Random(self.seed)
        else:
            rng = random.Random()
        
        # Initialize counters
        scoreline_counts: Dict[Tuple[int, int], int] = {}
        home_wins = 0
        draws = 0
        away_wins = 0
        
        # Over/Under counters
        over_under = {0.5: 0, 1.5: 0, 2.5: 0, 3.5: 0}
        
        # BTTS counters
        btts_yes = 0
        btts_no = 0
        
        # Team totals counters
        home_totals = {0.5: 0, 1.5: 0, 2.5: 0}
        away_totals = {0.5: 0, 1.5: 0, 2.5: 0}
        
        # Run simulations
        for _ in range(self.n_simulations):
            # Draw goals from Poisson distributions
            home_goals = self._poisson_sample(lambda_home, rng)
            away_goals = self._poisson_sample(lambda_away, rng)
            
            # Record scoreline
            scoreline = (home_goals, away_goals)
            scoreline_counts[scoreline] = scoreline_counts.get(scoreline, 0) + 1
            
            # 1X2
            if home_goals > away_goals:
                home_wins += 1
            elif home_goals == away_goals:
                draws += 1
            else:
                away_wins += 1
            
            # Over/Under
            total_goals = home_goals + away_goals
            for line in over_under.keys():
                if total_goals > line:
                    over_under[line] += 1
            
            # BTTS
            if home_goals > 0 and away_goals > 0:
                btts_yes += 1
            else:
                btts_no += 1
            
            # Team totals
            for line in home_totals.keys():
                if home_goals > line:
                    home_totals[line] += 1
            for line in away_totals.keys():
                if away_goals > line:
                    away_totals[line] += 1
        
        return {
            "scoreline_counts": scoreline_counts,
            "home_wins": home_wins,
            "draws": draws,
            "away_wins": away_wins,
            "over_under": over_under,
            "btts_yes": btts_yes,
            "btts_no": btts_no,
            "home_totals": home_totals,
            "away_totals": away_totals
        }
    
    def _poisson_sample(self, lam: float, rng: random.Random) -> int:
        """Sample from Poisson distribution using local RNG.
        
        Uses Knuth's algorithm for Poisson sampling.
        
        Args:
            lam: Lambda parameter (expected value)
            rng: Random number generator instance
        
        Returns:
            Sampled integer value
        """
        import math
        
        if lam <= 0:
            return 0
        
        # For large lambda, use normal approximation
        if lam > 30:
            # Normal approximation: N(lambda, lambda)
            value = rng.gauss(lam, math.sqrt(lam))
            return max(0, int(round(value)))
        
        # Knuth's algorithm for smaller lambda
        L = math.exp(-lam)
        k = 0
        p = 1.0
        
        while p > L:
            k += 1
            p *= rng.random()
        
        return k - 1
    
    def _calculate_confidence(
        self,
        simulation_results: Dict[str, Any],
        total_sims: int
    ) -> float:
        """Calculate confidence based on simulation convergence.
        
        Higher confidence when:
        - More simulations run
        - Clear outcome (not close to 33/33/33)
        - Stable distribution
        
        Args:
            simulation_results: Simulation results
            total_sims: Total simulations run
        
        Returns:
            Confidence score in [0, 1]
        """
        # Base confidence from number of simulations
        sim_confidence = min(1.0, total_sims / 10000.0)
        
        # Outcome clarity (how different from uniform distribution)
        home_prob = simulation_results["home_wins"] / total_sims
        draw_prob = simulation_results["draws"] / total_sims
        away_prob = simulation_results["away_wins"] / total_sims
        
        # Distance from uniform (0.333, 0.333, 0.333)
        uniform_distance = (
            abs(home_prob - 0.333) +
            abs(draw_prob - 0.333) +
            abs(away_prob - 0.333)
        ) / 2.0  # Normalize to [0, 1]
        
        outcome_confidence = 0.7 + (uniform_distance * 0.3)
        
        # Combined confidence
        confidence = sim_confidence * outcome_confidence
        
        return max(0.0, min(1.0, confidence))
    
    def get_metadata(self) -> PredictionModelMetadata:
        """Return model metadata.
        
        Returns:
            PredictionModelMetadata
        """
        if self.base_model is not None:
            base_metadata = self.base_model.get_metadata()
            required_features = base_metadata.required_features
            min_samples = base_metadata.min_samples_required
        else:
            required_features = ["home_expected_goals", "away_expected_goals"]
            min_samples = 5
        
        return PredictionModelMetadata(
            model_id=self.MODEL_ID,
            model_type=ModelType.MONTE_CARLO,
            version=self.MODEL_VERSION,
            description=f"Monte Carlo simulation with {self.n_simulations} iterations",
            required_features=required_features,
            optional_features=["seed"],
            min_samples_required=min_samples
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
        missing = []
        
        if self.base_model is not None:
            # Check base model requirements
            base_met, base_missing = self.base_model.check_requirements(features)
            if not base_met:
                missing.extend(base_missing)
        else:
            # Check for expected goals in features
            if features.get("home_expected_goals") is None:
                missing.append("home_expected_goals")
            if features.get("away_expected_goals") is None:
                missing.append("away_expected_goals")
        
        return len(missing) == 0, missing
