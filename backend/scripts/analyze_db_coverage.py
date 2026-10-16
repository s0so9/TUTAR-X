#!/usr/bin/env python3
"""Analyze database coverage and find best match for prediction."""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime
from app.database.session import SessionLocal

def main():
    """Analyze database to understand data coverage."""
    
    with SessionLocal() as db:
        print("=== DATABASE COVERAGE ANALYSIS ===")
        
        from sqlalchemy import text
        
        # Check total date range
        result = db.execute(text("""
            SELECT 
                MIN(scheduled_at) as earliest,
                MAX(scheduled_at) as latest,
                COUNT(*) as total_matches,
                COUNT(CASE WHEN status = 'FINISHED' THEN 1 END) as finished_matches
            FROM matches
        """))
        
        row = result.fetchone()
        print(f"Date range: {row[0]} to {row[1]}")
        print(f"Total matches: {row[2]}")
        print(f"Finished matches: {row[3]}")
        
        # Check team with most matches
        result = db.execute(text("""
            SELECT 
                t.name,
                t.id,
                COUNT(*) as match_count
            FROM teams t
            JOIN (
                SELECT home_team_id as team_id FROM matches
                UNION ALL
                SELECT away_team_id as team_id FROM matches
            ) m ON t.id = m.team_id
            GROUP BY t.id, t.name
            ORDER BY match_count DESC
            LIMIT 5
        """))
        
        print(f"\nTop teams by match count:")
        teams = result.fetchall()
        for team in teams:
            print(f"  {team[0]}: {team[2]} matches")
            
        # Use the team with most matches to find a good test case
        if teams:
            top_team_id = teams[0][1]
            top_team_name = teams[0][0]
            
            print(f"\nAnalyzing matches for top team: {top_team_name}")
            
            # Find matches of this team ordered by date
            result = db.execute(text("""
                SELECT id, home_team_id, away_team_id, scheduled_at, status,
                       CASE WHEN home_team_id = :team_id THEN 'HOME' ELSE 'AWAY' END as team_role
                FROM matches 
                WHERE home_team_id = :team_id OR away_team_id = :team_id
                ORDER BY scheduled_at ASC
                LIMIT 20
            """), {"team_id": top_team_id})
            
            matches = result.fetchall()
            print(f"First 20 matches for {top_team_name}:")
            
            for i, match in enumerate(matches):
                print(f"  {i+1}. {match[3]} - {match[4]} - Role: {match[5]}")
                
                # For matches after the 5th, check if there's sufficient history
                if i >= 5:  # At least 5 previous matches for some history
                    match_id = match[0]
                    scheduled_at = match[3]
                    
                    # Count historical finished matches for this team
                    hist_result = db.execute(text("""
                        SELECT COUNT(*) 
                        FROM matches
                        WHERE (home_team_id = ? OR away_team_id = ?)
                        AND scheduled_at < ?
                        AND status = 'FINISHED'
                    """), (top_team_id, top_team_id, scheduled_at))
                    
                    hist_count = hist_result.fetchone()[0]
                    print(f"    -> Historical matches for this team: {hist_count}")
                    
                    if hist_count >= 3:  # Minimum requirement met for at least one team
                        print(f"\n*** POTENTIAL MATCH: {match_id} ***")
                        print(f"Date: {scheduled_at}")
                        print(f"Team {top_team_name} has {hist_count} historical matches")
                        
                        # Now check the opponent team
                        opponent_id = match[2] if match[1] == top_team_id else match[1]
                        
                        opp_result = db.execute(text("""
                            SELECT COUNT(*) 
                            FROM matches
                            WHERE (home_team_id = ? OR away_team_id = ?)
                            AND scheduled_at < ?
                            AND status = 'FINISHED'
                        """), (opponent_id, opponent_id, scheduled_at))
                        
                        opp_count = opp_result.fetchone()[0]
                        
                        # Get opponent name
                        opp_name_result = db.execute(text("""
                            SELECT name FROM teams WHERE id = ?
                        """), (opponent_id,))
                        opp_name = opp_name_result.fetchone()[0]
                        
                        print(f"Opponent {opp_name} has {opp_count} historical matches")
                        
                        if opp_count >= 3:
                            print(f"\n🎯 EXCELLENT MATCH FOUND!")
                            print(f"Match ID: {match_id}")
                            print(f"Teams: {top_team_name} vs {opp_name}")
                            print(f"Date: {scheduled_at}")
                            print(f"Historical data: {hist_count} vs {opp_count}")
                            return match_id, hist_count, opp_count
                            
        return None, 0, 0

if __name__ == "__main__":
    main()