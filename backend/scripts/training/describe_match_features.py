"""Column dictionary + missing rate per split of match_features_full.csv.gz (README generator).

Reads the feature CSV (build_match_features.py with --split-bounds) and writes
data/training/README_match_features_full.md: run summary, rows per split and competition, and one
table row per column with its definition and the share of empty (missing) values in each split.
The definitions below are the ones of build_match_features.py / README_match_features.md.
No network requests.

Usage (from backend/):
  venv/Scripts/python.exe scripts/training/describe_match_features.py
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

TRAINING_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TRAINING_DIR))
import build_match_features as F  # noqa: E402

DATA = TRAINING_DIR.parents[1] / "data" / "training"
SPLITS = ("pre_train", "train", "validation", "test", "post_test")

GLOBAL_DEFS = {
    "match_id": "FotMob match id",
    "kickoff": "kick-off, naive UTC (details `scheduled_at`)",
    "split": "fixed split from the kick-off: train 2022-08-01..2025-06-30, validation 2025-07-01..2026-01-31, "
             "test 2026-02-01..2026-10-12; pre_train before 2022-08-01 (no lambda / ratings yet)",
    "season": "FotMob season name (history details file only; empty for the 2025-07+ file)",
    "competition_provider_id": "FotMob league id (parent league; stages share it)",
    "competition_name": "competition name in all_results.db (production rows: often a stage name)",
    "source_league_id": "FotMob league id of the stage / group",
    "comp_type": "`european` (42/73/10216 and their qualifications), `cup` (name has a cup marker), else `league`",
    "comp_is_euro": "1 when comp_type is european, else 0",
    "home_team_id": "FotMob team id, home side",
    "away_team_id": "FotMob team id, away side",
    "details_source": "details file the row comes from",
    "y_home_goals": "LABEL (never a feature): final home score",
    "y_away_goals": "LABEL: final away score",
    "y_home_xg": "LABEL: FotMob team xG of the home side in this match (empty = no xG, e.g. Czech 1. Liga history)",
    "y_away_xg": "LABEL: FotMob team xG of the away side",
    "lambda_cutoff": "cutoff of the walk-forward rating fit that produced the lambdas (fit on results before it)",
    "lambda_source": "lambdas file (walkforward_lambdas_full_2022_2026.csv)",
    "lambda_home_raw": "walk-forward rating lambda, home (production GlobalPoissonRatings, 50 % goals + 50 % xG target)",
    "lambda_away_raw": "walk-forward rating lambda, away",
    "lambda_home": "lambda_home_raw through the TRAIN-ONLY goal layer (goal_layer_train_only.json)",
    "lambda_away": "lambda_away_raw through the train-only goal layer",
    "home_starters_value": "home starters' market value total, EUR (line-up totalStarterMarketValue); empty = not sent",
    "away_starters_value": "away starters' market value total, EUR",
    "value_log_ratio": "ln(home_starters_value / away_starters_value), production squad-value signal; empty if either missing",
    "lineup_form": "production lineup form: starters' prior minutes-weighted FotMob rating (>= 180 prior min, >= 7 "
                   "starters) minus the team's mean over its previous <= 10 line-ups (>= 3), home minus away",
    "ratings_cutoff": "latest player_impact_asof_all cutoff strictly before kick-off",
    "ratings_age_days": "days between that cutoff and the kick-off",
    "league_hadv": "ln(home goals / away goals) of the competition over the 365 days before kick-off, shrunk to the "
                   "global value with 100 pseudo-matches",
    "global_hadv": "the same over all competitive results in the window",
    "league_hadv_dev": "league_hadv - global_hadv",
    "league_hadv_n": "results of the competition used for league_hadv",
}
SIDE_DEFS = {
    "xi_n": "number of starters in the line-up",
    "xi_off": "sum of the 11 starters' RAPM offence (xG/90 vs an average player; unrated -> position replacement level); "
              "empty unless exactly 11 starters and a ratings cutoff exists",
    "xi_def": "sum of the 11 starters' RAPM defence (+ = better)",
    "xi_unrated": "starters without a rating at the cutoff (replacement level used)",
    "usual_n": "earlier line-ups of the team used for the usual XI (<= 10)",
    "usual_off": "mean offence of the team's previous <= 10 line-ups at the SAME cutoff, scaled to 11; empty with < 3",
    "usual_def": "mean defence of the previous line-ups, same rule",
    "xi_d_off": "xi_off - usual_off (XI vs usual XI)",
    "xi_d_def": "xi_def - usual_def",
    "unavail_listed": "1 = FotMob sent the unavailable key for this side, 0 = key absent, empty = raw file unreadable",
    "n_injury": "listed unavailable players of type injury; empty when the key is absent (unknown), 0 = empty list",
    "n_suspension": "listed players of type suspension (same rule)",
    "n_other": "listed players of any other type (internationalDuty, ...)",
    "unavail_n_rated": "listed players with a rating at the cutoff",
    "unavail_off": "sum over rated listed players of (offence - replacement level of his position); expected_return never read",
    "unavail_def": "same for defence",
    "unavail_off_w": "unavail_off weighted by each player's minutes share of his team's last 10 matches (capped at 1)",
    "unavail_def_w": "unavail_def weighted the same way",
    "unavail_value": "sum of listed players' market values; empty if any is missing",
    "l5_n": "earlier details matches of the team considered for xG form (<= 5)",
    "l5_xg_n": "of those, matches with team xG",
    "xg_for_l5": "mean team xG for over the last 5 details matches with xG; empty with < 3",
    "xg_against_l5": "mean team xG against, same rule",
    "res_l5_n": "competitive results considered (<= 5, friendlies excluded, awarded + cancelled-conflict results excluded)",
    "ppg_l5": "mean points over the last 5 competitive results; empty with < 3",
    "gf_l5": "mean goals for over the last 5 competitive results",
    "ga_l5": "mean goals against over the last 5 competitive results",
    "rest_days": "days since the team's previous competitive result; empty when the team has none in the results table",
    "n_matches_14d": "competitive matches in the 14 x 24 h before kick-off",
    "euro_before_3d": "1 = European match within 3 calendar days before",
    "euro_after_3d": "1 = European fixture within 3 calendar days after (schedule only, never its result)",
}


def definition(col: str) -> str:
    if col in GLOBAL_DEFS:
        return GLOBAL_DEFS[col]
    for side in ("home", "away"):
        if col.startswith(side + "_") and col[len(side) + 1:] in SIDE_DEFS:
            return f"{side} side: " + SIDE_DEFS[col[len(side) + 1:]]
    return "(see build_match_features.py)"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", type=Path, default=DATA / "match_features_full.csv.gz")
    ap.add_argument("--report", type=Path, default=DATA / "match_features_full_report.json")
    ap.add_argument("--out", type=Path, default=DATA / "README_match_features_full.md")
    ap.add_argument("--json-out", type=Path, default=DATA / "match_features_full_missing.json")
    args = ap.parse_args(argv)

    n = Counter()
    miss = defaultdict(Counter)
    comp_split = defaultdict(Counter)
    euro_split = Counter()
    with gzip.open(args.features, "rt", encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f)
        cols = rd.fieldnames
        for r in rd:
            s = r.get("split") or "none"
            n[s] += 1
            comp_split[r["competition_provider_id"]][s] += 1
            if r["comp_is_euro"] == "1":
                euro_split[s] += 1
            for c in cols:
                if r[c] == "":
                    miss[s][c] += 1
    splits = [s for s in SPLITS if n[s]] + [s for s in n if s not in SPLITS]
    rates = {s: {c: round(miss[s][c] / n[s], 4) for c in cols} for s in splits}
    args.json_out.write_text(json.dumps({"rows": dict(n), "missing_rate": rates}, indent=1), encoding="utf-8")
    rep = json.loads(args.report.read_text(encoding="utf-8")) if args.report.exists() else {}

    L = []
    L.append("# `match_features_full.csv.gz` — full multi-season feature file (2026-10-14)\n")
    L.append("Built by `scripts/training/build_match_features.py` (command and method: "
             "`docs/training/player-impact-pipeline.md`, section \"Full run - base\"). One row per match of both "
             "details files (`fotmob_match_details.jsonl` + `fotmob_match_details_history.jsonl`: TARGET13 "
             "2022/23 -> 2026-10-12 plus the tail leagues), awarded matches dropped, the "
             "`production_vs_fixture_status` conflict ids dropped (cancelled / abandoned matches are not in the "
             "details files). Pre-kick-off information only; missing values are empty, never 0 or imputed "
             "(0 is a real count). `unavailable[*].expected_return` is never read. This file is generated by "
             "`scripts/training/describe_match_features.py`.\n")
    if rep:
        inp = rep.get("inputs", {})
        L.append(f"- Rows: {rep.get('rows')} ({rep.get('rows_with_lambda')} with a rating lambda); "
                 f"details stats: `{json.dumps(rep.get('details_stats'))}`")
        L.append(f"- Lambdas: {', '.join(Path(p).name for p in inp.get('lambdas', []))}; ratings: "
                 f"{Path(inp.get('ratings', '')).name} (+ {Path(inp.get('meta', '')).name}); goal layer: "
                 f"{Path(inp.get('goal_layer', {}).get('path', '')).name} "
                 f"(a {inp.get('goal_layer', {}).get('a', float('nan')):.4f}, "
                 f"b {inp.get('goal_layer', {}).get('b', float('nan')):.4f}, "
                 f"m {inp.get('goal_layer', {}).get('m', float('nan')):.4f})")
        L.append(f"- Results for form / rest / home advantage: {inp.get('results')}")
        L.append(f"- Rows with a lambda per split: `{json.dumps(rep.get('rows_with_lambda_per_split'))}`\n")
    L.append("## Rows per split\n")
    L.append("| Split | Kick-off range | Rows | European rows |")
    L.append("|---|---|---|---|")
    ranges = {"pre_train": "< 2022-08-01", "train": "2022-08-01 .. 2025-06-30", "validation": "2025-07-01 .. 2026-01-31",
              "test": "2026-02-01 .. 2026-10-12", "post_test": ">= 2026-10-13"}
    for s in splits:
        L.append(f"| {s} | {ranges.get(s, '')} | {n[s]} | {euro_split[s]} |")
    L.append("\n## Rows per competition and split\n")
    L.append("| FotMob id | " + " | ".join(splits) + " |")
    L.append("|---|" + "---|" * len(splits))
    for c, cnt in sorted(comp_split.items(), key=lambda kv: -sum(kv[1].values())):
        L.append(f"| {c} | " + " | ".join(str(cnt[s]) for s in splits) + " |")
    L.append("\n## Columns: definition and missing rate per split (% of rows with an empty value)\n")
    L.append("| Column | Definition | " + " | ".join(f"missing {s}" for s in splits) + " |")
    L.append("|---|---|" + "---|" * len(splits))
    for c in cols:
        L.append(f"| `{c}` | {definition(c)} | " + " | ".join(f"{100 * rates[s][c]:.1f}" for s in splits) + " |")
    L.append("\nMissing rates are also in `match_features_full_missing.json`. Why values are missing: no rating "
             "lambda (team history too short at the cutoff), no ratings cutoff before the kick-off (before "
             "2022-09-05), fewer than 3 earlier line-ups / results, FotMob not sending market values (thin in "
             "2022/23 and 2023/24), the unavailable key absent, or no xG (Czech 1. Liga history).")
    args.out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"-> {args.out} ({len(cols)} columns, rows {dict(n)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
