"""# Unofficial FotMob Integration

⚠️ This is NOT an official FotMob API integration.

This provider uses publicly accessible FotMob JSON endpoints for live/fast data.
Request volume must be conservative. No bypasses, no anti-bot evasion, no scraping tricks.
If a request fails, return structured provider failure — never invent data.

FotMob is the LIVE/FAST provider for real-time match data where it provides fresher
information than Ryzellx. This is an unofficial integration using conservative request
patterns only.

Conservative request patterns:
- retry_count=1 max (no aggressive retry loops)
- No CAPTCHA bypasses
- No authentication bypasses
- No anti-bot evasion
- No scraping tricks
- If request fails, raise ProviderError (never invent data)
"""

import logging
import re
from datetime import datetime, date, timezone
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
    HISTORICAL_MATCH_TTL,
)
from app.providers.models import (
    ProviderMatch,
    ProviderCompetition,
    ProviderTeam,
    ProviderPlayer,
    ProviderStanding,
    ProviderLiveMatch,
    ProviderMatchStats,
)
from app.domain.enums import MatchStatus, MatchOutcome


logger = logging.getLogger(__name__)


def _parse_round(value) -> int | None:
    """Safely parse a match round value to int.

    FotMob sometimes returns round as an integer (e.g. 9) or as a string
    containing the round number mixed with text (e.g. "Clausura - Round 9").
    Returns None if the value cannot be parsed to a meaningful integer.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    # Try direct int conversion first
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        pass
    # Try to extract a trailing number from strings like "Clausura - Round 9"
    import re
    m = re.search(r'\d+\s*$', str(value).strip())
    if m:
        try:
            return int(m.group())
        except ValueError:
            pass
    return None


# FotMob carries the running clock as status.liveTime.short, e.g. "23’",
# "45+2’" or "HT", wrapped in bidi marks (U+200E). Everything except digits,
# letters and '+' is noise for parsing purposes.
_LIVE_CLOCK_NOISE_RE = re.compile(r"[^0-9A-Za-z+]")
_LIVE_CLOCK_RE = re.compile(r"(\d{1,3})(?:\+(\d{1,2}))?")
_HALF_TIME_CLOCK_LABELS = {"HT", "HALFTIME"}


def _status_block(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return FotMob's status object for list items and matchDetails alike.

    Day-list items carry it at the top level (``status``); matchDetails
    responses only carry it under ``header.status``.
    """
    status_data = data.get("status")
    if isinstance(status_data, dict) and status_data:
        return status_data
    header_data = data.get("header")
    if isinstance(header_data, dict) and isinstance(header_data.get("status"), dict):
        return header_data["status"]
    return status_data if isinstance(status_data, dict) else {}


def _parse_live_clock(status_data: Any) -> Tuple[Optional[int], Optional[int], bool]:
    """Parse FotMob's live clock (status.liveTime.short).

    Returns (minute, added_time, is_half_time). Unknown or missing clocks give
    (None, None, False): the minute is never guessed.
    """
    if not isinstance(status_data, dict):
        return None, None, False
    live_time = status_data.get("liveTime")
    if not isinstance(live_time, dict):
        return None, None, False
    short = live_time.get("short")
    if not isinstance(short, str):
        return None, None, False
    cleaned = _LIVE_CLOCK_NOISE_RE.sub("", short)
    if cleaned.upper() in _HALF_TIME_CLOCK_LABELS:
        return None, None, True
    clock = _LIVE_CLOCK_RE.fullmatch(cleaned)
    if not clock:
        return None, None, False
    minute = int(clock.group(1))
    added_time = int(clock.group(2)) if clock.group(2) else None
    return minute, added_time, False


