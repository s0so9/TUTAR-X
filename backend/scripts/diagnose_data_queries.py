#!/usr/bin/env python3
"""Comprehensive data query diagnosis."""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime
from app.database.session import SessionLocal

def main():
    """Diagnose data availability and query conditions."""
    
    with SessionLocal() as db:
        print("=== DATA QUERY DIAGNOSIS ===")
        
        from sqlalchemy import text
        
        # 1. Total match count by status
        print("\n1. MATCH DISTRIBUTION BY STATUS:")
        result = db.execute(text("""
            SELECT status, COUNT(*) as count
            FROM matches 
            GROUP BY status
            ORDER BY count DESC
        """))
        
        for row in result:
            print(f"   {row[0]}: {row[1]} matches")
        
        # 2. Match distribution by date ranges
        print("\n2. MATCH DISTRIBUTION BY DATE RANGES:")
        result = db.execute(text("""
            SELECT 
                CASE 
                    WHEN scheduled_at < '2024-09-01' THEN 'Before Sept 1'
                    WHEN scheduled_at < '2024-10-01' THEN 'September 2024'
                    WHEN scheduled_at < '2024-11-01' THEN 'October 2024'
                    WHEN scheduled_at < '2025-01-01' THEN 'Rest of 2024'
                    ELSE 'Future (2025+)'
                END as date_range,
                COUNT(*) as count,
                COUNT(CASE WHEN status = 'FINISHED' THEN 1 END) as finished_count
            FROM matches
            GROUP BY date_range
            ORDER BY MIN(scheduled_at)
        """))
        
        for row in result:
            print(f"   {row[0]}: {row[1]} total ({row[2]} finished)")
        
        # 3. Team ID matching rate
        print("\n3. TEAM ID MATCHING RATES:")
        result = db.execute(text("""
            SELECT 
                COUNT(*) as total_matches,
                COUNT(h.id) as home_team_exists,
                COUNT(a.id) as away_team_exists,
                COUNT(CASE WHEN h.id IS NULL OR a.id IS NULL THEN 1 END) as orphaned_matches
            FROM matches m
            LEFT JOIN teams h ON m.home_team_id = h.id
            LEFT JOIN teams a ON m.away_team_id = a.id
        """))
        
        row = result.fetchone()
        print(f"   Total matches: {row[0]}")
        print(f"   With valid home team: {row[1]}")
        print(f"   With valid away team: {row[2]}")
        print(f"   Orphaned matches (missing team): {row[3]}")
        
        # 4. Find matches with maximum historical data potential
        print("\n4. ANALYSIS: MATCHES WITH HISTORICAL DATA POTENTIAL")
        
        # Get matches from mid-September when some history should exist
        result = db.execute(text("""
            SELECT 
                m.id,
                m.scheduled_at,
                m.status,
                ht.name as home_team,
                at.name as away_team,
                m.home_team_id,
                m.away_team_id
            FROM matches m
            JOIN teams ht ON m.home_team_id = ht.id
            JOIN teams at ON m.away_team_id = at.id
            WHERE m.scheduled_at >= '2024-09-15'
            AND m.scheduled_at <= '2024-12-31'
            ORDER BY m.scheduled_at ASC
            LIMIT 20
        """))
        
        matches = result.fetchall()
        print(f"\nAnalyzing {len(matches)} matches from Sept 15 - Dec 31 2024:")
        
        suitable_matches = []
        
        for i, match in enumerate(matches):
            match_id = match[0]
            scheduled_at = match[1]
            status = match[2]
            home_team = match[3]
            away_team = match[4]
            home_team_id = match[5]
            away_team_id = match[6]
            
            print(f"\n  Match {i+1}: {home_team} vs {away_team}")
            print(f"    ID: {match_id}")
            print(f"    Date: {scheduled_at}")
            print(f"    Status: {status}")
            
            # Count historical FINISHED matches for each team BEFORE this match date
            home_hist_result = db.execute(text("""
                SELECT COUNT(*) 
                FROM matches
                WHERE (home_team_id = :team_id OR away_team_id = :team_id)
                AND scheduled_at < :target_date
                AND status = 'FINISHED'
            """), {"team_id": home_team_id, "target_date": scheduled_at})
            
            away_hist_result = db.execute(text("""
                SELECT COUNT(*) 
                FROM matches
                WHERE (home_team_id = :team_id OR away_team_id = :team_id)
                AND scheduled_at < :target_date
                AND status = 'FINISHED'
            """), {"team_id": away_team_id, "target_date": scheduled_at})
            
            home_hist_count = home_hist_result.fetchone()[0]
            away_hist_count = away_hist_result.fetchone()[0]
            
            print(f"    Historical finished matches:")
            print(f"      {home_team}: {home_hist_count}")
            print(f"      {away_team}: {away_hist_count}")
            
            # Check if both teams meet minimum requirement (3 matches)
            if home_hist_count >= 3 and away_hist_count >= 3:
                print(f"    ✅ SUITABLE FOR PREDICTION!")
                suitable_matches.append({
                    'match_id': match_id,
                    'home_team': home_team,
                    'away_team': away_team,
                    'home_hist': home_hist_count,
                    'away_hist': away_hist_count,
                    'scheduled_at': scheduled_at
                })
            else:
                reasons = []
                if home_hist_count < 3:
                    reasons.append(f"{home_team} has only {home_hist_count} < 3")
                if away_hist_count < 3:
                    reasons.append(f"{away_team} has only {away_hist_count} < 3")
                print(f"    ❌ Insufficient data: {', '.join(reasons)}")
        
        print(f"\n=== SUMMARY ===")
        print(f"Matches analyzed: {len(matches)}")
        print(f"Suitable for prediction: {len(suitable_matches)}")
        
        if suitable_matches:
            print(f"\n🎯 BEST PREDICTION CANDIDATES:")
            for i, match in enumerate(suitable_matches[:3]):
                print(f"  {i+1}. {match['home_team']} vs {match['away_team']}")
                print(f"     ID: {match['match_id']}")
                print(f"     Historical data: {match['home_hist']} vs {match['away_hist']}")
                print(f"     Date: {match['scheduled_at']}")
                
            return suitable_matches[0]['match_id'], suitable_matches[0]['home_hist'], suitable_matches[0]['away_hist']
        else:
            print(f"❌ NO SUITABLE MATCHES FOUND")
            return None, 0, 0

if __name__ == "__main__":
    main()