"""Shot market prediction engine.

This module calculates shot market probabilities using the existing ShotProductionCalculator
from the shot production feature engineering module.

Shot Markets Supported:
- Team shots (home/away separately)
- Team shots on target (home/away separately)
- Total shots (home + away combined)
- Total shots on target (home + away combined)

Thresholds:
- Team shots: 10+, 12+, 15+, 18+, 20+
- Team SOT: 3+, 4+, 5+, 6+
- Total shots: 20+, 22+, 25+, 30+
- Total SOT: 8+, 10+, 12+ (combined thresholds)

Distribution Selection:
- Poisson: When variance ≈ mean (equidispersed)
- Negative Binomial: When variance > mean (overdispersed)
- UNAVAILABLE: When insufficient data

Data Flow:
1. Extract shot data from MatchFeatureSnapshot
2. Use ShotProductionCalculator to fit distributions
3. Calculate P(X >= T) for each threshold
4. Return ShotMarketPrediction with probabilities and provenance
"""

from __future__ import annotations

from typing import Optional, Dict, List
from datetime import datetime

from app.prediction.interfaces import (
    ShotMarketType,
    ShotMarketPrediction,
    ShotMarketThreshold,
    DistributionType
)
from app.prediction.feature_snapshot import MatchFeatureSnapshot
from app.features.shot_production import ShotProductionCalculator, ShotProduction
from app.features.shot_intelligence import ShotIntelligenceCalculator
from app.features.advanced_team_intelligence import MatchWithStatistics


