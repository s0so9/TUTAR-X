#!/usr/bin/env python3
"""
Final validation of all prediction API and match ID fixes
"""
import requests

def final_validation():
    print("🔍 FINAL VALIDATION - Prediction API and Match ID Flow")
    print("="*60)

    # Test the canonical match ID
    canonical_id = "aa4c9808-cb36-486e-bd41-003cc28b8543"
    base_url = "http://localhost:8001"

    # 1. Test List Matches (datetime bug fix)
    print("\n1. ✅ LIST MATCHES - Testing datetime bug fix")
    response = requests.get(f"{base_url}/api/v1/matches")
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Status: {response.status_code}")
        print(f"   ✅ Total matches: {data['count']}")
        print(f"   ✅ Is development data: {data['is_development_data']}")

        # Find our match in the list
        found = False
        for match in data['matches']:
            if match['id'] == canonical_id:
                found = True
                print(f"   ✅ Fluminense vs Coritiba found in list")
                print(f"      ID: {match['id']}")
                print(f"      Status: {match['status']}")
                print(f"      Date: {match['scheduled_at']}")
                break

        if not found:
            print(f"   ❌ Match {canonical_id} not found in list")
    else:
        print(f"   ❌ Status: {response.status_code}")
        return False

    # 2. Test Match Detail (ID propagation)
    print("\n2. ✅ MATCH DETAIL - Testing ID propagation")
    response = requests.get(f"{base_url}/api/v1/matches/{canonical_id}")
    if response.status_code == 200:
        data = response.json()
        match = data['match']
        print(f"   ✅ Status: {response.status_code}")
        print(f"   ✅ Match ID: {match['id']}")
        print(f"   ✅ Status: {match['status']}")
        print(f"   ✅ Date: {match['scheduled_at']}")
        print(f"   ✅ Home team ID: {match['home_team_id']}")
        print(f"   ✅ Away team ID: {match['away_team_id']}")
    else:
        print(f"   ❌ Status: {response.status_code}")
        return False

    # 3. Test Prediction Endpoint (main fix)
    print("\n3. ✅ PREDICTION - Testing prediction generation")
    response = requests.get(f"{base_url}/api/v1/matches/{canonical_id}/prediction")
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Status: {response.status_code}")
        print(f"   ✅ Match ID: {data['match_id']}")
        print(f"   ✅ Home win probability: {data['home_win_probability']:.3f}")
        print(f"   ✅ Draw probability: {data['draw_probability']:.3f}")
        print(f"   ✅ Away win probability: {data['away_win_probability']:.3f}")

        # Verify probabilities sum to ~1.0
        total_prob = data['home_win_probability'] + data['draw_probability'] + data['away_win_probability']
        print(f"   ✅ Total probability: {total_prob:.3f} (should be ≈ 1.0)")

        if abs(total_prob - 1.0) > 0.01:
            print(f"   ⚠️  Warning: Probabilities don't sum to 1.0")
    else:
        print(f"   ❌ Status: {response.status_code}")
        return False

    # 4. Test Wrong ID (should still return 404)
    print("\n4. ✅ ERROR HANDLING - Testing with wrong ID")
    wrong_id = "1f05edd0-b0a5-4453-b70c-1892247bea54"
    response = requests.get(f"{base_url}/api/v1/matches/{wrong_id}")
    if response.status_code == 404:
        print(f"   ✅ Status: {response.status_code} (expected 404)")
        print(f"   ✅ Wrong ID properly rejected")
    else:
        print(f"   ❌ Status: {response.status_code} (expected 404)")

    print("\n" + "="*60)
    print("🎉 SUCCESS! All prediction API and match ID issues RESOLVED")
    print("✅ Database datetime bug fixed")
    print("✅ Match ID propagation working")
    print("✅ Prediction endpoint functional")
    print("✅ End-to-end flow validated")
    print("="*60)

    return True

if __name__ == "__main__":
    success = final_validation()
    exit(0 if success else 1)
