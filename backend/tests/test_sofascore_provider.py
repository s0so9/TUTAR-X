"""Tests for SofaScore provider.

These tests verify the SofaScore provider implementation using mocked HTTP requests.
NO REAL API CALLS are made in these tests.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock
import httpx

from app.providers import (
    SofaScoreFootballProvider,
    ProviderCache,
    ProviderMatchStats,
    ProviderMatch,
    ProviderLiveMatch,
)
from app.providers.exceptions import (
    ProviderNotFoundError,
    ProviderHTTPError,
    ProviderInvalidDataError,
    ProviderTimeoutError,
)
from app.domain.enums import MatchStatus, MatchOutcome


@pytest.fixture
def provider():
    """Create a SofaScore provider instance without cache."""
    return SofaScoreFootballProvider(
        base_url="https://api.sofascore.test",
        timeout_seconds=5.0,
        retry_count=1,
        cache=None
    )


@pytest.fixture
def provider_with_cache():
    """Create a SofaScore provider instance with cache."""
    cache = ProviderCache()
    return SofaScoreFootballProvider(
        base_url="https://api.sofascore.test",
        timeout_seconds=5.0,
        retry_count=1,
        cache=cache
    )


@pytest.fixture
def mock_statistics_response():
    """Mock SofaScore statistics API response."""
    return {
        "event": {
            "id": 12345
        },
        "statistics": [
            {
                "period": "ALL",
                "groups": [
                    {
                        "groupName": "Shots",
                        "statisticsItems": [
                            {
                                "name": "Total shots",
                                "home": "14",
                                "away": "8",
                                "homeValue": 14,
                                "awayValue": 8
                            },
                            {
                                "name": "Shots on target",
                                "home": "5",
                                "away": "3",
                                "homeValue": 5,
                                "awayValue": 3
                            },
                            {
                                "name": "Shots off target",
                                "home": "6",
                                "away": "4",
                                "homeValue": 6,
                                "awayValue": 4
                            },
                            {
                                "name": "Blocked shots",
                                "home": "3",
                                "away": "1",
                                "homeValue": 3,
                                "awayValue": 1
                            }
                        ]
                    },
                    {
                        "groupName": "Possession",
                        "statisticsItems": [
                            {
                                "name": "Ball possession",
                                "home": "58%",
                                "away": "42%",
                                "homeValue": 58,
                                "awayValue": 42
                            }
                        ]
                    },
                    {
                        "groupName": "Expected goals",
                        "statisticsItems": [
                            {
                                "name": "Expected goals",
                                "home": "1.89",
                                "away": "0.76",
                                "homeValue": 1.89,
                                "awayValue": 0.76
                            }
                        ]
                    }
                ]
            }
        ]
    }


@pytest.fixture
def mock_match_response():
    """Mock SofaScore match API response."""
    return {
        "event": {
            "id": 12345,
            "startTimestamp": 1704119400,
            "homeTeam": {
                "id": 100,
                "name": "Liverpool"
            },
            "awayTeam": {
                "id": 200,
                "name": "Manchester United"
            },
            "homeScore": {
                "current": 2
            },
            "awayScore": {
                "current": 1
            },
            "status": {
                "type": "finished"
            },
            "tournament": {
                "id": 17,
                "name": "Premier League"
            },
            "season": {
                "name": "23/24"
            },
            "venue": {
                "stadium": {
                    "name": "Anfield"
                }
            },
            "roundInfo": {
                "round": 20
            }
        }
    }


@pytest.fixture
def mock_live_matches_response():
    """Mock SofaScore live matches API response."""
    return {
        "events": [
            {
                "id": 11111,
                "homeScore": {"current": 1},
                "awayScore": {"current": 0},
                "status": {
                    "type": "inprogress",
                    "description": "45"
                }
            },
            {
                "id": 22222,
                "homeScore": {"current": 2},
                "awayScore": {"current": 2},
                "status": {
                    "type": "halftime"
                }
            }
        ]
    }


class TestSofaScoreProviderInitialization:
    """Tests for SofaScore provider initialization."""

    def test_sofascore_provider_initialization(self, provider):
        """Verify SofaScore provider initializes correctly."""
        assert provider.PROVIDER_NAME == "sofascore"
        assert provider.base_url == "https://api.sofascore.test"
        assert provider.timeout_seconds == 5.0
        assert provider.retry_count == 1
        assert provider.cache is None

    def test_sofascore_provider_initialization_with_cache(self, provider_with_cache):
        """Verify SofaScore provider initializes with cache."""
        assert provider_with_cache.cache is not None
        assert isinstance(provider_with_cache.cache, ProviderCache)


class TestNormalizeMatchStatistics:
    """Tests for _normalize_match_statistics method."""

    def test_normalize_match_statistics_maps_all_fields(
        self,
        provider,
        mock_statistics_response
    ):
        """Verify statistics normalization maps all available fields."""
        home_stats, away_stats = provider._normalize_match_statistics(
            mock_statistics_response,
            period='full'
        )
        
        # Verify home stats
        assert home_stats is not None
        assert home_stats.provider == "sofascore"
        assert home_stats.match_id == "12345"
        assert home_stats.shots_total == 14
        assert home_stats.shots_on_target == 5
        assert home_stats.shots_off_target == 6
        assert home_stats.shots_blocked == 3
        assert home_stats.possession_percentage == 58
        assert home_stats.xg == 1.89
        assert home_stats.period == "full"
        
        # Verify away stats
        assert away_stats is not None
        assert away_stats.provider == "sofascore"
        assert away_stats.match_id == "12345"
        assert away_stats.shots_total == 8
        assert away_stats.shots_on_target == 3
        assert away_stats.shots_off_target == 4
        assert away_stats.shots_blocked == 1
        assert away_stats.possession_percentage == 42
        assert away_stats.xg == 0.76
        assert away_stats.period == "full"

    def test_normalize_match_statistics_handles_missing_fields(self, provider):
        """Verify normalization handles missing fields correctly."""
        minimal_response = {
            "event": {"id": 99999},
            "statistics": [
                {
                    "period": "ALL",
                    "groups": [
                        {
                            "groupName": "Shots",
                            "statisticsItems": [
                                {
                                    "name": "Total shots",
                                    "homeValue": 10,
                                    "awayValue": 7
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        
        home_stats, away_stats = provider._normalize_match_statistics(
            minimal_response,
            period='full'
        )
        
        assert home_stats is not None
        assert away_stats is not None
        assert home_stats.shots_total == 10
        assert away_stats.shots_total == 7
        
        # Fields not in response should be None
        assert home_stats.xg is None
        assert away_stats.xg is None
        assert home_stats.corners is None
        assert away_stats.corners is None

    def test_normalize_match_statistics_sets_period_field(
        self,
        provider,
        mock_statistics_response
    ):
        """Verify period field is set correctly."""
        home_stats, away_stats = provider._normalize_match_statistics(
            mock_statistics_response,
            period='full'
        )
        
        assert home_stats.period == "full"
        assert away_stats.period == "full"
        
        # Test with first_half period
        first_half_response = {
            "event": {"id": 12345},
            "statistics": [
                {
                    "period": "1ST",
                    "groups": [
                        {
                            "groupName": "Shots",
                            "statisticsItems": [
                                {
                                    "name": "Total shots",
                                    "homeValue": 7,
                                    "awayValue": 4
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        
        home_stats_ht, away_stats_ht = provider._normalize_match_statistics(
            first_half_response,
            period='first_half'
        )
        
        assert home_stats_ht.period == "first_half"
        assert away_stats_ht.period == "first_half"


class TestGetMatchStatistics:
    """Tests for get_match_statistics method."""

    @pytest.mark.asyncio
    async def test_get_match_statistics_returns_tuple(
        self,
        provider,
        mock_statistics_response
    ):
        """Verify get_match_statistics returns tuple of (home_stats, away_stats)."""
        # Mock the _request method
        with patch.object(provider, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_statistics_response
            
            result = await provider.get_match_statistics("12345", period='full')
            
            assert isinstance(result, tuple)
            assert len(result) == 2
            home_stats, away_stats = result
            assert isinstance(home_stats, ProviderMatchStats)
            assert isinstance(away_stats, ProviderMatchStats)
            
            # Verify request was made correctly
            mock_request.assert_called_once_with("GET", "/event/12345/statistics")

    @pytest.mark.asyncio
    async def test_get_match_caches_result(
        self,
        provider_with_cache,
        mock_statistics_response
    ):
        """Verify get_match_statistics caches results."""
        # Mock the _request method
        with patch.object(provider_with_cache, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_statistics_response
            
            # First call should hit API
            result1 = await provider_with_cache.get_match_statistics("12345", period='full')
            assert mock_request.call_count == 1
            
            # Second call should use cache
            result2 = await provider_with_cache.get_match_statistics("12345", period='full')
            assert mock_request.call_count == 1  # Still 1, not 2
            
            # Results should be identical
            assert result1[0].shots_total == result2[0].shots_total
            assert result1[1].shots_total == result2[1].shots_total


class TestParseMatchStatus:
    """Tests for _parse_match_status method."""

    def test_parse_match_status_handles_all_statuses(self, provider):
        """Verify _parse_match_status handles all status types."""
        test_cases = [
            ("inprogress", MatchStatus.LIVE),
            ("live", MatchStatus.LIVE),
            ("halftime", MatchStatus.HALF_TIME),
            ("finished", MatchStatus.FINISHED),
            ("ft", MatchStatus.FINISHED),
            ("postponed", MatchStatus.POSTPONED),
            ("cancelled", MatchStatus.CANCELLED),
            ("suspended", MatchStatus.SUSPENDED),
            ("notstarted", MatchStatus.SCHEDULED),
            ("scheduled", MatchStatus.SCHEDULED),
            (None, MatchStatus.SCHEDULED),
            ("unknown_status", MatchStatus.SCHEDULED),
        ]
        
        for status_str, expected in test_cases:
            result = provider._parse_match_status(status_str)
            assert result == expected, f"Failed for status: {status_str}"


class TestProviderExports:
    """Tests for provider exports and module structure."""

    def test_provider_exports(self):
        """Verify SofaScoreFootballProvider is properly exported."""
        from app.providers import SofaScoreFootballProvider as Exported
        assert Exported is not None
        assert Exported.PROVIDER_NAME == "sofascore"


@pytest.mark.asyncio
async def test_get_match_returns_provider_match(provider, mock_match_response):
    """Verify get_match returns ProviderMatch instance."""
    with patch.object(provider, '_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_match_response
        
        result = await provider.get_match("12345")
        
        assert isinstance(result, ProviderMatch)
        assert result.source_id == "12345"
        assert result.home_team_name == "Liverpool"
        assert result.away_team_name == "Manchester United"
        assert result.home_score == 2
        assert result.away_score == 1
        assert result.status == MatchStatus.FINISHED
        assert result.outcome == MatchOutcome.HOME_WIN


@pytest.mark.asyncio
async def test_get_match_not_found_returns_none(provider):
    """Verify get_match returns None for 404 responses."""
    with patch.object(provider, '_request', new_callable=AsyncMock) as mock_request:
        mock_request.side_effect = ProviderNotFoundError(
            provider_name="sofascore",
            operation="GET /event/99999",
            message="Not found"
        )
        
        result = await provider.get_match("99999")
        assert result is None


@pytest.mark.asyncio
async def test_get_live_matches_returns_list(provider, mock_live_matches_response):
    """Verify get_live_matches returns list of ProviderLiveMatch."""
    with patch.object(provider, '_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_live_matches_response
        
        result = await provider.get_live_matches()
        
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(match, ProviderLiveMatch) for match in result)
        assert result[0].match_id == "11111"
        assert result[0].home_score == 1
        assert result[0].away_score == 0
        assert result[0].status == MatchStatus.LIVE
        assert result[1].status == MatchStatus.HALF_TIME
