"""Shared helpers for external (non-FotMob) training-data collection.

Used by collect_football_data.py and collect_clubelo.py.

- Cached, throttled HTTP downloads under backend/data/external/raw/
- Read-only access to the live SQLite DB (backend/football_intelligence.db)
- Team-name normalisation and DB team matching (fixture-overlap and name based)

Nothing here invents data: a source team that cannot be matched with enough
confidence is left unmapped (db_team_id empty) and listed in the unmapped file.
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

BACKEND_DIR = Path(__file__).resolve().parents[2]
DB_PATH = BACKEND_DIR / "football_intelligence.db"
EXTERNAL_DIR = BACKEND_DIR / "data" / "external"
RAW_DIR = EXTERNAL_DIR / "raw"
TEAM_MAP_PATH = EXTERNAL_DIR / "team_name_map.csv"
UNMAPPED_PATH = EXTERNAL_DIR / "team_name_unmapped.csv"

USER_AGENT = "TUTARX-research/0.1 (personal non-commercial research; low request rate)"

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def http_get(url: str, timeout: float = 30.0, retries: int = 3, backoff: float = 5.0) -> bytes:
    """GET a URL and return the body. Raises the last error after retries."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:  # 404 is final, 429/5xx retry
            last_exc = exc
            if exc.code == 404:
                raise
            time.sleep(backoff * (attempt + 1))
        except Exception as exc:  # timeouts, connection errors
            last_exc = exc
            time.sleep(backoff * (attempt + 1) / 2)
    assert last_exc is not None
    raise last_exc


