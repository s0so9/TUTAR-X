#!/usr/bin/env python3
"""
Matches tablosundaki team_id formatlarını kontrol et.
"""

import sqlite3
import sys
from pathlib import Path

def check_matches():
    db_path = Path("football_intelligence.db")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Matches tablosunun varlığını kontrol et
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='matches'")
        if not cursor.fetchone():
            print("❌ Matches tablosu bulunamadı")
            return False
            
        # Matches tablosundaki kayıt sayısını kontrol et
        cursor.execute("SELECT COUNT(*) FROM matches")
        count = cursor.fetchone()[0]
        print(f"📊 Matches tablosunda {count} kayıt var")
        
        if count == 0:
            print("⚠️  Matches tablosu boş")
            return True
            
        # Crystal Palace'ın UUID'sini kullanarak maçlarını arayalım
        crystal_uuid = "b3bd533f-69df-49e9-89fd-133e022ad65f"
        
        # Home takım olarak Crystal Palace maçları
        cursor.execute("""
            SELECT m.id, m.home_team_id, m.away_team_id, m.scheduled_at, m.status
            FROM matches m
            WHERE m.home_team_id = ?
            LIMIT 5
        """, (crystal_uuid,))
        
        home_matches = cursor.fetchall()
        print(f"\n🏠 Crystal Palace home maçları ({len(home_matches)} found):")
        for match in home_matches:
            print(f"  Match ID: {match[0]}")
            print(f"  Home: {match[1][:8]}... | Away: {match[2][:8]}...")
            print(f"  Date: {match[3]} | Status: {match[4]}")
            print()
            
        # Away takım olarak Crystal Palace maçları
        cursor.execute("""
            SELECT m.id, m.home_team_id, m.away_team_id, m.scheduled_at, m.status
            FROM matches m
            WHERE m.away_team_id = ?
            LIMIT 5
        """, (crystal_uuid,))
        
        away_matches = cursor.fetchall()
        print(f"🚌 Crystal Palace away maçları ({len(away_matches)} found):")
        for match in away_matches:
            print(f"  Match ID: {match[0]}")
            print(f"  Home: {match[1][:8]}... | Away: {match[2][:8]}...")
            print(f"  Date: {match[3]} | Status: {match[4]}")
            print()
            
        # Şimdi FotMob provider ID '9826' ile arama yaparsak ne olur?
        print("🔍 Provider ID '9826' ile direct match arama:")
        cursor.execute("""
            SELECT m.id, m.home_team_id, m.away_team_id, m.scheduled_at
            FROM matches m
            WHERE m.home_team_id = '9826' OR m.away_team_id = '9826'
            LIMIT 3
        """)
        
        provider_matches = cursor.fetchall()
        print(f"   Found {len(provider_matches)} matches with direct provider ID")
        for match in provider_matches:
            print(f"     Match: {match[0]} | Home: {match[1]} | Away: {match[2]}")
            
        # Bazı örnek maçların team_id formatlarını inceleyelim
        cursor.execute("""
            SELECT DISTINCT home_team_id, away_team_id
            FROM matches
            LIMIT 10
        """)
        
        sample_ids = cursor.fetchall()
        print(f"\n📝 Örnek team_id formatları:")
        for home_id, away_id in sample_ids:
            print(f"  Home: {home_id[:20]}... | Away: {away_id[:20]}...")
            
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Veritabanı hatası: {e}")
        return False

if __name__ == "__main__":
    success = check_matches()
    sys.exit(0 if success else 1)