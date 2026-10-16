#!/usr/bin/env python3
"""Historical dataset census for Phase 10.3 calibration validation.

This script queries the database to document the exact state of historical match data:
- Total matches in database
- Finished matches with valid scores
- Exclusion reasons with counts
- Sample sizes per team/competition
- Data quality metrics

FEAT-001 requirement: Document exact usability without fabricating metrics.
If insufficient historical samples exist for any metric, explicitly report:
INSUFFICIENT_HISTORICAL_SAMPLE
"""

import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import json

# Add backend to path for imports
backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root))

from app.database.session import SessionLocal
from app.database.models import Match, Team, Competition, ProviderSource
from app.domain.enums import MatchStatus
from sqlalchemy import and_, func, desc


@dataclass
class TeamSample:
    """Sample size information for a team."""
    team_id: str
    team_name: str
    total_matches: int
    finished_matches: int
    home_matches: int
    away_matches: int
    usable_matches: int  # Matches that meet all criteria for prediction


@dataclass 
class CompetitionSample:
    """Sample size information for a competition."""
    competition_id: str
    competition_name: str
    total_matches: int
    finished_matches: int
    usable_matches: int
    teams_count: int
    date_range: Tuple[Optional[datetime], Optional[datetime]]


@dataclass
class ExclusionReason:
    """Reason for excluding matches from analysis."""
    reason: str
    count: int
    description: str


@dataclass
class DatasetCensus:
    """Complete dataset census results."""
    
    # High-level counts
    total_matches: int
    finished_matches: int
    usable_matches: int
    exclusion_percentage: float
    
    # Exclusions breakdown
    exclusion_reasons: List[ExclusionReason] = field(default_factory=list)
    
    # Sample distribution
    team_samples: List[TeamSample] = field(default_factory=list)
    competition_samples: List[CompetitionSample] = field(default_factory=list)
    
    # Date range
    earliest_match: Optional[datetime] = None
    latest_match: Optional[datetime] = None
    
    # Data quality indicators
    matches_with_xg: int = 0
    matches_with_lineups: int = 0  # Placeholder - not implemented yet
    matches_with_statistics: int = 0
    
    # Census metadata
    census_timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_matches": self.total_matches,
            "finished_matches": self.finished_matches,
            "usable_matches": self.usable_matches,
            "exclusion_percentage": self.exclusion_percentage,
            "exclusion_reasons": [
                {
                    "reason": er.reason,
                    "count": er.count,
                    "description": er.description
                }
                for er in self.exclusion_reasons
            ],
            "team_samples": [
                {
                    "team_id": ts.team_id,
                    "team_name": ts.team_name,
                    "total_matches": ts.total_matches,
                    "finished_matches": ts.finished_matches,
                    "home_matches": ts.home_matches,
                    "away_matches": ts.away_matches,
                    "usable_matches": ts.usable_matches
                }
                for ts in self.team_samples
            ],
            "competition_samples": [
                {
                    "competition_id": cs.competition_id,
                    "competition_name": cs.competition_name,
                    "total_matches": cs.total_matches,
                    "finished_matches": cs.finished_matches,
                    "usable_matches": cs.usable_matches,
                    "teams_count": cs.teams_count,
                    "date_range": [
                        cs.date_range[0].isoformat() if cs.date_range[0] else None,
                        cs.date_range[1].isoformat() if cs.date_range[1] else None
                    ]
                }
                for cs in self.competition_samples
            ],
            "earliest_match": self.earliest_match.isoformat() if self.earliest_match else None,
            "latest_match": self.latest_match.isoformat() if self.latest_match else None,
            "matches_with_xg": self.matches_with_xg,
            "matches_with_lineups": self.matches_with_lineups,
            "matches_with_statistics": self.matches_with_statistics,
            "census_timestamp": self.census_timestamp.isoformat()
        }


