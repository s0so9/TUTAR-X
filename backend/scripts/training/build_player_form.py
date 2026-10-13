"""Build the player-form table used by the lineup-strength adjustment.

From data/training/fotmob_match_details.jsonl: each player's minutes-weighted
FotMob rating over all collected matches, and each team's usual XI quality (mean
of its last line-ups' XI quality, same definition as
experiment_lineup_strength.py). gamma comes from that experiment's output.

Writes config/player_form.json. The adjustment is only active when this file
exists and carries a gamma.

Usage (from backend/): venv/Scripts/python.exe scripts/training/build_player_form.py
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

MIN_PRIOR_MINUTES = 180
MIN_KNOWN_STARTERS = 7
USUAL_WINDOW = 10


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--details", default="data/training/fotmob_match_details.jsonl")
    ap.add_argument("--experiment", default="data/training/lineup_experiment.json")
    ap.add_argument("--variant", default="value+form")
    ap.add_argument("--out", default="config/player_form.json")
    args = ap.parse_args()

    records = [json.loads(line) for line in open(args.details, encoding="utf-8")]
    records.sort(key=lambda r: r["scheduled_at"])
    player_sum = defaultdict(float)
    player_min = defaultdict(float)
    team_q = defaultdict(lambda: deque(maxlen=USUAL_WINDOW))
    for r in records:
        for side, team in (("home", r["home_team_provider_id"]), ("away", r["away_team_provider_id"])):
            starters = [p for p in r.get("players") or [] if p.get("is_starter") and p.get("team_side") == side]
            vals = [player_sum[p["player_id"]] / player_min[p["player_id"]]
                    for p in starters if player_min[p["player_id"]] >= MIN_PRIOR_MINUTES]
            if len(vals) >= MIN_KNOWN_STARTERS:
                team_q[str(team)].append(float(np.mean(vals)))
        for p in r.get("players") or []:
            if p.get("rating") is not None and p.get("minutes_played"):
                player_sum[p["player_id"]] += float(p["rating"]) * float(p["minutes_played"])
                player_min[p["player_id"]] += float(p["minutes_played"])

    experiment = json.loads(Path(args.experiment).read_text(encoding="utf-8"))
    variant = experiment["results"][args.variant]
    out = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "source": args.details,
        "n_matches": len(records),
        "gamma_form": variant["gamma_form"],
        "evidence": {"experiment": args.experiment, "variant": args.variant,
                     "n_train": experiment["n_train"], "n_test": experiment["n_test"],
                     "held_out": experiment["results"]},
        "min_prior_minutes": MIN_PRIOR_MINUTES,
        "min_known_starters": MIN_KNOWN_STARTERS,
        "players": {str(pid): round(player_sum[pid] / player_min[pid], 4)
                    for pid in player_min if player_min[pid] >= MIN_PRIOR_MINUTES},
        "teams_usual_xi": {team: round(float(np.mean(q)), 4) for team, q in team_q.items() if len(q) >= 3},
    }
    Path(args.out).write_text(json.dumps(out), encoding="utf-8")
    print(f"players={len(out['players'])} teams={len(out['teams_usual_xi'])} gamma={out['gamma_form']} -> {args.out}")


if __name__ == "__main__":
    main()
