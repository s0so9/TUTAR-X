#!/usr/bin/env python3
"""Script to update bookmaker odds from The Odds API.

Can be run manually or scheduled via cron/task scheduler.

Usage:
    python scripts/update_odds.py
    python scripts/update_odds.py --sport soccer_epl
    python scripts/update_odds.py --cleanup-days 7
"""

import sys
import os
import argparse
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.odds_updater_service import update_all_odds, OddsUpdaterService
from app.database.session import get_db


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Update bookmaker odds from The Odds API')
    parser.add_argument('--sport', help='Update specific sport (e.g., soccer_epl)')
    parser.add_argument('--cleanup-days', type=int, default=7, help='Clean up odds older than N days')
    parser.add_argument('--json', action='store_true', help='Output JSON format')
    
    args = parser.parse_args()
    
    if not args.json:
        print("=" * 60)
        print("TUTAR X - Bookmaker Odds Updater")
        print("=" * 60)
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
    
    try:
        if args.sport:
            # Update single sport
            db = next(get_db())
            service = OddsUpdaterService(db)
            result = service.update_odds_for_sport(args.sport)
            
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(f"Sport: {args.sport}")
                print(f"Success: {result.get('success')}")
                if result.get('success'):
                    print(f"Events processed: {result.get('events_processed', 0)}")
                    print(f"Odds created: {result.get('odds_created', 0)}")
                    print(f"Odds updated: {result.get('odds_updated', 0)}")
                    print(f"Averages calculated: {result.get('averages_calculated', 0)}")
                else:
                    print(f"Error: {result.get('error')}")
                
                if result.get('errors'):
                    print("\nErrors:")
                    for error in result['errors']:
                        print(f"  - {error}")
        else:
            # Update all sports
            result = update_all_odds()
            
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print("All Sports Update")
                print(f"Total events processed: {result.get('total_events', 0)}")
                print(f"Total odds created/updated: {result.get('total_odds', 0)}")
                print(f"Total averages calculated: {result.get('total_averages', 0)}")
                
                if result.get('errors'):
                    print(f"\nErrors: {len(result['errors'])}")
                    for error in result['errors'][:5]:  # Show first 5
                        print(f"  - {error}")
                    if len(result['errors']) > 5:
                        print(f"  ... and {len(result['errors']) - 5} more")
                
                print("\nPer-Sport Results:")
                for sport_stats in result.get('sports', []):
                    success_icon = "✓" if sport_stats.get('success') else "✗"
                    print(f"  {success_icon} {sport_stats.get('sport_key')}: "
                          f"{sport_stats.get('events_processed', 0)} events, "
                          f"{sport_stats.get('averages_calculated', 0)} averages")
        
        if not args.json:
            print()
            print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 60)
        
        return 0 if result.get('success', True) else 1
        
    except Exception as e:
        if args.json:
            print(json.dumps({'success': False, 'error': str(e)}, indent=2))
        else:
            print(f"\n✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
