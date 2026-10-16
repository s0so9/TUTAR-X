"""Tests for multi-provider football data abstraction foundation layer.

Tests for FEAT-001: normalized models, exceptions, and cache.
Tests for FEAT-002: RyzellxFootballProvider implementation.
"""

import pytest
from datetime import datetime, timedelta, date, timezone
import threading
import time
import json
import httpx
import respx

from app.providers.exceptions import (
    ProviderError,
    ProviderTimeoutError,
    ProviderHTTPError,
    ProviderInvalidDataError,
    ProviderNotFoundError,
)
from app.providers.cache import ProviderCache, LIVE_DATA_TTL, METADATA_TTL
from app.providers.models import (
    ProviderCompetition,
    ProviderTeam,
    ProviderPlayer,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderLineup,
    ProviderMatchStats,
    ProviderShot,
    ProviderStanding,
    ProviderLiveMatch,
)
from app.providers.ryzellx import RyzellxFootballProvider
from app.domain.enums import MatchStatus, MatchEventType


class TestProviderExceptions:
    """Tests for provider exception classes."""
    
    def test_provider_error_basic(self):
        """Test basic ProviderError creation and attributes."""
        error = ProviderError(
            provider_name="test_provider",
            operation="get_match",
            message="Something went wrong"
        )
        
        assert error.provider_name == "test_provider"
        assert error.operation == "get_match"
        assert error.message == "Something went wrong"
        assert error.original_error is None
        assert "[test_provider] get_match: Something went wrong" in str(error)
    
    def test_provider_error_with_original(self):
        """Test ProviderError wrapping an original exception."""
        original = ValueError("Invalid value")
        error = ProviderError(
            provider_name="test_provider",
            operation="parse_response",
            message="Failed to parse",
            original_error=original
        )
        
        assert error.original_error is original
        assert error.message == "Failed to parse"
    
    def test_provider_timeout_error(self):
        """Test ProviderTimeoutError."""
        error = ProviderTimeoutError(
            provider_name="slow_provider",
            operation="get_standings",
            message="Request timed out after 30s"
        )
        
        assert isinstance(error, ProviderError)
        assert error.provider_name == "slow_provider"
        assert "timed out" in error.message
    
    def test_provider_http_error(self):
        """Test ProviderHTTPError with status code."""
        error = ProviderHTTPError(
            provider_name="api_provider",
            operation="get_team",
            message="Not found",
            status_code=404
        )
        
        assert isinstance(error, ProviderError)
        assert error.status_code == 404
        assert error.message == "Not found"
        assert "status_code=404" in repr(error)
    
    def test_provider_invalid_data_error(self):
        """Test ProviderInvalidDataError."""
        error = ProviderInvalidDataError(
            provider_name="data_provider",
            operation="parse_match",
            message="Missing required field: home_team_id"
        )
        
        assert isinstance(error, ProviderError)
        assert "Missing required field" in error.message
    
    def test_provider_not_found_error(self):
        """Test ProviderNotFoundError."""
        error = ProviderNotFoundError(
            provider_name="api_provider",
            operation="get_player",
            message="Player with ID 'player_999' not found"
        )
        
        assert isinstance(error, ProviderError)
        assert "not found" in error.message
    
    def test_exception_repr(self):
        """Test exception repr() format."""
        error = ProviderError(
            provider_name="test",
            operation="test_op",
            message="test message"
        )
        
        repr_str = repr(error)
        assert "ProviderError" in repr_str
        assert "provider_name='test'" in repr_str
        assert "operation='test_op'" in repr_str
        assert "message='test message'" in repr_str


