#!/usr/bin/env python3
"""Load user-supplied (manual) bookmaker odds into average_market_odds.

The odds in the input file are typed in / collected by the user. They are
NOT fetched from a bookmaker API and NOT verified by the system, so every
row is labelled with source ``manual_user_supplied``:

  * provider_event_id = "manual_user_supplied:<match_id>"  (e.g. fotmob_6106260)
  * bookmakers        = ["manual_user_supplied"]
  * bookmaker_count   = 1, min_odds = max_odds = average_odds = supplied price

Rows follow the SAME storage convention as The Odds API updater
(app/services/odds_updater_service.py) so one converter
(app.services.odds_service.build_canonical_odds_quotes) handles both:

  market_key      market_point  outcome_name
  "h2h"           None          <home team name> | "Draw" | <away team name>
  "totals"        2.5 / 3.5     "Over" | "Under"
  "btts"          None          "Yes" | "No"
  "double_chance" None          "1X" | "12" | "X2"

match_id column: matches.id (UUID) when the fixture exists in the matches
table, otherwise NULL (the column is a foreign key to matches.id, so a
provider id such as "fotmob_6106260" must not be written there). The
prediction endpoint finds NULL-match rows through provider_event_id.

Input JSON format:
    {
      "source": "free text describing where the odds came from",
      "matches": [
        {"match_id": "fotmob_6106260", "label": "Arsenal - Lille",
         "home_team": "Arsenal", "away_team": "Lille",  # optional, DB team names
         "folder": "arsenal-lille",            # optional, for --markdown-dir
         "odds_1": 1.22, "odds_x": 5.8, "odds_2": 12.5,
         "dc_1x": 1.05, "dc_12": 1.12, "dc_x2": 4.2,
         "over_2_5": 1.5, "under_2_5": 2.5,
         "over_3_5": 2.25, "under_3_5": 1.58,
         "btts_yes": 2.1, "btts_no": 1.65}
      ]
    }
Absent fields are ignored; null / invalid (<= 1.0) prices are skipped and
reported (never stored as 0). Double chance prices are only loaded when the
user supplied them explicitly - they are never derived from 1X2.

--markdown-dir DIR: for every entry with a "folder", the per-team report
files DIR/<folder>/*.md (sampiyonlar-ligi format) are parsed. All files of a
folder must agree; prices missing from the JSON are filled in from them and
any price that disagrees with the JSON aborts the run (nothing is written).

Usage (from backend/):
    venv/Scripts/python.exe scripts/load_manual_odds.py path/to/market_odds.json
    venv/Scripts/python.exe scripts/load_manual_odds.py market_odds.json --dry-run
    venv/Scripts/python.exe scripts/load_manual_odds.py market_odds.json \
        --database-url sqlite:///./football_intelligence.db --api-base http://127.0.0.1:8003
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.database.models import (  # noqa: E402
    AverageMarketOdds,
    Match as DBMatch,
    ProviderSource,
    Team as DBTeam,
)
from app.services.odds_service import (  # noqa: E402
    BTTS_MARKET_KEY,
    DOUBLE_CHANCE_MARKET_KEY,
    H2H_MARKET_KEY,
    MANUAL_ODDS_SOURCE,
    TOTALS_MARKET_KEY,
    manual_provider_event_id,
)

# (json field, market_key, market_point, outcome_name or role placeholder)
HOME_ROLE = "<home>"
AWAY_ROLE = "<away>"
FIELD_SPECS: List[Tuple[str, str, Optional[float], str]] = [
    ("odds_1", H2H_MARKET_KEY, None, HOME_ROLE),
    ("odds_x", H2H_MARKET_KEY, None, "Draw"),
    ("odds_2", H2H_MARKET_KEY, None, AWAY_ROLE),
    ("dc_1x", DOUBLE_CHANCE_MARKET_KEY, None, "1X"),
    ("dc_12", DOUBLE_CHANCE_MARKET_KEY, None, "12"),
    ("dc_x2", DOUBLE_CHANCE_MARKET_KEY, None, "X2"),
    ("over_1_5", TOTALS_MARKET_KEY, 1.5, "Over"),
    ("under_1_5", TOTALS_MARKET_KEY, 1.5, "Under"),
    ("over_2_5", TOTALS_MARKET_KEY, 2.5, "Over"),
    ("under_2_5", TOTALS_MARKET_KEY, 2.5, "Under"),
    ("over_3_5", TOTALS_MARKET_KEY, 3.5, "Over"),
    ("under_3_5", TOTALS_MARKET_KEY, 3.5, "Under"),
    ("over_4_5", TOTALS_MARKET_KEY, 4.5, "Over"),
    ("under_4_5", TOTALS_MARKET_KEY, 4.5, "Under"),
    ("btts_yes", BTTS_MARKET_KEY, None, "Yes"),
    ("btts_no", BTTS_MARKET_KEY, None, "No"),
]
PRICE_FIELDS = [spec[0] for spec in FIELD_SPECS]


@dataclass
class MatchTeams:
    """Resolved fixture identity for one manual odds entry."""

    home_name: Optional[str]
    away_name: Optional[str]
    db_match_id: Optional[str]  # matches.id when the fixture is stored in the DB
    resolved_from: str


@dataclass
class LoadResult:
    match_id: str
    label: str
    created: int = 0
    updated: int = 0
    removed_stale: int = 0
    skipped_fields: List[str] = field(default_factory=list)
    teams: Optional[MatchTeams] = None
    error: Optional[str] = None


def _numeric_provider_id(match_id: str) -> Optional[str]:
    if "_" in match_id:
        prefix, rest = match_id.split("_", 1)
        if rest.isdigit():
            return rest
    return None


def _fetch_api_match(api_base: str, match_id: str, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
    url = f"{api_base.rstrip('/')}/api/v1/matches/{match_id}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        print(f"  [warn] API lookup failed for {match_id}: {exc}")
        return None


def resolve_match_teams(
    session: Session,
    match_id: str,
    label: str,
    api_base: Optional[str],
    explicit_home: Optional[str] = None,
    explicit_away: Optional[str] = None,
) -> MatchTeams:
    """Resolve home/away team names for a manual odds entry.

    Order: matches table (provider_id) -> explicit "home_team"/"away_team"
    in the entry -> running API (team ids verified against teams table) ->
    "Home - Away" label (last resort).
    """
    db_match = session.query(DBMatch).filter(
        (DBMatch.id == match_id) | (DBMatch.provider_id == match_id)
    ).first()
    numeric = _numeric_provider_id(match_id)
    if db_match is None and numeric:
        # "fotmob_6106260" -> provider_id "6106260" of provider source "fotmob"
        provider_name = match_id.split("_", 1)[0]
        db_match = (
            session.query(DBMatch)
            .join(ProviderSource, ProviderSource.id == DBMatch.provider_source_id)
            .filter(DBMatch.provider_id == numeric, ProviderSource.name == provider_name)
            .first()
        )
    if db_match is not None:
        home = session.get(DBTeam, db_match.home_team_id)
        away = session.get(DBTeam, db_match.away_team_id)
        return MatchTeams(
            home_name=home.name if home else None,
            away_name=away.name if away else None,
            db_match_id=db_match.id,
            resolved_from="matches_table",
        )

    if explicit_home and explicit_away:
        return MatchTeams(explicit_home, explicit_away, None, "json")

    if api_base:
        payload = _fetch_api_match(api_base, match_id)
        if isinstance(payload, dict) and isinstance(payload.get("match"), dict):
            payload = payload["match"]  # MatchDetailResponse wraps the match
        if payload:
            home_info = payload.get("home_team") or {}
            away_info = payload.get("away_team") or {}
            home_name = home_info.get("name") or payload.get("home_team_name")
            away_name = away_info.get("name") or payload.get("away_team_name")
            # Prefer the canonical DB team names when the ids are known
            for info, role in ((home_info, "home"), (away_info, "away")):
                team_id = info.get("id") or payload.get(f"{role}_team_id")
                if team_id:
                    team = session.get(DBTeam, team_id)
                    if team is not None:
                        if role == "home":
                            home_name = team.name
                        else:
                            away_name = team.name
            if home_name and away_name:
                return MatchTeams(home_name, away_name, None, "api")

    parts = [p.strip() for p in (label or "").split(" - ")]
    if len(parts) == 2 and all(parts):
        return MatchTeams(parts[0], parts[1], None, "label")
    return MatchTeams(None, None, None, "unresolved")


def _valid_price(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if price > 1.0 else None


# ---------------------------------------------------------------------------
# sampiyonlar-ligi markdown report parsing
# ---------------------------------------------------------------------------
#
# Table rows look like (bold markers optional, market cell empty on
# continuation rows):
#   | **Maç Sonucu (1X2)** | **Arsenal Galibiyeti (1)** | **1.22** | ... |
#   | **Çifte Şans** | 1X (Arsenal veya Beraberlik) | 1.05 | ... |
#   | **2.5 Gol Alt/Üst** | 2.5 Gol Alt | 2.50 (+150) | ... |
#   | **Karşılıklı Gol (KG)** | KG Var (İki takım da atar) | 2.10 (+110) | ... |
# Only these four explicit markets are read. Handicap, first-half, team
# specials ("~" approximate bullet values) are NOT parsed.

class MarkdownOddsError(ValueError):
    """Raised when report files are inconsistent or unparsable."""


_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_TOTALS_MARKET_RE = re.compile(r"^(\d+(?:\.\d+)?) gol alt/ust$")
_TOTALS_SELECTION_RE = re.compile(r"^(\d+(?:\.\d+)?) gol (ust|alt)\b")


def _md_norm(text: str) -> str:
    text = text.replace("*", "").replace("ı", "i").replace("İ", "I")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


def _md_market_kind(market_cell: str) -> Optional[Tuple[str, Optional[str]]]:
    m = _md_norm(market_cell)
    if "mac sonucu" in m and "1x2" in m:
        return ("1x2", None)
    if m.startswith("cifte sans"):
        return ("dc", None)
    totals = _TOTALS_MARKET_RE.match(m)
    if totals:
        return ("totals", totals.group(1))
    if m.startswith("karsilikli gol"):
        return ("btts", None)
    return None


def _md_field(kind: Tuple[str, Optional[str]], selection_cell: str) -> Optional[str]:
    sel = _md_norm(selection_cell)
    market, line = kind
    if market == "1x2":
        for suffix, field_name in (("(1)", "odds_1"), ("(x)", "odds_x"), ("(2)", "odds_2")):
            if sel.endswith(suffix):
                return field_name
        return None
    if market == "dc":
        token = sel.split(" ", 1)[0]
        return {"1x": "dc_1x", "12": "dc_12", "x2": "dc_x2"}.get(token)
    if market == "totals":
        m = _TOTALS_SELECTION_RE.match(sel)
        if not m or m.group(1) != line:
            return None
        suffix = line.replace(".", "_")
        return f"{'over' if m.group(2) == 'ust' else 'under'}_{suffix}"
    if market == "btts":
        if sel.startswith("kg var"):
            return "btts_yes"
        if sel.startswith("kg yok"):
            return "btts_no"
    return None


def parse_odds_markdown(text: str) -> Dict[str, float]:
    """Parse explicit 1X2 / double chance / totals / BTTS prices from one report."""
    prices: Dict[str, float] = {}
    kind: Optional[Tuple[str, Optional[str]]] = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            kind = None
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        if cells[0]:
            kind = _md_market_kind(cells[0])
        if kind is None:
            continue
        field_name = _md_field(kind, cells[1])
        if field_name is None:
            continue
        number = _NUMBER_RE.search(cells[2].replace("*", ""))
        if number is None:
            continue
        price = float(number.group(0))
        if field_name in prices and prices[field_name] != price:
            raise MarkdownOddsError(
                f"conflicting prices for {field_name}: {prices[field_name]} vs {price}"
            )
        prices[field_name] = price
    return prices


def odds_from_markdown_folder(folder: str) -> Tuple[Dict[str, float], List[str]]:
    """Merge the prices of every *.md file in a match folder.

    Raises MarkdownOddsError when two files disagree on a price.
    Returns (prices, file names read).
    """
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".md"))
    if not files:
        raise MarkdownOddsError(f"no .md files in {folder}")
    merged: Dict[str, float] = {}
    origin: Dict[str, str] = {}
    for name in files:
        with open(os.path.join(folder, name), encoding="utf-8") as fh:
            parsed = parse_odds_markdown(fh.read())
        for key, price in parsed.items():
            if key in merged and merged[key] != price:
                raise MarkdownOddsError(
                    f"{folder}: {key} is {merged[key]} in {origin[key]} but {price} in {name}"
                )
            merged[key] = price
            origin.setdefault(key, name)
    return merged, files


def merge_markdown_odds(payload: Dict[str, Any], markdown_dir: str) -> List[str]:
    """Fill / cross-check payload prices from DIR/<folder>/*.md (in place).

    Returns human-readable notes. Raises MarkdownOddsError on any mismatch
    between the JSON and the report files, so nothing inconsistent is loaded.
    """
    notes: List[str] = []
    mismatches: List[str] = []
    for entry in payload.get("matches", []):
        folder = entry.get("folder")
        if not folder:
            continue
        prices, files = odds_from_markdown_folder(os.path.join(markdown_dir, folder))
        filled = []
        for key in PRICE_FIELDS:
            if key not in prices:
                continue
            if entry.get(key) is None:
                entry[key] = prices[key]
                filled.append(key)
            elif abs(float(entry[key]) - prices[key]) > 1e-9:
                mismatches.append(
                    f"{entry.get('match_id')} {key}: json={entry[key]} markdown={prices[key]}"
                )
        notes.append(
            f"{entry.get('match_id')} <- {folder} ({', '.join(files)}): "
            f"{len(prices)} prices, filled {filled or 'nothing'}"
        )
    if mismatches:
        raise MarkdownOddsError("JSON/markdown mismatch: " + "; ".join(mismatches))
    return notes


def upsert_manual_odds(
    session: Session,
    entry: Dict[str, Any],
    teams: MatchTeams,
    calculated_at: datetime,
) -> LoadResult:
    """Upsert AverageMarketOdds rows for one manual odds entry (no commit)."""
    match_id = entry["match_id"]
    result = LoadResult(match_id=match_id, label=entry.get("label", ""), teams=teams)
    event_id = manual_provider_event_id(match_id)

    wanted: Dict[Tuple[str, Optional[float], str], float] = {}
    for json_field, market_key, point, outcome in FIELD_SPECS:
        if json_field not in entry:
            continue  # not supplied at all
        price = _valid_price(entry.get(json_field))
        if price is None:
            result.skipped_fields.append(json_field)
            continue
        if outcome == HOME_ROLE:
            outcome = teams.home_name
        elif outcome == AWAY_ROLE:
            outcome = teams.away_name
        if not outcome:
            result.skipped_fields.append(json_field)
            continue
        wanted[(market_key, point, outcome)] = price

    existing_rows = session.query(AverageMarketOdds).filter(
        AverageMarketOdds.provider_event_id == event_id
    ).all()
    existing = {(r.market_key, r.market_point, r.outcome_name): r for r in existing_rows}

    # Remove manual rows for this event that are no longer supplied
    # (e.g. a team name changed between runs). Only manual rows are touched.
    for key, row in existing.items():
        if key not in wanted:
            session.delete(row)
            result.removed_stale += 1

    for (market_key, point, outcome), price in wanted.items():
        row = existing.get((market_key, point, outcome))
        if row is None:
            session.add(AverageMarketOdds(
                provider_event_id=event_id,
                match_id=teams.db_match_id,
                market_key=market_key,
                market_point=point,
                outcome_name=outcome,
                average_odds=price,
                bookmaker_count=1,
                min_odds=price,
                max_odds=price,
                bookmakers=[MANUAL_ODDS_SOURCE],
                individual_odds=[price],
                calculated_at=calculated_at,
            ))
            result.created += 1
        else:
            row.match_id = teams.db_match_id
            row.average_odds = price
            row.bookmaker_count = 1
            row.min_odds = price
            row.max_odds = price
            row.bookmakers = [MANUAL_ODDS_SOURCE]
            row.individual_odds = [price]
            row.calculated_at = calculated_at
            row.updated_at = calculated_at
            result.updated += 1
    return result


def load_manual_odds(
    session: Session,
    payload: Dict[str, Any],
    api_base: Optional[str],
    calculated_at: Optional[datetime] = None,
) -> List[LoadResult]:
    """Load every entry of a manual odds payload (caller commits)."""
    calculated_at = calculated_at or datetime.now(timezone.utc)
    results: List[LoadResult] = []
    for entry in payload.get("matches", []):
        match_id = entry.get("match_id")
        if not match_id:
            results.append(LoadResult(match_id="?", label=entry.get("label", ""), error="missing match_id"))
            continue
        teams = resolve_match_teams(
            session, match_id, entry.get("label", ""), api_base,
            explicit_home=entry.get("home_team"), explicit_away=entry.get("away_team"),
        )
        results.append(upsert_manual_odds(session, entry, teams, calculated_at))
    return results


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Load user-supplied (manual) odds into average_market_odds")
    parser.add_argument("json_path", help="Path to manual odds JSON file")
    parser.add_argument("--database-url", default=None, help="SQLAlchemy URL (default: app settings DATABASE_URL)")
    parser.add_argument(
        "--api-base", default="http://127.0.0.1:8003",
        help="Running backend used to resolve team names of fixtures not in the matches table ('' to disable)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Resolve and print, then roll back")
    parser.add_argument(
        "--markdown-dir", default=None,
        help="Folder with per-match report folders (e.g. ../sampiyonlar-ligi); "
             "fills and cross-checks prices of entries that name a 'folder'",
    )
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    with open(args.json_path, encoding="utf-8") as fh:
        payload = json.load(fh)

    if args.markdown_dir:
        try:
            for note in merge_markdown_odds(payload, args.markdown_dir):
                print(f"  [markdown] {note}")
        except (MarkdownOddsError, OSError) as exc:
            print(f"  [error] markdown cross-check failed, nothing written: {exc}")
            return 2

    if args.database_url:
        database_url = args.database_url
    else:
        from app.config import settings
        database_url = settings.database_url

    print("=" * 70)
    print("TUTAR X - Manual (user-supplied, unverified) odds loader")
    print(f"Database : {database_url}")
    print(f"Source   : {payload.get('source', '(not given)')}")
    print(f"Entries  : {len(payload.get('matches', []))}")
    print("=" * 70)

    connect_args = {"timeout": 60} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, future=True, connect_args=connect_args)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)
    session = SessionLocal()
    try:
        results = load_manual_odds(session, payload, args.api_base or None)
        for r in results:
            if r.error:
                print(f"  [error] {r.label}: {r.error}")
                continue
            t = r.teams
            print(
                f"  {r.match_id:<16} {r.label:<34} home={t.home_name!r} away={t.away_name!r} "
                f"(teams via {t.resolved_from}, db_match_id={t.db_match_id}) "
                f"created={r.created} updated={r.updated} removed_stale={r.removed_stale}"
                + (f" skipped={r.skipped_fields}" if r.skipped_fields else "")
            )
        if args.dry_run:
            session.rollback()
            print("Dry run: rolled back, nothing written.")
        else:
            session.commit()
            total = sum(r.created + r.updated for r in results)
            print(f"Committed {total} rows (source={MANUAL_ODDS_SOURCE}).")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
