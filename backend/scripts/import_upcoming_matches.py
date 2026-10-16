"""Upcoming match import script.

Imports scheduled/upcoming matches from providers to populate the dashboard.

This script complements import_historical_data.py which focuses on finished matches
with detailed statistics. This script imports scheduled matches for prediction purposes.

Usage:
    python scripts/import_upcoming_matches.py --days 7
    python scripts/import_upcoming_matches.py --days 14 --provider fotmob
    python scripts/import_upcoming_matches.py --start-date 2024-12-01 --end-date 2024-12-31
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import List, Dict, Set, Optional
import argparse
from sqlalchemy.orm import Session

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.session import get_db
from app.database.models import Match as MatchDB
from app.providers.manager import ProviderManager
from app.providers.models import ProviderMatch
from app.domain.enums import MatchStatus
from app.ingestion.match_ingestion import MatchIngester


class UpcomingImportStats:
    """Track upcoming match import statistics."""
    
    def __init__(self):
        self.total_discovered = 0
        self.scheduled_matches = 0
        self.live_matches = 0
        self.finished_matches = 0
        self.new_matches = 0
        self.updated_matches = 0
        self.skipped_matches = 0
        self.provider_requests = 0
        self.errors = 0
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.earliest_scheduled: Optional[datetime] = None
        self.latest_scheduled: Optional[datetime] = None
    
    def duration_seconds(self) -> float:
        """Calculate import duration."""
        if not self.start_time or not self.end_time:
            return 0.0
        return (self.end_time - self.start_time).total_seconds()
    
    def report(self) -> str:
        """Generate summary report."""
        duration = self.duration_seconds()
        
        return f"""
Upcoming Match Import Summary
============================
Total Discovered: {self.total_discovered}
├─ Scheduled: {self.scheduled_matches}
├─ Live: {self.live_matches}
└─ Finished: {self.finished_matches}

Database Operations:
├─ New Matches: {self.new_matches}
├─ Updated Matches: {self.updated_matches}
└─ Skipped (existing): {self.skipped_matches}

Schedule Range:
├─ Earliest: {self.earliest_scheduled or 'N/A'}
└─ Latest: {self.latest_scheduled or 'N/A'}

