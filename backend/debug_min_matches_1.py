#!/usr/bin/env python3
"""Debug strength calculation with min_matches=1."""

import sys
sys.path.append('.')

from app.database import SessionLocal
from app.database.models import Match
from app.features.match_features import MatchFeatureExtractor
from app.providers.hybrid_provider import HybridProvider
from app.config import settings

def debug_min_matches_1():
    """Debug with min_matches=1."""
    match_id = "a57adb1d-c6f8-404f-b085-98bfc584e3ee"

    print(f"\n=== DEBUGGING WITH MIN_MATCHES=1 ===")
    print(f"Match ID: {match_id}")

    session = SessionLocal()
    try:
        match_db = session.query(Match).filter(Match.id == match_id).first()
        provider = HybridProvider(settings, session)
        match = provider.get_match(match_id)

        # Initialize with min_matches=1
        extractor = MatchFeatureExtractor(
            provider=provider,
            min_matches=1,
            recent_matches=5
        )

        # Extract features
        features = extractor.extract_features(match)

        print(f"\nFeature extraction results (min_matches=1):")
        required_features = ["home_goals_scored_avg", "away_goals_scored_avg", "home_goals_conceded_avg", "away_goals_conceded_avg"]
        for feature in required_features:
            value = features.get(feature)
            print(f"  {feature}: {value}")

        # Check historical data counts
        context = extractor._build_match_context(match)
        home_finished = context.home_team_history.get_finished_matches()
        away_finished = context.away_team_history.get_finished_matches()

        print(f"\nHistorical data (with min_matches=1):")
        print(f"  Home team finished matches: {len(home_finished)}")
        print(f"  Away team finished matches: {len(away_finished)}")
        print(f"  Min matches required: {extractor.strength_calculator.min_matches}")

        # Check if strength calculator is working
        from app.features.team_strength import TeamStrengthCalculator
        calculator = TeamStrengthCalculator(min_matches=1)

        home_strength = calculator.calculate(home_finished)
        away_strength = calculator.calculate(away_finished)

        print(f"\nTeam strength results:")
        print(f"  Home strength: {home_strength}")
        print(f"  Away strength: {away_strength}")

    finally:
        session.close()

    print(f"\n=== DEBUG COMPLETE ===")

if __name__ == "__main__":
    debug_min_matches_1()
