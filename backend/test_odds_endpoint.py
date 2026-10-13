#!/usr/bin/env python3
"""Test odds endpoint locally without running server."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
from app.main import app

def test_odds_health():
    """Test odds health endpoint with FastAPI test client."""
    client = TestClient(app)

    print("Testing /api/v1/odds/health endpoint...")

    try:
        response = client.get("/api/v1/odds/health")
        print(f"✅ Status Code: {response.status_code}")
        if response.status_code == 200:
            print(f"✅ Response: {response.json()}")
        else:
            print(f"❌ Error response: {response.text}")
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_odds_health()
