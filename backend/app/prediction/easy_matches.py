"""Easy Match Detection System.

This module identifies matches where predictions have high confidence
based on multiple validated signals from the prediction system.

An "Easy Match" is defined by:
- Strong model consensus across multiple signals
- Sufficient data quality
- Statistical confidence thresholds
- Model agreement on outcome

This is NOT a subjective assessment. All scores are derived from
numerical calculations based on available statistical signals.

The Easy Match score ranges from 0-100 and is computed from:
- 1X2 probability confidence (dominant outcome probability)
- Over/Under confidence signals
- BTTS confidence
- Expected goals differential
- Data sufficiency indicators
- Model calibration quality (when available)

Missing or insufficient data results in explicit "unavailable" state.
The system never fabricates an Easy Match score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
import math


@dataclass
class EasyMatchSignal:
    """Individual signal contributing to Easy Match detection."""
    
    name: str
    """Signal name (e.g., '1x2_confidence', 'ou_confidence')."""
    
    value: float
    """Signal value (0-1 range typically)."""
    
    weight: float
    """Weight of this signal in overall score (0-1)."""
    
    available: bool = True
    """Whether this signal was available from data."""
    
    description: Optional[str] = None
    """Human-readable description of what this signal represents."""


@dataclass
class EasyMatchResult:
    """Result of Easy Match detection analysis.
    
    Combines multiple statistical signals to produce a confidence score
    indicating how "easy" a match is to predict based on available data.
    """
    
    match_id: str
    """Match identifier."""
    
    is_easy_match: bool
    """True if match exceeds Easy Match threshold."""
    
    confidence_score: float
    """Overall confidence score (0-100). 0 means insufficient data."""
    
    threshold: float
    """Threshold used for Easy Match determination."""
    
    signals: List[EasyMatchSignal]
    """Individual signals that contributed to the score."""
    
    dominant_outcome: Optional[str] = None
    """Predicted dominant outcome (e.g., 'home', 'draw', 'away', 'over_2.5')."""
    
    dominant_probability: Optional[float] = None
    """Probability of the dominant outcome."""
    
    reasons: List[str] = field(default_factory=list)
    """Structured reasons why this is/isn't an Easy Match."""
    
    warnings: List[str] = field(default_factory=list)
    """Warnings about data quality or missing signals."""
    
    data_sufficient: bool = True
    """Whether sufficient data was available for analysis."""
    
    @property
    def weighted_score(self) -> float:
        """Compute weighted score from available signals."""
        if not self.signals:
            return 0.0
        
        available_signals = [s for s in self.signals if s.available]
        if not available_signals:
            return 0.0
        
        total_weight = sum(s.weight for s in available_signals)
        if total_weight == 0:
            return 0.0
        
        weighted_sum = sum(s.value * s.weight for s in available_signals)
        return (weighted_sum / total_weight) * 100.0


@dataclass
class EasyMatchConfig:
    """Configuration for Easy Match detection."""
    
    easy_match_threshold: float = 65.0
    """Minimum confidence score to qualify as Easy Match (0-100)."""
    
    min_dominant_probability: float = 0.60
    """Minimum probability for dominant 1X2 outcome."""
    
    min_data_signals: int = 3
    """Minimum number of available signals required."""
    
    # Signal weights (must sum to reasonable total)
    weight_1x2_confidence: float = 0.35
    """Weight for 1X2 outcome confidence."""
    
    weight_goals_confidence: float = 0.25
    """Weight for goals market confidence (O/U)."""
    
    weight_btts_confidence: float = 0.15
    """Weight for BTTS confidence."""
    
    weight_xg_differential: float = 0.15
    """Weight for expected goals differential."""
    
    weight_data_quality: float = 0.10
    """Weight for data sufficiency/quality."""


