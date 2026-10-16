"""Simple integration test: Verify settlement accepts canonical identifiers.

Tests that canonical market identifiers (BTTS_YES, HOME_WIN, OVER_2_5, etc.)
produced by the prediction pipeline can be directly settled.
"""

import pytest
from datetime import datetime, UTC

from app.prediction.settlement import SettlementEngine, SettlementOutcome
from app.prediction.result_ingestion import MatchResult
from app.domain.enums import MatchStatus, MatchOutcome


@pytest.fixture
def engine():
    """Settlement engine."""
    return SettlementEngine(stake=10.0)


class TestCanonicalIdentifierAcceptance:
    """Test that all canonical identifiers are accepted by settlement."""
    
    def test_all_1x2_markets(self, engine):
        """Test all 1X2 canonical identifiers."""
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=2,
            away_score=1,
            outcome=MatchOutcome.HOME_WIN,
            is_final=True,
            fetched_at=datetime.now(UTC)
        )
        
        # HOME_WIN should WIN
        outcome, _ = engine.settle_prediction(
            selected_market='HOME_WIN',
            selection_text='Home Win',
            selection_odds=2.10,
            match_result=result
        )
        assert outcome == SettlementOutcome.WIN
        
        # DRAW should LOSS
        outcome, _ = engine.settle_prediction(
            selected_market='DRAW',
            selection_text='Draw',
            selection_odds=3.40,
            match_result=result
        )
        assert outcome == SettlementOutcome.LOSS
        
        # AWAY_WIN should LOSS
        outcome, _ = engine.settle_prediction(
            selected_market='AWAY_WIN',
            selection_text='Away Win',
            selection_odds=3.50,
            match_result=result
        )
        assert outcome == SettlementOutcome.LOSS
    
    def test_all_btts_markets(self, engine):
        """Test BTTS canonical identifiers."""
        result_both_scored = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=1,
            away_score=1,
            outcome=MatchOutcome.DRAW,
            is_final=True,
            fetched_at=datetime.now(UTC)
        )
        
        result_only_home = MatchResult(
            match_id="test2",
            status=MatchStatus.FINISHED,
            home_score=2,
            away_score=0,
            outcome=MatchOutcome.HOME_WIN,
            is_final=True,
            fetched_at=datetime.now(UTC)
        )
        
        # BTTS_YES when both scored
        outcome, _ = engine.settle_prediction(
            selected_market='BTTS_YES',
            selection_text='Both Teams to Score',
            selection_odds=1.85,
            match_result=result_both_scored
        )
        assert outcome == SettlementOutcome.WIN
        
        # BTTS_YES when only one scored
        outcome, _ = engine.settle_prediction(
            selected_market='BTTS_YES',
            selection_text='Both Teams to Score',
            selection_odds=1.85,
            match_result=result_only_home
        )
        assert outcome == SettlementOutcome.LOSS
        
        # BTTS_NO when only one scored
        outcome, _ = engine.settle_prediction(
            selected_market='BTTS_NO',
            selection_text='Both Teams NOT to Score',
            selection_odds=2.10,
            match_result=result_only_home
        )
        assert outcome == SettlementOutcome.WIN
    
    def test_all_over_under_markets(self, engine):
        """Test Over/Under canonical identifiers."""
        result_3_goals = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=2,
            away_score=1,
            outcome=MatchOutcome.HOME_WIN,
            is_final=True,
            fetched_at=datetime.now(UTC)
        )
        
        # OVER_2_5 with 3 goals
        outcome, _ = engine.settle_prediction(
            selected_market='OVER_2_5',
            selection_text='Over 2.5 Goals',
            selection_odds=1.95,
            match_result=result_3_goals
        )
        assert outcome == SettlementOutcome.WIN
        
        # UNDER_2_5 with 3 goals
        outcome, _ = engine.settle_prediction(
            selected_market='UNDER_2_5',
            selection_text='Under 2.5 Goals',
            selection_odds=1.90,
            match_result=result_3_goals
        )
        assert outcome == SettlementOutcome.LOSS
        
        # OVER_1_5 with 3 goals
        outcome, _ = engine.settle_prediction(
            selected_market='OVER_1_5',
            selection_text='Over 1.5 Goals',
            selection_odds=1.40,
            match_result=result_3_goals
        )
        assert outcome == SettlementOutcome.WIN
        
        # OVER_3_5 with 3 goals
        outcome, _ = engine.settle_prediction(
            selected_market='OVER_3_5',
            selection_text='Over 3.5 Goals',
            selection_odds=2.80,
            match_result=result_3_goals
        )
        assert outcome == SettlementOutcome.LOSS
    
    def test_all_double_chance_markets(self, engine):
        """Test Double Chance canonical identifiers."""
        result_home = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=2,
            away_score=1,
            outcome=MatchOutcome.HOME_WIN,
            is_final=True,
            fetched_at=datetime.now(UTC)
        )
        
        result_draw = MatchResult(
            match_id="test2",
            status=MatchStatus.FINISHED,
            home_score=1,
            away_score=1,
            outcome=MatchOutcome.DRAW,
            is_final=True,
            fetched_at=datetime.now(UTC)
        )
        
        result_away = MatchResult(
            match_id="test3",
            status=MatchStatus.FINISHED,
            home_score=0,
            away_score=2,
            outcome=MatchOutcome.AWAY_WIN,
            is_final=True,
            fetched_at=datetime.now(UTC)
        )
        
        # HOME_OR_DRAW
        outcome, _ = engine.settle_prediction(
            selected_market='HOME_OR_DRAW',
            selection_text='Home or Draw',
            selection_odds=1.35,
            match_result=result_home
        )
        assert outcome == SettlementOutcome.WIN
        
        outcome, _ = engine.settle_prediction(
            selected_market='HOME_OR_DRAW',
            selection_text='Home or Draw',
            selection_odds=1.35,
            match_result=result_draw
        )
        assert outcome == SettlementOutcome.WIN
        
        outcome, _ = engine.settle_prediction(
            selected_market='HOME_OR_DRAW',
            selection_text='Home or Draw',
            selection_odds=1.35,
            match_result=result_away
        )
        assert outcome == SettlementOutcome.LOSS
        
        # DRAW_OR_AWAY
        outcome, _ = engine.settle_prediction(
            selected_market='DRAW_OR_AWAY',
            selection_text='Draw or Away',
            selection_odds=1.50,
            match_result=result_away
        )
        assert outcome == SettlementOutcome.WIN
        
        # HOME_OR_AWAY
        outcome, _ = engine.settle_prediction(
            selected_market='HOME_OR_AWAY',
            selection_text='Home or Away',
            selection_odds=1.25,
            match_result=result_draw
        )
        assert outcome == SettlementOutcome.LOSS


