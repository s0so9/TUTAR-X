"""Data coverage validation script.

Validates database state after imports and prepares for walk-forward validation.

Usage:
    python scripts/validate_data_coverage.py
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.database.models import Match, MatchStatistic, Team
from sqlalchemy import func, and_, or_


def validate_coverage():
    """Validate data coverage and report statistics."""
    
    db = SessionLocal()
    
    print("=" * 70)
    print("DATA COVERAGE VALIDATION REPORT")
    print("=" * 70)
    print()
    
    # === MATCH COUNTS ===
    print("MATCH COUNTS")
    print("-" * 70)
    
    total_matches = db.query(func.count(Match.id)).scalar()
    finished_matches = db.query(func.count(Match.id)).filter(Match.status == 'FINISHED').scalar()
    scheduled_matches = db.query(func.count(Match.id)).filter(Match.status == 'SCHEDULED').scalar()
    live_matches = db.query(func.count(Match.id)).filter(Match.status == 'LIVE').scalar()
    cancelled_matches = db.query(func.count(Match.id)).filter(Match.status == 'CANCELLED').scalar()
    postponed_matches = db.query(func.count(Match.id)).filter(Match.status == 'POSTPONED').scalar()
    
    print(f"Total Matches:      {total_matches:,}")
    print(f"├─ Finished:        {finished_matches:,}")
    print(f"├─ Scheduled:       {scheduled_matches:,}")
    print(f"├─ Live:            {live_matches:,}")
    print(f"├─ Cancelled:       {cancelled_matches:,}")
    print(f"└─ Postponed:       {postponed_matches:,}")
    print()
    
    # === STATISTICS COVERAGE ===
    print("STATISTICS COVERAGE")
    print("-" * 70)
    
    total_stats = db.query(func.count(MatchStatistic.id)).scalar()
    unique_matches_with_stats = db.query(func.count(func.distinct(MatchStatistic.match_id))).scalar()
    
    with_shots = db.query(func.count(MatchStatistic.id)).filter(
        MatchStatistic.shots_total.isnot(None)
    ).scalar()
    
    with_sot = db.query(func.count(MatchStatistic.id)).filter(
        MatchStatistic.shots_on_target.isnot(None)
    ).scalar()
    
    with_xg = db.query(func.count(MatchStatistic.id)).filter(
        MatchStatistic.xg.isnot(None)
    ).scalar()
    
    with_possession = db.query(func.count(MatchStatistic.id)).filter(
        MatchStatistic.possession_percentage.isnot(None)
    ).scalar()
    
    with_passes = db.query(func.count(MatchStatistic.id)).filter(
        MatchStatistic.passes_attempted.isnot(None)
    ).scalar()
    
    with_corners = db.query(func.count(MatchStatistic.id)).filter(
        MatchStatistic.corners.isnot(None)
    ).scalar()
    
    with_cards = db.query(func.count(MatchStatistic.id)).filter(
        or_(MatchStatistic.yellow_cards.isnot(None), MatchStatistic.red_cards.isnot(None))
    ).scalar()
    
    print(f"Total Statistics Records:  {total_stats:,}")
    print(f"Matches with Statistics:   {unique_matches_with_stats:,}")
    print()
    print("Coverage by Metric:")
    print(f"├─ Shots:                  {with_shots:,} ({_pct(with_shots, total_stats)})")
    print(f"├─ Shots on Target:        {with_sot:,} ({_pct(with_sot, total_stats)})")
    print(f"├─ xG:                     {with_xg:,} ({_pct(with_xg, total_stats)})")
    print(f"├─ Possession:             {with_possession:,} ({_pct(with_possession, total_stats)})")
    print(f"├─ Passes:                 {with_passes:,} ({_pct(with_passes, total_stats)})")
    print(f"├─ Corners:                {with_corners:,} ({_pct(with_corners, total_stats)})")
    print(f"└─ Cards:                  {with_cards:,} ({_pct(with_cards, total_stats)})")
    print()
    
    # === DATE RANGES ===
    print("DATE COVERAGE")
    print("-" * 70)
    
    overall_earliest = db.query(func.min(Match.scheduled_at)).scalar()
    overall_latest = db.query(func.max(Match.scheduled_at)).scalar()
    
    finished_earliest = db.query(func.min(Match.scheduled_at)).filter(
        Match.status == 'FINISHED'
    ).scalar()
    finished_latest = db.query(func.max(Match.scheduled_at)).filter(
        Match.status == 'FINISHED'
    ).scalar()
    
    scheduled_earliest = db.query(func.min(Match.scheduled_at)).filter(
        Match.status == 'SCHEDULED'
    ).scalar()
    scheduled_latest = db.query(func.max(Match.scheduled_at)).filter(
        Match.status == 'SCHEDULED'
    ).scalar()
    
    print(f"Overall Range:")
    print(f"└─ {overall_earliest} to {overall_latest}")
    print()
    print(f"Finished Matches:")
    print(f"└─ {finished_earliest} to {finished_latest}")
    print()
    print(f"Scheduled Matches:")
    print(f"└─ {scheduled_earliest} to {scheduled_latest}")
    print()
    
    # === UPCOMING MATCHES ===
    print("UPCOMING MATCHES (Next 7 Days)")
    print("-" * 70)
    
    now = datetime.utcnow()
    next_7_days = now + timedelta(days=7)
    
    upcoming_count = db.query(func.count(Match.id)).filter(
        Match.status == 'SCHEDULED',
        Match.scheduled_at >= now,
        Match.scheduled_at <= next_7_days
    ).scalar()
    
    # Get sample upcoming matches
    sample_upcoming = db.query(
        Match.provider_id,
        Match.scheduled_at
    ).filter(
        Match.status == 'SCHEDULED',
        Match.scheduled_at >= now,
        Match.scheduled_at <= next_7_days
    ).order_by(Match.scheduled_at).limit(10).all()
    
    print(f"Upcoming Matches (7 days): {upcoming_count:,}")
    print()
    if sample_upcoming:
        print("Sample (first 10):")
        for m in sample_upcoming:
            print(f"  {m.provider_id:20s} {m.scheduled_at}")
    else:
        print("  [No upcoming matches found]")
    print()
    
    # === WALK-FORWARD READINESS ===
    print("WALK-FORWARD BACKTEST READINESS")
    print("-" * 70)
    
    # Count matches with sufficient history (example: at least 10 prior matches per team)
    # This is a simplified check - actual feature engineering has more requirements
    
    matches_with_scores = db.query(func.count(Match.id)).filter(
        Match.status == 'FINISHED',
        Match.home_score.isnot(None),
        Match.away_score.isnot(None)
    ).scalar()
    
    matches_with_stats = db.query(func.count(func.distinct(MatchStatistic.match_id))).filter(
        MatchStatistic.shots_total.isnot(None)
    ).scalar()
    
    print(f"Finished Matches with Scores:     {matches_with_scores:,}")
    print(f"Finished Matches with Statistics: {matches_with_stats:,}")
    print()
    
    # Estimate eligible sample (finished + scores + stats from Sep 2024 onwards)
    sep_2024 = datetime(2024, 9, 1)
    recent_eligible = db.query(func.count(Match.id)).filter(
        Match.status == 'FINISHED',
        Match.scheduled_at >= sep_2024,
        Match.home_score.isnot(None),
        Match.away_score.isnot(None)
    ).scalar()
    
    print(f"Recent Eligible Sample (Sep 2024+): {recent_eligible:,}")
    print()
    
    if recent_eligible >= 500:
        print("✅ SUFFICIENT historical sample for walk-forward validation")
    elif recent_eligible >= 200:
        print("⚠️  MODERATE historical sample - validation possible but limited")
    else:
        print("❌ INSUFFICIENT historical sample - need more data")
    print()
    
    # === PROVIDER BREAKDOWN ===
    print("PROVIDER BREAKDOWN")
    print("-" * 70)
    
    fotmob_count = db.query(func.count(Match.id)).filter(
        Match.provider_id.like('fotmob_%')
    ).scalar()
    
    ryzellx_count = db.query(func.count(Match.id)).filter(
        Match.provider_id.like('ryzellx_%')
    ).scalar()
    
    openligadb_count = db.query(func.count(Match.id)).filter(
        Match.provider_id.like('openligadb_%')
    ).scalar()
    
    print(f"├─ FotMob:      {fotmob_count:,} ({_pct(fotmob_count, total_matches)})")
    print(f"├─ Ryzellx:     {ryzellx_count:,} ({_pct(ryzellx_count, total_matches)})")
    print(f"└─ OpenLigaDB:  {openligadb_count:,} ({_pct(openligadb_count, total_matches)})")
    print()
    
    # === TEAMS ===
    print("TEAMS")
    print("-" * 70)
    
    total_teams = db.query(func.count(Team.id)).scalar()
    print(f"Total Teams: {total_teams:,}")
    print()
    
    print("=" * 70)
    print("VALIDATION COMPLETE")
    print("=" * 70)
    
    db.close()
    
    return {
        'total_matches': total_matches,
        'finished_matches': finished_matches,
        'scheduled_matches': scheduled_matches,
        'upcoming_matches': upcoming_count,
        'matches_with_stats': unique_matches_with_stats,
        'recent_eligible': recent_eligible
    }


def _pct(count: int, total: int) -> str:
    """Format percentage."""
    if total == 0:
        return "0.0%"
    return f"{100.0 * count / total:.1f}%"


if __name__ == '__main__':
    try:
        stats = validate_coverage()
        sys.exit(0)
    except Exception as e:
        print(f"\nValidation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
