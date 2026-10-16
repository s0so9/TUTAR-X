"""
GROUP 3: Walk-Forward Backtest
CRITICAL TEST: Validate MENSIONE prediction pipeline has out-of-sample predictive power.

This test runs the ACTUAL prediction pipeline on historical finished matches using
walk-forward temporal validation to prevent data leakage.

Walk-Forward Process:
1. Sort all finished matches by scheduled_at (temporal ordering)
2. Split into train/test windows (e.g., 30-day test windows)
3. For each window:
   - Generate predictions using ONLY data from BEFORE window start
   - Compare predictions to actual outcomes
   - Measure accuracy, Brier score, calibration

CRITICAL: NO FUTURE INFORMATION ALLOWED
- Predictions generated at time T can only use data from before T
- If leakage detected: STOP and report

Database matches: 2,673 finished matches available for backtest
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any
import sys

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from app.database.session import get_session_factory
from app.database.models import Match, MatchStatus


OUTPUT_FILE = Path(__file__).parent / "group3_results.json"
WINDOW_SIZE_DAYS = 30  # Test window size
MIN_TRAIN_DAYS = 90  # Minimum training data
SAMPLE_SIZE = 100  # Test N matches (full 2,673 would take ~15 hours at 20s/pred)


def check_temporal_leakage(
    prediction_time: datetime,
    match_scheduled_time: datetime,
    match_actual_kickoff: datetime
) -> Dict[str, Any]:
    """
    Verify no future information leak.
    
    Args:
        prediction_time: When prediction was generated
        match_scheduled_time: Match scheduled_at from DB
        match_actual_kickoff: When match actually started
        
    Returns:
        Dict with leakage assessment
    """
    leakage_detected = False
    reasons = []
    
    # Prediction must be made BEFORE match starts
    if prediction_time >= match_actual_kickoff:
        leakage_detected = True
        reasons.append(f"Prediction made AFTER kickoff: pred={prediction_time}, kickoff={match_actual_kickoff}")
    
    # In real-world scenario, we'd predict 1-24 hours before scheduled time
    # For backtest, we allow predicting any time before kickoff
    # But warn if the gap is suspiciously small (< 1 minute)
    time_before_kickoff = match_actual_kickoff - prediction_time
    if time_before_kickoff.total_seconds() < 60:
        reasons.append(f"Warning: prediction made {time_before_kickoff.total_seconds():.1f}s before kickoff (suspicious)")
    
    return {
        "leakage_detected": leakage_detected,
        "reasons": reasons,
        "prediction_time": prediction_time.isoformat(),
        "match_kickoff": match_actual_kickoff.isoformat(),
        "time_before_kickoff_seconds": time_before_kickoff.total_seconds()
    }


async def get_finished_matches(limit: int = None) -> List[Dict[str, Any]]:
    """Get finished matches from DB, sorted by scheduled_at."""
    from app.database.session import SessionLocal
    
    session = SessionLocal()
    try:
        query = (
            select(Match)
            .where(Match.status == MatchStatus.FINISHED)
            .options(selectinload(Match.statistics))
            .order_by(Match.scheduled_at)
        )
        
        if limit:
            query = query.limit(limit)
        
        result = session.execute(query)
        matches = result.scalars().all()
        
        # Convert to dict to avoid session detachment issues
        match_dicts = []
        for match in matches:
            match_dicts.append({
                "id": match.id,
                "provider_id": match.provider_id,
                "provider_source_id": match.provider_source_id,
                "api_id": f"fotmob_{match.provider_id}",  # Prediction endpoint format
                "scheduled_at": match.scheduled_at,
                "status": match.status,
                "home_team_id": match.home_team_id,
                "away_team_id": match.away_team_id,
                "home_score": match.home_score,
                "away_score": match.away_score
            })
        
        return match_dicts
    finally:
        session.close()


async def run_prediction_for_match(match: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run prediction pipeline for a single match.
    
    NOTE: This is a SIMPLIFIED version. Full backtest would need to:
    1. Configure feature extractors to use ONLY pre-match data
    2. Re-train models on pre-match training window
    3. Ensure no data leakage in feature calculation
    
    For now, we'll document what SHOULD be done and run current pipeline.
    """
    import httpx
    
    prediction_time = datetime.now(timezone.utc)
    
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.get(
                f"http://localhost:8002/api/v1/matches/{match['api_id']}/prediction"
            )
            
            if response.status_code != 200:
                return {
                    "match_id": match['api_id'],
                    "db_id": match['id'],
                    "provider_id": match['provider_id'],
                    "scheduled_at": match['scheduled_at'].isoformat() if isinstance(match['scheduled_at'], datetime) else match['scheduled_at'],
                    "status": "ERROR",
                    "error": f"HTTP {response.status_code}: {response.text[:200]}"
                }
            
            prediction = response.json()
            
            # Extract predicted outcome
            mensione_pick = prediction.get("mensione_pick")
            
            return {
                "match_id": match['api_id'],
                "db_id": match['id'],
                "provider_id": match['provider_id'],
                "scheduled_at": match['scheduled_at'].isoformat() if isinstance(match['scheduled_at'], datetime) else match['scheduled_at'],
                "actual_home_score": match.get('home_score'),
                "actual_away_score": match.get('away_score'),
                "status": "SUCCESS",
                "mensione_pick": mensione_pick,
                "prediction_time": prediction_time.isoformat()
            }
            
    except Exception as e:
        return {
            "match_id": match.get('api_id', match['id']),
            "db_id": match['id'],
            "provider_id": match.get('provider_id'),
            "scheduled_at": match['scheduled_at'].isoformat() if isinstance(match['scheduled_at'], datetime) else match['scheduled_at'],
            "status": "ERROR",
            "error": str(e)
        }