class TestProviderModels:
    """Tests for normalized provider models."""
    
    def test_provider_competition_minimal(self):
        """Test ProviderCompetition with minimal required fields."""
        comp = ProviderCompetition(
            provider="test_provider",
            source_id="comp_123",
            fetched_at=datetime.utcnow(),
            name="Test League"
        )
        
        assert comp.provider == "test_provider"
        assert comp.source_id == "comp_123"
        assert comp.name == "Test League"
        assert comp.is_live is False
        assert comp.country is None
        assert comp.level is None
    
    def test_provider_competition_full(self):
        """Test ProviderCompetition with all fields."""
        now = datetime.utcnow()
        comp = ProviderCompetition(
            provider="ryzellx",
            source_id="39",
            fetched_at=now,
            source_updated_at=now - timedelta(hours=1),
            is_live=False,
            data_freshness_seconds=3600,
            name="Premier League",
            country="ENG",
            level=1,
            type="league",
            season="2023/2024",
            logo_url="https://example.com/logo.png"
        )
        
        assert comp.provider == "ryzellx"
        assert comp.name == "Premier League"
        assert comp.country == "ENG"
        assert comp.level == 1
        assert comp.data_freshness_seconds == 3600
    
    def test_provider_team_minimal(self):
        """Test ProviderTeam with minimal required fields."""
        team = ProviderTeam(
            provider="test_provider",
            source_id="team_123",
            fetched_at=datetime.utcnow(),
            name="Test FC"
        )
        
        assert team.name == "Test FC"
        assert team.short_name is None
        assert team.code is None
    
    def test_provider_player_optional_fields(self):
        """Test ProviderPlayer uses Optional for unavailable data."""
        player = ProviderPlayer(
            provider="test_provider",
            source_id="player_123",
            fetched_at=datetime.utcnow(),
            name="John Doe"
        )
        
        # All these should be None (not invented values)
        assert player.date_of_birth is None
        assert player.nationality is None
        assert player.position is None
        assert player.shirt_number is None
        assert player.height_cm is None
        assert player.weight_kg is None
    
    def test_provider_match_required_fields(self):
        """Test ProviderMatch with required fields."""
        match = ProviderMatch(
            provider="test_provider",
            source_id="match_123",
            fetched_at=datetime.utcnow(),
            home_team_id="team_1",
            home_team_name="Home FC",
            away_team_id="team_2",
            away_team_name="Away FC",
            scheduled_at=datetime.utcnow() + timedelta(days=1),
            status=MatchStatus.SCHEDULED
        )
        
        assert match.home_team_name == "Home FC"
        assert match.away_team_name == "Away FC"
        assert match.status == MatchStatus.SCHEDULED
        assert match.home_score is None  # Not yet played
        assert match.minute is None
    
    def test_provider_match_live(self):
        """Test ProviderMatch for live match."""
        now = datetime.utcnow()
        match = ProviderMatch(
            provider="fotmob",
            source_id="match_live",
            fetched_at=now,
            is_live=True,
            data_freshness_seconds=5,
            home_team_id="team_1",
            home_team_name="Home FC",
            away_team_id="team_2",
            away_team_name="Away FC",
            scheduled_at=now - timedelta(minutes=45),
            status=MatchStatus.LIVE,
            minute=45,
            home_score=2,
            away_score=1
        )
        
        assert match.is_live is True
        assert match.status == MatchStatus.LIVE
        assert match.minute == 45
        assert match.home_score == 2
        assert match.away_score == 1
    
    def test_provider_match_event(self):
        """Test ProviderMatchEvent."""
        event = ProviderMatchEvent(
            provider="test_provider",
            source_id="event_123",
            fetched_at=datetime.utcnow(),
            match_id="match_123",
            type=MatchEventType.GOAL,
            minute=23,
            team_id="team_1",
            player_id="player_1",
            player_name="John Doe"
        )
        
        assert event.type == MatchEventType.GOAL
        assert event.minute == 23
        assert event.added_time is None
    
    def test_provider_lineup(self):
        """Test ProviderLineup."""
        lineup = ProviderLineup(
            provider="test_provider",
            source_id="lineup_123",
            fetched_at=datetime.utcnow(),
            match_id="match_123",
            team_id="team_1",
            formation="4-3-3",
            starting_xi=["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10", "p11"],
            substitutes=["p12", "p13", "p14"]
        )
        
        assert lineup.formation == "4-3-3"
        assert len(lineup.starting_xi) == 11
        assert len(lineup.substitutes) == 3
    
    def test_provider_match_stats_all_optional(self):
        """Test ProviderMatchStats with all fields optional except identifiers."""
        stats = ProviderMatchStats(
            provider="test_provider",
            source_id="stats_123",
            fetched_at=datetime.utcnow(),
            match_id="match_123",
            team_id="team_1"
        )
        
        # All stats should be None if not provided
        assert stats.xg is None
        assert stats.shots_total is None
        assert stats.possession_percentage is None
        assert stats.corners is None
    
    def test_provider_match_stats_with_xg(self):
        """Test ProviderMatchStats with xG values."""
        stats = ProviderMatchStats(
            provider="ryzellx",
            source_id="stats_123",
            fetched_at=datetime.utcnow(),
            match_id="match_123",
            team_id="team_1",
            xg=2.35,
            xg_against=1.12,
            shots_total=15,
            shots_on_target=7
        )
        
        assert stats.xg == 2.35
        assert stats.xg_against == 1.12
        assert stats.shots_total == 15
    
    def test_provider_shot(self):
        """Test ProviderShot."""
        shot = ProviderShot(
            provider="test_provider",
            source_id="shot_123",
            fetched_at=datetime.utcnow(),
            match_id="match_123",
            team_id="team_1",
            player_id="player_1",
            minute=34,
            xg=0.45,
            result="goal",
            coordinates={"x": 88.5, "y": 52.3}
        )
        
        assert shot.xg == 0.45
        assert shot.result == "goal"
        assert shot.coordinates["x"] == 88.5
    
    def test_provider_standing(self):
        """Test ProviderStanding."""
        standing = ProviderStanding(
            provider="test_provider",
            source_id="standing_123",
            fetched_at=datetime.utcnow(),
            team_id="team_1",
            team_name="Test FC",
            position=3,
            played=10,
            won=6,
            drawn=2,
            lost=2,
            goals_for=18,
            goals_against=12,
            goal_difference=6,
            points=20
        )
        
        assert standing.position == 3
        assert standing.points == 20
        assert standing.goal_difference == 6
    
    def test_provider_live_match(self):
        """Test ProviderLiveMatch."""
        now = datetime.utcnow()
        live_match = ProviderLiveMatch(
            provider="fotmob",
            source_id="live_123",
            fetched_at=now,
            is_live=True,
            data_freshness_seconds=3,
            match_id="match_123",
            status=MatchStatus.LIVE,
            minute=67,
            added_time=None,
            home_score=2,
            away_score=1,
            last_updated=now
        )
        
        assert live_match.is_live is True
        assert live_match.status == MatchStatus.LIVE
        assert live_match.minute == 67
        assert live_match.home_score == 2


