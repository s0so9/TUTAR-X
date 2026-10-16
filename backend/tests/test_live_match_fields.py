"""Test for live match field preservation fix.

Verifies that _update_match_statuses preserves all match fields including
minute, added_time, home_score_ht, away_score_ht, and other live data.
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.domain.match import Match
from app.domain.enums import MatchStatus
from app.providers.hybrid_provider import HybridProvider


def test_update_match_statuses_preserves_live_fields():
    """Test that live match fields are preserved during status updates."""
    
    # Create a LIVE match with all live fields populated
    live_match = Match(
        id="match-live-001",
        competition_id="comp-1",
        season_id="season-1",
        home_team_id="home-team",
        away_team_id="away-team",
        scheduled_at=datetime.now(timezone.utc) - timedelta(hours=1),
        status=MatchStatus.LIVE,
        home_score=2,
        away_score=1,
        home_score_ht=1,
        away_score_ht=0,
        minute=70,
        added_time=2,
        round=10,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        provider_fetched_at=datetime.now(timezone.utc),
    )
    
    # Mock provider (we only need the _update_match_statuses method)
    # Create a minimal instance - we don't need external_provider for this test
    provider = HybridProvider.__new__(HybridProvider)
    
    # Call the method
    updated_matches = provider._update_match_statuses([live_match])
    
    assert len(updated_matches) == 1
    updated = updated_matches[0]
    
    # Verify ALL fields are preserved
    assert updated.id == live_match.id
    assert updated.status == MatchStatus.LIVE
    assert updated.home_score == 2
    assert updated.away_score == 1
    assert updated.home_score_ht == 1
    assert updated.away_score_ht == 0
    assert updated.minute == 70
    assert updated.added_time == 2
    assert updated.round == 10
    assert updated.provider_fetched_at == live_match.provider_fetched_at


def test_update_match_statuses_preserves_halftime_scores():
    """Test that halftime scores are not lost."""
    
    match = Match(
        id="match-ht-001",
        competition_id="comp-1",
        season_id="season-1",
        home_team_id="home-team",
        away_team_id="away-team",
        scheduled_at=datetime.now(timezone.utc) - timedelta(hours=1),
        status=MatchStatus.LIVE,
        home_score=3,
        away_score=2,
        home_score_ht=1,
        away_score_ht=0,
        minute=80,
        round=5,
    )
    
    provider = HybridProvider.__new__(HybridProvider)
    updated_matches = provider._update_match_statuses([match])
    
    updated = updated_matches[0]
    assert updated.home_score_ht == 1
    assert updated.away_score_ht == 0


def test_update_match_statuses_preserves_added_time():
    """Test that added_time field is preserved."""
    
    match = Match(
        id="match-addtime-001",
        competition_id="comp-1",
        season_id="season-1",
        home_team_id="home-team",
        away_team_id="away-team",
        scheduled_at=datetime.now(timezone.utc) - timedelta(hours=1),
        status=MatchStatus.LIVE,
        home_score=1,
        away_score=1,
        minute=45,
        added_time=3,
        round=12,
    )
    
    provider = HybridProvider.__new__(HybridProvider)
    updated_matches = provider._update_match_statuses([match])
    
    updated = updated_matches[0]
    assert updated.minute == 45
    assert updated.added_time == 3


def test_update_match_statuses_no_auto_finish():
    """Test that old SCHEDULED matches are NOT auto-finished.
    
    Per code review: time-based auto-finish removed. Status must come from provider.
    """
    
    # Create a SCHEDULED match 4 hours in the past
    old_scheduled = Match(
        id="match-old-001",
        competition_id="comp-1",
        season_id="season-1",
        home_team_id="home-team",
        away_team_id="away-team",
        scheduled_at=datetime.now(timezone.utc) - timedelta(hours=4),
        status=MatchStatus.SCHEDULED,
        round=3,
    )
    
    provider = HybridProvider.__new__(HybridProvider)
    updated_matches = provider._update_match_statuses([old_scheduled])
    
    updated = updated_matches[0]
    # Should remain SCHEDULED - not auto-finished
    assert updated.status == MatchStatus.SCHEDULED
    assert updated.home_score is None  # No fake scores added
    assert updated.away_score is None


def test_update_match_statuses_preserves_multiple_matches():
    """Test that multiple matches are all properly preserved."""
    
    matches = [
        Match(
            id=f"match-{i}",
            competition_id="comp-1",
            season_id="season-1",
            home_team_id="home-team",
            away_team_id="away-team",
            scheduled_at=datetime.now(timezone.utc),
            status=MatchStatus.LIVE,
            minute=30 + i * 10,
            added_time=i,
            home_score=i,
            away_score=i + 1,
        )
        for i in range(5)
    ]
    
    provider = HybridProvider.__new__(HybridProvider)
    updated_matches = provider._update_match_statuses(matches)
    
    assert len(updated_matches) == 5
    
    for i, updated in enumerate(updated_matches):
        assert updated.minute == 30 + i * 10
        assert updated.added_time == i
        assert updated.home_score == i
        assert updated.away_score == i + 1


def test_update_match_statuses_preserves_outcome():
    """Test that outcome field is preserved."""
    
    from app.domain.enums import MatchOutcome
    
    match = Match(
        id="match-outcome-001",
        competition_id="comp-1",
        season_id="season-1",
        home_team_id="home-team",
        away_team_id="away-team",
        scheduled_at=datetime.now(timezone.utc) - timedelta(hours=2),
        status=MatchStatus.FINISHED,
        home_score=2,
        away_score=1,
        outcome=MatchOutcome.HOME_WIN,
        round=8,
    )
    
    provider = HybridProvider.__new__(HybridProvider)
    updated_matches = provider._update_match_statuses([match])
    
    updated = updated_matches[0]
    assert updated.outcome == MatchOutcome.HOME_WIN
