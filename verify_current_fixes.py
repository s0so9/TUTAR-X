#!/usr/bin/env python3

import requests

def verify_fixes_after_restart():
    """Backend restart sonrası düzeltmeleri doğrula"""

    backend_url = 'http://127.0.0.1:8003'

    print('🔍 RESTART SONRASI DOĞRULAMA')
    print('='*50)

    # 1. Competition mapping kontrolü
    print('1️⃣ COMPETITION MAPPING:')
    try:
        comp_resp = requests.get(f'{backend_url}/api/v1/competitions', timeout=10)
        if comp_resp.ok:
            competitions = comp_resp.json()['competitions']

            target_comp = next((c for c in competitions if c['id'] == 'd13431f9-0ce0-46dd-a95b-76d6a9f71be8'), None)
            if target_comp:
                print(f'   Problemli ID: "{target_comp["name"]}"')
                if target_comp['name'] != 'Premier League':
                    print(f'   ✅ Düzeltildi: Artık "{target_comp["name"]}"')
                else:
                    print(f'   ❌ Hâlâ "Premier League" gösteriyor')

            print(f'   Toplam competition: {len(competitions)}')
        else:
            print(f'   ❌ Competition API error: {comp_resp.status_code}')
    except Exception as e:
        print(f'   ❌ Competition test failed: {e}')

    # 2. Prediction variation kontrolü
    print(f'\n2️⃣ PREDICTION VARIATION:')
    try:
        matches_resp = requests.get(f'{backend_url}/api/v1/matches?status=scheduled&limit=3', timeout=10)
        if matches_resp.ok:
            matches = matches_resp.json()['matches']

            predictions = []

            for i, match in enumerate(matches[:3], 1):
                match_id = match['id']
                print(f'   Maç {i}: {match_id[:8]}...')

                pred_resp = requests.get(f'{backend_url}/api/v1/matches/{match_id}/prediction', timeout=30)
                if pred_resp.ok:
                    pred = pred_resp.json()

                    prediction_data = {
                        'home_win': pred.get('home_win_probability'),
                        'draw': pred.get('draw_probability'),
                        'away_win': pred.get('away_win_probability'),
                        'home_xg': pred.get('home_xg'),
                        'away_xg': pred.get('away_xg'),
                        'market': pred.get('mensione_pick', {}).get('market')
                    }

                    predictions.append(prediction_data)

                    print(f'      1X2: {prediction_data["home_win"]:.3f}-{prediction_data["draw"]:.3f}-{prediction_data["away_win"]:.3f}')
                    print(f'      xG: {prediction_data["home_xg"]:.2f}-{prediction_data["away_xg"]:.2f}')
                    print(f'      Market: {prediction_data["market"]}')
                else:
                    print(f'      ❌ Prediction error: {pred_resp.status_code}')

            # Variation analysis
            if len(predictions) >= 2:
                home_wins = [p['home_win'] for p in predictions if p['home_win']]
                home_xgs = [p['home_xg'] for p in predictions if p['home_xg']]
                markets = [p['market'] for p in predictions if p['market']]

                home_win_unique = len(set([round(h, 3) for h in home_wins]))
                xg_unique = len(set([round(x, 2) for x in home_xgs]))
                market_unique = len(set(markets))

                print(f'\n📊 VARIATION RESULTS:')
                print(f'   Home Win Prob: {home_win_unique}/{len(home_wins)} different')
                print(f'   Home xG: {xg_unique}/{len(home_xgs)} different')
                print(f'   Selected Markets: {market_unique}/{len(markets)} different')

                return {
                    'competition_fixed': target_comp and target_comp['name'] != 'Premier League' if 'target_comp' in locals() else False,
                    'prediction_varied': home_win_unique > 1 or xg_unique > 1 or market_unique > 1
                }
        else:
            print(f'   ❌ Matches API error: {matches_resp.status_code}')
    except Exception as e:
        print(f'   ❌ Prediction test failed: {e}')

    return {'competition_fixed': False, 'prediction_varied': False}

if __name__ == "__main__":
    results = verify_fixes_after_restart()

    print(f"\n🎯 DURUM ÖZETI:")
    print(f"   Competition Fix: {'✅' if results['competition_fixed'] else '❌'}")
    print(f"   Prediction Variation: {'✅' if results['prediction_varied'] else '❌'}")

    if not results['competition_fixed'] or not results['prediction_varied']:
        print(f"\n🔧 EK DÜZELTMELERİ GEREKİYOR")