class EasyMatchDetector:
    """Detects matches with high prediction confidence.
    
    Uses multiple statistical signals from the prediction system to
    compute a confidence score. All calculations are deterministic
    and based on available data.
    
    Usage:
        detector = EasyMatchDetector()
        result = detector.detect(
            match_id="m1",
            home_win_prob=0.75,
            draw_prob=0.15,
            away_win_prob=0.10,
            btts_prob=0.35,
            over_2_5_prob=0.68,
            home_xg=2.3,
            away_xg=0.9,
        )
        
        if result.is_easy_match:
            print(f"Easy Match! Score: {result.confidence_score:.1f}")
    """
    
    def __init__(self, config: Optional[EasyMatchConfig] = None):
        """Initialize Easy Match detector.
        
        Args:
            config: Configuration for detection thresholds and weights.
        """
        self.config = config or EasyMatchConfig()
    
    def detect(
        self,
        match_id: str,
        *,
        # 1X2 probabilities
        home_win_prob: Optional[float] = None,
        draw_prob: Optional[float] = None,
        away_win_prob: Optional[float] = None,
        # Calibrated 1X2 (if available)
        home_win_calibrated: Optional[float] = None,
        draw_calibrated: Optional[float] = None,
        away_win_calibrated: Optional[float] = None,
        # Goals markets
        btts_prob: Optional[float] = None,
        over_2_5_prob: Optional[float] = None,
        over_3_5_prob: Optional[float] = None,
        # Expected goals
        home_xg: Optional[float] = None,
        away_xg: Optional[float] = None,
        # Data quality indicators
        has_sufficient_historical_data: bool = True,
        model_agreement_score: Optional[float] = None,
    ) -> EasyMatchResult:
        """Detect if a match qualifies as an Easy Match.
        
        All probability arguments are optional. Signals are only computed
        when the relevant data is available.
        
        Args:
            match_id: Match identifier.
            home_win_prob: Home win probability (model or calibrated).
            draw_prob: Draw probability.
            away_win_prob: Away win probability.
            home_win_calibrated: Calibrated home win probability.
            draw_calibrated: Calibrated draw probability.
            away_win_calibrated: Calibrated away win probability.
            btts_prob: Both teams to score probability.
            over_2_5_prob: Over 2.5 goals probability.
            over_3_5_prob: Over 3.5 goals probability.
            home_xg: Home expected goals.
            away_xg: Away expected goals.
            has_sufficient_historical_data: Data quality flag.
            model_agreement_score: Agreement across models (0-1).
        
        Returns:
            EasyMatchResult with confidence score and analysis.
        """
        signals = []
        reasons = []
        warnings = []
        
        # Use calibrated probabilities if available, else model probabilities
        h_prob = home_win_calibrated if home_win_calibrated is not None else home_win_prob
        d_prob = draw_calibrated if draw_calibrated is not None else draw_prob
        a_prob = away_win_calibrated if away_win_calibrated is not None else away_win_prob
        
        # Signal 1: 1X2 Confidence
        dominant_outcome = None
        dominant_probability = None
        
        if all(p is not None for p in [h_prob, d_prob, a_prob]):
            max_prob = max(h_prob, d_prob, a_prob)
            
            if h_prob == max_prob:
                dominant_outcome = "home"
                dominant_probability = h_prob
            elif a_prob == max_prob:
                dominant_outcome = "away"
                dominant_probability = a_prob
            else:
                dominant_outcome = "draw"
                dominant_probability = d_prob
            
            # Confidence is based on how much the dominant outcome exceeds others
            # Use entropy-like measure: higher dominance = higher confidence
            confidence_1x2 = self._compute_outcome_confidence(h_prob, d_prob, a_prob)
            
            signals.append(EasyMatchSignal(
                name="1x2_confidence",
                value=confidence_1x2,
                weight=self.config.weight_1x2_confidence,
                available=True,
                description=f"{dominant_outcome.capitalize()} win dominance",
            ))
            
            if dominant_probability >= self.config.min_dominant_probability:
                reasons.append(
                    f"Strong {dominant_outcome} prediction ({dominant_probability:.1%})"
                )
            else:
                reasons.append(
                    f"Moderate {dominant_outcome} prediction ({dominant_probability:.1%})"
                )
        else:
            signals.append(EasyMatchSignal(
                name="1x2_confidence",
                value=0.0,
                weight=self.config.weight_1x2_confidence,
                available=False,
                description="1X2 probabilities not available",
            ))
            warnings.append("1X2 probabilities not available")
        
        # Signal 2: Goals Market Confidence
        if over_2_5_prob is not None:
            # Clear signal if probability is strongly above or below 0.5
            goals_confidence = abs(over_2_5_prob - 0.5) * 2  # 0-1 scale
            
            signals.append(EasyMatchSignal(
                name="goals_confidence",
                value=goals_confidence,
                weight=self.config.weight_goals_confidence,
                available=True,
                description=f"Over 2.5 goals: {over_2_5_prob:.1%}",
            ))
            
            if over_2_5_prob >= 0.65:
                reasons.append(f"High-scoring match expected (O2.5: {over_2_5_prob:.1%})")
            elif over_2_5_prob <= 0.35:
                reasons.append(f"Low-scoring match expected (O2.5: {over_2_5_prob:.1%})")
        else:
            signals.append(EasyMatchSignal(
                name="goals_confidence",
                value=0.0,
                weight=self.config.weight_goals_confidence,
                available=False,
                description="Goals market not available",
            ))
            warnings.append("Goals market (O/U 2.5) not available")
        
        # Signal 3: BTTS Confidence
        if btts_prob is not None:
            btts_confidence = abs(btts_prob - 0.5) * 2  # 0-1 scale
            
            signals.append(EasyMatchSignal(
                name="btts_confidence",
                value=btts_confidence,
                weight=self.config.weight_btts_confidence,
                available=True,
                description=f"BTTS: {btts_prob:.1%}",
            ))
            
            if btts_prob >= 0.65:
                reasons.append(f"Both teams likely to score ({btts_prob:.1%})")
            elif btts_prob <= 0.35:
                reasons.append(f"Clean sheet likely ({(1-btts_prob):.1%})")
        else:
            signals.append(EasyMatchSignal(
                name="btts_confidence",
                value=0.0,
                weight=self.config.weight_btts_confidence,
                available=False,
                description="BTTS not available",
            ))
        
        # Signal 4: xG Differential
        if home_xg is not None and away_xg is not None:
            xg_diff = abs(home_xg - away_xg)
            # Normalize: 0 diff = 0 confidence, 2+ diff = 1.0 confidence
            xg_confidence = min(xg_diff / 2.0, 1.0)
            
            signals.append(EasyMatchSignal(
                name="xg_differential",
                value=xg_confidence,
                weight=self.config.weight_xg_differential,
                available=True,
                description=f"xG differential: {xg_diff:.2f}",
            ))
            
            if xg_diff >= 1.0:
                reasons.append(f"Clear quality gap (xG diff: {xg_diff:.2f})")
        else:
            signals.append(EasyMatchSignal(
                name="xg_differential",
                value=0.0,
                weight=self.config.weight_xg_differential,
                available=False,
                description="Expected goals not available",
            ))
        
        # Signal 5: Data Quality
        data_quality_score = 1.0 if has_sufficient_historical_data else 0.3
        
        if model_agreement_score is not None:
            # Blend data sufficiency with model agreement
            data_quality_score = (data_quality_score + model_agreement_score) / 2.0
        
        signals.append(EasyMatchSignal(
            name="data_quality",
            value=data_quality_score,
            weight=self.config.weight_data_quality,
            available=True,
            description="Data sufficiency and model agreement",
        ))
        
        if not has_sufficient_historical_data:
            warnings.append("Limited historical data available")
        
        # Compute overall confidence score
        available_count = sum(1 for s in signals if s.available)
        data_sufficient = available_count >= self.config.min_data_signals
        
        if not data_sufficient:
            warnings.append(
                f"Insufficient signals ({available_count}/{self.config.min_data_signals} minimum)"
            )
            confidence_score = 0.0
        else:
            confidence_score = self._compute_weighted_score(signals)
        
        # Determine if this is an Easy Match
        is_easy_match = (
            data_sufficient and
            confidence_score >= self.config.easy_match_threshold
        )
        
        if is_easy_match:
            reasons.append(
                f"Confidence score {confidence_score:.1f} exceeds threshold {self.config.easy_match_threshold:.1f}"
            )
        elif data_sufficient:
            reasons.append(
                f"Confidence score {confidence_score:.1f} below threshold {self.config.easy_match_threshold:.1f}"
            )
        else:
            reasons.append("Insufficient data for Easy Match determination")
        
        return EasyMatchResult(
            match_id=match_id,
            is_easy_match=is_easy_match,
            confidence_score=confidence_score,
            threshold=self.config.easy_match_threshold,
            signals=signals,
            dominant_outcome=dominant_outcome,
            dominant_probability=dominant_probability,
            reasons=reasons,
            warnings=warnings,
            data_sufficient=data_sufficient,
        )
    
    def _compute_outcome_confidence(
        self,
        home_prob: float,
        draw_prob: float,
        away_prob: float,
    ) -> float:
        """Compute confidence based on outcome probability distribution.
        
        Uses a normalized entropy-like measure where higher dominance
        of one outcome produces higher confidence.
        
        Args:
            home_prob: Home win probability.
            draw_prob: Draw probability.
            away_prob: Away win probability.
        
        Returns:
            Confidence score (0-1).
        """
        max_prob = max(home_prob, draw_prob, away_prob)
        
        # Confidence increases with dominance of max probability
        # Simple linear scaling: 0.33 (equal) -> 0, 1.0 (certain) -> 1
        baseline = 1.0 / 3.0  # Equal probabilities
        confidence = (max_prob - baseline) / (1.0 - baseline)
        
        return max(0.0, min(1.0, confidence))
    
    def _compute_weighted_score(self, signals: List[EasyMatchSignal]) -> float:
        """Compute weighted confidence score from signals.
        
        Args:
            signals: List of signals with values and weights.
        
        Returns:
            Weighted score (0-100).
        """
        available_signals = [s for s in signals if s.available]
        if not available_signals:
            return 0.0
        
        total_weight = sum(s.weight for s in available_signals)
        if total_weight == 0:
            return 0.0
        
        weighted_sum = sum(s.value * s.weight for s in available_signals)
        normalized_score = (weighted_sum / total_weight) * 100.0
        
        return max(0.0, min(100.0, normalized_score))


