#!/usr/bin/env python3
"""Debug complete API match flow to identify ID mapping issue."""

import asyncio
from app.api.v1.endpoints.matches import list_matches, get_match
from app.providers.hybrid_provider import HybridProvider
from app.providers.adapter import ProviderManagerAdapter
from app.providers.manager import ProviderManager
from app.providers.development import DevelopmentProvider
from app.database import SessionLocal

async def debug_api_flow():
    """Debug the complete API flow that frontend uses."""

    # Setup dependencies like the API endpoints do
    dev_provider = DevelopmentProvider()
    manager = ProviderManager(None, None, dev_provider)
    adapter = ProviderManagerAdapter(manager)
    session = SessionLocal()
    hybrid = HybridProvider(adapter, session)

    print("=== DEBUGGING API MATCH FLOW ===")

    # Step 1: Test list_matches endpoint behavior
    print("\n1. Testing list_matches endpoint:")
    try:
        # This simulates /api/v1/matches call
        matches_response = await list_matches(
            provider=hybrid,
            db=session
        )

        print(f"   ✅ Found {matches_response.count} matches")
        print(f"   Development data: {matches_response.is_development_data}")

        # Look for Fluminense matches specifically
        fluminense_matches = []
        for match in matches_response.matches:
            if (match.home_team and 'Fluminense' in str(match.home_team.name)) or \
               (match.away_team and 'Fluminense' in str(match.away_team.name)) or \
               match.home_team_id == '15fb5893-b396-433e-ae31-c85cfbcaef6b' or \
               match.away_team_id == '15fb5893-b396-433e-ae31-c85cfbcaef6b':
                fluminense_matches.append(match)

        print(f"   📋 Fluminense matches in API response: {len(fluminense_matches)}")

        for match in fluminense_matches:
            print(f"     ID: {match.id}")
            print(f"     Home: {match.home_team.name if match.home_team else match.home_team_id}")
            print(f"     Away: {match.away_team.name if match.away_team else match.away_team_id}")
            print(f"     Status: {match.status}")
            print("     ---")

    except Exception as e:
        print(f"   ❌ list_matches failed: {e}")
        import traceback
        traceback.print_exc()

    # Step 2: Test get_match for both IDs
    print("\n2. Testing get_match endpoint:")

    test_ids = [
        ("Real Canonical", "aa4c9808-cb36-486e-bd41-003cc28b8543"),
        ("User Reported", "1f05edd0-b0a5-4453-b70c-1892247bea54")
    ]

    for name, match_id in test_ids:
        print(f"   Testing {name} ID: {match_id}")
        try:
            match_response = await get_match(match_id=match_id, provider=hybrid)
            print(f"     ✅ Match found")
            print(f"     Home: {match_response.match.home_team.name if match_response.match.home_team else 'N/A'}")
            print(f"     Away: {match_response.match.away_team.name if match_response.match.away_team else 'N/A'}")
            print(f"     Status: {match_response.match.status}")
        except Exception as e:
            print(f"     ❌ Match not found or error: {e}")

    session.close()

if __name__ == "__main__":
    asyncio.run(debug_api_flow())
