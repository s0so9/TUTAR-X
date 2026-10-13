#!/usr/bin/env python3

import requests
import json

def check_frontend_matches_endpoint():
    """Frontend'in /api/v1/matches endpoint'inden aldığı veriyi kontrol et"""

    backend_url = 'http://127.0.0.1:8004'

    print('🔍 Frontend API çağrısını simüle ediyorum...')
    print('='*50)

    # Frontend'in yaptığı gibi maç listesi al
    list_url = f'{backend_url}/api/v1/matches?limit=20'
    print(f'GET {list_url}')

    try:
        resp = requests.get(list_url, timeout=10)
        print(f'Status: {resp.status_code}')

        if resp.ok:
            data = resp.json()
            matches = data['matches']

            print(f'✅ {len(matches)} maç alındı')
            print(f'Development data: {data.get("is_development_data", False)}')

            # İlk birkaç maçın detaylarını göster
            print(f'\n📋 İlk 5 maç detayları:')
            for i, match in enumerate(matches[:5], 1):
                match_id = match['id']
                status = match['status']
                scheduled_at = match.get('scheduled_at', 'N/A')

                # Takım isimleri
                home_team = match.get('home_team')
                away_team = match.get('away_team')

                if home_team and away_team:
                    home_name = home_team.get('name', 'N/A')
                    away_name = away_team.get('name', 'N/A')
                else:
                    home_name = f"ID: {match['home_team_id']}"
                    away_name = f"ID: {match['away_team_id']}"

                print(f'{i}. {match_id}')
                print(f'   {home_name} vs {away_name}')
                print(f'   Status: {status} | Tarih: {scheduled_at}')

                # Bu maç Carshalton Athletic - St Albans mu?
                if ('carshalton' in home_name.lower() or 'carshalton' in away_name.lower() or
                    'st albans' in home_name.lower() or 'st albans' in away_name.lower() or
                    'athletic' in home_name.lower() or 'athletic' in away_name.lower()):
                    print(f'   🎯 HEDEF MAÇ BULUNDU!')

                print()

            # Kullanıcının belirttiği ID'yi kontrol et
            problem_id = 'd13431f9-0ce0-46dd-a95b-76d6a9f71be8'
            found_problem_id = any(m['id'] == problem_id for m in matches)

            print(f'🔍 Problemli ID kontrolü:')
            print(f'   ID: {problem_id}')
            print(f'   Listede var mı: {found_problem_id}')

            if not found_problem_id:
                print(f'   ❌ Bu ID frontend maç listesinde YOK')
                print(f'   🤔 Bu ID nereden geliyorsa, şu kaynaklardan olabilir:')
                print(f'      - Eski browser cache/localStorage')
                print(f'      - Farklı API base URL')
                print(f'      - Mock/test verisi')
                print(f'      - URL\'de manuel olarak yazılmış')

            return matches[0] if matches else None

        else:
            print(f'❌ API Hatası: {resp.text[:200]}')
            return None

    except Exception as e:
        print(f'❌ Bağlantı Hatası: {e}')
        return None

def test_match_detail_flow(match_id):
    """Gerçek bir maç ID'siyle match detail flow'unu test et"""

    backend_url = 'http://127.0.0.1:8004'

    print(f'\n🧪 MATCH DETAIL FLOW TEST: {match_id}')
    print('='*50)

    # 1. Match detail endpoint
    print(f'1️⃣ Match detail test:')
    detail_url = f'{backend_url}/api/v1/matches/{match_id}'
    print(f'GET {detail_url}')

    detail_resp = requests.get(detail_url, timeout=10)
    print(f'Status: {detail_resp.status_code}')

    if detail_resp.ok:
        match_data = detail_resp.json()
        match = match_data['match']

        home_team = match.get('home_team')
        away_team = match.get('away_team')

        if home_team and away_team:
            print(f'✅ Takımlar: {home_team["name"]} vs {away_team["name"]}')
        else:
            print(f'✅ Takım ID\'leri: {match["home_team_id"]} vs {match["away_team_id"]}')

        print(f'✅ Status: {match["status"]}')
        print(f'✅ Scheduled: {match.get("scheduled_at", "N/A")}')

        # shouldLoadPrediction kontrol et
        should_load = match["status"] in ['SCHEDULED', 'POSTPONED']
        print(f'✅ shouldLoadPrediction: {should_load}')

        if should_load:
            # 2. Prediction endpoint test
            print(f'\n2️⃣ Prediction endpoint test:')
            pred_url = f'{backend_url}/api/v1/matches/{match_id}/prediction'
            print(f'GET {pred_url}')

            pred_resp = requests.get(pred_url, timeout=30)
            print(f'Status: {pred_resp.status_code}')

            if pred_resp.ok:
                pred_data = pred_resp.json()
                print(f'✅ Prediction başarılı')
                print(f'   match_id: {pred_data.get("match_id", "MISSING")}')
                print(f'   home_win_prob: {pred_data.get("home_win_probability", "MISSING")}')

                return True
            else:
                print(f'❌ Prediction hatası: {pred_resp.text[:200]}')
                return False
        else:
            print(f'ℹ️  Maç SCHEDULED değil, prediction test atlanıyor')
            return True
    else:
        print(f'❌ Match detail hatası: {detail_resp.text[:200]}')
        return False

if __name__ == "__main__":
    print("FRONTEND API ÇAĞRI ANALİZİ")
    print("=" * 60)

    # Frontend matches endpoint'ini test et
    first_match = check_frontend_matches_endpoint()

    if first_match:
        # Gerçek bir maçla flow'u test et
        success = test_match_detail_flow(first_match['id'])

        print(f"\n📊 SONUÇ:")
        if success:
            print(f"✅ API flow tamamen çalışıyor")
            print(f"🎯 Sorun: Frontend'de farklı/yanlış ID kullanılıyor")
            print(f"🔧 Çözüm: ID kaynağını bul ve düzelt")
        else:
            print(f"❌ API flow'da sorun var")
    else:
        print(f"\n❌ SONUÇ: Backend API'den maç verisi alınamıyor")
