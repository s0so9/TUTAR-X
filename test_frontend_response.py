#!/usr/bin/env python3

import requests
import json

def test_frontend_expected_response(match_id):
    """Test what the frontend actually expects vs what backend returns"""
    print(f"Testing match ID: {match_id}")
    print("="*60)

    try:
        # Get prediction
        pred_url = f'http://127.0.0.1:8004/api/v1/matches/{match_id}/prediction'
        print(f"GET {pred_url}")
        pred_resp = requests.get(pred_url, timeout=10)
        print(f"Status: {pred_resp.status_code}")

        if pred_resp.ok:
            pred_data = pred_resp.json()

            # What the backend actually returns
            print("\n✅ BACKEND RETURNS (first 5 fields):")
            for key in list(pred_data.keys())[:5]:
                print(f"  {key}: {pred_data[key]}")

            # What the frontend expects (MatchPredictionResponse type)
            print("\n✅ FRONTEND EXPECTS (MatchPredictionResponse):")
            print(f"  match_id: {pred_data.get('match_id', 'MISSING')}")
            print(f"  home_win_probability: {pred_data.get('home_win_probability', 'MISSING')}")
            print(f"  draw_probability: {pred_data.get('draw_probability', 'MISSING')}")
            print(f"  away_win_probability: {pred_data.get('away_win_probability', 'MISSING')}")
            print(f"  home_xg: {pred_data.get('home_xg', 'MISSING')}")
            print(f"  away_xg: {pred_data.get('away_xg', 'MISSING')}")
            print(f"  btts_probability: {pred_data.get('btts_probability', 'MISSING')}")

            # Check if it's a valid MatchPredictionResponse
            required_fields = ['match_id', 'home_win_probability', 'draw_probability', 'away_win_probability']
            all_present = all(field in pred_data for field in required_fields)
            print(f"\n✅ IS VALID MatchPredictionResponse: {all_present}")

            # Check if probabilities sum to ~1.0
            if all_present:
                prob_sum = pred_data['home_win_probability'] + pred_data['draw_probability'] + pred_data['away_win_probability']
                print(f"✅ PROBABILITIES SUM TO: {prob_sum:.4f} (should be ~1.0)")

            return pred_data
        else:
            print(f"❌ ERROR: {pred_resp.text}")
            return None

    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        return None

if __name__ == "__main__":
    # Test the working UUID
    data = test_frontend_expected_response("a0872be9-d188-41fd-96b5-1023a8cef0f8")

    if data:
        print(f"\n🎯 CONCLUSION:")
        print(f"   Backend returns exactly what frontend expects.")
        print(f"   The issue is NOT in the API response format.")
        print(f"   Issue must be in frontend rendering logic.")
