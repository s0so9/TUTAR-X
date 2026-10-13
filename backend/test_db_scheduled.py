"""Test database for SCHEDULED matches."""
from datetime import datetime
from app.database import get_db
from app.database.models import Match
from sqlalchemy import func, and_

db = next(get_db())

from_dt = datetime(2026, 10, 10)
to_dt = datetime(2026, 10, 17, 23, 59, 59)

# Count matches in range
scheduled = db.query(func.count(Match.id)).filter(
    and_(
        Match.status == 'SCHEDULED',
        Match.scheduled_at >= from_dt,
        Match.scheduled_at <= to_dt
    )
).scalar()

total = db.query(func.count(Match.id)).filter(
    and_(
        Match.scheduled_at >= from_dt,
        Match.scheduled_at <= to_dt
    )
).scalar()

print(f'Matches in date range 2026-10-10 to 2026-10-17: {total}')
print(f'SCHEDULED in range: {scheduled}')

print(f'\nFirst 3 SCHEDULED matches:')
for m in db.query(Match).filter(
    and_(
        Match.status == 'SCHEDULED',
        Match.scheduled_at >= from_dt,
        Match.scheduled_at <= to_dt
    )
).limit(3).all():
    print(f'  ID: {m.id[:12]}... Status: {m.status} Date: {m.scheduled_at}')
    print(f'    Home: {m.home_team_id[:12]}... Away: {m.away_team_id[:12]}...')

db.close()
