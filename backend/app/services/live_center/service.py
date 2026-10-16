"""Live match centre service: FotMob matchDetails -> parsed contract, cached and coalesced.

* match ids: ``fotmob_<id>``, a bare FotMob id, or a local ``matches.id`` whose
  ``provider_id`` is the FotMob id.
* HTTP goes through ``TeamNewsFotMobClient`` (in-process pacing <= 1 req/s,
  the shared cross-process limiter, 403/challenge stop, 429 back-off).
* The parsed response is cached for ``cache_ttl_seconds`` (15 s live, 5 min
  before kick-off, 1 h finished; see ``parsers.ttl_for``). Concurrent callers
  for the same match share one in-flight fetch.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from app.services.live_center.parsers import LiveCenterPayloadError, parse_match_details
from app.services.live_center.schemas import LiveCenterResponse
from app.services.team_news.fotmob_client import (
    FotMobBlockedError,
    FotMobNotFoundError,
    FotMobRateLimitedError,
    FotMobUnavailableError,
    TeamNewsFotMobClient,
)

logger = logging.getLogger(__name__)

FOTMOB_PREFIX = "fotmob_"


class LiveCenterError(Exception):
    """``code`` is a key of constants.ERROR_MESSAGES_TR."""

    def __init__(self, code: str, status_code: int, detail: str = ""):
        super().__init__(detail or code)
        self.code = code
        self.status_code = status_code


def provider_id_from_match_id(match_id: str, db=None) -> str:
    """FotMob match id for a route id, or LiveCenterError('unknown_match_id')."""
    mid = (match_id or "").strip()
    if mid.startswith(FOTMOB_PREFIX) and mid[len(FOTMOB_PREFIX):].isdigit():
        return mid[len(FOTMOB_PREFIX):]
    if mid.isdigit():
        return mid
    if db is not None and mid:
        try:
            from app.database.models import Match

            row = db.query(Match.provider_id).filter(Match.id == mid).first()
        except Exception:  # noqa: BLE001 - a DB problem must not become a fake answer
            logger.exception("live-center: match id lookup failed for %s", mid)
            row = None
        if row and row[0] and str(row[0]).isdigit():
            return str(row[0])
    raise LiveCenterError("unknown_match_id", 404, mid)


class LiveCenterService:
    def __init__(self, client: Optional[TeamNewsFotMobClient] = None, clock=time.monotonic):
        self._client = client
        self._clock = clock
        self._cache: dict[str, tuple[float, LiveCenterResponse]] = {}
        self._inflight: dict[str, asyncio.Future] = {}

    def _get_client(self) -> TeamNewsFotMobClient:
        if self._client is None:
            self._client = TeamNewsFotMobClient()
        return self._client

    async def get(self, match_id: str, db=None) -> LiveCenterResponse:
        provider_id = provider_id_from_match_id(match_id, db)
        route_id = match_id if match_id.startswith(FOTMOB_PREFIX) else f"{FOTMOB_PREFIX}{provider_id}"
        cached = self._cache.get(provider_id)
        if cached is not None and cached[0] > self._clock():
            return cached[1]
        pending = self._inflight.get(provider_id)
        if pending is not None:
            return await asyncio.shield(pending)
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._inflight[provider_id] = fut
        try:
            result = await self._fetch(route_id, provider_id)
        except BaseException as exc:
            if not fut.done():
                fut.set_exception(exc)
                fut.exception()  # mark retrieved: waiters re-raise it, nobody else has to
            raise
        else:
            if not fut.done():
                fut.set_result(result)
            return result
        finally:
            self._inflight.pop(provider_id, None)

    async def _fetch(self, route_id: str, provider_id: str) -> LiveCenterResponse:
        client = self._get_client()
        try:
            res = await client.match_details(provider_id, ttl_seconds=0)
        except FotMobBlockedError as exc:
            raise LiveCenterError("source_blocked", 503, str(exc)) from exc
        except FotMobRateLimitedError as exc:
            raise LiveCenterError("source_rate_limited", 503, str(exc)) from exc
        except FotMobNotFoundError as exc:
            raise LiveCenterError("match_not_found_at_source", 404, str(exc)) from exc
        except FotMobUnavailableError as exc:
            raise LiveCenterError("source_unavailable", 503, str(exc)) from exc
        try:
            parsed = parse_match_details(
                res.data,
                match_id=route_id,
                provider_match_id=provider_id,
                fetched_at=res.fetched_at or datetime.now(timezone.utc),
            )
        except LiveCenterPayloadError as exc:
            logger.warning("live-center: unusable FotMob body for %s: %s", provider_id, exc)
            raise LiveCenterError("source_payload_invalid", 503, str(exc)) from exc
        ttl = max(1, int(parsed.cache_ttl_seconds or 15))
        self._cache[provider_id] = (self._clock() + ttl, parsed)
        if len(self._cache) > 512:
            now = self._clock()
            for key in [k for k, (exp, _) in self._cache.items() if exp <= now]:
                self._cache.pop(key, None)
        return parsed


_service: Optional[LiveCenterService] = None


def get_live_center_service() -> LiveCenterService:
    global _service
    if _service is None:
        _service = LiveCenterService()
    return _service
