"""Research (2026-10-15, error analysis): extract round / stadium / referee / attendance per match from the
untouched FotMob raw match-details cache (backend/data/raw_cache/fotmob_match_details/<id>.json.gz).

Read-only on the cache; writes backend/data/research/err_match_info.csv. Nothing is imputed: a value the raw
response does not contain stays empty.

Run (from backend/):  OMP_NUM_THREADS=2 venv/Scripts/python.exe -I scripts/research/err_extract_raw.py
"""
from __future__ import annotations

import csv
import gzip
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
RAW = BACKEND / "data" / "raw_cache" / "fotmob_match_details"
OUT = BACKEND / "data" / "research" / "err_match_info.csv"


def main() -> int:
    files = sorted(RAW.glob("*.json.gz"))
    cols = ["match_id", "round", "round_name", "stadium", "city", "country", "lat", "lon", "capacity",
            "attendance", "referee", "home_team_id", "away_team_id"]
    n_ok = n_bad = 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for p in files:
            try:
                d = json.load(gzip.open(p, "rt", encoding="utf-8"))
            except Exception:
                n_bad += 1
                continue
            g = d.get("general") or {}
            ib = ((d.get("content") or {}).get("matchFacts") or {}).get("infoBox") or {}
            tour = ib.get("Tournament") or {}
            st = ib.get("Stadium") or {}
            ref = ib.get("Referee") or {}
            rnd = tour.get("round")
            if rnd in (None, ""):
                rnd = g.get("matchRound")
            w.writerow([p.name.split(".")[0], rnd if rnd is not None else "", tour.get("roundName") or "",
                        st.get("name") or "", st.get("city") or "", st.get("country") or "",
                        st.get("lat") if st.get("lat") is not None else "",
                        st.get("long") if st.get("long") is not None else "",
                        st.get("capacity") if st.get("capacity") is not None else "",
                        ib.get("Attendance") if ib.get("Attendance") is not None else "",
                        (ref.get("text") or "") if isinstance(ref, dict) else "",
                        ((g.get("homeTeam") or {}).get("id") or ""), ((g.get("awayTeam") or {}).get("id") or "")])
            n_ok += 1
    print(json.dumps({"files": len(files), "parsed": n_ok, "unreadable": n_bad, "out": str(OUT)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
