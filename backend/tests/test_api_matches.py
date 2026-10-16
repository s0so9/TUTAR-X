"""Tests for match API endpoints.

This test module verifies the match-related REST API endpoints
work correctly with the DevelopmentProvider.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.providers import DevelopmentProvider


@pytest.fixture
def client():
    """Create a test client for the FastAPI app with DevelopmentProvider."""
    from app.api.dependencies import get_data_provider
    
    # Override provider to use DevelopmentProvider for consistent test behavior
    app.dependency_overrides[get_data_provider] = lambda: DevelopmentProvider()
    client = TestClient(app)
    yield client
    # Clean up override
    app.dependency_overrides.clear()


@pytest.fixture
def dev_provider():
    """Create a DevelopmentProvider instance for reference."""
    return DevelopmentProvider()


@pytest.fixture
def predictable_match_id(client):
    """Find a match that has sufficient data for predictions."""
    response = client.get("/api/v1/matches")
    matches_data = response.json()
    
    for match in matches_data.get("matches", [])[:5]:  # Test first 5 matches
        response = client.get(f"/api/v1/matches/{match['id']}/prediction")
        if response.status_code == 200:
            return match["id"]
    
    # If no match has data, return None (tests will skip)
    return None


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_endpoint_returns_200(self, client):
        """Verify health endpoint returns 200 OK."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_endpoint_response_structure(self, client):
        """Verify health endpoint returns expected structure."""
        response = client.get("/health")
        data = response.json()
        assert "status" in data
        assert "service" in data
        assert "version" in data
        assert "database" in data
        assert "database_details" in data
        assert "ingestion_service" in data
        
        # Status can be 'healthy' or 'degraded' depending on environment
        assert data["status"] in ["healthy", "degraded"]
        
        # Database details should contain connection info
        db_details = data["database_details"]
        assert "connection_verified" in db_details
        assert isinstance(db_details["connection_verified"], bool)


class TestMatchListEndpoint:
    """Tests for GET /api/v1/matches endpoint."""

    def test_list_matches_returns_200(self, client):
        """Verify match list endpoint returns 200 OK."""
        response = client.get("/api/v1/matches")
        assert response.status_code == 200

    def test_list_matches_response_structure(self, client):
        """Verify match list response has correct structure."""
        response = client.get("/api/v1/matches")
        data = response.json()
        
        # Verify top-level structure
        assert "matches" in data
        assert "count" in data
        assert "is_development_data" in data
        
        # Verify it's a list
        assert isinstance(data["matches"], list)
        assert isinstance(data["count"], int)
        assert isinstance(data["is_development_data"], bool)

    def test_list_matches_returns_development_data(self, client):
        """Verify the development data flag is set correctly."""
        response = client.get("/api/v1/matches")
        data = response.json()
        
        # With DevelopmentProvider, should be True
        assert data["is_development_data"] is True

    def test_list_matches_count_matches_list_length(self, client):
        """Verify count field matches the actual number of matches."""
        response = client.get("/api/v1/matches")
        data = response.json()
        
        assert data["count"] == len(data["matches"])

    def test_list_matches_returns_non_empty(self, client):
        """Verify the endpoint returns matches from database."""
        response = client.get("/api/v1/matches")
        data = response.json()
        
        # Database should have matches
        assert len(data["matches"]) > 0
        assert data["count"] == len(data["matches"])

    def test_list_matches_contains_required_fields(self, client):
        """Verify each match contains required fields."""
        response = client.get("/api/v1/matches")
        data = response.json()
        
        if len(data["matches"]) > 0:
            match = data["matches"][0]
            
            # Required fields
            assert "id" in match
            assert "competition_id" in match
            assert "season_id" in match
            assert "home_team_id" in match
            assert "away_team_id" in match
            assert "scheduled_at" in match
            assert "status" in match
            assert "created_at" in match
            assert "updated_at" in match

    def test_list_matches_filter_by_competition(self, client):
        """Verify filtering by competition_id works."""
        # Get matches to find a competition ID
        response = client.get("/api/v1/matches")
        matches_data = response.json()
        
        if len(matches_data["matches"]) > 0:
            comp_id = matches_data["matches"][0]["competition_id"]
            
            response = client.get(f"/api/v1/matches?competition_id={comp_id}")
            data = response.json()
            
            assert response.status_code == 200
            # All returned matches should be from this competition
            for match in data["matches"]:
                assert match["competition_id"] == comp_id

    def test_list_matches_filter_by_team(self, client):
        """Verify filtering by team_id works."""
        # Get matches to find a team ID
        response = client.get("/api/v1/matches")
        matches_data = response.json()
        
        if len(matches_data["matches"]) > 0:
            team_id = matches_data["matches"][0]["home_team_id"]
            
            response = client.get(f"/api/v1/matches?team_id={team_id}")
            data = response.json()
            
            assert response.status_code == 200
            # All returned matches should involve this team
            for match in data["matches"]:
                assert (match["home_team_id"] == team_id or 
                       match["away_team_id"] == team_id)

    def test_list_matches_dev_prefix_present(self, client):
        """Verify development data flag is correctly set."""
        response = client.get("/api/v1/matches")
        data = response.json()
        
        # DevelopmentProvider should return True
        assert data["is_development_data"] is True


