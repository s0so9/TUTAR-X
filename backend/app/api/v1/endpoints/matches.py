"""Match endpoints for API v1.

This module implements the match-related REST API endpoints.
"""

from typing import Any, Dict, Optional
from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_data_provider
from app.database.session import get_db
from app.api.v1.schemas import (
    MatchListResponse,
    MatchDetailResponse,
    MatchResponse,
    ErrorResponse,
    MatchPredictionResponse,
    MarketAnalysisResponse,
    MarketOutcomeResponse,
    BookmakerComparisonResponse,
    EasyMatchResponse,
    TeamInfoResponse,
    EasyMatchSignalResponse,
    MatchStatisticsResponse,
)
from app.providers import FootballDataProvider
from app.prediction.service import PredictionService
from app.domain.entities import Team
from app.domain.statistics import TeamMatchStatistic
from app.domain.enums import MatchStatus


router = APIRouter(prefix="/matches", tags=["matches"])


def featured_competition_ids() -> set[str]:
    from app.config import settings

    return {x.strip() for x in str(settings.featured_competition_ids or "").split(",") if x.strip()}


def _map_team_to_response(team: Optional[Team]) -> Optional[TeamInfoResponse]:
    """Map Team domain model to TeamInfoResponse schema."""
    if team is None:
        return None
    return TeamInfoResponse(
        id=team.id,
        name=team.name,
        short_name=team.short_name,
        code=team.code,
        logo_url=team.logo_url,
    )


def _map_statistic_to_response(stat: Optional[TeamMatchStatistic]) -> Optional[MatchStatisticsResponse]:
    """Map TeamMatchStatistic domain model to MatchStatisticsResponse schema."""
    if stat is None:
        return None
    return MatchStatisticsResponse(
        goals_scored=stat.goals_scored,
        goals_conceded=stat.goals_conceded,
        xg=stat.xg,
        xg_against=stat.xg_against,
        shots_total=stat.shots_total,
        shots_on_target=stat.shots_on_target,
        shots_off_target=stat.shots_off_target,
        shots_blocked=stat.shots_blocked,
        possession_percentage=stat.possession_percentage,
        passes_completed=stat.passes_completed,
        passes_attempted=stat.passes_attempted,
        pass_accuracy=stat.pass_accuracy,
        corners=stat.corners,
        free_kicks=stat.free_kicks,
        offsides=stat.offsides,
        yellow_cards=stat.yellow_cards,
        red_cards=stat.red_cards,
        fouls_committed=stat.fouls_committed,
        tackles=stat.tackles,
        interceptions=stat.interceptions,
        clearances=stat.clearances,
        saves=stat.saves,
    )


def _map_market_outcome_to_response(outcome) -> MarketOutcomeResponse:
    """Map MarketOutcome domain model to MarketOutcomeResponse schema.
    
    Phase 5: Includes optional market intelligence fields when available.
    Odds & Value Intelligence: Includes value classification and scoring fields.
    """
    return MarketOutcomeResponse(
        label=outcome.label,
        model_probability=outcome.model_probability,
        calibrated_probability=outcome.calibrated_probability,
        fair_odds=outcome.fair_odds,
        # Phase 5 fields (all optional, backward compatible)
        real_odds=outcome.real_odds,
        implied_probability=outcome.implied_probability,
        market_edge=outcome.market_edge,
        bookmaker=outcome.bookmaker,
        odds_timestamp=outcome.odds_timestamp,
        # Odds & Value Intelligence fields (all optional, backward compatible)
        expected_value=outcome.expected_value,
        expected_value_percent=outcome.expected_value_percent,
        value_classification=outcome.value_classification.value if outcome.value_classification else None,
        value_score=outcome.value_score,
    )


def _map_bookmaker_comparison_to_response(comparison) -> BookmakerComparisonResponse:
    """Map BookmakerComparison domain model to BookmakerComparisonResponse schema.
    
    Odds & Value Intelligence: Includes value classification and scoring fields.
    """
    return BookmakerComparisonResponse(
        label=comparison.label,
        fair_probability=comparison.fair_probability,
        fair_odds=comparison.fair_odds,
        bookmaker_odds=comparison.bookmaker_odds,
        implied_probability=comparison.implied_probability,
        edge_value=comparison.edge_value,
        has_value_flag=comparison.has_value_flag,
        # Odds & Value Intelligence fields (all optional, backward compatible)
        expected_value=comparison.expected_value,
        expected_value_percent=comparison.expected_value_percent,
        value_classification=comparison.value_classification.value if comparison.value_classification else None,
        value_score=comparison.value_score,
    )


def _map_market_analysis_to_response(analysis) -> MarketAnalysisResponse:
    """Map MarketAnalysis domain model to MarketAnalysisResponse schema.
    
    Phase 5: Includes market intelligence data when real odds are available.
    """
    return MarketAnalysisResponse(
        market_type=analysis.market_type.value if hasattr(analysis.market_type, 'value') else str(analysis.market_type),
        line=analysis.line,
        outcomes=[_map_market_outcome_to_response(outcome) for outcome in analysis.outcomes],
        bookmaker_comparison=[
            _map_bookmaker_comparison_to_response(comp) 
            for comp in analysis.bookmaker_comparison
        ] if analysis.bookmaker_comparison else None,
        bookmaker_overround=analysis.bookmaker_overround,
        has_bookmaker_odds=analysis.has_bookmaker_odds,
    )


