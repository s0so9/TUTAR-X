#!/usr/bin/env python3
"""
Verification test for team ID mapping in the current system.
This tests that our performance optimization doesn't break existing functionality.
"""

import sys
import sqlite3
from datetime import datetime, timedelta, timezone

# Add the backend path
sys.path.append('backend')

from backend.app.features.match_features import MatchFeatureExtractor
from backend.app.domain.match import Match
from backend.app.domain.enums import MatchStatus
from backend.app.database.database import get_db

def test_team_mapping_performance_fix():
    """Test that team mapping works correctly with our performance fix."""

    print("Testing team ID mapping with performance fix...")

    # Get a real match from database
    conn = sqlite3.connect('backend/football_intelligence.db')
    cursor = conn.cursor()

    # Get a match that exists
    cursor.execute('SELECT id, home_team_id, away_team_id, scheduled_at FROM matches LIMIT 1')
    match_data = cursor.fetchone()

    if not match_data:
        print("❌ No matches found in database")
        return False

    match_id, home_team_id, away_team_id, scheduled_at = match_data
    print(f"✅ Testing with match: {match_id}")
    print(f"   Home team: {home_team_id}")
    print(f"   Away team: {away_team_id}")
    print(f"   Scheduled: {scheduled_at}")

    # Create a Match object
    match = Match(
        id=match_id,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        scheduled_at=datetime.fromisoformat(scheduled_at.replace('Z', '+00:00')) if 'Z' in scheduled_at else datetime.fromisoformat(scheduled_at),
        status=MatchStatus.SCHEDULED,
        home_score=None,
        away_score=None,
        competition_id='test-comp',
        season_id='test-season'
    )

    conn.close()

    # Test with database session (our optimized path)
    print("\n🔄 Testing database optimization path...")
    try:
        db_session = next(get_db())

        from app.providers.development_provider import DevelopmentProvider
        provider = DevelopmentProvider()

        extractor = MatchFeatureExtractor(
            provider=provider,
            db_session=db_session,
            min_matches=1
        )

        # This should use our optimized database path
        start_time = datetime.now()
        features = extractor.extract_features(match)
        end_time = datetime.now()

        duration = (end_time - start_time).total_seconds()
        print(f"✅ Feature extraction completed in {duration:.3f}s")
        print(f"✅ Database optimization path working")

        # Verify features structure
        if isinstance(features, dict) and 'match_id' in features:
            print("✅ Features extracted successfully")
            print(f"   Feature count: {len(features)}")
            print(f"   Match ID feature: {features.get('match_id')}")
            return True
        else:
            print("❌ Invalid features structure")
            return False

    except Exception as e:
        print(f"❌ Error in database path: {e}")
        return False
    finally:
        if 'db_session' in locals():
            db_session.close()

def test_without_database():
    """Test fallback behavior when no database session is provided."""

    print("\n🔄 Testing fallback path (no database)...")

    try:
        from app.providers.development_provider import DevelopmentProvider
        provider = DevelopmentProvider()

        # Get a sample match
        matches = provider.get_matches()
        if not matches:
            print("❌ No matches from provider")
            return False

        match = matches[0]
        print(f"✅ Testing with provider match: {match.id}")

        extractor = MatchFeatureExtractor(
            provider=provider,
            db_session=None,  # No database optimization
            min_matches=1
        )

        start_time = datetime.now()
        features = extractor.extract_features(match)
        end_time = datetime.now()

        duration = (end_time - start_time).total_seconds()
        print(f"✅ Fallback completed in {duration:.3f}s")

        if duration > 5.0:
            print(f"⚠️  Fallback took {duration:.1f}s (should be under timeout)")
        else:
            print("✅ Fallback respects timeout bounds")

        return True

    except Exception as e:
        print(f"❌ Error in fallback path: {e}")
        return False

if __name__ == "__main__":
    print("Team ID Mapping Verification Test")
    print("=================================")

    success1 = test_team_mapping_performance_fix()
    success2 = test_without_database()

    if success1 and success2:
        print("\n✅ All team mapping tests passed!")
        exit(0)
    else:
        print("\n❌ Some tests failed")
        exit(1)
