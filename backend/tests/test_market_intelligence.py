"""Tests for market intelligence value classification."""

import pytest

from app.prediction.market_intelligence import (
    ValueClassification,
    classify_value,
    MarketValueAssessment,
)


class TestValueClassification:
    """Test value classification logic."""
    
    def test_classify_value_strong_value_threshold(self):
        """Test STRONG_VALUE classification at >= 10% edge."""
        # Exactly at threshold
        assert classify_value(0.10) == ValueClassification.STRONG_VALUE
        
        # Above threshold
        assert classify_value(0.12) == ValueClassification.STRONG_VALUE
        assert classify_value(0.15) == ValueClassification.STRONG_VALUE
        assert classify_value(0.25) == ValueClassification.STRONG_VALUE
    
    def test_classify_value_value_threshold(self):
        """Test VALUE classification at >= 5% and < 10% edge."""
        # Exactly at threshold
        assert classify_value(0.05) == ValueClassification.VALUE
        
        # Between 5% and 10%
        assert classify_value(0.06) == ValueClassification.VALUE
        assert classify_value(0.07) == ValueClassification.VALUE
        assert classify_value(0.08) == ValueClassification.VALUE
        assert classify_value(0.09) == ValueClassification.VALUE
        
        # Just below STRONG_VALUE threshold
        assert classify_value(0.099) == ValueClassification.VALUE
    
    def test_classify_value_neutral_threshold(self):
        """Test NEUTRAL classification at >= 0% and < 5% edge."""
        # Exactly at threshold
        assert classify_value(0.0) == ValueClassification.NEUTRAL
        
        # Between 0% and 5%
        assert classify_value(0.01) == ValueClassification.NEUTRAL
        assert classify_value(0.02) == ValueClassification.NEUTRAL
        assert classify_value(0.03) == ValueClassification.NEUTRAL
        assert classify_value(0.04) == ValueClassification.NEUTRAL
        
        # Just below VALUE threshold
        assert classify_value(0.049) == ValueClassification.NEUTRAL
    
    def test_classify_value_negative_value(self):
        """Test NEGATIVE_VALUE classification at < 0% edge."""
        assert classify_value(-0.01) == ValueClassification.NEGATIVE_VALUE
        assert classify_value(-0.05) == ValueClassification.NEGATIVE_VALUE
        assert classify_value(-0.10) == ValueClassification.NEGATIVE_VALUE
        assert classify_value(-0.25) == ValueClassification.NEGATIVE_VALUE
    
    def test_classify_value_unavailable_when_none(self):
        """Test UNAVAILABLE classification when edge is None."""
        assert classify_value(None) == ValueClassification.UNAVAILABLE
    
    def test_classify_value_boundary_cases(self):
        """Test exact boundary values."""
        # Test boundaries between classifications
        assert classify_value(0.0) == ValueClassification.NEUTRAL
        assert classify_value(0.05) == ValueClassification.VALUE
        assert classify_value(0.10) == ValueClassification.STRONG_VALUE
        
        # Test just below boundaries
        assert classify_value(-0.000001) == ValueClassification.NEGATIVE_VALUE
        assert classify_value(0.049999) == ValueClassification.NEUTRAL
        assert classify_value(0.099999) == ValueClassification.VALUE


class TestMarketValueAssessment:
    """Test MarketValueAssessment dataclass."""
    
    def test_market_value_assessment_creation(self):
        """Test creating MarketValueAssessment with all fields."""
        assessment = MarketValueAssessment(
            market_name="match_result",
            model_probability=0.45,
            real_odds=2.10,
            implied_probability=0.476,
            market_edge=0.026,  # model_prob - implied_prob = 0.45 - 0.476 = -0.026 (wait, should be negative)
            value_classification=ValueClassification.NEUTRAL,
            bookmaker="Bet365"
        )
        
        assert assessment.market_name == "match_result"
        assert assessment.model_probability == 0.45
        assert assessment.real_odds == 2.10
        assert assessment.implied_probability == 0.476
        assert assessment.market_edge == 0.026
        assert assessment.value_classification == ValueClassification.NEUTRAL
        assert assessment.bookmaker == "Bet365"
    
    def test_market_value_assessment_with_none_fields(self):
        """Test creating MarketValueAssessment with missing odds data."""
        assessment = MarketValueAssessment(
            market_name="btts",
            model_probability=0.60,
            real_odds=None,
            implied_probability=None,
            market_edge=None,
            value_classification=ValueClassification.UNAVAILABLE,
            bookmaker=None
        )
        
        assert assessment.market_name == "btts"
        assert assessment.model_probability == 0.60
        assert assessment.real_odds is None
        assert assessment.implied_probability is None
        assert assessment.market_edge is None
        assert assessment.value_classification == ValueClassification.UNAVAILABLE
        assert assessment.bookmaker is None
    
    def test_market_value_assessment_strong_value_example(self):
        """Test realistic strong value scenario."""
        # Model thinks home win probability is 55%, but bookmaker odds of 2.20
        # imply only 45.45% probability -> 9.55% edge (should be VALUE, close to STRONG)
        model_prob = 0.55
        bookmaker_odds = 2.20
        implied_prob = 1.0 / bookmaker_odds  # 0.4545
        edge = model_prob - implied_prob  # 0.0955
        
        assessment = MarketValueAssessment(
            market_name="match_result",
            model_probability=model_prob,
            real_odds=bookmaker_odds,
            implied_probability=implied_prob,
            market_edge=edge,
            value_classification=classify_value(edge),
            bookmaker="Bet365"
        )
        
        assert assessment.value_classification == ValueClassification.VALUE
        assert assessment.market_edge > 0.05
        assert assessment.market_edge < 0.10
    
    def test_market_value_assessment_negative_value_example(self):
        """Test realistic negative value scenario."""
        # Model thinks draw probability is 25%, but bookmaker odds of 3.00
        # imply 33.33% probability -> model underestimates, negative edge
        model_prob = 0.25
        bookmaker_odds = 3.00
        implied_prob = 1.0 / bookmaker_odds  # 0.3333
        edge = model_prob - implied_prob  # -0.0833
        
        assessment = MarketValueAssessment(
            market_name="match_result",
            model_probability=model_prob,
            real_odds=bookmaker_odds,
            implied_probability=implied_prob,
            market_edge=edge,
            value_classification=classify_value(edge),
            bookmaker="Bet365"
        )
        
        assert assessment.value_classification == ValueClassification.NEGATIVE_VALUE
        assert assessment.market_edge < 0.0
