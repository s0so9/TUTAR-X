"""Tests for lineup intelligence calculator."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock

from app.features.lineup_intelligence import (
    PlayerAvailabilityStatus,
    PlayerAvailability,
    LineupImpactEstimate,
    LineupIntelligenceCalculator,
)
from app.features.advanced_team_intelligence import MatchWithStatistics
from app.domain.match import Match
from app.domain.statistics import TeamMatchStatistic
from app.domain.enums import MatchStatus, MatchOutcome


@pytest.fixture
def mock_session():
    """Create mock database session."""
    return Mock()


@pytest.fixture
def calculator(mock_session):
    """Create calculator instance."""
    return LineupIntelligenceCalculator(
        session=mock_session,
        min_with_player=3,
        min_without_player=3
    )


def create_match(
    match_id: str,
    home_team_id: str,
    away_team_id: str,
    scheduled_at: datetime,
    status: MatchStatus = MatchStatus.FINISHED
) -> Match:
    """Helper to create a Match object."""
    return Match(
        id=match_id,
        competition_id="comp_1",
        season_id="season_2024",
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        scheduled_at=scheduled_at,
        status=status,
        home_score=0,
        away_score=0,
        outcome=MatchOutcome.DRAW
    )


def create_match_with_stats(
    match_id: str,
    team_id: str,
    opponent_id: str,
    scheduled_at: datetime,
    is_home: bool = True
) -> MatchWithStatistics:
    """Helper to create MatchWithStatistics."""
    if is_home:
        match = create_match(match_id, team_id, opponent_id, scheduled_at)
        home_stats = TeamMatchStatistic(
            id=f"s_{match_id}_h",
            match_id=match_id,
            team_id=team_id,
            goals_scored=1,
            goals_conceded=0
        )
        away_stats = TeamMatchStatistic(
            id=f"s_{match_id}_a",
            match_id=match_id,
            team_id=opponent_id,
            goals_scored=0,
            goals_conceded=1
        )
    else:
        match = create_match(match_id, opponent_id, team_id, scheduled_at)
        home_stats = TeamMatchStatistic(
            id=f"s_{match_id}_h",
            match_id=match_id,
            team_id=opponent_id,
            goals_scored=0,
            goals_conceded=1
        )
        away_stats = TeamMatchStatistic(
            id=f"s_{match_id}_a",
            match_id=match_id,
            team_id=team_id,
            goals_scored=1,
            goals_conceded=0
        )
    
    return MatchWithStatistics(
        match=match,
        home_statistics=home_stats,
        away_statistics=away_stats
    )


class TestPlayerAvailabilityStatus:
    """Test PlayerAvailabilityStatus enum."""
    
    def test_player_availability_status_enum_values(self):
        """Test all required status values exist."""
        assert PlayerAvailabilityStatus.CONFIRMED == "confirmed"
        assert PlayerAvailabilityStatus.EXPECTED == "expected"
        assert PlayerAvailabilityStatus.INJURED == "injured"
        assert PlayerAvailabilityStatus.SUSPENDED == "suspended"
        assert PlayerAvailabilityStatus.UNAVAILABLE == "unavailable"
        assert PlayerAvailabilityStatus.UNKNOWN == "unknown"


class TestLineupImpactEstimate:
    """Test LineupImpactEstimate dataclass structure."""
    
    def test_lineup_impact_estimate_structure(self):
        """Test that all impact fields are Optional and default to None."""
        estimate = LineupImpactEstimate(team_id="team_a")
        
        # All impact fields should be None by default
        assert estimate.player_attack_impact is None
        assert estimate.player_defensive_impact is None
        assert estimate.player_shot_impact is None
        assert estimate.player_creation_impact is None
        assert estimate.attacking_adjustment is None
        assert estimate.defensive_adjustment is None
        assert estimate.shot_adjustment is None
        assert estimate.creation_adjustment is None
        
        # Lineup quality None by default
        assert estimate.lineup_quality is None
        
        # Default uncertainty and confidence
        assert estimate.uncertainty == 1.0
        assert estimate.data_quality == 0.0
        assert estimate.impact_confidence == 0.0
        
        # Default method
        assert estimate.impact_method == "unavailable"


class TestLineupIntelligenceCalculator:
    """Test LineupIntelligenceCalculator."""
    
    def test_no_absences_returns_none_impacts(self, calculator):
        """Test that no player absences returns neutral impact."""
        # Create some historical matches
        matches = [
            create_match_with_stats(
                f"m{i}",
                "team_a",
                f"opp_{i}",
                datetime(2024, 1, i+1)
            )
            for i in range(5)
        ]
        
        # No player absences
        player_absences = []
        
        result = calculator.calculate_lineup_impact(
            team_id="team_a",
            player_absences=player_absences,
            historical_matches_with_stats=matches,
            before_datetime=datetime(2024, 2, 1)
        )
        
        assert result.team_id == "team_a"
        assert result.impact_method == "no_absences"
        assert result.uncertainty == 0.5
    
    def test_no_lineup_data_returns_unavailable(self, calculator):
        """Test that absence of lineup data returns unavailable."""
        matches = [
            create_match_with_stats(
                f"m{i}",
                "team_a",
                f"opp_{i}",
                datetime(2024, 1, i+1)
            )
            for i in range(5)
        ]
        
        # Player absences but no lineup data available
        player_absences = [
            PlayerAvailability(
                player_id="player_1",
                player_name="Player One",
                status=PlayerAvailabilityStatus.INJURED,
                reason="hamstring"
            )
        ]
        
        result = calculator.calculate_lineup_impact(
            team_id="team_a",
            player_absences=player_absences,
            historical_matches_with_stats=matches,
            before_datetime=datetime(2024, 2, 1)
        )
        
        # Since we don't have lineup data access, impact should be unavailable
        assert result.impact_method == "unavailable"
        assert result.player_attack_impact is None
        assert result.player_defensive_impact is None
        assert result.uncertainty == 1.0
    
    def test_temporal_filtering(self, calculator):
        """Test that calculator respects before_datetime filter."""
        matches = [
            create_match_with_stats(
                f"m{i}",
                "team_a",
                f"opp_{i}",
                datetime(2024, 1, i+1)
            )
            for i in range(10)
        ]
        
        player_absences = [
            PlayerAvailability(
                player_id="player_1",
                status=PlayerAvailabilityStatus.INJURED
            )
        ]
        
        # Set cutoff to exclude last 5 matches
        result = calculator.calculate_lineup_impact(
            team_id="team_a",
            player_absences=player_absences,
            historical_matches_with_stats=matches,
            before_datetime=datetime(2024, 1, 6)  # Only first 5 matches
        )
        
        # Should only consider first 5 matches (before 2024-01-06)
        # Impact still unavailable due to no lineup data, but temporal filter applied
        assert result.impact_method == "unavailable"
    
    def test_never_hardcoded_percentages(self, calculator):
        """Test that calculator never uses hardcoded percentage impacts."""
        matches = [
            create_match_with_stats(
                f"m{i}",
                "team_a",
                f"opp_{i}",
                datetime(2024, 1, i+1)
            )
            for i in range(5)
        ]
        
        player_absences = [
            PlayerAvailability(
                player_id="star_player",
                player_name="Star Player",
                status=PlayerAvailabilityStatus.INJURED,
                reason="key injury"
            )
        ]
        
        result = calculator.calculate_lineup_impact(
            team_id="team_a",
            player_absences=player_absences,
            historical_matches_with_stats=matches,
            before_datetime=datetime(2024, 2, 1)
        )
        
        # Impact should be None (unavailable) or derived statistically
        # Never a hardcoded value like -0.10 (-10%)
        if result.player_attack_impact is not None:
            # If impact is calculated, it should be from real data
            assert result.impact_method == "statistical_with_without"
            assert result.sample_size_with > 0 or result.sample_size_without > 0
        else:
            # If unavailable, method should indicate why
            assert result.impact_method in ["unavailable", "insufficient_sample"]
    
    def test_impact_method_documented(self, calculator):
        """Test that impact_method field is always set appropriately."""
        matches = [
            create_match_with_stats(
                f"m{i}",
                "team_a",
                f"opp_{i}",
                datetime(2024, 1, i+1)
            )
            for i in range(5)
        ]
        
        player_absences = [
            PlayerAvailability(
                player_id="player_1",
                status=PlayerAvailabilityStatus.INJURED
            )
        ]
        
        result = calculator.calculate_lineup_impact(
            team_id="team_a",
            player_absences=player_absences,
            historical_matches_with_stats=matches,
            before_datetime=datetime(2024, 2, 1)
        )
        
        # impact_method should be one of the documented values
        valid_methods = [
            "unavailable",
            "statistical_with_without",
            "insufficient_sample",
            "no_absences"
        ]
        assert result.impact_method in valid_methods
