#!/usr/bin/env python
"""Diagnose which models have missing requirements."""

import logging
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.database import get_db
from app.providers.development import DevelopmentProvider
from app.prediction.service import PredictionService
from app.prediction.model_orchestrator import ModelOrchestrator
from app.prediction.feature_snapshot import extract_feature_snapshot

# Set up logging
logging.basicConfig(level=logging.ERROR)  # Only errors to reduce noise

def main():
    print("=== MODEL REQUIREMENTS DIAGNOSIS ===")

    # Get database session and provider using the same pattern as API
    session = next(get_db())

    # Use DevelopmentProvider directly (simpler for debugging)
    from app.providers.development import DevelopmentProvider
    provider = DevelopmentProvider()

    # Target match
    match_id = "a57adb1d-c6f8-404f-b085-98bfc584e3ee"
    print(f"Match ID: {match_id}")

    # Get match
    match = provider.get_match(match_id)
    print(f"Match: {match.home_team_id} vs {match.away_team_id}")
    print(f"Scheduled: {match.scheduled_at}")

    # Extract feature snapshot
    print("\n--- Step 1: Feature Snapshot ---")
    snapshot = extract_feature_snapshot(match=match, provider=provider, db_session=session)
    features = snapshot.get_feature_dict()

    # Show all features
    print(f"Feature count: {len(features)}")
    print("Available features:")
    for key, value in features.items():
        if value is not None:
            print(f"  {key}: {value}")

    print("\nMissing (None) features:")
    for key, value in features.items():
        if value is None:
            print(f"  {key}: None")

    # Create orchestrator
    print("\n--- Step 2: Model Requirements ---")
    orchestrator = ModelOrchestrator.create_default_registry()

    # Check each model
    for model_id, model in orchestrator._models.items():
        metadata = model.get_metadata()
        requirements_met, missing = model.check_requirements(features)

        print(f"\nModel: {model_id}")
        print(f"  Required features: {metadata.required_features}")
        print(f"  Requirements met: {requirements_met}")
        if not requirements_met:
            print(f"  Missing features: {missing}")

            # Check values of missing features
            print("  Missing feature values:")
            for feat in missing:
                value = features.get(feat)
                print(f"    {feat}: {value}")

if __name__ == "__main__":
    main()
