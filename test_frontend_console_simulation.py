#!/usr/bin/env python3

"""
Simulate what should happen in the browser console when the frontend calls the prediction API
"""

import requests
import json

def simulate_frontend_prediction_call():
    """Simulate the exact API call the frontend makes"""
    print("🔄 SIMULATING: Frontend prediction API call")
    print("=" * 50)

    match_id = "a0872be9-d188-41fd-96b5-1023a8cef0f8"
    api_url = f'http://127.0.0.1:8004/api/v1/matches/{match_id}/prediction'

    print(f"[getMatchPrediction] Called for match: {match_id}")
    print(f"API URL: {api_url}")

    try:
        import time
        start_time = time.time()

        response = requests.get(api_url, timeout=30)  # Match frontend timeout
        duration = (time.time() - start_time) * 1000  # Convert to ms

        print(f"[getMatchPrediction] Response received in {duration:.0f}ms")
        print(f"Status: {response.status_code}")

        if response.ok:
            data = response.json()
            print(f"[useLazyPrediction] Prediction received: SUCCESS")

            # Simulate what the frontend expects to find
            print(f"\n✅ Frontend will receive:")
            print(f"   match_id: {data.get('match_id')}")
            print(f"   home_win_probability: {data.get('home_win_probability')}")
            print(f"   draw_probability: {data.get('draw_probability')}")
            print(f"   away_win_probability: {data.get('away_win_probability')}")
            print(f"   home_xg: {data.get('home_xg')}")
            print(f"   away_xg: {data.get('away_xg')}")
            print(f"   btts_probability: {data.get('btts_probability')}")

            # Check if it's a truthy value (not null, not undefined)
            is_truthy = data is not None and len(data) > 0
            print(f"\n🎯 PREDICTION VALUE IS TRUTHY: {is_truthy}")
            print(f"   This means the condition 'prediction' will be {is_truthy}")

            return True

        else:
            print(f"[useLazyPrediction] Error occurred: {response.status_code}")
            print(f"Error response: {response.text[:200]}")
            return False

    except Exception as e:
        print(f"[useLazyPrediction] Error occurred: {e}")
        return False

def main():
    print("FRONTEND CONSOLE SIMULATION")
    print("Testing what browser console logs should show")

    success = simulate_frontend_prediction_call()

    print(f"\n📊 RESULT:")
    if success:
        print(f"✅ Frontend should show prediction tabs and data")
        print(f"✅ The condition 'shouldLoadPrediction && prediction' will be TRUE")
        print(f"✅ User will see the prediction interface")
    else:
        print(f"❌ Frontend API call would fail")
        print(f"❌ User would see error or loading state")

if __name__ == "__main__":
    main()
