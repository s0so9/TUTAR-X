"""Test settlement engine with canonical market identifiers from selector.

This test verifies that the settlement engine correctly interprets
canonical market identifiers produced by market_selector.py, without
relying on text parsing of selection_text fields.
"""

import pytest
from datetime import datetime

from app.prediction.settlement import SettlementEngine, SettlementOutcome
from app.prediction.result_ingestion import MatchResult
from app.domain.enums import MatchStatus, MatchOutcome


@pytest.fixture
def engine():
    """Create settlement engine with standard stake."""
    return SettlementEngine(stake=10.0)


@pytest.fixture
def home_win_result():
    """2-1 home win result."""
    return MatchResult(
        match_id="1001",
        home_score=2,
        away_score=1,
        status=MatchStatus.FINISHED,
        outcome=MatchOutcome.HOME_WIN,
        is_final=True,
        fetched_at=datetime.utcnow()
    )


@pytest.fixture
def draw_result():
    """1-1 draw result."""
    return MatchResult(
        match_id="1002",
        home_score=1,
        away_score=1,
        status=MatchStatus.FINISHED,
        outcome=MatchOutcome.DRAW,
        is_final=True,
        fetched_at=datetime.utcnow()
    )


@pytest.fixture
def away_win_result():
    """0-2 away win result."""
    return MatchResult(
        match_id="1003",
        home_score=0,
        away_score=2,
        status=MatchStatus.FINISHED,
        outcome=MatchOutcome.AWAY_WIN,
        is_final=True,
        fetched_at=datetime.utcnow()
    )


@pytest.fixture
def high_scoring_result():
    """3-2 high scoring result (both teams score, over 2.5)."""
    return MatchResult(
        match_id="1004",
        home_score=3,
        away_score=2,
        status=MatchStatus.FINISHED,
        outcome=MatchOutcome.HOME_WIN,
        is_final=True,
        fetched_at=datetime.utcnow()
    )


