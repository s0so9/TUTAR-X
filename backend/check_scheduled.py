"""Check scheduled matches for date range."""
from datetime import datetime
from app.infrastructure.database import get_db
from app.infrastructure.models import Match, Team, Competition
from sqlalchemy import func, and_

db = next(get_db())

print("=== SCHEDULED MATCHES CHECK ===")

# Check matches by status
scheduled_count = db.query(func.count(Match.id)).filter(Match.status == 'SCHEDULED').scalar()
print(f"Total SCHEDULED matches: {scheduled_count}")

# Check date range 2026-10-10 to 2026-10-17
from_date = datetime(2026, 10, 10)
to_date = datetime(2026, 10, 17, 23, 59, 59)

scheduled_in_range = db.query(func.count(Match.id)).filter(
    and_(
        Match.status == 'SCHEDULED',
        Match.scheduled_at >= from_date,
        Match.scheduled_at <= to_date
    )
).scalar()

print(f"SCHEDULED matches 2026-10-10 to 2026-10-17: {scheduled_in_range}")

# Get sample matches
samples = db.query(Match).filter(
    and_(
        Match.status == 'SCHEDULED',
        Match.scheduled_at >= from_date,
        Match.scheduled_at <= to_date
    )
).limit(5).all()

print(f"\n=== SAMPLE SCHEDULED MATCHES ===")
for match in samples:
    home_team = db.query(Team).filter(Team.id == match.home_team_id).first()
    away_team = db.query(Team).filter(Team.id == match.away_team_id).first()
    comp = db.query(Competition).filter(Competition.id == match.competition_id).first()

    print(f"\nMatch ID: {match.id}")
    print(f"  Home: {home_team.name if home_team else f'MISSING({match.home_team_id})'}")
    print(f"  Away: {away_team.name if away_team else f'MISSING({match.away_team_id})'}")
    print(f"  Competition: {comp.name if comp else f'MISSING({match.competition_id})'}")
    print(f"  Scheduled: {match.scheduled_at}")
    print(f"  Status: {match.status}")

db.close()
