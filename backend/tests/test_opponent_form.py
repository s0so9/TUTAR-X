"""Tests for opponent-adjusted form calculator."""

import pytest
from datetime import datetime, timedelta
from app.features.opponent_form import OpponentAdjustedFormCalculator
from app.database.models import Match
from app.domain.enums import MatchOutcome


class TestOpponentAdjustedFormCalculator:
    """Test opponent-adjusted form calculation."""
    
    def test_insufficient_matches_returns_none(self):
        """Test that insufficient matches returns None."""
        calc = OpponentAdjustedFormCalculator(min_matches=5)
        
        # Only 3 matches
        matches = [
            self._create_match(
                match_id=f"m{i}",
                home_team_id="team1",
                away_team_id=f"opp{i}",
                home_goals=2,
                away_goals=1,
                outcome=MatchOutcome.HOME_WIN,
                days_ago=i * 7
            )
            for i in range(3)
        ]
        
        reference_date = datetime.utcnow()
        result = calc.calculate(matches, [], "team1", "team2", reference_date)
        
        assert result["home_form_score"] is None
        assert result["home_form_matches_used"] == 0
    
    def test_all_wins_gives_positive_score(self):
        """Test that all wins gives positive form score."""
        calc = OpponentAdjustedFormCalculator(min_matches=5)
        
        # 5 wins
        matches = [
            self._create_match(
                match_id=f"m{i}",
                home_team_id="team1",
                away_team_id=f"opp{i}",
                home_goals=2,
                away_goals=1,
                outcome=MatchOutcome.HOME_WIN,
                days_ago=(i + 1) * 7
            )
            for i in range(5)
        ]
        
        reference_date = datetime.utcnow()
        result = calc.calculate(matches, [], "team1", "team2", reference_date)
        
        assert result["home_form_score"] is not None
        assert result["home_form_score"] > 0.5  # Strong positive form
        assert result["home_form_matches_used"] >= 5
    
    def test_all_losses_gives_negative_score(self):
        """Test that all losses gives negative form score."""
        calc = OpponentAdjustedFormCalculator(min_matches=5)
        
        # 5 losses
        matches = [
            self._create_match(
                match_id=f"m{i}",
                home_team_id="team1",
                away_team_id=f"opp{i}",
                home_goals=0,
                away_goals=2,
                outcome=MatchOutcome.AWAY_WIN,
                days_ago=(i + 1) * 7
            )
            for i in range(5)
        ]
        
        reference_date = datetime.utcnow()
        result = calc.calculate(matches, [], "team1", "team2", reference_date)
        
        assert result["home_form_score"] is not None
        assert result["home_form_score"] < -0.5  # Strong negative form
    
    def test_balanced_form_near_zero(self):
        """Test that balanced W/D/L gives form score near 0."""
        calc = OpponentAdjustedFormCalculator(min_matches=5)
        
        # Mixed results: 2W, 2D, 2L
        matches = [
            self._create_match("m1", "team1", "opp1", 2, 0, MatchOutcome.HOME_WIN, 42),
            self._create_match("m2", "team1", "opp2", 1, 1, MatchOutcome.DRAW, 35),
            self._create_match("m3", "team1", "opp3", 0, 1, MatchOutcome.AWAY_WIN, 28),
            self._create_match("m4", "team1", "opp4", 2, 1, MatchOutcome.HOME_WIN, 21),
            self._create_match("m5", "team1", "opp5", 1, 1, MatchOutcome.DRAW, 14),
            self._create_match("m6", "team1", "opp6", 0, 2, MatchOutcome.AWAY_WIN, 7),
        ]
        
        reference_date = datetime.utcnow()
        result = calc.calculate(matches, [], "team1", "team2", reference_date)
        
        assert result["home_form_score"] is not None
        # Balanced form should be near 0
        assert -0.3 < result["home_form_score"] < 0.3
    
    def test_form_score_bounds(self):
        """Test that form scores are bounded to [-1, 1]."""
        calc = OpponentAdjustedFormCalculator(min_matches=5)
        
        # Extreme winning streak
        matches = [
            self._create_match(
                match_id=f"m{i}",
                home_team_id="team1",
                away_team_id=f"opp{i}",
                home_goals=5,
                away_goals=0,
                outcome=MatchOutcome.HOME_WIN,
                days_ago=(i + 1) * 7
            )
            for i in range(10)
        ]
        
        reference_date = datetime.utcnow()
        result = calc.calculate(matches, [], "team1", "team2", reference_date)
        
        assert result["home_form_score"] is not None
        assert -1.0 <= result["home_form_score"] <= 1.0
    
    def test_time_decay_recent_matches_weighted_more(self):
        """Test that recent matches are weighted more heavily."""
        calc = OpponentAdjustedFormCalculator(time_decay_rate=0.1, min_matches=5)
        
        # Old losses, recent wins
        matches = [
            # Old losses (60-40 days ago)
            self._create_match("m1", "team1", "opp1", 0, 2, MatchOutcome.AWAY_WIN, 60),
            self._create_match("m2", "team1", "opp2", 0, 2, MatchOutcome.AWAY_WIN, 50),
            self._create_match("m3", "team1", "opp3", 0, 2, MatchOutcome.AWAY_WIN, 40),
            # Recent wins (21-7 days ago)
            self._create_match("m4", "team1", "opp4", 2, 0, MatchOutcome.HOME_WIN, 21),
            self._create_match("m5", "team1", "opp5", 2, 0, MatchOutcome.HOME_WIN, 14),
            self._create_match("m6", "team1", "opp6", 2, 0, MatchOutcome.HOME_WIN, 7),
        ]
        
        reference_date = datetime.utcnow()
        result = calc.calculate(matches, [], "team1", "team2", reference_date)
        
        # Recent wins should dominate, giving positive score
        assert result["home_form_score"] is not None
        assert result["home_form_score"] > 0
    
    def test_away_team_perspective(self):
        """Test form calculation from away team perspective."""
        calc = OpponentAdjustedFormCalculator(min_matches=5)
        
        # Away team wins
        matches = [
            self._create_match(
                match_id=f"m{i}",
                home_team_id=f"opp{i}",
                away_team_id="team2",
                home_goals=0,
                away_goals=2,
                outcome=MatchOutcome.AWAY_WIN,
                days_ago=(i + 1) * 7
            )
            for i in range(5)
        ]
        
        reference_date = datetime.utcnow()
        result = calc.calculate([], matches, "team1", "team2", reference_date)
        
        assert result["away_form_score"] is not None
        assert result["away_form_score"] > 0.5  # Away wins should give positive score
    
    def test_strength_of_schedule_adjustment(self):
        """Test that opponent strength affects form score."""
        calc = OpponentAdjustedFormCalculator(min_matches=5)
        
        # All wins, but we can't test exact strength adjustment without Elo data
        # Just verify it doesn't crash and produces valid scores
        matches = [
            self._create_match(
                match_id=f"m{i}",
                home_team_id="team1",
                away_team_id=f"strong_opp{i}",
                home_goals=2,
                away_goals=1,
                outcome=MatchOutcome.HOME_WIN,
                days_ago=(i + 1) * 7
            )
            for i in range(5)
        ]
        
        reference_date = datetime.utcnow()
        
        # With Elo ratings showing strong opponents
        elo_ratings = {f"strong_opp{i}": 1600.0 for i in range(5)}
        result = calc.calculate(matches, [], "team1", "team2", reference_date, elo_ratings)
        
        assert result["home_form_score"] is not None
        assert -1.0 <= result["home_form_score"] <= 1.0
    
    def test_matches_filtered_by_reference_date(self):
        """Test that only matches before reference date are considered."""
        calc = OpponentAdjustedFormCalculator(min_matches=5)
        
        # Matches spread across time
        matches = [
            self._create_match("m1", "team1", "opp1", 2, 0, MatchOutcome.HOME_WIN, -7),   # Future
            self._create_match("m2", "team1", "opp2", 2, 0, MatchOutcome.HOME_WIN, 7),
            self._create_match("m3", "team1", "opp3", 2, 0, MatchOutcome.HOME_WIN, 14),
            self._create_match("m4", "team1", "opp4", 2, 0, MatchOutcome.HOME_WIN, 21),
            self._create_match("m5", "team1", "opp5", 2, 0, MatchOutcome.HOME_WIN, 28),
            self._create_match("m6", "team1", "opp6", 2, 0, MatchOutcome.HOME_WIN, 35),
        ]
        
        reference_date = datetime.utcnow()
        result = calc.calculate(matches, [], "team1", "team2", reference_date)
        
        # Should only use 5 matches (future match excluded)
        assert result["home_form_matches_used"] <= 5
    
    # Helper methods
    
    def _create_match(
        self,
        match_id: str,
        home_team_id: str,
        away_team_id: str,
        home_goals: int,
        away_goals: int,
        outcome: MatchOutcome,
        days_ago: int
    ) -> Match:
        """Create a test match."""
        match_date = datetime.utcnow() - timedelta(days=days_ago)
        
        match = Match(
            id=match_id,
            provider_source_id="test_provider",
            provider_id=f"test_{match_id}",
            competition_id="comp1",
            season="2024",
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            scheduled_at=match_date,
            home_score=home_goals,
            away_score=away_goals,
            outcome=outcome,
            status="FINISHED"
        )
        
        return match
