#!/usr/bin/env python3

import requests
import json

def search_teams_in_matches():
    """Backend'de Carshalton ve St Albans takımlarını ara"""

    backend_url = 'http://127.0.0.1:8004'

    print('🔍 Carshalton Athletic ve St Albans maçı aranıyor...')
    print('='*50)

    # Tüm maçları al (takım isimleri ile)
    resp = requests.get(f'{backend_url}/api/v1/matches?limit=100', timeout=15)

    if not resp.ok:
        print(f'❌ API Hatası: {resp.status_code}')
        return None

    data = resp.json()
    matches = data['matches']

    print(f'📊 Toplam {len(matches)} maç taranacak...')

    # Carshalton ve St Albans takımlarını ara
    target_keywords = ['carshalton', 'st albans', 'st. albans', 'athletic']
    found_matches = []

    for match in matches:
        home_team = match.get('home_team')
        away_team = match.get('away_team')

        if home_team and away_team:
            home_name = home_team.get('name', '').lower()
            away_name = away_team.get('name', '').lower()

            # Anahtar kelimelerin herhangi birini ara
            found = False
            for keyword in target_keywords:
                if keyword in home_name or keyword in away_name:
                    found = True
                    break

            if found:
                found_matches.append(match)

    if found_matches:
        print(f'✅ {len(found_matches)} potansiyel maç bulundu:')
        print()

        for i, match in enumerate(found_matches, 1):
            home_name = match['home_team']['name']
            away_name = match['away_team']['name']

            print(f'{i}. ID: {match["id"]}')
            print(f'   Takımlar: {home_name} vs {away_name}')
            print(f'   Status: {match["status"]}')
            print(f'   Tarih: {match.get("scheduled_at", "N/A")}')

            # Bu maç Carshalton Athletic - St Albans'a ne kadar benziyor?
            similarity_score = 0
            if 'carshalton' in home_name.lower() and 'athletic' in home_name.lower():
                similarity_score += 50
            if 'st albans' in away_name.lower() or 'st. albans' in away_name.lower():
                similarity_score += 50

            if similarity_score > 0:
                print(f'   🎯 Benzerlik: {similarity_score}%')

            print()

        return found_matches[0] if found_matches else None
    else:
        print('❌ Carshalton/St Albans ile ilgili maç bulunamadı')

        # Takım isimlerinin örneklerini göster
        print('\n📋 Mevcut takım isimlerinden örnekler:')
        sample_teams = set()

        for match in matches[:20]:
            home_team = match.get('home_team')
            away_team = match.get('away_team')

            if home_team and home_team.get('name'):
                sample_teams.add(home_team['name'])
            if away_team and away_team.get('name'):
                sample_teams.add(away_team['name'])

            if len(sample_teams) >= 20:
                break

        for i, team_name in enumerate(sorted(list(sample_teams))[:10], 1):
            print(f'{i}. {team_name}')

        return None

def test_problematic_id():
    """Problemli ID'nin gerçekten 404 döndürdüğünü doğrula"""

    backend_url = 'http://127.0.0.1:8004'
    problem_id = 'd13431f9-0ce0-46dd-a95b-76d6a9f71be8'

    print(f'\n🧪 PROBLEMLİ ID TEST: {problem_id}')
    print('='*50)

    # Match detail
    detail_resp = requests.get(f'{backend_url}/api/v1/matches/{problem_id}', timeout=10)
    print(f'Match detail status: {detail_resp.status_code}')

    if detail_resp.status_code == 404:
        print(f'✅ Doğrulandı: Bu ID backend\'de yok')
        return True
    else:
        print(f'❌ Beklenmedik: Bu ID aslında mevcut!')
        if detail_resp.ok:
            data = detail_resp.json()
            match = data['match']
            home_team = match.get('home_team', {}).get('name') if match.get('home_team') else f"ID: {match['home_team_id']}"
            away_team = match.get('away_team', {}).get('name') if match.get('away_team') else f"ID: {match['away_team_id']}"
            print(f'   Takımlar: {home_team} vs {away_team}')
            print(f'   Status: {match["status"]}')
        return False

if __name__ == "__main__":
    print("CARSHALTON ATHLETIC - ST ALBANS MAÇ ARAMA")
    print("=" * 60)

    # Carshalton/St Albans maçını ara
    found_match = search_teams_in_matches()

    # Problemli ID'yi test et
    id_not_exists = test_problematic_id()

    print(f"\n📊 SONUÇ ANALİZİ:")

    if found_match:
        print(f"✅ Carshalton/St Albans tipi maç bulundu: {found_match['id']}")
        print(f"   Bu ID frontend'de kullanılmalı")
    else:
        print(f"❌ Carshalton/St Albans maçı backend'de yok")
        print(f"   Kullanıcı yanlış/eski veri kullanıyor olabilir")

    if id_not_exists:
        print(f"✅ Problemli ID (d13431f9...) gerçekten backend'de yok")
        print(f"   🎯 KÖK NEDEN: Frontend yanlış/eski ID kullanıyor")
    else:
        print(f"❌ Problemli ID aslında backend'de mevcut - başka bir sorun var")

    print(f"\n🔧 ÖNERİLEN ÇÖZÜM:")
    print(f"   1. Kullanıcı browser cache'ini temizlesin")
    print(f"   2. Frontend'den güncel maç listesini alsın (/matches)")
    print(f"   3. Doğru maç ID'siyle detay sayfasını açsın")
