"""Past-season football-data.co.uk odds mapped to FotMob match ids (history build).

TRAINING DATA COLLECTOR - real third-party data; nothing is generated, imputed or
defaulted. A value the source does not send stays empty; a row that cannot be
mapped with certainty keeps an empty FotMob id and is listed with its reason.

Purpose: closing (and pre-closing) odds for the seasons 2021/22 .. 2025/26, so that
models trained on those seasons can be benchmarked against the closing market.
Those seasons are not in the production DB, so rows are mapped to FotMob match ids
through FotMob's own league fixture lists.

Sources
  * football-data.co.uk season files mmz4281/<2122..2425>/<div>.csv for the 14
    divisions in FOTMOB_LEAGUE. The origin times out from this network, so the
    Internet Archive copy is used: one CDX listing per season
    (web.archive.org/cdx/search/cdx?url=football-data.co.uk/mmz4281/<season>/&matchType=prefix)
    -> latest HTTP-200 capture of each file -> web.archive.org/web/<ts>id_/<url>
    (the untouched archived body). At most 1 archive request per second.
    Raw bodies: data/external/raw/football_data/<season>/<div>.csv.gz (gzip),
    CDX listings: raw/football_data/cdx/<season>.json.gz, snapshot timestamps and
    row counts: raw/football_data/manifest.json.
  * 2025/26: the files already cached by the current-season pipeline
    (raw/football_data/2526/<div>.csv, the input of football_data_matches.csv, left
    untouched) are re-checked against a fresh CDX listing. A later capture is stored
    as raw/football_data/2526_latest/<div>.csv.gz; the build uses whichever file has
    more rows (a complete season replaces a partial one).
  * FotMob league fixture lists (/api/data/leagues?id=<league>&season=<YYYY/YYYY>),
    cached as the untouched gzip response body in
    data/raw_cache/fotmob_leagues/<league>_<YYYY-YYYY>.json.gz (shared with other
    collectors). Fetched only when missing, one request at a time, each one after
    fotmob_rate.acquire(). A 403 / captcha / challenge page stops all FotMob fetching.

Mapping (per division-season; see map_teams / map_rows)
  1. Team names. Anchors: the verified football_data -> DB team map in
     team_name_map.csv (DB teams.provider_id = FotMob team id), kept only when the
     FotMob team plays in that league-season and the fixture list confirms it.
     Remaining names: opponent-consistent votes (a match against an already mapped
     opponent points at the FotMob team that met that opponent, same venue, within
     +-1 day), then, if still needed, score-based fixture overlap. Every accepted
     name must then find >= 90% of its matches as exact FotMob (home, away) pairs.
  2. Rows. The FotMob fixture of the mapped (home id, away id) pair within +-1 day
     of the football-data date; exactly one candidate is required.
  Scores are compared afterwards (score_agrees) and are never used to pick a row.

Outputs (data/external/)
  football_data_history.csv            one row per football-data match
  football_data_history_unmapped.csv   rows without a FotMob match id, with the reason
  football_data_history_coverage.json  per division-season numbers (+ markdown table)
  team_name_map.csv / team_name_unmapped.csv   rows with source=football_data_fotmob

Usage (from backend/):
  venv/Scripts/python.exe -I scripts/data_collection/collect_football_data.py --history
  venv/Scripts/python.exe -I scripts/data_collection/collect_football_data.py --history --skip-download
  venv/Scripts/python.exe -I scripts/data_collection/football_data_history.py --spot-check 20 --skip-download
"""
from __future__ import annotations

import argparse
import base64
import csv
import gzip
import hashlib
import io
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_football_data as cfd  # noqa: E402  (CSV parsing + odds preference lists: same method)
import fotmob_rate  # noqa: E402
from external_common import (  # noqa: E402
    BACKEND_DIR,
    EXTERNAL_DIR,
    TEAM_MAP_FIELDS,
    TEAM_MAP_PATH,
    UNMAPPED_FIELDS,
    UNMAPPED_PATH,
    USER_AGENT,
    db_connect,
    load_manifest,
    name_similarity,
    read_team_map,
)

HISTORY_SEASONS = ["2122", "2223", "2324", "2425"]
RECHECK_SEASON = "2526"
ALL_SEASONS = HISTORY_SEASONS + [RECHECK_SEASON]

# football-data division -> FotMob league id (verified against competitions.provider_id)
FOTMOB_LEAGUE: dict[str, int] = {
    "E0": 47, "SP1": 87, "I1": 55, "D1": 54, "F1": 53, "N1": 57, "P1": 61, "B1": 40, "T1": 71,
    "E1": 48, "SP2": 140, "I2": 86, "D2": 146, "F2": 110,
}
TOP_DIVISIONS = ("E0", "SP1", "I1", "D1", "F1", "N1", "P1", "B1", "T1")
SECOND_DIVISIONS = ("E1", "SP2", "I2", "D2", "F2")

FD_RAW = cfd.FD_RAW
MANIFEST = cfd.MANIFEST
CDX_DIR = FD_RAW / "cdx"
LATEST_DIR = FD_RAW / f"{RECHECK_SEASON}_latest"
FOTMOB_LEAGUE_DIR = BACKEND_DIR / "data" / "raw_cache" / "fotmob_leagues"
OUT_HISTORY = EXTERNAL_DIR / "football_data_history.csv"
OUT_UNMAPPED_ROWS = EXTERNAL_DIR / "football_data_history_unmapped.csv"
OUT_COVERAGE = EXTERNAL_DIR / "football_data_history_coverage.json"
FD_MATCHES = EXTERNAL_DIR / "football_data_matches.csv"
TEAM_SOURCE = "football_data_fotmob"

ARCHIVE_CDX = "https://web.archive.org/cdx/search/cdx"
WAYBACK_RAW = "https://web.archive.org/web/{ts}id_/{url}"
FOTMOB_BASE = "https://www.fotmob.com"
# Same User-Agent as collect_fotmob_details.py
FOTMOB_HEADERS = {"User-Agent": "Mozilla/5.0 (TUTAR X research collector; low-rate)", "Accept": "application/json"}

# Pre-closing O/U 2.5, same preference/normalisation method as cfd.CLOSE_OU25
PRE_OU25 = [("P>2.5", "P<2.5"), ("Avg>2.5", "Avg<2.5"), ("B365>2.5", "B365<2.5")]
# Original odds columns behind the four probability sets (every column the preference lists can use)
ODDS_COLUMNS = [c for prefs in (cfd.CLOSE_1X2, cfd.CLOSE_OU25, cfd.PRE_1X2, PRE_OU25) for cols in prefs for c in cols]

OUT_FIELDS = (
    ["season", "division", "country", "league", "fotmob_league_id", "fotmob_season", "fd_file", "fd_snapshot",
     "fd_file_complete", "date", "time", "home", "away", "FTHG", "FTAG", "FTR",
     "map_status", "fotmob_match_id", "fotmob_home_id", "fotmob_away_id", "fotmob_home_name", "fotmob_away_name",
     "fotmob_utc_time", "fotmob_round", "fotmob_home_score", "fotmob_away_score", "fotmob_awarded", "score_agrees",
     "close_1x2_source", "p_close_home", "p_close_draw", "p_close_away", "close_1x2_overround",
     "close_ou25_source", "p_close_over25", "p_close_under25", "close_ou25_overround",
     "pre_1x2_source", "p_pre_home", "p_pre_draw", "p_pre_away", "pre_1x2_overround",
     "pre_ou25_source", "p_pre_over25", "p_pre_under25", "pre_ou25_overround"]
    + ODDS_COLUMNS
)
UNMAPPED_ROW_FIELDS = ["season", "division", "date", "time", "home", "away", "FTHG", "FTAG", "map_status", "reason",
                       "home_fotmob_id", "away_fotmob_id", "nearest_pair_fixture_id", "nearest_pair_fixture_utc",
                       "nearest_pair_fixture_score"]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fotmob_season(season: str) -> str:
    """football-data season code -> FotMob season string: '2122' -> '2021/2022'."""
    if not re.fullmatch(r"\d{4}", season):
        raise ValueError(f"bad season code {season!r}")
    return f"20{season[:2]}/20{season[2:]}"


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write via a temp file in the same directory + os.replace (never a half-written file)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def save_manifest(manifest: dict) -> None:
    text = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False)
    atomic_write_bytes(MANIFEST, text.encode("utf-8"))


def wayback_digest(body: bytes) -> str:
    """The Internet Archive's content digest (base32 SHA-1 of the body)."""
    return base64.b32encode(hashlib.sha1(body).digest()).decode("ascii")


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(BACKEND_DIR).as_posix()
    except ValueError:
        return path.as_posix()


def parse_score(text: Any) -> tuple[int, int] | None:
    """FotMob scoreStr '2 - 1' -> (2, 1); anything else -> None."""
    m = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", str(text or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _blank(v: Any) -> Any:
    return "" if v is None else v


# ---------------------------------------------------------------------------
# football-data.co.uk rows
# ---------------------------------------------------------------------------


