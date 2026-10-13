#!/usr/bin/env python3
"""Detailed prediction debugging with step-by-step logging."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import logging
from app.api.dependencies import get_data_provider
from app.database.session import get_db
from app.prediction.service import PredictionService

def setup_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    # Enable specific loggers
    logging.getLogger('app.prediction').setLevel(logging.DEBUG)
    logging.getLogger('app.features').setLevel(logging.DEBUG)
    logging.getLogger('app.database').setLevel(logging.DEBUG)

def debug_prediction_detailed():
    setup_logging()
    print("=== DETAILED PREDICTION DEBUG ===\n")

    # Get dependencies
    provider_gen = get_data_provider()
    provider = next(provider_gen)
    db_gen = get_db()
    db_session = next(db_gen)

    match_id = "eb12aca4-4319-4f70-9320-4903714fe90d"

    try:
        # Get match
        print(f"1. Getting match {match_id}")
        match = provider.get_match(match_id)
        print(f"   Match found: {match.home_team_id} vs {match.away_team_id}")
        print(f"   Scheduled: {match.scheduled_at}")

        # Initialize prediction service
        print(f"\n2. Initializing prediction service")
        prediction_service = PredictionService(
            provider=provider,
            db_session=db_session
        )
        print(f"   Feature extractor min_matches: {prediction_service.feature_extractor.min_matches}")

        # Test feature extraction directly
        print(f"\n3. Testing feature extraction")
        features = prediction_service.feature_extractor.extract_features(match)
        print(f"   Features extracted: {len(features)}")

        # Print key features that affect prediction
        key_features = [
            "home_match_count", "away_match_count",
            "home_sufficient", "away_sufficient", "both_sufficient",
            "min_required",
            "home_attack_strength", "away_attack_strength",
            "home_defense_strength", "away_defense_strength"
        ]

        print(f"\n   Key features:")
        for feat in key_features:
            val = features.get(feat)
            print(f"     {feat}: {val}")

        # Test data quality assessment
        print(f"\n4. Testing data quality assessment")
        from app.prediction.data_quality_gate import DataQualityGate
        data_quality_gate = DataQualityGate()
        quality_report = data_quality_gate.assess(features)

        print(f"   Overall score: {quality_report.overall_score:.3f}")
        print(f"   Missing critical: {quality_report.missing_critical_features}")
        print(f"   Missing recommended: {quality_report.missing_recommended_features}")

        # Test full prediction pipeline
        print(f"\n5. Testing full prediction pipeline")
        try:
            analysis_context = prediction_service.generate_full_prediction(
                match=match,
                odds_data=None,
                correlation_id="debug"
            )
            print(f"   SUCCESS: Generated prediction")
            print(f"   Model predictions: {len(analysis_context.model_predictions) if analysis_context.model_predictions else 0}")
        except Exception as e:
            print(f"   ERROR: {e}")
            import traceback
            traceback.print_exc()

    finally:
        db_session.close()
        try:
            next(provider_gen)
        except StopIteration:
            pass

if __name__ == "__main__":
    debug_prediction_detailed()
