"""Backfill the team-news live layer from the FotMob raw caches (no network).

Idempotent import (re-running changes nothing) of:
  * data/raw_cache/fotmob_match_details/<match id>.json.gz
      -> player_match_stats, lineup_snapshots, match-time player_availability
         (stamped with the kickoff, timestamp_basis = match_kickoff),
         team_news_matches, players (identity + light profile)
      index: data/training/fotmob_match_details.jsonl (ids + fetched_at of the
      collector) when present, else every <digits>.json.gz (fetched_at = file mtime)
  * data/raw_cache/fotmob_teams/_manifest.jsonl + <team id>.json.gz
      -> players (squad profile), team_squad_members, squad availability
  * data/raw_cache/fotmob_players/_manifest.jsonl + <player id>.json.gz
      -> players (full profile), profile availability
  * (optional --include-live) data/raw_cache/live_team_news/<kind>/_manifest.jsonl
Only files listed in a manifest (http_status 200) are read; unreadable or
partial files and partial manifest lines are skipped and counted.

Usage (from backend/):
  venv/Scripts/python.exe scripts/live/load_player_data.py --database-url sqlite:///C:/tmp/copy.db
The database must already be at Alembic revision 20261013_team_news. The
production file needs --allow-production-db (never the default).
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

BACKEND_DIR = Path(__file__).resolve().parents[2]
PRODUCTION_DB = (BACKEND_DIR / "football_intelligence.db").resolve()
RAW_ROOT = BACKEND_DIR / "data" / "raw_cache"
DETAILS_INDEX = BACKEND_DIR / "data" / "training" / "fotmob_match_details.jsonl"
LIVE_TABLES = ("team_squad_members", "player_availability", "player_match_stats", "lineup_snapshots", "team_news_matches")


def sqlite_path(url: str) -> Optional[Path]:
    if not url.startswith("sqlite:///"):
        return None
    raw = url[len("sqlite:///"):]
    if not raw or raw == ":memory:":
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve()


def guard_database_url(url: str, allow_production: bool) -> None:
    path = sqlite_path(url)
    if path is not None and path == PRODUCTION_DB and not allow_production:
        raise SystemExit(
            f"refusing to write to the production database {PRODUCTION_DB} without --allow-production-db"
        )


def parse_iso(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def read_manifest(path: Path) -> dict[str, datetime]:
    """id -> latest fetched_at of the lines with http_status 200 (partial lines skipped)."""
    out: dict[str, datetime] = {}
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("http_status") != 200 or rec.get("id") is None:
                continue
            at = parse_iso(rec.get("fetched_at"))
            if at is None:
                continue
            key = str(rec["id"])
            if key not in out or at > out[key]:
                out[key] = at
    return out


def details_index(raw_dir: Path, all_files: bool) -> list[tuple[str, datetime]]:
    """(match id, fetched_at) of the match-details raw files to import."""
    entries: dict[str, datetime] = {}
    if DETAILS_INDEX.exists() and not all_files:
        pat_id = re.compile(r'"match_provider_id":\s*"(\d+)"')
        pat_at = re.compile(r'"fetched_at":\s*"([^"]+)"\s*}?\s*$')
        with DETAILS_INDEX.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m_id = pat_id.search(line[:200])
                m_at = pat_at.search(line[-120:])
                if not m_id:
                    continue
                at = parse_iso(m_at.group(1)) if m_at else None
                f = raw_dir / f"{m_id.group(1)}.json.gz"
                if at is None and f.exists():
                    at = datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)
                if at is not None:
                    entries[m_id.group(1)] = at
    else:
        for f in raw_dir.glob("*.json.gz"):
            stem = f.name[: -len(".json.gz")]
            if stem.isdigit():
                entries[stem] = datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)
    return sorted(entries.items(), key=lambda kv: (kv[1], kv[0]))


def load_gz(path: Path) -> Any:
    return json.loads(gzip.decompress(path.read_bytes()))


def iter_live_manifest(root: Path, kind: str) -> Iterator[tuple[str, datetime, Path]]:
    manifest = root / kind / "_manifest.jsonl"
    if not manifest.exists():
        return
    rows = []
    with manifest.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            at = parse_iso(rec.get("fetched_at"))
            if rec.get("http_status") == 200 and at and rec.get("path"):
                rows.append((str(rec.get("id")), at, root / rec["path"]))
    rows.sort(key=lambda r: r[1])
    yield from rows


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--database-url", required=True, help="target DB (required; e.g. sqlite:///C:/tmp/copy.db)")
    ap.add_argument("--allow-production-db", action="store_true", help="permit backend/football_intelligence.db")
    ap.add_argument("--raw-root", default=str(RAW_ROOT))
    ap.add_argument("--only", choices=("all", "matches", "teams", "players"), default="all")
    ap.add_argument("--all-files", action="store_true", help="match details: every <id>.json.gz, not the dataset index")
    ap.add_argument("--include-live", action="store_true", help="also replay raw_cache/live_team_news manifests")
    ap.add_argument("--limit", type=int, default=0, help="at most N files per kind (testing)")
    ap.add_argument("--batch-size", type=int, default=200)
    args = ap.parse_args(argv)

    guard_database_url(args.database_url, args.allow_production_db)
    os.environ["DATABASE_URL"] = args.database_url  # before any app import: the app engine points here too
    sys.path.insert(0, str(BACKEND_DIR))

    from sqlalchemy import create_engine, func, inspect, select
    from sqlalchemy.orm import sessionmaker

    from app.database.models import (
        LineupSnapshot, Player, PlayerAvailability, PlayerMatchStat, TeamNewsMatch, TeamSquadMember,
    )
    from app.services.team_news.parsers import PayloadError
    from app.services.team_news.service import apply_match_payload, apply_player_payload, apply_team_payload
    from app.services.team_news.store import TeamNewsStore

    engine = create_engine(args.database_url, future=True)
    missing = [t for t in LIVE_TABLES if t not in set(inspect(engine).get_table_names())]
    if missing:
        print(f"ERROR: tables {missing} missing - run `alembic upgrade head` on this database first", file=sys.stderr)
        return 2
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    raw_root = Path(args.raw_root)
    t_start = time.monotonic()
    report: dict[str, Any] = {"database_url": args.database_url}

    session = Session()
    store = TeamNewsStore(session)
    report["players_preloaded"] = store.preload_players()

    def run_kind(name: str, items: list[tuple[str, datetime, Path]], apply_fn, **kw) -> dict[str, Any]:
        """Apply files in batches; one commit per batch. Unreadable files and payload
        errors are skipped before any write; an unexpected DB error rolls the batch
        back and the batch is replayed without the failing file."""
        stats = {"files": len(items), "ok": 0, "unreadable": 0, "payload_errors": 0, "errors": 0}
        t0 = time.monotonic()

        def apply_batch(batch: list[tuple[str, datetime, Path]]) -> None:
            pending = list(batch)
            while pending:
                ok = unreadable = payload = 0
                failed_at = None
                try:
                    for idx, (entity_id, at, path) in enumerate(pending):
                        failed_at = idx
                        try:
                            data = load_gz(path)
                        except (OSError, EOFError, ValueError, gzip.BadGzipFile):
                            unreadable += 1
                            continue
                        try:
                            apply_fn(store, data, at, **kw)
                            session.flush()  # surface DB errors at the file that caused them
                            ok += 1
                        except PayloadError:
                            payload += 1
                    session.commit()
                except Exception as exc:
                    session.rollback()
                    store._players.clear()
                    store.preload_players()
                    stats["errors"] += 1
                    entity_id = pending[failed_at][0] if failed_at is not None else "?"
                    if stats["errors"] <= 5:
                        print(f"  [{name}] {entity_id}: {type(exc).__name__}: {exc}", file=sys.stderr)
                    pending = pending[:failed_at] + pending[failed_at + 1 :] if failed_at is not None else []
                    continue
                stats["ok"] += ok
                stats["unreadable"] += unreadable
                stats["payload_errors"] += payload
                return

        for i in range(0, len(items), args.batch_size):
            apply_batch(items[i : i + args.batch_size])
            done = min(i + args.batch_size, len(items))
            print(f"  [{name}] {done}/{len(items)} ok={stats['ok']} ({time.monotonic() - t0:.0f}s)", flush=True)
        stats["seconds"] = round(time.monotonic() - t0, 1)
        return stats

    try:
        if args.only in ("all", "matches"):
            details_dir = raw_root / "fotmob_match_details"
            idx = details_index(details_dir, args.all_files)
            items = [(mid, at, details_dir / f"{mid}.json.gz") for mid, at in idx if (details_dir / f"{mid}.json.gz").exists()]
            if args.limit:
                items = items[: args.limit]
            store.match_ids([mid for mid, _, _ in items])  # warm the provider id -> matches.id cache
            print(f"match details: {len(items)} files", flush=True)
            report["match_details"] = run_kind("match_details", items, apply_match_payload, ingest_stats=True)
        if args.only in ("all", "teams"):
            d = raw_root / "fotmob_teams"
            man = read_manifest(d / "_manifest.jsonl")
            items = sorted(((k, at, d / f"{k}.json.gz") for k, at in man.items()), key=lambda r: r[1])
            if args.limit:
                items = items[: args.limit]
            print(f"teams: {len(items)} manifest entries", flush=True)
            report["teams"] = run_kind("teams", items, apply_team_payload)
        if args.only in ("all", "players"):
            d = raw_root / "fotmob_players"
            man = read_manifest(d / "_manifest.jsonl")
            items = sorted(((k, at, d / f"{k}.json.gz") for k, at in man.items()), key=lambda r: r[1])
            if args.limit:
                items = items[: args.limit]
            print(f"players: {len(items)} manifest entries", flush=True)
            report["players"] = run_kind("players", items, apply_player_payload)
        if args.include_live:
            live = raw_root / "live_team_news"
            for kind, fn, kw in (
                ("teams", apply_team_payload, {}),
                ("players", apply_player_payload, {}),
                ("match_details", apply_match_payload, {"ingest_stats": True}),
            ):
                items = list(iter_live_manifest(live, kind))
                report[f"live_{kind}"] = run_kind(f"live_{kind}", items, fn, **kw)
    finally:
        session.close()

    with Session() as s:
        report["row_counts"] = {
            "players": s.scalar(select(func.count()).select_from(Player)),
            "players_with_profile": s.scalar(
                select(func.count()).select_from(Player).where(Player.profile_source == "fotmob_player_profile")
            ),
            "team_squad_members": s.scalar(select(func.count()).select_from(TeamSquadMember)),
            "player_availability": s.scalar(select(func.count()).select_from(PlayerAvailability)),
            "player_availability_active": s.scalar(
                select(func.count()).select_from(PlayerAvailability).where(PlayerAvailability.cleared_at.is_(None))
            ),
            "player_match_stats": s.scalar(select(func.count()).select_from(PlayerMatchStat)),
            "player_match_stats_with_match_fk": s.scalar(
                select(func.count()).select_from(PlayerMatchStat).where(PlayerMatchStat.match_id.is_not(None))
            ),
            "lineup_snapshots": s.scalar(select(func.count()).select_from(LineupSnapshot)),
            "team_news_matches": s.scalar(select(func.count()).select_from(TeamNewsMatch)),
        }
    report["seconds_total"] = round(time.monotonic() - t_start, 1)
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
