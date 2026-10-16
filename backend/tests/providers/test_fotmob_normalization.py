"""Regression tests for FotMob match detail normalization.

Tests the fix for the FotMob matchDetails response structure bug where team data
is now located in general.homeTeam/awayTeam instead of the old home/away keys.
"""

import pytest
import respx
import httpx
from datetime import datetime, timezone

from app.providers.fotmob import FotMobFootballProvider
from app.providers.models import ProviderMatch
from app.providers.exceptions import ProviderInvalidDataError
from app.domain.enums import MatchStatus


@pytest.fixture
def provider():
    """Create FotMob provider instance for testing."""
    return FotMobFootballProvider(
        base_url="https://www.fotmob.com",
        timeout_seconds=10.0,
        retry_count=1
    )


@pytest.mark.asyncio
@respx.mock
async def test_fotmob_matchdetails_real_structure(provider):
    """Test normalization of confirmed FotMob matchDetails structure (match 5181855).
    
    This test uses the confirmed real response structure from FotMob's matchDetails
    endpoint with general.homeTeam/awayTeam and header.teams.
    """
    match_id = "5181855"
    
    # Confirmed real FotMob matchDetails response structure
    mock_response = {
        "general": {
            "matchId": "5181855",
            "leagueId": 920743,
            "leagueName": "UEFA Nations League A Grp. 3",
            "matchRound": "4",
            "homeTeam": {"name": "Croatia", "id": 10155},
            "awayTeam": {"name": "Spain", "id": 6720},
            "matchTimeUTCDate": "2026-10-06T18:45:00.000Z"
        },
        "header": {
            "teams": [
                {"name": "Croatia", "id": 10155, "score": 0},
                {"name": "Spain", "id": 6720, "score": 0}
            ],
            "status": {
                "utcTime": "2026-10-06T18:45:00.000Z",
                "started": False,
                "cancelled": False,
                "finished": False
            }
        },
        # Some endpoints may have top-level id/matchId, but matchDetails typically doesn't
        # Adding for compatibility with test infrastructure
        "id": "5181855"
    }
    
    respx.get(f"{provider.base_url}/api/data/matchDetails").mock(
        return_value=httpx.Response(200, json=mock_response)
    )
    
    # Call provider
    match = await provider.get_match(match_id)
    
    # Assertions
    assert match is not None
    assert match.provider == "fotmob"
    assert match.source_id == "5181855"
    assert match.home_team_id == "10155"
    assert match.home_team_name == "Croatia"
    assert match.away_team_id == "6720"
    assert match.away_team_name == "Spain"
    assert match.competition_id == "920743"
    assert match.competition_name == "UEFA Nations League A Grp. 3"
    assert match.round == 4
    assert match.home_score == 0
    assert match.away_score == 0
    assert match.status == MatchStatus.SCHEDULED
    # Verify scheduled_at parsed from general.matchTimeUTCDate
    assert match.scheduled_at.year == 2026
    assert match.scheduled_at.month == 10
    assert match.scheduled_at.day == 6
    assert match.scheduled_at.hour == 18
    assert match.scheduled_at.minute == 45


@pytest.mark.asyncio
@respx.mock
async def test_fotmob_header_teams_fallback(provider):
    """Test that header.teams is used when general.homeTeam/awayTeam not available.
    
    This tests the secondary fallback path for match list structures.
    """
    match_id = "5181856"
    
    # Response with header.teams but no general.homeTeam/awayTeam
    mock_response = {
        "id": "5181856",
        "header": {
            "teams": [
                {"name": "Portugal", "id": 8201, "score": 1},
                {"name": "France", "id": 8558, "score": 2}
            ],
            "status": {
                "utcTime": "2026-10-07T19:00:00.000Z",
                "started": False,
                "cancelled": False,
                "finished": True
            }
        },
        "status": {
            "utcTime": "2026-10-07T19:00:00.000Z",
            "finished": True
        }
    }
    
    respx.get(f"{provider.base_url}/api/data/matchDetails").mock(
        return_value=httpx.Response(200, json=mock_response)
    )
    
    # Call provider
    match = await provider.get_match(match_id)
    
    # Assertions - team data should come from header.teams
    assert match is not None
    assert match.home_team_id == "8201"
    assert match.home_team_name == "Portugal"
    assert match.away_team_id == "8558"
    assert match.away_team_name == "France"
    assert match.home_score == 1
    assert match.away_score == 2
    assert match.status == MatchStatus.FINISHED


