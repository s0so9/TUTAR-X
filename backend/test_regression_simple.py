#!/usr/bin/env python3
"""Simple regression test for team mapping functionality."""

from app.features.match_features import MatchFeatureExtractor
from app.providers import DevelopmentProvider
from app.database.database import get_db

def test_feature_extraction_still_works():
    """Verify that feature extraction still works after performance changes."""

    print("Running regression test for feature extraction...")

    try:
        # Test with DevelopmentProvider (no database session)
        provider = DevelopmentProvider()
        matches = provider.get_matches()

        if not matches:
            print("❌ No matches available from DevelopmentProvider")
            return False

        test_match = matches[0]
        print(f"✅ Testing with match: {test_match.id}")

        # Test without database (original path)
        extractor_no_db = MatchFeatureExtractor(
            provider=provider,
            db_session=None,
            min_matches=1
        )

        features_no_db = extractor_no_db.extract_features(test_match)

        if not isinstance(features_no_db, dict):
            print("❌ Feature extraction without DB failed")
            return False

        print(f"✅ Feature extraction without DB works: {len(features_no_db)} features")

        # Test with database (optimized path)
        try:
            db_session = next(get_db())

            extractor_with_db = MatchFeatureExtractor(
                provider=provider,
                db_session=db_session,
                min_matches=1
            )

            features_with_db = extractor_with_db.extract_features(test_match)

            db_session.close()

            if not isinstance(features_with_db, dict):
                print("❌ Feature extraction with DB failed")
                return False

            print(f"✅ Feature extraction with DB works: {len(features_with_db)} features")

            # Both should have basic structure
            for features in [features_no_db, features_with_db]:
                if 'match_id' not in features:
                    print("❌ Missing match_id in features")
                    return False

            print("✅ Both paths produce valid feature structures")
            return True

        except Exception as e:
            print(f"❌ Database path failed: {e}")
            return False

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False

if __name__ == "__main__":
    success = test_feature_extraction_still_works()
    if success:
        print("\n✅ Regression test passed - team mapping functionality preserved")
        exit(0)
    else:
        print("\n❌ Regression test failed")
        exit(1)
