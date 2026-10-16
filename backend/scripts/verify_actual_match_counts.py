#!/usr/bin/env python3
"""Verify actual historical match counts with direct SQL."""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime
from app.database.session import SessionLocal

def main():
    """Verify actual match counts with SQL."""
    
    with SessionLocal() as db:
        print("=== DIRECT SQL VERIFICATION ===")
        
        from sqlalchemy import text
        
        # Our test teams
        home_team_id = "ff783ba1-5eb9-4a61-80a2-2d04ca145b1a"  # Chicago Fire FC
        away_team_id = "d3d66b8f-c0dd-4ce4-a213-3bdd08a7171f"  # Vancouver Whitecaps
        target_date = "2026-10-07 00:30:00.000000"
        
        print(f"Home team: {home_team_id}")
        print(f"Away team: {away_team_id}")
        print(f"Target date: {target_date}")
        
        # Check home team matches
        print(f"\n--- Home Team Matches ---")
        result = db.execute(text("""
            SELECT id, scheduled_at, status, home_team_id, away_team_id
            FROM matches 
            WHERE (home_team_id = :team_id OR away_team_id = :team_id)
            AND scheduled_at < :target_date
            AND status = 'FINISHED'
            ORDER BY scheduled_at DESC
        """), {"team_id": home_team_id, "target_date": target_date})
        
        home_matches = result.fetchall()
        print(f"Total home team finished matches before target: {len(home_matches)}")
        for i, match in enumerate(home_matches[:5]):
            print(f"  {i+1}. {match[1]} - {match[2]} - {match[0]}")
        
        # Check away team matches  
        print(f"\n--- Away Team Matches ---")
        result = db.execute(text("""
            SELECT id, scheduled_at, status, home_team_id, away_team_id
            FROM matches 
            WHERE (home_team_id = :team_id OR away_team_id = :team_id)
            AND scheduled_at < :target_date
            AND status = 'FINISHED'
            ORDER BY scheduled_at DESC
        """), {"team_id": away_team_id, "target_date": target_date})
        
        away_matches = result.fetchall()
        print(f"Total away team finished matches before target: {len(away_matches)}")
        for i, match in enumerate(away_matches[:5]):
            print(f"  {i+1}. {match[1]} - {match[2]} - {match[0]}")
            
        # Check all matches for both teams (any status)
        print(f"\n--- All Matches (Any Status) ---")
        result = db.execute(text("""
            SELECT 
                CASE WHEN home_team_id = :home_id THEN 'HOME' ELSE 'AWAY' END as role,
                scheduled_at, status, id
            FROM matches 
            WHERE (home_team_id = :home_id OR away_team_id = :home_id)
            ORDER BY scheduled_at ASC
        """), {"home_id": home_team_id})
        
        all_home_matches = result.fetchall()
        print(f"Home team ALL matches (any status): {len(all_home_matches)}")
        for i, match in enumerate(all_home_matches):
            print(f"  {i+1}. {match[1]} - {match[2]} ({match[0]}) - {match[3]}")
            
        # Check if teams exist
        print(f"\n--- Team Verification ---")
        result = db.execute(text("""
            SELECT id, name FROM teams WHERE id IN (:home_id, :away_id)
        """), {"home_id": home_team_id, "away_id": away_team_id})
        
        teams = result.fetchall()
        print(f"Teams found: {len(teams)}")
        for team in teams:
            print(f"  {team[0]}: {team[1]}")
            
        # The query that should have worked from our analysis
        print(f"\n--- Previous Analysis Query Verification ---")
        result = db.execute(text("""
            WITH team_history AS (
                SELECT 
                    (SELECT COUNT(*) 
                     FROM matches m2 
                     WHERE (m2.home_team_id = :home_id OR m2.away_team_id = :home_id)
                     AND m2.scheduled_at < :target_date 
                     AND m2.status = 'FINISHED') as home_hist_count,
                    (SELECT COUNT(*) 
                     FROM matches m2 
                     WHERE (m2.home_team_id = :away_id OR m2.away_team_id = :away_id)
                     AND m2.scheduled_at < :target_date 
                     AND m2.status = 'FINISHED') as away_hist_count
            )
            SELECT home_hist_count, away_hist_count FROM team_history
        """), {"home_id": home_team_id, "away_id": away_team_id, "target_date": target_date})
        
        counts = result.fetchone()
        if counts:
            print(f"Analysis query results: home={counts[0]}, away={counts[1]}")
        else:
            print("Analysis query returned no results")

if __name__ == "__main__":
    main()