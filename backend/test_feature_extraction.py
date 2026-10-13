#!/usr/bin/env python3
"""Test feature extraction with fallback."""

import sys
sys.path.append('.')

from app.database import SessionLocal
from app.providers.hybrid_provider import HybridProvider
from app.features.match_features import MatchFeatureExtractor
from app.config import settings

def test_feature_extraction():
    """Test feature extraction."""
    match_id = "a57adb1d-c6f8-404f-b085-98bfc584e3ee"

    print(f"\n=== TESTING FEATURE EXTRACTION ===")
    print(f"Match ID: {match_id}")

    session = SessionLocal()
    try:
        provider = HybridProvider(settings, session)
        match = provider.get_match(match_id)

        extractor = MatchFeatureExtractor(
            provider=provider,
            min_matches=1,
            recent_matches=5
        )

        features = extractor.extract_features(match)

        print(f"\nCritical features:")
        critical = [
            "home_goals_scored_avg",
            "away_goals_scored_avg",
            "home_goals_conceded_avg",
            "away_goals_conceded_avg",
            "home_attack_strength",
            "away_attack_strength",
            "home_defense_strength",
            "away_defense_strength"
        ]

        for key in critical:
            value = features.get(key)
            print(f"  {key}: {value}")

        print(f"\nAll feature keys with non-None values:")
        non_none = {k: v for k, v in features.items() if v is not None}
        print(f"  Count: {len(non_none)}")
        for k, v in list(non_none.items())[:10]:
            print(f"  {k}: {v}")

    finally:
        session.close()

    print(f"\n=== TEST COMPLETE ===")

if __name__ == "__main__":
    test_feature_extraction()
