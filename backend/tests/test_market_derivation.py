"""Tests for market derivation engine."""

import pytest
from app.prediction.market_derivation import MarketDerivationEngine, MarketProbabilities


class TestMarketDerivationEngine:
    """Test MarketDerivationEngine."""
    
    def test_derive_1x2_from_distribution(self):
        """Test 1X2 derivation from score distribution."""
        engine = MarketDerivationEngine()
        
        # Simple distribution: home favorites
        distribution = {
            (2, 0): 0.25,  # home win
            (1, 0): 0.20,  # home win
            (1, 1): 0.15,  # draw
            (0, 0): 0.10,  # draw
            (0, 1): 0.15,  # away win
            (0, 2): 0.15,  # away win
        }
        
        markets = engine.derive(distribution)
        
        # Check 1X2
        assert pytest.approx(markets.home_win, 0.01) == 0.45  # 0.25 + 0.20
        assert pytest.approx(markets.draw, 0.01) == 0.25  # 0.15 + 0.10
        assert pytest.approx(markets.away_win, 0.01) == 0.30  # 0.15 + 0.15
        
        # Check probabilities sum to 1.0
        assert pytest.approx(markets.home_win + markets.draw + markets.away_win) == 1.0
    
    def test_derive_double_chance(self):
        """Test double chance market derivation."""
        engine = MarketDerivationEngine()
        
        distribution = {
            (2, 0): 0.40,  # home win
            (1, 1): 0.30,  # draw
            (0, 2): 0.30,  # away win
        }
        
        markets = engine.derive(distribution)
        
        # Check double chance
        assert pytest.approx(markets.home_or_draw) == 0.70  # home + draw
        assert pytest.approx(markets.draw_or_away) == 0.60  # draw + away
        assert pytest.approx(markets.home_or_away) == 0.70  # home + away
    
    def test_derive_over_under(self):
        """Test over/under market derivation."""
        engine = MarketDerivationEngine()
        
        distribution = {
            (0, 0): 0.10,  # total = 0
            (1, 0): 0.15,  # total = 1
            (0, 1): 0.15,  # total = 1
            (1, 1): 0.20,  # total = 2
            (2, 1): 0.20,  # total = 3
            (2, 2): 0.20,  # total = 4
        }
        
        markets = engine.derive(distribution)
        
        # Over/Under 1.5
        over_1_5, under_1_5 = markets.over_under[1.5]
        assert pytest.approx(over_1_5, 0.01) == 0.60  # total > 1.5: 2+1=3, 2+2=4
        assert pytest.approx(under_1_5, 0.01) == 0.40  # total <= 1.5
        assert pytest.approx(over_1_5 + under_1_5) == 1.0
        
        # Over/Under 2.5
        over_2_5, under_2_5 = markets.over_under[2.5]
        assert pytest.approx(over_2_5, 0.01) == 0.40  # total > 2.5
        assert pytest.approx(under_2_5, 0.01) == 0.60
        assert pytest.approx(over_2_5 + under_2_5) == 1.0
    
    def test_derive_btts(self):
        """Test BTTS market derivation."""
        engine = MarketDerivationEngine()
        
        distribution = {
            (0, 0): 0.10,  # btts no
            (1, 0): 0.20,  # btts no
            (0, 1): 0.10,  # btts no
            (1, 1): 0.30,  # btts yes
            (2, 1): 0.20,  # btts yes
            (1, 2): 0.10,  # btts yes
        }
        
        markets = engine.derive(distribution)
        
        # BTTS YES: both teams score (h>0 AND a>0)
        assert pytest.approx(markets.btts_yes, 0.01) == 0.60  # 0.30 + 0.20 + 0.10
        assert pytest.approx(markets.btts_no, 0.01) == 0.40
        assert pytest.approx(markets.btts_yes + markets.btts_no) == 1.0
    
    def test_derive_team_totals(self):
        """Test team totals market derivation."""
        engine = MarketDerivationEngine()
        
        distribution = {
            (0, 0): 0.10,
            (1, 0): 0.20,
            (2, 0): 0.30,
            (3, 0): 0.20,
            (0, 1): 0.10,
            (0, 2): 0.10,
        }
        
        markets = engine.derive(distribution)
        
        # Home team over 0.5
        assert pytest.approx(markets.home_team_over[0.5], 0.01) == 0.70  # h > 0.5
        
        # Home team over 1.5
        assert pytest.approx(markets.home_team_over[1.5], 0.01) == 0.50  # h > 1.5
        
        # Away team over 0.5
        assert pytest.approx(markets.away_team_over[0.5], 0.01) == 0.20  # a > 0.5
    
    def test_derive_exact_score(self):
        """Test exact score top N derivation."""
        engine = MarketDerivationEngine(top_scorelines=3)
        
        distribution = {
            (1, 0): 0.25,
            (2, 0): 0.20,
            (1, 1): 0.15,
            (0, 0): 0.10,
            (2, 1): 0.10,
            (3, 0): 0.10,
            (0, 1): 0.10,
        }
        
        markets = engine.derive(distribution)
        
        # Top 3 scorelines
        assert len(markets.exact_score_top) == 3
        assert markets.exact_score_top[0] == ("1-0", 0.25)
        assert markets.exact_score_top[1] == ("2-0", 0.20)
        assert markets.exact_score_top[2] == ("1-1", 0.15)
    
    def test_derive_asian_handicap(self):
        """Test Asian handicap derivation."""
        engine = MarketDerivationEngine()
        
        distribution = {
            (2, 0): 0.30,  # home wins by 2
            (1, 0): 0.30,  # home wins by 1
            (0, 0): 0.20,  # draw
            (0, 1): 0.20,  # away wins by 1
        }
        
        markets = engine.derive(distribution)
        
        # Handicap -0.5 (home must win)
        home_win, push, away_win = markets.asian_handicap[-0.5]
        assert pytest.approx(home_win, 0.01) == 0.60  # home wins
        assert pytest.approx(push, 0.01) == 0.0  # no push with 0.5 handicap
        assert pytest.approx(away_win, 0.01) == 0.40  # draw or away wins
        
        # Handicap -1.0 (home must win by 2+ for win, 1 is push)
        home_win, push, away_win = markets.asian_handicap[-1.0]
        assert pytest.approx(home_win, 0.01) == 0.30  # home wins by 2
        assert pytest.approx(push, 0.01) == 0.30  # home wins by 1
        assert pytest.approx(away_win, 0.01) == 0.40  # draw or away wins
    
    def test_probability_consistency_validation(self):
        """Test that derived markets validate probability consistency."""
        engine = MarketDerivationEngine()
        
        distribution = {
            (1, 0): 0.50,
            (0, 1): 0.30,
            (1, 1): 0.20,
        }
        
        markets = engine.derive(distribution)
        
        # validate() should not raise
        markets.validate()
        
        # Check specific consistency rules
        assert pytest.approx(markets.home_or_draw) == markets.home_win + markets.draw
        assert pytest.approx(markets.draw_or_away) == markets.draw + markets.away_win
        assert pytest.approx(markets.home_or_away) == markets.home_win + markets.away_win
    
    def test_empty_distribution_raises_error(self):
        """Test that empty distribution raises error."""
        engine = MarketDerivationEngine()
        
        with pytest.raises(ValueError, match="cannot be empty"):
            engine.derive({})
    
    def test_normalization_of_distribution(self):
        """Test that engine normalizes distributions that don't sum to 1.0."""
        engine = MarketDerivationEngine()
        
        # Distribution that sums to 0.5
        distribution = {
            (1, 0): 0.25,
            (0, 1): 0.15,
            (1, 1): 0.10,
        }
        
        markets = engine.derive(distribution)
        
        # Should normalize and still validate
        markets.validate()
        
        # 1X2 should sum to 1.0
        assert pytest.approx(markets.home_win + markets.draw + markets.away_win) == 1.0
