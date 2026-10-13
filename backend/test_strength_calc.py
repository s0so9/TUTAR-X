#!/usr/bin/env python3
"""Test strength calculator output for a real match."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.database.session import SessionLocal
from app.database.models import Match as DBMatch, MatchStatus
from app.domain.match import Match as DomainMatch
from app.features.match_features import MatchFeatureExtractor

def db_to_domain_match(match_db: DBMatch) -> DomainMatch:
    """Convert DB model to domain model."""
    return DomainMatch(
        id=match_db.id,
        home_team_id=match_db.home_team_id,
        away_team_id=match_db.away_team_id,
        competition_id=match_db.competition_id or "unknown",
        season_id=match_db.season or "unknown",
        scheduled_at=match_db.scheduled_at,
        status=match_db.status,
        home_score=match_db.home_score,
        away_score=match_db.away_score,
        home_score_ht=match_db.home_score_ht,
        away_score_ht=match_db.away_score_ht,
        outcome=match_db.outcome,
        round=match_db.round,
        created_at=match_db.created_at,
        updated_at=match_db.updated_at,
    )

def test_strength_calculation():
    """Test strength metrics for a real match."""
    db = SessionLocal()

    try:
        # Get a match with historical data (50th from latest finished matches)
        matches = db.query(DBMatch).filter(
            DBMatch.status == MatchStatus.FINISHED
        ).order_by(DBMatch.scheduled_at.desc()).limit(100).all()

        if len(matches) < 51:
            print("ERROR: Not enough matches in database")
            return

        match_db = matches[50]

        # Convert to domain model
        match = db_to_domain_match(match_db)

        print(f"Testing match: {match.id}")
        print(f"Home: {match.home_team_id}")
        print(f"Away: {match.away_team_id}")
        print(f"Scheduled: {match.scheduled_at}")
        print()

        # Extract features
        from app.providers.development import DevelopmentProvider
        provider = DevelopmentProvider()

        extractor = MatchFeatureExtractor(
            provider=provider,
            min_matches=1,  # Same as production
            recent_matches=5,
            db_session=db  # CRITICAL: Pass db_session!
        )
        features = extractor.extract_features(match)

        # Check strength metrics
        print("=== STRENGTH METRICS ===")
        strength_keys = [
            "home_attack_strength",
            "home_defense_strength",
            "away_attack_strength",
            "away_defense_strength"
        ]

        for key in strength_keys:
            value = features.get(key)
            print(f"{key}: {value}")

        print()
        print("=== EXPECTED GOALS ===")
        xg_keys = ["home_expected_goals", "away_expected_goals"]
        for key in xg_keys:
            value = features.get(key)
            print(f"{key}: {value}")

        print()
        print("=== ELO FEATURES ===")
        elo_keys = ["elo_home", "elo_away"]
        for key in elo_keys:
            value = features.get(key)
            print(f"{key}: {value}")

        print()
        print("=== LOGISTIC REGRESSION FEATURES (16) ===")
        lr_keys = [
            "home_attack_strength", "home_defense_strength",
            "home_home_strength", "home_away_strength",
            "home_recent_wins", "home_recent_draws", "home_recent_losses",
            "home_form_points_per_match",
            "away_attack_strength", "away_defense_strength",
            "away_home_strength", "away_away_strength",
            "away_recent_wins", "away_recent_draws", "away_recent_losses",
            "away_form_points_per_match"
        ]

        available = 0
        missing = []
        for key in lr_keys:
            value = features.get(key)
            if value is not None:
                available += 1
                print(f"✓ {key}: {value}")
            else:
                missing.append(key)
                print(f"✗ {key}: None")

        print()
        print(f"Logistic Regression: {available}/16 features available")
        if missing:
            print(f"Missing: {', '.join(missing)}")

    finally:
        db.close()

if __name__ == "__main__":
    test_strength_calculation()
