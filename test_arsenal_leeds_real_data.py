"""
Test Arsenal-Leeds real API response for form, H2H, and statistics.
"""

import requests
import json


def test_arsenal_leeds_prediction():
    """Test Arsenal-Leeds prediction API response."""
    match_id = "849f5743-1f96-4ade-be4c-af1c5d3da039"
    url = f"http://localhost:8000/api/v1/matches/{match_id}/prediction"

    print("=" * 80)
    print("ARSENAL-LEEDS PREDICTION API TEST")
    print("=" * 80)
    print()

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        # Check form data
        print("1. FORM DATA")
        print("-" * 80)
        home_form = data.get('home_form')
        away_form = data.get('away_form')

        if home_form:
            print(f"✓ Home form (Arsenal): {json.dumps(home_form, indent=2)}")
        else:
            print("✗ Home form: NULL or missing")

        print()

        if away_form:
            print(f"✓ Away form (Leeds): {json.dumps(away_form, indent=2)}")
        else:
            print("✗ Away form: NULL or missing")

        print()
        print()

        # Check H2H data
        print("2. HEAD-TO-HEAD (H2H) DATA")
        print("-" * 80)

        if 'head_to_head' in data and data['head_to_head']:
            h2h = data['head_to_head']
            print(f"✓ H2H found:")
            print(json.dumps(h2h, indent=2))
            h2h_found = True
        else:
            print("✗ H2H data: NULL or missing")
            if 'head_to_head' in data:
                print(f"  Field exists but value is: {data['head_to_head']}")

        print()
        print()

        # Check match statistics
        print("3. MATCH STATISTICS")
        print("-" * 80)

        stat_keys = [
            'home_statistics', 'away_statistics',
            'home_stats', 'away_stats',
            'statistics'
        ]

        stats_found = False
        for key in stat_keys:
            if key in data and data[key]:
                print(f"✓ Statistics found under key '{key}':")
                print(json.dumps(data[key], indent=2)[:500])
                stats_found = True
                break

        if not stats_found:
            print("✗ Match statistics: NULL or missing")
            print("  Checked keys:", stat_keys)

        print()
        print()

        # Check all available keys
        print("4. ALL AVAILABLE RESPONSE KEYS")
        print("-" * 80)
        print("Keys in response:", list(data.keys()))

        print()
        print("=" * 80)

        return data

    except requests.exceptions.HTTPError as e:
        print(f"✗ HTTP Error: {e.response.status_code}")
        print(f"  Detail: {e.response.json().get('detail', 'Unknown error')}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"✗ Request Error: {e}")
        return None


def test_match_detail():
    """Test match detail endpoint for statistics."""
    match_id = "849f5743-1f96-4ade-be4c-af1c5d3da039"
    url = f"http://localhost:8000/api/v1/matches/{match_id}"

    print()
    print("=" * 80)
    print("ARSENAL-LEEDS MATCH DETAIL API TEST")
    print("=" * 80)
    print()

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        match = data['match']

        print(f"Match: {match['home_team']['name']} vs {match['away_team']['name']}")
        print(f"Status: {match['status']}")
        print()

        print("Home Statistics:")
        if match.get('home_statistics'):
            stats = match['home_statistics']
            print(f"  Shots: {stats.get('shots_total')}")
            print(f"  Shots on target: {stats.get('shots_on_target')}")
            print(f"  Corners: {stats.get('corners')}")
            print(f"  Possession: {stats.get('possession_percentage')}%")
        else:
            print("  ✗ No statistics")

        print()
        print("Away Statistics:")
        if match.get('away_statistics'):
            stats = match['away_statistics']
            print(f"  Shots: {stats.get('shots_total')}")
            print(f"  Shots on target: {stats.get('shots_on_target')}")
            print(f"  Corners: {stats.get('corners')}")
            print(f"  Possession: {stats.get('possession_percentage')}%")
        else:
            print("  ✗ No statistics")

        print()
        print("=" * 80)

    except Exception as e:
        print(f"✗ Error: {e}")


if __name__ == '__main__':
    test_arsenal_leeds_prediction()
    test_match_detail()
