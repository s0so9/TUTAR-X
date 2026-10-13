#!/usr/bin/env python3
"""Check scheduled match data for prediction debugging."""

import sqlite3
from datetime import datetime

def check_match_data():
    conn = sqlite3.connect('football_intelligence.db')
    cursor = conn.cursor()

    match_id = 'eb12aca4-4319-4f70-9320-4903714fe90d'

    # Get match details
    cursor.execute('SELECT home_team_id, away_team_id, scheduled_at, status FROM matches WHERE id = ?', (match_id,))
    result = cursor.fetchone()

    if not result:
        print(f'Match {match_id} not found')
        return

    home_id, away_id, scheduled, status = result
    print(f'Match: {match_id}')
    print(f'  Status: {status}')
    print(f'  Scheduled: {scheduled}')
    print(f'  Home team ID: {home_id}')
    print(f'  Away team ID: {away_id}')

    # Get team names
    cursor.execute('SELECT name FROM teams WHERE id = ?', (home_id,))
    home_name = cursor.fetchone()
    cursor.execute('SELECT name FROM teams WHERE id = ?', (away_id,))
    away_name = cursor.fetchone()

    print(f'  Home team: {home_name[0] if home_name else "Not found"}')
    print(f'  Away team: {away_name[0] if away_name else "Not found"}')

    # Check historical matches for home team with correct status
    cursor.execute("""
        SELECT COUNT(*) FROM matches
        WHERE (home_team_id = ? OR away_team_id = ?)
        AND status = 'FINISHED'
        AND scheduled_at < ?
    """, (home_id, home_id, scheduled))
    home_history = cursor.fetchone()[0]

    # Check historical matches for away team with correct status
    cursor.execute("""
        SELECT COUNT(*) FROM matches
        WHERE (home_team_id = ? OR away_team_id = ?)
        AND status = 'FINISHED'
        AND scheduled_at < ?
    """, (away_id, away_id, scheduled))
    away_history = cursor.fetchone()[0]

    print(f'\nHistorical data (FINISHED status):')
    print(f'  Home team finished matches: {home_history}')
    print(f'  Away team finished matches: {away_history}')

    # Check all match statuses available
    cursor.execute("SELECT DISTINCT status FROM matches ORDER BY status")
    all_statuses = cursor.fetchall()
    print(f'\nAll match statuses in DB: {[s[0] for s in all_statuses]}')

    # Check matches with different status values
    for status in ['finished', 'FINISHED', 'completed', 'COMPLETED']:
        cursor.execute("""
            SELECT COUNT(*) FROM matches
            WHERE (home_team_id = ? OR away_team_id = ?)
            AND status = ?
            AND scheduled_at < ?
        """, (home_id, home_id, status, scheduled))
        count = cursor.fetchone()[0]
        if count > 0:
            print(f'  {status}: {count} matches')

    # Sample some historical matches
    if home_history > 0:
        cursor.execute("""
            SELECT id, scheduled_at, home_score, away_score
            FROM matches
            WHERE (home_team_id = ? OR away_team_id = ?)
            AND status = 'FINISHED'
            AND scheduled_at < ?
            ORDER BY scheduled_at DESC
            LIMIT 3
        """, (home_id, home_id, scheduled))
        home_sample = cursor.fetchall()
        print(f'\n  Home team recent matches:')
        for match in home_sample:
            print(f'    {match[1]}: {match[2]}-{match[3]}')

    conn.close()

if __name__ == "__main__":
    check_match_data()
