"""Live matches endpoint for API v1.

This module implements the live matches REST API endpoint with
provider health and data quality reporting.

CRITICAL: NEVER returns fabricated match data. Returns empty list
with provider health status on failure.
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.config import settings
from app.providers.models import ProviderLiveMatch
from app.providers.manager import ProviderManager
from app.providers.cache import ProviderCache
from app.providers.ryzellx import RyzellxFootballProvider
from app.providers.fotmob import FotMobFootballProvider
from app.providers.openligadb import OpenLigaDBFootballProvider
from app.providers.health import ProviderHealthService


router = APIRouter(prefix="/matches", tags=["live-matches"])
logger = logging.getLogger(__name__)

# Providers whose match ids the rest of the app addresses as
# "{provider}_{source_id}" (see ProviderManagerAdapter.get_match).
_PREFIXED_ID_PROVIDERS = {"fotmob", "ryzellx", "openligadb", "sofascore"}
_PROVIDER_HEALTH_CACHE_KEY = "live_matches:provider_health"
_PROVIDER_HEALTH_LAST_KNOWN_KEY = "live_matches:provider_health:last_known"
_PROVIDER_HEALTH_TTL_SECONDS = 30
_PROVIDER_HEALTH_LAST_KNOWN_TTL_SECONDS = 600
_provider_health_refresh: Optional["asyncio.Future"] = None


class LiveMatchResponse(BaseModel):
    """Live match response schema."""

    match_id: str
    status: str
    minute: Optional[int] = None
    added_time: Optional[int] = None  # e.g. 2 for "45+2'"; None when not supplied
    home_score: int
    away_score: int
    home_team_id: Optional[str] = None
    away_team_id: Optional[str] = None
    home_team: Optional[str] = None  # Team name for display
    away_team: Optional[str] = None  # Team name for display
    data_quality_flags: Dict[str, bool] = Field(default_factory=dict)


class LiveMatchesResponse(BaseModel):
    """Live matches API response."""

    matches: List[LiveMatchResponse] = Field(
        default_factory=list,
        description="List of live matches"
    )

    provider_health: Dict[str, Any] = Field(
        default_factory=dict,
        description="Provider health status"
    )

    data_quality: Dict[str, Any] = Field(
        default_factory=dict,
        description="Aggregated data quality indicators"
    )

    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response timestamp"
    )

    provider_used: Optional[str] = Field(
        None,
        description="Provider that supplied the data"
    )

    total_count: int = Field(
        0,
        description="Total number of live matches"
    )


def _build_data_quality_flags(match: ProviderLiveMatch) -> Dict[str, bool]:
    """Build data quality flags from ProviderLiveMatch.

    Args:
        match: Provider live match data

    Returns:
        Dict of data quality flags
    """
    flags = {}

    if match.data_quality:
        flags = {
            "has_xg": match.data_quality.has_xg,
            "has_events": match.data_quality.has_events,
            "has_shots": match.data_quality.has_shots,
            "has_player_positions": match.data_quality.has_player_positions,
            "has_ball_tracking": match.data_quality.has_ball_tracking,
            "has_shot_coordinates": match.data_quality.has_shot_coordinates,
            "has_live_statistics": match.data_quality.has_live_statistics,
        }
    else:
        # Infer from available data
        flags = {
            "has_xg": False,
            "has_events": match.live_events is not None and len(match.live_events) > 0,
            "has_shots": False,
            "has_player_positions": match.player_positions is not None,
            "has_ball_tracking": match.ball_position is not None,
            "has_shot_coordinates": False,
            "has_live_statistics": False,
        }

    return flags


def _aggregate_data_quality(matches: List[ProviderLiveMatch]) -> Dict[str, Any]:
    """Aggregate data quality across all matches.

    Args:
        matches: List of provider live matches

    Returns:
        Dict with aggregated quality statistics
    """
    if not matches:
        return {
            "total_matches": 0,
            "matches_with_xg": 0,
            "matches_with_events": 0,
            "matches_with_shots": 0,
            "matches_with_player_positions": 0,
            "matches_with_ball_tracking": 0,
        }

    total = len(matches)
    with_xg = 0
    with_events = 0
    with_shots = 0
    with_positions = 0
    with_ball = 0

    for match in matches:
        flags = _build_data_quality_flags(match)
        if flags.get("has_xg"):
            with_xg += 1
        if flags.get("has_events"):
            with_events += 1
        if flags.get("has_shots"):
            with_shots += 1
        if flags.get("has_player_positions"):
            with_positions += 1
        if flags.get("has_ball_tracking"):
            with_ball += 1

    return {
        "total_matches": total,
        "matches_with_xg": with_xg,
        "matches_with_events": with_events,
        "matches_with_shots": with_shots,
        "matches_with_player_positions": with_positions,
        "matches_with_ball_tracking": with_ball,
    }


_LIVE_STATUSES = {"LIVE", "HALF_TIME"}


def _normalize_live_match_id(match_id: Any, provider: Optional[str]) -> str:
    """Return the app-wide id form "{provider}_{source_id}".

    ProviderManager's live path returns bare source ids ("6106414") while the
    match list and match pages use "fotmob_6106414". Ids that already carry
    the prefix, and ids of providers without a prefixed route, are unchanged.
    """
    match_id = str(match_id)
    provider = (provider or "").lower()
    if provider not in _PREFIXED_ID_PROVIDERS or match_id.startswith(f"{provider}_"):
        return match_id
    return f"{provider}_{match_id}"


def _shared_provider_cache() -> ProviderCache:
    """Application-level provider cache (falls back to a request-local one)."""
    try:
        from app.main import app_state

        if app_state.provider_cache is not None:
            return app_state.provider_cache
    except Exception:  # pragma: no cover - app not initialised (tests/scripts)
        pass
    return ProviderCache()


async def _fotmob_daily_matches(fotmob: FotMobFootballProvider) -> List[Any]:
    """FotMob's fixture list for today (UTC), via the provider's short-TTL cache.

    Shortly after midnight UTC, yesterday's list is included too so matches
    that kicked off before midnight are not lost. Days that fail are skipped;
    never fabricates data.
    """
    now = datetime.now(timezone.utc)
    days = [now.date()] + ([now.date() - timedelta(days=1)] if now.hour < 3 else [])
    result: List[Any] = []
    for day in days:
        try:
            result.extend(await fotmob.get_matches_by_date(day))
        except Exception as exc:
            logger.warning(f"live matches: FotMob day list {day} unavailable: {exc}")
    return result


async def _fotmob_live_from_daily_list(
    fotmob: FotMobFootballProvider,
    league_id: Optional[str],
    daily_matches: Optional[List[Any]] = None,
) -> List[LiveMatchResponse]:
    """Live matches from FotMob's fixture list for today (UTC).

    Returns [] on any failure; never fabricates data.
    """
    if daily_matches is None:
        daily_matches = await _fotmob_daily_matches(fotmob)
    seen = set()
    result: List[LiveMatchResponse] = []
    if daily_matches:
        for m in daily_matches:
            status = m.status.value if hasattr(m.status, "value") else str(m.status)
            if status not in _LIVE_STATUSES:
                continue
            if league_id and str(m.competition_id) != str(league_id):
                continue
            match_id = _normalize_live_match_id(m.source_id, m.provider)
            if match_id in seen or m.home_score is None or m.away_score is None:
                continue
            seen.add(match_id)
            result.append(
                LiveMatchResponse(
                    match_id=match_id,
                    status=status,
                    minute=m.minute,
                    added_time=m.added_time,
                    home_score=m.home_score,
                    away_score=m.away_score,
                    home_team_id=m.home_team_id,
                    away_team_id=m.away_team_id,
                    home_team=m.home_team_name,
                    away_team=m.away_team_name,
                    data_quality_flags={
                        "has_xg": False,
                        "has_events": False,
                        "has_shots": False,
                        "has_player_positions": False,
                        "has_ball_tracking": False,
                        "has_shot_coordinates": False,
                        "has_live_statistics": False,
                    },
                )
            )
    return result


async def _probe_provider_health(
    health_service: ProviderHealthService, cache: ProviderCache
) -> Dict[str, Any]:
    try:
        health_statuses = await health_service.check_all()
    except Exception as exc:
        logger.warning(f"live matches: provider health probe failed: {exc}")
        return {}
    provider_health = {
        name: {
            "is_available": status.is_available,
            "availability_code": status.availability_code.value,
            "last_check_utc": status.last_check_utc.isoformat(),
            "consecutive_failures": status.consecutive_failures,
            "error_detail": status.error_detail,
        }
        for name, status in health_statuses.items()
    }
    cache.set(_PROVIDER_HEALTH_CACHE_KEY, provider_health, ttl_seconds=_PROVIDER_HEALTH_TTL_SECONDS)
    cache.set(
        _PROVIDER_HEALTH_LAST_KNOWN_KEY, provider_health,
        ttl_seconds=_PROVIDER_HEALTH_LAST_KNOWN_TTL_SECONDS,
    )
    return provider_health


async def _cached_provider_health(
    health_service: ProviderHealthService, cache: ProviderCache
) -> Dict[str, Any]:
    """Provider health, re-probed at most every 30 s without blocking polls.

    Live pages poll this endpoint and an unreachable provider can take seconds
    to refuse a connection. A fresh (< 30 s) result is served from the cache;
    an older one is served as-is (each entry keeps its own last_check_utc)
    while one background probe refreshes it. Only the first call waits.
    """
    global _provider_health_refresh
    fresh = cache.get(_PROVIDER_HEALTH_CACHE_KEY)
    if fresh is not None:
        return fresh
    loop = asyncio.get_running_loop()
    if (
        _provider_health_refresh is None
        or _provider_health_refresh.done()
        or _provider_health_refresh.get_loop() is not loop
    ):
        _provider_health_refresh = asyncio.ensure_future(
            _probe_provider_health(health_service, cache)
        )
    last_known = cache.get(_PROVIDER_HEALTH_LAST_KNOWN_KEY)
    if last_known is not None:
        return last_known
    return await asyncio.shield(_provider_health_refresh)


@router.get(
    "/live",
    response_model=LiveMatchesResponse,
    summary="Get live matches",
    description="Get currently live matches with provider health and data quality reporting.",
)
async def get_live_matches(
    league_id: Optional[str] = Query(None, description="Filter by league ID"),
    include_stats: bool = Query(False, description="Include live statistics"),
) -> LiveMatchesResponse:
    """
    Get currently live matches.

    Returns live matches from the provider with health and quality information.
    On provider failure, returns empty matches list with provider health status.
    NEVER fabricates match data.

    Query Parameters:
    - league_id: Optional filter by league/competition ID
    - include_stats: Whether to include live statistics (not yet implemented)

    Returns:
        LiveMatchesResponse with matches, provider health, and data quality
    """
    # Shared application-level cache: live entries expire after
    # LIVE_DATA_TTL (30 s), so polling does not refetch everything each time.
    cache = _shared_provider_cache()

    # Create provider instances
    ryzellx = RyzellxFootballProvider(
        base_url=settings.ryzellx_base_url,
        timeout_seconds=settings.provider_timeout_seconds,
        retry_count=settings.provider_retry_count,
        cache=cache,
    )

    fotmob = FotMobFootballProvider(
        base_url=settings.fotmob_base_url,
        timeout_seconds=settings.provider_timeout_seconds,
        retry_count=min(settings.provider_retry_count, 1),
        cache=cache,
    )

    openligadb = OpenLigaDBFootballProvider(
        base_url=settings.openligadb_base_url,
        timeout_seconds=settings.provider_timeout_seconds,
        retry_count=settings.provider_retry_count,
        cache=cache,
    )

    # Create provider manager
    manager = ProviderManager(
        ryzellx=ryzellx,
        fotmob=fotmob,
        openligadb=openligadb,
        cache=cache,
    )

    # Create health service
    health_service = ProviderHealthService(
        provider_configs={
            "ryzellx": {
                "base_url": settings.ryzellx_base_url,
                "test_endpoints": ["/api/matches/live"],
            },
            "fotmob": {
                "base_url": settings.fotmob_base_url,
                "test_endpoints": [f"/api/data/matches?date={datetime.utcnow().strftime('%Y%m%d')}"],
            },
            "openligadb": {
                "base_url": settings.openligadb_base_url,
                "test_endpoints": ["/getavailableleagues"],
            },
        },
        timeout_seconds=settings.provider_timeout_seconds,
    )

    # Provider health runs concurrently with the live fetch (an unreachable
    # provider can take seconds to refuse; see _cached_provider_health).
    health_task = asyncio.ensure_future(_cached_provider_health(health_service, cache))

    try:
        # Get live matches from manager
        matches_raw, metadata = await manager.get_live_matches()

        # Extract provider used
        provider_used = metadata.get("selected_provider")

        daily_matches = None
        if league_id and matches_raw:
            # The live feed's competition ids can be FotMob sub-league ids
            # (e.g. 943230 for the Champions League, parent 42); the day list
            # carries the parent id the rest of the app filters by.
            daily_matches = await _fotmob_daily_matches(fotmob)
            daily_competition = {
                _normalize_live_match_id(m.source_id, m.provider): str(m.competition_id)
                for m in daily_matches
            }
            wanted = str(league_id)
            matches_raw = [
                m for m in matches_raw
                if str(m.competition_id) == wanted
                or daily_competition.get(_normalize_live_match_id(m.match_id, m.provider)) == wanted
            ]

        # Convert to response schema
        matches_response = []
        if not matches_raw:
            # No dedicated live feed answered (Ryzellx is not configured).
            # FotMob's daily fixture list carries real live status, minute and
            # score, so serve those instead of an empty page.
            fallback = await _fotmob_live_from_daily_list(fotmob, league_id, daily_matches)
            if fallback:
                matches_response = fallback
                provider_used = "fotmob_daily_list"
        for match in matches_raw:
            match_response = LiveMatchResponse(
                match_id=_normalize_live_match_id(match.match_id, match.provider),
                status=match.status.value if hasattr(match.status, 'value') else str(match.status),
                minute=match.minute,
                added_time=match.added_time,
                home_score=match.home_score,
                away_score=match.away_score,
                home_team_id=match.home_team_id,
                away_team_id=match.away_team_id,
                home_team=match.home_team_name,  # Add team names
                away_team=match.away_team_name,  # Add team names
                data_quality_flags=_build_data_quality_flags(match),
            )
            matches_response.append(match_response)

        # Get provider health status
        provider_health = await health_task

        # Aggregate data quality
        data_quality = _aggregate_data_quality(matches_raw)
        if provider_used == "fotmob_daily_list":
            # Fallback rows carry score/minute only (no events, shots or xG)
            data_quality = {**data_quality, "total_matches": len(matches_response), "source": provider_used}

        # Build response
        return LiveMatchesResponse(
            matches=matches_response,
            provider_health=provider_health,
            data_quality=data_quality,
            timestamp=datetime.utcnow(),
            provider_used=provider_used,
            total_count=len(matches_response),
        )

    except Exception as e:
        # On any error, return empty list with health status
        # NEVER fabricate match data
        logger.warning(f"live matches: request failed: {type(e).__name__}: {e}")
        try:
            provider_health = await health_task
        except Exception:
            provider_health = {}

        return LiveMatchesResponse(
            matches=[],
            provider_health=provider_health,
            data_quality={"total_matches": 0, "error": str(type(e).__name__)},
            timestamp=datetime.utcnow(),
            provider_used=None,
            total_count=0,
        )

    finally:
        # Clean up
        if not health_task.done():
            health_task.cancel()
        await manager.close()
