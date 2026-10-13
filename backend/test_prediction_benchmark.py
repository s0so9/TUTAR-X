#!/usr/bin/env python3
"""
Simple prediction performance benchmark
"""
import time
import asyncio
import sys
import os
from datetime import timedelta
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.providers.development import DevelopmentProvider
from app.prediction.service import PredictionService
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def benchmark_prediction():
    """Benchmark a single prediction request"""

    print("=== PREDICTION PERFORMANCE BENCHMARK ===")

    # Initialize provider
    provider = DevelopmentProvider()

    # Get a suitable match for prediction
    print("Fetching upcoming matches...")
    from datetime import datetime, timezone

    # Get matches from the provider
    matches = provider.get_matches(
        competition_id=None,
        from_date=None,
        to_date=None
    )

    print(f"Total matches found: {len(matches)}")
    for i, match in enumerate(matches[:5]):
        home_team = provider.get_team(match.home_team_id) if match.home_team_id else None
        away_team = provider.get_team(match.away_team_id) if match.away_team_id else None
        print(f"Match {i+1}: {home_team.name if home_team else 'N/A'} vs {away_team.name if away_team else 'N/A'}")
        print(f"  Status: {match.status}")
        print(f"  Scheduled: {match.scheduled_at}")
        print(f"  ID: {match.id}")

    if not matches:
        print("No upcoming matches found")
        return None

    # Find a suitable match (any match with teams)
    suitable_match = None
    for match in matches[:10]:
        home_team = provider.get_team(match.home_team_id) if match.home_team_id else None
        away_team = provider.get_team(match.away_team_id) if match.away_team_id else None
        if home_team and away_team:
            suitable_match = match
            break

    if not suitable_match:
        print("No suitable match found for prediction")
        return None

    print(f"Selected match: {provider.get_team(suitable_match.home_team_id).name} vs {provider.get_team(suitable_match.away_team_id).name}")
    print(f"Match ID: {suitable_match.id}")
    print(f"Scheduled: {suitable_match.scheduled_at}")
    print(f"Status: {suitable_match.status}")

    # Initialize prediction service
    prediction_service = PredictionService(provider=provider, db_session=None)

    # Measure total prediction time
    print("\nStarting prediction generation...")
    start_time = time.time()

    try:
        # Generate prediction
        correlation_id = "benchmark_001"

        analysis_context = prediction_service.generate_full_prediction(
            match=suitable_match,
            odds_data=None,
            correlation_id=correlation_id
        )

        end_time = time.time()
        total_seconds = end_time - start_time
        total_ms = total_seconds * 1000

        print(f"\n=== BENCHMARK RESULTS ===")
        print(f"Total Time: {total_ms:.0f}ms ({total_seconds:.2f}s)")
        print(f"Match: {provider.get_team(suitable_match.home_team_id).name} vs {provider.get_team(suitable_match.away_team_id).name}")

        # Check prediction results
        if analysis_context.model_predictions and len(analysis_context.model_predictions) > 0:
            prediction = analysis_context.model_predictions[0]
            print(f"\n✅ Prediction Generated Successfully")
            print(f"1X2 Probabilities: {prediction.home_win_probability:.3f} / {prediction.draw_probability:.3f} / {prediction.away_win_probability:.3f}")
            print(f"Expected Goals: {prediction.home_xg:.2f} - {prediction.away_xg:.2f}")

            # Check probability sum (should be close to 1.0)
            prob_sum = prediction.home_win_probability + prediction.draw_probability + prediction.away_win_probability
            print(f"Probability Sum: {prob_sum:.3f} {'✅' if 0.99 <= prob_sum <= 1.01 else '❌'}")

            if analysis_context.mensione_pick:
                pick = analysis_context.mensione_pick
                if pick.get('pass_decision'):
                    print(f"MENSIONE Pick: PASS ({pick.get('pass_reason', 'no reason')})")
                else:
                    selection = pick.get('selection', 'N/A')
                    probability = pick.get('probability', 0)
                    confidence = pick.get('confidence', 0)
                    print(f"MENSIONE Pick: {selection} @ {probability:.3f} (confidence: {confidence:.2f})")
        else:
            print(f"❌ No prediction generated")

        return total_ms

    except Exception as e:
        end_time = time.time()
        total_ms = (end_time - start_time) * 1000
        print(f"❌ Error after {total_ms:.0f}ms: {e}")
        logger.exception("Prediction benchmark failed")
        return None

if __name__ == "__main__":
    result = asyncio.run(benchmark_prediction())
    if result:
        print(f"\n🏁 Benchmark completed in {result:.0f}ms")
        if result > 25000:  # 25 seconds
            print("⚠️  Performance is slower than expected (>25s)")
        elif result > 10000:  # 10 seconds
            print("⚠️  Performance could be improved (>10s)")
        else:
            print("✅ Performance is acceptable")
    else:
        print("\n❌ Benchmark failed")
