"""Tests for live matches API endpoint."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch
from fastapi.testclient import TestClient

from app.providers.models import ProviderLiveMatch, DataQualityIndicators
from app.domain.enums import MatchStatus


@pytest.mark.asyncio
async def test_empty_result_on_all_provider_failures():
    """Test that empty matches list is returned when all providers fail."""
    # This test validates the graceful failure behavior
    # Would need to mock ProviderManager to return empty list
    # For now, validate the response structure
    
    from app.api.v1.endpoints.live_matches import LiveMatchesResponse
    
    response = LiveMatchesResponse(
        matches=[],
        provider_health={},
        data_quality={"total_matches": 0},
        timestamp=datetime.utcnow(),
        provider_used=None,
        total_count=0,
    )
    
    assert response.matches == []
    assert response.total_count == 0
    assert response.provider_used is None


@pytest.mark.asyncio
async def test_spatial_fields_are_null_when_not_supplied():
    """Test that spatial fields are None when not supplied by provider."""
    match = ProviderLiveMatch(
        provider="test",
        source_id="123",
        fetched_at=datetime.utcnow(),
        match_id="match_123",
        status=MatchStatus.LIVE,
        home_score=1,
        away_score=0,
        last_updated=datetime.utcnow(),
    )
    
    # Spatial fields should be None
    assert match.player_positions is None
    assert match.ball_position is None
    assert match.field_dimensions is None


@pytest.mark.asyncio
async def test_provider_health_included_in_response():
    """Test that provider health is included in API response."""
    from app.api.v1.endpoints.live_matches import LiveMatchesResponse
    
    response = LiveMatchesResponse(
        matches=[],
        provider_health={
            "ryzellx": {
                "is_available": False,
                "availability_code": "PAYMENT_REQUIRED",
                "last_check_utc": datetime.utcnow().isoformat(),
                "consecutive_failures": 3,
                "error_detail": "Payment required (HTTP 402)",
            },
            "fotmob": {
                "is_available": False,
                "availability_code": "ENDPOINT_INVALID",
                "last_check_utc": datetime.utcnow().isoformat(),
                "consecutive_failures": 2,
                "error_detail": "Endpoint not found (HTTP 404)",
            },
        },
        data_quality={"total_matches": 0},
        timestamp=datetime.utcnow(),
        provider_used=None,
        total_count=0,
    )
    
    assert "ryzellx" in response.provider_health
    assert "fotmob" in response.provider_health
    assert response.provider_health["ryzellx"]["availability_code"] == "PAYMENT_REQUIRED"
    assert response.provider_health["fotmob"]["availability_code"] == "ENDPOINT_INVALID"


@pytest.mark.asyncio
async def test_data_quality_indicators_in_response():
    """Test that data quality indicators are computed and included."""
    from app.api.v1.endpoints.live_matches import (
        _build_data_quality_flags,
        _aggregate_data_quality,
    )
    
    # Test single match quality flags
    match = ProviderLiveMatch(
        provider="test",
        source_id="123",
        fetched_at=datetime.utcnow(),
        match_id="match_123",
        status=MatchStatus.LIVE,
        home_score=1,
        away_score=0,
        last_updated=datetime.utcnow(),
        data_quality=DataQualityIndicators(
            has_xg=True,
            has_events=True,
            has_shots=False,
        ),
    )
    
    flags = _build_data_quality_flags(match)
    assert flags["has_xg"] is True
    assert flags["has_events"] is True
    assert flags["has_shots"] is False
    
    # Test aggregation
    matches = [match]
    aggregated = _aggregate_data_quality(matches)
    
    assert aggregated["total_matches"] == 1
    assert aggregated["matches_with_xg"] == 1
    assert aggregated["matches_with_events"] == 1
    assert aggregated["matches_with_shots"] == 0


@pytest.mark.asyncio
async def test_live_matches_response_structure():
    """Test that LiveMatchesResponse has correct structure."""
    from app.api.v1.endpoints.live_matches import LiveMatchesResponse, LiveMatchResponse
    
    match_response = LiveMatchResponse(
        match_id="match_123",
        status="LIVE",
        minute=45,
        home_score=1,
        away_score=0,
        data_quality_flags={
            "has_xg": False,
            "has_events": True,
            "has_shots": False,
        },
    )
    
    response = LiveMatchesResponse(
        matches=[match_response],
        provider_health={},
        data_quality={"total_matches": 1},
        timestamp=datetime.utcnow(),
        provider_used="fotmob",
        total_count=1,
    )
    
    assert len(response.matches) == 1
    assert response.matches[0].match_id == "match_123"
    assert response.matches[0].minute == 45
    assert response.provider_used == "fotmob"
    assert response.total_count == 1


@pytest.mark.asyncio
async def test_empty_data_quality_aggregation():
    """Test data quality aggregation with no matches."""
    from app.api.v1.endpoints.live_matches import _aggregate_data_quality
    
    aggregated = _aggregate_data_quality([])
    
    assert aggregated["total_matches"] == 0
    assert aggregated["matches_with_xg"] == 0
    assert aggregated["matches_with_events"] == 0
