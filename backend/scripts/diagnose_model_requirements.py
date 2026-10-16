"""Diagnose why models fail check_requirements()."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import logging
from datetime import datetime
from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.providers import DevelopmentProvider
from app.features.match_features import MatchFeatureExtractor
from app.prediction.feature_snapshot import extract_feature_snapshot
from app.prediction.data_quality import DataQualityGate
from app.prediction.model_orchestrator import ModelOrchestrator

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def diagnose():
    """Diagnose model requirement failures."""
    
    db: Session = SessionLocal()
    provider = DevelopmentProvider()
    
    try:
        print("\n" + "="*80)
        print("DIAGNOSING MODEL REQUIREMENT FAILURES")
        print("="*80 + "\n")
        
        # Step 1: Get a match from the provider
        print("STEP 1: Getting match from DevelopmentProvider...")
        matches = provider.get_matches()
        
        if not matches:
            print("ERROR: No matches available from provider")
            return
        
        match = matches[0]
        print(f"  Match ID: {match.id}")
        print(f"  Home Team ID: {match.home_team_id}")
        print(f"  Away Team ID: {match.away_team_id}")
        print(f"  Scheduled: {match.scheduled_at}")
        print(f"  Status: {match.status}")
        
        # Step 2: Extract features
        print("\nSTEP 2: Extracting features...")
        extractor = MatchFeatureExtractor(
            provider=provider,
            db_session=db
        )
        
        features = extractor.extract_features(match)
        print(f"  Total features extracted: {len(features)}")
        
        # Print key strength features
        print("\n  Key strength features:")
        strength_features = [
            "home_attack_strength",
            "home_defense_strength",
            "away_attack_strength",
            "away_defense_strength",
        ]
        
        for feat in strength_features:
            val = features.get(feat)
            status = "OK" if val is not None else "MISS"
            print(f"    [{status}] {feat}: {val}")
        
        # Print key form features
        print("\n  Key form features:")
        form_features = [
            "home_recent_avg_goals_scored",
            "home_recent_avg_goals_conceded",
            "away_recent_avg_goals_scored",
            "away_recent_avg_goals_conceded",
            "home_match_count",
            "away_match_count",
        ]
        
        for feat in form_features:
            val = features.get(feat)
            status = "OK" if val is not None else "MISS"
            print(f"    [{status}] {feat}: {val}")
        
        # Step 3: Data quality assessment
        print("\nSTEP 3: Data Quality Assessment...")
        data_quality_gate = DataQualityGate()
        data_quality_report = data_quality_gate.assess(features)
        
        print(f"  Overall Score: {data_quality_report.overall_score:.3f}")
        print(f"  Checks Passed: {data_quality_report.passed}/{len(data_quality_report.checks)}")
        print(f"  Checks Failed: {data_quality_report.failed}")
        
        if data_quality_report.warnings:
            print(f"\n  Warnings:")
            for warning in data_quality_report.warnings:
                print(f"    - {warning}")
        
        print(f"\n  Detailed checks:")
        for check in data_quality_report.checks:
            status = "PASS" if check.passed else "FAIL"
            print(f"    [{status}] {check.check_name}: {check.message}")
            if not check.passed:
                print(f"         Severity: {check.severity}, Score: {check.score:.3f}")
                if check.details:
                    print(f"         Details: {check.details}")
        
        # Step 4: Build snapshot
        print("\nSTEP 4: Building feature snapshot...")
        
        # Build snapshot using the same logic as prediction service
        from app.prediction.service import PredictionService
        
        # Create a temporary prediction service instance to use its snapshot logic
        service = PredictionService(
            provider=provider,
            db_session=db
        )
        
        snapshot = service._extract_canonical_snapshot(match)
        
        print(f"  Snapshot created: version {snapshot.snapshot_version}")
        print(f"  Home strength metrics: {snapshot.home_strength is not None}")
        print(f"  Away strength metrics: {snapshot.away_strength is not None}")
        
        # Step 5: Check each model's requirements
        print("\nSTEP 5: Checking model requirements...")
        
        orchestrator = ModelOrchestrator.create_default_registry()
        
        print(f"  Total models registered: {len(orchestrator._models)}")
        
        # Get feature dict for models
        feature_dict = snapshot.get_feature_dict()
        
        print("\n  Model eligibility check:\n")
        for model_id, model in orchestrator._models.items():
            metadata = model.get_metadata()
            requirements_met, missing = model.check_requirements(feature_dict)
            
            status = "ELIGIBLE" if requirements_met else "REJECTED"
            print(f"  [{status}] {model_id} (v{metadata.version})")
            
            if not requirements_met:
                print(f"    Missing features: {', '.join(missing)}")
                
                # Show which specific features are None
                print(f"    Required features check:")
                for req in metadata.required_features:
                    val = feature_dict.get(req)
                    check = "OK" if val is not None else "MISS"
                    print(f"      [{check}] {req}: {val}")
        
        # Step 6: Run orchestrator
        print("\nSTEP 6: Running model orchestrator...")
        
        result = orchestrator.run_all(snapshot)
        
        print(f"  Successful predictions: {len(result.successful_predictions)}")
        print(f"  Unavailable models: {len(result.unavailable_models)}")
        print(f"  Failed models: {len(result.failed_models)}")
        
        if result.unavailable_models:
            print(f"\n  Unavailable models details:")
            for output in result.unavailable_models:
                print(f"    - {output.model_id}")
                if output.availability:
                    print(f"      Reason: {output.availability.reason}")
                    if output.availability.missing_features:
                        print(f"      Missing: {', '.join(output.availability.missing_features)}")
        
        if result.failed_models:
            print(f"\n  Failed models details:")
            for output in result.failed_models:
                print(f"    - {output.model_id}")
                print(f"      Error: {output.error_message}")
        
        if result.successful_predictions:
            print(f"\n  SUCCESS: {len(result.successful_predictions)} models produced predictions")
            for output in result.successful_predictions:
                pred = output.prediction
                print(f"    - {output.model_id}: H={pred.home_win_prob:.3f}, D={pred.draw_prob:.3f}, A={pred.away_win_prob:.3f}")
        else:
            print(f"\n  FAILURE: No models produced predictions")
            print(f"  This causes 'Insufficient data' error at endpoint")
        
        print("\n" + "="*80)
        print("DIAGNOSIS COMPLETE")
        print("="*80 + "\n")
        
    finally:
        db.close()


if __name__ == "__main__":
    diagnose()
