#!/usr/bin/env python3
"""
Check database schema and find Fluminense matches
"""

import sqlite3

conn = sqlite3.connect('backend/football_intelligence.db')
cursor = conn.cursor()

try:
    print("=== Matches table structure ===")
    cursor.execute("PRAGMA table_info(matches)")
    columns = cursor.fetchall()
    for col in columns:
        print(f"{col[1]}: {col[2]}")

    print("\n=== Teams table structure ===")
    cursor.execute("PRAGMA table_info(teams)")
    columns = cursor.fetchall()
    for col in columns:
        print(f"{col[1]}: {col[2]}")

    print("\n=== Sample match with team lookup ===")
    cursor.execute("""
    SELECT m.id, m.home_team_id, m.away_team_id, m.scheduled_at, m.status,
           ht.name as home_team, at.name as away_team
    FROM matches m
    LEFT JOIN teams ht ON m.home_team_id = ht.id
    LEFT JOIN teams at ON m.away_team_id = at.id
    WHERE ht.name LIKE "%Fluminense%" OR at.name LIKE "%Fluminense%"
    LIMIT 3
    """)
    matches = cursor.fetchall()
    for match in matches:
        print(f"ID: {match[0]}")
        print(f"Match: {match[5]} vs {match[6]}")
        print(f"Date: {match[3]}")
        print(f"Status: {match[4]}")
        print()

    print("=== Checking specific correct ID ===")
    correct_id = "aa4c9808-cb36-486e-bd41-003cc28b8543"
    cursor.execute("""
    SELECT m.id, ht.name as home_team, at.name as away_team, m.status
    FROM matches m
    LEFT JOIN teams ht ON m.home_team_id = ht.id
    LEFT JOIN teams at ON m.away_team_id = at.id
    WHERE m.id = ?
    """, (correct_id,))
    match = cursor.fetchone()
    if match:
        print(f"✅ Found: {match[1]} vs {match[2]} ({match[3]})")
    else:
        print("❌ Not found")

finally:
    conn.close()
