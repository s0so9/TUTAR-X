"""Tarihsel maç verilerini FotMob'dan çek ve veritabanına kaydet.

Arsenal ve Leeds gibi takımlar için yeterli geçmiş veri sağlamak üzere
2024 sezonundan tamamlanmış maçları çeker.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import date, datetime, timedelta
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from app.config import Settings
from app.providers.fotmob import FotMobFootballProvider
from app.ingestion.service import IngestionService

def main():
    print("=" * 80)
    print("HISTORICAL MATCH DATA INGESTION")
    print("=" * 80)
    
    # DB bağlantısı
    from app.config import Settings as AppSettings
    settings = AppSettings()
    db_path = os.path.join(os.path.dirname(__file__), '..', 'football_intelligence.db')
    engine = create_engine(f'sqlite:///{db_path}')
    Session = sessionmaker(bind=engine)
    
    # FotMob provider
    provider = FotMobFootballProvider(
        base_url=settings.fotmob_base_url,
        timeout_seconds=settings.provider_timeout_seconds
    )
    
    # Ingestion service
    ingestion = IngestionService(Session)
    
    # Tarih aralıkları - geçmiş 6 ay boyunca her hafta
    end_date = date.today()
    start_date = end_date - timedelta(days=180)  # 6 ay geriye
    
    print(f"\nTarih araligi: {start_date} - {end_date}")
    print(f"FotMob provider kullaniliyor...")
    
    # Her ay için maçları çek (performans için)
    current = start_date
    total_ingested = 0
    
    while current < end_date:
        # Bir aylık aralık
        range_end = min(current + timedelta(days=30), end_date)
        
        print(f"\n{current} - {range_end} araligi cekiliyor...")
        
        try:
            # FotMob'dan maçları çek
            matches = provider.get_matches(
                from_date=current,
                to_date=range_end
            )
            
            if not matches:
                print(f"  Info: Mac bulunamadi")
                current = range_end + timedelta(days=1)
                continue
            
            print(f"  OK: {len(matches)} mac cekildi")
            
            # Yalnızca finished maçları filtrele
            finished_matches = [m for m in matches if m.status and m.status.lower() == 'finished']
            print(f"  OK: {len(finished_matches)} finished mac")
            
            if finished_matches:
                # Veritabanına kaydet
                result = ingestion.ingest_provider_matches(finished_matches)
                
                if result.success:
                    print(f"  OK: {result.entity_count} mac ingested")
                    total_ingested += result.entity_count
                else:
                    print(f"  ERROR: Ingestion error: {result.errors}")
            
        except Exception as e:
            print(f"  ERROR: {e}")
        
        # Bir sonraki aralığa geç
        current = range_end + timedelta(days=1)
    
    print(f"\n" + "=" * 80)
    print(f"SUMMARY")
    print("=" * 80)
    print(f"Toplam ingested mac: {total_ingested}")
    print(f"Tarih araligi: {start_date} - {end_date}")
    
    # Arsenal ve Leeds kontrolü
    print(f"\n" + "=" * 80)
    print("ARSENAL AND LEEDS CHECK")
    print("=" * 80)
    
    session = Session()
    
    from app.database.models import Team, Match
    from sqlalchemy import or_, and_
    
    # Arsenal ve Leeds
    arsenal = session.query(Team).filter(Team.provider_id == '9825').first()
    leeds = session.query(Team).filter(Team.provider_id == '8463').first()
    
    if arsenal:
        arsenal_finished = session.query(Match).filter(
            or_(
                Match.home_team_id == arsenal.id,
                Match.away_team_id == arsenal.id
            ),
            Match.status == 'MatchStatus.FINISHED'
        ).count()
        print(f"\nArsenal: {arsenal_finished} finished mac")
    
    if leeds:
        leeds_finished = session.query(Match).filter(
            or_(
                Match.home_team_id == leeds.id,
                Match.away_team_id == leeds.id
            ),
            Match.status == 'MatchStatus.FINISHED'
        ).count()
        print(f"Leeds: {leeds_finished} finished mac")
    
    session.close()

if __name__ == "__main__":
    main()
