"""Detailed profiling with all timing measurements."""

import sys
import time
import logging

logging.basicConfig(level=logging.WARNING)

from app.database.session import get_db
from app.prediction.service import PredictionService
from app.providers.manager import ProviderManager
from app.providers import (
    ProviderManagerAdapter,
    ProviderCache,
    RyzellxFootballProvider,
    FotMobFootballProvider,
    OpenLigaDBFootballProvider,
)
from app.config import settings

def measure_time(label):
    """Context manager for timing."""
    class Timer:
        def __enter__(self):
            self.start = time.perf_counter()
            return self

        def __exit__(self, *args):
            self.duration = (time.perf_counter() - self.start) * 1000
            print(f"{label:40s}: {self.duration:8.2f}ms")

    return Timer()

def profile_prediction(match_id: str):
    """Profile prediction with detailed timing."""

    print("\n" + "="*80)
    print(f"DETAILED PREDICTION PROFILE: {match_id}")
    print("="*80 + "\n")

    overall_start = time.perf_counter()
    provider_call_count = [0]  # Mutable to track in nested scope

    try:
        # Initialize
        with measure_time("1. Provider initialization"):
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

        # Get match
        with measure_time("2. Get match"):
            match = provider.get_match(match_id)

        if not match:
            print(f"ERROR: Match {match_id} not found")
            return

        print(f"\nMatch: {match.home_team_id[:8]}... vs {match.away_team_id[:8]}...")
        print(f"Status: {match.status}")
        print(f"Scheduled: {match.scheduled_at}\n")

        # Initialize DB and service
        with measure_time("3. Database session"):
            db_session = next(get_db())

        with measure_time("4. Prediction service init"):
            prediction_service = PredictionService(
                provider=provider,
                db_session=db_session
            )

        # Generate prediction with sub-timing
        print("\nPREDICTION PIPELINE:")
        print("-" * 80)

        pipeline_start = time.perf_counter()

        analysis_context = prediction_service.generate_full_prediction(
            match=match,
            odds_data=None
        )

        pipeline_duration = (time.perf_counter() - pipeline_start) * 1000

        print(f"{'5. TOTAL PREDICTION PIPELINE':40s}: {pipeline_duration:8.2f}ms")

        # Check result
        if analysis_context.model_predictions and len(analysis_context.model_predictions) > 0:
            prediction = analysis_context.model_predictions[0]
            print(f"\n{'RESULT:':40s}")
            print(f"{'  Home win probability':40s}: {prediction.home_win_probability:.4f}")
            print(f"{'  Draw probability':40s}: {prediction.draw_probability:.4f}")
            print(f"{'  Away win probability':40s}: {prediction.away_win_probability:.4f}")
            print(f"{'  Sum':40s}: {prediction.home_win_probability + prediction.draw_probability + prediction.away_win_probability:.10f}")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        overall_duration = (time.perf_counter() - overall_start) * 1000

        print("\n" + "="*80)
        print(f"TOTAL DURATION: {overall_duration:.2f}ms ({overall_duration/1000:.2f}s)")
        print("="*80 + "\n")

        if 'db_session' in locals():
            db_session.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python detailed_profile.py <match_id>")
        sys.exit(1)

    match_id = sys.argv[1]
    profile_prediction(match_id)