class TestMatchDetailEndpoint:
    """Tests for GET /api/v1/matches/{match_id} endpoint."""

    def test_get_match_returns_200_for_existing_match(self, client):
        """Verify getting an existing match returns 200 OK."""
        # Get a valid match ID from the API itself
        response = client.get("/api/v1/matches")
        assert response.status_code == 200
        
        matches_data = response.json()
        matches = matches_data.get("matches", [])
        assert len(matches) > 0, "API should return matches"
        
        match_id = matches[0]["id"]
        response = client.get(f"/api/v1/matches/{match_id}")
        
        assert response.status_code == 200

    def test_get_match_returns_404_for_invalid_match(self, client):
        """Verify getting a non-existent match returns 404."""
        invalid_id = "nonexistent-match-id-12345"
        response = client.get(f"/api/v1/matches/{invalid_id}")
        
        assert response.status_code == 404

    def test_get_match_404_contains_detail(self, client):
        """Verify 404 response contains error detail."""
        invalid_id = "nonexistent-match-id-12345"
        response = client.get(f"/api/v1/matches/{invalid_id}")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_get_match_response_structure(self, client):
        """Verify match detail response has correct structure."""
        # Get a valid match ID from API
        response = client.get("/api/v1/matches")
        matches_data = response.json()
        match_id = matches_data["matches"][0]["id"]
        
        response = client.get(f"/api/v1/matches/{match_id}")
        data = response.json()
        
        # Verify top-level structure
        assert "match" in data
        assert "is_development_data" in data
        
        # Verify match object
        match = data["match"]
        assert "id" in match
        assert "competition_id" in match
        assert "home_team_id" in match
        assert "away_team_id" in match
        assert "scheduled_at" in match

    def test_get_match_returns_development_data_flag(self, client):
        """Verify the development data flag is set correctly."""
        # Get a valid match ID from API
        response = client.get("/api/v1/matches")
        matches_data = response.json()
        match_id = matches_data["matches"][0]["id"]
        
        response = client.get(f"/api/v1/matches/{match_id}")
        data = response.json()
        
        # DevelopmentProvider should return True
        assert data["is_development_data"] is True

    def test_get_match_returns_correct_match(self, client):
        """Verify the returned match has the requested ID."""
        # Get a valid match ID from API
        response = client.get("/api/v1/matches")
        matches_data = response.json()
        match_id = matches_data["matches"][0]["id"]
        
        response = client.get(f"/api/v1/matches/{match_id}")
        data = response.json()
        
        assert data["match"]["id"] == match_id

    def test_get_match_contains_all_fields(self, client):
        """Verify match detail contains all expected fields."""
        # Get a valid match ID from API
        response = client.get("/api/v1/matches")
        matches_data = response.json()
        match_id = matches_data["matches"][0]["id"]
        
        response = client.get(f"/api/v1/matches/{match_id}")
        data = response.json()
        match = data["match"]
        
        # Required fields
        required_fields = [
            "id",
            "competition_id",
            "season_id",
            "home_team_id",
            "away_team_id",
            "scheduled_at",
            "status",
            "created_at",
            "updated_at",
        ]
        
        for field in required_fields:
            assert field in match, f"Missing field: {field}"


class TestAPIDocumentation:
    """Tests for API documentation endpoints."""

    def test_openapi_docs_accessible(self, client):
        """Verify OpenAPI documentation is accessible."""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_openapi_json_accessible(self, client):
        """Verify OpenAPI JSON schema is accessible."""
        response = client.get("/openapi.json")
        assert response.status_code == 200

    def test_openapi_schema_contains_match_endpoints(self, client):
        """Verify OpenAPI schema includes match endpoints."""
        response = client.get("/openapi.json")
        schema = response.json()
        
        assert "paths" in schema
        assert "/api/v1/matches" in schema["paths"]
        assert "/api/v1/matches/{match_id}" in schema["paths"]


