#!/usr/bin/env python3
"""Debug strength calculation for the specific match."""

import sys
sys.path.append('.')

from app.database import SessionLocal
from app.database.models import Match
from app.features.match_features import MatchFeatureExtractor
from app.providers.hybrid_provider import HybridProvider
from app.config import settings

def debug_strength_calculation():
    """Debug strength calculation."""
    match_id = "a57adb1d-c6f8-404f-b085-98bfc584e3ee"

    print(f"\n=== DEBUGGING STRENGTH CALCULATION ===")
    print(f"Match ID: {match_id}")

    session = SessionLocal()
    try:
        # Get match
        match_db = session.query(Match).filter(Match.id == match_id).first()
        if not match_db:
            print("ERROR: Match not found")
            return

        provider = HybridProvider(settings, session)
        match = provider.get_match(match_id)

        # Initialize feature extractor
        extractor = MatchFeatureExtractor(
            provider=provider,
            min_matches=3,
            recent_matches=5
        )

        # Extract features
        features = extractor.extract_features(match)

        print(f"\nFeature extraction results:")
        print(f"  home_attack_strength: {features.get('home_attack_strength')}")
        print(f"  home_defense_strength: {features.get('home_defense_strength')}")
        print(f"  home_goals_scored_avg: {features.get('home_goals_scored_avg')}")
        print(f"  home_goals_conceded_avg: {features.get('home_goals_conceded_avg')}")
        print(f"  away_attack_strength: {features.get('away_attack_strength')}")
        print(f"  away_defense_strength: {features.get('away_defense_strength')}")
        print(f"  away_goals_scored_avg: {features.get('away_goals_scored_avg')}")
        print(f"  away_goals_conceded_avg: {features.get('away_goals_conceded_avg')}")

        # Check the context that was built
        context = extractor._build_match_context(match)

        home_finished = context.home_team_history.get_finished_matches()
        away_finished = context.away_team_history.get_finished_matches()

        print(f"\nHistorical data:")
        print(f"  Home team finished matches: {len(home_finished)}")
        print(f"  Away team finished matches: {len(away_finished)}")
        print(f"  Minimum required matches: {extractor.strength_calculator.min_matches}")

        if home_finished:
            print(f"  Home team sample matches:")
            for i, m in enumerate(home_finished[:3]):
                print(f"    {i+1}. {m.home_team_id} vs {m.away_team_id} = {m.home_score}-{m.away_score} ({m.scheduled_at})")

        if away_finished:
            print(f"  Away team sample matches:")
            for i, m in enumerate(away_finished[:3]):
                print(f"    {i+1}. {m.home_team_id} vs {m.away_team_id} = {m.home_score}-{m.away_score} ({m.scheduled_at})")

    finally:
        session.close()

    print(f"\n=== DEBUG COMPLETE ===")

if __name__ == "__main__":
    debug_strength_calculation()
