"""Provider Manager Adapter for FootballDataProvider interface.

This adapter wraps ProviderManager to expose the sync FootballDataProvider
interface required by the domain layer. It handles async-to-sync conversion
and maps ProviderXxx models to domain models.
"""

import asyncio
import logging
from datetime import date
from typing import List, Optional, Dict

from app.providers.base import FootballDataProvider
from app.providers.manager import ProviderManager
from app.domain.entities import Competition, Season, Team, Player, Venue
from app.domain.match import Match
from app.domain.statistics import Standing


logger = logging.getLogger(__name__)


class ProviderManagerAdapter(FootballDataProvider):
    """Adapter that wraps ProviderManager to implement FootballDataProvider.
    
    This adapter:
    1. Wraps async ProviderManager methods with asyncio.run()
    2. Maps ProviderXxx models to domain models
    3. Tracks provider metadata from last operation
    4. Exposes sync FootballDataProvider interface for domain layer
    
    Args:
        manager: ProviderManager instance to wrap
    """
    
    def __init__(self, manager: ProviderManager):
        """Initialize adapter with ProviderManager.
        
        Args:
            manager: ProviderManager instance
        """
        self._manager = manager
        self._last_metadata: Dict = {}
        
        logger.info("Initialized ProviderManagerAdapter")
    
    def get_provider_name(self) -> str:
        """Return the provider name from last operation.
        
        Returns:
            Provider name (e.g., 'ryzellx', 'fotmob', 'openligadb') or 'unknown'
        """
        return self._last_metadata.get('selected_provider', 'unknown')
    
    def is_development_data(self) -> bool:
        """Return False - this adapter uses real providers.
        
        Returns:
            False (real data providers)
        """
        return False
    
    async def _exec_async(self, coro):
        """Execute async coroutine and extract result and metadata.
        
        This helper runs an async coroutine, unpacks the (result, metadata) tuple,
        stores the metadata, and returns the result.
        
        Args:
            coro: Async coroutine that returns (result, metadata) tuple
            
        Returns:
            The result from the coroutine
        """
        result, metadata = await coro
        self._last_metadata = metadata
        return result
    
    def _exec(self, coro):
        """Execute async coroutine synchronously.
        
        Used for legacy sync code paths.
        
        Args:
            coro: Async coroutine that returns (result, metadata) tuple
            
        Returns:
            The result from the coroutine
        """
        # Check if we're already in an event loop
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context - but this is a sync method
            # Run in a new thread with its own event loop
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                result, metadata = future.result()
        except RuntimeError:
            # No running loop - safe to use asyncio.run()
            result, metadata = asyncio.run(coro)
        
        self._last_metadata = metadata
        return result
    
    # === Competition and Season ===
    
    def get_competitions(self) -> List[Competition]:
        """Get available competitions.
        
        NOT IMPLEMENTED: Multi-provider competition list not yet implemented.
        """
        raise NotImplementedError(
            "get_competitions not implemented in ProviderManagerAdapter - "
            "use specific provider or development provider"
        )
    
    def get_competition(self, competition_id: str) -> Optional[Competition]:
        """Get a specific competition by ID.
        
        NOT IMPLEMENTED: Multi-provider competition lookup not yet implemented.
        """
        raise NotImplementedError(
            "get_competition not implemented in ProviderManagerAdapter - "
            "use specific provider or development provider"
        )
    
    def get_seasons(self, competition_id: str) -> List[Season]:
        """Get seasons for a competition.
        
        NOT IMPLEMENTED: Multi-provider season list not yet implemented.
        """
        raise NotImplementedError(
            "get_seasons not implemented in ProviderManagerAdapter - "
            "use specific provider or development provider"
        )
    
    def get_current_season(self, competition_id: str) -> Optional[Season]:
        """Get the current season for a competition.
        
        NOT IMPLEMENTED: Multi-provider current season not yet implemented.
        """
        raise NotImplementedError(
            "get_current_season not implemented in ProviderManagerAdapter - "
            "use specific provider or development provider"
        )
    
    # === Teams ===
    
    def get_teams(self, competition_id: str, season_id: str) -> List[Team]:
        """Get teams in a competition season.
        
        NOT IMPLEMENTED: Multi-provider team list not yet implemented.
        """
        raise NotImplementedError(
            "get_teams not implemented in ProviderManagerAdapter - "
            "use specific provider or development provider"
        )
    
    def get_team(self, team_id: str) -> Optional[Team]:
        """Get a specific team by ID.
        
        Args:
            team_id: Team ID
            
        Returns:
            Team if found, None otherwise
        """
        provider_team = self._exec(self._manager.get_team(team_id))
        
        if provider_team is None:
            return None
        
        # Map ProviderTeam to domain Team
        return Team(
            id=provider_team.source_id,
            name=provider_team.name,
            short_name=provider_team.short_name,
            code=provider_team.code,
            country=provider_team.country,
            founded=provider_team.founded,
            venue_id=None,  # ProviderTeam doesn't have venue_id, only venue_name
            logo_url=provider_team.logo_url,
        )
    
    # === Matches ===
    
    async def get_matches_async(
        self,
        competition_id: Optional[str] = None,
        season_id: Optional[str] = None,
        team_id: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        status: Optional[str] = None,
    ) -> List[Match]:
        """Async version of get_matches for use from async contexts.
        
        Args:
            Same as get_matches
            
        Returns:
            List of matching fixtures
        """
        # If no date filters provided, use a default range (today and next 30 days)
        if from_date is None and to_date is None:
            from datetime import date, timedelta
            from_date = date.today()
            to_date = date.today() + timedelta(days=30)
            logger.debug(f"No date filters provided, using default range: {from_date} to {to_date}")
        elif from_date is None and to_date is not None:
            # If only to_date provided, set from_date to 30 days before
            from datetime import timedelta
            from_date = to_date - timedelta(days=30)
            logger.debug(f"Only to_date provided, setting from_date: {from_date}")
        elif from_date is not None and to_date is None:
            # If only from_date provided, set to_date to 30 days after
            from datetime import timedelta
            to_date = from_date + timedelta(days=30)
            logger.debug(f"Only from_date provided, setting to_date: {to_date}")
        
        # Determine query type
        if to_date == from_date:
            # Single date query
            logger.debug(f"Fetching matches for single date: {from_date}")
            provider_matches = await self._exec_async(
                self._manager.get_matches_by_date(from_date)
            )
        else:
            # Date range query
            logger.debug(f"Fetching matches for range: {from_date} to {to_date}")
            provider_matches = await self._exec_async(
                self._manager.get_matches_by_range(from_date, to_date)
            )
        
        # Map ProviderMatch list to domain Match list
        matches = []
        for pm in provider_matches:
            try:
                match = self._map_provider_match_to_domain(pm)
                matches.append(match)
            except Exception as e:
                logger.warning(
                    f"Failed to map provider match {pm.source_id} to domain: {e}"
                )
        
        # Apply all filters
        original_count = len(matches)
        
        if status:
            # Case-insensitive status comparison
            status_upper = status.upper()
            matches = [m for m in matches if m.status.value == status_upper]
            logger.debug(f"Filtered to {len(matches)} matches with status={status}")
        
        # CRITICAL FIX: Apply competition_id filter (was missing!)
        if competition_id:
            matches = [m for m in matches if m.competition_id == competition_id]
            logger.debug(f"Filtered to {len(matches)} matches with competition_id={competition_id}")
        
        # Apply season_id filter
        if season_id:
            matches = [m for m in matches if m.season_id == season_id]
            logger.debug(f"Filtered to {len(matches)} matches with season_id={season_id}")
        
        # Apply team_id filter (home or away)
        if team_id:
            matches = [m for m in matches if m.home_team_id == team_id or m.away_team_id == team_id]
            logger.debug(f"Filtered to {len(matches)} matches with team_id={team_id}")
        
        if original_count != len(matches):
            logger.debug(f"Applied filters: {original_count} -> {len(matches)} matches")
        
        # Log result
        logger.info(
            f"Returning {len(matches)} matches for date range "
            f"{from_date} to {to_date or from_date}"
        )
        
        return matches
    
    def get_matches(
        self,
        competition_id: Optional[str] = None,
        season_id: Optional[str] = None,
        team_id: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        status: Optional[str] = None,
    ) -> List[Match]:
        """Get matches with optional filters (sync version).
        
        Supports:
        - Single date query: from_date provided, to_date None or equal to from_date
        - Date range query: both from_date and to_date provided
        - Status filtering: applied after fetching matches
        
        NOT YET SUPPORTED:
        - competition_id, season_id, team_id filtering
        
        Args:
            competition_id: NOT IMPLEMENTED
            season_id: NOT IMPLEMENTED
            team_id: NOT IMPLEMENTED
            from_date: Fetch matches from this date
            to_date: Fetch matches up to this date (inclusive)
            status: Filter by match status (scheduled, live, finished, etc.)
            
        Returns:
            List of matching fixtures
        """
        # Use sync _exec for backward compatibility
        if from_date is None:
            raise NotImplementedError(
                "Date filter required - provide at least from_date parameter"
            )
        
        # Determine query type
        if to_date is None or to_date == from_date:
            # Single date query
            logger.debug(f"Fetching matches for single date: {from_date}")
            provider_matches = self._exec(
                self._manager.get_matches_by_date(from_date)
            )
        else:
            # Date range query
            logger.debug(f"Fetching matches for range: {from_date} to {to_date}")
            provider_matches = self._exec(
                self._manager.get_matches_by_range(from_date, to_date)
            )
        
        # Map ProviderMatch list to domain Match list
        matches = []
        for pm in provider_matches:
            try:
                match = self._map_provider_match_to_domain(pm)
                matches.append(match)
            except Exception as e:
                logger.warning(
                    f"Failed to map provider match {pm.source_id} to domain: {e}"
                )
        
        # Apply status filter if provided
        if status:
            # Case-insensitive status comparison
            status_upper = status.upper()
            matches = [m for m in matches if m.status.value == status_upper]
            logger.debug(f"Filtered to {len(matches)} matches with status={status}")
        
        # Log result
        logger.info(
            f"Returning {len(matches)} matches for date range "
            f"{from_date} to {to_date or from_date}"
        )
        
        return matches
    
    def get_match(self, match_id: str) -> Optional[Match]:
        """Get a specific match by ID.
        
        Supports prefixed match IDs in format "{provider}_{source_id}" 
        (e.g., "fotmob_5181855") by routing directly to the specific provider.
        Falls back to ProviderManager routing for unprefixed IDs.
        
        Args:
            match_id: Match ID (prefixed like "fotmob_5181855" or unprefixed)
            
        Returns:
            Match if found, None otherwise
        """
        # Check if match_id has format "{provider}_{source_id}"
        if '_' in match_id:
            parts = match_id.split('_', 1)
            if len(parts) == 2:
                provider_name, source_id = parts
                # Check if this is a known provider
                known_providers = ['fotmob', 'ryzellx', 'openligadb', 'sofascore']
                if provider_name in known_providers and provider_name in self._manager._providers:
                    # Route directly to specific provider
                    logger.debug(
                        f"Prefixed match ID detected: routing {match_id} to "
                        f"provider '{provider_name}' with source_id '{source_id}'"
                    )
                    try:
                        # Call provider directly with numeric ID
                        # Note: providers return just result, not (result, metadata) tuple
                        provider_match = self._exec_direct_provider(
                            provider_name, 
                            source_id
                        )
                        
                        if provider_match is None:
                            logger.debug(
                                f"Provider '{provider_name}' returned None for "
                                f"source_id '{source_id}'"
                            )
                            return None
                        
                        # Store metadata for this direct provider call
                        self._last_metadata = {
                            'selected_provider': provider_name,
                            'attempted_providers': [provider_name],
                            'routing_type': 'direct_prefixed_id'
                        }
                        
                        return self._map_provider_match_to_domain(provider_match)
                    
                    except Exception as e:
                        logger.warning(
                            f"Direct provider call failed for {match_id}: {e}, "
                            f"falling back to ProviderManager routing"
                        )
                        # Fall through to ProviderManager fallback
        
        # Fall back to ProviderManager routing for unprefixed IDs or if direct routing failed
        logger.debug(f"Using ProviderManager routing for match_id: {match_id}")
        provider_match = self._exec(self._manager.get_match(match_id))
        
        if provider_match is None:
            return None
        
        return self._map_provider_match_to_domain(provider_match)
    
    def _exec_direct_provider(self, provider_name: str, source_id: str):
        """Execute a direct provider call synchronously.
        
        Calls a specific provider's get_match() method directly.
        Unlike ProviderManager methods, individual providers return just the result,
        not a (result, metadata) tuple.
        
        Args:
            provider_name: Name of the provider (e.g., 'fotmob')
            source_id: The numeric source ID for the match
            
        Returns:
            ProviderMatch if found, None otherwise
        """
        provider = self._manager._providers[provider_name]
        coro = provider.get_match(source_id)
        
        # Check if we're already in an event loop
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context - run in a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                result = future.result()
        except RuntimeError:
            # No running loop - safe to use asyncio.run()
            result = asyncio.run(coro)
        
        return result
    
    def _map_provider_match_to_domain(self, pm) -> Match:
        """Map ProviderMatch to domain Match.
        
        Args:
            pm: ProviderMatch instance
            
        Returns:
            Domain Match instance with _provider_team_names attribute
        """
        # Generate match ID from provider and source_id
        match_id = f"{pm.provider}_{pm.source_id}"
        
        # Competition and season IDs
        # Use provider's IDs if available, otherwise generate from names
        competition_id = pm.competition_id or f"{pm.provider}_comp_{pm.competition_name}"
        season_id = pm.season or "unknown_season"
        
        # Team IDs - use provider's IDs or generate from names
        home_team_id = pm.home_team_id or f"{pm.provider}_team_{pm.home_team_name}"
        away_team_id = pm.away_team_id or f"{pm.provider}_team_{pm.away_team_name}"
        
        # Venue ID - generate from name if available
        venue_id = None
        if pm.venue_name:
            venue_id = f"{pm.provider}_venue_{pm.venue_name}"
        
        match = Match(
            id=match_id,
            competition_id=competition_id,
            season_id=season_id,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            venue_id=venue_id,
            scheduled_at=pm.scheduled_at,
            status=pm.status,
            home_score=pm.home_score,
            away_score=pm.away_score,
            home_score_ht=pm.home_score_ht,
            away_score_ht=pm.away_score_ht,
            minute=pm.minute,
            added_time=pm.added_time,
            outcome=pm.outcome,
            round=pm.round,
        )
        
        # Store provider team names as private attribute for use by API layer
        # This avoids modifying the domain model while preserving names from provider
        match._provider_home_team_name = pm.home_team_name
        match._provider_away_team_name = pm.away_team_name
        match._provider_competition_name = pm.competition_name
        
        return match
    
    # === Statistics ===
    
    def _extract_source_id_from_match_id(self, match_id: str) -> Optional[str]:
        """Extract the numeric source ID from a match ID.
        
        Match IDs are formatted as '{provider}_{source_id}', e.g., 'fotmob_12345'.
        
        Args:
            match_id: Full match ID with provider prefix
            
        Returns:
            Numeric source ID or None if extraction fails
        """
        if '_' in match_id:
            parts = match_id.split('_', 1)
            if len(parts) == 2:
                return parts[1]
        # If no underscore, assume the match_id itself is the source ID
        return match_id
    
    def _map_provider_stats_to_domain(self, provider_stats, team_id: str, match_id: str) -> "TeamMatchStatistic":
        """Map ProviderMatchStats to domain TeamMatchStatistic.
        
        Args:
            provider_stats: ProviderMatchStats instance
            team_id: Team ID to use in domain model
            match_id: Match ID
            
        Returns:
            TeamMatchStatistic domain model
        """
        from app.domain.statistics import TeamMatchStatistic
        
        return TeamMatchStatistic(
            id=f"{match_id}_{team_id}",
            match_id=match_id,
            team_id=team_id,
            goals_scored=provider_stats.goals_scored or 0,
            goals_conceded=provider_stats.goals_conceded or 0,
            xg=provider_stats.xg,
            xg_against=provider_stats.xg_against,
            shots_total=provider_stats.shots_total,
            shots_on_target=provider_stats.shots_on_target,
            shots_off_target=provider_stats.shots_off_target,
            shots_blocked=provider_stats.shots_blocked,
            possession_percentage=provider_stats.possession_percentage,
            passes_completed=provider_stats.passes_completed,
            passes_attempted=provider_stats.passes_attempted,
            pass_accuracy=provider_stats.pass_accuracy,
            corners=provider_stats.corners,
            free_kicks=provider_stats.free_kicks,
            offsides=provider_stats.offsides,
            yellow_cards=provider_stats.yellow_cards or 0,
            red_cards=provider_stats.red_cards or 0,
            fouls_committed=provider_stats.fouls_committed,
            tackles=provider_stats.tackles,
            interceptions=provider_stats.interceptions,
            clearances=provider_stats.clearances,
            saves=provider_stats.saves,
        )
    
    def get_team_match_statistics(self, match_id: str) -> List["TeamMatchStatistic"]:
        """Get team statistics for a match.
        
        Fetches statistics from FotMob provider and maps to domain models.
        
        Args:
            match_id: Match ID (format: '{provider}_{source_id}')
            
        Returns:
            List of TeamMatchStatistic objects (home and away)
        """
        from app.domain.statistics import TeamMatchStatistic
        
        # Extract source ID for FotMob API call
        source_id = self._extract_source_id_from_match_id(match_id)
        if not source_id:
            logger.warning(f"Could not extract source_id from match_id: {match_id}")
            return []
        
        # Determine which provider this match belongs to
        provider_name = match_id.split('_')[0] if '_' in match_id else 'fotmob'
        
        # Try to get statistics from FotMob provider
        try:
            # Call the async method using asyncio.run() directly
            # Note: FotMob's get_match_statistics returns (home_stats, away_stats), not (result, metadata)
            result = asyncio.run(
                self._manager._providers['fotmob'].get_match_statistics(source_id)
            )
            
            if result is None:
                return []
            
            home_provider_stats, away_provider_stats = result
            
            home_provider_stats, away_provider_stats = result
            
            # Convert to domain models
            domain_stats = []
            
            if home_provider_stats:
                # Use home team ID from the provider stats
                home_team_id = home_provider_stats.team_id or f"fotmob_{source_id}_home"
                domain_stats.append(
                    self._map_provider_stats_to_domain(home_provider_stats, home_team_id, match_id)
                )
            
            if away_provider_stats:
                # Use away team ID from the provider stats
                away_team_id = away_provider_stats.team_id or f"fotmob_{source_id}_away"
                domain_stats.append(
                    self._map_provider_stats_to_domain(away_provider_stats, away_team_id, match_id)
                )
            
            return domain_stats
            
        except Exception as e:
            logger.warning(f"get_team_match_statistics failed for {match_id}: {e}")
            return []
    
    def get_team_match_statistics_firsthalf(self, match_id: str) -> List["TeamMatchStatistic"]:
        """Get first-half team statistics for a match.
        
        Note: FotMob does not provide period-specific statistics via get_match_statistics.
        This method returns an empty list as first-half statistics are not available
        from the current provider implementation.
        
        Args:
            match_id: Match ID
            
        Returns:
            Empty list (first-half statistics not available from FotMob)
        """
        # FotMob's get_match_statistics returns only full-match statistics.
        # First-half specific statistics would require separate API calls or
        # parsing live match data which is not currently implemented.
        logger.debug(f"get_team_match_statistics_firsthalf: not available from FotMob for {match_id}")
        return []
    
    def get_standings(self, competition_id: str, season_id: str) -> List[Standing]:
        """Get league standings.
        
        NOT YET IMPLEMENTED: Multi-provider standings not yet mapped to domain.
        """
        raise NotImplementedError(
            "get_standings not yet implemented in ProviderManagerAdapter - "
            "use specific provider or development provider"
        )
