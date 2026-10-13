import sys
from app.database import get_session_factory
from app.database.models import Match, Team
from sqlalchemy import or_, and_
from datetime import datetime

s = get_session_factory()()

print('=== Team UUID Analysis ===')
test_match = s.query(Match).filter(Match.id == '000c4dcc-e92e-4f64-8cc5-988f4145385e').first()
print(f'Test match home_team_id: {test_match.home_team_id}')
print(f'Test match away_team_id: {test_match.away_team_id}')

home_team = s.query(Team).filter(Team.id == test_match.home_team_id).first()
away_team = s.query(Team).filter(Team.id == test_match.away_team_id).first()
print(f'Home team exists in teams table: {home_team is not None}')
print(f'Away team exists in teams table: {away_team is not None}')
if home_team:
    print(f'Home team name: {home_team.name}')
if away_team:
    print(f'Away team name: {away_team.name}')

print()
print('=== Sample FINISHED matches team IDs ===')
sample_matches = s.query(Match).filter(Match.status == 'FINISHED').limit(5).all()
for m in sample_matches:
    print(f'Match date {m.scheduled_at}: home={m.home_team_id}, away={m.away_team_id}')

print()
print('=== Checking if test match teams appear in any other match ===')
home_in_other = s.query(Match).filter(
    and_(
        or_(Match.home_team_id == test_match.home_team_id, Match.away_team_id == test_match.home_team_id),
        Match.id != test_match.id
    )
).count()
away_in_other = s.query(Match).filter(
    and_(
        or_(Match.home_team_id == test_match.away_team_id, Match.away_team_id == test_match.away_team_id),
        Match.id != test_match.id
    )
).count()
print(f'Home team appears in {home_in_other} other matches (any status)')
print(f'Away team appears in {away_in_other} other matches (any status)')

print()
print('=== Finding suitable match with historical data ===')
# Get matches ordered by date descending
recent_matches = s.query(Match).filter(
    Match.status == 'FINISHED',
    Match.scheduled_at > datetime(2024, 9, 10)
).order_by(Match.scheduled_at.desc()).limit(50).all()

found = False
for m in recent_matches:
    home_hist = s.query(Match).filter(
        and_(
            or_(Match.home_team_id == m.home_team_id, Match.away_team_id == m.home_team_id),
            Match.scheduled_at < m.scheduled_at,
            Match.status == 'FINISHED'
        )
    ).count()

    away_hist = s.query(Match).filter(
        and_(
            or_(Match.home_team_id == m.away_team_id, Match.away_team_id == m.away_team_id),
            Match.scheduled_at < m.scheduled_at,
            Match.status == 'FINISHED'
        )
    ).count()

    if home_hist >= 3 and away_hist >= 3:
        print(f'✅ Found suitable match:')
        print(f'   Match ID: {m.id}')
        print(f'   Date: {m.scheduled_at}')
        print(f'   Home team historical: {home_hist}')
        print(f'   Away team historical: {away_hist}')
        found = True
        break

if not found:
    print('❌ No suitable match found with both teams having >=3 historical matches')

s.close()
