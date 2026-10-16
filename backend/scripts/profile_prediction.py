#!/usr/bin/env python3
"""Profile prediction endpoint to identify bottlenecks."""

import sys
import os
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

# Set UTF-8 encoding for print
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def profile_prediction():
    """Profile a single prediction request."""
    
    # Reduce SQLAlchemy logging noise
    import logging
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    
    from app.main import app
    from fastapi.testclient import TestClient
    from app.prediction.profiler import get_profiler, reset_profiler
    import json
    
    client = TestClient(app)
    
    # Get first available match
    print("[SETUP] Fetching available matches...")
    list_response = client.get("/api/v1/matches")
    
    if list_response.status_code != 200:
        print(f"[ERROR] Failed to fetch matches: {list_response.status_code}")
        return None
    
    matches = list_response.json().get("matches", [])
    if not matches:
        print("[ERROR] No matches available")
        return None
    
    match_id = matches[0]["id"]
    print(f"[SETUP] Testing with match: {match_id}")
    print("=" * 80)
    
    # Reset profiler
    reset_profiler()
    
    # Make prediction request
    print("[PROFILE] Starting prediction request...")
    
    response = client.get(f"/api/v1/matches/{match_id}/prediction")
    
    print(f"\n[RESULT] Response Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"[SUCCESS] Prediction generated successfully")
        print(f"   Home Win: {data.get('home_win_probability', 0):.3f}")
        print(f"   Draw: {data.get('draw_probability', 0):.3f}")
        print(f"   Away Win: {data.get('away_win_probability', 0):.3f}")
    elif response.status_code == 400:
        print(f"[EXPECTED] Insufficient data for prediction")
        print(f"   Message: {response.json().get('detail', 'N/A')}")
    else:
        print(f"[FAILED] Prediction failed: {response.text[:200]}")
    
    # Get and print profiler report
    profiler = get_profiler()
    profiler.print_report()
    
    # Get JSON report for analysis
    report = profiler.get_report()
    
    # Save detailed report
    output_path = Path(__file__).parent / "profile_report.json"
    try:
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"\n[SAVED] Detailed report saved to: {output_path}")
    except Exception as e:
        print(f"\n[WARNING] Could not save report: {e}")
    
    return report

if __name__ == "__main__":
    profile_prediction()
