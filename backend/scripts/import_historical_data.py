"""Historical match data import script.

Imports maximum historical data from available providers with:
- Controlled parallel fetching
- Batch processing
- Bulk database operations
- Incremental import support
- Cache utilization

Usage:
    python scripts/import_historical_data.py --start-date 2023-08-01 --end-date 2024-05-31 --provider fotmob
    python scripts/import_historical_data.py --competition premier_league --season 2023-2024
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import List, Dict, Set, Optional
import argparse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.session import get_db
from app.database.models import Match as MatchDB, MatchStatistic
from app.providers.fotmob import FotMobFootballProvider
from app.providers.manager import ProviderManager
from app.providers.models import ProviderMatch, ProviderMatchStats
from app.domain.match import Match as DomainMatch
from app.domain.enums import MatchStatus
from app.ingestion.match_ingestion import MatchIngester


# Configuration
BATCH_SIZE = 50  # Matches per batch
MAX_CONCURRENCY = 5  # Concurrent provider requests
DETAIL_FETCH_DELAY = 0.2  # Seconds between detail requests


class HistoricalImportStats:
    """Track import statistics."""
    
    def __init__(self):
        self.total_fixtures = 0
        self.finished_matches = 0
        self.new_matches = 0
        self.updated_matches = 0
        self.skipped_matches = 0
        self.with_scores = 0
        self.with_shots = 0
        self.with_sot = 0
        self.with_xg = 0
        self.with_possession = 0
        self.provider_requests = 0
        self.cache_hits = 0
        self.errors = 0
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
    
    def duration_seconds(self) -> float:
        """Calculate import duration."""
        if not self.start_time or not self.end_time:
            return 0.0
        return (self.end_time - self.start_time).total_seconds()
    
    def throughput(self) -> float:
        """Calculate matches per second."""
        duration = self.duration_seconds()
        if duration == 0:
            return 0.0
        return self.finished_matches / duration
    
    def report(self) -> str:
        """Generate summary report."""
        duration = self.duration_seconds()
        throughput = self.throughput()
        
        return f"""
Historical Import Summary
========================
Total Fixtures: {self.total_fixtures}
Finished Matches: {self.finished_matches}
New Matches: {self.new_matches}
Updated Matches: {self.updated_matches}
Skipped (existing): {self.skipped_matches}

Coverage:
- Scores: {self.with_scores} ({self._pct(self.with_scores, self.finished_matches)})
- Shots: {self.with_shots} ({self._pct(self.with_shots, self.finished_matches)})
- Shots on Target: {self.with_sot} ({self._pct(self.with_sot, self.finished_matches)})
- xG: {self.with_xg} ({self._pct(self.with_xg, self.finished_matches)})
- Possession: {self.with_possession} ({self._pct(self.with_possession, self.finished_matches)})

