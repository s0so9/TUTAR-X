#!/usr/bin/env python3

import requests
import json

def test_match_uuid(match_id):
    """Test both match detail and prediction endpoints for a specific UUID"""
    print(f"Testing match ID: {match_id}")
    print("="*50)

    try:
        # Test match detail
        detail_url = f'http://127.0.0.1:8004/api/v1/matches/{match_id}'
        print(f"GET {detail_url}")
        detail_resp = requests.get(detail_url, timeout=10)
        print(f"Match detail status: {detail_resp.status_code}")

        if detail_resp.ok:
            detail_data = detail_resp.json()
            match = detail_data["match"]
            print(f"Match status: {match['status']}")
            home_team = match.get("home_team")
            away_team = match.get("away_team")
            print(f"Home team: {home_team['name'] if home_team else 'None'}")
            print(f"Away team: {away_team['name'] if away_team else 'None'}")
            print(f"Scheduled: {match.get('scheduled_at', 'N/A')}")
        else:
            print(f"Match detail error: {detail_resp.text[:200]}")
            return False

        print()

        # Test prediction
        pred_url = f'http://127.0.0.1:8004/api/v1/matches/{match_id}/prediction'
        print(f"GET {pred_url}")
        pred_resp = requests.get(pred_url, timeout=10)
        print(f"Prediction status: {pred_resp.status_code}")

        if pred_resp.ok:
            pred_data = pred_resp.json()
            has_prediction = 'prediction' in pred_data and pred_data['prediction'] is not None
            print(f"Has prediction: {has_prediction}")
            if has_prediction:
                pred = pred_data['prediction']
                print(f"Model version: {pred.get('model_version', 'Unknown')}")
                print(f"Home win probability: {pred.get('home_win_probability', 'N/A')}")
                print(f"Draw probability: {pred.get('draw_probability', 'N/A')}")
                print(f"Away win probability: {pred.get('away_win_probability', 'N/A')}")
            else:
                print("Prediction response:", json.dumps(pred_data, indent=2)[:300])
        else:
            print(f"Prediction error: {pred_resp.text[:200]}")
            return False

        return True

    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    # Test the specific UUID from user
    test_match_uuid("a0872be9-d188-41fd-96b5-1023a8cef0f8")

    print("\n" + "="*50)
    print("Testing d13431f9 UUID as well:")
    test_match_uuid("d13431f9-0ce0-46dd-a95b-76d6a9f71be8")
