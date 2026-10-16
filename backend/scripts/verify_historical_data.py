"""Verify historical data import."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.session import get_db
from app.database.models import Match, MatchStatistic
from sqlalchemy import func

session = next(get_db())

print("=== DATABASE VERIFICATION ===\n")
print(f"Total matches: {session.query(Match).count()}")
print(f"Finished matches: {session.query(Match).filter(Match.status == 'FINISHED').count()}")
print(f"Match statistics records: {session.query(MatchStatistic).count()}")
print()

print("=== COVERAGE ===\n")
print(f"Stats with shots_total: {session.query(MatchStatistic).filter(MatchStatistic.shots_total != None).count()}")
print(f"Stats with shots_on_target: {session.query(MatchStatistic).filter(MatchStatistic.shots_on_target != None).count()}")
print(f"Stats with xG: {session.query(MatchStatistic).filter(MatchStatistic.xg != None).count()}")
print(f"Stats with possession: {session.query(MatchStatistic).filter(MatchStatistic.possession_percentage != None).count()}")
print()

print("=== SAMPLE MATCH WITH STATS ===\n")
# Find a match with statistics
match_with_stats = session.query(Match).join(
    MatchStatistic, Match.id == MatchStatistic.match_id
).filter(
    Match.status == 'FINISHED',
    MatchStatistic.shots_total != None,
    MatchStatistic.xg != None
).first()

if match_with_stats:
    print(f"Match ID: {match_with_stats.provider_id}")
    print(f"Score: {match_with_stats.home_score}-{match_with_stats.away_score}")
    print(f"Status: {match_with_stats.status}")
    
    stats = session.query(MatchStatistic).filter(MatchStatistic.match_id == match_with_stats.id).all()
    print(f"Statistics records: {len(stats)}\n")
    
    for i, stat in enumerate(stats):
        print(f"Team {i+1}:")
        print(f"  Shots total: {stat.shots_total}")
        print(f"  Shots on target: {stat.shots_on_target}")
        print(f"  xG: {stat.xg}")
        print(f"  Possession: {stat.possession_percentage}%")
        print(f"  Passes: {stat.passes_completed}/{stat.passes_attempted}")
        print(f"  Yellow cards: {stat.yellow_cards}")
        print(f"  Corners: {stat.corners}")
        print()
else:
    print("No matches with complete statistics found")
