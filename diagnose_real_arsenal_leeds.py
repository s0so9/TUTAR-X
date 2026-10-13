"""Gerçek Arsenal (Provider ID 9825) ve Leeds United için diagnose."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from sqlalchemy import create_engine, func, and_, or_
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone

from app.database.models import Match, Team

# Backend klasöründeki DB'yi kullan
db_path = os.path.join(os.path.dirname(__file__), 'backend', 'football_intelligence.db')
engine = create_engine(f'sqlite:///{db_path}')
Session = sessionmaker(bind=engine)
session = Session()

print("=" * 80)
print("GERÇEK ARSENAL (9825) - LEEDS UNITED (8463) TAHMİN ANALİZİ")
print("=" * 80)

# Gerçek takımları al
arsenal = session.query(Team).filter(Team.provider_id == '9825').first()
leeds = session.query(Team).filter(Team.provider_id == '8463').first()

if not arsenal or not leeds:
    print("HATA: Takımlar bulunamadı!")
    exit(1)

print(f"\n✅ Arsenal: {arsenal.name} (UUID: {arsenal.id})")
print(f"✅ Leeds: {leeds.name} (UUID: {leeds.id})")

# Hedef maçı bul
target_match = session.query(Match).filter(
    and_(
        Match.home_team_id == arsenal.id,
        Match.away_team_id == leeds.id
    )
).first()

if target_match:
    print(f"\n✅ Hedef maç bulundu:")
    print(f"   Match ID: {target_match.id}")
    print(f"   Scheduled: {target_match.scheduled_at}")
    print(f"   Status: {target_match.status}")
    match_date = target_match.scheduled_at
else:
    print(f"\n❌ Arsenal - Leeds maçı bulunamadı")
    # Varsayılan tarih kullan
    match_date = datetime(2026, 10, 10, 11, 30, 0, tzinfo=timezone.utc)
    print(f"   Varsayılan tarih kullanılıyor: {match_date}")

print(f"\n" + "=" * 80)
print("ARSENAL GEÇMİŞ MAÇLARI")
print("=" * 80)

# Arsenal'in TÜM maçları
arsenal_all = session.query(Match).filter(
    or_(
        Match.home_team_id == arsenal.id,
        Match.away_team_id == arsenal.id
    )
).all()

print(f"\nToplam maç: {len(arsenal_all)}")

# Bitmiş maçlar
arsenal_finished = [m for m in arsenal_all if str(m.status) == 'MatchStatus.FINISHED' and m.scheduled_at < match_date]
print(f"Bitmiş maç (hedef tarihten önce): {len(arsenal_finished)}")

# Scheduled maçlar
arsenal_scheduled = [m for m in arsenal_all if str(m.status) == 'MatchStatus.SCHEDULED']
print(f"Scheduled maç: {len(arsenal_scheduled)}")

# İlk 5 bitmiş maçı detaylı göster
if arsenal_finished:
    print(f"\nİlk 5 bitmiş maç:")
    for m in sorted(arsenal_finished, key=lambda x: x.scheduled_at, reverse=True)[:5]:
        is_home = m.home_team_id == arsenal.id
        print(f"  {m.scheduled_at.date()}: {'Home' if is_home else 'Away'}, "
              f"Score: {m.home_score}-{m.away_score}, Status: {m.status}")

print(f"\n" + "=" * 80)
print("LEEDS UNITED GEÇMİŞ MAÇLARI")
print("=" * 80)

leeds_all = session.query(Match).filter(
    or_(
        Match.home_team_id == leeds.id,
        Match.away_team_id == leeds.id
    )
).all()

print(f"\nToplam maç: {len(leeds_all)}")

leeds_finished = [m for m in leeds_all if str(m.status) == 'MatchStatus.FINISHED' and m.scheduled_at < match_date]
print(f"Bitmiş maç (hedef tarihten önce): {len(leeds_finished)}")

leeds_scheduled = [m for m in leeds_all if str(m.status) == 'MatchStatus.SCHEDULED']
print(f"Scheduled maç: {len(leeds_scheduled)}")

if leeds_finished:
    print(f"\nİlk 5 bitmiş maç:")
    for m in sorted(leeds_finished, key=lambda x: x.scheduled_at, reverse=True)[:5]:
        is_home = m.home_team_id == leeds.id
        print(f"  {m.scheduled_at.date()}: {'Home' if is_home else 'Away'}, "
              f"Score: {m.home_score}-{m.away_score}, Status: {m.status}")

print(f"\n" + "=" * 80)
print("KÖK NEDEN ANALİZİ")
print("=" * 80)

min_required = 3
print(f"\nMinimum gereksinim: {min_required} bitmiş maç")
print(f"Arsenal geçmiş: {len(arsenal_finished)} maç")
print(f"Leeds geçmiş: {len(leeds_finished)} maç")

if len(arsenal_finished) < min_required:
    print(f"\n❌ Arsenal için yetersiz geçmiş veri ({len(arsenal_finished)} < {min_required})")
else:
    print(f"\n✅ Arsenal için yeterli geçmiş veri ({len(arsenal_finished)} >= {min_required})")

if len(leeds_finished) < min_required:
    print(f"❌ Leeds için yetersiz geçmiş veri ({len(leeds_finished)} < {min_required})")
else:
    print(f"✅ Leeds için yeterli geçmiş veri ({len(leeds_finished)} >= {min_required})")

# Eğer hedef maç varsa, route bilgisini göster
if target_match:
    print(f"\n" + "=" * 80)
    print("FRONTEND ROUTE BİLGİSİ")
    print("=" * 80)
    print(f"\nMatch UUID: {target_match.id}")
    print(f"Expected route: /matches/{target_match.id}")
    print(f"Expected API endpoint: /api/v1/matches/{target_match.id}/prediction")

session.close()
