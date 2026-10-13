#!/usr/bin/env python3
"""Debug the feature aggregator specifically."""

import sys
sys.path.append('.')

from app.database import SessionLocal
from app.database.models import Match
from app.features.aggregator import FeatureAggregator
from app.config import settings
import traceback
from datetime import datetime

def debug_feature_aggregator():
    """Debug feature aggregator step by step."""
    match_id = "a57adb1d-c6f8-404f-b085-98bfc584e3ee"

    print(f"\n=== DEBUGGING FEATURE AGGREGATOR ===")
    print(f"Match ID: {match_id}")

    # Step 1: Database connection and match lookup
    session = SessionLocal()
    try:
        match = session.query(Match).filter(Match.id == match_id).first()
        if not match:
            print("ERROR: Match not found")
            return

        print(f"OK Match: {match.home_team_id} vs {match.away_team_id}")
        print(f"  Scheduled: {match.scheduled_at}")

        # Step 2: Initialize FeatureAggregator
        aggregator = FeatureAggregator(session=session)
        print(f"OK FeatureAggregator initialized")

        # Step 3: Call extract_features_for_match with correct method name
        try:
            print(f"Calling extract_features_for_match with:")
            print(f"  match_id: {match.id}")

            feature_set = aggregator.extract_features_for_match(
                match_id=match.id
            )

            if feature_set is None:
                print("ERROR: feature_set is None")
            else:
                print(f"OK feature_set created: {type(feature_set)}")
                print(f"  Home team: {feature_set.home_team_id}")
                print(f"  Away team: {feature_set.away_team_id}")
                print(f"  Match date: {feature_set.match_date}")

                # Check key feature values
                attrs = ['home_goals_scored_avg', 'home_goals_conceded_avg',
                        'away_goals_scored_avg', 'away_goals_conceded_avg',
                        'elo_home', 'elo_away']
                for attr in attrs:
                    value = getattr(feature_set, attr, 'NOT_FOUND')
                    print(f"  {attr}: {value}")

        except Exception as e:
            print(f"ERROR: aggregate_features FAILED: {type(e).__name__}: {e}")
            traceback.print_exc()

    finally:
        session.close()

    print(f"\n=== DEBUG COMPLETE ===")

if __name__ == "__main__":
    debug_feature_aggregator()