class TestInternationalizationReadiness:
    """Test that settlement works regardless of selection_text language."""
    
    def test_btts_with_turkish_selection_text(self, engine):
        """Test BTTS with Turkish display text."""
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=1,
            away_score=1,
            outcome=MatchOutcome.DRAW,
            is_final=True,
            fetched_at=datetime.now(UTC)
        )
        
        # Turkish text - settlement should still work
        outcome, _ = engine.settle_prediction(
            selected_market='BTTS_YES',
            selection_text='İki Takım da Gol Atar',
            selection_odds=1.90,
            match_result=result
        )
        assert outcome == SettlementOutcome.WIN
    
    def test_over_under_with_turkish_selection_text(self, engine):
        """Test Over/Under with Turkish display text."""
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=2,
            away_score=2,
            outcome=MatchOutcome.DRAW,
            is_final=True,
            fetched_at=datetime.now(UTC)
        )
        
        # Turkish text
        outcome, _ = engine.settle_prediction(
            selected_market='OVER_2_5',
            selection_text='Üst 2.5 Gol',
            selection_odds=2.00,
            match_result=result
        )
        assert outcome == SettlementOutcome.WIN  # 4 goals > 2.5
    
    def test_match_result_with_custom_text(self, engine):
        """Test 1X2 with custom formatted text."""
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=3,
            away_score=1,
            outcome=MatchOutcome.HOME_WIN,
            is_final=True,
            fetched_at=datetime.now(UTC)
        )
        
        # Custom format without keywords
        outcome, _ = engine.settle_prediction(
            selected_market='HOME_WIN',
            selection_text='Ev Sahibi Galibiyeti 🏠',
            selection_odds=1.75,
            match_result=result
        )
        assert outcome == SettlementOutcome.WIN


