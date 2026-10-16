#!/usr/bin/env python3
"""Test prediction system with a match that has historical data."""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime
from app.database.session import SessionLocal
from app.database.repository import MatchRepository
from app.prediction.service import PredictionService
from app.providers.database_adapter import DatabaseAdapter

def main():
    """Test prediction with match that should have data."""
    
    with SessionLocal() as db:
        match_repo = MatchRepository(db)
        
        # Match ID from our previous search: OB vs Silkeborg
        test_match_id = "e74d0cb1-b7e1-42a6-adeb-fa0981ccf6e4"
        
        print(f"=== TESTING PREDICTION WITH MATCH: {test_match_id} ===")
        
        # Get the match
        match = match_repo.get_by_id(test_match_id)
        if not match:
            print("Match not found")
            return
            
        print(f"Match: {match.id}")
        print(f"Date: {match.scheduled_at}")
        print(f"Status: {match.status}")
        
        # Verify historical data exists
        home_historical = match_repo.get_team_matches_before_date(
            team_id=match.home_team_id,
            before_datetime=match.scheduled_at,
            finished_only=True
        )
        
        away_historical = match_repo.get_team_matches_before_date(
            team_id=match.away_team_id,
            before_datetime=match.scheduled_at,
            finished_only=True
        )
        
        print(f"Home team historical matches: {len(home_historical)}")
        print(f"Away team historical matches: {len(away_historical)}")
        
        # Now test the prediction service
        try:
            from app.providers.database_adapter import DatabaseAdapter
            from app.providers import FootballDataProvider
            
            print("\n--- Testing Prediction Service ---")
            
            # Get provider  
            db_adapter = DatabaseAdapter()
            provider = FootballDataProvider()
            
            prediction_service = PredictionService(
                db_adapter=db_adapter,
                provider=provider,
                db_session=db
            )
            
            # Convert database match to domain match
            from app.domain.match import Match as DomainMatch
            domain_match = DomainMatch(
                id=match.id,
                home_team_id=match.home_team_id,
                away_team_id=match.away_team_id,
                competition_id=match.competition_id or "unknown",
                season_id=match.season or "unknown",
                scheduled_at=match.scheduled_at,
                status=match.status,
                home_score=match.home_score,
                away_score=match.away_score,
                home_score_ht=match.home_score_ht,
                away_score_ht=match.away_score_ht,
                outcome=match.outcome,
                round=match.round,
                created_at=match.created_at,
                updated_at=match.updated_at,
            )
            
            prediction = prediction_service.get_prediction(domain_match)
            
            print("*** PREDICTION SUCCESS ***")
            print(f"Home win probability: {prediction.home_win_probability}")
            print(f"Draw probability: {prediction.draw_probability}") 
            print(f"Away win probability: {prediction.away_win_probability}")
            print(f"Expected home goals: {prediction.expected_home_goals}")
            print(f"Expected away goals: {prediction.expected_away_goals}")
            
        except Exception as e:
            print(f"*** PREDICTION FAILED ***")
            print(f"Error: {str(e)}")
            print(f"Error type: {type(e).__name__}")
            
            # If it's insufficient data, that's expected for some cases
            if "insufficient data" in str(e).lower():
                print("This appears to be a legitimate 'insufficient data' case")
            else:
                import traceback
                print("\nFull traceback:")
                traceback.print_exc()

if __name__ == "__main__":
    main()