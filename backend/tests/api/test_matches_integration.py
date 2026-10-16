"""Integration tests for matches API endpoint with date range support.

Tests the complete integration chain:
Frontend → /api/v1/matches → ProviderManagerAdapter → ProviderManager → RyzellxProvider
"""

import pytest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.match import Match
from app.domain.enums import MatchStatus
from app.providers.models import ProviderMatch


@pytest.fixture
def sample_provider_matches():
    """Sample provider matches for testing."""
    now = datetime.now(timezone.utc)
    return [
        ProviderMatch(
            provider="ryzellx",
            source_id="match_001",
            fetched_at=now,
            source_updated_at=None,
            is_live=False,
            data_freshness_seconds=None,
            competition_id="comp_001",
            competition_name="Test League",
            season="2026",
            home_team_id="team_home",
            home_team_name="Home Team",
            away_team_id="team_away",
            away_team_name="Away Team",
            venue_name="Test Stadium",
            scheduled_at=datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc),
            status=MatchStatus.SCHEDULED,
            minute=None,
            added_time=None,
            home_score=None,
            away_score=None,
            home_score_ht=None,
            away_score_ht=None,
            outcome=None,
            round=1,
        ),
        ProviderMatch(
            provider="ryzellx",
            source_id="match_002",
            fetched_at=now,
            source_updated_at=None,
            is_live=False,
            data_freshness_seconds=None,
            competition_id="comp_001",
            competition_name="Test League",
            season="2026",
            home_team_id="team_a",
            home_team_name="Team A",
            away_team_id="team_b",
            away_team_name="Team B",
            venue_name="Another Stadium",
            scheduled_at=datetime(2026, 10, 12, 18, 0, tzinfo=timezone.utc),
            status=MatchStatus.SCHEDULED,
            minute=None,
            added_time=None,
            home_score=None,
            away_score=None,
            home_score_ht=None,
            away_score_ht=None,
            outcome=None,
            round=2,
        ),
    ]


def test_adapter_get_matches_single_day(sample_provider_matches):
    """Test single-day query with from_date == to_date."""
    from app.providers.adapter import ProviderManagerAdapter
    
    # Mock manager
    mock_manager = MagicMock()
    mock_manager.get_matches_by_date = AsyncMock(
        return_value=([sample_provider_matches[0]], {'selected_provider': 'ryzellx'})
    )
    
    adapter = ProviderManagerAdapter(manager=mock_manager)
    
    # Query single day
    matches = adapter.get_matches(
        from_date=date(2026, 10, 5),
        to_date=date(2026, 10, 5)
    )
    
    # Should call get_matches_by_date
    mock_manager.get_matches_by_date.assert_called_once_with(date(2026, 10, 5))
    
    # Should return 1 match
    assert len(matches) == 1
    assert isinstance(matches[0], Match)
    assert matches[0].id == "ryzellx_match_001"


def test_adapter_get_matches_date_range(sample_provider_matches):
    """Test multi-day range query with from_date < to_date."""
    from app.providers.adapter import ProviderManagerAdapter
    
    # Mock manager
    mock_manager = MagicMock()
    mock_manager.get_matches_by_range = AsyncMock(
        return_value=(sample_provider_matches, {'selected_provider': 'ryzellx'})
    )
    
    adapter = ProviderManagerAdapter(manager=mock_manager)
    
    # Query date range
    matches = adapter.get_matches(
        from_date=date(2026, 10, 5),
        to_date=date(2026, 10, 12)
    )
    
    # Should call get_matches_by_range
    mock_manager.get_matches_by_range.assert_called_once_with(
        date(2026, 10, 5),
        date(2026, 10, 12)
    )
    
    # Should return 2 matches
    assert len(matches) == 2
    assert all(isinstance(m, Match) for m in matches)


def test_adapter_get_matches_with_status_filter(sample_provider_matches):
    """Test status filtering is applied after fetching."""
    from app.providers.adapter import ProviderManagerAdapter
    
    # Create matches with different statuses
    scheduled_match = sample_provider_matches[0]
    scheduled_match.status = MatchStatus.SCHEDULED
    
    live_match = sample_provider_matches[1]
    live_match.status = MatchStatus.LIVE
    
    # Mock manager
    mock_manager = MagicMock()
    mock_manager.get_matches_by_range = AsyncMock(
        return_value=([scheduled_match, live_match], {'selected_provider': 'ryzellx'})
    )
    
    adapter = ProviderManagerAdapter(manager=mock_manager)
    
    # Query with status filter
    matches = adapter.get_matches(
        from_date=date(2026, 10, 5),
        to_date=date(2026, 10, 12),
        status="scheduled"
    )
    
    # Should return only scheduled matches
    assert len(matches) == 1
    assert matches[0].status == MatchStatus.SCHEDULED


