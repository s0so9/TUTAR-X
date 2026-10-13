#!/usr/bin/env python3
"""
Verify HTTP status codes and JSON responses
"""
import requests
import json

base_url = 'http://localhost:8001'
canonical_id = 'aa4c9808-cb36-486e-bd41-003cc28b8543'

print('=== HTTP STATUS AND RESPONSE VERIFICATION ===')

# 1. GET /api/v1/matches
print('\n1. GET /api/v1/matches')
response = requests.get(f'{base_url}/api/v1/matches')
print(f'Status: {response.status_code}')
if response.status_code == 200:
    data = response.json()
    print(f'Response keys: {list(data.keys())}')
    print(f'Match count: {data["count"]}')
    print(f'First match ID: {data["matches"][0]["id"]}')
    print(f'Is development data: {data["is_development_data"]}')
else:
    print(f'Error: {response.text}')

# 2. Match detail endpoint
print(f'\n2. GET /api/v1/matches/{canonical_id}')
response = requests.get(f'{base_url}/api/v1/matches/{canonical_id}')
print(f'Status: {response.status_code}')
if response.status_code == 200:
    data = response.json()
    print(f'Response keys: {list(data.keys())}')
    print(f'Match ID: {data["match"]["id"]}')
    print(f'Match status: {data["match"]["status"]}')
    print(f'Match date: {data["match"]["scheduled_at"]}')
else:
    print(f'Error: {response.text}')

# 3. Prediction endpoint
print(f'\n3. GET /api/v1/matches/{canonical_id}/prediction')
response = requests.get(f'{base_url}/api/v1/matches/{canonical_id}/prediction')
print(f'Status: {response.status_code}')
if response.status_code == 200:
    data = response.json()
    print(f'Response keys: {list(data.keys())}')
    print(f'Match ID: {data["match_id"]}')
    home_prob = data["home_win_probability"]
    draw_prob = data["draw_probability"]
    away_prob = data["away_win_probability"]
    print(f'Home win: {home_prob}')
    print(f'Draw: {draw_prob}')
    print(f'Away win: {away_prob}')
    print(f'Total: {home_prob + draw_prob + away_prob}')
else:
    print(f'Error: {response.text}')