# ============================================================================
# SMART MARKET SELECTOR - Value-based market selection
# ============================================================================

from enum import Enum
from typing import Dict, Any


class ValueStatus(str, Enum):
    """Value assessment status for a market."""
    POSITIVE_VALUE = "positive_value"  # EV > threshold
    NEUTRAL = "neutral"  # EV ≈ 0
    NEGATIVE_VALUE = "negative_value"  # EV < 0
    UNAVAILABLE = "unavailable"  # No bookmaker odds supplied


class CalibrationStatus(str, Enum):
    """Calibration status for probabilities."""
    FITTED = "fitted"  # Calibration model fitted and applied
    NOT_FITTED = "not_fitted"  # No calibration available
    INSUFFICIENT_DATA = "insufficient_data"  # Not enough data to calibrate


@dataclass
class MarketCandidate:
    """A candidate market for BEST TIP selection.
    
    Represents one possible betting market with all scoring components:
    - Probability assessment (model + calibrated)
    - Value assessment (fair odds, bookmaker odds, edge, EV)
    - Reliability assessment (historical performance)
    - Uncertainty assessment (model agreement, data quality)
    """
    
    # Market identification (required fields first)
    market_type: str
    """Market type: 'match_result', 'over_under', 'btts', 'shots', 'sot'."""
    
    market_label: str
    """Human-readable market label (e.g., 'Over 2.5 Goals', 'Home Win')."""
    
    outcome: str
    """Outcome within market: 'home', 'away', 'draw', 'over', 'under', 'yes', 'no'."""
    
    # Probability components (required)
    model_probability: float
    """Raw model probability (before calibration)."""
    
    # Optional fields with defaults
    threshold: Optional[float] = None
    """Numeric threshold for O/U markets (e.g., 2.5, 20.0 for shots)."""
    
    calibrated_probability: Optional[float] = None
    """Calibrated probability (if calibration available)."""
    
    calibration_status: CalibrationStatus = CalibrationStatus.NOT_FITTED
    """Status of calibration for this market."""
    
    # Value components (when bookmaker odds available)
    fair_odds: float = 0.0
    """Fair odds computed from calibrated/model probability."""
    
    bookmaker_odds: Optional[float] = None
    """Bookmaker decimal odds (if available)."""
    
    implied_probability: Optional[float] = None
    """Implied probability from bookmaker odds."""
    
    edge: Optional[float] = None
    """Edge: calibrated_prob - implied_prob. Positive = model favors."""
    
    expected_value: Optional[float] = None
    """Expected value: calibrated_prob * bookmaker_odds - 1."""
    
    value_status: ValueStatus = ValueStatus.UNAVAILABLE
    """Value assessment status."""
    
    # Reliability components
    reliability_score: float = 0.0
    """Historical reliability score (0-1) from MarketReliabilityCalculator."""
    
    brier_score: Optional[float] = None
    """Historical Brier score (lower is better)."""
    
    hit_rate: Optional[float] = None
    """Historical hit rate (proportion of correct predictions)."""
    
    # Uncertainty components
    uncertainty: float = 0.0
    """Uncertainty score (0-1) from UncertaintyEngine."""
    
    data_quality: float = 0.0
    """Data quality score (0-1)."""
    
    model_agreement: float = 0.5
    """Model agreement score (0-1), default 0.5 (neutral)."""
    
    # Sample size and distribution info
    sample_size: int = 0
    """Historical sample size for this market."""
    
    distribution_type: Optional[str] = None
    """Distribution type for shot markets: 'POISSON', 'NEGATIVE_BINOMIAL', 'UNAVAILABLE'."""
    
    expected_count: Optional[float] = None
    """Expected count for shot markets."""
    
    variance: Optional[float] = None
    """Variance for shot markets."""
    
    # Scoring
    composite_score: float = 0.0
    """Final composite score (0-100) from scoring formula."""
    
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    """Breakdown of score components for transparency."""


