#!/usr/bin/env python3
"""Check if the specific match exists in database."""

from app.database import SessionLocal
from sqlalchemy import text

def check_match_existence():
    """Check if the match 1f05edd0-b0a5-4453-b70c-1892247bea54 exists."""
    session = SessionLocal()

    # Check exact match
    match_id = '1f05edd0-b0a5-4453-b70c-1892247bea54'
    result = session.execute(
        text("SELECT id, home_team_id, away_team_id, status, scheduled_at FROM matches WHERE id = :match_id"),
        {"match_id": match_id}
    ).fetchone()

    if result:
        print(f"✅ Match exists: {result}")
    else:
        print("❌ Match not found in database")

        # Check for similar IDs
        similar = session.execute(
            text("SELECT id FROM matches WHERE id LIKE :pattern LIMIT 5"),
            {"pattern": "1f05edd0%"}
        ).fetchall()

        print(f"Similar IDs: {len(similar)}")
        for row in similar:
            print(f"  {row[0]}")

        # Check total match count
        total = session.execute(text("SELECT COUNT(*) FROM matches")).fetchone()
        print(f"Total matches in DB: {total[0] if total else 0}")

        # Show some sample matches
        samples = session.execute(
            text("SELECT id, status FROM matches ORDER BY scheduled_at LIMIT 3")
        ).fetchall()
        print("Sample matches:")
        for row in samples:
            print(f"  {row[0]} - {row[1]}")

    session.close()

if __name__ == "__main__":
    check_match_existence()
