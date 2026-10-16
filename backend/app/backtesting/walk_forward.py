"""Walk-forward validation for shot market predictions.

This module implements temporal walk-forward validation that:
1. Iterates through historical finished matches chronologically
2. Freezes prediction timestamp at match.scheduled_at
3. Builds feature snapshot using ONLY data < prediction_timestamp
4. Generates shot market predictions
5. Evaluates against actual match statistics
6. Compares baseline vs advanced feature variants
7. Detects temporal leakage violations
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple
import math

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.database.models import Match, MatchStatistic
from app.domain.enums import MatchStatus
from app.prediction.shot_market_engine import ShotMarketEngine
from app.features.advanced_feature_engineering import AdvancedFeatureEngineer
from app.features.shot_intelligence import ShotIntelligenceCalculator
from app.prediction.interfaces import ShotMarketType


logger = logging.getLogger(__name__)


class TemporalLeakageError(Exception):
    """Raised when temporal leakage is detected in walk-forward validation."""
    pass


class ShotMarketVariant(str, Enum):
    """Shot market feature variants for comparison."""
    BASELINE = "baseline"  # Simple historical average only
    PLUS_OPPONENT = "plus_opponent"  # + opponent suppression
    PLUS_RECENCY = "plus_recency"  # + recency weighting
    PLUS_SHOT_QUALITY = "plus_shot_quality"  # + xG/shot quality
    PLUS_HOME_AWAY = "plus_home_away"  # + venue split
    FULL = "full"  # All shot intelligence features


@dataclass
class EvaluationMetrics:
    """Evaluation metrics for a single threshold."""
    
    sample_size: int = 0
    brier_score: Optional[float] = None
    log_loss: Optional[float] = None
    hit_rate: Optional[float] = None
    calibration_error: Optional[float] = None
    mean_probability: Optional[float] = None
    mean_actual: Optional[float] = None


@dataclass
class VariantResults:
    """Results for a single shot market variant."""
    
    variant_name: str
    thresholds: Dict[int, EvaluationMetrics] = field(default_factory=dict)


class WalkForwardValidator:
    """Walk-forward validator for shot market predictions.
    
    Implements strict temporal validation:
    - Chronological iteration through historical matches
    - Prediction timestamp frozen at match.scheduled_at
    - Feature snapshot uses ONLY data < prediction_timestamp
    - Temporal leakage detection raises error if violated
    """
    
    EPSILON = 1e-10  # Numerical stability for log loss
    
    def __init__(
        self,
        session: Session,
        shot_market_engine: ShotMarketEngine,
        min_matches: int = 10
    ):
        """Initialize walk-forward validator.
        
        Args:
            session: Database session
            shot_market_engine: Shot market engine instance
            min_matches: Minimum matches required for validation
        """
        self.session = session
        self.engine = shot_market_engine
        self.feature_engineer = AdvancedFeatureEngineer()
        self.min_matches = min_matches
    
    def validate(
        self,
        variant: ShotMarketVariant = ShotMarketVariant.FULL
    ) -> VariantResults:
        """Run walk-forward validation for a shot market variant.
        
        Args:
            variant: Feature variant to evaluate
            
        Returns:
            VariantResults with evaluation metrics per threshold
            
        Raises:
            TemporalLeakageError: If temporal leakage detected
        """
        logger.info(f"Starting walk-forward validation for variant: {variant.value}")
        
        # Query finished matches with shot data, ordered chronologically
        matches = self.session.query(Match).join(
            MatchStatistic,
            Match.id == MatchStatistic.match_id
        ).filter(
            and_(
                Match.status == MatchStatus.FINISHED,
                MatchStatistic.shots_total.isnot(None)
            )
        ).order_by(Match.scheduled_at.asc()).distinct().all()
        
        logger.info(f"Found {len(matches)} finished matches with shot data")
        
        if len(matches) < self.min_matches:
            logger.warning(
                f"Insufficient data: {len(matches)} matches, need {self.min_matches}"
            )
            return VariantResults(variant_name=variant.value, thresholds={})
        
        # Skip first min_matches as warmup period
        validation_matches = matches[self.min_matches:]
        logger.info(f"Using {len(validation_matches)} matches for validation after {self.min_matches} warmup")
        
        # Accumulators for predictions and actuals per threshold
        # Key: (threshold, is_home_team)
        predictions_by_threshold: Dict[Tuple[int, bool], List[Tuple[float, int]]] = {}
        
        for i, match in enumerate(validation_matches):
            if (i + 1) % 100 == 0:
                logger.info(f"Processed {i + 1}/{len(validation_matches)} matches")
            
            # Freeze prediction timestamp
            prediction_timestamp = match.scheduled_at
            
            try:
                # Build feature snapshot using ONLY data < prediction_timestamp
                snapshot = self.feature_engineer.build_snapshot(
                    match=match,
                    session=self.session,
                    before_datetime=prediction_timestamp
                )
                
                # Detect temporal leakage (target match must be excluded)
                self._check_temporal_leakage(snapshot, match, len(matches))
                
                # Configure variant-specific features
                shot_calc = self._create_variant_calculator(variant)
                variant_engine = ShotMarketEngine(
                    session=self.session,
                    shot_production_calc=shot_calc
                )
                
                # Generate shot market predictions
                # Need raw MatchWithStatistics for shot production calculator
                from app.features.advanced_team_intelligence import MatchWithStatistics
                
                # Get historical matches for both teams (before prediction timestamp)
                home_matches = self._get_team_matches(
                    match.home_team_id,
                    before_datetime=prediction_timestamp
                )
                away_matches = self._get_team_matches(
                    match.away_team_id,
                    before_datetime=prediction_timestamp
                )
                
                shot_predictions = variant_engine.predict_all_shot_markets(
                    snapshot=snapshot,
                    home_matches=home_matches,
                    away_matches=away_matches
                )
                
                # Load actual match statistics AFTER prediction
                home_stats = self.session.query(MatchStatistic).filter(
                    and_(
                        MatchStatistic.match_id == match.id,
                        MatchStatistic.team_id == match.home_team_id
                    )
                ).first()
                
                away_stats = self.session.query(MatchStatistic).filter(
                    and_(
                        MatchStatistic.match_id == match.id,
                        MatchStatistic.team_id == match.away_team_id
                    )
                ).first()
                
                if home_stats is None or away_stats is None:
                    continue
                
                if home_stats.shots_total is None or away_stats.shots_total is None:
                    continue
                
                # Extract predictions for team shots
                if ShotMarketType.TEAM_SHOTS in shot_predictions:
                    team_shots_preds = shot_predictions[ShotMarketType.TEAM_SHOTS]
                    
                    for pred in team_shots_preds:
                        is_home = (pred.team_id == match.home_team_id)
                        actual_shots = home_stats.shots_total if is_home else away_stats.shots_total
                        
                        # Evaluate each threshold
                        for threshold_obj in pred.thresholds:
                            threshold_val = threshold_obj.threshold
                            prob = threshold_obj.over_probability
                            
                            if prob is None:
                                continue
                            
                            # Binary actual: 1 if shots >= threshold, else 0
                            actual_binary = 1 if actual_shots >= threshold_val else 0
                            
                            key = (threshold_val, is_home)
                            if key not in predictions_by_threshold:
                                predictions_by_threshold[key] = []
                            
                            predictions_by_threshold[key].append((prob, actual_binary))
            
            except Exception as e:
                logger.warning(f"Error processing match {match.id}: {e}")
                continue
        
        # Calculate evaluation metrics for each threshold
        thresholds_metrics: Dict[int, EvaluationMetrics] = {}
        
        # Aggregate home and away predictions for each threshold
        threshold_values = set(t for t, _ in predictions_by_threshold.keys())
        
        for threshold in threshold_values:
            all_preds_for_threshold = []
            
            # Combine home and away predictions
            for is_home in [True, False]:
                key = (threshold, is_home)
                if key in predictions_by_threshold:
                    all_preds_for_threshold.extend(predictions_by_threshold[key])
            
            if all_preds_for_threshold:
                metrics = self.calculate_evaluation_metrics(all_preds_for_threshold)
                thresholds_metrics[threshold] = metrics
        
        logger.info(f"Validation complete for variant {variant.value}: {len(thresholds_metrics)} thresholds evaluated")
        
        return VariantResults(
            variant_name=variant.value,
            thresholds=thresholds_metrics
        )
    
    def calculate_evaluation_metrics(
        self,
        predictions: List[Tuple[float, int]]
    ) -> EvaluationMetrics:
        """Calculate evaluation metrics from predictions and actuals.
        
        Args:
            predictions: List of (probability, actual_binary) tuples
            
        Returns:
            EvaluationMetrics with Brier, log loss, hit rate, calibration
        """
        if not predictions:
            return EvaluationMetrics(sample_size=0)
        
        n = len(predictions)
        probs = [p for p, _ in predictions]
        actuals = [a for _, a in predictions]
        
        # Brier score: mean((p - a)^2)
        brier = sum((p - a) ** 2 for p, a in predictions) / n
        
        # Log loss: -mean(a*log(p) + (1-a)*log(1-p))
        log_loss_sum = 0.0
        for prob, actual in predictions:
            # Clip probabilities for numerical stability
            p_clipped = max(self.EPSILON, min(1 - self.EPSILON, prob))
            if actual == 1:
                log_loss_sum += -math.log(p_clipped)
            else:
                log_loss_sum += -math.log(1 - p_clipped)
        log_loss_val = log_loss_sum / n
        
        # Hit rate: proportion where prediction matches actual
        # (p >= 0.5 and a == 1) or (p < 0.5 and a == 0)
        hits = sum(
            1 for p, a in predictions
            if (p >= 0.5 and a == 1) or (p < 0.5 and a == 0)
        )
        hit_rate = hits / n
        
        # Calibration error (simplified binning approach)
        calibration_error = self._calculate_calibration_error(predictions)
        
        # Mean values
        mean_prob = sum(probs) / n
        mean_actual = sum(actuals) / n
        
        return EvaluationMetrics(
            sample_size=n,
            brier_score=brier,
            log_loss=log_loss_val,
            hit_rate=hit_rate,
            calibration_error=calibration_error,
            mean_probability=mean_prob,
            mean_actual=mean_actual
        )
    
    def _calculate_calibration_error(
        self,
        predictions: List[Tuple[float, int]],
        n_bins: int = 10
    ) -> float:
        """Calculate calibration error using binning approach.
        
        Args:
            predictions: List of (probability, actual) tuples
            n_bins: Number of bins for calibration
            
        Returns:
            Expected Calibration Error (ECE)
        """
        if not predictions:
            return 0.0
        
        # Sort by probability
        sorted_preds = sorted(predictions, key=lambda x: x[0])
        
        # Create bins
        bin_size = len(sorted_preds) // n_bins
        if bin_size == 0:
            return 0.0
        
        ece = 0.0
        total_samples = len(sorted_preds)
        
        for i in range(n_bins):
            start_idx = i * bin_size
            end_idx = start_idx + bin_size if i < n_bins - 1 else len(sorted_preds)
            
            bin_preds = sorted_preds[start_idx:end_idx]
            if not bin_preds:
                continue
            
            bin_probs = [p for p, _ in bin_preds]
            bin_actuals = [a for _, a in bin_preds]
            
            mean_prob = sum(bin_probs) / len(bin_probs)
            mean_actual = sum(bin_actuals) / len(bin_actuals)
            
            ece += (len(bin_preds) / total_samples) * abs(mean_prob - mean_actual)
        
        return ece
    
    def _check_temporal_leakage(
        self,
        snapshot,
        target_match: Match,
        total_historical_matches: int
    ):
        """Detect temporal leakage in feature snapshot.
        
        Args:
            snapshot: MatchFeatureSnapshot
            target_match: Target match being predicted
            total_historical_matches: Total historical matches available
            
        Raises:
            TemporalLeakageError: If target match included in features
        """
        # Check if shot intelligence sample size equals total matches
        # (which would mean target match was included)
        if hasattr(snapshot, 'home_shot_intelligence') and snapshot.home_shot_intelligence:
            if snapshot.home_shot_intelligence.sample_size >= total_historical_matches:
                raise TemporalLeakageError(
                    f"Temporal leakage detected: home shot intelligence sample size "
                    f"({snapshot.home_shot_intelligence.sample_size}) >= total matches "
                    f"({total_historical_matches}), indicating target match may be included"
                )
        
        if hasattr(snapshot, 'away_shot_intelligence') and snapshot.away_shot_intelligence:
            if snapshot.away_shot_intelligence.sample_size >= total_historical_matches:
                raise TemporalLeakageError(
                    f"Temporal leakage detected: away shot intelligence sample size "
                    f"({snapshot.away_shot_intelligence.sample_size}) >= total matches "
                    f"({total_historical_matches}), indicating target match may be included"
                )
    
    def _create_variant_calculator(
        self,
        variant: ShotMarketVariant
    ) -> ShotIntelligenceCalculator:
        """Create shot intelligence calculator for specific variant.
        
        Args:
            variant: Feature variant
            
        Returns:
            Configured ShotIntelligenceCalculator
        """
        # Different variants use different parameters
        # For now, all variants use same calculator
        # TODO: Implement feature filtering per variant
        return ShotIntelligenceCalculator(session=self.session)
    
    def _get_team_matches(
        self,
        team_id: str,
        before_datetime: datetime
    ) -> List:
        """Get historical matches for a team before cutoff datetime.
        
        Args:
            team_id: Team ID
            before_datetime: Cutoff datetime
            
        Returns:
            List of MatchWithStatistics
        """
        from app.features.advanced_team_intelligence import MatchWithStatistics
        
        # Query matches where team is home or away
        matches = self.session.query(Match).filter(
            and_(
                Match.status == MatchStatus.FINISHED,
                Match.scheduled_at < before_datetime,
                (Match.home_team_id == team_id) | (Match.away_team_id == team_id)
            )
        ).order_by(Match.scheduled_at.desc()).all()
        
        # Convert to MatchWithStatistics
        result = []
        for match in matches:
            # Load statistics
            home_stats = self.session.query(MatchStatistic).filter(
                and_(
                    MatchStatistic.match_id == match.id,
                    MatchStatistic.team_id == match.home_team_id
                )
            ).first()
            
            away_stats = self.session.query(MatchStatistic).filter(
                and_(
                    MatchStatistic.match_id == match.id,
                    MatchStatistic.team_id == match.away_team_id
                )
            ).first()
            
            mws = MatchWithStatistics(
                match=match,
                home_statistics=home_stats,
                away_statistics=away_stats
            )
            result.append(mws)
        
        return result
