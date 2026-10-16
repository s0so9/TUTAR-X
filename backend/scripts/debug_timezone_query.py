#!/usr/bin/env python3
"""Debug timezone handling in match queries."""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timezone
from app.database.session import SessionLocal
from app.database.repository import MatchRepository, TeamRepository
from app.domain.enums import MatchStatus

def main():
    """Debug timezone query logic."""
    
    with SessionLocal() as db:
        match_repo = MatchRepository(db)
        team_repo = TeamRepository(db)
        
        print("=== TIMEZONE QUERY DEBUGGING ===")
        
        # Get our test match
        target_match_id = "f5182fe2-baee-442e-8d7b-f8fafc6660b0"
        target_match = match_repo.get_by_id(target_match_id)
        
        if not target_match:
            print(f"Target match {target_match_id} not found")
            return
            
        print(f"\nTarget Match: {target_match.id}")
        print(f"Scheduled at: {target_match.scheduled_at}")
        print(f"Scheduled at type: {type(target_match.scheduled_at)}")
        print(f"Scheduled at timezone: {target_match.scheduled_at.tzinfo}")
        
        # Get team info
        home_team = team_repo.get_by_id(target_match.home_team_id)
        away_team = team_repo.get_by_id(target_match.away_team_id)
        
        print(f"Home Team: {home_team.name if home_team else 'Unknown'} ({target_match.home_team_id})")
        print(f"Away Team: {away_team.name if away_team else 'Unknown'} ({target_match.away_team_id})")
        
        # Check all finished matches for both teams (any date)
        print(f"\n--- ALL FINISHED MATCHES FOR TEAMS ---")
        
        all_home_finished = match_repo.get_team_matches_before_date(
            team_id=target_match.home_team_id,
            before_datetime=datetime(2030, 1, 1, tzinfo=timezone.utc),  # Far future
            finished_only=True
        )
        
        all_away_finished = match_repo.get_team_matches_before_date(
            team_id=target_match.away_team_id,
            before_datetime=datetime(2030, 1, 1, tzinfo=timezone.utc),  # Far future
            finished_only=True
        )
        
        print(f"Home team ALL finished matches: {len(all_home_finished)}")
        for i, match in enumerate(all_home_finished[:5]):  # Show first 5
            print(f"  {i+1}. {match.scheduled_at} - Status: {match.status}")
            
        print(f"Away team ALL finished matches: {len(all_away_finished)}")
        for i, match in enumerate(all_away_finished[:5]):  # Show first 5
            print(f"  {i+1}. {match.scheduled_at} - Status: {match.status}")
        
        # Now test the specific query that's failing
        print(f"\n--- HISTORICAL MATCHES BEFORE TARGET DATE ---")
        print(f"Query: scheduled_at < {target_match.scheduled_at}")
        
        home_historical = match_repo.get_team_matches_before_date(
            team_id=target_match.home_team_id,
            before_datetime=target_match.scheduled_at,
            finished_only=True
        )
        
        away_historical = match_repo.get_team_matches_before_date(
            team_id=target_match.away_team_id,
            before_datetime=target_match.scheduled_at,
            finished_only=True
        )
        
        print(f"Home team historical matches: {len(home_historical)}")
        for i, match in enumerate(home_historical):
            print(f"  {i+1}. {match.scheduled_at} - Status: {match.status}")
            
        print(f"Away team historical matches: {len(away_historical)}")
        for i, match in enumerate(away_historical):
            print(f"  {i+1}. {match.scheduled_at} - Status: {match.status}")
        
        # Manual comparison test
        print(f"\n--- MANUAL TIMEZONE COMPARISON ---")
        target_dt = target_match.scheduled_at
        
        print(f"Target datetime: {target_dt}")
        print(f"Target timezone: {target_dt.tzinfo}")
        
        if all_home_finished:
            sample_match = all_home_finished[0]
            sample_dt = sample_match.scheduled_at
            
            print(f"Sample match datetime: {sample_dt}")
            print(f"Sample timezone: {sample_dt.tzinfo}")
            
            # Test comparison
            is_before = sample_dt < target_dt
            print(f"Is sample ({sample_dt}) < target ({target_dt}): {is_before}")
            
            # Convert both to UTC for comparison
            if target_dt.tzinfo is None:
                target_utc = target_dt.replace(tzinfo=timezone.utc)
            else:
                target_utc = target_dt.astimezone(timezone.utc)
                
            if sample_dt.tzinfo is None:
                sample_utc = sample_dt.replace(tzinfo=timezone.utc)
            else:
                sample_utc = sample_dt.astimezone(timezone.utc)
                
            print(f"Target UTC: {target_utc}")
            print(f"Sample UTC: {sample_utc}")
            print(f"Is sample UTC < target UTC: {sample_utc < target_utc}")

if __name__ == "__main__":
    main()