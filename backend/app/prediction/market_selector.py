"""Smart Market Selector for TUTAR X canonical pipeline.

Evaluates all available betting markets and selects the best tip or issues a PASS decision.

This module is the authoritative market selection component in the canonical flow:
Match → Feature Snapshot → ModelOrchestrator → Ensemble → Calibration → Confidence
→ Market Intelligence → **Smart Market Selector** → Best Tip / PASS → Prediction → AnalysisContext → API

Selection criteria:
- Probability threshold (model conviction)
- Confidence threshold (overall confidence)
- Edge threshold (value over bookmaker odds, when available)
- Risk level (LOW/MEDIUM/HIGH based on confidence + agreement + data quality)
- Selection score (weighted combination of probability, confidence, agreement, quality, edge)

When no market qualifies, issues a PASS with explicit reasoning.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Any, List

from app.prediction.market_derivation import MarketProbabilities
from app.prediction.confidence_engine import ConfidenceAssessment
from app.prediction.uncertainty_engine import UncertaintyLevel  # NEW: Group 5 - For uncertainty level checks
from app.services.odds_service import OddsService, ValueAssessment, MarketOdds, MODEL_MARKET_CONFLICT  # NEW: İddaa integration


# Markets whose probabilities come from the same model quantity. A conflict on
# one member means the shared quantity is suspect, so the whole family is
# treated as conflicted (double chance = sums of 1X2; totals, BTTS and team
# totals = one goal distribution).
MATCH_RESULT_FAMILY_MARKETS = frozenset({
    'HOME_WIN', 'DRAW', 'AWAY_WIN', 'HOME_OR_DRAW', 'DRAW_OR_AWAY', 'HOME_OR_AWAY',
})
GOALS_FAMILY_PREFIXES = ('OVER_', 'UNDER_', 'BTTS_', 'HOME_OVER_', 'AWAY_OVER_')


def is_trivial_without_odds(candidate: Dict[str, Any]) -> bool:
    """Team-goal totals (e.g. "X scores at least once") and 0.5 goal lines are
    near-certain trivia; without a bookmaker price they are not offered as the pick."""
    if candidate.get('bookmaker_odds'):
        return False
    market = str(candidate.get('market') or '')
    return market.startswith(('HOME_OVER_', 'AWAY_OVER_')) or market.endswith('_0_5')


def market_family(market: str) -> Optional[str]:
    """Family of correlated markets for ``market``, or None (e.g. shot markets)."""
    if market in MATCH_RESULT_FAMILY_MARKETS:
        return 'match_result'
    if market.startswith(GOALS_FAMILY_PREFIXES):
        return 'goals'
    return None


def propagate_family_conflicts(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mark every member of a family that has a model-market conflict as conflicted.

    Without this a derived market (e.g. HOME_OR_AWAY = HOME_WIN + AWAY_WIN)
    can stay under the per-outcome guard and be selected although it rests on
    a conflicting probability. Members marked here carry
    ``family_conflict=True``; their own edge/EV numbers are left untouched.
    """
    conflicted = {
        market_family(c['market']) for c in candidates
        if c.get('value_classification') == MODEL_MARKET_CONFLICT
    }
    conflicted.discard(None)
    for c in candidates:
        if (
            c.get('value_classification') != MODEL_MARKET_CONFLICT
            and market_family(c['market']) in conflicted
        ):
            c['value_classification'] = MODEL_MARKET_CONFLICT
            c['family_conflict'] = True
    return candidates



