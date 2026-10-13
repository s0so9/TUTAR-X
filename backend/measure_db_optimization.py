"""
Direct measurement of DB-first feature extraction optimization.

This script measures the performance of the MatchFeatureExtractor
with DB-first optimization vs provider fallback scenarios.
"""

import sys
import time
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
import logging

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.database.session import SessionLocal
from app.database.models import Match as DBMatch
from app.domain.match import Match
from app.features.match_features import MatchFeatureExtractor
from app.providers.development import DevelopmentProvider

# Configure logging to capture timing details
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def db_match_to_domain(db_match: DBMatch) -> Match:
    """Convert database match to domain match."""
    return Match(
        id=db_match.id,
        home_team_id=db_match.home_team_id,
        away_team_id=db_match.away_team_id,
        competition_id=db_match.competition_id or "unknown",
        season_id=db_match.season or "unknown",
        scheduled_at=db_match.scheduled_at,
        status=db_match.status,
        home_score=db_match.home_score,
        away_score=db_match.away_score,
        home_score_ht=db_match.home_score_ht,
        away_score_ht=db_match.away_score_ht,
        outcome=db_match.outcome,
        round=db_match.round,
        created_at=db_match.created_at,
        updated_at=db_match.updated_at,
    )


def find_suitable_test_matches(session) -> List[Match]:
    """Find matches suitable for testing DB optimization."""

    # Get matches from different time periods to test various scenarios
    test_matches = []

    # 1. Recent matches (likely to have DB data)
    recent_matches = session.query(DBMatch).filter(
        DBMatch.scheduled_at >= datetime(2026, 10, 10, tzinfo=timezone.utc),
        DBMatch.scheduled_at <= datetime(2026, 10, 14, tzinfo=timezone.utc)
    ).order_by(DBMatch.scheduled_at.asc()).limit(3).all()

    # 2. Earlier matches (may have less historical context)
    earlier_matches = session.query(DBMatch).filter(
        DBMatch.scheduled_at >= datetime(2026, 10, 1, tzinfo=timezone.utc),
        DBMatch.scheduled_at <= datetime(2026, 10, 5, tzinfo=timezone.utc)
    ).order_by(DBMatch.scheduled_at.asc()).limit(2).all()

    all_db_matches = recent_matches + earlier_matches

    for db_match in all_db_matches:
        if db_match.home_team_id and db_match.away_team_id:
            test_matches.append(db_match_to_domain(db_match))

    logger.info(f"Found {len(test_matches)} suitable test matches")
    return test_matches


def measure_extraction_performance(
    match: Match,
    use_db: bool = True,
    provider = None
) -> Dict:
    """Measure feature extraction performance for a single match."""

    logger.info(f"\n{'='*80}")
    logger.info(f"MEASURING: Match {match.id}")
    logger.info(f"Scheduled: {match.scheduled_at}")
    logger.info(f"Using DB: {use_db}")
    logger.info(f"{'='*80}")

    # Create session if using DB
    db_session = SessionLocal() if use_db else None

    try:
        # Create feature extractor
        extractor = MatchFeatureExtractor(
            provider=provider or DevelopmentProvider(),
            db_session=db_session
        )

        # Measure overall feature extraction
        overall_start = time.time()

        logger.info(f"[BENCHMARK] Starting feature extraction...")
        features = extractor.extract_features(match)

        overall_time = (time.time() - overall_start) * 1000

        logger.info(f"[BENCHMARK] TOTAL extraction time: {overall_time:.2f}ms")

        # Count non-null features
        non_null_features = sum(1 for v in features.values() if v is not None)
        total_features = len(features)

        result = {
            "match_id": match.id,
            "scheduled_at": match.scheduled_at.isoformat(),
            "used_db": use_db,
            "total_time_ms": overall_time,
            "total_features": total_features,
            "non_null_features": non_null_features,
            "feature_coverage": non_null_features / total_features if total_features > 0 else 0,
            "success": True
        }

        # Sample some key features for verification
        sample_features = {
            k: v for k, v in list(features.items())[:10]
            if v is not None
        }
        result["sample_features"] = sample_features

        logger.info(f"[BENCHMARK] Features extracted: {non_null_features}/{total_features}")
        logger.info(f"[BENCHMARK] Coverage: {result['feature_coverage']:.1%}")

        return result

    except Exception as e:
        error_time = (time.time() - overall_start) * 1000
        logger.exception(f"[BENCHMARK] Error after {error_time:.2f}ms: {e}")

        return {
            "match_id": match.id,
            "scheduled_at": match.scheduled_at.isoformat(),
            "used_db": use_db,
            "total_time_ms": error_time,
            "success": False,
            "error": str(e)
        }

    finally:
        if db_session:
            db_session.close()


