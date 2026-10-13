#!/usr/bin/env python3
"""Debug the team ID mismatch in strength calculations."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.api.dependencies import get_data_provider, get_db
from app.features.match_features import MatchFeatureExtractor

def debug_team_id_mismatch():
    """Debug the team ID mismatch between context and matches."""
    print("=== TEAM ID MISMATCH DEBUG ===\n")

    # Get provider and database
    provider_gen = get_data_provider()
    provider = next(provider_gen)

    db_gen = get_db()
    db_session = next(db_gen)

    try:
        # Get the target match
        target_match_id = "849f5743-1f96-4ade-be4c-af1c5d3da039"
        match = provider.get_match(target_match_id)

        print(f"Target match team IDs:")
        print(f"  Home team ID: {match.home_team_id}")
        print(f"  Away team ID: {match.away_team_id}")

        # Create feature extractor
        extractor = MatchFeatureExtractor(
            provider=provider,
            db_session=db_session,
            min_matches=3
        )

        # Build context
        context = extractor._build_match_context(match)

        print(f"\nContext team IDs:")
        print(f"  Home team context ID: {context.home_team_history.team_id}")
        print(f"  Away team context ID: {context.away_team_history.team_id}")

        # Check historical matches
        home_matches = context.home_team_history.get_finished_matches()
        away_matches = context.away_team_history.get_finished_matches()

        print(f"\nHistorical match team IDs (first 3):")

        for i, hm in enumerate(home_matches[:3]):
            print(f"  Home match {i+1}: home_team_id={hm.home_team_id}, away_team_id={hm.away_team_id}")

        for i, am in enumerate(away_matches[:3]):
            print(f"  Away match {i+1}: home_team_id={am.home_team_id}, away_team_id={am.away_team_id}")

        # Test manual goal calculation
        print(f"\nManual goal calculation test:")
        print(f"Checking if context.home_team_history.team_id matches any team IDs in historical matches...")

        context_home_id = context.home_team_history.team_id

        matching_home_ids = set()
        matching_away_ids = set()

        for hm in home_matches:
            if hm.home_team_id == context_home_id:
                matching_home_ids.add(hm.home_team_id)
            if hm.away_team_id == context_home_id:
                matching_away_ids.add(hm.away_team_id)

        print(f"  Context home team ID: {context_home_id}")
        print(f"  Matches found as home team: {len(matching_home_ids)} unique IDs: {matching_home_ids}")
        print(f"  Matches found as away team: {len(matching_away_ids)} unique IDs: {matching_away_ids}")

        if not matching_home_ids and not matching_away_ids:
            print(f"  ❌ NO MATCHES FOUND! Context team ID doesn't match any historical match team IDs")
        else:
            print(f"  ✅ Matches found")

        return {
            'context_home_id': context_home_id,
            'historical_team_ids': {hm.home_team_id for hm in home_matches} | {hm.away_team_id for hm in home_matches},
            'matches_found': len(matching_home_ids) + len(matching_away_ids) > 0
        }

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        db_session.close()
        try:
            next(provider_gen)
        except StopIteration:
            pass

if __name__ == "__main__":
    debug_team_id_mismatch()
