#!/usr/bin/env python3
"""Debug database query issue."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.repository import MatchRepository, TeamRepository

# Initialize database session
DATABASE_URL = "sqlite:///./football_intelligence.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def debug_database_query():
    """Debug why database queries aren't finding historical matches."""
    
    # Use the same test data
    canonical_match_id = "47cea9fe-85e0-4c71-9614-ab18f60ce356"
    home_team_canonical = "ff783ba1-5eb9-4a61-80a2-2d04ca145b1a"
    away_team_canonical = "d3d66b8f-c0dd-4ce4-a213-3bdd08a7171f"
    home_provider_id = "6397"  # Chicago Fire FC
    away_provider_id = "307691"  # Vancouver Whitecaps
    
    with SessionLocal() as db_session:
        match_repo = MatchRepository(db_session)
        team_repo = TeamRepository(db_session)
        
        # Get the target match
        target_match = match_repo.get_by_id(canonical_match_id)
        print(f"Target match: {target_match.scheduled_at}")
        
        # Test direct canonical UUID queries
        print(f"\n--- Direct Canonical UUID Queries ---")
        
        home_matches = match_repo.get_team_matches_before_date(
            team_id=home_team_canonical,
            before_datetime=target_match.scheduled_at,
            limit=10,
            finished_only=True
        )
        print(f"Home team canonical matches: {len(home_matches)}")
        
        away_matches = match_repo.get_team_matches_before_date(
            team_id=away_team_canonical,
            before_datetime=target_match.scheduled_at,
            limit=10,
            finished_only=True
        )
        print(f"Away team canonical matches: {len(away_matches)}")
        
        # Test provider ID to canonical mapping
        print(f"\n--- Provider ID to Canonical Mapping ---")
        
        # Get FotMob provider source
        from app.database.models import ProviderSource
        from sqlalchemy import select
        stmt = select(ProviderSource).where(ProviderSource.name == "fotmob")
        fotmob_provider = db_session.execute(stmt).scalars().first()
        print(f"FotMob provider ID: {fotmob_provider.id}")
        
        # Test provider ID lookups
        home_team = team_repo.get_by_provider_id(
            provider_source_id=fotmob_provider.id,
            provider_id=home_provider_id
        )
        print(f"Home team from provider ID {home_provider_id}: {home_team.id if home_team else None}")
        
        away_team = team_repo.get_by_provider_id(
            provider_source_id=fotmob_provider.id,
            provider_id=away_provider_id
        )
        print(f"Away team from provider ID {away_provider_id}: {away_team.id if away_team else None}")
        
        # Check if the canonical IDs match what we expect
        if home_team:
            print(f"Expected home canonical: {home_team_canonical}")
            print(f"Actual home canonical:   {home_team.id}")
            print(f"Match: {home_team.id == home_team_canonical}")
        
        if away_team:
            print(f"Expected away canonical: {away_team_canonical}")
            print(f"Actual away canonical:   {away_team.id}")
            print(f"Match: {away_team.id == away_team_canonical}")
        
        # Test what matches exist for these teams BEFORE the target
        print(f"\n--- Historical Match Analysis ---")
        
        if home_team:
            # Check all matches for home team
            all_home_matches = match_repo.get_team_matches_before_date(
                team_id=home_team.id,
                before_datetime=target_match.scheduled_at,
                limit=100,
                finished_only=False  # Include all statuses
            )
            print(f"All home team matches before target: {len(all_home_matches)}")
            
            finished_home_matches = [m for m in all_home_matches if str(m.status) == 'MatchStatus.FINISHED']
            print(f"Finished home team matches: {len(finished_home_matches)}")
            
            # Check status values
            print(f"Status values in home matches:")
            for m in all_home_matches:
                print(f"  {m.scheduled_at}: {m.status} (type: {type(m.status)})")
        
        if away_team:
            all_away_matches = match_repo.get_team_matches_before_date(
                team_id=away_team.id,
                before_datetime=target_match.scheduled_at,
                limit=100,
                finished_only=False
            )
            print(f"All away team matches before target: {len(all_away_matches)}")
            
            finished_away_matches = [m for m in all_away_matches if str(m.status) == 'MatchStatus.FINISHED']
            print(f"Finished away team matches: {len(finished_away_matches)}")

if __name__ == "__main__":
    debug_database_query()