class ShotMarketEngine:
    """Calculate shot market probabilities using statistical distributions.
    
    Reuses ShotProductionCalculator from feature engineering infrastructure.
    """
    
    # Threshold definitions
    TEAM_SHOTS_THRESHOLDS = [10, 12, 15, 18, 20]
    SOT_THRESHOLDS = [3, 4, 5, 6]
    TOTAL_SHOTS_THRESHOLDS = [20, 22, 25, 30]
    TOTAL_SOT_THRESHOLDS = [8, 10, 12]
    
    def __init__(self, session, shot_production_calc: Optional[ShotProductionCalculator] = None):
        """Initialize shot market engine.
        
        Args:
            session: Database session
            shot_production_calc: Optional ShotProductionCalculator instance
        """
        self.session = session
        self.shot_calc = shot_production_calc or ShotProductionCalculator(session=session)
    
    def predict_all_shot_markets(
        self,
        snapshot: MatchFeatureSnapshot,
        home_matches: Optional[List[MatchWithStatistics]] = None,
        away_matches: Optional[List[MatchWithStatistics]] = None,
        before_datetime: Optional[datetime] = None
    ) -> Dict[ShotMarketType, List[ShotMarketPrediction]]:
        """Predict all available shot markets for a match.
        
        Args:
            snapshot: Match feature snapshot (contains aggregated shot intelligence)
            home_matches: Historical matches for home team (for raw shot counts)
            away_matches: Historical matches for away team (for raw shot counts)
            before_datetime: Temporal cutoff for data (strict <)
            
        Returns:
            Dictionary mapping market type to list of predictions (home, away, total)
        """
        results: Dict[ShotMarketType, List[ShotMarketPrediction]] = {}
        
        # Check if shot intelligence data is available in snapshot
        if snapshot.home_shot_intelligence is None or snapshot.away_shot_intelligence is None:
            # Shot intelligence not available - return empty dict
            return results
        
        # Check if we have raw match data for distribution fitting
        if home_matches is None or away_matches is None:
            # Cannot fit distributions without raw data - return empty dict
            return results
        
        # Initialize shot intelligence calculator to extract raw counts
        shot_intel_calc = ShotIntelligenceCalculator(session=self.session)
        
        # Extract raw shot counts for home team
        home_shots, home_sot = shot_intel_calc.get_raw_shot_counts(
            team_id=snapshot.home_team_id,
            matches_with_stats=home_matches,
            before_datetime=before_datetime
        )
        
        # Extract raw shot counts for away team
        away_shots, away_sot = shot_intel_calc.get_raw_shot_counts(
            team_id=snapshot.away_team_id,
            matches_with_stats=away_matches,
            before_datetime=before_datetime
        )
        
        # Calculate shot production for home team
        home_shot_prod = self.shot_calc.calculate(
            team_id=snapshot.home_team_id,
            shot_counts=home_shots,
            sot_counts=home_sot if home_sot else None,
            before_datetime=before_datetime
        )
        
        # Calculate shot production for away team
        away_shot_prod = self.shot_calc.calculate(
            team_id=snapshot.away_team_id,
            shot_counts=away_shots,
            sot_counts=away_sot if away_sot else None,
            before_datetime=before_datetime
        )
        
        # Calculate total shots production
        total_shot_prod = self.shot_calc.calculate_total(
            home_shot_counts=home_shots,
            away_shot_counts=away_shots
        )
        
        # Build team shots predictions
        home_shots_pred = self._build_team_shots_prediction(
            team_id=snapshot.home_team_id,
            shot_production=home_shot_prod,
            market_type=ShotMarketType.TEAM_SHOTS
        )
        
        away_shots_pred = self._build_team_shots_prediction(
            team_id=snapshot.away_team_id,
            shot_production=away_shot_prod,
            market_type=ShotMarketType.TEAM_SHOTS
        )
        
        results[ShotMarketType.TEAM_SHOTS] = [home_shots_pred, away_shots_pred]
        
        # Build team SOT predictions if available
        home_sot_pred = self._build_team_sot_prediction(
            team_id=snapshot.home_team_id,
            shot_production=home_shot_prod,
            market_type=ShotMarketType.TEAM_SHOTS_ON_TARGET
        )
        
        away_sot_pred = self._build_team_sot_prediction(
            team_id=snapshot.away_team_id,
            shot_production=away_shot_prod,
            market_type=ShotMarketType.TEAM_SHOTS_ON_TARGET
        )
        
        results[ShotMarketType.TEAM_SHOTS_ON_TARGET] = [home_sot_pred, away_sot_pred]
        
        # Build total shots prediction
        total_shots_pred = self._build_total_shots_prediction(
            shot_production=total_shot_prod
        )
        
        results[ShotMarketType.TOTAL_SHOTS] = [total_shots_pred]
        
        return results
    
    def _build_team_shots_prediction(
        self,
        team_id: str,
        shot_production: ShotProduction,
        market_type: ShotMarketType
    ) -> ShotMarketPrediction:
        """Build shot market prediction from ShotProduction result.
        
        Args:
            team_id: Team identifier
            shot_production: ShotProduction from calculator
            market_type: Market type
            
        Returns:
            ShotMarketPrediction
        """
        # Determine distribution type
        if shot_production.shots_distribution_model is None or shot_production.shots_distribution_model == "none":
            # Distribution fitting was not performed or failed
            dist_type = DistributionType.UNAVAILABLE
            unavailability_reason = "insufficient_shot_data"
        elif shot_production.shots_distribution_model == "poisson":
            dist_type = DistributionType.POISSON
            unavailability_reason = None
        elif shot_production.shots_distribution_model == "negative_binomial":
            dist_type = DistributionType.NEGATIVE_BINOMIAL
            unavailability_reason = None
        else:
            # Unknown distribution type
            dist_type = DistributionType.UNAVAILABLE
            unavailability_reason = "distribution_fitting_failed"
        
        # Build thresholds
        thresholds: List[ShotMarketThreshold] = []
        
        threshold_probs = [
            (10, shot_production.over_10_shots_prob),
            (12, shot_production.over_12_shots_prob),
            (15, shot_production.over_15_shots_prob),
            (18, shot_production.over_18_shots_prob),
            (20, shot_production.over_20_shots_prob),
        ]
        
        for threshold_val, prob in threshold_probs:
            if prob is not None:
                thresholds.append(ShotMarketThreshold(
                    threshold=threshold_val,
                    over_probability=prob,
                    distribution_model=dist_type,
                    expected_value=shot_production.expected_shots_mean,
                    variance=shot_production.expected_shots_variance,
                    data_quality=shot_production.data_quality_score
                ))
        
        # Check availability
        available = (dist_type != DistributionType.UNAVAILABLE and len(thresholds) > 0)
        
        # Set unavailability reason if needed
        if not available and unavailability_reason is None:
            if shot_production.sample_size < 5:
                unavailability_reason = "insufficient_historical_sample"
            else:
                unavailability_reason = "insufficient_shot_data"
        
        return ShotMarketPrediction(
            team_id=team_id,
            market_type=market_type,
            thresholds=thresholds,
            distribution_model=dist_type,
            expected_value=shot_production.expected_shots_mean,
            variance=shot_production.expected_shots_variance,
            available=available,
            unavailability_reason=unavailability_reason,
            sample_size=shot_production.sample_size,
            data_quality_score=shot_production.data_quality_score,
            model_id="shot_market_v1"
        )
    
    def _build_team_sot_prediction(
        self,
        team_id: str,
        shot_production: ShotProduction,
        market_type: ShotMarketType
    ) -> ShotMarketPrediction:
        """Build SOT market prediction from ShotProduction result.
        
        Args:
            team_id: Team identifier
            shot_production: ShotProduction from calculator
            market_type: Market type (TEAM_SHOTS_ON_TARGET)
            
        Returns:
            ShotMarketPrediction
        """
        # Determine distribution type for SOT
        if shot_production.sot_distribution_model is None or shot_production.sot_distribution_model == "none":
            dist_type = DistributionType.UNAVAILABLE
            unavailability_reason = "insufficient_sot_data"
        elif shot_production.sot_distribution_model == "poisson":
            dist_type = DistributionType.POISSON
            unavailability_reason = None
        elif shot_production.sot_distribution_model == "negative_binomial":
            dist_type = DistributionType.NEGATIVE_BINOMIAL
            unavailability_reason = None
        else:
            dist_type = DistributionType.UNAVAILABLE
            unavailability_reason = "distribution_fitting_failed"
        
        # Build SOT thresholds
        thresholds: List[ShotMarketThreshold] = []
        
        threshold_probs = [
            (3, shot_production.over_3_sot_prob),
            (4, shot_production.over_4_sot_prob),
            (5, shot_production.over_5_sot_prob),
            (6, shot_production.over_6_sot_prob),
        ]
        
        for threshold_val, prob in threshold_probs:
            if prob is not None:
                thresholds.append(ShotMarketThreshold(
                    threshold=threshold_val,
                    over_probability=prob,
                    distribution_model=dist_type,
                    expected_value=shot_production.expected_sot_mean,
                    variance=shot_production.expected_sot_variance,
                    data_quality=shot_production.data_quality_score
                ))
        
        # Check availability
        available = (dist_type != DistributionType.UNAVAILABLE and len(thresholds) > 0)
        
        # Set unavailability reason if needed
        if not available and unavailability_reason is None:
            if shot_production.sample_size < 5:
                unavailability_reason = "insufficient_historical_sample"
            else:
                unavailability_reason = "insufficient_sot_data"
        
        return ShotMarketPrediction(
            team_id=team_id,
            market_type=market_type,
            thresholds=thresholds,
            distribution_model=dist_type,
            expected_value=shot_production.expected_sot_mean,
            variance=shot_production.expected_sot_variance,
            available=available,
            unavailability_reason=unavailability_reason,
            sample_size=shot_production.sample_size,
            data_quality_score=shot_production.data_quality_score,
            model_id="shot_market_v1"
        )
    
    def _build_total_shots_prediction(
        self,
        shot_production: ShotProduction
    ) -> ShotMarketPrediction:
        """Build total shots market prediction.
        
        Args:
            shot_production: ShotProduction from calculate_total()
            
        Returns:
            ShotMarketPrediction for total shots market
        """
        # Determine distribution type
        if shot_production.total_shots_distribution_model is None or \
           shot_production.total_shots_distribution_model == "none":
            dist_type = DistributionType.UNAVAILABLE
            unavailability_reason = "insufficient_total_shots_data"
        elif shot_production.total_shots_distribution_model == "poisson":
            dist_type = DistributionType.POISSON
            unavailability_reason = None
        elif shot_production.total_shots_distribution_model == "negative_binomial":
            dist_type = DistributionType.NEGATIVE_BINOMIAL
            unavailability_reason = None
        else:
            dist_type = DistributionType.UNAVAILABLE
            unavailability_reason = "distribution_fitting_failed"
        
        # Build total shots thresholds
        thresholds: List[ShotMarketThreshold] = []
        
        threshold_probs = [
            (20, shot_production.total_over_20_prob),
            (22, shot_production.total_over_22_prob),
            (25, shot_production.total_over_25_prob),
            (30, shot_production.total_over_30_prob),
        ]
        
        for threshold_val, prob in threshold_probs:
            if prob is not None:
                thresholds.append(ShotMarketThreshold(
                    threshold=threshold_val,
                    over_probability=prob,
                    distribution_model=dist_type,
                    expected_value=shot_production.expected_total_shots_mean,
                    variance=shot_production.expected_total_shots_variance,
                    data_quality=shot_production.data_quality_score
                ))
        
        # Check availability
        available = (dist_type != DistributionType.UNAVAILABLE and len(thresholds) > 0)
        
        # Set unavailability reason if needed
        if not available and unavailability_reason is None:
            if shot_production.sample_size < 5:
                unavailability_reason = "insufficient_historical_sample"
            else:
                unavailability_reason = "insufficient_total_shots_data"
        
        return ShotMarketPrediction(
            team_id="total",
            market_type=ShotMarketType.TOTAL_SHOTS,
            thresholds=thresholds,
            distribution_model=dist_type,
            expected_value=shot_production.expected_total_shots_mean,
            variance=shot_production.expected_total_shots_variance,
            available=available,
            unavailability_reason=unavailability_reason,
            sample_size=shot_production.sample_size,
            data_quality_score=shot_production.data_quality_score,
            model_id="shot_market_v1"
        )