class HistoricalDatasetCensus:
    """Historical dataset census analyzer."""
    
    def __init__(self, session):
        """Initialize census analyzer.
        
        Args:
            session: Database session
        """
        self.session = session
    
    def run_full_census(self) -> DatasetCensus:
        """Run complete dataset census.
        
        Returns:
            DatasetCensus with all metrics
        """
        print("Running historical dataset census...")
        
        # Basic counts
        total_matches = self._count_total_matches()
        finished_matches = self._count_finished_matches()
        
        print(f"Total matches in database: {total_matches}")
        print(f"Finished matches: {finished_matches}")
        
        # Analyze exclusions
        exclusion_reasons = self._analyze_exclusions()
        
        # Calculate usable matches
        usable_matches = self._count_usable_matches()
        
        print(f"Usable matches (after exclusions): {usable_matches}")
        
        exclusion_percentage = 0.0
        if total_matches > 0:
            exclusion_percentage = ((total_matches - usable_matches) / total_matches) * 100
        
        print(f"Exclusion percentage: {exclusion_percentage:.1f}%")
        
        # Date range
        earliest, latest = self._get_date_range()
        
        # Team samples
        print("\nAnalyzing team samples...")
        team_samples = self._analyze_team_samples()
        
        # Competition samples  
        print("Analyzing competition samples...")
        competition_samples = self._analyze_competition_samples()
        
        # Data quality metrics
        print("Analyzing data quality...")
        matches_with_xg = self._count_matches_with_xg()
        matches_with_statistics = self._count_matches_with_statistics()
        
        census = DatasetCensus(
            total_matches=total_matches,
            finished_matches=finished_matches,
            usable_matches=usable_matches,
            exclusion_percentage=exclusion_percentage,
            exclusion_reasons=exclusion_reasons,
            team_samples=team_samples,
            competition_samples=competition_samples,
            earliest_match=earliest,
            latest_match=latest,
            matches_with_xg=matches_with_xg,
            matches_with_lineups=0,  # Not implemented yet
            matches_with_statistics=matches_with_statistics
        )
        
        return census
    
    def _count_total_matches(self) -> int:
        """Count total matches in database."""
        return self.session.query(Match).count()
    
    def _count_finished_matches(self) -> int:
        """Count finished matches."""
        return self.session.query(Match).filter(
            Match.status == MatchStatus.FINISHED
        ).count()
    
    def _analyze_exclusions(self) -> List[ExclusionReason]:
        """Analyze match exclusion reasons."""
        exclusions = []
        
        # Missing scores
        missing_scores = self.session.query(Match).filter(
            and_(
                Match.status == MatchStatus.FINISHED,
                or_(Match.home_score.is_(None), Match.away_score.is_(None))
            )
        ).count()
        
        if missing_scores > 0:
            exclusions.append(ExclusionReason(
                reason="missing_scores",
                count=missing_scores,
                description="Finished matches without valid home/away scores"
            ))
        
        # Missing teams
        missing_teams = self.session.query(Match).filter(
            or_(Match.home_team_id.is_(None), Match.away_team_id.is_(None))
        ).count()
        
        if missing_teams > 0:
            exclusions.append(ExclusionReason(
                reason="missing_teams",
                count=missing_teams,
                description="Matches without valid home/away team references"
            ))
        
        # Scheduled but not finished
        scheduled_not_finished = self.session.query(Match).filter(
            Match.status != MatchStatus.FINISHED
        ).count()
        
        if scheduled_not_finished > 0:
            exclusions.append(ExclusionReason(
                reason="not_finished",
                count=scheduled_not_finished,
                description="Matches that are scheduled but not yet finished"
            ))
        
        # Missing scheduled_at
        missing_scheduled = self.session.query(Match).filter(
            Match.scheduled_at.is_(None)
        ).count()
        
        if missing_scheduled > 0:
            exclusions.append(ExclusionReason(
                reason="missing_scheduled_at",
                count=missing_scheduled,
                description="Matches without scheduled_at timestamp"
            ))
        
        return exclusions
    
    def _count_usable_matches(self) -> int:
        """Count matches that meet all usability criteria."""
        return self.session.query(Match).filter(
            and_(
                Match.status == MatchStatus.FINISHED,
                Match.home_score.isnot(None),
                Match.away_score.isnot(None),
                Match.home_team_id.isnot(None),
                Match.away_team_id.isnot(None),
                Match.scheduled_at.isnot(None)
            )
        ).count()
    
    def _get_date_range(self) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Get earliest and latest match dates."""
        earliest = self.session.query(func.min(Match.scheduled_at)).scalar()
        latest = self.session.query(func.max(Match.scheduled_at)).scalar()
        return earliest, latest
    
    def _analyze_team_samples(self) -> List[TeamSample]:
        """Analyze sample sizes per team."""
        team_samples = []
        
        # Get all teams that have matches
        teams_with_matches = self.session.query(Team).join(
            Match, 
            or_(Match.home_team_id == Team.id, Match.away_team_id == Team.id)
        ).distinct().all()
        
        for team in teams_with_matches:
            # Count matches involving this team
            total_matches = self.session.query(Match).filter(
                or_(Match.home_team_id == team.id, Match.away_team_id == team.id)
            ).count()
            
            # Count finished matches
            finished_matches = self.session.query(Match).filter(
                and_(
                    Match.status == MatchStatus.FINISHED,
                    or_(Match.home_team_id == team.id, Match.away_team_id == team.id)
                )
            ).count()
            
            # Count home/away splits
            home_matches = self.session.query(Match).filter(
                Match.home_team_id == team.id
            ).count()
            
            away_matches = self.session.query(Match).filter(
                Match.away_team_id == team.id
            ).count()
            
            # Count usable matches
            usable_matches = self.session.query(Match).filter(
                and_(
                    Match.status == MatchStatus.FINISHED,
                    Match.home_score.isnot(None),
                    Match.away_score.isnot(None),
                    Match.scheduled_at.isnot(None),
                    or_(Match.home_team_id == team.id, Match.away_team_id == team.id)
                )
            ).count()
            
            team_sample = TeamSample(
                team_id=team.id,
                team_name=team.name,
                total_matches=total_matches,
                finished_matches=finished_matches,
                home_matches=home_matches,
                away_matches=away_matches,
                usable_matches=usable_matches
            )
            
            team_samples.append(team_sample)
        
        # Sort by usable matches descending
        team_samples.sort(key=lambda x: x.usable_matches, reverse=True)
        
        return team_samples
    
    def _analyze_competition_samples(self) -> List[CompetitionSample]:
        """Analyze sample sizes per competition."""
        competition_samples = []
        
        # Get all competitions that have matches
        competitions = self.session.query(Competition).join(Match).distinct().all()
        
        for comp in competitions:
            # Count matches in this competition
            total_matches = self.session.query(Match).filter(
                Match.competition_id == comp.id
            ).count()
            
            # Count finished matches
            finished_matches = self.session.query(Match).filter(
                and_(
                    Match.competition_id == comp.id,
                    Match.status == MatchStatus.FINISHED
                )
            ).count()
            
            # Count usable matches
            usable_matches = self.session.query(Match).filter(
                and_(
                    Match.competition_id == comp.id,
                    Match.status == MatchStatus.FINISHED,
                    Match.home_score.isnot(None),
                    Match.away_score.isnot(None),
                    Match.scheduled_at.isnot(None)
                )
            ).count()
            
            # Count teams in competition
            teams_count = self.session.query(func.count(func.distinct(
                func.coalesce(Match.home_team_id, Match.away_team_id)
            ))).filter(Match.competition_id == comp.id).scalar() or 0
            
            # Get date range for competition
            earliest = self.session.query(func.min(Match.scheduled_at)).filter(
                Match.competition_id == comp.id
            ).scalar()
            
            latest = self.session.query(func.max(Match.scheduled_at)).filter(
                Match.competition_id == comp.id
            ).scalar()
            
            comp_sample = CompetitionSample(
                competition_id=comp.id,
                competition_name=comp.name,
                total_matches=total_matches,
                finished_matches=finished_matches,
                usable_matches=usable_matches,
                teams_count=teams_count,
                date_range=(earliest, latest)
            )
            
            competition_samples.append(comp_sample)
        
        # Sort by usable matches descending
        competition_samples.sort(key=lambda x: x.usable_matches, reverse=True)
        
        return competition_samples
    
    def _count_matches_with_xg(self) -> int:
        """Count matches with xG data."""
        return self.session.query(Match).filter(
            and_(
                Match.home_xg.isnot(None),
                Match.away_xg.isnot(None)
            )
        ).count()
    
    def _count_matches_with_statistics(self) -> int:
        """Count matches with detailed statistics."""
        # This would count matches that have associated MatchStatistic records
        from app.database.models import MatchStatistic
        
        matches_with_stats = self.session.query(
            func.count(func.distinct(Match.id))
        ).join(MatchStatistic).scalar()
        
        return matches_with_stats or 0


def print_census_report(census: DatasetCensus) -> None:
    """Print human-readable census report."""
    print("\n" + "=" * 60)
    print("HISTORICAL DATASET CENSUS REPORT")
    print("=" * 60)
    
    print(f"\nHIGH-LEVEL STATISTICS:")
    print(f"Total matches in database: {census.total_matches:,}")
    print(f"Finished matches: {census.finished_matches:,}")
    print(f"Usable matches: {census.usable_matches:,}")
    print(f"Exclusion rate: {census.exclusion_percentage:.1f}%")
    
    if census.earliest_match and census.latest_match:
        print(f"Date range: {census.earliest_match.date()} to {census.latest_match.date()}")
    
    print(f"\nDATA QUALITY METRICS:")
    print(f"Matches with xG data: {census.matches_with_xg:,}")
    print(f"Matches with statistics: {census.matches_with_statistics:,}")
    
    if census.exclusion_reasons:
        print(f"\nEXCLUSION BREAKDOWN:")
        for reason in census.exclusion_reasons:
            print(f"  {reason.reason}: {reason.count:,} - {reason.description}")
    
    if census.competition_samples:
        print(f"\nTOP COMPETITIONS BY USABLE MATCHES:")
        for comp in census.competition_samples[:10]:  # Top 10
            print(f"  {comp.competition_name}: {comp.usable_matches:,} usable matches")
    
    if census.team_samples:
        print(f"\nTOP TEAMS BY USABLE MATCHES:")
        for team in census.team_samples[:10]:  # Top 10
            print(f"  {team.team_name}: {team.usable_matches:,} usable matches")
    
    print(f"\nUSABILITY ASSESSMENT:")
    if census.usable_matches >= 50:
        print("✓ SUFFICIENT samples for baseline evaluation")
    elif census.usable_matches >= 30:
        print("⚠ BORDERLINE samples - some metrics may be unreliable")  
    else:
        print("✗ INSUFFICIENT_HISTORICAL_SAMPLE - too few usable matches")
    
    print(f"\nCensus completed at: {census.census_timestamp}")


def main():
    """Main function."""
    try:
        # Get database session
        session = SessionLocal()
        
        # Run census
        census_analyzer = HistoricalDatasetCensus(session)
        census = census_analyzer.run_full_census()
        
        # Print report
        print_census_report(census)
        
        # Save to JSON file
        output_file = backend_root / "historical_dataset_census.json"
        with open(output_file, 'w') as f:
            json.dump(census.to_dict(), f, indent=2, default=str)
        
        print(f"\nDetailed census saved to: {output_file}")
        
        session.close()
        
    except Exception as e:
        print(f"Error running census: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    # Add missing import
    from sqlalchemy import or_
    exit(main())