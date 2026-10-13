#!/usr/bin/env python3
"""
Debug database matches to understand ID structure
"""

import sys
import os

# Add backend to Python path
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))

# Change to backend directory for imports
os.chdir('backend')

from app.db.session import SessionLocal
from app.db.models.match import Match as MatchDB

def debug_database_matches():
    """Debug matches in the database"""

    # Create database session
    session = SessionLocal()

    try:
        # Find Fluminense matches
        print("=== Searching for Fluminense matches ===")
        fluminense_matches = session.query(MatchDB).filter(
            (MatchDB.home_team.ilike('%Fluminense%')) |
            (MatchDB.away_team.ilike('%Fluminense%'))
        ).all()

        print(f"Found {len(fluminense_matches)} Fluminense matches")

        for match in fluminense_matches[:5]:  # Show first 5
            print(f"\nMatch ID: {match.id}")
            print(f"Home: {match.home_team} (ID: {match.home_team_id})")
            print(f"Away: {match.away_team} (ID: {match.away_team_id})")
            print(f"Date: {match.scheduled_at}")
            print(f"Status: {match.status}")

        # Search for specific IDs
        print(f"\n=== Searching for specific IDs ===")

        correct_id = "aa4c9808-cb36-486e-bd41-003cc28b8543"
        wrong_id = "1f05edd0-b0a5-4453-b70c-1892247bea54"

        print(f"\n1. Searching for correct ID: {correct_id}")
        match = session.query(MatchDB).filter(MatchDB.id == correct_id).first()
        if match:
            print(f"✅ Found: {match.home_team} vs {match.away_team}")
        else:
            print("❌ Not found in database")

        print(f"\n2. Searching for wrong ID: {wrong_id}")
        match = session.query(MatchDB).filter(MatchDB.id == wrong_id).first()
        if match:
            print(f"✅ Found: {match.home_team} vs {match.away_team}")
        else:
            print("❌ Not found in database")

        # Check if we have team_id fields populated
        print(f"\n=== Checking team ID structure ===")
        sample_matches = session.query(MatchDB).limit(3).all()
        for match in sample_matches:
            print(f"Match: {match.home_team} vs {match.away_team}")
            print(f"  home_team_id: {match.home_team_id} (type: {type(match.home_team_id)})")
            print(f"  away_team_id: {match.away_team_id} (type: {type(match.away_team_id)})")

    finally:
        session.close()

if __name__ == "__main__":
    debug_database_matches()