@dataclass
class CandidateEvaluation:
    """Detailed evaluation of a market candidate for debugging/analysis."""
    
    market: str
    selection: str
    
    # Probabilities
    model_probability: float
    calibrated_probability: float  # Same as model_probability after calibration
    implied_probability: Optional[float]
    
    # Odds
    fair_odds: float
    bookmaker_odds: Optional[float]
    
    # Value metrics
    edge: Optional[float]
    expected_value: Optional[float]
    value_classification: str
    
    # Reliability components
    confidence: float
    model_agreement: float
    data_quality: float
    uncertainty: Optional[float]
    
    # Scoring breakdown
    base_score: float              # From confidence + agreement + quality
    probability_contribution: float  # Contribution from probability
    value_contribution: float        # Contribution from odds/value
    high_base_rate_penalty: float    # Penalty if applicable (1.0 = no penalty)
    selection_score: float           # Final composite score
    
    # Decision
    qualified: bool
    rejection_reason: Optional[str]
    selection_reason: Optional[str]


@dataclass
class BestTip:
    """Best market selection with full analysis."""
    
    match_id: str
    market: str          # e.g. "HOME_WIN", "OVER_2_5", "BTTS_YES"
    selection: str       # Human-readable selection text
    probability: float   # Calibrated model probability
    confidence: float    # Overall confidence score 0.0-1.0
    model_agreement: float  # Agreement between models 0.0-1.0
    data_quality: float  # Data quality score 0.0-1.0
    edge: Optional[float]          # Edge over bookmaker odds (None when no odds)
    fair_odds: float               # Fair odds from model probability
    bookmaker_odds: Optional[float]  # Bookmaker odds (None when unavailable)
    odds_movement: Optional[str]   # "rising", "falling", "stable" or None
    value_classification: str      # "STRONG_VALUE", "VALUE", "NEUTRAL", "NEGATIVE_VALUE", "NO_ODDS"
    risk_level: str                # "LOW", "MEDIUM", "HIGH"
    selection_score: float         # Overall selection score 0.0-1.0
    selector_reason: str           # Why this market was selected
    timestamp: datetime
    pipeline_version: str
    
    # NEW: Expected value for value assessment
    expected_value: Optional[float] = None  # EV percentage (e.g., 0.08 = 8% EV)
    
    # NEW: Candidate evaluations for debugging
    all_candidates: Optional[List[CandidateEvaluation]] = None


@dataclass
class PassDecision:
    """Decision to pass on a match (no qualifying market)."""
    
    match_id: str
    pass_reason: str   # "insufficient_data", "weak_agreement", "poor_calibration",
                       # "negative_value", "insufficient_value", "no_qualifying_market", 
                       # "high_uncertainty"
    evaluated_markets_count: int
    best_market_details: Optional[Dict[str, Any]]  # Details of closest market that didn't qualify
    timestamp: datetime
    pipeline_version: str
    
    # NEW: All evaluated candidates for analysis
    all_candidates: Optional[List[CandidateEvaluation]] = None


