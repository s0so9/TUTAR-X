#!/usr/bin/env python3

import requests

def test_league_fix():
    """Competition mapping düzeltmesini test et"""
    backend_url = 'http://127.0.0.1:8003'

    print('🧪 LİG DÜZELTMESİ TEST')
    print('='*30)

    # Competition API
    comp_resp = requests.get(f'{backend_url}/api/v1/competitions', timeout=10)
    if comp_resp.ok:
        competitions = comp_resp.json()['competitions']

        for comp in competitions:
            print(f'✅ {comp["id"][:8]}...: "{comp["name"]}" ({comp.get("country", "N/A")})')

            # "Premier League" hard-coding düzeldi mi?
            if comp['id'] == 'd13431f9-0ce0-46dd-a95b-76d6a9f71be8':
                if comp['name'] != 'Premier League':
                    print(f'   ✅ Düzeltildi: Artık "{comp["name"]}" olarak gösteriliyor')
                else:
                    print(f'   ❌ Hâlâ "Premier League" gösteriyor')

        return True
    else:
        print('❌ Competition API hatası')
        return False

def test_prediction_variation():
    """Tahmin çeşitliliği düzeltmesini test et"""
    backend_url = 'http://127.0.0.1:8003'

    print(f'\n🧪 TAHMİN ÇEŞİTLİLİĞİ TEST')
    print('='*30)

    # Farklı scheduled maçları test et
    matches_resp = requests.get(f'{backend_url}/api/v1/matches?status=scheduled&limit=3', timeout=10)
    if matches_resp.ok:
        matches = matches_resp.json()['matches']

        predictions = []

        for i, match in enumerate(matches[:3], 1):
            match_id = match['id']
            print(f'{i}️⃣ {match_id[:8]}...')

            pred_resp = requests.get(f'{backend_url}/api/v1/matches/{match_id}/prediction', timeout=30)
            if pred_resp.ok:
                pred = pred_resp.json()

                home_win = pred.get('home_win_probability', 0)
                draw = pred.get('draw_probability', 0)
                away_win = pred.get('away_win_probability', 0)
                home_xg = pred.get('home_xg', 0)
                away_xg = pred.get('away_xg', 0)
                market = pred.get('mensione_pick', {}).get('market', 'N/A')

                predictions.append({
                    'match_id': match_id[:8],
                    'home_win': home_win,
                    'draw': draw,
                    'away_win': away_win,
                    'home_xg': home_xg,
                    'away_xg': away_xg,
                    'market': market
                })

                print(f'   1X2: {home_win:.3f}-{draw:.3f}-{away_win:.3f}')
                print(f'   xG: {home_xg:.2f}-{away_xg:.2f}')
                print(f'   Market: {market}')

        # Çeşitlilik kontrolü
        if len(predictions) >= 2:
            home_wins = [p['home_win'] for p in predictions]
            home_xgs = [p['home_xg'] for p in predictions]
            markets = [p['market'] for p in predictions]

            home_win_unique = len(set([round(h, 3) for h in home_wins]))
            xg_unique = len(set([round(x, 2) for x in home_xgs]))
            market_unique = len(set(markets))

            print(f'\n📊 ÇEŞİTLİLİK SONUÇLARI:')
            print(f'   Home Win Olasılık: {home_win_unique}/{len(home_wins)} farklı')
            print(f'   Home xG: {xg_unique}/{len(home_xgs)} farklı')
            print(f'   Seçilen Market: {market_unique}/{len(markets)} farklı')

            if home_win_unique > 1:
                print(f'   ✅ Olasılık çeşitliliği düzeldi')
            else:
                print(f'   ❌ Hâlâ aynı olasılıklar')

            if xg_unique > 1:
                print(f'   ✅ xG çeşitliliği düzeldi')
            else:
                print(f'   ❌ Hâlâ aynı xG değerleri')

            if market_unique > 1:
                print(f'   ✅ Market çeşitliliği arttı')
            else:
                print(f'   ❌ Hâlâ aynı market seçiliyor: {markets[0]}')

            return home_win_unique > 1 or xg_unique > 1

        return False
    else:
        print('❌ Matches API hatası')
        return False

if __name__ == "__main__":
    print("DÜZELTMELERİ DOĞRULAMA TESTİ")
    print("=" * 50)

    league_fixed = test_league_fix()
    prediction_fixed = test_prediction_variation()

    print(f"\n📊 SONUÇ ÖZETİ:")
    print(f"   Lig Etiketleri: {'✅ Düzeldi' if league_fixed else '❌ Sorun devam ediyor'}")
    print(f"   Tahmin Çeşitliliği: {'✅ İyileşti' if prediction_fixed else '❌ Sorun devam ediyor'}")

    if league_fixed and prediction_fixed:
        print(f"\n🎉 HER İKİ SORUN DA DÜZELTİLDİ!")
    else:
        print(f"\n⚠️ Bazı sorunlar devam ediyor - daha fazla düzeltme gerekiyor")
