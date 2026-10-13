#!/usr/bin/env python3
"""Debug the prediction chain step by step for a real match."""

import sys
sys.path.append('.')

from app.database import SessionLocal
from app.database.models import Match
from app.prediction.service import PredictionService
from app.providers.hybrid_provider import HybridProvider
from app.config import settings
import traceback
import uuid
import logging

# Set up logging to see all details
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def debug_prediction_chain():
    """Debug prediction chain step by step."""
    match_id = "a57adb1d-c6f8-404f-b085-98bfc584e3ee"
    correlation_id = str(uuid.uuid4())[:8]

    print(f"\n=== DEBUGGING PREDICTION CHAIN [{correlation_id}] ===")
    print(f"Match ID: {match_id}")

    # Step 1: Database connection
    print(f"\n[{correlation_id}] Step 1: Database connection")
    session = SessionLocal()
    try:
        match_db = session.query(Match).filter(Match.id == match_id).first()
        if match_db:
            print(f"OK Match found in DB: {match_db.home_team_id} vs {match_db.away_team_id}")
            print(f"  Status: {match_db.status}")
            print(f"  Scheduled: {match_db.scheduled_at}")
        else:
            print(f"ERROR Match not found in database")
            return
    except Exception as e:
        print(f"ERROR Database error: {e}")
        return

    # Step 2: Provider initialization
    print(f"\n[{correlation_id}] Step 2: Provider initialization")
    try:
        provider = HybridProvider(settings, session)
        print(f"OK Provider initialized: {type(provider)}")
    except Exception as e:
        print(f"ERROR Provider initialization failed: {e}")
        traceback.print_exc()
        return

    # Step 3: Get match from provider
    print(f"\n[{correlation_id}] Step 3: Get match from provider")
    try:
        match = provider.get_match(match_id)
        if match:
            print(f"OK Match retrieved: {match.home_team_id} vs {match.away_team_id}")
            print(f"  Home team name: {getattr(match, 'home_team_name', 'N/A')}")
            print(f"  Away team name: {getattr(match, 'away_team_name', 'N/A')}")
        else:
            print(f"ERROR Match not found by provider")
            return
    except Exception as e:
        print(f"ERROR Provider get_match failed: {e}")
        traceback.print_exc()
        return

    # Step 4: Initialize prediction service
    print(f"\n[{correlation_id}] Step 4: Initialize prediction service")
    try:
        prediction_service = PredictionService(
            provider=provider,
            db_session=session
        )
        print(f"OK PredictionService initialized")
    except Exception as e:
        print(f"ERROR PredictionService initialization failed: {e}")
        traceback.print_exc()
        return

    # Step 5: Generate full prediction - THIS IS WHERE THE ERROR OCCURS
    print(f"\n[{correlation_id}] Step 5: Generate full prediction")
    try:
        analysis_context = prediction_service.generate_full_prediction(
            match=match,
            odds_data=None,
            correlation_id=correlation_id
        )
        print(f"OK generate_full_prediction completed")
        print(f"  Model predictions count: {len(analysis_context.model_predictions) if analysis_context.model_predictions else 0}")
        if analysis_context.model_predictions:
            prediction = analysis_context.model_predictions[0]
            print(f"  First prediction: {prediction}")
        else:
            print(f"  ERROR NO MODEL PREDICTIONS GENERATED!")
            print(f"  Analysis context: {analysis_context}")
    except Exception as e:
        print(f"ERROR generate_full_prediction FAILED: {e}")
        traceback.print_exc()
        return

    print(f"\n[{correlation_id}] === DEBUG COMPLETE ===")

if __name__ == "__main__":
    debug_prediction_chain()