class TestEndpointIntegration:
    """Integration tests for endpoint behavior."""

    def test_list_and_detail_consistency(self, client):
        """Verify match from list can be retrieved via detail endpoint."""
        # Get match list
        list_response = client.get("/api/v1/matches")
        list_data = list_response.json()
        
        if len(list_data["matches"]) > 0:
            # Get first match ID
            first_match_id = list_data["matches"][0]["id"]
            
            # Get that match via detail endpoint
            detail_response = client.get(f"/api/v1/matches/{first_match_id}")
            detail_data = detail_response.json()
            
            # Should succeed
            assert detail_response.status_code == 200
            assert detail_data["match"]["id"] == first_match_id

    def test_all_listed_matches_retrievable(self, client):
        """Verify all matches from list endpoint can be retrieved individually."""
        # Get match list
        list_response = client.get("/api/v1/matches")
        list_data = list_response.json()
        
        # Try to get each match individually
        for match_summary in list_data["matches"]:
            match_id = match_summary["id"]
            detail_response = client.get(f"/api/v1/matches/{match_id}")
            
            # Each should return 200
            assert detail_response.status_code == 200
            detail_data = detail_response.json()
            assert detail_data["match"]["id"] == match_id


class TestMatchPredictionEndpoint:
    """Tests for GET /api/v1/matches/{match_id}/prediction endpoint."""
    
    def test_get_prediction_returns_200(self, client, predictable_match_id):
        """Verify getting prediction for existing match returns 200 OK."""
        if predictable_match_id is None:
            pytest.skip("No matches with sufficient historical data available")
        
        response = client.get(f"/api/v1/matches/{predictable_match_id}/prediction")
        assert response.status_code == 200
    
    def test_get_prediction_response_structure(self, client, predictable_match_id):
        """Verify prediction response has correct structure."""
        if predictable_match_id is None:
            pytest.skip("No matches with sufficient historical data available")
        
        response = client.get(f"/api/v1/matches/{predictable_match_id}/prediction")
        data = response.json()
        
        # Required fields
        assert "match_id" in data
        assert "home_win_probability" in data
        assert "draw_probability" in data
        assert "away_win_probability" in data
        assert "home_xg" in data
        assert "away_xg" in data
        assert "btts_probability" in data
        assert "is_development_data" in data
        
        # Optional fields
        assert "market_analysis" in data
        assert "easy_match" in data
    
    def test_get_prediction_probabilities_valid(self, client, predictable_match_id):
        """Verify prediction probabilities are valid (0-1 range)."""
        if predictable_match_id is None:
            pytest.skip("No matches with sufficient historical data available")
        
        response = client.get(f"/api/v1/matches/{predictable_match_id}/prediction")
        data = response.json()
        
        # Check probabilities are in valid range
        assert 0.0 <= data["home_win_probability"] <= 1.0
        assert 0.0 <= data["draw_probability"] <= 1.0
        assert 0.0 <= data["away_win_probability"] <= 1.0
        assert 0.0 <= data["btts_probability"] <= 1.0
    
    def test_get_prediction_probabilities_sum_near_one(self, client, predictable_match_id):
        """Verify 1X2 probabilities sum approximately to 1.0."""
        if predictable_match_id is None:
            pytest.skip("No matches with sufficient historical data available")
        
        response = client.get(f"/api/v1/matches/{predictable_match_id}/prediction")
        data = response.json()
        
        total = (data["home_win_probability"] + 
                data["draw_probability"] + 
                data["away_win_probability"])
        
        # Should be very close to 1.0 (allow small floating point error)
        assert 0.99 <= total <= 1.01
    
    def test_get_prediction_xg_non_negative(self, client, predictable_match_id):
        """Verify expected goals are non-negative."""
        if predictable_match_id is None:
            pytest.skip("No matches with sufficient historical data available")
        
        response = client.get(f"/api/v1/matches/{predictable_match_id}/prediction")
        data = response.json()
        
        assert data["home_xg"] >= 0.0
        assert data["away_xg"] >= 0.0
    
    def test_get_prediction_market_analysis_structure(self, client, predictable_match_id):
        """Verify market analysis structure when present."""
        if predictable_match_id is None:
            pytest.skip("No matches with sufficient historical data available")
        
        response = client.get(f"/api/v1/matches/{predictable_match_id}/prediction")
        data = response.json()
        
        if data["market_analysis"] is not None:
            assert isinstance(data["market_analysis"], list)
            
            for market in data["market_analysis"]:
                assert "market_type" in market
                assert "outcomes" in market
                assert "has_bookmaker_odds" in market
                assert isinstance(market["outcomes"], list)
                
                # Check outcome structure
                for outcome in market["outcomes"]:
                    assert "label" in outcome
                    assert "model_probability" in outcome
                    assert "fair_odds" in outcome
                    assert outcome["fair_odds"] >= 1.0  # Odds must be >= 1.0
    
    def test_get_prediction_no_fabricated_bookmaker_odds(self, client, predictable_match_id):
        """Verify bookmaker odds are not fabricated."""
        if predictable_match_id is None:
            pytest.skip("No matches with sufficient historical data available")
        
        response = client.get(f"/api/v1/matches/{predictable_match_id}/prediction")
        data = response.json()
        
        if data["market_analysis"] is not None:
            for market in data["market_analysis"]:
                # Development data should not have bookmaker odds
                assert market["has_bookmaker_odds"] is False
                assert market["bookmaker_comparison"] is None
                assert market["bookmaker_overround"] is None
    
    def test_get_prediction_easy_match_structure(self, client, predictable_match_id):
        """Verify easy match structure when present."""
        if predictable_match_id is None:
            pytest.skip("No matches with sufficient historical data available")
        
        response = client.get(f"/api/v1/matches/{predictable_match_id}/prediction")
        data = response.json()
        
        if data["easy_match"] is not None:
            easy = data["easy_match"]
            
            assert "match_id" in easy
            assert "is_easy_match" in easy
            assert "confidence_score" in easy
            assert "threshold" in easy
            assert "signals" in easy
            assert "reasons" in easy
            assert "warnings" in easy
            assert "data_sufficient" in easy
            
            # Check score range
            assert 0.0 <= easy["confidence_score"] <= 100.0
            
            # Check signals structure
            assert isinstance(easy["signals"], list)
            for signal in easy["signals"]:
                assert "name" in signal
                assert "value" in signal
                assert "weight" in signal
                assert "available" in signal
    
    def test_get_prediction_deterministic(self, client, predictable_match_id):
        """Verify predictions are deterministic (same input = same output)."""
        if predictable_match_id is None:
            pytest.skip("No matches with sufficient historical data available")
        
        # Get prediction twice
        response1 = client.get(f"/api/v1/matches/{predictable_match_id}/prediction")
        response2 = client.get(f"/api/v1/matches/{predictable_match_id}/prediction")
        
        data1 = response1.json()
        data2 = response2.json()
        
        # Should produce identical results
        assert data1["home_win_probability"] == data2["home_win_probability"]
        assert data1["draw_probability"] == data2["draw_probability"]
        assert data1["away_win_probability"] == data2["away_win_probability"]
        assert data1["home_xg"] == data2["home_xg"]
        assert data1["away_xg"] == data2["away_xg"]
        assert data1["btts_probability"] == data2["btts_probability"]
    
    def test_get_prediction_404_for_invalid_match(self, client):
        """Verify getting prediction for non-existent match returns 404."""
        invalid_id = "nonexistent-match-id-12345"
        response = client.get(f"/api/v1/matches/{invalid_id}/prediction")
        
        assert response.status_code == 404
    
    def test_get_prediction_development_data_flagged(self, client, predictable_match_id):
        """Verify development data is clearly flagged."""
        if predictable_match_id is None:
            pytest.skip("No matches with sufficient historical data available")
        
        response = client.get(f"/api/v1/matches/{predictable_match_id}/prediction")
        data = response.json()
        
        # Must be flagged as development data
        assert data["is_development_data"] is True
    
    def test_get_prediction_insufficient_data_handling(self, client):
        """Verify insufficient data is handled gracefully with 400."""
        response = client.get("/api/v1/matches")
        matches_data = response.json()
        
        # Try to find a match that returns 400 (insufficient data)
        found_insufficient = False
        for match in matches_data.get("matches", [])[:5]:  # Test first 5 matches
            response = client.get(f"/api/v1/matches/{match['id']}/prediction")
            if response.status_code == 400:
                found_insufficient = True
                data = response.json()
                assert "detail" in data
                assert "Insufficient data" in data["detail"]
                break
        
        # Note: This test may not always find an insufficient data case
        # depending on the development provider's data
        if not found_insufficient:
            pytest.skip("All matches have sufficient data for prediction")