def _build_odds_aware_market(
    market_type: str,
    line: Optional[float],
    outcome_specs: list,
    odds_quotes: dict,
    mutually_exclusive: bool = True,
) -> MarketAnalysisResponse:
    """Build a MarketAnalysisResponse whose outcomes carry real odds when stored.

    Args:
        market_type: Response market_type (e.g. "match_result", "btts", "OVER_UNDER_2_5")
        line: Goal line for over/under markets, else None
        outcome_specs: List of (label, model_probability, canonical_odds_key)
        odds_quotes: Dict canonical key -> CanonicalOddsQuote (may be empty)
        mutually_exclusive: False for markets whose outcomes overlap (double
            chance), where a bookmaker overround is not defined.

    Odds fields stay None when no quote exists for an outcome.
    """
    from app.services.odds_service import outcome_odds_fields
    from app.prediction import market_analysis as ma

    outcomes = []
    comparisons = []
    priced_odds = []
    for label, probability, odds_key in outcome_specs:
        quote = odds_quotes.get(odds_key) if odds_quotes else None
        fields = outcome_odds_fields(probability, quote)
        outcomes.append(MarketOutcomeResponse(
            label=label,
            model_probability=probability,
            calibrated_probability=probability,  # Same as model in development
            fair_odds=1.0 / probability if probability > 0 else None,
            **fields,
        ))
        if fields["real_odds"] is not None and probability > 0:
            priced_odds.append(fields["real_odds"])
            comparisons.append(BookmakerComparisonResponse(
                label=label,
                fair_probability=probability,
                fair_odds=1.0 / probability,
                bookmaker_odds=fields["real_odds"],
                implied_probability=fields["implied_probability"],
                edge_value=fields["market_edge"],
                # A model-market conflict is never value, whatever the raw edge says.
                has_value_flag=(
                    ma.has_value(probability, fields["real_odds"])
                    and fields["value_classification"]
                    != ma.ValueClassification.MODEL_MARKET_CONFLICT.value
                ),
                expected_value=fields["expected_value"],
                expected_value_percent=fields["expected_value_percent"],
                value_classification=fields["value_classification"],
                value_score=fields["value_score"],
            ))

    # Overround only when every outcome of a mutually exclusive market is priced
    complete = (
        mutually_exclusive
        and len(priced_odds) == len(outcome_specs)
        and len(priced_odds) > 1
    )
    return MarketAnalysisResponse(
        market_type=market_type,
        line=line,
        outcomes=outcomes,
        bookmaker_comparison=comparisons or None,
        bookmaker_overround=ma.overround(priced_odds) if complete else None,
        has_bookmaker_odds=bool(comparisons),
    )


def _annotate_pick_odds_source(mensione_pick, odds_quotes: dict):
    """Return a response copy of mensione_pick with the odds provenance added.

    ``odds_source`` is the CanonicalOddsQuote.source of the picked market
    ("manual_user_supplied" = typed in by the user, unverified;
    "the_odds_api_average" = The Odds API average) and None when the pick
    carries no bookmaker odds. The analysis context itself is not mutated.
    """
    if not isinstance(mensione_pick, dict) or mensione_pick.get("pass_decision"):
        return mensione_pick
    annotated = dict(mensione_pick)
    market = annotated.get("market")
    quote = None
    if odds_quotes and market and annotated.get("bookmaker_odds") is not None:
        quote = odds_quotes.get(market)
    annotated["odds_source"] = quote.source if quote is not None else None
    return annotated


