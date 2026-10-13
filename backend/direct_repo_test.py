#!/usr/bin/env python3
"""Direct test of MatchRepository."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.database.session import SessionLocal
from app.database.models import Match as DBMatch, MatchStatus
from app.database.repository import MatchRepository

def test_repository():
    db = SessionLocal()

    try:
        # Get a finished match
        match = db.query(DBMatch).filter(
            DBMatch.status == MatchStatus.FINISHED
        ).order_by(DBMatch.scheduled_at.desc()).limit(100).all()[50]

        print(f"Test match: {match.id}")
        print(f"Scheduled: {match.scheduled_at}")
        print(f"Home team: {match.home_team_id}")
        print(f"Away team: {match.away_team_id}")
        print()

        # Create repository
        repo = MatchRepository(db)

        # Get historical matches
        home_matches = repo.get_team_matches_before_date(
            team_id=match.home_team_id,
            before_datetime=match.scheduled_at,
            limit=100,
            finished_only=True
        )

        away_matches = repo.get_team_matches_before_date(
            team_id=match.away_team_id,
            before_datetime=match.scheduled_at,
            limit=100,
            finished_only=True
        )

        print(f"Home team historical matches: {len(home_matches)}")
        print(f"Away team historical matches: {len(away_matches)}")

        if home_matches:
            print(f"\nFirst home match: {home_matches[0].id}, scheduled: {home_matches[0].scheduled_at}")
        if away_matches:
            print(f"First away match: {away_matches[0].id}, scheduled: {away_matches[0].scheduled_at}")

    finally:
        db.close()

if __name__ == "__main__":
    test_repository()