@dataclass
class BestTipResult:
    """Result of Smart Market Selector BEST TIP selection."""
    
    match_id: str
    """Match identifier."""
    
    best_tip: Optional[MarketCandidate]
    """Selected BEST TIP market. None when PASS."""
    
    is_pass: bool
    """True when no sufficiently reliable/valuable market exists."""
    
    pass_reason: Optional[str] = None
    """Human-readable reason for PASS decision."""
    
    all_candidates: List[MarketCandidate] = field(default_factory=list)
    """All evaluated market candidates (sorted by composite_score descending)."""
    
    # Aggregate statistics
    best_edge: Optional[float] = None
    """Highest edge found across all candidates."""
    
    best_reliability: Optional[float] = None
    """Highest reliability found across all candidates."""
    
    best_ev: Optional[float] = None
    """Highest EV found across all candidates."""
    
    overall_data_quality: float = 0.0
    """Average data quality across candidates."""
    
    overall_uncertainty: float = 0.0
    """Average uncertainty across candidates."""
    
    selection_timestamp: Optional[str] = None
    """ISO timestamp of selection."""


@dataclass
class SmartMarketSelectorConfig:
    """Configuration for Smart Market Selector."""
    
    # Score thresholds
    best_tip_threshold: float = 55.0
    """Minimum composite score to qualify as BEST TIP."""
    
    pass_threshold: float = 40.0
    """If all candidates below this, issue PASS."""
    
    # Value thresholds
    min_edge_for_bonus: float = 0.03
    """Minimum edge to award edge bonus (3%)."""
    
    min_ev_for_bonus: float = 0.0
    """Minimum EV to award EV bonus."""
    
    negative_edge_penalty_threshold: float = -0.03
    """Edges worse than this trigger penalty."""
    
    # Reliability thresholds
    min_reliability_for_pick: float = 0.40
    """Minimum reliability to avoid PASS."""
    
    max_uncertainty_for_pick: float = 0.70
    """Maximum uncertainty to avoid PASS."""
    
    min_data_quality_for_pick: float = 0.30
    """Minimum data quality to avoid PASS."""
    
    # Sample size thresholds
    high_sample_size_threshold: int = 50
    """Sample size threshold for bonus."""
    
    low_sample_size_penalty_threshold: int = 20
    """Below this, apply uncertainty increase."""
    
    # Probability conviction thresholds
    low_conviction_threshold: float = 0.30
    """Probabilities with conviction below this get penalty."""
    
    high_conviction_no_odds_threshold: float = 0.75
    """Without odds, need this conviction to avoid penalty."""
    
    # Score weights and bonuses
    weight_probability_conviction: float = 20.0
    """Base points for probability conviction (0-20)."""
    
    weight_reliability: float = 20.0
    """Base points for market reliability (0-20)."""
    
    weight_data_quality: float = 10.0
    """Base points for data quality (0-10)."""
    
    weight_model_agreement: float = 10.0
    """Base points for model agreement (0-10)."""
    
    bonus_edge_max: float = 20.0
    """Maximum bonus points for positive edge."""
    
    bonus_ev_max: float = 10.0
    """Maximum bonus points for positive EV."""
    
    bonus_calibration_fitted: float = 5.0
    """Bonus when calibration fitted."""
    
    bonus_high_sample_size: float = 5.0
    """Bonus for high sample size."""
    
    penalty_uncertainty_max: float = 20.0
    """Maximum penalty for high uncertainty."""
    
    penalty_low_conviction_max: float = 10.0
    """Maximum penalty for low conviction."""
    
    penalty_no_odds: float = 10.0
    """Penalty when no odds and low conviction."""
    
    penalty_negative_edge_max: float = 20.0
    """Maximum penalty for negative edge."""