@dataclass
class FdRow:
    season: str
    division: str
    day: date
    time: str
    home: str
    away: str
    hg: int | None
    ag: int | None
    ftr: str
    raw: dict = field(repr=False, default_factory=dict)


def parse_fd_rows(raw_rows: Iterable[dict], season: str, division: str) -> tuple[list[FdRow], int]:
    """Main-league file rows -> FdRow. Returns (rows, number of non-blank rows skipped)."""
    out: list[FdRow] = []
    skipped = 0
    for r in raw_rows:
        d = cfd._parse_date(r.get("Date", ""))
        if not d or not r.get("HomeTeam") or not r.get("AwayTeam"):
            if any(v for v in r.values()):
                skipped += 1
            continue
        out.append(FdRow(season, division, d, r.get("Time", ""), r["HomeTeam"], r["AwayTeam"],
                         cfd._int(r.get("FTHG")), cfd._int(r.get("FTAG")), r.get("FTR", ""), r))
    return out, skipped


def _csv_dicts(body: bytes) -> list[dict]:
    """CSV bytes -> stripped dict rows (same decoding as cfd._read_csv)."""
    rows = csv.DictReader(io.StringIO(_decode(body)))
    return [{(k or "").strip(): (v or "").strip() for k, v in r.items() if k} for r in rows]


def fd_sources(season: str, div: str, manifest: dict) -> list[tuple[str, Path, str | None, Any]]:
    """Every cached source of one division-season: (source key, raw path, snapshot, loader), preferred first."""
    out: list[tuple[str, Path, str | None, Any]] = []
    if season == RECHECK_SEASON:
        prim = [(FD_RAW / season / f"{div}.csv", f"{season}/{div}"),
                (LATEST_DIR / f"{div}.csv.gz", f"{season}_latest/{div}")]
    else:
        prim = [(FD_RAW / season / f"{div}.csv.gz", f"{season}/{div}")]
    for path, key in prim:
        if path.exists():
            out.append((key, path, manifest.get(key, {}).get("wayback_snapshot"),
                        lambda p=path: cfd._read_csv(p)))
    for name in bundle_names(season):
        key = f"{season}/bundle/{name}"
        path = bundle_path(season, name)
        if path.exists():
            out.append((f"{key}#{div}", path, manifest.get(key, {}).get("wayback_snapshot"),
                        lambda p=path, n=name: bundle_division_dicts(gzip.decompress(p.read_bytes()), n, div)))
    return out


def load_fd_file(season: str, div: str, manifest: dict) -> tuple[list[FdRow], dict]:
    """Rows of the most complete cached source for (season, div) and a description of it.

    Candidates: the per-division file (2025/26: also the re-checked later snapshot) and
    the division inside an archived season bundle (data.zip / all-euro-data xlsx).
    The one with the most rows is used; ties keep the earlier (per-division) source.
    """
    best = None
    considered = []
    for key, path, snapshot, loader in fd_sources(season, div, manifest):
        dicts = loader()
        if dicts is None:  # bundle without this division
            continue
        rows, skipped = parse_fd_rows(dicts, season, div)
        considered.append({"key": key, "rows": len(rows), "snapshot": snapshot})
        if best is None or len(rows) > len(best[0]):
            best = (rows, skipped, path, key, snapshot)
    if best is None:
        return [], {"status": "missing", "manifest": manifest.get(f"{season}/{div}", {}), "candidates": considered}
    rows, skipped, path, key, snapshot = best
    entry = manifest.get(key.split("#")[0], {})
    teams = {r.home for r in rows} | {r.away for r in rows}
    return rows, {
        "status": "ok", "path": rel(path), "manifest_key": key, "snapshot": snapshot,
        "fetched_via": entry.get("fetched_via"), "rows": len(rows), "rows_skipped": skipped,
        "n_teams": len(teams), "double_round_robin_matches": len(teams) * (len(teams) - 1),
        # False = partial season file (fewer matches than a full double round robin), same rule as summarize_rows
        "complete": bool(rows) and len(rows) >= len(teams) * (len(teams) - 1),
        "first_date": min(r.day for r in rows).isoformat() if rows else None,
        "last_date": max(r.day for r in rows).isoformat() if rows else None,
        "candidates": considered,
    }


# ---------------------------------------------------------------------------
# Season bundles (data.zip with every division CSV; all-euro-data xlsx with one sheet per division)
# ---------------------------------------------------------------------------

_XLSX_NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def bundle_names(season: str) -> list[str]:
    return ["data.zip", f"all-euro-data-20{season[:2]}-20{season[2:]}.xlsx"]


def bundle_path(season: str, name: str) -> Path:
    return FD_RAW / season / "bundles" / f"{name}.gz"


def _col_index(ref: str) -> int:
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def _num_text(text: str) -> str:
    f = float(text)
    return str(int(f)) if f.is_integer() and abs(f) < 1e15 else repr(f)


def xlsx_sheet_dicts(raw: bytes, sheet: str) -> list[dict] | None:
    """One worksheet as CSV-like {header: text} rows; None when the sheet does not exist.

    Stdlib only (zipfile + ElementTree). Excel keeps dates as day serials and times as
    day fractions: Date/Time cells become the CSV text forms dd/mm/yyyy and HH:MM;
    other numbers become their shortest text form (1.9099999999999999 -> 1.91).
    """
    import xml.etree.ElementTree as ET
    import zipfile

    m = "{%s}" % _XLSX_NS["m"]
    z = zipfile.ZipFile(io.BytesIO(raw))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    targets = {r.get("Id"): r.get("Target") for r in rels}
    rid = next((s.get("{%s}id" % _XLSX_NS["r"]) for s in wb.iter(f"{m}sheet")
                if (s.get("name") or "").strip().lower() == sheet.lower()), None)
    if rid is None or rid not in targets:
        return None
    target = targets[rid]
    path = target.lstrip("/") if target.startswith("/") else "xl/" + target
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{m}si"):
            shared.append("".join(t.text or "" for t in si.iter(f"{m}t")))
    grid: list[dict[int, Any]] = []
    for row in ET.fromstring(z.read(path)).iter(f"{m}row"):
        cells: dict[int, Any] = {}
        col = -1
        for c in row.findall(f"{m}c"):
            ref = c.get("r")
            col = _col_index(ref) if ref else col + 1
            t, v = c.get("t"), c.find(f"{m}v")
            text = v.text if v is not None and v.text is not None else ""
            if t == "s":
                cells[col] = shared[int(text)] if text else ""
            elif t == "inlineStr":
                cells[col] = "".join(x.text or "" for x in c.iter(f"{m}t"))
            elif t in ("str", "b", "e"):
                cells[col] = text
            else:
                cells[col] = ("num", text) if text else ""
        grid.append(cells)
    if not grid:
        return []
    header = {i: (v[1] if isinstance(v, tuple) else str(v)).strip() for i, v in grid[0].items()}
    out: list[dict] = []
    for cells in grid[1:]:
        d: dict[str, str] = {}
        for i, name in header.items():
            if not name:
                continue
            v = cells.get(i, "")
            if isinstance(v, tuple):
                num = float(v[1])
                if name == "Date":
                    v = (datetime(1899, 12, 30) + timedelta(days=num)).strftime("%d/%m/%Y")
                elif name == "Time":
                    mins = round((num % 1) * 1440)
                    v = f"{mins // 60:02d}:{mins % 60:02d}"
                else:
                    v = _num_text(v[1])
            d[name] = str(v).strip()
        out.append(d)
    return out


def bundle_division_dicts(raw: bytes, name: str, div: str) -> list[dict] | None:
    """The rows of one division inside a season bundle; None when the bundle lacks it."""
    import zipfile

    if name.endswith(".zip"):
        z = zipfile.ZipFile(io.BytesIO(raw))
        member = next((n for n in z.namelist() if n.replace("\\", "/").split("/")[-1].lower() == f"{div}.csv".lower()),
                      None)
        return _csv_dicts(z.read(member)) if member else None
    return xlsx_sheet_dicts(raw, div)


# ---------------------------------------------------------------------------
# Internet Archive / origin download
# ---------------------------------------------------------------------------


class ArchiveClient:
    """GETs with a minimum interval between request starts (<= 1 request/s to the archive)."""

    def __init__(self, min_interval: float):
        self.min_interval = max(1.0, float(min_interval))
        self._last = 0.0
        self.requests = 0

    def get(self, url: str, timeout: float = 90.0, retries: int = 4) -> tuple[bytes, str]:
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            wait = self._last + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            self.requests += 1
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.read(), resp.geturl()
            except urllib.error.HTTPError as exc:
                last_exc = exc
                if exc.code in (403, 404, 410):
                    raise
                pause = (60.0 if exc.code == 429 else 10.0) * attempt
            except Exception as exc:  # timeouts, connection resets
                last_exc = exc
                pause = 5.0 * attempt
            print(f"[archive] {url[:140]}: {last_exc!r}; retry {attempt}/{retries} in {pause:.0f}s", flush=True)
            time.sleep(pause)
        assert last_exc is not None
        raise last_exc


