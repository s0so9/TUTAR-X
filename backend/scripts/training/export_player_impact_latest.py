"""Runtime export of the latest player-impact cutoff (player_impact_latest.json).

Reads the as-of ratings file written by player_impact.py (rows grouped by cutoff, ascending) and its
meta file, takes the LAST cutoff (or --cutoff), and writes one JSON document:

  cutoff, hyper_parameters, units, replacement_level (per position, from the meta file),
  players: {player_id: {offence, defence, prior_offence, prior_defence, minutes, rapm_minutes,
                        prior_only, position, team_id, flags}}

  offence / defence  xG per 90 added (offence) / removed from the opponent (defence) relative to an
                     average player, + = better; exactly the values of the ratings file
  minutes            the player's minutes in the details files before the cutoff (all competitions)
  rapm_minutes       stint minutes inside the fit window (the basis of the player's own deviation)
  prior_only         true when rapm_minutes == 0: the rating is the box-score prior only

The cutoff's ratings were fitted on matches that kicked off strictly before the cutoff date, so
they are safe for any match on or after it. Read by
app.prediction.player_impact.PlayerImpactRatings.load_latest_json. No network requests.

Usage (from backend/):
  venv/Scripts/python.exe scripts/training/export_player_impact_latest.py
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DATA = Path(__file__).resolve().parents[2] / "data" / "training"
FORMAT = "player_impact_latest/v1"


def _f(v: str) -> Optional[float]:
    return None if v in (None, "") else float(v)


def export(ratings: Path, meta: Path, out: Path, cutoff: Optional[str] = None) -> dict:
    meta_doc = json.loads(Path(meta).read_text(encoding="utf-8"))
    per = {e["cutoff"]: e for e in meta_doc.get("per_cutoff") or []}
    target = cutoff or (max(per) if per else None)
    rows = []
    last = None
    with gzip.open(ratings, "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            c = r["cutoff"]
            if target is None:            # no meta: keep the last block of the file
                if last is None or c > last:
                    last, rows = c, []
                if c == last:
                    rows.append(r)
            elif c == target:
                rows.append(r)
    target = target or last
    if not rows:
        raise SystemExit(f"no rows for cutoff {target} in {ratings}")
    players = {}
    for r in rows:
        flags = [x for x in (r.get("flags") or "").split(";") if x]
        players[r["player_id"]] = {
            "offence": float(r["offence"]), "defence": float(r["defence"]),
            "prior_offence": float(r["prior_offence"]), "prior_defence": float(r["prior_defence"]),
            "minutes": _f(r["minutes"]), "rapm_minutes": _f(r["rapm_minutes"]),
            "prior_only": "prior_only" in flags,
            "position": r["position"] or None, "team_id": r["team_id"] or None, "flags": flags,
        }
    entry = per.get(target) or {}
    hp = meta_doc.get("hyper_parameters") or {}
    doc = {
        "format": FORMAT,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cutoff": target,
        "fitted_on": f"usable stints of matches with kickoff before {target} "
                     f"(look-back {hp.get('lookback_days')} days, half-life {hp.get('half_life_days')} days)",
        "source_ratings": Path(ratings).name, "source_meta": Path(meta).name,
        "units": meta_doc.get("units"),
        "hyper_parameters": {k: hp.get(k) for k in ("lambda_player", "half_life_days", "lambda_team",
                                                    "lookback_days", "prior_features", "chosen_by_validation")},
        "replacement_level": entry.get("replacement_level"),
        "replacement_note": "players without a rating get the replacement level of their position "
                            "(mean prior of fringe players, < 450 minutes before the cutoff); flag them, never "
                            "treat them as average",
        "n_players": len(players),
        "n_prior_only": sum(p["prior_only"] for p in players.values()),
        "players": players,
    }
    out = Path(out)
    tmp = out.with_name(out.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, out)
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="export the latest player-impact cutoff as JSON")
    ap.add_argument("--ratings", type=Path, default=DATA / "player_impact_asof_all.csv.gz")
    ap.add_argument("--meta", type=Path, default=DATA / "player_impact_all_meta.json")
    ap.add_argument("--out", type=Path, default=DATA / "player_impact_latest.json")
    ap.add_argument("--cutoff", default=None, help="default: the last cutoff of the meta file")
    args = ap.parse_args(argv)
    doc = export(args.ratings, args.meta, args.out, args.cutoff)
    print(f"cutoff {doc['cutoff']}: {doc['n_players']} players ({doc['n_prior_only']} prior only) -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
