"""One pass of the headline pick tracker (Banko / Oranlı), for manual runs and the backfill.

The same code the in-app background loop runs every 60 s (app/services/headline_tracking):
  * freezes the Banko / Oranlı of every featured-competition match that kicks off within
    settings.headline_freeze_minutes_before (20) minutes, from a fresh prediction;
  * settles frozen picks whose match is over (local FINISHED row first, then the live centre).

Usage (from backend/):
  venv/Scripts/python.exe scripts/live/headline_tracking.py --once --database-url sqlite:///C:/tmp/copy.db
  ... --once --database-url <url> --now 2026-10-15T16:30:00Z        (pretend it is that time)
  ... --backfill-2026-10-14 --database-url <url>                     (import the hand-tracked night)
  ... --backfill-2026-10-14 --no-live --database-url <url>           (settle from the local matches table only)
The production database file needs --allow-production-db (the in-app loop writes there on its own).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from load_player_data import guard_database_url  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="run one tracker tick (freeze + settle) and exit")
    ap.add_argument("--backfill-2026-10-14", action="store_true", dest="backfill",
                    help="import the hand-tracked night of 2026-10-14 as already-frozen records and settle them")
    ap.add_argument("--database-url", default=None, help="default: DATABASE_URL / settings.database_url")
    ap.add_argument("--allow-production-db", action="store_true")
    ap.add_argument("--now", default=None, help="ISO time to act as 'now' (tests on a database copy)")
    ap.add_argument("--no-live", action="store_true",
                    help="never call FotMob: results only from the local matches table, no live line-up lookup")
    ap.add_argument("--picks-file", default=str(REPO_ROOT / "docs/live-tests/2026-10-14/system_picks.json"))
    ap.add_argument("--listing-file", default=str(REPO_ROOT / "docs/live-tests/2026-10-14/cl_2026-10-14.json"))
    return ap


async def run(args: argparse.Namespace) -> dict[str, Any]:
    from datetime import datetime, timezone

    from app.database.session import SessionLocal
    from app.services.headline_tracking.backfill import backfill_manual_2026_10_14
    from app.services.headline_tracking.records import parse_iso
    from app.services.headline_tracking.results import ChainedResultFetcher, DbResultFetcher, LiveCenterResultFetcher
    from app.services.headline_tracking.tracker import HeadlineTracker

    fetchers = [DbResultFetcher(SessionLocal)] + ([] if args.no_live else [LiveCenterResultFetcher()])
    results = ChainedResultFetcher(fetchers)
    out: dict[str, Any] = {}
    try:
        if args.backfill:
            out["backfill"] = await backfill_manual_2026_10_14(
                SessionLocal, results, picks_file=Path(args.picks_file),
                listing_file=Path(args.listing_file) if args.listing_file else None,
            )
        if args.once:
            tracker_kwargs: dict[str, Any] = {"results": results}
            if args.no_live:
                async def no_lineup(_match_id: str) -> Optional[dict]:
                    return None

                tracker_kwargs["lineup_lookup"] = no_lineup
            tracker = HeadlineTracker(SessionLocal, **tracker_kwargs)
            now = parse_iso(args.now) if args.now else datetime.now(timezone.utc)
            out["tick"] = await tracker.tick(now)
    finally:
        try:  # close the live-centre HTTP client when one was created
            from app.services.live_center import service as live_service

            client = getattr(live_service.get_live_center_service(), "_client", None)
            if client is not None:
                await client.aclose()
        except Exception:  # noqa: BLE001 - shutdown housekeeping only
            pass
    return out


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not (args.once or args.backfill):
        print("nothing to do: pass --once and/or --backfill-2026-10-14", file=sys.stderr)
        return 2
    if args.database_url:
        guard_database_url(args.database_url, args.allow_production_db)
        os.environ["DATABASE_URL"] = args.database_url  # before any app import
    else:
        from_env = os.environ.get("DATABASE_URL", "")
        if not from_env:
            print("pass --database-url (or set DATABASE_URL): refusing to guess the target database", file=sys.stderr)
            return 2
        guard_database_url(from_env, args.allow_production_db)
    sys.path.insert(0, str(BACKEND_DIR))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    summary = asyncio.run(run(args))
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
