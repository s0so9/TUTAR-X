"""Model orchestration layer for running multiple prediction models.

This module coordinates execution of all available prediction models from a
MatchFeatureSnapshot, handles partial failures gracefully, and aggregates results.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
import logging

from app.prediction.interfaces import (
    PredictionModel,
    ModelPrediction,
    ModelAvailability,
)
from app.prediction.feature_snapshot import MatchFeatureSnapshot
from app.prediction.poisson import PoissonModel
from app.prediction.dixon_coles import DixonColesModel
from app.prediction.elo import EloModel
from app.prediction.monte_carlo import MonteCarloSimulation
from app.prediction.negative_binomial import NegativeBinomialModel
from app.prediction.form_adjusted import FormAdjustedModel
from app.prediction.logistic_regression import LogisticRegressionModel
from app.prediction.ensemble_engine import EnsembleEngine, ReliabilityWeights
from app.prediction.calibration_engine import IsotonicCalibration
from app.prediction.confidence_engine import ConfidenceEngine, ConfidenceComponents, ConfidenceAssessment
from app.prediction.feature_snapshot import MatchFeatureSnapshot, LineupStatus


logger = logging.getLogger(__name__)


class ModelStatus(str, Enum):
    """Status of model execution."""
    SUPPORTED_RUN = "supported_run"  # Model ran successfully
    UNAVAILABLE_MISSING_INPUTS = "unavailable_missing_inputs"  # Required data missing
    FAILED = "failed"  # Model execution failed with error


@dataclass
class ModelOutput:
    """Output from a single model execution.
    
    Wraps either successful prediction or failure/unavailability information.
    """
    
    # Model identification
    model_id: str
    model_version: str
    
    # Execution status
    status: ModelStatus
    
    # Prediction result (only if status == SUPPORTED_RUN)
    prediction: Optional[ModelPrediction] = None
    
    # Availability info (only if status == UNAVAILABLE_MISSING_INPUTS)
    availability: Optional[ModelAvailability] = None
    
    # Error info (only if status == FAILED)
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None
    
    # Execution metadata
    execution_time_ms: Optional[float] = None
    warnings: List[str] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_successful(self) -> bool:
        """Check if model ran successfully."""
        return self.status == ModelStatus.SUPPORTED_RUN
    
    @property
    def is_unavailable(self) -> bool:
        """Check if model was unavailable due to missing inputs."""
        return self.status == ModelStatus.UNAVAILABLE_MISSING_INPUTS
    
    @property
    def is_failed(self) -> bool:
        """Check if model execution failed."""
        return self.status == ModelStatus.FAILED


@dataclass
class ModelOrchestrationResult:
    """Result of orchestrating multiple models."""
    
    # Model outputs
    successful_predictions: List[ModelOutput] = field(default_factory=list)
    unavailable_models: List[ModelOutput] = field(default_factory=list)
    failed_models: List[ModelOutput] = field(default_factory=list)
    
    # Metadata
    total_models: int = 0
    participating_model_ids: List[str] = field(default_factory=list)
    execution_metadata: Dict[str, Any] = field(default_factory=dict)
    orchestration_timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # NEW: Group 5 fields (Optional for backward compatibility)
    model_disagreement: Optional[Any] = None  # ModelDisagreementResult
    uncertainty_assessment: Optional[Any] = None  # UncertaintyAssessment
    shot_market_predictions: Optional[Dict[Any, List[Any]]] = None  # Dict[ShotMarketType, List[ShotMarketPrediction]]
    
    @property
    def has_predictions(self) -> bool:
        """Check if at least one model produced a prediction."""
        return len(self.successful_predictions) > 0
    
    @property
    def success_rate(self) -> float:
        """Calculate proportion of successful models."""
        if self.total_models == 0:
            return 0.0
        return len(self.successful_predictions) / self.total_models
    
    def get_all_outputs(self) -> List[ModelOutput]:
        """Get all model outputs regardless of status."""
        return (
            self.successful_predictions +
            self.unavailable_models +
            self.failed_models
        )


class ModelOrchestrator:
    """Orchestrates execution of multiple prediction models.
    
    Responsibilities:
    1. Register and manage prediction models
    2. Execute all compatible models from a MatchFeatureSnapshot
    3. Handle partial failures gracefully (one model failure doesn't kill pipeline)
    4. Distinguish between unavailable inputs vs execution failures
    5. Collect diagnostics and warnings
    """
    
    def __init__(self):
        """Initialize model orchestrator."""
        self._models: Dict[str, PredictionModel] = {}
    
    def register_model(self, model: PredictionModel) -> None:
        """Register a prediction model.
        
        Args:
            model: PredictionModel instance to register
        """
        metadata = model.get_metadata()
        model_id = metadata.model_id
        
        if model_id in self._models:
            logger.warning(f"Overwriting existing model: {model_id}")
        
        self._models[model_id] = model
        logger.info(f"Registered model: {model_id} (version {metadata.version})")
    
    def run_all(
        self,
        snapshot: MatchFeatureSnapshot,
        match_context: Optional[Dict[str, Any]] = None,
    ) -> ModelOrchestrationResult:
        """Run all registered models on the feature snapshot.
        
        Models are executed independently. A failure in one model does not
        prevent execution of other models.
        
        Args:
            snapshot: MatchFeatureSnapshot with match features
            match_context: Additional context (lineups, injuries, etc.)
        
        Returns:
            ModelOrchestrationResult with all model outputs
        """
        result = ModelOrchestrationResult(
            total_models=len(self._models),
            execution_metadata={
                "snapshot_version": snapshot.snapshot_version,
                "match_id": snapshot.match_id,
            }
        )
        
        # Convert snapshot to feature dict for models
        features = snapshot.get_feature_dict()
        
        # DEBUG: Log critical aliases
        
        # Execute each model
        for model_id, model in self._models.items():
            output = self._run_single_model(
                model=model,
                features=features,
                match_context=match_context,
            )
            
            # Categorize output by status
            if output.is_successful:
                result.successful_predictions.append(output)
                result.participating_model_ids.append(model_id)
            elif output.is_unavailable:
                result.unavailable_models.append(output)
            elif output.is_failed:
                result.failed_models.append(output)
        
        logger.info(
            f"Orchestration complete: {len(result.successful_predictions)} successful, "
            f"{len(result.unavailable_models)} unavailable, "
            f"{len(result.failed_models)} failed"
        )
        
        # DEBUG: Print detailed model execution status
        print(f"[DEBUG] SUCCESSFUL MODELS: {[o.model_id for o in result.successful_predictions]}")
        print(f"[DEBUG] UNAVAILABLE MODELS: {[(o.model_id, o.availability.reason if o.availability else 'unknown') for o in result.unavailable_models]}")
        if result.failed_models:
            print(f"[DEBUG] FAILED MODELS: {[(o.model_id, o.error_message) for o in result.failed_models]}")
        
        return result
    
    def _run_single_model(
        self,
        model: PredictionModel,
        features: Dict[str, Optional[float]],
        match_context: Optional[Dict[str, Any]],
    ) -> ModelOutput:
        """Run a single model and wrap the result.
        
        Args:
            model: PredictionModel to execute
            features: Feature dictionary
            match_context: Additional context
        
        Returns:
            ModelOutput with execution result
        """
        metadata = model.get_metadata()
        start_time = datetime.now()
        
        try:
            # Check if model can run with available features
            requirements_met, missing = model.check_requirements(features)
            
            if not requirements_met:
                # Model cannot run due to missing inputs
                return ModelOutput(
                    model_id=metadata.model_id,
                    model_version=metadata.version,
                    status=ModelStatus.UNAVAILABLE_MISSING_INPUTS,
                    availability=ModelAvailability(
                        model_id=metadata.model_id,
                        available=False,
                        reason=f"Missing required features: {', '.join(missing)}",
                        missing_features=missing,
                    ),
                    diagnostics={
                        "required_features": metadata.required_features,
                        "missing_features": missing,
                    }
                )
            
            # Run model prediction
            result = model.predict(features=features, match_context=match_context)
            
            # Check result type
            if isinstance(result, ModelPrediction):
                # Successful prediction
                execution_time = (datetime.now() - start_time).total_seconds() * 1000
                
                return ModelOutput(
                    model_id=metadata.model_id,
                    model_version=metadata.version,
                    status=ModelStatus.SUPPORTED_RUN,
                    prediction=result,
                    execution_time_ms=execution_time,
                    diagnostics={
                        "confidence_score": result.confidence_score,
                        "data_quality_score": result.data_quality_score,
                    }
                )
            
            elif isinstance(result, ModelAvailability):
                # Model returned unavailability
                return ModelOutput(
                    model_id=metadata.model_id,
                    model_version=metadata.version,
                    status=ModelStatus.UNAVAILABLE_MISSING_INPUTS,
                    availability=result,
                    diagnostics={"reason": result.reason}
                )
            
            else:
                # Unexpected return type
                return ModelOutput(
                    model_id=metadata.model_id,
                    model_version=metadata.version,
                    status=ModelStatus.FAILED,
                    error_message=f"Unexpected return type: {type(result)}",
                )
        
        except Exception as e:
            # Model execution failed
            import traceback
            logger.error(f"Model {metadata.model_id} failed: {e}", exc_info=True)
            
            return ModelOutput(
                model_id=metadata.model_id,
                model_version=metadata.version,
                status=ModelStatus.FAILED,
                error_message=str(e),
                error_traceback=traceback.format_exc(),
            )
    
    def get_registered_models(self) -> List[str]:
        """Get list of registered model IDs.
        
        Returns:
            List of model IDs
        """
        return list(self._models.keys())
    
    @staticmethod
    def create_default_registry() -> "ModelOrchestrator":
        """Create orchestrator with all standard models registered.
        
        Returns:
            ModelOrchestrator with 7 models registered:
            - Poisson
            - Dixon-Coles
            - Elo
            - Monte Carlo
            - Negative Binomial
            - Form-Adjusted Poisson
            - Logistic Regression
        """
        orchestrator = ModelOrchestrator()
        
        # Register core statistical models
        poisson_model = PoissonModel()
        orchestrator.register_model(poisson_model)
        
        # Fitted goal layer parameters (config/goal_model.json); the models'
        # own defaults apply when no trained layer is available.
        from app.prediction.goal_model import get_goal_layer
        goal_layer = get_goal_layer()
        if goal_layer.rho is not None:
            orchestrator.register_model(DixonColesModel(poisson_model=poisson_model, rho=goal_layer.rho))
        else:
            orchestrator.register_model(DixonColesModel(poisson_model=poisson_model))
        orchestrator.register_model(EloModel())
        orchestrator.register_model(MonteCarloSimulation())
        if goal_layer.nb_dispersion is not None:
            orchestrator.register_model(NegativeBinomialModel(dispersion=goal_layer.nb_dispersion))
        else:
            orchestrator.register_model(NegativeBinomialModel())
        
        # Register adjusted models
        orchestrator.register_model(FormAdjustedModel(base_model=poisson_model))
        
        # Register ML models - Load pre-trained logistic regression if available
        try:
            # Try to load cached trained model
            import pickle
            from app.prediction.model_paths import get_trained_logistic_model_path
            
            model_cache_path = get_trained_logistic_model_path()
            if model_cache_path:
                logger.info(f"Loading cached logistic regression model from {model_cache_path}")
                try:
                    with open(model_cache_path, 'rb') as f:
                        model_data = pickle.load(f)
                    
                    logistic_model = LogisticRegressionModel()
                    logistic_model._weights = model_data['weights']
                    logistic_model._training_stats = model_data.get('training_stats')
                    logistic_model._is_fitted = model_data.get('is_fitted', True)
                    
                    orchestrator.register_model(logistic_model)
                    logger.info("Registered trained LogisticRegressionModel from cache")
                except ImportError as e:
                    logger.warning(f"Failed to load logistic model: missing dependency {e}")
                    logger.warning("Model requires scikit-learn or other dependencies")
                    orchestrator.register_model(LogisticRegressionModel())
                except Exception as e:
                    logger.warning(f"Failed to load logistic model: {e}")
                    orchestrator.register_model(LogisticRegressionModel())
            else:
                # Register unfitted model - will be unavailable
                orchestrator.register_model(LogisticRegressionModel())
                logger.info("No trained logistic model found - registered unfitted model (unavailable)")
                
        except Exception as e:
            logger.warning(f"Failed to load logistic regression model: {e}")
            orchestrator.register_model(LogisticRegressionModel())
        
        logger.info(f"Created default orchestrator with {len(orchestrator._models)} models")
        
        return orchestrator


class EnsembleIntegration:
    """Integration layer for ensemble prediction.
    
    Wires the canonical ensemble_engine.py into the model orchestration pipeline.
    """
    
    def __init__(self, engine: Optional[EnsembleEngine] = None):
        """Initialize ensemble integration.
        
        Args:
            engine: EnsembleEngine instance (defaults to ReliabilityWeights)
        """
        if engine is None:
            # Default to reliability-based weighting
            engine = EnsembleEngine(strategy=ReliabilityWeights())
        self.engine = engine
    
    def combine_predictions(
        self,
        orchestration_result: ModelOrchestrationResult,
        context: Optional[Dict[str, Any]] = None
    ) -> ModelPrediction | ModelAvailability:
        """Combine predictions from orchestration result.
        
        Args:
            orchestration_result: Result from ModelOrchestrator.run_all()
            context: Optional context (league_id, etc.)
            
        Returns:
            Combined ensemble prediction or ModelAvailability
        """
        # Extract successful predictions
        predictions = [
            output.prediction
            for output in orchestration_result.successful_predictions
            if output.prediction is not None
        ]
        
        if len(predictions) == 0:
            return ModelAvailability(
                model_id="ensemble_v1",
                available=False,
                reason="No successful model predictions available",
                missing_features=[]
            )
        
        # Use ensemble engine to combine
        result = self.engine.combine(predictions, context)
        
        # Log ensemble result
        if isinstance(result, ModelPrediction):
            agreement = result.metadata.get("model_agreement", 0.0)
            n_models = result.metadata.get("n_models", 0)
            logger.info(
                f"Ensemble combined {n_models} models with agreement={agreement:.3f}"
            )
        
        return result
    
    @staticmethod
    def create_default() -> "EnsembleIntegration":
        """Create ensemble integration with default reliability-based weighting.
        
        Returns:
            EnsembleIntegration with ReliabilityWeights strategy
        """
        return EnsembleIntegration()


class Calibrator1X2:
    """Calibrator for 1X2 probabilities (home/draw/away).
    
    Wraps three IsotonicCalibration instances - one for each outcome.
    Renormalizes after calibration to ensure probabilities sum to 1.0.
    """
    
    def __init__(self):
        """Initialize three calibrators."""
        self.home_calibrator = IsotonicCalibration()
        self.draw_calibrator = IsotonicCalibration()
        self.away_calibrator = IsotonicCalibration()
    
    @property
    def is_fitted(self) -> bool:
        """Check if all three calibrators are fitted."""
        return (
            self.home_calibrator.is_fitted and
            self.draw_calibrator.is_fitted and
            self.away_calibrator.is_fitted
        )
    
    def calibrate_1x2(
        self,
        home_prob: float,
        draw_prob: float,
        away_prob: float
    ) -> Tuple[float, float, float]:
        """Calibrate 1X2 probabilities and renormalize.
        
        Args:
            home_prob: Raw home win probability
            draw_prob: Raw draw probability
            away_prob: Raw away win probability
            
        Returns:
            Tuple of (calibrated_home, calibrated_draw, calibrated_away)
        """
        if not self.is_fitted:
            # Return uncalibrated if not fitted
            return (home_prob, draw_prob, away_prob)
        
        # Calibrate each outcome
        cal_home = self.home_calibrator.calibrate(home_prob)
        cal_draw = self.draw_calibrator.calibrate(draw_prob)
        cal_away = self.away_calibrator.calibrate(away_prob)
        
        # Renormalize to sum to 1.0
        total = cal_home + cal_draw + cal_away
        if total > 0:
            cal_home /= total
            cal_draw /= total
            cal_away /= total
        else:
            # Fallback to original if calibration fails
            return (home_prob, draw_prob, away_prob)
        
        return (cal_home, cal_draw, cal_away)


class CalibrationIntegration:
    """Integration layer for probability calibration.
    
    Wires the canonical calibration_engine.py into the prediction pipeline.
    """
    
    def __init__(self, calibrator: Optional[Calibrator1X2] = None):
        """Initialize calibration integration.
        
        Args:
            calibrator: Calibrator1X2 instance (creates new if None)
        """
        if calibrator is None:
            calibrator = Calibrator1X2()
        self.calibrator = calibrator
    
    def calibrate_prediction(
        self,
        prediction: ModelPrediction
    ) -> ModelPrediction:
        """Calibrate a prediction's 1X2 probabilities.
        
        Args:
            prediction: Raw model prediction
            
        Returns:
            New ModelPrediction with calibrated probabilities
        
        BUGFIX: score_distribution is now rescaled proportionally after 1X2 calibration
        to maintain consistency between marginal probabilities and score distribution.
        """
        # Calibrate probabilities
        cal_home, cal_draw, cal_away = self.calibrator.calibrate_1x2(
            prediction.home_win_prob,
            prediction.draw_prob,
            prediction.away_win_prob
        )
        
        # Determine calibration status
        is_calibrated = self.calibrator.is_fitted
        calibration_status = (
            "calibrated" if is_calibrated
            else "uncalibrated_fallback"
        )
        
        # BUGFIX: Rescale score_distribution to match calibrated 1X2 probabilities
        rescaled_distribution = self._rescale_score_distribution(
            score_distribution=prediction.score_distribution,
            original_home_prob=prediction.home_win_prob,
            original_draw_prob=prediction.draw_prob,
            original_away_prob=prediction.away_win_prob,
            calibrated_home_prob=cal_home,
            calibrated_draw_prob=cal_draw,
            calibrated_away_prob=cal_away
        )
        
        # Create new prediction with calibrated probabilities
        calibrated_metadata = {
            **prediction.metadata,
            "calibration_status": calibration_status,
            "is_calibrated": is_calibrated,
            "original_home_prob": prediction.home_win_prob,
            "original_draw_prob": prediction.draw_prob,
            "original_away_prob": prediction.away_win_prob,
        }
        
        return ModelPrediction(
            model_id=prediction.model_id,
            home_score_mean=prediction.home_score_mean,
            away_score_mean=prediction.away_score_mean,
            home_win_prob=cal_home,
            draw_prob=cal_draw,
            away_win_prob=cal_away,
            confidence_score=prediction.confidence_score,
            data_quality_score=prediction.data_quality_score,
            score_distribution=rescaled_distribution,
            metadata=calibrated_metadata
        )
    
    def _rescale_score_distribution(
        self,
        score_distribution: Dict[Tuple[int, int], float],
        original_home_prob: float,
        original_draw_prob: float,
        original_away_prob: float,
        calibrated_home_prob: float,
        calibrated_draw_prob: float,
        calibrated_away_prob: float
    ) -> Dict[Tuple[int, int], float]:
        """Rescale score distribution to match calibrated 1X2 probabilities.
        
        FIXED Strategy:
        1. Classify each scoreline as Home/Draw/Away
        2. Calculate category sums from the distribution
        3. For each category with non-zero sum, scale proportionally to reach calibrated target
        4. For categories with zero sum, distribute calibrated prob equally among most likely scorelines
        5. Normalize final distribution to sum to 1.0
        
        This ensures:
        - Category sums match calibrated probabilities (invariant)
        - Total distribution sums to 1.0
        - No silent fallback to 1.0 scale factors
        
        Args:
            score_distribution: Original score distribution
            original_*_prob: Original 1X2 probabilities before calibration (for reference)
            calibrated_*_prob: Calibrated 1X2 probabilities (target category sums)
            
        Returns:
            Rescaled score distribution consistent with calibrated 1X2 probs
        """
        if not score_distribution:
            return {}
        
        # Categorize scorelines by outcome
        home_scorelines: Dict[Tuple[int, int], float] = {}
        draw_scorelines: Dict[Tuple[int, int], float] = {}
        away_scorelines: Dict[Tuple[int, int], float] = {}
        
        for (home_goals, away_goals), prob in score_distribution.items():
            if home_goals > away_goals:
                home_scorelines[(home_goals, away_goals)] = prob
            elif home_goals == away_goals:
                draw_scorelines[(home_goals, away_goals)] = prob
            else:
                away_scorelines[(home_goals, away_goals)] = prob
        
        # Calculate current category sums
        home_sum = sum(home_scorelines.values())
        draw_sum = sum(draw_scorelines.values())
        away_sum = sum(away_scorelines.values())
        
        rescaled = {}
        
        # Rescale Home category
        if home_sum > 1e-9:  # Non-zero category sum
            scale = calibrated_home_prob / home_sum
            for scoreline, prob in home_scorelines.items():
                rescaled[scoreline] = prob * scale
        elif calibrated_home_prob > 1e-9:  # Zero sum but non-zero target
            # Distribute target prob equally among plausible home scorelines
            # Use scorelines with home_goals in [1, 2, 3] and away_goals in [0, 1]
            fallback_scorelines = [(1, 0), (2, 0), (2, 1), (3, 0), (3, 1)]
            n_fallback = len(fallback_scorelines)
            for scoreline in fallback_scorelines:
                rescaled[scoreline] = calibrated_home_prob / n_fallback
        
        # Rescale Draw category
        if draw_sum > 1e-9:
            scale = calibrated_draw_prob / draw_sum
            for scoreline, prob in draw_scorelines.items():
                rescaled[scoreline] = prob * scale
        elif calibrated_draw_prob > 1e-9:
            # Distribute equally among plausible draws
            fallback_scorelines = [(0, 0), (1, 1), (2, 2)]
            n_fallback = len(fallback_scorelines)
            for scoreline in fallback_scorelines:
                rescaled[scoreline] = calibrated_draw_prob / n_fallback
        
        # Rescale Away category
        if away_sum > 1e-9:
            scale = calibrated_away_prob / away_sum
            for scoreline, prob in away_scorelines.items():
                rescaled[scoreline] = prob * scale
        elif calibrated_away_prob > 1e-9:
            # Distribute equally among plausible away wins
            fallback_scorelines = [(0, 1), (0, 2), (1, 2), (0, 3), (1, 3)]
            n_fallback = len(fallback_scorelines)
            for scoreline in fallback_scorelines:
                rescaled[scoreline] = calibrated_away_prob / n_fallback
        
        # Normalize to ensure total = 1.0
        total = sum(rescaled.values())
        if total > 1e-9:
            rescaled = {k: v / total for k, v in rescaled.items()}
        
        return rescaled
    
    @staticmethod
    def create_default() -> "CalibrationIntegration":
        """Create calibration integration with unfitted calibrator.
        
        Returns:
            CalibrationIntegration with new unfitted Calibrator1X2
        """
        return CalibrationIntegration()


class ConfidenceIntegration:
    """Integration layer for confidence assessment.
    
    Extracts real values from pipeline components and feeds them to ConfidenceEngine.
    NO HARDCODED VALUES - all inputs derived from actual pipeline outputs.
    """
    
    def __init__(self, engine: Optional[ConfidenceEngine] = None):
        """Initialize confidence integration.
        
        Args:
            engine: ConfidenceEngine instance (creates default if None)
        """
        if engine is None:
            engine = ConfidenceEngine()
        self.engine = engine
    
    def assess_confidence(
        self,
        snapshot: MatchFeatureSnapshot,
        orchestration_result: ModelOrchestrationResult,
        ensemble_prediction: ModelPrediction,
        calibration_metadata: Optional[Dict[str, Any]] = None,
    ) -> ConfidenceAssessment:
        """Assess confidence from actual pipeline outputs.
        
        Args:
            snapshot: Feature snapshot with data quality
            orchestration_result: Model orchestration result
            ensemble_prediction: Ensemble prediction with model agreement
            calibration_metadata: Calibration metadata (brier_score if available)
            
        Returns:
            ConfidenceAssessment with real values from pipeline
        """
        # Extract model agreement from ensemble metadata
        model_agreement = ensemble_prediction.metadata.get("model_agreement", 0.0)
        
        # Extract data quality from snapshot
        # FIXED: Report unknown/insufficient instead of defaulting to 0.5
        data_quality_score = None  # None = unknown/insufficient
        if snapshot.data_quality_report:
            data_quality_score = snapshot.data_quality_report.overall_score
        
        # Calculate n_matches from form data
        n_matches = self._extract_n_matches(snapshot)
        
        # Extract brier_score from calibration metadata
        brier_score = None
        if calibration_metadata:
            brier_score = calibration_metadata.get("brier_score")
        
        # Extract lineup status
        lineup_status = self._extract_lineup_status_string(snapshot)
        
        # Call ConfidenceEngine.assess with correct signature
        assessment = self.engine.assess(
            model_agreement=model_agreement,
            data_quality_score=data_quality_score,
            n_matches=n_matches,
            brier_score=brier_score,
            lineup_status=lineup_status,
            recent_predictions=None  # Not calculating stability yet
        )
        
        # Format data_quality_score null-safe
        dq_str = f"{data_quality_score:.3f}" if data_quality_score is not None else "None"
        logger.info(
            f"Confidence assessed: {assessment.overall_confidence:.3f} "
            f"(agreement={model_agreement:.3f}, data_quality={dq_str})"
        )
        
        return assessment
    
    def _extract_n_matches(
        self,
        snapshot: MatchFeatureSnapshot
    ) -> int:
        """Extract number of matches from snapshot form data.
        
        Args:
            snapshot: Feature snapshot
            
        Returns:
            Minimum of home/away matches analyzed
        """
        home_matches = 0
        away_matches = 0
        
        if snapshot.home_form and snapshot.home_form.matches_analyzed:
            home_matches = snapshot.home_form.matches_analyzed
        
        if snapshot.away_form and snapshot.away_form.matches_analyzed:
            away_matches = snapshot.away_form.matches_analyzed
        
        # Use minimum of the two teams
        return min(home_matches, away_matches) if (home_matches and away_matches) else max(home_matches, away_matches)
    
    def _extract_lineup_status_string(
        self,
        snapshot: MatchFeatureSnapshot
    ) -> str:
        """Extract lineup status as string for ConfidenceEngine.
        
        Args:
            snapshot: Feature snapshot
            
        Returns:
            "confirmed", "expected", or "unknown"
        """
        # Check both teams' lineup status and return the less certain one
        home_status = "expected"
        away_status = "expected"
        
        if snapshot.home_player_availability:
            status = snapshot.home_player_availability.lineup_status
            if status == LineupStatus.CONFIRMED:
                home_status = "confirmed"
            elif status == LineupStatus.UNAVAILABLE:
                home_status = "unknown"
        
        if snapshot.away_player_availability:
            status = snapshot.away_player_availability.lineup_status
            if status == LineupStatus.CONFIRMED:
                away_status = "confirmed"
            elif status == LineupStatus.UNAVAILABLE:
                away_status = "unknown"
        
        # Return the less certain status
        if "unknown" in [home_status, away_status]:
            return "unknown"
        elif "expected" in [home_status, away_status]:
            return "expected"
        else:
            return "confirmed"
    
    @staticmethod
    def create_default() -> "ConfidenceIntegration":
        """Create confidence integration with default engine.
        
        Returns:
            ConfidenceIntegration with default ConfidenceEngine
        """
        return ConfidenceIntegration()
