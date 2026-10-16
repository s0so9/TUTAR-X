"""Detailed check of which 4 models execute and why 3 don't."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.session import get_db
from app.database.models import Match
from app.prediction.service import PredictionService
import json

def main():
    print("=" * 80)
    print("DETAILED 7-MODEL EXECUTION ANALYSIS")
    print("=" * 80)
    print()
    
    # Get database and service
    db = next(get_db())
    service = PredictionService(db)
    
    # Get a match
    match = db.query(Match).first()
    
    if not match:
        print("ERROR: No matches in database")
        return
    
    print(f"Test Match: {match.provider_id}")
    print(f"Home: {match.home_team_id}")
    print(f"Away: {match.away_team_id}")
    print()
    
    # Generate prediction (this runs the full pipeline including orchestrator)
    print("Running prediction pipeline...")
    print("=" * 80)
    
    try:
        result = service.generate_prediction(match)
        print("SUCCESS: Pipeline completed")
        print()
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Check registered models
    registered = service.model_orchestrator.get_registered_models()
    print(f"Registered Models: {len(registered)}")
    for m in registered:
        print(f"  - {m}")
    print()
    
    # Get orchestration result from the prediction result
    # We need to inspect the result object
    print("Analyzing prediction result...")
    print(f"Result type: {type(result).__name__}")
    
    if hasattr(result, 'model_outputs'):
        print(f"Model outputs found: {len(result.model_outputs)}")
        
        successful = []
        unavailable = []
        failed = []
        
        for output in result.model_outputs:
            if output.is_successful:
                successful.append(output)
            elif output.is_unavailable:
                unavailable.append(output)
            else:
                failed.append(output)
        
        print()
        print("=" * 80)
        print("EXECUTION RESULTS")
        print("=" * 80)
        print()
        print(f"Successful: {len(successful)} models")
        print(f"Unavailable: {len(unavailable)} models")
        print(f"Failed: {len(failed)} models")
        print()
        
        # SUCCESSFUL MODELS
        if successful:
            print("=" * 80)
            print("SUCCESSFUL MODELS (EXECUTING + CONTRIBUTING TO ENSEMBLE)")
            print("=" * 80)
            for output in successful:
                print()
                print(f"Model: {output.model_id} v{output.model_version}")
                print(f"  Status: {output.status}")
                print(f"  Execution Time: {output.execution_time_ms:.2f}ms")
                if output.prediction:
                    print(f"  Predictions:")
                    print(f"    Home Win: {output.prediction.home_win:.4f}")
                    print(f"    Draw: {output.prediction.draw:.4f}")
                    print(f"    Away Win: {output.prediction.away_win:.4f}")
                    print(f"    Confidence: {output.prediction.confidence_score:.4f}")
        
        # UNAVAILABLE MODELS
        if unavailable:
            print()
            print("=" * 80)
            print("UNAVAILABLE MODELS (MISSING REQUIRED DATA)")
            print("=" * 80)
            for output in unavailable:
                print()
                print(f"Model: {output.model_id} v{output.model_version}")
                print(f"  Status: {output.status}")
                if output.availability:
                    print(f"  Reason: {output.availability.reason}")
                    if output.availability.missing_features:
                        print(f"  Missing Features:")
                        for feature in output.availability.missing_features:
                            print(f"    - {feature}")
        
        # FAILED MODELS
        if failed:
            print()
            print("=" * 80)
            print("FAILED MODELS (EXECUTION ERROR)")
            print("=" * 80)
            for output in failed:
                print()
                print(f"Model: {output.model_id} v{output.model_version}")
                print(f"  Status: {output.status}")
                print(f"  Error: {output.error_message}")
        
        # FINAL SUMMARY
        print()
        print("=" * 80)
        print("VALIDATION SUMMARY")
        print("=" * 80)
        print()
        print(f"Total Registered: 7 models")
        print(f"Successfully Executed: {len(successful)} models")
        print(f"Unavailable (missing data): {len(unavailable)} models")
        print(f"Failed (errors): {len(failed)} models")
        print()
        
        print("Executing models:")
        for output in successful:
            print(f"  OK: {output.model_id}")
        print()
        print("NOT executing (missing data):")
        for output in unavailable:
            print(f"  NO: {output.model_id}")
        if failed:
            print()
            print("NOT executing (errors):")
            for output in failed:
                print(f"  ERROR: {output.model_id}")
        print()
        
        # Save report
        report = {
            "registered_models": registered,
            "successful_count": len(successful),
            "unavailable_count": len(unavailable),
            "failed_count": len(failed),
            "successful_models": [
                {
                    "model_id": o.model_id,
                    "version": o.model_version,
                    "execution_time_ms": o.execution_time_ms,
                    "home_win": o.prediction.home_win if o.prediction else None,
                    "draw": o.prediction.draw if o.prediction else None,
                    "away_win": o.prediction.away_win if o.prediction else None,
                    "confidence": o.prediction.confidence_score if o.prediction else None,
                }
                for o in successful
            ],
            "unavailable_models": [
                {
                    "model_id": o.model_id,
                    "reason": o.availability.reason if o.availability else None,
                    "missing_features": o.availability.missing_features if o.availability else [],
                }
                for o in unavailable
            ],
            "failed_models": [
                {
                    "model_id": o.model_id,
                    "error": o.error_message,
                }
                for o in failed
            ],
        }
        
        report_path = Path(__file__).parent / "7_model_validation_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"Detailed report saved: {report_path}")
        print()
    else:
        print("ERROR: No model_outputs found in result")
        print(f"Result attributes: {dir(result)}")

if __name__ == "__main__":
    main()
