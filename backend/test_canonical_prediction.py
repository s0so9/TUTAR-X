#!/usr/bin/env python3
"""Test canonical match prediction with real UUID."""

import time
import requests
from datetime import datetime

def main():
    print('='*80)
    print('VALIDATING FULL PIPELINE WITH REAL CANONICAL MATCH UUID')
    print('='*80)

    # Real canonical Match UUID
    match_id = 'fcca0ac7-8551-41f1-922e-38ae3c97fce0'
    url = f'http://localhost:8000/api/v1/matches/{match_id}/prediction'

    print(f'Match ID: {match_id}')
    print(f'API Endpoint: {url}')
    print(f'Timestamp: {datetime.now()}')
    print()

    try:
        # Measure cold HTTP latency
        start_time = time.time()

        # Execute HTTP request
        print('Executing HTTP prediction request...')
        response = requests.get(url, timeout=30)

        end_time = time.time()
        execution_time_ms = (end_time - start_time) * 1000

        print(f'HTTP Status: {response.status_code}')
        print(f'Cold HTTP latency: {execution_time_ms:.2f}ms')
        print()

        if response.status_code == 200:
            result = response.json()

            print('✅ PREDICTION SUCCESSFUL')
            print()

            # Analyze result
            print('API RESPONSE FIELDS:')
            print(f'  match_id: {result.get("match_id")}')
            print(f'  home_team: {result.get("home_team")}')
            print(f'  away_team: {result.get("away_team")}')
            print(f'  confidence_assessment: {result.get("confidence_assessment")}')
            print(f'  predicted_score: {result.get("predicted_score")}')
            print(f'  mensione_pick: {result.get("mensione_pick")}')
            print()

            # Check prediction probabilities
            if 'prediction' in result and result['prediction']:
                pred = result['prediction']
                print('PREDICTION PROBABILITIES:')
                print(f'  Home Win: {pred.get("home_win_probability", 0):.3f}')
                print(f'  Draw: {pred.get("draw_probability", 0):.3f}')
                print(f'  Away Win: {pred.get("away_win_probability", 0):.3f}')
                total = (pred.get('home_win_probability', 0) +
                        pred.get('draw_probability', 0) +
                        pred.get('away_win_probability', 0))
                print(f'  Total: {total:.6f}')
                print()

            # Check markets
            if 'markets' in result and result['markets']:
                print('TUTAR X MARKETS:')
                for market in result['markets'][:3]:  # Show first 3 markets
                    print(f'  {market["market_name"]}: {market["selection_name"]} @ {market["decimal_odds"]:.2f}')
                print()

            print('✅ VALIDATION SUCCESSFUL - Full pipeline working with real canonical data')
            return True

        else:
            print(f'❌ HTTP REQUEST FAILED: {response.status_code}')
            print(f'Response: {response.text}')
            return False

    except requests.exceptions.ConnectionError:
        print('❌ CONNECTION FAILED - Backend server not running on localhost:8000')
        print('Please start the backend server first')
        return False
    except Exception as e:
        print(f'❌ REQUEST FAILED: {str(e)}')
        import traceback
        traceback.print_exc()
        return False

    finally:
        print('='*80)

if __name__ == '__main__':
    main()
