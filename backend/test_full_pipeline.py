#!/usr/bin/env python3
"""Test the full prediction pipeline with fallback."""

import sys
sys.path.append('.')

from app.database import SessionLocal
from app.providers.hybrid_provider import HybridProvider
from app.prediction.service import PredictionService
from app.config import settings

def test_full_pipeline():
    """Test full pipeline."""
    match_id = "a57adb1d-c6f8-404f-b085-98bfc584e3ee"

    print(f"\n=== TESTING FULL PIPELINE ===")
    print(f"Match ID: {match_id}")

    session = SessionLocal()
    try:
        provider = HybridProvider(settings, session)
        match = provider.get_match(match_id)

        # Initialize prediction service
        prediction_service = PredictionService(
            provider=provider,
            db_session=session
        )

        print(f"\nGenerating prediction...")
        analysis_context = prediction_service.generate_full_prediction(
            match=match,
            odds_data=None,
            correlation_id="test-pipeline"
        )

        print(f"\nResults:")
        print(f"  model_predictions: {analysis_context.model_predictions}")
        print(f"  models_used: {analysis_context.models_used}")

        if analysis_context.model_predictions:
            pred = analysis_context.model_predictions[0]
            print(f"  Prediction:")
            print(f"    home_win: {pred.home_win_probability}")
            print(f"    draw: {pred.draw_probability}")
            print(f"    away_win: {pred.away_win_probability}")
        else:
            print(f"  ERROR: No predictions generated!")
            print(f"  missing_data_notes: {analysis_context.missing_data_notes}")

    finally:
        session.close()

    print(f"\n=== TEST COMPLETE ===")

if __name__ == "__main__":
    test_full_pipeline()
