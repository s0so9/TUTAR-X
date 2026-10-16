"""Execute walk-forward validation for shot markets.

This script runs walk-forward validation on historical data to evaluate
whether shot intelligence features actually improve prediction accuracy.
"""

import json
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.database import SessionLocal
from app.prediction.shot_market_engine import ShotMarketEngine
from app.features.advanced_feature_engineering import AdvancedFeatureEngineer
from app.backtesting import WalkForwardValidator, ShotMarketVariant


def main():
    """Run walk-forward validation and write results."""
    print("=" * 80)
    print("TUTAR X Shot Market Walk-Forward Validation")
    print("=" * 80)
    print()
    
    # Initialize components
    session = SessionLocal()
    try:
        engine = ShotMarketEngine(session=session)
        validator = WalkForwardValidator(
            session=session,
            shot_market_engine=engine,
            min_matches=10
        )
        
        print("Validating shot market predictions with walk-forward evaluation...")
        print()
        
        # Run validation for FULL variant first
        print(f"Running validation for variant: {ShotMarketVariant.FULL.value}")
        full_results = validator.validate(variant=ShotMarketVariant.FULL)
        
        if not full_results.thresholds:
            # Insufficient data
            message = (
                f"INSUFFICIENT_HISTORICAL_SAMPLE: Found insufficient finished matches "
                f"with shot data. Shot market walk-forward validation cannot proceed."
            )
            print(f"\n{message}\n")
            
            results_output = {
                "status": "insufficient_data",
                "message": message,
                "matches_required": validator.min_matches
            }
            
            # Write results
            output_path = Path("c:/FootballIntelligence/.agents/tasks/shot-market-validation/results.json")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w') as f:
                json.dump(results_output, f, indent=2)
            
            print(f"Results written to: {output_path}")
            return
        
        # Format results for output
        variants_output = []
        
        variant_data = {
            "variant_name": full_results.variant_name,
            "thresholds": {}
        }
        
        for threshold, metrics in sorted(full_results.thresholds.items()):
            variant_data["thresholds"][threshold] = {
                "sample_size": metrics.sample_size,
                "brier_score": round(metrics.brier_score, 4) if metrics.brier_score else None,
                "log_loss": round(metrics.log_loss, 4) if metrics.log_loss else None,
                "hit_rate": round(metrics.hit_rate, 4) if metrics.hit_rate else None,
                "calibration_error": round(metrics.calibration_error, 4) if metrics.calibration_error else None,
                "mean_probability": round(metrics.mean_probability, 4) if metrics.mean_probability else None,
                "mean_actual": round(metrics.mean_actual, 4) if metrics.mean_actual else None
            }
        
        variants_output.append(variant_data)
        
        # Print summary
        print("\n" + "=" * 80)
        print("VALIDATION RESULTS")
        print("=" * 80)
        print()
        print(f"Variant: {full_results.variant_name}")
        print()
        
        for threshold in sorted(full_results.thresholds.keys()):
            metrics = full_results.thresholds[threshold]
            print(f"  Threshold {threshold}+ shots:")
            print(f"    Sample Size:        {metrics.sample_size}")
            print(f"    Brier Score:        {metrics.brier_score:.4f}" if metrics.brier_score else "    Brier Score:        N/A")
            print(f"    Log Loss:           {metrics.log_loss:.4f}" if metrics.log_loss else "    Log Loss:           N/A")
            print(f"    Hit Rate:           {metrics.hit_rate:.4f}" if metrics.hit_rate else "    Hit Rate:           N/A")
            print(f"    Calibration Error:  {metrics.calibration_error:.4f}" if metrics.calibration_error else "    Calibration Error:  N/A")
            print(f"    Mean Probability:   {metrics.mean_probability:.4f}" if metrics.mean_probability else "    Mean Probability:   N/A")
            print(f"    Mean Actual:        {metrics.mean_actual:.4f}" if metrics.mean_actual else "    Mean Actual:        N/A")
            print()
        
        # Create summary
        summary = {
            "status": "completed",
            "best_variant": full_results.variant_name,
            "total_thresholds_evaluated": len(full_results.thresholds)
        }
        
        # Write results
        results_output = {
            "variants": variants_output,
            "summary": summary
        }
        
        output_path = Path("c:/FootballIntelligence/.agents/tasks/shot-market-validation/results.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(results_output, f, indent=2)
        
        print("=" * 80)
        print(f"Results written to: {output_path}")
        print("=" * 80)
        
    finally:
        session.close()


if __name__ == "__main__":
    main()
