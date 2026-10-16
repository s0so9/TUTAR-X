"""Test for historical match query fix.

Verifies that get_team_matches_before_date returns the most recent N matches
when limit is specified, not the oldest N matches.
"""

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.database.models import Match, ProviderSource
from app.database.repository import MatchRepository
from app.domain.enums import MatchStatus


@pytest.fixture
def provider_source(db_session: Session) -> ProviderSource:
    """Create a test provider source."""
    provider = ProviderSource(
        id=str(uuid.uuid4()),
        name="test-provider",
        is_active=True
    )
    db_session.add(provider)
    db_session.commit()
    return provider


def test_get_team_matches_before_date_with_limit(db_session: Session, provider_source: ProviderSource):
    """Test that limit returns most recent N matches, not oldest N."""
    repo = MatchRepository(db_session)
    
    team_id = str(uuid.uuid4())
    other_team_id = str(uuid.uuid4())
    base_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    
    # Create 30 historical matches for the team
    matches = []
    for i in range(30):
        match = Match(
            id=str(uuid.uuid4()),
            provider_source_id=provider_source.id,
            provider_id=f"match-{i:02d}",
            home_team_id=team_id if i % 2 == 0 else other_team_id,
            away_team_id=other_team_id if i % 2 == 0 else team_id,
            scheduled_at=base_date + timedelta(days=i),
            status=MatchStatus.FINISHED,
            home_score=1,
            away_score=0,
        )
        db_session.add(match)
        matches.append(match)
    
    db_session.commit()
    
    # Query with limit=20, before match 30 (target match)
    target_date = base_date + timedelta(days=30)
    result = repo.get_team_matches_before_date(
        team_id=team_id,
        before_datetime=target_date,
        limit=20,
        finished_only=True
    )
    
    # Should return matches 10-29 (most recent 20), not 0-19 (oldest 20)
    assert len(result) == 20
    assert result[0].provider_id == "match-10"  # First in chronological order
    assert result[-1].provider_id == "match-29"  # Last (most recent)
    
    # Verify chronological order is preserved
    for i in range(len(result) - 1):
        assert result[i].scheduled_at < result[i + 1].scheduled_at


def test_get_team_matches_before_date_no_limit(db_session: Session, provider_source: ProviderSource):
    """Test that without limit, all matches are returned chronologically."""
    repo = MatchRepository(db_session)
    
    team_id = str(uuid.uuid4())
    other_team_id = str(uuid.uuid4())
    base_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    
    # Create 10 matches
    for i in range(10):
        match = Match(
            id=str(uuid.uuid4()),
            provider_source_id=provider_source.id,
            provider_id=f"match-{i:02d}",
            home_team_id=team_id,
            away_team_id=other_team_id,
            scheduled_at=base_date + timedelta(days=i),
            status=MatchStatus.FINISHED,
            home_score=1,
            away_score=0,
        )
        db_session.add(match)
    
    db_session.commit()
    
    # Query without limit
    target_date = base_date + timedelta(days=15)
    result = repo.get_team_matches_before_date(
        team_id=team_id,
        before_datetime=target_date,
        limit=None,
        finished_only=True
    )
    
    # Should return all 10 matches in chronological order
    assert len(result) == 10
    assert result[0].provider_id == "match-00"
    assert result[-1].provider_id == "match-09"


def test_get_team_matches_before_date_form_window(db_session: Session, provider_source: ProviderSource):
    """Test that last 5 matches for form calculation are 26-30, not 0-4."""
    repo = MatchRepository(db_session)
    
    team_id = str(uuid.uuid4())
    other_team_id = str(uuid.uuid4())
    base_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    
    # Create 30 historical matches
    for i in range(30):
        match = Match(
            id=str(uuid.uuid4()),
            provider_source_id=provider_source.id,
            provider_id=f"match-{i:02d}",
            home_team_id=team_id,
            away_team_id=other_team_id,
            scheduled_at=base_date + timedelta(days=i),
            status=MatchStatus.FINISHED,
            home_score=2 if i >= 25 else 0,  # Mark last 5 matches with score=2
            away_score=0,
        )
        db_session.add(match)
    
    db_session.commit()
    
    # Get last 20 matches
    target_date = base_date + timedelta(days=30)
    result = repo.get_team_matches_before_date(
        team_id=team_id,
        before_datetime=target_date,
        limit=20,
        finished_only=True
    )
    
    # Last 5 should be matches 25-29
    last_5 = result[-5:]
    assert len(last_5) == 5
    assert last_5[0].provider_id == "match-25"
    assert last_5[-1].provider_id == "match-29"
    
    # Verify these are the matches with score=2
    for match in last_5:
        assert match.home_score == 2


def test_get_team_matches_stable_sort_same_timestamp(db_session: Session, provider_source: ProviderSource):
    """Test stable sorting when matches have equal timestamps."""
    repo = MatchRepository(db_session)
    
    team_id = str(uuid.uuid4())
    other_team_id = str(uuid.uuid4())
    same_time = datetime(2024, 1, 1, 15, 0, tzinfo=timezone.utc)
    
    # Create 5 matches with the same timestamp
    match_ids = []
    for i in range(5):
        match_id = str(uuid.uuid4())
        match_ids.append(match_id)
        match = Match(
            id=match_id,
            provider_source_id=provider_source.id,
            provider_id=f"match-{i}",
            home_team_id=team_id,
            away_team_id=other_team_id,
            scheduled_at=same_time,
            status=MatchStatus.FINISHED,
            home_score=i,
            away_score=0,
        )
        db_session.add(match)
    
    db_session.commit()
    
    # Query multiple times - should get consistent order
    results = []
    for _ in range(3):
        result = repo.get_team_matches_before_date(
            team_id=team_id,
            before_datetime=same_time + timedelta(hours=1),
            limit=3,
            finished_only=True
        )
        results.append([m.id for m in result])
    
    # All queries should return the same order
    assert results[0] == results[1] == results[2]
    assert len(results[0]) == 3
