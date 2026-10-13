#!/usr/bin/env python3
"""Test prediction service directly with real canonical UUID."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import time
from datetime import datetime
from app.prediction.service import PredictionService
from app.database.session import SessionLocal
from app.providers.fotmob import FotMobFootballProvider

def main():
    print('='*80)
    print('VALIDATING FULL PIPELINE WITH REAL CANONICAL MATCH UUID')
    print('='*80)

    # Real Arsenal-Leeds Match UUID
    match_id = '849f5743-1f96-4ade-be4c-af1c5d3da039'

    print(f'Match ID: {match_id}')
    print(f'Timestamp: {datetime.now()}')
    print()

    # Initialize components
    db = SessionLocal()
    try:
        # Use FotMob provider with proper initialization
        provider = FotMobFootballProvider(
            base_url="https://www.fotmob.com",
            timeout_seconds=10.0
        )

        prediction_service = PredictionService(provider=provider, db_session=db)

        print('Components initialized successfully')
        print(f'Provider: {provider.__class__.__name__}')
        print()

        # Get the match from database first
        from app.database.models import Match
        match = db.query(Match).filter(Match.id == match_id).first()

        if not match:
            print(f'❌ MATCH NOT FOUND: {match_id}')
            return False

        print(f'Match found: {match.home_team_id} vs {match.away_team_id}')
        print()

        # Measure execution time
        start_time = time.time()

        # Execute prediction
        print('Executing prediction...')
        result = prediction_service.predict_match(match)

        end_time = time.time()
        execution_time_ms = (end_time - start_time) * 1000

        print(f'✅ PREDICTION SUCCESSFUL')
        print(f'Execution time: {execution_time_ms:.2f}ms')
        print()

        # Analyze result
        print('ANALYSIS CONTEXT FIELDS:')
        print(f'  match: {result.match.id}')
        print(f'  home_team: {result.home_team.name if result.home_team else "None"}')
        print(f'  away_team: {result.away_team.name if result.away_team else "None"}')
        print(f'  predicted_score: {result.predicted_score}')
        print(f'  mensione_pick: {result.mensione_pick}')
        print()

        # Check prediction probabilities
        if result.ensemble_prediction:
            pred = result.ensemble_prediction
            print('PREDICTION PROBABILITIES:')
            print(f'  Home Win: {pred.home_win_probability:.3f}')
            print(f'  Draw: {pred.draw_probability:.3f}')
            print(f'  Away Win: {pred.away_win_probability:.3f}')
            total = pred.home_win_probability + pred.draw_probability + pred.away_win_probability
            print(f'  Total: {total:.6f}')
            print()

        # Check markets - show 2.5 line specifically
        if result.prediction_markets:
            print('PREDICTION MARKETS:')

            # Find specific markets
            match_result = None
            btts = None
            over_under_2_5 = None

            for market in result.prediction_markets:
                if str(market.market_type) == 'PredictionMarketType.MATCH_RESULT':
                    match_result = market
                elif str(market.market_type) == 'PredictionMarketType.BTTS':
                    btts = market
                elif str(market.market_type) == 'PredictionMarketType.OVER_UNDER' and market.line == 2.5:
                    over_under_2_5 = market

            # Display in preferred order with correct line
            if match_result:
                probs_str = ', '.join([f'{k}: {v:.3f}' for k, v in match_result.probabilities.items()])
                print(f'  PredictionMarketType.MATCH_RESULT: {probs_str}')

            if btts:
                probs_str = ', '.join([f'{k}: {v:.3f}' for k, v in btts.probabilities.items()])
                print(f'  PredictionMarketType.BTTS: {probs_str}')

            if over_under_2_5:
                probs_str = ', '.join([f'{k}: {v:.3f}' for k, v in over_under_2_5.probabilities.items()])
                print(f'  PredictionMarketType.OVER_UNDER (2.5): {probs_str}')
            else:
                print(f'  ❌ 2.5 çizgisi bulunamadı')
            print()

        print('✅ VALIDATION SUCCESSFUL - Full pipeline working with real canonical data')
        return True

    except Exception as e:
        print(f'❌ PREDICTION FAILED: {str(e)}')
        import traceback
        traceback.print_exc()
        return False

    finally:
        db.close()
        print('='*80)

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
