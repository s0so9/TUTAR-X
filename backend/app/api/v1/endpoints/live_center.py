"""Live match centre endpoint.

GET /api/v1/matches/{match_id}/live-center
  match_id: "fotmob_<FotMob match id>", the bare FotMob id, or a local matches.id.
  Score, minute, events, line-ups with bench, all team stats (full match and
  halves), shotmap and momentum, straight from FotMob matchDetails. Nothing is
  filled in: sections the source does not send are listed in ``missing``.
  Errors are 404/503 with a reason code and a Turkish message, never fake data.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.live_center.constants import ERROR_MESSAGES_TR
from app.services.live_center.schemas import LiveCenterResponse
from app.services.live_center.service import LiveCenterError, get_live_center_service

router = APIRouter(tags=["live-center"])


@router.get(
    "/matches/{match_id}/live-center",
    response_model=LiveCenterResponse,
    summary="Live match centre",
    description=(
        "Live score and minute, event timeline (goals, cards, substitutions, VAR), line-ups with "
        "formation grid and bench, team stats for the full match and both halves, shotmap and "
        "momentum. Cached 15 s while live, 5 min before kick-off, 1 h after full time."
    ),
    responses={404: {"description": "Unknown match id"}, 503: {"description": "Source unavailable"}},
)
async def get_live_center(match_id: str, db: Session = Depends(get_db)) -> LiveCenterResponse:
    try:
        return await get_live_center_service().get(match_id, db)
    except LiveCenterError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": exc.code, "message": ERROR_MESSAGES_TR.get(exc.code, exc.code)},
        )
