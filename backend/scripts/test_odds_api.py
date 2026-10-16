#!/usr/bin/env python3
"""
Test script for The Odds API integration.

Usage:
    python scripts/test_odds_api.py --test connection
    python scripts/test_odds_api.py --test sports
    python scripts/test_odds_api.py --test turkey
    python scripts/test_odds_api.py --test bookmakers
    python scripts/test_odds_api.py --test odds --sport soccer_epl
"""

import os
import sys
import json
import argparse
from typing import List, Dict, Optional
import requests
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# API Configuration
BASE_URL = 'https://api.the-odds-api.com/v4'
API_KEY = os.getenv('THE_ODDS_API_KEY')

# Colors for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


def print_success(message: str):
    """Print success message in green."""
    print(f"{GREEN}✓ {message}{RESET}")


def print_error(message: str):
    """Print error message in red."""
    print(f"{RED}✗ {message}{RESET}")


def print_warning(message: str):
    """Print warning message in yellow."""
    print(f"{YELLOW}⚠ {message}{RESET}")


def print_info(message: str):
    """Print info message in blue."""
    print(f"{BLUE}ℹ {message}{RESET}")


def check_api_key() -> bool:
    """Check if API key is configured."""
    if not API_KEY:
        print_error("API key not found!")
        print_info("Please set THE_ODDS_API_KEY environment variable in backend/.env")
        print_info("Get your free API key from: https://the-odds-api.com/")
        return False
    
    print_success(f"API key found: {API_KEY[:10]}...")
    return True


def test_connection() -> bool:
    """Test basic API connection."""
    print_info("Testing API connection...")
    
    if not check_api_key():
        return False
    
    try:
        url = f'{BASE_URL}/sports'
        params = {'apiKey': API_KEY}
        
        response = requests.get(url, params=params, timeout=10)
        
        # Check rate limit headers
        remaining = response.headers.get('x-requests-remaining')
        used = response.headers.get('x-requests-used')
        
        if remaining:
            print_info(f"Requests remaining: {remaining}")
        if used:
            print_info(f"Requests used: {used}")
        
        if response.status_code == 200:
            data = response.json()
            print_success(f"Connection successful! Found {len(data)} sports")
            return True
        elif response.status_code == 401:
            print_error("Unauthorized! Check your API key")
            return False
        elif response.status_code == 429:
            print_error("Rate limit exceeded!")
            return False
        else:
            print_error(f"API returned status {response.status_code}")
            print(response.text)
            return False
            
    except requests.exceptions.Timeout:
        print_error("Request timed out")
        return False
    except requests.exceptions.RequestException as e:
        print_error(f"Request failed: {e}")
        return False


def list_sports() -> Optional[List[Dict]]:
    """List all available sports."""
    print_info("Fetching sports list...")
    
    if not check_api_key():
        return None
    
    try:
        url = f'{BASE_URL}/sports'
        params = {'apiKey': API_KEY}
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            sports = response.json()
            print_success(f"Found {len(sports)} sports")
            
            # Print football/soccer sports
            football_sports = [s for s in sports if 'soccer' in s.get('key', '').lower() 
                             or 'football' in s.get('key', '').lower()]
            
            if football_sports:
                print_info(f"\nFootball/Soccer leagues ({len(football_sports)}):")
                for sport in football_sports:
                    active = "✓" if sport.get('active') else "✗"
                    print(f"  {active} {sport['key']:<40} - {sport['title']}")
            
            return sports
        else:
            print_error(f"Failed to fetch sports: {response.status_code}")
            return None
            
    except Exception as e:
        print_error(f"Error fetching sports: {e}")
        return None


def check_turkey_support() -> bool:
    """Check if Turkey Super Lig is supported."""
    print_info("Checking Turkey Super Lig support...")
    
    sports = list_sports()
    if not sports:
        return False
    
    # Look for Turkey-related sports
    turkey_keywords = ['turkey', 'turkish', 'super', 'süper']
    turkey_sports = []
    
    for sport in sports:
        sport_key = sport.get('key', '').lower()
        sport_title = sport.get('title', '').lower()
        
        if any(keyword in sport_key or keyword in sport_title for keyword in turkey_keywords):
            turkey_sports.append(sport)
    
    if turkey_sports:
        print_success(f"Found {len(turkey_sports)} Turkey-related sport(s):")
        for sport in turkey_sports:
            active = "✓ ACTIVE" if sport.get('active') else "✗ INACTIVE"
            print(f"  {active}: {sport['key']} - {sport['title']}")
        return True
    else:
        print_warning("No Turkey-specific leagues found in The Odds API")
        print_info("Turkey Super Lig might not be covered by this API")
        print_info("Consider using EPL or other major leagues for testing")
        return False


