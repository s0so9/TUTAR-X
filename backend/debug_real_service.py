#!/usr/bin/env python
"""Debug real PredictionService feature extraction."""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.database import get_db
from app.api.dependencies import get_data_provider
from app.prediction.service import PredictionService

def main():
    print("=== REAL PREDICTION SERVICE DEBUG ===")

    # Get database session and provider using exact same pattern as endpoint
    session = next(get_db())
    provider = next(get_data_provider())

    # Target match
    match_id = "a57adb1d-c6f8-404f-b085-98bfc584e3ee"
    print(f"Match ID: {match_id}")

    # Get match
    match = provider.get_match(match_id)
    if not match:
        print("ERROR: Match not found!")
        return

    print(f"Match: {match.home_team_id} vs {match.away_team_id}")
    print(f"Scheduled: {match.scheduled_at}")

    # Create PredictionService using exact same pattern as endpoint
    prediction_service = PredictionService(
        provider=provider,
        db_session=session
    )

    # Test MatchFeatureExtractor directly
    print("\n--- MatchFeatureExtractor Direct Test ---")
    features = prediction_service.feature_extractor.extract_features(match)

    target_features = [
        'home_goals_scored_avg', 'away_goals_scored_avg',
        'home_goals_conceded_avg', 'away_goals_conceded_avg'
    ]

    print("Target features from MatchFeatureExtractor:")
    for feat in target_features:
        value = features.get(feat)
        print(f"  {feat}: {value}")

    # Test _extract_canonical_snapshot with detailed debugging
    print("\n--- _extract_canonical_snapshot Test ---")
    try:
        # Step 1: Call extract_features first to get the features dict
        print("Step 1: Getting features from MatchFeatureExtractor")
        features = prediction_service.feature_extractor.extract_features(match)
        print(f"Features dict keys count: {len(features)}")
        print("Key features from extract_features:")
        for feat in target_features:
            value = features.get(feat)
            print(f"  {feat}: {value}")

        # Step 2: Call _extract_canonical_snapshot and inspect each step
        print("\nStep 2: Calling _extract_canonical_snapshot")
        snapshot = prediction_service._extract_canonical_snapshot(match)

        print("\nStep 3: Inspecting snapshot objects BEFORE get_feature_dict")
        print(f"  snapshot.home_strength exists: {snapshot.home_strength is not None}")
        if snapshot.home_strength:
            print(f"  snapshot.home_strength.goals_scored_per_match: {snapshot.home_strength.goals_scored_per_match}")
            print(f"  snapshot.home_strength.goals_conceded_per_match: {snapshot.home_strength.goals_conceded_per_match}")

        print(f"  snapshot.away_strength exists: {snapshot.away_strength is not None}")
        if snapshot.away_strength:
            print(f"  snapshot.away_strength.goals_scored_per_match: {snapshot.away_strength.goals_scored_per_match}")
            print(f"  snapshot.away_strength.goals_conceded_per_match: {snapshot.away_strength.goals_conceded_per_match}")

        # Step 4: Call get_feature_dict to see what happens
        print("\nStep 4: Calling get_feature_dict")
        snapshot_features = snapshot.get_feature_dict()

        print("Target features from snapshot:")
        for feat in target_features:
            value = snapshot_features.get(feat)
            print(f"  {feat}: {value}")

    except Exception as e:
        print(f"ERROR in _extract_canonical_snapshot: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
