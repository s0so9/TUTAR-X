"""Tests for competitions API endpoint.

Tests the competition list endpoint that returns curated major competitions.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


def test_list_competitions_returns_200(client):
    """Test that GET /api/v1/competitions returns 200 OK."""
    response = client.get("/api/v1/competitions")
    assert response.status_code == 200


def test_list_competitions_response_structure(client):
    """Test that response has correct structure with required fields."""
    response = client.get("/api/v1/competitions")
    data = response.json()
    
    # Should have top-level fields
    assert "competitions" in data
    assert "count" in data
    assert "is_development_data" in data
    
    # Types
    assert isinstance(data["competitions"], list)
    assert isinstance(data["count"], int)
    assert isinstance(data["is_development_data"], bool)


def test_list_competitions_has_competitions(client):
    """Test that response contains at least one competition."""
    response = client.get("/api/v1/competitions")
    data = response.json()
    
    assert data["count"] >= 1
    assert len(data["competitions"]) >= 1


def test_competition_structure(client):
    """Test that each competition has required fields with correct types."""
    response = client.get("/api/v1/competitions")
    data = response.json()
    
    for comp in data["competitions"]:
        # Required fields
        assert "id" in comp
        assert "name" in comp
        assert "country" in comp
        
        # Types
        assert isinstance(comp["id"], str)
        assert isinstance(comp["name"], str)
        assert comp["country"] is None or isinstance(comp["country"], str)
        
        # Non-empty values for required fields
        assert comp["id"].strip() != ""
        assert comp["name"].strip() != ""


def test_count_matches_competition_list_length(client):
    """Test that count field matches actual list length."""
    response = client.get("/api/v1/competitions")
    data = response.json()
    
    assert data["count"] == len(data["competitions"])


def test_competitions_have_unique_ids(client):
    """Test that all competition IDs are unique."""
    response = client.get("/api/v1/competitions")
    data = response.json()
    
    competition_ids = [comp["id"] for comp in data["competitions"]]
    assert len(competition_ids) == len(set(competition_ids)), "Competition IDs are not unique"
