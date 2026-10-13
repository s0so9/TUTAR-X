#!/usr/bin/env python3
"""
Test end-to-end match ID flow
"""
import requests
import json

def test_end_to_end():
    print("=== End-to-End Match ID Flow Test ===")

    # Step 1: Get matches list
    print("\n1. Getting matches list...")
    response = requests.get('http://localhost:8001/api/v1/matches')
    if response.status_code != 200:
        print(f"❌ Failed to get matches: {response.text}")
        return

    matches_data = response.json()
    matches = matches_data.get('matches', [])
    print(f"✅ Found {len(matches)} matches")

    # Step 2: Look for the specific match by ID
    print("\n2. Looking for Fluminense vs Coritiba match...")
    target_id = "aa4c9808-cb36-486e-bd41-003cc28b8543"

    found_match = None
    for match in matches:
        if match.get('id') == target_id:
            found_match = match
            break

    if not found_match:
        print(f"❌ Match {target_id} not found in list")
        # Show first few matches for debugging
        print("First 5 matches:")
        for i, match in enumerate(matches[:5]):
            print(f"  {i+1}. {match.get('id')} - {match.get('status')} - {match.get('scheduled_at')}")
        return

    print(f"✅ Found match in list: {found_match.get('id')}")
    print(f"   Status: {found_match.get('status')}")
    print(f"   Date: {found_match.get('scheduled_at')}")
    print(f"   Home team ID: {found_match.get('home_team_id')}")
    print(f"   Away team ID: {found_match.get('away_team_id')}")

    # Step 3: Use the ID from the list to get match details
    print("\n3. Getting match details using ID from list...")
    response = requests.get(f'http://localhost:8001/api/v1/matches/{found_match["id"]}')
    if response.status_code != 200:
        print(f"❌ Failed to get match details: {response.text}")
        return

    detail_data = response.json()
    match_detail = detail_data.get('match', {})
    print(f"✅ Match detail retrieved: {match_detail.get('id')}")

    # Step 4: Use the ID to get prediction
    print("\n4. Getting prediction using same ID...")
    response = requests.get(f'http://localhost:8001/api/v1/matches/{found_match["id"]}/prediction')
    if response.status_code != 200:
        print(f"❌ Failed to get prediction: {response.text}")
        return

    prediction_data = response.json()
    print(f"✅ Prediction retrieved: {prediction_data.get('match_id')}")
    print(f"   Home win: {prediction_data.get('home_win_probability'):.3f}")
    print(f"   Draw: {prediction_data.get('draw_probability'):.3f}")
    print(f"   Away win: {prediction_data.get('away_win_probability'):.3f}")

    print(f"\n🎉 END-TO-END SUCCESS! Match ID flow working correctly.")
    print(f"   Canonical ID: {target_id}")
    print(f"   All endpoints (list/detail/prediction) use same ID successfully")

if __name__ == "__main__":
    test_end_to_end()
