#!/usr/bin/env python3
"""Verify historical match retrieval for Arsenal and Leeds United."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.api.dependencies import get_data_provider, get_db
from app.features.match_features import MatchFeatureExtractor
from datetime import datetime

def verify_historical_matches():
    """Verify that historical matches are properly retrieved for both teams."""
    print("=== HISTORICAL MATCH VERIFICATION ===\n")

    # Get provider and database
    provider_gen = get_data_provider()
    provider = next(provider_gen)

    db_gen = get_db()
    db_session = next(db_gen)

    try:
        # Get the target match
        target_match_id = "849f5743-1f96-4ade-be4c-af1c5d3da039"
        match = provider.get_match(target_match_id)

        if not match:
            print("ERROR: Could not retrieve target match")
            return

        print(f"Target Match:")
        print(f"  ID: {match.id}")
        print(f"  Home Team: {match.home_team_id}")
        print(f"  Away Team: {match.away_team_id}")
        print(f"  Scheduled: {match.scheduled_at}")

        # Create feature extractor
        extractor = MatchFeatureExtractor(
            provider=provider,
            db_session=db_session,
            min_matches=3
        )

        print(f"\nBuilding match context...")
        context = extractor._build_match_context(match)

        # Get historical matches for each team
        home_team_matches = context.home_team_history.get_finished_matches()
        away_team_matches = context.away_team_history.get_finished_matches()

        print(f"\nHistorical Match Counts:")
        print(f"  Home team ({match.home_team_id}): {len(home_team_matches)} finished matches")
        print(f"  Away team ({match.away_team_id}): {len(away_team_matches)} finished matches")

        # Show details of historical matches
        if home_team_matches:
            print(f"\nHome team historical matches:")
            for i, hm in enumerate(home_team_matches[:5]):  # Show first 5
                print(f"  {i+1}. {hm.scheduled_at} | {hm.status} | {hm.home_team_id} vs {hm.away_team_id}")
                print(f"      Score: {hm.home_score}-{hm.away_score} | Match ID: {hm.id}")

        if away_team_matches:
            print(f"\nAway team historical matches:")
            for i, am in enumerate(away_team_matches[:5]):  # Show first 5
                print(f"  {i+1}. {am.scheduled_at} | {am.status} | {am.home_team_id} vs {am.away_team_id}")
                print(f"      Score: {am.home_score}-{am.away_score} | Match ID: {am.id}")

        # Extract features to see the calculated values
        print(f"\nExtracting features...")
        features = extractor.extract_features(match)

        key_features = [
            'home_attack_strength', 'home_defense_strength',
            'away_attack_strength', 'away_defense_strength'
        ]

        print(f"\nCalculated Team Strengths:")
        for feature_name in key_features:
            value = features.get(feature_name)
            print(f"  {feature_name}: {value}")

        # Check if minimum data requirement is met
        meets_min_home = len(home_team_matches) >= 3
        meets_min_away = len(away_team_matches) >= 3

        print(f"\nMinimum Data Requirements (3 matches):")
        print(f"  Home team meets requirement: {meets_min_home}")
        print(f"  Away team meets requirement: {meets_min_away}")

        if not meets_min_home or not meets_min_away:
            print(f"\n⚠️  INSUFFICIENT DATA: At least one team has fewer than 3 historical matches")
            print(f"     This explains why team strengths may be 0.0 or None")
        else:
            print(f"\n✅ SUFFICIENT DATA: Both teams have enough historical matches")

        return {
            'home_matches': len(home_team_matches),
            'away_matches': len(away_team_matches),
            'meets_requirements': meets_min_home and meets_min_away,
            'features': {k: features.get(k) for k in key_features}
        }

    except Exception as e:
        print(f"Error during verification: {e}")
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
    verify_historical_matches()
