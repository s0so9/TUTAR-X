# Player impact — stints, as-of xG-RAPM ratings, XI experiment (stage A)

Built 2026-10-13 from `fotmob_match_details.jsonl` (6,798 FINISHED matches, 2025-07-01 → 2026-10-12) and the raw
FotMob `matchDetails` responses in `../raw_cache/fotmob_match_details/<match id>.json.gz`. Method, leakage guards and
results: `docs/training/player-impact-pipeline.md`. Nothing here is invented or imputed except where stated
explicitly below (the npxG/xA zero rule, documented by the source itself).

| File | Written by | Content |
|---|---|---|
| `stints.jsonl.gz` | `scripts/training/build_stints.py` | one JSON line per on-pitch segment (48,722 rows, 6,798 matches) |
| `stints_validation.csv` | same | one row per match: every check and its inputs |
| `stints_report.json` | same | pass rates, failure reasons, per-competition counts |
| `player_impact_asof.csv.gz` | `scripts/training/player_impact.py` | as-of player ratings, one row per (cutoff, player) — 509,594 rows, 60 cutoffs |
| `player_impact_meta.json` | same | hyper-parameters, time-forward validation, prior weights, replacement levels per cutoff |
| `xi_impact_experiment.json` | `scripts/training/experiment_xi_impact.py` | XI strength vs usual XI on top of rating lambdas (production split) |
| `xi_impact_experiment_extended.json` | same, `--lambdas …2025h2.csv --lambdas …xg.csv` | same with the Aug–Dec 2025 rows added to training |
| `walkforward_lambdas_xg_2025h2.csv` | `scripts/training/walkforward_dataset.py --start 2025-08-04 --end 2026-01-05` | out-of-sample rating lambdas, weekly cutoffs 2025-08-04 → 2025-12-29 (25,572 rows; same columns as `walkforward_lambdas_xg.csv`; DB read-only). Early cutoffs have little history (the DB starts 2025-07-01) |

## `stints.jsonl.gz` (one line per stint)

A stint is a stretch of play with unchanged line-ups. Boundaries: kick-off, substitutions, red cards (straight or
second yellow) that remove a player who is on the pitch. Half-time is not a boundary. Raw field paths are listed in
the docstring of `build_stints.py`.

| Field | Definition |
|---|---|
| `match_id`, `kickoff`, `competition_id`, `source_league_id`, `season` | from the details JSONL (`season` only in the history file, else null) |
| `home_team_id`, `away_team_id` | FotMob team ids (`general.homeTeam/awayTeam.id`) |
| `seg` | 0-based stint index within the match |
| `start`, `end`, `duration` | minutes of play from kick-off, stoppage time INCLUDED, half-time break excluded (clock rules below) |
| `start_nominal`, `end_nominal` | FotMob's nominal clock (a change at minute m counts as m; stoppage collapsed to 45/90/105/120), used only for the minutes check |
| `start_label`, `end_label`, `end_reason` | FotMob minute labels (`"60"`, `"90+1"`, `"FT"`, `"AET"`) and `substitution` / `red_card` / `full_time` |
| `halves` | halves the stint overlaps (`H1`, `H2`, `ET1`, `ET2`) |
| `home_players`, `away_players`, `n_home`, `n_away`, `man_adv` | FotMob player ids on the pitch; `man_adv = n_home − n_away` |
| `xg_available` | the match has a shotmap; when false every xG field is `null` (unknown, never 0) |
| `{side}_xg`, `{side}_npxg`, `{side}_shots` | sums over `content.shotmap.shots[*]` in the stint: `expectedGoals`; npxG excludes `situation == "Penalty"`; own goals and penalty-shootout kicks excluded |
| `{side}_goals`, `{side}_np_goals` | goal events in the stint (`matchFacts.events`, shoot-out excluded); own goals count for the benefiting side; `np_goals` excludes `goalDescriptionKey == "penalty"` |
| `score_start`, `home_lead_minutes`, `level_minutes`, `home_trail_minutes` | score when the stint starts and minutes by game state (home perspective) |
| `lineup_ok`, `goals_ok`, `xg_check`, `minutes_ok`, `usable`, `match_passed` | the match's validation outcome (see below), repeated on each stint |

**Clock.** Each half lasts regulation + stoppage. Stoppage comes from the half's start/end timestamps
(`header.status.halfs`) when plausible (regulation − 3 … regulation + 25 minutes), else the announced added time
(`AddedTime` event), else the latest stoppage minute seen; it is then raised to the latest stoppage minute seen in that
half (an event at 90+7 needs ≥ 7 minutes). A minute label `m` / `m+k` covers the interval [r−1, r) with
r = m − (first minute of the half) + k. Line-up changes sit at the START of their minute (so half-time substitutions,
labelled 46′, fall exactly on the break); shots and goals sit in the MIDDLE of their minute. A goal in the same minute
as a change is put before the change when the change event's score already includes it (6 goals). Non-goal shots in
the same minute as a change cannot be ordered without seconds and count after the change: 5,444 shots, 2.44 % of all
xG.

## Validation (`stints_validation.csv`, `stints_report.json`)

