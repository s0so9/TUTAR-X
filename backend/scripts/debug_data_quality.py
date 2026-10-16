#!/usr/bin/env python3
"""Debug data quality checks in detail."""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime
from app.database.session import SessionLocal
from app.features.match_features import MatchFeatureExtractor
from app.prediction.data_quality import DataQualityGate
from app.providers.development import DevelopmentProvider
from app.domain.match import Match

def main():
    """Debug data quality for our test match."""
    
    with SessionLocal() as db:
        print("=== DATA QUALITY DEBUG ===")
        
        # Our test match
        match_id = "47cea9fe-85e0-4c71-9614-ab18f60ce356"
        
        # Create a minimal match object for testing
        test_match = Match(
            id=match_id,
            home_team_id="ff783ba1-5eb9-4a61-80a2-2d04ca145b1a",  # Chicago Fire FC
            away_team_id="d3d66b8f-c0dd-4ce4-a213-3bdd08a7171f",  # Vancouver Whitecaps
            competition_id="test-comp",
            season_id="test-season",
            scheduled_at=datetime(2026, 10, 7, 0, 30),
            status="SCHEDULED",
            home_score=None,
            away_score=None,
            home_score_ht=None,
            away_score_ht=None,
            outcome=None,
            round=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        
        print(f"Match: {match_id}")
        print(f"Teams: Chicago Fire FC vs Vancouver Whitecaps")
        
        # Initialize feature extractor
        provider = DevelopmentProvider()
        extractor = MatchFeatureExtractor(
            provider=provider,
            min_matches=3,  # Use config value
            recent_matches=5,
            db_session=db
        )
        
        print(f"Extractor type: {type(extractor)}")
        print(f"Extractor provider: {type(extractor.provider)}")
        
        # Extract features
        print(f"\n--- Extracting Features ---")
        features = extractor.extract_features(test_match)
        
        # Show key features
        print(f"Key features:")
        for key in ["home_match_count", "away_match_count", "home_attack_strength", "away_attack_strength"]:
            print(f"  {key}: {features.get(key)}")
            
        # Check data sufficiency
        print(f"\n--- Data Sufficiency Check ---")
        sufficiency = extractor.check_data_sufficiency(test_match)
        for key, value in sufficiency.items():
            print(f"  {key}: {value}")
        
        # Initialize data quality gate with config values
        print(f"\n--- Data Quality Gate ---")
        from app.config import settings
        print(f"Config min_sample_size: {settings.min_sample_size}")
        
        gate = DataQualityGate()
        print(f"Gate min_sample_size: {gate.min_sample_size}")
        
        # Run quality assessment
        report = gate.assess(features)
        
        print(f"\nOverall Score: {report.overall_score:.3f}")
        print(f"Passed: {report.passed}, Failed: {report.failed}")
        
        if report.warnings:
            print(f"Warnings:")
            for warning in report.warnings:
                print(f"  - {warning}")
        
        print(f"\nIndividual Checks:")
        for check in report.checks:
            status = "✅ PASS" if check.passed else "❌ FAIL"
            print(f"  {status} {check.check_name} ({check.severity}): {check.message}")
            if check.details:
                for key, value in check.details.items():
                    print(f"    {key}: {value}")

if __name__ == "__main__":
    main()