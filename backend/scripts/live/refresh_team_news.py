"""One refresh cycle of the team-news live layer (for cron / manual runs).

Discovers the target-competition matches (local DB + FotMob league fixtures),
refreshes the pre-match team news (line-up snapshots, match unavailable lists)
of matches kicking off within --hours-ahead, ingests player stats of matches
finished within --lookback-hours, and refreshes squads (--squads).

Politeness: <= 1 request/s in-process plus the shared cross-process limiter
(scripts/data_collection/fotmob_rate.py) before every request; a 429 stops the
run (exit 2) after reporting the cool-down; a 403/captcha/challenge stops it
(exit 3). Raw responses whose relevant content changed are kept under
data/raw_cache/live_team_news (unless --no-raw).

Usage (from backend/):
  venv/Scripts/python.exe scripts/live/refresh_team_news.py --once --database-url sqlite:///C:/tmp/copy.db
  ... --once --hours-ahead 72 --squads all --database-url <url>
  ... --once --match-id 6106260 --database-url <url>          (one match only)
  ... --once --team-id 9825 --player-id 955406 --database-url <url>
The production file needs --allow-production-db.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from load_player_data import LIVE_TABLES, guard_database_url  # noqa: E402

EXIT_OK, EXIT_RATE_LIMITED, EXIT_BLOCKED, EXIT_NOT_MIGRATED = 0, 2, 3, 4


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", required=True, help="run one cycle and exit")
    ap.add_argument("--database-url", required=True)
    ap.add_argument("--allow-production-db", action="store_true")
    ap.add_argument("--hours-ahead", type=float, default=72.0)
    ap.add_argument("--lookback-hours", type=float, default=24.0)
    ap.add_argument("--competitions", default=None, help="FotMob league ids (default: settings.team_news_competitions)")
    ap.add_argument("--squads", choices=("none", "window", "all"), default="window")
    ap.add_argument("--max-requests", type=int, default=800, help="safety cap per run")
    ap.add_argument("--no-fixtures", action="store_true", help="discover matches from the local DB only")
    ap.add_argument("--no-finished", action="store_true", help="skip the finished-match stats ingest")
    ap.add_argument("--no-raw", action="store_true", help="do not keep raw responses")
    ap.add_argument("--match-id", action="append", default=[], help="refresh only these FotMob match ids")
    ap.add_argument("--team-id", action="append", default=[], help="refresh only these squads")
    ap.add_argument("--player-id", action="append", default=[], help="refresh these player profiles")
    return ap


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    guard_database_url(args.database_url, args.allow_production_db)
    os.environ["DATABASE_URL"] = args.database_url  # before any app import
    sys.path.insert(0, str(BACKEND_DIR))

    from sqlalchemy import create_engine, inspect
    from sqlalchemy.orm import sessionmaker

    from app.config import settings
    from app.services.team_news.fotmob_client import (
        FotMobBlockedError,
        FotMobRateLimitedError,
        TeamNewsFotMobClient,
    )
    from app.services.team_news.raw_store import RawStore, default_raw_store
    from app.services.team_news.scheduler import parse_competitions
    from app.services.team_news.service import TeamNewsService

    engine = create_engine(args.database_url, future=True)
    missing = [t for t in LIVE_TABLES if t not in set(inspect(engine).get_table_names())]
    if missing:
        print(f"ERROR: tables {missing} missing - apply Alembic revision 20261013_team_news first", file=sys.stderr)
        return EXIT_NOT_MIGRATED
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    competitions = parse_competitions(args.competitions or settings.team_news_competitions)
    client = TeamNewsFotMobClient()
    service = TeamNewsService(factory, client, RawStore(None) if args.no_raw else default_raw_store())

    async def run() -> dict[str, Any]:
        try:
            if args.match_id or args.team_id or args.player_id:
                out: dict[str, Any] = {"matches": [], "squads": None, "players": None}
                for mid in args.match_id:
                    # stats are ingested only when the response says the match is finished
                    out["matches"].append(await service.ingest_finished_match(mid))
                if args.team_id:
                    out["squads"] = await service.refresh_team_squads(args.team_id)
                if args.player_id:
                    out["players"] = await service.refresh_player_profiles(args.player_id, max_players=len(args.player_id))
                out["requests"] = client.request_count
                return out
            return await service.run_cycle(
                hours_ahead=args.hours_ahead,
                lookback_hours=args.lookback_hours,
                competitions=competitions,
                squads=args.squads,
                finished=not args.no_finished,
                max_requests=args.max_requests,
                use_fixtures=not args.no_fixtures,
            )
        finally:
            await client.aclose()

    try:
        summary = asyncio.run(run())
    except FotMobBlockedError as exc:
        print(f"STOPPED: FotMob refused or challenged the request ({exc}). Not retrying.", file=sys.stderr)
        return EXIT_BLOCKED
    except FotMobRateLimitedError as exc:
        print(f"STOPPED: rate limited ({exc}); the shared limiter cool-down was set.", file=sys.stderr)
        return EXIT_RATE_LIMITED
    summary["raw_saved"] = service.raw_store.saved
    print(json.dumps(summary, indent=2, default=str))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
