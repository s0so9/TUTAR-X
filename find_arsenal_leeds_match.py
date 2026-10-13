"""Arsenal-Leeds maçını bul."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from sqlalchemy import create_engine, or_, and_
from sqlalchemy.orm import sessionmaker
from app.database.models import Match, Team

db_path = os.path.join(os.path.dirname(__file__), 'backend', 'football_intelligence.db')
engine = create_engine(f'sqlite:///{db_path}')
Session = sessionmaker(bind=engine)
session = Session()

arsenal = session.query(Team).filter(Team.provider_id == '9825').first()
leeds = session.query(Team).filter(Team.provider_id == '8463').first()

print(f"Arsenal UUID: {arsenal.id}")
print(f"Leeds UUID: {leeds.id}")

# Tüm Arsenal-Leeds maçlarını bul
matches = session.query(Match).filter(
    or_(
        and_(Match.home_team_id == arsenal.id, Match.away_team_id == leeds.id),
        and_(Match.home_team_id == leeds.id, Match.away_team_id == arsenal.id)
    )
).all()

print(f"\nTüm Arsenal-Leeds maçları ({len(matches)}):")
for m in matches:
    is_arsenal_home = m.home_team_id == arsenal.id
    home_team = "Arsenal" if is_arsenal_home else "Leeds"
    away_team = "Leeds" if is_arsenal_home else "Arsenal"

    print(f"  {m.id}")
    print(f"    {home_team} vs {away_team}")
    print(f"    {m.scheduled_at}")
    print(f"    Status: {m.status}")
    print(f"    Score: {m.home_score}-{m.away_score}")
    print()

session.close()