class TestProviderCache:
    """Tests for ProviderCache."""
    
    def test_cache_get_set(self):
        """Test basic cache get/set operations."""
        cache = ProviderCache()
        
        cache.set("key1", "value1", ttl_seconds=60)
        
        assert cache.get("key1") == "value1"
        assert cache.get("nonexistent") is None
    
    def test_cache_ttl_expiry(self):
        """Test that cache entries expire after TTL."""
        cache = ProviderCache()
        
        # Set with very short TTL
        cache.set("short_lived", "data", ttl_seconds=1)
        
        # Should be available immediately
        assert cache.get("short_lived") == "data"
        
        # Wait for expiry
        time.sleep(1.1)
        
        # Should be expired
        assert cache.get("short_lived") is None
    
    def test_cache_delete(self):
        """Test cache delete operation."""
        cache = ProviderCache()
        
        cache.set("key1", "value1", ttl_seconds=60)
        assert cache.get("key1") == "value1"
        
        cache.delete("key1")
        assert cache.get("key1") is None
    
    def test_cache_clear(self):
        """Test cache clear operation."""
        cache = ProviderCache()
        
        cache.set("key1", "value1", ttl_seconds=60)
        cache.set("key2", "value2", ttl_seconds=60)
        
        assert cache.size() == 2
        
        cache.clear()
        
        assert cache.size() == 0
        assert cache.get("key1") is None
        assert cache.get("key2") is None
    
    def test_cache_cleanup_expired(self):
        """Test cleanup of expired entries."""
        cache = ProviderCache()
        
        # Add some entries
        cache.set("active", "data", ttl_seconds=60)
        cache.set("expired", "old_data", ttl_seconds=1)
        
        # Wait for one to expire
        time.sleep(1.1)
        
        # Cleanup should remove expired entry
        removed = cache.cleanup_expired()
        assert removed == 1
        assert cache.size() == 1
        assert cache.get("active") == "data"
    
    def test_cache_thread_safety(self):
        """Test that cache is thread-safe."""
        cache = ProviderCache()
        results = []
        
        def writer(key_prefix, count):
            for i in range(count):
                cache.set(f"{key_prefix}_{i}", f"value_{i}", ttl_seconds=60)
        
        def reader(key_prefix, count):
            found = 0
            for i in range(count):
                if cache.get(f"{key_prefix}_{i}") is not None:
                    found += 1
            results.append(found)
        
        # Create multiple threads
        threads = [
            threading.Thread(target=writer, args=("thread1", 50)),
            threading.Thread(target=writer, args=("thread2", 50)),
            threading.Thread(target=reader, args=("thread1", 50)),
            threading.Thread(target=reader, args=("thread2", 50)),
        ]
        
        # Start all threads
        for t in threads:
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join()
        
        # No assertions about specific counts due to race conditions,
        # but the test should complete without errors
        assert len(results) == 2
    
    def test_cache_ttl_constants(self):
        """Test that TTL constants are defined."""
        assert LIVE_DATA_TTL == 30
        assert METADATA_TTL == 3600
    
    def test_cache_complex_objects(self):
        """Test caching complex objects like Pydantic models."""
        cache = ProviderCache()
        
        match = ProviderMatch(
            provider="test",
            source_id="match_123",
            fetched_at=datetime.utcnow(),
            home_team_id="team_1",
            home_team_name="Home FC",
            away_team_id="team_2",
            away_team_name="Away FC",
            scheduled_at=datetime.utcnow(),
            status=MatchStatus.SCHEDULED
        )
        
        cache.set("match:123", match, ttl_seconds=60)
        
        cached_match = cache.get("match:123")
        assert cached_match is not None
        assert cached_match.source_id == "match_123"
        assert cached_match.home_team_name == "Home FC"


