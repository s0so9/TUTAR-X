#!/usr/bin/env python3
"""Debug timezone comparison issue."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import traceback
from datetime import datetime, timezone
from app.api.dependencies import get_data_provider
from app.database.session import get_db
from app.features.match_features import MatchFeatureExtractor

def debug_timezone():
    print("=== TIMEZONE DEBUG ===\n")

    # Get dependencies
    provider_gen = get_data_provider()
    provider = next(provider_gen)
    db_gen = get_db()
    db_session = next(db_gen)

    match_id = "f5182fe2-baee-442e-8d7b-f8fafc6660b0"  # Finished match

    try:
        # Get match
        match = provider.get_match(match_id)
        print(f"Match: {match.home_team_id} vs {match.away_team_id}")
        print(f"Match scheduled_at: {match.scheduled_at}")
        print(f"Match scheduled_at type: {type(match.scheduled_at)}")
        print(f"Match scheduled_at timezone: {match.scheduled_at.tzinfo}")

        # Check database record directly
        print(f"\n--- Database record check ---")
        from app.database.models import Match as MatchDB
        db_match = db_session.query(MatchDB).filter(MatchDB.id == match_id).first()
        if db_match:
            print(f"DB scheduled_at: {db_match.scheduled_at}")
            print(f"DB scheduled_at type: {type(db_match.scheduled_at)}")
            print(f"DB scheduled_at timezone: {db_match.scheduled_at.tzinfo}")

        # Test feature extractor initialization
        print(f"\n--- Feature extractor test ---")
        extractor = MatchFeatureExtractor(
            provider=provider,
            db_session=db_session,
            min_matches=1
        )

        # Try to extract features and catch the exact error
        try:
            features = extractor.extract_features(match)
            print(f"SUCCESS: Features extracted")
        except Exception as e:
            print(f"ERROR in feature extraction: {e}")
            print(f"Error type: {type(e)}")
            traceback.print_exc()

    finally:
        db_session.close()
        try:
            next(provider_gen)
        except StopIteration:
            pass

if __name__ == "__main__":
    debug_timezone()