def cdx_listing(archive: ArchiveClient, season: str, refresh: bool) -> list[dict]:
    """All archive captures under football-data.co.uk/mmz4281/<season>/ (www and non-www, http and https)."""
    path = CDX_DIR / f"{season}.json.gz"
    if path.exists() and not refresh:
        body = gzip.decompress(path.read_bytes())
    else:
        query = urllib.parse.urlencode({
            "url": f"football-data.co.uk/mmz4281/{season}/", "matchType": "prefix", "output": "json",
            "fl": "timestamp,original,statuscode,mimetype,length,digest",
        })
        body, _ = archive.get(f"{ARCHIVE_CDX}?{query}", timeout=120)
        atomic_write_bytes(path, gzip.compress(body, compresslevel=6))
    data = json.loads(body) if body.strip() else []
    if not data:
        return []
    head = data[0]
    return [dict(zip(head, r)) for r in data[1:]]


def file_captures(captures: list[dict], season: str, div: str | None, name: str | None = None) -> list[dict]:
    """Replayable captures of mmz4281/<season>/<div>.csv (or <name>), newest first.

    HTTP-200 captures, plus 'warc/revisit' records whose digest equals one of those
    200 captures (the archive's de-duplicated re-captures of identical content).
    """
    target = f"/mmz4281/{season}/{name or f'{div}.csv'}".lower()
    mine = [c for c in captures if urllib.parse.urlsplit(c.get("original", "")).path.lower() == target]
    ok_digests = {c.get("digest") for c in mine if c.get("statuscode") == "200"}
    ok = [c for c in mine if c.get("statuscode") == "200"
          or (c.get("mimetype") == "warc/revisit" and c.get("digest") in ok_digests)]
    return sorted(ok, key=lambda c: c["timestamp"], reverse=True)


def _snapshot_of(final_url: str | None) -> str | None:
    if final_url and "/web/" in final_url:
        return final_url.split("/web/")[1].split("id_")[0]
    return None


def summarize_rows(dicts: list[dict] | None, season: str, div: str) -> dict:
    """Row count, date range and a completeness flag (>= n_teams*(n_teams-1) matches, a full double round robin)."""
    rows, skipped = parse_fd_rows(dicts or [], season, div)
    teams = {r.home for r in rows} | {r.away for r in rows}
    expected = len(teams) * (len(teams) - 1)
    return {"n_rows": len(rows), "rows_skipped": skipped, "n_teams": len(teams),
            "double_round_robin_matches": expected, "complete": bool(rows) and len(rows) >= expected,
            "first_date": min(r.day for r in rows).isoformat() if rows else None,
            "last_date": max(r.day for r in rows).isoformat() if rows else None}


def _csv_summary(body: bytes, season: str, div: str) -> dict:
    return summarize_rows(_csv_dicts(body), season, div)


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def origin_reachable() -> bool:
    url = f"{cfd.ORIGIN}/mmz4281/{HISTORY_SEASONS[0]}/E0.csv"
    try:
        body, _ = cfd._fetch(url, timeout=15)
        return cfd._looks_like_csv(body)
    except Exception as exc:  # the origin times out from this network (2026-10-13)
        print(f"[origin] {url}: {exc!r} -> using the Internet Archive", flush=True)
        return False


def download_history_file(archive: ArchiveClient, manifest: dict, season: str, div: str, captures: list[dict],
                          origin_ok: bool, max_tries: int = 4) -> bool:
    """Fetch mmz4281/<season>/<div>.csv; returns True when the cached file is a complete season.

    Captures are tried newest first. The archive sometimes serves an older capture than
    the one requested (an unreplayable record falls back to the nearest one), so a
    partial body makes the next capture be tried; the file with the most rows is kept.
    Tried capture timestamps are stored in the manifest so a re-run only tries new ones.
    """
    key = f"{season}/{div}"
    path = FD_RAW / season / f"{div}.csv.gz"
    url = f"{cfd.ORIGIN}/mmz4281/{season}/{div}.csv"
    prev = manifest.get(key, {})
    best: tuple[int, bytes | None, dict] | None = None
    if path.exists():
        body = gzip.decompress(path.read_bytes())
        summ = _csv_summary(body, season, div)
        if summ["complete"]:
            if not prev.get("complete"):
                prev.update(summ)
                manifest[key] = prev
                save_manifest(manifest)
            return True
        best = (summ["n_rows"], None, {**prev, **summ})  # None body = keep the cached file
    if origin_ok:
        try:
            body, final_url = archive.get(url, timeout=30)
            if cfd._looks_like_csv(body):
                summ = _csv_summary(body, season, div)
                if best is None or summ["n_rows"] > best[0]:
                    atomic_write_bytes(path, gzip.compress(body, compresslevel=6))
                    manifest[key] = {"url": url, "fetched_via": "origin", "effective_url": final_url,
                                     "wayback_snapshot": None, "bytes": len(body), "sha1_b32": wayback_digest(body),
                                     "fetched_at": utc_now(), "status": "ok", "raw_path": rel(path), **summ}
                    save_manifest(manifest)
                    print(f"[ok] {key} via origin rows={summ['n_rows']}", flush=True)
                    return summ["complete"]
        except Exception as exc:
            print(f"[origin] {key}: {exc!r}; trying the archive", flush=True)
    tried = set(prev.get("tried_captures", []))
    for k in ("cdx_timestamp", "wayback_snapshot"):
        if prev.get(k):
            tried.add(prev[k])
    # an older capture than the cached file's served snapshot cannot hold more matches
    floor = (prev.get("wayback_snapshot") or "") if best is not None else ""
    caps = [c for c in file_captures(captures, season, div) if c["timestamp"] not in tried and c["timestamp"] > floor]
    for cap in caps[:max_tries]:
        tried.add(cap["timestamp"])
        try:
            body, final_url = archive.get(WAYBACK_RAW.format(ts=cap["timestamp"], url=cap["original"]))
        except urllib.error.HTTPError as exc:
            print(f"[archive] {key} @{cap['timestamp']}: HTTP {exc.code}", flush=True)
            continue
        except Exception as exc:
            print(f"[archive] {key} @{cap['timestamp']}: {exc!r}", flush=True)
            continue
        if not cfd._looks_like_csv(body):
            print(f"[archive] {key} @{cap['timestamp']}: body is not a football-data CSV", flush=True)
            continue
        served = _snapshot_of(final_url) or cap["timestamp"]
        tried.add(served)
        summ = _csv_summary(body, season, div)
        entry = {"url": url, "fetched_via": "wayback", "effective_url": final_url, "wayback_snapshot": served,
                 "cdx_timestamp": cap["timestamp"], "cdx_digest": cap.get("digest"), "sha1_b32": wayback_digest(body),
                 "bytes": len(body), "fetched_at": utc_now(), "status": "ok", "raw_path": rel(path), **summ}
        print(f"[archive] {key} requested @{cap['timestamp']} served @{served}: rows={summ['n_rows']} "
              f"{summ['first_date']}..{summ['last_date']} complete={summ['complete']}", flush=True)
        if best is None or summ["n_rows"] > best[0]:
            best = (summ["n_rows"], body, entry)
        if summ["complete"]:
            break
    if best is None:
        manifest[key] = {"url": url, "status": "unavailable", "checked_at": utc_now(), "tried_captures": sorted(tried),
                         "reason": "no replayable CSV capture in the Internet Archive"}
        save_manifest(manifest)
        print(f"[archive] {key}: unavailable", flush=True)
        return False
    n, body, entry = best
    if body is not None:
        atomic_write_bytes(path, gzip.compress(body, compresslevel=6))
    entry["tried_captures"] = sorted(tried)
    entry["n_captures_replayable"] = len(file_captures(captures, season, div))
    manifest[key] = entry
    save_manifest(manifest)
    if body is not None:
        print(f"[ok] {key} snapshot={entry['wayback_snapshot']} rows={n} complete={entry['complete']}", flush=True)
    return bool(entry.get("complete"))


