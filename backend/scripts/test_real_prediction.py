#!/usr/bin/env python3
"""Test real prediction pipeline with canonical match."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Initialize database session
DATABASE_URL = "sqlite:///./football_intelligence.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def test_real_prediction():
    """Test real prediction pipeline with canonical match data."""
    
    # Use the canonical match found earlier
    canonical_match_id = "47cea9fe-85e0-4c71-9614-ab18f60ce356"
    home_team_canonical = "ff783ba1-5eb9-4a61-80a2-2d04ca145b1a"
    away_team_canonical = "d3d66b8f-c0dd-4ce4-a213-3bdd08a7171f"
    home_provider_id = "6397"  # Chicago Fire FC
    away_provider_id = "307691"  # Vancouver Whitecaps
    
    print(f"Testing real prediction pipeline with match: {canonical_match_id}")
    print(f"Teams: Chicago Fire FC (canonical: {home_team_canonical}, provider: {home_provider_id})")
    print(f"       Vancouver Whitecaps (canonical: {away_team_canonical}, provider: {away_provider_id})")
    
    with SessionLocal() as db_session:
        # Test 1: Create Match object from database
        from app.database.repository import MatchRepository
        match_repo = MatchRepository(db_session)
        
        db_match = match_repo.get_by_id(canonical_match_id)
        if not db_match:
            print(f"ERROR: Match {canonical_match_id} not found in database")
            return
        
        print(f"Database match loaded: {db_match.scheduled_at}, status={db_match.status}")
        
        # Convert database match to domain Match object
        from app.domain.match import Match
        from datetime import timezone
        
        # Ensure datetime is timezone-aware
        scheduled_at = db_match.scheduled_at
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
        
        domain_match = Match(
            id=db_match.id,
            competition_id=db_match.competition_id or "unknown",
            season_id="2026",
            home_team_id=home_provider_id,  # Use provider ID for FotMob interface compatibility
            away_team_id=away_provider_id,
            scheduled_at=scheduled_at,
            status=db_match.status,
            home_score=db_match.home_score,
            away_score=db_match.away_score
        )
        
        print(f"Domain match created with provider team IDs")
        
        # Test 2: Create FotMob provider with synchronous interface
        from app.providers.fotmob import FotMobFootballProvider
        provider = FotMobFootballProvider(
            base_url="https://www.fotmob.com",
            timeout_seconds=5.0,
            retry_count=1
        )
        
        print(f"FotMob provider created")
        
        # Test 3: Test MatchFeatureExtractor with database session
        from app.features.match_features import MatchFeatureExtractor
        
        extractor = MatchFeatureExtractor(
            provider=provider,
            min_matches=3,
            recent_matches=5,
            db_session=db_session  # This enables database-first feature extraction
        )
        
        print(f"Feature extractor created with database session")
        
        # Test 4: Extract features (should use database, not provider)
        print(f"\n--- Testing Feature Extraction ---")
        try:
            features = extractor.extract_features(domain_match)
            print(f"Features extracted successfully!")
            
            # Check key features
            home_attack = features.get("home_attack_strength")
            away_attack = features.get("away_attack_strength")
            home_defense = features.get("home_defense_strength")
            away_defense = features.get("away_defense_strength")
            
            print(f"Team Strengths:")
            print(f"  Home attack: {home_attack}, defense: {home_defense}")
            print(f"  Away attack: {away_attack}, defense: {away_defense}")
            
            # Check if we have sufficient data
            has_sufficient_data = all(v is not None for v in [home_attack, away_attack, home_defense, away_defense])
            print(f"Has sufficient data for prediction: {has_sufficient_data}")
            
            if has_sufficient_data:
                # Test 5: Run prediction service
                from app.prediction.service import PredictionService
                
                prediction_service = PredictionService(
                    provider=provider,
                    db_session=db_session
                )
                
                print(f"\n--- Testing Prediction Service ---")
                try:
                    prediction = prediction_service.generate_prediction(domain_match)
                    
                    if prediction:
                        print(f"Prediction generated successfully!")
                        print(f"  Home win: {prediction.home_win_probability:.3f}")
                        print(f"  Draw: {prediction.draw_probability:.3f}")
                        print(f"  Away win: {prediction.away_win_probability:.3f}")
                        print(f"  Sum: {prediction.home_win_probability + prediction.draw_probability + prediction.away_win_probability:.3f}")
                        print(f"  Home xG: {prediction.home_xg:.3f}")
                        print(f"  Away xG: {prediction.away_xg:.3f}")
                        
                        # Test 6: Generate full MENSIONE pipeline
                        print(f"\n--- Testing Full MENSIONE Pipeline ---")
                        try:
                            context = prediction_service.generate_full_prediction(domain_match)
                            
                            if context:
                                print(f"Full MENSIONE pipeline completed!")
                                print(f"  Predicted score: {context.predicted_score}")
                                
                                if context.mensione_pick:
                                    if context.mensione_pick.get('pass_decision'):
                                        print(f"  TUTAR X: PASS ({context.mensione_pick.get('pass_reason')})")
                                    else:
                                        print(f"  TUTAR X: PICK - {context.mensione_pick.get('market')} {context.mensione_pick.get('selection')}")
                                        print(f"    Probability: {context.mensione_pick.get('probability'):.3f}")
                                        print(f"    Confidence: {context.mensione_pick.get('confidence'):.3f}")
                                else:
                                    print(f"  TUTAR X: Not generated")
                                
                                return {
                                    'success': True,
                                    'match_id': canonical_match_id,
                                    'features_extracted': True,
                                    'prediction_generated': True,
                                    'mensione_pipeline': True,
                                    'home_win_prob': prediction.home_win_probability,
                                    'draw_prob': prediction.draw_probability,
                                    'away_win_prob': prediction.away_win_probability,
                                    'predicted_score': context.predicted_score,
                                    'tutar_x_decision': 'PICK' if context.mensione_pick and not context.mensione_pick.get('pass_decision') else 'PASS'
                                }
                            else:
                                print(f"ERROR: Full pipeline returned None")
                        except Exception as e:
                            print(f"ERROR in full pipeline: {e}")
                            import traceback
                            traceback.print_exc()
                    else:
                        print(f"ERROR: Prediction service returned None")
                except Exception as e:
                    print(f"ERROR in prediction service: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"Insufficient data for prediction - some team strengths are None")
                return {
                    'success': False,
                    'error': 'Insufficient historical data',
                    'features': features
                }
        except Exception as e:
            print(f"ERROR in feature extraction: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': f'Feature extraction failed: {e}'
            }

if __name__ == "__main__":
    result = test_real_prediction()
    print(f"\n=== FINAL RESULT ===")
    if result:
        for key, value in result.items():
            print(f"  {key}: {value}")
    else:
        print("  No result returned")