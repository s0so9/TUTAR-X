#!/usr/bin/env python3
"""Test both backend ports to identify which is which."""

import requests
import json

def test_port(port):
    """Test a port to see what backend is running."""
    print(f"\n=== TESTING PORT {port} ===")
    
    # Test health endpoint
    try:
        health_url = f"http://127.0.0.1:{port}/health"
        print(f"Testing: {health_url}")
        
        response = requests.get(health_url, timeout=5)
        print(f"Health status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Health response: {json.dumps(data, indent=2)}")
        else:
            print(f"Health error: {response.text}")
            
    except Exception as e:
        print(f"Health endpoint failed: {str(e)}")
    
    # Test matches endpoint
    try:
        matches_url = f"http://127.0.0.1:{port}/api/v1/matches?limit=1"
        print(f"\nTesting: {matches_url}")
        
        response = requests.get(matches_url, timeout=10)
        print(f"Matches status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            matches = data.get('matches', [])
            
            if matches:
                match = matches[0]
                print(f"Sample match ID: {match.get('id')}")
                print(f"Home team: {match.get('home_team_name', 'NOT_SET')}")
                print(f"Away team: {match.get('away_team_name', 'NOT_SET')}")
                print(f"Status: {match.get('status')}")
                print(f"Scheduled: {match.get('scheduled_at')}")
                
                # Return match ID for prediction testing
                return match.get('id')
            else:
                print("No matches returned")
                
        else:
            print(f"Matches error: {response.text}")
            
    except Exception as e:
        print(f"Matches endpoint failed: {str(e)}")
    
    return None

def test_prediction(port, match_id):
    """Test prediction endpoint."""
    if not match_id:
        print(f"No match ID to test prediction on port {port}")
        return
        
    print(f"\n--- Testing prediction for {match_id} on port {port} ---")
    
    try:
        pred_url = f"http://127.0.0.1:{port}/api/v1/matches/{match_id}/prediction"
        response = requests.get(pred_url, timeout=15)
        
        print(f"Prediction status: {response.status_code}")
        
        if response.status_code == 200:
            print("*** PREDICTION SUCCESS ***")
            data = response.json()
            print(f"Home win: {data.get('home_win_probability')}")
            
        elif response.status_code == 400:
            print("*** INSUFFICIENT DATA (Expected for most matches) ***")
            
        elif response.status_code == 404:
            print("*** MATCH NOT FOUND ***")
            
        else:
            print(f"*** ERROR {response.status_code} ***")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"Prediction test failed: {str(e)}")

def main():
    """Test both ports to identify configurations."""
    
    print("=== BACKEND PORT IDENTIFICATION ===")
    
    # Test both ports
    ports_to_test = [8000, 8004]
    
    for port in ports_to_test:
        match_id = test_port(port)
        
        # Test prediction if we got a match
        if match_id:
            test_prediction(port, match_id)

if __name__ == "__main__":
    main()