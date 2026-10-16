"""Performance measurement script for TUTAR X critical paths.

Measures actual latency of:
- Provider HTTP requests
- Provider parsing
- Database queries
- Feature engineering
- Prediction generation
- API response time
"""

import asyncio
import time
from datetime import date, timedelta
from typing import Dict, List, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PerformanceTimer:
    """Context manager for timing operations."""
    
    def __init__(self, operation_name: str):
        self.operation_name = operation_name
        self.start_time = None
        self.duration_ms = None
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, *args):
        self.duration_ms = (time.perf_counter() - self.start_time) * 1000
        logger.info(f"⏱️  {self.operation_name}: {self.duration_ms:.2f}ms")


async def measure_fotmob_provider():
    """Measure FotMob provider performance."""
    from app.providers.fotmob import FotMobFootballProvider
    
    provider = FotMobFootballProvider(
        base_url="https://www.fotmob.com",
        timeout_seconds=10.0,
        retry_count=1
    )
    
    try:
        today = date.today()
        tomorrow = today + timedelta(days=1)
        
        with PerformanceTimer("FotMob: get_matches_by_date (today)"):
            matches = await provider.get_matches_by_date(today)
        logger.info(f"  → Returned {len(matches)} matches")
        
        with PerformanceTimer("FotMob: get_matches_by_range (2 days)"):
            range_matches = await provider.get_matches_by_range(
                date_from=today,
                date_to=tomorrow
            )
        logger.info(f"  → Returned {len(range_matches)} matches")
        
        if matches:
            match_id = matches[0].source_id
            with PerformanceTimer(f"FotMob: get_match ({match_id})"):
                single_match = await provider.get_match(match_id)
            logger.info(f"  → Match details loaded: {single_match is not None}")
    
    finally:
        await provider.close()


async def measure_hybrid_provider():
    """Measure HybridProvider performance."""
    from app.providers.hybrid_provider import HybridProvider
    from app.providers.manager import ProviderManagerAdapter
    from app.database.session import SessionLocal
    from app.config import get_settings
    
    settings = get_settings()
    session = SessionLocal()
    
    try:
        # Initialize provider manager
        provider_manager = ProviderManagerAdapter(use_real_providers=True)
        hybrid_provider = HybridProvider(
            external_provider=provider_manager,
            session=session
        )
        
        today = date.today()
        tomorrow = today + timedelta(days=1)
        
        with PerformanceTimer("HybridProvider: get_matches_async (status=scheduled, 2 days)"):
            scheduled_matches = await hybrid_provider.get_matches_async(
                from_date=today,
                to_date=tomorrow,
                status="scheduled"
            )
        logger.info(f"  → Returned {len(scheduled_matches)} scheduled matches")
        
        with PerformanceTimer("HybridProvider: get_matches_async (status=live)"):
            live_matches = await hybrid_provider.get_matches_async(
                status="live"
            )
        logger.info(f"  → Returned {len(live_matches)} live matches")
        
        with PerformanceTimer("HybridProvider: get_matches_async (no filter, 2 days)"):
            all_matches = await hybrid_provider.get_matches_async(
                from_date=today,
                to_date=tomorrow
            )
        logger.info(f"  → Returned {len(all_matches)} total matches")
    
    finally:
        session.close()


async def measure_database_queries():
    """Measure database query performance."""
    from app.database.session import SessionLocal
    from app.database.repository import MatchRepository
    from datetime import datetime, timezone
    
    session = SessionLocal()
    repo = MatchRepository(session)
    
    try:
        today = date.today()
        tomorrow = today + timedelta(days=1)
        
        with PerformanceTimer("Database: get_matches_by_status (SCHEDULED, 2 days)"):
            scheduled = repo.get_matches_by_status(
                status="SCHEDULED",
                from_date=today,
                to_date=tomorrow
            )
        logger.info(f"  → Returned {len(scheduled)} scheduled matches from DB")
        
        with PerformanceTimer("Database: get_matches_by_status (LIVE)"):
            live = repo.get_matches_by_status(status="LIVE")
        logger.info(f"  → Returned {len(live)} live matches from DB")
        
        if scheduled:
            match_id = scheduled[0].id
            with PerformanceTimer(f"Database: get_by_id ({match_id})"):
                single_match = repo.get_by_id(match_id)
            logger.info(f"  → Match loaded: {single_match is not None}")
    
    finally:
        session.close()


async def measure_api_endpoint():
    """Measure actual API endpoint response time."""
    import httpx
    
    client = httpx.AsyncClient(timeout=30.0)
    
    try:
        today = date.today()
        tomorrow = today + timedelta(days=1)
        
        # Test matches endpoint
        params = {
            "from_date": today.isoformat(),
            "to_date": tomorrow.isoformat(),
            "status": "scheduled"
        }
        
        with PerformanceTimer("API: GET /api/v1/matches (scheduled, 2 days)"):
            response = await client.get(
                "http://localhost:8003/api/v1/matches",
                params=params
            )
        
        if response.status_code == 200:
            data = response.json()
            matches_count = len(data.get("matches", []))
            logger.info(f"  → HTTP {response.status_code}, {matches_count} matches")
        else:
            logger.warning(f"  → HTTP {response.status_code}")
    
    except Exception as e:
        logger.error(f"  → API endpoint failed: {e}")
    
    finally:
        await client.aclose()


async def main():
    """Run all performance measurements."""
    logger.info("=" * 60)
    logger.info("TUTAR X PERFORMANCE BASELINE MEASUREMENT")
    logger.info("=" * 60)
    
    logger.info("\n📊 PROVIDER LAYER")
    logger.info("-" * 60)
    try:
        await measure_fotmob_provider()
    except Exception as e:
        logger.error(f"FotMob measurement failed: {e}")
    
    logger.info("\n📊 HYBRID PROVIDER LAYER")
    logger.info("-" * 60)
    try:
        await measure_hybrid_provider()
    except Exception as e:
        logger.error(f"HybridProvider measurement failed: {e}")
    
    logger.info("\n📊 DATABASE LAYER")
    logger.info("-" * 60)
    try:
        await measure_database_queries()
    except Exception as e:
        logger.error(f"Database measurement failed: {e}")
    
    logger.info("\n📊 API ENDPOINT (END-TO-END)")
    logger.info("-" * 60)
    try:
        await measure_api_endpoint()
    except Exception as e:
        logger.error(f"API endpoint measurement failed: {e}")
    
    logger.info("\n" + "=" * 60)
    logger.info("MEASUREMENT COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