def download_bundles(archive: ArchiveClient, manifest: dict, season: str, captures: list[dict],
                     problems: dict[str, str]) -> None:
    """Fetch archived season bundles (newest first) while some division file is missing or partial.

    problems: division -> snapshot timestamp of its best per-division file ('' when none).
    A bundle captured before that snapshot cannot hold more matches and is skipped.
    """
    bundles = []
    for name in bundle_names(season):
        caps = file_captures(captures, season, None, name=name)
        if caps:
            bundles.append((caps[0]["timestamp"], name, caps[0]))
    for ts, name, cap in sorted(bundles, reverse=True):
        open_divs = {d: snap for d, snap in problems.items() if not snap or ts > snap}
        if not open_divs:
            print(f"[bundle] {season}/{name} @{ts}: not newer than the partial files; skipped", flush=True)
            continue
        key = f"{season}/bundle/{name}"
        path = bundle_path(season, name)
        if path.exists() and manifest.get(key, {}).get("cdx_timestamp") == cap["timestamp"]:
            raw = gzip.decompress(path.read_bytes())
        else:
            try:
                raw, final_url = archive.get(WAYBACK_RAW.format(ts=cap["timestamp"], url=cap["original"]), timeout=240)
            except Exception as exc:
                print(f"[bundle] {key} @{ts}: {exc!r}", flush=True)
                continue
            if raw[:2] != b"PK":
                print(f"[bundle] {key} @{ts}: not a zip container; skipped", flush=True)
                continue
            atomic_write_bytes(path, gzip.compress(raw, compresslevel=6))
            manifest[key] = {"url": f"{cfd.ORIGIN}/mmz4281/{season}/{name}", "fetched_via": "wayback",
                             "effective_url": final_url, "wayback_snapshot": _snapshot_of(final_url) or ts,
                             "cdx_timestamp": cap["timestamp"], "cdx_digest": cap.get("digest"),
                             "sha1_b32": wayback_digest(raw), "bytes": len(raw), "fetched_at": utc_now(),
                             "status": "ok", "raw_path": rel(path)}
        per_div = {}
        for d in sorted(problems):
            dicts = bundle_division_dicts(raw, name, d)
            per_div[d] = summarize_rows(dicts, season, d) if dicts is not None else None
            if per_div[d] and per_div[d]["complete"]:
                problems.pop(d, None)
        manifest.setdefault(key, {})["divisions_checked"] = per_div
        save_manifest(manifest)
        print(f"[bundle] {key} @{manifest[key].get('wayback_snapshot')}: " + ", ".join(
            f"{d}={'-' if s is None else s['n_rows']}{'' if not s or not s['complete'] else ' complete'}"
            for d, s in per_div.items()), flush=True)
        if not problems:
            break


def recheck_current_season(archive: ArchiveClient, manifest: dict, div: str, captures: list[dict]) -> None:
    """Look for a 2025/26 capture newer than the file behind football_data_matches.csv."""
    season = RECHECK_SEASON
    key_old, key_new = f"{season}/{div}", f"{season}_latest/{div}"
    old_path = FD_RAW / season / f"{div}.csv"
    old = manifest.get(key_old, {})
    old_ts = old.get("wayback_snapshot") or ""
    old_body = old_path.read_bytes() if old_path.exists() else b""
    old_rows = _csv_summary(old_body, season, div)["n_rows"] if old_body else 0
    caps = file_captures(captures, season, div)
    entry: dict[str, Any] = {
        "url": f"{cfd.ORIGIN}/mmz4281/{season}/{div}.csv", "checked_at": utc_now(), "previous_key": key_old,
        "previous_snapshot": old_ts or None, "previous_rows": old_rows, "n_captures_200": len(caps),
        "latest_capture": caps[0]["timestamp"] if caps else None,
    }
    old_digest = wayback_digest(old_body) if old_body else None
    old_complete = _csv_summary(old_body, season, div)["complete"] if old_body else False
    prev = manifest.get(key_new, {})
    latest_path = LATEST_DIR / f"{div}.csv.gz"
    have_ts = max(old_ts, prev.get("wayback_snapshot") or "") if latest_path.exists() else old_ts
    later = [c for c in caps if c["timestamp"][:14] > have_ts[:14] and c.get("digest") != old_digest]
    probes: list[tuple[str, str]] = [(later[0]["timestamp"], WAYBACK_RAW.format(ts=later[0]["timestamp"],
                                                                               url=later[0]["original"]))] if later else []
    if not later and not old_complete:
        # The CDX index lags behind what the archive can replay: also ask for the capture closest to now.
        now_ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        probes.append((f"closest-to-{now_ts}", WAYBACK_RAW.format(ts=now_ts, url=entry["url"])))
    entry["probes"] = []
    for label, url in probes:
        try:
            body, final_url = archive.get(url)
        except Exception as exc:
            entry["probes"].append({"requested": label, "error": repr(exc)[:200]})
            continue
        served = _snapshot_of(final_url) or label
        probe = {"requested": label, "served": served}
        entry["probes"].append(probe)
        if not cfd._looks_like_csv(body):
            probe["result"] = "not a football-data CSV"
            continue
        if served[:14] <= have_ts[:14] or wayback_digest(body) == old_digest:
            probe["result"] = "nothing newer than the cached file"
            continue
        summary = _csv_summary(body, season, div)
        probe["result"] = f"{summary['n_rows']} rows"
        if summary["n_rows"] <= old_rows:
            continue
        atomic_write_bytes(latest_path, gzip.compress(body, compresslevel=6))
        entry.update({
            "status": "ok", "fetched_via": "wayback", "effective_url": final_url, "wayback_snapshot": served,
            "cdx_timestamp": label, "sha1_b32": wayback_digest(body), "bytes": len(body), "fetched_at": utc_now(),
            "raw_path": rel(latest_path), **summary, "replaces_previous_in_history_build": True,
        })
        manifest[key_new] = entry
        save_manifest(manifest)
        print(f"[recheck] {key_old}: {old_ts} ({old_rows} rows) -> {served} ({summary['n_rows']} rows)", flush=True)
        return
    if prev.get("status") == "ok" and latest_path.exists():
        prev["checked_at"] = entry["checked_at"]  # keep an earlier newer download
        prev["probes"] = entry["probes"]
        manifest[key_new] = prev
    else:
        entry["status"] = "no_later_snapshot"
        manifest[key_new] = entry
    save_manifest(manifest)
    print(f"[recheck] {key_old}: nothing newer than {have_ts} (newest indexed capture {entry['latest_capture']}; "
          f"probes: {[p.get('served') or p.get('error') for p in entry['probes']]})", flush=True)


def _best_cached(season: str, div: str, manifest: dict) -> tuple[bool, str]:
    """(is the most complete cached source a full season?, snapshot of the best per-division file)."""
    rows, info = load_fd_file(season, div, manifest)
    if not rows:
        return False, ""
    complete = len(rows) >= info["double_round_robin_matches"]
    snaps = [c["snapshot"] or "" for c in info["candidates"] if "/bundle/" not in c["key"]]
    return complete, max(snaps) if snaps else ""


def download_football_data(seasons: list[str], divisions: list[str], args: argparse.Namespace) -> None:
    manifest = load_manifest(MANIFEST)
    archive = ArchiveClient(args.delay)
    origin_ok = None  # probed lazily, only when something has to be downloaded
    for season in seasons:
        state = {d: _best_cached(season, d, manifest) for d in divisions}
        need = [d for d in divisions if season == RECHECK_SEASON or not state[d][0]]
        if not need:
            continue
        if origin_ok is None:
            origin_ok = origin_reachable()
        refresh = season == RECHECK_SEASON or args.refresh_cdx
        try:
            captures = cdx_listing(archive, season, refresh=refresh)
        except Exception as exc:
            print(f"[archive] CDX listing for {season} failed: {exc!r}", flush=True)
            continue
        print(f"[archive] {season}: {len(captures)} captures listed", flush=True)
        for div in need:
            try:
                if season == RECHECK_SEASON:
                    recheck_current_season(archive, manifest, div, captures)
                else:
                    download_history_file(archive, manifest, season, div, captures, origin_ok)
            except Exception as exc:  # one file must not stop the run; the next run retries it
                print(f"[archive] {season}/{div}: {exc!r}", flush=True)
        problems = {}
        for div in divisions:
            complete, snap = _best_cached(season, div, manifest)
            if not complete:
                problems[div] = snap
        if problems:
            print(f"[archive] {season}: incomplete or missing after per-file download: {sorted(problems)}", flush=True)
            try:
                download_bundles(archive, manifest, season, captures, problems)
            except Exception as exc:
                print(f"[bundle] {season}: {exc!r}", flush=True)
    print(f"[archive] requests made: {archive.requests}", flush=True)


# ---------------------------------------------------------------------------
# FotMob league fixture lists
# ---------------------------------------------------------------------------


class FotmobBlocked(RuntimeError):
    """FotMob answered 403 / a captcha / a challenge page: all FotMob fetching stops."""


@dataclass(frozen=True)
class FmFixture:
    id: str
    day: date | None
    utc: str
    round: str
    home_id: str
    away_id: str
    home_name: str
    away_name: str
    home_short: str
    away_short: str
    finished: bool
    cancelled: bool
    awarded: bool | None  # None: FotMob sent no 'awarded' flag (e.g. an abandoned match)
    hs: int | None
    as_: int | None
    score_str: str


def fotmob_cache_path(league_id: int, fm_season: str) -> Path:
    return FOTMOB_LEAGUE_DIR / f"{league_id}_{fm_season.replace('/', '-')}.json.gz"


def read_fotmob_cache(path: Path) -> dict | None:
    for _ in range(3):
        try:
            return json.loads(gzip.decompress(path.read_bytes()))
        except FileNotFoundError:
            return None
        except (OSError, EOFError, ValueError):
            time.sleep(1.0)  # another collector may be replacing the file
    raise RuntimeError(f"unreadable FotMob cache file {path}")