Performance:
- Provider Requests: {self.provider_requests}
- Cache Hits: {self.cache_hits}
- Errors: {self.errors}
- Duration: {duration:.1f}s
- Throughput: {throughput:.1f} matches/sec
"""
    
    @staticmethod
    def _pct(count: int, total: int) -> str:
        """Format percentage."""
        if total == 0:
            return "0%"
        return f"{100.0 * count / total:.1f}%"


class HistoricalImporter:
    """Import historical match data with controlled batching and concurrency."""
    
    def __init__(
        self,
        session: Session,
        provider_manager: ProviderManager,
        batch_size: int = BATCH_SIZE,
        max_concurrency: int = MAX_CONCURRENCY
    ):
        """Initialize importer.
        
        Args:
            session: Database session
            provider_manager: Provider manager
            batch_size: Matches per database batch
            max_concurrency: Maximum concurrent provider requests
        """
        self.session = session
        self.provider_manager = provider_manager
        self.batch_size = batch_size
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.stats = HistoricalImportStats()
    
    async def import_date_range(
        self,
        start_date: date,
        end_date: date,
        incremental: bool = True
    ) -> HistoricalImportStats:
        """Import matches for date range.
        
        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            incremental: Skip existing matches
            
        Returns:
            Import statistics
        """
        print(f"Importing historical data: {start_date} to {end_date}")
        print(f"Batch size: {self.batch_size}, Concurrency: {self.semaphore._value}")
        print(f"Incremental: {incremental}\n")
        
        self.stats.start_time = datetime.utcnow()
        
        # Stage A: Fixture Discovery
        print("Stage A: Fixture Discovery...")
        fixtures = await self._discover_fixtures(start_date, end_date)
        self.stats.total_fixtures = len(fixtures)
        print(f"Discovered {len(fixtures)} fixtures\n")
        
        # Filter to finished matches
        from app.domain.enums import MatchStatus
        finished = [f for f in fixtures if f.get('status') == MatchStatus.FINISHED.value]
        self.stats.finished_matches = len(finished)
        print(f"Finished matches: {len(finished)}\n")
        
        if not finished:
            print("No finished matches found in date range")
            self.stats.end_time = datetime.utcnow()
            return self.stats
        
        # Filter existing if incremental
        if incremental:
            to_import = await self._filter_existing(finished)
            print(f"After incremental filter: {len(to_import)} to import\n")
        else:
            to_import = finished
        
        if not to_import:
            print("All matches already imported (incremental mode)")
            self.stats.end_time = datetime.utcnow()
            return self.stats
        
        # Stage B: Batch Import with Detail Enrichment
        print("Stage B: Detail Enrichment & Import...")
        await self._batch_import(to_import)
        
        self.stats.end_time = datetime.utcnow()
        return self.stats
    
    async def _discover_fixtures(
        self,
        start_date: date,
        end_date: date
    ) -> List[Dict]:
        """Discover fixtures in date range (lightweight).
        
        Args:
            start_date: Start date
            end_date: End date
            
        Returns:
            List of fixture dicts with basic info
        """
        all_fixtures = []
        current = start_date
        
        # Collect fixtures day by day
        while current <= end_date:
            try:
                matches, metadata = await self.provider_manager.get_matches_by_date(current)
                self.stats.provider_requests += 1
                
                # Extract lightweight fixture info
                for match in matches:
                    # Get status as enum value or string
                    status_str = match.status.value if hasattr(match.status, 'value') else str(match.status)
                    
                    fixture = {
                        'match_id': match.source_id,
                        'home_team_id': match.home_team_id,
                        'away_team_id': match.away_team_id,
                        'scheduled_at': match.scheduled_at,
                        'status': status_str,
                        'home_score': match.home_score,
                        'away_score': match.away_score,
                        'competition_id': match.competition_id,
                        'season': match.season,
                        'provider_match': match  # Keep for detail fetch
                    }
                    all_fixtures.append(fixture)
                
                # Progress indicator
                if len(all_fixtures) % 100 == 0:
                    print(f"  Discovered {len(all_fixtures)} fixtures...", end='\r')
                
                await asyncio.sleep(0.1)  # Rate limit
                
            except Exception as e:
                print(f"Error fetching date {current}: {e}")
                self.stats.errors += 1
            
            current += timedelta(days=1)
        
        print()  # New line after progress
        return all_fixtures
    
    async def _filter_existing(self, fixtures: List[Dict]) -> List[Dict]:
        """Filter out existing matches for incremental import.
        
        Args:
            fixtures: Discovered fixtures
            
        Returns:
            Fixtures not yet in database
        """
        # Get existing match IDs using repository
        from app.database.repository import MatchRepository
        match_repo = MatchRepository(self.session)
        
        # Query for existing matches by provider IDs
        match_ids = [f['match_id'] for f in fixtures]
        
        # Check which ones already exist
        existing = self.session.query(MatchDB.provider_id).filter(
            MatchDB.provider_id.in_(match_ids)
        ).all()
        existing_ids = {row[0] for row in existing}
        
        self.stats.skipped_matches = len(existing_ids)
        
        # Return only new fixtures
        return [f for f in fixtures if f['match_id'] not in existing_ids]
    
    async def _batch_import(self, fixtures: List[Dict]):
        """Import fixtures in batches with detail enrichment.
        
        Args:
            fixtures: Fixtures to import
        """
        total = len(fixtures)
        
        for i in range(0, total, self.batch_size):
            batch = fixtures[i:i + self.batch_size]
            batch_num = i // self.batch_size + 1
            total_batches = (total + self.batch_size - 1) // self.batch_size
            
            print(f"Batch {batch_num}/{total_batches}: Processing {len(batch)} matches...")
            
            # Process batch
            await self._process_batch(batch)
            
            # Commit batch
            try:
                self.session.commit()
                print(f"  [OK] Batch {batch_num} committed\n")
            except Exception as e:
                self.session.rollback()
                print(f"  [FAIL] Batch {batch_num} failed: {e}\n")
                self.stats.errors += 1
    
    async def _process_batch(self, batch: List[Dict]):
        """Process a single batch of matches.
        
        Args:
            batch: Batch of fixtures
        """
        # Enrich details with controlled concurrency
        tasks = [self._fetch_and_store(fixture) for fixture in batch]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _fetch_and_store(self, fixture: Dict):
        """Fetch match details and store in database.
        
        Args:
            fixture: Fixture dict
        """
        async with self.semaphore:
            try:
                # Use existing provider match if available
                provider_match = fixture.get('provider_match')
                
                if provider_match:
                    # Already have data from discovery
                    match_obj = provider_match
                else:
                    # Fetch details
                    match_obj, metadata = await self.provider_manager.get_match(
                        fixture['match_id']
                    )
                    self.stats.provider_requests += 1
                    
                    if not match_obj:
                        return
                    
                    await asyncio.sleep(DETAIL_FETCH_DELAY)
                
                # Ingest using existing service
                await self._ingest_match(match_obj)
                
            except Exception as e:
                print(f"  Error processing {fixture['match_id']}: {e}")
                self.stats.errors += 1
    
    async def _ingest_match(self, match: ProviderMatch):
        """Ingest match into database using existing ingestion service.
        
        Args:
            match: Provider match object
        """
        try:
            # Use existing MatchIngester service
            ingester = MatchIngester(self.session)
            
            # Ingest match (upserts automatically)
            match_db = ingester.ingest_match(match)
            
            # Track if new or updated
            if match_db.created_at == match_db.updated_at:
                self.stats.new_matches += 1
            else:
                self.stats.updated_matches += 1
            
            # Track coverage
            if match.home_score is not None and match.away_score is not None:
                self.stats.with_scores += 1
            
            # Fetch and store statistics separately
            # Only for finished matches to avoid wasting API calls
            if match.status == MatchStatus.FINISHED:
                await self._fetch_and_store_statistics(match.source_id, match_db.id)
            
        except Exception as e:
            print(f"  Error ingesting {match.source_id}: {e}")
            self.stats.errors += 1
    
    async def _fetch_and_store_statistics(self, match_id: str, match_db_id: str):
        """Fetch and store match statistics.
        
        Args:
            match_id: Provider match ID
            match_db_id: Internal database match ID
        """
        try:
            # Fetch statistics from FotMob directly
            # ProviderManager doesn't expose fotmob attribute, use direct provider
            from app.config import Settings
            from app.providers.fotmob import FotMobFootballProvider
            
            settings = Settings()
            fotmob = FotMobFootballProvider(
                base_url=settings.fotmob_base_url,
                timeout_seconds=settings.provider_timeout_seconds,
                retry_count=min(settings.provider_retry_count, 1)
            )
            
            home_stats, away_stats = await fotmob.get_match_statistics(match_id)
            
            if not home_stats and not away_stats:
                return
            
            # Use existing MatchIngester to store statistics
            ingester = MatchIngester(self.session)
            
            # Store home team statistics
            if home_stats:
                ingester.ingest_match_stats(home_stats, match_db_id)
                
                # Track coverage (only count once per match)
                if home_stats.shots_total is not None:
                    self.stats.with_shots += 1
                
                if home_stats.shots_on_target is not None:
                    self.stats.with_sot += 1
                
                if home_stats.xg is not None:
                    self.stats.with_xg += 1
                
                if home_stats.possession_percentage is not None:
                    self.stats.with_possession += 1
            
            # Store away team statistics
            if away_stats:
                ingester.ingest_match_stats(away_stats, match_db_id)
                
        except Exception as e:
            # Statistics fetch failure shouldn't stop match import
            print(f"  Warning: Could not fetch statistics for {match_id}: {e}")
            self.stats.errors += 1


async def main():
    """Main import function."""
    parser = argparse.ArgumentParser(description='Import historical football match data')
    parser.add_argument('--start-date', type=str, required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--provider', type=str, default='fotmob', help='Provider (fotmob/ryzellx/openligadb)')
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE, help='Batch size')
    parser.add_argument('--concurrency', type=int, default=MAX_CONCURRENCY, help='Max concurrency')
    parser.add_argument('--full', action='store_true', help='Full import (skip incremental check)')
    
    args = parser.parse_args()
    
    # Parse dates
    try:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d').date()
    except ValueError as e:
        print(f"Invalid date format: {e}")
        print("Use YYYY-MM-DD format")
        return 1
    
    # Validate dates
    if start_date > end_date:
        print("Start date must be before end date")
        return 1
    
    if end_date > date.today():
        print("End date cannot be in the future")
        return 1
    
    # Initialize providers with config
    from app.config import Settings
    settings = Settings()
    
    fotmob = FotMobFootballProvider(
        base_url=settings.fotmob_base_url,
        timeout_seconds=settings.provider_timeout_seconds,
        retry_count=min(settings.provider_retry_count, 1)
    )
    
    # Create provider manager
    from app.providers.ryzellx import RyzellxFootballProvider
    from app.providers.openligadb import OpenLigaDBFootballProvider
    
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
        importer = HistoricalImporter(
            session=session,
            provider_manager=provider_manager,
            batch_size=args.batch_size,
            max_concurrency=args.concurrency
        )
        
        # Run import
        stats = await importer.import_date_range(
            start_date=start_date,
            end_date=end_date,
            incremental=not args.full
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
