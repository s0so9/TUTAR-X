#!/usr/bin/env python3
"""
HTTP prediction performance test
"""
import time
import requests
import json
from datetime import datetime

def test_http_prediction():
    """Test prediction via HTTP endpoint"""

    print("=== HTTP PREDICTION PERFORMANCE TEST ===")

    # Backend URL
    base_url = "http://localhost:8003"

    # First get matches to find a suitable one
    print("Fetching matches...")
    try:
        matches_response = requests.get(f"{base_url}/api/v1/matches", timeout=10)
        if matches_response.status_code != 200:
            print(f"❌ Failed to get matches: {matches_response.status_code}")
            return None

        matches_data = matches_response.json()
        matches = matches_data.get('matches', [])

        print(f"Found {len(matches)} matches")

        # Find a suitable match
        suitable_match = None
        for match in matches[:10]:
            if match.get('home_team') and match.get('away_team'):
                suitable_match = match
                break

        if not suitable_match:
            print("❌ No suitable match found")
            return None

        match_id = suitable_match.get('id')
        home_team = suitable_match.get('home_team')
        away_team = suitable_match.get('away_team')

        print(f"Selected match: {home_team} vs {away_team}")
        print(f"Match ID: {match_id}")

        # Test prediction endpoint
        print(f"\nTesting prediction endpoint...")
        start_time = time.time()

        prediction_response = requests.get(f"{base_url}/api/v1/matches/{match_id}/prediction", timeout=60)

        end_time = time.time()
        total_ms = (end_time - start_time) * 1000

        print(f"\n=== HTTP BENCHMARK RESULTS ===")
        print(f"HTTP Request Time: {total_ms:.0f}ms ({total_ms/1000:.2f}s)")
        print(f"Status Code: {prediction_response.status_code}")

        if prediction_response.status_code == 200:
            prediction_data = prediction_response.json()

            print(f"✅ Prediction Retrieved Successfully")

            # Check key fields
            home_win = prediction_data.get('home_win_probability', 0)
            draw = prediction_data.get('draw_probability', 0)
            away_win = prediction_data.get('away_win_probability', 0)

            print(f"1X2 Probabilities: {home_win:.3f} / {draw:.3f} / {away_win:.3f}")

            prob_sum = home_win + draw + away_win
            print(f"Probability Sum: {prob_sum:.3f} {'✅' if 0.99 <= prob_sum <= 1.01 else '❌'}")

            home_xg = prediction_data.get('home_xg', 0)
            away_xg = prediction_data.get('away_xg', 0)
            print(f"Expected Goals: {home_xg:.2f} - {away_xg:.2f}")

            # Check MENSIONE pick
            mensione = prediction_data.get('mensione_pick')
            if mensione:
                if mensione.get('pass_decision'):
                    print(f"MENSIONE Pick: PASS ({mensione.get('pass_reason', 'no reason')})")
                else:
                    selection = mensione.get('selection', 'N/A')
                    probability = mensione.get('probability', 0)
                    confidence = mensione.get('confidence', 0)
                    print(f"MENSIONE Pick: {selection} @ {probability:.3f} (confidence: {confidence:.2f})")

            # Check data quality
            data_quality = prediction_data.get('data_quality', {})
            if data_quality:
                total_matches = data_quality.get('total_matches', 0)
                home_matches = data_quality.get('home_historical_matches', 0)
                away_matches = data_quality.get('away_historical_matches', 0)
                print(f"Data Quality: {total_matches} total, {home_matches} home, {away_matches} away")

        else:
            print(f"❌ HTTP Request Failed")
            print(f"Response: {prediction_response.text}")

        return total_ms

    except requests.exceptions.Timeout:
        print("❌ Request timed out (>60s)")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

if __name__ == "__main__":
    result = test_http_prediction()
    if result:
        print(f"\n🏁 HTTP Test completed in {result:.0f}ms")
        if result > 28000:  # 28+ seconds
            print("⚠️  Performance matches reported 28-29s issue")
        elif result > 10000:  # 10+ seconds
            print("⚠️  Performance is slow (>10s)")
        elif result > 5000:   # 5+ seconds
            print("⚠️  Performance could be improved (>5s)")
        else:
            print("✅ Performance is good")
    else:
        print("\n❌ HTTP Test failed")
