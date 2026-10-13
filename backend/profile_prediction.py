"""Profile a single prediction request to identify latency bottlenecks.

Usage:
    python profile_prediction.py fotmob_5881179
"""

import sys
import os
import time
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.prediction.profiler import get_profiler, reset_profiler
from app.prediction.service import PredictionService
from app.providers.manager import ProviderManager
from app.database.session import get_db


def profile_prediction(match_id: str):
    """Profile a single prediction request with detailed timing."""

    print(f"\n{'='*80}")
    print(f"PROFILING PREDICTION FOR MATCH: {match_id}")
    print(f"{'='*80}\n")

    # Reset profiler
    reset_profiler()
    profiler = get_profiler()

    # Overall timing
    overall_start = time.perf_counter()

    try:
        # Initialize providers like the API does
        profiler.start_stage("00_provider_initialization")
        from app.providers import (
            DevelopmentProvider,
            RyzellxFootballProvider,
            FotMobFootballProvider,
            OpenLigaDBFootballProvider,
            ProviderManager,
            ProviderManagerAdapter,
            ProviderCache,
        )
        from app.config import settings

        # Check which provider mode
        if not settings.use_real_providers:
            provider = DevelopmentProvider()
        else:
            cache = ProviderCache()

            ryzellx = RyzellxFootballProvider(
                base_url=settings.ryzellx_base_url,
                timeout_seconds=settings.provider_timeout_seconds,
                retry_count=settings.provider_retry_count,
                cache=cache,
            )

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
                ryzellx=ryzellx,
                fotmob=fotmob,
                openligadb=openligadb,
                cache=cache,
            )

            provider = ProviderManagerAdapter(manager=manager)

        profiler.end_stage(provider_type=type(provider).__name__)

        # Get match
        profiler.start_stage("01_get_match")
        match = provider.get_match(match_id)
        profiler.end_stage(match_found=match is not None)

        if not match:
            print(f"ERROR: Match {match_id} not found")
            return

        print(f"Match: {match.home_team_id} vs {match.away_team_id}")
        print(f"Status: {match.status}")
        print(f"Scheduled: {match.scheduled_at}\n")

        # Initialize database session
        profiler.start_stage("02_db_session")
        db_session = next(get_db())
        profiler.end_stage()

        # Initialize prediction service
        profiler.start_stage("03_prediction_service_init")
        prediction_service = PredictionService(
            provider=provider,
            db_session=db_session
        )
        profiler.end_stage()

        # Now instrument the prediction pipeline
        # We'll need to patch the service to add timing

        print("Starting prediction pipeline...\n")

        # Generate prediction
        profiler.start_stage("04_FULL_PREDICTION_PIPELINE")
        analysis_context = prediction_service.generate_full_prediction(
            match=match,
            odds_data=None
        )
        profiler.end_stage(
            has_prediction=analysis_context.model_predictions is not None and len(analysis_context.model_predictions) > 0
        )

    except Exception as e:
        print(f"\nERROR during prediction: {e}")
        import traceback
        traceback.print_exc()
    finally:
        overall_duration = (time.perf_counter() - overall_start) * 1000
        print(f"\nOverall Duration: {overall_duration:.2f}ms ({overall_duration/1000:.2f}s)")

        # Print report
        profiler.print_report()

        # Close database
        if 'db_session' in locals():
            db_session.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python profile_prediction.py <match_id>")
        print("Example: python profile_prediction.py fotmob_5881179")
        sys.exit(1)

    match_id = sys.argv[1]
    profile_prediction(match_id)
