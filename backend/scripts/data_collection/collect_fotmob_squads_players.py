"""Collect FotMob squads and player profiles of the TARGET13 competitions (season 2026/2027).

AS-OF-TODAY SNAPSHOT COLLECTOR - source: FotMob unofficial API.

Every parsed row describes the state at ``snapshot_at`` (= the time its response was
fetched). Squads, injuries, market values, season stats and recent-match lists change
over time, so these rows must NEVER be used as features for matches played before
``snapshot_at`` (look-ahead leak). They describe "today", not the past.

Competitions (FotMob league ids): the 10 strongest leagues by UEFA association
coefficient - 47 Premier League, 87 LaLiga, 55 Serie A, 54 Bundesliga, 53 Ligue 1,
57 Eredivisie, 61 Liga Portugal, 40 Belgian Pro League, 71 Super Lig, 122 Czech 1. Liga -
plus 42 Champions League, 73 Europa League and 10216 Conference League.

Endpoints (base ``settings.fotmob_base_url``):
  /api/data/leagues?id=<league>&season=2026/2027  -> team list (table + fixtures)
  /api/data/teams?id=<team>                       -> squad snapshot
  /api/data/playerData?id=<player>                -> player profile
  /api/data/matchDetails?matchId=<match>          -> fallback roster only: a club FotMob sends no
                                                     squad list and no overview.lastLineupStats for

Raw cache (untouched response bodies, gzip, written atomically: temp file + os.replace):
  backend/data/raw_cache/fotmob_squads_leagues/<league>_<YYYY-YYYY>.json.gz
  backend/data/raw_cache/fotmob_teams/<team id>.json.gz
  backend/data/raw_cache/fotmob_players/<player id>.json.gz
  backend/data/raw_cache/fotmob_squads_fallback_matches/<match id>.json.gz
and in each directory ``_manifest.jsonl`` with one line per HTTP response:
  {"id": <int>, "fetched_at": "<UTC ISO>", "http_status": <int>, "bytes": <int>}
(league lines also carry "season"). A 200 line is written only after the raw file was
replaced, so "latest 200 line" = the snapshot time of the raw file on disk.

Parsed outputs (rebuilt from the raw cache at the end of every run, or with --from-raw),
in backend/data/players/: teams_2026_27.jsonl, squad_members_2026_27.jsonl, players.jsonl,
player_recent_matches.jsonl, player_market_values.jsonl, player_career.jsonl
(field paths: backend/data/players/README_players.md). The parsing itself lives in
fotmob_squads_parse.py (pure functions, no IO) so loaders can reuse it on the raw cache.

Politeness (hard caps): <= 2 workers, >= 0.5 s between two requests of one worker, the
shared cross-process limiter (``fotmob_rate.acquire``) before EVERY request, report_429 +
exponential backoff on HTTP 429, and a full stop on HTTP 403 / captcha / challenge pages
(never worked around).

Honesty (AGENTS.md 8-14): values are copied as sent; a value FotMob does not send is null.

Usage (from backend/):
  venv/Scripts/python.exe scripts/data_collection/collect_fotmob_squads_players.py
  ... --teams-only                 # league lists + squads only (injury flags, squad changes)
  ... --refresh-older-than 6       # re-fetch snapshots older than 6 h (periodic refresh job)
  ... --from-raw                   # rebuild the parsed files from the raw cache (no network)
  ... --coverage                   # markdown coverage tables of the parsed files
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import queue
import random
import sys
import threading
import time
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

import httpx

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import fotmob_rate  # noqa: E402  (shared cross-process FotMob politeness limiter)
import fotmob_squads_parse  # noqa: E402  (pure parsers, shared with loaders and tests)
from fotmob_squads_parse import (  # noqa: E402
    DOMESTIC_LEAGUES,
    EURO_CUPS,
    TARGET13,
    _to_float,
    _to_int,
    build_team_index,
    fallback_match_candidates,
    has_lineup,
    ordered_team_ids,
    parse_league,
    parse_player,
    team_roster,
    valid_league,
    valid_match,
    valid_player,
    valid_team,
)

BACKEND_DIR = SCRIPT_DIR.parents[1]
DEFAULT_RAW_ROOT = BACKEND_DIR / "data" / "raw_cache"
DEFAULT_OUT_DIR = BACKEND_DIR / "data" / "players"
DEFAULT_BASE_URL = "https://www.fotmob.com"
DEFAULT_SEASON = "2026/2027"
LEAGUES_DIR = "fotmob_squads_leagues"
TEAMS_DIR = "fotmob_teams"
PLAYERS_DIR = "fotmob_players"
FALLBACK_MATCHES_DIR = "fotmob_squads_fallback_matches"
MANIFEST_NAME = "_manifest.jsonl"
LOCK_NAME = ".fotmob_squads_players.lock"
ERRORS_FILE = "collect_errors.jsonl"
# Same User-Agent as collect_fotmob_details.py (identifies the low-rate research collector).
USER_AGENT = "Mozilla/5.0 (TUTAR X research collector; low-rate)"


# A non-JSON body containing one of these is a bot-protection page: stop, never work around it.
CHALLENGE_MARKERS = (
    b"captcha",
    b"cf-chl",
    b"challenge-platform",
    b"just a moment",
    b"attention required",
    b"cf-browser-verification",
    b"px-captcha",
    b"ddos-guard",
    b"are you a robot",
    b"verify you are human",
)

_MIN_TS = datetime.min.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------- helpers


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def season_file_key(season: str) -> str:
    """'2026/2027' -> '2026-2027' (file-name safe)."""
    return season.replace("/", "-")


def season_suffix(season: str) -> str:
    """'2026/2027' -> '2026_27' (output file suffix)."""
    if "/" in season:
        first, second = season.split("/", 1)
        return f"{first}_{second[-2:]}"
    return season


def output_names(season: str) -> dict[str, str]:
    sfx = season_suffix(season)
    return {
        "teams": f"teams_{sfx}.jsonl",
        "squad_members": f"squad_members_{sfx}.jsonl",
        "players": "players.jsonl",
        "recent_matches": "player_recent_matches.jsonl",
        "market_values": "player_market_values.jsonl",
        "career": "player_career.jsonl",
    }


def iter_jsonl(path: Path) -> Iterator[dict]:
    """Rows of a JSONL file; undecodable lines (a partial last line of an interrupted run) are skipped."""
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj


def _ensure_trailing_newline(path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        with path.open("rb") as fh:
            fh.seek(-1, 2)
            last = fh.read(1)
        if last != b"\n":
            with path.open("ab") as fa:
                fa.write(b"\n")


def _replace_with_retry(src: Path, dst: Path, attempts: int = 60) -> None:
    """os.replace with retries: on Windows the target cannot be replaced while a reader has it open."""
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.25)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}_{threading.get_ident()}")
    tmp.write_bytes(data)
    _replace_with_retry(tmp, path)


# --------------------------------------------------------------------------- raw cache


class RawStore:
    """``<dir>/<key>.json.gz`` (untouched response body, gzip) + ``<dir>/_manifest.jsonl``."""

    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self.manifest_path = self.dir / MANIFEST_NAME
        self._lock = threading.Lock()
        self._fh = None

    def path(self, key: Any) -> Path:
        return self.dir / f"{key}.json.gz"

    def latest_ok(self, key_fn: Callable[[dict], Any] = lambda r: _to_int(r.get("id"))) -> dict[Any, str]:
        """{key: fetched_at of the most recent HTTP-200 manifest line}."""
        out: dict[Any, str] = {}
        for row in iter_jsonl(self.manifest_path):
            if row.get("http_status") != 200:
                continue
            key, ts = key_fn(row), row.get("fetched_at")
            if key is None or not isinstance(ts, str):
                continue
            if key not in out or (_parse_ts(ts) or _MIN_TS) > (_parse_ts(out[key]) or _MIN_TS):
                out[key] = ts
        return out

    def append(self, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self._lock:
            if self._fh is None:
                self.dir.mkdir(parents=True, exist_ok=True)
                _ensure_trailing_newline(self.manifest_path)
                self._fh = self.manifest_path.open("a", encoding="utf-8")
            self._fh.write(line)
            self._fh.flush()

    def save(self, key: Any, body: bytes) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_bytes(self.path(key), gzip.compress(body, compresslevel=6))

    def load(self, key: Any) -> Any | None:
        try:
            return json.loads(gzip.decompress(self.path(key).read_bytes()))
        except FileNotFoundError:
            return None

    def mtime_iso(self, key: Any) -> str | None:
        try:
            ts = self.path(key).stat().st_mtime
        except FileNotFoundError:
            return None
        return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")

    def clean_temp_files(self) -> int:
        n = 0
        if self.dir.exists():
            for p in self.dir.glob("*.json.gz.tmp*"):
                try:
                    p.unlink()
                    n += 1
                except OSError:
                    pass
        return n

    def close(self) -> None:
        with self._lock:
            if self._fh is not None:
                self._fh.close()
                self._fh = None


class ErrorLog:
    """Append-only error file (thread-safe)."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._fh = None
        self.count = 0

    def write(self, kind: str, item_id: Any, error: str, detail: str = "", attempts: int = 0, **extra: Any) -> None:
        rec = {"kind": kind, "id": item_id, "error": error, "detail": str(detail)[:300], "attempts": attempts,
               "at": _utc_now(), **extra}
        with self._lock:
            if self._fh is None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                _ensure_trailing_newline(self.path)
                self._fh = self.path.open("a", encoding="utf-8")
            self._fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self._fh.flush()
            self.count += 1

    def close(self) -> None:
        with self._lock:
            if self._fh is not None:
                self._fh.close()
                self._fh = None


