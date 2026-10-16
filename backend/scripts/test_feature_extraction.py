#!/usr/bin/env python3
"""Test feature extraction step by step."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.domain.match import Match
from app.providers.fotmob import FotMobFootballProvider
from app.features.match_features import MatchFeatureExtractor

# Initialize database session
DATABASE_URL = "sqlite:///./football_intelligence.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def test_feature_extraction():
    """Test feature extraction step by step."""
    
    # Use test data
    home_provider_id = "6397"  # Chicago Fire FC  
    away_provider_id = "307691"  # Vancouver Whitecaps
    match_datetime = datetime(2026, 10, 7, 0, 30, tzinfo=timezone.utc)
    
    # Create domain match
    domain_match = Match(
        id="test-match-id",
        competition_id="test-comp", 
        season_id="2026",
        home_team_id=home_provider_id,
        away_team_id=away_provider_id,
        scheduled_at=match_datetime,
        status="scheduled",
    )
    
    with SessionLocal() as db_session:
        # Create extractor with database session
        provider = FotMobFootballProvider("https://test.com")
        extractor = MatchFeatureExtractor(
            provider=provider,
            min_matches=3,
            recent_matches=5,
            db_session=db_session
        )
        
        print("=== Testing _load_historical_matches_from_db ===")
        
        # Test database historical match loading directly
        try:
            historical_matches = extractor._load_historical_matches_from_db(
                match=domain_match,
                from_date=match_datetime.date(),
                to_date=match_datetime.date()
            )
            
            print(f"Database historical matches found: {len(historical_matches)}")
            
            if historical_matches:
                print("Sample matches:")
                for i, m in enumerate(historical_matches[:5]):
                    print(f"  {i+1}. {m.scheduled_at} - Teams: {m.home_team_id} vs {m.away_team_id}")
            
            # Filter for our test teams
            home_team_canonical = "ff783ba1-5eb9-4a61-80a2-2d04ca145b1a"
            away_team_canonical = "d3d66b8f-c0dd-4ce4-a213-3bdd08a7171f"
            
            home_matches = [
                m for m in historical_matches
                if m.home_team_id == home_team_canonical or m.away_team_id == home_team_canonical
            ]
            away_matches = [
                m for m in historical_matches 
                if m.home_team_id == away_team_canonical or m.away_team_id == away_team_canonical
            ]
            
            print(f"Home team matches in result: {len(home_matches)}")
            print(f"Away team matches in result: {len(away_matches)}")
            
        except Exception as e:
            print(f"Database query failed: {e}")
            import traceback
            traceback.print_exc()
            
        print("\n=== Testing Full _build_match_context ===")
        
        # Test full context building
        try:
            context = extractor._build_match_context(domain_match)
            
            print(f"Context built successfully")
            print(f"Home team matches: {len(context.home_team_history.matches)}")
            print(f"Away team matches: {len(context.away_team_history.matches)}")
            
            if context.home_team_history.matches:
                print("Home team sample matches:")
                for i, m in enumerate(context.home_team_history.matches[:3]):
                    print(f"  {i+1}. {m.scheduled_at} - {m.home_score}-{m.away_score}")
                    
            if context.away_team_history.matches:
                print("Away team sample matches:")
                for i, m in enumerate(context.away_team_history.matches[:3]):
                    print(f"  {i+1}. {m.scheduled_at} - {m.home_score}-{m.away_score}")
            
        except Exception as e:
            print(f"Context building failed: {e}")
            import traceback
            traceback.print_exc()
            
        print("\n=== Testing TeamStrengthCalculator ===")
        
        # Test team strength calculation directly
        try:
            from app.features.team_strength import TeamStrengthCalculator
            
            calculator = TeamStrengthCalculator(min_matches=3)
            strength_features = calculator.calculate(context)
            
            print(f"Strength features calculated")
            print(f"Home attack strength: {strength_features.get('home_attack_strength')}")
            print(f"Home defense strength: {strength_features.get('home_defense_strength')}")
            print(f"Away attack strength: {strength_features.get('away_attack_strength')}")
            print(f"Away defense strength: {strength_features.get('away_defense_strength')}")
            
        except Exception as e:
            print(f"Strength calculation failed: {e}")
            import traceback
            traceback.print_exc()
            
        print("\n=== Testing Full Feature Extraction ===")
        
        # Test full feature extraction
        try:
            features = extractor.extract_features(domain_match)
            
            print(f"Full feature extraction completed")
            print(f"Home attack strength: {features.get('home_attack_strength')}")
            print(f"Home defense strength: {features.get('home_defense_strength')}")
            print(f"Away attack strength: {features.get('away_attack_strength')}")
            print(f"Away defense strength: {features.get('away_defense_strength')}")
            print(f"Home match count: {features.get('home_match_count')}")
            print(f"Away match count: {features.get('away_match_count')}")
            
        except Exception as e:
            print(f"Feature extraction failed: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_feature_extraction()