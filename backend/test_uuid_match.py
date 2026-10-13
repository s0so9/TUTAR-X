#!/usr/bin/env python3
"""Test prediction with UUID match."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.main import app
from fastapi.testclient import TestClient

def test_uuid_match():
    client = TestClient(app)

    # Test with UUID match
    match_id = "1d70ebc5-237e-474a-97b2-6bbf63625482"

    print(f"Testing prediction for match: {match_id}\n")

    response = client.get(f"/api/v1/matches/{match_id}/prediction")

    print(f"Status Code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"\n[SUCCESS] Prediction successful!")
        print(f"  Home Win: {data.get('home_win_probability', 0):.3f}")
        print(f"  Draw: {data.get('draw_probability', 0):.3f}")
        print(f"  Away Win: {data.get('away_win_probability', 0):.3f}")
        print(f"  Home xG: {data.get('home_xg', 0):.2f}")
        print(f"  Away xG: {data.get('away_xg', 0):.2f}")
    else:
        print(f"\n[FAILED] Prediction failed:")
        print(response.text[:500])

if __name__ == "__main__":
    test_uuid_match()