def test_bookmakers(sport_key: str = 'soccer_epl') -> Optional[List[str]]:
    """Test bookmakers for a specific sport."""
    print_info(f"Checking bookmakers for {sport_key}...")
    
    if not check_api_key():
        return None
    
    try:
        url = f'{BASE_URL}/sports/{sport_key}/odds'
        params = {
            'apiKey': API_KEY,
            'regions': 'eu,uk,us',
            'markets': 'h2h',
            'oddsFormat': 'decimal'
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            events = response.json()
            
            if not events:
                print_warning(f"No events found for {sport_key}")
                return []
            
            # Collect all bookmakers
            bookmakers = set()
            for event in events:
                for bookmaker in event.get('bookmakers', []):
                    bookmakers.add(bookmaker['key'])
            
            print_success(f"Found {len(bookmakers)} bookmakers:")
            for bookmaker in sorted(bookmakers):
                print(f"  • {bookmaker}")
            
            # Check for İddaa variations
            iddaa_variations = ['iddaa', 'nesine', 'bilyoner', 'misli']
            iddaa_found = any(any(variation in bm.lower() for variation in iddaa_variations) 
                            for bm in bookmakers)
            
            if iddaa_found:
                print_success("✓ İddaa or Turkish bookmaker FOUND!")
            else:
                print_warning("✗ İddaa not found in bookmaker list")
                print_info("Will use alternative bookmaker (e.g., Bet365, Unibet)")
            
            return list(bookmakers)
        else:
            print_error(f"Failed to fetch bookmakers: {response.status_code}")
            return None
            
    except Exception as e:
        print_error(f"Error checking bookmakers: {e}")
        return None


def test_odds(sport_key: str = 'soccer_epl', limit: int = 3) -> bool:
    """Test fetching actual odds data."""
    print_info(f"Fetching odds for {sport_key} (limit: {limit})...")
    
    if not check_api_key():
        return False
    
    try:
        url = f'{BASE_URL}/sports/{sport_key}/odds'
        params = {
            'apiKey': API_KEY,
            'regions': 'eu,uk',
            'markets': 'h2h,spreads,totals',
            'oddsFormat': 'decimal'
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            events = response.json()
            
            if not events:
                print_warning(f"No upcoming events for {sport_key}")
                return False
            
            print_success(f"Found {len(events)} upcoming events")
            
            # Show details for first few events
            for i, event in enumerate(events[:limit]):
                print(f"\n{BLUE}Event {i+1}:{RESET}")
                print(f"  ID: {event['id']}")
                print(f"  {event['home_team']} vs {event['away_team']}")
                print(f"  Kickoff: {event['commence_time']}")
                print(f"  Bookmakers: {len(event.get('bookmakers', []))}")
                
                # Show first bookmaker's odds
                if event.get('bookmakers'):
                    bookmaker = event['bookmakers'][0]
                    print(f"\n  {bookmaker['title']} odds:")
                    
                    for market in bookmaker.get('markets', []):
                        print(f"    {market['key']}:")
                        for outcome in market.get('outcomes', []):
                            print(f"      {outcome['name']}: {outcome.get('price', 'N/A')}")
            
            # Save sample to file
            sample_file = 'odds_api_sample.json'
            with open(sample_file, 'w') as f:
                json.dump(events[:limit], f, indent=2)
            print_success(f"\nSample data saved to {sample_file}")
            
            return True
        else:
            print_error(f"Failed to fetch odds: {response.status_code}")
            print(response.text)
            return False
            
    except Exception as e:
        print_error(f"Error fetching odds: {e}")
        return False


def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description='Test The Odds API integration')
    parser.add_argument('--test', choices=['connection', 'sports', 'turkey', 'bookmakers', 'odds', 'all'],
                       default='all', help='Test to run')
    parser.add_argument('--sport', default='soccer_epl', help='Sport key for odds test')
    parser.add_argument('--limit', type=int, default=3, help='Number of events to fetch')
    
    args = parser.parse_args()
    
    print(f"\n{BLUE}═══════════════════════════════════════════════════{RESET}")
    print(f"{BLUE}   The Odds API Integration Test{RESET}")
    print(f"{BLUE}═══════════════════════════════════════════════════{RESET}\n")
    
    results = {}
    
    if args.test in ['connection', 'all']:
        results['connection'] = test_connection()
        print()
    
    if args.test in ['sports', 'all']:
        sports = list_sports()
        results['sports'] = sports is not None
        print()
    
    if args.test in ['turkey', 'all']:
        results['turkey'] = check_turkey_support()
        print()
    
    if args.test in ['bookmakers', 'all']:
        bookmakers = test_bookmakers(args.sport)
        results['bookmakers'] = bookmakers is not None
        print()
    
    if args.test in ['odds', 'all']:
        results['odds'] = test_odds(args.sport, args.limit)
        print()
    
    # Summary
    print(f"\n{BLUE}═══════════════════════════════════════════════════{RESET}")
    print(f"{BLUE}   Test Summary{RESET}")
    print(f"{BLUE}═══════════════════════════════════════════════════{RESET}\n")
    
    for test_name, passed in results.items():
        status = f"{GREEN}✓ PASS{RESET}" if passed else f"{RED}✗ FAIL{RESET}"
        print(f"  {test_name.upper():<15} {status}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print(f"\n{GREEN}All tests passed! The Odds API is ready to use.{RESET}\n")
        return 0
    else:
        print(f"\n{RED}Some tests failed. Check the output above.{RESET}\n")
        return 1


if __name__ == '__main__':
    sys.exit(main())
