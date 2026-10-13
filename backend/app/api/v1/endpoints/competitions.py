"""Competition endpoints for API v1.

This module implements competition-related REST API endpoints.
"""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_data_provider
from app.api.v1.schemas import (
    CompetitionListResponse,
    CompetitionResponse,
)
from app.providers import FootballDataProvider


router = APIRouter(prefix="/competitions", tags=["competitions"])

# Popular competition name keywords used to filter the competition list.
# Matched case-insensitively against competition.name.
_POPULAR_KEYWORDS = [
    "premier league",
    "bundesliga",
    "laliga",
    "la liga",
    "serie a",
    "ligue 1",
    "champions league",
    "europa league",
    "super lig",
    "eredivisie",
    "primeira liga",
    "scottish premiership",
]


def _is_popular(name: str) -> bool:
    """Return True if the competition name matches a popular league keyword."""
    name_lower = name.lower().strip()
    return any(kw in name_lower for kw in _POPULAR_KEYWORDS)


@router.get(
    "",
    response_model=CompetitionListResponse,
    summary="List competitions",
    description="Get a list of available competitions/leagues.",
)
async def list_competitions(
    provider: FootballDataProvider = Depends(get_data_provider),
) -> CompetitionListResponse:
    """
    List available competitions.

    Returns a curated list of major competitions available from the data provider.
    Competitions are filtered to popular major leagues by name keyword matching.

    Primary source: provider.get_competitions() (external providers + DB).
    Fallback: HybridProvider.get_competitions_from_matches_async() which derives
    the competition list from the live FotMob match schedule when neither the
    external provider nor the database competitions table are available.

    Returns:
        CompetitionListResponse containing list of competitions
    """
    import logging
    logger = logging.getLogger(__name__)

    if provider.is_development_data():
        # Development data: use DevelopmentProvider competition IDs
        major_competitions = [
            CompetitionResponse(
                id="dev_comp_league_a",
                name="[DEV] League A",
                country="DEV",
            ),
            CompetitionResponse(
                id="dev_comp_league_b",
                name="[DEV] League B",
                country="DEV",
            ),
        ]
    else:
        # Real data: query provider (HybridProvider) for competitions.
        #
        # Primary path: provider.get_competitions() tries:
        #   1. External providers (ProviderManagerAdapter – currently raises NotImplementedError)
        #   2. Database (may not have a competitions table in Vercel ephemeral SQLite)
        #
        # Fallback path: derive competitions from the live match schedule.
        # This uses the same FotMob match feed that powers /api/v1/matches so
        # competition IDs in both endpoints are consistent.
        #
        # No hardcoded UUIDs or mock data are ever returned.
        major_competitions = []
        all_competitions = []

        try:
            all_competitions = provider.get_competitions()
            logger.info(
                f"list_competitions: provider.get_competitions() returned "
                f"{len(all_competitions)} competitions"
            )
        except Exception as exc:
            logger.warning(
                f"list_competitions: provider.get_competitions() raised "
                f"{type(exc).__name__}: {exc}"
            )

        # If provider returned nothing, derive from the live match schedule
        if not all_competitions:
            logger.info(
                "list_competitions: get_competitions() returned empty – "
                "falling back to get_competitions_from_matches_async"
            )
            if hasattr(provider, "get_competitions_from_matches_async"):
                try:
                    all_competitions = await provider.get_competitions_from_matches_async()
                    logger.info(
                        f"list_competitions: get_competitions_from_matches_async returned "
                        f"{len(all_competitions)} competitions"
                    )
                except Exception as exc:
                    logger.error(
                        f"list_competitions: get_competitions_from_matches_async failed: {exc}"
                    )
            else:
                logger.warning(
                    "list_competitions: provider does not support "
                    "get_competitions_from_matches_async"
                )

        # Deduplicate by name and filter to popular leagues.
        # For names that appear multiple times (e.g. "Premier League" for
        # different countries) only the first entry is kept.
        seen_names: set = set()
        for comp in all_competitions:
            if not comp.name:
                continue
            if not _is_popular(comp.name):
                continue
            canonical = comp.name.strip()
            if canonical in seen_names:
                continue
            seen_names.add(canonical)
            major_competitions.append(
                CompetitionResponse(
                    id=comp.id,
                    name=comp.name,
                    country=comp.country,
                )
            )

        logger.info(
            f"list_competitions: returning {len(major_competitions)} popular competitions"
        )

    return CompetitionListResponse(
        competitions=major_competitions,
        count=len(major_competitions),
        is_development_data=provider.is_development_data(),
    )
