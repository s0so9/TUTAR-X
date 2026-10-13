"""Collect FotMob match details (line-ups, player stats, team xG) for training.

TRAINING DATA COLLECTOR - source: FotMob unofficial API
(``/api/data/matchDetails?matchId=<FotMob match id>``).

Match-id sources (``--source``):

* ``db`` (default): FINISHED matches of the local DB (``matches.provider_id`` = FotMob
  match id), opened READ-ONLY. Output ``data/training/fotmob_match_details.jsonl``.
* ``fixtures``: FotMob season fixture lists
  (``/api/data/leagues?id=<league>&season=<season>`` -> ``fixtures.allMatches``): matches that
  are finished and not cancelled (awarded matches are kept and flagged ``awarded``). The league
  response must report ``details.selectedSeason == <season>``, otherwise the list is rejected.
  League responses are cached untouched (gzip) in
  ``data/raw_cache/fotmob_leagues/<league>_<season, "/" -> "-">.json.gz`` and an existing file is
  reused instead of fetched. Output ``data/training/fotmob_match_details_history.jsonl``: the same
  schema as the db output plus ``season``; ``competition_provider_id`` = the requested league id;
  ``db_check`` = null. Seasons are processed in the given order (``--seasons``).

One JSON line per match is appended to the output file; failures go to a separate errors file.
The run is resumable: match ids already present in the output file are skipped, so the script can
be stopped and restarted at will. Raw responses are written atomically (temp file + os.replace).

Politeness rules (hard-coded caps):
  * the shared cross-process limiter ``fotmob_rate.py`` is called before EVERY FotMob request
    (one global budget for all collectors on this machine); an HTTP 429 is reported to it with
    ``report_429(Retry-After or 60 s)`` so every collector pauses
  * at most 3 concurrent workers for ``--source db`` and 2 for ``--source fixtures``
    (``--concurrency`` is clamped)
  * a pause of ``--delay`` seconds (>= 0.3 db, >= 0.4 fixtures) between requests of the same worker
  * exponential backoff with jitter on timeouts, connection errors, 429 and 5xx
    (Retry-After honoured for 429), a global cool-down after any 429
  * a worker stops after ``--max-consecutive-failures`` failed matches in a row
  * HTTP 403 or a challenge/captcha page stops the whole run (exit code 2); it is never worked around

Honesty rules (AGENTS.md): no value is ever invented. A stat that FotMob does not
send is written as ``null``; 0 is written only when FotMob sends 0.

Usage (from backend/):
  venv/Scripts/python.exe scripts/data_collection/collect_fotmob_details.py \
      --competitions 47,87,55,54,53,42,73,10216
  venv/Scripts/python.exe scripts/data_collection/collect_fotmob_details.py --coverage \
      --competitions 47,87,55
  venv/Scripts/python.exe scripts/data_collection/collect_fotmob_details.py --source fixtures \
      --seasons 2024/2025,2023/2024,2022/2023 --competitions TARGET13
  venv/Scripts/python.exe scripts/data_collection/collect_fotmob_details.py --source fixtures \
      --seasons 2024/2025,2023/2024,2022/2023 --competitions TARGET13 --coverage

Modes:
  (default)      fetch + parse + append
  --from-raw     re-parse the gzip raw cache into the output (no network)
  --coverage     print the coverage table (markdown) and exit; per competition for --source db,
                 per competition-season (vs the cached fixture lists) for --source fixtures
"""

from __future__ import annotations

import argparse
import asyncio
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

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import fotmob_rate  # noqa: E402  (shared cross-process FotMob limiter, sibling module)

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DB = BACKEND_DIR / "football_intelligence.db"
DEFAULT_OUT = BACKEND_DIR / "data" / "training" / "fotmob_match_details.jsonl"
DEFAULT_ERR = BACKEND_DIR / "data" / "training" / "fotmob_details_errors.jsonl"
DEFAULT_HISTORY_OUT = BACKEND_DIR / "data" / "training" / "fotmob_match_details_history.jsonl"
DEFAULT_HISTORY_ERR = BACKEND_DIR / "data" / "training" / "fotmob_details_history_errors.jsonl"
DEFAULT_RAW_DIR = BACKEND_DIR / "data" / "raw_cache" / "fotmob_match_details"
DEFAULT_LEAGUES_DIR = BACKEND_DIR / "data" / "raw_cache" / "fotmob_leagues"
DEFAULT_BASE_URL = "https://www.fotmob.com"
ENDPOINT = "/api/data/matchDetails"
LEAGUES_ENDPOINT = "/api/data/leagues"
HEADERS = {"User-Agent": "Mozilla/5.0 (TUTAR X research collector; low-rate)", "Accept": "application/json"}

SET_A = [47, 87, 55, 54, 53, 42, 73, 10216]
SET_B = [71, 57, 61, 40, 48, 59, 38, 64, 122, 135, 46, 69]
# The 10 strongest leagues by UEFA association coefficient (ENG, ESP, ITA, GER, FRA, NED, POR,
# BEL, TUR, CZE) + Champions League, Europa League, Conference League.
TARGET13 = [47, 87, 55, 54, 53, 57, 61, 40, 71, 122, 42, 73, 10216]
NAMED_SETS = {"A": SET_A, "B": SET_B, "TARGET13": TARGET13}
DEFAULT_SEASONS = "2024/2025,2023/2024,2022/2023"

# per source: (max concurrent workers, min seconds between requests of one worker)
CAPS = {"db": (3, 0.3), "fixtures": (2, 0.4)}
# answers that mean "FotMob does not want this client": stop, never work around
BLOCKED_KINDS = {"blocked_http_403", "blocked_challenge"}
# non-success request attempts of this process by kind (http_429, timeout, ...), for the run summary
HTTP_EVENTS: Counter = Counter()

# FotMob lineup "usualPlayingPositionId" -> role label (observed: 0 GK, 1 DEF, 2 MID, 3 FWD)
USUAL_POSITION_LABEL = {0: "GK", 1: "DEF", 2: "MID", 3: "FWD"}

# playerStats stat keys (stable "key" field, NOT the English title) -> output field
PLAYER_STAT_KEYS = {
    "rating_title": "rating",
    "minutes_played": "minutes_played",
    "goals": "goals",
    "assists": "assists",
    "expected_goals": "xg",
    "expected_assists": "xa",
    "expected_goals_on_target_variant": "xgot",
    "expected_goals_non_penalty": "npxg",
    "total_shots": "shots",
    "ShotsOnTarget": "shots_on_target",
}


