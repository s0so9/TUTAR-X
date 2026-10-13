import sys
sys.path.insert(0, 'backend')

from app.database import get_session_factory
from app.database.models import Match
from sqlalchemy import select

session = get_session_factory()()

# Check if test match exists
match_id = '000c4dcc-e92e-4f64-8cc5-988f4145385e'
stmt = select(Match).where(Match.id == match_id)
match = session.execute(stmt).scalar_one_or_none()

print(f'Match found: {match is not None}')
if match:
    print(f'Home team ID: {match.home_team_id}')
    print(f'Away team ID: {match.away_team_id}')
    print(f'Scheduled at: {match.scheduled_at}')
    print(f'Status: {match.status}')

    # Check historical matches for home team
    home_stmt = select(Match).where(
        (Match.home_team_id == match.home_team_id) | (Match.away_team_id == match.home_team_id)
    ).where(
        Match.scheduled_at < match.scheduled_at
    ).where(
        Match.status == 'FINISHED'
    )
    home_matches = list(session.execute(home_stmt).scalars().all())
    print(f'\nHome team historical matches: {len(home_matches)}')

    # Check historical matches for away team
    away_stmt = select(Match).where(
        (Match.home_team_id == match.away_team_id) | (Match.away_team_id == match.away_team_id)
    ).where(
        Match.scheduled_at < match.scheduled_at
    ).where(
        Match.status == 'FINISHED'
    )
    away_matches = list(session.execute(away_stmt).scalars().all())
    print(f'Away team historical matches: {len(away_matches)}')
else:
    print('Match not found in database!')

session.close()
