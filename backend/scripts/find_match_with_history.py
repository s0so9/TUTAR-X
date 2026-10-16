#!/usr/bin/env python3
"""Find a match that has historical data for both teams."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.database.models import Match, Team, ProviderSource
from app.database.repository import MatchRepository, TeamRepository

# Create database session  
DATABASE_URL = "sqlite:///./football_intelligence.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def find_match_with_history():
    """Find a match where both teams have historical data."""
    with SessionLocal() as session:
        match_repo = MatchRepository(session)
        
        # Get matches from later dates (so they have historical data)
        result = session.execute(text("""
            SELECT id, scheduled_at, home_team_id, away_team_id, home_score, away_score
            FROM matches 
            WHERE status = 'FINISHED' 
            AND scheduled_at LIKE '2026-10-07%'  -- Get finished matches from Oct 7
            ORDER BY scheduled_at ASC
            LIMIT 20
        """))
        
        potential_matches = result.fetchall()
        
        print(f"Found {len(potential_matches)} finished matches from Oct 7 2026 to check for historical data")
        
        for match_data in potential_matches:
            match_id, scheduled_at, home_team_id, away_team_id, home_score, away_score = match_data
            
            # Check historical matches for both teams
            home_historical = match_repo.get_team_matches_before_date(
                team_id=home_team_id,
                before_datetime=scheduled_at,
                limit=10,
                finished_only=True
            )
            
            away_historical = match_repo.get_team_matches_before_date(
                team_id=away_team_id,
                before_datetime=scheduled_at,
                limit=10,
                finished_only=True
            )
            
            if len(home_historical) >= 3 and len(away_historical) >= 3:
                print(f"\nFound suitable match: {match_id}")
                print(f"  Date: {scheduled_at}")
                print(f"  Score: {home_score}-{away_score}")
                print(f"  Home team historical matches: {len(home_historical)}")
                print(f"  Away team historical matches: {len(away_historical)}")
                
                # Get team names
                team_repo = TeamRepository(session)
                home_team = team_repo.get_by_id(home_team_id)
                away_team = team_repo.get_by_id(away_team_id)
                
                print(f"  Teams: {home_team.name if home_team else 'Unknown'} vs {away_team.name if away_team else 'Unknown'}")
                
                return {
                    'match_id': match_id,
                    'home_team_canonical': home_team_id,
                    'away_team_canonical': away_team_id,
                    'home_team_name': home_team.name if home_team else 'Unknown',
                    'away_team_name': away_team.name if away_team else 'Unknown',
                    'home_team_provider_id': home_team.provider_id if home_team else None,
                    'away_team_provider_id': away_team.provider_id if away_team else None,
                    'home_historical_count': len(home_historical),
                    'away_historical_count': len(away_historical),
                    'scheduled_at': scheduled_at,
                    'home_score': home_score,
                    'away_score': away_score
                }
        
        print("No matches found with sufficient historical data for both teams")
        return None

from app.database.repository import BaseRepository

class TeamRepository(BaseRepository[Team]):
    """Repository for teams."""
    
    def __init__(self, session):
        super().__init__(session, Team)

if __name__ == "__main__":
    result = find_match_with_history()
    if result:
        print("\nCanonical match with historical data:")
        for key, value in result.items():
            print(f"  {key}: {value}")
    else:
        print("\nNo suitable match found")