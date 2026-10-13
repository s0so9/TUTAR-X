#!/usr/bin/env python3
"""
Test specific match endpoint with canonical ID
"""
import requests

def test_match():
    print("Testing specific match endpoint...")

    # Test with the known canonical ID for Fluminense vs Coritiba
    correct_id = "aa4c9808-cb36-486e-bd41-003cc28b8543"

    print(f"Testing match ID: {correct_id}")
    try:
        response = requests.get(f'http://localhost:8001/api/v1/matches/{correct_id}')
        print(f'Status: {response.status_code}')
        if response.status_code == 200:
            data = response.json()
            match = data.get('match', {})
            print(f'✅ Match found!')
            print(f'ID: {match.get("id")}')
            print(f'Status: {match.get("status")}')
            print(f'Date: {match.get("scheduled_at")}')
            print(f'Home team ID: {match.get("home_team_id")}')
            print(f'Away team ID: {match.get("away_team_id")}')
        else:
            print(f'❌ Error: {response.text}')
    except Exception as e:
        print(f'Request failed: {e}')

if __name__ == "__main__":
    test_match()
