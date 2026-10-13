#!/usr/bin/env python3
"""Simple prediction debugging."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.api.dependencies import get_data_provider
from app.database.session import get_db
from app.features.match_features import MatchFeatureExtractor

def debug_simple():
    print("=== SIMPLE PREDICTION DEBUG ===\n")

    # Get dependencies
    provider_gen = get_data_provider()
    provider = next(provider_gen)
    db_gen = get_db()
    db_session = next(db_gen)

    match_id = "f5182fe2-baee-442e-8d7b-f8fafc6660b0"  # Use finished match

    try:
        # Get match
        match = provider.get_match(match_id)
        print(f"Match: {match.home_team_id} vs {match.away_team_id}")
        print(f"Scheduled: {match.scheduled_at}")

        # Test feature extractor with different min_matches values
        for min_matches in [3, 2, 1]:
            print(f"\n--- Testing with min_matches={min_matches} ---")

            extractor = MatchFeatureExtractor(
                provider=provider,
                db_session=db_session,
                min_matches=min_matches
            )

            features = extractor.extract_features(match)

            print(f"Features extracted: {len(features)}")
            print(f"Home match count: {features.get('home_match_count')}")
            print(f"Away match count: {features.get('away_match_count')}")
            print(f"Both sufficient: {features.get('both_sufficient')}")
            print(f"Home attack strength: {features.get('home_attack_strength')}")
            print(f"Away attack strength: {features.get('away_attack_strength')}")

            if features.get('both_sufficient'):
                print("✓ Sufficient data for prediction!")
                break
            else:
                print("✗ Insufficient data")

    finally:
        db_session.close()
        try:
            next(provider_gen)
        except StopIteration:
            pass

if __name__ == "__main__":
    debug_simple()
