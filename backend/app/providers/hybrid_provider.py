"""Hybrid provider that combines external providers with database fallback.

This provider tries external providers first for fresh data, but falls back
to database lookups for canonical UUIDs that external providers cannot resolve.

Implements smart data freshness policy based on match status and timestamps.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session

from app.providers.base import FootballDataProvider
from app.providers.adapter import ProviderManagerAdapter
from app.providers.database_adapter import DatabaseBackedProvider
from app.domain.match import Match
from app.domain.entities import Team, Competition, Season
from app.domain.statistics import TeamMatchStatistic
from app.domain.enums import MatchStatus
from app.config import settings


class HybridProvider(FootballDataProvider):
    """Provider that combines external providers with database fallback.
    
    This provider first attempts to use external providers (ProviderManagerAdapter)
    for live data, but falls back to database lookups when external providers
    fail to resolve canonical UUIDs.
    """
    
    def __init__(self, external_provider: ProviderManagerAdapter, session: Session):
        """Initialize hybrid provider.
        
        Args:
            external_provider: ProviderManagerAdapter for external data
            session: Database session for fallback lookups
        """
        self.external_provider = external_provider
        self.db_provider = DatabaseBackedProvider(session)
    
    def is_development_data(self) -> bool:
        """Return False since this uses real data from both sources."""
        return False
    
    def _is_canonical_uuid(self, id_str: str) -> bool:
        """Check if the ID looks like a canonical UUID.
        
        Args:
            id_str: ID string to check
            
        Returns:
            True if it looks like a UUID (contains dashes and is 36 chars)
        """
        return len(id_str) == 36 and id_str.count('-') == 4
    
    def _should_refresh_from_external(self, db_matches: List[Match], status_filter: Optional[str] = None) -> bool:
        """Determine if database matches need refreshing from external providers.
        
        Implements timestamp-based freshness policy:
        - LIVE: Always refresh (handled by status-aware policy, not called here)
        - SCHEDULED: Refresh if stale OR approaching kickoff
        - FINISHED: Refresh if recently finished and stale OR very old
        - No filter: Always refresh (handled by status-aware policy, not called here)
        
        Args:
            db_matches: List of matches from database
            status_filter: Status filter applied to query
            
        Returns:
            True if external provider should be called for fresh data
        """
        if not db_matches:
            # No data in database, need external refresh
            return True
        
        now = datetime.now(tz=db_matches[0].scheduled_at.tzinfo if db_matches[0].scheduled_at.tzinfo else None)
        
        for match in db_matches:
            # If any match lacks provider_fetched_at timestamp, refresh all
            if match.provider_fetched_at is None:
                return True
            
            # Calculate data age
            data_age = now - match.provider_fetched_at
            
            if status_filter and status_filter.upper() == "SCHEDULED":
                # SCHEDULED matches: Check for stale data or approaching kickoff
                scheduled_minutes = settings.data_freshness_scheduled_minutes
                approaching_minutes = settings.data_freshness_approaching_kickoff_minutes
                
                # Refresh if data is too old
                if data_age > timedelta(minutes=scheduled_minutes):
                    return True
                
                # Refresh if kickoff is approaching and data isn't very fresh
                time_until_kickoff = match.scheduled_at - now
                if time_until_kickoff < timedelta(minutes=approaching_minutes):
                    # For approaching matches, require fresher data (15 minutes)
                    if data_age > timedelta(minutes=15):
                        return True
            
            elif status_filter and status_filter.upper() == "FINISHED":
                # FINISHED matches: Check if recently finished or very old
                finished_recent_minutes = settings.data_freshness_finished_recent_minutes
                finished_minutes = settings.data_freshness_finished_minutes
                
                # Check if match finished recently (within last 3 hours)
                time_since_match = now - match.scheduled_at
                if time_since_match < timedelta(minutes=finished_recent_minutes):
                    # Recently finished: need fresh data for score confirmation (30 minutes freshness)
                    if data_age > timedelta(minutes=30):
                        return True
                
                # For older finished matches, allow longer staleness
                if data_age > timedelta(minutes=finished_minutes):
                    return True
        
        # All matches are fresh enough
        return False

    # -------------------------------------------------------------------------
    # Team ID resolution — FotMob numeric ID → canonical UUID
    # -------------------------------------------------------------------------

    def _batch_resolve_team_ids(self, team_ids: set) -> Dict[str, str]:
        """Batch resolve provider team IDs to canonical UUIDs.
        
        OPTIMIZATION (Section 5): Single batch query instead of individual lookups per team.
        
        Args:
            team_ids: Set of provider team IDs to resolve
            
        Returns:
            Dict mapping provider_id -> canonical UUID
        """
        if not team_ids:
            return {}
        
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            session = self.db_provider.session
            from app.database.models import Team as TeamDB
            
            # Single batch query for all team IDs
            rows = (
                session.query(TeamDB.provider_id, TeamDB.id)
                .filter(TeamDB.provider_id.in_(team_ids))
                .all()
            )
            
            mapping = {provider_id: canonical_id for provider_id, canonical_id in rows}
            
            if len(mapping) < len(team_ids):
                missing = team_ids - set(mapping.keys())
                logger.warning(
                    f"_batch_resolve_team_ids: {len(missing)} team IDs not found in database: {list(missing)[:5]}..."
                )
            
            return mapping
        
        except Exception as exc:
            logger.error(f"_batch_resolve_team_ids: batch lookup failed: {exc}")
            return {}

    def _resolve_team_canonical_uuid(self, provider_team_id: str) -> str:
        """Resolve a FotMob numeric team ID to the canonical UUID in the teams table.

        The DB stores teams with:
          - teams.id          → canonical UUID (e.g. 'b3bd533f-...')
          - teams.provider_id → FotMob numeric ID (e.g. '9826')

        When external providers (FotMob) return match.home_team_id = '9826', the
        feature extractor queries the matches table by teams.id (UUID format) and
        finds nothing, causing 'Insufficient data'.  This method performs the
        one-time lookup that bridges the two ID spaces.

        Args:
            provider_team_id: FotMob numeric ID string (e.g. '9826') OR an
                already-canonical UUID – the latter is returned unchanged.

        Returns:
            Canonical UUID string, or the original ID if mapping is unavailable.
        """
        import logging
        logger = logging.getLogger(__name__)

        # Already a canonical UUID – nothing to do
        if self._is_canonical_uuid(provider_team_id):
            return provider_team_id

        # Try to resolve via DB team lookup
        try:
            session = self.db_provider.session
            from app.database.models import Team as TeamDB
            row = (
                session.query(TeamDB.id)
                .filter(TeamDB.provider_id == provider_team_id)
                .first()
            )
            if row:
                logger.debug(
                    f"_resolve_team_canonical_uuid: {provider_team_id} → {row[0]}"
                )
                return row[0]
        except Exception as exc:
            logger.debug(
                f"_resolve_team_canonical_uuid: DB lookup failed for "
                f"provider_team_id={provider_team_id}: {exc}"
            )

        # No mapping found – return original so callers still work (degraded mode)
        logger.warning(
            f"_resolve_team_canonical_uuid: no canonical UUID found for provider_team_id={provider_team_id}. "
            f"This may indicate missing team data in the database. Returning original ID for graceful degradation."
        )
        return provider_team_id

    def _batch_resolve_match_team_uuids(self, matches: List[Match]) -> List[Match]:
        """Batch replace FotMob numeric team IDs with canonical UUIDs for multiple matches.
        
        OPTIMIZATION (Section 5): Collect all unique team IDs across all matches,
        resolve in one batch query, then apply mappings. This replaces O(n*2) individual
        queries with O(1) batch query where n is number of matches.
        
        Args:
            matches: List of Match objects with potentially numeric team IDs
            
        Returns:
            Same list of Match objects with team IDs updated in-place
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # Collect all unique provider team IDs
        provider_team_ids = set()
        for match in matches:
            if not self._is_canonical_uuid(match.home_team_id):
                provider_team_ids.add(match.home_team_id)
            if not self._is_canonical_uuid(match.away_team_id):
                provider_team_ids.add(match.away_team_id)
        
        if not provider_team_ids:
            # All team IDs are already canonical
            return matches
        
        # Batch resolve all team IDs
        team_id_mapping = self._batch_resolve_team_ids(provider_team_ids)
        
        # Apply mappings to all matches
        for match in matches:
            if match.home_team_id in team_id_mapping:
                match.home_team_id = team_id_mapping[match.home_team_id]
            elif not self._is_canonical_uuid(match.home_team_id):
                logger.warning(
                    f"No canonical UUID found for home_team_id={match.home_team_id} (match {match.id})"
                )
            
            if match.away_team_id in team_id_mapping:
                match.away_team_id = team_id_mapping[match.away_team_id]
            elif not self._is_canonical_uuid(match.away_team_id):
                logger.warning(
                    f"No canonical UUID found for away_team_id={match.away_team_id} (match {match.id})"
                )
        
        return matches

    def _resolve_match_team_uuids(self, match: Match) -> Match:
        """Replace FotMob numeric team IDs on a Match with canonical UUIDs.

        Called after any external provider returns a Match so that downstream
        feature extraction (which queries the DB by canonical UUID) can find
        historical data for both teams.

        Args:
            match: Domain Match whose home_team_id / away_team_id may be
                   FotMob numeric strings.

        Returns:
            The same Match object with team IDs updated in-place.
        """
        match.home_team_id = self._resolve_team_canonical_uuid(match.home_team_id)
        match.away_team_id = self._resolve_team_canonical_uuid(match.away_team_id)
        return match

    def get_match(self, match_id: str) -> Optional[Match]:
        """Get match, trying external providers first, then database.

        Returns None (never raises) if no source can resolve the match ID.

        After an external provider (FotMob) returns a match its team IDs are
        numeric FotMob IDs (e.g. '9826').  _resolve_match_team_uuids() maps
        these to canonical UUIDs so that the prediction feature extractor can
        query historical matches by the correct key.

        Args:
            match_id: Match ID (could be external provider ID or canonical UUID)

        Returns:
            Match domain object or None if not found
        """
        import logging
        logger = logging.getLogger(__name__)

        # First try external providers
        try:
            match = self.external_provider.get_match(match_id)
            if match is not None:
                # Resolve FotMob numeric team IDs → canonical UUIDs so feature
                # extraction can look up historical matches in the DB correctly.
                self._resolve_match_team_uuids(match)
                # Update status before returning - this fixes cached SCHEDULED matches
                updated_match = self._update_single_match_status(match)
                return updated_match
        except Exception as exc:
            logger.debug(f"HybridProvider.get_match: external provider failed for {match_id}: {exc}")

        # If external providers fail or return None, try database.
        # This handles canonical UUIDs that external providers don't know about.
        try:
            db_match = self.db_provider.get_match(match_id)
            if db_match is not None:
                return self._update_single_match_status(db_match)
            return None
        except Exception as exc:
            logger.warning(f"HybridProvider.get_match: DB fallback failed for {match_id}: {exc} – returning None")
            return None

    
    def get_team(self, team_id: str) -> Optional[Team]:
        """Get team, trying external providers first, then database.

        Returns None (never raises) if no source can resolve the team ID.
        On Vercel's ephemeral SQLite environment the 'teams' table may not
        exist; that OperationalError is caught here so callers receive None
        instead of an unhandled 500.

        Args:
            team_id: Team ID (could be external provider ID or canonical UUID)

        Returns:
            Team domain object or None if not found
        """
        import logging
        logger = logging.getLogger(__name__)

        # 1. Try external providers
        try:
            team = self.external_provider.get_team(team_id)
            if team is not None:
                return team
        except Exception as exc:
            logger.debug(
                f"HybridProvider.get_team: external provider failed for "
                f"team_id={team_id}: {exc}"
            )

        # 2. Try database (may fail if teams table does not exist)
        try:
            return self.db_provider.get_team(team_id)
        except Exception as exc:
            logger.warning(
                f"HybridProvider.get_team: database fallback failed for "
                f"team_id={team_id}: {exc} – returning None"
            )
            return None
    
    async def get_matches_async(
        self,
        competition_id: Optional[str] = None,
        season_id: Optional[str] = None,
        team_id: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        status: Optional[str] = None,
    ) -> List[Match]:
        """Async version of get_matches for API endpoints.
        
        PERFORMANCE OPTIMIZATION: Passes status filter to providers when safe to do so,
        reducing data transfer and processing overhead.
        
        Uses hybrid approach: merge external provider matches with database matches
        to ensure complete coverage of all matches.
        
        Args:
            competition_id: Filter by competition
            season_id: Filter by season  
            team_id: Filter by team
            from_date: Filter from date
            to_date: Filter to date
            status: Filter by status
            
        Returns:
            List of Match domain objects with updated statuses
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # PERFORMANCE: Determine if we can safely pass status filter to providers
        # We can pass status filter directly when:
        # 1. Status is provided
        # 2. We don't need status updates (statuses are trusted from provider/DB)
        # OR we're only querying database (which has canonical statuses)
        
        # For now, we need to update statuses after fetch, so we DON'T pass status
        # to external providers (they may have stale data). But we CAN pass it to database.
        
        requested_status = status
        provider_status_filter = None  # Don't filter at provider level yet
        db_status_filter = status  # Database has canonical statuses, filter there
        
        all_matches = []
        
        # DATA FRESHNESS POLICY:
        # - For LIVE matches: Always check external providers (real-time data critical)
        # - For SCHEDULED/FINISHED/CANCELLED: Database-first is safe (canonical statuses)
        # - For no status filter: Check external providers first (user expects fresh data)
        
        should_check_external_first = (
            not status or  # No status filter = user expects fresh data across all statuses
            status.upper() == "LIVE"  # Live matches need real-time updates
        )
        
        if should_check_external_first:
            # No status filter: Check external providers first for freshness
            try:
                logger.debug(f"HybridProvider.get_matches_async: Checking external providers first (no status filter)")
                external_matches = await self.external_provider.get_matches_async(
                    competition_id=competition_id,
                    season_id=season_id,
                    team_id=team_id,
                    from_date=from_date,
                    to_date=to_date,
                    status=provider_status_filter,
                )
                if external_matches:
                    logger.debug(f"HybridProvider.get_matches_async: External providers returned {len(external_matches)} matches")
                    # Resolve FotMob numeric team IDs → canonical UUIDs
                    for m in external_matches:
                        self._resolve_match_team_uuids(m)
                    all_matches.extend(external_matches)
            except Exception as e:
                logger.debug(f"HybridProvider.get_matches_async: External providers failed: {e}")
            
            # Also get database matches for merge ONLY if external provider returned no results
            # CRITICAL FIX: When competition_id filter is provided, external provider's results are authoritative.
            # Merging with database here would cause duplicate matches (ID formats differ: external vs UUID),
            # breaking the competition filter. Database is only used as fallback when external fails.
            if not all_matches:
                try:
                    logger.debug(f"HybridProvider.get_matches_async: External returned nothing, trying database")
                    db_matches = self.db_provider.get_matches(
                        competition_id=competition_id,
                        season_id=season_id,
                        team_id=team_id,
                        from_date=from_date,
                        to_date=to_date,
                        status=db_status_filter,
                    )
                    
                    if db_matches:
                        logger.debug(f"HybridProvider.get_matches_async: Database returned {len(db_matches)} matches")
                        all_matches.extend(db_matches)
                        logger.debug(f"HybridProvider.get_matches_async: Total matches after merge: {len(all_matches)}")
                except Exception as e:
                    logger.debug(f"HybridProvider.get_matches_async: Database lookup failed: {e}")
        
        else:
            # ALL STATUS queries: Database-first with freshness-based refresh
            # Database is authoritative for status filtering (SCHEDULED, LIVE, FINISHED, CANCELLED)
            db_matches = []
            try:
                logger.debug(f"HybridProvider.get_matches_async: Checking database first (status={db_status_filter})")
                db_matches = self.db_provider.get_matches(
                    competition_id=competition_id,
                    season_id=season_id,
                    team_id=team_id,
                    from_date=from_date,
                    to_date=to_date,
                    status=db_status_filter,
                )
                
                if db_matches:
                    logger.debug(f"HybridProvider.get_matches_async: Database returned {len(db_matches)} matches")
            except Exception as e:
                logger.debug(f"HybridProvider.get_matches_async: Database lookup failed: {e}")
            
            # UNIFIED FRESHNESS POLICY: Check if external refresh is needed
            should_refresh = self._should_refresh_from_external(db_matches, status)
            
            if should_refresh:
                try:
                    logger.debug(f"HybridProvider.get_matches_async: Data stale or unavailable, refreshing from external providers")
                    external_matches = await self.external_provider.get_matches_async(
                        competition_id=competition_id,
                        season_id=season_id,
                        team_id=team_id,
                        from_date=from_date,
                        to_date=to_date,
                        status=provider_status_filter,
                    )
                    if external_matches:
                        logger.debug(f"HybridProvider.get_matches_async: External providers returned {len(external_matches)} matches")

                        # Apply status filter to external matches since provider_status_filter is None
                        if status:
                            from app.domain.enums import MatchStatus
                            try:
                                filter_status = MatchStatus(status.upper())
                                external_matches = [m for m in external_matches if m.status == filter_status]
                                logger.debug(f"HybridProvider.get_matches_async: After status filter: {len(external_matches)} matches")
                            except ValueError:
                                logger.warning(f"HybridProvider.get_matches_async: Invalid status value: {status}")
                                external_matches = []

                        # Resolve FotMob numeric team IDs → canonical UUIDs
                        for m in external_matches:
                            self._resolve_match_team_uuids(m)

                        all_matches.extend(external_matches)
                    else:
                        # External refresh failed but we have db data - use it with availability info
                        logger.debug(f"HybridProvider.get_matches_async: External refresh returned no data, using cached database matches")
                        all_matches.extend(db_matches)
                except Exception as e:
                    logger.warning(f"HybridProvider.get_matches_async: External provider refresh failed: {e}")
                    # Use stale database data when external provider fails
                    logger.debug(f"HybridProvider.get_matches_async: Using stale database matches due to external failure")
                    all_matches.extend(db_matches)
            else:
                # Data is fresh enough, use database matches
                logger.debug(f"HybridProvider.get_matches_async: Using fresh database matches (canonical data)")
                all_matches.extend(db_matches)
            
            if not all_matches:
                logger.debug(f"HybridProvider.get_matches_async: No matches found from any source for status={status}")
        
        if not all_matches:
            logger.debug(f"HybridProvider.get_matches_async: No matches found from any source")
            return []
        
        # DATABASE-FIRST: No status updates needed (database is canonical)
        # Database query already filtered by correct status, results are authoritative
        logger.debug(f"HybridProvider.get_matches_async: Returning {len(all_matches)} matches (database-first)")
        
        # No post-update status filtering - database already filtered by status before update
        # This preserves matches that were corrected from SCHEDULED to FINISHED
        
        return all_matches

    def get_matches(
        self,
        competition_id: Optional[str] = None,
        season_id: Optional[str] = None,
        team_id: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        status: Optional[str] = None,
    ) -> List[Match]:
        """Get matches, trying external providers first, then database.
        
        PERFORMANCE OPTIMIZATION: Passes status filter to database queries when possible,
        reducing data transfer and processing overhead.
        
        Args:
            competition_id: Filter by competition
            season_id: Filter by season  
            team_id: Filter by team
            from_date: Filter from date
            to_date: Filter to date
            status: Filter by status
            
        Returns:
            List of Match domain objects with updated statuses
        """
        import logging
        logger = logging.getLogger(__name__)
        
        requested_status = status
        provider_status_filter = None  # External providers may have stale statuses
        db_status_filter = status  # Database has canonical statuses
        
        all_matches = []
        
        # DATA FRESHNESS POLICY:
        # - For LIVE matches: Always check external providers (real-time data critical)
        # - For SCHEDULED/FINISHED: Database-first is safe (stale data acceptable)
        # - For no status filter: Check external providers (user expects fresh data)
        
        should_check_external_first = (
            not status or  # No status filter = user expects fresh data
            status.upper() == "LIVE"  # Live matches need real-time updates
        )
        
        if should_check_external_first:
            # LIVE or unfiltered queries: Check external providers first for freshness
            try:
                logger.debug(f"HybridProvider.get_matches: Checking external providers first (status={status})")
                external_matches = self.external_provider.get_matches(
                    competition_id=competition_id,
                    season_id=season_id,
                    team_id=team_id,
                    from_date=from_date,
                    to_date=to_date,
                    status=provider_status_filter,
                )
                if external_matches:
                    logger.debug(f"HybridProvider.get_matches: External providers returned {len(external_matches)} matches")
                    all_matches.extend(external_matches)
            except Exception as e:
                logger.debug(f"HybridProvider.get_matches: External providers failed: {e}")
            
            # Also get database matches for merge ONLY if external provider returned no results
            # CRITICAL FIX: When competition_id filter is provided, external provider's results are authoritative.
            # Merging with database here would cause duplicate matches (ID formats differ: external vs UUID),
            # breaking the competition filter. Database is only used as fallback when external fails.
            if not all_matches:
                try:
                    logger.debug(f"HybridProvider.get_matches: External returned nothing, trying database")
                    db_matches = self.db_provider.get_matches(
                        competition_id=competition_id,
                        season_id=season_id,
                        team_id=team_id,
                        from_date=from_date,
                        to_date=to_date,
                        status=db_status_filter,
                    )
                    
                    if db_matches:
                        logger.debug(f"HybridProvider.get_matches: Database returned {len(db_matches)} matches")
                        all_matches.extend(db_matches)
                        logger.debug(f"HybridProvider.get_matches: Total matches after merge: {len(all_matches)}")
                except Exception as e:
                    logger.debug(f"HybridProvider.get_matches: Database lookup failed: {e}")
        
        else:
            # SCHEDULED/FINISHED queries: Database-first optimization is safe
            db_matches = []
            try:
                logger.debug(f"HybridProvider.get_matches: Checking database first (status={db_status_filter})")
                db_matches = self.db_provider.get_matches(
                    competition_id=competition_id,
                    season_id=season_id,
                    team_id=team_id,
                    from_date=from_date,
                    to_date=to_date,
                    status=db_status_filter,
                )
                
                if db_matches:
                    logger.debug(f"HybridProvider.get_matches: Database returned {len(db_matches)} matches")
                    
                    # TIMESTAMP-BASED FRESHNESS CHECK
                    should_refresh = self._should_refresh_from_external(db_matches, status)
                    
                    if should_refresh:
                        logger.debug(f"HybridProvider.get_matches: Database data is stale, refreshing from external providers")
                        # Fetch fresh data from external providers
                        try:
                            external_matches = self.external_provider.get_matches(
                                competition_id=competition_id,
                                season_id=season_id,
                                team_id=team_id,
                                from_date=from_date,
                                to_date=to_date,
                                status=provider_status_filter,
                            )
                            if external_matches:
                                logger.debug(f"HybridProvider.get_matches: External providers returned {len(external_matches)} matches (refreshed)")
                                # Merge: external data takes precedence
                                external_ids = {m.id for m in external_matches}
                                for db_match in db_matches:
                                    if db_match.id not in external_ids:
                                        external_matches.append(db_match)
                                all_matches.extend(external_matches)
                            else:
                                # External failed, use stale DB data as fallback
                                logger.debug(f"HybridProvider.get_matches: External refresh failed, using stale database data")
                                all_matches.extend(db_matches)
                        except Exception as e:
                            # External failed, use stale DB data as fallback
                            logger.debug(f"HybridProvider.get_matches: External refresh failed ({e}), using stale database data")
                            all_matches.extend(db_matches)
                    else:
                        # Data is fresh enough, use database
                        logger.debug(f"HybridProvider.get_matches: Database data is fresh, using cached data")
                        all_matches.extend(db_matches)
            except Exception as e:
                logger.debug(f"HybridProvider.get_matches: Database lookup failed: {e}")
            
            # Only try external providers if database returned nothing
            if not all_matches:
                try:
                    logger.debug(f"HybridProvider.get_matches: Database empty, trying external providers")
                    matches = self.external_provider.get_matches(
                        competition_id=competition_id,
                        season_id=season_id,
                        team_id=team_id,
                        from_date=from_date,
                        to_date=to_date,
                        status=provider_status_filter,
                    )
                    if matches:
                        logger.debug(f"HybridProvider.get_matches: External providers returned {len(matches)} matches")
                        all_matches.extend(matches)
                except Exception as e:
                    logger.debug(f"HybridProvider.get_matches: External providers failed: {e}")
        
        if not all_matches:
            return []
        
        # DATABASE-FIRST: No status updates needed (database is canonical)
        # Database query already filtered by correct status, results are authoritative
        logger.debug(f"HybridProvider.get_matches: Returning {len(all_matches)} matches (database-first)")
        
        # No post-update status filtering - database already filtered by status before update
        # This preserves matches that were corrected from SCHEDULED to FINISHED
        
        return all_matches
    
    def get_team_match_statistics(self, match_id: str) -> List[TeamMatchStatistic]:
        """Get team match statistics, trying external providers first, then database.
        
        Args:
            match_id: Match ID
            
        Returns:
            List of TeamMatchStatistic objects
        """
        # First try external providers
        try:
            stats = self.external_provider.get_team_match_statistics(match_id)
            if stats:
                return stats
        except Exception:
            # External provider failed, continue to database fallback
            pass
        
        # If external providers fail, try database
        return self.db_provider.get_team_match_statistics(match_id)
    
    def get_team_match_statistics_firsthalf(self, match_id: str) -> List[TeamMatchStatistic]:
        """Get first-half statistics, trying external providers first, then database.
        
        Args:
            match_id: Match ID
            
        Returns:
            List of TeamMatchStatistic objects for first half
        """
        # First try external providers
        try:
            stats = self.external_provider.get_team_match_statistics_firsthalf(match_id)
            if stats:
                return stats
        except Exception:
            # External provider failed, continue to database fallback
            pass
        
        # If external providers fail, try database
        return self.db_provider.get_team_match_statistics_firsthalf(match_id)
    
    def get_competitions(self, country: Optional[str] = None) -> List[Competition]:
        """Get competitions, trying external providers first, then database.

        If both external providers and the database return nothing (e.g. the DB
        competitions table does not exist in the Vercel SQLite ephemeral
        environment), returns an empty list and logs the root cause so that
        callers can use ``get_competitions_from_matches_async`` instead.

        Args:
            country: Filter by country

        Returns:
            List of Competition objects (may be empty if no source has data)
        """
        import logging
        logger = logging.getLogger(__name__)

        # 1. Try external providers (ProviderManagerAdapter raises NotImplementedError)
        try:
            competitions = self.external_provider.get_competitions()
            if competitions:
                logger.debug(
                    f"HybridProvider.get_competitions: external provider returned "
                    f"{len(competitions)} competitions"
                )
                return competitions
        except NotImplementedError:
            logger.info(
                "HybridProvider.get_competitions: external provider not implemented "
                "(ProviderManagerAdapter.get_competitions raises NotImplementedError) "
                "- falling back to database"
            )
        except Exception as exc:
            logger.warning(
                f"HybridProvider.get_competitions: external provider failed: {exc} "
                "- falling back to database"
            )

        # 2. Try database (may fail if competitions table does not exist)
        try:
            db_competitions = self.db_provider.get_competitions(country=country)
            if db_competitions:
                logger.debug(
                    f"HybridProvider.get_competitions: database returned "
                    f"{len(db_competitions)} competitions"
                )
                return db_competitions
            logger.info(
                "HybridProvider.get_competitions: database returned 0 competitions "
                "(table exists but is empty) - caller should use "
                "get_competitions_from_matches_async"
            )
        except Exception as exc:
            logger.warning(
                f"HybridProvider.get_competitions: database fallback failed: {exc} "
                "(competitions table likely missing) - caller should use "
                "get_competitions_from_matches_async"
            )

        return []

    async def get_competitions_from_matches_async(
        self,
        country: Optional[str] = None,
    ) -> List[Competition]:
        """Derive available competitions from the current match schedule.

        This is the primary source of competition data when neither the external
        provider nor the database can supply a competition list.  It fetches
        upcoming matches for a 30-day window from today via the external provider
        (FotMob) and extracts the unique (competition_id, competition_name) pairs
        that are already present in the live match feed.

        The IDs returned here are the same provider-numeric IDs that appear in
        ``/api/v1/matches``, so the frontend can use them to filter matches by
        competition without any UUID translation.

        Args:
            country: Unused – retained for signature compatibility.

        Returns:
            Deduplicated list of Competition objects derived from live matches.
            Returns an empty list (never raises) if the external provider fails.
        """
        import logging
        from datetime import date, timedelta
        logger = logging.getLogger(__name__)

        today = date.today()
        to_date = today + timedelta(days=30)

        provider_matches = []
        try:
            provider_matches = await self.external_provider.get_matches_async(
                from_date=today,
                to_date=to_date,
            )
            logger.debug(
                f"HybridProvider.get_competitions_from_matches_async: "
                f"fetched {len(provider_matches)} matches from external provider"
            )
        except Exception as exc:
            logger.warning(
                f"HybridProvider.get_competitions_from_matches_async: "
                f"external provider failed: {exc}"
            )

        # Extract unique competitions from match objects.
        # Matches produced by ProviderManagerAdapter carry competition_id
        # (fotmob numeric string) and _provider_competition_name (display name).
        seen: set = set()
        competitions: List[Competition] = []
        for match in provider_matches:
            comp_id = getattr(match, "competition_id", None)
            comp_name = getattr(match, "_provider_competition_name", None)
            if not comp_id or not comp_name:
                continue
            if comp_id in seen:
                continue
            seen.add(comp_id)
            competitions.append(
                Competition(
                    id=comp_id,
                    name=comp_name,
                    country=None,
                )
            )

        logger.info(
            f"HybridProvider.get_competitions_from_matches_async: "
            f"derived {len(competitions)} unique competitions from match schedule"
        )
        return competitions
    
    def get_provider_name(self) -> str:
        """Return the hybrid provider name."""
        return "HybridProvider"
    
    def get_competition(self, competition_id: str) -> Optional[Competition]:
        """Get competition, trying external providers first, then database.
        
        Args:
            competition_id: Competition ID
            
        Returns:
            Competition domain object or None if not found
        """
        # First try external providers
        try:
            competition = self.external_provider.get_competition(competition_id)
            if competition is not None:
                return competition
        except Exception:
            # External provider failed, continue to database fallback
            pass
        
        # If external providers fail, try database
        competitions = self.db_provider.get_competitions()
        for comp in competitions:
            if comp.id == competition_id:
                return comp
        return None
    
    def get_seasons(self, competition_id: str) -> List[Season]:
        """Get seasons, trying external providers first, then database.
        
        Args:
            competition_id: Competition ID
            
        Returns:
            List of Season objects
        """
        # First try external providers
        try:
            seasons = self.external_provider.get_seasons(competition_id)
            if seasons:
                return seasons
        except Exception:
            # External provider failed, continue to database fallback
            pass
        
        # Database fallback - return a default season if none found
        # This is a simple fallback for now
        return [Season(
            id="2024/25",
            competition_id=competition_id,
            year="2024/25",
            is_current=True
        )]
    
    def get_current_season(self, competition_id: str) -> Optional[Season]:
        """Get current season, trying external providers first, then database.
        
        Args:
            competition_id: Competition ID
            
        Returns:
            Current Season object or None if not found
        """
        # First try external providers
        try:
            season = self.external_provider.get_current_season(competition_id)
            if season is not None:
                return season
        except Exception:
            # External provider failed, continue to database fallback
            pass
        
        # Database fallback - return a default current season
        return Season(
            id="2024/25",
            competition_id=competition_id,
            year="2024/25",
            is_current=True
        )

    def get_teams(self, competition_id: str, season_id: Optional[str] = None) -> List[Team]:
        """Get teams, trying external providers first, then database.
        
        Args:
            competition_id: Competition ID
            season_id: Season ID
            
        Returns:
            List of Team objects
        """
        # First try external providers
        try:
            teams = self.external_provider.get_teams(competition_id, season_id)
            if teams:
                return teams
        except Exception:
            # External provider failed, continue to database fallback
            pass
        
        # If external providers fail, try database
        return self.db_provider.get_teams(competition_id, season_id)
    
    def _update_match_statuses(self, matches: List[Match]) -> List[Match]:
        """Update match statuses based on current time for stale SCHEDULED matches.
        
        REMOVED AUTO-FINISH LOGIC per code review:
        - Time-based auto-finish removed (was causing false positives)
        - Time threshold should only trigger refresh attempts, not status changes
        - Match status must come from provider data, not assumptions
        - Preserves all match fields including live data (minute, added_time, HT scores)
        
        This method now only ensures field preservation during status updates.
        External providers remain authoritative for status changes.
        """
        from datetime import datetime, timezone
        from app.domain.enums import MatchStatus
        import logging
        
        logger = logging.getLogger(__name__)
        updated_matches = []
        
        for match in matches:
            # Use model_copy if available (Pydantic v2), otherwise manual copy
            # This preserves ALL fields including minute, added_time, HT scores, outcome
            if hasattr(match, 'model_copy'):
                # Pydantic v2
                updated_match = match.model_copy(deep=False)
            elif hasattr(match, 'copy'):
                # Pydantic v1
                updated_match = match.copy(deep=False)
            else:
                # Manual copy preserving all domain model fields
                updated_match = Match(
                    id=match.id,
                    competition_id=match.competition_id,
                    season_id=match.season_id,
                    home_team_id=match.home_team_id,
                    away_team_id=match.away_team_id,
                    venue_id=match.venue_id,
                    scheduled_at=match.scheduled_at,
                    status=match.status,
                    home_score=match.home_score,
                    away_score=match.away_score,
                    home_score_ht=match.home_score_ht,
                    away_score_ht=match.away_score_ht,
                    minute=match.minute,
                    added_time=match.added_time,
                    outcome=match.outcome,
                    round=match.round,
                    created_at=match.created_at,
                    updated_at=match.updated_at,
                    provider_fetched_at=match.provider_fetched_at,
                )
            
            # NOTE: Removed automatic SCHEDULED -> FINISHED conversion
            # If match data is stale, the caller should trigger a provider refresh
            # rather than assuming the status based on elapsed time
            
            updated_matches.append(updated_match)
        
        return updated_matches
    
    def _update_single_match_status(self, match: Match) -> Match:
        """Update status for a single match."""
        if match is None:
            return None
        
        updated_matches = self._update_match_statuses([match])
        return updated_matches[0] if updated_matches else match