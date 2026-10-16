"""TUTAR X Pick generator (internal module name: mensione_pick for backward compatibility).

Generates recommended betting picks from market probabilities and confidence assessment.

The TUTAR X PICK is EXPLICITLY DISTINCT from the Predicted Score.

Example:
    Predicted Score: 3-1
    Score Distribution: 3-1 (18%), 2-1 (14%), 3-0 (11%), ...
    TUTAR X PICK: HOME OVER 1.5

The pick is chosen from market rankings based on:
1. Expected Value (EV) when odds available: EV = (model_prob * market_odds) - 1
2. Model conviction when no odds: distance from 50% threshold
3. Minimum confidence threshold filtering
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from app.prediction.market_derivation import MarketProbabilities
from app.prediction.confidence_engine import ConfidenceAssessment


@dataclass
class MensionePick:
    """TUTAR X recommended pick with confidence and reasoning.
    
    This is SEPARATE from the predicted score. The predicted score is the most
    likely scoreline from the distribution. The TUTAR X PICK is the recommended
    market outcome based on value analysis.
    """
    
    # Pick identification
    pick_market: str
    """Market outcome recommended (e.g., "HOME", "OVER 2.5", "BTTS YES", "HOME OVER 1.5")"""
    
    pick_probability: float
    """Model's probability for this outcome [0, 1]"""
    
    confidence_label: str
    """Confidence tier from ConfidenceAssessment: HIGH, MEDIUM, LOW"""
    
    confidence_score: float
    """Numerical confidence score [0, 1]"""
    
    # Value assessment
    expected_value: Optional[float] = None
    """Expected value if odds available: EV = (prob * odds) - 1"""
    
    market_odds: Optional[float] = None
    """Market odds if available"""
    
    fair_odds: float = 0.0
    """Fair odds from model: 1 / probability"""
    
    edge: Optional[float] = None
    """Edge over market: model_prob - implied_market_prob"""
    
    # Reasoning
    reasoning_factors: List[str] = field(default_factory=list)
    """Factual factors supporting this pick (max 5)"""
    
    # Score context (for reference, but NOT the pick itself)
    predicted_score: str = ""
    """Most likely scoreline (e.g., "3-1") - for context only"""
    
    score_distribution_top5: List[str] = field(default_factory=list)
    """Top 5 scorelines with probabilities (e.g., ["3-1 (18%)", "2-1 (14%)", ...])"""
    
    def __post_init__(self):
        """Validate pick after initialization."""
        if not (0.0 <= self.pick_probability <= 1.0):
            raise ValueError(f"pick_probability must be in [0, 1], got {self.pick_probability}")
        
        if not (0.0 <= self.confidence_score <= 1.0):
            raise ValueError(f"confidence_score must be in [0, 1], got {self.confidence_score}")
        
        if self.confidence_label not in ["HIGH", "MEDIUM", "LOW"]:
            raise ValueError(f"confidence_label must be HIGH/MEDIUM/LOW, got {self.confidence_label}")
        
        if self.pick_probability > 0:
            expected_fair_odds = 1.0 / self.pick_probability
            if not (0.99 <= self.fair_odds / expected_fair_odds <= 1.01):
                # Allow recalculation if not set correctly
                self.fair_odds = expected_fair_odds


@dataclass
class MarketRanking:
    """Internal ranking of a market for pick selection."""
    
    market_name: str
    probability: float
    conviction: float  # Distance from 50% threshold
    expected_value: Optional[float] = None
    edge: Optional[float] = None
    
    def score(self) -> float:
        """Calculate ranking score.
        
        When odds available: use EV
        When no odds: use conviction
        
        Returns:
            Ranking score (higher = better)
        """
        if self.expected_value is not None and self.edge is not None:
            # Prioritize positive EV and edge
            return self.expected_value + self.edge
        else:
            # Use conviction (distance from 50%)
            return self.conviction


