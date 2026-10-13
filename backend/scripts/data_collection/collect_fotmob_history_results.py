"""Collect FotMob results history before the production DB starts (2021-07-01 .. 2025-06-30).

TRAINING DATA COLLECTOR - source: FotMob unofficial API
``GET /api/data/leagues?id=<league>&season=<season>`` -> ``fixtures.allMatches`` (ONE request per
competition-season). Every response body is cached untouched (gzip, temp file + os.replace) at
``backend/data/raw_cache/fotmob_leagues/<league>_<season with "/" -> "-">.json.gz``. Other collectors
share that folder: an existing file is reused instead of fetched.

Scope
  1. TARGET13 (Premier League 47, LaLiga 87, Serie A 55, Bundesliga 54, Ligue 1 53, Eredivisie 57,
     Liga Portugal 61, Belgian Pro League 40, Super Lig 71, Czech 1. Liga 122, Champions League 42,
     Europa League 73, Conference League 10216).
  2. Context competitions: every production-DB competition (club friendlies, youth/U-xx, women's,
     reserve/B-team, futsal and exhibition competitions excluded by name) in which teams that appear in
     TARGET13 matches (production DB or the TARGET13 history of step 1) played >= 3 FINISHED
     production-DB matches, plus the second tiers of the 10 target countries (always).
  Seasons: every season of ``allAvailableSeasons`` overlapping 2021-07-01 .. 2025-06-30, i.e. "2021" ..
  "2025" (calendar-year leagues) and "2021/2022" .. "2024/2025" (split-year leagues) ("core"), plus the
  split-year "boundary" season "2025/2026" (some competitions start before July; its later matches are
  kept apart in ``matches_after_cutoff`` for cross-checks against the production DB), plus a "prewindow"
  season when the earliest core kickoff is after 2021-09-30 (FotMob labels super cups with shifted
  seasons: the January 2022 Supercopa is "2020/2021"; only its matches from 2021-07-01 on are kept).
  Only matches with kickoff < 2025-07-01T00:00:00Z go to the ``matches`` table.

Politeness: 1 worker, >= 0.6 s between this collector's requests, plus the shared cross-process limiter
(``fotmob_rate.acquire()``) before EVERY request. HTTP 429 -> ``fotmob_rate.report_429(Retry-After or 60)``
and back off; HTTP 403 or an HTML / captcha / challenge page -> the run STOPS (never work around bot
protection). ``--max-requests`` caps one run.

Honesty (AGENTS.md 8-14): nothing is invented. Scores are parsed from ``status.scoreStr`` only for
matches FotMob marks finished (awarded results included and flagged); every other score is NULL. A
season name FotMob does not know silently returns the latest season, so every response is checked
against ``details.selectedSeason`` and a mismatching body is never cached under the requested name.

Usage (from backend/):
  venv/Scripts/python.exe scripts/data_collection/collect_fotmob_history_results.py --dry-run
  venv/Scripts/python.exe scripts/data_collection/collect_fotmob_history_results.py            # collect + build
  venv/Scripts/python.exe scripts/data_collection/collect_fotmob_history_results.py --from-raw # rebuild, no network
  venv/Scripts/python.exe scripts/data_collection/collect_fotmob_history_results.py --coverage
  venv/Scripts/python.exe scripts/data_collection/collect_fotmob_history_results.py --spot-check 10
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import random
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fotmob_rate  # noqa: E402  (shared cross-process FotMob limiter)

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_PROD_DB = BACKEND_DIR / "football_intelligence.db"
RAW_DIR = BACKEND_DIR / "data" / "raw_cache" / "fotmob_leagues"
HISTORY_DIR = BACKEND_DIR / "data" / "history"
PROBE_DIR = HISTORY_DIR / "raw_probe"
SPOT_DIR = HISTORY_DIR / "raw_spotcheck"
DEFAULT_OUT_DB = HISTORY_DIR / "history_results.db"
SELECTION_CSV = HISTORY_DIR / "competition_selection.csv"
FETCH_LOG = HISTORY_DIR / "fetch_log.jsonl"

BASE_URL = "https://www.fotmob.com"
LEAGUES_ENDPOINT = "/api/data/leagues"
DETAILS_ENDPOINT = "/api/data/matchDetails"
# Same User-Agent as collect_fotmob_details.py
HEADERS = {"User-Agent": "Mozilla/5.0 (TUTAR X research collector; low-rate)", "Accept": "application/json"}
MIN_SPACING_S = 0.6
CUTOFF = "2025-07-01T00:00:00Z"
WINDOW_START = "2021-07-01T00:00:00Z"
PREWINDOW_TRIGGER = "2021-09-30T23:59:59Z"
SOURCE = "fotmob_league_fixtures"
SOURCE_BRACKET = "fotmob_league_playoff_bracket"
DISCOVERY_GUESS = "2024/2025"

TARGET13: dict[int, str] = {
    47: "Premier League",
    87: "LaLiga",
    55: "Serie A",
    54: "Bundesliga",
    53: "Ligue 1",
    57: "Eredivisie",
    61: "Liga Portugal",
    40: "Belgian Pro League",
    71: "Super Lig",
    122: "Czech 1. Liga",
    42: "Champions League",
    73: "Europa League",
    10216: "Conference League",
}
TARGET13_SEASONS = ["2021/2022", "2022/2023", "2023/2024", "2024/2025", "2025/2026"]

# Second tiers of the 10 target countries: FotMob league id -> (expected details.country, label).
# Ids found in the production DB by name (DB names are FotMob stage names, e.g. "Championship Playoff");
# the country is verified against the API response (details.country) at build time.
SECOND_TIERS: dict[int, tuple[str, str]] = {
    48: ("ENG", "Championship"),
    140: ("ESP", "LaLiga2"),
    86: ("ITA", "Serie B"),
    146: ("GER", "2. Bundesliga"),
    110: ("FRA", "Ligue 2"),
    111: ("NED", "Eerste Divisie"),
    185: ("POR", "Liga Portugal 2"),
    264: ("BEL", "Challenger Pro League"),
    165: ("TUR", "1. Lig"),
    253: ("CZE", "FNL"),
}
MIN_CONNECTED_MATCHES = 3

# Name rules for competitions that are out of scope whatever their team overlap (first match wins).
EXCLUDE_RULES: list[tuple[re.Pattern[str], str]] = [
    # "The Atlantic Cup" is a pre-season friendly tournament (Algarve, January/February)
    (re.compile(r"friendl|atlantic cup", re.I), "club friendlies / friendlies"),
    (re.compile(r"futsal|beach", re.I), "futsal / beach soccer"),
    (re.compile(r"\bu-?\d{2}\b|youth|junior|revela", re.I), "youth / U-xx"),
    (
        re.compile(
            r"women|femen|femin|femm|f.minin|frauen|vrouwen|kvinner|damallsvenskan|toppserien|elitettan|\bwsl\b|nwsl"
            r"|\bliga f\b|\bwe league|swpl|\bswf\b|copa de la reina|premiere ligue|kansallinen liiga"
            r"|shebelieves|concacaf w ",
            re.I,
        ),
        "women's",
    ),
    (re.compile(r"premier league 2\b|next pro|reserve|\bb team", re.I), "reserve / B teams"),
    (
        re.compile(r"baller league|soccer aid|charity|legends|all-star|choose one|sidemen", re.I),
        "exhibition / non-competitive",
    ),
]

_CAL_RE = re.compile(r"^(\d{4})$")
_SPLIT_RE = re.compile(r"^(\d{4})/(\d{4})$")
_SCORE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


# --------------------------------------------------------------------------- small helpers


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _flag(value: Any) -> int | None:
    """FotMob boolean -> 1/0; None when the key is missing or not a boolean."""
    return int(value) if isinstance(value, bool) else None


def season_file_name(league: int, season: str) -> str:
    return f"{league}_{season.replace('/', '-')}.json.gz"


def cache_path(league: int, season: str, raw_dir: Path = RAW_DIR) -> Path:
    return raw_dir / season_file_name(league, season)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def atomic_write_gzip(path: Path, raw: bytes) -> None:
    atomic_write_bytes(path, gzip.compress(raw, compresslevel=6))


def load_gzip_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(gzip.decompress(path.read_bytes()))
    except (OSError, EOFError, ValueError):
        return None


def normalise_utc(value: Any) -> str | None:
    """'2023-07-28T18:45:00Z' / '2024-02-20T20:00:00.000Z' -> '2023-07-28T18:45:00Z'."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_score(score_str: Any) -> tuple[int | None, int | None]:
    m = _SCORE_RE.match(score_str) if isinstance(score_str, str) else None
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def season_role(name: str) -> str | None:
    """'core' when the season overlaps 2021-07-01..2025-06-30, 'boundary' for the split season that
    starts in 2025 (only its pre-cutoff matches belong to the window), None otherwise."""
    m = _CAL_RE.match(name)
    if m:
        year = int(m.group(1))
        return "core" if 2021 <= year <= 2025 else None
    m = _SPLIT_RE.match(name)
    if m:
        y1, y2 = int(m.group(1)), int(m.group(2))
        if y2 != y1 + 1:
            return None
        if 2021 <= y1 <= 2024:
            return "core"
        if y1 == 2025:
            return "boundary"
    return None


