"""Arsenal-Leeds tahmin hattını test et."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# Test prediction pipeline
from app.database.models import Match, Team
from app.prediction.service import PredictionService

def main():
    print("=" * 80)
    print("ARSENAL-LEEDS PREDICTION TEST")
    print("=" * 80)

    # DB setup
    db_path = os.path.join(os.path.dirname(__file__), 'backend', 'football_intelligence.db')
    engine = create_engine(f'sqlite:///{db_path}')
    Session = sessionmaker(bind=engine)
    session = Session()

    # Find the match
    arsenal = session.query(Team).filter(Team.provider_id == '9825').first()
    leeds = session.query(Team).filter(Team.provider_id == '8463').first()

    target_match = session.query(Match).filter(
        Match.home_team_id == arsenal.id,
        Match.away_team_id == leeds.id,
        Match.status == 'MatchStatus.SCHEDULED'
    ).first()

    if not target_match:
        print("ERROR: Arsenal-Leeds scheduled match not found!")
        return

    print(f"\nMatch found:")
    print(f"  ID: {target_match.id}")
    print(f"  Home: Arsenal (ID: {target_match.home_team_id})")
    print(f"  Away: Leeds (ID: {target_match.away_team_id})")
    print(f"  Scheduled: {target_match.scheduled_at}")
    print(f"  Status: {target_match.status}")

    # Count historical matches for each team
    arsenal_finished = session.query(Match).filter(
        or_(Match.home_team_id == arsenal.id, Match.away_team_id == arsenal.id),
        Match.status == 'MatchStatus.FINISHED',
        Match.scheduled_at < target_match.scheduled_at
    ).count()

    leeds_finished = session.query(Match).filter(
        or_(Match.home_team_id == leeds.id, Match.away_team_id == leeds.id),
        Match.status == 'MatchStatus.FINISHED',
        Match.scheduled_at < target_match.scheduled_at
    ).count()

    print(f"\nHistorical data check:")
    print(f"  Arsenal finished matches (before target): {arsenal_finished}")
    print(f"  Leeds finished matches (before target): {leeds_finished}")
    print(f"  Minimum required: 3")

    if arsenal_finished >= 3 and leeds_finished >= 3:
        print(f"  ✅ Both teams have sufficient data!")
    else:
        print(f"  ❌ Insufficient data!")
        return

    # Test prediction service
    print(f"\n" + "=" * 80)
    print("TESTING PREDICTION SERVICE")
    print("=" * 80)

    try:
        # Create prediction service
        prediction_service = PredictionService(Session)

        print(f"\nGenerating prediction for match {target_match.id}...")

        # Generate prediction
        result = prediction_service.predict_match(
            match_id=str(target_match.id)
        )

        print(f"\nPrediction result:")
        print(f"  Type: {type(result)}")

        if hasattr(result, 'prediction_id'):
            print(f"  Prediction ID: {result.prediction_id}")
            print(f"  Home Win: {result.home_win_probability:.1%}")
            print(f"  Draw: {result.draw_probability:.1%}")
            print(f"  Away Win: {result.away_win_probability:.1%}")

            prob_sum = result.home_win_probability + result.draw_probability + result.away_win_probability
            print(f"  Probability Sum: {prob_sum:.3f}")

            if abs(prob_sum - 1.0) < 0.01:
                print(f"  ✅ Probabilities sum correctly!")
            else:
                print(f"  ⚠️  Probability sum issue!")

            print(f"\n✅ SUCCESS: Prediction generated successfully!")

        else:
            print(f"  Unexpected result format: {result}")
            print(f"  ❌ FAILED: Unexpected response")

    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        import traceback
        print(f"\nStacktrace:")
        print(traceback.format_exc())

    session.close()

if __name__ == "__main__":
    main()
