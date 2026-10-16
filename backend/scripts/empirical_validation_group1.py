"""GROUP 1: Upcoming Prediction Sample Validation

Tests real upcoming matches against the prediction API and classifies outcomes.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import asyncio
import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.database.models import Match


class PredictionOutcome:
    VALID_PREDICTION = "VALID_PREDICTION"
    VALID_PASS = "VALID_PASS"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    API_ERROR = "API_ERROR"
    MODEL_ERROR = "MODEL_ERROR"
    OTHER = "OTHER"


async def test_upcoming_predictions(sample_size: int = 50, timeout_sec: int = 60):
    """Test predictions on upcoming matches via HTTP API."""
    
    print("=" * 70)
    print(f"GROUP 1: UPCOMING PREDICTION SAMPLE (N={sample_size})")
    print("=" * 70)
    print()
    
    db = SessionLocal()
    
    try:
        # Get upcoming matches
        now = datetime.now(datetime.UTC) if hasattr(datetime, 'UTC') else datetime.utcnow()
        future = now + timedelta(days=7)
        
        matches = db.query(
            Match.provider_id,
            Match.scheduled_at
        ).filter(
            Match.status == 'SCHEDULED',
            Match.scheduled_at >= now,
            Match.scheduled_at <= future
        ).order_by(Match.scheduled_at).limit(sample_size).all()
        
        print(f"Testing {len(matches)} upcoming matches\n")
        
        if not matches:
            print("❌ No upcoming matches found")
            return
        
        # Test each match
        results = {
            'valid_predictions': [],
            'valid_passes': [],
            'insufficient_data': [],
            'api_errors': [],
            'model_errors': [],
            'other_errors': []
        }
        
        response_times = []
        
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            for idx, (match_id, scheduled_at) in enumerate(matches, 1):
                print(f"[{idx}/{len(matches)}] Testing {match_id}...", end=' ')
                
                result = {
                    'match_id': match_id,
                    'scheduled_at': scheduled_at,
                    'outcome': None,
                    'response_time': None,
                    'details': {}
                }
                
                try:
                    start = datetime.now(datetime.UTC) if hasattr(datetime, 'UTC') else datetime.utcnow()
                    
                    response = await client.get(
                        f"http://127.0.0.1:8002/api/v1/matches/{match_id}/prediction"
                    )
                    
                    end = datetime.now(datetime.UTC) if hasattr(datetime, 'UTC') else datetime.utcnow()
                    response_time = (end - start).total_seconds()
                    response_times.append(response_time)
                    result['response_time'] = response_time
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Check for MENSIONE pick
                        if 'mensione_pick' in data and data['mensione_pick']:
                            pick = data['mensione_pick']
                            
                            if pick.get('pass_decision') is True:
                                # Valid PASS
                                result['outcome'] = PredictionOutcome.VALID_PASS
                                result['details'] = {
                                    'pass_reason': pick.get('pass_reason'),
                                    'evaluated_markets': pick.get('evaluated_markets_count', 0)
                                }
                                results['valid_passes'].append(result)
                                print(f"PASS ({pick.get('pass_reason')}) [{response_time:.2f}s]")
                            else:
                                # Valid PREDICTION
                                result['outcome'] = PredictionOutcome.VALID_PREDICTION
                                result['details'] = {
                                    'market': pick.get('market'),
                                    'probability': pick.get('probability'),
                                    'confidence': pick.get('confidence'),
                                    'model_agreement': pick.get('model_agreement'),
                                    'data_quality': pick.get('data_quality')
                                }
                                results['valid_predictions'].append(result)
                                print(f"PICK {pick.get('market')} P={pick.get('probability', 0):.3f} [{response_time:.2f}s]")
                        else:
                            result['outcome'] = PredictionOutcome.OTHER
                            result['details'] = {'reason': 'No mensione_pick in response'}
                            results['other_errors'].append(result)
                            print(f"❌ No pick data [{response_time:.2f}s]")
                    
                    elif response.status_code == 400:
                        # Likely insufficient data
                        try:
                            error_data = response.json()
                            detail = error_data.get('detail', '')
                            
                            if 'insufficient' in detail.lower() or 'not enough' in detail.lower():
                                result['outcome'] = PredictionOutcome.INSUFFICIENT_DATA
                                result['details'] = {'error': detail}
                                results['insufficient_data'].append(result)
                                print(f"⚠️  INSUFFICIENT_DATA")
                            else:
                                result['outcome'] = PredictionOutcome.API_ERROR
                                result['details'] = {'status': 400, 'error': detail}
                                results['api_errors'].append(result)
                                print(f"❌ API_ERROR (400): {detail[:50]}")
                        except:
                            result['outcome'] = PredictionOutcome.API_ERROR
                            result['details'] = {'status': 400, 'error': 'Unknown'}
                            results['api_errors'].append(result)
                            print(f"❌ API_ERROR (400)")
                    
                    else:
                        result['outcome'] = PredictionOutcome.API_ERROR
                        result['details'] = {'status': response.status_code}
                        results['api_errors'].append(result)
                        print(f"❌ API_ERROR ({response.status_code})")
                
                except httpx.TimeoutException:
                    result['outcome'] = PredictionOutcome.API_ERROR
                    result['details'] = {'error': 'Timeout'}
                    results['api_errors'].append(result)
                    print(f"[X] TIMEOUT")
                
                except Exception as e:
                    result['outcome'] = PredictionOutcome.OTHER
                    result['details'] = {'error': str(e)}
                    results['other_errors'].append(result)
                    print(f"[X] ERROR: {str(e)[:50]}")
        
        # Summary Report
        print()
        print("=" * 70)
        print("SUMMARY")
        print("=" * 70)
        
        total = len(matches)
        valid_preds = len(results['valid_predictions'])
        valid_passes = len(results['valid_passes'])
        insufficient = len(results['insufficient_data'])
        api_errors = len(results['api_errors'])
        model_errors = len(results['model_errors'])
        other_errors = len(results['other_errors'])
        
        print(f"Total Tested:          {total}")
        print(f"├─ Valid Predictions:  {valid_preds} ({100*valid_preds/total:.1f}%)")
        print(f"├─ Valid Passes:       {valid_passes} ({100*valid_passes/total:.1f}%)")
        print(f"├─ Insufficient Data:  {insufficient} ({100*insufficient/total:.1f}%)")
        print(f"├─ API Errors:         {api_errors} ({100*api_errors/total:.1f}%)")
        print(f"├─ Model Errors:       {model_errors} ({100*model_errors/total:.1f}%)")
        print(f"└─ Other Errors:       {other_errors} ({100*other_errors/total:.1f}%)")
        print()
        
        if response_times:
            avg_time = sum(response_times) / len(response_times)
            min_time = min(response_times)
            max_time = max(response_times)
            print(f"Response Times:")
            print(f"├─ Average: {avg_time:.2f}s")
            print(f"├─ Min:     {min_time:.2f}s")
            print(f"└─ Max:     {max_time:.2f}s")
            print()
        
        # Pass reasons breakdown
        if valid_passes:
            print("Pass Reasons:")
            pass_reasons = {}
            for result in results['valid_passes']:
                reason = result['details'].get('pass_reason', 'unknown')
                pass_reasons[reason] = pass_reasons.get(reason, 0) + 1
            
            for reason, count in sorted(pass_reasons.items(), key=lambda x: -x[1]):
                print(f"  {reason}: {count}")
            print()
        
        # Pick markets breakdown
        if valid_preds:
            print("Pick Markets:")
            markets = {}
            for result in results['valid_predictions']:
                market = result['details'].get('market', 'unknown')
                markets[market] = markets.get(market, 0) + 1
            
            for market, count in sorted(markets.items(), key=lambda x: -x[1]):
                print(f"  {market}: {count}")
            print()
        
        # Confidence distribution for picks
        if valid_preds:
            print("Confidence Distribution (Picks):")
            confidences = [r['details'].get('confidence', 0) for r in results['valid_predictions']]
            if confidences:
                avg_conf = sum(confidences) / len(confidences)
                min_conf = min(confidences)
                max_conf = max(confidences)
                print(f"  Average: {avg_conf:.3f}")
                print(f"  Min:     {min_conf:.3f}")
                print(f"  Max:     {max_conf:.3f}")
            print()
        
        print("=" * 70)
        print("GROUP 1 COMPLETE")
        print("=" * 70)
        
        return results
    
    finally:
        db.close()


async def main():
    import argparse
    parser = argparse.ArgumentParser(description='GROUP 1: Upcoming Prediction Sample')
    parser.add_argument('--count', type=int, default=50, help='Number of matches to test')
    parser.add_argument('--timeout', type=int, default=60, help='Timeout per request (seconds)')
    
    args = parser.parse_args()
    
    try:
        results = await test_upcoming_predictions(
            sample_size=args.count,
            timeout_sec=args.timeout
        )
        return 0
    except Exception as e:
        print(f"\n[ERROR] Validation failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
