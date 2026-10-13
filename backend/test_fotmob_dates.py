"""Test FotMob API with different dates."""
import asyncio
import logging
from datetime import date, timedelta

logging.basicConfig(level=logging.ERROR)

from app.config import settings
from app.providers import FotMobFootballProvider, ProviderCache

async def main():
    cache = ProviderCache()
    fotmob = FotMobFootballProvider(
        base_url=settings.fotmob_base_url,
        timeout_seconds=settings.provider_timeout_seconds,
        retry_count=1,
        cache=cache,
    )

    # Test today (should work)
    today = date.today()
    print(f"Testing today ({today})...")
    try:
        matches_today = await fotmob.get_matches_by_date(today)
        print(f"  OK: Got {len(matches_today)} matches for today")
    except Exception as e:
        print(f"  ERROR: {e}")

    # Test yesterday (should work)
    yesterday = today - timedelta(days=1)
    print(f"\nTesting yesterday ({yesterday})...")
    try:
        matches_yesterday = await fotmob.get_matches_by_date(yesterday)
        print(f"  OK: Got {len(matches_yesterday)} matches for yesterday")
    except Exception as e:
        print(f"  ERROR: {e}")

    # Test tomorrow (might not work)
    tomorrow = today + timedelta(days=1)
    print(f"\nTesting tomorrow ({tomorrow})...")
    try:
        matches_tomorrow = await fotmob.get_matches_by_date(tomorrow)
        print(f"  OK: Got {len(matches_tomorrow)} matches for tomorrow")
    except Exception as e:
        print(f"  ERROR: {e}")

    # Test future date (October 6, 2026 - 1 day)
    future_date = date(2026, 10, 5)
    print(f"\nTesting future date ({future_date})...")
    try:
        matches_future = await fotmob.get_matches_by_date(future_date)
        print(f"  OK: Got {len(matches_future)} matches for {future_date}")
    except Exception as e:
        print(f"  ERROR: {e}")

    await fotmob.close()

if __name__ == "__main__":
    asyncio.run(main())
