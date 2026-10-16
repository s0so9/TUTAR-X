"""Tests for provider health monitoring system."""

import pytest
from unittest.mock import AsyncMock, Mock
import httpx

from app.providers.health import (
    ProviderAvailabilityCode,
    ProviderHealthStatus,
    ProviderHealthService,
)


@pytest.mark.asyncio
async def test_ryzellx_402_maps_to_payment_required():
    """Test that Ryzellx 402 response maps to PAYMENT_REQUIRED."""
    mock_response = Mock()
    mock_response.status_code = 402
    
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_response)
    
    service = ProviderHealthService(
        provider_configs={
            "ryzellx": {
                "base_url": "https://api.example.com",
                "test_endpoints": ["/api/matches/live"],
            }
        },
        timeout_seconds=10.0,
    )
    
    status = await service.check_provider("ryzellx", http_client=mock_client)
    
    assert status.availability_code == ProviderAvailabilityCode.PAYMENT_REQUIRED
    assert not status.is_available
    assert "402" in status.error_detail


@pytest.mark.asyncio
async def test_fotmob_404_maps_to_endpoint_invalid():
    """Test that FotMob 404 response maps to ENDPOINT_INVALID."""
    mock_response = Mock()
    mock_response.status_code = 404
    
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_response)
    
    service = ProviderHealthService(
        provider_configs={
            "fotmob": {
                "base_url": "https://www.fotmob.com",
                "test_endpoints": ["/api/data/matches?date=20261005"],
            }
        },
        timeout_seconds=10.0,
    )
    
    status = await service.check_provider("fotmob", http_client=mock_client)
    
    assert status.availability_code == ProviderAvailabilityCode.ENDPOINT_INVALID
    assert not status.is_available
    assert "404" in status.error_detail


@pytest.mark.asyncio
async def test_timeout_maps_to_timeout_code():
    """Test that timeout maps to TIMEOUT availability code."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
    
    service = ProviderHealthService(
        provider_configs={
            "test": {
                "base_url": "https://api.example.com",
                "test_endpoints": ["/test"],
            }
        },
        timeout_seconds=10.0,
    )
    
    status = await service.check_provider("test", http_client=mock_client)
    
    assert status.availability_code == ProviderAvailabilityCode.TIMEOUT
    assert not status.is_available
    assert "timeout" in status.error_detail.lower()


@pytest.mark.asyncio
async def test_consecutive_failures_tracked():
    """Test that consecutive failures are tracked correctly."""
    mock_response = Mock()
    mock_response.status_code = 500
    
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_response)
    
    service = ProviderHealthService(
        provider_configs={
            "test": {
                "base_url": "https://api.example.com",
                "test_endpoints": ["/test"],
            }
        },
        timeout_seconds=10.0,
    )
    
    # First failure
    status1 = await service.check_provider("test", http_client=mock_client)
    assert status1.consecutive_failures == 1
    
    # Second failure
    status2 = await service.check_provider("test", http_client=mock_client)
    assert status2.consecutive_failures == 2
    
    # Third failure
    status3 = await service.check_provider("test", http_client=mock_client)
    assert status3.consecutive_failures == 3


@pytest.mark.asyncio
async def test_available_on_200():
    """Test that HTTP 200 maps to AVAILABLE."""
    mock_response = Mock()
    mock_response.status_code = 200
    
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_response)
    
    service = ProviderHealthService(
        provider_configs={
            "test": {
                "base_url": "https://api.example.com",
                "test_endpoints": ["/test"],
            }
        },
        timeout_seconds=10.0,
    )
    
    status = await service.check_provider("test", http_client=mock_client)
    
    assert status.availability_code == ProviderAvailabilityCode.AVAILABLE
    assert status.is_available
    assert status.consecutive_failures == 0
    assert status.last_success_utc is not None


@pytest.mark.asyncio
async def test_no_secrets_in_error_detail():
    """Test that error_detail never contains secrets."""
    # Simulate an exception that might contain sensitive data
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(
        side_effect=Exception("API key abc123secret should not appear")
    )
    
    service = ProviderHealthService(
        provider_configs={
            "test": {
                "base_url": "https://api.example.com",
                "test_endpoints": ["/test"],
            }
        },
        timeout_seconds=10.0,
    )
    
    status = await service.check_provider("test", http_client=mock_client)
    
    # Error detail should only contain exception type, not message
    assert status.error_detail == "Error: Exception"
    assert "abc123secret" not in status.error_detail
    assert "API key" not in status.error_detail