@router.get(
    "",
    response_model=MatchListResponse,
    summary="List matches",
    description="Get a list of matches with optional filters.",
)
async def list_matches(
    competition_id: Optional[str] = Query(None, description="Filter by competition ID"),
    season_id: Optional[str] = Query(None, description="Filter by season ID"),
    team_id: Optional[str] = Query(None, description="Filter by team ID (home or away)"),
    from_date: Optional[date] = Query(None, description="Filter matches from this date"),
    to_date: Optional[date] = Query(None, description="Filter matches to this date"),
    status: Optional[str] = Query(None, description="Filter by match status"),
    scheduled_after: Optional[datetime] = Query(None, description="Filter matches scheduled after this UTC datetime (ISO8601)"),
    limit: Optional[int] = Query(100, description="Maximum number of matches to return", ge=1, le=1000),
    offset: Optional[int] = Query(0, description="Number of matches to skip", ge=0),
    scope: str = Query(
        "all",
        description="'all' (default): every competition; 'featured': only settings.featured_competition_ids "
        "(ignored when competition_id or team_id is given)",
    ),
    provider: FootballDataProvider = Depends(get_data_provider),
) -> MatchListResponse:
    """
    List matches with optional filtering.
    
    Returns all available matches from the data provider.
    The response includes a flag indicating whether this is development/mock data.
    
    Query Parameters:
    - competition_id: Filter by competition
    - season_id: Filter by season
    - team_id: Filter by team (matches where team is home or away)
    - from_date: Only matches scheduled from this date onwards
    - to_date: Only matches scheduled up to this date
    - status: Filter by match status (scheduled, live, finished, etc.)
    
    Returns:
        MatchListResponse containing list of matches and metadata
    """
    # Get matches from provider with filters
    # Use async method if available (ProviderManagerAdapter)
    if hasattr(provider, 'get_matches_async'):
        matches = await provider.get_matches_async(
            competition_id=competition_id,
            season_id=season_id,
            team_id=team_id,
            from_date=from_date,
            to_date=to_date,
            status=status,
        )
        
        # DEBUG: Log match count from provider
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"[DEBUG] Provider returned {len(matches)} matches for status={status}")
        
    else:
        # Fall back to sync method (DevelopmentProvider)
        matches = provider.get_matches(
            competition_id=competition_id,
            season_id=season_id,
            team_id=team_id,
            from_date=from_date,
            to_date=to_date,
            status=status,
        )
    
    # Featured competitions only (before pagination), unless the caller asked for a
    # specific competition/team or for every competition.
    if scope == "featured" and competition_id is None and team_id is None:
        featured = featured_competition_ids()
        matches = [m for m in matches if str(m.competition_id) in featured]

    # Apply scheduled_after filter BEFORE pagination
    # This ensures pagination works correctly for upcoming matches
    if scheduled_after is not None:
        import logging
        logger = logging.getLogger(__name__)
        
        # Ensure scheduled_after is UTC-aware
        if scheduled_after.tzinfo is None:
            scheduled_after = scheduled_after.replace(tzinfo=timezone.utc)
        
        original_count = len(matches)
        matches = [
            m for m in matches 
            if m.scheduled_at and (
                # Make scheduled_at timezone-aware if it isn't
                (m.scheduled_at.replace(tzinfo=timezone.utc) if m.scheduled_at.tzinfo is None else m.scheduled_at)
                >= scheduled_after
            )
        ]
        logger.debug(
            f"[FILTER] scheduled_after={scheduled_after.isoformat()}: "
            f"{original_count} → {len(matches)} matches"
        )
    
    # Convert domain models to API response schemas
    match_responses = []
    
    # CRITICAL FIX: Apply pagination BEFORE batch loading teams
    # This prevents loading teams for 44k+ matches when only 20 are displayed
    total_count = len(matches)
    paginated_matches = matches[offset:offset + limit] if offset is not None and limit is not None else matches
    
    # OPTIMIZATION: Batch load teams only for VISIBLE matches (after pagination)
    team_ids = set()
    for match in paginated_matches:
        if match.home_team_id:
            team_ids.add(match.home_team_id)
        if match.away_team_id:
            team_ids.add(match.away_team_id)
    
    # Batch load teams from database
    teams_cache = {}
    if team_ids:
        try:
            # Import here to avoid circular imports
            from app.database.models import Team
            from app.database.session import get_db
            
            db_session = next(get_db())
            try:
                team_rows = db_session.query(Team).filter(Team.id.in_(team_ids)).all()
                from app.domain.entities import Team as DomainTeam
                
                for team_row in team_rows:
                    teams_cache[team_row.id] = DomainTeam(
                        id=team_row.id,
                        name=team_row.name,
                        short_name=team_row.short_name,
                        code=team_row.code,
                        logo_url=team_row.logo_url
                    )
            finally:
                db_session.close()
        except Exception:
            # If team lookup fails, continue without team info
            pass
    
    for match in paginated_matches:
        try:
            # Get team info from cache
            home_team = teams_cache.get(match.home_team_id) if match.home_team_id else None
            away_team = teams_cache.get(match.away_team_id) if match.away_team_id else None
            
            # FALLBACK: If team not in database, use provider team names
            # ProviderManagerAdapter stores these as private attributes on Match objects
            if home_team is None and hasattr(match, '_provider_home_team_name'):
                from app.domain.entities import Team as DomainTeam
                home_team = DomainTeam(
                    id=match.home_team_id,
                    name=match._provider_home_team_name,
                    short_name=match._provider_home_team_name[:3].upper() if match._provider_home_team_name else None,
                    code=match._provider_home_team_name[:3].upper() if match._provider_home_team_name else None,
                    logo_url=None
                )
            
            if away_team is None and hasattr(match, '_provider_away_team_name'):
                from app.domain.entities import Team as DomainTeam
                away_team = DomainTeam(
                    id=match.away_team_id,
                    name=match._provider_away_team_name,
                    short_name=match._provider_away_team_name[:3].upper() if match._provider_away_team_name else None,
                    code=match._provider_away_team_name[:3].upper() if match._provider_away_team_name else None,
                    logo_url=None
                )
            
            # Get competition name from provider if available
            competition_name = None
            if hasattr(match, '_provider_competition_name'):
                competition_name = match._provider_competition_name

            # Create basic match response
            match_response = MatchResponse(
                id=match.id,
                competition_id=match.competition_id,
                competition_name=competition_name,
                season_id=match.season_id,
                home_team_id=match.home_team_id,
                away_team_id=match.away_team_id,
                venue_id=match.venue_id,
                home_team=_map_team_to_response(home_team),
                away_team=_map_team_to_response(away_team),
                scheduled_at=match.scheduled_at,
                status=match.status,
                home_score=match.home_score,
                away_score=match.away_score,
                home_score_ht=match.home_score_ht,
                away_score_ht=match.away_score_ht,
                home_statistics=None,
                away_statistics=None,
                home_statistics_ht=None,
                away_statistics_ht=None,
                minute=match.minute,
                added_time=match.added_time,
                outcome=match.outcome,
                round=match.round,  # Domain model uses 'round', schema also uses 'round'
                created_at=match.created_at,
                updated_at=match.updated_at,
                provider_fetched_at=match.provider_fetched_at,
            )
            match_responses.append(match_response)
        except Exception as e:
            logger.warning(f"[DEBUG] Failed to process match {match.id[:8]}...: {type(e).__name__}: {e}")
            # Skip this match and continue
            continue
    
    # Build response with development data flag
    return MatchListResponse(
        matches=match_responses,
        count=len(match_responses),  # Count of matches returned in this response
        is_development_data=provider.is_development_data(),
    )


@router.get("/health", tags=["health"])
async def health_check():
    """Simple health check endpoint for diagnostics."""
    return {"status": "ok", "message": "matches endpoint is responding"}


# --- Live status refresh for fotmob_ matches -------------------------------
# The provider chain caches match details (up to 5 min for non-live data), so
# a match fetched just before kickoff kept showing SCHEDULED 0-0 after it had
# started. While a fotmob_ match is inside its playing window and not yet
# FINISHED, status/score/minute are re-read from FotMob without the cache.
_LIVE_REFRESH_WINDOW_SECONDS = 4 * 3600
_LIVE_REFRESH_MIN_INTERVAL_SECONDS = 20.0
_LIVE_REFRESH_TIMEOUT_SECONDS = 3.0
_LIVE_REFRESH_STATUSES = (MatchStatus.SCHEDULED, MatchStatus.LIVE, MatchStatus.HALF_TIME)
# match_id -> (monotonic time of the fetch, fresh ProviderMatch)
_live_refresh_memo: Dict[str, Any] = {}