| Check | Definition | Result (6,798 matches) |
|---|---|---|
| `lineup_ok` | 11 starters per side; each substitution takes off an on-pitch player and brings on an off-pitch one; red cards hit on-pitch players; red cards = header counts | 99.96 % (3 matches fail: substitution of a player not on the pitch) |
| `goals_ok` | stint goals = header score | 100 % |
| `xg_check` | \|Σ stint xG − team xG (`content.stats`)\| ≤ 0.05 per side | 71.65 % of the 6,444 matches with team xG (354 Czech matches: no xG at all → `n/a`) |
| `minutes_ok` | every player's nominal stint minutes within 1 of FotMob `minutes_played` | 96.16 % (97.88 % within 3) |
| `length_ok` | 90 ≤ length ≤ 125 (120–160 with extra time) | 100 % (median 98.6 min, max 140.5) |
| **`usable`** | `lineup_ok` and `goals_ok` and all minutes within 3 | **6,654 matches (97.88 %)**, 6,315 of them with xG |

**Why the xG check fails (1,827 matches).** FotMob sends three xG figures: per shot (shotmap), per player
(`playerStats`) and per team (`stats`). They disagree in part of the matches: `fail_shot_values_differ` (player stats =
team stat ≠ shots: 1,088), `fail_team_stat_differs` (shots = player stats ≠ team stat: 552), both (103), unexplained
(80), no shotmap although team xG exists (4). In a sample of 19,499 player-matches with exactly one shot (the first
2,500 matches with xG), the shot's xG differs from the player-stat xG by > 0.01 in 5.4 % of cases (Sep 2025 – Apr 2026
≈ 6–9 %, other months ≈ 0–1 %, penalties never, in both directions) — two xG versions in the source. The stints use the per-shot values (the only source with timing), so Σ stint xG equals the
shotmap total exactly; matches are not excluded for this.

**Why the minutes check fails (261 matches).** FotMob's `minutes_played` is sometimes 2–4 minutes off the
substitution-event minute, counts stoppage for late substitutes, or names a different player than the substitution
event (e.g. 4695474: event says Seone off at 77′, playerStats give Seone 90 and Innvær 77). 144 matches with a
player > 3 minutes off are marked not `usable`.

## `player_impact_asof.csv.gz` (one row per cutoff × player)

Cutoffs: weekly Mondays 2025-09-01 → 2026-10-12, plus 2026-10-13 (day after the last match). A cutoff's ratings were
fitted only on stints/details of matches that kicked off before the cutoff date, so they can be used for any match on
or after that date. 5,634 players at the first cutoff, 10,628 at the last.

| Column | Definition |
|---|---|
| `cutoff`, `player_id`, `team_id`, `position` | latest team and usual position (GK/DEF/MID/FWD; empty = unknown) before the cutoff |
| `minutes`, `minutes_decayed`, `xg_minutes`, `rapm_minutes`, `n_apps` | raw minutes (all collected competitions), time-decayed minutes, minutes in matches with shot data, minutes in usable xG stints in the fit, appearances |
| `offence`, `defence` | xG-RAPM rating, xG per 90 the player adds to his side / takes away from the opponent, relative to an average player (+ is better for both) |
| `prior_offence`, `prior_defence` | the box-score prior part (z · g); `offence − prior_offence` is the RAPM deviation |
| `npxg90`, `xa90`, `xgxa90` | npxG/90, xA/90 and their sum, decayed (half-life 365 d) and shrunk with 450 minutes of the position average |
| `rating` | minutes-weighted FotMob rating, decayed, shrunk the same way |
| `minutes_share` | share of the 90-minute slots of the current team's last 10 matches (> 1 possible with extra time) |
| `market_value` | latest FotMob line-up market value (EUR) before the cutoff; empty = unknown |
| `flags` | `prior_only` (no usable xG stint: rating = prior), `no_xg_data` (only matches without shot data, e.g. Czech 1. Liga), `market_value_missing`, `position_unknown` |

At the last cutoff: 473 `prior_only`, 453 `no_xg_data`, 1,043 `market_value_missing`, 7 `position_unknown` (of 10,628).

**npxG / xA zero rule (an imputation, decided here).** FotMob omits `npxg`/`xa` for a player without a shot / chance
created. In a match WITH team xG, a player who appeared with stats gets 0 for an omitted value; in a match without shot
data both stay unknown and the minutes do not count in the per-90 denominators.

## `player_impact_meta.json`

`hyper_parameters` (λ_player 16,000, half-life 365 d, team intercepts off, grid, chosen config), `validation` (time-forward
weighted squared error of every configuration, per cutoff), `per_cutoff` (stints, players, CG iterations/residual,
fixed effects, prior weights for offence and defence, feature means/sds, replacement level per position, sds of the
ratings), `leakage_guards`.

## Known gaps

1. Only 2025-07 → 2026-10 (≈ 1.25 seasons). The RAPM deviations from the prior are therefore small (sd ≈ 0.01 xG/90
   vs ≈ 0.115 for the prior); the multi-season history file should allow a smaller λ.
2. Czech 1. Liga (122) has no xG: its stints carry goals but no xG; those players are rated from the prior (rating,
   market value, minutes share) unless they played European matches with xG.
3. Absolute values compare well within a league; across leagues only partly (market value and European matches tie
   leagues together). A high npxG/90 in a weaker league gives a high offence value.
4. Only competitions in the details file are seen: domestic cups and friendlies are missing from minutes shares and
   usual XIs.
