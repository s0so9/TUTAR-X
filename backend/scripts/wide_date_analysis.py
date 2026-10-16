#!/usr/bin/env python3
"""Wide date range analysis to find any suitable match."""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.database.session import SessionLocal

def main():
    """Comprehensive date range analysis."""
    
    with SessionLocal() as db:
        print("=== WIDE DATE RANGE ANALYSIS ===")
        
        from sqlalchemy import text
        
        # Check if ANY match has sufficient historical data anywhere in the database
        result = db.execute(text("""
            WITH team_history AS (
                SELECT 
                    m1.id as target_match_id,
                    m1.scheduled_at as target_date,
                    m1.home_team_id,
                    m1.away_team_id,
                    ht.name as home_team_name,
                    at.name as away_team_name,
                    (SELECT COUNT(*) 
                     FROM matches m2 
                     WHERE (m2.home_team_id = m1.home_team_id OR m2.away_team_id = m1.home_team_id)
                     AND m2.scheduled_at < m1.scheduled_at 
                     AND m2.status = 'FINISHED') as home_hist_count,
                    (SELECT COUNT(*) 
                     FROM matches m2 
                     WHERE (m2.home_team_id = m1.away_team_id OR m2.away_team_id = m1.away_team_id)
                     AND m2.scheduled_at < m1.scheduled_at 
                     AND m2.status = 'FINISHED') as away_hist_count
                FROM matches m1
                JOIN teams ht ON m1.home_team_id = ht.id
                JOIN teams at ON m1.away_team_id = at.id
                WHERE m1.scheduled_at >= '2024-09-20'  -- After initial data
                ORDER BY m1.scheduled_at ASC
                LIMIT 100
            )
            SELECT 
                target_match_id,
                target_date,
                home_team_name,
                away_team_name,
                home_hist_count,
                away_hist_count
            FROM team_history
            WHERE home_hist_count >= 3 AND away_hist_count >= 3
            ORDER BY target_date ASC
            LIMIT 5
        """))
        
        suitable_matches = result.fetchall()
        
        print(f"Suitable matches found: {len(suitable_matches)}")
        
        if suitable_matches:
            print(f"\n🎯 TOP PREDICTION CANDIDATES:")
            for i, match in enumerate(suitable_matches):
                print(f"  {i+1}. {match[2]} vs {match[3]}")
                print(f"     Match ID: {match[0]}")
                print(f"     Date: {match[1]}")
                print(f"     Historical: {match[4]} vs {match[5]}")
                
            # Return first match for testing
            best_match = suitable_matches[0]
            return best_match[0], best_match[4], best_match[5]
        else:
            print("\n❌ NO MATCHES WITH 3+ HISTORICAL DATA FOR BOTH TEAMS")
            
            # Check maximum available
            result = db.execute(text("""
                SELECT 
                    MAX(home_hist_count) as max_home,
                    MAX(away_hist_count) as max_away,
                    COUNT(*) as total_analyzed
                FROM (
                    SELECT 
                        (SELECT COUNT(*) 
                         FROM matches m2 
                         WHERE (m2.home_team_id = m1.home_team_id OR m2.away_team_id = m1.home_team_id)
                         AND m2.scheduled_at < m1.scheduled_at 
                         AND m2.status = 'FINISHED') as home_hist_count,
                        (SELECT COUNT(*) 
                         FROM matches m2 
                         WHERE (m2.home_team_id = m1.away_team_id OR m2.away_team_id = m1.away_team_id)
                         AND m2.scheduled_at < m1.scheduled_at 
                         AND m2.status = 'FINISHED') as away_hist_count
                    FROM matches m1
                    WHERE m1.scheduled_at >= '2024-09-20'
                    LIMIT 500
                ) sub
            """))
            
            stats = result.fetchone()
            print(f"\nDatabase Statistics:")
            print(f"  Max home team historical matches: {stats[0]}")
            print(f"  Max away team historical matches: {stats[1]}")
            print(f"  Matches analyzed: {stats[2]}")
            
            return None, 0, 0

if __name__ == "__main__":
    main()