def classify_seasons(all_seasons: list[str]) -> tuple[list[tuple[str, str]], list[str]]:
    """-> ([(season, role)], unrecognised season names). Order: oldest first."""
    targets: list[tuple[str, str]] = []
    unrecognised: list[str] = []
    for s in all_seasons or []:
        if not isinstance(s, str):
            continue
        role = season_role(s)
        if role:
            targets.append((s, role))
        elif not (_CAL_RE.match(s) or _SPLIT_RE.match(s)):
            unrecognised.append(s)
    targets.sort(key=lambda t: t[0])
    return targets, unrecognised


def previous_season_name(name: str) -> str | None:
    m = _CAL_RE.match(name)
    if m:
        return str(int(m.group(1)) - 1)
    m = _SPLIT_RE.match(name)
    if m:
        return f"{int(m.group(1)) - 1}/{int(m.group(2)) - 1}"
    return None


def earliest_kickoff(league: int, seasons: list[str], raw_dir: Path = RAW_DIR) -> str | None:
    """Earliest kickoff over the cached files of the given seasons (None when none is cached)."""
    first: str | None = None
    for season in seasons:
        path = cache_path(league, season, raw_dir)
        data = load_gzip_json(path) if path.exists() else None
        if data is None or response_problem(data, league, season):
            continue
        for m in (data.get("fixtures") or {}).get("allMatches") or []:
            k = normalise_utc((m.get("status") or {}).get("utcTime"))
            if k and (first is None or k < first):
                first = k
    return first


def prewindow_season(league: int, all_seasons: list[str], core: list[str], raw_dir: Path = RAW_DIR) -> str | None:
    """FotMob labels some competitions with shifted seasons (e.g. the Spanish Super Cup played in January
    2022 is season "2020/2021"). When the earliest core-season kickoff is later than PREWINDOW_TRIGGER, the
    season before the earliest core season is also a target (role "prewindow"); only its matches with
    kickoff in [WINDOW_START, CUTOFF) are kept. Returns that season name if FotMob lists it."""
    if not core:
        return None
    first = earliest_kickoff(league, core, raw_dir)
    if first is None or first <= PREWINDOW_TRIGGER:
        return None
    prev = previous_season_name(min(core))
    return prev if prev in (all_seasons or []) else None


def derive_status(st: dict[str, Any]) -> str:
    """Status from FotMob's flags (and reason keys for postponed / abandoned)."""
    reason = st.get("reason") or {}
    long_key = str(reason.get("longKey") or "").lower()
    short = str(reason.get("short") or "").lower()
    abandoned = "abandon" in long_key or "abort" in long_key or short == "ab"
    postponed = "postpon" in long_key or short == "pp"
    if st.get("cancelled") is True:
        if postponed:
            return "POSTPONED"
        if abandoned:  # FotMob: finished=true, cancelled=true, reason Ab / aborted
            return "ABANDONED"
        return "CANCELLED"
    if st.get("awarded") is True:
        return "AWARDED"
    if abandoned:
        return "ABANDONED"
    if st.get("finished") is True:
        return "FINISHED"
    if postponed:
        return "POSTPONED"
    if st.get("started") is True:
        return "STARTED_NOT_FINISHED"
    return "NOT_PLAYED"


def exclusion_reason(name: str) -> str | None:
    for pattern, label in EXCLUDE_RULES:
        if pattern.search(name or ""):
            return label
    return None


# --------------------------------------------------------------------------- parsing


def _match_row(
    mid: Any, home: dict[str, Any], away: dict[str, Any], st: dict[str, Any], league: int, season: str,
    round_: Any, round_name: Any, source: str,
) -> dict[str, Any] | None:
    match_id = _to_int(mid)
    if match_id is None:
        return None
    status = derive_status(st)
    # FotMob marks abandoned matches finished=true AND cancelled=true and keeps the score at the moment of
    # abandonment in scoreStr: that is not a result, so a score is kept only for FINISHED / AWARDED.
    has_result = status in ("FINISHED", "AWARDED") and st.get("finished") is True
    score_str = st.get("scoreStr")
    hs, as_ = parse_score(score_str) if has_result else (None, None)
    reason = st.get("reason") or {}
    return {
        "provider_id": match_id,
        "competition_provider_id": league,
        "season": season,
        "round": None if round_ is None else str(round_),
        "round_name": None if round_name is None else str(round_name),
        "scheduled_at": normalise_utc(st.get("utcTime")),
        "home_team_provider_id": _to_int(home.get("id")),
        "away_team_provider_id": _to_int(away.get("id")),
        "home_team_name": home.get("name"),
        "away_team_name": away.get("name"),
        "home_score": hs,
        "away_score": as_,
        "status": status,
        "status_reason": reason.get("short") or None,
        "status_reason_key": reason.get("longKey") or None,
        "finished": _flag(st.get("finished")),
        "started": _flag(st.get("started")),
        "cancelled": _flag(st.get("cancelled")),
        "awarded": _flag(st.get("awarded")),
        "score_str": score_str if isinstance(score_str, str) else None,
        "score_unparsed": int(has_result and hs is None),
        "source": source,
    }


