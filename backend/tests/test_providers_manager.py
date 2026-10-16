"""Tests for ProviderManager."""

import pytest
from datetime import datetime, timezone, date
from unittest.mock import AsyncMock, MagicMock

from app.providers.manager import ProviderManager
from app.providers.models import ProviderMatch, ProviderTeam
from app.providers.exceptions import ProviderError, ProviderHTTPError
from app.domain.enums import MatchStatus


@pytest.fixture
def mock_ryzellx():
    """Create mock Ryzellx provider."""
    mock = MagicMock()
    mock.get_match = AsyncMock()
    mock.get_matches_by_date = AsyncMock()
    mock.get_live_matches = AsyncMock()
    mock.get_team = AsyncMock()
    mock.get_player = AsyncMock()
    mock.get_league = AsyncMock()
    mock.get_standings = AsyncMock()
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def mock_fotmob():
    """Create mock FotMob provider."""
    mock = MagicMock()
    mock.get_match = AsyncMock()
    mock.get_matches_by_date = AsyncMock()
    mock.get_live_matches = AsyncMock()
    mock.get_team = AsyncMock()
    mock.get_player = AsyncMock()
    mock.get_league = AsyncMock()
    mock.get_standings = AsyncMock()
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def mock_openligadb():
    """Create mock OpenLigaDB provider."""
    mock = MagicMock()
    mock.get_match = AsyncMock()
    mock.get_matches_by_date = AsyncMock()
    mock.get_live_matches = AsyncMock()
    mock.get_team = AsyncMock()
    mock.get_player = AsyncMock()
    mock.get_league = AsyncMock()
    mock.get_standings = AsyncMock()
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def provider_manager(mock_ryzellx, mock_fotmob, mock_openligadb):
    """Create ProviderManager with mocked providers."""
    return ProviderManager(
        ryzellx=mock_ryzellx,
        fotmob=mock_fotmob,
        openligadb=mock_openligadb,
    )


@pytest.fixture
def sample_provider_match():
    """Create sample ProviderMatch for testing."""
    return ProviderMatch(
        provider="ryzellx",
        source_id="match_123",
        fetched_at=datetime.now(timezone.utc),
        source_updated_at=None,
        is_live=False,
        data_freshness_seconds=None,
        competition_id="comp_1",
        competition_name="Premier League",
        season="2023/2024",
        home_team_id="team_1",
        home_team_name="Team A",
        away_team_id="team_2",
        away_team_name="Team B",
        venue_name="Stadium A",
        scheduled_at=datetime.now(timezone.utc),
        status=MatchStatus.FINISHED,
        minute=None,
        added_time=None,
        home_score=2,
        away_score=1,
        home_score_ht=1,
        away_score_ht=0,
        outcome=None,
        round=10,
    )


@pytest.mark.asyncio
async def test_manager_get_match_uses_match_detail_order(
    provider_manager,
    mock_ryzellx,
    sample_provider_match
):
    """Test that get_match uses MATCH_DETAIL_ORDER (sofascore → ryzellx, ryzellx used when sofascore not configured)."""
    mock_ryzellx.get_match.return_value = sample_provider_match
    
    result, metadata = await provider_manager.get_match("match_123")
    
    assert result is not None
    assert result == sample_provider_match
    assert metadata['selected_provider'] == 'ryzellx'
    # When sofascore is not configured, ryzellx is used (sofascore would have been first if present)
    # So this is technically a fallback from the defined order, but functionally correct
    assert metadata['fallback_used'] is True
    assert 'ryzellx' in metadata['attempted_providers']
    
    # Verify ryzellx was called
    mock_ryzellx.get_match.assert_called_once_with("match_123")


