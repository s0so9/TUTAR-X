#!/usr/bin/env python3
"""
Analyze the actual API response structure for statistics display mapping
"""

import requests
import json
import time

def analyze_api_response():
    match_id = '849f5743-1f96-4ade-be4c-af1c5d3da039'
    url = f'http://localhost:8000/api/v1/matches/{match_id}/prediction'

    print(f"Analyzing API response structure: {url}")

    try:
        response = requests.get(url, timeout=60)
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()

            print("\n📊 FULL API RESPONSE STRUCTURE:")
            print(json.dumps(data, indent=2, default=str))

            print("\n🎯 LOOKING FOR OVER/UNDER DATA:")

            # Check market_analysis field
            if 'market_analysis' in data:
                market_analysis = data['market_analysis']
                print(f"Market analysis type: {type(market_analysis)}")

                if isinstance(market_analysis, dict):
                    print("Market analysis keys:", list(market_analysis.keys()))

                    for key, value in market_analysis.items():
                        if 'over' in key.lower() or 'under' in key.lower():
                            print(f"  Over/Under related: {key} = {value}")

                print("\nMarket analysis details:")
                print(json.dumps(market_analysis, indent=2, default=str)[:1000] + "...")

            # Check mensione_pick field
            if 'mensione_pick' in data:
                mensione_pick = data['mensione_pick']
                print(f"\n📈 MENSIONE PICK:")
                print(json.dumps(mensione_pick, indent=2, default=str))

                if isinstance(mensione_pick, dict) and 'market_type' in mensione_pick:
                    market_type = mensione_pick['market_type']
                    if 'over' in market_type.lower() or 'under' in market_type.lower():
                        print("✅ Found Over/Under in Mensione pick!")

            # Check for any probability fields
            print(f"\n📊 PROBABILITY FIELDS:")
            prob_fields = [k for k in data.keys() if 'prob' in k.lower()]
            for field in prob_fields:
                print(f"  {field}: {data[field]}")

        else:
            print(f"❌ Error {response.status_code}: {response.text[:200]}")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == '__main__':
    time.sleep(1)  # Wait for server
    analyze_api_response()
