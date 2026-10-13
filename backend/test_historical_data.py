"""Quick test to check historical data availability for fotmob_5181855."""
import asyncio
import logging
from datetime import timedelta

# Suppress verbose logging
logging.basicConfig(level=logging.ERROR)

from app.config import settings
from app.providers import (
    FotMobFootballProvider,
    ProviderManager,
    ProviderManagerAdapter,
    ProviderCache,
)
from app.providers.development import DevelopmentProvider

async def main():
    settings.use_real_providers = True

    cache = ProviderCache()
    fotmob = FotMobFootballProvider(
        base_url=settings.fotmob_base_url,
        timeout_seconds=settings.provider_timeout_seconds,
        retry_count=1,
        cache=cache,
    )

    dev = DevelopmentProvider()
    manager = ProviderManager(
        ryzellx=dev,
        fotmob=fotmob,
        openligadb=dev,
        cache=cache,
    )

    adapter = ProviderManagerAdapter(manager=manager)

    # Get the match
    match = adapter.get_match('fotmob_5181855')
    print(f"Match: {match.id}")
    print(f"Home: {match.home_team_id}, Away: {match.away_team_id}")
    print(f"Date: {match.scheduled_at}")
    print()

    # Query historical data
    match_date = match.scheduled_at.date()
    from_date = match_date - timedelta(days=90)
    to_date = match_date - timedelta(days=1)

    print(f"Querying: {from_date} to {to_date}")
    print("(This will make ~90 API calls, please wait...)")
    print()

    historical = adapter.get_matches(from_date=from_date, to_date=to_date)

    # Filter for teams
    croatia = [m for m in historical if m.home_team_id == '10155' or m.away_team_id == '10155']
    spain = [m for m in historical if m.home_team_id == '6720' or m.away_team_id == '6720']

    croatia_finished = [m for m in croatia if m.status.value == 'finished']
    spain_finished = [m for m in spain if m.status.value == 'finished']

    print(f"Results:")
    print(f"  Total matches fetched: {len(historical)}")
    print(f"  Croatia matches: {len(croatia)} ({len(croatia_finished)} finished)")
    print(f"  Spain matches: {len(spain)} ({len(spain_finished)} finished)")
    print(f"  Min required: {settings.min_sample_size}")
    print()
    print(f"Data sufficient: {len(croatia_finished) >= settings.min_sample_size and len(spain_finished) >= settings.min_sample_size}")

    await fotmob.close()

if __name__ == "__main__":
    asyncio.run(main())