class TestRyzellxProvider:
    """Tests for RyzellxFootballProvider."""
    
    @pytest.fixture
    def provider(self):
        """Create RyzellxFootballProvider instance for testing."""
        cache = ProviderCache()
        provider = RyzellxFootballProvider(
            base_url="https://test-api.example.com",
            timeout_seconds=5.0,
            retry_count=2,
            cache=cache
        )
        yield provider
        # Cleanup
        import asyncio
        asyncio.run(provider.close())
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_ryzellx_get_matches_by_date(self, provider):
        """Test get_matches_by_date returns normalized matches."""
        test_date = date(2024, 1, 15)
        
        # Mock API response
        mock_response = [
            {
                "id": "match_123",
                "home_team": "Arsenal",
                "home_id": "team_1",
                "away_team": "Liverpool",
                "away_id": "team_2",
                "date": "2024-01-15T15:00:00Z",
                "status": "scheduled",
                "league": "Premier League",
                "competition_id": "39"
            },
            {
                "id": "match_124",
                "home_team": "Chelsea",
                "home_id": "team_3",
                "away_team": "Manchester City",
                "away_id": "team_4",
                "date": "2024-01-15T17:30:00Z",
                "status": "scheduled",
                "league": "Premier League",
                "competition_id": "39"
            }
        ]
        
        respx.get(f"{provider.base_url}/api/matches/date/{test_date.isoformat()}").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        
        # Call method
        matches = await provider.get_matches_by_date(test_date)
        
        # Assertions
        assert len(matches) == 2
        assert all(isinstance(m, ProviderMatch) for m in matches)
        assert matches[0].provider == "ryzellx"
        assert matches[0].source_id == "match_123"
        assert matches[0].home_team_name == "Arsenal"
        assert matches[0].away_team_name == "Liverpool"
        assert matches[0].status == MatchStatus.SCHEDULED
        assert matches[0].home_score is None  # Not yet played
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_ryzellx_get_matches_by_range(self, provider):
        """Test get_matches_by_range returns normalized matches."""
        start_date = date(2024, 1, 15)
        end_date = date(2024, 1, 20)
        
        # Mock API response
        mock_response = [
            {
                "id": "match_125",
                "home_team": "Team A",
                "home_id": "team_a",
                "away_team": "Team B",
                "away_id": "team_b",
                "date": "2024-01-17T20:00:00Z",
                "status": "finished",
                "home_score": 2,
                "away_score": 1
            }
        ]
        
        respx.get(f"{provider.base_url}/api/matches/range").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        
        # Call method
        matches = await provider.get_matches_by_range(start_date, end_date)
        
        # Assertions
        assert len(matches) == 1
        assert matches[0].source_id == "match_125"
        assert matches[0].status == MatchStatus.FINISHED
        assert matches[0].home_score == 2
        assert matches[0].away_score == 1
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_ryzellx_get_match(self, provider):
        """Test get_match returns detailed match info."""
        match_id = "match_456"
        
        # Mock API response
        mock_response = {
            "id": "match_456",
            "home_team": "Real Madrid",
            "home_id": "team_10",
            "away_team": "Barcelona",
            "away_id": "team_11",
            "date": "2024-01-20T21:00:00Z",
            "status": "live",
            "minute": 67,
            "home_score": 2,
            "away_score": 2,
            "venue": "Santiago Bernabéu",
            "league": "La Liga",
            "competition_id": "140"
        }
        
        respx.get(f"{provider.base_url}/api/match/{match_id}").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        
        # Call method
        match = await provider.get_match(match_id)
        
        # Assertions
        assert match is not None
        assert match.source_id == "match_456"
        assert match.home_team_name == "Real Madrid"
        assert match.away_team_name == "Barcelona"
        assert match.status == MatchStatus.LIVE
        assert match.minute == 67
        assert match.home_score == 2
        assert match.away_score == 2
        assert match.is_live is True
        assert match.venue_name == "Santiago Bernabéu"
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_ryzellx_get_match_not_found(self, provider):
        """Test get_match returns None for 404."""
        match_id = "nonexistent"
        
        respx.get(f"{provider.base_url}/api/match/{match_id}").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        
        # Call method
        match = await provider.get_match(match_id)
        
        # Assertions
        assert match is None
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_ryzellx_get_live_matches(self, provider):
        """Test get_live_matches returns live match data."""
        # Mock API response
        mock_response = [
            {
                "id": "live_1",
                "home_team": "Team X",
                "home_id": "team_x",
                "away_team": "Team Y",
                "away_id": "team_y",
                "status": "live",
                "minute": 34,
                "home_score": 1,
                "away_score": 0
            },
            {
                "id": "live_2",
                "home_team": "Team Z",
                "home_id": "team_z",
                "away_team": "Team W",
                "away_id": "team_w",
                "status": "2h",
                "minute": 78,
                "home_score": 2,
                "away_score": 2
            }
        ]
        
        respx.get(f"{provider.base_url}/api/matches/live").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        
        # Call method
        live_matches = await provider.get_live_matches()
        
        # Assertions
        assert len(live_matches) == 2
        assert all(isinstance(m, ProviderLiveMatch) for m in live_matches)
        assert live_matches[0].match_id == "live_1"
        assert live_matches[0].status == MatchStatus.LIVE
        assert live_matches[0].minute == 34
        assert live_matches[0].home_score == 1
        assert live_matches[0].away_score == 0
        assert live_matches[0].is_live is True
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_ryzellx_get_team(self, provider):
        """Test get_team returns team info."""
        team_id = "team_789"
        
        # Mock API response
        mock_response = {
            "id": "team_789",
            "name": "Manchester United",
            "code": "MUN",
            "country": "ENG",
            "founded": 1878,
            "stadium": "Old Trafford",
            "logo": "https://example.com/mun.png"
        }
        
        respx.get(f"{provider.base_url}/api/team/{team_id}").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        
        # Call method
        team = await provider.get_team(team_id)
        
        # Assertions
        assert team is not None
        assert team.source_id == "team_789"
        assert team.name == "Manchester United"
        assert team.code == "MUN"
        assert team.country == "ENG"
        assert team.founded == 1878
        assert team.venue_name == "Old Trafford"
        assert team.logo_url == "https://example.com/mun.png"
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_ryzellx_get_player(self, provider):
        """Test get_player returns player info."""
        player_id = "player_999"
        
        # Mock API response
        mock_response = {
            "id": "player_999",
            "name": "Cristiano Ronaldo",
            "position": "Forward",
            "number": 7,
            "nationality": "PRT",
            "dob": "1985-02-05",
            "height": 187,
            "weight": 83,
            "team": "Al Nassr",
            "team_id": "team_saudi"
        }
        
        respx.get(f"{provider.base_url}/api/player/{player_id}").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        
        # Call method
        player = await provider.get_player(player_id)
        
        # Assertions
        assert player is not None
        assert player.source_id == "player_999"
        assert player.name == "Cristiano Ronaldo"
        assert player.position == "Forward"
        assert player.shirt_number == 7
        assert player.nationality == "PRT"
        assert player.date_of_birth == "1985-02-05"
        assert player.height_cm == 187
        assert player.weight_kg == 83
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_ryzellx_get_league(self, provider):
        """Test get_league returns competition info."""
        league_id = "39"
        
        # Mock API response
        mock_response = {
            "id": "39",
            "name": "Premier League",
            "country": "England",
            "type": "league",
            "current_season": "2023/2024",
            "logo": "https://example.com/pl.png"
        }
        
        respx.get(f"{provider.base_url}/api/league/{league_id}").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        
        # Call method
        league = await provider.get_league(league_id)
        
        # Assertions
        assert league is not None
        assert league.source_id == "39"
        assert league.name == "Premier League"
        assert league.country == "England"
        assert league.type == "league"
        assert league.season == "2023/2024"
        assert league.logo_url == "https://example.com/pl.png"
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_ryzellx_get_standings(self, provider):
        """Test get_standings returns league table."""
        league_id = "39"
        
        # Mock API response
        mock_response = [
            {
                "position": 1,
                "team_id": "team_1",
                "team": "Manchester City",
                "played": 20,
                "won": 15,
                "drawn": 3,
                "lost": 2,
                "goals_for": 45,
                "goals_against": 20,
                "goal_difference": 25,
                "points": 48,
                "form": "WWDWW"
            },
            {
                "position": 2,
                "team_id": "team_2",
                "team": "Arsenal",
                "played": 20,
                "won": 14,
                "drawn": 4,
                "lost": 2,
                "goals_for": 42,
                "goals_against": 18,
                "goal_difference": 24,
                "points": 46,
                "form": "WDWWL"
            }
        ]
        
        respx.get(f"{provider.base_url}/api/league/{league_id}/table").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        
        # Call method
        standings = await provider.get_standings(league_id)
        
        # Assertions
        assert len(standings) == 2
        assert all(isinstance(s, ProviderStanding) for s in standings)
        assert standings[0].position == 1
        assert standings[0].team_name == "Manchester City"
        assert standings[0].points == 48
        assert standings[0].form == "WWDWW"
        assert standings[1].position == 2
        assert standings[1].team_name == "Arsenal"
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_ryzellx_timeout_error(self, provider):
        """Test that timeout raises ProviderTimeoutError."""
        test_date = date(2024, 1, 15)
        
        respx.get(f"{provider.base_url}/api/matches/date/{test_date.isoformat()}").mock(
            side_effect=httpx.TimeoutException("Timeout")
        )
        
        with pytest.raises(ProviderTimeoutError) as exc_info:
            await provider.get_matches_by_date(test_date)
        
        assert exc_info.value.provider_name == "ryzellx"
        assert "timed out" in exc_info.value.message.lower()
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_ryzellx_http_4xx_error(self, provider):
        """Test that 4xx errors raise ProviderHTTPError."""
        match_id = "bad_id"
        
        respx.get(f"{provider.base_url}/api/match/{match_id}").mock(
            return_value=httpx.Response(400, json={"error": "Bad request"})
        )
        
        with pytest.raises(ProviderHTTPError) as exc_info:
            await provider.get_match(match_id)
        
        assert exc_info.value.provider_name == "ryzellx"
        assert exc_info.value.status_code == 400
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_ryzellx_http_5xx_retry(self, provider):
        """Test that 5xx errors are retried."""
        team_id = "team_123"
        
        # First two requests fail with 500, third succeeds
        mock_response = {
            "id": "team_123",
            "name": "Test Team"
        }
        
        route = respx.get(f"{provider.base_url}/api/team/{team_id}")
        route.side_effect = [
            httpx.Response(500, json={"error": "Server error"}),
            httpx.Response(500, json={"error": "Server error"}),
            httpx.Response(200, json=mock_response)
        ]
        
        # Call method - should succeed after retries
        team = await provider.get_team(team_id)
        
        # Assertions
        assert team is not None
        assert team.name == "Test Team"
        assert route.call_count == 3  # Initial + 2 retries
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_ryzellx_invalid_json_error(self, provider):
        """Test that invalid JSON raises ProviderInvalidDataError."""
        test_date = date(2024, 1, 15)
        
        respx.get(f"{provider.base_url}/api/matches/date/{test_date.isoformat()}").mock(
            return_value=httpx.Response(200, text="This is not JSON")
        )
        
        with pytest.raises(ProviderInvalidDataError) as exc_info:
            await provider.get_matches_by_date(test_date)
        
        assert exc_info.value.provider_name == "ryzellx"
        assert "parse" in exc_info.value.message.lower()
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_ryzellx_cache_integration(self, provider):
        """Test that cache is used correctly."""
        team_id = "team_cached"
        
        # Mock API response
        mock_response = {
            "id": "team_cached",
            "name": "Cached Team"
        }
        
        route = respx.get(f"{provider.base_url}/api/team/{team_id}").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        
        # First call - should hit API
        team1 = await provider.get_team(team_id)
        assert team1 is not None
        assert team1.name == "Cached Team"
        assert route.call_count == 1
        
        # Second call - should hit cache
        team2 = await provider.get_team(team_id)
        assert team2 is not None
        assert team2.name == "Cached Team"
        assert route.call_count == 1  # Still 1, not called again
        
        # Verify both returns are the same
        assert team1.source_id == team2.source_id
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_ryzellx_normalization_none_values(self, provider):
        """Test that missing fields are normalized to None, not invented."""
        match_id = "match_minimal"
        
        # Mock API response with minimal fields
        mock_response = {
            "id": "match_minimal",
            "home_team": "Home Team",
            "home_id": "home_1",
            "away_team": "Away Team",
            "away_id": "away_1",
            "date": "2024-01-20T15:00:00Z",
            "status": "scheduled"
            # No xG, no stats, no venue, etc.
        }
        
        respx.get(f"{provider.base_url}/api/match/{match_id}").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        
        # Call method
        match = await provider.get_match(match_id)
        
        # Assertions - all optional fields should be None
        assert match is not None
        assert match.venue_name is None
        assert match.home_score is None
        assert match.away_score is None
        assert match.minute is None
        assert match.competition_id is None
        # No invented values!


