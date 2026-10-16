#!/usr/bin/env python3
"""Test basic endpoints to verify backend is working."""

import requests

def main():
    """Test health and matches endpoints."""
    
    port = 8004
    print(f"=== TESTING BASIC ENDPOINTS ON PORT {port} ===")
    
    # Test health
    try:
        health_url = f"http://127.0.0.1:{port}/health"
        print(f"Testing: {health_url}")
        
        response = requests.get(health_url, timeout=5)
        print(f"Health status: {response.status_code}")
        
        if response.status_code == 200:
            print(f"✅ Health OK")
        else:
            print(f"❌ Health failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Health endpoint failed: {str(e)}")
        return False
    
    # Test matches
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
                print(f"✅ Matches OK - Sample match: {match.get('id')}")
                print(f"  Home team: {match.get('home_team', {}).get('name', 'Missing')}")
                print(f"  Away team: {match.get('away_team', {}).get('name', 'Missing')}")
                return True
            else:
                print(f"❌ No matches returned")
                return False
        else:
            print(f"❌ Matches failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Matches endpoint failed: {str(e)}")
        return False

if __name__ == "__main__":
    success = main()
    if not success:
        print("\n❌ Basic endpoints failed")
    else:
        print("\n✅ All basic endpoints working")