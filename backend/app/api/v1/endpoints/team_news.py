"""Team-news endpoint (live layer): line-ups, absentees, last-5 form per side.

GET /api/v1/matches/{match_id}/team-news
  match_id: local matches.id (UUID), "fotmob_<FotMob match id>" or the bare
  FotMob match id. Reads the database only (no provider call); the data is
  written by the team-news refresh (docs/live-layer.md).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.team_news.builder import TeamNewsNotFound, build_team_news
from app.services.team_news.constants import MISSING_REASON_LABELS_TR
from app.services.team_news.schemas import TeamNewsResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["team-news"])

NOT_MIGRATED_DETAIL = {
    "error": "team_news_not_migrated",
    "message": "Team-news tables are not available yet (apply Alembic revision 20261013_team_news).",
}
DB_UNAVAILABLE_DETAIL = {"error": "database_unavailable", "message": "Database temporarily unavailable."}


def db_error_detail(exc: Exception) -> dict:
    """503 detail: 'not migrated' only when the error says a table/column is missing."""
    text = str(getattr(exc, "orig", exc)).lower()
    if "no such table" in text or "no such column" in text or "does not exist" in text:
        return NOT_MIGRATED_DETAIL
    return DB_UNAVAILABLE_DETAIL


def not_found_detail(reason: str) -> dict:
    return {"missing_reason": reason, "message": MISSING_REASON_LABELS_TR.get(reason, reason)}


@router.get(
    "/matches/{match_id}/team-news",
    response_model=TeamNewsResponse,
    summary="Team news of a match",
    description=(
        "Expected/confirmed XI with last-5 form, absentees (injuries, suspensions, ...) with their "
        "contribution shares, team last 5 and data freshness, per side. Missing data is null plus a "
        "missing_reason code."
    ),
    responses={404: {"description": "Match unknown to the local DB and to the team-news layer"}},
)
def get_match_team_news(match_id: str, db: Session = Depends(get_db)) -> TeamNewsResponse:
    try:
        return build_team_news(db, match_id)
    except TeamNewsNotFound as exc:
        raise HTTPException(status_code=404, detail=not_found_detail(exc.reason))
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("team-news: database error for match %s", match_id)
        raise HTTPException(status_code=503, detail=db_error_detail(exc))
