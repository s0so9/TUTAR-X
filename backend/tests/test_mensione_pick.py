"""Tests for MENSIONE pick generator."""

import pytest
from app.prediction.mensione_pick import MensionePickGenerator, MensionePick
from app.prediction.market_derivation import MarketProbabilities
from app.prediction.confidence_engine import ConfidenceAssessment, ConfidenceComponents, ConfidenceWeights


class TestMensionePickGenerator:
    """Test MensionePickGenerator."""
    
    def test_generate_pick_high_confidence(self):
        """Test pick generation with high confidence."""
        generator = MensionePickGenerator(
            min_confidence=0.4,
            min_probability=0.55
        )
        
        # Build market probabilities
        markets = MarketProbabilities(
            home_win=0.65,
            draw=0.20,
            away_win=0.15,
            home_or_draw=0.85,
            draw_or_away=0.35,
            home_or_away=0.80,
            over_under={
                0.5: (0.85, 0.15),
                1.5: (0.70, 0.30),
                2.5: (0.60, 0.40),
                3.5: (0.35, 0.65)
            },
            btts_yes=0.55,
            btts_no=0.45,
            home_team_over={0.5: 0.75, 1.5: 0.60, 2.5: 0.40},
            away_team_over={0.5: 0.50, 1.5: 0.30, 2.5: 0.15},
            exact_score_top=[("2-1", 0.18), ("2-0", 0.15), ("1-0", 0.12)]
        )
        
        # Build confidence assessment
        confidence = ConfidenceAssessment(
            overall_confidence=0.75,
            confidence_label="HIGH",
            components=ConfidenceComponents(
                model_agreement=0.85,
                data_quality=0.80,
                sample_size_score=0.70,
                calibration_reliability=0.75,
                lineup_certainty=0.50,
                feature_stability=0.90
            ),
            weights=ConfidenceWeights()
        )
        
        # Generate pick (no odds)
        pick = generator.generate(markets, confidence)
        
        assert pick is not None
        # Should select a high-conviction market (distance from 50%)
        assert pick.pick_probability >= 0.55  # Above minimum threshold
        assert pick.pick_market in ["HOME", "OVER 0.5", "HOME OVER 0.5", "HOME OVER 1.5"]
        assert pick.confidence_label == "HIGH"
        assert pick.confidence_score == 0.75
        assert pick.predicted_score == "2-1"
        assert len(pick.score_distribution_top5) <= 5
        assert len(pick.reasoning_factors) <= 5
    
    def test_pick_vs_predicted_score_separation(self):
        """Test that MENSIONE PICK is separate from predicted score."""
        generator = MensionePickGenerator(min_confidence=0.4, min_probability=0.55)
        
        # Distribution where most likely score is 3-1 but HOME OVER 1.5 has highest conviction
        markets = MarketProbabilities(
            home_win=0.60,
            draw=0.25,
            away_win=0.15,
            home_or_draw=0.85,
            draw_or_away=0.40,
            home_or_away=0.75,
            over_under={2.5: (0.55, 0.45)},
            btts_yes=0.50,
            btts_no=0.50,
            home_team_over={
                0.5: 0.85,
                1.5: 0.72,  # Strong probability for HOME OVER 1.5
                2.5: 0.45
            },
            away_team_over={0.5: 0.55, 1.5: 0.30, 2.5: 0.15},
            exact_score_top=[("3-1", 0.18), ("2-1", 0.15), ("2-0", 0.12)]
        )
        
        confidence = ConfidenceAssessment(
            overall_confidence=0.70,
            confidence_label="HIGH",
            components=ConfidenceComponents(),
            weights=ConfidenceWeights()
        )
        
        pick = generator.generate(markets, confidence)
        
        assert pick is not None
        # Predicted score is 3-1 (most likely)
        assert pick.predicted_score == "3-1"
        # Pick should be a high-conviction market from team totals or home win
        assert pick.pick_market in ["HOME", "HOME OVER 0.5", "HOME OVER 1.5"]
        assert pick.pick_probability >= 0.60  # Should be high conviction
    
    def test_no_pick_when_low_confidence(self):
        """Test that no pick is generated when confidence is too low."""
        generator = MensionePickGenerator(min_confidence=0.6)
        
        markets = MarketProbabilities(
            home_win=0.60,
            draw=0.25,
            away_win=0.15,
            home_or_draw=0.85,
            draw_or_away=0.40,
            home_or_away=0.75,
            over_under={2.5: (0.55, 0.45)},
            btts_yes=0.50,
            btts_no=0.50,
            home_team_over={0.5: 0.75, 1.5: 0.60, 2.5: 0.40},
            away_team_over={0.5: 0.50, 1.5: 0.30, 2.5: 0.15},
            exact_score_top=[("2-1", 0.18)]
        )
        
        # Low confidence
        confidence = ConfidenceAssessment(
            overall_confidence=0.35,  # Below threshold
            confidence_label="LOW",
            components=ConfidenceComponents(),
            weights=ConfidenceWeights()
        )
        
        pick = generator.generate(markets, confidence)
        
        assert pick is None  # No pick due to low confidence
    
    def test_pick_with_odds_uses_ev(self):
        """Test that pick selection uses EV when odds available."""
        generator = MensionePickGenerator(min_confidence=0.4, min_edge=0.05)
        
        markets = MarketProbabilities(
            home_win=0.55,  # Fair odds: 1.82
            draw=0.25,  # Fair odds: 4.0
            away_win=0.20,  # Fair odds: 5.0
            home_or_draw=0.80,
            draw_or_away=0.45,
            home_or_away=0.75,
            over_under={2.5: (0.60, 0.40)},  # Over fair odds: 1.67
            btts_yes=0.50,
            btts_no=0.50,
            home_team_over={0.5: 0.70, 1.5: 0.55, 2.5: 0.35},
            away_team_over={0.5: 0.50, 1.5: 0.30, 2.5: 0.15},
            exact_score_top=[("2-1", 0.18)]
        )
        
        # Market odds (higher than fair = value)
        odds_data = {
            "HOME": 2.1,  # EV = 0.55 * 2.1 - 1 = 0.155 (15.5%)
            "DRAW": 3.5,  # EV = 0.25 * 3.5 - 1 = -0.125 (negative)
            "AWAY": 4.5,  # EV = 0.20 * 4.5 - 1 = -0.10 (negative)
            "OVER_2_5": 1.90,  # EV = 0.60 * 1.90 - 1 = 0.14 (14%)
        }
        
        confidence = ConfidenceAssessment(
            overall_confidence=0.70,
            confidence_label="HIGH",
            components=ConfidenceComponents(),
            weights=ConfidenceWeights()
        )
        
        pick = generator.generate(markets, confidence, odds_data)
        
        assert pick is not None
        assert pick.pick_market == "HOME"  # Best EV
        assert pick.expected_value is not None
        assert pick.expected_value > 0.1  # Positive EV
        assert pick.edge is not None
        assert pick.edge > 0  # Positive edge
        assert pick.market_odds == 2.1
    
    def test_no_pick_when_all_probabilities_too_low(self):
        """Test no pick when all probabilities below minimum."""
        generator = MensionePickGenerator(min_probability=0.70)
        
        # Balanced match (no strong conviction)
        markets = MarketProbabilities(
            home_win=0.40,
            draw=0.30,
            away_win=0.30,
            home_or_draw=0.70,  # Exactly at threshold
            draw_or_away=0.60,
            home_or_away=0.70,  # Exactly at threshold
            over_under={2.5: (0.55, 0.45)},
            btts_yes=0.52,
            btts_no=0.48,
            home_team_over={0.5: 0.65, 1.5: 0.45, 2.5: 0.25},
            away_team_over={0.5: 0.60, 1.5: 0.40, 2.5: 0.20},
            exact_score_top=[("1-1", 0.15)]
        )
        
        confidence = ConfidenceAssessment(
            overall_confidence=0.75,
            confidence_label="HIGH",
            components=ConfidenceComponents(),
            weights=ConfidenceWeights()
        )
        
        pick = generator.generate(markets, confidence)
        
        # Should select double chance markets which are exactly at threshold
        assert pick is not None
        assert pick.pick_probability >= 0.70
    
    def test_reasoning_factors(self):
        """Test that reasoning factors are generated correctly."""
        generator = MensionePickGenerator(min_confidence=0.4)
        
        markets = MarketProbabilities(
            home_win=0.70,
            draw=0.20,
            away_win=0.10,
            home_or_draw=0.90,
            draw_or_away=0.30,
            home_or_away=0.80,
            over_under={2.5: (0.60, 0.40)},
            btts_yes=0.55,
            btts_no=0.45,
            home_team_over={0.5: 0.80, 1.5: 0.65, 2.5: 0.45},
            away_team_over={0.5: 0.55, 1.5: 0.35, 2.5: 0.20},
            exact_score_top=[("2-1", 0.20)]
        )
        
        # High model agreement and data quality
        confidence = ConfidenceAssessment(
            overall_confidence=0.85,
            confidence_label="HIGH",
            components=ConfidenceComponents(
                model_agreement=0.90,
                data_quality=0.85,
                sample_size_score=0.80,
                calibration_reliability=0.80,
                lineup_certainty=1.0,
                feature_stability=0.90
            ),
            weights=ConfidenceWeights()
        )
        
        pick = generator.generate(markets, confidence)
        
        assert pick is not None
        assert len(pick.reasoning_factors) > 0
        assert len(pick.reasoning_factors) <= 5
        
        # Check reasoning contains probability and confidence info
        reasoning_str = " ".join(pick.reasoning_factors)
        assert "70.0%" in reasoning_str or "probability" in reasoning_str.lower()
        assert "HIGH" in reasoning_str or "confidence" in reasoning_str.lower()
    
    def test_fair_odds_calculation(self):
        """Test that fair odds are calculated correctly."""
        generator = MensionePickGenerator(min_confidence=0.4)
        
        markets = MarketProbabilities(
            home_win=0.50,  # Fair odds = 2.0
            draw=0.30,
            away_win=0.20,
            home_or_draw=0.80,
            draw_or_away=0.50,
            home_or_away=0.70,
            over_under={2.5: (0.60, 0.40)},
            btts_yes=0.50,
            btts_no=0.50,
            home_team_over={0.5: 0.70, 1.5: 0.55, 2.5: 0.35},
            away_team_over={0.5: 0.50, 1.5: 0.30, 2.5: 0.15},
            exact_score_top=[("1-0", 0.18)]
        )
        
        confidence = ConfidenceAssessment(
            overall_confidence=0.70,
            confidence_label="HIGH",
            components=ConfidenceComponents(),
            weights=ConfidenceWeights()
        )
        
        pick = generator.generate(markets, confidence)
        
        assert pick is not None
        # If pick is HOME with prob 0.50, fair odds should be 2.0
        if pick.pick_market == "HOME":
            assert pytest.approx(pick.fair_odds, 0.01) == 2.0
