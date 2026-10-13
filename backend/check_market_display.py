#!/usr/bin/env python3
"""Over/Under market gösterim kontrolü."""

import sys
import os
sys.path.append(os.path.abspath('.'))

from app.database import get_db
from app.database.models import Match
from app.prediction.service import PredictionService
from app.providers.fotmob import FotMobFootballProvider

def main():
    print("=" * 60)
    print("OVER/UNDER MARKET GÖSTERIM KONTROLÜ")
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

        # Initialize services
        provider = FotMobFootballProvider(base_url="https://www.fotmob.com")
        prediction_service = PredictionService(provider=provider, db_session=session)

        # Get full analysis context
        result = prediction_service.predict_match(match)

        print(f"\n📊 TÜM PREDICTION MARKETS:")
        if result.prediction_markets:
            for i, market in enumerate(result.prediction_markets):
                print(f"Market {i+1}: {market.market_type}")
                if str(market.market_type) == 'PredictionMarketType.OVER_UNDER':
                    line = market.line if market.line else "bilinmeyen"
                    over_prob = market.probabilities.get('over', 0)
                    under_prob = market.probabilities.get('under', 0)

                    print(f"  Line: {line}")
                    print(f"  Over: {over_prob:.6f} ({over_prob*100:.2f}%)")
                    print(f"  Under: {under_prob:.6f} ({under_prob*100:.2f}%)")

                    if over_prob > 0.99:
                        print(f"  ⚠️  BU 99%+ OVER OLASILIK!")
                        if line == 0.5:
                            print(f"      ✅ 0.5 çizgisi için normal")
                        elif line == 2.5:
                            print(f"      ❌ 2.5 çizgisi için aşırı yüksek!")
                        else:
                            print(f"      ❓ {line} çizgisi için beklenmeyen")
                else:
                    # Other market types
                    probs_str = ', '.join([f'{k}: {v:.3f}' for k, v in market.probabilities.items()])
                    print(f"  {probs_str}")
                print()
        else:
            print("❌ Prediction markets bulunamadı")

        # Test script output format ile karşılaştır
        print(f"📋 TEST SCRIPT OUTPUT FORMATINDA:")
        if result.prediction_markets:
            for market in result.prediction_markets[:3]:  # İlk 3 market
                market_type = str(market.market_type)
                if market_type == 'PredictionMarketType.OVER_UNDER':
                    probs_str = ', '.join([f'{k}: {v:.3f}' for k, v in market.probabilities.items()])
                    line_info = f" (Line: {market.line})" if market.line else ""
                    print(f"  {market_type}{line_info}: {probs_str}")
                else:
                    probs_str = ', '.join([f'{k}: {v:.3f}' for k, v in market.probabilities.items()])
                    print(f"  {market_type}: {probs_str}")

    finally:
        session.close()

if __name__ == '__main__':
    main()
