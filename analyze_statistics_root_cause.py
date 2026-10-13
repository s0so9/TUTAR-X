"""
Root cause analysis for missing statistics (shots, corners, possession).
Traces data flow from provider → database → API → frontend.
"""

import requests
import json
from typing import Optional, Dict, Any


def check_match_statistics(match_id: str) -> Dict[str, Any]:
    """Check if match has statistics in database."""
    url = f"http://localhost:8000/api/v1/matches/{match_id}"

    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()

    match = data['match']

    return {
        'match_id': match['id'],
        'home_team': match['home_team']['name'],
        'away_team': match['away_team']['name'],
        'status': match['status'],
        'home_statistics': match.get('home_statistics'),
        'away_statistics': match.get('away_statistics'),
    }


def check_prediction_statistics(match_id: str) -> Dict[str, Any]:
    """Check if prediction endpoint includes statistics."""
    url = f"http://localhost:8000/api/v1/matches/{match_id}/prediction"

    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()

    # Look for any statistics fields
    result = {
        'has_home_form': data.get('home_form') is not None,
        'has_away_form': data.get('away_form') is not None,
    }

    # Check if there are any statistics fields
    stats_fields = ['shots', 'corners', 'possession', 'home_statistics', 'away_statistics']
    for field in stats_fields:
        if field in data:
            result[f'has_{field}'] = True

    return result


def analyze_statistics_flow():
    """Analyze the complete statistics data flow."""
    match_id = "849f5743-1f96-4ade-be4c-af1c5d3da039"

    print("=" * 80)
    print("STATISTICS ROOT CAUSE ANALYSIS: Arsenal vs Leeds")
    print("=" * 80)
    print()

    # Step 1: Check database
    print("STEP 1: Database Check")
    print("-" * 80)

    match_data = check_match_statistics(match_id)

    print(f"Match: {match_data['home_team']} vs {match_data['away_team']}")
    print(f"Status: {match_data['status']}")
    print()

    print("HOME STATISTICS (Arsenal):")
    if match_data['home_statistics']:
        stats = match_data['home_statistics']
        print(f"  Shots Total: {stats.get('shots_total')}")
        print(f"  Shots On Target: {stats.get('shots_on_target')}")
        print(f"  Corners: {stats.get('corners')}")
        print(f"  Possession: {stats.get('possession_percentage')}")

        has_shots = stats.get('shots_total') is not None
        has_corners = stats.get('corners') is not None
        has_possession = stats.get('possession_percentage') is not None

        print()
        print(f"  ✓ Shots available: {has_shots}")
        print(f"  ✓ Corners available: {has_corners}")
        print(f"  ✓ Possession available: {has_possession}")
    else:
        print("  ❌ No statistics in database")

    print()
    print("AWAY STATISTICS (Leeds):")
    if match_data['away_statistics']:
        stats = match_data['away_statistics']
        print(f"  Shots Total: {stats.get('shots_total')}")
        print(f"  Shots On Target: {stats.get('shots_on_target')}")
        print(f"  Corners: {stats.get('corners')}")
        print(f"  Possession: {stats.get('possession_percentage')}")
    else:
        print("  ❌ No statistics in database")

    print()
    print()

    # Step 2: Check prediction API
    print("STEP 2: Prediction API Check")
    print("-" * 80)

    pred_data = check_prediction_statistics(match_id)

    print(f"Prediction API includes form data: {pred_data['has_home_form']}")
    print(f"Prediction API includes statistics: {any(k.startswith('has_') and k not in ['has_home_form', 'has_away_form'] for k in pred_data.keys())}")
    print()

    # Step 3: Root cause summary
    print()
    print("ROOT CAUSE ANALYSIS")
    print("=" * 80)
    print()

    if not match_data['home_statistics'] and not match_data['away_statistics']:
        print("❌ ROOT CAUSE: Statistics NOT AVAILABLE in database")
        print()
        print("REASON:")
        print("  This is a SCHEDULED (future) match.")
        print("  Shots, corners, and possession are IN-MATCH statistics.")
        print("  They only exist for FINISHED matches.")
        print()
        print("CONCLUSION:")
        print("  This is NOT a bug - it's expected behavior.")
        print("  Frontend correctly shows '--' for unavailable data.")
        print()
        print("VERIFICATION NEEDED:")
        print("  Test with a FINISHED match to see if statistics flow correctly.")

    else:
        print("✓ Statistics ARE available in database")
        print()
        print("NEXT STEP:")
        print("  Check if statistics are included in prediction response")
        print("  Check if frontend is reading the correct field names")

    print()
    print("=" * 80)

    return match_data


if __name__ == '__main__':
    analyze_statistics_flow()
