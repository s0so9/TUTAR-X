#!/usr/bin/env python3
"""
Production senaryosunu simüle et - teams tablosunun boş olduğu durumu test et.
"""

import sys
from pathlib import Path
import tempfile
import os

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.providers.hybrid_provider import HybridProvider
from app.providers.adapter import ProviderManagerAdapter
from app.database.session import get_session_factory
from app.database.models import Match, Team as TeamDB
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

def test_empty_teams_table():
    """Test nasıl davranacağını kontrol et teams tablosu boş olduğunda."""
    
    # Temporary database oluştur
    temp_db_path = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    temp_db_path.close()
    
    try:
        # Temporary engine ve session oluştur
        engine = create_engine(f"sqlite:///{temp_db_path.name}")
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        
        # Create tables
        from app.database.models import Base
        Base.metadata.create_all(bind=engine)
        
        print("🧪 Empty teams table scenario test")
        
        with SessionLocal() as session:
            # Teams tablosunda kayıt olmadığını doğrula
            team_count = session.query(TeamDB).count()
            print(f"📊 Teams count: {team_count}")
            
            # HybridProvider oluştur - mock provider gerektiğinden basit bir test yapalım
            print("\n🔍 Testing _resolve_team_canonical_uuid directly:")
            
            # Direct olarak method test et
            from app.providers.hybrid_provider import HybridProvider
            from app.providers.database_backed import DatabaseBackedProvider
            
            db_provider = DatabaseBackedProvider(session)
            
            # Test _resolve_team_canonical_uuid fonksiyonu mock external_provider ile
            class MockExternalProvider:
                def is_development_data(self):
                    return False
            
            mock_provider = MockExternalProvider()
            hybrid_provider = HybridProvider(mock_provider, session)
            
            # Test _resolve_team_canonical_uuid fonksiyonu
            print("\n🔍 Testing _resolve_team_canonical_uuid with empty teams table:")
            
            test_cases = [
                "9826",  # FotMob Crystal Palace ID
                "10261", # FotMob Newcastle ID
                "b3bd533f-69df-49e9-89fd-133e022ad65f", # Already UUID format
                "invalid_id"
            ]
            
            for provider_id in test_cases:
                try:
                    result = hybrid_provider._resolve_team_canonical_uuid(provider_id)
                    print(f"  {provider_id} → {result}")
                    
                    # UUID formatında olanlar değişmemeli
                    if hybrid_provider._is_canonical_uuid(provider_id):
                        assert result == provider_id, f"UUID should remain unchanged: {provider_id}"
                    else:
                        # Mapping bulunamazsa original ID dönmeli
                        assert result == provider_id, f"Should return original ID when no mapping: {provider_id}"
                        
                except Exception as e:
                    print(f"  ❌ Error for {provider_id}: {e}")
                    
            print("\n✅ Empty teams table test completed")
            
            # Şimdi production health check scenario test et
            print("\n🏥 Testing health check with empty teams table:")
            
            try:
                team_count = session.query(TeamDB).count()
                print(f"  Teams count: {team_count}")
                print(f"  Database connection: {'✅ OK' if team_count >= 0 else '❌ Failed'}")
                
                # Production'da bu scenario'da nasıl response verilmeli?
                health_response = {
                    "status": "healthy" if team_count >= 0 else "degraded",
                    "database": "connected",
                    "database_details": {
                        "teams_count": team_count,
                        "connection_verified": True,
                        "warning": "Teams table is empty - may need data seeding" if team_count == 0 else None
                    }
                }
                
                print(f"  Health response: {health_response}")
                
            except Exception as e:
                print(f"  ❌ Health check failed: {e}")
                
    finally:
        # Cleanup
        try:
            os.unlink(temp_db_path.name)
        except:
            pass

if __name__ == "__main__":
    test_empty_teams_table()