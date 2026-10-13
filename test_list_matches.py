#!/usr/bin/env python3
"""
Test list matches endpoint for datetime issues
"""
import requests
import json

def test_list_matches():
    print("Testing list-matches endpoint...")
    try:
        response = requests.get('http://localhost:8000/api/v1/matches')
        print(f'Status: {response.status_code}')
        if response.status_code == 200:
            data = response.json()
            print(f'Success: Found {len(data.get("matches", []))} matches')
            if data.get('matches'):
                match = data['matches'][0]
                print(f'First match ID: {match.get("id")}')
                home_team = match.get("home_team", {})
                away_team = match.get("away_team", {})
                print(f'First match: {home_team.get("name", "Unknown")} vs {away_team.get("name", "Unknown")}')
                print(f'Date: {match.get("scheduled_at")}')
                print(f'Status: {match.get("status")}')

                # Look for Fluminense match
                for i, m in enumerate(data.get('matches', [])[:20]):  # Check first 20
                    home = m.get("home_team", {}).get("name", "")
                    away = m.get("away_team", {}).get("name", "")
                    if "Fluminense" in home or "Fluminense" in away:
                        print(f'Found Fluminense match at position {i}: {home} vs {away}')
                        print(f'  ID: {m.get("id")}')
                        print(f'  Date: {m.get("scheduled_at")}')
                        print(f'  Status: {m.get("status")}')
                        break
        else:
            print(f'Error response: {response.text[:500]}')
    except Exception as e:
        print(f'Request failed: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_list_matches()
