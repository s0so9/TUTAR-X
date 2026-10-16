"""Research (2026-10-15, "additional data" study): extract pre-match context per match from the untouched
FotMob raw match-details cache (backend/data/raw_cache/fotmob_match_details/<id>.json.gz):
stadium (name, city, lat, lon, capacity, surface), referee, attendance and both head coaches.

Read-only on the cache; writes backend/data/research/xdata_match_context.csv. Nothing is imputed: a value the
raw response does not contain stays empty.

Run (from backend/):  OMP_NUM_THREADS=2 venv/Scripts/python.exe -I scripts/research/xdata_extract_context.py
"""
from __future__ import annotations

import csv
import gzip
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
RAW = BACKEND / "data" / "raw_cache" / "fotmob_match_details"
OUT = BACKEND / "data" / "research" / "xdata_match_context.csv"

COLS = ["match_id", "kickoff", "home_team_id", "away_team_id", "stadium", "city", "lat", "lon", "capacity",
        "surface", "attendance", "referee", "referee_country", "home_coach_id", "home_coach", "away_coach_id",
        "away_coach"]


def g(d, *path):
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


def s(v) -> str:
    return "" if v is None else str(v)


def main() -> int:
    files = sorted(RAW.glob("*.json.gz"))
    n_ok = n_bad = 0
    tmp = OUT.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        for fp in files:
            try:
                with gzip.open(fp, "rt", encoding="utf-8") as fh:
                    d = json.load(fh)
            except Exception:  # noqa: BLE001 - a broken cache file is counted, never guessed
                n_bad += 1
                continue
            gen = d.get("general") or {}
            ib = g(d, "content", "matchFacts", "infoBox") or {}
            st = ib.get("Stadium") or {}
            ref = ib.get("Referee") or {}
            lu = g(d, "content", "lineup") or {}
            hc = g(lu, "homeTeam", "coach") or {}
            ac = g(lu, "awayTeam", "coach") or {}
            w.writerow([s(gen.get("matchId")), s(gen.get("matchTimeUTCDate")), s(g(gen, "homeTeam", "id")),
                        s(g(gen, "awayTeam", "id")), s(st.get("name")), s(st.get("city")), s(st.get("lat")),
                        s(st.get("long")), s(st.get("capacity")), s(st.get("surface")), s(ib.get("Attendance")),
                        s(ref.get("text")), s(ref.get("country")), s(hc.get("id")), s(hc.get("name")),
                        s(ac.get("id")), s(ac.get("name"))])
            n_ok += 1
    tmp.replace(OUT)
    print(json.dumps({"files": len(files), "written": n_ok, "unreadable": n_bad, "out": str(OUT)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
