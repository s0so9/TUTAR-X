"""Check which models are executing successfully and why others fail."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.prediction.model_orchestrator import ModelOrchestrator
from app.database.session import get_db
from datetime import datetime
import json

def main():
    print("=" * 80)
    print("7-MODEL ARCHITECTURE VALIDATION REPORT")
    print("=" * 80)
    print()
    
    # Create orchestrator with all 7 models
    orchestrator = ModelOrchestrator.create_default_registry()
    
    print(f"Registered Models: {len(orchestrator.get_registered_models())}")
    print("-" * 80)
    for model_id in orchestrator.get_registered_models():
        print(f"  - {model_id}")
    print()
    
    # Get a real match to test
    db = next(get_db())
    
    from app.database.models import Match
    match = db.query(Match).first()
    
    if not match:
        print("ERROR: No matches found in database")
        return
    
    print(f"Test Match: {match.provider_id}")
    print(f"  Home: {match.home_team_id}")
    print(f"  Away: {match.away_team_id}")
    print(f"  Status: {match.status}")
    print()
    
    # Extract features
    print("Extracting Features...")
    print("-" * 80)
    
    from app.features.match_features import MatchFeatureExtractor
    extractor = MatchFeatureExtractor(db)
    
    try:
        snapshot = extractor.extract_features(match)
        print("SUCCESS: Features extracted successfully")
        print()
    except Exception as e:
        print(f"ERROR: Failed to extract features: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # snapshot is already a dict
    features = snapshot if isinstance(snapshot, dict) else snapshot.to_flat_dict()
    match_context = None  # We'll use None for match_context
    available_features = {k: v for k, v in features.items() if v is not None}
    missing_features = {k: v for k, v in features.items() if v is None}
    
    print(f"Total Features: {len(features)}")
    print(f"Available: {len(available_features)} ({len(available_features)/len(features)*100:.1f}%)")
    print(f"Missing: {len(missing_features)} ({len(missing_features)/len(features)*100:.1f}%)")
    print()
    
    # Key features for model requirements
    key_features = {
        "home_goals_scored_avg": features.get("home_goals_scored_avg"),
        "away_goals_scored_avg": features.get("away_goals_scored_avg"),
        "home_form_score": features.get("home_form_score"),
        "away_form_score": features.get("away_form_score"),
        "elo_home": features.get("elo_home"),
        "elo_away": features.get("elo_away"),
        "home_expected_goals": features.get("home_expected_goals"),
        "away_expected_goals": features.get("away_expected_goals"),
    }
    
    print("Key Features for Model Requirements:")
    print("-" * 80)
    for key, value in key_features.items():
        status = "AVAILABLE" if value is not None else "MISSING"
        value_str = f"({value:.3f})" if value is not None else ""
        print(f"  {key:30s}: {status:15s} {value_str}")
    print()
    
    # Run orchestrator
    print("Running Model Orchestrator...")
    print("=" * 80)
    
    outputs = orchestrator.run_all_models(
        features=features,
        match_context=match_context
    )
    
    print()
    print("MODEL EXECUTION RESULTS")
    print("=" * 80)
    
    successful_models = []
    unavailable_models = []
    failed_models = []
    
    for output in outputs:
        print(f"\nModel: {output.model_id} (v{output.model_version})")
        print(f"  Status: {output.status}")
        
        if output.is_successful:
            successful_models.append(output)
            print(f"  SUCCESS: EXECUTED SUCCESSFULLY")
            print(f"  Execution Time: {output.execution_time_ms:.2f}ms")
            if output.prediction:
                print(f"  Home Win: {output.prediction.home_win:.3f}")
                print(f"  Draw: {output.prediction.draw:.3f}")
                print(f"  Away Win: {output.prediction.away_win:.3f}")
                print(f"  Confidence: {output.prediction.confidence_score:.3f}")
        
        elif output.is_unavailable:
            unavailable_models.append(output)
            print(f"  UNAVAILABLE")
            if output.availability:
                print(f"  Reason: {output.availability.reason}")
                if output.availability.missing_features:
                    print(f"  Missing: {', '.join(output.availability.missing_features)}")
        
        else:
            failed_models.append(output)
            print(f"  FAILED")
            if output.error_message:
                print(f"  Error: {output.error_message}")
    
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Registered: {len(orchestrator.get_registered_models())} models")
    print(f"Successful: {len(successful_models)} models")
    print(f"Unavailable: {len(unavailable_models)} models")
    print(f"Failed: {len(failed_models)} models")
    print()
    
    print("Successful Models:")
    for output in successful_models:
        print(f"  OK {output.model_id}")
    print()
    
    print("Unavailable Models (missing inputs):")
    for output in unavailable_models:
        print(f"  NO {output.model_id}")
        if output.availability and output.availability.missing_features:
            print(f"     Missing: {', '.join(output.availability.missing_features)}")
    print()
    
    if failed_models:
        print("Failed Models (execution error):")
        for output in failed_models:
            print(f"  FAIL {output.model_id}: {output.error_message}")
        print()
    
    print("=" * 80)
    print("ENSEMBLE CONTRIBUTION CHECK")
    print("=" * 80)
    print(f"Models contributing to ensemble: {len(successful_models)}/7")
    print()
    
    # Save detailed report
    report = {
        "timestamp": datetime.now().isoformat(),
        "registered_models": orchestrator.get_registered_models(),
        "test_match": match.provider_id,
        "successful_count": len(successful_models),
        "unavailable_count": len(unavailable_models),
        "failed_count": len(failed_models),
        "successful_models": [m.model_id for m in successful_models],
        "unavailable_models": [
            {
                "model_id": m.model_id,
                "reason": m.availability.reason if m.availability else None,
                "missing_features": m.availability.missing_features if m.availability else []
            }
            for m in unavailable_models
        ],
        "failed_models": [
            {
                "model_id": m.model_id,
                "error": m.error_message
            }
            for m in failed_models
        ]
    }
    
    report_path = Path(__file__).parent / "model_status_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"Detailed report saved to: {report_path}")
    print()

if __name__ == "__main__":
    main()
