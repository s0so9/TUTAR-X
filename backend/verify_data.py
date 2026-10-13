#!/usr/bin/env python3
"""Arsenal-Leeds veri doğrulaması."""

import sqlite3
from datetime import datetime

def main():
    conn = sqlite3.connect('football_intelligence.db')
    cursor = conn.cursor()

    # Arsenal ve Leeds için maç verilerini kontrol et
    target_match_id = 'fcca0ac7-8551-41f1-922e-38ae3c97fce0'

    # Hedef maçı al
    cursor.execute('SELECT home_team_id, away_team_id, scheduled_at FROM matches WHERE id = ?', (target_match_id,))
    result = cursor.fetchone()

    if not result:
        print('❌ Hedef maç bulunamadı')
        return

    home_team_id, away_team_id, scheduled_at = result
    print(f'✅ Hedef maç bulundu: {scheduled_at}')
    print(f'  Home team: {home_team_id}')
    print(f'  Away team: {away_team_id}')
    print()

    # Arsenal maçları (hedef maçtan önce, tamamlanmış)
    query = 'SELECT COUNT(*) FROM matches WHERE (home_team_id = ? OR away_team_id = ?) AND scheduled_at < ? AND status = ?'
    cursor.execute(query, (home_team_id, home_team_id, scheduled_at, 'FINISHED'))
    arsenal_matches = cursor.fetchone()[0]
    print(f'Arsenal tamamlanmış maçlar (hedef maçtan önce): {arsenal_matches}')

    # Leeds maçları
    cursor.execute(query, (away_team_id, away_team_id, scheduled_at, 'FINISHED'))
    leeds_matches = cursor.fetchone()[0]
    print(f'Leeds tamamlanmış maçlar (hedef maçtan önce): {leeds_matches}')

    # Min sample size kontrolü
    min_sample_size = 3
    arsenal_ok = arsenal_matches >= min_sample_size
    leeds_ok = leeds_matches >= min_sample_size

    print()
    print(f'Min sample size gereksinimi: {min_sample_size}')
    print(f'Arsenal durumu: {"✅" if arsenal_ok else "❌"} ({arsenal_matches} >= {min_sample_size})')
    print(f'Leeds durumu: {"✅" if leeds_ok else "❌"} ({leeds_matches} >= {min_sample_size})')

    if arsenal_ok and leeds_ok:
        print('✅ Her iki takım da min_sample_size gereksinimini karşılıyor')
    else:
        print('❌ Min_sample_size gereksinimi karşılanmıyor')

    # Skor bütünlüğü kontrolü
    print()
    cursor.execute('SELECT COUNT(*) FROM matches WHERE status = ? AND (home_score IS NULL OR away_score IS NULL)', ('FINISHED',))
    missing_scores = cursor.fetchone()[0]
    print(f'Tamamlanmış maçlarda eksik skor: {missing_scores}')

    if missing_scores == 0:
        print('✅ Tamamlanmış maçlarda skor bütünlüğü tamam')
    else:
        print('⚠️ Bazı tamamlanmış maçlarda skor bilgisi eksik')

    conn.close()

if __name__ == '__main__':
    main()
