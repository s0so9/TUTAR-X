"""Backfill matches.home_xg / away_xg from the collected FotMob match details.

Only fills rows whose xG is NULL, matched by matches.provider_id; never
overwrites existing values and never writes 0 for a missing xG.

Usage (from backend/): venv/Scripts/python.exe scripts/training/backfill_match_xg.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="football_intelligence.db")
    ap.add_argument("--details", default="data/training/fotmob_match_details.jsonl")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    values = []
    with open(args.details, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("home_xg") is None or r.get("away_xg") is None:
                continue
            values.append((float(r["home_xg"]), float(r["away_xg"]), str(r["match_provider_id"])))

    con = sqlite3.connect(Path(args.db).as_posix(), timeout=30)
    before = con.execute("select count(*) from matches where home_xg is not null").fetchone()[0]
    if not args.dry_run:
        con.executemany(
            "update matches set home_xg = ?, away_xg = ? where provider_id = ? and home_xg is null and away_xg is null",
            values,
        )
        con.commit()
    after = con.execute("select count(*) from matches where home_xg is not null").fetchone()[0]
    con.close()
    print(f"xG rows available: {len(values)}; matches with xG before={before} after={after}{' (dry run)' if args.dry_run else ''}")


if __name__ == "__main__":
    main()
