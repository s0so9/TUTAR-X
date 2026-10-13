"""Direct performance analysis by instrumenting the prediction service.

This script runs a prediction directly and measures each stage.
"""

import sys
import time
from pathlib import Path
from datetime import datetime

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

# Import and configure logging first
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from app.database import SessionLocal
from app.providers import (
    HybridProvider,
    ProviderManagerAdapter,
    ProviderManager,
    FotMobFootballProvider,
    OpenLigaDBFootballProvider,
    ProviderCache,
)
from app.config import settings
from app.prediction.service import PredictionService
from app.domain.match import Match


def create_provider(db_session):
    """Create hybrid provider for testing."""
    cache = ProviderCache()

    fotmob = FotMobFootballProvider(
        base_url=settings.fotmob_base_url,
        timeout_seconds=settings.provider_timeout_seconds,
        retry_count=min(settings.provider_retry_count, 1),
        cache=cache,
    )

    openligadb = OpenLigaDBFootballProvider(
        base_url=settings.openligadb_base_url,
        timeout_seconds=settings.provider_timeout_seconds,
        retry_count=settings.provider_retry_count,
        cache=cache,
    )

    manager = ProviderManager(
        ryzellx=None,  # Disabled
        fotmob=fotmob,
        openligadb=openligadb,
        cache=cache,
    )

    external_adapter = ProviderManagerAdapter(manager=manager)

    return HybridProvider(
        external_provider=external_adapter,
        session=db_session
    )


def analyze_prediction_performance(match_id: str):
    """Analyze prediction performance with detailed timing.

    Args:
        match_id: Match ID to analyze
    """
    print("\n" + "="*80)
    print("DIRECT PREDICTION PERFORMANCE ANALYSIS")
    print("="*80)
    print(f"Match ID: {match_id}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("="*80)
    print()

    # Setup
    print("Setting up database and provider...")
    db = SessionLocal()
    provider = create_provider(db_session=db)

    # Get match
    print(f"Fetching match {match_id}...")
    start = time.time()
    try:
        from app.database.models import Match as MatchDB
        match_db = db.query(MatchDB).filter(MatchDB.id == match_id).first()
        if not match_db:
            print(f"✗ Match not found: {match_id}")
            return

        # Convert to domain Match
        match = Match(
            id=match_db.id,
            home_team_id=match_db.home_team_id,
            away_team_id=match_db.away_team_id,
            competition_id=match_db.competition_id,
            season_id=match_db.season or "unknown",  # DB uses 'season', provide fallback
            scheduled_at=match_db.scheduled_at,
            status=match_db.status,
        )
        fetch_time = (time.time() - start) * 1000
        print(f"✓ Match fetched in {fetch_time:.2f}ms")
        print(f"  Home: {match_db.home_team_id}")
        print(f"  Away: {match_db.away_team_id}")
    except Exception as e:
        print(f"✗ Error fetching match: {e}")
        return

    # Create prediction service
    print("\nCreating prediction service...")
    start = time.time()
    service = PredictionService(
        provider=provider,
        db_session=db
    )
    service_time = (time.time() - start) * 1000
    print(f"✓ Service created in {service_time:.2f}ms")

    # Generate prediction with profiling
    print("\nGenerating prediction with profiling...")
    print("-" * 80)

    from app.prediction.profiler import reset_profiler, get_profiler
    reset_profiler()

    start = time.time()
    try:
        context = service.generate_full_prediction(
            match=match,
            correlation_id="analyze_perf"
        )
        total_time = (time.time() - start) * 1000

        print("-" * 80)
        print(f"\n✓ Prediction generated in {total_time:.2f}ms ({total_time/1000:.2f}s)")

        # Get profiler report
        profiler = get_profiler()
        report = profiler.get_report()

        print("\n" + "="*80)
        print("PROFILER REPORT")
        print("="*80)
        print(f"\nTotal Pipeline Duration: {report['total_duration_ms']:.2f}ms ({report['total_duration_ms']/1000:.2f}s)")

        print("\nStages (sorted by duration):")
        print("-"*80)
        print(f"{'Stage':<35} {'Duration (ms)':>12} {'%':>6}")
        print("-"*80)

        sorted_stages = sorted(report['stages'], key=lambda x: x['duration_ms'], reverse=True)
        for stage in sorted_stages:
            print(f"{stage['stage']:<35} {stage['duration_ms']:>12.2f} {stage['percentage']:>5.1f}%")

        print("\n" + "-"*80)
        print("Category Summary:")
        print("-"*80)
        print(f"{'Category':<30} {'Total (ms)':>12} {'Count':>6} {'Avg (ms)':>10}")
        print("-"*80)

        if 'summary' in report and report['summary']:
            for category, stats in sorted(report['summary'].items(), key=lambda x: x[1]['total_ms'], reverse=True):
                print(f"{category:<30} {stats['total_ms']:>12.2f} {stats['count']:>6} {stats['average_ms']:>10.2f}")
        else:
            print("No category summary available")

        print("="*80)

        # Show prediction results
        print("\nPrediction Results:")
        print("-"*80)
        if context.predicted_score:
            print(f"Predicted Score: {context.predicted_score}")

        if hasattr(context, 'mensione_pick') and context.mensione_pick:
            pick = context.mensione_pick
            if pick.get('pass_decision'):
                print(f"TUTAR X Pick: PASS - {pick.get('pass_reason')}")
            else:
                print(f"TUTAR X Pick: {pick.get('market')} - {pick.get('selection')}")
                print(f"  Probability: {pick.get('probability', 0):.3f}")
                print(f"  Confidence: {pick.get('confidence', 0):.3f}")

        if context.model_predictions:
            pred = context.model_predictions[0]
            print(f"1X2 Probabilities: H={pred.home_win_probability:.3f} D={pred.draw_probability:.3f} A={pred.away_win_probability:.3f}")
            print(f"xG: Home={pred.home_xg:.2f}, Away={pred.away_xg:.2f}")
            print(f"Confidence: {pred.confidence_score:.3f}")

        print("="*80)

    except Exception as e:
        print(f"\n✗ Prediction failed: {e}")
        import traceback
        traceback.print_exc()
        return

    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Analyze prediction performance with detailed profiling")
    parser.add_argument("--match-id", required=True, help="Match ID to analyze")

    args = parser.parse_args()

    analyze_prediction_performance(args.match_id)