def fetch_fotmob_league(client: Any, league_id: int, fm_season: str, log: list[dict], max_attempts: int = 4) -> dict | None:
    """Cached league response, or one polite fetch (shared limiter) written atomically to the cache."""
    import httpx

    path = fotmob_cache_path(league_id, fm_season)
    cached = read_fotmob_cache(path)
    if cached is not None:
        return cached
    for attempt in range(1, max_attempts + 1):
        fotmob_rate.acquire()
        cached = read_fotmob_cache(path)  # another collector may have fetched it meanwhile
        if cached is not None:
            return cached
        try:
            resp = client.get("/api/data/leagues", params={"id": league_id, "season": fm_season})
        except httpx.HTTPError as exc:
            pause = min(60.0, 5.0 * 2 ** (attempt - 1)) + random.uniform(0, 1)
            print(f"[fotmob] {league_id} {fm_season}: {exc!r}; retry in {pause:.0f}s", flush=True)
            time.sleep(pause)
            continue
        body = resp.content
        ctype = resp.headers.get("content-type", "")
        log.append({"league": league_id, "season": fm_season, "status": resp.status_code, "bytes": len(body),
                    "at": utc_now()})
        if resp.status_code == 403:
            raise FotmobBlocked(f"HTTP 403 for league {league_id} season {fm_season}: {body[:200]!r}")
        if resp.status_code == 429:
            retry_after = cfd._int(resp.headers.get("Retry-After")) or 60
            fotmob_rate.report_429(retry_after)
            print(f"[fotmob] 429, cooling down {retry_after}s", flush=True)
            time.sleep(retry_after)
            continue
        if resp.status_code >= 500:
            pause = min(60.0, 5.0 * 2 ** (attempt - 1)) + random.uniform(0, 1)
            print(f"[fotmob] {league_id} {fm_season}: HTTP {resp.status_code}; retry in {pause:.0f}s", flush=True)
            time.sleep(pause)
            continue
        if resp.status_code != 200:
            print(f"[fotmob] {league_id} {fm_season}: HTTP {resp.status_code}; not cached", flush=True)
            return None
        try:
            data = json.loads(body)
        except ValueError:
            head = body[:2000].lower()
            if b"<html" in head or b"captcha" in head or b"challenge" in head or "html" in ctype:
                raise FotmobBlocked(f"non-JSON page for league {league_id} season {fm_season}: {body[:200]!r}")
            print(f"[fotmob] {league_id} {fm_season}: invalid JSON; not cached", flush=True)
            return None
        selected = (data.get("details") or {}).get("selectedSeason")
        if selected != fm_season:
            print(f"[fotmob] {league_id} {fm_season}: FotMob returned season {selected!r}; not cached", flush=True)
            log[-1]["note"] = f"selectedSeason={selected!r}"
            return None
        atomic_write_bytes(path, gzip.compress(body, compresslevel=6))
        print(f"[fotmob] {league_id} {fm_season}: cached {len((data.get('fixtures') or {}).get('allMatches') or [])} "
              f"fixtures", flush=True)
        return data
    return None


def parse_fotmob_fixtures(data: dict) -> list[FmFixture]:
    out: list[FmFixture] = []
    for m in ((data.get("fixtures") or {}).get("allMatches") or []):
        st = m.get("status") or {}
        home, away = m.get("home") or {}, m.get("away") or {}
        utc = st.get("utcTime") or ""
        try:
            day = datetime.fromisoformat(utc.replace("Z", "+00:00")).date() if utc else None
        except ValueError:
            day = None
        score = parse_score(st.get("scoreStr"))
        awarded = st.get("awarded")  # absent for some fixtures (abandoned 4219847): never default it to False
        out.append(FmFixture(
            id=str(m.get("id")), day=day, utc=utc, round=str(m.get("round") or ""),
            home_id=str(home.get("id")), away_id=str(away.get("id")),
            home_name=home.get("name") or "", away_name=away.get("name") or "",
            home_short=home.get("shortName") or "", away_short=away.get("shortName") or "",
            finished=bool(st.get("finished")), cancelled=bool(st.get("cancelled")),
            awarded=None if awarded is None else bool(awarded),
            hs=score[0] if score else None, as_=score[1] if score else None, score_str=st.get("scoreStr") or "",
        ))
    return out


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------


def _window(day: date) -> tuple[date, date, date]:
    return (day - timedelta(days=1), day, day + timedelta(days=1))


class FixtureIndex:
    def __init__(self, fixtures: list[FmFixture]):
        self.fixtures = fixtures
        self.teams: dict[str, tuple[str, str]] = {}
        self.by_home_day: dict[tuple[str, date], list[FmFixture]] = defaultdict(list)
        self.by_away_day: dict[tuple[str, date], list[FmFixture]] = defaultdict(list)
        self.by_pair: dict[tuple[str, str], list[FmFixture]] = defaultdict(list)
        self.by_day_score: dict[tuple[date, int, int], list[FmFixture]] = defaultdict(list)
        for f in fixtures:
            self.teams.setdefault(f.home_id, (f.home_name, f.home_short))
            self.teams.setdefault(f.away_id, (f.away_name, f.away_short))
            if f.day is None:
                continue
            self.by_home_day[(f.home_id, f.day)].append(f)
            self.by_away_day[(f.away_id, f.day)].append(f)
            self.by_pair[(f.home_id, f.away_id)].append(f)
            if f.hs is not None and f.as_ is not None:
                self.by_day_score[(f.day, f.hs, f.as_)].append(f)

    def pair_candidates(self, home_id: str, away_id: str, day: date) -> list[FmFixture]:
        return [f for f in self.by_pair.get((home_id, away_id), ()) if abs((f.day - day).days) <= 1]


@dataclass
class TeamMapResult:
    mapping: dict[str, str]          # football-data name -> FotMob team id (verified)
    details: dict[str, dict]         # evidence per mapped name
    unmapped: dict[str, dict]        # reason / best candidate per unmapped name


def _pair_agreement(rows: list[FdRow], idx: FixtureIndex, mapping: dict[str, str], name: str) -> tuple[int, int]:
    """(rows found as an exact FotMob (home, away) pair within +-1 day, rows against mapped opponents)."""
    hits = tot = 0
    t = mapping[name]
    for r in rows:
        if r.home == name and r.away in mapping:
            tot += 1
            hits += bool(idx.pair_candidates(t, mapping[r.away], r.day))
        elif r.away == name and r.home in mapping:
            tot += 1
            hits += bool(idx.pair_candidates(mapping[r.home], t, r.day))
    return hits, tot


def _accept(votes: dict[str, Counter], considered: Counter, mapping: dict[str, str], how: dict[str, dict],
            method: str, min_votes: int, min_conf: float, max_runner_up: float) -> bool:
    taken = set(mapping.values())
    proposals = []
    for name, counter in votes.items():
        if name in mapping or not counter:
            continue
        ranked = counter.most_common(2)
        top, v = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0
        conf = v / considered[name] if considered[name] else 0.0
        if v >= min_votes and conf >= min_conf and second <= max_runner_up * v and top not in taken:
            proposals.append((conf, v, name, top, second))
    proposals.sort(key=lambda p: (-p[0], -p[1], p[2]))
    accepted = False
    for conf, v, name, top, second in proposals:
        if top in taken or name in mapping:
            continue
        mapping[name] = top
        taken.add(top)
        how[name] = {"method": method, "votes": v, "n": considered[name], "runner_up": second}
        accepted = True
    return accepted


