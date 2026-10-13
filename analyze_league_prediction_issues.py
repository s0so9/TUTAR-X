#!/usr/bin/env python3

import requests
import json

def analyze_api_responses():
    """Lig ve tahmin sorunlarının kök nedenini bul"""

    # Backend sunucu kontrolü
    backend_url = None
    for port in [8003, 8004]:
        try:
            r = requests.get(f'http://127.0.0.1:{port}/api/v1/matches?limit=1', timeout=5)
            if r.ok:
                backend_url = f'http://127.0.0.1:{port}'
                print(f'✅ Backend çalışıyor: {backend_url}')
                break
        except:
            continue

    if not backend_url:
        print('❌ Backend sunucu çalışmıyor')
        return

    print('🔍 API YANITLARINI İNCELİYORUM...')
    print('='*60)

    # Test maçları - sorunlu lig isimleri
    test_matches = [
        'a0872be9-d188-41fd-96b5-1023a8cef0f8',  # Burgess Hill Town – Aveley
        '03d5e3db-f1d6-4af8-9a93-e4b80711876a'   # Başka scheduled maç
    ]

    for i, match_id in enumerate(test_matches, 1):
        print(f'\n{i}️⃣ MAÇ ANALİZİ: {match_id}')
        print('-'*50)

        # Match detail
        detail_resp = requests.get(f'{backend_url}/api/v1/matches/{match_id}', timeout=10)
        print(f'Match Detail Status: {detail_resp.status_code}')

        if detail_resp.ok:
            match_data = detail_resp.json()
            match = match_data['match']

            # Takım bilgileri
            home_team = match.get('home_team', {}).get('name') if match.get('home_team') else f"ID: {match['home_team_id']}"
            away_team = match.get('away_team', {}).get('name') if match.get('away_team') else f"ID: {match['away_team_id']}"

            print(f'📋 Takımlar: {home_team} vs {away_team}')
            print(f'📋 Status: {match["status"]}')

            # Lig/Competition bilgileri
            competition_id = match.get('competition_id')
            print(f'📋 Competition ID: {competition_id}')

            # Competition API'den lig bilgisini al
            if competition_id:
                comp_resp = requests.get(f'{backend_url}/api/v1/competitions', timeout=10)
                if comp_resp.ok:
                    competitions = comp_resp.json().get('competitions', [])
                    competition = next((c for c in competitions if c['id'] == competition_id), None)

                    if competition:
                        print(f'📋 Lig Adı: "{competition["name"]}"')
                        print(f'📋 Ülke: {competition.get("country", "N/A")}')

                        # Bu gerçekten Premier League mi?
                        is_premier_league = 'premier league' in competition['name'].lower()
                        print(f'📋 Gerçek Premier League: {is_premier_league}')

                        if not is_premier_league and 'premier league' in competition['name'].lower():
                            print('🚨 SORUN BULUNDU: Yanlış Premier League etiketi')
                    else:
                        print('❌ Competition listesinde bulunamadı')
                else:
                    print('❌ Competition API hatası')

            # Prediction API
            if match['status'].upper() == 'SCHEDULED':
                print(f'\n📊 TAHMİN ANALİZİ:')
                pred_resp = requests.get(f'{backend_url}/api/v1/matches/{match_id}/prediction', timeout=30)
                print(f'Prediction Status: {pred_resp.status_code}')

                if pred_resp.ok:
                    pred_data = pred_resp.json()

                    # Ana tahmin değerleri
                    home_win = pred_data.get('home_win_probability')
                    draw = pred_data.get('draw_probability')
                    away_win = pred_data.get('away_win_probability')
                    btts = pred_data.get('btts_probability')

                    print(f'   Home Win: {home_win:.3f}')
                    print(f'   Draw: {draw:.3f}')
                    print(f'   Away Win: {away_win:.3f}')
                    print(f'   BTTS: {btts:.3f}')

                    # TUTAR X Pick (Over 1.5 sorunu)
                    mensione_pick = pred_data.get('mensione_pick')
                    if mensione_pick:
                        print(f'   TUTAR X Pick: {json.dumps(mensione_pick, indent=2)[:200]}...')

                        market = mensione_pick.get('market')
                        selection = mensione_pick.get('selection')
                        print(f'   Seçilen Market: {market}')
                        print(f'   Seçim: {selection}')

                        if market == 'OVER_1_5':
                            print('🚨 SORUN: Yine Over 1.5 seçildi')
                    else:
                        print('   ℹ️ TUTAR X Pick yok')

                    # Market Analysis
                    market_analysis = pred_data.get('market_analysis')
                    if market_analysis:
                        print(f'   Market Analysis: {len(market_analysis)} market')
                        for ma in market_analysis[:3]:  # İlk 3 market
                            market_type = ma.get('market_type')
                            outcomes = ma.get('outcomes', [])
                            print(f'      {market_type}: {len(outcomes)} outcome')
                    else:
                        print('   ℹ️ Market Analysis yok')
                else:
                    print(f'❌ Prediction hatası: {pred_resp.text[:200]}')
        else:
            print(f'❌ Match detail hatası: {detail_resp.text[:200]}')

    print(f'\n🔍 COMPETITIONS API GENEL KONTROL:')
    comp_resp = requests.get(f'{backend_url}/api/v1/competitions', timeout=10)
    if comp_resp.ok:
        competitions = comp_resp.json().get('competitions', [])
        print(f'Toplam {len(competitions)} competition')

        # Premier League içeren tüm ligleri listele
        premier_leagues = [c for c in competitions if 'premier' in c['name'].lower()]
        print(f'Premier League içeren ligler: {len(premier_leagues)}')

        for pl in premier_leagues[:5]:  # İlk 5 tanesi
            print(f'   - {pl["id"]}: "{pl["name"]}" ({pl.get("country", "N/A")})')

        # Farklı lig örnekleri
        other_leagues = [c for c in competitions if 'premier' not in c['name'].lower()][:5]
        print(f'Diğer lig örnekleri:')
        for ol in other_leagues:
            print(f'   - {ol["id"]}: "{ol["name"]}" ({ol.get("country", "N/A")})')

if __name__ == "__main__":
    print("LİG VE TAHMİN SORUNLARI KÖK NEDEN ANALİZİ")
    print("=" * 60)
    analyze_api_responses()
