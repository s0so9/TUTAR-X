#!/usr/bin/env python3
"""Baseline model evaluation script for Phase 10.3.

This script runs baseline evaluation of the current 4-model production system
and outputs structured metrics in JSON format.

FEAT-001 requirement: Produces JSON report with per-model and ensemble metrics
using current production configuration. Handles insufficient samples with
explicit INSUFFICIENT_HISTORICAL_SAMPLE reporting.
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime
from typing import List

# Add backend to path for imports
backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root))

from app.database.session import SessionLocal
from app.database.models import Match
from app.domain.enums import MatchStatus
from app.prediction.baseline_evaluator import BaselineProductionEvaluator
from app.prediction.dataset_validator import DatasetValidator, ValidationLevel
from sqlalchemy import and_


def load_historical_matches(session) -> List[Match]:
    """Load historical matches from database.
    
    Args:
        session: Database session
        
    Returns:
        List of Match objects
    """
    print("Loading historical matches from database...")
    
    # Query for all matches (will be filtered by validator)
    matches = session.query(Match).all()
    
    print(f"Loaded {len(matches)} total matches from database")
    
    return matches


def run_baseline_evaluation(matches: List[Match], session) -> dict:
    """Run baseline evaluation and return results as dictionary.
    
    Args:
        matches: List of historical matches
        session: Database session
        
    Returns:
        Dictionary with evaluation results
    """
    print("Initializing baseline production evaluator...")
    
    # Initialize evaluator
    evaluator = BaselineProductionEvaluator(session=session)
    
    # Run evaluation
    result = evaluator.evaluate_baseline_system(matches)
    
    return result.to_dict()


def print_summary_report(results: dict) -> None:
    """Print human-readable summary of evaluation results.
    
    Args:
        results: Evaluation results dictionary
    """
    print("\n" + "=" * 60)
    print("BASELINE MODEL EVALUATION SUMMARY")
    print("=" * 60)
    
    # Dataset summary
    dataset = results.get("dataset_summary", {})
    print(f"\nDataset Summary:")
    print(f"Total matches: {dataset.get('total_matches', 0):,}")
    print(f"Eligible matches: {dataset.get('eligible_matches', 0):,}")
    print(f"Excluded matches: {dataset.get('excluded_matches', 0):,}")
    print(f"Sufficient data: {'Yes' if dataset.get('is_sufficient', False) else 'No'}")
    
    # Model status summary
    print(f"\nModel Status Summary:")
    print(f"Operational models: {results.get('operational_models_count', 0)}/{results.get('total_models_count', 0)}")
    print(f"Production ready: {'Yes' if results.get('is_production_ready', False) else 'No'}")
    
    # Individual model results
    model_metrics = results.get("model_metrics", {})
    operational_models = []
    
    print(f"\nIndividual Model Performance:")
    for model_id, metrics in model_metrics.items():
        status = metrics.get("status", "unknown")
        sample_size = metrics.get("sample_size", 0)
        accuracy = metrics.get("accuracy")
        brier_score = metrics.get("brier_score")
        
        print(f"  {model_id}:")
        print(f"    Status: {status}")
        print(f"    Sample size: {sample_size}")
        
        if status == "operational":
            operational_models.append(model_id)
            
            if metrics.get("is_sufficient_sample", False):
                print(f"    Accuracy: {accuracy:.3f}" if accuracy else "    Accuracy: N/A")
                print(f"    Brier Score: {brier_score:.3f}" if brier_score else "    Brier Score: N/A")
            else:
                print(f"    Performance: INSUFFICIENT_HISTORICAL_SAMPLE")
    
    # Ensemble results
    ensemble = results.get("ensemble_metrics")
    if ensemble:
        print(f"\nEnsemble Performance:")
        print(f"  Strategy: {ensemble.get('weighting_strategy', 'Unknown')}")
        print(f"  Sample size: {ensemble.get('sample_size', 0)}")
        print(f"  Avg models participating: {ensemble.get('avg_models_participating', 0.0):.1f}")
        
        if ensemble.get("is_sufficient_sample", False):
            accuracy = ensemble.get("accuracy")
            brier_score = ensemble.get("brier_score")
            agreement = ensemble.get("avg_model_agreement", 0.0)
            
            print(f"  Accuracy: {accuracy:.3f}" if accuracy else "  Accuracy: N/A")
            print(f"  Brier Score: {brier_score:.3f}" if brier_score else "  Brier Score: N/A")
            print(f"  Avg Agreement: {agreement:.3f}")
        else:
            print(f"  Performance: INSUFFICIENT_HISTORICAL_SAMPLE")
    else:
        print(f"\nEnsemble Performance: Not evaluated (insufficient operational models)")
    
    # Issues and warnings
    issues = results.get("issues", [])
    warnings_list = results.get("warnings", [])
    
    if issues:
        print(f"\nIssues Found:")
        for issue in issues:
            print(f"  ✗ {issue}")
    
    if warnings_list:
        print(f"\nWarnings:")
        for warning in warnings_list:
            print(f"  ⚠ {warning}")
    
    print(f"\nEvaluation completed at: {results.get('evaluation_timestamp', 'Unknown')}")


def save_detailed_results(results: dict, output_file: Path) -> None:
    """Save detailed results to JSON file.
    
    Args:
        results: Evaluation results dictionary
        output_file: Path to output JSON file
    """
    print(f"\nSaving detailed results to: {output_file}")
    
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"Detailed results saved successfully")


def validate_results(results: dict) -> bool:
    """Validate that results contain expected structure.
    
    Args:
        results: Results dictionary to validate
        
    Returns:
        True if results are valid, False otherwise
    """
    required_keys = [
        "evaluation_timestamp",
        "dataset_summary", 
        "model_metrics",
        "operational_models_count",
        "total_models_count"
    ]
    
    for key in required_keys:
        if key not in results:
            print(f"ERROR: Missing required key in results: {key}")
            return False
    
    # Check model metrics structure
    model_metrics = results.get("model_metrics", {})
    expected_models = [
        "poisson_v1",
        "dixon_coles_v1", 
        "negative_binomial_v1",
        "form_adjusted_v1",
        "monte_carlo_v1",
        "elo_v1",
        "logistic_regression_v1"
    ]
    
    operational_count = 0
    for model_id in expected_models:
        if model_id not in model_metrics:
            print(f"WARNING: Expected model not found in results: {model_id}")
        else:
            metrics = model_metrics[model_id]
            if metrics.get("status") == "operational":
                operational_count += 1
    
    # Verify operational count matches
    reported_count = results.get("operational_models_count", 0)
    if operational_count != reported_count:
        print(f"WARNING: Operational model count mismatch: found {operational_count}, reported {reported_count}")
    
    return True


def main():
    """Main function."""
    try:
        print("Starting baseline model evaluation...")
        
        # Get database session
        session = SessionLocal()
        
        # Load historical matches
        matches = load_historical_matches(session)
        
        if not matches:
            print("ERROR: No matches found in database")
            return 1
        
        # Run evaluation
        results = run_baseline_evaluation(matches, session)
        
        # Validate results structure
        if not validate_results(results):
            print("ERROR: Results validation failed")
            return 1
        
        # Print summary
        print_summary_report(results)
        
        # Save detailed results
        output_file = backend_root / "baseline_metrics.json"
        save_detailed_results(results, output_file)
        
        # Check if evaluation was successful
        if results.get("operational_models_count", 0) >= 4:
            print("\n✓ Baseline evaluation completed successfully")
            print("✓ 4/7 models operational status confirmed")
            return 0
        else:
            print(f"\n⚠ Baseline evaluation completed with issues")
            print(f"⚠ Only {results.get('operational_models_count', 0)}/7 models operational")
            return 0
        
    except Exception as e:
        print(f"ERROR: Baseline evaluation failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        if 'session' in locals():
            session.close()


if __name__ == "__main__":
    exit(main())