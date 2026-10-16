#!/usr/bin/env python3
"""Find a match where both teams have sufficient historical data."""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime
from app.database.session import SessionLocal
from app.database.repository import MatchRepository, TeamRepository

def main():
    """Find a match with sufficient historical data for prediction."""
    
    with SessionLocal() as db:
        match_repo = MatchRepository(db)
        team_repo = TeamRepository(db)
        
        print("=== FINDING PREDICTABLE MATCH ===")
        print("Minimum required: 3 historical matches per team")
        
        # Get all matches ordered by date
        all_matches = match_repo.get_team_matches_before_date(
            team_id="dummy",  # Will error but let's use SQL directly
            before_datetime=datetime(2030, 1, 1),
            finished_only=False
        )
        
        # Use raw SQL to get all matches sorted by date
        from sqlalchemy import text
        
        result = db.execute(text("""
            SELECT id, home_team_id, away_team_id, scheduled_at, status
            FROM matches 
            ORDER BY scheduled_at ASC
            LIMIT 100
        """))
        
        matches = result.fetchall()
        print(f"Total matches to check: {len(matches)}")
        
        # Check each match for sufficient historical data
        for i, match_row in enumerate(matches[10:]):  # Skip first 10 to ensure some history exists
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
            
            print(f"Match {i+11}: {match_id}")
            print(f"  Date: {scheduled_at}")
            print(f"  Status: {status}")
            print(f"  Home team historical: {home_count}")
            print(f"  Away team historical: {away_count}")
            
            # Check if both teams have sufficient data (minimum 3 matches)
            if home_count >= 3 and away_count >= 3:
                # Get team names
                home_team = team_repo.get_by_id(home_team_id)
                away_team = team_repo.get_by_id(away_team_id)
                
                print(f"\n*** FOUND PREDICTABLE MATCH ***")
                print(f"Match ID: {match_id}")
                print(f"Date: {scheduled_at}")
                print(f"Status: {status}")
                print(f"Teams: {home_team.name if home_team else 'Unknown'} vs {away_team.name if away_team else 'Unknown'}")
                print(f"Home team historical matches: {home_count}")
                print(f"Away team historical matches: {away_count}")
                
                # Show some historical matches for verification
                print(f"\nHome team recent historical matches:")
                for j, hist in enumerate(home_historical[-3:]):
                    print(f"  {j+1}. {hist.scheduled_at} - {hist.status}")
                    
                print(f"\nAway team recent historical matches:")
                for j, hist in enumerate(away_historical[-3:]):
                    print(f"  {j+1}. {hist.scheduled_at} - {hist.status}")
                
                return match_id, home_count, away_count
                
            if i > 20:  # Don't check too many matches
                break
                
        print("\nNo match found with sufficient historical data in first 30 matches")
        return None, 0, 0

if __name__ == "__main__":
    main()