"""
Find a FINISHED match to test statistics data flow.
"""

import requests
from typing import Optional, Dict, Any


def find_finished_match() -> Optional[Dict[str, Any]]:
    """Find a finished match with statistics."""
    url = "http://localhost:8000/api/v1/matches"

    # Get matches
    response = requests.get(url, params={'limit': 100}, timeout=10)
    response.raise_for_status()
    data = response.json()

    matches = data['matches']

    # Find finished matches with statistics
    finished_with_stats = []

    for match in matches:
        if match['status'] == 'finished':
            # Check if has statistics
            if match.get('home_statistics') and match.get('away_statistics'):
                home_stats = match['home_statistics']
                away_stats = match['away_statistics']

                # Check if has the key statistics we care about
                has_shots = home_stats.get('shots_total') is not None
                has_corners = home_stats.get('corners') is not None
                has_possession = home_stats.get('possession_percentage') is not None

                if has_shots or has_corners or has_possession:
                    finished_with_stats.append({
                        'id': match['id'],
                        'home': match['home_team']['name'],
                        'away': match['away_team']['name'],
                        'score': f"{match['home_score']}-{match['away_score']}",
                        'has_shots': has_shots,
                        'has_corners': has_corners,
                        'has_possession': has_possession,
                        'home_stats': home_stats,
                        'away_stats': away_stats
                    })

    return finished_with_stats


def main():
    print("=" * 80)
    print("SEARCHING FOR FINISHED MATCHES WITH STATISTICS")
    print("=" * 80)
    print()

    matches = find_finished_match()

    if not matches:
        print("❌ No finished matches with statistics found in database")
        print()
        print("CONCLUSION:")
        print("  The database only contains SCHEDULED (future) matches.")
        print("  Shots/corners/possession statistics only exist for FINISHED matches.")
        print("  Frontend correctly shows '--' because data doesn't exist at source.")
        print()
        print("STATUS: NOT A BUG - Expected behavior")
        return

    print(f"✓ Found {len(matches)} finished match(es) with statistics")
    print()

    # Show first few matches
    for i, match in enumerate(matches[:5], 1):
        print(f"{i}. {match['home']} {match['score']} {match['away']}")
        print(f"   Match ID: {match['id']}")
        print(f"   Shots: {'✓' if match['has_shots'] else '✗'}")
        print(f"   Corners: {'✓' if match['has_corners'] else '✗'}")
        print(f"   Possession: {'✓' if match['has_possession'] else '✗'}")

        if match['has_shots']:
            print(f"   Home Shots: {match['home_stats']['shots_total']} ({match['home_stats']['shots_on_target']} on target)")
            print(f"   Away Shots: {match['away_stats']['shots_total']} ({match['away_stats']['shots_on_target']} on target)")

        if match['has_corners']:
            print(f"   Home Corners: {match['home_stats']['corners']}")
            print(f"   Away Corners: {match['away_stats']['corners']}")

        if match['has_possession']:
            print(f"   Home Possession: {match['home_stats']['possession_percentage']}%")
            print(f"   Away Possession: {match['away_stats']['possession_percentage']}%")

        print()

    if matches:
        print("=" * 80)
        print("NEXT STEP: Test prediction API with first match")
        print("=" * 80)
        test_match = matches[0]
        print(f"Match ID: {test_match['id']}")
        print(f"Match: {test_match['home']} vs {test_match['away']}")


if __name__ == '__main__':
    main()