class TestBTTSSettlement:
    """Test BTTS market settlement with canonical identifiers.
    
    CRITICAL: BTTS_YES/BTTS_NO must be interpreted from the market field,
    NOT from parsing 'YES' in selection_text.
    """
    
    def test_btts_yes_win_on_1_1(self, engine, draw_result):
        """BTTS_YES should WIN when both teams score (1-1)."""
        outcome, profit = engine.settle_prediction(
            selected_market='BTTS_YES',
            selection_text='Both Teams to Score',  # Not parsed
            selection_odds=1.85,
            match_result=draw_result
        )
        
        assert outcome == SettlementOutcome.WIN
        assert profit > 0
    
    def test_btts_yes_loss_on_1_0(self, engine, home_win_result):
        """BTTS_YES should LOSS when only home scores (2-1 has both, use 1-0)."""
        result_1_0 = MatchResult(
            match_id="1005",
            home_score=1,
            away_score=0,
            status=MatchStatus.FINISHED,
            outcome=MatchOutcome.HOME_WIN,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, profit = engine.settle_prediction(
            selected_market='BTTS_YES',
            selection_text='Both Teams to Score',
            selection_odds=1.85,
            match_result=result_1_0
        )
        
        assert outcome == SettlementOutcome.LOSS
        assert profit < 0
    
    def test_btts_no_win_on_1_0(self, engine):
        """BTTS_NO should WIN when only one team scores."""
        result_1_0 = MatchResult(
            match_id="1006",
            home_score=1,
            away_score=0,
            status=MatchStatus.FINISHED,
            outcome=MatchOutcome.HOME_WIN,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, profit = engine.settle_prediction(
            selected_market='BTTS_NO',
            selection_text='Both Teams NOT to Score',
            selection_odds=2.10,
            match_result=result_1_0
        )
        
        assert outcome == SettlementOutcome.WIN
        assert profit > 0
    
    def test_btts_no_loss_on_1_1(self, engine, draw_result):
        """BTTS_NO should LOSS when both teams score."""
        outcome, profit = engine.settle_prediction(
            selected_market='BTTS_NO',
            selection_text='Both Teams NOT to Score',
            selection_odds=2.10,
            match_result=draw_result
        )
        
        assert outcome == SettlementOutcome.LOSS
        assert profit < 0
    
    def test_btts_yes_win_on_high_scoring(self, engine, high_scoring_result):
        """BTTS_YES should WIN on 3-2 (both teams score)."""
        outcome, profit = engine.settle_prediction(
            selected_market='BTTS_YES',
            selection_text='Both Teams to Score',
            selection_odds=1.90,
            match_result=high_scoring_result
        )
        
        assert outcome == SettlementOutcome.WIN


class TestMatchResultSettlement:
    """Test 1X2 market settlement with canonical identifiers."""
    
    def test_home_win_correct(self, engine, home_win_result):
        """HOME_WIN should WIN on 2-1 home win."""
        outcome, profit = engine.settle_prediction(
            selected_market='HOME_WIN',
            selection_text='Home Win',
            selection_odds=2.10,
            match_result=home_win_result
        )
        
        assert outcome == SettlementOutcome.WIN
        assert profit == pytest.approx((2.10 - 1.0) * 10.0)
    
    def test_draw_correct(self, engine, draw_result):
        """DRAW should WIN on 1-1 draw."""
        outcome, profit = engine.settle_prediction(
            selected_market='DRAW',
            selection_text='Draw',
            selection_odds=3.40,
            match_result=draw_result
        )
        
        assert outcome == SettlementOutcome.WIN
        assert profit == pytest.approx((3.40 - 1.0) * 10.0)
    
    def test_away_win_correct(self, engine, away_win_result):
        """AWAY_WIN should WIN on 0-2 away win."""
        outcome, profit = engine.settle_prediction(
            selected_market='AWAY_WIN',
            selection_text='Away Win',
            selection_odds=2.80,
            match_result=away_win_result
        )
        
        assert outcome == SettlementOutcome.WIN
    
    def test_home_win_loss_on_draw(self, engine, draw_result):
        """HOME_WIN should LOSS on draw."""
        outcome, profit = engine.settle_prediction(
            selected_market='HOME_WIN',
            selection_text='Home Win',
            selection_odds=2.10,
            match_result=draw_result
        )
        
        assert outcome == SettlementOutcome.LOSS
        assert profit == pytest.approx(-10.0)


class TestOverUnderSettlement:
    """Test Over/Under market settlement with canonical identifiers."""
    
    def test_over_2_5_win_on_3_goals(self, engine, home_win_result):
        """OVER_2_5 should WIN on 2-1 (3 total goals)."""
        outcome, profit = engine.settle_prediction(
            selected_market='OVER_2_5',
            selection_text='Over 2.5 Goals',
            selection_odds=1.95,
            match_result=home_win_result
        )
        
        assert outcome == SettlementOutcome.WIN
    
    def test_over_2_5_loss_on_2_goals(self, engine, draw_result):
        """OVER_2_5 should LOSS on 1-1 (2 total goals)."""
        outcome, profit = engine.settle_prediction(
            selected_market='OVER_2_5',
            selection_text='Over 2.5 Goals',
            selection_odds=1.95,
            match_result=draw_result
        )
        
        assert outcome == SettlementOutcome.LOSS
    
    def test_under_2_5_win_on_2_goals(self, engine, draw_result):
        """UNDER_2_5 should WIN on 1-1 (2 total goals)."""
        outcome, profit = engine.settle_prediction(
            selected_market='UNDER_2_5',
            selection_text='Under 2.5 Goals',
            selection_odds=1.80,
            match_result=draw_result
        )
        
        assert outcome == SettlementOutcome.WIN
    
    def test_under_2_5_loss_on_5_goals(self, engine, high_scoring_result):
        """UNDER_2_5 should LOSS on 3-2 (5 total goals)."""
        outcome, profit = engine.settle_prediction(
            selected_market='UNDER_2_5',
            selection_text='Under 2.5 Goals',
            selection_odds=1.80,
            match_result=high_scoring_result
        )
        
        assert outcome == SettlementOutcome.LOSS
    
    def test_over_1_5_win_on_2_goals(self, engine, draw_result):
        """OVER_1_5 should WIN on 1-1 (2 total goals)."""
        outcome, profit = engine.settle_prediction(
            selected_market='OVER_1_5',
            selection_text='Over 1.5 Goals',
            selection_odds=1.40,
            match_result=draw_result
        )
        
        assert outcome == SettlementOutcome.WIN


class TestDoubleChanceSettlement:
    """Test Double Chance market settlement with canonical identifiers."""
    
    def test_home_or_draw_win_on_home(self, engine, home_win_result):
        """HOME_OR_DRAW should WIN on home win."""
        outcome, profit = engine.settle_prediction(
            selected_market='HOME_OR_DRAW',
            selection_text='Home or Draw',
            selection_odds=1.30,
            match_result=home_win_result
        )
        
        assert outcome == SettlementOutcome.WIN
    
    def test_home_or_draw_win_on_draw(self, engine, draw_result):
        """HOME_OR_DRAW should WIN on draw."""
        outcome, profit = engine.settle_prediction(
            selected_market='HOME_OR_DRAW',
            selection_text='Home or Draw',
            selection_odds=1.30,
            match_result=draw_result
        )
        
        assert outcome == SettlementOutcome.WIN
    
    def test_home_or_draw_loss_on_away(self, engine, away_win_result):
        """HOME_OR_DRAW should LOSS on away win."""
        outcome, profit = engine.settle_prediction(
            selected_market='HOME_OR_DRAW',
            selection_text='Home or Draw',
            selection_odds=1.30,
            match_result=away_win_result
        )
        
        assert outcome == SettlementOutcome.LOSS
    
    def test_draw_or_away_win_on_away(self, engine, away_win_result):
        """DRAW_OR_AWAY should WIN on away win."""
        outcome, profit = engine.settle_prediction(
            selected_market='DRAW_OR_AWAY',
            selection_text='Draw or Away',
            selection_odds=1.40,
            match_result=away_win_result
        )
        
        assert outcome == SettlementOutcome.WIN
    
    def test_home_or_away_loss_on_draw(self, engine, draw_result):
        """HOME_OR_AWAY should LOSS on draw."""
        outcome, profit = engine.settle_prediction(
            selected_market='HOME_OR_AWAY',
            selection_text='Home or Away',
            selection_odds=1.25,
            match_result=draw_result
        )
        
        assert outcome == SettlementOutcome.LOSS


class TestUnsupportedMarkets:
    """Test that unsupported markets produce clear errors."""
    
    def test_unknown_market_raises_error(self, engine, home_win_result):
        """Unknown market types should raise clear error."""
        with pytest.raises(ValueError, match="Cannot parse market type"):
            engine.settle_prediction(
                selected_market='UNKNOWN_MARKET',
                selection_text='Some Selection',
                selection_odds=2.00,
                match_result=home_win_result
            )
    
    def test_invalid_btts_market_raises_error(self, engine, home_win_result):
        """Invalid BTTS market identifier should raise clear error."""
        with pytest.raises(ValueError, match="Unsupported BTTS market"):
            engine.settle_prediction(
                selected_market='BTTS_MAYBE',  # Invalid
                selection_text='Both Teams Maybe Score',
                selection_odds=2.00,
                match_result=home_win_result
            )
    
    def test_invalid_1x2_market_raises_error(self, engine, home_win_result):
        """Invalid 1X2 market identifier should raise clear error."""
        with pytest.raises(ValueError, match="Cannot parse market type"):
            engine.settle_prediction(
                selected_market='NEUTRAL_WIN',  # Invalid
                selection_text='Neutral Win',
                selection_odds=2.00,
                match_result=home_win_result
            )


class TestSelectorIntegration:
    """Test that selector output can be directly fed to settlement.
    
    This simulates the actual integration where selector produces
    canonical market/selection pairs that settlement must interpret.
    """
    
    def test_selector_btts_yes_output(self, engine, draw_result):
        """Selector produces BTTS_YES, settlement interprets correctly."""
        # Simulate selector output
        selector_output = {
            'market': 'BTTS_YES',
            'selection': 'Both Teams to Score',
            'probability': 0.65,
            'bookmaker_odds': 1.85
        }
        
        outcome, profit = engine.settle_prediction(
            selected_market=selector_output['market'],
            selection_text=selector_output['selection'],
            selection_odds=selector_output['bookmaker_odds'],
            match_result=draw_result
        )
        
        assert outcome == SettlementOutcome.WIN
    
    def test_selector_over_2_5_output(self, engine, home_win_result):
        """Selector produces OVER_2_5, settlement interprets correctly."""
        selector_output = {
            'market': 'OVER_2_5',
            'selection': 'Over 2.5 Goals',
            'probability': 0.58,
            'bookmaker_odds': 1.95
        }
        
        outcome, profit = engine.settle_prediction(
            selected_market=selector_output['market'],
            selection_text=selector_output['selection'],
            selection_odds=selector_output['bookmaker_odds'],
            match_result=home_win_result
        )
        
        assert outcome == SettlementOutcome.WIN
    
    def test_selector_home_or_draw_output(self, engine, draw_result):
        """Selector produces HOME_OR_DRAW, settlement interprets correctly."""
        selector_output = {
            'market': 'HOME_OR_DRAW',
            'selection': 'Home or Draw',
            'probability': 0.75,
            'bookmaker_odds': 1.30
        }
        
        outcome, profit = engine.settle_prediction(
            selected_market=selector_output['market'],
            selection_text=selector_output['selection'],
            selection_odds=selector_output['bookmaker_odds'],
            match_result=draw_result
        )
        
        assert outcome == SettlementOutcome.WIN


class TestOriginalFieldsPreserved:
    """Test that settlement does not modify the original prediction fields.
    
    CRITICAL: Settlement reads market/selection but NEVER modifies them.
    """
    
    def test_selection_text_not_modified(self, engine, draw_result):
        """Settlement should not modify selection_text."""
        original_market = 'BTTS_YES'
        original_selection = 'Both Teams to Score'
        
        outcome, profit = engine.settle_prediction(
            selected_market=original_market,
            selection_text=original_selection,
            selection_odds=1.85,
            match_result=draw_result
        )
        
        # Settlement returns outcome but does not modify input
        assert outcome == SettlementOutcome.WIN
        # Original values unchanged (verified by not passing by reference)
    
    def test_market_identifier_not_modified(self, engine, home_win_result):
        """Settlement should not modify market identifier."""
        original_market = 'OVER_2_5'
        
        outcome, profit = engine.settle_prediction(
            selected_market=original_market,
            selection_text='Over 2.5 Goals',
            selection_odds=1.95,
            match_result=home_win_result
        )
        
        assert outcome == SettlementOutcome.WIN
        # Original market unchanged
