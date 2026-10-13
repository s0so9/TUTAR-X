#!/usr/bin/env python3
"""Debug the match detail endpoint directly."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import traceback
from app.api.dependencies import get_data_provider
from app.providers.base import FootballDataProvider

def debug_match_detail():
    """Debug match detail endpoint logic directly."""
    print("=== MATCH DETAIL ENDPOINT DEBUG ===\n")

    # Get provider using the same dependency as the endpoint
    provider_gen = get_data_provider()
    provider: FootballDataProvider = next(provider_gen)

    match_id = "f5182fe2-baee-442e-8d7b-f8fafc6660b0"

    try:
        print(f"Step 1: Getting match {match_id}")
        match = provider.get_match(match_id)

        if match is None:
            print(f"ERROR: Match {match_id} not found")
            return

        print(f"✓ Match found: {match.id}")
        print(f"  Home team ID: {match.home_team_id}")
        print(f"  Away team ID: {match.away_team_id}")
        print(f"  Status: {match.status}")

        print(f"\nStep 2: Getting home team {match.home_team_id}")
        try:
            home_team = provider.get_team(match.home_team_id)
            if home_team:
                print(f"✓ Home team found: {home_team.name}")
            else:
                print(f"⚠ Home team not found: {match.home_team_id}")
        except Exception as e:
            print(f"ERROR getting home team: {e}")
            traceback.print_exc()

        print(f"\nStep 3: Getting away team {match.away_team_id}")
        try:
            away_team = provider.get_team(match.away_team_id)
            if away_team:
                print(f"✓ Away team found: {away_team.name}")
            else:
                print(f"⚠ Away team not found: {match.away_team_id}")
        except Exception as e:
            print(f"ERROR getting away team: {e}")
            traceback.print_exc()

        print(f"\nStep 4: Getting team statistics (if finished)")
        print(f"  Match status: {match.status}")
        print(f"  Match status type: {type(match.status)}")

        from app.domain.enums import MatchStatus
        print(f"  MatchStatus.FINISHED: {MatchStatus.FINISHED}")
        print(f"  Status equals FINISHED: {match.status == MatchStatus.FINISHED}")

        if match.status == MatchStatus.FINISHED:
            try:
                team_stats = provider.get_team_match_statistics(match.id)
                print(f"✓ Team statistics found: {len(team_stats)} records")

                # Try first-half stats too
                try:
                    ht_stats = provider.get_team_match_statistics_firsthalf(match.id)
                    print(f"✓ First-half statistics found: {len(ht_stats)} records")
                except Exception as e:
                    print(f"⚠ First-half statistics error: {e}")

            except Exception as e:
                print(f"ERROR getting team statistics: {e}")
                traceback.print_exc()
        else:
            print(f"Match status not finished ({match.status}), skipping statistics")

        print(f"\n✓ All steps completed successfully")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        traceback.print_exc()

    finally:
        try:
            next(provider_gen)
        except StopIteration:
            pass

if __name__ == "__main__":
    debug_match_detail()