def map_teams(rows: list[FdRow], idx: FixtureIndex, anchors: dict[str, str], *, min_votes: int = 3,
              opp_min_conf: float = 0.8, opp_max_runner_up: float = 0.25, score_min_conf: float = 0.5,
              score_max_runner_up: float = 0.5, verify_min: float = 0.9) -> TeamMapResult:
    """Map the football-data team names of ONE division-season to FotMob team ids of that league-season."""
    names = sorted({r.home for r in rows} | {r.away for r in rows})
    mapping: dict[str, str] = {}
    how: dict[str, dict] = {}

    # 1. anchors: existing verified football_data -> DB map (DB provider id = FotMob team id)
    cand = {n: anchors[n] for n in names if anchors.get(n) in idx.teams}
    dup = Counter(cand.values())
    cand = {n: t for n, t in cand.items() if dup[t] == 1}
    while True:  # drop anchors the fixture list contradicts, worst first
        worst = None
        for n in cand:
            hits, tot = _pair_agreement(rows, idx, cand, n)
            if tot >= 3 and hits < verify_min * tot and (worst is None or hits / tot < worst[0]):
                worst = (hits / tot, n)
        if worst is None:
            break
        del cand[worst[1]]
    for n, t in cand.items():
        mapping[n] = t
        how[n] = {"method": "existing_map_anchor"}

    last_votes: dict[str, tuple[str, Counter, Counter]] = {}
    while True:
        # 2. opponent-consistent votes: the FotMob team that met the mapped opponent (same venue, +-1 day)
        votes: dict[str, Counter] = defaultdict(Counter)
        considered: Counter = Counter()
        for r in rows:
            for n, opp, n_is_home in ((r.home, r.away, True), (r.away, r.home, False)):
                if n in mapping or opp not in mapping:
                    continue
                considered[n] += 1
                oid = mapping[opp]
                found: set[str] = set()
                for d in _window(r.day):
                    if n_is_home:
                        found.update(f.home_id for f in idx.by_away_day.get((oid, d), ()))
                    else:
                        found.update(f.away_id for f in idx.by_home_day.get((oid, d), ()))
                for c in found:
                    votes[n][c] += 1
        for n in votes:
            last_votes[n] = ("opponent_fixture_votes", votes[n], considered)
        if _accept(votes, considered, mapping, how, "opponent_fixture_votes", min_votes, opp_min_conf,
                   opp_max_runner_up):
            continue
        # 3. score-based fixture overlap (names still without enough mapped opponents)
        votes = defaultdict(Counter)
        considered = Counter()
        for r in rows:
            if r.hg is None or r.ag is None:
                continue
            fs = [f for d in _window(r.day) for f in idx.by_day_score.get((d, r.hg, r.ag), ())]
            for n, is_home in ((r.home, True), (r.away, False)):
                if n in mapping:
                    continue
                considered[n] += 1
                for c in {f.home_id if is_home else f.away_id for f in fs}:
                    votes[n][c] += 1
        for n in votes:
            if n not in last_votes or not last_votes[n][1]:
                last_votes[n] = ("score_fixture_overlap", votes[n], considered)
        if not _accept(votes, considered, mapping, how, "score_fixture_overlap", min_votes, score_min_conf,
                       score_max_runner_up):
            break

    # final check of every accepted name against the whole mapping
    final: dict[str, str] = {}
    details: dict[str, dict] = {}
    unmapped: dict[str, dict] = {}
    for n in names:
        if n not in mapping:
            method, counter, cons = last_votes.get(n, ("", Counter(), Counter()))
            ranked = counter.most_common(2)
            if ranked:
                top, v = ranked[0]
                second = ranked[1][1] if len(ranked) > 1 else 0
                owner = next((k for k, t in mapping.items() if t == top), None)
                reason = (f"best candidate already mapped to {owner!r}" if owner else
                          f"below threshold ({method}): {v}/{cons[n]} votes, runner-up {second}")
                unmapped[n] = {"reason": reason, "candidate_id": top,
                               "candidate_name": idx.teams.get(top, ("", ""))[0],
                               "score": round(v / cons[n], 3) if cons[n] else ""}
            else:
                unmapped[n] = {"reason": "no FotMob candidate in this league-season", "candidate_id": "",
                               "candidate_name": "", "score": ""}
            continue
        hits, tot = _pair_agreement(rows, idx, mapping, n)
        t = mapping[n]
        fm_name, fm_short = idx.teams.get(t, ("", ""))
        if tot == 0 or hits < verify_min * tot:
            unmapped[n] = {"reason": f"fixture check failed: {hits}/{tot} matches found as exact FotMob pairs",
                           "candidate_id": t, "candidate_name": fm_name, "score": round(hits / tot, 3) if tot else ""}
            continue
        final[n] = t
        sim = max(name_similarity(n, fm_name), name_similarity(n, fm_short) if fm_short else 0.0)
        details[n] = {**how[n], "pair_hits": hits, "pair_n": tot, "fotmob_name": fm_name,
                      "fotmob_short_name": fm_short, "name_sim": round(sim, 2)}
    return TeamMapResult(final, details, unmapped)


def map_rows(rows: list[FdRow], idx: FixtureIndex, mapping: dict[str, str]) -> list[dict]:
    """Link each football-data row to exactly one FotMob fixture (mapped pair, +-1 day) or give the reason."""
    results: list[dict] = []
    for r in rows:
        h, a = mapping.get(r.home), mapping.get(r.away)
        res: dict[str, Any] = {"row": r, "status": "", "fixture": None, "reason": "", "home_id": h, "away_id": a,
                               "nearest": None}
        if not h or not a:
            missing = [n for n, t in ((r.home, h), (r.away, a)) if not t]
            res.update(status="unmapped_team", reason="team name not mapped: " + ", ".join(missing))
        else:
            cands = idx.pair_candidates(h, a, r.day)
            if len(cands) > 1:
                live = [f for f in cands if not f.cancelled]
                if len(live) == 1:
                    cands = live
            if len(cands) == 1:
                res.update(status="mapped", fixture=cands[0])
            elif not cands:
                near = sorted(idx.by_pair.get((h, a), ()), key=lambda f: abs((f.day - r.day).days))
                res.update(status="no_fixture", reason="no FotMob fixture of the mapped pair within +-1 day",
                           nearest=near[0] if near else None)
            else:
                res.update(status="ambiguous", reason=f"{len(cands)} FotMob fixtures of the pair within +-1 day")
        results.append(res)
    # one FotMob fixture can back only one football-data row
    used = Counter(res["fixture"].id for res in results if res["fixture"] is not None)
    for res in results:
        f = res["fixture"]
        if f is not None and used[f.id] > 1:
            res.update(status="ambiguous", fixture=None,
                       reason=f"FotMob fixture {f.id} matched by {used[f.id]} football-data rows")
    return results


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def existing_anchor_map() -> dict[str, dict[str, str]]:
    """country -> {football-data name: FotMob team id} from the verified football_data -> DB map."""
    out: dict[str, dict[str, str]] = defaultdict(dict)
    for r in read_team_map("football_data"):
        country = (r.get("source_context") or "").split(":")[0].strip()
        if country and r.get("db_team_provider_id"):
            out[country][r["source_name"]] = str(r["db_team_provider_id"])
    return out


def db_teams_by_provider() -> dict[str, tuple[str, str]]:
    """FotMob team id -> (DB team uuid, DB name); production DB opened read-only."""
    try:
        con = db_connect()
    except Exception:
        return {}
    try:
        return {str(pid): (tid, name) for tid, name, pid in con.execute("select id, name, provider_id from teams")}
    finally:
        con.close()


def output_row(res: dict, div: str, season: str, finfo: dict) -> dict:
    r: FdRow = res["row"]
    country, league = cfd.MAIN_DIVISIONS[div]
    f: FmFixture | None = res["fixture"]
    out: dict[str, Any] = {c: r.raw.get(c, "") for c in ODDS_COLUMNS}
    agrees = ""
    if f is not None and f.hs is not None and f.as_ is not None and r.hg is not None and r.ag is not None:
        agrees = int(f.hs == r.hg and f.as_ == r.ag)
    out.update({
        "season": season, "division": div, "country": country, "league": league,
        "fotmob_league_id": FOTMOB_LEAGUE[div], "fotmob_season": fotmob_season(season),
        "fd_file": finfo.get("manifest_key", ""), "fd_snapshot": _blank(finfo.get("snapshot")),
        "fd_file_complete": "" if finfo.get("complete") is None else int(finfo["complete"]),
        "date": r.day.isoformat(), "time": r.time, "home": r.home, "away": r.away,
        "FTHG": _blank(r.hg), "FTAG": _blank(r.ag), "FTR": r.ftr, "map_status": res["status"],
        "fotmob_match_id": f.id if f else "", "fotmob_home_id": f.home_id if f else "",
        "fotmob_away_id": f.away_id if f else "", "fotmob_home_name": f.home_name if f else "",
        "fotmob_away_name": f.away_name if f else "", "fotmob_utc_time": f.utc if f else "",
        "fotmob_round": f.round if f else "", "fotmob_home_score": _blank(f.hs) if f else "",
        "fotmob_away_score": _blank(f.as_) if f else "",
        "fotmob_awarded": ("" if f.awarded is None else int(f.awarded)) if f else "",
        "score_agrees": agrees,
    })
    for prefix, prefs, names in (
        ("close_1x2", cfd.CLOSE_1X2, ("p_close_home", "p_close_draw", "p_close_away")),
        ("close_ou25", cfd.CLOSE_OU25, ("p_close_over25", "p_close_under25")),
        ("pre_1x2", cfd.PRE_1X2, ("p_pre_home", "p_pre_draw", "p_pre_away")),
        ("pre_ou25", PRE_OU25, ("p_pre_over25", "p_pre_under25")),
    ):
        src, probs, overround = cfd.implied(r.raw, prefs)
        out[f"{prefix}_source"] = src or ""
        for k, v in zip(names, probs):
            out[k] = _blank(v)
        out[f"{prefix}_overround"] = _blank(overround)
    return out


def write_csv_atomic(path: Path, fields: list[str], rows: Iterable[dict]) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    atomic_write_bytes(path, buf.getvalue().encode("utf-8"))


def _stable_read(path: Path, tries: int = 10) -> bytes:
    """Read a shared file only when two reads 0.3 s apart agree (another script may be rewriting it in place)."""
    prev = None
    for _ in range(tries):
        cur = path.read_bytes()
        if cur == prev:
            return cur
        prev = cur
        time.sleep(0.3)
    raise RuntimeError(f"{path} keeps changing; not rewriting it")


def rewrite_source_rows(path: Path, fields: list[str], source: str, rows: list[dict]) -> None:
    """Replace this source's rows in a shared CSV (other sources kept), written atomically."""
    kept: list[dict] = []
    if path.exists():
        text = _stable_read(path).decode("utf-8")
        kept = [r for r in csv.DictReader(io.StringIO(text, newline="")) if r.get("source") != source]
    write_csv_atomic(path, fields, kept + rows)