def parse_season(data: dict[str, Any], league: int, season: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """All matches of one competition-season response: fixtures.allMatches, plus any playoff-bracket
    match missing from allMatches (counted separately; none were seen when this was written)."""
    rows: list[dict[str, Any]] = []
    stats: Counter = Counter()
    all_matches = ((data.get("fixtures") or {}).get("allMatches")) or []
    seen: set[int] = set()
    for m in all_matches:
        row = _match_row(
            m.get("id"), m.get("home") or {}, m.get("away") or {}, m.get("status") or {}, league, season,
            m.get("round"), m.get("roundName"), SOURCE,
        )
        if row is None:
            stats["rejected_no_id"] += 1
            continue
        if row["provider_id"] in seen:
            stats["repeated_in_all_matches"] += 1
            continue
        seen.add(row["provider_id"])
        rows.append(row)
    stats["n_source"] = len(all_matches)

    playoff = data.get("playoff")
    if isinstance(playoff, dict):
        for rnd in playoff.get("rounds") or []:
            for mu in rnd.get("matchups") or []:
                for m in mu.get("matches") or []:
                    mid = _to_int(m.get("matchId"))
                    if mid is None or mid in seen:
                        continue
                    row = _match_row(
                        mid, m.get("home") or {}, m.get("away") or {}, m.get("status") or {}, league, season,
                        rnd.get("stage"), rnd.get("stage"), SOURCE_BRACKET,
                    )
                    if row is not None:
                        seen.add(mid)
                        rows.append(row)
                        stats["bracket_only"] += 1
    return rows, dict(stats)


def response_problem(data: Any, league: int, season: str | None) -> str | None:
    """None when ``data`` is the requested league-season, else a short reason."""
    if not isinstance(data, dict):
        return "not_an_object"
    details = data.get("details")
    if not isinstance(details, dict):
        return "no_details"
    if _to_int(details.get("id")) != league:
        return f"league_mismatch:{details.get('id')}"
    if season is not None and details.get("selectedSeason") != season:
        return f"season_mismatch:{details.get('selectedSeason')}"
    if not isinstance(data.get("fixtures"), dict):
        return "no_fixtures"
    return None


# --------------------------------------------------------------------------- HTTP


class StopCollection(Exception):
    """Bot protection, repeated 429s, request cap or repeated failures: stop the whole run."""


def acquire_slot() -> None:
    """fotmob_rate.acquire(), tolerating a Windows race in the shared limiter: os.mkdir of the lock
    directory raises PermissionError (not FileExistsError) while another process is removing it."""
    for _ in range(500):
        try:
            fotmob_rate.acquire()
            return
        except PermissionError:
            time.sleep(0.01 + random.random() * 0.03)
    raise StopCollection("shared limiter lock kept failing with PermissionError")


def report_429_safe(seconds: float) -> None:
    for _ in range(500):
        try:
            fotmob_rate.report_429(seconds)
            return
        except PermissionError:
            time.sleep(0.01 + random.random() * 0.03)
    raise StopCollection("could not record the 429 cool-down in the shared limiter")


def _log(event: dict[str, Any]) -> None:
    event = {"at": _utc_now(), **event}
    FETCH_LOG.parent.mkdir(parents=True, exist_ok=True)
    with FETCH_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


class Fetcher:
    """One worker; >= MIN_SPACING_S between requests; shared limiter before every request."""

    def __init__(self, base_url: str, timeout: float, max_requests: int, max_consecutive_failures: int = 5):
        self.client = httpx.Client(
            base_url=base_url, timeout=httpx.Timeout(timeout), headers=HEADERS, follow_redirects=True
        )
        self.max_requests = max_requests
        self.max_consecutive_failures = max_consecutive_failures
        self.n_requests = 0
        self.consecutive_failures = 0
        self.bad_payloads = 0
        self._last = 0.0

    def close(self) -> None:
        self.client.close()

    def note_payload(self, problem: str | None) -> None:
        """Count consecutive JSON answers that are not league payloads at all (possible soft block)."""
        structural = problem in ("not_an_object", "no_details")
        self.bad_payloads = self.bad_payloads + 1 if structural else 0
        if self.bad_payloads >= 3:
            raise StopCollection(f"3 consecutive unexpected JSON payloads (last: {problem})")

    def _pace(self) -> None:
        if self.n_requests >= self.max_requests:
            raise StopCollection(f"request cap reached ({self.max_requests})")
        wait = MIN_SPACING_S - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        acquire_slot()
        self._last = time.monotonic()
        self.n_requests += 1

    def get_json(self, endpoint: str, params: dict[str, Any], max_attempts: int = 4) -> tuple[Any, bytes | None, str | None]:
        """-> (json, raw body, error kind). Raises StopCollection on bot protection / repeated 429."""
        n_429 = 0
        last_error = "unknown"
        for attempt in range(1, max_attempts + 1):
            self._pace()
            t0 = time.monotonic()
            try:
                resp = self.client.get(endpoint, params=params)
            except httpx.TimeoutException as exc:
                last_error = f"timeout:{type(exc).__name__}"
            except httpx.RequestError as exc:
                last_error = f"connection_error:{type(exc).__name__}"
            else:
                status = resp.status_code
                ctype = resp.headers.get("content-type", "")
                head = resp.content[:4000].lower()
                _log({"endpoint": endpoint, "params": params, "status": status, "bytes": len(resp.content),
                      "elapsed_s": round(time.monotonic() - t0, 2), "attempt": attempt})
                if status == 429:
                    n_429 += 1
                    retry_after = _to_float(resp.headers.get("Retry-After")) or 60.0
                    report_429_safe(retry_after)
                    print(f"  HTTP 429 (Retry-After={resp.headers.get('Retry-After')}), cooling down {retry_after:.0f}s", flush=True)
                    if n_429 >= 3:
                        raise StopCollection("HTTP 429 three times for one request")
                    time.sleep(min(retry_after, 600.0))
                    last_error = "http_429"
                    continue
                if status == 403:
                    raise StopCollection(f"HTTP 403 from {resp.url}: {resp.text[:200]!r}")
                # Only a non-JSON body can be a challenge page: league names such as "Challenger Pro
                # League" legitimately contain the word inside JSON.
                starts_json = resp.content.lstrip()[:1] in (b"{", b"[")
                if not starts_json and (head.lstrip().startswith(b"<") or b"<html" in head
                                        or b"captcha" in head or b"challenge" in head):
                    raise StopCollection(f"HTML / captcha / challenge page from {resp.url} (HTTP {status}, {ctype})")
                if starts_json and b"captcha" in head:
                    raise StopCollection(f"captcha mentioned in a JSON body from {resp.url} (HTTP {status})")
                if status == 404:
                    self.consecutive_failures = 0
                    return None, None, "http_404"
                if 500 <= status < 600:
                    last_error = f"http_{status}"
                elif status != 200:
                    self.consecutive_failures = 0
                    return None, None, f"http_{status}"
                else:
                    try:
                        data = resp.json()
                    except ValueError:
                        last_error = "invalid_json"
                    else:
                        self.consecutive_failures = 0
                        return data, resp.content, None
            if attempt < max_attempts:
                time.sleep(min(2.0 ** attempt, 30.0) + random.uniform(0.0, 1.0))
        self.consecutive_failures += 1
        _log({"endpoint": endpoint, "params": params, "error": last_error, "attempts": max_attempts})
        if self.consecutive_failures >= self.max_consecutive_failures:
            raise StopCollection(f"{self.consecutive_failures} consecutive failed requests (last: {last_error})")
        return None, None, last_error


# --------------------------------------------------------------------------- season discovery / fetching


def known_league_info(league: int, raw_dir: Path = RAW_DIR, probe_dir: Path = PROBE_DIR) -> tuple[list[str] | None, dict[str, Any] | None, str | None]:
    """(allAvailableSeasons, details, file name) from any cached response of this league."""
    candidates = sorted(raw_dir.glob(f"{league}_*.json.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    candidates += sorted(probe_dir.glob(f"{league}__*.json.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        data = load_gzip_json(path)
        if data is None or response_problem(data, league, None):
            continue
        seasons = data.get("allAvailableSeasons")
        if isinstance(seasons, list) and seasons:
            return [s for s in seasons if isinstance(s, str)], data.get("details") or {}, path.name
    return None, None, None


def _valid_cached(path: Path, league: int, season: str) -> bool:
    data = load_gzip_json(path) if path.exists() else None
    return data is not None and response_problem(data, league, season) is None


def fetch_season(fetcher: Fetcher, league: int, season: str, stats: Counter) -> str:
    """Make sure the raw file of one league-season exists. -> outcome label."""
    path = cache_path(league, season)
    if path.exists():
        if _valid_cached(path, league, season):
            stats["reused"] += 1
            return "reused"
        _log({"league": league, "season": season, "event": "cached_file_invalid", "file": path.name})
    data, raw, err = fetcher.get_json(LEAGUES_ENDPOINT, {"id": league, "season": season})
    if data is None:
        stats["error"] += 1
        _log({"league": league, "season": season, "event": "fetch_failed", "error": err})
        return f"error:{err}"
    problem = response_problem(data, league, season)
    fetcher.note_payload(problem)
    if problem:
        got = (data.get("details") or {}).get("selectedSeason") if isinstance(data, dict) else None
        name = f"{league}__requested-{season.replace('/', '-')}__got-{str(got).replace('/', '-')}.json.gz"
        atomic_write_gzip(PROBE_DIR / name, raw or b"")
        stats["mismatch"] += 1
        _log({"league": league, "season": season, "event": "response_mismatch", "problem": problem, "file": name})
        return f"mismatch:{problem}"
    atomic_write_gzip(path, raw or b"")
    stats["fetched"] += 1
    return "fetched"


def discover_league(fetcher: Fetcher | None, league: int, stats: Counter) -> tuple[list[str] | None, dict[str, Any] | None]:
    """allAvailableSeasons of a league: from the cache, else one request for DISCOVERY_GUESS (a valid
    answer is cached as that season; a fallback answer is kept in PROBE_DIR for traceability)."""
    seasons, details, _ = known_league_info(league)
    if seasons is not None or fetcher is None:
        return seasons, details
    data, raw, err = fetcher.get_json(LEAGUES_ENDPOINT, {"id": league, "season": DISCOVERY_GUESS})
    if data is None:
        stats["error"] += 1
        _log({"league": league, "event": "discovery_failed", "error": err})
        return None, None
    problem = response_problem(data, league, DISCOVERY_GUESS)
    fetcher.note_payload(problem)
    if problem is None:
        atomic_write_gzip(cache_path(league, DISCOVERY_GUESS), raw or b"")
        stats["fetched"] += 1
    elif problem.startswith("season_mismatch"):
        got = (data.get("details") or {}).get("selectedSeason")
        name = f"{league}__requested-{DISCOVERY_GUESS.replace('/', '-')}__got-{str(got).replace('/', '-')}.json.gz"
        atomic_write_gzip(PROBE_DIR / name, raw or b"")
        stats["probe"] += 1
        _log({"league": league, "event": "discovery_fallback", "got": got, "file": name})
    else:
        stats["error"] += 1
        _log({"league": league, "event": "discovery_bad_payload", "problem": problem})
        return None, None
    seasons = [s for s in (data.get("allAvailableSeasons") or []) if isinstance(s, str)]
    return seasons, data.get("details") or {}


def collect_league(fetcher: Fetcher, league: int, stats: Counter, seasons_override: list[str] | None = None) -> None:
    seasons, details = discover_league(fetcher, league, stats)
    if seasons is None:
        print(f"  [{league}] no league data (see fetch_log)", flush=True)
        return
    targets, unrecognised = classify_seasons(seasons)
    if seasons_override is not None:
        targets = [(s, season_role(s) or "core") for s in seasons_override if s in seasons]
    if unrecognised:
        _log({"league": league, "event": "unrecognised_season_names", "names": unrecognised})
    outcomes = []
    for season, _role in targets:
        outcomes.append(f"{season}:{fetch_season(fetcher, league, season, stats)}")
    pre = prewindow_season(league, seasons, [s for s, r in targets if r == "core"])
    if pre:
        outcomes.append(f"{pre}(prewindow):{fetch_season(fetcher, league, pre, stats)}")
    name = (details or {}).get("name")
    print(f"  [{league}] {name} ({(details or {}).get('country')}): {', '.join(outcomes) or 'no target seasons'}"
          f" | requests so far {fetcher.n_requests}", flush=True)


# --------------------------------------------------------------------------- selection


def _prod_conn(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=30)


def target13_history_teams(raw_dir: Path = RAW_DIR) -> tuple[set[int], list[str]]:
    """Team ids in kept (kickoff < cutoff) TARGET13 history matches of the cached season files."""
    teams: set[int] = set()
    missing: list[str] = []
    for league in TARGET13:
        for season in TARGET13_SEASONS:
            path = cache_path(league, season, raw_dir)
            data = load_gzip_json(path) if path.exists() else None
            if data is None or response_problem(data, league, season):
                missing.append(f"{league}_{season}")
                continue
            rows, _ = parse_season(data, league, season)
            for r in rows:
                if r["scheduled_at"] and r["scheduled_at"] < CUTOFF:
                    for t in (r["home_team_provider_id"], r["away_team_provider_id"]):
                        if t is not None:
                            teams.add(t)
    return teams, missing


def select_competitions(prod_db: Path, hist_teams: set[int], include: list[int] | None = None) -> list[dict[str, Any]]:
    """Decision for every production-DB competition (+ forced ones). TARGET13 rows first."""
    conn = _prod_conn(prod_db)
    try:
        comps = {int(r[0]): r[1] for r in conn.execute("SELECT provider_id, name FROM competitions")
                 if str(r[0]).lstrip("-").isdigit()}
        t13 = [str(c) for c in TARGET13]
        q = (
            "SELECT DISTINCT t.provider_id FROM matches m JOIN competitions co ON co.id = m.competition_id "
            "JOIN teams t ON t.id IN (m.home_team_id, m.away_team_id) "
            f"WHERE m.status = 'FINISHED' AND co.provider_id IN ({','.join('?' * len(t13))})"
        )
        prod_teams = {str(r[0]) for r in conn.execute(q, t13)}
        connected = prod_teams | {str(t) for t in hist_teams}
        counts: dict[int, list[Any]] = defaultdict(lambda: [0, 0, set()])
        for comp, home, away in conn.execute(
            "SELECT co.provider_id, ht.provider_id, at.provider_id FROM matches m "
            "JOIN competitions co ON co.id = m.competition_id JOIN teams ht ON ht.id = m.home_team_id "
            "JOIN teams at ON at.id = m.away_team_id WHERE m.status = 'FINISHED'"
        ):
            cid = _to_int(comp)
            if cid is None:
                continue
            c = counts[cid]
            c[0] += 1
            hit = [t for t in (str(home), str(away)) if t in connected]
            if hit:
                c[1] += 1
                c[2].update(hit)
    finally:
        conn.close()

    include = include or []
    out: list[dict[str, Any]] = []
    for cid in sorted(set(comps) | set(TARGET13) | set(SECOND_TIERS) | set(include)):
        n_db, n_conn, teams = counts.get(cid, [0, 0, set()])
        row = {
            "provider_id": cid,
            "db_name": comps.get(cid),
            "n_db_finished": n_db,
            "n_db_connected": n_conn,
            "n_connected_teams": len(teams),
        }
        excl = exclusion_reason(comps.get(cid) or "")
        if cid in TARGET13:
            kind = "UEFA club competition" if cid in (42, 73, 10216) else "top-10 UEFA association league"
            row.update(decision="included", group="TARGET13", reason=f"TARGET13 ({kind})")
        elif cid in SECOND_TIERS:
            cc, label = SECOND_TIERS[cid]
            row.update(decision="included", group="second_tier",
                       reason=f"second tier of {cc} ({label}), always included; {n_conn} of {n_db} production-DB "
                              f"FINISHED matches involve TARGET13-connected teams ({len(teams)} teams)")
        elif cid in include:
            row.update(decision="included", group="forced", reason="forced with --include")
        elif excl:
            row.update(decision="excluded", group="", reason=f"excluded by name rule: {excl}")
        elif n_conn >= MIN_CONNECTED_MATCHES:
            row.update(decision="included", group="context",
                       reason=f"{n_conn} of {n_db} production-DB FINISHED matches involve TARGET13-connected "
                              f"teams ({len(teams)} teams) >= {MIN_CONNECTED_MATCHES}")
        else:
            row.update(decision="excluded", group="",
                       reason=f"only {n_conn} production-DB FINISHED matches involve TARGET13-connected teams "
                              f"(< {MIN_CONNECTED_MATCHES})")
        out.append(row)
    rank = {"TARGET13": 0, "second_tier": 1, "forced": 2, "context": 3, "": 4}
    out.sort(key=lambda r: (rank[r["group"]], -r["n_db_connected"], r["provider_id"]))
    return out


def write_selection_csv(selection: list[dict[str, Any]], path: Path = SELECTION_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["provider_id", "db_name", "fotmob_name", "country", "decision", "group", "reason",
            "n_db_finished", "n_db_connected", "n_connected_teams"]
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for row in selection:
            seasons, details, _ = known_league_info(row["provider_id"])
            w.writerow({**row, "fotmob_name": (details or {}).get("name"), "country": (details or {}).get("country")})
    os.replace(tmp, path)


# --------------------------------------------------------------------------- DB build

SCHEMA = """
CREATE TABLE competitions (
    provider_id INTEGER PRIMARY KEY,
    name TEXT,
    country TEXT,
    reason_included TEXT NOT NULL,
    selection_group TEXT NOT NULL,
    db_name TEXT,
    fotmob_type TEXT,
    n_db_finished INTEGER,
    n_db_connected INTEGER,
    n_connected_teams INTEGER,
    all_available_seasons TEXT,
    unrecognised_seasons TEXT,
    note TEXT
);
CREATE TABLE competition_selection (
    provider_id INTEGER PRIMARY KEY,
    db_name TEXT,
    decision TEXT NOT NULL,
    selection_group TEXT,
    reason TEXT NOT NULL,
    n_db_finished INTEGER,
    n_db_connected INTEGER,
    n_connected_teams INTEGER
);
CREATE TABLE seasons (
    competition_provider_id INTEGER NOT NULL,
    season TEXT NOT NULL,
    season_role TEXT NOT NULL,
    fetch_status TEXT NOT NULL,
    n_matches INTEGER,
    n_source INTEGER,
    n_after_cutoff INTEGER,
    n_before_window INTEGER,
    n_finished INTEGER,
    n_awarded INTEGER,
    n_abandoned INTEGER,
    n_cancelled INTEGER,
    n_postponed INTEGER,
    n_other_status INTEGER,
    n_bracket_only INTEGER,
    n_duplicate_ids INTEGER,
    n_no_kickoff INTEGER,
    n_score_unparsed INTEGER,
    first_kickoff TEXT,
    last_kickoff TEXT,
    fetched_at TEXT,
    raw_file TEXT,
    PRIMARY KEY (competition_provider_id, season)
);
CREATE TABLE teams (
    provider_id INTEGER PRIMARY KEY,
    name TEXT,
    n_matches INTEGER,
    first_kickoff TEXT,
    last_kickoff TEXT
);
CREATE TABLE matches (
    provider_id INTEGER PRIMARY KEY,
    competition_provider_id INTEGER NOT NULL,
    season TEXT NOT NULL,
    round TEXT,
    round_name TEXT,
    scheduled_at TEXT NOT NULL,
    home_team_provider_id INTEGER,
    away_team_provider_id INTEGER,
    home_score INTEGER,
    away_score INTEGER,
    status TEXT NOT NULL,
    status_reason TEXT,
    status_reason_key TEXT,
    finished INTEGER,
    started INTEGER,
    cancelled INTEGER,
    awarded INTEGER,
    score_str TEXT,
    source TEXT NOT NULL
);
CREATE TABLE matches_after_cutoff (
    provider_id INTEGER PRIMARY KEY,
    competition_provider_id INTEGER NOT NULL,
    season TEXT NOT NULL,
    round TEXT,
    round_name TEXT,
    scheduled_at TEXT NOT NULL,
    home_team_provider_id INTEGER,
    away_team_provider_id INTEGER,
    home_score INTEGER,
    away_score INTEGER,
    status TEXT NOT NULL,
    status_reason TEXT,
    status_reason_key TEXT,
    finished INTEGER,
    started INTEGER,
    cancelled INTEGER,
    awarded INTEGER,
    score_str TEXT,
    source TEXT NOT NULL
);
CREATE TABLE duplicate_match_ids (
    provider_id INTEGER NOT NULL,
    kept_competition_provider_id INTEGER,
    kept_season TEXT,
    dropped_competition_provider_id INTEGER,
    dropped_season TEXT,
    same_teams INTEGER,
    same_score INTEGER,
    same_kickoff INTEGER
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX ix_matches_comp_season ON matches (competition_provider_id, season);
CREATE INDEX ix_matches_kickoff ON matches (scheduled_at);
CREATE INDEX ix_matches_home ON matches (home_team_provider_id);
CREATE INDEX ix_matches_away ON matches (away_team_provider_id);
"""

MATCH_COLS = [
    "provider_id", "competition_provider_id", "season", "round", "round_name", "scheduled_at",
    "home_team_provider_id", "away_team_provider_id", "home_score", "away_score", "status", "status_reason",
    "status_reason_key", "finished", "started", "cancelled", "awarded", "score_str", "source",
]


def _fetched_at(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")


def build_history_db(selection: list[dict[str, Any]], out_db: Path = DEFAULT_OUT_DB, raw_dir: Path = RAW_DIR) -> dict[str, Any]:
    """(Re)build history_results.db from the raw cache only. Atomic: temp file + os.replace."""
    out_db.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_db.with_name(out_db.name + ".tmp")
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(tmp)
    conn.executescript(SCHEMA)
    summary: Counter = Counter()
    kept: dict[int, dict[str, Any]] = {}
    after: dict[int, dict[str, Any]] = {}
    team_names: dict[int, tuple[str, str]] = {}
    status_combos: Counter = Counter()
    problems: list[str] = []

    for row in selection:
        conn.execute(
            "INSERT INTO competition_selection VALUES (?,?,?,?,?,?,?,?)",
            (row["provider_id"], row["db_name"], row["decision"], row["group"], row["reason"],
             row["n_db_finished"], row["n_db_connected"], row["n_connected_teams"]),
        )
    included = [r for r in selection if r["decision"] == "included"]
    for comp in included:
        league = comp["provider_id"]
        seasons, details, _src = known_league_info(league, raw_dir)
        note = None
        if seasons is None:
            note = "no cached FotMob response for this league"
            problems.append(f"{league}: {note}")
        targets, unrecognised = classify_seasons(seasons or [])
        if league in TARGET13:
            targets = [(s, season_role(s) or "core") for s in TARGET13_SEASONS if s in (seasons or [])]
        pre = prewindow_season(league, seasons or [], [s for s, r in targets if r == "core"], raw_dir)
        if pre:
            targets = targets + [(pre, "prewindow")]
        if league in SECOND_TIERS and details:
            exp_cc = SECOND_TIERS[league][0]
            if details.get("country") != exp_cc:
                note = f"expected country {exp_cc}, FotMob says {details.get('country')}"
                problems.append(f"{league}: {note}")
        conn.execute(
            "INSERT INTO competitions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (league, (details or {}).get("name"), (details or {}).get("country"), comp["reason"], comp["group"],
             comp["db_name"], (details or {}).get("type"), comp["n_db_finished"], comp["n_db_connected"],
             comp["n_connected_teams"], json.dumps(seasons) if seasons is not None else None,
             json.dumps(unrecognised) if unrecognised else None, note),
        )
        for season, role in targets:
            path = cache_path(league, season, raw_dir)
            data = load_gzip_json(path) if path.exists() else None
            problem = "missing_raw" if data is None else response_problem(data, league, season)
            if problem:
                conn.execute(
                    "INSERT INTO seasons (competition_provider_id, season, season_role, fetch_status, raw_file) "
                    "VALUES (?,?,?,?,?)",
                    (league, season, role, problem, path.name if path.exists() else None),
                )
                summary["seasons_missing"] += 1
                problems.append(f"{league} {season}: {problem}")
                continue
            rows, pstats = parse_season(data, league, season)
            c: Counter = Counter()
            first = last = None
            for r in rows:
                status_combos[(r["status"], r["status_reason"], r["finished"], r["started"], r["cancelled"], r["awarded"])] += 1
                if r["scheduled_at"] is None:
                    c["no_kickoff"] += 1
                    continue
                if r["home_team_provider_id"] is None or r["away_team_provider_id"] is None:
                    c["no_team"] += 1
                    continue
                if role == "prewindow" and r["scheduled_at"] < WINDOW_START:
                    c["before_window"] += 1  # a pre-window season contributes only its in-window matches
                    continue
                target = kept if r["scheduled_at"] < CUTOFF else after
                prev = target.get(r["provider_id"]) or (after if target is kept else kept).get(r["provider_id"])
                if prev is not None:
                    c["dup"] += 1
                    conn.execute(
                        "INSERT INTO duplicate_match_ids VALUES (?,?,?,?,?,?,?,?)",
                        (r["provider_id"], prev["competition_provider_id"], prev["season"], league, season,
                         int((prev["home_team_provider_id"], prev["away_team_provider_id"]) ==
                             (r["home_team_provider_id"], r["away_team_provider_id"])),
                         int((prev["home_score"], prev["away_score"]) == (r["home_score"], r["away_score"])),
                         int(prev["scheduled_at"] == r["scheduled_at"])),
                    )
                    continue
                target[r["provider_id"]] = r
                if target is after:
                    c["after_cutoff"] += 1
                else:
                    c["kept"] += 1
                    c["status:" + r["status"]] += 1
                    c["score_unparsed"] += r["score_unparsed"]
                    c["bracket"] += int(r["source"] == SOURCE_BRACKET)
                    first = r["scheduled_at"] if first is None or r["scheduled_at"] < first else first
                    last = r["scheduled_at"] if last is None or r["scheduled_at"] > last else last
                    for tid, tname in ((r["home_team_provider_id"], r["home_team_name"]),
                                       (r["away_team_provider_id"], r["away_team_name"])):
                        if tname and (tid not in team_names or r["scheduled_at"] >= team_names[tid][1]):
                            team_names[tid] = (tname, r["scheduled_at"])
            other = (c["kept"] - c["status:FINISHED"] - c["status:AWARDED"] - c["status:ABANDONED"]
                     - c["status:CANCELLED"] - c["status:POSTPONED"])
            conn.execute(
                "INSERT INTO seasons VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (league, season, role, "ok", c["kept"], pstats.get("n_source", 0), c["after_cutoff"],
                 c["before_window"],
                 c["status:FINISHED"], c["status:AWARDED"], c["status:ABANDONED"], c["status:CANCELLED"],
                 c["status:POSTPONED"], other,
                 c["bracket"], c["dup"] + pstats.get("repeated_in_all_matches", 0), c["no_kickoff"] + c["no_team"],
                 c["score_unparsed"], first, last, _fetched_at(path), path.name),
            )
            summary["seasons_ok"] += 1

    conn.executemany(f"INSERT INTO matches ({','.join(MATCH_COLS)}) VALUES ({','.join('?' * len(MATCH_COLS))})",
                     [tuple(r[k] for k in MATCH_COLS) for r in kept.values()])
    conn.executemany(f"INSERT INTO matches_after_cutoff ({','.join(MATCH_COLS)}) VALUES ({','.join('?' * len(MATCH_COLS))})",
                     [tuple(r[k] for k in MATCH_COLS) for r in after.values()])
    conn.execute(
        """INSERT INTO teams (provider_id, n_matches, first_kickoff, last_kickoff)
           SELECT t, COUNT(*), MIN(k), MAX(k) FROM (
               SELECT home_team_provider_id AS t, scheduled_at AS k FROM matches
               UNION ALL SELECT away_team_provider_id, scheduled_at FROM matches) GROUP BY t"""
    )
    conn.executemany("UPDATE teams SET name = ? WHERE provider_id = ?",
                     [(name, tid) for tid, (name, _k) in team_names.items()])
    meta = {
        "built_at": _utc_now(),
        "cutoff": CUTOFF,
        "source": "FotMob /api/data/leagues fixtures.allMatches (raw cache: data/raw_cache/fotmob_leagues)",
        "n_matches": str(len(kept)),
        "n_matches_after_cutoff": str(len(after)),
        "status_combinations": json.dumps({"|".join(map(str, k)): v for k, v in status_combos.most_common()}),
        "problems": json.dumps(problems, ensure_ascii=False),
    }
    conn.executemany("INSERT INTO meta VALUES (?,?)", list(meta.items()))
    conn.commit()
    conn.close()
    os.replace(tmp, out_db)
    summary["matches"] = len(kept)
    summary["matches_after_cutoff"] = len(after)
    summary["problems"] = len(problems)
    return {"summary": dict(summary), "problems": problems, "status_combos": status_combos}


# --------------------------------------------------------------------------- coverage

# Known season sizes of TARGET13 (outside knowledge, not taken from the data):
#   leagues: double round robin n x (n - 1) of the regular season (play-offs come on top)
#   UEFA:    the full format (group stage / league phase + knock-out rounds, two-legged ties)
_RR = {20: 380, 19: 342, 18: 306, 16: 240}
_TEAMS: dict[int, tuple[int, int, int, int]] = {  # teams in 2021/22, 2022/23, 2023/24, 2024/25
    47: (20, 20, 20, 20), 87: (20, 20, 20, 20), 55: (20, 20, 20, 20), 54: (18, 18, 18, 18),
    53: (20, 20, 18, 18), 57: (18, 18, 18, 18), 61: (18, 18, 18, 18), 40: (18, 18, 16, 16),
    71: (20, 19, 20, 19),
    122: (16, 16, 16, 16),  # 16 teams and the split format from 2021/22 (18 until 2020/21)
}
KNOWN_SIZE: dict[tuple[int, str], tuple[int, str]] = {
    (lg, s): (_RR[n], f"{n} teams round robin") for lg, ns in _TEAMS.items() for s, n in zip(TARGET13_SEASONS, ns)
}
for _lg in (42,):
    KNOWN_SIZE.update({(_lg, s): (125, "96 group + 29 KO") for s in TARGET13_SEASONS[:3]})
    KNOWN_SIZE[(_lg, "2024/2025")] = (189, "144 league + 16 play-off + 29 KO")
for _lg in (73, 10216):
    KNOWN_SIZE.update({(_lg, s): (141, "96 group + 16 KO play-off + 29 KO") for s in TARGET13_SEASONS[:3]})
KNOWN_SIZE[(73, "2024/2025")] = (189, "144 league + 16 play-off + 29 KO")
KNOWN_SIZE[(10216, "2024/2025")] = (153, "108 league + 16 play-off + 29 KO")


def coverage(out_db: Path = DEFAULT_OUT_DB) -> str:
    conn = sqlite3.connect(f"file:{out_db.as_posix()}?mode=ro", uri=True)
    try:
        lines = ["### TARGET13 per competition-season", "",
                 "| FotMob id | Competition | Season | allMatches | Kept (< cutoff) | Finished | Awarded | Abandoned | Cancelled | Postponed | Other | Known size | Basis | Deviation | First kickoff | Last kickoff |",
                 "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        names = dict(conn.execute("SELECT provider_id, name FROM competitions"))
        for league in TARGET13:
            for (season, role, fs, n, n_src, fin, aw, ab, can, pp, oth, first, last) in conn.execute(
                "SELECT season, season_role, fetch_status, n_matches, n_source, n_finished, n_awarded, n_abandoned,"
                " n_cancelled, n_postponed, n_other_status, first_kickoff, last_kickoff FROM seasons"
                " WHERE competition_provider_id = ? ORDER BY season", (league,)
            ):
                known, basis = KNOWN_SIZE.get((league, season), (None, "-"))
                dev = "" if known is None or n_src is None else f"{n_src - known:+d}"
                lines.append(
                    f"| {league} | {names.get(league)} | {season} ({role}) | {n_src if fs == 'ok' else fs} | {n} | {fin} | {aw} | {ab} | {can} | {pp} | {oth} | "
                    f"{known if known is not None else '-'} | {basis} | {dev} | {first} | {last} |"
                )
        lines += ["", "### All competitions (kept matches, kickoff < cutoff)", "",
                  "| FotMob id | Competition | Country | Group | Seasons ok | Seasons missing | Kept matches | Finished | Awarded | Not played* | After cutoff (boundary) | First kickoff | Last kickoff |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        tot: Counter = Counter()
        for (cid, name, cc, grp) in conn.execute(
            "SELECT provider_id, name, country, selection_group FROM competitions ORDER BY "
            "CASE selection_group WHEN 'TARGET13' THEN 0 WHEN 'second_tier' THEN 1 WHEN 'forced' THEN 2 ELSE 3 END, n_db_connected DESC"
        ):
            r = conn.execute(
                "SELECT SUM(fetch_status='ok'), SUM(fetch_status!='ok'), SUM(n_matches), SUM(n_finished), SUM(n_awarded),"
                " SUM(COALESCE(n_abandoned,0)+COALESCE(n_cancelled,0)+COALESCE(n_postponed,0)+COALESCE(n_other_status,0)),"
                " SUM(n_after_cutoff),"
                " MIN(first_kickoff), MAX(last_kickoff) FROM seasons WHERE competition_provider_id = ?", (cid,)
            ).fetchone()
            ok, miss, n, fin, aw, notp, aft, first, last = [x if x is not None else 0 for x in r[:7]] + list(r[7:])
            for k, v in zip(["ok", "miss", "n", "fin", "aw", "notp", "aft"], [ok, miss, n, fin, aw, notp, aft]):
                tot[k] += v
            lines.append(f"| {cid} | {name} | {cc} | {grp} | {ok} | {miss} | {n} | {fin} | {aw} | {notp} | {aft} | {first} | {last} |")
        lines.append(f"| | **Total** | | | {tot['ok']} | {tot['miss']} | {tot['n']} | {tot['fin']} | {tot['aw']} | {tot['notp']} | {tot['aft']} | | |")
        lines += ["", "*Not played = cancelled + postponed + other non-finished statuses (scores NULL)."]
        return "\n".join(lines)
    finally:
        conn.close()


# --------------------------------------------------------------------------- spot check


def spot_check(n: int, out_db: Path, base_url: str, seed: int) -> list[dict[str, Any]]:
    """Compare n random kept FINISHED history scores with matchDetails headers (n requests, limiter)."""
    conn = sqlite3.connect(f"file:{out_db.as_posix()}?mode=ro", uri=True)
    rows = conn.execute(
        "SELECT provider_id, competition_provider_id, season, scheduled_at, home_team_provider_id,"
        " away_team_provider_id, home_score, away_score, awarded FROM matches WHERE status = 'FINISHED'"
        " ORDER BY provider_id"
    ).fetchall()
    conn.close()
    sample = random.Random(seed).sample(rows, min(n, len(rows)))
    fetcher = Fetcher(base_url, 30.0, max_requests=n)
    results = []
    try:
        for (mid, comp, season, kickoff, h, a, hs, as_, aw) in sample:
            data, raw, err = fetcher.get_json(DETAILS_ENDPOINT, {"matchId": mid}, max_attempts=2)
            res = {"match_provider_id": mid, "competition_provider_id": comp, "season": season, "kickoff": kickoff,
                   "history": [h, a, hs, as_]}
            if data is None:
                res["error"] = err
            else:
                atomic_write_gzip(SPOT_DIR / f"{mid}.json.gz", raw or b"")
                header = data.get("header") or {}
                teams = header.get("teams") or [{}, {}]
                general = data.get("general") or {}
                det = [_to_int((general.get("homeTeam") or {}).get("id")), _to_int((general.get("awayTeam") or {}).get("id")),
                       _to_int(teams[0].get("score")), _to_int(teams[1].get("score"))]
                res["details"] = det
                res["details_kickoff"] = normalise_utc(general.get("matchTimeUTCDate"))
                res["details_status"] = {k: (header.get("status") or {}).get(k) for k in ("finished", "awarded", "cancelled")}
                res["agree"] = det == [h, a, hs, as_]
            results.append(res)
            print(json.dumps(res), flush=True)
    finally:
        fetcher.close()
    return results


# --------------------------------------------------------------------------- CLI


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(DEFAULT_PROD_DB), help="production DB (opened read-only)")
    ap.add_argument("--out", default=str(DEFAULT_OUT_DB))
    ap.add_argument("--base-url", default=BASE_URL)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--max-requests", type=int, default=1500, help="hard cap of HTTP requests in one run")
    ap.add_argument("--include", default="", help="comma-separated FotMob league ids to force-include")
    ap.add_argument("--only-target13", action="store_true", help="collect TARGET13 only (phase 1)")
    ap.add_argument("--dry-run", action="store_true", help="list the plan from the cache, no network")
    ap.add_argument("--from-raw", action="store_true", help="rebuild the DB from the raw cache, no network")
    ap.add_argument("--coverage", action="store_true", help="print coverage tables (markdown) and exit")
    ap.add_argument("--spot-check", type=int, default=0, help="compare N random history scores with matchDetails")
    ap.add_argument("--seed", type=int, default=20261013)
    return ap.parse_args(argv)


def _include_ids(spec: str) -> list[int]:
    return [int(t) for t in (x.strip() for x in spec.split(",")) if t.lstrip("-").isdigit()]


def run_dry(args: argparse.Namespace) -> None:
    hist_teams, missing = target13_history_teams()
    selection = select_competitions(Path(args.db), hist_teams, _include_ids(args.include))
    included = [r for r in selection if r["decision"] == "included"]
    print(f"TARGET13 history teams from cache: {len(hist_teams)} (TARGET13 season files missing: {len(missing)})")
    need = 0
    unknown = 0
    for r in included:
        seasons, details, _ = known_league_info(r["provider_id"])
        if r["provider_id"] in TARGET13:
            targets = [(s, season_role(s) or "core") for s in TARGET13_SEASONS]
        else:
            targets, _ = classify_seasons(seasons or [])
        pre = prewindow_season(r["provider_id"], seasons or [], [s for s, role in targets if role == "core"])
        if pre:
            targets.append((pre, "prewindow"))
        todo = [s for s, _ in targets if not cache_path(r["provider_id"], s).exists()]
        if seasons is None and r["provider_id"] not in TARGET13:
            unknown += 1
            plan = "seasons unknown (1 discovery request + 4-5 seasons)"
            need += 5
        else:
            plan = f"{len(targets)} target seasons, {len(todo)} to fetch: {','.join(todo)}"
            need += len(todo)
        print(f"{r['group']:<11} {r['provider_id']:>6} {str((details or {}).get('name') or r['db_name'])[:38]:<38} "
              f"{str((details or {}).get('country') or ''):<4} | {plan} | {r['reason']}")
    excl = [r for r in selection if r["decision"] == "excluded"]
    print(f"\nincluded={len(included)} excluded={len(excl)} leagues_without_known_seasons={unknown} "
          f"estimated_requests~{need}")


def run_collect(args: argparse.Namespace) -> int:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stats: Counter = Counter()
    fetcher = Fetcher(args.base_url, args.timeout, args.max_requests)
    stopped = None
    t0 = time.monotonic()
    try:
        print(f"[{_utc_now()}] phase 1: TARGET13", flush=True)
        for league in TARGET13:
            collect_league(fetcher, league, stats, seasons_override=TARGET13_SEASONS)
        if not args.only_target13:
            hist_teams, missing = target13_history_teams()
            selection = select_competitions(Path(args.db), hist_teams, _include_ids(args.include))
            write_selection_csv(selection)
            todo = [r for r in selection if r["decision"] == "included" and r["provider_id"] not in TARGET13]
            print(f"[{_utc_now()}] phase 2: {len(todo)} context / second-tier competitions "
                  f"(TARGET13 history teams {len(hist_teams)}, missing TARGET13 files {len(missing)})", flush=True)
            for r in todo:
                collect_league(fetcher, r["provider_id"], stats)
    except StopCollection as exc:
        stopped = str(exc)
        print(f"STOPPED: {exc}", flush=True)
        _log({"event": "stopped", "reason": stopped})
    finally:
        fetcher.close()
    print(f"[{_utc_now()}] requests={fetcher.n_requests} {dict(stats)} elapsed={time.monotonic() - t0:.0f}s", flush=True)
    rebuild(args)
    return 2 if stopped else 0


def rebuild(args: argparse.Namespace) -> None:
    hist_teams, missing = target13_history_teams()
    selection = select_competitions(Path(args.db), hist_teams, _include_ids(args.include))
    write_selection_csv(selection)
    result = build_history_db(selection, Path(args.out))
    print(f"[{_utc_now()}] built {args.out}: {result['summary']}", flush=True)
    for p in result["problems"][:50]:
        print("  problem:", p)
    print("  status combinations (status, reason, finished, started, cancelled, awarded):")
    for k, v in result["status_combos"].most_common():
        print(f"    {k}: {v}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.coverage:
        print(coverage(Path(args.out)))
        return 0
    if args.dry_run:
        run_dry(args)
        return 0
    if args.from_raw:
        rebuild(args)
        return 0
    if args.spot_check:
        res = spot_check(args.spot_check, Path(args.out), args.base_url, args.seed)
        out = HISTORY_DIR / "spot_check.json"
        atomic_write_bytes(out, json.dumps(res, indent=1).encode("utf-8"))
        agree = sum(1 for r in res if r.get("agree"))
        print(f"spot check: {agree}/{len(res)} agree; details in {out}")
        return 0
    return run_collect(args)


if __name__ == "__main__":
    sys.exit(main())
