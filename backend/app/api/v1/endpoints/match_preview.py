"""Pre-match analysis ("Maç analizi") endpoint.

GET /api/v1/matches/{match_id}/preview
  match_id: "fotmob_<FotMob match id>", the bare FotMob id, or a local matches.id.
  Per side: last 5 matches (any competition except friendlies), last 5 at home / away,
  goals and xG, rest days, absentees, line-up type and rotation versus the previous
  match's XI, plus deterministic Turkish highlights. Results and xG come from the local
  database; absentees and line-ups from the FotMob live centre (cached, paced). Missing
  data is ``null`` with a ``missing_reason``. Errors: 404/503 with a reason code and a
  Turkish message, never fake data.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.live_center.service import LiveCenterError
from app.services.match_preview.schemas import MatchPreviewResponse
from app.services.match_preview.service import MatchPreviewError, error_message_tr, get_match_preview_service

router = APIRouter(tags=["match-preview"])


@router.get(
    "/matches/{match_id}/preview",
    response_model=MatchPreviewResponse,
    summary="Pre-match analysis (last 5, form, rest, absentees, rotation)",
    description=(
        "Deterministic pre-match analysis built from real results (local database, FotMob data) and the "
        "FotMob live centre. The response is cached for 5 minutes."
    ),
    responses={404: {"description": "Unknown match id"}, 503: {"description": "Source unavailable"}},
)
async def get_match_preview(match_id: str, db: Session = Depends(get_db)) -> MatchPreviewResponse:
    try:
        return await get_match_preview_service().get(match_id, db)
    except (LiveCenterError, MatchPreviewError) as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": exc.code, "message": error_message_tr(exc.code)},
        )
