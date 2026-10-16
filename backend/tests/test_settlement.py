"""Comprehensive tests for Phase 6 & 7: Result Ingestion and Settlement.

Tests cover:
- Settlement logic for all markets
- Frozen pick integrity
- Profit/loss calculation
- Track record aggregation
"""

import pytest
from datetime import datetime
from app.prediction.settlement import SettlementEngine, SettlementOutcome
from app.prediction.result_ingestion import MatchResult, ResultIngestionService
from app.domain.enums import MatchStatus, MatchOutcome


class TestMatchResultSettlement:
    """Test 1X2 market settlement."""
    
    def test_home_win_correct(self):
        """Test home win prediction wins when home wins."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=2,
            away_score=1,
            outcome=MatchOutcome.HOME_WIN,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, pl = engine.settle_prediction(
            selected_market="HOME_WIN",
            selection_text="Home Win",
            selection_odds=2.10,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.WIN
        assert pl == pytest.approx((2.10 - 1.0) * 1.0)
    
    def test_home_win_incorrect(self):
        """Test home win prediction loses when away wins."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=0,
            away_score=2,
            outcome=MatchOutcome.AWAY_WIN,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, pl = engine.settle_prediction(
            selected_market="HOME_WIN",
            selection_text="Home Win",
            selection_odds=2.10,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.LOSS
        assert pl == pytest.approx(-1.0)
    
    def test_draw_correct(self):
        """Test draw prediction wins when match draws."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=1,
            away_score=1,
            outcome=MatchOutcome.DRAW,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, pl = engine.settle_prediction(
            selected_market="DRAW",
            selection_text="Draw",
            selection_odds=3.20,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.WIN
        assert pl == pytest.approx((3.20 - 1.0) * 1.0)
    
    def test_away_win_correct(self):
        """Test away win prediction wins when away wins."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=1,
            away_score=3,
            outcome=MatchOutcome.AWAY_WIN,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, pl = engine.settle_prediction(
            selected_market="AWAY_WIN",
            selection_text="Away Win",
            selection_odds=2.50,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.WIN
        assert pl == pytest.approx((2.50 - 1.0) * 1.0)


class TestOverUnderSettlement:
    """Test Over/Under market settlement."""
    
    def test_over_25_wins(self):
        """Test over 2.5 wins when total goals > 2.5."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=2,
            away_score=1,
            outcome=MatchOutcome.HOME_WIN,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, pl = engine.settle_prediction(
            selected_market="OVER_2_5",
            selection_text="Over 2.5",
            selection_odds=1.90,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.WIN
        assert pl == pytest.approx((1.90 - 1.0) * 1.0)
    
    def test_over_25_loses(self):
        """Test over 2.5 loses when total goals < 2.5."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=1,
            away_score=0,
            outcome=MatchOutcome.HOME_WIN,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, pl = engine.settle_prediction(
            selected_market="OVER_2_5",
            selection_text="Over 2.5",
            selection_odds=1.90,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.LOSS
        assert pl == pytest.approx(-1.0)
    
    def test_under_25_wins(self):
        """Test under 2.5 wins when total goals < 2.5."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=1,
            away_score=1,
            outcome=MatchOutcome.DRAW,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, pl = engine.settle_prediction(
            selected_market="UNDER_2_5",
            selection_text="Under 2.5",
            selection_odds=2.05,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.WIN
        assert pl == pytest.approx((2.05 - 1.0) * 1.0)
    
    def test_over_3_0_push(self):
        """Test over 3.0 voids when total goals == 3.0 (push)."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=2,
            away_score=1,
            outcome=MatchOutcome.HOME_WIN,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, pl = engine.settle_prediction(
            selected_market="OVER_3_0",
            selection_text="Over 3.0",
            selection_odds=1.90,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.VOID
        assert pl == 0.0


class TestBTTSSettlement:
    """Test BTTS market settlement."""
    
    def test_btts_yes_correct(self):
        """Test BTTS yes wins when both teams score."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=2,
            away_score=1,
            outcome=MatchOutcome.HOME_WIN,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, pl = engine.settle_prediction(
            selected_market="BTTS_YES",
            selection_text="BTTS Yes",
            selection_odds=1.75,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.WIN
        assert pl == pytest.approx((1.75 - 1.0) * 1.0)
    
    def test_btts_yes_incorrect(self):
        """Test BTTS yes loses when one team doesn't score."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=2,
            away_score=0,
            outcome=MatchOutcome.HOME_WIN,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, pl = engine.settle_prediction(
            selected_market="BTTS_YES",
            selection_text="BTTS Yes",
            selection_odds=1.75,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.LOSS
        assert pl == pytest.approx(-1.0)
    
    def test_btts_no_correct(self):
        """Test BTTS no wins when one team doesn't score."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=3,
            away_score=0,
            outcome=MatchOutcome.HOME_WIN,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, pl = engine.settle_prediction(
            selected_market="BTTS_NO",
            selection_text="BTTS No",
            selection_odds=2.10,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.WIN
        assert pl == pytest.approx((2.10 - 1.0) * 1.0)


class TestDoubleChanceSettlement:
    """Test double chance market settlement."""
    
    def test_1x_home_win(self):
        """Test 1X wins on home win."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=2,
            away_score=1,
            outcome=MatchOutcome.HOME_WIN,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, pl = engine.settle_prediction(
            selected_market="1X",
            selection_text="1X",
            selection_odds=1.30,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.WIN
        assert pl == pytest.approx((1.30 - 1.0) * 1.0)
    
    def test_1x_draw(self):
        """Test 1X wins on draw."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=1,
            away_score=1,
            outcome=MatchOutcome.DRAW,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, pl = engine.settle_prediction(
            selected_market="1X",
            selection_text="1X",
            selection_odds=1.25,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.WIN
        assert pl == pytest.approx((1.25 - 1.0) * 1.0)
    
    def test_1x_away_loss(self):
        """Test 1X loses on away win."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=0,
            away_score=2,
            outcome=MatchOutcome.AWAY_WIN,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, pl = engine.settle_prediction(
            selected_market="1X",
            selection_text="1X",
            selection_odds=1.30,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.LOSS
        assert pl == pytest.approx(-1.0)
    
    def test_12_home_win(self):
        """Test 12 wins on home win."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=2,
            away_score=1,
            outcome=MatchOutcome.HOME_WIN,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, pl = engine.settle_prediction(
            selected_market="12",
            selection_text="12",
            selection_odds=1.20,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.WIN
        assert pl == pytest.approx((1.20 - 1.0) * 1.0)
    
    def test_12_away_win(self):
        """Test 12 wins on away win."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=1,
            away_score=3,
            outcome=MatchOutcome.AWAY_WIN,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, pl = engine.settle_prediction(
            selected_market="12",
            selection_text="12",
            selection_odds=1.18,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.WIN
        assert pl == pytest.approx((1.18 - 1.0) * 1.0)
    
    def test_12_draw_loss(self):
        """Test 12 loses on draw."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=1,
            away_score=1,
            outcome=MatchOutcome.DRAW,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, pl = engine.settle_prediction(
            selected_market="12",
            selection_text="12",
            selection_odds=1.20,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.LOSS
        assert pl == pytest.approx(-1.0)


class TestHandicapSettlement:
    """Test handicap market settlement."""
    
    def test_handicap_minus_15_home_win(self):
        """Test -1.5 home handicap wins."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=3,
            away_score=0,
            outcome=MatchOutcome.HOME_WIN,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, pl = engine.settle_prediction(
            selected_market="HANDICAP_-1.5_HOME",
            selection_text="Home -1.5",
            selection_odds=2.00,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.WIN
        assert pl == pytest.approx((2.00 - 1.0) * 1.0)
    
    def test_handicap_minus_15_home_loss(self):
        """Test -1.5 home handicap loses."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=2,
            away_score=1,
            outcome=MatchOutcome.HOME_WIN,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, pl = engine.settle_prediction(
            selected_market="HANDICAP_-1.5_HOME",
            selection_text="Home -1.5",
            selection_odds=2.00,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.LOSS
        assert pl == pytest.approx(-1.0)
    
    def test_handicap_plus_1_away_push(self):
        """Test +1 away handicap push."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=1,
            away_score=0,
            outcome=MatchOutcome.HOME_WIN,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, pl = engine.settle_prediction(
            selected_market="HANDICAP_+1_AWAY",
            selection_text="Away +1",
            selection_odds=1.85,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.VOID
        assert pl == 0.0


class TestVoidScenarios:
    """Test void/cancelled scenarios."""
    
    def test_postponed_match(self):
        """Test postponed match results in VOID."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.POSTPONED,
            home_score=None,
            away_score=None,
            outcome=None,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, pl = engine.settle_prediction(
            selected_market="HOME_WIN",
            selection_text="Home Win",
            selection_odds=2.10,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.VOID
        assert pl == 0.0
    
    def test_cancelled_match(self):
        """Test cancelled match results in VOID."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.CANCELLED,
            home_score=None,
            away_score=None,
            outcome=None,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        outcome, pl = engine.settle_prediction(
            selected_market="HOME_WIN",
            selection_text="Home Win",
            selection_odds=2.10,
            match_result=result
        )
        
        assert outcome == SettlementOutcome.VOID
        assert pl == 0.0


class TestInvalidScenarios:
    """Test invalid/unsupported scenarios."""
    
    def test_match_not_finished(self):
        """Test unsettleable match raises error."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.LIVE,
            home_score=1,
            away_score=0,
            outcome=None,
            is_final=False,
            fetched_at=datetime.utcnow()
        )
        
        with pytest.raises(ValueError, match="not settleable"):
            engine.settle_prediction(
                selected_market="HOME_WIN",
                selection_text="Home Win",
                selection_odds=2.10,
                match_result=result
            )
    
    def test_unsupported_market(self):
        """Test unsupported market raises error."""
        engine = SettlementEngine(stake=1.0)
        result = MatchResult(
            match_id="test",
            status=MatchStatus.FINISHED,
            home_score=2,
            away_score=1,
            outcome=MatchOutcome.HOME_WIN,
            is_final=True,
            fetched_at=datetime.utcnow()
        )
        
        with pytest.raises(ValueError, match="Cannot parse market type"):
            engine.settle_prediction(
                selected_market="CORRECT_SCORE",
                selection_text="2-1",
                selection_odds=12.00,
                match_result=result
            )
