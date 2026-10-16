"""Tests for HybridProvider timestamp-based freshness logic.

Tests verify that the provider intelligently refreshes data based on:
- Match status (SCHEDULED, LIVE, FINISHED)
- Data age (provider_fetched_at timestamp)
- Match timing (kickoff approaching, recently finished)
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch

from app.providers.hybrid_provider import HybridProvider
from app.domain.match import Match
from app.domain.enums import MatchStatus


@pytest.fixture
def mock_session():
    """Mock database session."""
    return Mock()


@pytest.fixture
def mock_external_provider():
    """Mock external provider."""
    mock = Mock()
    mock.get_matches_async = AsyncMock(return_value=[])
    mock.get_matches = Mock(return_value=[])
    return mock


@pytest.fixture
def mock_db_provider():
    """Mock database provider."""
    return Mock()


@pytest.mark.asyncio
async def test_fresh_scheduled_data_no_external_call(
    mock_session,
    mock_external_provider,
    mock_db_provider
):
    """Fresh scheduled match data should not trigger external refresh."""
    now = datetime.now(timezone.utc)
    
    # Database has match with data fetched 30 minutes ago (fresh)
    db_match = Match(
        id="match_1",
        home_team_id="team_a",
        away_team_id="team_b",
        competition_id="comp_1",
        season_id="2024",
        scheduled_at=now + timedelta(days=7),  # Match in 7 days
        status=MatchStatus.SCHEDULED,
        home_score=None,
        away_score=None,
        provider_fetched_at=now - timedelta(minutes=30),  # 30 mins old
    )
    
    with patch.object(HybridProvider, '__init__', lambda self, external_provider, session: None):
        provider = HybridProvider(mock_external_provider, mock_session)
        provider.external_provider = mock_external_provider
        provider.db_provider = mock_db_provider
        
        mock_db_provider.get_matches = Mock(return_value=[db_match])
        provider._update_match_statuses = lambda matches: matches
        
        result = await provider.get_matches_async(status="scheduled")
        
        # External provider should NOT be called (data is fresh)
        mock_external_provider.get_matches_async.assert_not_called()
        
        assert len(result) == 1
        assert result[0].id == "match_1"


@pytest.mark.asyncio
async def test_stale_scheduled_data_triggers_refresh(
    mock_session,
    mock_external_provider,
    mock_db_provider
):
    """Stale scheduled match data (>2 hours) should trigger external refresh."""
    now = datetime.now(timezone.utc)
    
    # Database has match with data fetched 3 hours ago (stale)
    db_match = Match(
        id="match_1",
        home_team_id="team_a",
        away_team_id="team_b",
        competition_id="comp_1",
        season_id="2024",
        scheduled_at=now + timedelta(days=7),
        status=MatchStatus.SCHEDULED,
        home_score=None,
        away_score=None,
        provider_fetched_at=now - timedelta(hours=3),  # 3 hours old (stale)
    )
    
    # External provider returns fresh data
    fresh_match = Match(
        id="match_1",
        home_team_id="team_a",
        away_team_id="team_b",
        competition_id="comp_1",
        season_id="2024",
        scheduled_at=now + timedelta(days=7),
        status=MatchStatus.SCHEDULED,
        home_score=None,
        away_score=None,
        provider_fetched_at=now,
    )
    
    mock_external_provider.get_matches_async.return_value = [fresh_match]
    
    with patch.object(HybridProvider, '__init__', lambda self, external_provider, session: None):
        provider = HybridProvider(mock_external_provider, mock_session)
        provider.external_provider = mock_external_provider
        provider.db_provider = mock_db_provider
        
        mock_db_provider.get_matches = Mock(return_value=[db_match])
        provider._update_match_statuses = lambda matches: matches
        
        result = await provider.get_matches_async(status="scheduled")
        
        # External provider SHOULD be called (data is stale)
        mock_external_provider.get_matches_async.assert_called_once()
        
        assert len(result) == 1


@pytest.mark.asyncio
async def test_approaching_kickoff_requires_fresh_data(
    mock_session,
    mock_external_provider,
    mock_db_provider
):
    """Match with kickoff within 1 hour requires fresh data (< 15 mins old)."""
    now = datetime.now(timezone.utc)
    
    # Database has match starting in 30 minutes, data 20 minutes old
    db_match = Match(
        id="match_1",
        home_team_id="team_a",
        away_team_id="team_b",
        competition_id="comp_1",
        season_id="2024",
        scheduled_at=now + timedelta(minutes=30),  # Kickoff in 30 minutes
        status=MatchStatus.SCHEDULED,
        home_score=None,
        away_score=None,
        provider_fetched_at=now - timedelta(minutes=20),  # 20 mins old
    )
    
    fresh_match = Match(
        id="match_1",
        home_team_id="team_a",
        away_team_id="team_b",
        competition_id="comp_1",
        season_id="2024",
        scheduled_at=now + timedelta(minutes=30),
        status=MatchStatus.SCHEDULED,
        home_score=None,
        away_score=None,
        provider_fetched_at=now,
    )
    
    mock_external_provider.get_matches_async.return_value = [fresh_match]
    
    with patch.object(HybridProvider, '__init__', lambda self, external_provider, session: None):
        provider = HybridProvider(mock_external_provider, mock_session)
        provider.external_provider = mock_external_provider
        provider.db_provider = mock_db_provider
        
        mock_db_provider.get_matches = Mock(return_value=[db_match])
        provider._update_match_statuses = lambda matches: matches
        
        result = await provider.get_matches_async(status="scheduled")
        
        # External provider SHOULD be called (kickoff approaching, data not fresh enough)
        mock_external_provider.get_matches_async.assert_called_once()


@pytest.mark.asyncio
async def test_recently_finished_match_needs_verification(
    mock_session,
    mock_external_provider,
    mock_db_provider
):
    """Match finished 1 hour ago with 2-hour-old data needs verification."""
    now = datetime.now(timezone.utc)
    
    # Database has match that finished 1 hour ago, data 2 hours old
    db_match = Match(
        id="match_1",
        home_team_id="team_a",
        away_team_id="team_b",
        competition_id="comp_1",
        season_id="2024",
        scheduled_at=now - timedelta(hours=1),  # Finished 1 hour ago
        status=MatchStatus.FINISHED,
        home_score=2,
        away_score=1,
        provider_fetched_at=now - timedelta(hours=2),  # 2 hours old (stale)
    )
    
    verified_match = Match(
        id="match_1",
        home_team_id="team_a",
        away_team_id="team_b",
        competition_id="comp_1",
        season_id="2024",
        scheduled_at=now - timedelta(hours=1),
        status=MatchStatus.FINISHED,
        home_score=2,
        away_score=1,
        provider_fetched_at=now,
    )
    
    mock_external_provider.get_matches_async.return_value = [verified_match]
    
    with patch.object(HybridProvider, '__init__', lambda self, external_provider, session: None):
        provider = HybridProvider(mock_external_provider, mock_session)
        provider.external_provider = mock_external_provider
        provider.db_provider = mock_db_provider
        
        mock_db_provider.get_matches = Mock(return_value=[db_match])
        provider._update_match_statuses = lambda matches: matches
        
        result = await provider.get_matches_async(status="finished")
        
        # External provider SHOULD be called (recently finished, needs verification)
        mock_external_provider.get_matches_async.assert_called_once()


@pytest.mark.asyncio
async def test_old_finished_match_uses_cached_data(
    mock_session,
    mock_external_provider,
    mock_db_provider
):
    """Match finished 3 days ago with 12-hour-old data should use cache."""
    now = datetime.now(timezone.utc)
    
    # Database has match finished 3 days ago, data 12 hours old (acceptable for old match)
    db_match = Match(
        id="match_1",
        home_team_id="team_a",
        away_team_id="team_b",
        competition_id="comp_1",
        season_id="2024",
        scheduled_at=now - timedelta(days=3),  # Finished 3 days ago
        status=MatchStatus.FINISHED,
        home_score=2,
        away_score=1,
        provider_fetched_at=now - timedelta(hours=12),  # 12 hours old (acceptable)
    )
    
    with patch.object(HybridProvider, '__init__', lambda self, external_provider, session: None):
        provider = HybridProvider(mock_external_provider, mock_session)
        provider.external_provider = mock_external_provider
        provider.db_provider = mock_db_provider
        
        mock_db_provider.get_matches = Mock(return_value=[db_match])
        provider._update_match_statuses = lambda matches: matches
        
        result = await provider.get_matches_async(status="finished")
        
        # External provider should NOT be called (old finished match, data acceptable)
        mock_external_provider.get_matches_async.assert_not_called()
        
        assert len(result) == 1


@pytest.mark.asyncio
async def test_missing_provider_fetched_at_triggers_refresh(
    mock_session,
    mock_external_provider,
    mock_db_provider
):
    """Match without provider_fetched_at timestamp should trigger refresh."""
    now = datetime.now(timezone.utc)
    
    # Database has match with no provider_fetched_at (legacy data)
    db_match = Match(
        id="match_1",
        home_team_id="team_a",
        away_team_id="team_b",
        competition_id="comp_1",
        season_id="2024",
        scheduled_at=now + timedelta(days=1),
        status=MatchStatus.SCHEDULED,
        home_score=None,
        away_score=None,
        provider_fetched_at=None,  # Missing timestamp
    )
    
    fresh_match = Match(
        id="match_1",
        home_team_id="team_a",
        away_team_id="team_b",
        competition_id="comp_1",
        season_id="2024",
        scheduled_at=now + timedelta(days=1),
        status=MatchStatus.SCHEDULED,
        home_score=None,
        away_score=None,
        provider_fetched_at=now,
    )
    
    mock_external_provider.get_matches_async.return_value = [fresh_match]
    
    with patch.object(HybridProvider, '__init__', lambda self, external_provider, session: None):
        provider = HybridProvider(mock_external_provider, mock_session)
        provider.external_provider = mock_external_provider
        provider.db_provider = mock_db_provider
        
        mock_db_provider.get_matches = Mock(return_value=[db_match])
        provider._update_match_statuses = lambda matches: matches
        
        result = await provider.get_matches_async(status="scheduled")
        
        # External provider SHOULD be called (no timestamp = unknown freshness)
        mock_external_provider.get_matches_async.assert_called_once()


@pytest.mark.asyncio
async def test_provider_timeout_uses_stale_data_as_fallback(
    mock_session,
    mock_external_provider,
    mock_db_provider
):
    """When external provider fails, use stale database data as fallback."""
    now = datetime.now(timezone.utc)
    
    # Database has stale data
    db_match = Match(
        id="match_1",
        home_team_id="team_a",
        away_team_id="team_b",
        competition_id="comp_1",
        season_id="2024",
        scheduled_at=now + timedelta(days=1),
        status=MatchStatus.SCHEDULED,
        home_score=None,
        away_score=None,
        provider_fetched_at=now - timedelta(hours=5),  # 5 hours old (stale)
    )
    
    # External provider times out
    mock_external_provider.get_matches_async.side_effect = Exception("Timeout")
    
    with patch.object(HybridProvider, '__init__', lambda self, external_provider, session: None):
        provider = HybridProvider(mock_external_provider, mock_session)
        provider.external_provider = mock_external_provider
        provider.db_provider = mock_db_provider
        
        mock_db_provider.get_matches = Mock(return_value=[db_match])
        provider._update_match_statuses = lambda matches: matches
        
        result = await provider.get_matches_async(status="scheduled")
        
        # External provider was called but failed
        mock_external_provider.get_matches_async.assert_called_once()
        
        # Should fallback to stale database data
        assert len(result) == 1
        assert result[0].id == "match_1"
        # Original timestamp preserved (not updated to "now")
        assert result[0].provider_fetched_at == now - timedelta(hours=5)


@pytest.mark.asyncio
async def test_mixed_freshness_triggers_refresh_all(
    mock_session,
    mock_external_provider,
    mock_db_provider
):
    """If ANY match is stale, refresh all matches in the query."""
    now = datetime.now(timezone.utc)
    
    # Database has 2 matches: one fresh, one stale
    fresh_db_match = Match(
        id="match_1",
        home_team_id="team_a",
        away_team_id="team_b",
        competition_id="comp_1",
        season_id="2024",
        scheduled_at=now + timedelta(days=1),
        status=MatchStatus.SCHEDULED,
        provider_fetched_at=now - timedelta(minutes=30),  # Fresh
    )
    
    stale_db_match = Match(
        id="match_2",
        home_team_id="team_c",
        away_team_id="team_d",
        competition_id="comp_1",
        season_id="2024",
        scheduled_at=now + timedelta(days=2),
        status=MatchStatus.SCHEDULED,
        provider_fetched_at=now - timedelta(hours=5),  # Stale
    )
    
    # External returns fresh data for both
    external_matches = [
        Match(
            id="match_1",
            home_team_id="team_a",
            away_team_id="team_b",
            competition_id="comp_1",
            season_id="2024",
            scheduled_at=now + timedelta(days=1),
            status=MatchStatus.SCHEDULED,
            provider_fetched_at=now,
        ),
        Match(
            id="match_2",
            home_team_id="team_c",
            away_team_id="team_d",
            competition_id="comp_1",
            season_id="2024",
            scheduled_at=now + timedelta(days=2),
            status=MatchStatus.SCHEDULED,
            provider_fetched_at=now,
        ),
    ]
    
    mock_external_provider.get_matches_async.return_value = external_matches
    
    with patch.object(HybridProvider, '__init__', lambda self, external_provider, session: None):
        provider = HybridProvider(mock_external_provider, mock_session)
        provider.external_provider = mock_external_provider
        provider.db_provider = mock_db_provider
        
        mock_db_provider.get_matches = Mock(return_value=[fresh_db_match, stale_db_match])
        provider._update_match_statuses = lambda matches: matches
        
        result = await provider.get_matches_async(status="scheduled")
        
        # External provider SHOULD be called (one match is stale)
        mock_external_provider.get_matches_async.assert_called_once()
        
        # Should get both matches with fresh data
        assert len(result) == 2