@pytest.mark.asyncio
@respx.mock
async def test_fotmob_scores_from_header_teams(provider):
    """Test that scores are correctly extracted from header.teams.
    
    Priority 1: header.teams[x].score
    Priority 2: team object scores (backward compatibility)
    """
    match_id = "5181857"
    
    mock_response = {
        "id": "5181857",
        "general": {
            "matchId": "5181857",
            "homeTeam": {"name": "Germany", "id": 8722},  # No score here
            "awayTeam": {"name": "Italy", "id": 8676},    # No score here
            "matchTimeUTCDate": "2026-10-08T20:00:00.000Z"
        },
        "header": {
            "teams": [
                {"name": "Germany", "id": 8722, "score": 3},  # Scores here
                {"name": "Italy", "id": 8676, "score": 1}
            ],
            "status": {
                "utcTime": "2026-10-08T20:00:00.000Z",
                "started": False,
                "cancelled": False,
                "finished": True
            }
        }
    }
    
    respx.get(f"{provider.base_url}/api/data/matchDetails").mock(
        return_value=httpx.Response(200, json=mock_response)
    )
    
    # Call provider
    match = await provider.get_match(match_id)
    
    # Assertions - scores should come from header.teams (priority 1)
    assert match is not None
    assert match.home_score == 3
    assert match.away_score == 1


@pytest.mark.asyncio
@respx.mock
async def test_fotmob_malformed_data_no_fabrication(provider):
    """Test that malformed data with no valid team IDs raises error (no fabrication).
    
    DATA INTEGRITY RULE: REAL DATA > NULL/UNAVAILABLE > FABRICATED DATA
    
    When neither general.homeTeam/awayTeam nor header.teams contains valid IDs,
    the provider must raise ProviderInvalidDataError instead of fabricating IDs.
    """
    match_id = "5181858"
    
    # Malformed response with no valid team IDs
    mock_response = {
        "id": "5181858",  # Has ID but no team data
        "general": {
            "matchId": "5181858",
            # homeTeam and awayTeam missing
        },
        "header": {
            # teams missing or malformed
            "status": {
                "utcTime": "2026-10-09T18:00:00.000Z"
            }
        }
    }
    
    respx.get(f"{provider.base_url}/api/data/matchDetails").mock(
        return_value=httpx.Response(200, json=mock_response)
    )
    
    # Call provider - should raise ProviderInvalidDataError
    with pytest.raises(ProviderInvalidDataError) as exc_info:
        await provider.get_match(match_id)
    
    # Verify error details
    assert exc_info.value.provider_name == "fotmob"
    assert exc_info.value.operation == "normalize_match"
    assert "Missing required team IDs" in exc_info.value.message
    assert "5181858" in exc_info.value.message


@pytest.mark.asyncio
@respx.mock
async def test_fotmob_backward_compatibility_old_structure(provider):
    """Test backward compatibility with old data.home / data.away structure.
    
    Some FotMob endpoints may still return the old structure, so we maintain
    backward compatibility as a tertiary fallback.
    """
    match_id = "5181859"
    
    # Old structure with home/away keys (match list format)
    mock_response = {
        "id": "5181859",
        "home": {
            "id": 9825,
            "name": "Belgium",
            "score": 2
        },
        "away": {
            "id": 9789,
            "name": "Netherlands",
            "score": 2
        },
        "status": {
            "utcTime": "2026-10-10T17:30:00.000Z",
            "finished": True
        }
    }
    
    respx.get(f"{provider.base_url}/api/data/matchDetails").mock(
        return_value=httpx.Response(200, json=mock_response)
    )
    
    # Call provider
    match = await provider.get_match(match_id)
    
    # Assertions - should still work with old structure
    assert match is not None
    assert match.home_team_id == "9825"
    assert match.home_team_name == "Belgium"
    assert match.away_team_id == "9789"
    assert match.away_team_name == "Netherlands"
    assert match.home_score == 2
    assert match.away_score == 2


