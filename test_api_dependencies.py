#!/usr/bin/env python3
"""
Test API dependencies directly
"""

import sys
import os
os.chdir('backend')
sys.path.insert(0, '.')

from app.api.dependencies import get_data_provider
from app.database.session import get_db

def test_api_dependencies():
    """Test API dependencies to see if they work like manual creation"""

    print("=== Testing API Dependencies ===")

    # Test 1: get_data_provider
    print("\n1. Testing get_data_provider:")
    try:
        provider_gen = get_data_provider()
        provider = next(provider_gen)
        print(f"✅ Provider created: {type(provider)}")

        # Test with our match
        correct_id = "aa4c9808-cb36-486e-bd41-003cc28b8543"
        print(f"\nTesting match lookup with {correct_id}:")

        match = provider.get_match(correct_id)
        if match:
            print(f"✅ Found match: {match.id}")
            print(f"   Status: {match.status}")
            print(f"   Date: {match.scheduled_at}")
        else:
            print("❌ Match not found through dependency")

        # Clean up generator
        try:
            next(provider_gen)
        except StopIteration:
            pass

    except Exception as e:
        print(f"❌ Error creating provider: {e}")
        import traceback
        traceback.print_exc()

    # Test 2: get_db
    print(f"\n2. Testing get_db:")
    try:
        db_gen = get_db()
        db = next(db_gen)
        print(f"✅ DB session created: {type(db)}")

        # Clean up generator
        try:
            next(db_gen)
        except StopIteration:
            pass

    except Exception as e:
        print(f"❌ Error creating DB session: {e}")

if __name__ == "__main__":
    test_api_dependencies()
