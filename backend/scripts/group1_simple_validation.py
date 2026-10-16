"""GROUP 1: Simple validation - ASCII output only."""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import asyncio
import httpx
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.database.models import Match


async def validate_predictions(count: int = 30):
    """Test predictions and return JSON results."""
    
    db = SessionLocal()
    
    try:
        now = datetime.now(datetime.UTC) if hasattr(datetime, 'UTC') else datetime.utcnow()
        future = now + timedelta(days=7)
        
        matches = db.query(Match.provider_id, Match.scheduled_at).filter(
            Match.status == 'SCHEDULED',
            Match.scheduled_at >= now,
            Match.scheduled_at <= future
        ).order_by(Match.scheduled_at).limit(count).all()
        
        results = {
            'total': len(matches),
            'valid_predictions': 0,
            'valid_passes': 0,
            'insufficient_data': 0,
            'api_errors': 0,
            'other_errors': 0,
            'response_times': [],
            'picks': [],
            'passes': [],
            'errors': []
        }
        
        async with httpx.AsyncClient(timeout=90.0) as client:
            for idx, (match_id, scheduled_at) in enumerate(matches, 1):
                try:
                    start = datetime.now(datetime.UTC) if hasattr(datetime, 'UTC') else datetime.utcnow()
                    response = await client.get(f"http://127.0.0.1:8002/api/v1/matches/{match_id}/prediction")
                    end = datetime.now(datetime.UTC) if hasattr(datetime, 'UTC') else datetime.utcnow()
                    response_time = (end - start).total_seconds()
                    results['response_times'].append(response_time)
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        if 'mensione_pick' in data and data['mensione_pick']:
                            pick = data['mensione_pick']
                            
                            if pick.get('pass_decision') is True:
                                results['valid_passes'] += 1
                                results['passes'].append({
                                    'match_id': match_id,
                                    'reason': pick.get('pass_reason'),
                                    'response_time': response_time
                                })
                            else:
                                results['valid_predictions'] += 1
                                results['picks'].append({
                                    'match_id': match_id,
                                    'market': pick.get('market'),
                                    'probability': pick.get('probability'),
                                    'confidence': pick.get('confidence'),
                                    'model_agreement': pick.get('model_agreement'),
                                    'data_quality': pick.get('data_quality'),
                                    'response_time': response_time
                                })
                        else:
                            results['other_errors'] += 1
                            results['errors'].append({
                                'match_id': match_id,
                                'type': 'no_pick_data',
                                'response_time': response_time
                            })
                    
                    elif response.status_code == 400:
                        error_data = response.json()
                        detail = error_data.get('detail', '')
                        
                        if 'insufficient' in detail.lower() or 'not enough' in detail.lower():
                            results['insufficient_data'] += 1
                        else:
                            results['api_errors'] += 1
                        
                        results['errors'].append({
                            'match_id': match_id,
                            'type': 'api_400',
                            'detail': detail
                        })
                    
                    else:
                        results['api_errors'] += 1
                        results['errors'].append({
                            'match_id': match_id,
                            'type': f'api_{response.status_code}'
                        })
                
                except httpx.TimeoutException:
                    results['api_errors'] += 1
                    results['errors'].append({
                        'match_id': match_id,
                        'type': 'timeout'
                    })
                
                except Exception as e:
                    results['other_errors'] += 1
                    results['errors'].append({
                        'match_id': match_id,
                        'type': 'exception',
                        'error': str(e)
                    })
        
        # Calculate statistics
        if results['response_times']:
            results['avg_response_time'] = sum(results['response_times']) / len(results['response_times'])
            results['min_response_time'] = min(results['response_times'])
            results['max_response_time'] = max(results['response_times'])
        
        # Write to file
        output_file = Path(__file__).parent / 'group1_results.json'
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"GROUP 1 VALIDATION COMPLETE")
        print(f"Total: {results['total']}")
        print(f"Valid Predictions: {results['valid_predictions']}")
        print(f"Valid Passes: {results['valid_passes']}")
        print(f"Insufficient Data: {results['insufficient_data']}")
        print(f"API Errors: {results['api_errors']}")
        print(f"Other Errors: {results['other_errors']}")
        
        if results['response_times']:
            print(f"Avg Response Time: {results['avg_response_time']:.2f}s")
        
        print(f"\nResults saved to: {output_file}")
        
        return results
    
    finally:
        db.close()


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, default=30)
    args = parser.parse_args()
    
    try:
        await validate_predictions(args.count)
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
