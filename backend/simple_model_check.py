#!/usr/bin/env python
"""Simple model requirements check using the exact same flow as endpoint."""

import logging
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.database import get_db
from app.prediction.service import PredictionService
from app.prediction.model_orchestrator import ModelOrchestrator

# Set up logging
logging.basicConfig(level=logging.WARNING)

def main():
    print("=== SIMPLE MODEL REQUIREMENTS CHECK ===")

    # Get database session using exact same pattern as endpoint
    session = next(get_db())

    # Get provider using same pattern as endpoint
    from app.api.dependencies import get_data_provider
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

    # Test model orchestrator directly
    print("\n--- Testing ModelOrchestrator ---")
    orchestrator = ModelOrchestrator.create_default_registry()

    print(f"Registered models: {orchestrator.get_registered_models()}")

    # Extract feature snapshot using PredictionService internals
    print("\n--- Extracting Feature Snapshot ---")
    from app.prediction.feature_snapshot import extract_feature_snapshot

    try:
        # Extract feature snapshot using correct parameters
        snapshot = extract_feature_snapshot(
            match_id=match.id,
            home_team_id=match.home_team_id,
            away_team_id=match.away_team_id,
        )
        features = snapshot.get_feature_dict()

        print(f"Feature count: {len(features)}")

        # Show key features that models need
        key_features = [
            'home_goals_scored_avg', 'away_goals_scored_avg',
            'home_goals_conceded_avg', 'away_goals_conceded_avg',
            'elo_home', 'elo_away',
            'home_expected_goals', 'away_expected_goals'
        ]

        print("\nKey feature values:")
        for feat in key_features:
            value = features.get(feat)
            print(f"  {feat}: {value}")

        # Test orchestrator
        print("\n--- Running ModelOrchestrator ---")
        result = orchestrator.run_all(snapshot)

        print(f"Total models: {result.total_models}")
        print(f"Successful: {len(result.successful_predictions)}")
        print(f"Unavailable: {len(result.unavailable_models)}")
        print(f"Failed: {len(result.failed_models)}")

        # Show details for each unavailable model
        if result.unavailable_models:
            print("\nUnavailable models:")
            for output in result.unavailable_models:
                print(f"  {output.model_id}: {output.availability.reason if output.availability else 'No reason'}")
                if output.diagnostics and 'missing_features' in output.diagnostics:
                    missing = output.diagnostics['missing_features']
                    print(f"    Missing: {missing}")

        # Show details for failed models
        if result.failed_models:
            print("\nFailed models:")
            for output in result.failed_models:
                print(f"  {output.model_id}: {output.error_message}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
