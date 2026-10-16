"""Default data sources of the headline tracker (all reuse existing, cached components).

* fixtures: the provider chain behind GET /matches (HybridProvider -> FotMob by date, shared
  application provider cache), so the tracker costs no more than one extra client of that list;
* prediction: the same endpoint function the match page calls (GET /matches/{id}/prediction),
  after dropping the cached line-up of the match so confirmed line-ups are picked up;
* line-up type fallback: the live match centre (cached).

Every source is injectable (see HeadlineTracker) so tests never touch the network.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.services.headline_tracking.records import as_utc

logger = logging.getLogger(__name__)


class PredictionUnavailable(Exception):
    """The prediction endpoint could not produce a prediction (insufficient data, unknown match)."""


@dataclass(frozen=True)
class ScheduledMatch:
    match_id: str
    competition_id: Optional[str]
    competition_name: Optional[str]
    kickoff_at: datetime  # aware, UTC
    status: str  # SCHEDULED | LIVE | FINISHED | ...
    home_team: Optional[str]
    away_team: Optional[str]


def featured_competitions() -> set[str]:
    from app.config import settings

    return {x.strip() for x in str(settings.featured_competition_ids or "").split(",") if x.strip()}


def _status_text(value: Any) -> str:
    return str(getattr(value, "value", value) or "").upper()


def to_scheduled_match(m: Any) -> Optional[ScheduledMatch]:
    """Domain Match (as the fixture list returns it) -> ScheduledMatch; None without a kick-off."""
    kickoff = as_utc(getattr(m, "scheduled_at", None))
    if kickoff is None or not getattr(m, "id", None):
        return None
    competition_id = getattr(m, "competition_id", None)
    return ScheduledMatch(
        match_id=str(m.id),
        competition_id=str(competition_id) if competition_id is not None else None,
        competition_name=getattr(m, "_provider_competition_name", None),
        kickoff_at=kickoff,
        status=_status_text(getattr(m, "status", None)),
        home_team=getattr(m, "_provider_home_team_name", None),
        away_team=getattr(m, "_provider_away_team_name", None),
    )


@contextmanager
def _provider():
    """The request-time data provider (HybridProvider, shared application cache)."""
    from app.api.dependencies import get_data_provider

    generator = get_data_provider()
    provider = next(generator)
    try:
        yield provider
    finally:
        generator.close()


async def fetch_schedule(now: datetime) -> List[ScheduledMatch]:
    """Fixtures around ``now`` (usually one UTC date; cached per date by the provider)."""
    from_date: date = (now - timedelta(hours=1)).astimezone(timezone.utc).date()
    to_date: date = (now + timedelta(hours=1)).astimezone(timezone.utc).date()
    with _provider() as provider:
        if hasattr(provider, "get_matches_async"):
            matches = await provider.get_matches_async(from_date=from_date, to_date=to_date)
        else:
            matches = provider.get_matches(from_date=from_date, to_date=to_date)
    out = [s for s in (to_scheduled_match(m) for m in matches or []) if s is not None]
    return out


def fotmob_id(match_id: str) -> Optional[str]:
    if match_id.startswith("fotmob_") and match_id[len("fotmob_"):].isdigit():
        return match_id[len("fotmob_"):]
    return None


async def fetch_prediction(match_id: str) -> Dict[str, Any]:
    """A fresh prediction response (as dict) for the match, exactly what the match page gets."""
    from fastapi import HTTPException

    from app.api.v1.endpoints.matches import get_match_prediction
    from app.database.session import SessionLocal
    from app.prediction.squad_value import invalidate_squad_info

    source_id = fotmob_id(match_id)
    if source_id is not None:
        invalidate_squad_info(source_id)  # confirmed line-ups may be only minutes old
    db = SessionLocal()
    try:
        with _provider() as provider:
            response = await get_match_prediction(match_id=match_id, provider=provider, db=db)
    except HTTPException as exc:
        raise PredictionUnavailable(f"HTTP {exc.status_code}: {exc.detail}") from exc
    finally:
        db.close()
    return response.model_dump(mode="json")


_LINEUP_TYPES = {"standard": "confirmed", "confirmed": "confirmed", "predicted": "predicted"}


def normalise_lineup_type(raw: Any) -> Optional[str]:
    """FotMob lineupType as sent -> confirmed | predicted | last_starting11 | None (unknown)."""
    text = str(raw or "").strip().lower()
    if not text:
        return None
    if text in _LINEUP_TYPES:
        return _LINEUP_TYPES[text]
    if "last" in text:
        return "last_starting11"
    return None


def lineup_types_from_squad_info(squad_info: Any) -> Optional[Dict[str, Any]]:
    """Line-up type per side from prediction.squad_info; None when neither side is known."""
    if not isinstance(squad_info, dict):
        return None
    home = normalise_lineup_type((squad_info.get("home") or {}).get("lineup_type"))
    away = normalise_lineup_type((squad_info.get("away") or {}).get("lineup_type"))
    if home is None and away is None:
        return None
    return {"home": home, "away": away, "source": "prediction.squad_info"}


async def fetch_lineup_types(match_id: str) -> Optional[Dict[str, Any]]:
    """Line-up type per side from the live match centre (cached); None when unknown."""
    from app.services.live_center.service import LiveCenterError, get_live_center_service

    try:
        response = await get_live_center_service().get(match_id)
    except LiveCenterError:
        return None
    home = response.lineups.home.lineup_type
    away = response.lineups.away.lineup_type
    if home is None and away is None:
        return None
    return {"home": home, "away": away, "source": "live_center"}
