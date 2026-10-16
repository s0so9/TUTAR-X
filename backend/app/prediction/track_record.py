"""Track record management and evaluation.

Stores and evaluates prediction performance transparently.
Tracks ALL predictions including failures (no cherry-picking).

Metrics:
- Brier score: mean((predicted_prob - actual)^2) for 1X2
- Log loss: -mean(log(predicted_prob_of_actual_outcome))
- Accuracy: % of correct predictions
- ROI: Return on investment if betting with flat stakes
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum
import math


class PredictionOutcome(str, Enum):
    """Actual match outcomes."""
    
    HOME_WIN = "home_win"
    DRAW = "draw"
    AWAY_WIN = "away_win"


@dataclass
class PredictionResult:
    """Single prediction with actual outcome."""
    
    prediction_version_id: str
    """Prediction version identifier"""
    
    match_id: str
    """Match identifier"""
    
    predicted_home_win: float
    """Predicted home win probability [0, 1]"""
    
    predicted_draw: float
    """Predicted draw probability [0, 1]"""
    
    predicted_away_win: float
    """Predicted away win probability [0, 1]"""
    
    actual_outcome: PredictionOutcome
    """Actual match outcome"""
    
    actual_home_score: int
    """Actual home score"""
    
    actual_away_score: int
    """Actual away score"""
    
    prediction_timestamp: datetime
    """When prediction was made"""
    
    match_timestamp: datetime
    """When match was played"""
    
    # Market outcomes (optional)
    over_2_5_predicted: Optional[float] = None
    over_2_5_actual: Optional[bool] = None
    
    btts_predicted: Optional[float] = None
    btts_actual: Optional[bool] = None
    
    # Betting outcomes (optional)
    home_odds: Optional[float] = None
    draw_odds: Optional[float] = None
    away_odds: Optional[float] = None
    
    # Metadata
    league_id: Optional[str] = None
    model_id: Optional[str] = None
    stage: Optional[str] = None


@dataclass
class TrackRecordReport:
    """Track record performance report."""
    
    # Sample info
    n_predictions: int
    """Total predictions evaluated"""
    
    date_range: tuple[datetime, datetime]
    """(earliest, latest) prediction timestamps"""
    
    # Performance metrics
    brier_score: float
    """Brier score for 1X2 market [0, 1] (lower is better)"""
    
    log_loss: float
    """Log loss for 1X2 market (lower is better)"""
    
    accuracy: float
    """Accuracy rate [0, 1] (correct predictions / total)"""
    
    roi_flat_betting: Optional[float] = None
    """ROI if betting on most probable outcome with flat stakes (None if no odds)"""
    
    # Breakdowns
    by_league: Dict[str, Dict[str, float]] = field(default_factory=dict)
    """Performance by league: {league_id: {metric: value, ...}}"""
    
    by_model: Dict[str, Dict[str, float]] = field(default_factory=dict)
    """Performance by model: {model_id: {metric: value, ...}}"""
    
    by_stage: Dict[str, Dict[str, float]] = field(default_factory=dict)
    """Performance by stage: {stage: {metric: value, ...}}"""
    
    # Calibration info
    calibration_curve: List[tuple[float, float]] = field(default_factory=list)
    """Calibration curve: [(predicted_prob_bin, actual_frequency), ...]"""


class TrackRecordManager:
    """Manages prediction track record and performance evaluation.
    
    Features:
    - Stores ALL predictions with outcomes (no cherry-picking)
    - Calculates standard performance metrics
    - Provides breakdowns by league, model, stage
    - Generates calibration curves
    - Transparent reporting (includes failures)
    
    Track record is persisted through PredictionPersistenceService.
    """
    
    def __init__(self, persistence_service=None):
        """Initialize track record manager.
        
        Args:
            persistence_service: Optional PredictionPersistenceService
        """
        self.persistence_service = persistence_service
        # In-memory storage for testing
        self._memory_store: List[PredictionResult] = []
    
    def record_outcome(
        self,
        prediction_version_id: str,
        match_id: str,
        predicted_probs: tuple[float, float, float],  # (home, draw, away)
        actual_outcome: PredictionOutcome,
        actual_scores: tuple[int, int],  # (home, away)
        prediction_timestamp: datetime,
        match_timestamp: datetime,
        market_predictions: Optional[Dict[str, float]] = None,
        market_actuals: Optional[Dict[str, bool]] = None,
        odds: Optional[tuple[float, float, float]] = None,
        league_id: Optional[str] = None,
        model_id: Optional[str] = None,
        stage: Optional[str] = None
    ) -> PredictionResult:
        """Record prediction outcome.
        
        Args:
            prediction_version_id: Prediction version ID
            match_id: Match ID
            predicted_probs: (home_win, draw, away_win) probabilities
            actual_outcome: Actual match outcome
            actual_scores: (home_score, away_score)
            prediction_timestamp: When prediction was made
            match_timestamp: When match was played
            market_predictions: Optional market predictions
            market_actuals: Optional market actuals
            odds: Optional (home_odds, draw_odds, away_odds)
            league_id: Optional league identifier
            model_id: Optional model identifier
            stage: Optional prediction stage
        
        Returns:
            Created PredictionResult
        """
        home_prob, draw_prob, away_prob = predicted_probs
        home_score, away_score = actual_scores
        
        result = PredictionResult(
            prediction_version_id=prediction_version_id,
            match_id=match_id,
            predicted_home_win=home_prob,
            predicted_draw=draw_prob,
            predicted_away_win=away_prob,
            actual_outcome=actual_outcome,
            actual_home_score=home_score,
            actual_away_score=away_score,
            prediction_timestamp=prediction_timestamp,
            match_timestamp=match_timestamp,
            league_id=league_id,
            model_id=model_id,
            stage=stage
        )
        
        # Add market predictions/actuals if provided
        if market_predictions:
            result.over_2_5_predicted = market_predictions.get("over_2_5")
            result.btts_predicted = market_predictions.get("btts")
        
        if market_actuals:
            result.over_2_5_actual = market_actuals.get("over_2_5")
            result.btts_actual = market_actuals.get("btts")
        
        # Add odds if provided
        if odds:
            result.home_odds, result.draw_odds, result.away_odds = odds
        
        # Persist result
        if self.persistence_service:
            self.persistence_service.save_track_record(result)
        else:
            self._memory_store.append(result)
        
        return result
    
    def get_track_record(
        self,
        filters: Optional[Dict[str, any]] = None
    ) -> TrackRecordReport:
        """Get track record report with optional filters.
        
        Args:
            filters: Optional filters:
                - league_id: Filter by league
                - model_id: Filter by model
                - stage: Filter by prediction stage
                - date_from: Filter by prediction date
                - date_to: Filter by prediction date
        
        Returns:
            TrackRecordReport with performance metrics
        """
        # Get results
        if self.persistence_service:
            results = self.persistence_service.get_track_record(filters or {})
        else:
            results = self._memory_store
            
            # Apply filters
            if filters:
                if "league_id" in filters:
                    results = [r for r in results if r.league_id == filters["league_id"]]
                if "model_id" in filters:
                    results = [r for r in results if r.model_id == filters["model_id"]]
                if "stage" in filters:
                    results = [r for r in results if r.stage == filters["stage"]]
                if "date_from" in filters:
                    results = [r for r in results if r.prediction_timestamp >= filters["date_from"]]
                if "date_to" in filters:
                    results = [r for r in results if r.prediction_timestamp <= filters["date_to"]]
        
        if not results:
            # Return empty report
            return TrackRecordReport(
                n_predictions=0,
                date_range=(datetime.min, datetime.max),
                brier_score=0.0,
                log_loss=0.0,
                accuracy=0.0
            )
        
        # Calculate metrics
        brier_score = self._calculate_brier_score(results)
        log_loss = self._calculate_log_loss(results)
        accuracy = self._calculate_accuracy(results)
        roi = self._calculate_roi(results)
        
        # Calculate breakdowns
        by_league = self._calculate_breakdown(results, "league_id")
        by_model = self._calculate_breakdown(results, "model_id")
        by_stage = self._calculate_breakdown(results, "stage")
        
        # Calculate calibration curve
        calibration_curve = self._calculate_calibration_curve(results)
        
        # Date range
        timestamps = [r.prediction_timestamp for r in results]
        date_range = (min(timestamps), max(timestamps))
        
        return TrackRecordReport(
            n_predictions=len(results),
            date_range=date_range,
            brier_score=brier_score,
            log_loss=log_loss,
            accuracy=accuracy,
            roi_flat_betting=roi,
            by_league=by_league,
            by_model=by_model,
            by_stage=by_stage,
            calibration_curve=calibration_curve
        )
    
    def _calculate_brier_score(self, results: List[PredictionResult]) -> float:
        """Calculate Brier score for 1X2 market.
        
        Brier = mean((predicted - actual)^2) for each outcome
        
        Args:
            results: Prediction results
        
        Returns:
            Brier score [0, 1] (lower is better)
        """
        if not results:
            return 0.0
        
        total_score = 0.0
        
        for result in results:
            # Create outcome vector (one-hot encoding)
            if result.actual_outcome == PredictionOutcome.HOME_WIN:
                actual = [1.0, 0.0, 0.0]
            elif result.actual_outcome == PredictionOutcome.DRAW:
                actual = [0.0, 1.0, 0.0]
            else:  # AWAY_WIN
                actual = [0.0, 0.0, 1.0]
            
            predicted = [
                result.predicted_home_win,
                result.predicted_draw,
                result.predicted_away_win
            ]
            
            # Calculate squared errors
            score = sum((p - a) ** 2 for p, a in zip(predicted, actual))
            total_score += score
        
        return total_score / len(results)
    
    def _calculate_log_loss(self, results: List[PredictionResult]) -> float:
        """Calculate log loss for 1X2 market.
        
        LogLoss = -mean(log(predicted_prob_of_actual_outcome))
        
        Args:
            results: Prediction results
        
        Returns:
            Log loss (lower is better)
        """
        if not results:
            return 0.0
        
        total_loss = 0.0
        
        for result in results:
            # Get predicted probability of actual outcome
            if result.actual_outcome == PredictionOutcome.HOME_WIN:
                prob = result.predicted_home_win
            elif result.actual_outcome == PredictionOutcome.DRAW:
                prob = result.predicted_draw
            else:
                prob = result.predicted_away_win
            
            # Clip probability to avoid log(0)
            prob = max(0.0001, min(0.9999, prob))
            
            total_loss += -math.log(prob)
        
        return total_loss / len(results)
    
    def _calculate_accuracy(self, results: List[PredictionResult]) -> float:
        """Calculate accuracy rate.
        
        Accuracy = (correct predictions) / (total predictions)
        
        A prediction is correct if the most probable outcome matches actual.
        
        Args:
            results: Prediction results
        
        Returns:
            Accuracy [0, 1]
        """
        if not results:
            return 0.0
        
        correct = 0
        
        for result in results:
            # Find most probable outcome
            probs = {
                PredictionOutcome.HOME_WIN: result.predicted_home_win,
                PredictionOutcome.DRAW: result.predicted_draw,
                PredictionOutcome.AWAY_WIN: result.predicted_away_win
            }
            
            predicted_outcome = max(probs, key=probs.get)
            
            if predicted_outcome == result.actual_outcome:
                correct += 1
        
        return correct / len(results)
    
    def _calculate_roi(self, results: List[PredictionResult]) -> Optional[float]:
        """Calculate ROI if betting on most probable outcome with flat stakes.
        
        ROI = (total_returns - total_stakes) / total_stakes
        
        Args:
            results: Prediction results
        
        Returns:
            ROI as decimal (e.g., 0.15 = 15% ROI) or None if no odds available
        """
        # Check if any results have odds
        results_with_odds = [r for r in results if r.home_odds and r.draw_odds and r.away_odds]
        
        if not results_with_odds:
            return None
        
        total_stake = len(results_with_odds)  # 1 unit per bet
        total_return = 0.0
        
        # Invariant: total_stake > 0 (guaranteed by early return above)
        assert total_stake > 0, "total_stake must be > 0 after filtering"
        
        for result in results_with_odds:
            # Find most probable outcome
            probs = {
                PredictionOutcome.HOME_WIN: result.predicted_home_win,
                PredictionOutcome.DRAW: result.predicted_draw,
                PredictionOutcome.AWAY_WIN: result.predicted_away_win
            }
            
            predicted_outcome = max(probs, key=probs.get)
            
            # Get odds for predicted outcome
            if predicted_outcome == PredictionOutcome.HOME_WIN:
                odds = result.home_odds
            elif predicted_outcome == PredictionOutcome.DRAW:
                odds = result.draw_odds
            else:
                odds = result.away_odds
            
            # Calculate return
            if predicted_outcome == result.actual_outcome:
                total_return += odds  # Win: return = odds (includes stake)
            # Else: lose stake (return = 0)
        
        roi = (total_return - total_stake) / total_stake
        return roi
    
    def _calculate_breakdown(
        self,
        results: List[PredictionResult],
        group_by: str
    ) -> Dict[str, Dict[str, float]]:
        """Calculate performance breakdown by grouping attribute.
        
        Args:
            results: Prediction results
            group_by: Attribute to group by ("league_id", "model_id", "stage")
        
        Returns:
            Dict mapping group value to metrics dict
        """
        # Group results
        groups: Dict[str, List[PredictionResult]] = {}
        
        for result in results:
            key = getattr(result, group_by, None)
            if key is None:
                key = "unknown"
            
            if key not in groups:
                groups[key] = []
            groups[key].append(result)
        
        # Calculate metrics for each group
        breakdown = {}
        
        for key, group_results in groups.items():
            breakdown[key] = {
                "n_predictions": len(group_results),
                "brier_score": self._calculate_brier_score(group_results),
                "log_loss": self._calculate_log_loss(group_results),
                "accuracy": self._calculate_accuracy(group_results),
                "roi": self._calculate_roi(group_results)
            }
        
        return breakdown
    
    def _calculate_calibration_curve(
        self,
        results: List[PredictionResult],
        n_bins: int = 10
    ) -> List[tuple[float, float]]:
        """Calculate calibration curve.
        
        Groups predictions into probability bins and calculates actual frequency.
        
        Args:
            results: Prediction results
            n_bins: Number of probability bins
        
        Returns:
            List of (predicted_prob_bin_center, actual_frequency) tuples
        """
        # Create bins
        bins = {i: {"predicted": [], "actual": []} for i in range(n_bins)}
        
        for result in results:
            # Use home win probability as example
            prob = result.predicted_home_win
            bin_idx = min(int(prob * n_bins), n_bins - 1)
            
            bins[bin_idx]["predicted"].append(prob)
            bins[bin_idx]["actual"].append(
                1.0 if result.actual_outcome == PredictionOutcome.HOME_WIN else 0.0
            )
        
        # Calculate curve points
        curve = []
        
        for bin_idx in range(n_bins):
            if not bins[bin_idx]["predicted"]:
                continue
            
            avg_predicted = sum(bins[bin_idx]["predicted"]) / len(bins[bin_idx]["predicted"])
            avg_actual = sum(bins[bin_idx]["actual"]) / len(bins[bin_idx]["actual"])
            
            curve.append((avg_predicted, avg_actual))
        
        return curve
    
    def get_settled_summary(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        market_type: Optional[str] = None
    ) -> Dict[str, any]:
        """Get summary of settled predictions.
        
        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
            market_type: Optional market type filter
        
        Returns:
            Dict with settlement metrics
        """
        # Get settled predictions from persistence layer
        if self.persistence_service:
            from app.database.models import PredictionVersionDB
            
            query = self.persistence_service.session.query(PredictionVersionDB).filter(
                PredictionVersionDB.actual_result.isnot(None)
            )
            
            if start_date:
                query = query.filter(PredictionVersionDB.settled_at >= start_date)
            
            if end_date:
                query = query.filter(PredictionVersionDB.settled_at <= end_date)
            
            if market_type:
                query = query.filter(
                    PredictionVersionDB.selected_market.ilike(f'%{market_type.upper()}%')
                )
            
            settled_versions = query.all()
        else:
            # Fallback to memory (not implemented in base TrackRecordManager)
            settled_versions = []
        
        if not settled_versions:
            return {
                'total_predictions': 0,
                'settled_predictions': 0,
                'wins': 0,
                'losses': 0,
                'voids': 0,
                'win_rate': 0.0,
                'roi': 0.0,
                'total_profit_loss': 0.0,
                'average_odds': 0.0,
                'average_confidence': 0.0,
                'average_probability': 0.0
            }
        
        # Calculate metrics
        total = len(settled_versions)
        wins = sum(1 for v in settled_versions if v.actual_result == 'WIN')
        losses = sum(1 for v in settled_versions if v.actual_result == 'LOSS')
        voids = sum(1 for v in settled_versions if v.actual_result == 'VOID')
        
        # Win rate (exclude voids)
        non_void = wins + losses
        win_rate = wins / non_void if non_void > 0 else 0.0
        
        # Profit/loss
        total_pl = sum(v.profit_loss for v in settled_versions if v.profit_loss is not None)
        total_stake = sum(1.0 for v in settled_versions if v.actual_result in ('WIN', 'LOSS'))
        roi = total_pl / total_stake if total_stake > 0 else 0.0
        
        # Averages
        odds_list = [v.selection_odds for v in settled_versions if v.selection_odds is not None]
        avg_odds = sum(odds_list) / len(odds_list) if odds_list else 0.0
        
        conf_list = [v.selection_confidence for v in settled_versions if v.selection_confidence is not None]
        avg_confidence = sum(conf_list) / len(conf_list) if conf_list else 0.0
        
        prob_list = [v.selection_probability for v in settled_versions if v.selection_probability is not None]
        avg_probability = sum(prob_list) / len(prob_list) if prob_list else 0.0
        
        return {
            'total_predictions': total,
            'settled_predictions': total,
            'wins': wins,
            'losses': losses,
            'voids': voids,
            'win_rate': win_rate,
            'roi': roi,
            'total_profit_loss': total_pl,
            'average_odds': avg_odds,
            'average_confidence': avg_confidence,
            'average_probability': avg_probability
        }

    def get_market_performance(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, any]]:
        """Get performance breakdown by market type.
        
        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
        
        Returns:
            List of per-market performance dicts
        """
        if not self.persistence_service:
            return []
        
        from app.database.models import PredictionVersionDB
        from sqlalchemy import func
        import sqlalchemy as sa
        
        query = self.persistence_service.session.query(
            PredictionVersionDB.selected_market,
            func.count(PredictionVersionDB.id).label('total'),
            func.sum(
                sa.case((PredictionVersionDB.actual_result == 'WIN', 1), else_=0)
            ).label('wins'),
            func.sum(
                sa.case((PredictionVersionDB.actual_result == 'LOSS', 1), else_=0)
            ).label('losses'),
            func.sum(
                sa.case((PredictionVersionDB.actual_result == 'VOID', 1), else_=0)
            ).label('voids'),
            func.sum(PredictionVersionDB.profit_loss).label('total_pl'),
            func.avg(PredictionVersionDB.selection_odds).label('avg_odds'),
            func.avg(PredictionVersionDB.selection_confidence).label('avg_confidence'),
        ).filter(
            PredictionVersionDB.actual_result.isnot(None),
            PredictionVersionDB.selected_market.isnot(None)
        )
        
        if start_date:
            query = query.filter(PredictionVersionDB.settled_at >= start_date)
        
        if end_date:
            query = query.filter(PredictionVersionDB.settled_at <= end_date)
        
        query = query.group_by(PredictionVersionDB.selected_market)
        
        results = query.all()
        
        performance = []
        for row in results:
            non_void = (row.wins or 0) + (row.losses or 0)
            win_rate = (row.wins or 0) / non_void if non_void > 0 else 0.0
            
            total_stake = non_void  # 1 unit per bet
            roi = (row.total_pl or 0.0) / total_stake if total_stake > 0 else 0.0
            
            performance.append({
                'market_type': row.selected_market,
                'sample_size': row.total,
                'wins': row.wins or 0,
                'losses': row.losses or 0,
                'voids': row.voids or 0,
                'win_rate': win_rate,
                'roi': roi,
                'total_profit_loss': row.total_pl or 0.0,
                'average_odds': row.avg_odds or 0.0,
                'average_confidence': row.avg_confidence or 0.0,
            })
        
        return performance

