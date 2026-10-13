#!/usr/bin/env python3
"""
Debug HybridProvider behavior
"""

import sys
import os
os.chdir('backend')
sys.path.insert(0, '.')

from app.providers.hybrid_provider import HybridProvider
from app.providers.adapter import ProviderManagerAdapter
from app.providers.manager import ProviderManager
from app.providers import ProviderCache, FotMobFootballProvider
from app.database.session import SessionLocal
from app.config import settings

def test_hybrid_provider():
    """Test HybridProvider to see why it fails"""

    # Create database session
    db_session = SessionLocal()

    try:
        # Create external provider components (similar to dependencies.py)
        cache = ProviderCache()

        fotmob = FotMobFootballProvider(
            base_url=settings.fotmob_base_url,
            timeout_seconds=settings.provider_timeout_seconds,
            retry_count=min(settings.provider_retry_count, 1),
            cache=cache,
        )

        # Create manager and adapter
        manager = ProviderManager(
            ryzellx=None,  # Disabled like in dependencies.py
            fotmob=fotmob,
            openligadb=None,  # Simplify for debug
            cache=cache,
        )

        external_adapter = ProviderManagerAdapter(manager=manager)

        # Create hybrid provider
        hybrid_provider = HybridProvider(
            external_provider=external_adapter,
            session=db_session
        )

        print("=== Testing HybridProvider ===")

        # Test 1: Check UUID detection
        correct_id = "aa4c9808-cb36-486e-bd41-003cc28b8543"
        is_uuid = hybrid_provider._is_canonical_uuid(correct_id)
        print(f"ID {correct_id} is canonical UUID: {is_uuid}")

        # Test 2: Try get_match
        print(f"\nTesting get_match with {correct_id}:")

        print("  Step 1: Trying external provider...")
        try:
            external_match = hybrid_provider.external_provider.get_match(correct_id)
            print(f"  External result: {external_match}")
        except Exception as e:
            print(f"  External failed: {e}")

        print("  Step 2: Trying database provider...")
        try:
            db_match = hybrid_provider.db_provider.get_match(correct_id)
            if db_match:
                print(f"  ✅ Database found: {db_match.id}")
                print(f"      Status: {db_match.status}")
            else:
                print(f"  ❌ Database returned None")
        except Exception as e:
            print(f"  Database failed: {e}")

        print("  Step 3: Full hybrid get_match:")
        try:
            hybrid_match = hybrid_provider.get_match(correct_id)
            if hybrid_match:
                print(f"  ✅ Hybrid found: {hybrid_match.id}")
            else:
                print(f"  ❌ Hybrid returned None")
        except Exception as e:
            print(f"  Hybrid failed: {e}")

    finally:
        db_session.close()

if __name__ == "__main__":
    test_hybrid_provider()