class FotMobFootballProvider:
    """FotMob Football Provider (LIVE/FAST provider, unofficial).

    This provider is designed for LIVE/FAST data where FotMob provides fresher
    information than other providers. It is NOT an official FotMob API integration.

    PRIMARY USE CASES:
    - Live match data (scores, minute, events)
    - Daily match schedules with fresh data
    - Match details with real-time updates

    STUB/NOT IMPLEMENTED:
    - League metadata (use Ryzellx instead)
    - Team details (use Ryzellx instead)
    - Player details (use Ryzellx instead)
    - Standings (use Ryzellx or OpenLigaDB instead)

    Conservative request patterns only:
    - retry_count=1 max (no aggressive retry loops)
    - No bypasses, no anti-bot evasion, no scraping tricks
    - If request fails, raise ProviderError (never invent data)

    Args:
        base_url: Base URL for FotMob endpoints (configurable)
        timeout_seconds: HTTP request timeout in seconds
        retry_count: Max retries for transient failures (default: 1, conservative)
        cache: Optional ProviderCache for caching responses
    """

    PROVIDER_NAME = "fotmob"

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
            endpoint: API endpoint path (e.g., '/api/matches')
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
        """Parse FotMob match status to domain MatchStatus.

        Args:
            status_str: Status string from FotMob API

        Returns:
            Normalized MatchStatus
        """
        if not status_str:
            return MatchStatus.SCHEDULED

        status_lower = status_str.lower()

        # FotMob typically uses status strings like:
        # "live", "finished", "not_started", "halftime", "postponed", "fulltime_short", etc.
        if status_lower in ["live", "in_play", "playing"]:
            return MatchStatus.LIVE
        elif status_lower in ["ht", "half_time", "halftime", "halftime_short"]:
            return MatchStatus.HALF_TIME
        elif status_lower in ["ft", "finished", "full_time", "fulltime", "fulltime_short", "penalties_short", "afterextratime_short"]:
            return MatchStatus.FINISHED
        elif status_lower in ["postponed", "pst", "postponed_short"]:
            return MatchStatus.POSTPONED
        elif status_lower in ["cancelled", "canceled", "cnc", "cancelled_short", "aborted_short"]:
            return MatchStatus.CANCELLED
        elif status_lower in ["suspended", "susp", "suspended_short"]:
            return MatchStatus.SUSPENDED
        elif status_lower in ["scheduled", "not_started", "ns", "not started", "notstarted_short"]:
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

    def _normalize_match(self, data: Dict[str, Any], is_live: bool = False, league_context: Optional[Dict[str, Any]] = None) -> ProviderMatch:
        """Normalize FotMob match data to ProviderMatch.

        Args:
            data: Raw match data from FotMob API
            is_live: Whether this is live match data
            league_context: Optional league data when parsing from leagues list

        Returns:
            Normalized ProviderMatch
        """
        now = datetime.now(timezone.utc)

        # Parse scheduled time
        # Priority 1: general.matchTimeUTCDate (matchDetails primary field)
        # Priority 2-N: existing fallbacks preserved
        scheduled_at = now
        general_data = data.get("general") or {}

        # Try general.matchTimeUTCDate first
        if isinstance(general_data, dict) and "matchTimeUTCDate" in general_data:
            try:
                scheduled_at = datetime.fromisoformat(general_data["matchTimeUTCDate"].replace("Z", "+00:00"))
            except:
                pass

        # Existing fallback logic preserved
        if scheduled_at == now:
            status_data = data.get("status") or {}
            # Try status.utcTime first (existing logic)
            if isinstance(status_data, dict) and "utcTime" in status_data:
                try:
                    scheduled_at = datetime.fromisoformat(status_data["utcTime"].replace("Z", "+00:00"))
                except:
                    pass

            # Fallback to other time fields (existing logic preserved)
            if scheduled_at == now:
                scheduled_str = (
                    data.get("startTime") or
                    data.get("time") or
                    data.get("kickoff") or
                    data.get("date")
                )
                if scheduled_str:
                    try:
                        # Try parsing as ISO format
                        scheduled_at = datetime.fromisoformat(scheduled_str.replace("Z", "+00:00"))
                    except:
                        try:
                            # Try parsing as timestamp (milliseconds)
                            timestamp_ms = int(scheduled_str) if isinstance(scheduled_str, (int, str)) else scheduled_str
                            scheduled_at = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
                        except:
                            pass

        # matchDetails keeps the status under header.status (no top-level
        # "status"), so read it from there too; otherwise matchDetails
        # responses always looked SCHEDULED with no minute.
        status_data = _status_block(data)

        # Parse status from status.reason or status object
        if isinstance(status_data, dict):
            # Check for nested reason
            if "reason" in status_data and isinstance(status_data["reason"], dict):
                status_str = status_data["reason"].get("shortKey") or status_data["reason"].get("short")
            else:
                status_str = status_data.get("type") or status_data.get("reason")

            # Map FotMob status flags to status string
            if not status_str:
                if status_data.get("finished"):
                    status_str = "finished"
                elif status_data.get("started"):
                    status_str = "live"
                elif status_data.get("cancelled"):
                    status_str = "cancelled"
                else:
                    status_str = "not_started"
        else:
            status_str = str(status_data)

        status = self._parse_match_status(status_str)

        # Parse teams - FotMob matchDetails structure
        # Priority 1: general.homeTeam / general.awayTeam
        # Priority 2: header.teams[0] / header.teams[1]
        home_team = None
        away_team = None
        home_team_id = None
        away_team_id = None
        home_team_name = ""
        away_team_name = ""

        # Try general.homeTeam / awayTeam first (matchDetails primary structure)
        general_data = data.get("general") or {}
        if isinstance(general_data, dict):
            home_team = general_data.get("homeTeam")
            away_team = general_data.get("awayTeam")

        # Fallback to header.teams if general not available (match list structure)
        if not home_team or not away_team:
            header_data = data.get("header") or {}
            if isinstance(header_data, dict):
                teams = header_data.get("teams", [])
                if isinstance(teams, list) and len(teams) >= 2:
                    home_team = teams[0]
                    away_team = teams[1]

        # Fallback to old structure for backward compatibility with other endpoints
        if not home_team:
            home_team = data.get("home") or data.get("homeTeam") or {}
        if not away_team:
            away_team = data.get("away") or data.get("awayTeam") or {}

        # Extract team IDs and names
        if isinstance(home_team, dict):
            home_team_id = home_team.get("id")
            if home_team_id is not None:
                home_team_id = str(home_team_id)
            home_team_name = home_team.get("longName") or home_team.get("name", "")
        else:
            home_team_name = str(home_team) if home_team else ""

        if isinstance(away_team, dict):
            away_team_id = away_team.get("id")
            if away_team_id is not None:
                away_team_id = str(away_team_id)
            away_team_name = away_team.get("longName") or away_team.get("name", "")
        else:
            away_team_name = str(away_team) if away_team else ""

        # DATA INTEGRITY CHECK: If no valid team IDs, raise ProviderInvalidDataError
        # Do NOT fabricate team IDs - fail safely
        if not home_team_id or not away_team_id:
            match_id_for_error = (
                data.get("id") or
                data.get("matchId") or
                (general_data.get("matchId") if isinstance(general_data, dict) else None) or
                "unknown"
            )
            raise ProviderInvalidDataError(
                provider_name=self.PROVIDER_NAME,
                operation="normalize_match",
                message=f"Missing required team IDs in match data (match_id: {match_id_for_error})"
            )

        # Parse scores
        # Priority 1: header.teams[0].score / header.teams[1].score
        # Priority 2: team object scores (for backward compatibility)
        # Priority 3: existing fallbacks
        home_score = None
        away_score = None

        # Try header.teams scores first (most reliable for matchDetails)
        header_data = data.get("header") or {}
        if isinstance(header_data, dict):
            teams = header_data.get("teams", [])
            if isinstance(teams, list) and len(teams) >= 2:
                home_score = teams[0].get("score")
                away_score = teams[1].get("score")

        # Fallback: check team objects (for backward compatibility)
        if home_score is None and isinstance(home_team, dict):
            home_score = home_team.get("score")
        if away_score is None and isinstance(away_team, dict):
            away_score = away_team.get("score")

        # Fallback: check for separate score object (existing logic preserved)
        if home_score is None and "score" in data:
            home_score = data["score"].get("home")
            away_score = data["score"].get("away")
        elif home_score is None:
            home_score = data.get("homeScore") or data.get("home_score")
            away_score = data.get("awayScore") or data.get("away_score")

        # Parse competition - use league context if provided, otherwise from match data
        if league_context:
            competition_id = str(league_context.get("primaryId")) if league_context.get("primaryId") else str(league_context.get("id")) if league_context.get("id") else None
            competition_name = league_context.get("name")
        else:
            # Try general.leagueId / leagueName first (matchDetails structure)
            general_data = data.get("general") or {}
            if isinstance(general_data, dict) and general_data.get("leagueId"):
                competition_id = str(general_data["leagueId"])
                competition_name = general_data.get("leagueName")
            else:
                # Fallback to existing logic
                league_data = data.get("league") or data.get("competition") or {}
                if isinstance(league_data, dict):
                    competition_id = str(league_data.get("id")) if league_data.get("id") else None
                    competition_name = league_data.get("name")
                else:
                    # Final fallback: top-level leagueId
                    league_id = data.get("leagueId")
                    competition_id = str(league_id) if league_id else None
                    competition_name = str(league_data) if league_data else None

        # Parse minute
        minute = None
        if "minute" in data:
            minute = data.get("minute")
        elif isinstance(status_data, dict) and "minute" in status_data:
            minute = status_data.get("minute")
        added_time = data.get("addedTime") or data.get("added_time")

        # Day lists and matchDetails carry the clock only as
        # status.liveTime.short ("23’", "45+2’", "HT").
        if status in (MatchStatus.LIVE, MatchStatus.HALF_TIME):
            clock_minute, clock_added, clock_half_time = _parse_live_clock(status_data)
            if minute is None:
                minute = clock_minute
            if added_time is None:
                added_time = clock_added
            if clock_half_time:
                status = MatchStatus.HALF_TIME

        # Parse outcome
        outcome = None
        if status == MatchStatus.FINISHED:
            outcome = self._parse_match_outcome(home_score, away_score)

        return ProviderMatch(
            # Source metadata
            provider=self.PROVIDER_NAME,
            source_id=str(
                data.get("id") or
                data.get("matchId") or
                (general_data.get("matchId") if isinstance(general_data, dict) else None) or
                ""
            ),
            fetched_at=now,
            source_updated_at=None,  # FotMob doesn't typically provide this
            is_live=is_live or status in (MatchStatus.LIVE, MatchStatus.HALF_TIME),
            data_freshness_seconds=None,

            # Match identifiers
            competition_id=competition_id,
            competition_name=competition_name,
            season=None,  # FotMob doesn't always provide season in match data

            # Teams
            home_team_id=home_team_id,
            home_team_name=home_team_name,
            away_team_id=away_team_id,
            away_team_name=away_team_name,

            # Venue
            venue_name=data.get("venue") or data.get("stadium"),

            # Timing
            scheduled_at=scheduled_at,
            status=status,
            minute=minute,
            added_time=added_time,

            # Scores
            home_score=home_score,
            away_score=away_score,
            home_score_ht=None,  # Would need to parse from detailed match data
            away_score_ht=None,

            # Outcome
            outcome=outcome,

            # Match round
            # Priority 1: general.matchRound (may be int or string like "Clausura - Round 9")
            # Priority 2: existing fallbacks
            round=(
                (lambda: (
                    _parse_round(general_data.get("matchRound"))
                    if isinstance(general_data, dict) and "matchRound" in general_data and general_data.get("matchRound") is not None
                    else None
                ))() or data.get("round") or data.get("matchday")
            ),
        )

    def _extract_match_statistics(
        self,
        data: Dict[str, Any],
        match_id: str,
        home_team_id: str,
        away_team_id: str
    ) -> Tuple[Optional[ProviderMatchStats], Optional[ProviderMatchStats]]:
        """Extract match statistics from FotMob matchDetails response.

        Args:
            data: Raw matchDetails data from FotMob
            match_id: Match ID
            home_team_id: Home team ID
            away_team_id: Away team ID

        Returns:
            Tuple of (home_stats, away_stats), either may be None if unavailable
        """
        from app.providers.models import ProviderMatchStats

        now = datetime.now(timezone.utc)

        # Extract stats from content.stats.Periods.All
        content = data.get("content", {})
        if not content:
            return (None, None)

        stats_data = content.get("stats", {})
        if not stats_data:
            return (None, None)

        periods = stats_data.get("Periods", {})
        all_period = periods.get("All", {})
        stat_groups = all_period.get("stats", [])

        if not stat_groups:
            return (None, None)

        # Extract home/away values from nested structure
        home_values = {}
        away_values = {}

        for group in stat_groups:
            group_stats = group.get("stats", [])

            for stat in group_stats:
                key = stat.get("key")
                if not key:
                    continue

                raw_stats = stat.get("rawStats", [])
                if len(raw_stats) >= 2 and raw_stats[0] and raw_stats[1]:
                    home_value = raw_stats[0].get("value")
                    away_value = raw_stats[1].get("value")

                    home_values[key] = home_value
                    away_values[key] = away_value

        if not home_values and not away_values:
            return (None, None)

        # Map FotMob keys to our ProviderMatchStats fields
        def create_stats(values: Dict, team_id: str) -> ProviderMatchStats:
            return ProviderMatchStats(
                provider=self.PROVIDER_NAME,
                source_id=f"{match_id}_{team_id}",
                fetched_at=now,
                match_id=match_id,
                team_id=team_id,
                period="full",
                # Goals - not in stats, need from match data
                goals_scored=None,
                goals_conceded=None,
                # Expected goals
                xg=float(values.get("expected_goals")) if values.get("expected_goals") is not None else None,
                xg_against=None,  # Would need opponent's xg
                # Shots
                shots_total=int(values.get("total_shots")) if values.get("total_shots") is not None else None,
                shots_on_target=int(values.get("ShotsOnTarget")) if values.get("ShotsOnTarget") is not None else None,
                shots_off_target=int(values.get("ShotsOffTarget")) if values.get("ShotsOffTarget") is not None else None,
                shots_blocked=int(values.get("blocked_shots")) if values.get("blocked_shots") is not None else None,
                # Possession
                possession_percentage=float(values.get("BallPossesion")) if values.get("BallPossesion") is not None else None,
                # Passing
                passes_completed=int(values.get("accurate_passes")) if values.get("accurate_passes") is not None else None,
                passes_attempted=int(values.get("passes")) if values.get("passes") is not None else None,
                pass_accuracy=None,  # Could calculate from above
                # Set pieces
                corners=int(values.get("corners")) if values.get("corners") is not None else None,
                free_kicks=None,  # Not directly available
                offsides=int(values.get("Offsides")) if values.get("Offsides") is not None else None,
                # Discipline
                yellow_cards=int(values.get("yellow_cards")) if values.get("yellow_cards") is not None else None,
                red_cards=int(values.get("red_cards")) if values.get("red_cards") is not None else None,
                fouls_committed=int(values.get("fouls")) if values.get("fouls") is not None else None,
                # Defensive
                tackles=int(values.get("matchstats.headers.tackles")) if values.get("matchstats.headers.tackles") is not None else None,
                interceptions=int(values.get("interceptions")) if values.get("interceptions") is not None else None,
                clearances=int(values.get("clearances")) if values.get("clearances") is not None else None,
                saves=int(values.get("keeper_saves")) if values.get("keeper_saves") is not None else None,
            )

        home_stats = create_stats(home_values, home_team_id) if home_values else None
        away_stats = create_stats(away_values, away_team_id) if away_values else None

        return (home_stats, away_stats)

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

        Args:
            competition_id: Filter by competition (not supported, ignored)
            season_id: Filter by season (not supported, ignored)
            team_id: Filter by team (not supported, ignored)
            from_date: Filter matches from this date
            to_date: Filter matches to this date
            status: Filter by match status (not supported, ignored)

        Returns:
            List of ProviderMatch objects

        Raises:
            ProviderError: On request failure
        """
        import asyncio
        import logging

        logger = logging.getLogger(__name__)

        # Only date range filtering is supported by FotMob
        if not from_date or not to_date:
            # Default to today if no dates provided
            from datetime import date
            to_date = to_date or date.today()
            from_date = from_date or to_date

        try:
            # Use asyncio.run to make async method synchronous
            loop = None
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If loop is already running, we need to use a different approach
                    import concurrent.futures
                    import threading

                    def run_in_thread():
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            return new_loop.run_until_complete(
                                self.get_matches_by_range(from_date, to_date)
                            )
                        finally:
                            new_loop.close()

                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(run_in_thread)
                        matches = future.result(timeout=30)  # 30 second timeout
                else:
                    matches = loop.run_until_complete(
                        self.get_matches_by_range(from_date, to_date)
                    )
            except RuntimeError:
                # No event loop exists, create one
                matches = asyncio.run(self.get_matches_by_range(from_date, to_date))

            logger.debug(
                f"[{self.PROVIDER_NAME}] Synchronous get_matches returned "
                f"{len(matches)} matches for {from_date} to {to_date}"
            )

            return matches

        except Exception as e:
            logger.error(
                f"[{self.PROVIDER_NAME}] Synchronous get_matches failed: {e}",
                exc_info=True
            )
            # Return empty list rather than crashing - allows graceful fallback
            return []

    def get_teams(self, competition_id: str, season_id: str):
        """Get teams for a competition season.

        FotMob provider doesn't implement team lists - return empty list.
        Use Ryzellx for team metadata instead.

        Args:
            competition_id: Competition ID (ignored)
            season_id: Season ID (ignored)

        Returns:
            Empty list (not implemented)
        """
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(
            f"[{self.PROVIDER_NAME}] get_teams not implemented - "
            f"use Ryzellx for team metadata"
        )

        return []

    def get_competitions(self):
        """Get available competitions.

        FotMob provider doesn't implement competition lists - return empty list.
        Use Ryzellx for competition metadata instead.

        Returns:
            Empty list (not implemented)
        """
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(
            f"[{self.PROVIDER_NAME}] get_competitions not implemented - "
            f"use Ryzellx for competition metadata"
        )

        return []

    def get_competition(self, competition_id: str):
        """Get a specific competition.

        Args:
            competition_id: Competition ID (ignored)

        Returns:
            None (not implemented)
        """
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(
            f"[{self.PROVIDER_NAME}] get_competition not implemented - "
            f"use Ryzellx for competition metadata"
        )

        return None

    def get_seasons(self, competition_id: str):
        """Get seasons for a competition.

        Args:
            competition_id: Competition ID (ignored)

        Returns:
            Empty list (not implemented)
        """
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(
            f"[{self.PROVIDER_NAME}] get_seasons not implemented - "
            f"use Ryzellx for competition metadata"
        )

        return []

    def get_current_season(self, competition_id: str):
        """Get current season for a competition.

        Args:
            competition_id: Competition ID (ignored)

        Returns:
            None (not implemented)
        """
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(
            f"[{self.PROVIDER_NAME}] get_current_season not implemented - "
            f"use Ryzellx for competition metadata"
        )

        return None

    def get_team(self, team_id: str):
        """Get a specific team.

        Args:
            team_id: Team ID (ignored)

        Returns:
            None (not implemented)
        """
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(
            f"[{self.PROVIDER_NAME}] get_team not implemented - "
            f"use Ryzellx for team metadata"
        )

        return None

    def get_match(self, match_id: str):
        """Get a specific match.

        Args:
            match_id: Match ID (ignored)

        Returns:
            None (not implemented)
        """
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(
            f"[{self.PROVIDER_NAME}] get_match not implemented - "
            f"use Ryzellx for match metadata"
        )

        return None

    async def get_match_statistics(
        self,
        match_id: str,
        period: str = 'full'
    ) -> Tuple[Optional[ProviderMatchStats], Optional[ProviderMatchStats]]:
        """Get match statistics from FotMob matchDetails.

        Args:
            match_id: FotMob match ID
            period: Period to fetch ('full' only supported by FotMob)

        Returns:
            Tuple of (home_stats, away_stats), both None if not found

        Raises:
            ProviderError: On request failure (except 404)
        """
        from app.providers.models import ProviderMatchStats

        # Check cache
        cache_key = f"{self.PROVIDER_NAME}:stats:{match_id}:{period}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.debug(f"[{self.PROVIDER_NAME}] Cache hit: {cache_key}")
                return cached

        # Fetch match details (includes statistics)
        try:
            endpoint = "/api/data/matchDetails"
            params = {"matchId": match_id}
            data = await self._request("GET", endpoint, params=params)

            # Extract team IDs from match data first
            general_data = data.get("general", {})
            home_team_data = general_data.get("homeTeam", {})
            away_team_data = general_data.get("awayTeam", {})

            home_team_id = str(home_team_data.get("id", ""))
            away_team_id = str(away_team_data.get("id", ""))

            if not home_team_id or not away_team_id:
                # Fallback to header.teams
                header_data = data.get("header", {})
                teams = header_data.get("teams", [])
                if len(teams) >= 2:
                    home_team_id = str(teams[0].get("id", ""))
                    away_team_id = str(teams[1].get("id", ""))

            if not home_team_id or not away_team_id:
                logger.warning(f"[{self.PROVIDER_NAME}] Could not extract team IDs for match {match_id}")
                return (None, None)

            # Extract statistics
            home_stats, away_stats = self._extract_match_statistics(
                data, match_id, home_team_id, away_team_id
            )

            # Cache result
            if self.cache:
                ttl = HISTORICAL_MATCH_TTL  # Statistics are static after match
                self.cache.set(cache_key, (home_stats, away_stats), ttl_seconds=ttl)

            logger.info(f"[{self.PROVIDER_NAME}] Fetched statistics for match {match_id}")
            return (home_stats, away_stats)

        except ProviderNotFoundError:
            logger.info(f"[{self.PROVIDER_NAME}] Statistics for match {match_id} not found")
            return (None, None)
        except ProviderError:
            raise

    async def get_matches_by_date(self, date_obj: date) -> List[ProviderMatch]:
        """Get matches for a specific date.

        FotMob typically provides daily matches through endpoints like:
        /api/matches?date=YYYYMMDD

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

        # Fetch from API - FotMob uses YYYYMMDD format
        date_str = date_obj.strftime("%Y%m%d")
        endpoint = "/api/data/matches"
        params = {"date": date_str}

        try:
            data = await self._request("GET", endpoint, params=params)
        except ProviderError:
            # If request fails, raise error (never invent data)
            raise

        # Parse response - FotMob structure may vary
        matches = []

        # FotMob typically nests matches in leagues
        if isinstance(data, dict):
            # Check for matches in various possible structures
            if "leagues" in data:
                for league in data["leagues"]:
                    league_matches = league.get("matches", [])
                    for match_data in league_matches:
                        try:
                            # Pass league context for better normalization
                            match = self._normalize_match(match_data, is_live=False, league_context=league)
                            matches.append(match)
                        except Exception as e:
                            logger.warning(
                                f"[{self.PROVIDER_NAME}] Failed to normalize match: {e}"
                            )
            elif "matches" in data:
                for match_data in data["matches"]:
                    try:
                        match = self._normalize_match(match_data, is_live=False)
                        matches.append(match)
                    except Exception as e:
                        logger.warning(
                            f"[{self.PROVIDER_NAME}] Failed to normalize match: {e}"
                        )
        elif isinstance(data, list):
            for match_data in data:
                try:
                    match = self._normalize_match(match_data, is_live=False)
                    matches.append(match)
                except Exception as e:
                    logger.warning(
                        f"[{self.PROVIDER_NAME}] Failed to normalize match: {e}"
                    )

        # Cache result with appropriate TTL
        if self.cache:
            today = date.today()
            if date_obj == today:
                ttl = LIVE_DATA_TTL
            else:
                ttl = UPCOMING_FIXTURES_TTL
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

        FotMob doesn't have a native range endpoint, so we iterate through dates.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List of ProviderMatch in the range

        Raises:
            ProviderError: On request failure
        """
        from datetime import timedelta

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

        # Iterate through dates and collect matches
        # OPTIMIZATION: Use bounded concurrency instead of serial loop
        # Track successful vs failed days to distinguish legitimate empty from failure
        all_matches = []
        successful_dates = []
        failed_dates = []

        # OPTIMIZATION: Bounded concurrent fetching (Section 1 & 4 of performance spec)
        # Use semaphore to limit concurrent requests (respects rate limits)
        # Conservative limit: 2 concurrent requests to unofficial FotMob API
        import asyncio
        MAX_CONCURRENT_REQUESTS = 2
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

        async def fetch_single_date(fetch_date: date) -> tuple:
            """Fetch matches for a single date with semaphore control."""
            async with semaphore:
                try:
                    daily_matches = await self.get_matches_by_date(fetch_date)
                    return (fetch_date, daily_matches, None)
                except ProviderError as e:
                    return (fetch_date, [], str(e))

        # Generate all dates in range
        dates_to_fetch = []
        current_date = start_date
        while current_date <= end_date:
            dates_to_fetch.append(current_date)
            current_date += timedelta(days=1)

        # Fetch all dates concurrently with bounded parallelism
        tasks = [fetch_single_date(d) for d in dates_to_fetch]
        results = await asyncio.gather(*tasks)

        # Process results
        for fetch_date, daily_matches, error in results:
            if error is None:
                successful_dates.append(fetch_date)
                all_matches.extend(daily_matches)
            else:
                failed_dates.append(fetch_date)
                logger.warning(
                    f"[{self.PROVIDER_NAME}] Failed to fetch matches for {fetch_date}: {error}"
                )

        # If NO successful dates, raise ProviderError (don't return empty list)
        # This allows manager to try fallback providers
        if not successful_dates:
            raise ProviderError(
                provider_name=self.PROVIDER_NAME,
                operation='get_matches_by_range',
                message=f'Fixture data unavailable for requested range {start_date} to {end_date} - all {len(failed_dates)} days failed'
            )

        # If partial success, cache what we got
        if failed_dates:
            logger.warning(
                f"[{self.PROVIDER_NAME}] Partial data coverage: "
                f"{len(successful_dates)} successful, {len(failed_dates)} failed days"
            )

        # Cache result with TTL based on date range
        if self.cache:
            today = date.today()
            if end_date < today:
                # Historical data - longer TTL
                ttl = HISTORICAL_MATCH_TTL
            elif start_date > today:
                # Future data - medium TTL
                ttl = UPCOMING_FIXTURES_TTL
            else:
                # Range includes today - short TTL
                ttl = LIVE_DATA_TTL
            self.cache.set(cache_key, all_matches, ttl_seconds=ttl)

        logger.info(
            f"[{self.PROVIDER_NAME}] Fetched {len(all_matches)} matches for range {start_date} to {end_date} "
            f"(successful days: {len(successful_dates)}, failed days: {len(failed_dates)})"
        )
        return all_matches

    async def get_match(self, match_id: str) -> Optional[ProviderMatch]:
        """Get detailed match information.

        FotMob typically provides match details through:
        /api/matchDetails?matchId={match_id}

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
            endpoint = "/api/data/matchDetails"
            params = {"matchId": match_id}
            data = await self._request("GET", endpoint, params=params)

            # Normalize match
            is_live = False
            if "status" in data:
                status_data = data["status"]
                if isinstance(status_data, dict):
                    status_str = status_data.get("type", "")
                else:
                    status_str = str(status_data)
                is_live = "live" in status_str.lower()

            match = self._normalize_match(data, is_live=is_live)

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

        FotMob's live match detection has issues. As emergency fallback,
        we'll use ESPN's live data and cross-reference with FotMob match IDs.

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

        # Emergency fix: Use ESPN for live detection, FotMob for match details
        now = datetime.now(timezone.utc)
        live_matches = []

        try:
            # Step 1: Get live matches from ESPN using existing httpx client
            espn_response = await self._client.get("https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard")

            # Check ESPN HTTP status
            if espn_response.status_code != 200:
                logger.error(
                    f"[{self.PROVIDER_NAME}] ESPN API failed with status {espn_response.status_code}"
                )
                raise ProviderError(
                    provider_name=self.PROVIDER_NAME,
                    operation="get_live_matches",
                    message=f"ESPN API returned HTTP {espn_response.status_code}",
                    original_error=None
                )

            # Parse ESPN JSON
            try:
                espn_data = espn_response.json()
            except Exception as json_err:
                logger.error(f"[{self.PROVIDER_NAME}] ESPN returned invalid JSON: {json_err}")
                raise ProviderError(
                    provider_name=self.PROVIDER_NAME,
                    operation="get_live_matches",
                    message="ESPN API returned invalid JSON",
                    original_error=json_err
                )

            if not espn_data or 'events' not in espn_data:
                logger.warning(f"[{self.PROVIDER_NAME}] ESPN response missing events field")
                raise ProviderError(
                    provider_name=self.PROVIDER_NAME,
                    operation="get_live_matches",
                    message="ESPN API response missing 'events' field",
                    original_error=None
                )

            live_match_names = set()
            for event in espn_data['events']:
                status = event.get('status', {})
                type_info = status.get('type', {})

                if type_info.get('state') == 'in':  # ESPN live state
                    match_name = event.get('name', '')
                    if match_name:
                        live_match_names.add(match_name.lower())

            if not live_match_names:
                logger.info(f"[{self.PROVIDER_NAME}] No live matches found via ESPN")
                return []

            logger.info(f"[{self.PROVIDER_NAME}] Found {len(live_match_names)} live matches via ESPN")

            # Step 2: Get today's matches from FotMob and match with ESPN live matches
            today = date.today()
            date_str = today.strftime("%Y%m%d")
            endpoint = "/api/data/matches"
            params = {"date": date_str}
            data = await self._request("GET", endpoint, params=params)

        except ProviderError:
            # If request fails, raise error (never invent data)
            raise
        except Exception as e:
            logger.error(f"[{self.PROVIDER_NAME}] Emergency live match detection failed: {e}")
            raise ProviderError(
                provider_name=self.PROVIDER_NAME,
                operation="get_live_matches",
                message=f"Live match detection failed: {e}",
                original_error=e
            )

        # Parse FotMob response and cross-reference with ESPN
        match_list = []
        if isinstance(data, dict):
            if "leagues" in data:
                for league in data["leagues"]:
                    match_list.extend(league.get("matches", []))
            elif "matches" in data:
                match_list = data["matches"]
        elif isinstance(data, list):
            match_list = data

        # Cross-reference FotMob matches with ESPN live matches
        for match_data in match_list:
            try:
                # Build match name for comparison
                home_team = match_data.get("home", {})
                away_team = match_data.get("away", {})

                if isinstance(home_team, dict):
                    home_name = home_team.get("longName") or home_team.get("name", "")
                    home_team_id = str(home_team.get("id", ""))
                    home_score = home_team.get("score", 0) or 0
                else:
                    home_name = str(home_team)
                    home_team_id = ""
                    home_score = 0

                if isinstance(away_team, dict):
                    away_name = away_team.get("longName") or away_team.get("name", "")
                    away_team_id = str(away_team.get("id", ""))
                    away_score = away_team.get("score", 0) or 0
                else:
                    away_name = str(away_team)
                    away_team_id = ""
                    away_score = 0

                # Skip matches without proper team data
                if not home_name or not away_name or not home_team_id or not away_team_id:
                    continue

                # Normalize team names for safe matching (remove extra spaces, common suffixes)
                def normalize_team_name(name: str) -> str:
                    """Normalize team name for matching."""
                    normalized = name.lower().strip()
                    # Remove common prefixes and suffixes that might differ between providers
                    # Handle prefix like "FC", "AC" at the start
                    tokens = normalized.split()
                    if len(tokens) > 1:
                        if tokens[0] in ['fc', 'ac', 'sc', 'cf', 'bk', 'afc', 'rcd']:
                            normalized = ' '.join(tokens[1:])
                        elif tokens[-1] in ['fc', 'ac', 'sc', 'cf', 'bk', 'afc']:
                            normalized = ' '.join(tokens[:-1])
                    return normalized.strip()

                home_normalized = normalize_team_name(home_name)
                away_normalized = normalize_team_name(away_name)

                # Check if this match is live according to ESPN
                # ESPN format: "Away Team at Home Team"
                # Match only if BOTH teams are found in the ESPN match name
                is_live_match = False
                for espn_live_name in live_match_names:
                    # Extract teams from ESPN format: "team1 at team2"
                    if ' at ' in espn_live_name:
                        parts = espn_live_name.split(' at ')
                        if len(parts) == 2:
                            espn_away = normalize_team_name(parts[0])
                            espn_home = normalize_team_name(parts[1])

                            # Exact match: both teams must match (order matters)
                            if espn_home == home_normalized and espn_away == away_normalized:
                                is_live_match = True
                                break

                if not is_live_match:
                    continue

                logger.info(f"[{self.PROVIDER_NAME}] Matched live match: {home_name} vs {away_name} ({home_score}-{away_score})")

                # Parse match data
                status = MatchStatus.LIVE  # We know it's live from ESPN

                # Parse minute and status details
                minute = match_data.get("minute")
                status_data = match_data.get("status", {})
                if isinstance(status_data, dict):
                    if not minute:
                        minute = status_data.get("minute")
                    # Check if it's actually live
                    if status_data.get("finished"):
                        continue  # Skip finished matches
                    if not status_data.get("started"):
                        continue  # Skip not started matches

                # The day list carries the clock as status.liveTime.short
                added_time = match_data.get("addedTime") or match_data.get("added_time")
                clock_minute, clock_added, clock_half_time = _parse_live_clock(status_data)
                if minute is None:
                    minute = clock_minute
                if added_time is None:
                    added_time = clock_added
                if clock_half_time:
                    status = MatchStatus.HALF_TIME

                # Get match ID
                match_id = str(match_data.get("id") or match_data.get("matchId", ""))
                if not match_id:
                    continue

                # Parse league/competition info
                competition_id = str(match_data.get("leagueId", ""))

                live_match = ProviderLiveMatch(
                    # Source metadata
                    provider=self.PROVIDER_NAME,
                    source_id=match_id,
                    fetched_at=now,
                    source_updated_at=None,
                    is_live=True,
                    data_freshness_seconds=None,

                    # Live state
                    match_id=match_id,
                    status=status,
                    minute=minute,
                    added_time=added_time,

                    # Teams
                    home_team_id=home_team_id,
                    home_team_name=home_name,
                    away_team_id=away_team_id,
                    away_team_name=away_name,

                    # Competition
                    competition_id=competition_id,

                    # Scores
                    home_score=home_score,
                    away_score=away_score,

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
            f"[{self.PROVIDER_NAME}] Fetched {len(live_matches)} live matches (ESPN cross-reference)"
        )
        return live_matches

    async def get_league(self, league_id: str) -> Optional[ProviderCompetition]:
        """Get league/competition information.

        STUB: FotMob league lookup not implemented — use Ryzellx or OpenLigaDB for metadata.

        Args:
            league_id: League ID

        Returns:
            None (not implemented)
        """
        logger.debug(
            f"[{self.PROVIDER_NAME}] get_league not implemented — "
            f"use Ryzellx or OpenLigaDB for league metadata"
        )
        return None

    async def get_team(self, team_id: str) -> Optional[ProviderTeam]:
        """Get team information.

        STUB: FotMob team lookup not a priority — use Ryzellx instead.

        Args:
            team_id: Team ID

        Returns:
            None (not implemented)
        """
        logger.debug(
            f"[{self.PROVIDER_NAME}] get_team not implemented — "
            f"use Ryzellx for team metadata"
        )
        return None

    async def get_player(self, player_id: str) -> Optional[ProviderPlayer]:
        """Get player information.

        STUB: FotMob player lookup not a priority — use Ryzellx instead.

        Args:
            player_id: Player ID

        Returns:
            None (not implemented)
        """
        logger.debug(
            f"[{self.PROVIDER_NAME}] get_player not implemented — "
            f"use Ryzellx for player metadata"
        )
        return None

    async def get_standings(self, league_id: str) -> List[ProviderStanding]:
        """Get league standings/table.

        STUB: FotMob standings not a priority — use Ryzellx or OpenLigaDB instead.

        Args:
            league_id: League ID

        Returns:
            Empty list (not implemented)
        """
        logger.debug(
            f"[{self.PROVIDER_NAME}] get_standings not implemented — "
            f"use Ryzellx or OpenLigaDB for standings"
        )
        return []

    def get_standings(self, competition_id: str, season_id: str):
        """Get league standings (synchronous wrapper).

        This method provides compatibility with the base FootballDataProvider interface
        which requires a synchronous get_standings method.

        Args:
            competition_id: Competition ID (ignored)
            season_id: Season ID (ignored)

        Returns:
            Empty list (not implemented)
        """
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(
            f"[{self.PROVIDER_NAME}] synchronous get_standings not implemented — "
            f"use Ryzellx or OpenLigaDB for standings"
        )

        return []
