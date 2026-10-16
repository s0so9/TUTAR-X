"""Check available historical data for calibration."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.domain.match import Match
from sqlalchemy import func

def check_data():
    """Check what historical data is available."""
    db = SessionLocal()
    
    try:
        # Total matches
        total = db.query(func.count(Match.id)).scalar()
        print(f"Total matches: {total}")
        
        # Count by status
        status_counts = db.query(
            Match.status,
            func.count(Match.id)
        ).group_by(Match.status).all()
        
        print("\nMatch status distribution:")
        for status, count in status_counts:
            print(f"  {status}: {count}")
        
        # Finished matches with scores
        finished_with_scores = db.query(func.count(Match.id)).filter(
            Match.home_score.isnot(None),
            Match.away_score.isnot(None)
        ).scalar()
        
        print(f"\nFinished matches with scores: {finished_with_scores}")
        
        # Date range
        date_range = db.query(
            func.min(Match.scheduled_at),
            func.max(Match.scheduled_at)
        ).filter(
            Match.home_score.isnot(None)
        ).first()
        
        print(f"Date range: {date_range[0]} to {date_range[1]}")
        
    finally:
        db.close()

if __name__ == "__main__":
    check_data()
