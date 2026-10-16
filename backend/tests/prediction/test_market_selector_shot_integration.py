"""Integration tests for shot market evaluation in Smart Market Selector.

Tests FEAT-003: Shot markets evaluated alongside 1X2/BTTS/goals markets,
competing on selection_score (not just probability).

Shot markets with low confidence, high uncertainty, or insufficient data
should trigger PASS with explicit reason.
"""

import pytest
from datetime import datetime
from typing import Dict, List

from app.prediction.market_selector import SmartMarketSelector, BestTip, PassDecision
from app.prediction.market_derivation import MarketProbabilities
from app.prediction.confidence_engine import (
    ConfidenceAssessment,
    ConfidenceComponents,
    ConfidenceWeights
)
from app.prediction.interfaces import (
    ShotMarketType,
    ShotMarketPrediction,
    ShotMarketThreshold,
    DistributionType
)


def create_test_market_probs() -> MarketProbabilities:
    """Create test market probabilities."""
    return MarketProbabilities(
        home_win=0.45,
        draw=0.30,
        away_win=0.25,
        home_or_draw=0.75,
        draw_or_away=0.55,
        home_or_away=0.70,
        over_under={
            0.5: (0.92, 0.08),
            1.5: (0.75, 0.25),
            2.5: (0.58, 0.42),
            3.5: (0.35, 0.65)
        },
        btts_yes=0.52,
        btts_no=0.48,
        home_team_over={0.5: 0.78, 1.5: 0.45},
        away_team_over={0.5: 0.72, 1.5: 0.38}
    )


def create_test_confidence_assessment(
    overall_confidence: float = 0.7,
    model_agreement: float = 0.8,
    data_quality: float = 0.75
) -> ConfidenceAssessment:
    """Create test confidence assessment."""
    return ConfidenceAssessment(
        overall_confidence=overall_confidence,
        confidence_label="HIGH" if overall_confidence >= 0.7 else "MEDIUM",
        components=ConfidenceComponents(
            model_agreement=model_agreement,
            data_quality=data_quality,
            sample_size_score=0.8,
            calibration_reliability=0.7,
            lineup_certainty=0.6,
            feature_stability=0.75
        ),
        weights=ConfidenceWeights(),
        component_breakdown={}
    )


def create_test_shot_market_prediction(
    team_id: str,
    market_type: ShotMarketType,
    thresholds: List[tuple],  # [(threshold, probability), ...]
    available: bool = True,
    sample_size: int = 20,
    data_quality: float = 0.8,
    variance: float = 4.0,
    expected_value: float = 12.0
) -> ShotMarketPrediction:
    """Create test shot market prediction.
    
    Args:
        team_id: Team identifier
        market_type: Market type
        thresholds: List of (threshold, probability) tuples
        available: Whether prediction is available
        sample_size: Historical sample size
        data_quality: Data quality score
        variance: Shot distribution variance
        expected_value: Expected shot count
    """
    threshold_objs = [
        ShotMarketThreshold(
            threshold=t,
            over_probability=p,
            distribution_model=DistributionType.POISSON,
            expected_value=expected_value,
            variance=variance,
            data_quality=data_quality
        )
        for t, p in thresholds
    ]
    
    return ShotMarketPrediction(
        team_id=team_id,
        market_type=market_type,
        thresholds=threshold_objs,
        distribution_model=DistributionType.POISSON,
        expected_value=expected_value,
        variance=variance,
        available=available,
        unavailability_reason=None if available else "insufficient_shot_data",
        sample_size=sample_size,
        data_quality_score=data_quality,
        model_id="shot_market_v1"
    )


