#!/usr/bin/env python3
"""Test API endpoint for prediction markets."""

import requests
import json

def test_prediction_markets():
    """Test if prediction_markets includes Over/Under 2.5."""

    # Arsenal vs Leeds match
    match_id = "849f5743-1f96-4ade-be4c-af1c5d3da039"
    url = f"http://localhost:8000/api/v1/matches/{match_id}/prediction"


    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        # Check prediction_markets first
        markets = data.get('prediction_markets', [])
        if markets:
            print(f"prediction_markets bulundu: {len(markets)} market")

            for i, market in enumerate(markets):
                mtype = market.get('market_type')
                line = market.get('line')
                probs = market.get('probabilities', {})

                if mtype == 'over_under' and line == 2.5:
                    print(f"✅ BULUNDU - Over/Under 2.5 in prediction_markets:")
                    print(f"  Over: {probs.get('over', 'N/A'):.4f}")
                    print(f"  Under: {probs.get('under', 'N/A'):.4f}")
                    return True
        else:
            print("prediction_markets alani yok, market_analysis kontrolu yapiliyor...")

        # Check market_analysis
        market_analysis = data.get('market_analysis', [])
        if market_analysis:
            print(f"market_analysis bulundu: {len(market_analysis)} item")

            # Over/Under 2.5 için arama
            over_under_2_5_found = False
            for market in market_analysis:
                market_type = market.get('market_type', '')
                line = market.get('line')

                if market_type == 'OVER_UNDER_2_5' and line == 2.5:
                    over_under_2_5_found = True
                    outcomes = market.get('outcomes', [])
                    over_prob = None
                    under_prob = None

                    for outcome in outcomes:
                        if 'Over' in outcome.get('label', ''):
                            over_prob = outcome.get('model_probability')
                        elif 'Under' in outcome.get('label', ''):
                            under_prob = outcome.get('model_probability')

                    print(f"✅ BULUNDU - Over/Under 2.5 in market_analysis:")
                    print(f"  Over 2.5: {over_prob:.4f} ({over_prob*100:.2f}%)")
                    print(f"  Under 2.5: {under_prob:.4f} ({under_prob*100:.2f}%)")
                    return True

            if not over_under_2_5_found:
                print(f"❌ Over/Under 2.5 bulunamadi, mevcut marketler:")
                for market in market_analysis:
                    print(f"  - {market.get('market_type')}, line: {market.get('line')}")
        else:
            print("market_analysis alani da yok!")

        return over_under_2_5_found

    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    test_prediction_markets()
