#!/usr/bin/env python3

import requests

def check_competition_mismatch():
    """Competition ID ve maç verisi arasındaki uyumsuzluğu kontrol et"""

    backend_url = 'http://127.0.0.1:8003'
    match_id = 'a0872be9-d188-41fd-96b5-1023a8cef0f8'  # Burgess Hill vs Aveley

    print('🔍 COMPETITION UYUMSUZLUĞU ANALİZİ')
    print('='*50)

    # Match detail - gerçek competition_id
    detail_resp = requests.get(f'{backend_url}/api/v1/matches/{match_id}', timeout=10)
    if detail_resp.ok:
        match = detail_resp.json()['match']
        competition_id = match['competition_id']

        print(f'📋 Maç: {match["home_team"]["name"]} vs {match["away_team"]["name"]}')
        print(f'📋 Competition ID: {competition_id}')

        # Bu takımlar gerçek Premier League takımı mı?
        home_team = match["home_team"]["name"]
        away_team = match["away_team"]["name"]

        real_pl_teams = [
            'Arsenal', 'Chelsea', 'Liverpool', 'Manchester City', 'Manchester United',
            'Tottenham', 'Newcastle', 'Brighton', 'West Ham', 'Aston Villa',
            'Crystal Palace', 'Fulham', 'Wolves', 'Everton', 'Brentford',
            'Nottingham Forest', 'Bournemouth', 'Sheffield United', 'Burnley', 'Luton'
        ]

        is_real_pl = any(team in home_team for team in real_pl_teams) or any(team in away_team for team in real_pl_teams)

        print(f'📋 Gerçek PL takımı: {is_real_pl}')
        print(f'📋 Takım seviyeleri: {home_team} - muhtemelen alt lig')
        print(f'📋 Takım seviyeleri: {away_team} - muhtemelen alt lig')

        if not is_real_pl:
            print('🚨 SORUN BULUNDU: Premier League olmayan takımlar PL ID\'si kullanıyor')

            # Diğer maçları kontrol et
            print(f'\n🔍 AYNI COMPETITION ID\'YE SAHİP DİĞER MAÇLAR:')
            matches_resp = requests.get(f'{backend_url}/api/v1/matches?limit=20', timeout=10)
            if matches_resp.ok:
                all_matches = matches_resp.json()['matches']
                same_comp_matches = [m for m in all_matches if m.get('competition_id') == competition_id]

                print(f'Aynı competition_id ({competition_id}) ile {len(same_comp_matches)} maç')

                for i, m in enumerate(same_comp_matches[:5], 1):
                    home = m.get('home_team', {}).get('name', f"ID: {m['home_team_id']}")
                    away = m.get('away_team', {}).get('name', f"ID: {m['away_team_id']}")
                    print(f'   {i}. {home} vs {away}')

                    # Bu takımlar gerçek PL takımı mı?
                    is_real_pl_match = any(team in home for team in real_pl_teams) or any(team in away for team in real_pl_teams)
                    if not is_real_pl_match:
                        print(f'      ❌ PL değil: {home}, {away}')

    # Competition API - sabit eşleştirme
    comp_resp = requests.get(f'{backend_url}/api/v1/competitions', timeout=10)
    if comp_resp.ok:
        competitions = comp_resp.json()['competitions']

        print(f'\n📋 SABIT COMPETITION MAPPING:')
        for comp in competitions:
            print(f'   {comp["id"]}: "{comp["name"]}" ({comp.get("country", "N/A")})')

        # Problemli ID
        problem_comp = next((c for c in competitions if c['id'] == 'd13431f9-0ce0-46dd-a95b-76d6a9f71be8'), None)
        if problem_comp:
            print(f'\n🚨 PROBLEMLİ EŞLEŞTIRME:')
            print(f'   ID: {problem_comp["id"]}')
            print(f'   Sabit İsim: "{problem_comp["name"]}"')
            print(f'   Gerçek Kullanım: Alt lig maçları (Burgess Hill, Aveley, vb.)')

if __name__ == "__main__":
    check_competition_mismatch()
