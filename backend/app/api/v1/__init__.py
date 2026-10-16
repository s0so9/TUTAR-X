"""API version 1 module."""

from fastapi import APIRouter

from app.api.v1.endpoints import matches, live_matches, competitions, team_news, teams, live_center, props, track_record
from app.api.v1.endpoints import match_preview
from app.routers import odds

# Create API v1 router
api_router = APIRouter(prefix="/api/v1")

# Include endpoint routers
# IMPORTANT: live_matches must be registered BEFORE matches to prevent
# /{match_id} from capturing /live as a match_id parameter
api_router.include_router(competitions.router)
api_router.include_router(live_matches.router)
# Team-news live layer: /matches/{match_id}/team-news and /teams/{team_id}/squad
api_router.include_router(team_news.router)
# Live match centre: /matches/{match_id}/live-center
api_router.include_router(live_center.router)
# Cards / corners / shots: /matches/{match_id}/props
api_router.include_router(props.router)
# Headline picks (Banko / Oranli) track record: /track-record/headline, /matches/{match_id}/headline-record
api_router.include_router(track_record.router)
# Pre-match analysis: /matches/{match_id}/preview
api_router.include_router(match_preview.router)
api_router.include_router(teams.router)
api_router.include_router(matches.router)
api_router.include_router(odds.router)

__all__ = ["api_router"]
