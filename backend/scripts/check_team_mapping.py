#!/usr/bin/env python3
"""
Takım ID eşleşmesini kontrol etmek için SQLite veritabanını sorgula.
"""

import sqlite3
import sys
from pathlib import Path

def check_team_mapping():
    db_path = Path("football_intelligence.db")
    if not db_path.exists():
        print(f"❌ Database dosyası bulunamadı: {db_path}")
        return False
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Teams tablosunun varlığını kontrol et
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='teams'")
        if not cursor.fetchone():
            print("❌ Teams tablosu bulunamadı")
            return False
            
        # Teams tablosundaki kayıt sayısını kontrol et
        cursor.execute("SELECT COUNT(*) FROM teams")
        count = cursor.fetchone()[0]
        print(f"📊 Teams tablosunda {count} kayıt var")
        
        if count == 0:
            print("⚠️  Teams tablosu boş")
            return True
            
        # Örnek kayıtları göster
        cursor.execute("SELECT id, name, provider_id FROM teams LIMIT 10")
        rows = cursor.fetchall()
        print("\n📋 İlk 10 team kaydı:")
        for row in rows:
            print(f"  UUID: {row[0][:8]}... | Name: {row[1]} | Provider ID: {row[2]}")
            
        # '9826' provider_id'sini arayalım
        cursor.execute("SELECT id, name, provider_id FROM teams WHERE provider_id = ?", ('9826',))
        crystal_palace = cursor.fetchone()
        
        if crystal_palace:
            print(f"\n✅ Crystal Palace (9826) bulundu:")
            print(f"  UUID: {crystal_palace[0]}")
            print(f"  Name: {crystal_palace[1]}")
            print(f"  Provider ID: {crystal_palace[2]}")
        else:
            print(f"\n❌ Provider ID '9826' bulunamadı")
            
        # Provider_id'si olan takım sayısını kontrol et
        cursor.execute("SELECT COUNT(*) FROM teams WHERE provider_id IS NOT NULL AND provider_id != ''")
        provider_count = cursor.fetchone()[0]
        print(f"\n📊 Provider ID'si olan takım sayısı: {provider_count}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Veritabanı hatası: {e}")
        return False

if __name__ == "__main__":
    success = check_team_mapping()
    sys.exit(0 if success else 1)