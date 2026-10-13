#!/usr/bin/env python3
"""
Test script to verify the match-detail timeout fix.
"""
import time
import requests
import sys

def test_match_detail_performance():
    """Test match detail endpoint performance."""
    match_id = '849f5743-1f96-4ade-be4c-af1c5d3da039'
    base_url = 'http://127.0.0.1:8003/api/v1'

    print("=== TIMEOUT FIX VERIFICATION ===")
    print(f"Match ID: {match_id}")
    print()

    # Test 1: Match detail endpoint
    print("1. Testing match detail endpoint...")
    start_time = time.time()
    try:
        response = requests.get(f"{base_url}/matches/{match_id}", timeout=10)
        match_time = time.time() - start_time

        if response.status_code == 200:
            print(f"   ✅ Match Detail: {match_time:.1f}s - SUCCESS")
            match_data = response.json()
            status = match_data['match']['status']
            print(f"   Status: {status}")

            if status == 'scheduled':
                # Test 2: Prediction endpoint (this was timing out)
                print("\n2. Testing prediction endpoint...")
                start_time = time.time()
                try:
                    response = requests.get(f"{base_url}/matches/{match_id}/prediction", timeout=15)
                    pred_time = time.time() - start_time

                    if response.status_code == 200:
                        print(f"   ✅ Prediction: {pred_time:.1f}s - SUCCESS")
                        pred_data = response.json()
                        print(f"   Home Win: {pred_data['home_win_probability']*100:.1f}%")
                        print(f"   Match ID: {pred_data['mensione_pick']['match_id']}")

                        print(f"\n🎉 TIMEOUT FIX SUCCESSFUL!")
                        print(f"   - Match detail: {match_time:.1f}s (was ~2s)")
                        print(f"   - Prediction: {pred_time:.1f}s (was 25-30s timeout)")
                        print(f"   - Total flow: {match_time + pred_time:.1f}s")
                        return True
                    else:
                        print(f"   ❌ Prediction: HTTP {response.status_code}")
                        return False
                except requests.exceptions.Timeout:
                    pred_time = time.time() - start_time
                    print(f"   ❌ Prediction: TIMEOUT after {pred_time:.1f}s")
                    return False
                except Exception as e:
                    pred_time = time.time() - start_time
                    print(f"   ❌ Prediction: ERROR after {pred_time:.1f}s - {e}")
                    return False
            else:
                print(f"   ℹ️  Match is {status}, prediction not expected")
                return True
        else:
            print(f"   ❌ Match Detail: HTTP {response.status_code}")
            return False
    except requests.exceptions.Timeout:
        match_time = time.time() - start_time
        print(f"   ❌ Match Detail: TIMEOUT after {match_time:.1f}s")
        return False
    except Exception as e:
        match_time = time.time() - start_time
        print(f"   ❌ Match Detail: ERROR after {match_time:.1f}s - {e}")
        return False

if __name__ == "__main__":
    success = test_match_detail_performance()
    sys.exit(0 if success else 1)