class CollectorLock:
    """One collecting instance at a time (heartbeat lock file; stale after ``stale_seconds``).

    Never uses os.kill to probe a PID: on Windows that terminates the process.
    """

    def __init__(self, path: Path, stale_seconds: float = 600.0, heartbeat_seconds: float = 30.0):
        self.path = path
        self.stale_seconds = stale_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "CollectorLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    age = time.time() - self.path.stat().st_mtime
                except FileNotFoundError:
                    continue
                if age > self.stale_seconds:
                    try:
                        os.remove(self.path)
                    except OSError:
                        pass
                    continue
                raise SystemExit(f"another collector instance holds {self.path} (heartbeat {age:.0f}s ago)")
            else:
                os.write(fd, json.dumps({"pid": os.getpid(), "started_at": _utc_now()}).encode())
                os.close(fd)
                break
        self._thread = threading.Thread(target=self._beat, name="lock-heartbeat", daemon=True)
        self._thread.start()
        return self

    def _beat(self) -> None:
        while not self._stop.wait(self.heartbeat_seconds):
            try:
                os.utime(self.path)
            except OSError:
                pass

    def __exit__(self, *exc: Any) -> None:
        self._stop.set()
        try:
            os.remove(self.path)
        except OSError:
            pass


# --------------------------------------------------------------------------- fetching


class Blocked(RuntimeError):
    """FotMob answered 403 / a captcha / a challenge page: the whole run must stop."""


class Fetched:
    __slots__ = ("data", "body", "fetched_at", "attempts")

    def __init__(self, data: Any, body: bytes, fetched_at: str, attempts: int):
        self.data, self.body, self.fetched_at, self.attempts = data, body, fetched_at, attempts


class Failed:
    __slots__ = ("error", "detail", "attempts", "http_status")

    def __init__(self, error: str, detail: str, attempts: int, http_status: int | None = None):
        self.error, self.detail, self.attempts, self.http_status = error, detail, attempts, http_status


def detect_block(status: int, content_type: str, body: bytes) -> str | None:
    """Name of the bot-protection signal in a response, or None."""
    if status == 403:
        return "http_403"
    if "json" in (content_type or "").lower():
        return None
    head = body[:16384].lower()
    if any(marker in head for marker in CHALLENGE_MARKERS):
        return "challenge_page"
    if status == 200:
        return "non_json_200"  # an HTML page where the API sends JSON: treat as a challenge, stop
    return None


