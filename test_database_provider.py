#!/usr/bin/env python3
"""
Test DatabaseBackedProvider directly
"""

import sys
import os
os.chdir('backend')
sys.path.insert(0, '.')

from app.providers.database_adapter import DatabaseBackedProvider
from app.database.session import SessionLocal

def test_database_provider():
    """Test database provider directly"""

    session = SessionLocal()
    provider = DatabaseBackedProvider(session)

    try:
        print("=== Testing DatabaseBackedProvider ===")

        # Test get_matches
        print("\n1. Testing get_matches:")
        matches = provider.get_matches()
        print(f"Total matches: {len(matches)}")

        if matches:
            print(f"First match: {matches[0].id}")
            # Look for Fluminense
            for match in matches[:10]:  # Check first 10
                home_team = provider.get_team(match.home_team_id)
                away_team = provider.get_team(match.away_team_id)
                home_name = home_team.name if home_team else "Unknown"
                away_name = away_team.name if away_team else "Unknown"

                if "Fluminense" in home_name or "Fluminense" in away_name:
                    print(f"Found Fluminense match: {home_name} vs {away_name} (ID: {match.id})")
                    break

        # Test specific match
        print("\n2. Testing get_match with correct ID:")
        correct_id = "aa4c9808-cb36-486e-bd41-003cc28b8543"
        match = provider.get_match(correct_id)

        if match:
            home_team = provider.get_team(match.home_team_id)
            away_team = provider.get_team(match.away_team_id)
            home_name = home_team.name if home_team else "Unknown"
            away_name = away_team.name if away_team else "Unknown"
            print(f"✅ Found: {home_name} vs {away_name}")
            print(f"   Status: {match.status}")
            print(f"   Date: {match.scheduled_at}")
        else:
            print("❌ Match not found")

    finally:
        session.close()

if __name__ == "__main__":
    test_database_provider()
