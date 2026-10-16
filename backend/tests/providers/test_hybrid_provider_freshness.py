"""Test HybridProvider data freshness and consistency.

Ensures database-first optimization doesn't compromise data freshness for live matches.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone
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
    provider = Mock()
    provider.get_matches = Mock(return_value=[])
    provider.get_matches_async = AsyncMock(return_value=[])
    return provider


@pytest.fixture
def mock_db_provider():
    """Mock database provider."""
    return Mock()


@pytest.mark.asyncio
async def test_live_matches_always_check_external_provider(
    mock_session,
    mock_external_provider,
    mock_db_provider
):
    """LIVE matches should always check external provider for freshness."""
    # Setup: Database has a live match
    db_match = Match(
        id="match_1",
        home_team_id="team_a",
        away_team_id="team_b",
        competition_id="comp_1",
        season_id="2024",
        scheduled_at=datetime(2024, 1, 1, 15, 0, tzinfo=timezone.utc),
        status=MatchStatus.LIVE,
        home_score=1,
        away_score=0,
    )
    
    # External provider has updated score
    external_match = Match(
        id="match_1",
        home_team_id="team_a",
        away_team_id="team_b",
        competition_id="comp_1",
        season_id="2024",
        scheduled_at=datetime(2024, 1, 1, 15, 0, tzinfo=timezone.utc),
        status=MatchStatus.LIVE,
        home_score=2,  # Score changed!
        away_score=1,
    )
    
    # Mock returns
    mock_external_provider.get_matches_async.return_value = [external_match]
    
    with patch.object(HybridProvider, '__init__', lambda self, external_provider, session: None):
        provider = HybridProvider(mock_external_provider, mock_session)
        provider.external_provider = mock_external_provider
        provider.db_provider = mock_db_provider
        
        # Mock database provider
        mock_db_provider.get_matches = Mock(return_value=[db_match])
        
        # Mock _update_match_statuses to return input as-is
        provider._update_match_statuses = lambda matches: matches
        
        # Query for LIVE matches
        result = await provider.get_matches_async(status="live")
        
        # External provider MUST be called for LIVE matches
        mock_external_provider.get_matches_async.assert_called_once()
        
        # Result should have fresh data from external provider
        assert len(result) == 1
        assert result[0].home_score == 2  # Fresh score, not stale DB score
        assert result[0].away_score == 1


@pytest.mark.asyncio
async def test_scheduled_matches_use_database_first(
    mock_session,
    mock_external_provider,
    mock_db_provider
):
    """SCHEDULED matches with fresh data use database-first optimization."""
    # Setup: Database has scheduled match with recent provider_fetched_at
    db_match = Match(
        id="match_1",
        home_team_id="team_a",
        away_team_id="team_b",
        competition_id="comp_1",
        season_id="2024",
        scheduled_at=datetime(2024, 12, 1, 15, 0, tzinfo=timezone.utc),
        status=MatchStatus.SCHEDULED,
        home_score=None,
        away_score=None,
        provider_fetched_at=datetime.now(timezone.utc),  # Fresh data
    )
    
    with patch.object(HybridProvider, '__init__', lambda self, external_provider, session: None):
        provider = HybridProvider(mock_external_provider, mock_session)
        provider.external_provider = mock_external_provider
        provider.db_provider = mock_db_provider
        
        # Mock database provider
        mock_db_provider.get_matches = Mock(return_value=[db_match])
        
        # Mock _update_match_statuses
        provider._update_match_statuses = lambda matches: matches
        
        # Query for SCHEDULED matches
        result = await provider.get_matches_async(status="scheduled")
        
        # External provider should NOT be called (database-first optimization)
        mock_external_provider.get_matches_async.assert_not_called()
        
        # Result should come from database
        assert len(result) == 1
        assert result[0].id == "match_1"


@pytest.mark.asyncio
async def test_no_status_filter_checks_external_for_freshness(
    mock_session,
    mock_external_provider,
    mock_db_provider
):
    """No status filter means user expects fresh data - check external provider."""
    external_match = Match(
        id="match_1",
        home_team_id="team_a",
        away_team_id="team_b",
        competition_id="comp_1",
        season_id="2024",
        scheduled_at=datetime(2024, 1, 1, 15, 0, tzinfo=timezone.utc),
        status=MatchStatus.LIVE,
        home_score=2,
        away_score=1,
    )
    
    mock_external_provider.get_matches_async.return_value = [external_match]
    
    with patch.object(HybridProvider, '__init__', lambda self, external_provider, session: None):
        provider = HybridProvider(mock_external_provider, mock_session)
        provider.external_provider = mock_external_provider
        provider.db_provider = mock_db_provider
        
        mock_db_provider.get_matches = Mock(return_value=[])
        provider._update_match_statuses = lambda matches: matches
        
        # Query without status filter
        result = await provider.get_matches_async()
        
        # External provider MUST be called
        mock_external_provider.get_matches_async.assert_called_once()
        
        assert len(result) == 1


@pytest.mark.asyncio
async def test_database_empty_fallback_to_external(
    mock_session,
    mock_external_provider,
    mock_db_provider
):
    """If database is empty, should fallback to external provider."""
    external_match = Match(
        id="match_1",
        home_team_id="team_a",
        away_team_id="team_b",
        competition_id="comp_1",
        season_id="2024",
        scheduled_at=datetime(2024, 12, 1, 15, 0, tzinfo=timezone.utc),
        status=MatchStatus.SCHEDULED,
    )
    
    mock_external_provider.get_matches_async.return_value = [external_match]
    
    with patch.object(HybridProvider, '__init__', lambda self, external_provider, session: None):
        provider = HybridProvider(mock_external_provider, mock_session)
        provider.external_provider = mock_external_provider
        provider.db_provider = mock_db_provider
        
        # Database is empty
        mock_db_provider.get_matches = Mock(return_value=[])
        provider._update_match_statuses = lambda matches: matches
        
        # Query for SCHEDULED matches
        result = await provider.get_matches_async(status="scheduled")
        
        # External provider should be called as fallback
        mock_external_provider.get_matches_async.assert_called_once()
        
        # Result should come from external provider
        assert len(result) == 1
        assert result[0].id == "match_1"


@pytest.mark.asyncio
async def test_external_and_database_merge_for_live(
    mock_session,
    mock_external_provider,
    mock_db_provider
):
    """For LIVE matches, external and database results should be merged."""
    # External has match_1 with fresh data
    external_match = Match(
        id="match_1",
        home_team_id="team_a",
        away_team_id="team_b",
        competition_id="comp_1",
        season_id="2024",
        scheduled_at=datetime(2024, 1, 1, 15, 0, tzinfo=timezone.utc),
        status=MatchStatus.LIVE,
        home_score=2,
        away_score=1,
    )
    
    # Database has match_1 (stale) and match_2 (not in external)
    db_match_1 = Match(
        id="match_1",
        home_team_id="team_a",
        away_team_id="team_b",
        competition_id="comp_1",
        season_id="2024",
        scheduled_at=datetime(2024, 1, 1, 15, 0, tzinfo=timezone.utc),
        status=MatchStatus.LIVE,
        home_score=1,  # Stale score
        away_score=0,
    )
    
    db_match_2 = Match(
        id="match_2",
        home_team_id="team_c",
        away_team_id="team_d",
        competition_id="comp_1",
        season_id="2024",
        scheduled_at=datetime(2024, 1, 1, 16, 0, tzinfo=timezone.utc),
        status=MatchStatus.LIVE,
        home_score=0,
        away_score=0,
    )
    
    mock_external_provider.get_matches_async.return_value = [external_match]
    
    with patch.object(HybridProvider, '__init__', lambda self, external_provider, session: None):
        provider = HybridProvider(mock_external_provider, mock_session)
        provider.external_provider = mock_external_provider
        provider.db_provider = mock_db_provider
        
        mock_db_provider.get_matches = Mock(return_value=[db_match_1, db_match_2])
        provider._update_match_statuses = lambda matches: matches
        
        # Query for LIVE matches
        result = await provider.get_matches_async(status="live")
        
        # Should have both matches
        assert len(result) == 2
        
        # match_1 should have fresh external data (not stale DB data)
        match_1_result = next(m for m in result if m.id == "match_1")
        assert match_1_result.home_score == 2  # Fresh, not 1
        
        # match_2 should be from database
        match_2_result = next(m for m in result if m.id == "match_2")
        assert match_2_result.id == "match_2"
