"""Arsenal-Leeds maçı için direkt tahmin testi."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

def main():
    print("=" * 80)
    print("DIRECT PREDICTION TEST")
    print("=" * 80)

    # Target match ID
    match_id = "849f5743-1f96-4ade-be4c-af1c5d3da039"
    print(f"Testing match: {match_id}")

    # DB setup
    db_path = os.path.join(os.path.dirname(__file__), 'backend', 'football_intelligence.db')
    engine = create_engine(f'sqlite:///{db_path}')
    Session = sessionmaker(bind=engine)

    try:
        # Import needed components
        from app.prediction.service import PredictionService
        from app.database.models import Match
        from app.providers.development import DevelopmentProvider
        from app.config import Settings

        print(f"\nCreating development provider...")
        # Use development provider for testing
        provider = DevelopmentProvider()

        print(f"Creating PredictionService...")
        service = PredictionService(provider=provider)

        print(f"Fetching match from database...")
        session = Session()
        match = session.query(Match).filter(Match.id == match_id).first()

        if not match:
            print(f"❌ Match not found in database!")
            return

        print(f"Match found: {match.home_team_id} vs {match.away_team_id}")
        print(f"Scheduled: {match.scheduled_at}")
        print(f"Status: {match.status}")

        print(f"Generating prediction...")

        # Call predict_match with Match object
        result = service.predict_match(match)

        print(f"\nResult type: {type(result)}")

        if hasattr(result, 'prediction') and result.prediction:
            prediction = result.prediction
            print(f"\n✅ SUCCESS!")
            print(f"Home Win: {prediction.home_win_probability:.1%}")
            print(f"Draw: {prediction.draw_probability:.1%}")
            print(f"Away Win: {prediction.away_win_probability:.1%}")

            total = prediction.home_win_probability + prediction.draw_probability + prediction.away_win_probability
            print(f"Total: {total:.3f}")

            if hasattr(result, 'mensione_pick') and result.mensione_pick:
                pick = result.mensione_pick
                print(f"\nMensione Pick: {pick.pick_type}")
                print(f"Market: {pick.market_type}")
                print(f"Selection: {pick.selection}")
                print(f"Probability: {pick.probability:.1%}")
                print(f"Confidence: {pick.confidence:.1%}")

        else:
            print(f"\n❌ No prediction in result")
            print(f"Result: {result}")
            if hasattr(result, 'prediction'):
                print(f"Prediction: {result.prediction}")

        session.close()

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    main()
