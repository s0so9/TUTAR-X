#!/usr/bin/env python3
"""Test hybrid provider fallback functionality."""
import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from datetime import date

from app.providers.hybrid_provider import HybridProvider
from app.domain.enums import MatchStatus


@pytest.fixture
def mock_db_provider():
    """Mock database provider."""
    mock = Mock()
    mock.get_matches = Mock()
    return mock


@pytest.fixture
def mock_external_provider():
    """Mock external provider."""
    mock = Mock()
    mock.get_matches_async = AsyncMock()
    return mock


@pytest.fixture
def mock_session():
    """Mock database session."""
    return Mock()


@pytest.fixture
def hybrid_provider(mock_external_provider, mock_session, mock_db_provider):
    """Create hybrid provider instance."""
    provider = HybridProvider(
        external_provider=mock_external_provider,
        session=mock_session
    )
    # Replace the auto-created db_provider with our mock
    provider.db_provider = mock_db_provider
    return provider


def create_mock_match(match_id: str, status: MatchStatus, scheduled_at: str):
    """Create a mock match for testing."""
    match = MagicMock()
    match.id = match_id
    match.status = status
    match.scheduled_at = scheduled_at
    match.home_team_id = "home_team_1"
    match.away_team_id = "away_team_1"
    match.competition_id = "comp_1"
    match.season_id = "2026/27"
    return match


class TestHybridProviderFallback:
    """Test hybrid provider fallback behavior."""
    
    @pytest.mark.asyncio
    async def test_database_first_when_results_exist(self, hybrid_provider, mock_external_provider):
        """Test that external provider is NOT called when database has results."""
        # Setup: Database returns matches
        db_matches = [
            create_mock_match("db_match_1", MatchStatus.SCHEDULED, "2026-10-10T15:00:00"),
            create_mock_match("db_match_2", MatchStatus.SCHEDULED, "2026-10-10T17:00:00"),
        ]
        hybrid_provider.db_provider.get_matches.return_value = db_matches
        
        # Execute: Get matches with status filter
        result = await hybrid_provider.get_matches_async(
            from_date=date(2026, 10, 10),
            to_date=date(2026, 10, 17),
            status="SCHEDULED"
        )
        
        # Verify: Database was called
        hybrid_provider.db_provider.get_matches.assert_called_once_with(
            competition_id=None,
            season_id=None,
            team_id=None,
            from_date=date(2026, 10, 10),
            to_date=date(2026, 10, 17),
            status="SCHEDULED"
        )
        
        # Verify: External provider was NOT called (database-first optimization)
        mock_external_provider.get_matches_async.assert_not_called()
        
        # Verify: Database results returned
        assert len(result) == 2
        assert result[0].id == "db_match_1"
        assert result[1].id == "db_match_2"
    
    @pytest.mark.asyncio
    async def test_fallback_when_database_empty(self, hybrid_provider, mock_external_provider):
        """Test that external provider is called as fallback when database is empty."""
        # Setup: Database returns empty list
        hybrid_provider.db_provider.get_matches.return_value = []
        
        # Setup: External provider returns matches (unfiltered)
        external_matches = [
            create_mock_match("ext_match_1", MatchStatus.SCHEDULED, "2026-10-10T15:00:00"),
            create_mock_match("ext_match_2", MatchStatus.FINISHED, "2026-10-10T17:00:00"),
            create_mock_match("ext_match_3", MatchStatus.SCHEDULED, "2026-10-10T19:00:00"),
        ]
        mock_external_provider.get_matches_async.return_value = external_matches
        
        # Execute: Get matches with status filter
        result = await hybrid_provider.get_matches_async(
            from_date=date(2026, 10, 10),
            to_date=date(2026, 10, 17),
            status="SCHEDULED"
        )
        
        # Verify: Database was called first
        hybrid_provider.db_provider.get_matches.assert_called_once()
        
        # Verify: External provider was called as fallback
        mock_external_provider.get_matches_async.assert_called_once_with(
            competition_id=None,
            season_id=None,
            team_id=None,
            from_date=date(2026, 10, 10),
            to_date=date(2026, 10, 17),
            status=None  # provider_status_filter is None
        )
        
        # Verify: Status filter applied to external results
        assert len(result) == 2  # Only SCHEDULED matches
        assert result[0].id == "ext_match_1"
        assert result[1].id == "ext_match_3"
        assert all(m.status == MatchStatus.SCHEDULED for m in result)
    
    @pytest.mark.asyncio
    async def test_external_provider_failure_handled(self, hybrid_provider, mock_external_provider):
        """Test that external provider failures are handled gracefully."""
        # Setup: Database returns empty list
        hybrid_provider.db_provider.get_matches.return_value = []
        
        # Setup: External provider raises exception
        mock_external_provider.get_matches_async.side_effect = Exception("External API failed")
        
        # Execute: Get matches with status filter
        result = await hybrid_provider.get_matches_async(
            status="SCHEDULED"
        )
        
        # Verify: Database was called
        hybrid_provider.db_provider.get_matches.assert_called_once()
        
        # Verify: External provider was called (and failed)
        mock_external_provider.get_matches_async.assert_called_once()
        
        # Verify: Empty result returned (no crash)
        assert len(result) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])