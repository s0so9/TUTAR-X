#!/usr/bin/env python3

import requests
import json

def test_working_match():
    """Çalışan bir scheduled maçla end-to-end test"""
    backend_url = 'http://127.0.0.1:8004'

    # Bilinen çalışan maç ID'si
    working_match_id = 'aa4c9808-cb36-486e-bd41-003cc28b8543'

    print(f'🧪 ÇALIŞAN MAÇ TEST: {working_match_id}')
    print('='*60)

    # 1. Maç detayını al
    print(f'1️⃣ Maç detayı test:')
    detail_resp = requests.get(f'{backend_url}/api/v1/matches/{working_match_id}', timeout=10)
    print(f'   Status: {detail_resp.status_code}')

    if not detail_resp.ok:
        print(f'   ❌ Maç detayı alınamadı: {detail_resp.text[:200]}')
        return False

    match_data = detail_resp.json()
    match = match_data['match']
    print(f'   ✅ Maç: ID {match["id"]}')
    print(f'   ✅ Durum: {match["status"]}')
    print(f'   ✅ Takımlar: {match["home_team_id"]} vs {match["away_team_id"]}')

    # 2. Tahmin API'sini test et
    print(f'\n2️⃣ Tahmin API test:')
    pred_resp = requests.get(f'{backend_url}/api/v1/matches/{working_match_id}/prediction', timeout=30)
    print(f'   Status: {pred_resp.status_code}')

    if not pred_resp.ok:
        print(f'   ❌ Tahmin API hatası: {pred_resp.text[:300]}')
        return False

    pred_data = pred_resp.json()
    print(f'   ✅ Tahmin alındı')

    # 3. Yanıt yapısını kontrol et (frontend beklentisi)
    print(f'\n3️⃣ Frontend beklentisi kontrolü:')
    required_fields = ['match_id', 'home_win_probability', 'draw_probability', 'away_win_probability']

    for field in required_fields:
        if field in pred_data:
            print(f'   ✅ {field}: {pred_data[field]}')
        else:
            print(f'   ❌ {field}: EKSIK')
            return False

    # Olasılık toplamı
    total = pred_data['home_win_probability'] + pred_data['draw_probability'] + pred_data['away_win_probability']
    print(f'   ✅ Olasılık toplamı: {total:.4f}')

    # 4. Frontend test URL'i oluştur
    frontend_url = f'http://localhost:5173/matches/{working_match_id}'
    print(f'\n4️⃣ Frontend test URL:')
    print(f'   {frontend_url}')

    # 5. Frontend serverının çalışıp çalışmadığını kontrol et
    print(f'\n5️⃣ Frontend server kontrolü:')
    try:
        frontend_resp = requests.get('http://localhost:5173/', timeout=5)
        if frontend_resp.ok:
            print(f'   ✅ Frontend çalışıyor (5173)')
        else:
            print(f'   ❌ Frontend yanıt vermiyor (5173)')

        # Vite dev server kontrolü
        vite_resp = requests.get('http://127.0.0.1:5173/', timeout=5)
        if vite_resp.ok:
            print(f'   ✅ Vite dev server çalışıyor (127.0.0.1:5173)')
        else:
            print(f'   ❌ Vite dev server yanıt vermiyor')

    except Exception as e:
        print(f'   ❌ Frontend server hatası: {e}')
        return False

    return True, working_match_id

def check_frontend_api_base_url():
    """Frontend'in hangi API URL'ini kullandığını kontrol et"""
    print(f'\n🔍 FRONTEND API KONFIGÜRASYON KONTROLÜ:')

    # client.ts dosyasını kontrol et
    try:
        with open('frontend/src/api/client.ts', 'r', encoding='utf-8') as f:
            content = f.read()

        # API base URL'i bul
        if 'API_BASE_URL' in content:
            lines = content.split('\n')
            for line in lines:
                if 'API_BASE_URL' in line and ('import.meta.env' in line or 'http' in line):
                    print(f'   API URL config: {line.strip()}')

        # Çevre değişkeni kontrolü
        if 'VITE_API_BASE_URL' in content:
            print(f'   ✅ VITE_API_BASE_URL kullanılıyor')
        else:
            print(f'   ℹ️  Sabit URL kullanılıyor olabilir')

    except Exception as e:
        print(f'   ❌ client.ts okunamadı: {e}')

if __name__ == "__main__":
    print("END-TO-END ÇALIŞAN MAÇ TESTİ")
    print("=" * 60)

    result = test_working_match()

    if result and len(result) > 1:
        success, match_id = result
        if success:
            print(f"\n✅ SONUÇ: Backend tamamen çalışıyor")
            print(f"   Test maçı: {match_id}")
            print(f"   Frontend URL: http://localhost:5173/matches/{match_id}")
            print(f"\n🎯 SONRAKI ADIM: Frontend debugging")
            check_frontend_api_base_url()
        else:
            print(f"\n❌ SONUÇ: Backend problemi var")
    else:
        print(f"\n❌ SONUÇ: Test başarısız")
