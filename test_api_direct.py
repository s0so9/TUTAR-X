#!/usr/bin/env python3
"""
Test API directly
"""

import requests

def test_api():
    """Test API endpoints"""

    print("=== Testing matches list API ===")
    response = requests.get("http://localhost:8000/api/v1/matches")
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"Matches count: {len(data.get('matches', []))}")
        if data.get('matches'):
            first_match = data['matches'][0]
            print(f"First match: {first_match.get('home_team', {}).get('name')} vs {first_match.get('away_team', {}).get('name')}")
            print(f"First match ID: {first_match.get('id')}")
    else:
        print(f"Error: {response.text}")

    # Test specific match
    print(f"\n=== Testing specific match API ===")
    correct_id = "aa4c9808-cb36-486e-bd41-003cc28b8543"
    response = requests.get(f"http://localhost:8000/api/v1/matches/{correct_id}")
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        match = data.get('match', {})
        print(f"✅ Match found: {match.get('home_team', {}).get('name')} vs {match.get('away_team', {}).get('name')}")
    else:
        print(f"❌ Error: {response.text}")

if __name__ == "__main__":
    test_api()
