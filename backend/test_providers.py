#!/usr/bin/env python3
"""Test script to diagnose real provider failures."""

import asyncio
import logging
import sys
from datetime import date, timedelta

# Add backend to path
sys.path.insert(0, '.')

from app.config import settings
from app.providers.fotmob import FotMobFootballProvider
from app.providers.ryzellx import RyzellxFootballProvider
from app.providers.openligadb import OpenLigaDBFootballProvider
from app.providers.exceptions import ProviderError

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def test_fotmob():
    """Test FotMob provider."""
    print("\n=== TESTING FOTMOB ===")
    print(f"Base URL: {settings.fotmob_base_url}")

    provider = FotMobFootballProvider(
        base_url=settings.fotmob_base_url,
        timeout_seconds=settings.provider_timeout_seconds,
        retry_count=settings.provider_retry_count
    )

    try:
        # Test today's matches
        today = date.today()
        print(f"Testing matches for today ({today})")
        matches = await provider.get_matches_by_date(today)
        print(f"✓ FotMob returned {len(matches)} matches for {today}")

        # Test tomorrow's matches (upcoming)
        tomorrow = today + timedelta(days=1)
        print(f"Testing matches for tomorrow ({tomorrow})")
        upcoming_matches = await provider.get_matches_by_date(tomorrow)
        print(f"✓ FotMob returned {len(upcoming_matches)} matches for {tomorrow}")

        # Show sample match if available
        if matches:
            match = matches[0]
            print(f"Sample match: {match.home_team_name} vs {match.away_team_name}")
            print(f"Competition: {match.competition_name} (ID: {match.competition_id})")
            print(f"Teams: {match.home_team_id} / {match.away_team_id}")
            print(f"Status: {match.status}")
        elif upcoming_matches:
            match = upcoming_matches[0]
            print(f"Sample upcoming: {match.home_team_name} vs {match.away_team_name}")
            print(f"Competition: {match.competition_name} (ID: {match.competition_id})")
            print(f"Teams: {match.home_team_id} / {match.away_team_id}")
            print(f"Scheduled: {match.scheduled_at}")

        return len(matches) + len(upcoming_matches) > 0

    except ProviderError as e:
        print(f"✗ FotMob failed: {e}")
        print(f"Provider: {e.provider_name}")
        print(f"Operation: {e.operation}")
        print(f"Message: {e.message}")
        if hasattr(e, 'status_code'):
            print(f"Status code: {e.status_code}")
        if e.original_error:
            print(f"Original error: {e.original_error}")
        return False
    except Exception as e:
        print(f"✗ FotMob unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await provider.close()

async def test_ryzellx():
    """Test Ryzellx provider."""
    print("\n=== TESTING RYZELLX ===")
    print(f"Base URL: {settings.ryzellx_base_url}")

    provider = RyzellxFootballProvider(
        base_url=settings.ryzellx_base_url,
        timeout_seconds=settings.provider_timeout_seconds,
        retry_count=settings.provider_retry_count
    )

    try:
        # Test today's matches
        today = date.today()
        print(f"Testing matches for today ({today})")
        matches = await provider.get_matches_by_date(today)
        print(f"✓ Ryzellx returned {len(matches)} matches for {today}")

        # Test tomorrow's matches (upcoming)
        tomorrow = today + timedelta(days=1)
        print(f"Testing matches for tomorrow ({tomorrow})")
        upcoming_matches = await provider.get_matches_by_date(tomorrow)
        print(f"✓ Ryzellx returned {len(upcoming_matches)} matches for {tomorrow}")

        # Show sample match if available
        if matches:
            match = matches[0]
            print(f"Sample match: {match.home_team_name} vs {match.away_team_name}")
            print(f"Competition: {match.competition_name} (ID: {match.competition_id})")
            print(f"Teams: {match.home_team_id} / {match.away_team_id}")
            print(f"Status: {match.status}")
        elif upcoming_matches:
            match = upcoming_matches[0]
            print(f"Sample upcoming: {match.home_team_name} vs {match.away_team_name}")
            print(f"Competition: {match.competition_name} (ID: {match.competition_id})")
            print(f"Teams: {match.home_team_id} / {match.away_team_id}")
            print(f"Scheduled: {match.scheduled_at}")

        return len(matches) + len(upcoming_matches) > 0

    except ProviderError as e:
        print(f"✗ Ryzellx failed: {e}")
        print(f"Provider: {e.provider_name}")
        print(f"Operation: {e.operation}")
        print(f"Message: {e.message}")
        if hasattr(e, 'status_code'):
            print(f"Status code: {e.status_code}")
        if e.original_error:
            print(f"Original error: {e.original_error}")
        return False
    except Exception as e:
        print(f"✗ Ryzellx unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await provider.close()

async def test_openligadb():
    """Test OpenLigaDB provider."""
    print("\n=== TESTING OPENLIGADB ===")
    print(f"Base URL: {settings.openligadb_base_url}")

    provider = OpenLigaDBFootballProvider(
        base_url=settings.openligadb_base_url,
        timeout_seconds=settings.provider_timeout_seconds,
        retry_count=settings.provider_retry_count
    )

    try:
        # Test available leagues first
        print("Testing available leagues...")
        leagues = await provider.get_competitions()
        print(f"✓ OpenLigaDB returned {len(leagues)} leagues")

        # Test today's matches (usually empty for OpenLigaDB)
        today = date.today()
        print(f"Testing matches for today ({today})")
        matches = await provider.get_matches_by_date(today)
        print(f"✓ OpenLigaDB returned {len(matches)} matches for {today}")

        # Show sample data
        if leagues:
            league = leagues[0]
            print(f"Sample league: {league.name} (ID: {league.source_id})")

        if matches:
            match = matches[0]
            print(f"Sample match: {match.home_team_name} vs {match.away_team_name}")
            print(f"Competition: {match.competition_name} (ID: {match.competition_id})")
            print(f"Teams: {match.home_team_id} / {match.away_team_id}")
            print(f"Status: {match.status}")

        return len(leagues) > 0 or len(matches) > 0

    except ProviderError as e:
        print(f"✗ OpenLigaDB failed: {e}")
        print(f"Provider: {e.provider_name}")
        print(f"Operation: {e.operation}")
        print(f"Message: {e.message}")
        if hasattr(e, 'status_code'):
            print(f"Status code: {e.status_code}")
        if e.original_error:
            print(f"Original error: {e.original_error}")
        return False
    except Exception as e:
        print(f"✗ OpenLigaDB unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await provider.close()

async def test_provider_manager():
    """Test the ProviderManager with fallback."""
    print("\n=== TESTING PROVIDER MANAGER ===")

    from app.providers.manager import ProviderManager
    from app.providers.cache import ProviderCache

    # Create provider instances
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
        retry_count=min(settings.provider_retry_count, 1),  # Cap at 1 for unofficial API
        cache=cache,
    )

    openligadb = OpenLigaDBFootballProvider(
        base_url=settings.openligadb_base_url,
        timeout_seconds=settings.provider_timeout_seconds,
        retry_count=settings.provider_retry_count,
        cache=cache,
    )

    # Create manager
    manager = ProviderManager(
        ryzellx=ryzellx,
        fotmob=fotmob,
        openligadb=openligadb,
        cache=cache,
    )

    try:
        # Test today's matches
        today = date.today()
        print(f"Testing manager for today ({today})")
        matches, metadata = await manager.get_matches_by_date(today)
        print(f"✓ Manager returned {len(matches)} matches for {today}")
        print(f"Selected provider: {metadata.get('selected_provider')}")
        print(f"Attempted providers: {metadata.get('attempted_providers')}")
        print(f"Fallback used: {metadata.get('fallback_used')}")

        return len(matches) > 0

    except Exception as e:
        print(f"✗ Manager unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await manager.close()

async def main():
    """Test all providers."""
    print("=== PROVIDER DIAGNOSIS ===")
    print(f"Configuration:")
    print(f"  USE_REAL_PROVIDERS: {settings.use_real_providers}")
    print(f"  PROVIDER_TIMEOUT: {settings.provider_timeout_seconds}s")
    print(f"  PROVIDER_RETRY_COUNT: {settings.provider_retry_count}")

    fotmob_works = await test_fotmob()
    ryzellx_works = await test_ryzellx()
    openligadb_works = await test_openligadb()
    manager_works = await test_provider_manager()

    print(f"\n=== DIAGNOSIS COMPLETE ===")
    print(f"FotMob: {'✓ Working' if fotmob_works else '✗ Failed'}")
    print(f"Ryzellx: {'✓ Working' if ryzellx_works else '✗ Failed'}")
    print(f"OpenLigaDB: {'✓ Working' if openligadb_works else '✗ Failed'}")
    print(f"Manager: {'✓ Working' if manager_works else '✗ Failed'}")

    return fotmob_works or ryzellx_works or openligadb_works

if __name__ == "__main__":
    result = asyncio.run(main())
    if result:
        print("\n✓ At least one provider is working - real provider mode should work")
    else:
        print("\n✗ All providers failed - real provider mode will not work")
    sys.exit(0 if result else 1)
