"""Team squad endpoint (live layer).

GET /api/v1/teams/{team_id}/squad
  team_id: local teams.id (UUID), "fotmob_<FotMob team id>" or the bare FotMob
  team id. Returns the latest observed squad with each player's active
  availability reports. Reads the database only.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.api.v1.endpoints.team_news import db_error_detail, not_found_detail
from app.database.session import get_db
from app.services.team_news.builder import TeamNewsNotFound, build_team_squad
from app.services.team_news.schemas import TeamSquadResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get(
    "/{team_id}/squad",
    response_model=TeamSquadResponse,
    summary="Team squad with availability",
    description=(
        "Latest observed squad (FotMob team squad) with profile fields and active availability reports. "
        "availability_status is 'unavailable' when a report is active, otherwise 'no_report' "
        "(not a fitness guarantee)."
    ),
    responses={404: {"description": "Team unknown"}},
)
def get_team_squad(
    team_id: str,
    include_former: bool = Query(False, description="Also list players no longer in the latest squad observation"),
    db: Session = Depends(get_db),
) -> TeamSquadResponse:
    try:
        return build_team_squad(db, team_id, include_former=include_former)
    except TeamNewsNotFound as exc:
        raise HTTPException(status_code=404, detail=not_found_detail(exc.reason))
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("team-news: database error for team %s", team_id)
        raise HTTPException(status_code=503, detail=db_error_detail(exc))
