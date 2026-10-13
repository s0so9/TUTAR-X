"""Freeze pre-match predictions for tonight's UCL matches.

Fetches /api/v1/matches/{id}/prediction for each match in cl_tonight.json,
stores the raw response plus the fetch timestamp, and refuses to snapshot a
match whose kickoff has already passed (so the test stays a true pre-match test).
"""
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
API = "http://127.0.0.1:8003/api/v1/matches/{}/prediction"
import os
OUT = HERE / os.environ.get("SNAP_DIR", "snapshots")
OUT.mkdir(exist_ok=True)

matches = json.loads((HERE / "cl_tonight.json").read_text(encoding="utf-8"))
only = set(sys.argv[1:])

for m in matches:
    if only and m["id"] not in only:
        continue
    now = datetime.now(timezone.utc)
    kickoff = datetime.fromisoformat(m["scheduled_at"].replace("Z", "+00:00"))
    label = f'{m["home_team"]["name"]} vs {m["away_team"]["name"]}'
    if now >= kickoff:
        print(f"SKIP (kickoff passed) {label}")
        continue
    try:
        with urllib.request.urlopen(API.format(m["id"]), timeout=180) as r:
            status, body = r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        status, body = e.code, json.loads(e.read().decode("utf-8") or "{}")
    record = {
        "match": m,
        "fetched_at_utc": now.isoformat(),
        "minutes_before_kickoff": round((kickoff - now).total_seconds() / 60, 1),
        "http_status": status,
        "response": body,
    }
    (OUT / f'{m["id"]}.json').write_text(
        json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"{status}  {label}")
