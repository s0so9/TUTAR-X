"""Historical data coverage inspection script.

Inspects the real database for shot coverage, xG coverage, date ranges, and competition
distribution. This establishes the data foundation for shot market engine implementation.

Usage:
    python scripts/inspect_historical_coverage.py
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.database.models import Match, MatchStatistic
from sqlalchemy import func, and_


def inspect_coverage():
    """Inspect historical data coverage for shot intelligence."""
    
    db = SessionLocal()
    
    try:
        print("=" * 70)
        print("HISTORICAL DATA COVERAGE INSPECTION")
        print("Shot Intelligence Foundation")
        print("=" * 70)
        print()
        
        # === FINISHED MATCHES ===
        print("FINISHED MATCHES")
        print("-" * 70)
        
        total_finished = db.query(func.count(Match.id)).filter(
            Match.status == 'FINISHED'
        ).scalar()
        
        if total_finished == 0:
            print("❌ INSUFFICIENT_HISTORICAL_SAMPLE")
            print("   No finished matches found in database.")
            print()
            return
        
        print(f"Total Finished Matches: {total_finished:,}")
        print()
        
        # === SHOT COVERAGE ===
        print("SHOT DATA COVERAGE")
        print("-" * 70)
        
        # Count finished matches with shot statistics
        finished_match_ids = db.query(Match.id).filter(Match.status == 'FINISHED').all()
        finished_match_ids = [m[0] for m in finished_match_ids]
        
        # Count statistics records for finished matches
        stats_for_finished = db.query(func.count(MatchStatistic.id)).filter(
            MatchStatistic.match_id.in_(finished_match_ids)
        ).scalar()
        
        # Shots total coverage
        with_shots_total = db.query(func.count(MatchStatistic.id)).filter(
            MatchStatistic.match_id.in_(finished_match_ids),
            MatchStatistic.shots_total.isnot(None)
        ).scalar()
        
        # Shots on target coverage
        with_sot = db.query(func.count(MatchStatistic.id)).filter(
            MatchStatistic.match_id.in_(finished_match_ids),
            MatchStatistic.shots_on_target.isnot(None)
        ).scalar()
        
        # xG coverage
        with_xg = db.query(func.count(MatchStatistic.id)).filter(
            MatchStatistic.match_id.in_(finished_match_ids),
            MatchStatistic.xg.isnot(None)
        ).scalar()
        
        # Unique matches with shot data
        unique_matches_with_shots = db.query(func.count(func.distinct(MatchStatistic.match_id))).filter(
            MatchStatistic.match_id.in_(finished_match_ids),
            MatchStatistic.shots_total.isnot(None)
        ).scalar()
        
        unique_matches_with_sot = db.query(func.count(func.distinct(MatchStatistic.match_id))).filter(
            MatchStatistic.match_id.in_(finished_match_ids),
            MatchStatistic.shots_on_target.isnot(None)
        ).scalar()
        
        unique_matches_with_xg = db.query(func.count(func.distinct(MatchStatistic.match_id))).filter(
            MatchStatistic.match_id.in_(finished_match_ids),
            MatchStatistic.xg.isnot(None)
        ).scalar()
        
        print(f"Statistics Records (Finished Matches): {stats_for_finished:,}")
        print()
        print("Coverage by Metric:")
        print(f"├─ Shots Total:        {with_shots_total:,} records ({_pct(with_shots_total, stats_for_finished)})")
        print(f"│  └─ Unique Matches:  {unique_matches_with_shots:,} ({_pct(unique_matches_with_shots, total_finished)})")
        print(f"├─ Shots on Target:    {with_sot:,} records ({_pct(with_sot, stats_for_finished)})")
        print(f"│  └─ Unique Matches:  {unique_matches_with_sot:,} ({_pct(unique_matches_with_sot, total_finished)})")
        print(f"└─ xG:                 {with_xg:,} records ({_pct(with_xg, stats_for_finished)})")
        print(f"   └─ Unique Matches:  {unique_matches_with_xg:,} ({_pct(unique_matches_with_xg, total_finished)})")
        print()
        
        # === DATE RANGE ===
        print("DATE RANGE")
        print("-" * 70)
        
        earliest = db.query(func.min(Match.scheduled_at)).filter(
            Match.status == 'FINISHED'
        ).scalar()
        latest = db.query(func.max(Match.scheduled_at)).filter(
            Match.status == 'FINISHED'
        ).scalar()
        
        print(f"Earliest Finished Match: {earliest}")
        print(f"Latest Finished Match:   {latest}")
        
        if earliest and latest:
            days = (latest - earliest).days
            print(f"Total Days Covered:      {days:,}")
        print()
        
        # === COMPETITION DISTRIBUTION ===
        print("COMPETITION DISTRIBUTION")
        print("-" * 70)
        
        comp_counts = db.query(
            Match.competition_id,
            func.count(Match.id).label('match_count')
        ).filter(
            Match.status == 'FINISHED'
        ).group_by(
            Match.competition_id
        ).order_by(
            func.count(Match.id).desc()
        ).limit(10).all()
        
        if comp_counts:
            print("Top 10 Competitions by Finished Matches:")
            for comp_id, count in comp_counts:
                comp_name = comp_id if comp_id else "Unknown"
                print(f"  {comp_name:40s} {count:,}")
        else:
            print("  [No competition data available]")
        print()
        
        # === SHOT MARKET READINESS ===
        print("SHOT MARKET ENGINE READINESS")
        print("-" * 70)
        
        # Check for sufficient sample
        shot_market_ready_matches = unique_matches_with_shots
        
        print(f"Matches with Shot Data:  {shot_market_ready_matches:,}")
        
        if shot_market_ready_matches >= 500:
            print("✅ SUFFICIENT shot data for shot market engine")
        elif shot_market_ready_matches >= 200:
            print("⚠️  MODERATE shot data - shot market possible but limited")
        elif shot_market_ready_matches >= 50:
            print("⚠️  MINIMAL shot data - shot market will have high uncertainty")
        else:
            print("❌ INSUFFICIENT_HISTORICAL_SAMPLE")
            print("   Need at least 50 matches with shot data for shot markets")
        print()
        
        print("=" * 70)
        print("INSPECTION COMPLETE")
        print("=" * 70)
        
        return {
            'total_finished': total_finished,
            'unique_matches_with_shots': unique_matches_with_shots,
            'unique_matches_with_sot': unique_matches_with_sot,
            'unique_matches_with_xg': unique_matches_with_xg,
            'shot_coverage_pct': _pct_value(unique_matches_with_shots, total_finished),
            'sot_coverage_pct': _pct_value(unique_matches_with_sot, total_finished),
            'xg_coverage_pct': _pct_value(unique_matches_with_xg, total_finished),
            'earliest': earliest,
            'latest': latest
        }
    
    finally:
        db.close()


def _pct(count: int, total: int) -> str:
    """Format percentage."""
    if total == 0:
        return "0.0%"
    return f"{100.0 * count / total:.1f}%"


def _pct_value(count: int, total: int) -> float:
    """Calculate percentage as float."""
    if total == 0:
        return 0.0
    return 100.0 * count / total


if __name__ == '__main__':
    try:
        result = inspect_coverage()
        sys.exit(0)
    except Exception as e:
        print(f"\nInspection failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
