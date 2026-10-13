"""Polite FotMob HTTP client for the team-news live layer.

* base URL: ``settings.fotmob_base_url``; User-Agent of the training collectors
  (scripts/data_collection/collect_fotmob_details.py).
* in-process limit: at most one request per ``min_interval_seconds`` (default
  1 s, ``settings.team_news_fotmob_min_interval_seconds``) across every client
  of the process, one request in flight per client.
* before EVERY request the shared cross-process limiter
  ``scripts/data_collection/fotmob_rate.py`` (acquire_async) is called when the
  file exists; HTTP 429 -> ``report_429(Retry-After or 60)`` + RateLimited.
* 403, a captcha or an HTML challenge page -> ``FotMobBlockedError``; the
  client then refuses further requests (``blocked``) and the caller stops.
  Bot protection is never worked around.
* short in-memory response cache per client (TTL per call).
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (TUTAR X research collector; low-rate)"
DEFAULT_BASE_URL = "https://www.fotmob.com"
_LIMITER_PATH = Path(__file__).resolve().parents[3] / "scripts" / "data_collection" / "fotmob_rate.py"


class FotMobError(Exception):
    """Base error of the team-news FotMob client."""


class FotMobBlockedError(FotMobError):
    """403 / captcha / challenge page: stop collecting and report it."""


class FotMobRateLimitedError(FotMobError):
    """HTTP 429 (the shared limiter was told to cool down)."""


class FotMobNotFoundError(FotMobError):
    """HTTP 404."""


class FotMobUnavailableError(FotMobError):
    """Network error, timeout, 5xx or an unexpected status."""


@dataclass
class FetchResult:
    data: Any
    raw: bytes
    fetched_at: datetime
    from_cache: bool = False


# ----------------------------------------------------------------- process-wide pacing

_slot_lock = threading.Lock()
_next_slot = 0.0


def _reserve_slot(min_interval: float) -> float:
    """Reserve the next request slot of this process; returns seconds to wait."""
    global _next_slot
    with _slot_lock:
        now = time.monotonic()
        slot = max(now, _next_slot)
        _next_slot = slot + max(0.0, min_interval)
        return slot - now


_limiter_module: Optional[ModuleType] = None
_limiter_loaded = False


def shared_limiter() -> Optional[ModuleType]:
    """scripts/data_collection/fotmob_rate.py loaded by path (None when absent)."""
    global _limiter_module, _limiter_loaded
    if not _limiter_loaded:
        _limiter_loaded = True
        if _LIMITER_PATH.exists():
            try:
                spec = importlib.util.spec_from_file_location("tutarx_fotmob_rate", _LIMITER_PATH)
                module = importlib.util.module_from_spec(spec)
                assert spec.loader is not None
                spec.loader.exec_module(module)
                _limiter_module = module
            except Exception:  # pragma: no cover - defensive
                logger.exception("team-news: could not load the shared FotMob limiter %s", _LIMITER_PATH)
        else:  # pragma: no cover - deployment without scripts/
            logger.warning("team-news: shared FotMob limiter not found at %s", _LIMITER_PATH)
    return _limiter_module


def _looks_like_challenge(resp: httpx.Response) -> bool:
    ctype = (resp.headers.get("content-type") or "").lower()
    if "json" in ctype:
        return False
    head = resp.content[:2048].lower()
    return (
        "text/html" in ctype
        or b"<html" in head
        or b"captcha" in head
        or b"challenge" in head
    )


def _mentions_challenge(resp: httpx.Response) -> bool:
    head = resp.content[:4096].lower()
    return b"captcha" in head or b"challenge" in head


class TeamNewsFotMobClient:
    """Async FotMob client with pacing, the shared limiter and a short cache."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        *,
        min_interval_seconds: Optional[float] = None,
        timeout_seconds: float = 15.0,
        use_shared_limiter: bool = True,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        max_cache_entries: int = 2048,
        test_mode: bool = False,
    ):
        """``test_mode`` (tests with a mock transport only): no pacing floor and no
        shared limiter, so unit tests run fast and never touch the shared state."""
        if base_url is None or min_interval_seconds is None:
            from app.config import settings

            base_url = base_url or settings.fotmob_base_url
            if min_interval_seconds is None:
                min_interval_seconds = settings.team_news_fotmob_min_interval_seconds
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        if test_mode:
            self.min_interval_seconds = max(0.0, float(min_interval_seconds))
            self.use_shared_limiter = False
        else:
            self.min_interval_seconds = max(1.0, float(min_interval_seconds))  # never faster than 1 req/s
            self.use_shared_limiter = use_shared_limiter
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            transport=transport,
        )
        self._lock: Optional[asyncio.Lock] = None
        self._cache: dict[str, tuple[float, FetchResult]] = {}
        self._max_cache_entries = max_cache_entries
        self.blocked = False
        self.blocked_detail: Optional[str] = None
        self.request_count = 0
        self.connect_retries = 0 if test_mode else 2
        self.connect_retry_seconds = 3.0

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "TeamNewsFotMobClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    # ------------------------------------------------------------------ endpoints

    async def match_details(self, match_id: str, ttl_seconds: float = 60.0) -> FetchResult:
        return await self.get_json("/api/data/matchDetails", {"matchId": str(match_id)}, ttl_seconds)

    async def team(self, team_id: str, ttl_seconds: float = 600.0) -> FetchResult:
        return await self.get_json("/api/data/teams", {"id": str(team_id)}, ttl_seconds)

    async def player(self, player_id: str, ttl_seconds: float = 3600.0) -> FetchResult:
        return await self.get_json("/api/data/playerData", {"id": str(player_id)}, ttl_seconds)

    async def league(self, league_id: int | str, ttl_seconds: float = 3600.0) -> FetchResult:
        return await self.get_json("/api/data/leagues", {"id": str(league_id)}, ttl_seconds)

    # ------------------------------------------------------------------ core

    async def get_json(self, endpoint: str, params: dict[str, str], ttl_seconds: float) -> FetchResult:
        key = endpoint + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
        cached = self._cache.get(key)
        if cached is not None and cached[0] > time.monotonic():
            res = cached[1]
            return FetchResult(res.data, res.raw, res.fetched_at, from_cache=True)
        if self.blocked:
            raise FotMobBlockedError(self.blocked_detail or "FotMob blocked earlier in this process")

        if self._lock is None:
            self._lock = asyncio.Lock()
        limiter = shared_limiter() if self.use_shared_limiter else None
        async with self._lock:
            attempt = 0
            while True:
                attempt += 1
                wait = _reserve_slot(self.min_interval_seconds)
                if wait > 0:
                    await asyncio.sleep(wait)
                if limiter is not None:
                    await _acquire_shared(limiter)  # before EVERY request, retries included
                self.request_count += 1
                try:
                    resp = await self._client.get(endpoint, params=params)
                    break
                except httpx.TimeoutException as exc:
                    raise FotMobUnavailableError(f"timeout {endpoint}: {type(exc).__name__}") from exc
                except httpx.ConnectError as exc:
                    # DNS/connect failures (no request reached FotMob): short bounded retry
                    if attempt > self.connect_retries:
                        raise FotMobUnavailableError(f"connection error {endpoint}: {exc}") from exc
                    await asyncio.sleep(self.connect_retry_seconds * attempt)
                except httpx.RequestError as exc:
                    raise FotMobUnavailableError(f"request error {endpoint}: {type(exc).__name__}") from exc

        fetched_at = datetime.now(timezone.utc)
        if resp.status_code == 403:
            self._mark_blocked(f"HTTP 403 on {endpoint}")
        if resp.status_code == 429:
            retry_after = _to_seconds(resp.headers.get("Retry-After"))
            if limiter is not None:
                limiter.report_429(retry_after)
            raise FotMobRateLimitedError(f"HTTP 429 on {endpoint} (Retry-After={resp.headers.get('Retry-After')})")
        if resp.status_code == 404:
            raise FotMobNotFoundError(f"HTTP 404 on {endpoint} {params}")
        if resp.status_code != 200:
            if _mentions_challenge(resp):  # e.g. a 503 captcha page; a plain 5xx error page is not a block
                self._mark_blocked(f"HTTP {resp.status_code} captcha/challenge page on {endpoint}")
            raise FotMobUnavailableError(f"HTTP {resp.status_code} on {endpoint}")
        if _looks_like_challenge(resp):
            self._mark_blocked(f"non-JSON challenge page on {endpoint}")
        try:
            data = resp.json()
        except ValueError as exc:
            self._mark_blocked(f"invalid JSON on {endpoint}")
            raise FotMobBlockedError(self.blocked_detail or "") from exc  # pragma: no cover
        result = FetchResult(data=data, raw=resp.content, fetched_at=fetched_at)
        if ttl_seconds > 0:
            if len(self._cache) >= self._max_cache_entries:
                now = time.monotonic()
                for k in [k for k, v in self._cache.items() if v[0] <= now] or list(self._cache)[: self._max_cache_entries // 4]:
                    self._cache.pop(k, None)
            self._cache[key] = (time.monotonic() + ttl_seconds, result)
        return result

    def _mark_blocked(self, detail: str) -> None:
        self.blocked = True
        self.blocked_detail = detail
        logger.error("team-news: FotMob refused/challenged the request (%s); stopping requests", detail)
        raise FotMobBlockedError(detail)


async def _acquire_shared(limiter: ModuleType, attempts: int = 300) -> None:
    """limiter.acquire_async() tolerant of a Windows race in fotmob_rate._Lock:
    os.mkdir on a lock directory that another process is deleting raises
    PermissionError (not FileExistsError). No request slot was taken when that
    happens, so retrying is safe."""
    for _ in range(attempts):
        try:
            await limiter.acquire_async()
            return
        except PermissionError:
            await asyncio.sleep(0.01 + random.random() * 0.02)
    raise FotMobUnavailableError("shared FotMob limiter lock unavailable")


def _to_seconds(value: Optional[str]) -> float:
    try:
        return max(1.0, float(value)) if value else 60.0
    except ValueError:
        return 60.0