class Fetcher:
    """GET with the shared limiter, retries/backoff, 429 cool-down and a hard stop on blocks."""

    def __init__(
        self,
        base_url: str,
        timeout: float,
        max_retries: int,
        stop: threading.Event,
        acquire: Callable[[], None] | None = None,
        report_429: Callable[[float], None] | None = None,
        transport: httpx.BaseTransport | None = None,
        backoff_base: float = 2.0,
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.stop = stop
        self.acquire = acquire or fotmob_rate.acquire
        self.report_429 = report_429 or fotmob_rate.report_429
        self.transport = transport
        self.backoff_base = backoff_base
        self._local = threading.local()
        self._clients: list[httpx.Client] = []
        self._clients_lock = threading.Lock()
        self.requests = 0
        self.limiter_retries = 0

    def _client(self) -> httpx.Client:
        client = getattr(self._local, "client", None)
        if client is None:
            client = httpx.Client(
                base_url=self.base_url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
                transport=self.transport,
            )
            self._local.client = client
            with self._clients_lock:
                self._clients.append(client)
        return client

    def close(self) -> None:
        with self._clients_lock:
            for c in self._clients:
                c.close()
            self._clients.clear()

    def _acquire_slot(self, tries: int = 20) -> None:
        """The shared limiter, before EVERY FotMob request. On Windows its state-file replace can be
        denied for a moment (another process / a scanner holds the file): such an OSError is retried,
        and no request is sent until ``acquire()`` has returned normally."""
        for attempt in range(tries):
            try:
                self.acquire()
                return
            except OSError:
                if attempt == tries - 1:
                    raise
                with self._clients_lock:
                    self.limiter_retries += 1
                time.sleep(0.2 + 0.1 * attempt)

    def get(self, path: str, params: dict[str, Any], log_http: Callable[[int, int, str], None]) -> Fetched | Failed:
        """``log_http(status, bytes, fetched_at)`` is called for every non-200 HTTP response;
        the caller logs the 200 line itself after the raw body has been stored."""
        attempts = 0
        last = Failed("unknown", "", 0)
        while attempts <= self.max_retries:
            if self.stop.is_set():
                return Failed("stopped", "run stopped", attempts)
            attempts += 1
            self._acquire_slot()  # shared cross-process limiter: before EVERY FotMob request
            with self._clients_lock:
                self.requests += 1
            try:
                resp = self._client().get(path, params=params)
            except httpx.TimeoutException as exc:
                last = Failed("timeout", type(exc).__name__, attempts)
            except httpx.RequestError as exc:
                last = Failed("connection_error", f"{type(exc).__name__}: {exc}"[:200], attempts)
            else:
                fetched_at = _utc_now()
                body = resp.content
                status = resp.status_code
                blocked = detect_block(status, resp.headers.get("content-type", ""), body)
                if blocked:
                    log_http(status, len(body), fetched_at)
                    self.stop.set()
                    raise Blocked(f"{blocked} (HTTP {status}) for {path} {params}")
                if status == 200:
                    try:
                        data = json.loads(body)
                    except ValueError as exc:
                        log_http(status, len(body), fetched_at)
                        last = Failed("invalid_json", str(exc)[:200], attempts, status)
                    else:
                        return Fetched(data, body, fetched_at, attempts)
                else:
                    log_http(status, len(body), fetched_at)
                    if status == 404:
                        return Failed("http_404", "not found", attempts, status)
                    if status == 429:
                        retry_after = _to_float(resp.headers.get("Retry-After")) or 60.0
                        self.report_429(min(max(retry_after, 1.0), 600.0))
                        last = Failed("http_429", f"Retry-After={resp.headers.get('Retry-After')}", attempts, status)
                    elif 500 <= status < 600:
                        last = Failed(f"http_{status}", resp.reason_phrase, attempts, status)
                    else:
                        return Failed(f"http_{status}", resp.reason_phrase, attempts, status)
            if attempts <= self.max_retries:
                backoff = min(self.backoff_base ** attempts, 60.0) + random.uniform(0, 1.0) * (self.backoff_base > 0)
                self.stop.wait(backoff)
        return last


# --------------------------------------------------------------------------- collecting


class Stores:
    def __init__(self, raw_root: Path):
        self.leagues = RawStore(raw_root / LEAGUES_DIR)
        self.teams = RawStore(raw_root / TEAMS_DIR)
        self.players = RawStore(raw_root / PLAYERS_DIR)
        self.matches = RawStore(raw_root / FALLBACK_MATCHES_DIR)

    def all(self) -> tuple[RawStore, ...]:
        return (self.leagues, self.teams, self.players, self.matches)

    def close(self) -> None:
        for s in self.all():
            s.close()

    def team_roster(self, tid: int, data: Any, snapshot_at: str | None,
                    match_latest: dict[Any, str] | None = None) -> tuple[dict, list[dict]]:
        """``team_roster`` with the cached fallback matchDetails responses (candidate order) when needed."""
        matches: list[tuple[int, Any]] = []
        snapshots: dict[int, str] = {}
        candidates = fallback_match_candidates(data)
        if candidates:
            latest = match_latest if match_latest is not None else self.matches.latest_ok()
            for mid in candidates:
                match_data = self.matches.load(mid)
                if match_data is not None:
                    matches.append((mid, match_data))
                    snapshots[mid] = latest.get(mid) or self.matches.mtime_iso(mid)
        return team_roster(data, tid, snapshot_at, matches, snapshots)


def league_key(league_id: int, season: str) -> str:
    return f"{league_id}_{season_file_key(season)}"


def needs_fetch(raw_path: Path, latest_ok: str | None, cutoff: datetime | None) -> bool:
    """Missing raw file or no 200 manifest line -> fetch; with a cutoff, also when older than it."""
    if latest_ok is None or not raw_path.exists():
        return True
    if cutoff is not None:
        ts = _parse_ts(latest_ok)
        return ts is None or ts < cutoff
    return False


class RunState:
    def __init__(self, max_consecutive_failures: int, deadline: float | None):
        self.lock = threading.Lock()
        self.consecutive_failures = 0
        self.max_consecutive_failures = max_consecutive_failures
        self.deadline = deadline
        self.stop_reason: str | None = None

    def success(self) -> None:
        with self.lock:
            self.consecutive_failures = 0

    def failure(self, stop: threading.Event) -> None:
        with self.lock:
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.max_consecutive_failures and not stop.is_set():
                self.stop_reason = f"{self.consecutive_failures} consecutive failed requests"
                stop.set()


def run_pool(
    items: list[Any],
    handle: Callable[[Any], bool],
    workers: int,
    delay: float,
    stop: threading.Event,
    state: RunState,
    label: str,
    progress_every: int = 100,
    errors: "ErrorLog | None" = None,
    kind: str = "",
) -> dict[str, int]:
    """Process ``items`` with ``workers`` threads; ``delay`` seconds between two requests of a worker."""
    q: queue.Queue = queue.Queue()
    for it in items:
        q.put(it)
    counts = {"total": len(items), "done": 0, "ok": 0, "failed": 0}
    lock = threading.Lock()
    t0 = time.monotonic()

    def loop() -> None:
        while not stop.is_set():
            if state.deadline is not None and time.monotonic() > state.deadline:
                return
            try:
                item = q.get_nowait()
            except queue.Empty:
                return
            try:
                ok = handle(item)
            except Blocked as exc:
                state.stop_reason = f"BLOCKED: {exc}"
                stop.set()
                print(f"[{_utc_now()}] STOP {state.stop_reason}", flush=True)
                return
            except Exception as exc:  # never let one bad item kill the run silently
                ok = False
                where = traceback.extract_tb(exc.__traceback__)[-1]
                at = f"{Path(where.filename).name}:{where.lineno} ({where.name})"
                print(f"[{_utc_now()}] {label} {item}: unexpected {exc!r} at {at}", flush=True)
                if errors is not None:
                    errors.write(kind or label, item, "unexpected_exception", f"{exc!r} at {at}")
            with lock:
                counts["done"] += 1
                counts["ok" if ok else "failed"] += 1
                if counts["done"] % progress_every == 0 or counts["done"] == counts["total"]:
                    el = max(time.monotonic() - t0, 1e-6)
                    rate = counts["done"] / el
                    eta = (counts["total"] - counts["done"]) / rate if rate > 0 else 0
                    print(
                        f"[{_utc_now()}] {label}: {counts['done']}/{counts['total']} ok={counts['ok']} "
                        f"failed={counts['failed']} rate={rate:.2f}/s eta={eta / 60:.1f} min",
                        flush=True,
                    )
            stop.wait(delay)

    threads = [threading.Thread(target=loop, name=f"{label}-w{i}", daemon=True) for i in range(max(1, workers))]
    for t in threads:
        t.start()
    try:
        for t in threads:
            while t.is_alive():
                t.join(0.5)
    except KeyboardInterrupt:
        state.stop_reason = "interrupted"
        stop.set()
        for t in threads:
            t.join(30)
    counts["not_started"] = q.qsize()
    return counts


def _make_handler(
    kind: str,
    store: RawStore,
    fetcher: Fetcher,
    errors: ErrorLog,
    state: RunState,
    stop: threading.Event,
    season: str,
) -> Callable[[int], bool]:
    endpoint = {"league": "/api/data/leagues", "team": "/api/data/teams", "player": "/api/data/playerData",
                "match": "/api/data/matchDetails"}[kind]
    validator = {"league": valid_league, "team": valid_team, "player": valid_player, "match": valid_match}[kind]

    def handle(item_id: int) -> bool:
        params: dict[str, Any] = {"matchId": item_id} if kind == "match" else {"id": item_id}
        extra: dict[str, Any] = {}
        key: Any = item_id
        if kind == "league":
            params["season"] = season
            extra = {"season": season}
            key = league_key(item_id, season)

        def log_http(status: int, nbytes: int, fetched_at: str) -> None:
            store.append({"id": item_id, "fetched_at": fetched_at, "http_status": status, "bytes": nbytes, **extra})

        res = fetcher.get(endpoint, params, log_http)
        if isinstance(res, Failed):
            if res.error != "stopped":
                errors.write(kind, item_id, res.error, res.detail, res.attempts, http_status=res.http_status, **extra)
                if res.error != "http_404":
                    state.failure(stop)
                else:
                    state.success()
            return False
        if not validator(res.data):
            # Not stored: the manifest's 200 lines must always point at a usable raw file.
            errors.write(kind, item_id, "unexpected_shape", res.body[:200].decode("utf-8", "replace"), res.attempts, **extra)
            state.success()
            return False
        store.save(key, res.body)
        log_http(200, len(res.body), res.fetched_at)
        if kind == "player" and _to_int(res.data.get("id")) != item_id:
            errors.write(kind, item_id, "id_mismatch_info", f"response id {res.data.get('id')}", res.attempts)
        state.success()
        return True

    return handle


def load_league_payloads(stores: Stores, leagues: list[int], season: str) -> list[dict]:
    latest = stores.leagues.latest_ok(key_fn=lambda r: (_to_int(r.get("id")), r.get("season")))
    parsed = []
    for lid in leagues:
        data = stores.leagues.load(league_key(lid, season))
        if data is None:
            continue
        snapshot = latest.get((lid, season)) or stores.leagues.mtime_iso(league_key(lid, season))
        parsed.append(parse_league(data, lid, snapshot))
    return parsed


def squad_player_order(stores: Stores, team_order: list[int]) -> tuple[list[int], dict[int, list[int]]]:
    """Player ids in team order (first occurrence wins) and {player id: [team ids listing him]}
    (squad lists, plus the labelled fallback roster of clubs FotMob sends no squad for)."""
    order: list[int] = []
    teams_of: dict[int, list[int]] = defaultdict(list)
    match_latest = stores.matches.latest_ok()
    for tid in team_order:
        data = stores.teams.load(tid)
        if not valid_team(data):
            continue
        _, members = stores.team_roster(tid, data, None, match_latest)
        for m in members:
            pid = m["player_id"]
            if pid is None:
                continue
            if pid not in teams_of:
                order.append(pid)
            if tid not in teams_of[pid]:
                teams_of[pid].append(tid)
    return order, dict(teams_of)


def collect(args: argparse.Namespace, transport: httpx.BaseTransport | None = None,
            acquire: Callable[[], None] | None = None, report_429: Callable[[float], None] | None = None) -> int:
    raw_root, out_dir, season = Path(args.raw_root), Path(args.out_dir), args.season
    stores = Stores(raw_root)
    for s in stores.all():
        s.clean_temp_files()
    errors = ErrorLog(out_dir / ERRORS_FILE)
    stop = threading.Event()
    deadline = time.monotonic() + args.max_minutes * 60 if args.max_minutes else None
    state = RunState(args.max_consecutive_failures, deadline)
    fetcher = Fetcher(args.base_url, args.timeout, args.max_retries, stop, acquire=acquire,
                      report_429=report_429, transport=transport, backoff_base=args.backoff_base)
    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=args.refresh_older_than)
        if args.refresh_older_than is not None
        else None
    )
    t0 = time.monotonic()
    summary: dict[str, Any] = {}
    try:
        # 1. league lists ------------------------------------------------------------
        latest = stores.leagues.latest_ok(key_fn=lambda r: (_to_int(r.get("id")), r.get("season")))
        todo = [
            lid for lid in args.leagues
            if needs_fetch(stores.leagues.path(league_key(lid, season)), latest.get((lid, season)), cutoff)
        ]
        print(f"[{_utc_now()}] leagues: {len(args.leagues)} requested, {len(todo)} to fetch", flush=True)
        summary["leagues"] = run_pool(
            todo, _make_handler("league", stores.leagues, fetcher, errors, state, stop, season),
            1, args.delay, stop, state, "leagues", progress_every=5, errors=errors, kind="league",
        )
        parsed_leagues = load_league_payloads(stores, args.leagues, season)
        for lp in parsed_leagues:
            if lp["selected_season"] != season:
                print(f"WARNING league {lp['league_id']}: selectedSeason={lp['selected_season']!r} != {season!r}",
                      flush=True)
        index = build_team_index(parsed_leagues)
        team_order = ordered_team_ids(index, args.leagues)
        if args.limit_teams:
            team_order = team_order[: args.limit_teams]

        # 2. squads -----------------------------------------------------------------
        if not stop.is_set():
            latest_t = stores.teams.latest_ok()
            todo = [t for t in team_order if needs_fetch(stores.teams.path(t), latest_t.get(t), cutoff)]
            n_dom = sum(1 for t in team_order if index[t]["group"] == "target_league")
            print(f"[{_utc_now()}] teams: {len(team_order)} clubs ({n_dom} in the 10 leagues, "
                  f"{len(team_order) - n_dom} European-cup-only), {len(todo)} to fetch", flush=True)
            summary["teams"] = run_pool(
                todo, _make_handler("team", stores.teams, fetcher, errors, state, stop, season),
                args.workers, args.delay, stop, state, "teams", progress_every=25, errors=errors, kind="team",
            )

        # 2b. fallback line-ups: clubs without a squad list and without lastLineupStats --------------
        # walk back through the club's finished matches (most recent first, at most 6) until one has a line-up
        if not stop.is_set():
            match_handler = _make_handler("match", stores.matches, fetcher, errors, state, stop, season)
            fb = Counter()
            for tid in team_order:
                data = stores.teams.load(tid)
                candidates = fallback_match_candidates(data) if valid_team(data) else []
                if not candidates:
                    continue
                fb["clubs"] += 1
                for mid in candidates:
                    if stop.is_set():
                        break
                    latest_m = stores.matches.latest_ok()
                    if needs_fetch(stores.matches.path(mid), latest_m.get(mid), cutoff):
                        fb["requests"] += 1
                        try:
                            match_handler(mid)
                        except Blocked as exc:
                            state.stop_reason = f"BLOCKED: {exc}"
                            stop.set()
                            print(f"[{_utc_now()}] STOP {state.stop_reason}", flush=True)
                            break
                        stop.wait(args.delay)
                    if has_lineup(stores.matches.load(mid), tid):
                        fb["clubs_with_lineup"] += 1
                        break
            print(f"[{_utc_now()}] fallback line-ups: {dict(fb)}", flush=True)
            summary["fallback_matches"] = dict(fb)

        # 3. players ----------------------------------------------------------------
        if not stop.is_set() and not args.teams_only:
            player_order, _ = squad_player_order(stores, team_order)
            if args.limit_players:
                player_order = player_order[: args.limit_players]
            latest_p = stores.players.latest_ok()
            todo = [p for p in player_order if needs_fetch(stores.players.path(p), latest_p.get(p), cutoff)]
            print(f"[{_utc_now()}] players: {len(player_order)} squad players, {len(todo)} to fetch", flush=True)
            summary["players"] = run_pool(
                todo, _make_handler("player", stores.players, fetcher, errors, state, stop, season),
                args.workers, args.delay, stop, state, "players", progress_every=100, errors=errors,
                kind="player",
            )
    finally:
        fetcher.close()
        stores.close()
        errors.close()

    el = time.monotonic() - t0
    print(f"[{_utc_now()}] fetch phase done in {el / 60:.1f} min, requests={fetcher.requests}, "
          f"limiter_retries={fetcher.limiter_retries}, errors logged={errors.count}, "
          f"summary={json.dumps(summary)}", flush=True)
    if state.stop_reason:
        print(f"[{_utc_now()}] RUN STOPPED: {state.stop_reason}", flush=True)
    if not args.no_build:
        stats = build_outputs(raw_root, out_dir, args.leagues, season)
        print(f"[{_utc_now()}] build: {json.dumps(stats)}", flush=True)
    return 2 if state.stop_reason and state.stop_reason.startswith("BLOCKED") else (1 if state.stop_reason else 0)