class SmartMarketSelector:
    """Smart market selector for the TUTAR X canonical pipeline.
    
    Evaluates all available markets from MarketProbabilities and selects the best tip
    based on probability, confidence, edge, and risk assessment.
    
    Issues a PASS decision when no market meets the qualification criteria.
    """
    
    def __init__(
        self,
        min_confidence: float = 0.4,
        min_probability: float = 0.5,
        min_edge: float = 0.0,
        max_risk_level: str = "HIGH",
        max_uncertainty: float = 0.7  # NEW: Group 5 - reject if uncertainty > threshold
    ):
        """Initialize smart market selector.
        
        Args:
            min_confidence: Minimum confidence threshold [0, 1]
            min_probability: Minimum probability threshold [0, 1]
            min_edge: Minimum edge threshold (when odds available)
            max_risk_level: Maximum acceptable risk level ("LOW", "MEDIUM", "HIGH")
            max_uncertainty: Maximum uncertainty threshold [0, 1] (Group 5)
        """
        self.min_confidence = min_confidence
        self.min_probability = min_probability
        self.min_edge = min_edge
        self.max_risk_level = max_risk_level
        self.max_uncertainty = max_uncertainty
    
    def evaluate_and_select(
        self,
        market_probs: MarketProbabilities,
        confidence_assessment: ConfidenceAssessment,
        odds_data: Optional[Dict[str, float]] = None,
        pipeline_version: str = "1.0.0",
        uncertainty_assessment=None,  # NEW: Group 5 - Optional[UncertaintyAssessment]
        model_disagreement=None,       # NEW: Group 5 - Optional[ModelDisagreementResult]
        shot_market_predictions=None,  # NEW: FEAT-003 - Optional[Dict[ShotMarketType, List[ShotMarketPrediction]]]
        home_team_name: Optional[str] = None,  # NEW: FEAT-003 - For readable market names
        away_team_name: Optional[str] = None,   # NEW: FEAT-003 - For readable market names
        match_id: Optional[str] = None  # NEW: Pass actual match ID instead of using 'unknown'
    ):
        """Evaluate all available markets and select the best tip or issue a PASS.
        
        Args:
            market_probs: MarketProbabilities from market_derivation
            confidence_assessment: ConfidenceAssessment from confidence_engine
            odds_data: Optional dict mapping market_key -> bookmaker_odds
            pipeline_version: Pipeline version for tracking
            uncertainty_assessment: Optional UncertaintyAssessment (Group 5)
            model_disagreement: Optional ModelDisagreementResult (Group 5)
            shot_market_predictions: Optional shot market predictions (Group 5)
            
        Returns:
            BestTip if a qualifying market is found, PassDecision otherwise
        """
        # Use provided match_id or fallback to 'unknown'
        actual_match_id = match_id or getattr(market_probs, 'match_id', 'unknown')
        
        # Extract confidence components
        overall_confidence = confidence_assessment.overall_confidence
        model_agreement = confidence_assessment.components.model_agreement
        data_quality = confidence_assessment.components.data_quality
        
        # Build candidate markets (1X2, BTTS, goals)
        candidates = self._build_candidates(
            market_probs=market_probs,
            overall_confidence=overall_confidence,
            model_agreement=model_agreement,
            data_quality=data_quality,
            odds_data=odds_data
        )
        
        # Add shot market candidates if available
        if shot_market_predictions:
            shot_candidates = self._build_shot_market_candidates(
                shot_market_predictions=shot_market_predictions,
                overall_confidence=overall_confidence,
                model_agreement=model_agreement,
                data_quality=data_quality,
                home_team_name=home_team_name,
                away_team_name=away_team_name
            )
            candidates.extend(shot_candidates)

        candidates = [c for c in candidates if not is_trivial_without_odds(c)]
        
        if not candidates:
            return PassDecision(
                match_id=actual_match_id,
                pass_reason="insufficient_data",
                evaluated_markets_count=0,
                best_market_details=None,
                timestamp=datetime.utcnow(),
                pipeline_version=pipeline_version
            )
        
        # Apply filters
        # NEW: If odds_data exists, require positive EV for selection
        require_positive_ev = odds_data is not None and len(odds_data) > 0
        
        qualifying = self._filter_candidates(
            candidates=candidates,
            min_confidence=self.min_confidence,
            min_probability=self.min_probability,
            min_edge=self.min_edge,
            max_risk_level=self.max_risk_level,
            uncertainty_assessment=uncertainty_assessment,  # NEW: Group 5
            max_uncertainty=self.max_uncertainty,  # NEW: Group 5
            require_positive_ev_when_odds_exist=require_positive_ev  # NEW: Value requirement
        )
        
        if not qualifying:
            # Determine pass reason
            pass_reason = self._determine_pass_reason(
                candidates=candidates,
                min_confidence=self.min_confidence,
                min_probability=self.min_probability,
                min_edge=self.min_edge,
                uncertainty_assessment=uncertainty_assessment  # NEW: Group 5
            )
            
            # Find best candidate (highest selection_score before filtering)
            best_candidate = max(candidates, key=lambda c: c['selection_score'])
            best_market_details = {
                'market': best_candidate['market'],
                'selection': best_candidate['selection'],
                'probability': best_candidate['probability'],
                'confidence': best_candidate['confidence'],
                'selection_score': best_candidate['selection_score'],
                'risk_level': best_candidate['risk_level'],
                'value_classification': best_candidate['value_classification']
            }
            
            return PassDecision(
                match_id=actual_match_id,
                pass_reason=pass_reason,
                evaluated_markets_count=len(candidates),
                best_market_details=best_market_details,
                timestamp=datetime.utcnow(),
                pipeline_version=pipeline_version
            )
        
        # Sort by selection_score (descending), then confidence, then probability
        qualifying.sort(
            key=lambda c: (c['selection_score'], c['confidence'], c['probability']),
            reverse=True
        )
        
        # Select best
        best = qualifying[0]
        
        # Build selector reason (enhanced with value info)
        selector_reason_parts = [
            f"Selected {best['market']}: probability={best['probability']:.2f}",
            f"confidence={best['confidence']:.2f}",
            f"model_agreement={best['model_agreement']:.2f}",
            f"risk={best['risk_level']}",
            f"value={best['value_classification']}"
        ]
        
        # Add EV if available
        if best.get('expected_value') is not None:
            ev_pct = best['expected_value'] * 100
            selector_reason_parts.append(f"EV={ev_pct:+.1f}%")
        
        selector_reason = ", ".join(selector_reason_parts)
        
        return BestTip(
            match_id=actual_match_id,
            market=best['market'],
            selection=best['selection'],
            probability=best['probability'],
            confidence=best['confidence'],
            model_agreement=best['model_agreement'],
            data_quality=best['data_quality'],
            edge=best['edge'],
            fair_odds=best['fair_odds'],
            bookmaker_odds=best['bookmaker_odds'],
            odds_movement=best['odds_movement'],
            value_classification=best['value_classification'],
            risk_level=best['risk_level'],
            selection_score=best['selection_score'],
            selector_reason=selector_reason,
            expected_value=best.get('expected_value'),  # NEW: Include EV
            timestamp=datetime.utcnow(),
            pipeline_version=pipeline_version,
            all_candidates=None  # TODO: Add candidate diagnostics when needed
        )
    
    def _build_candidates(
        self,
        market_probs: MarketProbabilities,
        overall_confidence: float,
        model_agreement: float,
        data_quality: float,
        odds_data: Optional[Dict[str, float]]
    ):
        """Build list of candidate markets with all analysis fields.
        
        Returns:
            List of candidate dicts with all fields computed
        """
        candidates = []
        
        # 1X2 markets
        for market_key, prob, selection in [
            ('HOME_WIN', market_probs.home_win, 'Home Win'),
            ('DRAW', market_probs.draw, 'Draw'),
            ('AWAY_WIN', market_probs.away_win, 'Away Win')
        ]:
            if prob and prob > 0:
                candidate = self._build_candidate(
                    market=market_key,
                    selection=selection,
                    probability=prob,
                    confidence=overall_confidence,
                    model_agreement=model_agreement,
                    data_quality=data_quality,
                    odds_data=odds_data
                )
                candidates.append(candidate)
        
        # Double chance markets
        for market_key, prob, selection in [
            ('HOME_OR_DRAW', market_probs.home_or_draw, 'Home or Draw'),
            ('DRAW_OR_AWAY', market_probs.draw_or_away, 'Draw or Away'),
            ('HOME_OR_AWAY', market_probs.home_or_away, 'Home or Away')
        ]:
            if prob and prob > 0:
                candidate = self._build_candidate(
                    market=market_key,
                    selection=selection,
                    probability=prob,
                    confidence=overall_confidence,
                    model_agreement=model_agreement,
                    data_quality=data_quality,
                    odds_data=odds_data
                )
                candidates.append(candidate)
        
        # Over/Under markets
        for line, (over_prob, under_prob) in market_probs.over_under.items():
            if over_prob and over_prob > 0:
                candidate = self._build_candidate(
                    market=f'OVER_{line}'.replace('.', '_'),
                    selection=f'Over {line} Goals',
                    probability=over_prob,
                    confidence=overall_confidence,
                    model_agreement=model_agreement,
                    data_quality=data_quality,
                    odds_data=odds_data
                )
                candidates.append(candidate)
            
            if under_prob and under_prob > 0:
                candidate = self._build_candidate(
                    market=f'UNDER_{line}'.replace('.', '_'),
                    selection=f'Under {line} Goals',
                    probability=under_prob,
                    confidence=overall_confidence,
                    model_agreement=model_agreement,
                    data_quality=data_quality,
                    odds_data=odds_data
                )
                candidates.append(candidate)
        
        # BTTS markets
        if market_probs.btts_yes and market_probs.btts_yes > 0:
            candidate = self._build_candidate(
                market='BTTS_YES',
                selection='Both Teams to Score',
                probability=market_probs.btts_yes,
                confidence=overall_confidence,
                model_agreement=model_agreement,
                data_quality=data_quality,
                odds_data=odds_data
            )
            candidates.append(candidate)
        
        if market_probs.btts_no and market_probs.btts_no > 0:
            candidate = self._build_candidate(
                market='BTTS_NO',
                selection='Both Teams NOT to Score',
                probability=market_probs.btts_no,
                confidence=overall_confidence,
                model_agreement=model_agreement,
                data_quality=data_quality,
                odds_data=odds_data
            )
            candidates.append(candidate)
        
        # Team totals
        for line, prob in market_probs.home_team_over.items():
            if prob and prob > 0:
                candidate = self._build_candidate(
                    market=f'HOME_OVER_{line}'.replace('.', '_'),
                    selection=f'Home Over {line} Goals',
                    probability=prob,
                    confidence=overall_confidence,
                    model_agreement=model_agreement,
                    data_quality=data_quality,
                    odds_data=odds_data
                )
                candidates.append(candidate)
        
        for line, prob in market_probs.away_team_over.items():
            if prob and prob > 0:
                candidate = self._build_candidate(
                    market=f'AWAY_OVER_{line}'.replace('.', '_'),
                    selection=f'Away Over {line} Goals',
                    probability=prob,
                    confidence=overall_confidence,
                    model_agreement=model_agreement,
                    data_quality=data_quality,
                    odds_data=odds_data
                )
                candidates.append(candidate)
        
        return propagate_family_conflicts(candidates)
    
    def _build_candidate(
        self,
        market: str,
        selection: str,
        probability: float,
        confidence: float,
        model_agreement: float,
        data_quality: float,
        odds_data: Optional[Dict[str, float]]
    ) -> Dict[str, Any]:
        """Build a single candidate market with value-aware scoring.
        
        NEW SCORING FORMULA (fixes OVER_0.5 dominance):
        - Base score from reliability (confidence + agreement + quality)
        - Probability contribution (reduced from 35% to dynamic)
        - Value contribution (based on EV when odds available)
        - High base-rate protection (penalties for trivial markets without value)
        
        Returns:
            Dict containing all candidate fields
        """
        # Calculate fair odds
        fair_odds = 1.0 / probability if probability > 0 else 0.0
        
        # Get odds and calculate value
        market_odds = OddsService.get_market_odds(
            odds_data=odds_data,
            market=market
        )
        
        value_assessment = ValueAssessment.from_market_odds(
            market=market,
            model_probability=probability,
            market_odds=market_odds
        )
        
        # Extract value metrics
        bookmaker_odds = value_assessment.bookmaker_odds
        edge = value_assessment.edge
        value_classification = value_assessment.value_classification
        
        # NEW SCORING FORMULA
        # 1. Base score from reliability/confidence (NOT probability)
        base_score = (
            0.40 * confidence +
            0.30 * model_agreement +
            0.30 * data_quality
        )
        
        # 2. Probability contribution (REDUCED and CAPPED)
        # Use Kelly-like criterion: weight by probability but cap contribution
        # This prevents OVER_0.5 from dominating purely on probability
        probability_contribution = min(probability * 0.5, 0.35)  # Max 0.35
        
        # 3. Value contribution (NEW - replaces tiny edge bonus)
        value_contribution = OddsService.calculate_value_contribution(
            value_assessment=value_assessment,
            use_conservative_thresholds=True  # Require meaningful EV
        )
        
        # 4. Composite selection score
        selection_score = base_score + probability_contribution + value_contribution
        
        # 5. High base-rate protection (NEW)
        # Apply penalty to trivial high-probability markets without value
        selection_score_with_protection = OddsService.apply_high_base_rate_protection(
            market=market,
            probability=probability,
            value_assessment=value_assessment,
            base_selection_score=selection_score
        )
        
        high_base_rate_penalty = selection_score_with_protection / selection_score if selection_score > 0 else 1.0
        selection_score = selection_score_with_protection
        
        # Risk level (unchanged)
        if confidence >= 0.7 and model_agreement >= 0.8 and data_quality >= 0.7:
            risk_level = "LOW"
        elif confidence >= 0.5 and model_agreement >= 0.6 and data_quality >= 0.5:
            risk_level = "MEDIUM"
        else:
            risk_level = "HIGH"
        
        return {
            'market': market,
            'selection': selection,
            'probability': probability,
            'confidence': confidence,
            'model_agreement': model_agreement,
            'data_quality': data_quality,
            'fair_odds': fair_odds,
            'bookmaker_odds': bookmaker_odds,
            'edge': edge,
            'expected_value': value_assessment.expected_value,
            'value_classification': value_classification,
            'risk_level': risk_level,
            'selection_score': selection_score,
            'odds_movement': None,  # Not implemented yet
            
            # NEW: Scoring breakdown for diagnostics
            'base_score': base_score,
            'probability_contribution': probability_contribution,
            'value_contribution': value_contribution,
            'high_base_rate_penalty': high_base_rate_penalty
        }
    
    def _build_shot_market_candidates(
        self,
        shot_market_predictions: Dict,  # Dict[ShotMarketType, List[ShotMarketPrediction]]
        overall_confidence: float,
        model_agreement: float,
        data_quality: float,
        home_team_name: Optional[str] = None,
        away_team_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Build shot market candidates from shot market predictions.
        
        Shot markets are evaluated using the same scoring logic as traditional markets,
        considering probability, confidence, data quality, uncertainty, and threshold stability.
        
        Weak shot markets (low confidence, high uncertainty, insufficient data) will fail
        qualification and trigger PASS decision.
        
        Args:
            shot_market_predictions: Dict mapping ShotMarketType -> List[ShotMarketPrediction]
            overall_confidence: Overall confidence from confidence assessment
            model_agreement: Model agreement score
            data_quality: Data quality score
            home_team_name: Home team name for readable market names
            away_team_name: Away team name for readable market names
            
        Returns:
            List of candidate dicts with all fields computed
        """
        from app.prediction.interfaces import ShotMarketType
        
        candidates = []
        
        for market_type, predictions in shot_market_predictions.items():
            for prediction in predictions:
                # Skip unavailable predictions
                if not prediction.available:
                    continue
                
                # Determine team name for market label
                if prediction.team_id == "total":
                    team_label = "Total"
                elif prediction.team_id and home_team_name and prediction.team_id in [home_team_name, "home"]:
                    team_label = home_team_name
                elif prediction.team_id and away_team_name and prediction.team_id in [away_team_name, "away"]:
                    team_label = away_team_name
                else:
                    team_label = prediction.team_id  # Fallback to ID
                
                # Determine market suffix
                if market_type == ShotMarketType.TEAM_SHOTS:
                    market_suffix = "Shots"
                elif market_type == ShotMarketType.TEAM_SHOTS_ON_TARGET:
                    market_suffix = "Shots on Target"
                elif market_type == ShotMarketType.TOTAL_SHOTS:
                    market_suffix = "Shots"
                elif market_type == ShotMarketType.TOTAL_SHOTS_ON_TARGET:
                    market_suffix = "Shots on Target"
                else:
                    market_suffix = str(market_type.value)
                
                # Evaluate each threshold as a candidate
                for threshold in prediction.thresholds:
                    # Build market key
                    market_key = f"SHOT_{market_type.value.upper()}_{prediction.team_id}_{threshold.threshold}PLUS"
                    
                    # Build selection text
                    selection_text = f"{team_label} {threshold.threshold}+ {market_suffix}"
                    
                    # Calculate shot-market-specific confidence
                    # Factors: base confidence, data quality, sample size, threshold stability (variance)
                    shot_confidence = self._calculate_shot_market_confidence(
                        base_confidence=overall_confidence,
                        data_quality=threshold.data_quality,
                        sample_size=prediction.sample_size,
                        variance=threshold.variance,
                        expected_value=threshold.expected_value
                    )
                    
                    # Build candidate using standard logic
                    candidate = self._build_candidate(
                        market=market_key,
                        selection=selection_text,
                        probability=threshold.over_probability,
                        confidence=shot_confidence,  # Use shot-specific confidence
                        model_agreement=model_agreement,
                        data_quality=threshold.data_quality,  # Use threshold-specific data quality
                        odds_data=None  # Shot markets typically don't have bookmaker odds
                    )
                    
                    # Mark as shot market for debugging
                    candidate['market_category'] = 'shot'
                    candidate['shot_sample_size'] = prediction.sample_size
                    candidate['shot_variance'] = threshold.variance
                    candidate['shot_expected_value'] = threshold.expected_value
                    
                    candidates.append(candidate)
        
        return candidates
    
    def _calculate_shot_market_confidence(
        self,
        base_confidence: float,
        data_quality: float,
        sample_size: int,
        variance: Optional[float],
        expected_value: Optional[float]
    ) -> float:
        """Calculate confidence for shot market predictions.
        
        Shot market confidence considers:
        - Base confidence from overall pipeline
        - Data quality from shot production
        - Sample size (historical matches with shot data)
        - Threshold stability (penalize high variance)
        
        Args:
            base_confidence: Overall confidence from pipeline
            data_quality: Shot-specific data quality score
            sample_size: Number of historical matches
            variance: Shot distribution variance
            expected_value: Expected shot count
            
        Returns:
            Shot market confidence score [0.0, 1.0]
        """
        # Start with base confidence
        confidence = base_confidence
        
        # Weight by shot-specific data quality
        confidence = (0.6 * confidence) + (0.4 * data_quality)
        
        # Sample size penalty
        if sample_size < 5:
            confidence *= 0.5  # Heavy penalty
        elif sample_size < 10:
            confidence *= 0.7  # Moderate penalty
        elif sample_size < 15:
            confidence *= 0.85  # Light penalty
        # else: no penalty
        
        # Variance/stability penalty (high variance = less reliable)
        if variance is not None and expected_value is not None and expected_value > 0:
            coefficient_of_variation = (variance ** 0.5) / expected_value
            if coefficient_of_variation > 0.8:
                confidence *= 0.8  # High uncertainty
            elif coefficient_of_variation > 0.6:
                confidence *= 0.9  # Moderate uncertainty
            # else: stable, no penalty
        
        return max(0.0, min(1.0, confidence))
    
    def _filter_candidates(
        self,
        candidates,
        min_confidence: float,
        min_probability: float,
        min_edge: float,
        max_risk_level: str,
        uncertainty_assessment=None,  # NEW: Group 5 - Optional[UncertaintyAssessment]
        max_uncertainty: float = 0.7,  # NEW: Group 5
        require_positive_ev_when_odds_exist: bool = False  # NEW: Strict value requirement
    ):
        """Filter candidates by thresholds.
        
        Returns:
            List of qualifying candidates
        """
        risk_order = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}
        max_risk_value = risk_order.get(max_risk_level, 2)
        
        # NEW: Group 5 - Check for high uncertainty (auto-PASS)
        # Simplified to single numeric threshold check for predictable behavior
        if uncertainty_assessment is not None:
            if hasattr(uncertainty_assessment, 'overall_uncertainty'):
                if uncertainty_assessment.overall_uncertainty >= max_uncertainty:
                    # Force PASS when uncertainty exceeds threshold
                    return []
        
        # NEW: Check if ANY candidate has odds with positive EV
        # If odds exist but all show negative/insufficient EV, enforce strict filtering
        candidates_with_odds = [c for c in candidates if c.get('expected_value') is not None]
        if candidates_with_odds and require_positive_ev_when_odds_exist:
            # EV from model-market conflicts is not credible value
            credible_evs = [
                c['expected_value'] for c in candidates_with_odds
                if c.get('value_classification') != MODEL_MARKET_CONFLICT
            ]
            max_ev = max(credible_evs) if credible_evs else float("-inf")
            if max_ev < 0.03:  # No market has credible EV >= 3%
                # Force PASS - insufficient value across all markets with odds
                return []
        
        qualifying = []
        for c in candidates:
            # Check confidence
            if c['confidence'] < min_confidence:
                continue
            
            # Check probability
            if c['probability'] < min_probability:
                continue
            
            # Check edge (only if edge is available)
            if c['edge'] is not None and c['edge'] < min_edge:
                continue

            # Never recommend a market where model and bookmakers disagree
            # beyond credibility (see odds_service.MAX_CREDIBLE_EDGE)
            if c.get('value_classification') == MODEL_MARKET_CONFLICT:
                continue

            # Check risk level
            candidate_risk_value = risk_order.get(c['risk_level'], 2)
            if candidate_risk_value > max_risk_value:
                continue
            
            qualifying.append(c)
        
        return qualifying
    
    def _determine_pass_reason(
        self,
        candidates,
        min_confidence: float,
        min_probability: float,
        min_edge: float,
        uncertainty_assessment=None  # NEW: Group 5
    ) -> str:
        """Determine the reason for passing on this match.
        
        Returns:
            Pass reason string
        """
        # NEW: Group 5 - Check for high uncertainty first
        if uncertainty_assessment is not None:
            if hasattr(uncertainty_assessment, 'overall_uncertainty'):
                if uncertainty_assessment.overall_uncertainty >= self.max_uncertainty:
                    return "high_uncertainty"
        
        if not candidates:
            return "insufficient_data"
        
        # Check if all below confidence
        all_below_confidence = all(c['confidence'] < min_confidence for c in candidates)
        if all_below_confidence:
            return "poor_calibration"
        
        # Check if all below probability
        all_below_probability = all(c['probability'] < min_probability for c in candidates)
        if all_below_probability:
            return "weak_agreement"
        
        # NEW: Check if all have insufficient value (when odds available)
        candidates_with_ev = [c for c in candidates if c.get('expected_value') is not None]
        if candidates_with_ev and any(
            c.get('value_classification') == MODEL_MARKET_CONFLICT for c in candidates_with_ev
        ) and all(
            c.get('expected_value', 0) < 0.03 or c.get('value_classification') == MODEL_MARKET_CONFLICT
            for c in candidates_with_ev
        ):
            # The only apparent value comes from model-market conflicts
            return "model_market_conflict"
        if candidates_with_ev:
            all_insufficient_value = all(
                c.get('expected_value', 0) < 0.03  # Less than 3% EV
                for c in candidates_with_ev
            )
            if all_insufficient_value:
                return "insufficient_value"
        
        # Check if all have negative edge
        candidates_with_edge = [c for c in candidates if c['edge'] is not None]
        if candidates_with_edge and all(c['edge'] < min_edge for c in candidates_with_edge):
            return "negative_value"
        
        return "no_qualifying_market"