def process_order(seasons: list[str], divisions: list[str]) -> list[tuple[str, str]]:
    """Second tiers first (FotMob lists other collectors are unlikely to cache), newest season first."""
    order = [d for d in SECOND_DIVISIONS + TOP_DIVISIONS if d in divisions]
    return [(d, s) for d in order for s in sorted(seasons, reverse=True)]


def collect_fotmob(seasons: list[str], divisions: list[str], allow_fetch: bool) -> tuple[dict, dict]:
    """(div, season) -> league response (or None); plus a fetch report."""
    import httpx

    fm: dict[tuple[str, str], dict | None] = {}
    log: list[dict] = []
    report: dict[str, Any] = {"blocked": None, "fetched": 0, "from_cache": 0, "missing": []}
    client = httpx.Client(base_url=FOTMOB_BASE, headers=FOTMOB_HEADERS, timeout=30.0,
                          follow_redirects=True) if allow_fetch else None
    try:
        for div, season in process_order(seasons, divisions):
            league_id, fms = FOTMOB_LEAGUE[div], fotmob_season(season)
            path = fotmob_cache_path(league_id, fms)
            data = read_fotmob_cache(path)
            fetched = False
            if data is None and client is not None and report["blocked"] is None:
                n_before = len(log)
                try:
                    data = fetch_fotmob_league(client, league_id, fms, log)
                except FotmobBlocked as exc:
                    report["blocked"] = str(exc)
                    print(f"[fotmob] STOPPED: {exc}", flush=True)
                fetched = len(log) > n_before
            if data is not None:
                details = data.get("details") or {}
                if details.get("selectedSeason") != fms or str(details.get("id")) != str(league_id):
                    # not the requested league-season (e.g. written by another collector): never used
                    report.setdefault("cache_mismatch", []).append(
                        f"{path.name}: id={details.get('id')} season={details.get('selectedSeason')}")
                    data = None
                else:
                    report["fetched" if fetched else "from_cache"] += 1
            if data is None:
                report["missing"].append(f"{league_id}_{fms}")
            fm[(div, season)] = data
    finally:
        if client is not None:
            client.close()
    report["requests"] = log
    return fm, report


