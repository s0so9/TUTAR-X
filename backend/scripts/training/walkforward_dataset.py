"""Build an out-of-sample dataset of rating-model expected goals.

For every weekly cutoff, global ratings are fitted on finished matches strictly
before the cutoff and used to predict the following seven days. Each row is a
genuine pre-match prediction (no look-ahead), suitable for training
calibration, Dixon-Coles rho, goal level, and blending layers.

Usage (from backend/):
    venv/Scripts/python.exe scripts/training/walkforward_dataset.py \
        --start 2026-01-05 --end 2026-10-12 --out data/training/walkforward_lambdas.csv
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.prediction.team_ratings import (  # noqa: E402
    DEFAULT_LOOKBACK_DAYS,
    XG_GOAL_WEIGHT,
    GlobalPoissonRatings,
    domestic_groups,
)

EURO_PROVIDER_IDS = {"42", "73", "10216"}


def load_matches(db_path: Path):
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    rows = con.execute(
        """select m.id, m.home_team_id, m.away_team_id, m.home_score, m.away_score, m.scheduled_at,
                  m.competition_id, coalesce(c.name, ''), coalesce(c.provider_id, ''), m.home_xg, m.away_xg
           from matches m left join competitions c on c.id = m.competition_id
           where m.status = 'FINISHED' and m.home_score is not null and m.away_score is not null
           order by m.scheduled_at"""
    ).fetchall()
    con.close()
    return [
        {
            "id": r[0], "home": r[1], "away": r[2], "hs": r[3], "as": r[4],
            "at": datetime.fromisoformat(r[5][:19]), "comp_id": r[6], "comp_name": r[7], "comp_pid": r[8],
            "hxg": r[9], "axg": r[10],
        }
        for r in rows
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="football_intelligence.db")
    parser.add_argument("--start", default="2026-01-05")
    parser.add_argument("--end", default="2026-10-12")
    parser.add_argument("--step-days", type=int, default=7)
    parser.add_argument("--out", default="data/training/walkforward_lambdas.csv")
    args = parser.parse_args()

    data = load_matches(Path(args.db))
    print(f"{len(data)} finished matches loaded", flush=True)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    cutoff = datetime.fromisoformat(args.start)
    end = datetime.fromisoformat(args.end)
    written = 0
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "match_id", "kickoff", "cutoff", "competition_id", "competition_provider_id", "competition_name",
            "is_euro", "home_team_id", "away_team_id", "home_matches", "away_matches",
            "lambda_home", "lambda_away", "home_score", "away_score",
        ])
        while cutoff < end:
            t0 = time.time()
            window_end = cutoff + timedelta(days=args.step_days)
            train = [d for d in data if cutoff - timedelta(days=DEFAULT_LOOKBACK_DAYS) <= d["at"] < cutoff]
            test = [d for d in data if cutoff <= d["at"] < window_end]
            if train and test:
                groups = domestic_groups(
                    [d["home"] for d in train], [d["away"] for d in train],
                    [d["comp_name"] for d in train], [d["comp_id"] for d in train],
                )
                w = XG_GOAL_WEIGHT

                def target(goals, xg):
                    return goals if xg is None or w >= 1.0 else w * goals + (1 - w) * xg

                ratings = GlobalPoissonRatings().fit(
                    [d["home"] for d in train], [d["away"] for d in train],
                    [target(d["hs"], d["hxg"]) for d in train], [target(d["as"], d["axg"]) for d in train],
                    [(cutoff - d["at"]).total_seconds() / 86400 for d in train],
                    team_groups=groups,
                )
                n = 0
                for d in test:
                    lam = ratings.predict(d["home"], d["away"])
                    if lam is None:
                        continue
                    writer.writerow([
                        d["id"], d["at"].isoformat(), cutoff.date().isoformat(), d["comp_id"], d["comp_pid"],
                        d["comp_name"], int(d["comp_pid"] in EURO_PROVIDER_IDS), d["home"], d["away"],
                        lam.home_matches, lam.away_matches, f"{lam.home:.5f}", f"{lam.away:.5f}", d["hs"], d["as"],
                    ])
                    n += 1
                written += n
                f.flush()
                print(f"{cutoff.date()}: train={len(train)} predicted={n} ({time.time() - t0:.1f}s)", flush=True)
            cutoff = window_end
    print(f"DONE rows={written} -> {out}", flush=True)


if __name__ == "__main__":
    main()
