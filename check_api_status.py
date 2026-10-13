#!/usr/bin/env python3

import requests

match_id = 'a0872be9-d188-41fd-96b5-1023a8cef0f8'
backend_url = 'http://127.0.0.1:8003'

try:
    resp = requests.get(f'{backend_url}/api/v1/matches/{match_id}', timeout=10)
    if resp.ok:
        data = resp.json()
        status = data['match']['status']
        print(f'API status: "{status}" (type: {type(status).__name__})')
        print(f'status.lower(): "{status.lower()}"')

        # shouldLoadPrediction test
        should_load_old = status == 'scheduled' or status == 'postponed'
        should_load_new = status.upper() == 'SCHEDULED' or status.upper() == 'POSTPONED'
        print(f'shouldLoadPrediction (old logic): {should_load_old}')
        print(f'shouldLoadPrediction (new logic): {should_load_new}')
    else:
        print(f'API Error: {resp.status_code} - {resp.text[:100]}')
except Exception as e:
    print(f'Error: {e}')