def _needs_live_refresh(match_id: str, match, now: datetime) -> bool:
    """True for a fotmob_ match whose kickoff passed less than 4 h ago and
    whose status is not final yet."""
    if not match_id.startswith("fotmob_") or match is None:
        return False
    if match.status not in _LIVE_REFRESH_STATUSES:
        return False
    kickoff = match.scheduled_at
    if kickoff is None:
        return False
    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)
    elapsed = (now - kickoff).total_seconds()
    return 0 <= elapsed < _LIVE_REFRESH_WINDOW_SECONDS


async def _fetch_fresh_fotmob_match(source_id: str):
    """One uncached FotMob matchDetails request (raises on provider errors)."""
    from app.config import settings
    from app.providers.fotmob import FotMobFootballProvider

    fotmob = FotMobFootballProvider(
        base_url=settings.fotmob_base_url,
        timeout_seconds=_LIVE_REFRESH_TIMEOUT_SECONDS,
        retry_count=0,
        cache=None,
    )
    try:
        return await fotmob.get_match(source_id)
    finally:
        await fotmob.close()


def _store_fresh_in_shared_cache(source_id: str, fresh) -> None:
    """Let other readers of the shared provider cache see the fresh state."""
    try:
        from app.main import app_state
        from app.providers.cache import LIVE_DATA_TTL

        if app_state.provider_cache is not None:
            app_state.provider_cache.set(
                f"fotmob:match:{source_id}", fresh, ttl_seconds=LIVE_DATA_TTL
            )
    except Exception:  # pragma: no cover - cache is an optimisation only
        pass


async def _refresh_stale_live_status(
    match_id: str,
    match,
    fetch=None,
    now: Optional[datetime] = None,
):
    """Refresh status, score, minute and added time of a started fotmob_ match.

    At most one FotMob request per match every 20 s (memoised); on any error
    the cached data is kept and the failure is logged. Never invents values:
    every refreshed field comes from the fresh FotMob response.
    """
    import logging
    import time

    logger = logging.getLogger(__name__)
    fetch = fetch or _fetch_fresh_fotmob_match
    now = now or datetime.now(timezone.utc)
    if not _needs_live_refresh(match_id, match, now):
        return match

    source_id = match_id.split("_", 1)[1]
    memo = _live_refresh_memo.get(match_id)
    if memo is not None and time.monotonic() - memo[0] < _LIVE_REFRESH_MIN_INTERVAL_SECONDS:
        fresh = memo[1]
    else:
        try:
            fresh = await fetch(source_id)
        except Exception as exc:
            logger.warning(
                f"get_match: live refresh failed for {match_id}, keeping cached data: {exc}"
            )
            return match
        if len(_live_refresh_memo) > 256:
            cutoff = time.monotonic() - 600
            for key in [k for k, v in _live_refresh_memo.items() if v[0] < cutoff]:
                _live_refresh_memo.pop(key, None)
        _live_refresh_memo[match_id] = (time.monotonic(), fresh)
        if fresh is not None:
            _store_fresh_in_shared_cache(source_id, fresh)

    if fresh is None or str(getattr(fresh, "source_id", "")) != source_id:
        return match

    match.status = fresh.status
    match.home_score = fresh.home_score
    match.away_score = fresh.away_score
    match.minute = fresh.minute
    match.added_time = fresh.added_time
    match.outcome = fresh.outcome
    match.provider_fetched_at = fresh.fetched_at
    return match