@pytest.mark.asyncio
@respx.mock
async def test_fotmob_league_context_preservation(provider):
    """Test that league_context is respected when provided.
    
    When get_matches_by_date calls _normalize_match with league_context,
    competition data should come from league_context, not general data.
    """
    # This test verifies the internal _normalize_match behavior
    # by directly calling it (normally called by get_matches_by_date)
    
    match_data = {
        "id": "5181860",
        "general": {
            "matchId": "5181860",
            "leagueId": 999999,  # Should be IGNORED
            "leagueName": "Wrong League",  # Should be IGNORED
            "homeTeam": {"name": "Team A", "id": 1001},
            "awayTeam": {"name": "Team B", "id": 1002},
            "matchTimeUTCDate": "2026-10-11T18:00:00.000Z"
        },
        "header": {
            "teams": [
                {"name": "Team A", "id": 1001, "score": 0},
                {"name": "Team B", "id": 1002, "score": 0}
            ],
            "status": {
                "utcTime": "2026-10-11T18:00:00.000Z",
                "started": False
            }
        }
    }
    
    league_context = {
        "id": 54321,
        "name": "Correct League from Context"
    }
    
    # Call internal _normalize_match with league_context
    match = provider._normalize_match(match_data, league_context=league_context)
    
    # Assertions - competition should come from league_context, not general
    assert match is not None
    assert match.competition_id == "54321"
    assert match.competition_name == "Correct League from Context"
    # Team data should still come from general
    assert match.home_team_id == "1001"
    assert match.away_team_id == "1002"


@pytest.mark.asyncio
@respx.mock
async def test_fotmob_incomplete_header_teams(provider):
    """Test that incomplete header.teams (less than 2 teams) is handled.
    
    Should fall back to old structure or raise error if no valid team data.
    """
    match_id = "5181861"
    
    # Incomplete header.teams (only 1 team)
    mock_response = {
        "id": "5181861",
        "general": {
            "matchId": "5181861",
        },
        "header": {
            "teams": [
                {"name": "Team X", "id": 2001}
                # Missing second team
            ],
            "status": {
                "utcTime": "2026-10-12T18:00:00.000Z"
            }
        }
    }
    
    respx.get(f"{provider.base_url}/api/data/matchDetails").mock(
        return_value=httpx.Response(200, json=mock_response)
    )
    
    # Call provider - should raise ProviderInvalidDataError (no valid team data)
    with pytest.raises(ProviderInvalidDataError) as exc_info:
        await provider.get_match(match_id)
    
    assert "Missing required team IDs" in exc_info.value.message


@pytest.mark.asyncio
@respx.mock
async def test_fotmob_penalties_short_status(provider):
    """Test that 'penalties_short' status is correctly mapped to FINISHED.
    
    Regression test for FotMob status normalization issue where penalties_short
    was treated as unknown and defaulted to SCHEDULED, incorrectly classifying
    historical matches.
    """
    match_id = "5181862"
    
    mock_response = {
        "id": "5181862",
        "general": {
            "matchId": "5181862",
            "leagueId": 920743,
            "leagueName": "UEFA Nations League",
            "homeTeam": {"name": "Portugal", "id": 8201},
            "awayTeam": {"name": "France", "id": 8558},
            "matchTimeUTCDate": "2026-10-01T18:45:00.000Z"
        },
        "header": {
            "teams": [
                {"name": "Portugal", "id": 8201, "score": 1},
                {"name": "France", "id": 8558, "score": 1}
            ],
            "status": {
                "utcTime": "2026-10-01T18:45:00.000Z",
                "started": True,
                "cancelled": False,
                "finished": True,
                "reason": {
                    "shortKey": "penalties_short"
                }
            }
        },
        "status": {
            "reason": {
                "shortKey": "penalties_short"
            },
            "finished": True
        }
    }
    
    respx.get(f"{provider.base_url}/api/data/matchDetails").mock(
        return_value=httpx.Response(200, json=mock_response)
    )
    
    match = await provider.get_match(match_id)
    
    # Assert penalties_short maps to FINISHED (not SCHEDULED)
    assert match is not None
    assert match.status == MatchStatus.FINISHED, \
        "penalties_short should map to FINISHED, not SCHEDULED"
    assert match.home_score == 1
    assert match.away_score == 1


