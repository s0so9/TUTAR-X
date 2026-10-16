#!/usr/bin/env python3
"""Find a match that should have legitimate historical data."""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timezone
from app.database.session import SessionLocal
from app.database.repository import MatchRepository, TeamRepository
from app.domain.enums import MatchStatus

def main():
    """Find matches with legitimate historical data."""
    
    with SessionLocal() as db:
        match_repo = MatchRepository(db)
        team_repo = TeamRepository(db)
        
        print("=== FINDING MATCH WITH ACTUAL HISTORY ===")
        
        # Get all finished matches, ordered by date
        all_finished_matches = match_repo.get_team_matches_before_date(
            team_id="any-team-id",  # This will fail but let's use raw SQL
            before_datetime=datetime(2030, 1, 1),
            finished_only=True
        )
        
        # Let's use raw SQL to get all finished matches
        from sqlalchemy import text
        
        result = db.execute(text("""
            SELECT id, home_team_id, away_team_id, scheduled_at, status
            FROM matches 
            WHERE status = 'FINISHED'
            ORDER BY scheduled_at ASC
        """))
        
        all_matches = result.fetchall()
        
        print(f"Total finished matches: {len(all_matches)}")
        
        if len(all_matches) < 2:
            print("Not enough matches to find one with history")
            return
        
        # Look for a match that has other matches before it
        for i, match in enumerate(all_matches[1:], 1):  # Skip first match
            match_id = match[0]
            home_team_id = match[1]
            away_team_id = match[2]
            scheduled_at = match[3]
            
            print(f"\n--- Testing Match {i}: {match_id} ---")
            print(f"Scheduled: {scheduled_at}")
            
            # Check if this match has historical data for either team
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
            
            print(f"Home team historical matches: {home_count}")
            print(f"Away team historical matches: {away_count}")
            
            if home_count > 0 or away_count > 0:
                # Get team names
                home_team = team_repo.get_by_id(home_team_id)
                away_team = team_repo.get_by_id(away_team_id)
                
                print(f"\n*** FOUND MATCH WITH HISTORY ***")
                print(f"Match ID: {match_id}")
                print(f"Date: {scheduled_at}")
                print(f"Teams: {home_team.name if home_team else 'Unknown'} vs {away_team.name if away_team else 'Unknown'}")
                print(f"Home team historical: {home_count} matches")
                print(f"Away team historical: {away_count} matches")
                
                # Show some historical matches
                if home_historical:
                    print(f"\nHome team historical matches:")
                    for j, hist_match in enumerate(home_historical[:3]):
                        print(f"  {j+1}. {hist_match.scheduled_at}")
                        
                if away_historical:
                    print(f"\nAway team historical matches:")
                    for j, hist_match in enumerate(away_historical[:3]):
                        print(f"  {j+1}. {hist_match.scheduled_at}")
                
                return  # Found what we need
                
        print("\nNo matches found with sufficient historical data")

if __name__ == "__main__":
    main()