@pytest.mark.asyncio
async def test_manager_get_live_matches_uses_live_order(
    provider_manager,
    mock_fotmob
):
    """Test that get_live_matches uses LIVE_ORDER (fotmob first)."""
    mock_live_matches = [{"match_id": "live_1"}, {"match_id": "live_2"}]
    mock_fotmob.get_live_matches.return_value = mock_live_matches
    
    result, metadata = await provider_manager.get_live_matches()
    
    assert result == mock_live_matches
    assert metadata['selected_provider'] == 'fotmob'
    assert metadata['fallback_used'] is False
    assert 'fotmob' in metadata['attempted_providers']
    
    # Verify fotmob was called
    mock_fotmob.get_live_matches.assert_called_once()


@pytest.mark.asyncio
async def test_manager_get_matches_by_date_uses_normal_order(
    provider_manager,
    mock_ryzellx
):
    """Test that get_matches_by_date uses NORMAL_ORDER (ryzellx first)."""
    mock_matches = [{"match_id": "1"}, {"match_id": "2"}]
    mock_ryzellx.get_matches_by_date.return_value = mock_matches
    
    test_date = date(2024, 3, 15)
    result, metadata = await provider_manager.get_matches_by_date(test_date)
    
    assert result == mock_matches
    assert metadata['selected_provider'] == 'ryzellx'
    assert metadata['fallback_used'] is False
    
    # Verify ryzellx was called with correct date
    mock_ryzellx.get_matches_by_date.assert_called_once_with(test_date)


@pytest.mark.asyncio
async def test_manager_failover_on_provider_error(
    sample_provider_match
):
    """Test failover when primary provider raises ProviderError."""
    # Create fresh mocks for this test
    mock_ryzellx = MagicMock()
    mock_fotmob = MagicMock()
    mock_openligadb = MagicMock()
    mock_ryzellx.close = AsyncMock()
    mock_fotmob.close = AsyncMock()
    mock_openligadb.close = AsyncMock()
    
    # Ryzellx raises error (using AsyncMock properly)
    async def raise_error(*args, **kwargs):
        raise ProviderHTTPError(
            provider_name="ryzellx",
            operation="get_match",
            message="Server error",
            status_code=500
        )
    
    mock_ryzellx.get_match = AsyncMock(side_effect=raise_error)
    
    # FotMob returns None (not found)
    mock_fotmob.get_match = AsyncMock(return_value=None)
    
    # OpenLigaDB succeeds
    openligadb_match = sample_provider_match.model_copy()
    openligadb_match.provider = "openligadb"
    mock_openligadb.get_match = AsyncMock(return_value=openligadb_match)
    
    # Create manager with these mocks
    provider_manager = ProviderManager(
        ryzellx=mock_ryzellx,
        fotmob=mock_fotmob,
        openligadb=mock_openligadb,
    )
    
    result, metadata = await provider_manager.get_match("match_123")
    
    assert result is not None
    assert result.provider == "openligadb"
    assert metadata['selected_provider'] == 'openligadb'
    assert metadata['fallback_used'] is True
    assert 'ryzellx' in metadata['attempted_providers']
    assert 'openligadb' in metadata['attempted_providers']


@pytest.mark.asyncio
async def test_manager_failover_on_none(
    provider_manager,
    mock_ryzellx,
    mock_fotmob,
    sample_provider_match
):
    """Test failover when primary provider returns None."""
    # Ryzellx returns None (not found)
    mock_ryzellx.get_match.return_value = None
    
    # FotMob succeeds
    fotmob_match = sample_provider_match.model_copy()
    fotmob_match.provider = "fotmob"
    mock_fotmob.get_match.return_value = fotmob_match
    
    result, metadata = await provider_manager.get_match("match_123")
    
    assert result is not None
    assert result.provider == "fotmob"
    assert metadata['selected_provider'] == 'fotmob'
    assert metadata['fallback_used'] is True