class TestProfitCalculations:
    """Test profit/loss calculations."""
    
    def test_win_profit_calculation(self, engine):
        """Test profit on winning bet."""
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=2,
            away_score=1,
            outcome=MatchOutcome.HOME_WIN,
            is_final=True,
            fetched_at=datetime.now(UTC)
        )
        
        outcome, profit = engine.settle_prediction(
            selected_market='HOME_WIN',
            selection_text='Home Win',
            selection_odds=2.50,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.WIN
        # Profit = (odds - 1) * stake = (2.50 - 1) * 10 = 15.0
        assert profit == pytest.approx(15.0)
    
    def test_loss_profit_calculation(self, engine):
        """Test loss on losing bet."""
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=0,
            away_score=2,
            outcome=MatchOutcome.AWAY_WIN,
            is_final=True,
            fetched_at=datetime.now(UTC)
        )
        
        outcome, profit = engine.settle_prediction(
            selected_market='HOME_WIN',
            selection_text='Home Win',
            selection_odds=2.10,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.LOSS
        # Loss = -stake = -10.0
        assert profit == pytest.approx(-10.0)
    
    def test_void_profit_calculation(self, engine):
        """Test void returns stake."""
        result = MatchResult(
            match_id="test",
            status=MatchStatus.POSTPONED,
            home_score=None,
            away_score=None,
            outcome=None,
            is_final=True,
            fetched_at=datetime.now(UTC)
        )
        
        outcome, profit = engine.settle_prediction(
            selected_market='HOME_WIN',
            selection_text='Home Win',
            selection_odds=2.10,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.VOID
        # Void = 0 profit/loss
        assert profit == pytest.approx(0.0)


class TestRealWorldScenario:
    """Test realistic match scenarios."""
    
    def test_high_scoring_match_multiple_markets(self, engine):
        """Test 3-2 match with multiple markets."""
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=3,
            away_score=2,
            outcome=MatchOutcome.HOME_WIN,
            is_final=True,
            fetched_at=datetime.now(UTC)
        )
        
        # HOME_WIN ✓
        outcome, _ = engine.settle_prediction(
            selected_market='HOME_WIN',
            selection_text='Home Win',
            selection_odds=2.30,
            match_result=result
        )
        assert outcome == SettlementOutcome.WIN
        
        # OVER_2_5 ✓ (5 goals)
        outcome, _ = engine.settle_prediction(
            selected_market='OVER_2_5',
            selection_text='Over 2.5',
            selection_odds=1.85,
            match_result=result
        )
        assert outcome == SettlementOutcome.WIN
        
        # OVER_4_5 ✓ (5 goals)
        outcome, _ = engine.settle_prediction(
            selected_market='OVER_4_5',
            selection_text='Over 4.5',
            selection_odds=3.50,
            match_result=result
        )
        assert outcome == SettlementOutcome.WIN
        
        # OVER_5_5 ✗ (5 goals)
        outcome, _ = engine.settle_prediction(
            selected_market='OVER_5_5',
            selection_text='Over 5.5',
            selection_odds=6.00,
            match_result=result
        )
        assert outcome == SettlementOutcome.LOSS
        
        # BTTS_YES ✓
        outcome, _ = engine.settle_prediction(
            selected_market='BTTS_YES',
            selection_text='BTTS',
            selection_odds=1.70,
            match_result=result
        )
        assert outcome == SettlementOutcome.WIN
        
        # HOME_OR_DRAW ✓
        outcome, _ = engine.settle_prediction(
            selected_market='HOME_OR_DRAW',
            selection_text='1X',
            selection_odds=1.30,
            match_result=result
        )
        assert outcome == SettlementOutcome.WIN
    
    def test_low_scoring_draw(self, engine):
        """Test 0-0 draw with multiple markets."""
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=0,
            away_score=0,
            outcome=MatchOutcome.DRAW,
            is_final=True,
            fetched_at=datetime.now(UTC)
        )
        
        # DRAW ✓
        outcome, _ = engine.settle_prediction(
            selected_market='DRAW',
            selection_text='Draw',
            selection_odds=3.20,
            match_result=result
        )
        assert outcome == SettlementOutcome.WIN
        
        # UNDER_0_5 ✓ (0 goals)
        outcome, _ = engine.settle_prediction(
            selected_market='UNDER_0_5',
            selection_text='Under 0.5',
            selection_odds=4.50,
            match_result=result
        )
        assert outcome == SettlementOutcome.WIN
        
        # BTTS_NO ✓ (no goals)
        outcome, _ = engine.settle_prediction(
            selected_market='BTTS_NO',
            selection_text='BTTS No',
            selection_odds=1.80,
            match_result=result
        )
        assert outcome == SettlementOutcome.WIN
        
        # HOME_WIN ✗
        outcome, _ = engine.settle_prediction(
            selected_market='HOME_WIN',
            selection_text='Home',
            selection_odds=2.10,
            match_result=result
        )
        assert outcome == SettlementOutcome.LOSS
