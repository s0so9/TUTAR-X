#!/usr/bin/env python3
"""Check if xG and ELO are in response."""

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
resp = client.get('/api/v1/matches/fotmob_5795469/prediction')

if resp.status_code == 200:
    data = resp.json()
    print(f"Home xG: {data.get('home_xg')}")
    print(f"Away xG: {data.get('away_xg')}")
    print(f"Model count: {data.get('models_used_count', 'N/A')}")

    # Check version metadata
    version = data.get('version', {})
    if version:
        models = version.get('models', [])
        print(f"\nModels in version metadata: {len(models)}")
        for m in models:
            print(f"  - {m.get('model_id')}: {m.get('success')}")
else:
    print(f"Error: {resp.status_code}")
