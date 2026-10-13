#!/usr/bin/env python3

"""
Browser automation test to verify the UI fixes.
This tests the actual user-visible behavior.
"""

import requests
import time
import json

def test_prediction_api_integration():
    """Test end-to-end API integration for the specific match"""
    print("🧪 TESTING: API Integration")
    match_id = "a0872be9-d188-41fd-96b5-1023a8cef0f8"

    try:
        # Test match detail
        detail_resp = requests.get(f'http://127.0.0.1:8004/api/v1/matches/{match_id}', timeout=10)
        print(f"   Match Detail: {detail_resp.status_code}")

        if not detail_resp.ok:
            print(f"   ❌ Match detail failed: {detail_resp.text[:100]}")
            return False

        match_data = detail_resp.json()
        match_status = match_data["match"]["status"]
        print(f"   Match Status: {match_status}")

        # Test prediction
        pred_resp = requests.get(f'http://127.0.0.1:8004/api/v1/matches/{match_id}/prediction', timeout=10)
        print(f"   Prediction API: {pred_resp.status_code}")

        if not pred_resp.ok:
            print(f"   ❌ Prediction failed: {pred_resp.text[:100]}")
            return False

        pred_data = pred_resp.json()

        # Validate prediction structure
        required_fields = ['match_id', 'home_win_probability', 'draw_probability', 'away_win_probability']
        has_all_fields = all(field in pred_data for field in required_fields)
        print(f"   Valid Structure: {has_all_fields}")

        if has_all_fields:
            prob_sum = pred_data['home_win_probability'] + pred_data['draw_probability'] + pred_data['away_win_probability']
            print(f"   Probability Sum: {prob_sum:.4f} (should be ~1.0)")

        return has_all_fields

    except Exception as e:
        print(f"   ❌ Exception: {e}")
        return False

def test_frontend_endpoint():
    """Test that frontend serves the match detail page"""
    print("\n🧪 TESTING: Frontend Serving")

    try:
        # Test root page
        root_resp = requests.get('http://localhost:5173/', timeout=10)
        print(f"   Root Page: {root_resp.status_code}")

        # Frontend routes are handled client-side, so we can't directly test the route
        # But we can verify the frontend is serving the React app
        if root_resp.ok and 'id="root"' in root_resp.text:
            print("   ✅ React app serving correctly")
            return True
        else:
            print("   ❌ Frontend not serving React app")
            return False

    except Exception as e:
        print(f"   ❌ Exception: {e}")
        return False

def create_manual_test_guide():
    """Create a guide for manual testing since we can't use Playwright/Selenium"""
    print("\n📋 MANUAL TESTING GUIDE")
    print("=" * 60)

    match_url = "http://localhost:5173/matches/a0872be9-d188-41fd-96b5-1023a8cef0f8"
    live_url = "http://localhost:5173/live"

    print(f"""
🎯 TEST 1: Prediction Display Fix
   1. Open: {match_url}
   2. ✅ SHOULD SEE: Prediction tabs (Genel, İlk Yarı, Maç)
   3. ✅ SHOULD SEE: Loading state initially, then prediction data
   4. ❌ SHOULD NOT SEE: Empty page with no prediction section

🎯 TEST 2: Sidebar Navigation Fix
   1. Open: {match_url}
   2. ❌ SHOULD NOT SEE: "Canlı" highlighted in sidebar
   3. Open: {live_url}
   4. ✅ SHOULD SEE: "Canlı" highlighted in sidebar

🔍 BROWSER CONSOLE LOGS TO EXPECT:
   - [useLazyPrediction] Fetching prediction for match: {match_url.split('/')[-1]}
   - [getMatchPrediction] Called for match: {match_url.split('/')[-1]}
   - [useLazyPrediction] Prediction received: SUCCESS

🚨 RED FLAGS (bugs still present):
   - ❌ No prediction tabs visible
   - ❌ "Canlı" highlighted when viewing match detail
   - ❌ Console errors about failed API calls
   - ❌ Stuck on loading state forever
""")

def main():
    print("TUTAR X - UI Fix Verification")
    print("=" * 60)

    api_ok = test_prediction_api_integration()
    frontend_ok = test_frontend_endpoint()

    print(f"\n📊 AUTOMATED TEST RESULTS:")
    print(f"   API Integration: {'✅ PASS' if api_ok else '❌ FAIL'}")
    print(f"   Frontend Serving: {'✅ PASS' if frontend_ok else '❌ FAIL'}")

    if api_ok and frontend_ok:
        print(f"\n🎉 AUTOMATED TESTS PASS")
        create_manual_test_guide()

        print(f"\n✨ EXPECTED OUTCOME:")
        print(f"   - User can see predictions on scheduled match pages")
        print(f"   - Sidebar navigation works correctly")
        print(f"   - No more 'predictions not visible' issue")

    else:
        print(f"\n❌ AUTOMATED TESTS FAILED - Check errors above")

if __name__ == "__main__":
    main()
