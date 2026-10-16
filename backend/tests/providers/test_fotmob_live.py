"""Test FotMob provider with real API calls.

This test validates the corrected FotMob integration by making
actual HTTP calls to FotMob's public endpoints.
"""

import pytest
from datetime import date, datetime
from app.providers.fotmob import FotMobFootballProvider


@pytest.mark.asyncio
async def test_fotmob_get_matches_by_date_real():
    """Test FotMob get_matches_by_date with real API call."""
    provider = FotMobFootballProvider(
        base_url="https://www.fotmob.com",
        timeout_seconds=10.0,
        retry_count=1,
    )
    
    try:
        # Get matches for today
        today = date.today()
        matches = await provider.get_matches_by_date(today)
        
        # Validate response
        assert isinstance(matches, list), "Response should be a list"
        
        if len(matches) > 0:
            # If matches exist, validate structure
            match = matches[0]
            assert match.provider == "fotmob"
            assert match.source_id is not None
            assert match.home_team_name is not None
            assert match.away_team_name is not None
            print(f"✓ Found {len(matches)} matches for {today}")
            print(f"  Sample: {match.home_team_name} vs {match.away_team_name}")
        else:
            print(f"✓ No matches scheduled for {today} (valid response)")
            
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_fotmob_endpoint_structure():
    """Test that FotMob endpoints are correctly structured."""
    provider = FotMobFootballProvider(
        base_url="https://www.fotmob.com",
        timeout_seconds=10.0,
        retry_count=1,
    )
    
    try:
        # Make a raw request to verify endpoint structure
        today = date.today()
        date_str = today.strftime("%Y%m%d")
        
        # This should succeed with HTTP 200
        data = await provider._request("GET", "/api/data/matches", params={"date": date_str})
        
        # Validate response structure
        assert isinstance(data, dict), "Response should be a dict"
        assert "leagues" in data or "date" in data, "Response should contain leagues or date"
        
        print(f"✓ Endpoint structure validated")
        if "leagues" in data:
            print(f"  Leagues in response: {len(data['leagues'])}")
        if "date" in data:
            print(f"  Date in response: {data['date']}")
            
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_fotmob_live_matches_real():
    """Test FotMob get_live_matches with real API call."""
    provider = FotMobFootballProvider(
        base_url="https://www.fotmob.com",
        timeout_seconds=10.0,
        retry_count=1,
    )
    
    try:
        # Get live matches
        live_matches = await provider.get_live_matches()
        
        # Validate response
        assert isinstance(live_matches, list), "Response should be a list"
        
        if len(live_matches) > 0:
            # If live matches exist, validate structure
            match = live_matches[0]
            assert match.provider == "fotmob"
            assert match.is_live is True
            assert match.home_score is not None
            assert match.away_score is not None
            print(f"✓ Found {len(live_matches)} live matches")
            print(f"  Sample: Score {match.home_score}-{match.away_score}, Minute: {match.minute}")
        else:
            print(f"✓ No live matches currently (valid response)")
            
    finally:
        await provider.close()


if __name__ == "__main__":
    import asyncio
    
    async def run_tests():
        print("Testing FotMob Provider with Real API Calls")
        print("=" * 60)
        
        print("\nTest 1: Get Matches by Date")
        print("-" * 60)
        await test_fotmob_get_matches_by_date_real()
        
        print("\nTest 2: Endpoint Structure")
        print("-" * 60)
        await test_fotmob_endpoint_structure()
        
        print("\nTest 3: Live Matches")
        print("-" * 60)
        await test_fotmob_live_matches_real()
        
        print("\n" + "=" * 60)
        print("All FotMob tests completed successfully!")
    
    asyncio.run(run_tests())