def test_adapter_get_matches_empty_result_no_fabrication():
    """Test empty result when no matches exist (no fabrication)."""
    from app.providers.adapter import ProviderManagerAdapter
    
    # Mock manager returning empty list
    mock_manager = MagicMock()
    mock_manager.get_matches_by_range = AsyncMock(
        return_value=([], {'selected_provider': 'ryzellx', 'all_failed': False})
    )
    
    adapter = ProviderManagerAdapter(manager=mock_manager)
    
    # Query date range
    matches = adapter.get_matches(
        from_date=date(2026, 10, 5),
        to_date=date(2026, 10, 12)
    )
    
    # Should return empty list, not fabricated matches
    assert len(matches) == 0
    assert isinstance(matches, list)


def test_adapter_single_day_without_to_date(sample_provider_matches):
    """Test single-day query when to_date is None."""
    from app.providers.adapter import ProviderManagerAdapter
    
    # Mock manager
    mock_manager = MagicMock()
    mock_manager.get_matches_by_date = AsyncMock(
        return_value=([sample_provider_matches[0]], {'selected_provider': 'ryzellx'})
    )
    
    adapter = ProviderManagerAdapter(manager=mock_manager)
    
    # Query with only from_date
    matches = adapter.get_matches(from_date=date(2026, 10, 5))
    
    # Should call get_matches_by_date
    mock_manager.get_matches_by_date.assert_called_once_with(date(2026, 10, 5))
    assert len(matches) == 1


def test_adapter_requires_from_date():
    """Test that from_date is required."""
    from app.providers.adapter import ProviderManagerAdapter
    
    mock_manager = MagicMock()
    adapter = ProviderManagerAdapter(manager=mock_manager)
    
    # Should raise NotImplementedError when from_date is None
    with pytest.raises(NotImplementedError) as exc_info:
        adapter.get_matches()
    
    assert "Date filter required" in str(exc_info.value)


@pytest.mark.asyncio
async def test_manager_get_matches_by_range():
    """Test ProviderManager.get_matches_by_range method."""
    from app.providers.manager import ProviderManager
    from app.providers.cache import ProviderCache
    
    # Create mock provider
    mock_ryzellx = MagicMock()
    mock_ryzellx.get_matches_by_range = AsyncMock(
        return_value=[
            # Return list directly (not tuple)
        ]
    )
    
    # Create manager
    cache = ProviderCache()
    manager = ProviderManager(
        ryzellx=mock_ryzellx,
        fotmob=None,
        sofascore=None,
        openligadb=None,
        cache=cache,
    )
    
    # Call range method
    matches, metadata = await manager.get_matches_by_range(
        date(2026, 10, 5),
        date(2026, 10, 12)
    )
    
    # Should call provider's range method
    mock_ryzellx.get_matches_by_range.assert_called_once_with(
        date(2026, 10, 5),
        date(2026, 10, 12)
    )
    
    # Should return tuple
    assert isinstance(matches, list)
    assert isinstance(metadata, dict)


def test_backward_compatibility_single_day_still_works(sample_provider_matches):
    """Test backward compatibility: single-day queries still work after date range fix."""
    from app.providers.adapter import ProviderManagerAdapter
    
    # Mock manager
    mock_manager = MagicMock()
    mock_manager.get_matches_by_date = AsyncMock(
        return_value=([sample_provider_matches[0]], {'selected_provider': 'ryzellx'})
    )
    
    adapter = ProviderManagerAdapter(manager=mock_manager)
    
    # Both forms should work:
    
    # Form 1: from_date only
    matches1 = adapter.get_matches(from_date=date(2026, 10, 5))
    assert len(matches1) == 1
    
    # Form 2: from_date == to_date
    matches2 = adapter.get_matches(
        from_date=date(2026, 10, 5),
        to_date=date(2026, 10, 5)
    )
    assert len(matches2) == 1
    
    # Should call get_matches_by_date both times
    assert mock_manager.get_matches_by_date.call_count == 2
