"""# Unofficial SofaScore Integration

⚠️ This is NOT an official SofaScore API integration.

This provider uses publicly accessible SofaScore JSON endpoints for match statistics
and detailed match data. Request volume must be conservative. No bypasses, no anti-bot
evasion, no scraping tricks. If a request fails, return structured provider failure —
never invent data.

SofaScore is prioritized for MATCH STATISTICS where it provides comprehensive data
including period-specific statistics (full match, first half, second half).

Conservative request patterns:
- retry_count=1 max (no aggressive retry loops)
- No CAPTCHA bypasses
- No authentication bypasses
- No anti-bot evasion
- No scraping tricks
- If request fails, raise ProviderError (never invent data)
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple
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
)
from app.providers.models import (
    ProviderMatch,
    ProviderMatchStats,
    ProviderLiveMatch,
)
from app.domain.enums import MatchStatus, MatchOutcome


logger = logging.getLogger(__name__)


class SofaScoreFootballProvider:
    """SofaScore Football Provider (MATCH STATISTICS provider, unofficial).
    
    This provider is designed for MATCH STATISTICS where SofaScore provides
    comprehensive data including period-specific stats. It is NOT an official
    SofaScore API integration.
    
    PRIMARY USE CASES:
    - Match statistics (shots, possession, xG, etc.)
    - Period-specific statistics (first half, second half)
    - Match details with comprehensive data
    - Live match state
    
    Conservative request patterns only:
    - retry_count=1 max (no aggressive retry loops)
    - No bypasses, no anti-bot evasion, no scraping tricks
    - If request fails, raise ProviderError (never invent data)
    
    Args:
        base_url: Base URL for SofaScore endpoints (configurable)
        timeout_seconds: HTTP request timeout in seconds
        retry_count: Max retries for transient failures (default: 1, conservative)
        cache: Optional ProviderCache for caching responses
    """
    
    PROVIDER_NAME = "sofascore"
    
    # ID mapping - empty for now, to be populated later
    MENSIONE_TO_SOFASCORE_IDS: Dict[str, str] = {}
    
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 10.0,
        retry_count: int = 1,  # Conservative: only 1 retry
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
            f"Initialized {self.PROVIDER_NAME} provider (UNOFFICIAL): "
            f"base_url={self.base_url}, timeout={timeout_seconds}s, "
            f"retry_count={retry_count}, cache={'enabled' if cache else 'disabled'}"
        )
    
    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
    
    def _resolve_sofascore_id(self, mensione_id: str) -> Optional[str]:
        """Resolve TUTAR X internal ID to SofaScore ID.
        
        Args:
            mensione_id: TUTAR X internal match/team ID (parameter name kept for backward compatibility)
            
        Returns:
            SofaScore ID if mapped, None otherwise
        """
        return self.MENSIONE_TO_SOFASCORE_IDS.get(mensione_id)
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make HTTP request with error handling and conservative retry logic.
        
        Conservative retry policy:
        - retry_count=1 max (no aggressive retry loops)
        - Only retry on connection errors and 5xx server errors
        - No bypasses, no anti-bot evasion
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path (e.g., '/event/12345')
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
                    # Server error - retry once (conservative)
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
                # Connection error - retry once (conservative)
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
        """Parse SofaScore match status to domain MatchStatus.
        
        Args:
            status_str: Status string from SofaScore API
            
        Returns:
            Normalized MatchStatus
        """
        if not status_str:
            return MatchStatus.SCHEDULED
        
        status_lower = status_str.lower()
        
        # SofaScore typically uses status codes/strings like:
        # "notstarted", "inprogress", "finished", "postponed", "cancelled", etc.
        if status_lower in ["inprogress", "live", "in_progress"]:
            return MatchStatus.LIVE
        elif status_lower in ["halftime", "ht"]:
            return MatchStatus.HALF_TIME
        elif status_lower in ["finished", "ft", "ended", "after_penalties", "after_extra_time"]:
            return MatchStatus.FINISHED
        elif status_lower in ["postponed", "pst"]:
            return MatchStatus.POSTPONED
        elif status_lower in ["cancelled", "canceled", "cnc"]:
            return MatchStatus.CANCELLED
        elif status_lower in ["suspended", "interrupted"]:
            return MatchStatus.SUSPENDED
        elif status_lower in ["notstarted", "not_started", "scheduled"]:
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
    
    def _normalize_match_statistics(
        self,
        data: Dict[str, Any],
        period: str = 'full'
    ) -> Tuple[Optional[ProviderMatchStats], Optional[ProviderMatchStats]]:
        """Normalize SofaScore match statistics to ProviderMatchStats.
        
        SofaScore statistics response format:
        {
            "statistics": [
                {
                    "period": "ALL"|"1ST"|"2ND",
                    "groups": [
                        {
                            "groupName": str,
                            "statisticsItems": [
                                {
                                    "name": str,
                                    "home": str,
                                    "away": str,
                                    "homeValue": int,
                                    "awayValue": int
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        
        Args:
            data: Raw statistics data from SofaScore API
            period: Target period ('full', 'first_half', 'second_half')
            
        Returns:
            Tuple of (home_stats, away_stats), both None if period not found
        """
        now = datetime.now(timezone.utc)
        
        # Map period to SofaScore period codes
        period_map = {
            'full': 'ALL',
            'first_half': '1ST',
            'second_half': '2ND'
        }
        sofascore_period = period_map.get(period, 'ALL')
        
        # Find the matching period in statistics
        statistics_list = data.get("statistics", [])
        period_data = None
        
        for period_obj in statistics_list:
            if period_obj.get("period") == sofascore_period:
                period_data = period_obj
                break
        
        if not period_data:
            logger.debug(
                f"[{self.PROVIDER_NAME}] Period '{period}' (SofaScore: '{sofascore_period}') "
                f"not found in statistics"
            )
            return (None, None)
        
        # Extract statistics into home and away dicts
        home_values = {}
        away_values = {}
        
        groups = period_data.get("groups", [])
        for group in groups:
            items = group.get("statisticsItems", [])
            for item in items:
                stat_name = item.get("name", "")
                home_val = item.get("homeValue")
                away_val = item.get("awayValue")
                
                # Store by name
                home_values[stat_name] = home_val
                away_values[stat_name] = away_val
        
        # Map SofaScore field names to ProviderMatchStats fields
        def map_stat(stat_dict: Dict[str, Any], match_id: str, team_id: str) -> ProviderMatchStats:
            """Map statistics dict to ProviderMatchStats."""
            
            # Helper to safely get int value
            def get_int(key: str) -> Optional[int]:
                val = stat_dict.get(key)
                if val is None:
                    return None
                try:
                    return int(val)
                except (ValueError, TypeError):
                    return None
            
            # Helper to safely get float value
            def get_float(key: str) -> Optional[float]:
                val = stat_dict.get(key)
                if val is None:
                    return None
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return None
            
            return ProviderMatchStats(
                # Source metadata
                provider=self.PROVIDER_NAME,
                source_id=match_id,
                fetched_at=now,
                source_updated_at=None,
                is_live=False,
                data_freshness_seconds=None,
                
                # Match and team identifiers
                match_id=match_id,
                team_id=team_id,
                team_name=None,
                period=period,
                
                # Map statistics
                possession_percentage=get_float("Ball possession"),
                shots_total=get_int("Total shots") or get_int("Shots"),
                shots_on_target=get_int("Shots on target"),
                shots_off_target=get_int("Shots off target"),
                shots_blocked=get_int("Blocked shots"),
                xg=get_float("Expected goals") or get_float("xG"),
                corners=get_int("Corner kicks") or get_int("Corners"),
                fouls_committed=get_int("Fouls"),
                offsides=get_int("Offsides"),
                yellow_cards=get_int("Yellow cards"),
                red_cards=get_int("Red cards"),
                passes_attempted=get_int("Passes") or get_int("Total passes"),
                passes_completed=get_int("Accurate passes") or get_int("Passes accurate"),
                tackles=get_int("Tackles"),
                interceptions=get_int("Interceptions"),
                clearances=get_int("Clearances"),
                saves=get_int("Goalkeeper saves") or get_int("Saves"),
                
                # Fields not commonly in SofaScore stats
                goals_scored=None,
                goals_conceded=None,
                xg_against=None,
                pass_accuracy=None,
                free_kicks=None,
            )
        
        # Get match_id from data (usually in event object)
        match_id = str(data.get("event", {}).get("id", "unknown"))
        
        # Create home and away stats
        home_stats = map_stat(home_values, match_id, "home")
        away_stats = map_stat(away_values, match_id, "away")
        
        return (home_stats, away_stats)
    
    async def get_match_statistics(
        self,
        match_id: str,
        period: str = 'full'
    ) -> Tuple[Optional[ProviderMatchStats], Optional[ProviderMatchStats]]:
        """Get match statistics for a specific period.
        
        Args:
            match_id: SofaScore match ID
            period: Period to fetch ('full', 'first_half', 'second_half')
            
        Returns:
            Tuple of (home_stats, away_stats), both None if not found
            
        Raises:
            ProviderError: On request failure (except 404)
        """
        # Check cache
        cache_key = f"{self.PROVIDER_NAME}:stats:{match_id}:{period}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.debug(f"[{self.PROVIDER_NAME}] Cache hit: {cache_key}")
                return cached
        
        # Fetch from API
        try:
            endpoint = f"/event/{match_id}/statistics"
            data = await self._request("GET", endpoint)
            
            # Normalize statistics
            home_stats, away_stats = self._normalize_match_statistics(data, period)
            
            # Cache result
            if self.cache:
                ttl = LIVE_DATA_TTL if data.get("event", {}).get("status", {}).get("type") in ["inprogress", "live"] else UPCOMING_FIXTURES_TTL
                self.cache.set(cache_key, (home_stats, away_stats), ttl_seconds=ttl)
            
            logger.info(
                f"[{self.PROVIDER_NAME}] Fetched statistics for match {match_id}, period {period}"
            )
            return (home_stats, away_stats)
            
        except ProviderNotFoundError:
            logger.info(
                f"[{self.PROVIDER_NAME}] Statistics for match {match_id} not found"
            )
            return (None, None)
        except ProviderError:
            # If request fails, raise error (never invent data)
            raise
    
    async def get_match(self, match_id: str) -> Optional[ProviderMatch]:
        """Get detailed match information.
        
        Args:
            match_id: SofaScore match ID
            
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
            endpoint = f"/event/{match_id}"
            data = await self._request("GET", endpoint)
            
            now = datetime.now(timezone.utc)
            
            # Parse event data
            event = data.get("event", {})
            
            # Parse status
            status_data = event.get("status", {})
            status_type = status_data.get("type", "")
            status = self._parse_match_status(status_type)
            is_live = status in [MatchStatus.LIVE, MatchStatus.HALF_TIME]
            
            # Parse scheduled time
            start_timestamp = event.get("startTimestamp")
            if start_timestamp:
                scheduled_at = datetime.fromtimestamp(start_timestamp, tz=timezone.utc)
            else:
                scheduled_at = now
            
            # Parse scores
            home_score = event.get("homeScore", {}).get("current")
            away_score = event.get("awayScore", {}).get("current")
            
            # Parse teams
            home_team = event.get("homeTeam", {})
            away_team = event.get("awayTeam", {})
            
            home_team_id = str(home_team.get("id", ""))
            home_team_name = home_team.get("name", "")
            away_team_id = str(away_team.get("id", ""))
            away_team_name = away_team.get("name", "")
            
            # Parse competition
            tournament = event.get("tournament", {})
            competition_id = str(tournament.get("id")) if tournament.get("id") else None
            competition_name = tournament.get("name")
            
            # Parse season
            season_data = event.get("season")
            season = season_data.get("name") if season_data else None
            
            # Parse venue
            venue_name = event.get("venue", {}).get("stadium", {}).get("name")
            
            # Parse minute
            minute = status_data.get("description")
            if minute and minute.isdigit():
                minute = int(minute)
            else:
                minute = None
            
            # Parse outcome
            outcome = None
            if status == MatchStatus.FINISHED:
                outcome = self._parse_match_outcome(home_score, away_score)
            
            # Parse round
            round_info = event.get("roundInfo", {})
            round_num = round_info.get("round")
            
            match = ProviderMatch(
                # Source metadata
                provider=self.PROVIDER_NAME,
                source_id=str(event.get("id", match_id)),
                fetched_at=now,
                source_updated_at=None,
                is_live=is_live,
                data_freshness_seconds=None,
                
                # Match identifiers
                competition_id=competition_id,
                competition_name=competition_name,
                season=season,
                
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
                minute=minute,
                added_time=None,
                
                # Scores
                home_score=home_score,
                away_score=away_score,
                home_score_ht=None,  # Would need additional endpoint for period scores
                away_score_ht=None,
                
                # Outcome
                outcome=outcome,
                
                # Match round
                round=round_num,
            )
            
            # Cache result
            if self.cache:
                ttl = LIVE_DATA_TTL if is_live else UPCOMING_FIXTURES_TTL
                self.cache.set(cache_key, match, ttl_seconds=ttl)
            
            logger.info(f"[{self.PROVIDER_NAME}] Fetched match {match_id}")
            return match
            
        except ProviderNotFoundError:
            logger.info(f"[{self.PROVIDER_NAME}] Match {match_id} not found")
            return None
        except ProviderError:
            # If request fails, raise error (never invent data)
            raise
    
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
        try:
            endpoint = "/sport/football/events/live"
            data = await self._request("GET", endpoint)
            
            now = datetime.now(timezone.utc)
            live_matches = []
            
            # Parse response - SofaScore returns list of events
            events = data.get("events", [])
            
            for event in events:
                try:
                    # Parse status
                    status_data = event.get("status", {})
                    status_type = status_data.get("type", "")
                    status = self._parse_match_status(status_type)
                    
                    # Only include live matches
                    if status not in [MatchStatus.LIVE, MatchStatus.HALF_TIME]:
                        continue
                    
                    # Parse scores
                    home_score = event.get("homeScore", {}).get("current", 0)
                    away_score = event.get("awayScore", {}).get("current", 0)
                    
                    # Parse minute
                    minute = status_data.get("description")
                    if minute and minute.isdigit():
                        minute = int(minute)
                    else:
                        minute = None
                    
                    live_match = ProviderLiveMatch(
                        # Source metadata
                        provider=self.PROVIDER_NAME,
                        source_id=str(event.get("id", "")),
                        fetched_at=now,
                        source_updated_at=None,
                        is_live=True,
                        data_freshness_seconds=None,
                        
                        # Live state
                        match_id=str(event.get("id", "")),
                        status=status,
                        minute=minute,
                        added_time=None,
                        
                        # Scores
                        home_score=home_score,
                        away_score=away_score,
                        
                        # Events
                        live_events=None,
                        
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
            
        except ProviderError:
            # If request fails, return empty list (conservative)
            logger.warning(
                f"[{self.PROVIDER_NAME}] Failed to fetch live matches, returning empty list"
            )
            return []
