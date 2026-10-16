"""Tests for market movement tracking."""

import pytest
from datetime import datetime, timedelta

from app.domain.market_movement import (
    OddsMovement,
    calculate_odds_movement,
)


class TestOddsMovement:
    """Test OddsMovement dataclass."""
    
    def test_odds_movement_with_previous_odds(self):
        """Test creating OddsMovement with previous odds available."""
        now = datetime.now()
        previous = now - timedelta(hours=2)
        
        movement = OddsMovement(
            market_name="match_result",
            selection_label="home",
            bookmaker="Bet365",
            current_odds=2.00,
            previous_odds=1.80,
            odds_change=0.20,
            odds_change_percentage=11.11,
            movement_timestamp=now,
            previous_timestamp=previous
        )
        
        assert movement.market_name == "match_result"
        assert movement.selection_label == "home"
        assert movement.bookmaker == "Bet365"
        assert movement.current_odds == 2.00
        assert movement.previous_odds == 1.80
        assert movement.odds_change == 0.20
        assert movement.odds_change_percentage == 11.11
        assert movement.movement_timestamp == now
        assert movement.previous_timestamp == previous
    
    def test_odds_movement_without_previous_odds(self):
        """Test creating OddsMovement when no previous odds available."""
        now = datetime.now()
        
        movement = OddsMovement(
            market_name="btts",
            selection_label="yes",
            bookmaker="Bet365",
            current_odds=1.85,
            previous_odds=None,
            odds_change=None,
            odds_change_percentage=None,
            movement_timestamp=now,
            previous_timestamp=None
        )
        
        assert movement.current_odds == 1.85
        assert movement.previous_odds is None
        assert movement.odds_change is None
        assert movement.odds_change_percentage is None
        assert movement.previous_timestamp is None
    
    def test_odds_movement_validates_current_odds_gt_1(self):
        """Test that current_odds must be > 1.0."""
        now = datetime.now()
        
        with pytest.raises(ValueError, match="Invalid current_odds.*must be > 1.0"):
            OddsMovement(
                market_name="match_result",
                selection_label="home",
                bookmaker="Bet365",
                current_odds=0.95,  # Invalid: <= 1.0
                previous_odds=None,
                odds_change=None,
                odds_change_percentage=None,
                movement_timestamp=now,
                previous_timestamp=None
            )
    
    def test_odds_movement_validates_previous_odds_gt_1(self):
        """Test that previous_odds must be > 1.0 if not None."""
        now = datetime.now()
        previous = now - timedelta(hours=1)
        
        with pytest.raises(ValueError, match="Invalid previous_odds.*must be > 1.0"):
            OddsMovement(
                market_name="match_result",
                selection_label="home",
                bookmaker="Bet365",
                current_odds=2.00,
                previous_odds=0.80,  # Invalid: <= 1.0
                odds_change=1.20,
                odds_change_percentage=150.0,
                movement_timestamp=now,
                previous_timestamp=previous
            )
    
    def test_odds_movement_validates_consistency_none_previous_requires_none_change(self):
        """Test that odds_change must be None when previous_odds is None."""
        now = datetime.now()
        
        with pytest.raises(ValueError, match="odds_change must be None when previous_odds is None"):
            OddsMovement(
                market_name="match_result",
                selection_label="home",
                bookmaker="Bet365",
                current_odds=2.00,
                previous_odds=None,
                odds_change=0.20,  # Invalid: should be None
                odds_change_percentage=None,
                movement_timestamp=now,
                previous_timestamp=None
            )
    
    def test_odds_movement_validates_consistency_none_previous_requires_none_percentage(self):
        """Test that odds_change_percentage must be None when previous_odds is None."""
        now = datetime.now()
        
        with pytest.raises(ValueError, match="odds_change_percentage must be None when previous_odds is None"):
            OddsMovement(
                market_name="match_result",
                selection_label="home",
                bookmaker="Bet365",
                current_odds=2.00,
                previous_odds=None,
                odds_change=None,
                odds_change_percentage=10.0,  # Invalid: should be None
                movement_timestamp=now,
                previous_timestamp=None
            )
    
    def test_odds_movement_validates_consistency_none_previous_requires_none_timestamp(self):
        """Test that previous_timestamp must be None when previous_odds is None."""
        now = datetime.now()
        previous = now - timedelta(hours=1)
        
        with pytest.raises(ValueError, match="previous_timestamp must be None when previous_odds is None"):
            OddsMovement(
                market_name="match_result",
                selection_label="home",
                bookmaker="Bet365",
                current_odds=2.00,
                previous_odds=None,
                odds_change=None,
                odds_change_percentage=None,
                movement_timestamp=now,
                previous_timestamp=previous  # Invalid: should be None
            )


class TestCalculateOddsMovement:
    """Test odds movement calculation helper."""
    
    def test_calculate_movement_positive_change(self):
        """Test calculating movement when odds increase."""
        change, percentage = calculate_odds_movement(2.00, 1.80)
        
        assert change == pytest.approx(0.20)
        assert percentage == pytest.approx(11.11, rel=0.01)
    
    def test_calculate_movement_negative_change(self):
        """Test calculating movement when odds decrease."""
        change, percentage = calculate_odds_movement(1.75, 2.00)
        
        assert change == pytest.approx(-0.25)
        assert percentage == pytest.approx(-12.5)
    
    def test_calculate_movement_no_change(self):
        """Test calculating movement when odds stay the same."""
        change, percentage = calculate_odds_movement(1.90, 1.90)
        
        assert change == pytest.approx(0.0)
        assert percentage == pytest.approx(0.0)
    
    def test_calculate_movement_large_increase(self):
        """Test calculating movement with large odds increase."""
        change, percentage = calculate_odds_movement(3.50, 2.00)
        
        assert change == pytest.approx(1.50)
        assert percentage == pytest.approx(75.0)
    
    def test_calculate_movement_large_decrease(self):
        """Test calculating movement with large odds decrease."""
        change, percentage = calculate_odds_movement(1.50, 3.00)
        
        assert change == pytest.approx(-1.50)
        assert percentage == pytest.approx(-50.0)
    
    def test_calculate_movement_none_previous_returns_none(self):
        """Test that movement returns (None, None) when no previous odds."""
        change, percentage = calculate_odds_movement(2.00, None)
        
        assert change is None
        assert percentage is None
    
    def test_calculate_movement_validates_current_odds(self):
        """Test that invalid current_odds raises ValueError."""
        with pytest.raises(ValueError, match="Invalid current_odds.*must be > 1.0"):
            calculate_odds_movement(0.95, 1.80)
    
    def test_calculate_movement_validates_previous_odds(self):
        """Test that invalid previous_odds raises ValueError."""
        with pytest.raises(ValueError, match="Invalid previous_odds.*must be > 1.0"):
            calculate_odds_movement(2.00, 0.80)
    
    def test_calculate_movement_realistic_scenarios(self):
        """Test realistic odds movement scenarios."""
        # Sharp move upward (steam move)
        change, pct = calculate_odds_movement(2.20, 1.90)
        assert change == pytest.approx(0.30)
        assert pct == pytest.approx(15.79, rel=0.01)
        
        # Gradual drift downward
        change, pct = calculate_odds_movement(1.88, 1.92)
        assert change == pytest.approx(-0.04)
        assert pct == pytest.approx(-2.08, rel=0.01)
        
        # Minimal movement
        change, pct = calculate_odds_movement(2.01, 2.00)
        assert change == pytest.approx(0.01)
        assert pct == pytest.approx(0.5)
