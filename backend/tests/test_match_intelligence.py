"""Tests for Match Intelligence API (Phase 3).

Verifies that match statistics, first-half data, and team logos are correctly exposed through the API.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.dependencies import get_data_provider
from app.providers.development import DevelopmentProvider


@pytest.fixture
def client():
    """Create test client with DevelopmentProvider."""
    # Override dependency
    app.dependency_overrides[get_data_provider] = lambda: DevelopmentProvider()
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


class TestMatchListTeamInfo:
    """Test GET /matches returns team information."""
    
    def test_matches_include_team_info(self, client):
        """Verify matches include home_team and away_team."""
        response = client.get("/api/v1/matches")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] > 0
        
        match = data["matches"][0]
        assert "home_team" in match
        assert "away_team" in match
        assert match["home_team"] is not None
        assert match["away_team"] is not None
    
    def test_team_info_includes_logo_url(self, client):
        """Verify team info includes logo_url field."""
        response = client.get("/api/v1/matches")
        assert response.status_code == 200
        data = response.json()
        
        match = data["matches"][0]
        assert "logo_url" in match["home_team"]
        assert "logo_url" in match["away_team"]
    
    def test_team_logo_can_be_null(self, client):
        """Verify system handles missing team logos gracefully."""
        response = client.get("/api/v1/matches")
        assert response.status_code == 200
        data = response.json()
        
        # dev_team_gamma has no logo - find a match with this team
        gamma_match = None
        for match in data["matches"]:
            if match["home_team"]["id"] == "dev_team_gamma" or match["away_team"]["id"] == "dev_team_gamma":
                gamma_match = match
                break
        
        assert gamma_match is not None, "No match found with dev_team_gamma"
        
        # Check that gamma's logo_url is None
        if gamma_match["home_team"]["id"] == "dev_team_gamma":
            assert gamma_match["home_team"]["logo_url"] is None
        else:
            assert gamma_match["away_team"]["logo_url"] is None
    
    def test_team_logos_with_dev_urls(self, client):
        """Verify teams with logos have dev URLs."""
        response = client.get("/api/v1/matches")
        assert response.status_code == 200
        data = response.json()
        
        # Find alpha team match
        alpha_match = None
        for match in data["matches"]:
            if match["home_team"]["id"] == "dev_team_alpha":
                alpha_match = match
                break
        
        assert alpha_match is not None, "No match found with dev_team_alpha"
        assert alpha_match["home_team"]["logo_url"] is not None
        assert "dev.example.com" in alpha_match["home_team"]["logo_url"]


class TestMatchDetailStatistics:
    """Test GET /matches/{match_id} returns match statistics."""
    
    def test_finished_match_has_statistics(self, client):
        """Verify finished match includes full-match statistics."""
        response = client.get("/api/v1/matches/dev_match_001")
        assert response.status_code == 200
        data = response.json()
        
        match = data["match"]
        assert match["status"] == "finished"
        assert match["home_statistics"] is not None
        assert match["away_statistics"] is not None
    
    def test_scheduled_match_has_no_statistics(self, client):
        """Verify scheduled match does not have statistics."""
        response = client.get("/api/v1/matches/dev_match_002")
        assert response.status_code == 200
        data = response.json()
        
        match = data["match"]
        assert match["status"] == "scheduled"
        assert match["home_statistics"] is None
        assert match["away_statistics"] is None
        assert match["home_statistics_ht"] is None
        assert match["away_statistics_ht"] is None
    
    def test_statistics_structure(self, client):
        """Verify statistics contain expected fields."""
        response = client.get("/api/v1/matches/dev_match_001")
        assert response.status_code == 200
        data = response.json()
        
        stats = data["match"]["home_statistics"]
        assert "goals_scored" in stats
        assert "xg" in stats
        assert "shots_total" in stats
        assert "shots_on_target" in stats
        assert "possession_percentage" in stats
        assert "corners" in stats
        assert "yellow_cards" in stats
        assert "fouls_committed" in stats
        assert "tackles" in stats
    
    def test_statistics_internal_consistency(self, client):
        """Verify statistics are internally consistent."""
        response = client.get("/api/v1/matches/dev_match_001")
        assert response.status_code == 200
        data = response.json()
        
        stats = data["match"]["home_statistics"]
        
        # shots_on_target should be <= shots_total
        if stats["shots_on_target"] is not None and stats["shots_total"] is not None:
            assert stats["shots_on_target"] <= stats["shots_total"]
        
        # Possession should be between 0-100
        if stats["possession_percentage"] is not None:
            assert 0 <= stats["possession_percentage"] <= 100
        
        # Pass accuracy calculation check
        if stats["pass_accuracy"] is not None:
            assert 0 <= stats["pass_accuracy"] <= 100
    
    def test_all_finished_matches_have_statistics(self, client):
        """Verify all finished matches have statistics."""
        for match_id in ["dev_match_001", "dev_match_003", "dev_match_004"]:
            response = client.get(f"/api/v1/matches/{match_id}")
            assert response.status_code == 200
            data = response.json()
            
            match = data["match"]
            assert match["status"] == "finished"
            assert match["home_statistics"] is not None, f"{match_id} missing home stats"
            assert match["away_statistics"] is not None, f"{match_id} missing away stats"


class TestFirstHalfStatistics:
    """Test first-half statistics functionality."""
    
    def test_finished_match_has_firsthalf_statistics(self, client):
        """Verify finished match includes first-half statistics."""
        response = client.get("/api/v1/matches/dev_match_001")
        assert response.status_code == 200
        data = response.json()
        
        match = data["match"]
        assert match["home_statistics_ht"] is not None
        assert match["away_statistics_ht"] is not None
    
    def test_firsthalf_statistics_structure(self, client):
        """Verify first-half statistics have same structure as full-match."""
        response = client.get("/api/v1/matches/dev_match_001")
        assert response.status_code == 200
        data = response.json()
        
        ht_stats = data["match"]["home_statistics_ht"]
        full_stats = data["match"]["home_statistics"]
        
        # Should have same keys
        assert set(ht_stats.keys()) == set(full_stats.keys())
    
    def test_firsthalf_not_computed_from_fullmatch(self, client):
        """Verify first-half stats are NOT simply full-match / 2."""
        response = client.get("/api/v1/matches/dev_match_001")
        assert response.status_code == 200
        data = response.json()
        
        match = data["match"]
        ht_shots = match["home_statistics_ht"]["shots_total"]
        full_shots = match["home_statistics"]["shots_total"]
        
        # HT shots is 8, full shots is 15
        # If it was divided, HT would be 7.5, but we have 8 (distinct value)
        # The key test: 8 != 15/2 (7.5)
        assert ht_shots != full_shots / 2, "First-half shots appear to be computed from full-match / 2"
        
        # Verify HT <= full
        assert ht_shots <= full_shots
    
    def test_firsthalf_goals_match_halftime_score(self, client):
        """Verify first-half goals_scored matches the half-time score."""
        response = client.get("/api/v1/matches/dev_match_001")
        assert response.status_code == 200
        data = response.json()
        
        match = data["match"]
        
        assert match["home_statistics_ht"]["goals_scored"] == match["home_score_ht"]
        assert match["away_statistics_ht"]["goals_scored"] == match["away_score_ht"]
    
    def test_firsthalf_values_plausible_subset(self, client):
        """Verify first-half values are plausible subsets of full-match."""
        response = client.get("/api/v1/matches/dev_match_003")
        assert response.status_code == 200
        data = response.json()
        
        match = data["match"]
        home_ht = match["home_statistics_ht"]
        home_full = match["home_statistics"]
        
        # All HT statistics should be <= full-match
        assert home_ht["shots_total"] <= home_full["shots_total"]
        assert home_ht["shots_on_target"] <= home_full["shots_on_target"]
        assert home_ht["corners"] <= home_full["corners"]
        assert home_ht["yellow_cards"] <= home_full["yellow_cards"]
        assert home_ht["passes_completed"] <= home_full["passes_completed"]
    
    def test_all_finished_matches_have_firsthalf_stats(self, client):
        """Verify all finished matches have first-half statistics."""
        for match_id in ["dev_match_001", "dev_match_003", "dev_match_004"]:
            response = client.get(f"/api/v1/matches/{match_id}")
            assert response.status_code == 200
            data = response.json()
            
            match = data["match"]
            assert match["home_statistics_ht"] is not None, f"{match_id} missing home HT stats"
            assert match["away_statistics_ht"] is not None, f"{match_id} missing away HT stats"


class TestBackwardCompatibility:
    """Test that existing functionality still works."""
    
    def test_match_list_still_works(self, client):
        """Verify match list endpoint still returns basic fields."""
        response = client.get("/api/v1/matches")
        assert response.status_code == 200
        data = response.json()
        
        assert "matches" in data
        assert "count" in data
        assert "is_development_data" in data
    
    def test_match_detail_still_works(self, client):
        """Verify match detail endpoint still returns basic fields."""
        response = client.get("/api/v1/matches/dev_match_001")
        assert response.status_code == 200
        data = response.json()
        
        match = data["match"]
        assert "id" in match
        assert "home_team_id" in match
        assert "away_team_id" in match
        assert "home_score" in match
        assert "away_score" in match
        assert "status" in match
    
    def test_prediction_endpoint_still_works(self, client):
        """Verify prediction endpoint was not affected."""
        response = client.get("/api/v1/matches/dev_match_002/prediction")
        assert response.status_code == 200
        data = response.json()
        
        assert "home_win_probability" in data
        assert "away_win_probability" in data
        assert "draw_probability" in data
    
    def test_new_fields_optional_in_list(self, client):
        """Verify new fields (home_statistics_ht, away_statistics_ht) exist but are optional."""
        response = client.get("/api/v1/matches")
        assert response.status_code == 200
        data = response.json()
        
        # Check scheduled match has None for new fields
        scheduled_match = None
        for match in data["matches"]:
            if match["status"] == "scheduled":
                scheduled_match = match
                break
        
        if scheduled_match:
            # New fields should exist but be None
            assert "home_statistics_ht" in scheduled_match
            assert "away_statistics_ht" in scheduled_match
            # For scheduled matches, these should be None
            # (list endpoint doesn't populate statistics anyway)


class TestMatchStatisticsConsistency:
    """Test that match statistics are internally consistent."""
    
    def test_shots_consistency(self, client):
        """Verify shots_on_target <= shots_total for all matches."""
        for match_id in ["dev_match_001", "dev_match_003", "dev_match_004"]:
            response = client.get(f"/api/v1/matches/{match_id}")
            assert response.status_code == 200
            data = response.json()
            
            match = data["match"]
            for team in ["home", "away"]:
                stats = match[f"{team}_statistics"]
                if stats and stats["shots_on_target"] and stats["shots_total"]:
                    assert stats["shots_on_target"] <= stats["shots_total"], \
                        f"{match_id} {team} shots_on_target > shots_total"
    
    def test_possession_sums_approximately_100(self, client):
        """Verify home and away possession sum to approximately 100%."""
        response = client.get("/api/v1/matches/dev_match_001")
        assert response.status_code == 200
        data = response.json()
        
        match = data["match"]
        home_poss = match["home_statistics"]["possession_percentage"]
        away_poss = match["away_statistics"]["possession_percentage"]
        
        # Should sum to approximately 100 (allowing small rounding differences)
        assert abs((home_poss + away_poss) - 100.0) < 1.0
    
    def test_goals_match_score(self, client):
        """Verify goals_scored in statistics match the match score."""
        response = client.get("/api/v1/matches/dev_match_001")
        assert response.status_code == 200
        data = response.json()
        
        match = data["match"]
        assert match["home_statistics"]["goals_scored"] == match["home_score"]
        assert match["away_statistics"]["goals_scored"] == match["away_score"]
    
    def test_goals_consistency_reciprocal(self, client):
        """Verify goals_scored for one team = goals_conceded for the other."""
        response = client.get("/api/v1/matches/dev_match_003")
        assert response.status_code == 200
        data = response.json()
        
        match = data["match"]
        home_scored = match["home_statistics"]["goals_scored"]
        home_conceded = match["home_statistics"]["goals_conceded"]
        away_scored = match["away_statistics"]["goals_scored"]
        away_conceded = match["away_statistics"]["goals_conceded"]
        
        assert home_scored == away_conceded
        assert away_scored == home_conceded


class TestTeamIdentityStability:
    """Test that team identity is stable across endpoints."""
    
    def test_team_id_consistent_across_endpoints(self, client):
        """Verify team IDs are consistent between list and detail endpoints."""
        # Get match from list
        response_list = client.get("/api/v1/matches")
        assert response_list.status_code == 200
        list_data = response_list.json()
        
        match_from_list = list_data["matches"][0]
        match_id = match_from_list["id"]
        
        # Get same match from detail
        response_detail = client.get(f"/api/v1/matches/{match_id}")
        assert response_detail.status_code == 200
        detail_data = response_detail.json()
        
        match_from_detail = detail_data["match"]
        
        # Team IDs should be identical
        assert match_from_list["home_team"]["id"] == match_from_detail["home_team"]["id"]
        assert match_from_list["away_team"]["id"] == match_from_detail["away_team"]["id"]
    
    def test_team_logo_url_consistent(self, client):
        """Verify logo URLs are consistent across different matches."""
        response = client.get("/api/v1/matches")
        assert response.status_code == 200
        data = response.json()
        
        # Collect all instances of dev_team_alpha
        alpha_logos = []
        for match in data["matches"]:
            if match["home_team"]["id"] == "dev_team_alpha":
                alpha_logos.append(match["home_team"]["logo_url"])
            if match["away_team"]["id"] == "dev_team_alpha":
                alpha_logos.append(match["away_team"]["logo_url"])
        
        # All logo URLs for the same team should be identical
        assert len(set(alpha_logos)) == 1, "Team Alpha has inconsistent logo URLs"
