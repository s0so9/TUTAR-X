"""Tests for Phase 5 FEAT-001: Canonical Market Model + Real Odds Normalization."""

import pytest
from datetime import datetime

from app.providers.development import DevelopmentProvider
from app.domain.odds import Odds
from app.domain.enums import PredictionMarketType


class TestPhase5FEAT001:
    """Test Phase 5 FEAT-001 implementation."""
    
    def test_development_provider_returns_odds_with_phase5_fields(self):
        """Test DevelopmentProvider returns odds with Phase 5 fields populated."""
        provider = DevelopmentProvider()
        
        # Get odds for a known match
        match_odds = provider.get_match_odds("dev_match_001")
        
        assert len(match_odds) > 0, "DevelopmentProvider should return odds"
        
        odds = match_odds[0]
        
        # Check Phase 5 fields are populated
        assert odds.source_provider == "development"
        assert odds.normalized_market_type == "match_result"
        assert odds.selection_label == "home"
        assert odds.odds_timestamp is not None
        assert isinstance(odds.odds_timestamp, datetime)
        
        # Check existing fields still work
        assert odds.bookmaker == "[DEV] Mock Bookmaker"
        assert odds.home_win_odds == 2.10
        assert odds.draw_odds == 3.40
        assert odds.away_win_odds == 3.60
        
    def test_development_provider_odds_are_deterministic(self):
        """Test DevelopmentProvider returns deterministic odds."""
        provider = DevelopmentProvider()
        
        # Get odds twice
        odds1 = provider.get_match_odds("dev_match_001")
        odds2 = provider.get_match_odds("dev_match_001")
        
        assert len(odds1) == len(odds2)
        assert odds1[0].home_win_odds == odds2[0].home_win_odds
        assert odds1[0].source_provider == odds2[0].source_provider
        
    def test_development_provider_no_odds_for_invalid_match(self):
        """Test DevelopmentProvider returns empty list for invalid match."""
        provider = DevelopmentProvider()
        
        odds = provider.get_match_odds("invalid_match_id")
        
        assert odds == []
        
    def test_prediction_market_type_includes_double_chance_and_handicap(self):
        """Test PredictionMarketType enum includes Phase 5 market types."""
        # Verify Phase 5 market types exist
        assert hasattr(PredictionMarketType, "DOUBLE_CHANCE")
        assert hasattr(PredictionMarketType, "HANDICAP")
        
        # Verify values
        assert PredictionMarketType.DOUBLE_CHANCE.value == "double_chance"
        assert PredictionMarketType.HANDICAP.value == "handicap"
        
        # Verify existing types still exist
        assert PredictionMarketType.MATCH_RESULT.value == "match_result"
        assert PredictionMarketType.OVER_UNDER.value == "over_under"
        assert PredictionMarketType.BTTS.value == "btts"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
