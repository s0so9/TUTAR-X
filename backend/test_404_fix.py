#!/usr/bin/env python3
"""Test and fix potential 404 issues in match prediction."""

from app.api.v1.endpoints.matches import get_match_prediction
from app.providers.hybrid_provider import HybridProvider
from app.providers.adapter import ProviderManagerAdapter
from app.providers.manager import ProviderManager
from app.providers.development import DevelopmentProvider
from app.database import SessionLocal
from fastapi import HTTPException

def test_404_scenarios():
    """Test prediction with both valid and invalid match IDs."""

    # Setup dependencies
    dev_provider = DevelopmentProvider()
    manager = ProviderManager(None, None, dev_provider)
    adapter = ProviderManagerAdapter(manager)
    session = SessionLocal()
    hybrid = HybridProvider(adapter, session)

    # Test cases
    valid_id = "aa4c9808-cb36-486e-bd41-003cc28b8543"  # Real Fluminense vs Coritiba
    invalid_id = "1f05edd0-b0a5-4453-b70c-1892247bea54"  # User's reported ID

    print("=== Testing Match Prediction 404 Scenarios ===")

    # Test 1: Valid ID
    print(f"\\n1. Testing VALID ID: {valid_id}")
    try:
        # This simulates the endpoint call
        match = hybrid.get_match(valid_id)
        if match:
            print(f"   ✅ Match found: {match.home_team_id} vs {match.away_team_id}")
            print(f"   Status: {match.status}")
        else:
            print("   ❌ Match not found")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test 2: Invalid ID
    print(f"\\n2. Testing INVALID ID: {invalid_id}")
    try:
        match = hybrid.get_match(invalid_id)
        if match:
            print(f"   ✅ Match found: {match.home_team_id} vs {match.away_team_id}")
        else:
            print("   ❌ Match not found (expected)")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test 3: HTTP Endpoint behavior simulation
    print(f"\\n3. Simulating HTTP endpoint behavior:")

    try:
        from unittest.mock import AsyncMock

        # Test valid ID through endpoint logic
        match = hybrid.get_match(valid_id)
        if match is None:
            print(f"   📧 Would return 404 for valid ID: {valid_id}")
        else:
            print(f"   ✅ Would return prediction for valid ID: {valid_id}")

        # Test invalid ID through endpoint logic
        match = hybrid.get_match(invalid_id)
        if match is None:
            print(f"   📧 Would return 404 for invalid ID: {invalid_id}")
        else:
            print(f"   ⚠️ Unexpected: found match for invalid ID")

    except Exception as e:
        print(f"   ❌ Endpoint simulation error: {e}")

    session.close()

if __name__ == "__main__":
    test_404_scenarios()