def build(seasons: list[str], divisions: list[str], fm: dict, fetch_report: dict) -> dict:
    manifest = load_manifest(MANIFEST)
    anchors = existing_anchor_map()
    db_teams = db_teams_by_provider()
    out_rows: list[dict] = []
    unmapped_rows: list[dict] = []
    coverage: dict[str, Any] = {}
    team_ev: dict[tuple[str, str], dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    team_names: dict[str, str] = {}
    team_unmapped: list[dict] = []

    for season in seasons:
        for div in divisions:
            key = f"{season}/{div}"
            country, league = cfd.MAIN_DIVISIONS[div]
            rows, finfo = load_fd_file(season, div, manifest)
            data = fm.get((div, season))
            cov: dict[str, Any] = {"season": season, "division": div, "country": country, "league": league,
                                   "fotmob_league_id": FOTMOB_LEAGUE[div], "fd_file": finfo, "rows": len(rows)}
            if not rows:
                cov["note"] = "football-data file unavailable"
                coverage[key] = cov
                continue
            fixtures = parse_fotmob_fixtures(data) if data else []
            idx = FixtureIndex(fixtures)
            if data:
                tm = map_teams(rows, idx, anchors.get(country, {}))
                results = map_rows(rows, idx, tm.mapping)
            else:
                tm = TeamMapResult({}, {}, {})
                results = [{"row": r, "status": "no_fotmob_fixture_list", "fixture": None, "home_id": None,
                            "away_id": None, "nearest": None,
                            "reason": "FotMob fixture list for this league-season not available"} for r in rows]
            for name, d in tm.details.items():
                team_ev[(country, name)][tm.mapping[name]].append({"season": season, "division": div, **d})
                team_names[tm.mapping[name]] = d["fotmob_name"]
            for name, u in tm.unmapped.items():
                team_unmapped.append({
                    "source": TEAM_SOURCE, "source_name": name, "source_context": f"{country}: {div}@{season}",
                    "best_candidate_db_team_name": u["candidate_name"], "best_candidate_score": u["score"],
                    "reason": f"{u['reason']} (FotMob candidate id {u['candidate_id'] or '-'})",
                })
            status = Counter(res["status"] for res in results)
            linked = {res["fixture"].id for res in results if res["fixture"] is not None}
            finished_fm = [f for f in fixtures if f.finished and not f.cancelled]
            compared = agrees = 0
            for res in results:
                row = output_row(res, div, season, finfo)
                out_rows.append(row)
                if row["score_agrees"] != "":
                    compared += 1
                    agrees += int(row["score_agrees"])
                if res["status"] != "mapped":
                    r: FdRow = res["row"]
                    near: FmFixture | None = res.get("nearest")
                    unmapped_rows.append({
                        "season": season, "division": div, "date": r.day.isoformat(), "time": r.time,
                        "home": r.home, "away": r.away, "FTHG": _blank(r.hg), "FTAG": _blank(r.ag),
                        "map_status": res["status"], "reason": res["reason"],
                        "home_fotmob_id": res.get("home_id") or "", "away_fotmob_id": res.get("away_id") or "",
                        "nearest_pair_fixture_id": near.id if near else "",
                        "nearest_pair_fixture_utc": near.utc if near else "",
                        "nearest_pair_fixture_score": near.score_str if near else "",
                    })
            season_rows = out_rows[-len(results):] if results else []
            src_count = Counter(x["close_1x2_source"] for x in season_rows)
            cov.update({
                "fotmob_fixtures": len(fixtures), "fotmob_finished": len(finished_fm),
                "fotmob_finished_without_fd_row": sum(1 for f in finished_fm if f.id not in linked),
                "fd_team_names": len(tm.mapping) + len(tm.unmapped), "team_names_mapped": len(tm.mapping),
                "team_names_unmapped": sorted(tm.unmapped),
                "mapped": status.get("mapped", 0),
                "mapped_pct": round(100.0 * status.get("mapped", 0) / len(rows), 2),
                "status_counts": dict(status), "score_compared": compared, "score_agrees": agrees,
                "score_agree_pct": round(100.0 * agrees / compared, 2) if compared else None,
                "close_1x2": sum(1 for x in season_rows if x["close_1x2_source"]),
                "close_1x2_by_source": {k: v for k, v in src_count.items() if k},
                "close_ou25": sum(1 for x in season_rows if x["close_ou25_source"]),
                "pre_1x2": sum(1 for x in season_rows if x["pre_1x2_source"]),
                "pre_ou25": sum(1 for x in season_rows if x["pre_ou25_source"]),
                "team_methods": dict(Counter(d["method"] for d in tm.details.values())),
                "min_team_pair_agreement": min((round(d["pair_hits"] / d["pair_n"], 3) for d in tm.details.values()),
                                               default=None),
            })
            coverage[key] = cov
            print(f"[build] {key:9} rows={len(rows):4} mapped={cov['mapped']:4} ({cov['mapped_pct']:6.2f}%) "
                  f"score_agree={agrees}/{compared} teams={len(tm.mapping)}/{cov['fd_team_names']} "
                  f"fm_finished_wo_fd={cov['fotmob_finished_without_fd_row']}", flush=True)

    out_rows.sort(key=lambda x: (x["season"], x["division"], x["date"], x["home"]))
    write_csv_atomic(OUT_HISTORY, OUT_FIELDS, out_rows)
    write_csv_atomic(OUT_UNMAPPED_ROWS, UNMAPPED_ROW_FIELDS, unmapped_rows)

    # team map rows: one per (country, football-data name, FotMob id)
    team_rows: list[dict] = []
    for (country, name), by_id in sorted(team_ev.items()):
        for fid, evs in sorted(by_id.items()):
            evs.sort(key=lambda e: (e["season"], e["division"]))
            per_div: dict[str, list[str]] = defaultdict(list)
            for e in evs:
                per_div[e["division"]].append(e["season"])
            context = f"{country}: " + "; ".join(f"{d}@{'+'.join(s)}" for d, s in sorted(per_div.items()))
            methods = sorted({e["method"] for e in evs})
            sim = max(e["name_sim"] for e in evs)
            ev_txt = "; ".join(
                f"{e['season']}/{e['division']} {e['method']}"
                + (f" {e['votes']}/{e['n']} votes (runner-up {e['runner_up']})" if "votes" in e else "")
                + f", {e['pair_hits']}/{e['pair_n']} matches found as FotMob pairs" for e in evs)
            if len(by_id) > 1:
                ev_txt += f"; NOTE: this name maps to {len(by_id)} FotMob ids in different seasons"
            db = db_teams.get(fid)
            team_rows.append({
                "source": TEAM_SOURCE, "source_name": name, "source_context": context,
                "db_team_id": db[0] if db else "", "db_team_provider_id": fid,
                "db_team_name": team_names.get(fid, ""),
                "method": "+".join(methods) + ("+name" if sim >= 0.85 else ""),
                "confidence": round(min(e["pair_hits"] / e["pair_n"] for e in evs), 3),
                "evidence": f"{ev_txt}; name_sim={sim:.2f}",
            })
    rewrite_source_rows(TEAM_MAP_PATH, TEAM_MAP_FIELDS, TEAM_SOURCE, team_rows)
    rewrite_source_rows(UNMAPPED_PATH, UNMAPPED_FIELDS, TEAM_SOURCE, team_unmapped)

    total = Counter()
    for k, c in coverage.items():
        for f in ("rows", "mapped", "score_compared", "score_agrees", "close_1x2", "close_ou25", "pre_1x2",
                  "pre_ou25", "fotmob_finished", "fotmob_finished_without_fd_row"):
            total[f] += c.get(f, 0) or 0
    coverage["_total"] = {
        **dict(total), "mapped_pct": round(100.0 * total["mapped"] / total["rows"], 2) if total["rows"] else None,
        "score_agree_pct": round(100.0 * total["score_agrees"] / total["score_compared"], 2)
        if total["score_compared"] else None,
        "team_map_rows": len(team_rows), "team_names_unmapped": len(team_unmapped),
        "partial_division_seasons": sorted(k for k, c in coverage.items()
                                           if c.get("rows") and not c["fd_file"].get("complete")),
        "names_with_several_fotmob_ids": sorted(f"{c}:{n}" for (c, n), by_id in team_ev.items() if len(by_id) > 1),
        "built_at": utc_now(), "fotmob_fetch": {k: v for k, v in fetch_report.items() if k != "requests"},
        "fotmob_requests": fetch_report.get("requests", []),
    }
    coverage["_markdown"] = coverage_markdown(coverage)
    atomic_write_bytes(OUT_COVERAGE, json.dumps(coverage, indent=2, ensure_ascii=False, default=str).encode("utf-8"))
    return coverage


def _snap(ts: str | None) -> str:
    return ts[:8] if ts else "-"


def coverage_markdown(coverage: dict) -> str:
    lines = ["| Season | Div | FotMob league | Rows | Mapped | % mapped | Score agrees | % agree | Close 1X2 (PS / Avg / B365) "
             "| Close O/U 2.5 | Pre 1X2 | Pre O/U 2.5 | FotMob finished without fd row | Snapshot |",
             "|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|"]
    for key, c in coverage.items():
        if key.startswith("_"):
            continue
        if not c.get("rows"):
            lines.append(f"| {c['season']} | {c['division']} | {c['fotmob_league_id']} | 0 | - | - | - | - | - | - | - | - "
                         f"| - | unavailable |")
            continue
        src = c.get("close_1x2_by_source", {})
        lines.append(
            f"| {c['season']} | {c['division']} | {c['fotmob_league_id']} | {c['rows']} | {c['mapped']} | "
            f"{c['mapped_pct']:.1f} | {c['score_agrees']}/{c['score_compared']} | "
            f"{(c['score_agree_pct'] if c['score_agree_pct'] is not None else 0):.1f} | "
            f"{c['close_1x2']} ({src.get('PSCH', 0)} / {src.get('AvgCH', 0)} / {src.get('B365CH', 0)}) | "
            f"{c['close_ou25']} | {c['pre_1x2']} | {c['pre_ou25']} | {c['fotmob_finished_without_fd_row']} | "
            f"{_snap(c['fd_file'].get('snapshot'))}{'' if c['fd_file'].get('complete', True) else ' partial'} |")
    t = coverage.get("_total", {})
    if t:
        lines.append(f"| **Total** | | | {t['rows']} | {t['mapped']} | {t['mapped_pct']:.1f} | "
                     f"{t['score_agrees']}/{t['score_compared']} | {t['score_agree_pct']:.1f} | {t['close_1x2']} | "
                     f"{t['close_ou25']} | {t['pre_1x2']} | {t['pre_ou25']} | {t['fotmob_finished_without_fd_row']} | |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Verification helpers (read-only)
# ---------------------------------------------------------------------------


def spot_check(n: int, seed: int) -> int:
    """Re-read n random mapped rows and compare them with the cached FotMob fixture list."""
    with OUT_HISTORY.open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["map_status"] == "mapped"]
    rng = random.Random(seed)
    sample = rng.sample(rows, min(n, len(rows)))
    cache: dict[tuple[str, str], dict[str, FmFixture]] = {}
    bad = 0
    for r in sorted(sample, key=lambda x: (x["season"], x["division"], x["date"])):
        k = (r["fotmob_league_id"], r["fotmob_season"])
        if k not in cache:
            data = read_fotmob_cache(fotmob_cache_path(int(k[0]), k[1])) or {}
            cache[k] = {f.id: f for f in parse_fotmob_fixtures(data)}
        f = cache[k].get(r["fotmob_match_id"])
        ok = (f is not None and f.home_id == r["fotmob_home_id"] and f.away_id == r["fotmob_away_id"]
              and f.day is not None and abs((f.day - date.fromisoformat(r["date"])).days) <= 1)
        bad += not ok
        fm_txt = f"{f.utc[:16]} {f.home_name} {f.score_str} {f.away_name}" if f else "NOT IN CACHE"
        print(f"{'OK ' if ok else 'BAD'} {r['season']}/{r['division']:3} fd {r['date']} {r['home']} "
              f"{r['FTHG']}-{r['FTAG']} {r['away']} | FotMob {r['fotmob_match_id']}: {fm_txt} | "
              f"score_agrees={r['score_agrees']}")
    print(f"spot check: {len(sample) - bad}/{len(sample)} consistent with the FotMob fixture cache")
    return bad


def db_cross_check() -> dict:
    """2025/26 rows: our FotMob match id vs the DB match linked in football_data_matches.csv (read-only DB)."""
    con = db_connect()
    try:
        provider = {mid: str(pid) for mid, pid in con.execute("select id, provider_id from matches")}
    finally:
        con.close()
    linked: dict[tuple[str, str, str, str], str] = {}
    with FD_MATCHES.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["season"] == RECHECK_SEASON and r["db_match_id"]:
                linked[(r["division"], r["date"], r["home"], r["away"])] = provider.get(r["db_match_id"], "")
    stats = Counter()
    examples = []
    with OUT_HISTORY.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["season"] != RECHECK_SEASON:
                continue
            k = (r["division"], r["date"], r["home"], r["away"])
            if k not in linked:
                stats["not_in_football_data_matches_or_unlinked"] += 1
                continue
            if not r["fotmob_match_id"]:
                stats["history_unmapped_but_db_linked"] += 1
                continue
            same = r["fotmob_match_id"] == linked[k]
            stats["same_id" if same else "different_id"] += 1
            if not same and len(examples) < 10:
                examples.append({"key": k, "history": r["fotmob_match_id"], "db": linked[k]})
    out = {**dict(stats), "examples": examples}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # -I ignores PYTHONIOENCODING
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seasons", default=",".join(ALL_SEASONS), help="football-data season codes, e.g. 2122,2223")
    ap.add_argument("--divisions", default=",".join(TOP_DIVISIONS + SECOND_DIVISIONS))
    ap.add_argument("--skip-download", action="store_true", help="no network at all: build from the caches")
    ap.add_argument("--no-fotmob-fetch", action="store_true", help="use cached FotMob fixture lists only")
    ap.add_argument("--refresh-cdx", action="store_true", help="re-list archive captures of past seasons too")
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between archive requests (min 1.0)")
    ap.add_argument("--spot-check", type=int, default=0, help="after the build, verify N random mapped rows")
    ap.add_argument("--seed", type=int, default=20261013)
    ap.add_argument("--db-check", action="store_true", help="after the build, compare 2025/26 ids with the DB link")
    ap.add_argument("--checks-only", action="store_true", help="run --spot-check / --db-check on the existing output")
    args = ap.parse_args(argv)
    seasons = [s.strip() for s in args.seasons.split(",") if s.strip()]
    divisions = [d.strip() for d in args.divisions.split(",") if d.strip()]
    for s in seasons:
        fotmob_season(s)
        if s not in ALL_SEASONS:
            ap.error(f"season {s} is outside {ALL_SEASONS}")
    for d in divisions:
        if d not in FOTMOB_LEAGUE:
            ap.error(f"unknown division {d}")

    rc = 0
    if not args.checks_only:
        if not args.skip_download:
            download_football_data(seasons, divisions, args)
        fm, report = collect_fotmob(seasons, divisions, allow_fetch=not (args.skip_download or args.no_fotmob_fetch))
        cov = build(seasons, divisions, fm, report)
        print(cov["_markdown"])
        t = cov["_total"]
        print(f"TOTAL rows={t['rows']} mapped={t['mapped']} ({t['mapped_pct']}%) score agrees "
              f"{t['score_agrees']}/{t['score_compared']} ({t['score_agree_pct']}%) "
              f"fotmob fetched={report['fetched']} cached={report['from_cache']} missing={len(report['missing'])}")
        if report["blocked"]:
            print(f"FotMob fetching was STOPPED: {report['blocked']}")
            rc = 2
    if args.spot_check:
        rc = max(rc, 1 if spot_check(args.spot_check, args.seed) else 0)
    if args.db_check:
        db_cross_check()
    return rc


if __name__ == "__main__":
    sys.exit(main())
