#!/usr/bin/env python3
"""Test team names after restart."""

import requests
import json

def main():
    """Test team name resolution after backend restart."""
    
    port = 8004
    print(f"=== TESTING TEAM NAMES ON PORT {port} ===")
    
    try:
        url = f"http://127.0.0.1:{port}/api/v1/matches?limit=3"
        print(f"Testing: {url}")
        
        response = requests.get(url, timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            matches = data.get('matches', [])
            
            print(f"Matches returned: {len(matches)}")
            
            for i, match in enumerate(matches[:3]):
                print(f"\n--- Match {i+1} ---")
                print(f"ID: {match.get('id')}")
                print(f"Status: {match.get('status')}")
                print(f"Date: {match.get('scheduled_at')}")
                
                # Check team fields
                home_team = match.get('home_team')
                away_team = match.get('away_team')
                
                print(f"Home team field: {home_team}")
                print(f"Away team field: {away_team}")
                
                if home_team and isinstance(home_team, dict):
                    home_name = home_team.get('name', 'NO_NAME')
                    print(f"Home team name: '{home_name}'")
                else:
                    print(f"Home team is null/missing")
                    
                if away_team and isinstance(away_team, dict):
                    away_name = away_team.get('name', 'NO_NAME')
                    print(f"Away team name: '{away_name}'")
                else:
                    print(f"Away team is null/missing")
                    
                # Also check legacy fields for comparison
                print(f"Home team ID: {match.get('home_team_id')}")
                print(f"Away team ID: {match.get('away_team_id')}")
                
                # Try to get team names
                home_team_name = match.get('home_team_name', 'FIELD_NOT_FOUND')
                away_team_name = match.get('away_team_name', 'FIELD_NOT_FOUND') 
                print(f"Legacy home_team_name: {home_team_name}")
                print(f"Legacy away_team_name: {away_team_name}")
                
        else:
            print(f"Error {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()