#!/usr/bin/env python3
"""
Test prediction endpoint with correct canonical ID
"""

import requests
import json

# Test with correct canonical ID
correct_id = "aa4c9808-cb36-486e-bd41-003cc28b8543"
wrong_id = "1f05edd0-b0a5-4453-b70c-1892247bea54"

base_url = "http://localhost:8000"

print("=== Testing Prediction Endpoint ===")

# Test 1: Correct ID
print(f"\n1. Testing with CORRECT ID: {correct_id}")
try:
    response = requests.get(f"{base_url}/api/v1/matches/{correct_id}/prediction")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print("✅ Prediction loaded successfully!")
        print(f"Match: {data.get('match_info', {}).get('home_team')} vs {data.get('match_info', {}).get('away_team')}")
        if 'prediction' in data:
            print(f"Prediction probabilities: {data['prediction'].get('probabilities', 'N/A')}")
        else:
            print("❌ No prediction data in response")
    else:
        print(f"❌ Error: {response.text}")
except Exception as e:
    print(f"❌ Request failed: {e}")

# Test 2: Wrong ID (what frontend uses)
print(f"\n2. Testing with WRONG ID (frontend uses): {wrong_id}")
try:
    response = requests.get(f"{base_url}/api/v1/matches/{wrong_id}/prediction")
    print(f"Status: {response.status_code}")
    if response.status_code != 200:
        print(f"❌ Expected error: {response.text}")
except Exception as e:
    print(f"❌ Request failed: {e}")

# Test 3: Check match details endpoint
print(f"\n3. Testing match details endpoint with correct ID:")
try:
    response = requests.get(f"{base_url}/api/v1/matches/{correct_id}")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Match details: {data.get('home_team')} vs {data.get('away_team')}")
        print(f"Match status: {data.get('status')}")
        print(f"Match date: {data.get('match_date')}")
    else:
        print(f"❌ Error: {response.text}")
except Exception as e:
    print(f"❌ Request failed: {e}")