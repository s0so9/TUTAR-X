#!/usr/bin/env python3
"""Over/Under %99.3 olasılığının kök neden analizi."""

import sys
import os
sys.path.append(os.path.abspath('.'))

from app.prediction.service import PredictionService
from app.database import get_db
from app.providers.fotmob import FotMobFootballProvider

def analyze_over_under_calculation():
    """Over/Under hesaplama detaylarını incele."""

    # Test match ID
    target_match_id = 'fcca0ac7-8551-41f1-922e-38ae3c97fce0'

    print("=" * 60)
    print("OVER/UNDER %99.3 OLASILIK KÖK NEDENİ ANALİZİ")
    print("=" * 60)

    # Initialize services
    session = next(get_db())
    provider = FotMobFootballProvider(base_url="https://www.fotmob.com")
    prediction_service = PredictionService(provider=provider, db_session=session)

    try:
        # Get match
        match = session.query(prediction_service.db_service.Match).filter_by(id=target_match_id).first()
        if not match:
            print("❌ Match not found")
            return

        print(f"✅ Match: {match.home_team_id} vs {match.away_team_id}")
        print(f"   Scheduled: {match.scheduled_at}")

        # Get Poisson model result directly
        try:
            # We need to trace the prediction path to see Poisson calculations
            context = prediction_service.build_analysis_context(
                match=match,
                home_team=None,  # Will be fetched internally
                away_team=None,  # Will be fetched internally
                competition=None  # Will be fetched internally
            )

            print(f"\n🔍 ENSEMBLE PREDICTION FOUND")
            if context.ensemble_prediction:
                pred = context.ensemble_prediction
                print(f"   Home win: {pred.home_win_probability:.3f}")
                print(f"   Draw: {pred.draw_probability:.3f}")
                print(f"   Away win: {pred.away_win_probability:.3f}")
                print(f"   Model ID: {pred.model_id}")

            # Check prediction markets
            if context.prediction_markets:
                print(f"\n📊 PREDICTION MARKETS:")
                for market in context.prediction_markets:
                    if str(market.market_type) == 'PredictionMarketType.OVER_UNDER':
                        line = market.line if market.line else "unknown"
                        over_prob = market.probabilities.get('over', 0)
                        under_prob = market.probabilities.get('under', 0)

                        print(f"   Over/Under {line}:")
                        print(f"     Over: {over_prob:.6f} ({over_prob*100:.2f}%)")
                        print(f"     Under: {under_prob:.6f} ({under_prob*100:.2f}%)")
                        print(f"     Total: {over_prob + under_prob:.6f}")

                        if over_prob > 0.99:
                            print(f"     ⚠️  AŞIRI YÜKSEK OVER OLASILIK!")

            # Check if we can access individual model results
            if context.model_predictions:
                print(f"\n🔬 INDIVIDUAL MODEL PREDICTIONS:")
                for i, pred in enumerate(context.model_predictions):
                    print(f"   Model {i+1}: {pred.model_id}")
                    print(f"     Home: {pred.home_win_probability:.3f}")
                    print(f"     Draw: {pred.draw_probability:.3f}")
                    print(f"     Away: {pred.away_win_probability:.3f}")

        except Exception as e:
            print(f"❌ Prediction failed: {e}")
            import traceback
            traceback.print_exc()

    finally:
        session.close()

def analyze_expected_goals():
    """Expected goals hesaplamalarını incele."""

    target_match_id = 'fcca0ac7-8551-41f1-922e-38ae3c97fce0'
    session = next(get_db())

    try:
        # Get match and teams
        from app.database.models import Match, Team
        match = session.query(Match).filter_by(id=target_match_id).first()

        if match:
            home_team = session.query(Team).filter_by(id=match.home_team_id).first()
            away_team = session.query(Team).filter_by(id=match.away_team_id).first()

            print(f"\n🏟️  TEAM INFO:")
            print(f"   Home: {home_team.name if home_team else 'Unknown'} ({match.home_team_id})")
            print(f"   Away: {away_team.name if away_team else 'Unknown'} ({match.away_team_id})")

            # Check if we have any historical xG data
            historical_matches = session.query(Match).filter(
                ((Match.home_team_id == match.home_team_id) | (Match.away_team_id == match.home_team_id) |
                 (Match.home_team_id == match.away_team_id) | (Match.away_team_id == match.away_team_id)) &
                (Match.scheduled_at < match.scheduled_at) &
                (Match.status == 'FINISHED') &
                (Match.home_xg.isnot(None)) &
                (Match.away_xg.isnot(None))
            ).limit(10).all()

            if historical_matches:
                print(f"\n📈 RECENT xG DATA (sample):")
                total_xg = 0
                count = 0
                for hm in historical_matches[:5]:
                    total_xg += (hm.home_xg or 0) + (hm.away_xg or 0)
                    count += 1
                    print(f"   {hm.scheduled_at.date()}: {hm.home_xg:.2f} + {hm.away_xg:.2f} = {(hm.home_xg or 0) + (hm.away_xg or 0):.2f} xG")

                if count > 0:
                    avg_total_xg = total_xg / count
                    print(f"   Average total xG: {avg_total_xg:.2f}")

                    if avg_total_xg > 3.0:
                        print(f"   ⚠️  Yüksek xG ortalaması - Over 2.5 için yüksek olasılık beklenir")
            else:
                print(f"   ⚠️  xG verisi bulunamadı")

    finally:
        session.close()

if __name__ == '__main__':
    analyze_over_under_calculation()
    analyze_expected_goals()
