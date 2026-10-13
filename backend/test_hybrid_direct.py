"""Test HybridProvider directly."""
from datetime import datetime, timedelta, date
from app.database.session import SessionLocal
from app.providers.adapter import ProviderManagerAdapter
from app.providers.hybrid_provider import HybridProvider

session = SessionLocal()

# Create provider manager with empty list (will use dev data)
manager = ProviderManagerAdapter([])

# Create hybrid provider
hybrid = HybridProvider(manager, session)

# Test with date range - last 7 days finished
today = date.today()
past7 = today - timedelta(days=7)

print(f"Testing HybridProvider.get_matches with:")
print(f"  from_date: {past7}")
print(f"  to_date: {today}")
print(f"  status: finished")
print()

matches = hybrid.get_matches(
    from_date=past7,
    to_date=today,
    status='finished'
)

print(f"Result: {len(matches)} matches")
if matches:
    for m in matches[:5]:
        print(f"  {m.id[:12]}... {m.scheduled_at} - {m.status}")
else:
    print("  No matches returned!")

session.close()
