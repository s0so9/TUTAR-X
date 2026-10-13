#!/usr/bin/env python3
"""Debug why prediction_markets is null in the Arsenal-Leeds case."""

import sys
import os
sys.path.append(os.path.abspath('.'))

from app.prediction.service import PredictionService
from app.database import get_db
from app.providers.fotmob import FotMobFootballProvider
from app.database.models import Match

def debug_market_failure():
    """Debug each step to find where market generation fails."""

    # Test match ID - Arsenal vs Leeds
    target_match_id = '849f5743-1f96-4ade-be4c-af1c5d3da039'

    print("=== DEBUGGING MARKET GENERATION FAILURE ===")

    session = next(get_db())
    provider = FotMobFootballProvider(base_url="https://www.fotmob.com")
    prediction_service = PredictionService(provider=provider, db_session=session)

    try:
        # Get match from database
        match = session.query(Match).filter_by(id=target_match_id).first()
        if not match:
            print("Match not found")
            return

        print(f"Match: {match.home_team_id} vs {match.away_team_id}")

        # Run the full pipeline and capture where it fails
        try:
            context = prediction_service.generate_full_prediction(
                match=match,
                correlation_id="debug_markets"
            )

            # Check prediction markets
            markets_count = len(context.prediction_markets) if context.prediction_markets else 0
            print(f"RESULT: {markets_count} markets generated")

            if markets_count == 0:
                print("NO MARKETS GENERATED")

                # Check if we have a prediction at all
                if hasattr(context, 'model_predictions') and context.model_predictions:
                    print(f"Model predictions exist: {len(context.model_predictions)}")
                    pred = context.model_predictions[0]
                    print(f"   Home win: {pred.home_win_probability:.3f}")
                    print(f"   Draw: {pred.draw_probability:.3f}")
                    print(f"   Away win: {pred.away_win_probability:.3f}")

                    # Check if we have score distribution
                    if hasattr(pred, 'score_distribution') and pred.score_distribution:
                        print(f"Score distribution exists: {len(pred.score_distribution)} scorelines")

                        # Now let's trace the market derivation step
                        # Step 1: Check score_dist_tuples conversion
                        score_dist_tuples = {}
                        for score_key, prob in pred.score_distribution.items():
                            try:
                                if isinstance(score_key, tuple):
                                    score_dist_tuples[score_key] = prob
                                else:
                                    h, a = str(score_key).split('-')
                                    score_dist_tuples[(int(h), int(a))] = prob
                            except (ValueError, AttributeError):
                                continue

                        print(f"Score dist tuples: {len(score_dist_tuples)} items")

                        if score_dist_tuples:
                            try:
                                # Test market derivation directly
                                market_probs = prediction_service.market_derivation_engine.derive(score_dist_tuples)
                                print(f"Market derivation SUCCESS: {type(market_probs)}")
                                print(f"Market probs attributes: {[attr for attr in dir(market_probs) if not attr.startswith('_')]}")
                                print(f"Over/Under structure: {market_probs.over_under}")

                                # Now test the conversion to PredictionMarket objects
                                try:
                                    markets = prediction_service._convert_market_probs_to_prediction_markets(match, market_probs)
                                    print(f"Market conversion SUCCESS: {len(markets)} markets")
                                except Exception as e:
                                    print(f"Market conversion FAILED: {e}")
                                    import traceback
                                    traceback.print_exc()

                            except Exception as e:
                                print(f"Market derivation FAILED: {e}")
                        else:
                            print("Score dist tuples EMPTY!")
                    else:
                        print("NO SCORE DISTRIBUTION - This is likely the root cause!")
                else:
                    print("No model predictions at all")
            else:
                print("Markets generated successfully!")
                for i, market in enumerate(context.prediction_markets[:3]):
                    print(f"   Market {i+1}: {market.type}")

        except Exception as e:
            print(f"Pipeline failed: {e}")
            import traceback
            traceback.print_exc()

    finally:
        session.close()

if __name__ == "__main__":
    debug_market_failure()
