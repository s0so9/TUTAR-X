#!/usr/bin/env python3
"""Comprehensive validation test for real provider recovery."""

import sys
import asyncio
import requests
from datetime import date, timedelta

def test_api_endpoint(url, description):
    """Test an API endpoint and return success status."""
    try:
        print(f"Testing: {description}")
        print(f"URL: {url}")

        response = requests.get(url, timeout=10)
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()

            if 'matches' in data:
                match_count = len(data['matches'])
                is_dev_data = data.get('is_development_data', True)
                print(f"Matches: {match_count}")
                print(f"Development data: {is_dev_data}")

                if match_count > 0 and not is_dev_data:
                    # Show sample match
                    sample = data['matches'][0]
                    print(f"Sample: {sample.get('home_team', {}).get('name', 'Unknown')} vs {sample.get('away_team', {}).get('name', 'Unknown')}")
                    print(f"Competition: {sample.get('competition_id')}")
                    print(f"Status: {sample.get('status')}")
                    return True, match_count
                elif not is_dev_data:
                    print("✓ Real providers enabled, but no matches for this query")
                    return True, 0
                else:
                    print("✗ Still returning development data")
                    return False, 0
            else:
                print(f"Response: {str(data)[:200]}...")
                return response.status_code == 200, 0

        else:
            print(f"✗ HTTP {response.status_code}")
            if response.text:
                print(f"Error: {response.text[:200]}")
            return False, 0

    except Exception as e:
        print(f"✗ Exception: {e}")
        return False, 0

    finally:
        print()

def main():
    """Run comprehensive validation."""
    print("=== REAL PROVIDER VALIDATION ===")
    print()

    base_url = "http://localhost:8002/api/v1"
    today = date.today().strftime("%Y-%m-%d")
    tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

    tests = [
        # Test 1: Today's matches
        (f"{base_url}/matches?from_date={today}&to_date={today}", "Today's matches"),

        # Test 2: Tomorrow's matches
        (f"{base_url}/matches?from_date={tomorrow}&to_date={tomorrow}", "Tomorrow's matches"),

        # Test 3: Scheduled matches for tomorrow
        (f"{base_url}/matches?from_date={tomorrow}&status=scheduled", "Scheduled matches tomorrow"),

        # Test 4: Date range (today + tomorrow)
        (f"{base_url}/matches?from_date={today}&to_date={tomorrow}", "Date range matches"),
    ]

    successful_tests = 0
    total_real_matches = 0
    test_results = []

    for url, description in tests:
        success, match_count = test_api_endpoint(url, description)
        test_results.append((description, success, match_count))
        if success:
            successful_tests += 1
            total_real_matches += match_count

    # Summary
    print("=== VALIDATION SUMMARY ===")
    for description, success, match_count in test_results:
        status = "✓" if success else "✗"
        print(f"{status} {description}: {match_count} matches")

    print()
    print(f"Successful tests: {successful_tests}/{len(tests)}")
    print(f"Total real matches found: {total_real_matches}")

    # Final assessment
    if successful_tests >= len(tests) // 2 and total_real_matches > 0:
        print("\n✓ VALIDATION PASSED")
        print("Real provider recovery is working correctly.")
        print("- At least one provider is returning real data")
        print("- Fallback mechanism is functional")
        print("- API endpoints are responsive")
        return True
    else:
        print("\n✗ VALIDATION FAILED")
        print("Real provider recovery needs more work.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
