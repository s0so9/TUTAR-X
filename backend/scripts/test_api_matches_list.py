#!/usr/bin/env python3
"""Test API matches list to find available match IDs."""

import requests

def main():
    """Test matches list endpoint to find available matches."""
    
    print("=== TESTING MATCHES LIST API ===")
    
    url = "http://localhost:8000/api/v1/matches"
    print(f"URL: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        print(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            matches = data.get('matches', [])
            
            print(f"\nTotal matches available: {len(matches)}")
            
            if matches:
                print("\nFirst 5 matches:")
                for i, match in enumerate(matches[:5]):
                    print(f"  {i+1}. ID: {match.get('id')}")
                    print(f"     Date: {match.get('scheduled_at')}")
                    print(f"     Status: {match.get('status')}")
                    print(f"     Home: {match.get('home_team_name', 'Unknown')}")
                    print(f"     Away: {match.get('away_team_name', 'Unknown')}")
                    print()
                
                # Test prediction with first scheduled match
                test_match = None
                for match in matches:
                    if match.get('status') == 'SCHEDULED':
                        test_match = match
                        break
                
                if test_match:
                    print(f"Testing prediction with SCHEDULED match: {test_match['id']}")
                    test_prediction(test_match['id'])
                else:
                    print("No SCHEDULED matches found for prediction testing")
            else:
                print("No matches returned")
        else:
            print(f"Error: {response.text}")
            
    except Exception as e:
        print(f"Error: {str(e)}")

def test_prediction(match_id):
    """Test prediction endpoint with a match ID."""
    print(f"\n--- Testing prediction for {match_id} ---")
    
    url = f"http://localhost:8000/api/v1/matches/{match_id}/prediction"
    
    try:
        response = requests.get(url, timeout=15)
        print(f"Prediction status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("*** PREDICTION SUCCESS ***")
            print(f"Home win: {data.get('home_win_probability', 'N/A')}")
            print(f"Draw: {data.get('draw_probability', 'N/A')}")
            print(f"Away win: {data.get('away_win_probability', 'N/A')}")
            
        elif response.status_code == 400:
            print("*** INSUFFICIENT DATA (Expected) ***")
            print(f"Error: {response.text}")
            
        else:
            print(f"*** ERROR ***")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"Prediction error: {str(e)}")

if __name__ == "__main__":
    main()