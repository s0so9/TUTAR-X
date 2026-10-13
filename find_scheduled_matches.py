#!/usr/bin/env python3

import requests
from datetime import datetime, timedelta

def find_scheduled_matches():
    backend_url = 'http://127.0.0.1:8004'

    print('🔍 SCHEDULED maçları arıyorum...')
    print('='*50)

    # Gelecek 30 gün
    today = datetime.now()
    future = today + timedelta(days=30)
    from_date = today.strftime('%Y-%m-%d')
    to_date = future.strftime('%Y-%m-%d')

    list_url = f'{backend_url}/api/v1/matches?status=scheduled&from_date={from_date}&to_date={to_date}&limit=50'
    print(f'GET {list_url}')

    try:
        resp = requests.get(list_url, timeout=10)
        print(f'Status: {resp.status_code}')

        if resp.ok:
            data = resp.json()
            matches = data['matches']
            print(f'✅ Toplam {len(matches)} scheduled maç bulundu')

            # Carshalton Athletic - St Albans maçını ara
            target_teams = ['carshalton', 'st albans', 'st. albans', 'athletic']
            found_matches = []

            for match in matches:
                home_team = match.get('home_team', {}).get('name', '').lower() if match.get('home_team') else ''
                away_team = match.get('away_team', {}).get('name', '').lower() if match.get('away_team') else ''

                # Takım isimlerinde arama
                if any(team in home_team or team in away_team for team in target_teams):
                    found_matches.append(match)

            if found_matches:
                print(f'\n✅ Hedef takımlar ile eşleşen maçlar:')
                for i, match in enumerate(found_matches, 1):
                    home_name = match.get('home_team', {}).get('name') if match.get('home_team') else f"ID: {match['home_team_id']}"
                    away_name = match.get('away_team', {}).get('name') if match.get('away_team') else f"ID: {match['away_team_id']}"
                    print(f'{i}. ID: {match["id"]}')
                    print(f'   Takımlar: {home_name} vs {away_name}')
                    print(f'   Tarih: {match.get("scheduled_at", "N/A")}')
                    print(f'   Durum: {match["status"]}')

                    # Bu maç için tahmin test et
                    print(f'   Tahmin testi...')
                    pred_resp = requests.get(f'{backend_url}/api/v1/matches/{match["id"]}/prediction', timeout=20)
                    if pred_resp.ok:
                        print(f'   ✅ Tahmin API: {pred_resp.status_code}')
                    else:
                        print(f'   ❌ Tahmin API: {pred_resp.status_code} - {pred_resp.text[:100]}')
                    print()

                return found_matches[0]["id"] if found_matches else None
            else:
                print('❌ Carshalton/St Albans maçı bulunamadı')
                print('\n📋 İlk 10 scheduled maç:')
                for i, match in enumerate(matches[:10], 1):
                    home_name = match.get('home_team', {}).get('name') if match.get('home_team') else f"ID: {match['home_team_id']}"
                    away_name = match.get('away_team', {}).get('name') if match.get('away_team') else f"ID: {match['away_team_id']}"
                    print(f'{i}. {match["id"]} | {home_name} vs {away_name} | {match.get("scheduled_at", "N/A")}')

                # İlk maçı test maçı olarak döndür
                return matches[0]["id"] if matches else None
        else:
            print(f'❌ API Hatası: {resp.text[:200]}')
            return None

    except Exception as e:
        print(f'❌ Bağlantı Hatası: {e}')
        return None

if __name__ == "__main__":
    print("SCHEDULED MAÇ ARAMA ve TAHMIN TESTİ")
    print("=" * 60)

    test_match_id = find_scheduled_matches()

    if test_match_id:
        print(f"\n🎯 TEST MAÇI BULUNDU: {test_match_id}")
        print(f"   Bu ID ile frontend testi yapılabilir")
        print(f"   URL: http://localhost:5173/matches/{test_match_id}")
    else:
        print(f"\n❌ UYGUN SCHEDULED MAÇ BULUNAMADI")
        print(f"   Veritabanında scheduled maç yok veya API hatası var")