@pytest.mark.asyncio
@respx.mock
async def test_fotmob_afterextratime_short_status(provider):
    """Test that 'afterextratime_short' status is correctly mapped to FINISHED.
    
    Regression test for FotMob status normalization issue where afterextratime_short
    was treated as unknown and defaulted to SCHEDULED, incorrectly classifying
    historical matches.
    """
    match_id = "5181863"
    
    mock_response = {
        "id": "5181863",
        "general": {
            "matchId": "5181863",
            "leagueId": 920743,
            "leagueName": "UEFA Nations League",
            "homeTeam": {"name": "Germany", "id": 8722},
            "awayTeam": {"name": "Italy", "id": 8676},
            "matchTimeUTCDate": "2026-10-02T19:00:00.000Z"
        },
        "header": {
            "teams": [
                {"name": "Germany", "id": 8722, "score": 3},
                {"name": "Italy", "id": 8676, "score": 2}
            ],
            "status": {
                "utcTime": "2026-10-02T19:00:00.000Z",
                "started": True,
                "cancelled": False,
                "finished": True,
                "reason": {
                    "shortKey": "afterextratime_short"
                }
            }
        },
        "status": {
            "reason": {
                "shortKey": "afterextratime_short"
            },
            "finished": True
        }
    }
    
    respx.get(f"{provider.base_url}/api/data/matchDetails").mock(
        return_value=httpx.Response(200, json=mock_response)
    )
    
    match = await provider.get_match(match_id)
    
    # Assert afterextratime_short maps to FINISHED (not SCHEDULED)
    assert match is not None
    assert match.status == MatchStatus.FINISHED, \
        "afterextratime_short should map to FINISHED, not SCHEDULED"
    assert match.home_score == 3
    assert match.away_score == 2


@pytest.mark.asyncio
@respx.mock
async def test_fotmob_aborted_short_status(provider):
    """Test that 'aborted_short' status is correctly mapped to CANCELLED.
    
    Regression test for FotMob status normalization issue where aborted_short
    was treated as unknown and defaulted to SCHEDULED, incorrectly classifying
    abandoned matches.
    """
    match_id = "5181864"
    
    mock_response = {
        "id": "5181864",
        "general": {
            "matchId": "5181864",
            "leagueId": 920743,
            "leagueName": "UEFA Nations League",
            "homeTeam": {"name": "Spain", "id": 6720},
            "awayTeam": {"name": "Croatia", "id": 10155},
            "matchTimeUTCDate": "2026-10-03T20:00:00.000Z"
        },
        "header": {
            "teams": [
                {"name": "Spain", "id": 6720, "score": 0},
                {"name": "Croatia", "id": 10155, "score": 0}
            ],
            "status": {
                "utcTime": "2026-10-03T20:00:00.000Z",
                "started": True,
                "cancelled": True,
                "finished": False,
                "reason": {
                    "shortKey": "aborted_short"
                }
            }
        },
        "status": {
            "reason": {
                "shortKey": "aborted_short"
            },
            "cancelled": True
        }
    }
    
    respx.get(f"{provider.base_url}/api/data/matchDetails").mock(
        return_value=httpx.Response(200, json=mock_response)
    )
    
    match = await provider.get_match(match_id)
    
    # Assert aborted_short maps to CANCELLED (not SCHEDULED)
    assert match is not None
    assert match.status == MatchStatus.CANCELLED, \
        "aborted_short should map to CANCELLED, not SCHEDULED"
    assert match.home_score == 0
    assert match.away_score == 0