Performance:
├─ Provider Requests: {self.provider_requests}
├─ Errors: {self.errors}
└─ Duration: {duration:.1f}s
"""


class UpcomingMatchImporter:
    """Import upcoming/scheduled matches for prediction purposes."""
    
    def __init__(
        self,
        session: Session,
        provider_manager: ProviderManager
    ):
        """Initialize importer.
        
        Args:
            session: Database session
            provider_manager: Provider manager
        """
        self.session = session
        self.provider_manager = provider_manager
        self.stats = UpcomingImportStats()
        self.ingester = MatchIngester(session)
    
    async def import_upcoming_days(
        self,
        days: int,
        include_live: bool = True
    ) -> UpcomingImportStats:
        """Import upcoming matches for the next N days.
        
        Args:
            days: Number of days from today
            include_live: Include currently live matches
            
        Returns:
            Import statistics
        """
        today = date.today()
        end_date = today + timedelta(days=days)
        
        return await self.import_date_range(
            start_date=today,
            end_date=end_date,
            include_live=include_live
        )
    
    async def import_date_range(
        self,
        start_date: date,
        end_date: date,
        include_live: bool = True
    ) -> UpcomingImportStats:
        """Import upcoming matches for date range.
        
        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            include_live: Include currently live matches
            
        Returns:
            Import statistics
        """
        print(f"Importing upcoming matches: {start_date} to {end_date}")
        print(f"Include live matches: {include_live}\n")
        
        self.stats.start_time = datetime.utcnow()
        
        # Collect all matches in date range
        all_matches = []
        
        # Fetch live matches first if requested
        if include_live:
            print("Fetching live matches...")
            live_matches = await self._fetch_live_matches()
            all_matches.extend(live_matches)
            self.stats.live_matches = len(live_matches)
            print(f"Found {len(live_matches)} live matches\n")
        
        # Fetch scheduled matches day by day
        print("Fetching scheduled matches by date...")
        current = start_date
        while current <= end_date:
            try:
                day_matches = await self._fetch_date_matches(current)
                all_matches.extend(day_matches)
                
                # Progress indicator
                if (current - start_date).days % 7 == 0:
                    print(f"  Progress: {current} ({len(all_matches)} matches so far)")
                
                await asyncio.sleep(0.1)  # Rate limit
                
            except Exception as e:
                print(f"  Error fetching {current}: {e}")
                self.stats.errors += 1
            
            current += timedelta(days=1)
        
        self.stats.total_discovered = len(all_matches)
        print(f"\nDiscovered {len(all_matches)} total matches\n")
        
        if not all_matches:
            print("No matches found in date range")
            self.stats.end_time = datetime.utcnow()
            return self.stats
        
        # Categorize by status
        scheduled = []
        finished = []
        
        for match in all_matches:
            status = match.status
            if isinstance(status, MatchStatus):
                status_value = status.value
            else:
                status_value = str(status)
            
            if status_value in ['scheduled', 'SCHEDULED', 'upcoming']:
                scheduled.append(match)
            elif status_value in ['finished', 'FINISHED']:
                finished.append(match)
        
        self.stats.scheduled_matches = len(scheduled)
        self.stats.finished_matches += len(finished)
        
        print(f"Status breakdown:")
        print(f"  Scheduled: {len(scheduled)}")
        print(f"  Finished: {len(finished)}")
        print(f"  Live: {self.stats.live_matches}")
        print()
        
        # Import scheduled matches (primary purpose)
        print("Importing scheduled matches...")
        await self._batch_import(scheduled)
        
        # Also import finished matches if any (they might have just finished)
        if finished:
            print(f"\nImporting {len(finished)} recently finished matches...")
            await self._batch_import(finished)
        
        # Calculate schedule range
        if scheduled:
            scheduled_times = [m.scheduled_at for m in scheduled if m.scheduled_at]
            if scheduled_times:
                self.stats.earliest_scheduled = min(scheduled_times)
                self.stats.latest_scheduled = max(scheduled_times)
        
        self.stats.end_time = datetime.utcnow()
        
        # Commit all changes
        try:
            self.session.commit()
            print("\n[OK] All matches committed to database")
        except Exception as e:
            self.session.rollback()
            print(f"\n[FAIL] Database commit failed: {e}")
            self.stats.errors += 1
        
        return self.stats
    
    async def _fetch_live_matches(self) -> List[ProviderMatch]:
        """Fetch currently live matches.
        
        Returns:
            List of live matches
        """
        try:
            matches, metadata = await self.provider_manager.get_live_matches()
            self.stats.provider_requests += 1
            
            # Convert ProviderLiveMatch to ProviderMatch if needed
            # (they should already be ProviderMatch instances)
            return matches
            
        except Exception as e:
            print(f"  Error fetching live matches: {e}")
            self.stats.errors += 1
            return []
    
    async def _fetch_date_matches(self, date_obj: date) -> List[ProviderMatch]:
        """Fetch all matches for a specific date.
        
        Args:
            date_obj: Date to fetch
            
        Returns:
            List of matches (all statuses)
        """
        try:
            matches, metadata = await self.provider_manager.get_matches_by_date(date_obj)
            self.stats.provider_requests += 1
            return matches
            
        except Exception as e:
            print(f"  Error fetching date {date_obj}: {e}")
            self.stats.errors += 1
            return []
    
    async def _batch_import(self, matches: List[ProviderMatch]):
        """Import matches into database.
        
        Args:
            matches: Provider matches to import
        """
        for match in matches:
            try:
                # Check if match already exists
                existing = self.session.query(MatchDB).filter(
                    MatchDB.provider_id == match.source_id
                ).first()
                
                if existing:
                    # Update existing match
                    match_db = self.ingester.ingest_match(match)
                    self.stats.updated_matches += 1
                else:
                    # Insert new match
                    match_db = self.ingester.ingest_match(match)
                    self.stats.new_matches += 1
                
                # Print progress every 50 matches
                total_processed = self.stats.new_matches + self.stats.updated_matches
                if total_processed % 50 == 0:
                    print(f"  Processed {total_processed} matches...", end='\r')
                
            except Exception as e:
                print(f"\n  Error importing match {match.source_id}: {e}")
                self.stats.errors += 1
        
        print()  # New line after progress


async def main():
    """Main import function."""
    parser = argparse.ArgumentParser(description='Import upcoming football matches')
    
    # Date range options
    date_group = parser.add_mutually_exclusive_group(required=True)
    date_group.add_argument('--days', type=int, help='Import next N days from today')
    date_group.add_argument('--date-range', action='store_true', help='Use --start-date and --end-date')
    
    parser.add_argument('--start-date', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--no-live', action='store_true', help='Exclude live matches')
    parser.add_argument('--provider', type=str, default='fotmob', help='Provider (fotmob/ryzellx/openligadb)')
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.date_range:
        if not args.start_date or not args.end_date:
            print("Error: --start-date and --end-date required when using --date-range")
            return 1
        
        try:
            start_date = datetime.strptime(args.start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(args.end_date, '%Y-%m-%d').date()
        except ValueError as e:
            print(f"Invalid date format: {e}")
            print("Use YYYY-MM-DD format")
            return 1
        
        if start_date > end_date:
            print("Start date must be before end date")
            return 1
    
    # Initialize providers with config
    from app.config import Settings
    settings = Settings()
    
    from app.providers.fotmob import FotMobFootballProvider
    from app.providers.ryzellx import RyzellxFootballProvider
    from app.providers.openligadb import OpenLigaDBFootballProvider
    
    fotmob = FotMobFootballProvider(
        base_url=settings.fotmob_base_url,
        timeout_seconds=settings.provider_timeout_seconds,
        retry_count=min(settings.provider_retry_count, 1)
    )
    
    ryzellx = RyzellxFootballProvider(
        base_url=settings.ryzellx_base_url,
        timeout_seconds=settings.provider_timeout_seconds,
        retry_count=settings.provider_retry_count
    )
    
    openligadb = OpenLigaDBFootballProvider(
        base_url=settings.openligadb_base_url,
        timeout_seconds=settings.provider_timeout_seconds,
        retry_count=settings.provider_retry_count
    )
    
    provider_manager = ProviderManager(
        ryzellx=ryzellx,
        fotmob=fotmob,
        openligadb=openligadb
    )
    
    # Get database session
    session = next(get_db())
    
    try:
        # Create importer
        importer = UpcomingMatchImporter(
            session=session,
            provider_manager=provider_manager
        )
        
        # Run import
        if args.days:
            stats = await importer.import_upcoming_days(
                days=args.days,
                include_live=not args.no_live
            )
        else:
            stats = await importer.import_date_range(
                start_date=start_date,
                end_date=end_date,
                include_live=not args.no_live
            )
        
        # Print report
        print(stats.report())
        
        return 0
        
    except KeyboardInterrupt:
        print("\nImport cancelled by user")
        session.rollback()
        return 1
    
    except Exception as e:
        print(f"\nImport failed: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
        return 1
    
    finally:
        session.close()
        await provider_manager.close()


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
