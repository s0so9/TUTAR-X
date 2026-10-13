"""Check database status and match counts."""
from app.infrastructure.database import get_db
from app.infrastructure.models import Match, Team, Competition
from sqlalchemy import func

db = next(get_db())

print("=== DATABASE STATUS ===")
total_matches = db.query(func.count(Match.id)).scalar()
scheduled_matches = db.query(func.count(Match.id)).filter(Match.status == 'SCHEDULED').scalar()
total_teams = db.query(func.count(Team.id)).scalar()
total_competitions = db.query(func.count(Competition.id)).scalar()

print(f"Total matches: {total_matches}")
print(f"SCHEDULED matches: {scheduled_matches}")
print(f"Total teams: {total_teams}")
print(f"Total competitions: {total_competitions}")

# Get sample match if exists
sample = db.query(Match).limit(1).first()
if sample:
    print(f"\n=== SAMPLE MATCH ===")
    print(f"ID: {sample.id}")
    print(f"Home team ID: {sample.home_team_id}")
    print(f"Away team ID: {sample.away_team_id}")
    print(f"Competition ID: {sample.competition_id}")
    print(f"Status: {sample.status}")
    print(f"Match date: {sample.match_date}")

    # Check if team exists
    if sample.home_team_id:
        home_team = db.query(Team).filter(Team.id == sample.home_team_id).first()
        print(f"Home team object: {home_team.name if home_team else 'NOT FOUND'}")

    if sample.competition_id:
        comp = db.query(Competition).filter(Competition.id == sample.competition_id).first()
        print(f"Competition object: {comp.name if comp else 'NOT FOUND'}")
else:
    print("\nNo matches in database")

db.close()