@pytest.mark.asyncio
async def test_manager_all_providers_fail(
    provider_manager,
    mock_ryzellx,
    mock_fotmob,
    mock_openligadb
):
    """Test that manager returns None when all providers fail."""
    # All providers raise errors
    mock_ryzellx.get_match.side_effect = ProviderError(
        provider_name="ryzellx",
        operation="get_match",
        message="Connection error"
    )
    mock_fotmob.get_match.side_effect = ProviderError(
        provider_name="fotmob",
        operation="get_match",
        message="Connection error"
    )
    mock_openligadb.get_match.side_effect = ProviderError(
        provider_name="openligadb",
        operation="get_match",
        message="Connection error"
    )
    
    result, metadata = await provider_manager.get_match("match_123")
    
    assert result is None
    assert metadata['selected_provider'] is None
    assert len(metadata['attempted_providers']) == 3
    assert 'ryzellx' in metadata['attempted_providers']
    assert 'fotmob' in metadata['attempted_providers']
    assert 'openligadb' in metadata['attempted_providers']


@pytest.mark.asyncio
async def test_manager_source_of_truth_no_failover_for_optional_none(
    provider_manager,
    mock_ryzellx,
    mock_fotmob,
    sample_provider_match
):
    """Test SOURCE-OF-TRUTH rule: no failover for missing optional fields.
    
    If ryzellx returns a valid ProviderMatch (even with some fields as None),
    the manager does NOT try next provider. One provider per response.
    """
    # Ryzellx returns match with some None fields (e.g., no xG, no venue)
    ryzellx_match = sample_provider_match.model_copy()
    ryzellx_match.venue_name = None
    ryzellx_match.home_score_ht = None
    ryzellx_match.away_score_ht = None
    mock_ryzellx.get_match.return_value = ryzellx_match
    
    # FotMob could theoretically provide these fields
    fotmob_match = sample_provider_match.model_copy()
    fotmob_match.provider = "fotmob"
    fotmob_match.venue_name = "Full Stadium Name"
    mock_fotmob.get_match.return_value = fotmob_match
    
    result, metadata = await provider_manager.get_match("match_123")
    
    # Result should be from ryzellx only (SOURCE-OF-TRUTH)
    assert result is not None
    assert result.provider == "ryzellx"
    assert result.venue_name is None  # Not filled from fotmob
    assert metadata['selected_provider'] == 'ryzellx'
    # When sofascore is not configured, ryzellx is used from position 1 in MATCH_DETAIL_ORDER
    assert metadata['fallback_used'] is True
    
    # Verify fotmob was NOT called
    mock_fotmob.get_match.assert_not_called()


@pytest.mark.asyncio
async def test_manager_metadata_structure(
    provider_manager,
    mock_ryzellx,
    sample_provider_match
):
    """Test that metadata has correct structure."""
    mock_ryzellx.get_match.return_value = sample_provider_match
    
    result, metadata = await provider_manager.get_match("match_123")
    
    # Verify metadata structure
    assert 'selected_provider' in metadata
    assert 'attempted_providers' in metadata
    assert 'fallback_used' in metadata
    assert 'fetched_at' in metadata
    
    assert isinstance(metadata['selected_provider'], str)
    assert isinstance(metadata['attempted_providers'], list)
    assert isinstance(metadata['fallback_used'], bool)
    assert isinstance(metadata['fetched_at'], datetime)


@pytest.mark.asyncio
async def test_manager_close_calls_all_providers(
    provider_manager,
    mock_ryzellx,
    mock_fotmob,
    mock_openligadb
):
    """Test that close() calls close on all providers."""
    await provider_manager.close()
    
    mock_ryzellx.close.assert_called_once()
    mock_fotmob.close.assert_called_once()
    mock_openligadb.close.assert_called_once()


@pytest.mark.asyncio
async def test_manager_get_team(
    provider_manager,
    mock_ryzellx
):
    """Test get_team uses METADATA_ORDER."""
    mock_team = ProviderTeam(
        provider="ryzellx",
        source_id="team_123",
        fetched_at=datetime.now(timezone.utc),
        name="Test Team",
    )
    mock_ryzellx.get_team.return_value = mock_team
    
    result, metadata = await provider_manager.get_team("team_123")
    
    assert result == mock_team
    assert metadata['selected_provider'] == 'ryzellx'
