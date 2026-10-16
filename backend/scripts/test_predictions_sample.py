"""Test prediction API on sample upcoming matches.

Usage:
    python scripts/test_predictions_sample.py --count 10
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
import argparse
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.database.models import Match
from app.prediction.service import PredictionService


async def test_predictions(sample_size: int = 10):
    """Test predictions on upcoming matches."""
    
    print("=" * 70)
    print(f"PREDICTION API TEST - Sample Size: {sample_size}")
    print("=" * 70)
    print()
    
    db = SessionLocal()
    
    # Get upcoming matches
    now = datetime.now(datetime.UTC) if hasattr(datetime, 'UTC') else datetime.utcnow()
    future = now + timedelta(days=3)
    
    upcoming = db.query(Match.provider_id, Match.scheduled_at).filter(
        Match.status == 'SCHEDULED',
        Match.scheduled_at >= now,
        Match.scheduled_at <= future
    ).order_by(Match.scheduled_at).limit(sample_size).all()
    
    print(f"Testing {len(upcoming)} upcoming matches...")
    print()
    
    # Initialize prediction service with provider adapter
    from app.providers.adapter import ProviderManagerAdapter
    from app.providers.manager import ProviderManager
    from app.providers.fotmob import FotMobFootballProvider
    from app.providers.ryzellx import RyzellxFootballProvider
    from app.providers.openligadb import OpenLigaDBFootballProvider
    from app.config import Settings
    
    settings = Settings()
    
    fotmob = FotMobFootballProvider(
        base_url=settings.fotmob_base_url,
        timeout_seconds=settings.provider_timeout_seconds,
        retry_count=min(settings.provider_retry_count, 1)
    )
    
    ryzellx = RyzellxFootballProvider(
        base_url=settings.ryzellx_base_url,
        timeout_seconds=settings.provider_timeout_seconds,
        retry_count=settings.provider_retry_count
    )
    
    openligadb = OpenLigaDBFootballProvider(
        base_url=settings.openligadb_base_url,
        timeout_seconds=settings.provider_timeout_seconds,
        retry_count=settings.provider_retry_count
    )
    
    provider_manager = ProviderManager(
        ryzellx=ryzellx,
        fotmob=fotmob,
        openligadb=openligadb
    )
    provider_adapter = ProviderManagerAdapter(provider_manager)
    
    prediction_service = PredictionService(
        provider=provider_adapter,
        db_session=db
    )
    
    results = []
    
    for idx, (match_id, scheduled_at) in enumerate(upcoming, 1):
        print(f"[{idx}/{len(upcoming)}] Testing {match_id} (scheduled {scheduled_at})...")
        
        result = {
            'match_id': match_id,
            'scheduled_at': scheduled_at,
            'status': None,
            'response_time': None,
            'has_prediction': False,
            'mensione_pick_type': None,
            'pass_reason': None,
            'error': None
        }
        
        try:
            start_time = datetime.now(datetime.UTC) if hasattr(datetime, 'UTC') else datetime.utcnow()
            
            # Call prediction service
            prediction_context = await prediction_service.generate_prediction(match_id)
            
            end_time = datetime.now(datetime.UTC) if hasattr(datetime, 'UTC') else datetime.utcnow()
            response_time = (end_time - start_time).total_seconds()
            
            result['status'] = 'SUCCESS'
            result['response_time'] = response_time
            result['has_prediction'] = True
            
            # Check MENSIONE pick type
            mensione = prediction_context.mensione_pick
            if isinstance(mensione, dict):
                if mensione.get('pass_decision') is True:
                    result['mensione_pick_type'] = 'PASS'
                    result['pass_reason'] = mensione.get('pass_reason', 'unknown')
                else:
                    result['mensione_pick_type'] = 'PICK'
                    result['market'] = mensione.get('market', 'unknown')
                    result['probability'] = mensione.get('probability')
            
            print(f"  ✓ {result['mensione_pick_type']} ({response_time:.2f}s)")
            if result['mensione_pick_type'] == 'PASS':
                print(f"    Reason: {result['pass_reason']}")
            elif result['mensione_pick_type'] == 'PICK':
                print(f"    Market: {result['market']}, P={result.get('probability', 'N/A')}")
            
        except Exception as e:
            result['status'] = 'ERROR'
            result['error'] = str(e)
            print(f"  ✗ ERROR: {e}")
        
        results.append(result)
        print()
    
    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    total = len(results)
    success = sum(1 for r in results if r['status'] == 'SUCCESS')
    errors = sum(1 for r in results if r['status'] == 'ERROR')
    picks = sum(1 for r in results if r['mensione_pick_type'] == 'PICK')
    passes = sum(1 for r in results if r['mensione_pick_type'] == 'PASS')
    
    print(f"Total Tested:   {total}")
    print(f"├─ Success:     {success}")
    print(f"├─ Errors:      {errors}")
    print(f"├─ Picks:       {picks}")
    print(f"└─ Passes:      {passes}")
    print()
    
    if success > 0:
        avg_response_time = sum(r['response_time'] for r in results if r['response_time']) / success
        print(f"Avg Response Time: {avg_response_time:.2f}s")
    print()
    
    # Pass reasons breakdown
    if passes > 0:
        print("Pass Reasons:")
        pass_reasons = {}
        for r in results:
            if r['mensione_pick_type'] == 'PASS' and r['pass_reason']:
                pass_reasons[r['pass_reason']] = pass_reasons.get(r['pass_reason'], 0) + 1
        
        for reason, count in sorted(pass_reasons.items(), key=lambda x: -x[1]):
            print(f"  {reason}: {count}")
    
    print()
    print("=" * 70)
    
    db.close()
    await provider_manager.close()
    
    return results


async def main():
    parser = argparse.ArgumentParser(description='Test prediction API on upcoming matches')
    parser.add_argument('--count', type=int, default=10, help='Number of matches to test')
    
    args = parser.parse_args()
    
    try:
        results = await test_predictions(sample_size=args.count)
        return 0
    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
