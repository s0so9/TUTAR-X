#!/usr/bin/env python3
import requests
import time
import json

# Test match ID
match_id = "000c4dcc-e92e-4f64-8cc5-988f4145385e"
url = f"http://localhost:8003/api/v1/matches/{match_id}/prediction"

print(f"Testing prediction endpoint: {url}")
print("Starting performance test...")

start_time = time.time()
try:
    response = requests.get(url, timeout=30)
    end_time = time.time()

    duration = end_time - start_time
    print(f"✅ Response received in {duration:.2f} seconds")
    print(f"Status Code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print("✅ Valid JSON response received")

        # Check if we got prediction data
        if "home_win_probability" in data:
            print(f"✅ Prediction data present:")
            print(f"  Home win: {data['home_win_probability']:.3f}")
            print(f"  Draw: {data['draw_probability']:.3f}")
            print(f"  Away win: {data['away_win_probability']:.3f}")

            # Check for data quality indicators
            if "data_context" in data:
                print(f"  Data context: {data['data_context']}")
            if "feature_coverage" in data:
                print(f"  Feature coverage: {data['feature_coverage']}")
        else:
            print("❌ No prediction probabilities in response")
            print(f"Response keys: {list(data.keys())}")
    else:
        print(f"❌ Error response: {response.text}")

except requests.exceptions.Timeout:
    end_time = time.time()
    duration = end_time - start_time
    print(f"❌ Request timed out after {duration:.2f} seconds")
except requests.exceptions.RequestException as e:
    end_time = time.time()
    duration = end_time - start_time
    print(f"❌ Request failed after {duration:.2f} seconds: {e}")
