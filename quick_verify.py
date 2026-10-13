import requests

backend_url = 'http://127.0.0.1:8003'

print('🔍 RESTART SONRASI DOĞRULAMA')

# Competition check
comp_resp = requests.get(f'{backend_url}/api/v1/competitions', timeout=10)
competitions = comp_resp.json()['competitions']
target_comp = next((c for c in competitions if c['id'] == 'd13431f9-0ce0-46dd-a95b-76d6a9f71be8'), None)
print(f'Competition: "{target_comp["name"]}"')

# Prediction check
matches_resp = requests.get(f'{backend_url}/api/v1/matches?status=scheduled&limit=2', timeout=10)
matches = matches_resp.json()['matches']

for i, match in enumerate(matches[:2], 1):
    pred_resp = requests.get(f'{backend_url}/api/v1/matches/{match["id"]}/prediction', timeout=30)
    pred = pred_resp.json()
    print(f'Maç {i}: {pred["home_win_probability"]:.3f} | {pred["home_xg"]:.2f} | {pred.get("mensione_pick", {}).get("market")}')