# --------------------------------------------------------------------------- building parsed files


TEAM_RESPONSE_FIELDS = (
    "short_name", "country", "primary_league_id", "primary_league_name", "latest_season", "coach", "coach_count",
    "squad_list_sent", "squad_player_count", "squad_other_members", "response_team_id", "roster_source",
    "fallback_roster_count",
)


class AtomicJsonl:
    """Write rows to a temp file, then replace the target in one step."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
        self.fh = self.tmp.open("w", encoding="utf-8", newline="\n")
        self.n = 0

    def write(self, row: dict) -> None:
        self.fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.n += 1

    def commit(self) -> None:
        self.fh.close()
        _replace_with_retry(self.tmp, self.path)

    def abort(self) -> None:
        try:
            self.fh.close()
        finally:
            try:
                self.tmp.unlink()
            except OSError:
                pass


def build_outputs(raw_root: Path, out_dir: Path, leagues: list[int], season: str) -> dict[str, Any]:
    """Rebuild every parsed file from the raw cache (no network). Players = current squad members."""
    stores = Stores(Path(raw_root))
    names = output_names(season)
    writers = {k: AtomicJsonl(Path(out_dir) / v) for k, v in names.items()}
    stats: Counter = Counter()
    try:
        parsed_leagues = load_league_payloads(stores, leagues, season)
        stats["leagues"] = len(parsed_leagues)
        index = build_team_index(parsed_leagues)
        team_order = ordered_team_ids(index, leagues)
        latest_t = stores.teams.latest_ok()
        match_latest = stores.matches.latest_ok()
        player_order: list[int] = []
        teams_of: dict[int, list[int]] = defaultdict(list)
        for tid in team_order:
            entry = index[tid]
            data = stores.teams.load(tid)
            snapshot = latest_t.get(tid)
            if data is not None and snapshot is None:
                latest_t = stores.teams.latest_ok()
                snapshot = latest_t.get(tid)
            if data is not None and snapshot is None:
                snapshot = stores.teams.mtime_iso(tid)
                stats["team_snapshot_from_mtime"] += 1
            competitions = [entry["competitions"][lid] for lid in leagues if lid in entry["competitions"]]
            row: dict[str, Any] = {
                "team_id": tid,
                "name": entry["name"],
                "group": entry["group"],
                "competitions": competitions,
                "competition_ids": [c["league_id"] for c in competitions],
                "team_response_available": False,
                # same keys for every club; null = no team response (unknown)
                **dict.fromkeys(TEAM_RESPONSE_FIELDS),
            }
            if valid_team(data):
                team, members = stores.team_roster(tid, data, snapshot, match_latest)
                row.update(team)
                row["name"] = team["name"] or entry["name"]
                row["team_response_available"] = True
                stats[f"roster_source_{team['roster_source']}"] += 1
                for m in members:
                    writers["squad_members"].write(m)
                    pid = m["player_id"]
                    if pid is None:
                        continue
                    if pid not in teams_of:
                        player_order.append(pid)
                    if tid not in teams_of[pid]:
                        teams_of[pid].append(tid)
                stats["teams_with_response"] += 1
                stats["squad_rows"] += len(members)
            else:
                stats["teams_without_response"] += 1
            row["snapshot_at"] = snapshot if row["team_response_available"] else None
            writers["teams"].write(row)
            stats["teams"] += 1

        latest_p = stores.players.latest_ok()
        for pid in player_order:
            data = stores.players.load(pid)
            if not valid_player(data):
                stats["players_missing"] += 1
                continue
            snapshot = latest_p.get(pid)
            if snapshot is None:  # stored after the manifest was read (a collector is running): re-read it
                latest_p = stores.players.latest_ok()
                snapshot = latest_p.get(pid)
            if snapshot is None:
                snapshot = stores.players.mtime_iso(pid)
                stats["player_snapshot_from_mtime"] += 1
            try:
                prow, recent, mvs, career = parse_player(data, pid, snapshot, teams_of.get(pid))
            except Exception as exc:  # keep going; report
                stats["player_parse_errors"] += 1
                print(f"parse error player {pid}: {exc!r}", flush=True)
                continue
            writers["players"].write(prow)
            for r in recent:
                writers["recent_matches"].write(r)
            for r in mvs:
                writers["market_values"].write(r)
            for r in career:
                writers["career"].write(r)
            stats["players"] += 1
        stats["squad_unique_players"] = len(player_order)
        for k, w in writers.items():
            stats[f"rows_{k}"] = w.n
    except BaseException:
        for w in writers.values():
            w.abort()
        raise
    for w in writers.values():
        w.commit()
    return dict(stats)


# --------------------------------------------------------------------------- coverage


def _pct(x: int, n: int) -> str:
    return f"{100.0 * x / n:.1f}%" if n else "-"


def coverage(raw_root: Path, out_dir: Path, leagues: list[int], season: str) -> str:
    names = output_names(season)
    out_dir = Path(out_dir)
    stores = Stores(Path(raw_root))
    parsed_leagues = {lp["league_id"]: lp for lp in load_league_payloads(stores, leagues, season)}
    teams = list(iter_jsonl(out_dir / names["teams"]))
    squad = list(iter_jsonl(out_dir / names["squad_members"]))
    players = {r["player_id"]: r for r in iter_jsonl(out_dir / names["players"])}
    recent_n: Counter = Counter(r["player_id"] for r in iter_jsonl(out_dir / names["recent_matches"]))
    mv_n: Counter = Counter(r["player_id"] for r in iter_jsonl(out_dir / names["market_values"]))
    career_n: Counter = Counter(r["player_id"] for r in iter_jsonl(out_dir / names["career"]))
    team_by_id = {t["team_id"]: t for t in teams}
    squad_by_team: dict[int, list[dict]] = defaultdict(list)
    for m in squad:
        squad_by_team[m["team_id"]].append(m)

    lines: list[str] = []
    lines.append(f"### Teams and players per competition (season {season})")
    lines.append("")
    lines.append("| FotMob id | Competition | selectedSeason | Table teams | Fixture teams | Clubs (union) | "
                 "Qualifying-only | Squad lists sent | Roster players | playerData parsed | Missing |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    tot = Counter()
    for lid in leagues:
        lp = parsed_leagues.get(lid)
        if lp is None:
            lines.append(f"| {lid} | {DOMESTIC_LEAGUES.get(lid) or EURO_CUPS.get(lid)} | (no league response) "
                         f"| - | - | - | - | - | - | - | - |")
            continue
        clubs = [t for t in teams if lid in (t.get("competition_ids") or [])]
        qual = sum(1 for t in clubs for c in t["competitions"] if c["league_id"] == lid and c.get("qualifying_only"))
        fetched = sum(1 for t in clubs if t.get("squad_list_sent"))
        sp = [m for t in clubs for m in squad_by_team.get(t["team_id"], [])]
        got = sum(1 for m in sp if m["player_id"] in players)
        lines.append(
            f"| {lid} | {lp['league_name']} | {lp['selected_season']} | {lp['table_team_count']} | "
            f"{lp['fixture_team_count']} | {len(clubs)} | {qual} | {fetched} | {len(sp)} | {got} | {len(sp) - got} |"
        )
    groups = Counter(t["group"] for t in teams)
    uniq_squad_players = {m["player_id"] for m in squad if m["player_id"] is not None}
    lines.append("")
    lines.append(
        f"Unique clubs: **{len(teams)}** ({groups.get('target_league', 0)} in the 10 leagues, "
        f"{groups.get('european_cup_only', 0)} European-cup-only); team responses: "
        f"**{sum(1 for t in teams if t.get('team_response_available'))}**; roster source per club: "
        f"{dict(Counter(t.get('roster_source') for t in teams))}; roster rows: **{len(squad)}** "
        f"({dict(Counter(m.get('roster_source') for m in squad))}); unique roster players: "
        f"**{len(uniq_squad_players)}**; playerData parsed: **{len(players)}**; missing: "
        f"**{len(uniq_squad_players - set(players))}**. Per-competition counts overlap (a club plays its league and a cup)."
    )

    # player field coverage
    def has(v: Any) -> bool:
        return v is not None and v != [] and v != {}

    def player_cov(pids: list[int]) -> dict[str, int]:
        c = Counter()
        for pid in pids:
            p = players.get(pid)
            if p is None:
                continue
            c["n"] += 1
            c["dob"] += has(p.get("birth_date"))
            c["foot"] += has(p.get("preferred_foot"))
            c["height"] += has(p.get("height_cm"))
            c["mv"] += has(p.get("market_value"))
            c["contract"] += has(p.get("contract_end"))
            c["country"] += has(p.get("country_code"))
            c["position"] += has(p.get("position_primary_key"))
            c["injury"] += has(p.get("injury_information"))
            c["intl"] += has(p.get("international_duty"))
            c["main_league"] += has((p.get("main_league") or {}).get("stats"))
            c["recent"] += recent_n.get(pid, 0) > 0
            c["mv_hist"] += mv_n.get(pid, 0) > 0
            c["career"] += career_n.get(pid, 0) > 0
            c["traits"] += has(p.get("traits"))
        return c

    lines.append("")
    lines.append("### playerData field coverage (share of parsed players where FotMob sends the value)")
    lines.append("")
    lines.append("| Scope | Players | Birth date | Foot | Height | Market value | Contract end | Country | Position | "
                 "Injury info (non-null) | Intl duty (non-null) | Main-league stats | Recent matches | MV history | "
                 "Career | Traits |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    scopes: list[tuple[str, list[int]]] = []
    for lid in leagues:
        pids = sorted({m["player_id"] for t in teams if lid in (t.get("competition_ids") or [])
                       for m in squad_by_team.get(t["team_id"], []) if m["player_id"] is not None})
        scopes.append((f"{lid} {parsed_leagues[lid]['league_name'] if lid in parsed_leagues else ''}", pids))
    scopes.append(("**All (unique)**", sorted(uniq_squad_players)))
    for label, pids in scopes:
        c = player_cov(pids)
        n = c["n"]
        lines.append(
            f"| {label} | {n} | {_pct(c['dob'], n)} | {_pct(c['foot'], n)} | {_pct(c['height'], n)} | "
            f"{_pct(c['mv'], n)} | {_pct(c['contract'], n)} | {_pct(c['country'], n)} | {_pct(c['position'], n)} | "
            f"{_pct(c['injury'], n)} | {_pct(c['intl'], n)} | {_pct(c['main_league'], n)} | {_pct(c['recent'], n)} | "
            f"{_pct(c['mv_hist'], n)} | {_pct(c['career'], n)} | {_pct(c['traits'], n)} |"
        )

    # squad snapshot coverage
    sc = Counter()
    squad_list_rows = [m for m in squad if m.get("roster_source") == "squad"]
    for m in squad_list_rows:
        sc["n"] += 1
        sc["dob"] += has(m.get("date_of_birth"))
        sc["height"] += has(m.get("height"))
        sc["tv"] += has(m.get("transfer_value"))
        sc["shirt"] += has(m.get("shirt_number"))
        sc["injured"] += m.get("injured") is True
        sc["injury"] += has(m.get("injury"))
        sc["rating"] += has(m.get("rating"))
    n = sc["n"]
    lines.append("")
    lines.append(
        f"Squad-list rows ({n}; fallback line-up rows excluded): date of birth {_pct(sc['dob'], n)}, height "
        f"{_pct(sc['height'], n)}, transfer value {_pct(sc['tv'], n)}, shirt {_pct(sc['shirt'], n)}, season rating "
        f"{_pct(sc['rating'], n)}, `injured: true` {sc['injured']} rows, non-null `injury` {sc['injury']} rows."
    )

    # injury agreement (two separate FotMob fields; reported, never reconciled). Fallback line-up
    # rows carry no squad injury field (unknown, not "not injured") and are left out.
    agree = Counter()
    disagreements: list[str] = []
    for m in squad_list_rows:
        p = players.get(m["player_id"])
        if p is None:
            continue
        sq = m.get("injured") is True or has(m.get("injury"))
        pl = has(p.get("injury_information"))
        agree[(sq, pl)] += 1
        if sq != pl and len(disagreements) < 40:
            disagreements.append(
                f"{m['player_id']} {m['name']} (team {m['team_id']}): squad injured={m.get('injured')} "
                f"injury={json.dumps(m.get('injury'), ensure_ascii=False)} | playerData injuryInformation="
                f"{(p.get('injury_key'), p.get('injury_expected_return_text'))}"
            )
    lines.append("")
    lines.append("### Squad injury flag vs playerData injuryInformation (separate FotMob fields, not reconciled)")
    lines.append("")
    lines.append("| Squad lists injury | playerData has injuryInformation | Squad rows |")
    lines.append("|---|---|---|")
    for (sq, pl), cnt in sorted(agree.items(), key=lambda kv: (not kv[0][0], not kv[0][1])):
        lines.append(f"| {'yes' if sq else 'no'} | {'yes' if pl else 'no'} | {cnt} |")
    if disagreements:
        lines.append("")
        lines.append(f"Disagreements ({sum(c for (a, b), c in agree.items() if a != b)} rows; first 40):")
        lines.append("")
        lines.extend(f"- {d}" for d in disagreements)

    # missing players
    missing = sorted(uniq_squad_players - set(players))
    lines.append("")
    lines.append(f"### Squad members without a parsed playerData ({len(missing)})")
    if missing:
        name_of = {m["player_id"]: (m["name"], m["team_id"]) for m in squad}
        lines.append("")
        for pid in missing[:100]:
            nm, tid = name_of.get(pid, (None, None))
            lines.append(f"- {pid} {nm} (team {tid} {team_by_id.get(tid, {}).get('name')})")

    # squad groups / roles observed
    pairs = Counter((m.get("squad_group"), m.get("role_key")) for m in squad_list_rows)
    lines.append("")
    lines.append("### Clubs without a FotMob squad list")
    lines.append("")
    for t in teams:
        if t.get("team_response_available") and not t.get("squad_list_sent"):
            roles = Counter(m.get("lineup_role") for m in squad_by_team.get(t["team_id"], []))
            matches = sorted({(m.get("lineup_match_id"), m.get("lineup_match_date"))
                              for m in squad_by_team.get(t["team_id"], [])} - {(None, None)}, key=str)
            lines.append(
                f"- {t['team_id']} {t.get('name')} ({', '.join(str(c) for c in t.get('competition_ids') or [])}): "
                f"roster_source={t.get('roster_source')}, fallback rows={t.get('fallback_roster_count')} "
                f"{dict(roles) if roles else ''} line-up match (id, date) {matches or '-'}"
            )
        elif not t.get("team_response_available"):
            lines.append(f"- {t['team_id']} {t.get('name')}: no team response")
    others = Counter((o.get("group"), o.get("role_key")) for t in teams for o in (t.get("squad_other_members") or []))
    lines.append("")
    lines.append("### Squad groups / role keys observed")
    lines.append("")
    lines.append("Players: " + ", ".join(f"{g}/{r}: {c}" for (g, r), c in sorted(pairs.items(), key=str)))
    lines.append("")
    lines.append("Non-player, non-coach members (not fetched): "
                 + (", ".join(f"{g}/{r}: {c}" for (g, r), c in sorted(others.items(), key=str)) or "none"))
    coach_counts = Counter(t.get("coach_count") for t in teams if t.get("squad_list_sent"))
    lines.append("")
    lines.append(f"Coach entries per squad: {dict(sorted(coach_counts.items(), key=str))}")

    ts_t = sorted(t["snapshot_at"] for t in teams if t.get("snapshot_at"))
    ts_p = sorted(p["snapshot_at"] for p in players.values() if p.get("snapshot_at"))
    lines.append("")
    if ts_t:
        lines.append(f"Team snapshots: {ts_t[0]} -> {ts_t[-1]}.")
    if ts_p:
        lines.append(f"Player snapshots: {ts_p[0]} -> {ts_p[-1]}.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- CLI


def _base_url() -> str:
    """Base URL from app settings (settings.fotmob_base_url), with a safe fallback."""
    try:
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))
        from app.config import settings  # type: ignore

        return str(settings.fotmob_base_url).rstrip("/")
    except Exception:
        return DEFAULT_BASE_URL


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--leagues", default=",".join(str(x) for x in TARGET13),
                    help="comma-separated FotMob league ids (default: TARGET13)")
    ap.add_argument("--season", default=DEFAULT_SEASON)
    ap.add_argument("--teams-only", action="store_true", help="league lists + squads only (no playerData)")
    ap.add_argument("--refresh-older-than", type=float, default=None, metavar="HOURS",
                    help="also re-fetch snapshots whose latest successful fetch is older than HOURS")
    ap.add_argument("--from-raw", action="store_true", help="rebuild the parsed files from the raw cache (no network)")
    ap.add_argument("--coverage", action="store_true", help="print markdown coverage tables and exit")
    ap.add_argument("--no-build", action="store_true", help="fetch only; do not rebuild the parsed files")
    ap.add_argument("--workers", type=int, default=2, help="concurrent workers, clamped to 1..2")
    ap.add_argument("--delay", type=float, default=0.5, help="seconds between two requests of one worker (min 0.5)")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--max-retries", type=int, default=4)
    ap.add_argument("--max-consecutive-failures", type=int, default=8)
    ap.add_argument("--max-minutes", type=float, default=0, help="stop starting new requests after N minutes")
    ap.add_argument("--limit-teams", type=int, default=0, help="testing: only the first N clubs")
    ap.add_argument("--limit-players", type=int, default=0, help="testing: only the first N players")
    ap.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    ap.add_argument("--base-url", default=None, help="default: settings.fotmob_base_url")
    args = ap.parse_args(argv)
    args.leagues = [int(x) for x in str(args.leagues).split(",") if x.strip()]
    args.workers = max(1, min(2, args.workers))
    args.delay = max(0.5, args.delay)
    args.backoff_base = 2.0
    if args.base_url is None:
        args.base_url = _base_url()
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    args = parse_args(argv)
    if args.coverage:
        print(coverage(Path(args.raw_root), Path(args.out_dir), args.leagues, args.season))
        return 0
    if args.from_raw:
        stats = build_outputs(Path(args.raw_root), Path(args.out_dir), args.leagues, args.season)
        print(json.dumps(stats, indent=1))
        return 0
    with CollectorLock(Path(args.raw_root) / LOCK_NAME):
        return collect(args)


if __name__ == "__main__":
    sys.exit(main())
