"""Diagnostic script to trace exact cause of prediction failure."""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import logging
from datetime import datetime
from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.providers.fotmob import FotMobProvider
from app.features.match_features import MatchFeatureExtractor
from app.prediction.service import PredictionService
from app.database.repository import TeamRepository, MatchRepository, ProviderSourceRepository
from sqlalchemy import select
from app.database.models import ProviderSource

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def diagnose_prediction(match_id: str):
    """Diagnose why prediction fails for a specific match."""
    
    db: Session = SessionLocal()
    provider = FotMobProvider()
    
    try:
        print("\n" + "="*80)
        print(f"DIAGNOSING PREDICTION FAILURE FOR MATCH: {match_id}")
        print("="*80 + "\n")
        
        # Step 1: Get match from provider
        print("STEP 1: Getting match from provider...")
        match = provider.get_match(match_id)
        if not match:
            print(f"ERROR: Match {match_id} not found in provider")
            return
        
        print(f"  Match: {match.home_team.name if match.home_team else 'Unknown'} vs {match.away_team.name if match.away_team else 'Unknown'}")
        print(f"  Home Team ID (FotMob): {match.home_team_id}")
        print(f"  Away Team ID (FotMob): {match.away_team_id}")
        print(f"  Scheduled: {match.scheduled_at}")
        print(f"  Status: {match.status}")
        
        # Step 2: Verify canonical Team UUID resolution
        print("\nSTEP 2: Resolving canonical Team UUIDs...")
        
        team_repo = TeamRepository(db)
        provider_repo = ProviderSourceRepository(db)
        
        stmt = select(ProviderSource).where(ProviderSource.name == "fotmob")
        fotmob_provider = db.execute(stmt).scalars().first()
        
        if not fotmob_provider:
            print("  ERROR: FotMob provider source not found in database")
            return
        
        print(f"  FotMob Provider Source ID: {fotmob_provider.id}")
        
        home_team_canonical = team_repo.get_by_provider_id(
            provider_source_id=fotmob_provider.id,
            provider_id=match.home_team_id
        )
        
        away_team_canonical = team_repo.get_by_provider_id(
            provider_source_id=fotmob_provider.id,
            provider_id=match.away_team_id
        )
        
        if not home_team_canonical:
            print(f"  ERROR: Home team not found - FotMob ID {match.home_team_id}")
            return
        
        if not away_team_canonical:
            print(f"  ERROR: Away team not found - FotMob ID {match.away_team_id}")
            return
        
        print(f"  Home Team Canonical UUID: {home_team_canonical.id}")
        print(f"  Home Team Name: {home_team_canonical.name}")
        print(f"  Away Team Canonical UUID: {away_team_canonical.id}")
        print(f"  Away Team Name: {away_team_canonical.name}")
        
        # Step 3: Check historical matches in database
        print("\nSTEP 3: Checking historical matches in database...")
        
        match_repo = MatchRepository(db)
        
        home_historical = match_repo.get_team_matches_before_date(
            team_id=home_team_canonical.id,
            before_datetime=match.scheduled_at,
            limit=100,
            finished_only=True
        )
        
        away_historical = match_repo.get_team_matches_before_date(
            team_id=away_team_canonical.id,
            before_datetime=match.scheduled_at,
            limit=100,
            finished_only=True
        )
        
        print(f"  Home team historical matches (FINISHED): {len(home_historical)}")
        print(f"  Away team historical matches (FINISHED): {len(away_historical)}")
        
        if home_historical:
            print(f"  Home team sample match: {home_historical[0].scheduled_at} - Status: {home_historical[0].status}")
        
        if away_historical:
            print(f"  Away team sample match: {away_historical[0].scheduled_at} - Status: {away_historical[0].status}")
        
        # Step 4: Extract features
        print("\nSTEP 4: Extracting features...")
        
        extractor = MatchFeatureExtractor(
            provider=provider,
            db_session=db
        )
        
        features = extractor.extract_features(match)
        
        print(f"  Total features extracted: {len(features)}")
        print("\n  Feature availability:")
        
        key_features = [
            "home_attack_strength",
            "home_defense_strength",
            "away_attack_strength",
            "away_defense_strength",
            "home_recent_avg_goals_scored",
            "away_recent_avg_goals_scored",
            "home_recent_avg_goals_conceded",
            "away_recent_avg_goals_conceded",
            "home_match_count",
            "away_match_count",
        ]
        
        for feat in key_features:
            val = features.get(feat)
            status = "✓" if val is not None else "✗"
            print(f"    {status} {feat}: {val}")
        
        # Step 5: Check model eligibility
        print("\nSTEP 5: Testing prediction service...")
        
        prediction_service = PredictionService(
            provider=provider,
            db_session=db
        )
        
        # Generate prediction
        try:
            analysis_context = prediction_service.generate_full_prediction(
                match=match,
                odds_data=None
            )
            
            print(f"\n  Model predictions generated: {len(analysis_context.model_predictions) if analysis_context.model_predictions else 0}")
            
            if not analysis_context.model_predictions:
                print("\n  ERROR: No model predictions generated!")
                print("  This is the root cause of 'Insufficient data' error")
                
                # Try to get more details from orchestrator
                from app.prediction.feature_snapshot import extract_feature_snapshot
                from app.features.feature_aggregator import FeatureAggregator
                from app.prediction.data_quality_gate import DataQualityGate
                
                # Build snapshot
                feature_aggregator = FeatureAggregator(db_session=db)
                data_quality_gate = DataQualityGate()
                
                data_quality_report = data_quality_gate.assess(features)
                print(f"\n  Data Quality Report:")
                print(f"    Overall Score: {data_quality_report.overall_score:.3f}")
                print(f"    Missing Critical: {len(data_quality_report.missing_critical_features)}")
                print(f"    Missing Recommended: {len(data_quality_report.missing_recommended_features)}")
                
                if data_quality_report.missing_critical_features:
                    print(f"    Critical Features Missing: {', '.join(data_quality_report.missing_critical_features)}")
                
                # Try feature aggregator
                try:
                    feature_set = feature_aggregator.aggregate_features(
                        home_team_id=match.home_team_id,
                        away_team_id=match.away_team_id,
                        match_date=match.scheduled_at
                    )
                    print(f"\n  Feature Aggregator succeeded")
                    print(f"    Feature set available: {feature_set is not None}")
                except Exception as e:
                    print(f"\n  Feature Aggregator failed: {e}")
                
                # Try model orchestrator directly
                from app.prediction.model_orchestrator import ModelOrchestrator
                from app.prediction.feature_snapshot import extract_feature_snapshot
                
                snapshot = extract_feature_snapshot(
                    match_id=match.id,
                    home_team_id=match.home_team_id,
                    away_team_id=match.away_team_id,
                    feature_set=None,
                    data_quality_report=data_quality_report,
                    home_team_name=match.home_team.name if match.home_team else None,
                    away_team_name=match.away_team.name if match.away_team else None,
                    scheduled_at=match.scheduled_at,
                    market_info=None
                )
                
                orchestrator = ModelOrchestrator()
                orchestrator.register_all_models()
                
                result = orchestrator.run_all(snapshot)
                
                print(f"\n  Model Orchestration Result:")
                print(f"    Successful: {len(result.successful_predictions)}")
                print(f"    Unavailable: {len(result.unavailable_models)}")
                print(f"    Failed: {len(result.failed_models)}")
                
                if result.unavailable_models:
                    print(f"\n  Unavailable Models:")
                    for output in result.unavailable_models:
                        print(f"    - {output.model_id}: {output.availability.reason if output.availability else 'No reason'}")
                        if output.availability and output.availability.missing_features:
                            print(f"      Missing: {', '.join(output.availability.missing_features)}")
                
                if result.failed_models:
                    print(f"\n  Failed Models:")
                    for output in result.failed_models:
                        print(f"    - {output.model_id}: {output.error_message}")
            
            else:
                print(f"\n  SUCCESS: Prediction generated")
                prediction = analysis_context.model_predictions[0]
                print(f"    Home Win: {prediction.home_win_probability:.3f}")
                print(f"    Draw: {prediction.draw_probability:.3f}")
                print(f"    Away Win: {prediction.away_win_probability:.3f}")
                
        except Exception as e:
            print(f"\n  ERROR during prediction: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "="*80)
        print("DIAGNOSIS COMPLETE")
        print("="*80 + "\n")
        
    finally:
        db.close()


if __name__ == "__main__":
    # Use the match ID that's failing
    # Arsenal vs Leeds from FotMob
    match_id = "4193490"  # Replace with actual failing match ID
    
    if len(sys.argv) > 1:
        match_id = sys.argv[1]
    
    diagnose_prediction(match_id)
