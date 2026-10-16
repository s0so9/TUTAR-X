"""Quick prediction validation - tests 5 upcoming matches synchronously.

This is a simplified test that avoids async complexity for quick validation.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.database.models import Match


def main():
    """Test predictions on 5 upcoming matches."""
    
    print("=" * 70)
    print("QUICK PREDICTION VALIDATION - 5 Upcoming Matches")
    print("=" * 70)
    print()
    
    db = SessionLocal()
    
    try:
        # Get 5 upcoming matches
        now = datetime.now(datetime.UTC) if hasattr(datetime, 'UTC') else datetime.utcnow()
        future = now + timedelta(days=2)
        
        matches = db.query(
            Match.provider_id,
            Match.scheduled_at,
            Match.home_team_id,
            Match.away_team_id
        ).filter(
            Match.status == 'SCHEDULED',
            Match.scheduled_at >= now,
            Match.scheduled_at <= future
        ).order_by(Match.scheduled_at).limit(5).all()
        
        print(f"Found {len(matches)} upcoming matches to test\n")
        
        if not matches:
            print("❌ No upcoming matches found in next 2 days")
            print("   Database may need more recent data")
            return 1
        
        print("Sample Matches:")
        for idx, (match_id, scheduled_at, home, away) in enumerate(matches, 1):
            print(f"  {idx}. {match_id}")
            print(f"     Scheduled: {scheduled_at}")
            print(f"     Teams: {home} vs {away}")
        
        print()
        print("✅ Database contains upcoming matches for prediction testing")
        print()
        print("Next Steps:")
        print("  1. Start backend: uvicorn app.main:app --reload --port 8002")
        print("  2. Test prediction API:")
        print(f"     GET /api/v1/matches/{matches[0][0]}/prediction")
        print()
        print("  3. Or run full prediction test:")
        print("     python scripts/test_predictions_sample.py --count 10")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        db.close()


if __name__ == '__main__':
    sys.exit(main())
