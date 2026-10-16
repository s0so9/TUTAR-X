#!/usr/bin/env python3
"""Test script to find and use a canonical match from the database for validation."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.models import Match, Team, ProviderSource
from app.database.repository import MatchRepository, TeamRepository
from app.domain.enums import MatchStatus

# Create database session  
DATABASE_URL = "sqlite:///./football_intelligence.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def find_canonical_match():
    """Find a canonical match from database for testing."""
    with SessionLocal() as session:
        match_repo = MatchRepository(session)
        
        # Get finished matches (don't require xG for this test)
        from sqlalchemy import select, and_
        stmt = select(Match).where(
            Match.status == MatchStatus.FINISHED
        ).limit(10)
        
        matches = session.execute(stmt).scalars().all()
        
        print(f"Found {len(matches)} finished matches:")
        for i, match in enumerate(matches):
            print(f"  {i+1}. Match ID: {match.id}")
            print(f"     Teams: {match.home_team_id} vs {match.away_team_id}")
            print(f"     Date: {match.scheduled_at}")
            print(f"     Score: {match.home_score}-{match.away_score}")
            print(f"     xG: {match.home_xg}-{match.away_xg}")
            print()
        
        if matches:
            # Use first match for testing
            test_match = matches[0]
            print(f"Using match {test_match.id} for testing")
            
            # Test historical data for both teams
            team_repo = TeamRepository(session)
            
            # Test home team historical data
            home_matches = match_repo.get_team_matches_before_date(
                team_id=test_match.home_team_id,
                before_datetime=test_match.scheduled_at,
                limit=10,
                finished_only=True
            )
            
            # Test away team historical data  
            away_matches = match_repo.get_team_matches_before_date(
                team_id=test_match.away_team_id,
                before_datetime=test_match.scheduled_at,
                limit=10,
                finished_only=True
            )
            
            print(f"Home team ({test_match.home_team_id}) historical matches: {len(home_matches)}")
            print(f"Away team ({test_match.away_team_id}) historical matches: {len(away_matches)}")
            
            if home_matches:
                print(f"  Sample home match: {home_matches[0].id}, {home_matches[0].scheduled_at}")
            if away_matches:
                print(f"  Sample away match: {away_matches[0].id}, {away_matches[0].scheduled_at}")
            
            # Test provider source mapping
            provider_repo = ProviderSourceRepository(session)
            
            # Find FotMob provider
            from sqlalchemy import select
            stmt = select(ProviderSource).where(ProviderSource.name == "fotmob")
            fotmob_provider = session.execute(stmt).scalars().first()
            
            if fotmob_provider:
                print(f"FotMob provider found: {fotmob_provider.id}")
                
                # Test canonical team lookup
                home_team = team_repo.get_by_id(test_match.home_team_id)
                away_team = team_repo.get_by_id(test_match.away_team_id)
                
                if home_team:
                    print(f"Home team: {home_team.name} (canonical: {home_team.id}, provider: {home_team.provider_id})")
                if away_team:
                    print(f"Away team: {away_team.name} (canonical: {away_team.id}, provider: {away_team.provider_id})")
                
                return {
                    'match_id': test_match.id,
                    'home_team_canonical': test_match.home_team_id,
                    'away_team_canonical': test_match.away_team_id,
                    'home_team_provider_id': home_team.provider_id if home_team else None,
                    'away_team_provider_id': away_team.provider_id if away_team else None,
                    'fotmob_provider_id': fotmob_provider.id,
                    'home_historical_count': len(home_matches),
                    'away_historical_count': len(away_matches),
                    'scheduled_at': test_match.scheduled_at
                }
            else:
                print("FotMob provider not found in database")
                return None
        else:
            print("No finished matches found")
            return None

# Import missing repository class
from app.database.repository import BaseRepository

class ProviderSourceRepository(BaseRepository[ProviderSource]):
    """Repository for provider sources."""
    
    def __init__(self, session):
        super().__init__(session, ProviderSource)

if __name__ == "__main__":
    result = find_canonical_match()
    if result:
        print("\nCanonical match test data:")
        for key, value in result.items():
            print(f"  {key}: {value}")
    else:
        print("\nNo suitable canonical match found for testing")