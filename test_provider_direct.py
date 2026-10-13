#!/usr/bin/env python3
"""
Test provider directly to isolate the issue
"""
import sys
import os
os.chdir('backend')
sys.path.insert(0, '.')

from app.api.dependencies import get_data_provider
from app.database.session import get_db

def test_provider_direct():
    print("Testing provider directly...")

    try:
        # Test get_data_provider
        print("1. Testing get_data_provider...")
        provider_gen = get_data_provider()
        provider = next(provider_gen)
        print(f"✅ Provider created: {type(provider)}")

        # Test get_matches
        print("2. Testing provider.get_matches()...")
        matches = provider.get_matches()
        print(f"✅ Found {len(matches)} matches")

        if matches:
            print(f"First match ID: {matches[0].id}")
            print(f"First match status: {matches[0].status}")

        # Clean up
        try:
            next(provider_gen)
        except StopIteration:
            pass

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    try:
        # Test get_db
        print("3. Testing get_db...")
        db_gen = get_db()
        db = next(db_gen)
        print(f"✅ DB session: {type(db)}")

        # Clean up
        try:
            next(db_gen)
        except StopIteration:
            pass

    except Exception as e:
        print(f"❌ DB Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_provider_direct()