class TestShotMarketIntegration:
    """Test shot market integration with Smart Market Selector."""
    
    def test_shot_markets_evaluated_alongside_1x2(self):
        """Test that shot markets are evaluated alongside 1X2 markets."""
        selector = SmartMarketSelector(
            min_confidence=0.4,
            min_probability=0.5,
            min_edge=0.0
        )
        
        market_probs = create_test_market_probs()
        confidence = create_test_confidence_assessment()
        
        # Create shot market predictions with moderate probabilities
        shot_markets = {
            ShotMarketType.TEAM_SHOTS: [
                create_test_shot_market_prediction(
                    team_id="home",
                    market_type=ShotMarketType.TEAM_SHOTS,
                    thresholds=[
                        (10, 0.75),
                        (12, 0.60),
                        (15, 0.42)
                    ],
                    sample_size=25,
                    data_quality=0.85
                )
            ]
        }
        
        result = selector.evaluate_and_select(
            market_probs=market_probs,
            confidence_assessment=confidence,
            shot_market_predictions=shot_markets,
            home_team_name="Team A",
            away_team_name="Team B"
        )
        
        # Should select either 1X2 or shot market based on selection_score
        # Not testing which is selected, just that shot markets are evaluated
        assert result is not None
        if isinstance(result, BestTip):
            # Either a traditional market or shot market selected
            assert result.market is not None
            assert result.selection is not None
        elif isinstance(result, PassDecision):
            # Both traditional and shot markets failed qualification
            assert result.evaluated_markets_count > 0
    
    def test_best_shot_market_selected_when_highest_score(self):
        """Test that best shot market is selected when it has highest selection_score."""
        selector = SmartMarketSelector(
            min_confidence=0.4,
            min_probability=0.5,
            min_edge=0.0
        )
        
        # Create market probs with low probabilities
        market_probs = MarketProbabilities(
            home_win=0.35,
            draw=0.30,
            away_win=0.35,
            home_or_draw=0.65,
            draw_or_away=0.65,
            home_or_away=0.70,
            over_under={2.5: (0.52, 0.48)},
            btts_yes=0.51,
            btts_no=0.49,
            home_team_over={},
            away_team_over={}
        )
        
        confidence = create_test_confidence_assessment(
            overall_confidence=0.75,
            model_agreement=0.85,
            data_quality=0.8
        )
        
        # Create shot market with high probability and good quality
        shot_markets = {
            ShotMarketType.TEAM_SHOTS: [
                create_test_shot_market_prediction(
                    team_id="home",
                    market_type=ShotMarketType.TEAM_SHOTS,
                    thresholds=[
                        (10, 0.85),  # High probability
                        (12, 0.70),
                        (15, 0.52)
                    ],
                    sample_size=30,  # Good sample
                    data_quality=0.9,  # High quality
                    variance=3.5,  # Low variance (stable)
                    expected_value=14.0
                )
            ]
        }
        
        result = selector.evaluate_and_select(
            market_probs=market_probs,
            confidence_assessment=confidence,
            shot_market_predictions=shot_markets,
            home_team_name="Team A",
            away_team_name="Team B"
        )
        
        # Shot market should be selected due to high probability + confidence
        assert isinstance(result, BestTip)
        assert "SHOT_" in result.market or "Shot" in result.selection
        assert result.probability >= 0.5
        assert result.confidence >= 0.4
    
    def test_weak_shot_markets_trigger_pass(self):
        """Test that weak shot markets trigger PASS decision."""
        selector = SmartMarketSelector(
            min_confidence=0.6,  # Higher threshold
            min_probability=0.5,
            min_edge=0.0
        )
        
        # Weak traditional markets
        market_probs = MarketProbabilities(
            home_win=0.40,
            draw=0.32,
            away_win=0.28,
            home_or_draw=0.72,
            draw_or_away=0.60,
            home_or_away=0.68,
            over_under={2.5: (0.48, 0.52)},
            btts_yes=0.49,
            btts_no=0.51,
            home_team_over={},
            away_team_over={}
        )
        
        # Low confidence
        confidence = create_test_confidence_assessment(
            overall_confidence=0.45,  # Below min_confidence
            model_agreement=0.5,
            data_quality=0.4
        )
        
        # Weak shot market: low sample, high variance
        shot_markets = {
            ShotMarketType.TEAM_SHOTS: [
                create_test_shot_market_prediction(
                    team_id="home",
                    market_type=ShotMarketType.TEAM_SHOTS,
                    thresholds=[(10, 0.55), (12, 0.38)],
                    sample_size=4,  # Insufficient
                    data_quality=0.3,  # Poor quality
                    variance=12.0,  # High variance
                    expected_value=10.0
                )
            ]
        }
        
        result = selector.evaluate_and_select(
            market_probs=market_probs,
            confidence_assessment=confidence,
            shot_market_predictions=shot_markets,
            home_team_name="Team A",
            away_team_name="Team B"
        )
        
        # Should trigger PASS due to weak confidence/quality
        assert isinstance(result, PassDecision)
        assert result.pass_reason in [
            "poor_calibration",
            "weak_agreement",
            "no_qualifying_market"
        ]
    
    def test_shot_market_with_insufficient_data_excluded(self):
        """Test that shot markets with insufficient data are excluded from candidates."""
        selector = SmartMarketSelector(
            min_confidence=0.4,
            min_probability=0.5,
            min_edge=0.0
        )
        
        market_probs = create_test_market_probs()
        confidence = create_test_confidence_assessment()
        
        # Unavailable shot market
        shot_markets = {
            ShotMarketType.TEAM_SHOTS: [
                create_test_shot_market_prediction(
                    team_id="home",
                    market_type=ShotMarketType.TEAM_SHOTS,
                    thresholds=[],  # No thresholds
                    available=False,  # Not available
                    sample_size=2,
                    data_quality=0.1
                )
            ]
        }
        
        result = selector.evaluate_and_select(
            market_probs=market_probs,
            confidence_assessment=confidence,
            shot_market_predictions=shot_markets,
            home_team_name="Team A",
            away_team_name="Team B"
        )
        
        # Should select from traditional markets, not unavailable shot market
        if isinstance(result, BestTip):
            # Traditional market selected (shot market was excluded)
            assert "SHOT_" not in result.market
    
    def test_shot_market_candidate_structure_matches_evaluation(self):
        """Test that shot market candidates match CandidateEvaluation format."""
        selector = SmartMarketSelector(
            min_confidence=0.4,
            min_probability=0.5,
            min_edge=0.0
        )
        
        market_probs = create_test_market_probs()
        confidence = create_test_confidence_assessment()
        
        shot_markets = {
            ShotMarketType.TEAM_SHOTS: [
                create_test_shot_market_prediction(
                    team_id="home",
                    market_type=ShotMarketType.TEAM_SHOTS,
                    thresholds=[(10, 0.75), (12, 0.60)],
                    sample_size=20,
                    data_quality=0.8
                )
            ]
        }
        
        result = selector.evaluate_and_select(
            market_probs=market_probs,
            confidence_assessment=confidence,
            shot_market_predictions=shot_markets,
            home_team_name="Team A",
            away_team_name="Team B"
        )
        
        # Verify result structure
        assert result is not None
        if isinstance(result, BestTip):
            assert hasattr(result, 'market')
            assert hasattr(result, 'selection')
            assert hasattr(result, 'probability')
            assert hasattr(result, 'confidence')
            assert hasattr(result, 'selection_score')
            assert hasattr(result, 'risk_level')
        elif isinstance(result, PassDecision):
            assert hasattr(result, 'pass_reason')
            assert hasattr(result, 'evaluated_markets_count')
    
    def test_shot_on_target_markets_evaluated(self):
        """Test that shots on target markets are evaluated correctly."""
        selector = SmartMarketSelector(
            min_confidence=0.4,
            min_probability=0.5,
            min_edge=0.0
        )
        
        market_probs = create_test_market_probs()
        confidence = create_test_confidence_assessment()
        
        # SOT market
        shot_markets = {
            ShotMarketType.TEAM_SHOTS_ON_TARGET: [
                create_test_shot_market_prediction(
                    team_id="home",
                    market_type=ShotMarketType.TEAM_SHOTS_ON_TARGET,
                    thresholds=[(3, 0.80), (4, 0.65), (5, 0.48)],
                    sample_size=25,
                    data_quality=0.85,
                    variance=2.0,
                    expected_value=5.5
                )
            ]
        }
        
        result = selector.evaluate_and_select(
            market_probs=market_probs,
            confidence_assessment=confidence,
            shot_market_predictions=shot_markets,
            home_team_name="Team A",
            away_team_name="Team B"
        )
        
        # Should evaluate SOT markets
        assert result is not None
    
    def test_total_shots_markets_evaluated(self):
        """Test that total shots markets are evaluated correctly."""
        selector = SmartMarketSelector(
            min_confidence=0.4,
            min_probability=0.5,
            min_edge=0.0
        )
        
        market_probs = create_test_market_probs()
        confidence = create_test_confidence_assessment()
        
        # Total shots market
        shot_markets = {
            ShotMarketType.TOTAL_SHOTS: [
                create_test_shot_market_prediction(
                    team_id="total",
                    market_type=ShotMarketType.TOTAL_SHOTS,
                    thresholds=[(20, 0.70), (22, 0.58), (25, 0.40)],
                    sample_size=30,
                    data_quality=0.9,
                    variance=8.0,
                    expected_value=24.0
                )
            ]
        }
        
        result = selector.evaluate_and_select(
            market_probs=market_probs,
            confidence_assessment=confidence,
            shot_market_predictions=shot_markets,
            home_team_name="Team A",
            away_team_name="Team B"
        )
        
        # Should evaluate total shots markets
        assert result is not None
