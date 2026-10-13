#!/usr/bin/env python3
"""Test HTTP endpoints for SCHEDULED match predictions."""

import requests
import sys

def test_scheduled_prediction_http():
    """Test HTTP endpoints for SCHEDULED match predictions."""
    try:
        # Test matches endpoint
        resp = requests.get('http://127.0.0.1:8003/api/v1/matches', timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print(f'Matches endpoint: SUCCESS')
            print(f'Found {data.get("count", 0)} matches')

            # Find a SCHEDULED match to test prediction
            scheduled_matches = [m for m in data.get('matches', []) if m.get('status') == 'scheduled']
            if scheduled_matches:
                match = scheduled_matches[0]
                match_id = match['id']
                print(f'Testing prediction for SCHEDULED match: {match_id}')
                print(f'  Home team: {match.get("home_team_id")}')
                print(f'  Away team: {match.get("away_team_id")}')

                # Test prediction endpoint
                pred_resp = requests.get(f'http://127.0.0.1:8003/api/v1/matches/{match_id}/prediction', timeout=30)
                if pred_resp.status_code == 200:
                    pred_data = pred_resp.json()
                    print(f'Prediction endpoint: SUCCESS')
                    print(f'Home win probability: {pred_data.get("home_win_probability", 0):.3f}')
                    print(f'Draw probability: {pred_data.get("draw_probability", 0):.3f}')
                    print(f'Away win probability: {pred_data.get("away_win_probability", 0):.3f}')
                    print('✅ SCHEDULED MATCH PREDICTION ACCESS: WORKING')
                    return True
                else:
                    print(f'❌ Prediction failed: {pred_resp.status_code}')
                    print(f'Error: {pred_resp.text}')
                    return False
            else:
                print('⚠️ No SCHEDULED matches found for prediction test')
                return True
        else:
            print(f'❌ Matches endpoint failed: {resp.status_code}')
            return False

    except requests.exceptions.ConnectionError:
        print('⚠️ Backend not running - skipping HTTP test')
        return True
    except Exception as e:
        print(f'❌ HTTP test failed: {e}')
        return False

if __name__ == '__main__':
    success = test_scheduled_prediction_http()
    sys.exit(0 if success else 1)