def _base_url() -> str:
    """Base URL from app settings (settings.fotmob_base_url), with a safe fallback."""
    try:
        sys.path.insert(0, str(BACKEND_DIR))
        from app.config import settings  # type: ignore

        return str(settings.fotmob_base_url).rstrip("/")
    except Exception:
        return DEFAULT_BASE_URL


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` via a temp file + os.replace, so readers never see a partial
    file. The temp name ends in ``.tmp`` (never matches ``*.json.gz``)."""
    path = Path(path)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(data)
    for attempt in range(6):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:  # Windows: target briefly open by a reader
            if attempt == 5:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.2 * (attempt + 1))


# --------------------------------------------------------------------------- DB


def load_matches(db_path: Path, competition_ids: list[int]) -> list[dict[str, Any]]:
    """Finished matches of the given FotMob league ids, from the DB (read-only)."""
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        rows: list[dict[str, Any]] = []
        for comp in competition_ids:
            cur = conn.execute(
                """
                SELECT m.provider_id, m.scheduled_at, co.provider_id,
                       ht.provider_id, at.provider_id, m.home_score, m.away_score
                FROM matches m
                JOIN competitions co ON co.id = m.competition_id
                JOIN teams ht ON ht.id = m.home_team_id
                JOIN teams at ON at.id = m.away_team_id
                WHERE co.provider_id = ? AND m.status = 'FINISHED'
                ORDER BY m.scheduled_at
                """,
                (str(comp),),
            )
            for r in cur.fetchall():
                rows.append(
                    {
                        "match_provider_id": str(r[0]),
                        "db_scheduled_at": r[1],
                        "competition_provider_id": _to_int(r[2]),
                        "db_home_team_provider_id": _to_int(r[3]),
                        "db_away_team_provider_id": _to_int(r[4]),
                        "db_home_score": r[5],
                        "db_away_score": r[6],
                    }
                )
        return rows
    finally:
        conn.close()


def competition_names(db_path: Path, competition_ids: list[int]) -> dict[int, str]:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        out = {}
        for comp in competition_ids:
            r = conn.execute(
                "SELECT name, country FROM competitions WHERE provider_id = ?", (str(comp),)
            ).fetchone()
            out[comp] = f"{r[0]} ({r[1]})" if r and r[1] else (r[0] if r else "?")
        return out
    finally:
        conn.close()


# ------------------------------------------------------------- fixture lists


class LeagueSeasonError(Exception):
    """The league response cannot be used as the fixture list of the requested season."""


def season_slug(season: str) -> str:
    return season.strip().replace("/", "-")


def league_cache_path(cache_dir: Path, league_id: int, season: str) -> Path:
    """``<cache_dir>/<league>_<season with "/" replaced by "-">.json.gz`` (shared with other collectors)."""
    return Path(cache_dir) / f"{league_id}_{season_slug(season)}.json.gz"


def parse_seasons(spec: str) -> list[str]:
    """Comma-separated seasons (``YYYY/YYYY`` or ``YYYY`` for calendar-year leagues), order kept."""
    out: list[str] = []
    for tok in (spec or "").split(","):
        tok = tok.strip()
        if not tok:
            continue
        if not re.fullmatch(r"\d{4}(/\d{4})?", tok):
            raise ValueError(f"invalid season {tok!r}: expected YYYY/YYYY or YYYY")
        if tok not in out:
            out.append(tok)
    return out


def _league_payload(obj: Any) -> dict[str, Any]:
    """The /api/data/leagues response itself (tolerates a cache file that wraps the body)."""
    if isinstance(obj, dict) and "fixtures" in obj:
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, dict) and "fixtures" in v:
                return v
    raise LeagueSeasonError("league_response_without_fixtures")


def parse_fixture_list(
    league_data: dict[str, Any], league_id: int, season: str
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Match metas (finished, not cancelled; awarded kept + flagged) of one league-season.

    Returns (metas sorted by kick-off, summary counts). Raises LeagueSeasonError when the
    response is not the requested league/season (``details.selectedSeason``/``details.id``).
    """
    data = _league_payload(league_data)
    details = data.get("details") or {}
    selected = details.get("selectedSeason")
    if selected is None or str(selected) != season:
        raise LeagueSeasonError(f"season_mismatch requested={season} selectedSeason={selected}")
    if _to_int(details.get("id")) not in (None, league_id):
        raise LeagueSeasonError(f"league_mismatch requested={league_id} details.id={details.get('id')}")

    summary = {"listed": 0, "kept": 0, "awarded": 0, "cancelled": 0, "not_finished": 0, "duplicates": 0, "no_id": 0}
    metas: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in (data.get("fixtures") or {}).get("allMatches") or []:
        summary["listed"] += 1
        st = m.get("status") or {}
        if m.get("id") is None:
            summary["no_id"] += 1
            continue
        mid = str(m.get("id"))
        if mid in seen:
            summary["duplicates"] += 1
            continue
        seen.add(mid)
        if st.get("cancelled"):
            summary["cancelled"] += 1
            continue
        if st.get("finished") is not True:
            summary["not_finished"] += 1
            continue
        awarded = bool(st.get("awarded"))
        summary["kept"] += 1
        summary["awarded"] += int(awarded)
        metas.append(
            {
                "match_provider_id": mid,
                "competition_provider_id": league_id,
                "season": season,
                "source": "fixtures",
                "fixture_utc_time": st.get("utcTime"),
                "fixture_home_team_provider_id": _to_int((m.get("home") or {}).get("id")),
                "fixture_away_team_provider_id": _to_int((m.get("away") or {}).get("id")),
                "fixture_score_str": st.get("scoreStr"),
                "fixture_awarded": awarded,
            }
        )
    metas.sort(key=lambda x: (x["fixture_utc_time"] or "", x["match_provider_id"]))
    return metas, summary


def read_cached_league(cache_dir: Path, league_id: int, season: str) -> dict[str, Any] | None:
    """Cached league response, or None when missing/unreadable."""
    path = league_cache_path(cache_dir, league_id, season)
    if not path.exists():
        return None
    try:
        return json.loads(gzip.decompress(path.read_bytes()))
    except (OSError, EOFError, ValueError):
        return None


def _score_from_str(score: Any) -> tuple[int | None, int | None]:
    """'2 - 1' -> (2, 1); anything else -> (None, None) (no check possible)."""
    m = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", score) if isinstance(score, str) else None
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


# ------------------------------------------------------------------- parsing


def _team_xg(stats: Any) -> tuple[float | None, float | None]:
    """content.stats.Periods.All.stats[*].stats[*] where key == 'expected_goals' (type != 'title')."""
    try:
        groups = stats["Periods"]["All"]["stats"]
    except (KeyError, TypeError):
        return None, None
    for group in groups or []:
        for s in group.get("stats") or []:
            if s.get("type") == "title":  # section header row, values always [null, null]
                continue
            if s.get("key") == "expected_goals":
                vals = s.get("stats") or [None, None]
                if len(vals) >= 2:
                    return _to_float(vals[0]), _to_float(vals[1])
    return None, None


def _team_stats(stats: Any) -> dict[str, list[Any]] | None:
    """All full-match team stats as {key: [home, away]} exactly as sent (raw values)."""
    try:
        groups = stats["Periods"]["All"]["stats"]
    except (KeyError, TypeError):
        return None
    out: dict[str, list[Any]] = {}
    for group in groups or []:
        for s in group.get("stats") or []:
            if s.get("type") == "title":  # section header row, not a stat
                continue
            key = s.get("key")
            vals = s.get("stats")
            if key and isinstance(vals, list) and len(vals) == 2 and key not in out:
                out[key] = vals
    return out or None


def _player_stat_values(entry: dict[str, Any] | None) -> dict[str, Any]:
    """Flatten playerStats[pid].stats[*].stats{title: {key, stat:{value}}} by stable key."""
    found: dict[str, Any] = {}
    if not entry:
        return found
    for block in entry.get("stats") or []:
        for _title, sv in (block.get("stats") or {}).items():
            if not isinstance(sv, dict):
                continue
            key = sv.get("key")
            if key in PLAYER_STAT_KEYS and PLAYER_STAT_KEYS[key] not in found:
                stat = sv.get("stat") or {}
                if "value" in stat:
                    found[PLAYER_STAT_KEYS[key]] = stat.get("value")
    return found


def _sub_minutes(perf: dict[str, Any]) -> tuple[int | None, int | None]:
    sub_in = sub_out = None
    for ev in perf.get("substitutionEvents") or []:
        if ev.get("type") == "subIn" and sub_in is None:
            sub_in = _to_int(ev.get("time"))
        elif ev.get("type") == "subOut" and sub_out is None:
            sub_out = _to_int(ev.get("time"))
    return sub_in, sub_out


def _parse_player(
    p: dict[str, Any], side: str, team_id: int | None, is_starter: bool, player_stats: dict[str, Any]
) -> dict[str, Any]:
    pid = p.get("id")
    entry = player_stats.get(str(pid)) if pid is not None else None
    vals = _player_stat_values(entry)
    perf = p.get("performance") or {}
    sub_in, sub_out = _sub_minutes(perf)

    rating = _to_float(vals.get("rating"))
    rating_source = "playerStats" if rating is not None else None
    if rating is None and _to_float(perf.get("rating")) is not None:
        rating = _to_float(perf.get("rating"))
        rating_source = "lineup"

    shotmap = entry.get("shotmap") if entry else None
    usual = _to_int(p.get("usualPlayingPositionId"))
    return {
        "player_id": _to_int(pid),
        "name": p.get("name"),
        "team_side": side,
        "team_provider_id": team_id,
        "is_starter": is_starter,
        "appeared": bool(is_starter or sub_in is not None),
        "position": USUAL_POSITION_LABEL.get(usual) if usual is not None else None,
        "usual_position_id": usual,
        "position_id": _to_int(p.get("positionId")),
        "is_goalkeeper": entry.get("isGoalkeeper") if entry else None,
        "shirt_number": p.get("shirtNumber"),
        "age": _to_int(p.get("age")),
        "minutes_played": _to_int(vals.get("minutes_played")),
        "sub_in_minute": sub_in,
        "sub_out_minute": sub_out,
        "rating": rating,
        "rating_source": rating_source,
        "goals": _to_int(vals.get("goals")),
        "assists": _to_int(vals.get("assists")),
        "xg": _to_float(vals.get("xg")),
        "xa": _to_float(vals.get("xa")),
        "xgot": _to_float(vals.get("xgot")),
        "npxg": _to_float(vals.get("npxg")),
        "shots": _to_int(vals.get("shots")),
        "shots_on_target": _to_int(vals.get("shots_on_target")),
        "shotmap_count": len(shotmap) if isinstance(shotmap, list) else None,
        "stats_available": bool(entry and entry.get("stats")),
        "market_value": _to_int(p.get("marketValue")),
    }


def _parse_unavailable(items: list[dict[str, Any]] | None, side: str) -> list[dict[str, Any]]:
    out = []
    for u in items or []:
        un = u.get("unavailability") or {}
        out.append(
            {
                "player_id": _to_int(u.get("id")),
                "name": u.get("name"),
                "team_side": side,
                "type": un.get("type"),
                "expected_return": un.get("expectedReturn"),
                "market_value": _to_int(u.get("marketValue")),
            }
        )
    return out


class ParseError(Exception):
    pass


def _finalize_for_source(record: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    """Fixture-list records: add ``season`` (right after competition_provider_id); db_check = null."""
    if meta.get("source") != "fixtures":
        return record
    out: dict[str, Any] = {}
    for key, value in record.items():
        out[key] = value
        if key == "competition_provider_id":
            out["season"] = meta.get("season")
    out["db_check"] = None
    return out


def parse_match(data: dict[str, Any], meta: dict[str, Any], fetched_at: str) -> dict[str, Any]:
    general = data.get("general") or {}
    header = data.get("header") or {}
    content = data.get("content") or {}
    status = header.get("status") or {}

    if not general.get("finished") and not status.get("finished"):
        raise ParseError("not_finished_in_source")
    if status.get("cancelled"):
        raise ParseError("cancelled_in_source")

    teams = header.get("teams") or []
    if len(teams) != 2:
        raise ParseError("header_teams_missing")

    home_id = _to_int((general.get("homeTeam") or {}).get("id")) or _to_int(teams[0].get("id"))
    away_id = _to_int((general.get("awayTeam") or {}).get("id")) or _to_int(teams[1].get("id"))

    lineup = content.get("lineup") or {}
    player_stats = content.get("playerStats") or {}
    home_xg, away_xg = _team_xg(content.get("stats"))

    players: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    formations: dict[str, Any] = {}
    team_meta: dict[str, Any] = {}
    for side, key in (("home", "homeTeam"), ("away", "awayTeam")):
        t = lineup.get(key) or {}
        team_id = _to_int(t.get("id")) or (home_id if side == "home" else away_id)
        formations[side] = t.get("formation")
        team_meta[f"{side}_starters_market_value"] = _to_int(t.get("totalStarterMarketValue"))
        team_meta[f"{side}_starters_avg_age"] = _to_float(t.get("averageStarterAge"))
        team_meta[f"{side}_team_rating"] = _to_float(t.get("rating"))
        for p in t.get("starters") or []:
            players.append(_parse_player(p, side, team_id, True, player_stats))
        for p in t.get("subs") or []:
            players.append(_parse_player(p, side, team_id, False, player_stats))
        unavailable.extend(_parse_unavailable(t.get("unavailable"), side))

    record = {
        "match_provider_id": str(general.get("matchId") or meta["match_provider_id"]),
        "scheduled_at": general.get("matchTimeUTCDate")
        or status.get("utcTime")
        or meta.get("db_scheduled_at")
        or meta.get("fixture_utc_time"),
        "competition_provider_id": meta.get("competition_provider_id"),
        "source_league_id": _to_int(general.get("leagueId")),
        "source_parent_league_id": _to_int(general.get("parentLeagueId")),
        "home_team_provider_id": home_id,
        "away_team_provider_id": away_id,
        "home_score": _to_int(teams[0].get("score")),
        "away_score": _to_int(teams[1].get("score")),
        # fixture-list source: also flagged when the season fixture list marks the match awarded
        "awarded": bool(status.get("awarded")) or bool(meta.get("fixture_awarded")),
        "home_xg": home_xg,
        "away_xg": away_xg,
        "lineup_type": lineup.get("lineupType"),
        "lineup_source": lineup.get("source"),
        "home_formation": formations.get("home"),
        "away_formation": formations.get("away"),
        **team_meta,
        "team_stats": _team_stats(content.get("stats")),
        "players": players,
        "unavailable": unavailable,
        "db_check": {
            "home_team_matches_db": home_id == meta.get("db_home_team_provider_id"),
            "away_team_matches_db": away_id == meta.get("db_away_team_provider_id"),
            "score_matches_db": (
                _to_int(teams[0].get("score")) == meta.get("db_home_score")
                and _to_int(teams[1].get("score")) == meta.get("db_away_score")
            ),
        },
        "fetched_at": fetched_at,
    }
    return _finalize_for_source(record, meta)


# ------------------------------------------------------------------- files


def read_done_ids(path: Path) -> set[str]:
    done: set[str] = set()
    if not path.exists():
        return done
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(str(json.loads(line)["match_provider_id"]))
            except (json.JSONDecodeError, KeyError):
                continue  # a partially written last line from an interrupted run
    return done


def _ensure_trailing_newline(path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        with path.open("rb") as fh:
            fh.seek(-1, 2)
            if fh.read(1) != b"\n":
                with path.open("ab") as fa:
                    fa.write(b"\n")


def _read_raw(raw_dir: Path, match_id: str) -> tuple[dict[str, Any] | None, str | None]:
    """(cached raw response, its file time) or (None, None) when missing/unreadable."""
    f = raw_dir / f"{match_id}.json.gz"
    if not f.exists():
        return None, None
    try:
        data = json.loads(gzip.decompress(f.read_bytes()))
    except (OSError, EOFError, ValueError):
        return None, None
    fetched = datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
    return data, fetched


class Sink:
    """Append-only JSONL writer (single event loop -> writes are serialised)."""

    def __init__(self, out_path: Path, err_path: Path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        err_path.parent.mkdir(parents=True, exist_ok=True)
        _ensure_trailing_newline(out_path)
        _ensure_trailing_newline(err_path)
        self.out = out_path.open("a", encoding="utf-8")
        self.err = err_path.open("a", encoding="utf-8")
        self.ok = 0
        self.failed = 0

    def write(self, record: dict[str, Any]) -> None:
        self.out.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.out.flush()
        self.ok += 1

    def error(
        self, match_id: Any, competition: Any, kind: str, detail: str, attempts: int, season: str | None = None
    ) -> None:
        row = {
            "match_provider_id": match_id,
            "competition_provider_id": competition,
            "error": kind,
            "detail": detail[:300],
            "attempts": attempts,
            "at": _utc_now(),
        }
        if season is not None:  # fixture-list source only (db rows keep their original shape)
            row = {**row, "season": season}
        self.err.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.err.flush()
        self.failed += 1

    def close(self) -> None:
        self.out.close()
        self.err.close()


# ------------------------------------------------------------------- fetching


class Throttle:
    """Global cool-down shared by all workers (set after a 429)."""

    def __init__(self) -> None:
        self.resume_at = 0.0

    async def wait(self) -> None:
        delay = self.resume_at - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)

    def cool_down(self, seconds: float) -> None:
        self.resume_at = max(self.resume_at, time.monotonic() + seconds)


async def _acquire_shared_slot() -> None:
    """``fotmob_rate.acquire_async()``, retried while the limiter's lock directory hits a transient
    OS error. On Windows ``os.mkdir`` of a lock directory that another process is removing raises
    ``PermissionError [WinError 5]`` (fotmob_rate only handles FileExistsError). The limiter is
    never skipped: the request waits until a slot was granted."""
    while True:
        try:
            await fotmob_rate.acquire_async()
            return
        except OSError:
            await asyncio.sleep(0.05 + random.uniform(0, 0.1))


def _report_429_shared(seconds: float) -> None:
    """``fotmob_rate.report_429``, retried on the same transient lock error (best effort)."""
    for _ in range(50):
        try:
            fotmob_rate.report_429(seconds)
            return
        except OSError:
            time.sleep(0.05 + random.uniform(0, 0.1))
    print(f"WARNING: could not record a 429 cool-down of {seconds}s in the shared limiter", flush=True)


def _looks_like_challenge(resp: httpx.Response) -> bool:
    """A non-JSON answer that looks like a bot-protection / captcha page."""
    if resp.headers.get("cf-mitigated"):
        return True
    ctype = (resp.headers.get("content-type") or "").lower()
    head = resp.content[:4000].lower()
    return "html" in ctype or head.lstrip().startswith(b"<") or any(
        s in head for s in (b"captcha", b"challenge", b"just a moment")
    )


async def fetch_json(
    client: httpx.AsyncClient, endpoint: str, params: dict[str, Any], throttle: Throttle, max_retries: int
) -> tuple[dict[str, Any] | None, bytes | None, str | None, str, int]:
    """GET one FotMob endpoint. Returns (json, raw_bytes, error_kind, error_detail, attempts).

    The shared limiter (fotmob_rate) is acquired before every request; 429 is reported to it.
    403 / challenge pages return a BLOCKED_KINDS error at once (the caller must stop)."""
    attempt = 0
    last_kind, last_detail = "unknown", ""

    def fail(kind: str, detail: str) -> tuple[None, None, str, str, int]:
        HTTP_EVENTS[kind] += 1
        return None, None, kind, detail, attempt

    while attempt <= max_retries:
        attempt += 1
        await throttle.wait()
        await _acquire_shared_slot()
        try:
            resp = await client.get(endpoint, params=params)
        except httpx.TimeoutException as exc:
            last_kind, last_detail = "timeout", type(exc).__name__
        except httpx.RequestError as exc:
            last_kind, last_detail = "connection_error", type(exc).__name__
        else:
            if resp.status_code == 200:
                try:
                    return resp.json(), resp.content, None, "", attempt
                except ValueError as exc:
                    if _looks_like_challenge(resp):
                        return fail("blocked_challenge", f"HTTP 200 non-JSON ({resp.headers.get('content-type')})")
                    last_kind, last_detail = "invalid_json", str(exc)
            elif resp.status_code == 403:
                return fail("blocked_http_403", resp.reason_phrase)
            elif resp.status_code == 404:
                return fail("http_404", "not found")
            elif resp.status_code == 429:
                retry_after = _to_float(resp.headers.get("Retry-After"))
                _report_429_shared(retry_after if retry_after is not None else 60.0)
                throttle.cool_down(min(retry_after or 30.0, 120.0))
                last_kind, last_detail = "http_429", f"Retry-After={resp.headers.get('Retry-After')}"
            elif 500 <= resp.status_code < 600:
                if resp.headers.get("cf-mitigated"):
                    return fail("blocked_challenge", f"HTTP {resp.status_code} cf-mitigated")
                last_kind, last_detail = f"http_{resp.status_code}", resp.reason_phrase
            else:
                return fail(f"http_{resp.status_code}", resp.reason_phrase)
        HTTP_EVENTS[last_kind] += 1  # a retryable failure of this attempt
        if attempt <= max_retries:
            backoff = min(2.0 ** attempt, 60.0) + random.uniform(0, 1.0)
            await asyncio.sleep(backoff)
    return None, None, last_kind, last_detail, attempt


async def fetch_one(
    client: httpx.AsyncClient, match_id: str, throttle: Throttle, max_retries: int
) -> tuple[dict[str, Any] | None, bytes | None, str | None, str, int]:
    """matchDetails of one match. Returns (json, raw_bytes, error_kind, error_detail, attempts)."""
    return await fetch_json(client, ENDPOINT, {"matchId": match_id}, throttle, max_retries)


async def worker(
    name: str,
    queue: asyncio.Queue,
    client: httpx.AsyncClient,
    sink: Sink,
    throttle: Throttle,
    args: argparse.Namespace,
    raw_dir: Path | None,
    deadline: float | None,
    stats: dict[str, Any],
) -> None:
    consecutive_failures = 0
    reuse_raw = bool(getattr(args, "reuse_raw", False))
    while True:
        if stats.get("blocked"):
            return
        if deadline is not None and time.monotonic() > deadline:
            return
        try:
            meta = queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        mid = meta["match_provider_id"]
        comp = meta["competition_provider_id"]
        season = meta.get("season")
        record = None
        requested = False
        if reuse_raw and raw_dir is not None:
            cached, cached_at = _read_raw(raw_dir, mid)
            if cached is not None:
                try:
                    record = parse_match(cached, meta, cached_at or _utc_now())
                    stats["reused_raw"] = stats.get("reused_raw", 0) + 1
                except Exception:
                    record = None  # stale/unusable cache entry: fetch it again below
        if record is not None:
            sink.write(record)
            consecutive_failures = 0
        else:
            requested = True
            data, raw, kind, detail, attempts = await fetch_one(client, mid, throttle, args.max_retries)
            if data is not None:
                if raw_dir is not None and raw is not None:
                    _atomic_write_bytes(raw_dir / f"{mid}.json.gz", gzip.compress(raw, compresslevel=6))
                try:
                    sink.write(parse_match(data, meta, _utc_now()))
                    consecutive_failures = 0
                except ParseError as exc:
                    sink.error(mid, comp, "parse_" + str(exc), "", attempts, season=season)
                    consecutive_failures = 0  # the source answered; not a transport failure
                except Exception as exc:  # unexpected shape: keep going, log it
                    sink.error(mid, comp, "parse_exception", repr(exc), attempts, season=season)
            else:
                sink.error(mid, comp, kind or "unknown", detail, attempts, season=season)
                if kind in BLOCKED_KINDS:
                    stats["blocked"] = f"{kind}: {detail}"
                    print(f"[{name}] STOP: FotMob answered {kind} ({detail}); not working around it", flush=True)
                    return
                if kind != "http_404":
                    consecutive_failures += 1
        stats["done"] += 1
        if stats["done"] % 100 == 0:
            el = time.monotonic() - stats["t0"]
            where = f" at={comp}/{season}" if season else ""
            print(
                f"[{_utc_now()}] processed={stats['done']}/{stats['total']} ok={sink.ok} "
                f"failed={sink.failed} reused_raw={stats.get('reused_raw', 0)} rate={stats['done'] / el:.2f}/s{where}",
                flush=True,
            )
        if consecutive_failures >= args.max_consecutive_failures:
            print(f"[{name}] stopping after {consecutive_failures} consecutive failures", flush=True)
            return
        if requested:
            await asyncio.sleep(args.delay)


def _client(args: argparse.Namespace) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=args.base_url, timeout=httpx.Timeout(args.timeout), follow_redirects=True, headers=HEADERS
    )


async def _process_queue(
    todo: list[dict[str, Any]],
    args: argparse.Namespace,
    raw_dir: Path | None,
    sink: Sink,
    deadline: float | None,
    stats: dict[str, Any],
) -> int:
    """Run the workers over ``todo``; returns the number of matches left in the queue."""
    queue: asyncio.Queue = asyncio.Queue()
    for m in todo:
        queue.put_nowait(m)
    throttle = Throttle()
    max_workers, _min_delay = CAPS[getattr(args, "source", "db")]
    concurrency = max(1, min(max_workers, args.concurrency))
    async with _client(args) as client:
        workers = [
            asyncio.create_task(worker(f"w{i}", queue, client, sink, throttle, args, raw_dir, deadline, stats))
            for i in range(concurrency)
        ]
        await asyncio.gather(*workers)
    return queue.qsize()


async def load_fixture_matches(
    args: argparse.Namespace, comps: list[int], seasons: list[str], sink: Sink, stats: dict[str, Any]
) -> list[dict[str, Any]]:
    """Fixture-list metas for every (season, competition) in processing order (season first).

    A cached league response is reused; a missing one is fetched (shared limiter) and cached
    atomically. Unusable lists are logged to the errors file (match_provider_id = null)."""
    cache_dir = Path(args.leagues_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    throttle = Throttle()
    out: list[dict[str, Any]] = []
    queued: set[str] = set()
    async with _client(args) as client:
        for season in seasons:
            for comp in comps:
                data = read_cached_league(cache_dir, comp, season)
                origin = "cache"
                if data is None:
                    origin = "fetched"
                    data, raw, kind, detail, attempts = await fetch_json(
                        client, LEAGUES_ENDPOINT, {"id": comp, "season": season}, throttle, args.max_retries
                    )
                    if data is None:
                        sink.error(None, comp, f"league_{kind}", detail, attempts, season=season)
                        print(f"league {comp} {season}: FAILED {kind} {detail}", flush=True)
                        if kind in BLOCKED_KINDS:
                            stats["blocked"] = f"{kind}: {detail}"
                            print("STOP: FotMob blocked the league request; not working around it", flush=True)
                            return out
                        continue
                    _atomic_write_bytes(league_cache_path(cache_dir, comp, season), gzip.compress(raw, compresslevel=6))
                    await asyncio.sleep(args.delay)
                try:
                    metas, summary = parse_fixture_list(data, comp, season)
                except LeagueSeasonError as exc:
                    sink.error(None, comp, "league_unusable", str(exc), 0, season=season)
                    print(f"league {comp} {season} ({origin}): UNUSABLE {exc}", flush=True)
                    continue
                cross_dup = 0
                for m in metas:
                    if m["match_provider_id"] in queued:
                        cross_dup += 1
                        continue
                    queued.add(m["match_provider_id"])
                    out.append(m)
                print(
                    f"league {comp} {season} ({origin}): listed={summary['listed']} kept={summary['kept']} "
                    f"awarded={summary['awarded']} cancelled={summary['cancelled']} "
                    f"not_finished={summary['not_finished']} duplicates={summary['duplicates']} "
                    f"in_other_list={cross_dup}",
                    flush=True,
                )
    return out


async def run_collect(args: argparse.Namespace, comps: list[int]) -> dict[str, Any]:
    out_path, err_path = Path(args.output), Path(args.errors)
    raw_dir = None if args.no_raw else Path(args.raw_dir)
    if raw_dir is not None:
        raw_dir.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.max_minutes * 60 if args.max_minutes else None
    stats: dict[str, Any] = {"done": 0, "total": 0, "t0": time.monotonic(), "reused_raw": 0, "blocked": None}

    if getattr(args, "source", "db") == "fixtures":
        sink = Sink(out_path, err_path)  # opened first: league-level errors go to the errors file
        remaining = 0
        try:
            matches = await load_fixture_matches(args, comps, args.seasons_list, sink, stats)
            done = read_done_ids(out_path)
            todo = [m for m in matches if m["match_provider_id"] not in done]
            if args.limit:
                todo = todo[: args.limit]
            print(
                f"source=fixtures seasons={args.seasons_list} competitions={comps} "
                f"finished_in_fixture_lists={len(matches)} already_collected="
                f"{len(matches) - len([m for m in matches if m['match_provider_id'] not in done])} to_fetch={len(todo)}",
                flush=True,
            )
            stats["total"] = len(todo)
            stats["t0"] = time.monotonic()
            if todo and not stats["blocked"]:
                remaining = await _process_queue(todo, args, raw_dir, sink, deadline, stats)
        finally:
            sink.close()
        el = time.monotonic() - stats["t0"]
        print(
            f"finished: processed={stats['done']} ok={sink.ok} failed={sink.failed} "
            f"reused_raw={stats['reused_raw']} remaining_in_queue={remaining} elapsed={el:.0f}s "
            f"non_success_attempts={dict(HTTP_EVENTS)}"
            + (f" BLOCKED={stats['blocked']}" if stats["blocked"] else ""),
            flush=True,
        )
        return stats

    matches = load_matches(Path(args.db), comps)
    done = read_done_ids(out_path)
    todo = [m for m in matches if m["match_provider_id"] not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(
        f"competitions={comps} finished_in_db={len(matches)} already_collected="
        f"{len(matches) - len([m for m in matches if m['match_provider_id'] not in done])} to_fetch={len(todo)}",
        flush=True,
    )
    if not todo:
        return stats

    sink = Sink(out_path, err_path)
    stats["total"] = len(todo)
    try:
        remaining = await _process_queue(todo, args, raw_dir, sink, deadline, stats)
    finally:
        sink.close()
    el = time.monotonic() - stats["t0"]
    print(
        f"finished: processed={stats['done']} ok={sink.ok} failed={sink.failed} "
        f"remaining_in_queue={remaining} elapsed={el:.0f}s non_success_attempts={dict(HTTP_EVENTS)}"
        + (f" BLOCKED={stats['blocked']}" if stats["blocked"] else ""),
        flush=True,
    )
    return stats


def _fixture_metas_from_cache(args: argparse.Namespace, comps: list[int]) -> list[dict[str, Any]]:
    """Fixture-list metas from the cached league responses only (no network)."""
    metas: list[dict[str, Any]] = []
    queued: set[str] = set()
    for season in args.seasons_list:
        for comp in comps:
            data = read_cached_league(Path(args.leagues_dir), comp, season)
            if data is None:
                print(f"no cached fixture list for {comp} {season}: skipped")
                continue
            try:
                found, _summary = parse_fixture_list(data, comp, season)
            except LeagueSeasonError as exc:
                print(f"fixture list {comp} {season} unusable: {exc}")
                continue
            for m in found:
                if m["match_provider_id"] not in queued:
                    queued.add(m["match_provider_id"])
                    metas.append(m)
    return metas


def run_from_raw(args: argparse.Namespace, comps: list[int]) -> None:
    """Re-parse cached raw responses (no network). Writes a NEW output file."""
    raw_dir = Path(args.raw_dir)
    if getattr(args, "source", "db") == "fixtures":
        matches = _fixture_metas_from_cache(args, comps)
    else:
        matches = load_matches(Path(args.db), comps)
    out_path = Path(args.output)
    done = read_done_ids(out_path)
    sink = Sink(out_path, Path(args.errors))
    n = 0
    try:
        for meta in matches:
            mid = meta["match_provider_id"]
            f = raw_dir / f"{mid}.json.gz"
            if mid in done or not f.exists():
                continue
            data = json.loads(gzip.decompress(f.read_bytes()))
            fetched = datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
            try:
                sink.write(parse_match(data, meta, fetched))
                n += 1
            except ParseError as exc:
                sink.error(mid, meta["competition_provider_id"], "parse_" + str(exc), "", 0, season=meta.get("season"))
    finally:
        sink.close()
    print(f"re-parsed {n} matches from {raw_dir}")


# ------------------------------------------------------------------- coverage


def coverage(args: argparse.Namespace, comps: list[int]) -> str:
    db_matches = load_matches(Path(args.db), comps)
    in_db = defaultdict(int)
    for m in db_matches:
        in_db[m["competition_provider_id"]] += 1
    names = competition_names(Path(args.db), comps)

    agg: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    out_path = Path(args.output)
    seen: set[str] = set()
    if out_path.exists():
        with out_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                c = r.get("competition_provider_id")
                if c not in comps or r["match_provider_id"] in seen:
                    continue
                seen.add(r["match_provider_id"])
                a = agg[c]
                a["n"] += 1
                a["team_xg"] += int(r.get("home_xg") is not None and r.get("away_xg") is not None)
                ps = r.get("players") or []
                a["lineup"] += int(len(ps) > 0)
                a["ratings"] += int(any(p.get("rating") is not None for p in ps))
                a["player_xg"] += int(any(p.get("xg") is not None for p in ps))
                a["minutes"] += int(any(p.get("minutes_played") is not None for p in ps))
                a["mv"] += int(any(p.get("market_value") is not None for p in ps))
                a["players"] += len(ps)
                app = [p for p in ps if p.get("appeared")]
                a["appeared"] += len(app)
                a["appeared_rated"] += sum(1 for p in app if p.get("rating") is not None)
                a["unavail"] += int(len(r.get("unavailable") or []) > 0)
                a["db_mismatch"] += int(not all((r.get("db_check") or {}).values()))
    errs: dict[int, int] = defaultdict(int)
    err_path = Path(args.errors)
    if err_path.exists():
        with err_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("match_provider_id") not in seen:
                    errs[e.get("competition_provider_id")] += 1

    def pct(x: int, n: int) -> str:
        return f"{100.0 * x / n:.1f}%" if n else "-"

    lines = [
        "| FotMob id | Competition | Finished in DB | Collected | Error rows* | Line-up present | Team xG | Player ratings | Player xG | Player minutes | Market values | Rated appearances | Unavailable list | Avg players/match | Score/team mismatch vs DB |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    tot = defaultdict(int)
    for c in comps:
        a = agg.get(c, defaultdict(int))
        n = a["n"]
        lines.append(
            f"| {c} | {names.get(c)} | {in_db[c]} | {n} | {errs[c]} | {pct(a['lineup'], n)} | {pct(a['team_xg'], n)} | "
            f"{pct(a['ratings'], n)} | {pct(a['player_xg'], n)} | {pct(a['minutes'], n)} | {pct(a['mv'], n)} | "
            f"{pct(a['appeared_rated'], a['appeared'])} | {pct(a['unavail'], n)} | "
            f"{(a['players'] / n if n else 0):.1f} | {a['db_mismatch']} |"
        )
        tot["db"] += in_db[c]
        tot["err"] += errs[c]
        for k, v in a.items():
            tot[k] += v
    n = tot["n"]
    lines.append(
        f"| | **Total** | {tot['db']} | {n} | {tot['err']} | {pct(tot['lineup'], n)} | {pct(tot['team_xg'], n)} | "
        f"{pct(tot['ratings'], n)} | {pct(tot['player_xg'], n)} | {pct(tot['minutes'], n)} | {pct(tot['mv'], n)} | "
        f"{pct(tot['appeared_rated'], tot['appeared'])} | {pct(tot['unavail'], n)} | "
        f"{(tot['players'] / n if n else 0):.1f} | {tot['db_mismatch']} |"
    )
    lines.append("")
    lines.append(
        "Match-level columns (Team xG ... Market values) = share of collected matches where the value exists "
        "(team xG: both sides; player columns: at least one player). Rated appearances = share of players who "
        "appeared (starter or subbed on) with a rating. Unavailable list = share of matches with a non-empty "
        "injury/suspension list. *Error rows = error-file rows for matches still not collected."
    )
    return "\n".join(lines)


def coverage_history(args: argparse.Namespace, comps: list[int]) -> str:
    """Per competition-season coverage of the fixture-list output vs the cached fixture lists."""
    seasons = args.seasons_list
    leagues_dir = Path(args.leagues_dir)
    expected: dict[tuple[int, str], dict[str, dict[str, Any]] | None] = {}
    names: dict[int, str] = {}
    for season in seasons:
        for comp in comps:
            data = read_cached_league(leagues_dir, comp, season)
            if data is None:
                expected[(comp, season)] = None
                continue
            try:
                metas, _summary = parse_fixture_list(data, comp, season)
            except LeagueSeasonError:
                expected[(comp, season)] = None
                continue
            expected[(comp, season)] = {m["match_provider_id"]: m for m in metas}
            d = _league_payload(data).get("details") or {}
            names.setdefault(comp, f"{d.get('name')} ({d.get('country')})" if d.get("country") else str(d.get("name")))

    agg: dict[tuple[int, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    seen: set[str] = set()
    duplicates = 0
    out_path = Path(args.output)
    if out_path.exists():
        with out_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = (r.get("competition_provider_id"), r.get("season"))
                if key[0] not in comps or key[1] not in seasons:
                    continue
                mid = str(r.get("match_provider_id"))
                if mid in seen:
                    duplicates += 1
                    continue
                seen.add(mid)
                a = agg[key]
                a["n"] += 1
                exp = expected.get(key)
                meta = exp.get(mid) if exp else None
                if exp is not None and meta is None:
                    a["not_in_list"] += 1
                if meta is not None:
                    fh_, fa_ = _score_from_str(meta.get("fixture_score_str"))
                    teams_differ = (
                        r.get("home_team_provider_id") != meta.get("fixture_home_team_provider_id")
                        or r.get("away_team_provider_id") != meta.get("fixture_away_team_provider_id")
                    )
                    score_differs = fh_ is not None and (r.get("home_score"), r.get("away_score")) != (fh_, fa_)
                    a["mismatch"] += int(teams_differ or score_differs)
                    a["score_unchecked"] += int(fh_ is None)
                ps = r.get("players") or []
                a["lineup"] += int(len(ps) > 0)
                a["ratings"] += int(any(p.get("rating") is not None for p in ps))
                a["team_xg"] += int(r.get("home_xg") is not None and r.get("away_xg") is not None)
                a["player_xg"] += int(any(p.get("xg") is not None for p in ps))
                a["unavail"] += int(len(r.get("unavailable") or []) > 0)
                a["awarded"] += int(bool(r.get("awarded")))
                a["players"] += len(ps)
                app = [p for p in ps if p.get("appeared")]
                a["appeared"] += len(app)
                a["appeared_rated"] += sum(1 for p in app if p.get("rating") is not None)

    err_ids: dict[tuple[int, str], set[str]] = defaultdict(set)
    list_errors: dict[tuple[int, str], int] = defaultdict(int)
    err_path = Path(args.errors)
    if err_path.exists():
        with err_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = (e.get("competition_provider_id"), e.get("season"))
                if e.get("match_provider_id") is None:
                    list_errors[key] += 1
                elif str(e.get("match_provider_id")) not in seen:
                    err_ids[key].add(str(e.get("match_provider_id")))

    def pct(x: int, n: int) -> str:
        return f"{100.0 * x / n:.1f}%" if n else "-"

    header = (
        "| FotMob id | Competition | Season | Fixture list (finished, not cancelled) | Collected | Missing | "
        "Error ids* | Line-ups | Player ratings | Team xG | Player xG | Unavailable lists | Awarded | "
        "Rated appearances | Avg players/match | Mismatch vs fixture list |"
    )
    lines = [header, "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]

    def row(label_id: str, label: str, season: str, exp_n: Any, a: dict[str, int], missing: Any, errs: int) -> str:
        n = a["n"]
        return (
            f"| {label_id} | {label} | {season} | {exp_n} | {n} | {missing} | {errs} | {pct(a['lineup'], n)} | "
            f"{pct(a['ratings'], n)} | {pct(a['team_xg'], n)} | {pct(a['player_xg'], n)} | {pct(a['unavail'], n)} | "
            f"{a['awarded']} | {pct(a['appeared_rated'], a['appeared'])} | "
            f"{(a['players'] / n if n else 0):.1f} | {a['mismatch']} |"
        )

    grand: dict[str, int] = defaultdict(int)
    grand_exp = grand_missing = grand_err = 0
    for season in seasons:
        sub: dict[str, int] = defaultdict(int)
        sub_exp = sub_missing = sub_err = 0
        for comp in comps:
            key = (comp, season)
            exp = expected.get(key)
            a = agg.get(key, defaultdict(int))
            if exp is None:
                exp_n: Any = "no list" + (f" ({list_errors[key]} list errors)" if list_errors.get(key) else "")
                missing: Any = "?"
            else:
                exp_n = len(exp)
                missing = len([m for m in exp if m not in seen])
                sub_exp += exp_n
                sub_missing += missing
            errs = len(err_ids.get(key, set()))
            sub_err += errs
            lines.append(row(str(comp), names.get(comp, "?"), season, exp_n, a, missing, errs))
            for k, v in a.items():
                sub[k] += v
        lines.append(row("", f"**Subtotal {season}**", season, sub_exp, sub, sub_missing, sub_err))
        for k, v in sub.items():
            grand[k] += v
        grand_exp += sub_exp
        grand_missing += sub_missing
        grand_err += sub_err
    lines.append(row("", "**Total**", "all", grand_exp, grand, grand_missing, grand_err))
    lines.append("")
    lines.append(
        f"Duplicate match ids in the output: {duplicates}. Rows whose id is not in the cached fixture list: "
        f"{sum(a['not_in_list'] for a in agg.values())}. Matches whose fixture-list score could not be parsed "
        f"(not compared): {sum(a['score_unchecked'] for a in agg.values())}."
    )
    lines.append(
        "Fixture list = `fixtures.allMatches` of the cached `/api/data/leagues` response, finished and not "
        "cancelled. Line-ups / Player ratings / Player xG = share of collected matches with at least one player "
        "row / rated player / player xG value; Team xG = both sides present; Unavailable lists = non-empty "
        "injury/suspension list; Awarded = count of matches flagged awarded (the score is the awarded score; "
        "player stats exist only when the match was actually played before it was awarded). Rated "
        "appearances = share of players who appeared (starter or subbed on) with a rating. Mismatch = home/away "
        "team id or score differs from the fixture list. *Error ids = distinct still-missing match ids with at "
        "least one row in the errors file."
    )
    return "\n".join(lines)


# ------------------------------------------------------------------- CLI


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--competitions",
        default="A",
        help="Comma-separated FotMob league ids, or the predefined sets 'A', 'B', 'TARGET13' (default A)",
    )
    ap.add_argument(
        "--source",
        choices=sorted(CAPS),
        default="db",
        help="where match ids come from: 'db' (FINISHED DB matches, default) or 'fixtures' (FotMob season fixture lists)",
    )
    ap.add_argument(
        "--seasons",
        default=DEFAULT_SEASONS,
        help=f"--source fixtures: comma-separated seasons in processing order (default {DEFAULT_SEASONS})",
    )
    ap.add_argument("--leagues-dir", default=str(DEFAULT_LEAGUES_DIR), help="--source fixtures: league response cache")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--output", default=None, help="default: fotmob_match_details.jsonl (db) / _history.jsonl (fixtures)")
    ap.add_argument("--errors", default=None, help="default: fotmob_details_errors.jsonl (db) / _history_errors (fixtures)")
    ap.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR), help="gzip cache of raw responses")
    ap.add_argument("--no-raw", action="store_true", help="do not keep raw responses")
    ap.add_argument(
        "--no-reuse-raw",
        action="store_true",
        help="--source fixtures: always fetch, even when the raw cache already holds the match",
    )
    ap.add_argument("--base-url", default=None, help="default: settings.fotmob_base_url")
    ap.add_argument("--concurrency", type=int, default=3, help="workers, clamped to 1..3 (db) / 1..2 (fixtures)")
    ap.add_argument(
        "--delay", type=float, default=0.3, help="seconds between requests per worker (min 0.3 db / 0.4 fixtures)"
    )
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--max-retries", type=int, default=4)
    ap.add_argument("--max-consecutive-failures", type=int, default=5)
    ap.add_argument("--max-minutes", type=float, default=0, help="stop starting new matches after N minutes")
    ap.add_argument("--limit", type=int, default=0, help="fetch at most N matches (testing)")
    ap.add_argument("--from-raw", action="store_true")
    ap.add_argument("--coverage", action="store_true")
    args = ap.parse_args(argv)
    max_workers, min_delay = CAPS[args.source]
    args.delay = max(min_delay, args.delay)
    args.concurrency = max(1, min(max_workers, args.concurrency))
    fixtures = args.source == "fixtures"
    if args.output is None:
        args.output = str(DEFAULT_HISTORY_OUT if fixtures else DEFAULT_OUT)
    if args.errors is None:
        args.errors = str(DEFAULT_HISTORY_ERR if fixtures else DEFAULT_ERR)
    args.seasons_list = parse_seasons(args.seasons)
    args.reuse_raw = fixtures and not args.no_reuse_raw
    if args.base_url is None:
        args.base_url = _base_url()
    return args


def parse_competitions(spec: str) -> list[int]:
    out: list[int] = []
    for tok in spec.split(","):
        tok = tok.strip()
        if not tok:
            continue
        ids = NAMED_SETS.get(tok.upper(), None)
        for i in ids if ids is not None else [int(tok)]:
            if i not in out:
                out.append(i)
    return out


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    comps = parse_competitions(args.competitions)
    if args.coverage:
        print(coverage_history(args, comps) if args.source == "fixtures" else coverage(args, comps))
        return 0
    if args.from_raw:
        run_from_raw(args, comps)
        return 0
    stats = asyncio.run(run_collect(args, comps))
    return 2 if stats.get("blocked") else 0


if __name__ == "__main__":
    sys.exit(main())
