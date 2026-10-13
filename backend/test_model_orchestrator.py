#!/usr/bin/env python3
"""Test model orchestrator with current features."""

import sys
sys.path.append('.')

from app.database import SessionLocal
from app.providers.hybrid_provider import HybridProvider
from app.features.match_features import MatchFeatureExtractor
from app.prediction.model_orchestrator import ModelOrchestrator
from app.prediction.feature_snapshot import extract_feature_snapshot
from app.config import settings

def test_model_orchestrator():
    """Test model orchestrator."""
    match_id = "a57adb1d-c6f8-404f-b085-98bfc584e3ee"

    print(f"\n=== TESTING MODEL ORCHESTRATOR ===")
    print(f"Match ID: {match_id}")

    session = SessionLocal()
    try:
        provider = HybridProvider(settings, session)
        match = provider.get_match(match_id)

        # Extract features
        extractor = MatchFeatureExtractor(
            provider=provider,
            min_matches=1,
            recent_matches=5
        )
        features = extractor.extract_features(match)

        print(f"\nKey features:")
        print(f"  home_goals_scored_avg: {features.get('home_goals_scored_avg')}")
        print(f"  away_goals_scored_avg: {features.get('away_goals_scored_avg')}")
        print(f"  home_goals_conceded_avg: {features.get('home_goals_conceded_avg')}")
        print(f"  away_goals_conceded_avg: {features.get('away_goals_conceded_avg')}")

        # Build snapshot
        from app.prediction.data_quality import DataQualityGate
        data_quality_gate = DataQualityGate()
        data_quality_report = data_quality_gate.assess(features)

        snapshot = extract_feature_snapshot(
            match_id=match.id,
            home_team_id=match.home_team_id,
            away_team_id=match.away_team_id,
            feature_set=None,
            data_quality_report=data_quality_report,
            home_team_name=None,
            away_team_name=None,
            scheduled_at=match.scheduled_at,
            market_info=None
        )

        # If snapshot has no strength metrics, populate from features
        if snapshot.home_strength is None or snapshot.away_strength is None:
            from app.prediction.feature_snapshot import TeamStrengthMetrics

            if snapshot.home_strength is None:
                snapshot.home_strength = TeamStrengthMetrics(
                    goals_scored_per_match=features.get("home_goals_scored_avg"),
                    xg_per_match=features.get("home_xg_avg"),
                    goals_conceded_per_match=features.get("home_goals_conceded_avg"),
                    xg_against_per_match=features.get("home_xg_conceded_avg"),
                    points_per_match=features.get("home_form_points_per_match"),
                    elo_rating=features.get("home_elo"),
                )

            if snapshot.away_strength is None:
                snapshot.away_strength = TeamStrengthMetrics(
                    goals_scored_per_match=features.get("away_goals_scored_avg"),
                    xg_per_match=features.get("away_xg_avg"),
                    goals_conceded_per_match=features.get("away_goals_conceded_avg"),
                    xg_against_per_match=features.get("away_xg_conceded_avg"),
                    points_per_match=features.get("away_form_points_per_match"),
                    elo_rating=features.get("away_elo"),
                )

        print(f"\nSnapshot strength metrics:")
        print(f"  home_strength.goals_scored_per_match: {snapshot.home_strength.goals_scored_per_match if snapshot.home_strength else None}")
        print(f"  away_strength.goals_scored_per_match: {snapshot.away_strength.goals_scored_per_match if snapshot.away_strength else None}")

        # Test orchestrator
        orchestrator = ModelOrchestrator.create_default_registry()
        result = orchestrator.run_all(snapshot)

        print(f"\nOrchestration result:")
        print(f"  Total models: {result.total_models}")
        print(f"  Successful: {len(result.successful_predictions)}")
        print(f"  Failed: {len(result.failed_models)}")
        print(f"  Unavailable: {len(result.unavailable_models)}")

        if result.failed_models:
            print(f"\nFailed models:")
            for failure in result.failed_models:
                print(f"  - {failure.model_name}: {failure.error_message}")

        if result.unavailable_models:
            print(f"\nUnavailable models:")
            for unavail in result.unavailable_models:
                print(f"  - {unavail.model_name}: {unavail.error_message}")

        if result.successful_predictions:
            print(f"\nSuccessful predictions:")
            for success in result.successful_predictions:
                pred = success.prediction
                print(f"  - {success.model_name}:")
                print(f"      home_win: {pred.home_win_probability:.3f}")
                print(f"      draw: {pred.draw_probability:.3f}")
                print(f"      away_win: {pred.away_win_probability:.3f}")

    finally:
        session.close()

    print(f"\n=== TEST COMPLETE ===")

if __name__ == "__main__":
    test_model_orchestrator()
