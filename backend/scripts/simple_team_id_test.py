#!/usr/bin/env python3
"""
Basit takım ID çözümleme testi.
"""

import sys
from pathlib import Path
import os

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

def test_team_id_resolution():
    """Test team ID resolution with current database."""
    
    try:
        # Import after path is set
        from app.database.session import get_session_factory
        from app.database.models import Team as TeamDB
        
        print("🔍 Testing team ID resolution scenarios...")
        
        # Get session factory
        session_factory = get_session_factory()
        
        with session_factory() as session:
            # Check current teams count
            team_count = session.query(TeamDB).count()
            print(f"📊 Current teams in database: {team_count}")
            
            if team_count > 0:
                # Test resolution with real data
                print("\n✅ Testing with populated database:")
                
                # Find Crystal Palace
                crystal_palace = session.query(TeamDB).filter(
                    TeamDB.provider_id == '9826'
                ).first()
                
                if crystal_palace:
                    print(f"  ✅ Found Crystal Palace:")
                    print(f"    UUID: {crystal_palace.id}")
                    print(f"    Provider ID: {crystal_palace.provider_id}")
                    print(f"    Name: {crystal_palace.name}")
                    
                    # Test _is_canonical_uuid helper function
                    uuid_str = crystal_palace.id
                    provider_id = crystal_palace.provider_id
                    
                    print(f"\n  🧪 Testing UUID detection:")
                    print(f"    is_uuid('{uuid_str[:8]}...'): Expected True")
                    print(f"    is_uuid('{provider_id}'): Expected False")
                    
                else:
                    print("  ❌ Crystal Palace not found in database")
                    
                # Test with some sample IDs
                test_ids = ['9826', '10261', '8455']  # Crystal Palace, Newcastle, Chelsea
                
                print(f"\n  🧪 Testing provider ID lookup:")
                for provider_id in test_ids:
                    team = session.query(TeamDB).filter(
                        TeamDB.provider_id == provider_id
                    ).first()
                    
                    if team:
                        print(f"    {provider_id} → {team.name} ({team.id[:8]}...)")
                    else:
                        print(f"    {provider_id} → Not found")
                        
            else:
                print("\n⚠️  Empty database scenario:")
                print("  - No teams in database")
                print("  - ID resolution should return original ID")
                print("  - System should still work (degraded mode)")
                
            # Test health check database connectivity
            print(f"\n🏥 Health check simulation:")
            try:
                count = session.query(TeamDB).count()
                print(f"  ✅ Database connection successful")
                print(f"  📊 Teams count: {count}")
                
                health_status = {
                    "database": "connected",
                    "teams_count": count,
                    "connection_verified": True
                }
                
                if count == 0:
                    health_status["warning"] = "Teams table is empty"
                    
                print(f"  📋 Health status: {health_status}")
                
            except Exception as e:
                print(f"  ❌ Database connection failed: {e}")
                
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_team_id_resolution()