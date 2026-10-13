"""Arsenal - Leeds United maçı için tahmin hatasını diagnose et."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from sqlalchemy import create_engine, select, func, and_, or_
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone
import json

from app.database.models import Match, Team, Competition
from app.config import Settings

settings = Settings()
# Backend klasöründeki DB'yi kullan
db_path = os.path.join(os.path.dirname(__file__), 'backend', 'football_intelligence.db')
engine = create_engine(f'sqlite:///{db_path}')
Session = sessionmaker(bind=engine)

def main():
    session = Session()

    print("=" * 80)
    print("ARSENAL - LEEDS UNITED TAHMIN HATASI DİAGNOSTİK")
    print("=" * 80)

    # 1. Arsenal ve Leeds United takımlarını bul
    print("\n1. TAKIMLARI BUL")
    print("-" * 80)

    arsenal = session.query(Team).filter(
        or_(
            Team.name.ilike('%arsenal%'),
            Team.provider_id.in_(['9825', 'arsenal'])
        )
    ).first()

    leeds = session.query(Team).filter(
        or_(
            Team.name.ilike('%leeds%'),
            Team.provider_id.in_(['8463', 'leeds'])
        )
    ).first()

    if arsenal:
        print(f"\nArsenal bulundu:")
        print(f"  Canonical UUID: {arsenal.id}")
        print(f"  Name: {arsenal.name}")
        print(f"  Provider ID: {arsenal.provider_id}")
        print(f"  Provider Source ID: {arsenal.provider_source_id}")
    else:
        print("\n❌ Arsenal bulunamadı!")

    if leeds:
        print(f"\nLeeds United bulundu:")
        print(f"  Canonical UUID: {leeds.id}")
        print(f"  Name: {leeds.name}")
        print(f"  Provider ID: {leeds.provider_id}")
        print(f"  Provider Source ID: {leeds.provider_source_id}")
    else:
        print("\n❌ Leeds United bulunamadı!")

    if not arsenal or not leeds:
        print("\n❌ Her iki takım da bulunamadığı için devam edilemiyor.")
        return

    # 2. Arsenal - Leeds maçını bul
    print("\n2. HEDEF MAÇI BUL")
    print("-" * 80)

    target_match = session.query(Match).filter(
        and_(
            Match.home_team_id == arsenal.id,
            Match.away_team_id == leeds.id,
            Match.status == 'scheduled'
        )
    ).first()

    if target_match:
        print(f"\nHedef maç bulundu:")
        print(f"  Match ID: {target_match.id}")
        print(f"  Home Team ID: {target_match.home_team_id}")
        print(f"  Away Team ID: {target_match.away_team_id}")
        print(f"  Scheduled: {target_match.scheduled_at}")
        print(f"  Status: {target_match.status}")
        print(f"  Provider Source ID: {target_match.provider_source_id}")
        print(f"  Provider Match ID: {target_match.provider_match_id}")
    else:
        print("\n❌ Arsenal - Leeds maçı bulunamadı!")
        print("\nAlternatif: Diğer scheduled maçlar:")
        alt_matches = session.query(Match).filter(
            or_(
                Match.home_team_id == arsenal.id,
                Match.away_team_id == leeds.id
            )
        ).limit(3).all()
        for m in alt_matches:
            print(f"  {m.id}: status={m.status}, scheduled={m.scheduled_at}")

    # 3. Arsenal için geçmiş maçları say
    print("\n3. ARSENAL GEÇMİŞ MAÇLARI")
    print("-" * 80)

    if target_match:
        match_date = target_match.scheduled_at
    else:
        match_date = datetime(2026, 10, 10, 11, 30, 0, tzinfo=timezone.utc)

    print(f"Hedef tarih: {match_date}")

    # Arsenal'in tüm maçları
    arsenal_total = session.query(func.count(Match.id)).filter(
        or_(
            Match.home_team_id == arsenal.id,
            Match.away_team_id == arsenal.id
        )
    ).scalar()

    # Arsenal'in bitmiş maçları (hedef tarihten önce)
    arsenal_finished = session.query(func.count(Match.id)).filter(
        or_(
            Match.home_team_id == arsenal.id,
            Match.away_team_id == arsenal.id
        ),
        Match.status == 'finished',
        Match.scheduled_at < match_date
    ).scalar()

    print(f"\nArsenal (UUID: {arsenal.id}):")
    print(f"  Toplam maç sayısı: {arsenal_total}")
    print(f"  Bitmiş maç sayısı (hedef tarihten önce): {arsenal_finished}")

    # İlk 3 bitmiş maçı göster
    sample_arsenal = session.query(Match).filter(
        or_(
            Match.home_team_id == arsenal.id,
            Match.away_team_id == arsenal.id
        ),
        Match.status == 'finished',
        Match.scheduled_at < match_date
    ).order_by(Match.scheduled_at.desc()).limit(3).all()

    print(f"\n  İlk 3 bitmiş maç:")
    for m in sample_arsenal:
        is_home = m.home_team_id == arsenal.id
        print(f"    {m.scheduled_at.date()}: {'Home' if is_home else 'Away'}, "
              f"Score: {m.home_score}-{m.away_score}, Status: {m.status}")

    # 4. Leeds için geçmiş maçları say
    print("\n4. LEEDS UNITED GEÇMİŞ MAÇLARI")
    print("-" * 80)

    leeds_total = session.query(func.count(Match.id)).filter(
        or_(
            Match.home_team_id == leeds.id,
            Match.away_team_id == leeds.id
        )
    ).scalar()

    leeds_finished = session.query(func.count(Match.id)).filter(
        or_(
            Match.home_team_id == leeds.id,
            Match.away_team_id == leeds.id
        ),
        Match.status == 'finished',
        Match.scheduled_at < match_date
    ).scalar()

    print(f"\nLeeds United (UUID: {leeds.id}):")
    print(f"  Toplam maç sayısı: {leeds_total}")
    print(f"  Bitmiş maç sayısı (hedef tarihten önce): {leeds_finished}")

    sample_leeds = session.query(Match).filter(
        or_(
            Match.home_team_id == leeds.id,
            Match.away_team_id == leeds.id
        ),
        Match.status == 'finished',
        Match.scheduled_at < match_date
    ).order_by(Match.scheduled_at.desc()).limit(3).all()

    print(f"\n  İlk 3 bitmiş maç:")
    for m in sample_leeds:
        is_home = m.home_team_id == leeds.id
        print(f"    {m.scheduled_at.date()}: {'Home' if is_home else 'Away'}, "
              f"Score: {m.home_score}-{m.away_score}, Status: {m.status}")

    # 5. Provider ID ile karışıklık kontrolü
    print("\n5. PROVIDER ID vs CANONICAL UUID KONTROL")
    print("-" * 80)

    # Provider ID'lerle yanlış sorgu yapılıyor mu?
    wrong_arsenal = session.query(func.count(Match.id)).filter(
        or_(
            Match.home_team_id == arsenal.provider_id,
            Match.away_team_id == arsenal.provider_id
        )
    ).scalar()

    wrong_leeds = session.query(func.count(Match.id)).filter(
        or_(
            Match.home_team_id == leeds.provider_id,
            Match.away_team_id == leeds.provider_id
        )
    ).scalar()

    print(f"\nProvider ID ile yanlış sorgu testi:")
    print(f"  Arsenal provider_id ({arsenal.provider_id}) ile maç sayısı: {wrong_arsenal}")
    print(f"  Leeds provider_id ({leeds.provider_id}) ile maç sayısı: {wrong_leeds}")

    if wrong_arsenal > 0 or wrong_leeds > 0:
        print("  ⚠️  Provider ID'ler yanlışlıkla team_id olarak kullanılıyor olabilir!")

    # 6. Özet
    print("\n6. ÖZET ve KÖK NEDEN ANALİZİ")
    print("-" * 80)

    min_required = 3

    print(f"\nMinimum gereksinim: {min_required} bitmiş maç")
    print(f"Arsenal geçmiş: {arsenal_finished} maç")
    print(f"Leeds geçmiş: {leeds_finished} maç")

    if arsenal_finished < min_required:
        print(f"\n❌ KÖK NEDEN: Arsenal için yetersiz geçmiş veri ({arsenal_finished} < {min_required})")

    if leeds_finished < min_required:
        print(f"❌ KÖK NEDEN: Leeds için yetersiz geçmiş veri ({leeds_finished} < {min_required})")

    if arsenal_finished >= min_required and leeds_finished >= min_required:
        print(f"\n✅ Her iki takım için yeterli geçmiş veri var!")
        print("   Sorun başka bir yerde olmalı (feature hesaplama, API routing, vb.)")

    # 7. Match durumları dağılımı
    print("\n7. MATCH DURUM DAĞILIMI")
    print("-" * 80)

    all_statuses = session.query(Match.status, func.count(Match.id)).group_by(Match.status).all()
    print("\nTüm maçların durum dağılımı:")
    for status, count in all_statuses:
        print(f"  {status}: {count}")

    session.close()

if __name__ == "__main__":
    main()
