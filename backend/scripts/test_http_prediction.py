#!/usr/bin/env python3
"""Test prediction via HTTP API endpoint."""

import requests
import time
import sys

def main():
    """Test prediction endpoint with match that has historical data."""
    
    # Match ID that we know exists from previous debugging
    test_match_id = "f5182fe2-baee-442e-8d7b-f8fafc6660b0"  # Boca Juniors vs Rosario Central
    
    print(f"=== TESTING HTTP PREDICTION ENDPOINT ===")
    print(f"Match ID: {test_match_id}")
    
    # Test different possible ports
    ports = [8000, 8002, 8003]
    
    for port in ports:
        url = f"http://localhost:{port}/api/v1/matches/{test_match_id}/prediction"
        print(f"Trying port {port}: {url}")
        
        try:
            response = requests.get(url, timeout=5)
            print(f"  Port {port}: Status {response.status_code}")
            
            if response.status_code != 404:
                print(f"  Success on port {port}!")
                # Process the response
                process_response(response, port)
                return
                
        except requests.exceptions.ConnectionError:
            print(f"  Port {port}: Connection refused")
        except requests.exceptions.Timeout:
            print(f"  Port {port}: Timeout")
    
    print("No working ports found")

def process_response(response, port):
    """Process a successful response."""
    print(f"\n=== USING PORT {port} ===")
    
    if response.status_code == 200:
        data = response.json()
        print("\n*** PREDICTION SUCCESS ***")
        print(f"Home win probability: {data.get('home_win_probability')}")
        print(f"Draw probability: {data.get('draw_probability')}")
        print(f"Away win probability: {data.get('away_win_probability')}")
        print(f"Expected home goals: {data.get('home_xg')}")
        print(f"Expected away goals: {data.get('away_xg')}")
        print(f"BTTS probability: {data.get('btts_probability')}")
        
        if 'mensione_pick' in data and data['mensione_pick']:
            pick = data['mensione_pick']
            print(f"\nMensione Pick:")
            print(f"  Market: {pick.get('market_type')}")
            print(f"  Selection: {pick.get('selection')}")
            print(f"  Confidence: {pick.get('confidence')}")
            
    elif response.status_code == 400:
        print("\n*** INSUFFICIENT DATA ERROR ***")
        print(f"Error: {response.text}")
        print("This confirms the 'insufficient data' error is working as designed")
        
    elif response.status_code == 404:
        print("\n*** MATCH NOT FOUND ***")
        print(f"Error: {response.text}")
        
    else:
        print(f"\n*** UNEXPECTED ERROR ***")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")

if __name__ == "__main__":
    main()