def run_comprehensive_benchmark():
    """Run comprehensive performance benchmark."""

    print("="*80)
    print("DB-FIRST FEATURE EXTRACTION OPTIMIZATION BENCHMARK")
    print("="*80)
    print()

    # Get database session for finding test matches
    session = SessionLocal()

    try:
        # Find suitable test matches
        test_matches = find_suitable_test_matches(session)

        if not test_matches:
            print("No suitable test matches found in database")
            return

        print(f"Testing with {len(test_matches)} matches")
        print()

        results = []

        # Test each match with DB optimization
        for i, match in enumerate(test_matches[:3], 1):  # Test first 3 matches
            print(f"--- Test {i}: DB Optimization Path ---")

            result_db = measure_extraction_performance(match, use_db=True)
            results.append(result_db)

            print(f"✓ DB path completed: {result_db['total_time_ms']:.2f}ms")
            print()

        # Test one match without DB for comparison
        if test_matches:
            print("--- Test: Provider Fallback Path ---")
            result_no_db = measure_extraction_performance(test_matches[0], use_db=False)
            results.append(result_no_db)
            print(f"✓ No-DB path completed: {result_no_db['total_time_ms']:.2f}ms")
            print()

        # Analysis
        print("="*80)
        print("PERFORMANCE ANALYSIS")
        print("="*80)

        db_results = [r for r in results if r.get('used_db', False) and r.get('success', False)]
        no_db_results = [r for r in results if not r.get('used_db', False) and r.get('success', False)]

        if db_results:
            db_times = [r['total_time_ms'] for r in db_results]
            print(f"DB Optimization Results:")
            print(f"  • Successful runs: {len(db_results)}")
            print(f"  • Average time: {sum(db_times)/len(db_times):.2f}ms")
            print(f"  • Min time: {min(db_times):.2f}ms")
            print(f"  • Max time: {max(db_times):.2f}ms")

            if len(db_times) > 1:
                import statistics
                print(f"  • Std deviation: {statistics.stdev(db_times):.2f}ms")
            print()

        if no_db_results:
            no_db_times = [r['total_time_ms'] for r in no_db_results]
            print(f"Provider Fallback Results:")
            print(f"  • Successful runs: {len(no_db_results)}")
            print(f"  • Average time: {sum(no_db_times)/len(no_db_times):.2f}ms")
            print()

        # Comparison
        if db_results and no_db_results:
            db_avg = sum(r['total_time_ms'] for r in db_results) / len(db_results)
            no_db_avg = sum(r['total_time_ms'] for r in no_db_results) / len(no_db_results)

            speedup = no_db_avg / db_avg if db_avg > 0 else 0
            time_saved = no_db_avg - db_avg

            print(f"Performance Comparison:")
            print(f"  • DB optimization average: {db_avg:.2f}ms")
            print(f"  • Provider fallback average: {no_db_avg:.2f}ms")
            print(f"  • Time saved: {time_saved:.2f}ms")
            print(f"  • Speedup: {speedup:.1f}x")
            print()

        # Check for issues
        failed_results = [r for r in results if not r.get('success', False)]
        if failed_results:
            print(f"Failed extractions: {len(failed_results)}")
            for result in failed_results:
                print(f"  • {result['match_id']}: {result.get('error', 'Unknown error')}")
            print()

        # Previous baseline comparison
        baseline_26_6_sec = 26600  # 26.60 seconds from previous measurement

        if db_results:
            current_avg = sum(r['total_time_ms'] for r in db_results) / len(db_results)
            baseline_improvement = baseline_26_6_sec / current_avg if current_avg > 0 else 0

            print(f"Baseline Comparison:")
            print(f"  • Previous measurement: {baseline_26_6_sec/1000:.2f}s")
            print(f"  • Current average: {current_avg/1000:.2f}s")
            print(f"  • Improvement: {baseline_improvement:.1f}x faster")
            print()

        print("="*80)

        # Save detailed results
        output_file = "db_optimization_benchmark_results.json"
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2, default=str)

        print(f"Detailed results saved to {output_file}")

        return results

    finally:
        session.close()


def analyze_db_state():
    """Analyze current database state for optimization effectiveness."""

    print("\n" + "="*80)
    print("DATABASE STATE ANALYSIS")
    print("="*80)

    session = SessionLocal()
    try:
        # Overall match count
        total_matches = session.query(DBMatch).count()
        print(f"Total matches in database: {total_matches:,}")

        # Status breakdown
        from sqlalchemy import func
        status_counts = session.query(
            DBMatch.status,
            func.count(DBMatch.id)
        ).group_by(DBMatch.status).all()

        print(f"\nMatch status breakdown:")
        for status, count in status_counts:
            print(f"  • {status}: {count:,}")

        # Date range
        earliest = session.query(func.min(DBMatch.scheduled_at)).scalar()
        latest = session.query(func.max(DBMatch.scheduled_at)).scalar()

        print(f"\nDate range:")
        print(f"  • Earliest: {earliest}")
        print(f"  • Latest: {latest}")

        # Teams with most historical data
        print(f"\nSample of teams with most matches:")

        from sqlalchemy import or_
        from sqlalchemy import text
        team_match_counts = session.execute(text("""
            SELECT team_id, count(*) as match_count
            FROM (
                SELECT home_team_id as team_id FROM matches WHERE status = 'finished'
                UNION ALL
                SELECT away_team_id as team_id FROM matches WHERE status = 'finished'
            ) team_matches
            GROUP BY team_id
            ORDER BY match_count DESC
            LIMIT 5
        """)).fetchall()

        for team_id, match_count in team_match_counts:
            print(f"  • {team_id[:16]}...: {match_count} finished matches")

        print("="*80)

    finally:
        session.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Benchmark DB-first feature extraction optimization")
    parser.add_argument("--analyze-db", action="store_true", help="Analyze database state")
    parser.add_argument("--quick", action="store_true", help="Quick test with 1 match only")

    args = parser.parse_args()

    if args.analyze_db:
        analyze_db_state()

    # Run benchmark
    results = run_comprehensive_benchmark()

    if args.analyze_db and not results:
        print("\nNo benchmark results to analyze further")
