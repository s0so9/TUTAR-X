#!/usr/bin/env python3
"""Maç kimliği uyuşmazlığı araştırması."""

import sqlite3

def main():
    conn = sqlite3.connect('football_intelligence.db')
    cursor = conn.cursor()

    print("=" * 60)
    print("MAÇ KİMLİĞİ UYUŞMAZLIĞI ARAŞTIRMASI")
    print("=" * 60)

    # Beklenen Arsenal-Leeds ID'sini ara
    expected_id = 'c2744bd9-5915-440c-98db-97167177a9bb'
    cursor.execute('SELECT home_team_id, away_team_id, scheduled_at FROM matches WHERE id = ?', (expected_id,))
    expected_match = cursor.fetchone()

    if expected_match:
        home_id, away_id, scheduled_at = expected_match
        cursor.execute('SELECT name FROM teams WHERE id = ?', (home_id,))
        home_name = cursor.fetchone()
        cursor.execute('SELECT name FROM teams WHERE id = ?', (away_id,))
        away_name = cursor.fetchone()

        print(f'✅ Beklenen Arsenal-Leeds ID bulundu: {expected_id}')
        print(f'  Home: {home_name[0] if home_name else "Unknown"} ({home_id})')
        print(f'  Away: {away_name[0] if away_name else "Unknown"} ({away_id})')
        print(f'  Date: {scheduled_at}')
    else:
        print(f'❌ Beklenen Arsenal-Leeds ID bulunamadı: {expected_id}')

    # Mevcut test scriptindeki ID'yi kontrol et
    current_test_id = 'fcca0ac7-8551-41f1-922e-38ae3c97fce0'
    cursor.execute('SELECT home_team_id, away_team_id, scheduled_at FROM matches WHERE id = ?', (current_test_id,))
    current_match = cursor.fetchone()

    print(f'\nMevcut test ID: {current_test_id}')
    if current_match:
        home_id, away_id, scheduled_at = current_match
        cursor.execute('SELECT name FROM teams WHERE id = ?', (home_id,))
        home_name = cursor.fetchone()
        cursor.execute('SELECT name FROM teams WHERE id = ?', (away_id,))
        away_name = cursor.fetchone()

        print(f'  Home: {home_name[0] if home_name else "Unknown"} ({home_id})')
        print(f'  Away: {away_name[0] if away_name else "Unknown"} ({away_id})')
        print(f'  Date: {scheduled_at}')
    else:
        print('  ❌ Mevcut test ID bulunamadı')

    # Arsenal ve Leeds takım ID'lerini bul
    print('\nArsenal/Leeds takım arama:')
    cursor.execute("SELECT id, name FROM teams WHERE name LIKE '%Arsenal%' OR name LIKE '%Leeds%'")
    arsenal_leeds_teams = cursor.fetchall()

    if arsenal_leeds_teams:
        for team_id, name in arsenal_leeds_teams:
            print(f'  {team_id}: {name}')
    else:
        print('  ❌ Arsenal/Leeds takımları bulunamadı')

    # Gerçek Arsenal-Leeds maçlarını bul (isim bazlı)
    print('\nArsenal-Leeds maçlarını arama:')
    cursor.execute("""
    SELECT m.id, m.scheduled_at, h.name as home_name, a.name as away_name
    FROM matches m
    JOIN teams h ON m.home_team_id = h.id
    JOIN teams a ON m.away_team_id = a.id
    WHERE (h.name LIKE '%Arsenal%' AND a.name LIKE '%Leeds%')
       OR (h.name LIKE '%Leeds%' AND a.name LIKE '%Arsenal%')
    ORDER BY m.scheduled_at DESC
    LIMIT 5
    """)

    arsenal_leeds_matches = cursor.fetchall()
    if arsenal_leeds_matches:
        for match_id, date, home, away in arsenal_leeds_matches:
            print(f'  {match_id}: {home} vs {away} ({date})')
    else:
        print('  ❌ Arsenal-Leeds maçı bulunamadı')

    conn.close()

if __name__ == '__main__':
    main()