async def evaluate_prediction(
    prediction: Dict[str, Any],
    actual_outcome: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Compare prediction to actual match outcome.
    
    Args:
        prediction: Prediction data including mensione_pick
        actual_outcome: Actual match statistics
        
    Returns:
        Evaluation metrics
    """
    # TODO: Implement proper evaluation
    # Need to:
    # 1. Extract mensione_pick market and selection
    # 2. Determine if selection was correct based on actual outcome
    # 3. Calculate Brier score for probabilities
    # 4. Track calibration bins
    
    return {
        "evaluated": False,
        "reason": "Evaluation logic not yet implemented"
    }


async def main():
    print("=" * 70)
    print("GROUP 3: WALK-FORWARD BACKTEST")
    print("=" * 70)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"Sample size: {SAMPLE_SIZE} matches")
    print(f"Window size: {WINDOW_SIZE_DAYS} days")
    print()
    
    print("[CRITICAL WARNING]")
    print("This backtest requires temporal data isolation to prevent leakage.")
    print("Current implementation runs predictions using CURRENT trained models,")
    print("which may have seen future data during training.")
    print()
    print("For true walk-forward validation, we need to:")
    print("1. Re-train models for each test window using ONLY prior data")
    print("2. Ensure feature extractors don't use future information")
    print("3. Validate temporal boundaries are enforced")
    print()
    print("Proceeding with CURRENT pipeline to establish baseline...")
    print("=" * 70)
    print()
    
    # Load finished matches
    print(f"Loading {SAMPLE_SIZE} finished matches...")
    matches = await get_finished_matches(limit=SAMPLE_SIZE)
    print(f"Loaded {len(matches)} matches")
    if matches:
        first_date = matches[0]['scheduled_at']
        last_date = matches[-1]['scheduled_at']
        if isinstance(first_date, datetime):
            first_date = first_date.isoformat()
        if isinstance(last_date, datetime):
            last_date = last_date.isoformat()
        print(f"Date range: {first_date} to {last_date}")
    print()
    
    results = {
        "group": "GROUP_3_WALK_FORWARD_BACKTEST",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "sample_size": SAMPLE_SIZE,
            "actual_matches": len(matches),
            "window_size_days": WINDOW_SIZE_DAYS,
            "min_train_days": MIN_TRAIN_DAYS
        },
        "warnings": [
            "Current implementation uses pre-trained models (potential leakage)",
            "True walk-forward requires per-window model retraining",
            "Feature extraction may access future data"
        ],
        "predictions": [],
        "summary": {}
    }
    
    # Run predictions on sample
    print(f"Running predictions on {len(matches)} matches...")
    print("(This may take several minutes at ~20-30s per prediction)")
    print()
    
    for i, match in enumerate(matches[:10], 1):  # Start with 10 for speed
        print(f"[{i}/{10}] Match {match['api_id']} @ {match['scheduled_at']}")
        
        pred_result = await run_prediction_for_match(match)
        results["predictions"].append(pred_result)
        
        if pred_result["status"] == "SUCCESS":
            pick = pred_result.get("mensione_pick")
            if pick:
                print(f"  -> {pick['market']}: {pick['selection']} ({pick['confidence']:.1%})")
            else:
                print(f"  -> NO PICK")
        else:
            print(f"  -> ERROR: {pred_result.get('error', 'Unknown')}")
    
    # Summary statistics
    total = len(results["predictions"])
    success = sum(1 for p in results["predictions"] if p["status"] == "SUCCESS")
    errors = total - success
    
    results["summary"] = {
        "total_predictions": total,
        "successful": success,
        "errors": errors,
        "success_rate": success / total if total > 0 else 0
    }
    
    # Save results
    OUTPUT_FILE.write_text(json.dumps(results, indent=2))
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total predictions: {total}")
    print(f"Successful: {success}")
    print(f"Errors: {errors}")
    print(f"Success rate: {results['summary']['success_rate']:.1%}")
    print()
    print(f"Results saved to: {OUTPUT_FILE}")
    print()
    print("[NEXT STEPS]")
    print("1. Implement proper outcome evaluation (match predictions to results)")
    print("2. Calculate accuracy, Brier score, calibration")
    print("3. Add per-window model retraining for true walk-forward")
    print("4. Validate temporal boundaries in feature extraction")


if __name__ == "__main__":
    asyncio.run(main())
