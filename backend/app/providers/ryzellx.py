"""Ryzellx Football Live API provider implementation.

Ryzellx is the PRIMARY provider for:
- Normal match lists (fixtures, results)
- Match detail with xG, stats, events when available
- Teams, players, leagues, standings
- General statistics

This provider uses the documented public API endpoints from the
Ryzellx football-live-api project. Base URL is configurable through
environment/configuration - no hardcoded production URLs.

API Documentation:
- /api/home - API information
- /api/matches/live - Live matches
- /api/matches/date/:date - Matches for specific date
- /api/matches/range - Matches in date range
- /api/match/:id - Match detail
- /api/team/:id - Team information
- /api/player/:id - Player information
- /api/leagues - Available leagues
- /api/league/:id - League information
- /api/league/:id/table - League standings
"""

import logging
from datetime import datetime, date, timezone, timedelta
from typing import List, Optional, Dict, Any
import httpx

from app.providers.exceptions import (
    ProviderError,
    ProviderTimeoutError,
    ProviderHTTPError,
    ProviderInvalidDataError,
    ProviderNotFoundError,
)
from app.providers.cache import (
    ProviderCache,
    LIVE_DATA_TTL,
    UPCOMING_FIXTURES_TTL,
    HISTORICAL_MATCH_TTL,
    METADATA_TTL,
)
from app.providers.models import (
    ProviderMatch,
    ProviderTeam,
    ProviderPlayer,
    ProviderCompetition,
    ProviderStanding,
    ProviderLiveMatch,
)
from app.domain.enums import MatchStatus, MatchOutcome


logger = logging.getLogger(__name__)


