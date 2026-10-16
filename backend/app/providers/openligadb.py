"""OpenLigaDB Football Provider implementation.

OpenLigaDB is an INDEPENDENT FALLBACK provider for:
- League/competition metadata
- Match detail (NO xG data)
- League standings/tables
- German football data specifically

CRITICAL: OpenLigaDB does NOT provide xG data.
When this provider returns a match, xg=None is the authoritative result.

This provider uses the public OpenLigaDB API endpoints:
- GET /getavailableleagues - Get available leagues
- GET /getmatchdata/{matchId} - Get match detail
- GET /getbltable/{leagueShortcut}/{leagueSeason} - Get standings
"""

import logging
from datetime import datetime, date, timezone
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
    UPCOMING_FIXTURES_TTL,
    HISTORICAL_MATCH_TTL,
    METADATA_TTL,
)
from app.providers.models import (
    ProviderMatch,
    ProviderCompetition,
    ProviderStanding,
)
from app.domain.enums import MatchStatus, MatchOutcome


logger = logging.getLogger(__name__)


class OpenLigaDBFootballProvider:
    """OpenLigaDB Football Provider (INDEPENDENT FALLBACK provider).
    
    This provider is designed as an independent fallback for match data,
    particularly for German football leagues. It provides match details and
    standings but does NOT provide xG data.
    
    PRIMARY USE CASES:
    - Match detail (NO xG)
    - League standings
    - League metadata
    
    STUB/NOT IMPLEMENTED:
    - Daily match schedules by date (use Ryzellx or FotMob instead)
    - Live matches (use FotMob or Ryzellx instead)
    - Team details (use Ryzellx instead)
    - Player details (use Ryzellx instead)
    
    CRITICAL: xg=None always (OpenLigaDB does not provide xG).
    This is NOT a missing field to failover on - it's the authoritative result.
    
    Args:
        base_url: Base URL for OpenLigaDB endpoints (configurable)
        timeout_seconds: HTTP request timeout in seconds
        retry_count: Max retries for transient failures (default: 2)
        cache: Optional ProviderCache for caching responses
    """
    
    PROVIDER_NAME = "openligadb"
    
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
    ) -> Any:
        """Make HTTP request with error handling and retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path (e.g., '/getmatchdata/12345')
            params: Optional query parameters
            
        Returns:
            Parsed JSON response (dict or list)
            
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
    
    def _parse_match_status(self, status_str: Optional[str]) -> MatchStatus:
        """Parse OpenLigaDB match status to domain MatchStatus.
        
        Args:
            status_str: Status string from OpenLigaDB API
            
        Returns:
            Normalized MatchStatus
        """
        if not status_str:
            return MatchStatus.SCHEDULED
        
        status_lower = status_str.lower()
        
        # OpenLigaDB typically uses status like:
        # "finished", "running", "not started", etc.
        if status_lower in ["running", "live", "in_progress"]:
            return MatchStatus.LIVE
        elif status_lower in ["halftime", "half_time", "ht"]:
            return MatchStatus.HALF_TIME
        elif status_lower in ["finished", "beendet", "ft", "full_time"]:
            return MatchStatus.FINISHED
        elif status_lower in ["postponed", "verschoben", "pst"]:
            return MatchStatus.POSTPONED
        elif status_lower in ["cancelled", "canceled", "abgesagt", "cnc"]:
            return MatchStatus.CANCELLED
        elif status_lower in ["suspended", "unterbrochen", "susp"]:
            return MatchStatus.SUSPENDED
        elif status_lower in ["scheduled", "angesetzt", "not started", "ns"]:
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
    
    def _normalize_match(self, data: Dict[str, Any]) -> ProviderMatch:
        """Normalize OpenLigaDB match data to ProviderMatch.
        
        CRITICAL: xg=None always (OpenLigaDB does not provide xG).
        
        Args:
            data: Raw match data from OpenLigaDB API
            
        Returns:
            Normalized ProviderMatch (with xg=None)
        """
        now = datetime.now(timezone.utc)
        
        # Parse scheduled time
        scheduled_str = data.get("matchDateTime") or data.get("matchDateTimeUTC")
        if scheduled_str:
            try:
                scheduled_at = datetime.fromisoformat(scheduled_str.replace("Z", "+00:00"))
            except:
                scheduled_at = now
        else:
            scheduled_at = now
        
        # Parse status
        status_str = data.get("matchIsFinished")
        if status_str is True or (isinstance(status_str, str) and status_str.lower() == "true"):
            status = MatchStatus.FINISHED
        else:
            # Check for other status indicators
            status = self._parse_match_status(data.get("status"))
        
        # Parse scores
        home_score = None
        away_score = None
        
        # OpenLigaDB typically provides scores in matchResults array
        match_results = data.get("matchResults", [])
        if match_results:
            # Get final score (resultTypeID == 2 for final, 1 for half-time)
            final_result = None
            for result in match_results:
                if result.get("resultTypeID") == 2:
                    final_result = result
                    break
            if not final_result and match_results:
                final_result = match_results[-1]
            
            if final_result:
                home_score = final_result.get("pointsTeam1")
                away_score = final_result.get("pointsTeam2")
        
        # Parse teams
        home_team = data.get("team1") or {}
        away_team = data.get("team2") or {}
        
        home_team_id = str(home_team.get("teamId", "")) if home_team.get("teamId") else ""
        home_team_name = home_team.get("teamName", "") if home_team else ""
        away_team_id = str(away_team.get("teamId", "")) if away_team.get("teamId") else ""
        away_team_name = away_team.get("teamName", "") if away_team else ""
        
        # Parse competition
        competition_id = str(data.get("leagueId")) if data.get("leagueId") else None
        competition_name = data.get("leagueName")
        
        # Parse outcome
        outcome = None
        if status == MatchStatus.FINISHED:
            outcome = self._parse_match_outcome(home_score, away_score)
        
        # Parse venue
        venue_name = data.get("location") or data.get("stadium")
        
        # Parse round
        round_num = data.get("group") or data.get("matchday")
        if round_num and isinstance(round_num, dict):
            round_num = round_num.get("groupOrderID")
        
        return ProviderMatch(
            # Source metadata
            provider=self.PROVIDER_NAME,
            source_id=str(data.get("matchID") or data.get("matchId", "")),
            fetched_at=now,
            source_updated_at=None,
            is_live=status == MatchStatus.LIVE,
            data_freshness_seconds=None,
            
            # Match identifiers
            competition_id=competition_id,
            competition_name=competition_name,
            season=data.get("leagueSeason"),
            
            # Teams
            home_team_id=home_team_id,
            home_team_name=home_team_name,
            away_team_id=away_team_id,
            away_team_name=away_team_name,
            
            # Venue
            venue_name=venue_name,
            
            # Timing
            scheduled_at=scheduled_at,
            status=status,
            minute=None,  # OpenLigaDB doesn't typically provide live minute
            added_time=None,
            
            # Scores
            home_score=home_score,
            away_score=away_score,
            home_score_ht=None,  # Would need to parse from matchResults with resultTypeID == 1
            away_score_ht=None,
            
            # Outcome
            outcome=outcome,
            
            # Match round
            round=round_num,
        )
    
    async def get_match(self, match_id: str) -> Optional[ProviderMatch]:
        """Get detailed match information.
        
        CRITICAL: xg=None always (OpenLigaDB does not provide xG).
        
        Args:
            match_id: Match ID
            
        Returns:
            ProviderMatch if found (with xg=None), None if not found
            
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
            endpoint = f"/getmatchdata/{match_id}"
            data = await self._request("GET", endpoint)
            
            # Normalize match
            match = self._normalize_match(data)
            
            # Cache result
            if self.cache:
                # Determine TTL based on match status
                if match.status == MatchStatus.FINISHED:
                    ttl = HISTORICAL_MATCH_TTL
                else:
                    ttl = UPCOMING_FIXTURES_TTL
                self.cache.set(cache_key, match, ttl_seconds=ttl)
            
            logger.info(f"[{self.PROVIDER_NAME}] Fetched match {match_id}")
            return match
            
        except ProviderNotFoundError:
            logger.info(f"[{self.PROVIDER_NAME}] Match {match_id} not found")
            return None
        except ProviderError:
            # If request fails, raise error (never invent data)
            raise
    
    async def get_league(self, league_id: str) -> Optional[ProviderCompetition]:
        """Get league/competition information.
        
        Args:
            league_id: League ID
            
        Returns:
            ProviderCompetition if found, None if not found
            
        Raises:
            ProviderError: On request failure
        """
        # Check cache
        cache_key = f"{self.PROVIDER_NAME}:league:{league_id}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.debug(f"[{self.PROVIDER_NAME}] Cache hit: {cache_key}")
                return cached
        
        try:
            # OpenLigaDB uses /getavailableleagues to list all leagues
            endpoint = "/getavailableleagues"
            data = await self._request("GET", endpoint)
            
            # Find the specific league
            if isinstance(data, list):
                for league_data in data:
                    if str(league_data.get("leagueId")) == str(league_id):
                        now = datetime.now(timezone.utc)
                        
                        league = ProviderCompetition(
                            # Source metadata
                            provider=self.PROVIDER_NAME,
                            source_id=str(league_data.get("leagueId")),
                            fetched_at=now,
                            source_updated_at=None,
                            is_live=False,
                            data_freshness_seconds=None,
                            
                            # Competition data
                            name=league_data.get("leagueName", ""),
                            country=league_data.get("leagueShortcut", "").split("-")[0] if league_data.get("leagueShortcut") else None,
                            level=None,
                            type="league",
                            season=league_data.get("leagueSeason"),
                            logo_url=None,
                        )
                        
                        # Cache result
                        if self.cache:
                            self.cache.set(cache_key, league, ttl_seconds=METADATA_TTL)
                        
                        logger.info(f"[{self.PROVIDER_NAME}] Fetched league {league_id}")
                        return league
            
            # League not found
            logger.info(f"[{self.PROVIDER_NAME}] League {league_id} not found")
            return None
            
        except ProviderError:
            raise
    
    async def get_standings(self, league_id: str) -> List[ProviderStanding]:
        """Get league standings/table.
        
        Note: This requires leagueShortcut and leagueSeason parameters.
        For simplicity, we return empty list. Full implementation would need
        mapping from league_id to shortcut/season.
        
        Args:
            league_id: League ID
            
        Returns:
            List of ProviderStanding (currently empty - not fully implemented)
        """
        logger.debug(
            f"[{self.PROVIDER_NAME}] get_standings not fully implemented - "
            f"requires leagueShortcut and leagueSeason mapping"
        )
        return []
    
    async def get_matches_by_date(self, date_obj: date) -> List[ProviderMatch]:
        """Get matches for a specific date.
        
        STUB: OpenLigaDB not used for date-based queries.
        Use Ryzellx or FotMob for daily match schedules instead.
        
        Args:
            date_obj: Date to fetch matches for
            
        Returns:
            Empty list (not implemented)
        """
        logger.debug(
            f"[{self.PROVIDER_NAME}] get_matches_by_date not implemented - "
            f"use Ryzellx or FotMob for daily match schedules"
        )
        return []
    
    async def get_matches_by_range(
        self,
        start_date: date,
        end_date: date
    ) -> List[ProviderMatch]:
        """Get matches in date range.
        
        STUB: OpenLigaDB not used for date-range queries.
        Use Ryzellx or FotMob for date-range match schedules instead.
        
        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            
        Returns:
            Empty list (not implemented)
        """
        logger.debug(
            f"[{self.PROVIDER_NAME}] get_matches_by_range not implemented - "
            f"use Ryzellx or FotMob for date-range match schedules"
        )
        return []
    
    def get_matches(
        self,
        competition_id: Optional[str] = None,
        season_id: Optional[str] = None,
        team_id: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        status: Optional[str] = None,
    ) -> List[ProviderMatch]:
        """Synchronous wrapper for async get_matches_by_range method.
        
        This method provides compatibility with the base FootballDataProvider interface
        which requires a synchronous get_matches method for feature extraction.
        
        OpenLigaDB is not used for date-range match schedules, so this returns empty.
        Use Ryzellx or FotMob for actual match data instead.
        
        Args:
            competition_id: Filter by competition (not supported, ignored)
            season_id: Filter by season (not supported, ignored)  
            team_id: Filter by team (not supported, ignored)
            from_date: Filter matches from this date (not supported, ignored)
            to_date: Filter matches to this date (not supported, ignored)
            status: Filter by match status (not supported, ignored)
            
        Returns:
            Empty list (OpenLigaDB not used for match schedules)
        """
        import logging
        
        logger = logging.getLogger(__name__)
        logger.debug(
            f"[{self.PROVIDER_NAME}] Synchronous get_matches not implemented - "
            f"use Ryzellx or FotMob for date-range match schedules"
        )
        
        # Return empty list - this allows graceful fallback in MatchFeatureExtractor
        return []
    
    async def get_live_matches(self) -> List:
        """Get currently live matches.
        
        STUB: OpenLigaDB not used for live match queries.
        Use FotMob or Ryzellx for live matches instead.
        
        Returns:
            Empty list (not implemented)
        """
        logger.debug(
            f"[{self.PROVIDER_NAME}] get_live_matches not implemented - "
            f"use FotMob or Ryzellx for live matches"
        )
        return []
    
    async def get_team(self, team_id: str) -> None:
        """Get team information.
        
        STUB: OpenLigaDB team lookup not a priority - use Ryzellx instead.
        
        Args:
            team_id: Team ID
            
        Returns:
            None (not implemented)
        """
        logger.debug(
            f"[{self.PROVIDER_NAME}] get_team not implemented - "
            f"use Ryzellx for team metadata"
        )
        return None
    
    async def get_player(self, player_id: str) -> None:
        """Get player information.
        
        STUB: OpenLigaDB player lookup not a priority - use Ryzellx instead.
        
        Args:
            player_id: Player ID
            
        Returns:
            None (not implemented)
        """
        logger.debug(
            f"[{self.PROVIDER_NAME}] get_player not implemented - "
            f"use Ryzellx for player metadata"
        )
        return None
    
    async def get_competitions(self) -> List[ProviderCompetition]:
        """Get available competitions/leagues from OpenLigaDB.
        
        Returns:
            List of ProviderCompetition objects
            
        Raises:
            ProviderError: On request failure (gracefully degrades to empty list)
        """
        # Check cache
        cache_key = f"{self.PROVIDER_NAME}:competitions"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.debug(f"[{self.PROVIDER_NAME}] Cache hit: {cache_key}")
                return cached
        
        # Fetch from API
        try:
            endpoint = "/getavailableleagues"
            data = await self._request("GET", endpoint)
            
            # Parse competitions
            competitions = []
            now = datetime.now(timezone.utc)
            
            if isinstance(data, list):
                for league_data in data:
                    try:
                        competition = ProviderCompetition(
                            provider=self.PROVIDER_NAME,
                            source_id=str(league_data.get("leagueId", "")),
                            fetched_at=now,
                            source_updated_at=None,
                            
                            name=league_data.get("leagueName", ""),
                            country=None,  # OpenLigaDB doesn't provide this
                            season=league_data.get("leagueSeason"),
                            type=None,  # OpenLigaDB doesn't categorize
                        )
                        competitions.append(competition)
                    except Exception as e:
                        logger.warning(
                            f"[{self.PROVIDER_NAME}] Failed to normalize competition: {e}"
                        )
            
            # Cache result
            if self.cache:
                self.cache.set(cache_key, competitions, ttl_seconds=METADATA_TTL)
            
            logger.info(f"[{self.PROVIDER_NAME}] Fetched {len(competitions)} competitions")
            return competitions
            
        except ProviderError:
            # If request fails, return empty list (graceful degradation)
            logger.warning(f"[{self.PROVIDER_NAME}] Failed to fetch competitions, returning empty list")
            return []
