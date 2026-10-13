#!/usr/bin/env python3
"""Find Fluminense vs Coritiba match in database."""

from app.database import SessionLocal
from sqlalchemy import text

def find_fluminense_coritiba():
    """Find Fluminense vs Coritiba match."""
    session = SessionLocal()

    # Search for team names containing these strings
    fluminense_teams = session.execute(
        text("SELECT id, name FROM teams WHERE LOWER(name) LIKE LOWER(:pattern)"),
        {"pattern": "%fluminense%"}
    ).fetchall()

    coritiba_teams = session.execute(
        text("SELECT id, name FROM teams WHERE LOWER(name) LIKE LOWER(:pattern)"),
        {"pattern": "%coritiba%"}
    ).fetchall()

    print("Fluminense teams:")
    for team in fluminense_teams:
        print(f"  {team[0]} - {team[1]}")

    print("Coritiba teams:")
    for team in coritiba_teams:
        print(f"  {team[0]} - {team[1]}")

    # If we found the teams, look for matches between them
    if fluminense_teams and coritiba_teams:
        flu_id = fluminense_teams[0][0]
        cori_id = coritiba_teams[0][0]

        matches = session.execute(
            text("""
                SELECT m.id, m.status, m.scheduled_at, m.home_score, m.away_score,
                       h.name as home_team, a.name as away_team
                FROM matches m
                JOIN teams h ON m.home_team_id = h.id
                JOIN teams a ON m.away_team_id = a.id
                WHERE (m.home_team_id = :flu_id AND m.away_team_id = :cori_id)
                   OR (m.home_team_id = :cori_id AND m.away_team_id = :flu_id)
                ORDER BY m.scheduled_at DESC
                LIMIT 5
            """),
            {"flu_id": flu_id, "cori_id": cori_id}
        ).fetchall()

        print(f"\\nMatches between {fluminense_teams[0][1]} and {coritiba_teams[0][1]}:")
        for match in matches:
            print(f"  ID: {match[0]}")
            print(f"  Status: {match[1]}")
            print(f"  Teams: {match[5]} vs {match[6]}")
            print(f"  Score: {match[3]}-{match[4]}")
            print(f"  Scheduled: {match[2]}")
            print()

    session.close()

if __name__ == "__main__":
    find_fluminense_coritiba()
