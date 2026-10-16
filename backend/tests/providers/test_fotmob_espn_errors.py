"""Test ESPN error handling in FotMob provider."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import httpx

from app.providers.fotmob import FotMobFootballProvider
from app.providers.exceptions import ProviderError, ProviderTimeoutError


@pytest.mark.asyncio
async def test_espn_http_500_raises_error():
    """ESPN HTTP 500 should raise ProviderError, not return empty list."""
    provider = FotMobFootballProvider('https://www.fotmob.com')
    
    # Mock ESPN returning HTTP 500
    mock_response = MagicMock()
    mock_response.status_code = 500
    
    with patch.object(provider._client, 'get', return_value=mock_response):
        with pytest.raises(ProviderError) as exc_info:
            await provider.get_live_matches()
        
        assert "ESPN API returned HTTP 500" in str(exc_info.value)
    
    await provider.close()


@pytest.mark.asyncio
async def test_espn_http_404_raises_error():
    """ESPN HTTP 404 should raise ProviderError."""
    provider = FotMobFootballProvider('https://www.fotmob.com')
    
    # Mock ESPN returning HTTP 404
    mock_response = MagicMock()
    mock_response.status_code = 404
    
    with patch.object(provider._client, 'get', return_value=mock_response):
        with pytest.raises(ProviderError) as exc_info:
            await provider.get_live_matches()
        
        assert "ESPN API returned HTTP 404" in str(exc_info.value)
    
    await provider.close()


@pytest.mark.asyncio
async def test_espn_timeout_raises_error():
    """ESPN timeout should raise ProviderError."""
    provider = FotMobFootballProvider('https://www.fotmob.com')
    
    # Mock ESPN timing out
    async def mock_timeout(*args, **kwargs):
        raise httpx.TimeoutException("Request timed out")
    
    with patch.object(provider._client, 'get', side_effect=mock_timeout):
        with pytest.raises(ProviderError) as exc_info:
            await provider.get_live_matches()
        
        # Could be ProviderTimeoutError or ProviderError with timeout message
        assert "timed out" in str(exc_info.value).lower() or "Live match detection failed" in str(exc_info.value)
    
    await provider.close()


@pytest.mark.asyncio
async def test_espn_invalid_json_raises_error():
    """ESPN invalid JSON should raise ProviderError."""
    provider = FotMobFootballProvider('https://www.fotmob.com')
    
    # Mock ESPN returning invalid JSON
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = ValueError("Invalid JSON")
    
    with patch.object(provider._client, 'get', return_value=mock_response):
        with pytest.raises(ProviderError) as exc_info:
            await provider.get_live_matches()
        
        assert "invalid json" in str(exc_info.value).lower()
    
    await provider.close()


@pytest.mark.asyncio
async def test_espn_missing_events_field_raises_error():
    """ESPN response missing 'events' field should raise ProviderError."""
    provider = FotMobFootballProvider('https://www.fotmob.com')
    
    # Mock ESPN returning valid JSON but missing 'events'
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "ok"}  # No 'events' field
    
    with patch.object(provider._client, 'get', return_value=mock_response):
        with pytest.raises(ProviderError) as exc_info:
            await provider.get_live_matches()
        
        assert "missing 'events' field" in str(exc_info.value).lower()
    
    await provider.close()


@pytest.mark.asyncio
async def test_espn_empty_events_returns_empty_list():
    """ESPN with empty events array should return empty list (no error)."""
    provider = FotMobFootballProvider('https://www.fotmob.com')
    
    # Mock ESPN returning empty events (no live matches)
    mock_espn_response = MagicMock()
    mock_espn_response.status_code = 200
    mock_espn_response.json.return_value = {"events": []}
    
    # Mock FotMob request (won't be called but needed for structure)
    mock_fotmob_response = MagicMock()
    mock_fotmob_response.status_code = 200
    mock_fotmob_response.json.return_value = {"leagues": []}
    
    call_count = [0]
    
    async def mock_get(url, *args, **kwargs):
        call_count[0] += 1
        if 'espn' in url.lower():
            return mock_espn_response
        return mock_fotmob_response
    
    with patch.object(provider._client, 'get', side_effect=mock_get):
        with patch.object(provider, '_request', return_value={"leagues": []}):
            result = await provider.get_live_matches()
            
            # Should return empty list, not raise error
            assert result == []
    
    await provider.close()


@pytest.mark.asyncio
async def test_fotmob_request_error_after_espn_success():
    """If ESPN succeeds but FotMob request fails, should raise ProviderError."""
    provider = FotMobFootballProvider('https://www.fotmob.com')
    
    # Mock ESPN success
    mock_espn_response = MagicMock()
    mock_espn_response.status_code = 200
    mock_espn_response.json.return_value = {
        "events": [
            {
                "name": "Villarreal at Real Madrid",
                "status": {"type": {"state": "in"}}
            }
        ]
    }
    
    with patch.object(provider._client, 'get', return_value=mock_espn_response):
        # Mock FotMob _request raising error
        with patch.object(provider, '_request', side_effect=ProviderError(
            provider_name="fotmob",
            operation="get_matches",
            message="FotMob API failed"
        )):
            with pytest.raises(ProviderError) as exc_info:
                await provider.get_live_matches()
            
            # Should preserve the FotMob error
            assert "FotMob API failed" in str(exc_info.value) or "fotmob" in str(exc_info.value).lower()
    
    await provider.close()
