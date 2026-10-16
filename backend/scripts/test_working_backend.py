#!/usr/bin/env python3
"""Test working backend on port 8004 to verify team names and find predictable matches."""

import requests
import json

def main():
    """Test port 8004 backend comprehensively."""
    
    port = 8004
    print(f"=== COMPREHENSIVE TEST OF PORT {port} ===")
    
    # Test matches with more details
    try:
        url = f"http://127.0.0.1:{port}/api/v1/matches?limit=10"
        print(f"Testing: {url}")
        
        response = requests.get(url, timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            matches = data.get('matches', [])
            
            print(f"Total matches available: {len(matches)}")
            
            # Check team name resolution
            print("\n--- TEAM NAME ANALYSIS ---")
            for i, match in enumerate(matches[:5]):
                print(f"Match {i+1}: {match.get('id')}")
                print(f"  Home: {match.get('home_team_name', 'MISSING')}")
                print(f"  Away: {match.get('away_team_name', 'MISSING')}")
                print(f"  Status: {match.get('status')}")
                print(f"  Date: {match.get('scheduled_at')}")
                print()
            
            # Find different status matches
            finished_matches = [m for m in matches if m.get('status') == 'FINISHED']
            scheduled_matches = [m for m in matches if m.get('status') == 'SCHEDULED']
            
            print(f"FINISHED matches: {len(finished_matches)}")
            print(f"SCHEDULED matches: {len(scheduled_matches)}")
            
            # Test prediction with different matches
            test_matches = []
            if scheduled_matches:
                test_matches.append(("SCHEDULED", scheduled_matches[0]))
            if finished_matches:
                test_matches.append(("FINISHED", finished_matches[0]))
                
            for match_type, match in test_matches:
                print(f"\n--- TESTING {match_type} MATCH PREDICTION ---")
                test_prediction(port, match.get('id'), match_type)
                
        else:
            print(f"Error: {response.text}")
            
    except Exception as e:
        print(f"Error: {str(e)}")

def test_prediction(port, match_id, match_type):
    """Test prediction with timeout handling."""
    print(f"Testing prediction for {match_type} match: {match_id}")
    
    try:
        url = f"http://127.0.0.1:{port}/api/v1/matches/{match_id}/prediction"
        
        # Use longer timeout for predictions
        response = requests.get(url, timeout=30)
        print(f"Prediction status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("*** PREDICTION SUCCESS ***")
            print(f"Home win: {data.get('home_win_probability')}")
            print(f"Draw: {data.get('draw_probability')}")  
            print(f"Away win: {data.get('away_win_probability')}")
            
            if 'mensione_pick' in data:
                pick = data['mensione_pick']
                if pick:
                    print(f"Mensione pick: {pick.get('market_type')} - {pick.get('selection')}")
                    
        elif response.status_code == 400:
            print("*** INSUFFICIENT DATA ***")
            error_text = response.text
            if "insufficient data" in error_text.lower():
                print("This is expected for matches without historical data")
            print(f"Error: {error_text}")
            
        elif response.status_code == 404:
            print("*** MATCH NOT FOUND ***")
            print(f"Error: {response.text}")
            
        else:
            print(f"*** ERROR {response.status_code} ***")
            print(f"Response: {response.text}")
            
    except requests.exceptions.Timeout:
        print("*** TIMEOUT (30s) ***")
        print("Prediction took longer than 30 seconds")
        
    except Exception as e:
        print(f"Prediction failed: {str(e)}")

if __name__ == "__main__":
    main()