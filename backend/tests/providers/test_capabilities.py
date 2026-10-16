"""Tests for provider capability detection system."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, Mock
import httpx

from app.providers.capabilities import (
    ProviderCapabilityStatus,
    ProviderCapability,
    ProviderCapabilityMatrix,
    detect_provider_capabilities,
)


@pytest.mark.asyncio
async def test_default_capabilities_are_not_tested():
    """Test that default capabilities are NOT_TESTED without validation."""
    # Create mock HTTP client that returns no endpoints
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    
    matrix = await detect_provider_capabilities(
        provider_name="test_provider",
        base_url="https://api.example.com",
        test_endpoints={},  # No endpoints to test
        http_client=mock_client,
    )
    
    assert matrix.provider_name == "test_provider"
    assert all(
        status == ProviderCapabilityStatus.NOT_TESTED
        for status in matrix.capabilities.values()
    )


@pytest.mark.asyncio
async def test_payment_required_maps_to_payment_required_status():
    """Test that HTTP 402 maps to PAYMENT_REQUIRED status."""
    # Mock HTTP response with 402 status
    mock_response = Mock()
    mock_response.status_code = 402
    
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_response)
    
    matrix = await detect_provider_capabilities(
        provider_name="ryzellx",
        base_url="https://api.example.com",
        test_endpoints={
            ProviderCapability.live_matches: "/api/matches/live"
        },
        http_client=mock_client,
    )
    
    assert matrix.capabilities[ProviderCapability.live_matches] == ProviderCapabilityStatus.PAYMENT_REQUIRED
    assert "402" in matrix.detection_notes[ProviderCapability.live_matches.value]


@pytest.mark.asyncio
async def test_capability_matrix_serialization():
    """Test that ProviderCapabilityMatrix can be serialized."""
    matrix = ProviderCapabilityMatrix(
        provider_name="test",
        capabilities={
            ProviderCapability.live_matches: ProviderCapabilityStatus.SUPPORTED,
            ProviderCapability.xg_data: ProviderCapabilityStatus.UNAVAILABLE,
        },
        last_detected_utc=datetime.utcnow(),
        detection_notes={"test": "note"},
    )
    
    # Should serialize to dict without errors
    data = matrix.model_dump()
    assert data["provider_name"] == "test"
    assert "capabilities" in data
    assert "last_detected_utc" in data


@pytest.mark.asyncio
async def test_auth_error_maps_to_auth_required_status():
    """Test that HTTP 401/403 map to AUTH_REQUIRED status."""
    # Test 401
    mock_response_401 = Mock()
    mock_response_401.status_code = 401
    
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_response_401)
    
    matrix = await detect_provider_capabilities(
        provider_name="test",
        base_url="https://api.example.com",
        test_endpoints={
            ProviderCapability.match_details: "/api/match/123"
        },
        http_client=mock_client,
    )
    
    assert matrix.capabilities[ProviderCapability.match_details] == ProviderCapabilityStatus.AUTH_REQUIRED
    assert "401" in matrix.detection_notes[ProviderCapability.match_details.value]
    
    # Test 403
    mock_response_403 = Mock()
    mock_response_403.status_code = 403
    
    mock_client.get = AsyncMock(return_value=mock_response_403)
    
    matrix = await detect_provider_capabilities(
        provider_name="test",
        base_url="https://api.example.com",
        test_endpoints={
            ProviderCapability.match_details: "/api/match/123"
        },
        http_client=mock_client,
    )
    
    assert matrix.capabilities[ProviderCapability.match_details] == ProviderCapabilityStatus.AUTH_REQUIRED
    assert "403" in matrix.detection_notes[ProviderCapability.match_details.value]


@pytest.mark.asyncio
async def test_timeout_maps_to_unavailable_status():
    """Test that timeout maps to UNAVAILABLE status."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
    
    matrix = await detect_provider_capabilities(
        provider_name="test",
        base_url="https://api.example.com",
        test_endpoints={
            ProviderCapability.live_matches: "/api/live"
        },
        http_client=mock_client,
    )
    
    assert matrix.capabilities[ProviderCapability.live_matches] == ProviderCapabilityStatus.UNAVAILABLE
    assert "Timeout" in matrix.detection_notes[ProviderCapability.live_matches.value]
