#!/usr/bin/env python3
"""Arsenal-Leeds lambda ve Over/Under debug analizi."""

import sys
import os
sys.path.append(os.path.abspath('.'))

from app.database import get_db
from app.database.models import Match
from app.prediction.service import PredictionService
from app.providers.fotmob import FotMobFootballProvider
from app.prediction.poisson import PoissonModel

def main():
    print("=" * 60)
    print("ARSENAL-LEEDS LAMBDA VE OVER/UNDER DEBUG ANALİZİ")
    print("=" * 60)

    # Arsenal-Leeds match ID
    match_id = '849f5743-1f96-4ade-be4c-af1c5d3da039'

    session = next(get_db())
    try:
        # Get match
        match = session.query(Match).filter_by(id=match_id).first()
        if not match:
            print("❌ Match not found")
            return

        print(f"✅ Match: Arsenal vs Leeds United")
        print(f"   Date: {match.scheduled_at}")
        print()

        # Initialize services
        provider = FotMobFootballProvider(base_url="https://www.fotmob.com")
        prediction_service = PredictionService(provider=provider, db_session=session)

        # Extract features
        print("🔍 FEATURE EXTRACTION:")
        features = prediction_service.feature_extractor.extract_features(match)

        # Key strength features
        home_attack = features.get("home_attack_strength")
        away_attack = features.get("away_attack_strength")
        home_defense = features.get("home_defense_strength")
        away_defense = features.get("away_defense_strength")

        print(f"   Arsenal Attack Strength: {home_attack}")
        print(f"   Arsenal Defense Strength: {home_defense}")
        print(f"   Leeds Attack Strength: {away_attack}")
        print(f"   Leeds Defense Strength: {away_defense}")

        if any(v is None for v in [home_attack, away_attack, home_defense, away_defense]):
            print("❌ Missing strength features")
            return

        # Calculate lambdas
        print(f"\n⚡ LAMBDA CALCULATION:")
        poisson_model = prediction_service.poisson_model

        home_lambda = poisson_model.estimate_lambda_from_features(
            home_attack, away_defense, 1.0  # venue_adjustment=1.0 for neutral
        )
        away_lambda = poisson_model.estimate_lambda_from_features(
            away_attack, home_defense, 1.0
        )

        print(f"   Arsenal Lambda (expected goals): {home_lambda:.3f}")
        print(f"   Leeds Lambda (expected goals): {away_lambda:.3f}")
        print(f"   Total Expected Goals: {home_lambda + away_lambda:.3f}")

        # Generate Poisson prediction
        print(f"\n📊 POISSON PREDICTION:")
        poisson_result = poisson_model.predict_from_lambda(home_lambda, away_lambda)

        print(f"   1X2: H={poisson_result.home_win_probability:.3f}, D={poisson_result.draw_probability:.3f}, A={poisson_result.away_win_probability:.3f}")
        print(f"   BTTS: Yes={poisson_result.btts_yes_probability:.3f}, No={poisson_result.btts_no_probability:.3f}")

        # Over/Under analysis
        print(f"\n🎯 OVER/UNDER ANALİZİ:")
        for line, (over_prob, under_prob) in poisson_result.over_under_probabilities.items():
            print(f"   Line {line}: Over={over_prob:.6f} ({over_prob*100:.2f}%), Under={under_prob:.6f} ({under_prob*100:.2f}%)")

            # Check for extreme probabilities
            if over_prob > 0.95:
                print(f"     ⚠️  AŞIRI YÜKSEK OVER: {over_prob*100:.1f}%")

        # Calculate manual verification for 2.5 line
        print(f"\n🧮 MANUEL DOĞRULAMA (2.5 Çizgisi):")

        # Get scoreline probabilities
        scoreline_probs = {}
        max_goals = 10  # Reasonable upper bound

        from math import exp, factorial

        total_manual_prob = 0.0
        over_2_5_manual = 0.0
        under_2_5_manual = 0.0

        print("   Başlıca skorlar ve olasılıkları:")
        for h in range(max_goals + 1):  # Calculate all scores up to max_goals
            for a in range(max_goals + 1):
                # Poisson probability calculation
                prob_h = (home_lambda ** h) * exp(-home_lambda) / factorial(h)
                prob_a = (away_lambda ** a) * exp(-away_lambda) / factorial(a)
                prob = prob_h * prob_a

                scoreline_probs[(h, a)] = prob
                total_manual_prob += prob

                total_goals = h + a
                if total_goals > 2.5:
                    over_2_5_manual += prob
                else:
                    under_2_5_manual += prob

                if h <= 3 and a <= 3:  # Show only first few for display
                    print(f"     {h}-{a}: {prob:.4f} ({prob*100:.2f}%) [Total: {total_goals}]")

        print(f"\n   Manuel Hesaplama 2.5 Çizgisi:")
        print(f"     Over 2.5: {over_2_5_manual:.6f} ({over_2_5_manual*100:.2f}%)")
        print(f"     Under 2.5: {under_2_5_manual:.6f} ({under_2_5_manual*100:.2f}%)")
        print(f"     Toplam Olasılık: {total_manual_prob:.6f}")

        # Compare with model result
        model_2_5 = poisson_result.over_under_probabilities.get(2.5)
        if model_2_5:
            model_over, model_under = model_2_5
            print(f"\n   Model vs Manuel Karşılaştırma:")
            print(f"     Model Over: {model_over:.6f} vs Manuel: {over_2_5_manual:.6f}")
            print(f"     Model Under: {model_under:.6f} vs Manuel: {under_2_5_manual:.6f}")

            over_diff = abs(model_over - over_2_5_manual)
            if over_diff > 0.001:
                print(f"     ⚠️  FARKLILIIK: {over_diff:.6f}")
            else:
                print(f"     ✅ Uyumlu (fark: {over_diff:.6f})")

    finally:
        session.close()

if __name__ == '__main__':
    main()
