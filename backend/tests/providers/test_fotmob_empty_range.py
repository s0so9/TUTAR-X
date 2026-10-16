"""Test FotMob provider handling of failed date ranges.

This test reproduces the scenario where all days in a range fail,
but the provider returns [] instead of raising ProviderError.
"""

import pytest
from datetime import date
from unittest.mock import AsyncMock, Mock
from app.providers.fotmob import FotMobFootballProvider
from app.providers.exceptions import ProviderError


@pytest.mark.asyncio
async def test_get_matches_by_range_all_days_fail():
    """Test that get_matches_by_range raises ProviderError when all days fail.
    
    Current behavior: Returns [] (treated as success by manager)
    Expected behavior: Raises ProviderError so manager tries fallback
    """
    provider = FotMobFootballProvider(
        base_url="https://www.fotmob.com",
        timeout_seconds=10,
        cache=None
    )
    
    # Mock get_matches_by_date to always raise ProviderError
    async def mock_get_matches_by_date(date_obj: date):
        raise ProviderError(
            provider_name="fotmob",
            operation="get_matches_by_date",
            message=f"API returned 403 for {date_obj}"
        )
    
    provider.get_matches_by_date = mock_get_matches_by_date
    
    start_date = date(2026, 10, 13)
    end_date = date(2026, 10, 15)  # 3 days
    
    # Current behavior: returns []
    # Expected behavior: should raise ProviderError
    with pytest.raises(ProviderError) as exc_info:
        await provider.get_matches_by_range(start_date, end_date)
    
    assert "no successful" in exc_info.value.message.lower() or \
           "unavailable" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_get_matches_by_range_partial_success():
    """Test that get_matches_by_range succeeds when some days return matches.
    
    Expected behavior: Returns matches from successful days, logs failures
    """
    provider = FotMobFootballProvider(
        base_url="https://www.fotmob.com",
        timeout_seconds=10,
        cache=None
    )
    
    # Mock get_matches_by_date: day 1 fails, day 2-3 succeed
    call_count = [0]
    
    async def mock_get_matches_by_date(date_obj: date):
        call_count[0] += 1
        if call_count[0] == 1:
            raise ProviderError(
                provider_name="fotmob",
                operation="get_matches_by_date",
                message="First day failed"
            )
        # Return empty list for successful days (legitimately no matches)
        return []
    
    provider.get_matches_by_date = mock_get_matches_by_date
    
    start_date = date(2026, 10, 13)
    end_date = date(2026, 10, 15)
    
    # Should succeed (partial success is OK)
    result = await provider.get_matches_by_range(start_date, end_date)
    
    # Result can be [] if successful days legitimately had no matches
    assert isinstance(result, list)
    assert call_count[0] == 3  # Tried all 3 days


@pytest.mark.asyncio
async def test_get_matches_by_range_empty_vs_failed():
    """Test distinction between successful-empty and failed queries.
    
    A day with legitimately zero matches (HTTP 200, empty array) should
    not be treated the same as a day that failed (HTTP 403, exception).
    """
    provider = FotMobFootballProvider(
        base_url="https://www.fotmob.com",
        timeout_seconds=10,
        cache=None
    )
    
    # Day 1: HTTP 200 but empty matches
    # Day 2: HTTP 403 error
    call_count = [0]
    
    async def mock_get_matches_by_date(date_obj: date):
        call_count[0] += 1
        if call_count[0] == 1:
            # Successful query, legitimately no matches
            return []
        else:
            # Failed query
            raise ProviderError(
                provider_name="fotmob",
                operation="get_matches_by_date",
                message="API error"
            )
    
    provider.get_matches_by_date = mock_get_matches_by_date
    
    start_date = date(2026, 10, 13)
    end_date = date(2026, 10, 14)
    
    # Should succeed because day 1 was successful (even though empty)
    result = await provider.get_matches_by_range(start_date, end_date)
    assert isinstance(result, list)
    assert result == []  # Legitimately empty
