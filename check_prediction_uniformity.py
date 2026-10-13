#!/usr/bin/env python3

import requests

def check_prediction_data_source():
    """Aynı tahmin değerlerinin neden üretildiğini kontrol et"""

    backend_url = 'http://127.0.0.1:8003'

    print('🔍 TAHMİN UNIFORMITY ANALİZİ')
    print('='*50)

    # Farklı scheduled maçlarla test
    scheduled_matches = []
    matches_resp = requests.get(f'{backend_url}/api/v1/matches?status=scheduled&limit=10', timeout=10)

    if matches_resp.ok:
        matches = matches_resp.json()['matches']
        scheduled_matches = [m['id'] for m in matches[:5]]  # İlk 5 maç

    print(f'Test edilecek {len(scheduled_matches)} scheduled maç')

    predictions = []

    for i, match_id in enumerate(scheduled_matches, 1):
        print(f'\n{i}️⃣ MAÇ: {match_id[:8]}...')

        # Match detail
        detail_resp = requests.get(f'{backend_url}/api/v1/matches/{match_id}', timeout=10)
        if detail_resp.ok:
            match = detail_resp.json()['match']
            home_team = match.get('home_team', {}).get('name', 'Unknown')
            away_team = match.get('away_team', {}).get('name', 'Unknown')
            print(f'   {home_team} vs {away_team}')

        # Prediction
        pred_resp = requests.get(f'{backend_url}/api/v1/matches/{match_id}/prediction', timeout=30)
        if pred_resp.ok:
            pred_data = pred_resp.json()

            prediction_summary = {
                'match_id': match_id[:8] + '...',
                'home_team': home_team,
                'away_team': away_team,
                'home_win': pred_data.get('home_win_probability'),
                'draw': pred_data.get('draw_probability'),
                'away_win': pred_data.get('away_win_probability'),
                'btts': pred_data.get('btts_probability'),
                'home_xg': pred_data.get('home_xg'),
                'away_xg': pred_data.get('away_xg'),
                'market': pred_data.get('mensione_pick', {}).get('market'),
                'selection': pred_data.get('mensione_pick', {}).get('selection'),
                'pick_prob': pred_data.get('mensione_pick', {}).get('probability')
            }

            predictions.append(prediction_summary)

            print(f'   1X2: {prediction_summary["home_win"]:.3f} - {prediction_summary["draw"]:.3f} - {prediction_summary["away_win"]:.3f}')
            print(f'   xG: {prediction_summary["home_xg"]:.2f} - {prediction_summary["away_xg"]:.2f}')
            print(f'   Pick: {prediction_summary["market"]} ({prediction_summary["pick_prob"]:.3f})')

    # Uniformity analizi
    print(f'\n📊 UNIFORMITY ANALİZİ:')
    print('-'*50)

    if len(predictions) >= 2:
        # 1X2 uniformity
        home_wins = [p['home_win'] for p in predictions if p['home_win']]
        draws = [p['draw'] for p in predictions if p['draw']]
        away_wins = [p['away_win'] for p in predictions if p['away_win']]

        home_win_unique = len(set([round(h, 4) for h in home_wins]))
        draw_unique = len(set([round(d, 4) for d in draws]))
        away_win_unique = len(set([round(a, 4) for a in away_wins]))

        print(f'Home Win: {home_win_unique} farklı değer ({len(home_wins)} toplam)')
        print(f'Draw: {draw_unique} farklı değer ({len(draws)} toplam)')
        print(f'Away Win: {away_win_unique} farklı değer ({len(away_wins)} toplam)')

        # Market uniformity
        markets = [p['market'] for p in predictions if p['market']]
        market_unique = len(set(markets))
        print(f'Selected Markets: {market_unique} farklı market ({len(markets)} toplam)')

        if market_unique == 1 and markets:
            print(f'🚨 TÜM MAÇLAR AYNI MARKETİ SEÇİYOR: {markets[0]}')

        # xG uniformity
        home_xgs = [p['home_xg'] for p in predictions if p['home_xg']]
        away_xgs = [p['away_xg'] for p in predictions if p['away_xg']]

        home_xg_unique = len(set([round(x, 3) for x in home_xgs]))
        away_xg_unique = len(set([round(x, 3) for x in away_xgs]))

        print(f'Home xG: {home_xg_unique} farklı değer ({len(home_xgs)} toplam)')
        print(f'Away xG: {away_xg_unique} farklı değer ({len(away_xgs)} toplam)')

        if home_xg_unique == 1 and away_xg_unique == 1:
            print(f'🚨 TÜM MAÇLAR AYNI xG DEĞERLERİNE SAHİP: {home_xgs[0]} - {away_xgs[0]}')
            print(f'   Bu model girdilerinde problem olduğunu gösterir')

    # Detaylar
    print(f'\n📋 DETAYLI KARŞILAŞTIRMA:')
    for p in predictions:
        print(f'{p["home_team"][:15]:15} vs {p["away_team"][:15]:15} | {p["home_win"]:.3f}-{p["draw"]:.3f}-{p["away_win"]:.3f} | {p["market"]} ({p["pick_prob"]:.3f})')

if __name__ == "__main__":
    check_prediction_data_source()
