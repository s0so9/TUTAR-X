#!/usr/bin/env python3
"""
Test prediction endpoint with canonical ID
"""
import requests

def test_prediction():
    print("Testing prediction endpoint...")

    # Test with the known canonical ID for Fluminense vs Coritiba
    correct_id = "aa4c9808-cb36-486e-bd41-003cc28b8543"

    print(f"Testing prediction for match ID: {correct_id}")
    try:
        response = requests.get(f'http://localhost:8001/api/v1/matches/{correct_id}/prediction')
        print(f'Status: {response.status_code}')
        if response.status_code == 200:
            data = response.json()
            print(f'✅ Prediction found!')
            print(f'Match ID: {data.get("match_id")}')
            print(f'Home win probability: {data.get("home_win_probability")}')
            print(f'Draw probability: {data.get("draw_probability")}')
            print(f'Away win probability: {data.get("away_win_probability")}')
            print(f'Is development data: {data.get("is_development_data")}')
        else:
            print(f'❌ Error: {response.text}')
    except Exception as e:
        print(f'Request failed: {e}')

if __name__ == "__main__":
    test_prediction()
