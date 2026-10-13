#!/usr/bin/env python3

import requests

backend_url = 'http://127.0.0.1:8004'

# Scheduled maçları bul
resp = requests.get(f'{backend_url}/api/v1/matches?status=scheduled&limit=5', timeout=10)
if resp.ok:
    matches = resp.json()['matches']
    print(f'SCHEDULED maçlar ({len(matches)} adet):')
    for i, match in enumerate(matches[:3], 1):
        home_team = match.get('home_team', {}).get('name') if match.get('home_team') else f"ID: {match['home_team_id']}"
        away_team = match.get('away_team', {}).get('name') if match.get('away_team') else f"ID: {match['away_team_id']}"
        print(f'{i}. {match["id"]} | {home_team} vs {away_team} | {match["status"]}')

    if matches:
        # İlk scheduled maçla prediction test
        test_id = matches[0]['id']
        print(f'\nPrediction test: {test_id}')
        pred_resp = requests.get(f'{backend_url}/api/v1/matches/{test_id}/prediction', timeout=30)
        print(f'Status: {pred_resp.status_code}')
        if pred_resp.ok:
            pred_data = pred_resp.json()
            print(f'✅ Prediction çalışıyor: home_win={pred_data.get("home_win_probability", "N/A")}')
            print(f'Frontend test URL: http://localhost:5173/matches/{test_id}')
        else:
            print(f'❌ Prediction hatası: {pred_resp.text[:100]}')
else:
    print('❌ Scheduled maç listesi alınamadı')
