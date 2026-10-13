#!/usr/bin/env python3
"""Test API endpoint for statistics display mapping"""

import requests
import json
import time

def test_prediction_api():
    match_id = '849f5743-1f96-4ade-be4c-af1c5d3da039'
    url = f'http://localhost:8000/api/v1/matches/{match_id}/prediction'

    print(f"Testing API endpoint: {url}")

    try:
        response = requests.get(url, timeout=60)
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"Response keys: {list(data.keys())}")

            if 'markets' in data:
                print(f"Markets found: {len(data['markets'])}")

                for i, market in enumerate(data['markets']):
                    market_type = market.get('market_type', 'Unknown')
                    print(f"  {i+1}. Market: {market_type}")

                    if 'over_under' in market_type.lower():
                        line = market.get('line')
                        print(f"     Line: {line}")

                        if 'selections' in market:
                            for sel in market['selections']:
                                sel_type = sel.get('selection_type', '')
                                prob = sel.get('probability', 0)
                                print(f"       {sel_type}: {prob:.4f} ({prob*100:.2f}%)")
                        print()

                # Check for specific Over/Under 2.5 market
                found_2_5 = False
                for market in data['markets']:
                    if 'over_under' in market.get('market_type', '').lower():
                        line = market.get('line')
                        if line == 2.5:
                            found_2_5 = True
                            print(f"✅ Found Over/Under 2.5 market")
                            break

                if not found_2_5:
                    print("⚠️  Over/Under 2.5 market not found")

            else:
                print("❌ No 'markets' field in response")

        else:
            print(f"❌ Error {response.status_code}: {response.text[:200]}")

    except requests.exceptions.ConnectionError:
        print("❌ Connection failed - server may not be running")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == '__main__':
    # Wait a bit for server to be ready
    time.sleep(2)
    test_prediction_api()
