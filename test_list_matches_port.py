#!/usr/bin/env python3
"""
Test list matches on port 8001
"""
import requests

def test_matches():
    print("Testing list-matches on port 8001...")
    try:
        response = requests.get('http://localhost:8001/api/v1/matches')
        print(f'Status: {response.status_code}')
        if response.status_code == 200:
            data = response.json()
            print(f'Success: Found {len(data.get("matches", []))} matches')
            if data.get('matches'):
                match = data['matches'][0]
                print(f'First match ID: {match.get("id")}')
                home_team = match.get("home_team")
                away_team = match.get("away_team")
                if home_team and away_team:
                    print(f'First match: {home_team.get("name")} vs {away_team.get("name")}')
                else:
                    print('First match: No team names (expected for debugging)')
        else:
            print(f'Error response: {response.text}')
    except Exception as e:
        print(f'Request failed: {e}')

if __name__ == "__main__":
    test_matches()