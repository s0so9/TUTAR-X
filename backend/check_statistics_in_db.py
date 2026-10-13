"""
Direct database check for finished matches with statistics.
"""

from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session
from app.database.models import Match, MatchStatistic
from app.config import Settings

settings = Settings()
engine = create_engine(settings.database_url)


def check_finished_matches():
    """Check for finished matches with statistics."""
    with Session(engine) as session:
        # Count total matches
        total_matches = session.query(func.count(Match.id)).scalar()

        # Count finished matches
        finished_count = session.query(func.count(Match.id)).filter(
            Match.status == 'finished'
        ).scalar()

        # Count scheduled matches
        scheduled_count = session.query(func.count(Match.id)).filter(
            Match.status == 'scheduled'
        ).scalar()

        print("=" * 80)
        print("DATABASE STATISTICS CHECK")
        print("=" * 80)
        print()
        print(f"Total matches: {total_matches}")
        print(f"Finished matches: {finished_count}")
        print(f"Scheduled matches: {scheduled_count}")
        print()

        if finished_count == 0:
            print("❌ NO FINISHED MATCHES IN DATABASE")
            print()
            print("CONCLUSION:")
            print("  Database contains only future/scheduled matches.")
            print("  Shots, corners, and possession are IN-MATCH statistics.")
            print("  They CANNOT exist for matches that haven't been played yet.")
            print()
            print("ROOT CAUSE IDENTIFIED:")
            print("  Frontend shows '--' because data doesn't exist at source.")
            print("  This is EXPECTED BEHAVIOR, not a bug.")
            print()
            print("=" * 80)
            return

        # Get sample finished matches
        print(f"Checking {finished_count} finished match(es) for statistics...")
        print()

        finished_matches = session.query(Match).filter(
            Match.status == 'finished'
        ).limit(10).all()

        matches_with_stats = 0
        matches_without_stats = 0

        for match in finished_matches:
            # Check if has statistics in match_statistics table
            home_stats = session.query(MatchStatistic).filter(
                MatchStatistic.match_id == match.id,
                MatchStatistic.team_id == match.home_team_id
            ).first()

            away_stats = session.query(MatchStatistic).filter(
                MatchStatistic.match_id == match.id,
                MatchStatistic.team_id == match.away_team_id
            ).first()

            has_stats = home_stats is not None and away_stats is not None

            if has_stats:
                matches_with_stats += 1
                print(f"✓ Match ID: {match.id[:16]}...")

                if home_stats:
                    print(f"  Home: shots={home_stats.shots_total}, corners={home_stats.corners}, "
                          f"possession={home_stats.possession_percentage}")
                if away_stats:
                    print(f"  Away: shots={away_stats.shots_total}, corners={away_stats.corners}, "
                          f"possession={away_stats.possession_percentage}")
                print()
            else:
                matches_without_stats += 1

        print()
        print(f"Finished matches WITH statistics: {matches_with_stats}")
        print(f"Finished matches WITHOUT statistics: {matches_without_stats}")
        print()

        if matches_with_stats > 0:
            print("✓ Database HAS finished matches with statistics")
            print()
            print("NEXT STEP: Verify if statistics reach the API and frontend")
        else:
            print("❌ No finished matches have statistics")
            print()
            print("CONCLUSION: Data doesn't exist at source")

        print("=" * 80)


if __name__ == '__main__':
    check_finished_matches()