def load_manifest(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# DB (read-only)
# ---------------------------------------------------------------------------


def db_connect() -> sqlite3.Connection:
    uri = f"file:{DB_PATH.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


@dataclass(frozen=True)
class DbMatch:
    id: str
    day: date
    home_id: str
    away_id: str
    home_score: int | None
    away_score: int | None
    competition_id: str | None


def load_db_teams(con: sqlite3.Connection) -> dict[str, tuple[str, str]]:
    """team id -> (name, provider_id)."""
    return {r[0]: (r[1], r[2]) for r in con.execute("select id, name, provider_id from teams")}


def load_db_matches(con: sqlite3.Connection) -> list[DbMatch]:
    rows = con.execute(
        "select id, scheduled_at, home_team_id, away_team_id, home_score, away_score, competition_id "
        "from matches where status='FINISHED'"
    )
    out = []
    for mid, sched, h, a, hs, as_, comp in rows:
        out.append(DbMatch(mid, datetime.fromisoformat(str(sched)[:19]).date(), h, a, hs, as_, comp))
    return out


def load_db_competitions(con: sqlite3.Connection) -> dict[str, tuple[str, str]]:
    """competition id -> (name, provider_id)."""
    return {r[0]: (r[1], r[2]) for r in con.execute("select id, name, provider_id from competitions")}


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------

_TR_MAP = str.maketrans({"ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g", "ç": "c", "Ç": "c",
                         "ö": "o", "Ö": "o", "ü": "u", "Ü": "u", "ø": "o", "Ø": "o", "æ": "ae", "Æ": "ae",
                         "ß": "ss", "đ": "d", "Đ": "d", "ł": "l", "Ł": "l", "å": "a", "Å": "a"})

# Club-form tokens that carry no identity. Kept deliberately small so that
# e.g. "Real", "Inter", "Sporting", "Athletic" (identity words) survive.
_STOP_TOKENS = {
    "fc", "sc", "afc", "cf", "ac", "fk", "sk", "bk", "if", "cd", "sd", "ud", "ss", "ssc", "us", "as",
    "rc", "rcd", "sv", "tsg", "vfb", "vfl", "bv", "ca", "club", "de", "da", "do", "del", "la", "le", "the",
    "and", "calcio", "kv", "krc", "kaa", "rsc", "jk", "nk", "hnk", "gnk", "pfc", "sl", "cp", "ksk",
    "1", "04", "05", "09", "1846", "1860", "1899", "1900", "1907", "1909", "1910", "1913", "1919", "1920", "1928",
}


def strip_accents(text: str) -> str:
    text = text.translate(_TR_MAP)
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalise_name(name: str) -> str:
    """Lowercase, accent-free, punctuation-free, without generic club-form tokens."""
    s = strip_accents(name).lower()
    s = s.replace("&", " and ").replace("'", "")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    tokens = [t for t in s.split() if t not in _STOP_TOKENS]
    return " ".join(tokens) if tokens else re.sub(r"\s+", " ", s).strip()


def is_youth_or_women(name: str) -> bool:
    """FotMob names reserve/youth/women sides with suffixes; never map senior clubs to them."""
    return bool(re.search(r"\b(u\d{2}|ii|b|w|women|reserves?|youth|academy|frauen|femenino|feminin[ea]?|fem)\b|\(w\)",
                          strip_accents(name).lower()))


def name_similarity(a: str, b: str) -> float:
    na, nb = normalise_name(a), normalise_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = set(na.split()), set(nb.split())
    if ta and tb and (ta <= tb or tb <= ta):
        return 0.9
    return SequenceMatcher(None, na, nb).ratio()


# ---------------------------------------------------------------------------
# Fixture-overlap team matching (used for football-data.co.uk results)
# ---------------------------------------------------------------------------


@dataclass
class SourceMatch:
    day: date
    home: str
    away: str
    hg: int | None
    ag: int | None


def build_db_index(db_matches: Iterable[DbMatch]) -> dict[tuple[date, int, int], list[DbMatch]]:
    idx: dict[tuple[date, int, int], list[DbMatch]] = defaultdict(list)
    for m in db_matches:
        if m.home_score is None or m.away_score is None:
            continue
        idx[(m.day, m.home_score, m.away_score)].append(m)
    return idx


def fixture_overlap_map(
    source_matches: list[SourceMatch],
    db_index: dict[tuple[date, int, int], list[DbMatch]],
    db_min_day: date,
    db_max_day: date,
    min_votes: int = 3,
    min_conf: float = 0.5,
    max_runner_up_ratio: float = 0.5,
) -> dict[str, dict]:
    """Map each source team name to a DB team id by co-occurring results.

    A source result (day, home, away, hg, ag) votes for every DB match with the
    same score within +-1 day: source home -> DB home, source away -> DB away.
    The true team collects about one vote per match; random teams collect a few
    scattered votes. Confidence = top votes / source matches inside DB range.
    """
    votes: dict[str, Counter] = defaultdict(Counter)
    n_matches: Counter = Counter()
    for sm in source_matches:
        if sm.hg is None or sm.ag is None or sm.day < db_min_day or sm.day > db_max_day:
            continue
        n_matches[sm.home] += 1
        n_matches[sm.away] += 1
        seen_h: set[str] = set()
        seen_a: set[str] = set()
        for d in (sm.day - timedelta(days=1), sm.day, sm.day + timedelta(days=1)):
            for m in db_index.get((d, sm.hg, sm.ag), ()):
                seen_h.add(m.home_id)
                seen_a.add(m.away_id)
        for t in seen_h:
            votes[sm.home][t] += 1
        for t in seen_a:
            votes[sm.away][t] += 1

    result: dict[str, dict] = {}
    for team, n in n_matches.items():
        ranked = votes[team].most_common(2)
        top_id, top_v = ranked[0] if ranked else (None, 0)
        second_v = ranked[1][1] if len(ranked) > 1 else 0
        conf = top_v / n if n else 0.0
        ok = top_v >= min_votes and conf >= min_conf and second_v <= max_runner_up_ratio * top_v
        result[team] = {
            "db_team_id": top_id if ok else None,
            "candidate_id": top_id,
            "votes": top_v,
            "runner_up_votes": second_v,
            "n_matches": n,
            "confidence": round(conf, 3),
        }
    return result


# ---------------------------------------------------------------------------
# Team map file (shared by both sources)
# ---------------------------------------------------------------------------

TEAM_MAP_FIELDS = ["source", "source_name", "source_context", "db_team_id", "db_team_provider_id", "db_team_name",
                   "method", "confidence", "evidence"]
UNMAPPED_FIELDS = ["source", "source_name", "source_context", "best_candidate_db_team_name", "best_candidate_score",
                   "reason"]


def _rewrite_rows(path: Path, fields: list[str], source: str, rows: list[dict]) -> None:
    """Replace this source's rows in a shared CSV, keeping other sources' rows."""
    kept: list[dict] = []
    if path.exists():
        with path.open(encoding="utf-8", newline="") as f:
            kept = [r for r in csv.DictReader(f) if r.get("source") != source]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in kept + rows:
            w.writerow(r)


def write_team_map(source: str, mapped: list[dict], unmapped: list[dict]) -> None:
    _rewrite_rows(TEAM_MAP_PATH, TEAM_MAP_FIELDS, source, mapped)
    _rewrite_rows(UNMAPPED_PATH, UNMAPPED_FIELDS, source, unmapped)


def read_team_map(source: str | None = None) -> list[dict]:
    if not TEAM_MAP_PATH.exists():
        return []
    with TEAM_MAP_PATH.open(encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if source is None or r["source"] == source]
