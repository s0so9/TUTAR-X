#!/usr/bin/env python3
"""Check database contents to understand the current state."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.database.models import Match, Team, ProviderSource
from app.domain.enums import MatchStatus

# Create database session  
DATABASE_URL = "sqlite:///./football_intelligence.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def check_database():
    """Check database contents."""
    with SessionLocal() as session:
        # Check if tables exist
        result = session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = [row[0] for row in result.fetchall()]
        print(f"Tables in database: {tables}")
        
        if 'matches' in tables:
            # Count total matches
            result = session.execute(text("SELECT COUNT(*) FROM matches"))
            total_matches = result.scalar()
            print(f"Total matches: {total_matches}")
            
            # Count finished matches
            result = session.execute(text("SELECT COUNT(*) FROM matches WHERE status = 'FINISHED'"))
            finished_matches = result.scalar()
            print(f"Finished matches: {finished_matches}")
            
            # Count matches with xG
            result = session.execute(text("SELECT COUNT(*) FROM matches WHERE home_xg IS NOT NULL AND away_xg IS NOT NULL"))
            xg_matches = result.scalar()
            print(f"Matches with xG data: {xg_matches}")
            
            # Sample some matches
            result = session.execute(text("SELECT id, scheduled_at, status, home_score, away_score, home_xg, away_xg FROM matches LIMIT 10"))
            matches = result.fetchall()
            print(f"\nSample matches:")
            for match in matches:
                print(f"  {match[0]}: {match[1]}, status={match[2]}, score={match[3]}-{match[4]}, xG={match[5]}-{match[6]}")
        
        if 'teams' in tables:
            result = session.execute(text("SELECT COUNT(*) FROM teams"))
            total_teams = result.scalar()
            print(f"Total teams: {total_teams}")
        
        if 'provider_sources' in tables:
            result = session.execute(text("SELECT id, name FROM provider_sources"))
            providers = result.fetchall()
            print(f"Provider sources: {providers}")

if __name__ == "__main__":
    check_database()