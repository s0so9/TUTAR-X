"""
GROUP 2: Dashboard End-to-End Verification
Tests frontend API integration with backend prediction pipeline.

Validates:
1. Frontend can load upcoming matches from /api/v1/matches/upcoming
2. Frontend can request predictions for those matches
3. Response format matches frontend expectations
4. Dashboard would display picks correctly

NO browser automation - just API contract validation.
"""

import asyncio
import httpx
import json
from datetime import datetime, timezone
from pathlib import Path


BASE_URL = "http://localhost:8002"
TIMEOUT = 90.0  # Predictions take 20-30s on average
OUTPUT_FILE = Path(__file__).parent / "group2_results.json"


async def test_upcoming_matches_endpoint():
    """Test GET /api/v1/matches?status=scheduled&from_date=today - frontend's data source."""
    from datetime import date
    today = date.today().isoformat()
    
    print(f"\n[TEST] GET /api/v1/matches?status=scheduled&from_date={today}")
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BASE_URL}/api/v1/matches",
            params={"status": "scheduled", "from_date": today}
        )
        
        if response.status_code != 200:
            return {
                "endpoint": f"/api/v1/matches?status=scheduled&from_date={today}",
                "status": "FAIL",
                "status_code": response.status_code,
                "error": response.text
            }
        
        matches = response.json()
        
        # Response is {matches: [...], count: int, is_development_data: bool}
        match_list = matches.get("matches", [])
        
        return {
            "endpoint": f"/api/v1/matches?status=scheduled&from_date={today}",
            "status": "PASS",
            "match_count": len(match_list),
            "sample_match_ids": [m["id"] for m in match_list[:5]] if match_list else [],
            "response_time_sec": response.elapsed.total_seconds()
        }


async def test_prediction_contract(match_id: str):
    """Test prediction response matches frontend expectations."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(f"{BASE_URL}/api/v1/matches/{match_id}/prediction")
        
        if response.status_code != 200:
            return {
                "match_id": match_id,
                "status": "FAIL",
                "status_code": response.status_code,
                "error": response.text
            }
        
        data = response.json()
        
        # Frontend expects these fields (MatchPredictionResponse schema)
        required_fields = [
            "match_id",
            "home_win_probability",
            "draw_probability",
            "away_win_probability",
            "home_xg",
            "away_xg",
            "btts_probability"
        ]
        
        missing_fields = [f for f in required_fields if f not in data]
        
        # Check mensione_pick structure (optional but should be valid if present)
        pick = data.get("mensione_pick")
        pick_valid = False
        if pick:
            pick_valid = all(k in pick for k in ["market", "selection", "pass_decision", "confidence"])
        
        return {
            "match_id": match_id,
            "status": "PASS" if not missing_fields else "FAIL",
            "missing_fields": missing_fields,
            "has_mensione_pick": pick is not None,
            "pick_structure_valid": pick_valid,
            "mensione_pick": pick if pick_valid else None,
            "response_time_sec": response.elapsed.total_seconds()
        }


async def main():
    print("=" * 70)
    print("GROUP 2: DASHBOARD END-TO-END VALIDATION")
    print("=" * 70)
    print(f"Backend: {BASE_URL}")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    
    results = {
        "group": "GROUP_2_DASHBOARD_E2E",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "backend_url": BASE_URL,
        "tests": []
    }
    
    # Test 1: Upcoming matches endpoint
    print("\n--- Test 1: Upcoming Matches Endpoint ---")
    upcoming_result = await test_upcoming_matches_endpoint()
    results["tests"].append(upcoming_result)
    
    print(f"Status: {upcoming_result['status']}")
    if upcoming_result["status"] == "PASS":
        print(f"Matches returned: {upcoming_result['match_count']}")
        print(f"Sample IDs: {upcoming_result['sample_match_ids']}")
    else:
        print(f"Error: {upcoming_result.get('error', 'Unknown')}")
        # Can't continue without matches
        OUTPUT_FILE.write_text(json.dumps(results, indent=2))
        return
    
    # Test 2: Prediction contract validation (sample 3 matches)
    print("\n--- Test 2: Prediction Contract Validation ---")
    sample_ids = upcoming_result["sample_match_ids"][:3]
    
    for match_id in sample_ids:
        print(f"\nTesting match {match_id}...")
        contract_result = await test_prediction_contract(match_id)
        results["tests"].append(contract_result)
        
        print(f"  Status: {contract_result['status']}")
        if contract_result["status"] == "PASS":
            has_pick = contract_result["has_mensione_pick"]
            pick_valid = contract_result["pick_structure_valid"]
            print(f"  Has MENSIONE pick: {has_pick}")
            if has_pick and pick_valid:
                pick = contract_result["mensione_pick"]
                print(f"  Pick: {pick['market']} -> {pick['selection']}")
                print(f"  Confidence: {pick['confidence']:.1%}")
                print(f"  Pass: {pick['pass_decision']}")
            elif has_pick:
                print(f"  Pick structure invalid")
            print(f"  Response time: {contract_result['response_time_sec']:.2f}s")
        else:
            print(f"  Missing fields: {contract_result.get('missing_fields', [])}")
            print(f"  Pick valid: {contract_result.get('pick_structure_valid', False)}")
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    total_tests = len(results["tests"])
    passed = sum(1 for t in results["tests"] if t["status"] == "PASS")
    failed = total_tests - passed
    
    print(f"Total tests: {total_tests}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    results["summary"] = {
        "total_tests": total_tests,
        "passed": passed,
        "failed": failed,
        "pass_rate": passed / total_tests if total_tests > 0 else 0
    }
    
    # Save results
    OUTPUT_FILE.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved to: {OUTPUT_FILE}")
    
    if failed == 0:
        print("\n[PASS] Dashboard E2E validation successful")
    else:
        print(f"\n[FAIL] {failed} test(s) failed")


if __name__ == "__main__":
    asyncio.run(main())
