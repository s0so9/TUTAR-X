"""Quick integration test"""
import asyncio
from datetime import date
from app.providers.fotmob import FotMobFootballProvider
from app.providers.manager import ProviderManager
from app.providers.adapter import ProviderManagerAdapter
from app.providers.cache import ProviderCache

async def test():
    print("Testing FotMob integration...")

    # Direct FotMob test
    fotmob = FotMobFootballProvider(
        base_url="https://www.fotmob.com",
        timeout_seconds=10.0,
        retry_count=1,
    )

    test_date = date(2026, 10, 6)
    matches = await fotmob.get_matches_by_date(test_date)
    print(f"\n1. FotMob direct: {len(matches)} matches")
    if matches:
        print(f"   Sample: {matches[0].home_team_name} vs {matches[0].away_team_name}")

    # Manager test
    cache = ProviderCache()
    manager = ProviderManager(
        ryzellx=None,
        fotmob=fotmob,
        openligadb=None,
        cache=cache
    )

    matches_manager, metadata = await manager.get_matches_by_date(test_date)
    print(f"\n2. ProviderManager: {len(matches_manager)} matches")
    print(f"   Selected provider: {metadata.get('selected_provider')}")
    if matches_manager:
        print(f"   Sample: {matches_manager[0].home_team_name} vs {matches_manager[0].away_team_name}")

    # Adapter test (async)
    adapter = ProviderManagerAdapter(manager=manager)
    matches_adapter = await adapter.get_matches_async(from_date=test_date)
    print(f"\n3. Adapter async: {len(matches_adapter)} matches")
    if matches_adapter:
        print(f"   Sample: {matches_adapter[0].home_team_id} - {matches_adapter[0].away_team_id}")

    await fotmob.close()

asyncio.run(test())