class TestFotMobProvider:
    """Tests for FotMobFootballProvider (LIVE/FAST provider, unofficial)."""
    
    @pytest.fixture
    def provider(self):
        """Create FotMobFootballProvider instance for testing."""
        from app.providers.fotmob import FotMobFootballProvider
        
        cache = ProviderCache()
        provider = FotMobFootballProvider(
            base_url="https://test-fotmob.example.com",
            timeout_seconds=10.0,
            retry_count=1,  # Conservative
            cache=cache
        )
        yield provider
        # Cleanup
        import asyncio
        asyncio.run(provider.close())
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_fotmob_provider_name(self, provider):
        """Test FotMob provider identifies itself correctly."""
        assert provider.PROVIDER_NAME == "fotmob"
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_fotmob_get_matches_by_date(self, provider):
        """Test get_matches_by_date returns normalized matches."""
        from app.providers.fotmob import FotMobFootballProvider
        
        test_date = date(2024, 1, 15)
        date_str = "20240115"
        
        # Mock FotMob API response structure
        mock_response = {
            "leagues": [
                {
                    "name": "Premier League",
                    "id": "47",
                    "matches": [
                        {
                            "id": "fotmob_match_1",
                            "home": {
                                "id": "team_1",
                                "name": "Arsenal"
                            },
                            "away": {
                                "id": "team_2",
                                "name": "Liverpool"
                            },
                            "startTime": "2024-01-15T15:00:00Z",
                            "status": {
                                "type": "not_started"
                            },
                            "league": {
                                "id": "47",
                                "name": "Premier League"
                            }
                        }
                    ]
                }
            ]
        }
        
        respx.get(f"{provider.base_url}/api/data/matches").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        
        # Call method
        matches = await provider.get_matches_by_date(test_date)
        
        # Assertions
        assert len(matches) == 1
        assert all(isinstance(m, ProviderMatch) for m in matches)
        assert matches[0].provider == "fotmob"
        assert matches[0].source_id == "fotmob_match_1"
        assert matches[0].home_team_name == "Arsenal"
        assert matches[0].away_team_name == "Liverpool"
        assert matches[0].status == MatchStatus.SCHEDULED
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_fotmob_get_match(self, provider):
        """Test get_match returns detailed match info."""
        match_id = "fotmob_456"
        
        # Mock FotMob match details response
        mock_response = {
            "id": "fotmob_456",
            "home": {
                "id": "team_10",
                "name": "Real Madrid"
            },
            "away": {
                "id": "team_11",
                "name": "Barcelona"
            },
            "startTime": "2024-01-20T21:00:00Z",
            "status": {
                "type": "live",
                "minute": 67
            },
            "score": {
                "home": 2,
                "away": 2
            },
            "venue": "Santiago Bernabéu",
            "league": {
                "id": "87",
                "name": "La Liga"
            }
        }
        
        respx.get(f"{provider.base_url}/api/data/matchDetails").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        
        # Call method
        match = await provider.get_match(match_id)
        
        # Assertions
        assert match is not None
        assert match.provider == "fotmob"
        assert match.source_id == "fotmob_456"
        assert match.home_team_name == "Real Madrid"
        assert match.away_team_name == "Barcelona"
        assert match.status == MatchStatus.LIVE
        assert match.minute == 67
        assert match.home_score == 2
        assert match.away_score == 2
        assert match.is_live is True
        assert match.venue_name == "Santiago Bernabéu"
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_fotmob_get_match_not_found(self, provider):
        """Test get_match returns None for 404."""
        match_id = "nonexistent"
        
        respx.get(f"{provider.base_url}/api/data/matchDetails").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        
        # Call method
        match = await provider.get_match(match_id)
        
        # Assertions
        assert match is None
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_fotmob_get_live_matches(self, provider):
        """Test get_live_matches returns live match data."""
        # Mock FotMob live matches response
        mock_response = {
            "leagues": [
                {
                    "matches": [
                        {
                            "id": "live_1",
                            "home": {"id": "team_x", "name": "Team X"},
                            "away": {"id": "team_y", "name": "Team Y"},
                            "status": {"type": "live", "minute": 34},
                            "score": {"home": 1, "away": 0}
                        },
                        {
                            "id": "live_2",
                            "home": {"id": "team_z", "name": "Team Z"},
                            "away": {"id": "team_w", "name": "Team W"},
                            "status": {"type": "live", "minute": 78},
                            "score": {"home": 2, "away": 2}
                        },
                        {
                            "id": "finished_1",
                            "home": {"id": "team_a", "name": "Team A"},
                            "away": {"id": "team_b", "name": "Team B"},
                            "status": {"type": "finished"},
                            "score": {"home": 3, "away": 1}
                        }
                    ]
                }
            ]
        }
        
        # FotMob doesn't have /live endpoint - it queries today's matches
        # Mock today's date endpoint
        from datetime import date
        today = date.today()
        date_str = today.strftime("%Y%m%d")
        
        respx.get(f"{provider.base_url}/api/data/matches").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        
        # Call method
        live_matches = await provider.get_live_matches()
        
        # Assertions - should only return live matches, not finished
        assert len(live_matches) == 2
        assert all(isinstance(m, ProviderLiveMatch) for m in live_matches)
        assert live_matches[0].provider == "fotmob"
        assert live_matches[0].match_id == "live_1"
        assert live_matches[0].status == MatchStatus.LIVE
        assert live_matches[0].minute == 34
        assert live_matches[0].home_score == 1
        assert live_matches[0].away_score == 0
        assert live_matches[0].is_live is True
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_fotmob_timeout_error(self, provider):
        """Test that timeout raises ProviderTimeoutError."""
        test_date = date(2024, 1, 15)
        
        respx.get(f"{provider.base_url}/api/data/matches").mock(
            side_effect=httpx.TimeoutException("Timeout")
        )
        
        with pytest.raises(ProviderTimeoutError) as exc_info:
            await provider.get_matches_by_date(test_date)
        
        assert exc_info.value.provider_name == "fotmob"
        assert "timed out" in exc_info.value.message.lower()
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_fotmob_http_error(self, provider):
        """Test that HTTP errors raise ProviderHTTPError."""
        match_id = "bad_id"
        
        respx.get(f"{provider.base_url}/api/data/matchDetails").mock(
            return_value=httpx.Response(400, json={"error": "Bad request"})
        )
        
        with pytest.raises(ProviderHTTPError) as exc_info:
            await provider.get_match(match_id)
        
        assert exc_info.value.provider_name == "fotmob"
        assert exc_info.value.status_code == 400
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_fotmob_conservative_retry(self, provider):
        """Test that FotMob uses conservative retry (retry_count=1)."""
        team_id = "team_123"
        
        # Verify provider has conservative retry_count
        assert provider.retry_count == 1
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_fotmob_invalid_json_error(self, provider):
        """Test that invalid JSON raises ProviderInvalidDataError."""
        test_date = date(2024, 1, 15)
        
        respx.get(f"{provider.base_url}/api/data/matches").mock(
            return_value=httpx.Response(200, text="This is not JSON")
        )
        
        with pytest.raises(ProviderInvalidDataError) as exc_info:
            await provider.get_matches_by_date(test_date)
        
        assert exc_info.value.provider_name == "fotmob"
        assert "parse" in exc_info.value.message.lower()
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_fotmob_normalization_none_values(self, provider):
        """Test that missing fields are normalized to None, not invented."""
        match_id = "match_minimal"
        
        # Mock API response with minimal fields
        mock_response = {
            "id": "match_minimal",
            "home": {
                "id": "home_1",
                "name": "Home Team"
            },
            "away": {
                "id": "away_1",
                "name": "Away Team"
            },
            "startTime": "2024-01-20T15:00:00Z",
            "status": {
                "type": "not_started"
            }
            # No venue, no score, no minute, etc.
        }
        
        respx.get(f"{provider.base_url}/api/data/matchDetails").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        
        # Call method
        match = await provider.get_match(match_id)
        
        # Assertions - all optional fields should be None
        assert match is not None
        assert match.venue_name is None
        assert match.home_score is None
        assert match.away_score is None
        assert match.minute is None
        # No invented values!
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_fotmob_cache_integration(self, provider):
        """Test that cache is used correctly."""
        match_id = "match_cached"
        
        # Mock API response
        mock_response = {
            "id": "match_cached",
            "home": {"id": "home_1", "name": "Home Team"},
            "away": {"id": "away_1", "name": "Away Team"},
            "startTime": "2024-01-20T15:00:00Z",
            "status": {"type": "scheduled"}
        }
        
        route = respx.get(f"{provider.base_url}/api/data/matchDetails").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        
        # First call - should hit API
        match1 = await provider.get_match(match_id)
        assert match1 is not None
        assert match1.home_team_name == "Home Team"
        assert route.call_count == 1
        
        # Second call - should hit cache
        match2 = await provider.get_match(match_id)
        assert match2 is not None
        assert match2.home_team_name == "Home Team"
        assert route.call_count == 1  # Still 1, not called again
        
        # Verify both returns are the same
        assert match1.source_id == match2.source_id
    
    @pytest.mark.asyncio
    async def test_fotmob_stub_methods(self, provider):
        """Test that stub methods return None/empty as documented."""
        # get_league should return None
        league = await provider.get_league("league_123")
        assert league is None
        
        # get_team should return None
        team = await provider.get_team("team_123")
        assert team is None
        
        # get_player should return None
        player = await provider.get_player("player_123")
        assert player is None
        
        # get_standings should return empty list
        standings = await provider.get_standings("league_123")
        assert standings == []
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_fotmob_live_matches_fallback(self, provider):
        """Test that get_live_matches falls back to daily matches if live endpoint fails."""
        # Mock primary live endpoint to fail
        respx.get(f"{provider.base_url}/api/matches/live").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        
        # Mock fallback to daily matches
        today = date.today()
        date_str = today.strftime("%Y%m%d")
        
        mock_response = {
            "leagues": [
                {
                    "matches": [
                        {
                            "id": "live_fallback",
                            "home": {"id": "team_x", "name": "Team X"},
                            "away": {"id": "team_y", "name": "Team Y"},
                            "status": {"type": "live", "minute": 50},
                            "score": {"home": 1, "away": 1}
                        }
                    ]
                }
            ]
        }
        
        respx.get(f"{provider.base_url}/api/data/matches").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        
        # Call method
        live_matches = await provider.get_live_matches()
        
        # Assertions - should get live matches from fallback
        assert len(live_matches) == 1
        assert live_matches[0].match_id == "live_fallback"
        assert live_matches[0].status == MatchStatus.LIVE