@router.get(
    "/{match_id}",
    response_model=MatchDetailResponse,
    responses={
        404: {
            "model": ErrorResponse,
            "description": "Match not found",
        }
    },
    summary="Get match details",
    description="Get detailed information about a specific match by ID.",
)
async def get_match(
    match_id: str,
    provider: FootballDataProvider = Depends(get_data_provider),
) -> MatchDetailResponse:
    """
    Get details for a specific match.
    
    Returns detailed information about a single match identified by match_id.
    
    Path Parameters:
    - match_id: Unique match identifier
    
    Returns:
        MatchDetailResponse containing match details
        
    Raises:
        HTTPException: 404 if match is not found
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"get_match called with match_id: {match_id}")

    # Get match from provider
    match = provider.get_match(match_id)

    # Return 404 if match doesn't exist
    if match is None:
        logger.info(f"Match not found: {match_id}")
        raise HTTPException(
            status_code=404,
            detail=f"Match with ID '{match_id}' not found"
        )

    # Started-but-not-finished fotmob_ matches: re-read the live state
    # without the provider cache (fails soft to the cached data).
    match = await _refresh_stale_live_status(match_id, match)

    # Get team information.
    # get_team() returns None when no source can resolve the ID (e.g. the
    # teams table does not exist in the Vercel ephemeral SQLite environment).
    # Fall back to the _provider_*_team_name attributes attached by
    # ProviderManagerAdapter._map_provider_match_to_domain(), mirroring the
    # list_matches endpoint.
    from app.domain.entities import Team as DomainTeam

    home_team = provider.get_team(match.home_team_id)
    if home_team is None and hasattr(match, "_provider_home_team_name") and match._provider_home_team_name:
        ht_name = match._provider_home_team_name
        home_team = DomainTeam(
            id=match.home_team_id,
            name=ht_name,
            short_name=ht_name[:3].upper(),
            code=ht_name[:3].upper(),
            logo_url=None,
        )

    away_team = provider.get_team(match.away_team_id)
    if away_team is None and hasattr(match, "_provider_away_team_name") and match._provider_away_team_name:
        at_name = match._provider_away_team_name
        away_team = DomainTeam(
            id=match.away_team_id,
            name=at_name,
            short_name=at_name[:3].upper(),
            code=at_name[:3].upper(),
            logo_url=None,
        )

    # Competition name from provider attribute
    competition_name = getattr(match, "_provider_competition_name", None)

    # Initialize statistics as None
    home_statistics = None
    away_statistics = None
    home_statistics_ht = None
    away_statistics_ht = None

    # Get statistics for finished, live, and halftime matches
    # Statistics should be available for any match that has started
    if match.status in (MatchStatus.FINISHED, MatchStatus.LIVE, MatchStatus.HALF_TIME):
        try:
            team_stats = provider.get_team_match_statistics(match.id)
            for stat in team_stats:
                if stat.team_id == match.home_team_id:
                    home_statistics = _map_statistic_to_response(stat)
                elif stat.team_id == match.away_team_id:
                    away_statistics = _map_statistic_to_response(stat)
        except Exception as exc:
            logger.warning(f"get_match: get_team_match_statistics failed for {match_id}: {exc}")

    # Get first-half statistics for halftime and finished matches
    if match.status in (MatchStatus.HALF_TIME, MatchStatus.FINISHED):
        try:
            ht_stats = provider.get_team_match_statistics_firsthalf(match.id)
            for stat in ht_stats:
                if stat.team_id == match.home_team_id:
                    home_statistics_ht = _map_statistic_to_response(stat)
                elif stat.team_id == match.away_team_id:
                    away_statistics_ht = _map_statistic_to_response(stat)
        except (NotImplementedError, Exception):
            pass

    # Convert domain model to API response schema with enriched data
    match_response = MatchResponse(
        id=match.id,
        competition_id=match.competition_id,
        competition_name=competition_name,
        season_id=match.season_id,
        home_team_id=match.home_team_id,
        away_team_id=match.away_team_id,
        venue_id=match.venue_id,
        home_team=_map_team_to_response(home_team),
        away_team=_map_team_to_response(away_team),
        scheduled_at=match.scheduled_at,
        status=match.status,
        home_score=match.home_score,
        away_score=match.away_score,
        home_score_ht=match.home_score_ht,
        away_score_ht=match.away_score_ht,
        home_statistics=home_statistics,
        away_statistics=away_statistics,
        home_statistics_ht=home_statistics_ht,
        away_statistics_ht=away_statistics_ht,
        minute=match.minute,
        added_time=match.added_time,
        outcome=match.outcome,
        round=match.round,
        created_at=match.created_at,
        updated_at=match.updated_at,
        provider_fetched_at=match.provider_fetched_at,
    )

    # Build response with development data flag
    return MatchDetailResponse(
        match=match_response,
        is_development_data=provider.is_development_data(),
    )



@router.get(
    "/{match_id}/prediction",
    response_model=MatchPredictionResponse,
    responses={
        404: {
            "model": ErrorResponse,
            "description": "Match not found",
        }
    },
    summary="Get match prediction",
    description="Get prediction, TUTAR X PICK, versioned prediction, market analysis, and easy match detection for a specific match.",
)
async def get_match_prediction(
    match_id: str,
    provider: FootballDataProvider = Depends(get_data_provider),
    db: Optional[Session] = Depends(get_db),
) -> MatchPredictionResponse:
    """Get prediction for a specific match.
    
    Returns:
    - Match outcome probabilities (1X2)
    - Expected goals (xG)
    - BTTS probability
    - Predicted score (most likely scoreline)
    - TUTAR X PICK (recommended market with confidence and reasoning)
    - Prediction version ID (immutable versioning)
    - Easy Match detection result
    
    TUTAR X PICK Structure:
    The mensione_pick field contains either a BestTip or a PassDecision.
    
    BestTip (when a qualifying market is found):
    - market: Market identifier (e.g., "HOME_WIN", "OVER_2_5", "BTTS_YES")
    - selection: Human-readable selection text
    - probability: Calibrated model probability [0, 1]
    - confidence: Overall confidence score [0, 1]
    - model_agreement: Agreement between models [0, 1]
    - data_quality: Data quality score [0, 1]
    - edge: Edge over bookmaker odds (None when odds unavailable)
    - fair_odds: Fair odds from model probability
    - bookmaker_odds: Bookmaker odds (None when unavailable)
    - odds_movement: "rising", "falling", "stable", or None
    - value_classification: "STRONG_VALUE", "VALUE", "NEUTRAL", "NEGATIVE_VALUE"
    - risk_level: "LOW", "MEDIUM", "HIGH"
    - selection_score: Overall selection score [0, 1]
    - selector_reason: Why this market was selected
    - timestamp: ISO 8601 timestamp
    - pipeline_version: Pipeline version string
    - pass_decision: False
    
    PassDecision (when no market qualifies):
    - pass_decision: True
    - match_id: Match identifier
    - pass_reason: "insufficient_data", "weak_agreement", "poor_calibration",
                   "negative_value", "no_qualifying_market", "high_uncertainty"
    - evaluated_markets_count: Number of markets evaluated
    - best_market_details: Details of closest market that didn't qualify
    - timestamp: ISO 8601 timestamp
    - pipeline_version: Pipeline version string
    
    Path Parameters:
    - match_id: Unique match identifier
    
    Returns:
        MatchPredictionResponse containing prediction and analysis
        
    Raises:
        HTTPException: 404 if match is not found
    """
    import time
    import uuid
    import logging
    
    # Generate correlation ID for this request
    correlation_id = str(uuid.uuid4())[:8]
    logger = logging.getLogger(__name__)
    
    stage_timings = {}
    request_start = time.time()
    
    logger.info(f"[{correlation_id}] START prediction request for match {match_id}")
    logger.info(f"[{correlation_id}] Provider type: {type(provider).__name__}")
    
    # Stage 1: Get match from provider or database
    stage_start = time.time()
    logger.info(f"[{correlation_id}] Stage 1: Getting match")
    match = provider.get_match(match_id)
    logger.info(f"[{correlation_id}] Provider returned: {type(match).__name__ if match else 'None'}")
    
    # If provider returns None, try database lookup
    if match is None and db is not None:
        logger.info(f"[{correlation_id}] Provider returned None, trying database lookup")
        
        try:
            from app.database.models import Match as DBMatch
            from app.domain.match import Match as DomainMatch
            
            db_match = None
            
            # Try 1: Direct UUID lookup
            try:
                uuid.UUID(match_id)
                db_match = db.query(DBMatch).filter(DBMatch.id == match_id).first()
                if db_match:
                    logger.info(f"[{correlation_id}] Found match by canonical UUID")
            except ValueError:
                # Not a UUID, try provider_id lookup
                logger.info(f"[{correlation_id}] Not a UUID: {match_id}")
            
            # Try 2: Provider ID lookup (e.g., fotmob_5795469)
            if db_match is None:
                db_match = db.query(DBMatch).filter(DBMatch.provider_id == match_id).first()
                if db_match:
                    logger.info(f"[{correlation_id}] Found match by provider_id")
                else:
                    logger.warning(f"[{correlation_id}] No match found in database for ID: {match_id}")
            
            # Convert DB model to domain model
            if db_match:
                match = DomainMatch(
                    id=db_match.id,
                    home_team_id=db_match.home_team_id,
                    away_team_id=db_match.away_team_id,
                    competition_id=db_match.competition_id or "unknown",
                    season_id=db_match.season or "unknown",
                    scheduled_at=db_match.scheduled_at,
                    status=db_match.status,
                    home_score=db_match.home_score,
                    away_score=db_match.away_score,
                    home_score_ht=db_match.home_score_ht,
                    away_score_ht=db_match.away_score_ht,
                    outcome=db_match.outcome,
                    round=db_match.round,
                    created_at=db_match.created_at,
                    updated_at=db_match.updated_at,
                )
                logger.info(f"[{correlation_id}] Successfully loaded match from database")
                logger.info(f"[{correlation_id}] Match details - Home: {match.home_team_id[:8]}..., Away: {match.away_team_id[:8]}..., Status: {match.status}")
                
        except Exception as e:
            logger.warning(f"[{correlation_id}] Database lookup failed: {e}")
    
    stage_timings["1_match_lookup"] = (time.time() - stage_start) * 1000
    logger.info(f"[{correlation_id}] Stage 1 complete: {stage_timings['1_match_lookup']:.1f}ms")
    
    # Return 404 if match doesn't exist
    if match is None:
        logger.info(f"[{correlation_id}] Match not found, returning 404")
        raise HTTPException(
            status_code=404,
            detail=f"Match with ID '{match_id}' not found"
        )
    
    # Stage 2: Initialize prediction service
    stage_start = time.time()
    logger.info(f"[{correlation_id}] Stage 2: Initializing prediction service")
    
    prediction_service = PredictionService(
        provider=provider,
        db_session=db
    )
    stage_timings["2_service_init"] = (time.time() - stage_start) * 1000
    logger.info(f"[{correlation_id}] Stage 2 complete: {stage_timings['2_service_init']:.1f}ms")
    
    # Stage 3: Generate full TUTAR X prediction
    stage_start = time.time()
    logger.info(f"[{correlation_id}] Stage 3: Starting generate_full_prediction")
    
    # Fetch bookmaker odds (AverageMarketOdds rows) and convert them to the
    # FLAT canonical dict the pipeline expects, e.g.
    # {"HOME_WIN": 1.22, "DRAW": 5.8, "AWAY_WIN": 12.5, "OVER_2_5": 1.5, ...}.
    # Missing odds stay missing (odds_data=None) - never fabricated.
    from app.services.odds_service import load_canonical_odds_quotes
    odds_quotes = {}
    try:
        odds_quotes = load_canonical_odds_quotes(
            db,
            [match_id, match.id],
            home_team_id=match.home_team_id,
            away_team_id=match.away_team_id,
        )
    except Exception as e:
        logger.warning(f"[{correlation_id}] Odds lookup failed, continuing without odds: {e}")
        odds_quotes = {}
        if db is not None:
            try:
                db.rollback()  # PostgreSQL: clear the aborted transaction state
            except Exception:
                pass

    odds_data = {key: quote.odds for key, quote in odds_quotes.items()} or None
    if odds_data:
        sources = sorted({quote.source for quote in odds_quotes.values()})
        logger.info(
            f"[{correlation_id}] Loaded canonical odds for {sorted(odds_data)} (sources: {sources})"
        )
    else:
        logger.info(f"[{correlation_id}] No odds data available for match {match_id}")
    
    # B-10 Fix: Run sync prediction in executor to avoid blocking async event loop
    import asyncio
    loop = asyncio.get_running_loop()
    analysis_context = await loop.run_in_executor(
        None,
        lambda: prediction_service.generate_full_prediction(
            match=match,
            odds_data=odds_data,
            correlation_id=correlation_id
        )
    )
    stage_timings["3_full_prediction"] = (time.time() - stage_start) * 1000
    logger.info(f"[{correlation_id}] Stage 3 complete: {stage_timings['3_full_prediction']:.1f}ms")
    
    # Stage 4: Extract prediction from context
    stage_start = time.time()
    logger.info(f"[{correlation_id}] Stage 4: Extracting prediction from context")
    prediction = None
    if analysis_context.model_predictions and len(analysis_context.model_predictions) > 0:
        prediction = analysis_context.model_predictions[0]
    
    if prediction is None:
        total_time = (time.time() - request_start) * 1000
        logger.info(f"[{correlation_id}] INSUFFICIENT DATA - Total time: {total_time:.1f}ms")
        logger.info(f"[{correlation_id}] Stage timings: {stage_timings}")
        raise HTTPException(
            status_code=400,
            detail="Insufficient data to generate prediction for this match"
        )
    stage_timings["4_extract_prediction"] = (time.time() - stage_start) * 1000
    logger.info(f"[{correlation_id}] Stage 4 complete: {stage_timings['4_extract_prediction']:.1f}ms")
    
    # Stage 5: Detect easy match
    stage_start = time.time()
    logger.info(f"[{correlation_id}] Stage 5: Detecting easy match")
    easy_match_result = prediction_service.detect_easy_match(
        match=match,
        prediction=prediction,
    )
    stage_timings["5_easy_match_detection"] = (time.time() - stage_start) * 1000
    logger.info(f"[{correlation_id}] Stage 5 complete: {stage_timings['5_easy_match_detection']:.1f}ms")
    
    # Stage 6: Convert easy match result to response schema
    stage_start = time.time()
    logger.info(f"[{correlation_id}] Stage 6: Converting easy match result")
    easy_match_response = None
    if easy_match_result:
        easy_match_response = EasyMatchResponse(
            match_id=easy_match_result.match_id,
            is_easy_match=easy_match_result.is_easy_match,
            confidence_score=easy_match_result.confidence_score,
            threshold=easy_match_result.threshold,
            signals=[
                EasyMatchSignalResponse(
                    name=s.name,
                    value=s.value,
                    weight=s.weight,
                    available=s.available,
                    description=s.description,
                )
                for s in easy_match_result.signals
            ],
            dominant_outcome=easy_match_result.dominant_outcome,
            dominant_probability=easy_match_result.dominant_probability,
            reasons=easy_match_result.reasons,
            warnings=easy_match_result.warnings,
            data_sufficient=easy_match_result.data_sufficient,
        )
    stage_timings["6_response_conversion"] = (time.time() - stage_start) * 1000
    logger.info(f"[{correlation_id}] Stage 6 complete: {stage_timings['6_response_conversion']:.1f}ms")
    
    # Stage 7: Build market analysis from prediction markets
    stage_start = time.time()
    logger.info(f"[{correlation_id}] Stage 7: Building market analysis from prediction markets")
    
    market_analysis_response = None
    
    # Use prediction_markets from analysis_context (generated by our fixed pipeline)
    if analysis_context.prediction_markets and len(analysis_context.prediction_markets) > 0:
        logger.info(f"[{correlation_id}] Found {len(analysis_context.prediction_markets)} prediction markets")
        
        markets = []
        
        # Convert prediction_markets to market_analysis format.
        # Real odds (when stored) are attached per outcome via odds_quotes;
        # outcomes without stored odds keep real_odds/edge/EV = None.
        from app.services.odds_service import line_suffix
        for prediction_market in analysis_context.prediction_markets:
            if prediction_market.market_type == 'match_result':
                probs = prediction_market.probabilities
                home_prob = probs.get('home')
                draw_prob = probs.get('draw')
                away_prob = probs.get('away')
                if None not in (home_prob, draw_prob, away_prob):
                    markets.append(_build_odds_aware_market(
                        market_type="match_result",
                        line=None,
                        outcome_specs=[
                            ("Home", home_prob, "HOME_WIN"),
                            ("Draw", draw_prob, "DRAW"),
                            ("Away", away_prob, "AWAY_WIN"),
                        ],
                        odds_quotes=odds_quotes,
                    ))
                    # Double chance: model probabilities are sums of the 1X2
                    # outcomes; odds only from explicitly supplied DC prices.
                    markets.append(_build_odds_aware_market(
                        market_type="double_chance",
                        line=None,
                        outcome_specs=[
                            ("1X", min(1.0, home_prob + draw_prob), "HOME_OR_DRAW"),
                            ("12", min(1.0, home_prob + away_prob), "HOME_OR_AWAY"),
                            ("X2", min(1.0, draw_prob + away_prob), "DRAW_OR_AWAY"),
                        ],
                        odds_quotes=odds_quotes,
                        mutually_exclusive=False,
                    ))

            elif prediction_market.market_type == 'btts':
                probs = prediction_market.probabilities
                yes_prob = probs.get('yes')
                no_prob = probs.get('no')
                if yes_prob is not None and no_prob is not None:
                    markets.append(_build_odds_aware_market(
                        market_type="btts",
                        line=None,
                        outcome_specs=[
                            ("Yes", yes_prob, "BTTS_YES"),
                            ("No", no_prob, "BTTS_NO"),
                        ],
                        odds_quotes=odds_quotes,
                    ))

            elif prediction_market.market_type == 'over_under' and prediction_market.line is not None:
                line = prediction_market.line
                probs = prediction_market.probabilities
                over_prob = probs.get('over', 0.0)
                under_prob = probs.get('under', 0.0)

                logger.info(f"[{correlation_id}] Creating Over/Under {line} market: Over={over_prob:.3f}, Under={under_prob:.3f}")

                suffix = line_suffix(line)
                markets.append(_build_odds_aware_market(
                    market_type=f"OVER_UNDER_{line}".replace(".", "_"),  # e.g., OVER_UNDER_2_5
                    line=line,
                    outcome_specs=[
                        (f"Over {line} Goals", over_prob, f"OVER_{suffix}"),
                        (f"Under {line} Goals", under_prob, f"UNDER_{suffix}"),
                    ],
                    odds_quotes=odds_quotes,
                ))

            elif prediction_market.market_type == 'over_2_5_and_btts':
                # Handle combined Over 2.5 + BTTS market
                probs = prediction_market.probabilities
                yes_prob = probs.get('yes', 0.0)
                no_prob = probs.get('no', 0.0)
                
                logger.info(f"[{correlation_id}] Creating Over 2.5 + BTTS market: Yes={yes_prob:.3f}, No={no_prob:.3f}")
                
                # Create market outcomes
                yes_outcome = MarketOutcomeResponse(
                    label="Over 2.5 & Both Teams Score",
                    model_probability=yes_prob,
                    calibrated_probability=yes_prob,
                    fair_odds=1.0 / yes_prob if yes_prob > 0 else None,
                    real_odds=None,
                    implied_probability=None,
                    market_edge=None,
                    bookmaker=None,
                    odds_timestamp=None,
                    expected_value=None,
                    expected_value_percent=None,
                    value_classification=None,
                )
                
                no_outcome = MarketOutcomeResponse(
                    label="Not (Over 2.5 & Both Teams Score)",
                    model_probability=no_prob,
                    calibrated_probability=no_prob,
                    fair_odds=1.0 / no_prob if no_prob > 0 else None,
                    real_odds=None,
                    implied_probability=None,
                    market_edge=None,
                    bookmaker=None,
                    odds_timestamp=None,
                    expected_value=None,
                    expected_value_percent=None,
                    value_classification=None,
                )
                
                # Create combined market analysis
                market_analysis = MarketAnalysisResponse(
                    market_type="OVER_2_5_AND_BTTS",
                    line=2.5,  # Reference line
                    outcomes=[yes_outcome, no_outcome],
                    bookmaker_comparison=None,
                    bookmaker_overround=None,
                    has_bookmaker_odds=False
                )
                markets.append(market_analysis)
            
            if markets:
                market_analysis_response = markets  # Already a list of MarketAnalysisResponse
                logger.info(f"[{correlation_id}] Built market analysis with {len(markets)} Over/Under markets")
            else:
                logger.info(f"[{correlation_id}] No Over/Under markets created")
    else:
        logger.info(f"[{correlation_id}] No prediction_markets available for market analysis")
    
    stage_timings["7_market_analysis"] = (time.time() - stage_start) * 1000
    logger.info(f"[{correlation_id}] Stage 7 complete: {stage_timings['7_market_analysis']:.1f}ms")
    
    # Calculate total time
    total_time = (time.time() - request_start) * 1000
    stage_timings["0_TOTAL"] = total_time
    
    # Log timing information
    logger.info(f"[{correlation_id}] TIMING INSTRUMENTATION for {match_id}:")
    logger.info(f"[{correlation_id}]   Home Team ID: {match.home_team_id}")
    logger.info(f"[{correlation_id}]   Away Team ID: {match.away_team_id}")
    for stage, timing_ms in sorted(stage_timings.items()):
        logger.info(f"[{correlation_id}]   {stage}: {timing_ms:.2f}ms")
    
    # Build response
    # Extract form data from analysis_context if available
    from app.api.v1.schemas import TeamFormResponse, HeadToHeadResponse
    
    home_form_response = None
    away_form_response = None
    h2h_response = None
    
    if hasattr(analysis_context, 'home_form') and analysis_context.home_form:
        hf = analysis_context.home_form
        home_form_response = TeamFormResponse(
            wins=hf.wins,
            draws=hf.draws,
            losses=hf.losses,
            points=hf.points,
            matches_analyzed=hf.matches_analyzed,
            goals_for=hf.goals_for,
            goals_against=hf.goals_against,
            form_string=None  # Not available in FormMetrics yet
        )
    
    if hasattr(analysis_context, 'away_form') and analysis_context.away_form:
        af = analysis_context.away_form
        away_form_response = TeamFormResponse(
            wins=af.wins,
            draws=af.draws,
            losses=af.losses,
            points=af.points,
            matches_analyzed=af.matches_analyzed,
            goals_for=af.goals_for,
            goals_against=af.goals_against,
            form_string=None  # Not available in FormMetrics yet
        )
    
    # Extract H2H data if available
    if (hasattr(analysis_context, 'h2h_home_wins') and 
        analysis_context.h2h_home_wins is not None):
        # Calculate total goals from H2H matches if available
        home_goals_total = None
        away_goals_total = None
        
        if (hasattr(analysis_context, 'head_to_head_matches') and 
            analysis_context.head_to_head_matches):
            home_goals_total = 0
            away_goals_total = 0
            
            for h2h_match in analysis_context.head_to_head_matches:
                if h2h_match.home_score is not None and h2h_match.away_score is not None:
                    # Determine which team scored how much from current match perspective
                    if h2h_match.home_team_id == match.home_team_id:
                        home_goals_total += h2h_match.home_score
                        away_goals_total += h2h_match.away_score
                    else:
                        home_goals_total += h2h_match.away_score
                        away_goals_total += h2h_match.home_score
        
        total_matches = (analysis_context.h2h_home_wins + 
                        analysis_context.h2h_draws + 
                        analysis_context.h2h_away_wins)
        
        h2h_response = HeadToHeadResponse(
            total_matches=total_matches,
            home_wins=analysis_context.h2h_home_wins,
            draws=analysis_context.h2h_draws,
            away_wins=analysis_context.h2h_away_wins,
            home_goals=home_goals_total,
            away_goals=away_goals_total
        )
    
    return MatchPredictionResponse(
        match_id=match.id,
        home_win_probability=prediction.home_win_probability,
        draw_probability=prediction.draw_probability,
        away_win_probability=prediction.away_win_probability,
        home_xg=prediction.home_xg,
        away_xg=prediction.away_xg,
        btts_probability=prediction.btts_probability,
        predicted_score=analysis_context.predicted_score,
        mensione_pick=_annotate_pick_odds_source(analysis_context.mensione_pick, odds_quotes),
        prediction_version_id=analysis_context.prediction_version_id,
        market_analysis=market_analysis_response,  # Now includes Over/Under markets from prediction
        easy_match=easy_match_response,
        home_form=home_form_response,
        away_form=away_form_response,
        head_to_head=h2h_response,
        shot_markets=analysis_context.shot_markets if hasattr(analysis_context, 'shot_markets') else None,
        squad_info=_squad_info_response(getattr(prediction_service.feature_extractor, "squad_info", None)),
        is_development_data=provider.is_development_data(),
    )


def _squad_info_response(squad_info) -> Optional[Dict[str, Any]]:
    """Serialise (home, away) TeamSquadInfo for the API; None when unavailable."""
    if not squad_info:
        return None
    from dataclasses import asdict

    home, away = squad_info
    return {"source": "fotmob", "home": asdict(home), "away": asdict(away)}