class SmartMarketSelector:
    """Smart Market Selector - Value-based BEST TIP selection.
    
    Selects BEST TIP by evaluating:
    1. Probability conviction (how confident is the model)
    2. Value assessment (edge and EV when bookmaker odds available)
    3. Market reliability (historical calibration and performance)
    4. Data quality and model agreement
    5. Uncertainty assessment
    
    Issues PASS when no market meets minimum value + reliability criteria.
    
    Usage:
        selector = SmartMarketSelector()
        result = selector.select_best_tip(
            match_id="m1",
            candidates=[...],  # List of MarketCandidate objects
        )
        
        if not result.is_pass:
            print(f"BEST TIP: {result.best_tip.market_label}")
            print(f"Edge: {result.best_tip.edge:.2%}")
        else:
            print(f"PASS: {result.pass_reason}")
    """
    
    def __init__(self, config: Optional[SmartMarketSelectorConfig] = None):
        """Initialize Smart Market Selector.
        
        Args:
            config: Configuration for scoring and thresholds.
        """
        self.config = config or SmartMarketSelectorConfig()
    
    def select_best_tip(
        self,
        match_id: str,
        candidates: List[MarketCandidate],
    ) -> BestTipResult:
        """Select BEST TIP from candidate markets.
        
        Architecture:
        1. Filter candidates through eligibility gates
        2. Score only eligible candidates
        3. Return best eligible or PASS with specific reason
        
        Args:
            match_id: Match identifier.
            candidates: List of market candidates to evaluate.
        
        Returns:
            BestTipResult with selected tip or PASS decision.
        """
        if not candidates:
            return BestTipResult(
                match_id=match_id,
                best_tip=None,
                is_pass=True,
                pass_reason="NO_CANDIDATES",
                all_candidates=[],
            )
        
        # Phase 1: Apply eligibility gates
        eligible_candidates = []
        ineligible_reasons = {}
        
        for candidate in candidates:
            is_eligible, reason = self._check_eligibility(candidate)
            if is_eligible:
                eligible_candidates.append(candidate)
            else:
                ineligible_reasons[candidate.market_label] = reason
        
        # Phase 2: Score eligible candidates only
        for candidate in eligible_candidates:
            candidate.composite_score = self._score_market(candidate)
        
        # Phase 3: Sort by composite score descending
        eligible_sorted = sorted(
            eligible_candidates,
            key=lambda c: c.composite_score,
            reverse=True,
        )
        
        # All candidates sorted (eligible first, then ineligible with score=0)
        all_sorted = eligible_sorted + [c for c in candidates if c not in eligible_candidates]
        
        # Compute aggregate statistics
        if eligible_sorted:
            best_edge = max((c.edge for c in eligible_sorted if c.edge is not None), default=None)
            best_reliability = max((c.reliability_score for c in eligible_sorted), default=0.0)
            best_ev = max((c.expected_value for c in eligible_sorted if c.expected_value is not None), default=None)
        else:
            best_edge = None
            best_reliability = 0.0
            best_ev = None
        
        overall_data_quality = sum(c.data_quality for c in candidates) / len(candidates) if candidates else 0.0
        overall_uncertainty = sum(c.uncertainty for c in candidates) / len(candidates) if candidates else 0.0
        
        # Phase 4: Check PASS conditions
        is_pass, pass_reason = self._evaluate_pass_conditions(
            eligible_sorted,
            best_edge,
            best_reliability,
            overall_data_quality,
            overall_uncertainty,
            ineligible_reasons,
        )
        
        best_tip = None if is_pass else eligible_sorted[0]
        
        return BestTipResult(
            match_id=match_id,
            best_tip=best_tip,
            is_pass=is_pass,
            pass_reason=pass_reason,
            all_candidates=all_sorted,
            best_edge=best_edge,
            best_reliability=best_reliability,
            best_ev=best_ev,
            overall_data_quality=overall_data_quality,
            overall_uncertainty=overall_uncertainty,
        )
    
    def _check_eligibility(self, candidate: MarketCandidate) -> tuple[bool, Optional[str]]:
        """Check if a market candidate passes eligibility gates.
        
        Eligibility gates (hard stops):
        1. Negative edge when odds exist → INELIGIBLE
        2. Near-zero edge (< min threshold) when odds exist → INELIGIBLE
        3. Poor calibration + low reliability → INELIGIBLE
        4. Very low reliability (< 0.30) → INELIGIBLE
        5. Very high uncertainty (> 0.80) → INELIGIBLE
        
        Args:
            candidate: Market candidate to check.
        
        Returns:
            Tuple of (is_eligible, ineligibility_reason).
        """
        # Gate 1: Negative edge
        if candidate.edge is not None and candidate.edge < self.config.negative_edge_penalty_threshold:
            return False, "NEGATIVE_EDGE"
        
        # Gate 2: Near-zero edge when odds exist
        # This is THE critical gate: prevents high-probability, zero-edge markets
        if (candidate.value_status != ValueStatus.UNAVAILABLE and 
            candidate.edge is not None and 
            candidate.edge < self.config.min_edge_for_bonus):
            return False, "NEAR_ZERO_EDGE"
        
        # Gate 3: Poor calibration + low reliability
        if (candidate.calibration_status == CalibrationStatus.INSUFFICIENT_DATA and 
            candidate.reliability_score < 0.40):
            return False, "POOR_CALIBRATION_AND_RELIABILITY"
        
        # Gate 4: Very low reliability
        if candidate.reliability_score < 0.30:
            return False, "VERY_LOW_RELIABILITY"
        
        # Gate 5: Very high uncertainty
        if candidate.uncertainty > 0.80:
            return False, "VERY_HIGH_UNCERTAINTY"
        
        # Passed all gates
        return True, None
    
    def _score_market(self, candidate: MarketCandidate) -> float:
        """Compute composite score for an ELIGIBLE market candidate.
        
        This method is only called for markets that passed eligibility gates.
        
        Ranking priority (0-100 scale):
        1. Calibration validity (0-20 pts)
        2. Market reliability (0-20 pts)
        3. Edge/EV when odds exist (0-20 pts)
        4. Data quality (0-10 pts)
        5. Model agreement (0-10 pts)
        6. Probability conviction (0-10 pts)
        7. Uncertainty penalty (-20 pts max)
        
        Args:
            candidate: Market candidate to score (assumed eligible).
        
        Returns:
            Composite score (0-100).
        """
        score = 0.0
        breakdown = {}
        
        # Use calibrated probability if available, else model probability
        prob = candidate.calibrated_probability if candidate.calibrated_probability is not None else candidate.model_probability
        conviction = abs(prob - 0.5) / 0.5
        
        # Priority 1: Calibration validity (0-20 pts)
        if candidate.calibration_status == CalibrationStatus.FITTED:
            calibration_score = 20.0
        elif candidate.calibration_status == CalibrationStatus.NOT_FITTED:
            calibration_score = 10.0
        else:  # INSUFFICIENT_DATA
            calibration_score = 5.0
        score += calibration_score
        breakdown['calibration_validity'] = calibration_score
        
        # Priority 2: Market reliability (0-20 pts)
        reliability_score = 20.0 * candidate.reliability_score
        score += reliability_score
        breakdown['market_reliability'] = reliability_score
        
        # Priority 3: Edge/EV when odds exist (0-20 pts)
        if candidate.edge is not None and candidate.edge > self.config.min_edge_for_bonus:
            # Edge: scale up to 15 pts
            edge_score = min(15.0, candidate.edge * 150)  # 0.10 edge = 15 pts
            score += edge_score
            breakdown['edge_value'] = edge_score
            
            # EV: additional up to 5 pts
            if candidate.expected_value is not None and candidate.expected_value > 0:
                ev_score = min(5.0, candidate.expected_value * 25)
                score += ev_score
                breakdown['ev_value'] = ev_score
            else:
                breakdown['ev_value'] = 0.0
        else:
            breakdown['edge_value'] = 0.0
            breakdown['ev_value'] = 0.0
        
        # Priority 4: Data quality (0-10 pts)
        data_quality_score = 10.0 * candidate.data_quality
        score += data_quality_score
        breakdown['data_quality'] = data_quality_score
        
        # Priority 5: Model agreement (0-10 pts)
        model_agreement_score = 10.0 * candidate.model_agreement
        score += model_agreement_score
        breakdown['model_agreement'] = model_agreement_score
        
        # Priority 6: Probability conviction (0-5 pts, heavily de-emphasized)
        # This is the LEAST important factor - value and reliability dominate
        prob_conviction_score = 5.0 * conviction
        score += prob_conviction_score
        breakdown['probability_conviction'] = prob_conviction_score
        
        # Priority 7: Uncertainty penalty (-20 pts max)
        uncertainty_penalty = 20.0 * candidate.uncertainty
        score -= uncertainty_penalty
        breakdown['uncertainty_penalty'] = -uncertainty_penalty
        
        # Minor adjustments
        
        # Sample size bonus
        if candidate.sample_size >= self.config.high_sample_size_threshold:
            sample_bonus = 5.0
            score += sample_bonus
            breakdown['sample_size_bonus'] = sample_bonus
        else:
            breakdown['sample_size_bonus'] = 0.0
        
        # No odds penalty (when unavailable and low conviction)
        if (candidate.value_status == ValueStatus.UNAVAILABLE and 
            conviction < self.config.high_conviction_no_odds_threshold):
            no_odds_penalty = 5.0
            score -= no_odds_penalty
            breakdown['no_odds_penalty'] = -no_odds_penalty
        else:
            breakdown['no_odds_penalty'] = 0.0
        
        # Store breakdown
        candidate.score_breakdown = breakdown
        
        # Clamp to 0-100
        return max(0.0, min(100.0, score))
    
    def _evaluate_pass_conditions(
        self,
        eligible_candidates: List[MarketCandidate],
        best_edge: Optional[float],
        best_reliability: float,
        overall_data_quality: float,
        overall_uncertainty: float,
        ineligible_reasons: Dict[str, str],
    ) -> tuple[bool, Optional[str]]:
        """Evaluate whether to issue PASS instead of selecting BEST TIP.
        
        PASS priority (most specific first):
        1. No eligible markets
        2. All markets failed specific gates (negative/near-zero edge, etc.)
        3. Low reliability
        4. High uncertainty
        5. Insufficient data
        6. Best score below threshold
        
        Args:
            eligible_candidates: Candidates that passed eligibility gates, sorted by score.
            best_edge: Highest edge found among eligible candidates.
            best_reliability: Highest reliability found among eligible candidates.
            overall_data_quality: Average data quality across all candidates.
            overall_uncertainty: Average uncertainty across all candidates.
            ineligible_reasons: Dict mapping market labels to ineligibility reasons.
        
        Returns:
            Tuple of (is_pass, pass_reason).
        """
        # Condition 1: No eligible markets
        if not eligible_candidates:
            # Determine most common ineligibility reason
            if ineligible_reasons:
                reason_counts = {}
                for reason in ineligible_reasons.values():
                    reason_counts[reason] = reason_counts.get(reason, 0) + 1
                most_common_reason = max(reason_counts, key=reason_counts.get)
                
                # Map ineligibility reasons to PASS reasons
                if most_common_reason == "NEGATIVE_EDGE":
                    return True, "NO_POSITIVE_EDGE"
                elif most_common_reason == "NEAR_ZERO_EDGE":
                    return True, "NEAR_ZERO_EDGE"
                elif most_common_reason in ["POOR_CALIBRATION_AND_RELIABILITY", "VERY_LOW_RELIABILITY"]:
                    return True, "LOW_RELIABILITY"
                elif most_common_reason == "VERY_HIGH_UNCERTAINTY":
                    return True, "HIGH_UNCERTAINTY"
                else:
                    return True, "NO_ELIGIBLE_MARKETS"
            return True, "NO_ELIGIBLE_MARKETS"
        
        best_candidate = eligible_candidates[0]
        
        # Condition 2: Low reliability among eligible markets
        if best_reliability < self.config.min_reliability_for_pick:
            return True, "LOW_RELIABILITY"
        
        # Condition 3: High uncertainty among all markets
        if overall_uncertainty > self.config.max_uncertainty_for_pick:
            return True, "HIGH_UNCERTAINTY"
        
        # Condition 4: Insufficient data quality
        if overall_data_quality < self.config.min_data_quality_for_pick:
            return True, "INSUFFICIENT_DATA"
        
        # Condition 5: No odds + low confidence
        # When no bookmaker odds, require reasonable composite score OR good conviction
        has_odds = any(c.value_status != ValueStatus.UNAVAILABLE for c in eligible_candidates)
        if not has_odds:
            # Use calibrated probability for conviction check
            best_prob = best_candidate.calibrated_probability if best_candidate.calibrated_probability is not None else best_candidate.model_probability
            conviction = abs(best_prob - 0.5) / 0.5
            
            # Require either decent score (50+) OR good conviction (0.55+)
            if best_candidate.composite_score < 50.0 and conviction < 0.55:
                return True, "NO_BOOKMAKER_ODDS_AND_LOW_CONFIDENCE"
        
        # Condition 6: Best score below threshold
        # When no odds available, use a lower threshold (45 instead of 55)
        has_odds = any(c.value_status != ValueStatus.UNAVAILABLE for c in eligible_candidates)
        effective_best_tip_threshold = self.config.best_tip_threshold if has_odds else 45.0
        
        if best_candidate.composite_score < effective_best_tip_threshold:
            # Score is below effective threshold
            if best_candidate.composite_score < self.config.pass_threshold:
                return True, "LOW_COMPOSITE_SCORE"
            # Between pass and best_tip threshold
            return True, "INSUFFICIENT_CONFIDENCE"
        
        # Passed all conditions - select best tip
        return False, None
