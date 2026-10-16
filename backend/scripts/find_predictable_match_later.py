#!/usr/bin/env python3
"""Find a match from later dates with sufficient historical data."""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime
from app.database.session import SessionLocal
from app.database.repository import MatchRepository, TeamRepository

def main():
    """Find a match with sufficient historical data from later dates."""
    
    with SessionLocal() as db:
        match_repo = MatchRepository(db)
        team_repo = TeamRepository(db)
        
        print("=== FINDING PREDICTABLE MATCH (LATER DATES) ===")
        
        # Search matches from September onwards (after some history accumulated)
        from sqlalchemy import text
        
        result = db.execute(text("""
            SELECT id, home_team_id, away_team_id, scheduled_at, status
            FROM matches 
            WHERE scheduled_at >= '2024-09-10'
            ORDER BY scheduled_at ASC
            LIMIT 50
        """))
        
        matches = result.fetchall()
        print(f"Matches from Sept 10+ to check: {len(matches)}")
        
        found_count = 0
        
        for match_row in matches:
            match_id = match_row[0]
            home_team_id = match_row[1]
            away_team_id = match_row[2] 
            scheduled_at = match_row[3]
            status = match_row[4]
            
            # Get historical matches for both teams
            home_historical = match_repo.get_team_matches_before_date(
                team_id=home_team_id,
                before_datetime=scheduled_at,
                finished_only=True
            )
            
            away_historical = match_repo.get_team_matches_before_date(
                team_id=away_team_id,
                before_datetime=scheduled_at,
                finished_only=True
            )
            
            home_count = len(home_historical)
            away_count = len(away_historical)
            
            # Check if both teams have sufficient data
            if home_count >= 3 and away_count >= 3:
                found_count += 1
                
                # Get team names
                home_team = team_repo.get_by_id(home_team_id)
                away_team = team_repo.get_by_id(away_team_id)
                
                print(f"\n*** PREDICTABLE MATCH #{found_count} ***")
                print(f"Match ID: {match_id}")
                print(f"Date: {scheduled_at}")
                print(f"Status: {status}")
                print(f"Teams: {home_team.name if home_team else 'Unknown'} vs {away_team.name if away_team else 'Unknown'}")
                print(f"Home historical: {home_count} matches")
                print(f"Away historical: {away_count} matches")
                
                if found_count == 1:  # Return first good match
                    print(f"\nUsing this match for prediction test...")
                    return match_id, home_count, away_count
                    
        print(f"\nTotal predictable matches found: {found_count}")
        return None, 0, 0

if __name__ == "__main__":
    main()