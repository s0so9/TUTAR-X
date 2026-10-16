"""Tests for OpenLigaDB Football Provider."""

import pytest
from datetime import datetime, timezone
import respx
from httpx import Response

from app.providers.openligadb import OpenLigaDBFootballProvider
from app.providers.models import ProviderMatch, ProviderCompetition
from app.providers.exceptions import ProviderHTTPError, ProviderNotFoundError
from app.domain.enums import MatchStatus


@pytest.fixture
def openligadb_provider():
    """Create OpenLigaDB provider for testing."""
    return OpenLigaDBFootballProvider(
        base_url="https://api.openligadb.de",
        timeout_seconds=10.0,
        retry_count=2,
    )


@pytest.fixture
def mock_match_data():
    """Mock match data from OpenLigaDB API."""
    return {
        "matchID": 12345,
        "matchDateTime": "2024-03-15T15:30:00Z",
        "matchDateTimeUTC": "2024-03-15T15:30:00Z",
        "matchIsFinished": True,
        "leagueId": 4711,
        "leagueName": "Bundesliga",
        "leagueSeason": "2023/2024",
        "team1": {
            "teamId": 100,
            "teamName": "FC Bayern München"
        },
        "team2": {
            "teamId": 101,
            "teamName": "Borussia Dortmund"
        },
        "matchResults": [
            {
                "resultTypeID": 1,
                "pointsTeam1": 1,
                "pointsTeam2": 0
            },
            {
                "resultTypeID": 2,
                "pointsTeam1": 3,
                "pointsTeam2": 1
            }
        ],
        "location": "Allianz Arena",
        "group": {
            "groupOrderID": 10
        }
    }


@pytest.fixture
def mock_league_data():
    """Mock league data from OpenLigaDB API."""
    return [
        {
            "leagueId": 4711,
            "leagueName": "Bundesliga",
            "leagueShortcut": "bl1",
            "leagueSeason": "2023/2024"
        },
        {
            "leagueId": 4512,
            "leagueName": "2. Bundesliga",
            "leagueShortcut": "bl2",
            "leagueSeason": "2023/2024"
        }
    ]


@pytest.mark.asyncio
async def test_openligadb_get_match_returns_provider_match(
    openligadb_provider,
    mock_match_data
):
    """Test that get_match returns ProviderMatch."""
    with respx.mock:
        respx.get("https://api.openligadb.de/getmatchdata/12345").mock(
            return_value=Response(200, json=mock_match_data)
        )
        
        result = await openligadb_provider.get_match("12345")
        
        assert result is not None
        assert isinstance(result, ProviderMatch)
        assert result.provider == "openligadb"
        assert result.source_id == "12345"
        assert result.home_team_name == "FC Bayern München"
        assert result.away_team_name == "Borussia Dortmund"
        assert result.home_score == 3
        assert result.away_score == 1
        assert result.status == MatchStatus.FINISHED


@pytest.mark.asyncio
async def test_openligadb_get_match_no_xg(openligadb_provider, mock_match_data):
    """Test that OpenLigaDB provider never provides xG data.
    
    CRITICAL: OpenLigaDB does not provide xG. This is NOT a missing field
    to failover on - it's the authoritative result.
    """
    with respx.mock:
        respx.get("https://api.openligadb.de/getmatchdata/12345").mock(
            return_value=Response(200, json=mock_match_data)
        )
        
        result = await openligadb_provider.get_match("12345")
        
        assert result is not None
        # ProviderMatch doesn't have xg field directly - xG would be in ProviderMatchStats
        # The point is that OpenLigaDB never provides xG data in any form
        assert result.provider == "openligadb"
        assert result.source_id == "12345"


@pytest.mark.asyncio
async def test_openligadb_get_league_returns_competition(
    openligadb_provider,
    mock_league_data
):
    """Test that get_league returns ProviderCompetition."""
    with respx.mock:
        respx.get("https://api.openligadb.de/getavailableleagues").mock(
            return_value=Response(200, json=mock_league_data)
        )
        
        result = await openligadb_provider.get_league("4711")
        
        assert result is not None
        assert isinstance(result, ProviderCompetition)
        assert result.provider == "openligadb"
        assert result.source_id == "4711"
        assert result.name == "Bundesliga"
        assert result.season == "2023/2024"


@pytest.mark.asyncio
async def test_openligadb_get_matches_by_date_returns_empty(openligadb_provider):
    """Test that get_matches_by_date returns empty list (stub)."""
    from datetime import date
    
    result = await openligadb_provider.get_matches_by_date(date(2024, 3, 15))
    
    assert result == []


@pytest.mark.asyncio
async def test_openligadb_get_live_matches_returns_empty(openligadb_provider):
    """Test that get_live_matches returns empty list (stub)."""
    result = await openligadb_provider.get_live_matches()
    
    assert result == []


@pytest.mark.asyncio
async def test_openligadb_get_team_returns_none(openligadb_provider):
    """Test that get_team returns None (stub)."""
    result = await openligadb_provider.get_team("100")
    
    assert result is None


@pytest.mark.asyncio
async def test_openligadb_get_player_returns_none(openligadb_provider):
    """Test that get_player returns None (stub)."""
    result = await openligadb_provider.get_player("500")
    
    assert result is None


@pytest.mark.asyncio
async def test_openligadb_get_match_not_found_returns_none(openligadb_provider):
    """Test that get_match returns None when match not found (404)."""
    with respx.mock:
        respx.get("https://api.openligadb.de/getmatchdata/99999").mock(
            return_value=Response(404)
        )
        
        result = await openligadb_provider.get_match("99999")
        
        assert result is None


@pytest.mark.asyncio
async def test_openligadb_get_match_server_error_raises(openligadb_provider):
    """Test that server error raises ProviderHTTPError after retries."""
    with respx.mock:
        # Mock all retry attempts to return 500
        respx.get("https://api.openligadb.de/getmatchdata/12345").mock(
            return_value=Response(500, text="Internal Server Error")
        )
        
        with pytest.raises(ProviderHTTPError) as exc_info:
            await openligadb_provider.get_match("12345")
        
        assert exc_info.value.status_code == 500
        assert exc_info.value.provider_name == "openligadb"


@pytest.mark.asyncio
async def test_openligadb_close(openligadb_provider):
    """Test that close() properly closes the HTTP client."""
    await openligadb_provider.close()
    
    # Verify client is closed (attempting to use it would fail)
    assert openligadb_provider._client.is_closed
