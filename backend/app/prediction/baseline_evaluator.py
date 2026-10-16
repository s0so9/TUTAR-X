"""Baseline production model evaluator for Phase 10.3.

This module evaluates the current 4-model production system without optimization:
- Poisson Model
- Dixon-Coles Model  
- Negative Binomial Model
- Form Adjusted Model

Uses the current production ensemble configuration (ReliabilityWeights).
Measures individual model performance and ensemble performance.

FEAT-001 requirement: Handle insufficient samples with explicit 
INSUFFICIENT_HISTORICAL_SAMPLE reporting.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

from app.database.models import Match
from app.domain.enums import MatchStatus, MatchOutcome
from app.prediction.interfaces import ModelPrediction, ModelAvailability
from app.prediction.model_orchestrator import ModelOrchestrator, ModelOutput
from app.prediction.ensemble_engine import EnsembleEngine, ReliabilityWeights
from app.prediction.feature_snapshot import MatchFeatureSnapshot
from app.prediction.dataset_validator import DatasetValidator, ValidationLevel
from app.prediction.calibration import brier_score, log_loss_multiclass, calibration_error


class ModelOperationalStatus(str, Enum):
    """Operational status of models in production."""
    OPERATIONAL = "operational"  # Model is active and producing predictions
    AWAITING_INTEGRATION = "awaiting_integration"  # Model exists but not activated
    AWAITING_DATA = "awaiting_data"  # Model awaits data population
    DISABLED = "disabled"  # Model temporarily disabled


@dataclass
class ModelMetrics:
    """Performance metrics for a single model."""
    
    model_id: str
    status: ModelOperationalStatus
    
    # Prediction counts
    predictions_attempted: int = 0
    predictions_successful: int = 0
    predictions_failed: int = 0
    
    # Performance metrics (None if insufficient data)
    accuracy: Optional[float] = None
    brier_score: Optional[float] = None
    log_loss: Optional[float] = None
    
    # Calibration metrics (if sample size supports)
    calibration_error: Optional[float] = None
    calibration_slope: Optional[float] = None
    
    # Sample information
    sample_size: int = 0
    is_sufficient_sample: bool = False
    
    # 1X2 accuracy breakdown
    home_win_accuracy: Optional[float] = None
    draw_accuracy: Optional[float] = None
    away_win_accuracy: Optional[float] = None
    
    # Probability distribution stats
    avg_confidence: Optional[float] = None
    avg_home_prob: Optional[float] = None
    avg_draw_prob: Optional[float] = None
    avg_away_prob: Optional[float] = None
    
    # Error information
    failure_reasons: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "model_id": self.model_id,
            "status": self.status.value,
            "predictions_attempted": self.predictions_attempted,
            "predictions_successful": self.predictions_successful,
            "predictions_failed": self.predictions_failed,
            "accuracy": self.accuracy,
            "brier_score": self.brier_score,
            "log_loss": self.log_loss,
            "calibration_error": self.calibration_error,
            "calibration_slope": self.calibration_slope,
            "sample_size": self.sample_size,
            "is_sufficient_sample": self.is_sufficient_sample,
            "home_win_accuracy": self.home_win_accuracy,
            "draw_accuracy": self.draw_accuracy,
            "away_win_accuracy": self.away_win_accuracy,
            "avg_confidence": self.avg_confidence,
            "avg_home_prob": self.avg_home_prob,
            "avg_draw_prob": self.avg_draw_prob,
            "avg_away_prob": self.avg_away_prob,
            "failure_reasons": self.failure_reasons
        }


@dataclass
class EnsembleMetrics:
    """Performance metrics for ensemble."""
    
    ensemble_id: str = "ensemble_v1"
    weighting_strategy: str = "ReliabilityWeights"
    
    # Prediction counts
    predictions_attempted: int = 0
    predictions_successful: int = 0
    
    # Performance metrics
    accuracy: Optional[float] = None
    brier_score: Optional[float] = None
    log_loss: Optional[float] = None
    calibration_error: Optional[float] = None
    
    # Model participation
    avg_models_participating: float = 0.0
    avg_model_agreement: float = 0.0
    
    # Sample information
    sample_size: int = 0
    is_sufficient_sample: bool = False
    
    # Ensemble-specific metrics
    avg_ensemble_confidence: Optional[float] = None
    model_weight_distribution: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "ensemble_id": self.ensemble_id,
            "weighting_strategy": self.weighting_strategy,
            "predictions_attempted": self.predictions_attempted,
            "predictions_successful": self.predictions_successful,
            "accuracy": self.accuracy,
            "brier_score": self.brier_score,
            "log_loss": self.log_loss,
            "calibration_error": self.calibration_error,
            "avg_models_participating": self.avg_models_participating,
            "avg_model_agreement": self.avg_model_agreement,
            "sample_size": self.sample_size,
            "is_sufficient_sample": self.is_sufficient_sample,
            "avg_ensemble_confidence": self.avg_ensemble_confidence,
            "model_weight_distribution": self.model_weight_distribution
        }


@dataclass
class BaselineEvaluationResult:
    """Complete baseline evaluation result."""
    
    # Evaluation metadata
    evaluation_timestamp: datetime = field(default_factory=datetime.utcnow)
    dataset_summary: Dict[str, Any] = field(default_factory=dict)
    
    # Individual model results
    model_metrics: Dict[str, ModelMetrics] = field(default_factory=dict)
    
    # Ensemble results
    ensemble_metrics: Optional[EnsembleMetrics] = None
    
    # Overall assessment
    is_production_ready: bool = False
    operational_models_count: int = 0
    total_models_count: int = 0
    
    # Issues and warnings
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "evaluation_timestamp": self.evaluation_timestamp.isoformat(),
            "dataset_summary": self.dataset_summary,
            "model_metrics": {
                model_id: metrics.to_dict() 
                for model_id, metrics in self.model_metrics.items()
            },
            "ensemble_metrics": self.ensemble_metrics.to_dict() if self.ensemble_metrics else None,
            "is_production_ready": self.is_production_ready,
            "operational_models_count": self.operational_models_count,
            "total_models_count": self.total_models_count,
            "issues": self.issues,
            "warnings": self.warnings
        }


class BaselineProductionEvaluator:
    """Evaluator for baseline production model system."""
    
    # Model status mapping based on Phase 10.2 completion
    EXPECTED_MODEL_STATUS = {
        "poisson_v1": ModelOperationalStatus.OPERATIONAL,
        "dixon_coles_v1": ModelOperationalStatus.OPERATIONAL,
        "negative_binomial_v1": ModelOperationalStatus.OPERATIONAL,
        "form_adjusted_v1": ModelOperationalStatus.OPERATIONAL,
        "monte_carlo_v1": ModelOperationalStatus.AWAITING_DATA,  # Awaiting xG population
        "elo_v1": ModelOperationalStatus.AWAITING_INTEGRATION,  # Awaiting EloRatingSystem  
        "logistic_regression_v1": ModelOperationalStatus.AWAITING_INTEGRATION  # Awaiting training infrastructure
    }
    
    MIN_RELIABLE_SAMPLES = 30
    
    def __init__(self, session):
        """Initialize baseline evaluator.
        
        Args:
            session: Database session
        """
        self.session = session
        self.orchestrator = ModelOrchestrator.create_default_registry()
        self.ensemble_engine = EnsembleEngine(strategy=ReliabilityWeights())
        self.validator = DatasetValidator(level=ValidationLevel.MINIMAL)
    
    def evaluate_baseline_system(self, matches: List[Match]) -> BaselineEvaluationResult:
        """Evaluate the baseline production system.
        
        Args:
            matches: Historical matches for evaluation
            
        Returns:
            BaselineEvaluationResult with all metrics
        """
        print("Starting baseline production system evaluation...")
        
        # Validate dataset
        validation_result = self.validator.validate_dataset(matches)
        print(f"Dataset validation result: valid={validation_result.is_valid}, sufficient={validation_result.is_sufficient}")
        if validation_result.issues:
            print(f"Validation issues: {[f'{issue.issue_type}: {issue.message}' for issue in validation_result.issues]}")
        
        if not validation_result.is_valid:
            return BaselineEvaluationResult(
                issues=[f"Dataset validation failed: {', '.join([issue.issue_type for issue in validation_result.issues])}"],
                dataset_summary={
                    "total_matches": validation_result.total_matches,
                    "eligible_matches": validation_result.eligible_matches,
                    "is_sufficient": validation_result.is_sufficient
                }
            )
        
        eligible_matches = self.validator.get_eligible_matches(matches)
        
        print(f"Evaluating {len(eligible_matches)} eligible matches...")
        
        # Initialize results
        result = BaselineEvaluationResult(
            dataset_summary={
                "total_matches": validation_result.total_matches,
                "eligible_matches": len(eligible_matches),
                "excluded_matches": validation_result.excluded_matches,
                "is_sufficient": validation_result.is_sufficient,
                "date_range": [
                    validation_result.date_range[0].isoformat() if validation_result.date_range[0] else None,
                    validation_result.date_range[1].isoformat() if validation_result.date_range[1] else None
                ]
            },
            total_models_count=len(self.EXPECTED_MODEL_STATUS)
        )
        
        # Check if we have sufficient data
        if len(eligible_matches) < self.MIN_RELIABLE_SAMPLES:
            result.issues.append(
                f"INSUFFICIENT_HISTORICAL_SAMPLE: {len(eligible_matches)} < {self.MIN_RELIABLE_SAMPLES}"
            )
            return result
        
        # Evaluate each expected model
        model_results = {}
        successful_models = []
        
        for model_id, expected_status in self.EXPECTED_MODEL_STATUS.items():
            print(f"Evaluating model: {model_id}")
            
            # First check if model is actually registered
            registered_models = self.orchestrator.get_registered_models()
            print(f"Registered models: {registered_models}")
            
            model_metrics = self._evaluate_single_model(
                model_id=model_id,
                expected_status=expected_status,
                matches=eligible_matches
            )
            
            model_results[model_id] = model_metrics
            
            if model_metrics.status == ModelOperationalStatus.OPERATIONAL:
                successful_models.append(model_id)
                if model_metrics.is_sufficient_sample:
                    result.operational_models_count += 1
        
        result.model_metrics = model_results
        
        # Evaluate ensemble if we have operational models
        if len(successful_models) >= 2:
            print("Evaluating ensemble...")
            ensemble_metrics = self._evaluate_ensemble(
                eligible_matches=eligible_matches,
                operational_model_ids=successful_models
            )
            result.ensemble_metrics = ensemble_metrics
        else:
            result.issues.append(
                f"Insufficient operational models for ensemble: {len(successful_models)} < 2"
            )
        
        # Determine production readiness
        result.is_production_ready = (
            result.operational_models_count >= 4 and
            result.ensemble_metrics is not None and
            result.ensemble_metrics.is_sufficient_sample
        )
        
        print(f"Baseline evaluation complete. Operational models: {result.operational_models_count}/{result.total_models_count}")
        
        return result
    
    def _evaluate_single_model(
        self,
        model_id: str,
        expected_status: ModelOperationalStatus,
        matches: List[Match]
    ) -> ModelMetrics:
        """Evaluate a single model's performance.
        
        Args:
            model_id: Model identifier
            expected_status: Expected operational status
            matches: Eligible matches for evaluation
            
        Returns:
            ModelMetrics with performance data
        """
        metrics = ModelMetrics(
            model_id=model_id,
            status=expected_status
        )
        
        # If model is not operational, return early
        if expected_status != ModelOperationalStatus.OPERATIONAL:
            return metrics
        
        # Try to get model predictions for each match
        predictions = []
        outcomes = []
        
        for match in matches:
            try:
                # Create minimal feature snapshot for this match
                snapshot = self._create_minimal_snapshot(match)
                
                # Run single model (this is simplified - in real implementation
                # would need proper feature extraction)
                orchestration_result = self.orchestrator.run_all(snapshot=snapshot)
                
                # Find this specific model's output
                model_output = None
                for output in orchestration_result.get_all_outputs():
                    if output.model_id == model_id:
                        model_output = output
                        break
                
                metrics.predictions_attempted += 1
                
                if model_output and model_output.is_successful:
                    prediction = model_output.prediction
                    outcome = self._get_match_outcome(match)
                    
                    if outcome is not None:
                        predictions.append(prediction)
                        outcomes.append(outcome)
                        metrics.predictions_successful += 1
                    else:
                        metrics.predictions_failed += 1
                        metrics.failure_reasons["invalid_outcome"] = metrics.failure_reasons.get("invalid_outcome", 0) + 1
                
                elif model_output and model_output.is_unavailable:
                    metrics.predictions_failed += 1
                    metrics.failure_reasons["unavailable"] = metrics.failure_reasons.get("unavailable", 0) + 1
                    
                elif model_output and model_output.is_failed:
                    metrics.predictions_failed += 1
                    metrics.failure_reasons["execution_error"] = metrics.failure_reasons.get("execution_error", 0) + 1
                    
                else:
                    metrics.predictions_failed += 1
                    metrics.failure_reasons["not_found"] = metrics.failure_reasons.get("not_found", 0) + 1
            
            except Exception as e:
                metrics.predictions_attempted += 1
                metrics.predictions_failed += 1
                metrics.failure_reasons["exception"] = metrics.failure_reasons.get("exception", 0) + 1
        
        # Calculate metrics if we have sufficient predictions
        metrics.sample_size = len(predictions)
        metrics.is_sufficient_sample = metrics.sample_size >= self.MIN_RELIABLE_SAMPLES
        
        if metrics.sample_size > 0:
            metrics = self._calculate_model_metrics(metrics, predictions, outcomes)
        
        return metrics
    
    def _evaluate_ensemble(
        self,
        eligible_matches: List[Match],
        operational_model_ids: List[str]
    ) -> EnsembleMetrics:
        """Evaluate ensemble performance.
        
        Args:
            eligible_matches: Matches for evaluation
            operational_model_ids: List of operational model IDs
            
        Returns:
            EnsembleMetrics with ensemble performance
        """
        ensemble_metrics = EnsembleMetrics()
        
        ensemble_predictions = []
        outcomes = []
        model_participation_counts = []
        model_agreements = []
        
        for match in eligible_matches:
            try:
                # Create minimal snapshot
                snapshot = self._create_minimal_snapshot(match)
                
                # Run orchestration
                orchestration_result = self.orchestrator.run_all(snapshot=snapshot)
                
                # Check if we have enough successful predictions for ensemble
                successful_predictions = [
                    output.prediction for output in orchestration_result.successful_predictions
                    if output.model_id in operational_model_ids and output.prediction is not None
                ]
                
                ensemble_metrics.predictions_attempted += 1
                
                if len(successful_predictions) >= 2:
                    # Run ensemble
                    ensemble_result = self.ensemble_engine.combine(successful_predictions)
                    
                    if isinstance(ensemble_result, ModelPrediction):
                        outcome = self._get_match_outcome(match)
                        
                        if outcome is not None:
                            ensemble_predictions.append(ensemble_result)
                            outcomes.append(outcome)
                            ensemble_metrics.predictions_successful += 1
                            
                            # Track participation and agreement
                            model_participation_counts.append(len(successful_predictions))
                            model_agreements.append(
                                ensemble_result.metadata.get("model_agreement", 0.0)
                            )
            
            except Exception as e:
                # Continue evaluation even if individual matches fail
                continue
        
        # Calculate ensemble metrics
        ensemble_metrics.sample_size = len(ensemble_predictions)
        ensemble_metrics.is_sufficient_sample = ensemble_metrics.sample_size >= self.MIN_RELIABLE_SAMPLES
        
        if ensemble_metrics.sample_size > 0:
            ensemble_metrics = self._calculate_ensemble_metrics(
                ensemble_metrics, ensemble_predictions, outcomes
            )
            
            # Calculate participation and agreement averages
            ensemble_metrics.avg_models_participating = (
                sum(model_participation_counts) / len(model_participation_counts)
                if model_participation_counts else 0.0
            )
            
            ensemble_metrics.avg_model_agreement = (
                sum(model_agreements) / len(model_agreements)
                if model_agreements else 0.0
            )
        
        return ensemble_metrics
    
    def _create_minimal_snapshot(self, match: Match) -> MatchFeatureSnapshot:
        """Create minimal feature snapshot for evaluation.
        
        This is a simplified implementation. Real feature extraction would
        require full database queries and feature engineering.
        
        Args:
            match: Match to create snapshot for
            
        Returns:
            MatchFeatureSnapshot (minimal)
        """
        return MatchFeatureSnapshot(
            match_id=match.id,
            home_team_id=match.home_team_id,
            away_team_id=match.away_team_id,
            scheduled_at=match.scheduled_at,
            data_quality_score=0.7,  # Simplified
            team_strength=None,
            form_metrics=None,
            player_availability=None,
            league_context=None,
            tactical_context=None,
            source_provenance=None,
            market_information=None,
            advanced_feature_set=None,
            extracted_at=datetime.utcnow()
        )
    
    def _get_match_outcome(self, match: Match) -> Optional[str]:
        """Get match outcome for evaluation.
        
        Args:
            match: Match to get outcome for
            
        Returns:
            Outcome string or None if invalid
        """
        if match.home_score is None or match.away_score is None:
            return None
        
        if match.home_score > match.away_score:
            return "home_win"
        elif match.home_score == match.away_score:
            return "draw"
        else:
            return "away_win"
    
    def _calculate_model_metrics(
        self,
        metrics: ModelMetrics,
        predictions: List[ModelPrediction],
        outcomes: List[str]
    ) -> ModelMetrics:
        """Calculate performance metrics for a model.
        
        Args:
            metrics: ModelMetrics object to update
            predictions: List of model predictions
            outcomes: List of actual outcomes
            
        Returns:
            Updated ModelMetrics
        """
        if not predictions or len(predictions) != len(outcomes):
            return metrics
        
        n = len(predictions)
        
        # Calculate accuracy
        correct_predictions = 0
        home_correct = draw_correct = away_correct = 0
        home_total = draw_total = away_total = 0
        
        # Extract probabilities and calculate metrics
        home_probs = []
        draw_probs = []
        away_probs = []
        
        brier_sum = 0.0
        log_loss_sum = 0.0
        
        for pred, outcome in zip(predictions, outcomes):
            home_probs.append(pred.home_win_prob)
            draw_probs.append(pred.draw_prob)
            away_probs.append(pred.away_win_prob)
            
            # Determine predicted outcome (highest probability)
            max_prob = max(pred.home_win_prob, pred.draw_prob, pred.away_win_prob)
            if pred.home_win_prob == max_prob:
                predicted_outcome = "home_win"
            elif pred.draw_prob == max_prob:
                predicted_outcome = "draw"
            else:
                predicted_outcome = "away_win"
            
            # Count accuracy
            if predicted_outcome == outcome:
                correct_predictions += 1
            
            # Count by outcome type
            if outcome == "home_win":
                home_total += 1
                if predicted_outcome == "home_win":
                    home_correct += 1
            elif outcome == "draw":
                draw_total += 1
                if predicted_outcome == "draw":
                    draw_correct += 1
            else:  # away_win
                away_total += 1
                if predicted_outcome == "away_win":
                    away_correct += 1
            
            # Brier score (per outcome)
            h = 1 if outcome == "home_win" else 0
            d = 1 if outcome == "draw" else 0
            a = 1 if outcome == "away_win" else 0
            
            brier_sum += (
                (pred.home_win_prob - h) ** 2 +
                (pred.draw_prob - d) ** 2 +
                (pred.away_win_prob - a) ** 2
            ) / 3.0
            
            # Log loss (with numerical safety)
            eps = 1e-15
            if outcome == "home_win":
                log_loss_sum -= math.log(max(pred.home_win_prob, eps))
            elif outcome == "draw":
                log_loss_sum -= math.log(max(pred.draw_prob, eps))
            else:
                log_loss_sum -= math.log(max(pred.away_win_prob, eps))
        
        # Set calculated metrics
        metrics.accuracy = correct_predictions / n
        metrics.brier_score = brier_sum / n
        metrics.log_loss = log_loss_sum / n
        
        # Outcome-specific accuracy
        metrics.home_win_accuracy = home_correct / home_total if home_total > 0 else None
        metrics.draw_accuracy = draw_correct / draw_total if draw_total > 0 else None
        metrics.away_win_accuracy = away_correct / away_total if away_total > 0 else None
        
        # Average probabilities
        metrics.avg_home_prob = sum(home_probs) / n
        metrics.avg_draw_prob = sum(draw_probs) / n  
        metrics.avg_away_prob = sum(away_probs) / n
        
        # Average confidence (simplified as max probability)
        confidences = [max(p.home_win_prob, p.draw_prob, p.away_win_prob) for p in predictions]
        metrics.avg_confidence = sum(confidences) / n
        
        # Calibration error (for home win probability)
        if n >= 10:  # Minimum for calibration analysis
            home_outcomes = [1 if outcome == "home_win" else 0 for outcome in outcomes]
            cal_result = calibration_error(home_probs, home_outcomes, n_bins=min(5, n//2))
            metrics.calibration_error = cal_result.ece if not math.isnan(cal_result.ece) else None
        
        return metrics
    
    def _calculate_ensemble_metrics(
        self,
        metrics: EnsembleMetrics,
        predictions: List[ModelPrediction],
        outcomes: List[str]
    ) -> EnsembleMetrics:
        """Calculate performance metrics for ensemble.
        
        Args:
            metrics: EnsembleMetrics object to update
            predictions: List of ensemble predictions
            outcomes: List of actual outcomes
            
        Returns:
            Updated EnsembleMetrics
        """
        if not predictions or len(predictions) != len(outcomes):
            return metrics
        
        n = len(predictions)
        
        # Calculate accuracy
        correct_predictions = 0
        brier_sum = 0.0
        log_loss_sum = 0.0
        confidence_sum = 0.0
        
        home_probs = []
        
        for pred, outcome in zip(predictions, outcomes):
            # Determine predicted outcome
            max_prob = max(pred.home_win_prob, pred.draw_prob, pred.away_win_prob)
            if pred.home_win_prob == max_prob:
                predicted_outcome = "home_win"
            elif pred.draw_prob == max_prob:
                predicted_outcome = "draw"
            else:
                predicted_outcome = "away_win"
            
            if predicted_outcome == outcome:
                correct_predictions += 1
            
            # Brier score
            h = 1 if outcome == "home_win" else 0
            d = 1 if outcome == "draw" else 0
            a = 1 if outcome == "away_win" else 0
            
            brier_sum += (
                (pred.home_win_prob - h) ** 2 +
                (pred.draw_prob - d) ** 2 +
                (pred.away_win_prob - a) ** 2
            ) / 3.0
            
            # Log loss
            eps = 1e-15
            if outcome == "home_win":
                log_loss_sum -= math.log(max(pred.home_win_prob, eps))
            elif outcome == "draw":
                log_loss_sum -= math.log(max(pred.draw_prob, eps))
            else:
                log_loss_sum -= math.log(max(pred.away_win_prob, eps))
            
            # Confidence
            confidence_sum += pred.confidence_score
            
            # Track home probabilities for calibration
            home_probs.append(pred.home_win_prob)
        
        # Set metrics
        metrics.accuracy = correct_predictions / n
        metrics.brier_score = brier_sum / n
        metrics.log_loss = log_loss_sum / n
        metrics.avg_ensemble_confidence = confidence_sum / n
        
        # Calibration error
        if n >= 10:
            home_outcomes = [1 if outcome == "home_win" else 0 for outcome in outcomes]
            cal_result = calibration_error(home_probs, home_outcomes, n_bins=min(5, n//2))
            metrics.calibration_error = cal_result.ece if not math.isnan(cal_result.ece) else None
        
        return metrics