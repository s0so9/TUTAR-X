#!/usr/bin/env python3

import requests
import json

def check_backend_and_match():
    match_id = 'd13431f9-0ce0-46dd-a95b-76d6a9f71be8'

    # Backend sunucu kontrolü
    print('🔍 Backend sunucu kontrolü...')
    backend_url = None

    for port in [8004, 8003, 8002, 8001, 8000]:
        try:
            r = requests.get(f'http://127.0.0.1:{port}/api/v1/matches?limit=1', timeout=5)
            if r.status_code == 200:
                print(f'✅ Backend çalışıyor (port {port})')
                backend_url = f'http://127.0.0.1:{port}'
                break
        except:
            continue

    if not backend_url:
        print('❌ KÖKÜ NEDEN: Backend sunucu çalışmıyor')
        print('Backend\'i başlatmak gerekiyor: cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8004')
        return False

    # Maç detayını kontrol et
    print(f'\n🔍 MAÇ ID KONTROLÜ: {match_id}')
    print('='*60)
    detail_url = f'{backend_url}/api/v1/matches/{match_id}'
    print(f'GET {detail_url}')

    try:
        detail_resp = requests.get(detail_url, timeout=10)
        print(f'Status: {detail_resp.status_code}')

        if detail_resp.status_code == 404:
            print('❌ KÖK NEDEN BULUNDU: Bu maç ID backend veritabanında YOK')
            print('   Frontend farklı bir ID gösteriyor olabilir')

            # Gerçek maçları listele
            print('\n📋 Mevcut maçları listeleyelim:')
            list_resp = requests.get(f'{backend_url}/api/v1/matches?limit=10', timeout=10)
            if list_resp.ok:
                matches = list_resp.json()['matches'][:5]
                print('İlk 5 maç:')
                for i, m in enumerate(matches, 1):
                    home_team = m.get('home_team', {}).get('name') if m.get('home_team') else f"ID: {m['home_team_id']}"
                    away_team = m.get('away_team', {}).get('name') if m.get('away_team') else f"ID: {m['away_team_id']}"
                    print(f'  {i}. {m["id"]} | {home_team} vs {away_team} | {m["status"]}')
            return False

        elif detail_resp.ok:
            data = detail_resp.json()
            match = data['match']
            home_name = match.get('home_team', {}).get('name') if match.get('home_team') else f"ID: {match['home_team_id']}"
            away_name = match.get('away_team', {}).get('name') if match.get('away_team') else f"ID: {match['away_team_id']}"

            print(f'✅ Maç backend\'de bulundu:')
            print(f'   Takımlar: {home_name} vs {away_name}')
            print(f'   Durum: {match["status"]}')
            print(f'   Tarih: {match.get("scheduled_at", "N/A")}')

            # Tahmin API kontrolü
            print(f'\n🔍 TAHMİN API KONTROLÜ:')
            pred_url = f'{backend_url}/api/v1/matches/{match_id}/prediction'
            print(f'GET {pred_url}')

            pred_resp = requests.get(pred_url, timeout=30)
            print(f'Status: {pred_resp.status_code}')

            if pred_resp.ok:
                pred_data = pred_resp.json()
                print('✅ Tahmin API başarılı')

                # Veri yapısını kontrol et
                required_fields = ['match_id', 'home_win_probability', 'draw_probability', 'away_win_probability']
                print('📊 Yanıt yapısı:')
                for field in required_fields:
                    value = pred_data.get(field, 'MISSING')
                    print(f'   {field}: {value}')

                # Olasılık toplamı
                if all(field in pred_data for field in required_fields[1:]):
                    total = pred_data['home_win_probability'] + pred_data['draw_probability'] + pred_data['away_win_probability']
                    print(f'   Olasılık toplamı: {total:.4f} (1.0 olmalı)')

                    if abs(total - 1.0) > 0.01:
                        print('⚠️ Olasılık toplamı 1.0 değil - veri problemi olabilir')

                return True, backend_url

            else:
                print(f'❌ KÖK NEDEN: Tahmin API hatası')
                print(f'   Hata: {pred_resp.text[:300]}')
                return False

        else:
            print(f'❌ API genel hatası: {detail_resp.text[:200]}')
            return False

    except Exception as e:
        print(f'❌ KÖK NEDEN: Bağlantı hatası - {e}')
        return False

if __name__ == "__main__":
    print("TUTAR X - Tahmin Sorunu Kök Neden Analizi")
    print("=" * 60)

    result = check_backend_and_match()

    if result:
        print(f"\n✅ SONUÇ: Backend API çalışıyor, sorun frontend'de olabilir")
        print(f"   Devam eden adım: Frontend useLazyPrediction hook kontrolü")
    else:
        print(f"\n❌ SONUÇ: Backend sorunu tespit edildi")
        print(f"   Önce backend sorununu çözmek gerekiyor")
