"""Cards / corners / shots predictions for a match.

GET /api/v1/matches/{match_id}/props
  Expected counts per team and in total for yellow cards, corners, shots and
  shots on target, with over/under probabilities for the standard lines and the
  teams' last-5 averages. Teams, competition and referee come from the live
  match centre (FotMob matchDetails, cached). 503 when the model is not deployed.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.prediction.props_model import STAT_MARKETS, get_props_model
from app.services.live_center.constants import ERROR_MESSAGES_TR
from app.services.live_center.service import LiveCenterError, get_live_center_service

router = APIRouter(tags=["props"])


class PropLine(BaseModel):
    line: float
    over: float
    under: float


class PropMarket(BaseModel):
    key: str
    label_tr: str
    group: str
    scope: str = Field(description="home | away | total")
    expected: float
    lines: list[PropLine]
    banko_eligible: bool = Field(True, description="False for markets the audit ruled out as banko (cards, total corners)")


class RecentAverages(BaseModel):
    stat: str
    label_tr: str
    for_last5: Optional[float] = None
    against_last5: Optional[float] = None
    n: Optional[int] = None


class PropsResponse(BaseModel):
    match_id: str
    model_version: str
    trained_through: Optional[str] = None
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    competition_id: Optional[str] = None
    referee: Optional[str] = None
    referee_used: bool = False
    unknown_teams: list[str] = Field(default_factory=list)
    markets: list[PropMarket]
    recent: dict[str, list[RecentAverages]] = Field(default_factory=dict, description="home/away last-5 actual averages")
    note: str = (
        "Beklenen sayılar ve olasılıklar TUTAR X kart/korner/şut modelinden; takımın kendi eğilimi, rakibin "
        "verdiği/yediği sayılar, lig ortalaması ve (kartlarda) hakem etkisi. Son 5 maç ortalamaları gerçek değerlerdir."
    )


RECENT_LABELS = {"yellow_cards": "Sarı kart", "corners": "Korner", "total_shots": "Şut", "shots_on_target": "İsabetli şut"}


@router.get(
    "/matches/{match_id}/props",
    response_model=PropsResponse,
    summary="Cards, corners and shots predictions",
    responses={404: {"description": "Unknown match"}, 503: {"description": "Model not deployed or source unavailable"}},
)
async def get_match_props(match_id: str, db: Session = Depends(get_db)) -> PropsResponse:
    model = get_props_model()
    if model is None:
        raise HTTPException(status_code=503, detail={"error": "props_model_unavailable", "message": "Kart/korner/şut modeli henüz yüklenmedi."})
    try:
        centre = await get_live_center_service().get(match_id, db)
    except LiveCenterError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": exc.code, "message": ERROR_MESSAGES_TR.get(exc.code, exc.code)},
        )
    home_id, away_id = centre.teams.home.id, centre.teams.away.id
    if not home_id or not away_id:
        raise HTTPException(status_code=503, detail={"error": "teams_unknown", "message": "Takım kimlikleri alınamadı."})
    names = {"home": centre.teams.home.name or "Ev sahibi", "away": centre.teams.away.name or "Deplasman"}
    result = model.predict(home_id, away_id, centre.competition_id, centre.referee, names)
    if result["unknown_teams"]:
        # Unknown teams would fall back to the league average, which was never validated.
        raise HTTPException(
            status_code=404,
            detail={"error": "teams_not_in_model", "message": "Bu takımlar için kart/korner/şut verisi yok."},
        )

    recent: dict[str, list[RecentAverages]] = {}
    for side, tid in (("home", home_id), ("away", away_id)):
        team = model.team_recent.get(str(tid)) or {}
        recent[side] = [
            RecentAverages(
                stat=stat,
                label_tr=RECENT_LABELS[stat],
                for_last5=(team.get(stat) or {}).get("for_last5"),
                against_last5=(team.get(stat) or {}).get("against_last5"),
                n=(team.get(stat) or {}).get("n"),
            )
            for stat in STAT_MARKETS
            if stat in model.stats
        ]
    return PropsResponse(
        match_id=centre.match_id,
        model_version=model.version,
        trained_through=model.trained_through,
        home_team=names["home"],
        away_team=names["away"],
        competition_id=centre.competition_id,
        referee=centre.referee,
        referee_used=result["referee_used"],
        unknown_teams=result["unknown_teams"],
        markets=[PropMarket(**m) for m in result["markets"]],
        recent=recent,
    )
