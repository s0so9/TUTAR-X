#!/usr/bin/env python3
"""Debug specific match to understand prediction flow."""

from app.providers.hybrid_provider import HybridProvider
from app.providers.adapter import ProviderManagerAdapter
from app.providers.manager import ProviderManager
from app.providers.development import DevelopmentProvider
from app.database import SessionLocal
from app.prediction.service import PredictionService

def debug_match(match_id):
    """Debug specific match data and prediction flow."""
    # Initialize providers
    dev_provider = DevelopmentProvider()
    manager = ProviderManager(None, None, dev_provider)
    adapter = ProviderManagerAdapter(manager)
    session = SessionLocal()
    hybrid = HybridProvider(adapter, session)

    print(f"=== DEBUGGING MATCH: {match_id} ===")

    # Step 1: Check if match exists
    match = hybrid.get_match(match_id)

    if not match:
        print(f"❌ Match not found: {match_id}")
        session.close()
        return False

    print(f"✅ Match found:")
    print(f"  Home Team ID: {match.home_team_id}")
    print(f"  Away Team ID: {match.away_team_id}")
    print(f"  Status: {match.status}")
    print(f"  Scheduled: {match.scheduled_at}")
    print(f"  Home Score: {match.home_score}")
    print(f"  Away Score: {match.away_score}")

    # Step 2: Get team names
    home_team = hybrid.get_team(match.home_team_id)
    away_team = hybrid.get_team(match.away_team_id)

    home_name = home_team.name if home_team else "Not found"
    away_name = away_team.name if away_team else "Not found"

    print(f"  Home Team: {home_name}")
    print(f"  Away Team: {away_name}")

    # Step 3: Check if this should load prediction
    should_load = str(match.status) in ['MatchStatus.SCHEDULED', 'MatchStatus.POSTPONED'] or match.status.value in ['scheduled', 'postponed']
    print(f"  Should load prediction: {should_load} (status: {match.status}, value: {match.status.value})")

    if should_load:
        # Step 4: Try prediction service
        try:
            print("\n=== PREDICTION SERVICE TEST ===")
            prediction_service = PredictionService(provider=hybrid, db_session=session)

            analysis_context = prediction_service.generate_full_prediction(
                match=match,
                odds_data=None,
                correlation_id=f"debug-{match_id[:8]}"
            )

            if analysis_context.model_predictions:
                pred = analysis_context.model_predictions[0]
                print(f"✅ Prediction successful:")
                print(f"  Home win: {pred.home_win_probability:.3f}")
                print(f"  Draw: {pred.draw_probability:.3f}")
                print(f"  Away win: {pred.away_win_probability:.3f}")
                return True
            else:
                print("❌ No predictions generated")
                return False

        except Exception as e:
            print(f"❌ Prediction failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    else:
        print("ℹ️ Match status does not require prediction")
        return True

    session.close()

def find_sample_match():
    """Find a sample SCHEDULED match to debug."""
    from app.providers.hybrid_provider import HybridProvider
    from app.providers.adapter import ProviderManagerAdapter
    from app.providers.manager import ProviderManager
    from app.providers.development import DevelopmentProvider
    from app.database import SessionLocal

    # Initialize providers
    dev_provider = DevelopmentProvider()
    manager = ProviderManager(None, None, dev_provider)
    adapter = ProviderManagerAdapter(manager)
    session = SessionLocal()
    hybrid = HybridProvider(adapter, session)

    # Get SCHEDULED matches
    matches = hybrid.get_matches(status='SCHEDULED')
    print(f"Found {len(matches)} SCHEDULED matches")

    if matches:
        match = matches[0]
        print(f"Sample match ID: {match.id}")

        home_team = hybrid.get_team(match.home_team_id)
        away_team = hybrid.get_team(match.away_team_id)

        home_name = home_team.name if home_team else "Unknown"
        away_name = away_team.name if away_team else "Unknown"

        print(f"Teams: {home_name} vs {away_name}")
        session.close()
        return match.id

    session.close()
    return None

if __name__ == "__main__":
    # Use the real Fluminense vs Coritiba match ID
    match_id = "aa4c9808-cb36-486e-bd41-003cc28b8543"
    print(f"Testing with real Fluminense vs Coritiba match: {match_id}")
    success = debug_match(match_id)

    if not success:
        print("\n=== TRYING SAMPLE MATCH ===")
        sample_id = find_sample_match()
        if sample_id:
            debug_match(sample_id)
