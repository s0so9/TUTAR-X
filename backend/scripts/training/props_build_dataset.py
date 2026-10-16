"""Props dataset (props:train, 2026-10-14): one row per match with home/away counts of corners, yellow cards,
total shots, shots on target and fouls + referee name.

Inputs (read only, no network):
  data/training/fotmob_match_details.jsonl          (6,798 matches, 2025-07 .. 2026-10-12)
  data/training/fotmob_match_details_history.jsonl  (13,250 matches, 2022/23 .. 2024/25 + tails)
  data/raw_cache/fotmob_match_details/<id>.json.gz  (ONLY content.matchFacts.infoBox.Referee.text is read)

Honesty rules (AGENTS.md 10, 14): a stat FotMob did not send is an empty cell (missing) and the match is
excluded from that stat's fit and evaluation (and counted in the report); it is never replaced by 0.
Awarded matches are excluded entirely. Cancelled matches are not in the files (collector drops them).

Output: data/training/props_match_stats.csv.gz and data/training/props_dataset_report.json (coverage per
stat and per competition, duplicates, referee read errors).

Usage (from backend/):
  venv/Scripts/python.exe scripts/training/props_build_dataset.py
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Optional

TRAINING_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TRAINING_DIR.parents[1]
DATA = BACKEND_DIR / "data" / "training"
RAW = BACKEND_DIR / "data" / "raw_cache" / "fotmob_match_details"

SOURCES = ["fotmob_match_details.jsonl", "fotmob_match_details_history.jsonl"]
# model stat name -> FotMob team_stats key
STAT_KEYS = {
    "corners": "corners",
    "yellow_cards": "yellow_cards",
    "total_shots": "total_shots",
    "shots_on_target": "ShotsOnTarget",
    "fouls": "fouls",
}
STATS = list(STAT_KEYS)
COMP_NAMES = {
    47: "Premier League", 87: "LaLiga", 55: "Serie A", 54: "Bundesliga", 53: "Ligue 1",
    57: "Eredivisie", 61: "Liga Portugal", 40: "Belgian Pro League", 71: "Super Lig", 122: "Czech 1. Liga",
    42: "Champions League", 73: "Europa League", 10216: "Conference League",
    48: "Championship", 38: "Austrian Bundesliga", 64: "Scottish Premiership", 135: "Greek Super League",
    46: "Superligaen", 69: "Swiss Super League", 59: "Eliteserien",
}
EUROPEAN = {42, 73, 10216}
CSV_COLUMNS = (
    ["match_id", "kickoff", "competition_id", "season", "home_team_id", "away_team_id", "home_score", "away_score", "referee"]
    + [f"{side}_{s}" for s in STATS for side in ("home", "away")]
)


def parse_count(value) -> Optional[int]:
    """A team stat cell as a non-negative int, or None. Strings that are not plain integers are missing."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value == int(value) and value >= 0:
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def read_referee(match_id: str) -> tuple[str, Optional[str]]:
    """(status, name). status: ok | no_referee | no_file | unreadable. Only the referee field is used."""
    path = RAW / f"{match_id}.json.gz"
    if not path.exists():
        return "no_file", None
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            body = json.load(f)
        info = (((body.get("content") or {}).get("matchFacts") or {}).get("infoBox")) or {}
        ref = info.get("Referee")
        text = ref.get("text") if isinstance(ref, dict) else None
        if isinstance(text, str) and text.strip():
            return "ok", text.strip()
        return "no_referee", None
    except Exception:
        return "unreadable", None


def _referee_task(match_id: str) -> tuple[str, str, Optional[str]]:
    status, name = read_referee(match_id)
    return match_id, status, name


def load_rows() -> tuple[list[dict], dict]:
    rows: list[dict] = []
    drops = Counter()
    seen: set[str] = set()
    for fn in SOURCES:
        with open(DATA / fn, encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                mid = str(d["match_provider_id"])
                drops["input_rows"] += 1
                if mid in seen:
                    drops["duplicate_id"] += 1
                    continue
                seen.add(mid)
                if d.get("awarded"):
                    drops["awarded"] += 1
                    continue
                ts = d.get("team_stats") or {}
                row = {
                    "match_id": mid,
                    "kickoff": d["scheduled_at"],
                    "competition_id": int(d["competition_provider_id"]),
                    "season": d.get("season") or "",
                    "home_team_id": int(d["home_team_provider_id"]),
                    "away_team_id": int(d["away_team_provider_id"]),
                    "home_score": d.get("home_score"),
                    "away_score": d.get("away_score"),
                    "referee": "",
                }
                for stat, key in STAT_KEYS.items():
                    cell = ts.get(key)
                    h = a = None
                    if isinstance(cell, (list, tuple)) and len(cell) == 2:
                        h, a = parse_count(cell[0]), parse_count(cell[1])
                    if h is None or a is None:  # a pair is usable only when both sides are present
                        h = a = None
                    row[f"home_{stat}"] = h
                    row[f"away_{stat}"] = a
                rows.append(row)
    return rows, dict(drops)


def build(workers: int) -> dict:
    rows, drops = load_rows()
    ids = [r["match_id"] for r in rows]
    status_counts = Counter()
    index = {k: i for i, k in enumerate(ids)}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for mid, status, name in ex.map(_referee_task, ids, chunksize=200):
            status_counts[status] += 1
            if name:
                rows[index[mid]]["referee"] = name
    rows.sort(key=lambda r: (r["kickoff"], r["match_id"]))
    out = DATA / "props_match_stats.csv.gz"
    with gzip.open(out, "wt", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLUMNS)
        for r in rows:
            w.writerow(["" if r.get(c) is None else r[c] for c in CSV_COLUMNS])
    return report(rows, drops, status_counts, out)


def report(rows: list[dict], drops: dict, ref_status: Counter, out: Path) -> dict:
    by_comp: dict[int, dict] = defaultdict(lambda: {"matches": 0, "referee": 0, **{s: 0 for s in STATS}})
    for r in rows:
        c = by_comp[r["competition_id"]]
        c["matches"] += 1
        if r["referee"]:
            c["referee"] += 1
        for s in STATS:
            if r[f"home_{s}"] is not None:
                c[s] += 1
    total = {"matches": len(rows), "referee": sum(1 for r in rows if r["referee"]),
             **{s: sum(1 for r in rows if r[f"home_{s}"] is not None) for s in STATS}}
    both_zero = {s: sum(1 for r in rows if r[f"home_{s}"] == 0 and r[f"away_{s}"] == 0) for s in STATS}
    rep = {
        "output": str(out.relative_to(BACKEND_DIR)).replace("\\", "/"),
        "kickoff_min": rows[0]["kickoff"], "kickoff_max": rows[-1]["kickoff"],
        "input_and_drops": drops, "matches_kept": len(rows),
        "referee_read_status": dict(ref_status),
        "coverage_total": total,
        "stat_missing_total": {s: total["matches"] - total[s] for s in STATS},
        "stat_both_sides_zero": both_zero,
        "coverage_by_competition": {
            str(cid): {"name": COMP_NAMES.get(cid, "?"), **v} for cid, v in sorted(by_comp.items())
        },
    }
    with open(DATA / "props_dataset_report.json", "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=1, ensure_ascii=False)
    return rep


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    rep = build(args.workers)
    print(json.dumps({k: rep[k] for k in ("matches_kept", "input_and_drops", "referee_read_status", "coverage_total",
                                           "stat_missing_total", "stat_both_sides_zero")}, indent=1))


if __name__ == "__main__":
    main()