class MensionePickGenerator:
    """Generates MENSIONE recommended picks from market probabilities.
    
    Algorithm:
    1. Extract all markets from MarketProbabilities
    2. Calculate conviction for each market (distance from 50%)
    3. Calculate EV and edge if odds available
    4. Rank markets by score (EV + edge when available, else conviction)
    5. Filter by minimum confidence threshold
    6. Select top-ranked market as TUTAR X PICK
    7. Build reasoning factors from data
    
    The TUTAR X PICK is separate from the predicted score. A match with
    predicted score 3-1 might have pick "HOME OVER 1.5" if that market
    offers the best value.
    """
    
    def __init__(
        self,
        min_confidence: float = 0.4,
        min_probability: float = 0.55,
        min_edge: float = 0.0
    ):
        """Initialize TUTAR X pick generator (class name kept for backward compatibility).
        
        Args:
            min_confidence: Minimum confidence threshold for generating pick
            min_probability: Minimum probability threshold for pick
            min_edge: Minimum edge required when odds available
        """
        self.min_confidence = min_confidence
        self.min_probability = min_probability
        self.min_edge = min_edge
    
    def generate(
        self,
        market_probs: MarketProbabilities,
        confidence_assessment: ConfidenceAssessment,
        odds_data: Optional[Dict[str, float]] = None
    ) -> Optional[MensionePick]:
        """Generate TUTAR X pick from market probabilities.
        
        Args:
            market_probs: Derived market probabilities
            confidence_assessment: Confidence assessment for prediction
            odds_data: Optional market odds (market_name -> odds)
                Format: {"HOME": 2.1, "DRAW": 3.5, "AWAY": 3.8, "OVER_2_5": 1.85, ...}
        
        Returns:
            MensionePick if confidence sufficient, None otherwise
        """
        # Check confidence threshold
        if confidence_assessment.overall_confidence < self.min_confidence:
            return None
        
        # Build market rankings
        rankings = self._build_market_rankings(market_probs, odds_data)
        
        # Filter by minimum probability and edge
        filtered_rankings = [
            r for r in rankings
            if r.probability >= self.min_probability
            and (r.edge is None or r.edge >= self.min_edge)
        ]
        
        if not filtered_rankings:
            return None
        
        # Sort by score (highest first)
        filtered_rankings.sort(key=lambda r: r.score(), reverse=True)
        
        # Select top-ranked market
        top_market = filtered_rankings[0]
        
        # Build reasoning factors
        reasoning = self._build_reasoning(
            top_market,
            market_probs,
            confidence_assessment
        )
        
        # Get predicted score (most likely scoreline)
        predicted_score = market_probs.exact_score_top[0][0] if market_probs.exact_score_top else "N/A"
        
        # Get top 5 scorelines with percentages
        score_dist_top5 = [
            f"{scoreline} ({prob*100:.0f}%)"
            for scoreline, prob in market_probs.exact_score_top[:5]
        ]
        
        # Build pick
        pick = MensionePick(
            pick_market=top_market.market_name,
            pick_probability=top_market.probability,
            confidence_label=confidence_assessment.confidence_label,
            confidence_score=confidence_assessment.overall_confidence,
            expected_value=top_market.expected_value,
            market_odds=odds_data.get(top_market.market_name) if odds_data else None,
            fair_odds=1.0 / top_market.probability if top_market.probability > 0 else 0.0,
            edge=top_market.edge,
            reasoning_factors=reasoning[:5],  # Max 5 factors
            predicted_score=predicted_score,
            score_distribution_top5=score_dist_top5
        )
        
        return pick
    
    def _build_market_rankings(
        self,
        market_probs: MarketProbabilities,
        odds_data: Optional[Dict[str, float]]
    ) -> List[MarketRanking]:
        """Build rankings for all markets.
        
        Args:
            market_probs: Market probabilities
            odds_data: Optional odds data
        
        Returns:
            List of MarketRanking objects
        """
        rankings = []
        
        # 1X2 markets
        for market_name, prob in [
            ("HOME", market_probs.home_win),
            ("DRAW", market_probs.draw),
            ("AWAY", market_probs.away_win)
        ]:
            conviction = abs(prob - 0.333)  # Distance from uniform 1X2
            ev = None
            edge = None
            
            if odds_data and market_name in odds_data:
                odds = odds_data[market_name]
                ev = (prob * odds) - 1.0
                implied_prob = 1.0 / odds
                edge = prob - implied_prob
            
            rankings.append(MarketRanking(
                market_name=market_name,
                probability=prob,
                conviction=conviction,
                expected_value=ev,
                edge=edge
            ))
        
        # Double chance markets
        for market_name, prob in [
            ("1X", market_probs.home_or_draw),
            ("X2", market_probs.draw_or_away),
            ("12", market_probs.home_or_away)
        ]:
            conviction = abs(prob - 0.667)  # Distance from 2/3
            ev = None
            edge = None
            
            if odds_data and market_name in odds_data:
                odds = odds_data[market_name]
                ev = (prob * odds) - 1.0
                implied_prob = 1.0 / odds
                edge = prob - implied_prob
            
            rankings.append(MarketRanking(
                market_name=market_name,
                probability=prob,
                conviction=conviction,
                expected_value=ev,
                edge=edge
            ))
        
        # Over/Under markets
        for line, (over_prob, under_prob) in market_probs.over_under.items():
            for market_type, prob in [("OVER", over_prob), ("UNDER", under_prob)]:
                market_name = f"{market_type} {line}"
                conviction = abs(prob - 0.5)  # Distance from 50%
                ev = None
                edge = None
                
                market_key = f"{market_type}_{line}".replace(".", "_")
                if odds_data and market_key in odds_data:
                    odds = odds_data[market_key]
                    ev = (prob * odds) - 1.0
                    implied_prob = 1.0 / odds
                    edge = prob - implied_prob
                
                rankings.append(MarketRanking(
                    market_name=market_name,
                    probability=prob,
                    conviction=conviction,
                    expected_value=ev,
                    edge=edge
                ))
        
        # BTTS markets
        for market_name, prob in [
            ("BTTS YES", market_probs.btts_yes),
            ("BTTS NO", market_probs.btts_no)
        ]:
            conviction = abs(prob - 0.5)
            ev = None
            edge = None
            
            market_key = market_name.replace(" ", "_")
            if odds_data and market_key in odds_data:
                odds = odds_data[market_key]
                ev = (prob * odds) - 1.0
                implied_prob = 1.0 / odds
                edge = prob - implied_prob
            
            rankings.append(MarketRanking(
                market_name=market_name,
                probability=prob,
                conviction=conviction,
                expected_value=ev,
                edge=edge
            ))
        
        # Team totals markets
        for line, prob in market_probs.home_team_over.items():
            market_name = f"HOME OVER {line}"
            conviction = abs(prob - 0.5)
            ev = None
            edge = None
            
            market_key = f"HOME_OVER_{line}".replace(".", "_")
            if odds_data and market_key in odds_data:
                odds = odds_data[market_key]
                ev = (prob * odds) - 1.0
                implied_prob = 1.0 / odds
                edge = prob - implied_prob
            
            rankings.append(MarketRanking(
                market_name=market_name,
                probability=prob,
                conviction=conviction,
                expected_value=ev,
                edge=edge
            ))
        
        for line, prob in market_probs.away_team_over.items():
            market_name = f"AWAY OVER {line}"
            conviction = abs(prob - 0.5)
            ev = None
            edge = None
            
            market_key = f"AWAY_OVER_{line}".replace(".", "_")
            if odds_data and market_key in odds_data:
                odds = odds_data[market_key]
                ev = (prob * odds) - 1.0
                implied_prob = 1.0 / odds
                edge = prob - implied_prob
            
            rankings.append(MarketRanking(
                market_name=market_name,
                probability=prob,
                conviction=conviction,
                expected_value=ev,
                edge=edge
            ))
        
        return rankings
    
    def _build_reasoning(
        self,
        top_market: MarketRanking,
        market_probs: MarketProbabilities,
        confidence_assessment: ConfidenceAssessment
    ) -> List[str]:
        """Build reasoning factors for the pick.
        
        Args:
            top_market: Selected market ranking
            market_probs: Market probabilities
            confidence_assessment: Confidence assessment
        
        Returns:
            List of factual reasoning strings (max 5)
        """
        factors = []
        
        # Probability strength
        prob_pct = top_market.probability * 100
        factors.append(f"Model assigns {prob_pct:.1f}% probability to {top_market.market_name}")
        
        # Confidence level
        conf_pct = confidence_assessment.overall_confidence * 100
        factors.append(f"{confidence_assessment.confidence_label} confidence ({conf_pct:.0f}%)")
        
        # Edge/EV if available
        if top_market.edge is not None and top_market.edge > 0:
            edge_pct = top_market.edge * 100
            factors.append(f"Model edge of {edge_pct:.1f}% over market odds")
        
        if top_market.expected_value is not None and top_market.expected_value > 0:
            ev_pct = top_market.expected_value * 100
            factors.append(f"Positive expected value of {ev_pct:.1f}%")
        
        # Model agreement (if strong)
        model_agreement = confidence_assessment.components.model_agreement
        if model_agreement >= 0.8:
            agreement_pct = model_agreement * 100
            factors.append(f"Strong model consensus ({agreement_pct:.0f}% agreement)")
        
        # Data quality (if strong)
        data_quality = confidence_assessment.components.data_quality
        if data_quality >= 0.8:
            quality_pct = data_quality * 100
            factors.append(f"High data quality ({quality_pct:.0f}%)")
        
        return factors