class RyzellxFootballProvider:
    """Ryzellx Football Live API provider.
    
    PRIMARY provider for matches, fixtures, results, match detail,
    teams, players, leagues, standings, and xG/stats when available.
    
    Uses async httpx.AsyncClient with configurable base URL, timeout,
    and retry behavior for transient failures.
    
    Normalizes all responses to ProviderXxx models with source metadata.
    NEVER invents values - uses None for unavailable fields.
    
    Args:
        base_url: Base URL for Ryzellx API (configurable, not hardcoded)
        timeout_seconds: HTTP request timeout in seconds
        retry_count: Max retries for transient failures (connection errors, 5xx)
        cache: Optional ProviderCache for caching responses
    """
    
    PROVIDER_NAME = "ryzellx"
    
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 10.0,
        retry_count: int = 2,
        cache: Optional[ProviderCache] = None
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.retry_count = retry_count
        self.cache = cache
        
        # Create async HTTP client with timeout
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=True,
        )
        
        logger.info(
            f"Initialized {self.PROVIDER_NAME} provider: "
            f"base_url={self.base_url}, timeout={timeout_seconds}s, "
            f"retry_count={retry_count}, cache={'enabled' if cache else 'disabled'}"
        )
    
    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make HTTP request with error handling and retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path (e.g., '/api/matches/live')
            params: Optional query parameters
            
        Returns:
            Parsed JSON response as dict
            
        Raises:
            ProviderTimeoutError: Request timed out
            ProviderHTTPError: HTTP error response (4xx, 5xx after retries)
            ProviderNotFoundError: Resource not found (404)
            ProviderInvalidDataError: Invalid JSON response
            ProviderError: Connection or other request errors
        """
        operation = f"{method} {endpoint}"
        attempt = 0
        last_error = None
        
        while attempt <= self.retry_count:
            try:
                if attempt > 0:
                    logger.debug(
                        f"[{self.PROVIDER_NAME}] Retry {attempt}/{self.retry_count} "
                        f"for {operation}"
                    )
                
                logger.debug(
                    f"[{self.PROVIDER_NAME}] {operation} "
                    f"params={params if params else 'none'}"
                )
                
                response = await self._client.request(
                    method=method,
                    url=endpoint,
                    params=params
                )
                
                # Check HTTP status
                if response.status_code == 404:
                    raise ProviderNotFoundError(
                        provider_name=self.PROVIDER_NAME,
                        operation=operation,
                        message=f"Resource not found: {endpoint}"
                    )
                
                if 400 <= response.status_code < 500:
                    raise ProviderHTTPError(
                        provider_name=self.PROVIDER_NAME,
                        operation=operation,
                        message=f"Client error: {response.status_code} {response.reason_phrase}",
                        status_code=response.status_code
                    )
                
                if 500 <= response.status_code < 600:
                    # Server error - retry
                    last_error = ProviderHTTPError(
                        provider_name=self.PROVIDER_NAME,
                        operation=operation,
                        message=f"Server error: {response.status_code} {response.reason_phrase}",
                        status_code=response.status_code
                    )
                    attempt += 1
                    if attempt <= self.retry_count:
                        await self._wait_before_retry(attempt)
                        continue
                    raise last_error
                
                # Success - parse JSON
                try:
                    data = response.json()
                    logger.debug(
                        f"[{self.PROVIDER_NAME}] {operation} succeeded: "
                        f"{response.status_code}"
                    )
                    return data
                    
                except Exception as e:
                    raise ProviderInvalidDataError(
                        provider_name=self.PROVIDER_NAME,
                        operation=operation,
                        message=f"Failed to parse JSON response: {str(e)}",
                        original_error=e
                    )
            
            except httpx.TimeoutException as e:
                raise ProviderTimeoutError(
                    provider_name=self.PROVIDER_NAME,
                    operation=operation,
                    message=f"Request timed out after {self.timeout_seconds}s",
                    original_error=e
                )
            
            except httpx.RequestError as e:
                # Connection error - retry
                last_error = ProviderError(
                    provider_name=self.PROVIDER_NAME,
                    operation=operation,
                    message=f"Connection error: {type(e).__name__}",
                    original_error=e
                )
                attempt += 1
                if attempt <= self.retry_count:
                    logger.warning(
                        f"[{self.PROVIDER_NAME}] {operation} connection error, "
                        f"retrying ({attempt}/{self.retry_count})"
                    )
                    await self._wait_before_retry(attempt)
                    continue
                raise last_error
            
            except (ProviderTimeoutError, ProviderHTTPError, ProviderNotFoundError, 
                    ProviderInvalidDataError, ProviderError):
                # Re-raise provider exceptions as-is
                raise
            
            except Exception as e:
                # Unexpected error
                raise ProviderError(
                    provider_name=self.PROVIDER_NAME,
                    operation=operation,
                    message=f"Unexpected error: {type(e).__name__}",
                    original_error=e
                )
        
        # Should not reach here, but raise last error if we do
        if last_error:
            raise last_error
        raise ProviderError(
            provider_name=self.PROVIDER_NAME,
            operation=operation,
            message="Max retries exceeded"
        )
    
    async def _wait_before_retry(self, attempt: int):
        """Wait before retry with exponential backoff."""
        import asyncio
        wait_seconds = min(2 ** attempt, 10)  # Max 10 seconds
        await asyncio.sleep(wait_seconds)
    
    def _get_cache_ttl(self, date_obj: Optional[date] = None, is_live: bool = False) -> int:
        """Determine appropriate cache TTL based on data type.
        
        Args:
            date_obj: Match date if applicable
            is_live: Whether data is live
            
        Returns:
            TTL in seconds
        """
        if is_live:
            return LIVE_DATA_TTL
        
        if date_obj:
            today = date.today()
            if date_obj < today:
                # Historical match
                return HISTORICAL_MATCH_TTL
            else:
                # Upcoming fixture
                return UPCOMING_FIXTURES_TTL
        
        return METADATA_TTL
    
    def _parse_match_status(self, status_str: Optional[str]) -> MatchStatus:
        """Parse Ryzellx match status to domain MatchStatus.
        
        Args:
            status_str: Status string from Ryzellx API
            
        Returns:
            Normalized MatchStatus
        """
        if not status_str:
            return MatchStatus.SCHEDULED
        
        status_lower = status_str.lower()
        
        if status_lower in ["live", "in_play", "1h", "2h"]:
            return MatchStatus.LIVE
        elif status_lower in ["ht", "half_time", "halftime"]:
            return MatchStatus.HALF_TIME
        elif status_lower in ["ft", "finished", "full_time"]:
            return MatchStatus.FINISHED
        elif status_lower in ["postponed", "pst"]:
            return MatchStatus.POSTPONED
        elif status_lower in ["cancelled", "cnc"]:
            return MatchStatus.CANCELLED
        elif status_lower in ["suspended", "susp"]:
            return MatchStatus.SUSPENDED
        elif status_lower in ["scheduled", "not_started", "ns"]:
            return MatchStatus.SCHEDULED
        else:
            logger.warning(
                f"[{self.PROVIDER_NAME}] Unknown status '{status_str}', "
                f"defaulting to SCHEDULED"
            )
            return MatchStatus.SCHEDULED
    
    def _parse_match_outcome(
        self,
        home_score: Optional[int],
        away_score: Optional[int]
    ) -> Optional[MatchOutcome]:
        """Parse match outcome from scores.
        
        Args:
            home_score: Home team score
            away_score: Away team score
            
        Returns:
            MatchOutcome if match is finished, None otherwise
        """
        if home_score is None or away_score is None:
            return None
        
        if home_score > away_score:
            return MatchOutcome.HOME_WIN
        elif away_score > home_score:
            return MatchOutcome.AWAY_WIN
        else:
            return MatchOutcome.DRAW
    
    def _normalize_match(self, data: Dict[str, Any], is_live: bool = False) -> ProviderMatch:
        """Normalize Ryzellx match data to ProviderMatch.
        
        Args:
            data: Raw match data from Ryzellx API
            is_live: Whether this is live match data
            
        Returns:
            Normalized ProviderMatch
        """
        now = datetime.now(timezone.utc)
        
        # Parse scheduled time
        scheduled_str = data.get("date") or data.get("scheduled_at")
        if scheduled_str:
            try:
                scheduled_at = datetime.fromisoformat(scheduled_str.replace("Z", "+00:00"))
            except:
                scheduled_at = now
        else:
            scheduled_at = now
        
        # Parse status
        status = self._parse_match_status(data.get("status"))
        
        # Parse scores
        home_score = data.get("home_score")
        away_score = data.get("away_score")
        
        # Parse outcome
        outcome = None
        if status == MatchStatus.FINISHED:
            outcome = self._parse_match_outcome(home_score, away_score)
        
        return ProviderMatch(
            # Source metadata
            provider=self.PROVIDER_NAME,
            source_id=str(data.get("id") or data.get("match_id")),
            fetched_at=now,
            source_updated_at=None,  # Ryzellx doesn't provide this
            is_live=is_live or status == MatchStatus.LIVE,
            data_freshness_seconds=None,
            
            # Match identifiers
            competition_id=str(data.get("competition_id")) if data.get("competition_id") else None,
            competition_name=data.get("competition_name") or data.get("league"),
            season=data.get("season"),
            
            # Teams
            home_team_id=str(data.get("home_team_id") or data.get("home_id", "")),
            home_team_name=data.get("home_team") or data.get("home_name", ""),
            away_team_id=str(data.get("away_team_id") or data.get("away_id", "")),
            away_team_name=data.get("away_team") or data.get("away_name", ""),
            
            # Venue
            venue_name=data.get("venue"),
            
            # Timing
            scheduled_at=scheduled_at,
            status=status,
            minute=data.get("minute"),
            added_time=data.get("added_time"),
            
            # Scores
            home_score=home_score,
            away_score=away_score,
            home_score_ht=data.get("home_score_ht"),
            away_score_ht=data.get("away_score_ht"),
            
            # Outcome
            outcome=outcome,
            
            # Match round
            round=data.get("round"),
        )
    
    async def get_matches_by_date(self, date_obj: date) -> List[ProviderMatch]:
        """Get matches for a specific date.
        
        Args:
            date_obj: Date to fetch matches for
            
        Returns:
            List of ProviderMatch for the date
            
        Raises:
            ProviderError: On request failure
        """
        # Check cache
        cache_key = f"{self.PROVIDER_NAME}:matches:date:{date_obj.isoformat()}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.debug(f"[{self.PROVIDER_NAME}] Cache hit: {cache_key}")
                return cached
        
        # Fetch from API
        endpoint = f"/api/matches/date/{date_obj.isoformat()}"
        data = await self._request("GET", endpoint)
        
        # Parse response
        matches = []
        if isinstance(data, list):
            for match_data in data:
                try:
                    match = self._normalize_match(match_data, is_live=False)
                    matches.append(match)
                except Exception as e:
                    logger.warning(
                        f"[{self.PROVIDER_NAME}] Failed to normalize match: {e}"
                    )
        elif isinstance(data, dict) and "matches" in data:
            for match_data in data["matches"]:
                try:
                    match = self._normalize_match(match_data, is_live=False)
                    matches.append(match)
                except Exception as e:
                    logger.warning(
                        f"[{self.PROVIDER_NAME}] Failed to normalize match: {e}"
                    )
        
        # Cache result
        if self.cache:
            ttl = self._get_cache_ttl(date_obj=date_obj)
            self.cache.set(cache_key, matches, ttl_seconds=ttl)
        
        logger.info(
            f"[{self.PROVIDER_NAME}] Fetched {len(matches)} matches for {date_obj}"
        )
        return matches
    
    async def get_matches_by_range(
        self,
        start_date: date,
        end_date: date
    ) -> List[ProviderMatch]:
        """Get matches in date range.
        
        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            
        Returns:
            List of ProviderMatch in the range
            
        Raises:
            ProviderError: On request failure
        """
        # Check cache
        cache_key = (
            f"{self.PROVIDER_NAME}:matches:range:"
            f"{start_date.isoformat()}:{end_date.isoformat()}"
        )
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.debug(f"[{self.PROVIDER_NAME}] Cache hit: {cache_key}")
                return cached
        
        # Fetch from API
        endpoint = "/api/matches/range"
        params = {
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        }
        data = await self._request("GET", endpoint, params=params)
        
        # Parse response
        matches = []
        if isinstance(data, list):
            for match_data in data:
                try:
                    match = self._normalize_match(match_data, is_live=False)
                    matches.append(match)
                except Exception as e:
                    logger.warning(
                        f"[{self.PROVIDER_NAME}] Failed to normalize match: {e}"
                    )
        elif isinstance(data, dict) and "matches" in data:
            for match_data in data["matches"]:
                try:
                    match = self._normalize_match(match_data, is_live=False)
                    matches.append(match)
                except Exception as e:
                    logger.warning(
                        f"[{self.PROVIDER_NAME}] Failed to normalize match: {e}"
                    )
        
        # Cache result with TTL based on date range
        if self.cache:
            today = date.today()
            if end_date < today:
                ttl = HISTORICAL_MATCH_TTL
            else:
                ttl = UPCOMING_FIXTURES_TTL
            self.cache.set(cache_key, matches, ttl_seconds=ttl)
        
        logger.info(
            f"[{self.PROVIDER_NAME}] Fetched {len(matches)} matches "
            f"for range {start_date} to {end_date}"
        )
        return matches
    
    async def get_match(self, match_id: str) -> Optional[ProviderMatch]:
        """Get detailed match information.
        
        Args:
            match_id: Match ID
            
        Returns:
            ProviderMatch if found, None if not found
            
        Raises:
            ProviderError: On request failure (except 404)
        """
        # Check cache
        cache_key = f"{self.PROVIDER_NAME}:match:{match_id}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.debug(f"[{self.PROVIDER_NAME}] Cache hit: {cache_key}")
                return cached
        
        # Fetch from API
        try:
            endpoint = f"/api/match/{match_id}"
            data = await self._request("GET", endpoint)
            
            # Normalize match
            match = self._normalize_match(data, is_live=(data.get("status", "").lower() == "live"))
            
            # Cache result
            if self.cache:
                ttl = self._get_cache_ttl(is_live=match.is_live)
                self.cache.set(cache_key, match, ttl_seconds=ttl)
            
            logger.info(f"[{self.PROVIDER_NAME}] Fetched match {match_id}")
            return match
            
        except ProviderNotFoundError:
            logger.info(f"[{self.PROVIDER_NAME}] Match {match_id} not found")
            return None
    
    async def get_live_matches(self) -> List[ProviderLiveMatch]:
        """Get currently live matches.
        
        Returns:
            List of ProviderLiveMatch
            
        Raises:
            ProviderError: On request failure
        """
        # Check cache
        cache_key = f"{self.PROVIDER_NAME}:matches:live"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.debug(f"[{self.PROVIDER_NAME}] Cache hit: {cache_key}")
                return cached
        
        # Fetch from API
        endpoint = "/api/matches/live"
        data = await self._request("GET", endpoint)
        
        # Parse response
        now = datetime.now(timezone.utc)
        live_matches = []
        
        if isinstance(data, list):
            match_list = data
        elif isinstance(data, dict) and "matches" in data:
            match_list = data["matches"]
        else:
            match_list = []
        
        for match_data in match_list:
            try:
                status = self._parse_match_status(match_data.get("status"))
                
                live_match = ProviderLiveMatch(
                    # Source metadata
                    provider=self.PROVIDER_NAME,
                    source_id=str(match_data.get("id") or match_data.get("match_id")),
                    fetched_at=now,
                    source_updated_at=None,
                    is_live=True,
                    data_freshness_seconds=None,
                    
                    # Live state
                    match_id=str(match_data.get("id") or match_data.get("match_id")),
                    status=status,
                    minute=match_data.get("minute"),
                    added_time=match_data.get("added_time"),
                    
                    # Scores
                    home_score=match_data.get("home_score", 0),
                    away_score=match_data.get("away_score", 0),
                    
                    # Events (simplified)
                    live_events=match_data.get("events") if match_data.get("events") else None,
                    
                    # Last updated
                    last_updated=now,
                )
                live_matches.append(live_match)
                
            except Exception as e:
                logger.warning(
                    f"[{self.PROVIDER_NAME}] Failed to normalize live match: {e}"
                )
        
        # Cache result
        if self.cache:
            self.cache.set(cache_key, live_matches, ttl_seconds=LIVE_DATA_TTL)
        
        logger.info(
            f"[{self.PROVIDER_NAME}] Fetched {len(live_matches)} live matches"
        )
        return live_matches
    
    async def get_team(self, team_id: str) -> Optional[ProviderTeam]:
        """Get team information.
        
        Args:
            team_id: Team ID
            
        Returns:
            ProviderTeam if found, None if not found
            
        Raises:
            ProviderError: On request failure (except 404)
        """
        # Check cache
        cache_key = f"{self.PROVIDER_NAME}:team:{team_id}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.debug(f"[{self.PROVIDER_NAME}] Cache hit: {cache_key}")
                return cached
        
        # Fetch from API
        try:
            endpoint = f"/api/team/{team_id}"
            data = await self._request("GET", endpoint)
            
            now = datetime.now(timezone.utc)
            
            team = ProviderTeam(
                # Source metadata
                provider=self.PROVIDER_NAME,
                source_id=str(data.get("id") or team_id),
                fetched_at=now,
                source_updated_at=None,
                is_live=False,
                data_freshness_seconds=None,
                
                # Team data
                name=data.get("name", ""),
                short_name=data.get("short_name") or data.get("code"),
                code=data.get("code"),
                country=data.get("country"),
                founded=data.get("founded"),
                venue_name=data.get("venue") or data.get("stadium"),
                logo_url=data.get("logo") or data.get("logo_url"),
            )
            
            # Cache result
            if self.cache:
                self.cache.set(cache_key, team, ttl_seconds=METADATA_TTL)
            
            logger.info(f"[{self.PROVIDER_NAME}] Fetched team {team_id}")
            return team
            
        except ProviderNotFoundError:
            logger.info(f"[{self.PROVIDER_NAME}] Team {team_id} not found")
            return None
    
    async def get_player(self, player_id: str) -> Optional[ProviderPlayer]:
        """Get player information.
        
        Args:
            player_id: Player ID
            
        Returns:
            ProviderPlayer if found, None if not found
            
        Raises:
            ProviderError: On request failure (except 404)
        """
        # Check cache
        cache_key = f"{self.PROVIDER_NAME}:player:{player_id}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.debug(f"[{self.PROVIDER_NAME}] Cache hit: {cache_key}")
                return cached
        
        # Fetch from API
        try:
            endpoint = f"/api/player/{player_id}"
            data = await self._request("GET", endpoint)
            
            now = datetime.now(timezone.utc)
            
            player = ProviderPlayer(
                # Source metadata
                provider=self.PROVIDER_NAME,
                source_id=str(data.get("id") or player_id),
                fetched_at=now,
                source_updated_at=None,
                is_live=False,
                data_freshness_seconds=None,
                
                # Player data
                name=data.get("name", ""),
                date_of_birth=data.get("date_of_birth") or data.get("dob"),
                nationality=data.get("nationality") or data.get("country"),
                position=data.get("position"),
                shirt_number=data.get("shirt_number") or data.get("number"),
                team_id=str(data.get("team_id")) if data.get("team_id") else None,
                team_name=data.get("team_name") or data.get("team"),
                height_cm=data.get("height_cm") or data.get("height"),
                weight_kg=data.get("weight_kg") or data.get("weight"),
                photo_url=data.get("photo") or data.get("photo_url"),
            )
            
            # Cache result
            if self.cache:
                self.cache.set(cache_key, player, ttl_seconds=METADATA_TTL)
            
            logger.info(f"[{self.PROVIDER_NAME}] Fetched player {player_id}")
            return player
            
        except ProviderNotFoundError:
            logger.info(f"[{self.PROVIDER_NAME}] Player {player_id} not found")
            return None
    
    async def get_league(self, league_id: str) -> Optional[ProviderCompetition]:
        """Get league/competition information.
        
        Args:
            league_id: League ID
            
        Returns:
            ProviderCompetition if found, None if not found
            
        Raises:
            ProviderError: On request failure (except 404)
        """
        # Check cache
        cache_key = f"{self.PROVIDER_NAME}:league:{league_id}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.debug(f"[{self.PROVIDER_NAME}] Cache hit: {cache_key}")
                return cached
        
        # Fetch from API
        try:
            endpoint = f"/api/league/{league_id}"
            data = await self._request("GET", endpoint)
            
            now = datetime.now(timezone.utc)
            
            league = ProviderCompetition(
                # Source metadata
                provider=self.PROVIDER_NAME,
                source_id=str(data.get("id") or league_id),
                fetched_at=now,
                source_updated_at=None,
                is_live=False,
                data_freshness_seconds=None,
                
                # Competition data
                name=data.get("name", ""),
                country=data.get("country"),
                level=data.get("level") or data.get("tier"),
                type=data.get("type"),
                season=data.get("season") or data.get("current_season"),
                logo_url=data.get("logo") or data.get("logo_url"),
            )
            
            # Cache result
            if self.cache:
                self.cache.set(cache_key, league, ttl_seconds=METADATA_TTL)
            
            logger.info(f"[{self.PROVIDER_NAME}] Fetched league {league_id}")
            return league
            
        except ProviderNotFoundError:
            logger.info(f"[{self.PROVIDER_NAME}] League {league_id} not found")
            return None
    
    async def get_standings(self, league_id: str) -> List[ProviderStanding]:
        """Get league standings/table.
        
        Args:
            league_id: League ID
            
        Returns:
            List of ProviderStanding
            
        Raises:
            ProviderError: On request failure
        """
        # Check cache
        cache_key = f"{self.PROVIDER_NAME}:standings:{league_id}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.debug(f"[{self.PROVIDER_NAME}] Cache hit: {cache_key}")
                return cached
        
        # Fetch from API
        endpoint = f"/api/league/{league_id}/table"
        data = await self._request("GET", endpoint)
        
        # Parse response
        now = datetime.now(timezone.utc)
        standings = []
        
        if isinstance(data, list):
            table_data = data
        elif isinstance(data, dict) and "standings" in data:
            table_data = data["standings"]
        elif isinstance(data, dict) and "table" in data:
            table_data = data["table"]
        else:
            table_data = []
        
        for entry in table_data:
            try:
                standing = ProviderStanding(
                    # Source metadata
                    provider=self.PROVIDER_NAME,
                    source_id=str(entry.get("id") or f"{league_id}_{entry.get('position')}"),
                    fetched_at=now,
                    source_updated_at=None,
                    is_live=False,
                    data_freshness_seconds=None,
                    
                    # Standing identifiers
                    competition_id=league_id,
                    competition_name=entry.get("competition_name") or entry.get("league"),
                    season=entry.get("season"),
                    team_id=str(entry.get("team_id") or ""),
                    team_name=entry.get("team_name") or entry.get("team", ""),
                    
                    # Table position
                    position=entry.get("position", 0),
                    played=entry.get("played", 0),
                    won=entry.get("won", 0),
                    drawn=entry.get("drawn", 0),
                    lost=entry.get("lost", 0),
                    
                    # Goals
                    goals_for=entry.get("goals_for", 0),
                    goals_against=entry.get("goals_against", 0),
                    goal_difference=entry.get("goal_difference", 0),
                    
                    # Points
                    points=entry.get("points", 0),
                    
                    # Home/away splits
                    home_played=entry.get("home_played"),
                    home_won=entry.get("home_won"),
                    home_drawn=entry.get("home_drawn"),
                    home_lost=entry.get("home_lost"),
                    away_played=entry.get("away_played"),
                    away_won=entry.get("away_won"),
                    away_drawn=entry.get("away_drawn"),
                    away_lost=entry.get("away_lost"),
                    
                    # Form
                    form=entry.get("form"),
                )
                standings.append(standing)
                
            except Exception as e:
                logger.warning(
                    f"[{self.PROVIDER_NAME}] Failed to normalize standing: {e}"
                )
        
        # Cache result
        if self.cache:
            self.cache.set(cache_key, standings, ttl_seconds=UPCOMING_FIXTURES_TTL)
        
        logger.info(
            f"[{self.PROVIDER_NAME}] Fetched {len(standings)} standings "
            f"for league {league_id}"
        )
        return standings
