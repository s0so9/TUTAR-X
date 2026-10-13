#!/usr/bin/env python3

import requests
import time
import json

def test_backend_prediction():
    """Verify backend is still working correctly"""
    print("1. Testing Backend Prediction API...")
    match_id = "a0872be9-d188-41fd-96b5-1023a8cef0f8"

    try:
        response = requests.get(f'http://127.0.0.1:8004/api/v1/matches/{match_id}/prediction', timeout=10)
        print(f"   ✅ Status: {response.status_code}")

        if response.ok:
            data = response.json()
            print(f"   ✅ Has home_win_probability: {data.get('home_win_probability') is not None}")
            print(f"   ✅ Has match_id: {data.get('match_id') == match_id}")
            return True
        else:
            print(f"   ❌ Error: {response.text[:100]}")
            return False
    except Exception as e:
        print(f"   ❌ Exception: {e}")
        return False

def test_frontend_loading():
    """Test if frontend loads without errors"""
    print("\n2. Testing Frontend Loading...")

    try:
        response = requests.get('http://localhost:5173/', timeout=10)
        print(f"   ✅ Frontend status: {response.status_code}")

        if response.ok:
            # Check if it's a React app (contains 'root' div)
            if 'id="root"' in response.text:
                print("   ✅ React app detected")
                return True
            else:
                print("   ❌ Not a React app or unexpected content")
                return False
        else:
            print(f"   ❌ Error loading frontend: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Exception: {e}")
        return False

def main():
    print("TUTAR X - Frontend Fix Verification")
    print("=" * 50)

    backend_ok = test_backend_prediction()
    frontend_ok = test_frontend_loading()

    print(f"\n📊 SUMMARY:")
    print(f"   Backend API: {'✅ Working' if backend_ok else '❌ Failed'}")
    print(f"   Frontend: {'✅ Working' if frontend_ok else '❌ Failed'}")

    if backend_ok and frontend_ok:
        print(f"\n🎯 NEXT STEPS:")
        print(f"   1. Visit: http://localhost:5173/matches/a0872be9-d188-41fd-96b5-1023a8cef0f8")
        print(f"   2. Check if sidebar shows 'Canlı' as active (should not)")
        print(f"   3. Check if prediction tabs appear (should appear)")
        print(f"   4. Check browser console for prediction loading logs")
        print(f"   5. Visit: http://localhost:5173/live (should show 'Canlı' as active)")
    else:
        print(f"\n❌ Fix prerequisites not met - check errors above")

if __name__ == "__main__":
    main()
