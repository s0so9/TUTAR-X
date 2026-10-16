"""Provider Manager for intelligent multi-provider routing.

The ProviderManager orchestrates multiple football data providers with
intelligent routing based on data type and use case:

- NORMAL_ORDER: Standard match lists and fixtures (ryzellx → openligadb)
- LIVE_ORDER: Live/fast data (fotmob → sofascore → ryzellx → openligadb)
- MATCH_DETAIL_ORDER: Match detail with stats (sofascore → ryzellx → fotmob → openligadb)
- METADATA_ORDER: Teams, players, leagues (ryzellx → fotmob → openligadb)

SOURCE-OF-TRUTH RULE:
Once a provider returns a result (non-None), that is the final result.
NO field-level failover. If sofascore returns a match with xg=None, we do NOT
try fotmob to get xG. This prevents data inconsistency where different fields
come from different sources with different timestamps.
"""

import logging
from datetime import datetime, date, timezone
from typing import List, Optional, Dict, Any, Tuple, Callable

from app.providers.exceptions import ProviderError


logger = logging.getLogger(__name__)


class ProviderManager:
    """Manager for orchestrating multiple football data providers.
    
    This manager implements intelligent routing across multiple providers based
    on data type and use case. It handles failover, error handling, and metadata
    tracking for all provider operations.
    
    SOURCE-OF-TRUTH RULE:
    One provider per response. Once a provider returns a result, that is the
    source of truth - no failover for missing optional fields.
    
    Args:
        ryzellx: RyzellxFootballProvider instance (PRIMARY provider)
        fotmob: FotMobFootballProvider instance (LIVE/FAST provider)
        sofascore: SofaScoreFootballProvider instance (STATISTICS provider)
        openligadb: OpenLigaDBFootballProvider instance (FALLBACK provider)
        cache: Optional ProviderCache (passed to individual providers)
    """
    
    # Routing constants - define provider order for different operations
    NORMAL_ORDER = ['ryzellx', 'openligadb']
    LIVE_ORDER = ['fotmob', 'sofascore', 'ryzellx', 'openligadb']
    MATCH_DETAIL_ORDER = ['sofascore', 'ryzellx', 'fotmob', 'openligadb']
    METADATA_ORDER = ['ryzellx', 'fotmob', 'openligadb']
    
    def __init__(self, ryzellx, fotmob, openligadb, sofascore=None, cache=None):
        """Initialize ProviderManager with provider instances.
        
        Args:
            ryzellx: RyzellxFootballProvider instance
            fotmob: FotMobFootballProvider instance
            openligadb: OpenLigaDBFootballProvider instance
            sofascore: Optional SofaScoreFootballProvider instance
            cache: Optional ProviderCache (for tracking only, providers use their own)
        """
        self._providers = {
            'ryzellx': ryzellx,
            'fotmob': fotmob,
            'openligadb': openligadb,
        }
        if sofascore is not None:
            self._providers['sofascore'] = sofascore
        self.cache = cache
        
        logger.info(
            f"Initialized ProviderManager with providers: "
            f"{', '.join(self._providers.keys())}"
        )
    
    async def close(self):
        """Close all provider HTTP clients."""
        for name, provider in self._providers.items():
            try:
                await provider.close()
                logger.debug(f"Closed provider: {name}")
            except Exception as e:
                logger.warning(f"Error closing provider {name}: {e}")
    
    async def _try_providers(
        self,
        operation_name: str,
        provider_order: List[str],
        provider_method_map: Dict[str, Callable]
    ) -> Tuple[Optional[Any], Dict]:
        """Try providers in order until one succeeds.
        
        This is the core routing logic. It tries providers in the specified
        order and returns the first successful result.
        
        SOURCE-OF-TRUTH RULE:
        Once a provider returns non-None, return immediately. Do NOT try
        subsequent providers even if the result has missing optional fields.
        
        Args:
            operation_name: Name of operation for logging (e.g., 'get_match')
            provider_order: List of provider names in priority order
            provider_method_map: Dict mapping provider names to async callables
            
        Returns:
            Tuple of (result, metadata_dict) where:
            - result: The result from the first successful provider, or None
            - metadata_dict: Dict with keys:
                - selected_provider: Name of provider that returned result
                - attempted_providers: List of provider names attempted
                - fallback_used: True if not the first provider
                - fetched_at: Timestamp
        """
        metadata = {
            'selected_provider': None,
            'attempted_providers': [],
            'fallback_used': False,
            'fetched_at': datetime.now(timezone.utc),
        }
        
        for i, provider_name in enumerate(provider_order):
            # Check if this provider implements the operation
            if provider_name not in provider_method_map:
                continue
            
            provider_method = provider_method_map[provider_name]
            metadata['attempted_providers'].append(provider_name)
            
            try:
                logger.debug(
                    f"[ProviderManager] {operation_name}: "
                    f"trying provider '{provider_name}'"
                )
                
                # Call the provider method
                result = await provider_method()
                
                # SOURCE-OF-TRUTH CHECK: If result is not None, use it
                if result is not None:
                    metadata['selected_provider'] = provider_name
                    metadata['fallback_used'] = (i > 0)
                    
                    logger.info(
                        f"[ProviderManager] {operation_name}: "
                        f"success from provider '{provider_name}'"
                        f"{' (fallback)' if metadata['fallback_used'] else ''}"
                    )
                    
                    return (result, metadata)
                else:
                    logger.debug(
                        f"[ProviderManager] {operation_name}: "
                        f"provider '{provider_name}' returned None"
                    )
            
            except ProviderError as e:
                # Provider raised an error - log and try next provider
                logger.warning(
                    f"[ProviderManager] {operation_name}: "
                    f"provider '{provider_name}' raised {type(e).__name__}: {e.message}"
                )
                # Continue to next provider
            
            except Exception as e:
                # Unexpected error - log and try next provider
                logger.error(
                    f"[ProviderManager] {operation_name}: "
                    f"provider '{provider_name}' raised unexpected error: {type(e).__name__}"
                )
                # Continue to next provider
        
        # All providers failed or returned None
        logger.warning(
            f"[ProviderManager] {operation_name}: "
            f"all providers failed or returned None (attempted: {metadata['attempted_providers']})"
        )
        
        return (None, metadata)
    
    async def get_matches_by_date(self, date_obj: date) -> Tuple[List, Dict]:
        """Get matches for a specific date.
        
        Uses NORMAL_ORDER: ryzellx → openligadb
        
        Args:
            date_obj: Date to fetch matches for
            
        Returns:
            Tuple of (matches_list, metadata_dict)
        """
        provider_method_map = {}

        # Only add providers that are not None
        if self._providers.get('ryzellx'):
            provider_method_map['ryzellx'] = lambda: self._providers['ryzellx'].get_matches_by_date(date_obj)
        if self._providers.get('fotmob'):
            provider_method_map['fotmob'] = lambda: self._providers['fotmob'].get_matches_by_date(date_obj)
        if self._providers.get('openligadb'):
            provider_method_map['openligadb'] = lambda: self._providers['openligadb'].get_matches_by_date(date_obj)

        # Use extended order that includes fotmob
        provider_order = ['ryzellx', 'fotmob', 'openligadb']

        result, metadata = await self._try_providers(
            operation_name='get_matches_by_date',
            provider_order=provider_order,
            provider_method_map=provider_method_map
        )
        
        # Return empty list if no provider succeeded
        return (result if result is not None else [], metadata)
    
    async def get_matches_by_range(
        self,
        start_date: date,
        end_date: date
    ) -> Tuple[List, Dict]:
        """Get matches in date range.
        
        Uses extended order: ryzellx → fotmob → openligadb
        
        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            
        Returns:
            Tuple of (matches_list, metadata_dict)
        """
        provider_method_map = {}

        # Only add providers that are not None
        if self._providers.get('ryzellx'):
            provider_method_map['ryzellx'] = lambda: self._providers['ryzellx'].get_matches_by_range(start_date, end_date)
        if self._providers.get('fotmob'):
            provider_method_map['fotmob'] = lambda: self._providers['fotmob'].get_matches_by_range(start_date, end_date)
        if self._providers.get('openligadb'):
            provider_method_map['openligadb'] = lambda: self._providers['openligadb'].get_matches_by_range(start_date, end_date)

        # Use extended order that includes fotmob
        provider_order = ['ryzellx', 'fotmob', 'openligadb']

        result, metadata = await self._try_providers(
            operation_name='get_matches_by_range',
            provider_order=provider_order,
            provider_method_map=provider_method_map
        )
        
        # Return empty list if no provider succeeded
        return (result if result is not None else [], metadata)
    
    async def get_match(self, match_id: str) -> Tuple[Optional[Any], Dict]:
        """Get detailed match information.
        
        Uses MATCH_DETAIL_ORDER: sofascore → ryzellx → fotmob → openligadb
        
        Args:
            match_id: Match ID
            
        Returns:
            Tuple of (ProviderMatch or None, metadata_dict)
        """
        provider_method_map = {}
        
        if 'sofascore' in self._providers:
            provider_method_map['sofascore'] = lambda: self._providers['sofascore'].get_match(match_id)
        
        provider_method_map.update({
            'ryzellx': lambda: self._providers['ryzellx'].get_match(match_id),
            'fotmob': lambda: self._providers['fotmob'].get_match(match_id),
            'openligadb': lambda: self._providers['openligadb'].get_match(match_id),
        })
        
        return await self._try_providers(
            operation_name='get_match',
            provider_order=self.MATCH_DETAIL_ORDER,
            provider_method_map=provider_method_map
        )
    
    async def get_live_matches(self) -> Tuple[List, Dict]:
        """Get currently live matches.
        
        Uses LIVE_ORDER: fotmob → sofascore → ryzellx → openligadb
        
        Returns:
            Tuple of (live_matches_list, metadata_dict)
        """
        provider_method_map = {
            'fotmob': lambda: self._providers['fotmob'].get_live_matches(),
            'ryzellx': lambda: self._providers['ryzellx'].get_live_matches(),
            'openligadb': lambda: self._providers['openligadb'].get_live_matches(),
        }
        
        if 'sofascore' in self._providers:
            provider_method_map['sofascore'] = lambda: self._providers['sofascore'].get_live_matches()
        
        result, metadata = await self._try_providers(
            operation_name='get_live_matches',
            provider_order=self.LIVE_ORDER,
            provider_method_map=provider_method_map
        )
        
        # Return empty list if no provider succeeded
        return (result if result is not None else [], metadata)
    
    async def get_team(self, team_id: str) -> Tuple[Optional[Any], Dict]:
        """Get team information.
        
        Uses METADATA_ORDER: ryzellx → fotmob → openligadb
        
        Args:
            team_id: Team ID
            
        Returns:
            Tuple of (ProviderTeam or None, metadata_dict)
        """
        provider_method_map = {
            'ryzellx': lambda: self._providers['ryzellx'].get_team(team_id),
            'fotmob': lambda: self._providers['fotmob'].get_team(team_id),
            'openligadb': lambda: self._providers['openligadb'].get_team(team_id),
        }
        
        return await self._try_providers(
            operation_name='get_team',
            provider_order=self.METADATA_ORDER,
            provider_method_map=provider_method_map
        )
    
    async def get_player(self, player_id: str) -> Tuple[Optional[Any], Dict]:
        """Get player information.
        
        Uses METADATA_ORDER: ryzellx → fotmob → openligadb
        
        Args:
            player_id: Player ID
            
        Returns:
            Tuple of (ProviderPlayer or None, metadata_dict)
        """
        provider_method_map = {
            'ryzellx': lambda: self._providers['ryzellx'].get_player(player_id),
            'fotmob': lambda: self._providers['fotmob'].get_player(player_id),
            'openligadb': lambda: self._providers['openligadb'].get_player(player_id),
        }
        
        return await self._try_providers(
            operation_name='get_player',
            provider_order=self.METADATA_ORDER,
            provider_method_map=provider_method_map
        )
    
    async def get_league(self, league_id: str) -> Tuple[Optional[Any], Dict]:
        """Get league/competition information.
        
        Uses METADATA_ORDER: ryzellx → fotmob → openligadb
        
        Args:
            league_id: League ID
            
        Returns:
            Tuple of (ProviderCompetition or None, metadata_dict)
        """
        provider_method_map = {
            'ryzellx': lambda: self._providers['ryzellx'].get_league(league_id),
            'fotmob': lambda: self._providers['fotmob'].get_league(league_id),
            'openligadb': lambda: self._providers['openligadb'].get_league(league_id),
        }
        
        return await self._try_providers(
            operation_name='get_league',
            provider_order=self.METADATA_ORDER,
            provider_method_map=provider_method_map
        )
    
    async def get_standings(self, league_id: str) -> Tuple[List, Dict]:
        """Get league standings/table.
        
        Uses METADATA_ORDER: ryzellx → fotmob → openligadb
        
        Args:
            league_id: League ID
            
        Returns:
            Tuple of (standings_list, metadata_dict)
        """
        provider_method_map = {
            'ryzellx': lambda: self._providers['ryzellx'].get_standings(league_id),
            'fotmob': lambda: self._providers['fotmob'].get_standings(league_id),
            'openligadb': lambda: self._providers['openligadb'].get_standings(league_id),
        }
        
        result, metadata = await self._try_providers(
            operation_name='get_standings',
            provider_order=self.METADATA_ORDER,
            provider_method_map=provider_method_map
        )
        
        # Return empty list if no provider succeeded
        return (result if result is not None else [], metadata)
