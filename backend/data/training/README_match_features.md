# Match features, history lambdas and the match model (player-impact pipeline, stage B)

Built 2026-10-13. Method, results and the multi-season re-run commands:
`docs/training/player-impact-pipeline.md` (stage B section). Everything here is derived from files that already
existed (no FotMob requests were made); the production DB was opened read-only. Nothing is invented or imputed:
a value the inputs do not provide is empty (null) in the CSVs; 0 appears only when it is a real count / value.

| File | Written by | Content |
|---|---|---|
| `match_features.csv.gz` | `scripts/training/build_match_features.py` | one row per match of `fotmob_match_details.jsonl` (6,798 rows, 6,660 with a rating lambda), pre-kick-off features + labels |
| `match_features_report.json` | same | inputs, goal-layer parameters used, per-column non-null share, per-competition coverage |
| `walkforward_lambdas_results_2022_2025.csv` (+ `.meta.json`) | `scripts/training/walkforward_from_results.py --start 2022-08-01 --end 2025-06-30` | out-of-sample rating lambdas from `data/history/all_results.db`, 152 weekly cutoffs 2022-08-01..2025-06-23, 55,729 rows |
| `walkforward_lambdas_results_2025_07.csv` (+ `.meta.json`) | same, `--start 2025-06-30 --end 2025-08-04` | the 5 cutoffs between the history file and `walkforward_lambdas_xg_2025h2.csv` (first DB cutoff 2025-08-04), 1,822 rows |
| `walkforward_from_results_check.json` | same, `--compare` | reproduction check of the results-table port against `walkforward_lambdas_xg.csv` and against a fresh fit on the current DB |
| `match_model_report.json` | `scripts/training/train_match_model.py` | splits, validation selection traces, ablations (validation), test metrics with bootstrap CIs, calibration tables, market comparison |
| `match_model_candidate.json` | same | DRAFT config of the selected model (coefficients, exact feature definitions, standardisation); not production |

## `match_features.csv.gz`

One row per match of the details files given with `--details` (default: `fotmob_match_details.jsonl`; first occurrence of
a match id wins; `awarded` matches dropped; a partial last line of a file that is still being written is skipped and
counted). Columns prefixed `home_` / `away_` exist once per side. `kickoff` is naive UTC.

**No-look-ahead rule:** every history-based value uses matches with kick-off strictly before this kick-off; the match's
own id and a duplicate fixture of the same pair within 1 day are excluded. From the match itself only pre-match line-up
information is read: the starters and their usual positions, the starters' market-value total and the `unavailable`
list. `euro_after_3d` uses the fixture schedule (a later fixture's date, never its result).
`tests/test_match_features_training.py` checks that adding post-kick-off matches, results or rating cutoffs, or
changing the match's own score / xG / player match stats, leaves every feature unchanged.

| Column(s) | Definition / source |
|---|---|
| `match_id`, `kickoff`, `season`, `competition_provider_id`, `source_league_id`, `home_team_id`, `away_team_id` | details JSONL (FotMob ids; `season` only in the history details file) |
| `competition_name` | name of the match in `all_results.db` (production-DB name, often a stage name) |
| `comp_type`, `comp_is_euro` | `european` for 42 / 73 / 10216 (and their qualifications 10611 / 10613 / 10615), `cup` when the name contains a cup marker (Cup, Pokal, Coupe, Copa, Coppa, Beker, Taça, Kupa, Trophy, Shield, Super Cup …), else `league`. The current rows are `league` or `european` only (the details files hold no cup matches) |
| `details_source` | details file name |
| `y_home_goals`, `y_away_goals`, `y_home_xg`, `y_away_xg` | **labels, never features**: final score (`header.teams[*].score`) and FotMob team xG of the match |
| `lambda_cutoff`, `lambda_source`, `lambda_home_raw`, `lambda_away_raw` | walk-forward rating lambdas (first lambdas file containing the match: default `walkforward_lambdas_xg_2025h2.csv`, `walkforward_lambdas_xg.csv`, `walkforward_lambdas_results_2025_07.csv`) |
| `lambda_home`, `lambda_away` | the raw lambdas through the production goal layer (`app/prediction/goal_model.py`, `config/goal_model.json` read only; parameters in the report). The layer was fitted on lambda rows up to 2026-10-11, see the caveat below |
| `home_starters_value`, `away_starters_value` | `{side}_starters_market_value` (line-up `totalStarterMarketValue`, EUR); empty when FotMob sends none |
| `value_log_ratio` | ln(home / away starters' value), the production squad-value signal; empty when either is missing |
| `lineup_form` | production lineup form (definition of `experiment_lineup_strength.py`, via `experiment_xi_impact.production_features`): mean prior minutes-weighted FotMob rating of the starters (players with ≥ 180 prior minutes, ≥ 7 such starters) minus the team's mean over its previous ≤ 10 line-ups (≥ 3), home minus away |
| `ratings_cutoff`, `ratings_age_days` | latest cutoff of `player_impact_asof.csv.gz` strictly before kick-off (its ratings were fitted on matches before the cutoff date) and its age |
| `{side}_xi_n` | number of starters in the line-up |
| `{side}_xi_off`, `{side}_xi_def` | sum of the 11 starters' stage-A RAPM offence / defence (xG/90 relative to an average player; + = better). A starter without a rating gets the replacement level of his usual position (`player_impact_meta.json`); `{side}_xi_unrated` counts them. Empty unless exactly 11 starters |
| `{side}_usual_n`, `{side}_usual_off`, `{side}_usual_def` | the team's previous ≤ 10 line-ups in the details files, valued at the SAME cutoff, scaled to 11 players, averaged; empty with fewer than 3 line-ups |
| `{side}_xi_d_off`, `{side}_xi_d_def` | XI minus usual XI (identical to stage A's `xi_features`: 6,017 matches compared, max difference 5e-7) |
| `{side}_unavail_listed` | 1 = FotMob sent `content.lineup.{side}Team.unavailable` (raw response), 0 = the key is absent, empty = raw file unreadable and the parsed list empty |
| `{side}_n_injury`, `{side}_n_suspension`, `{side}_n_other` | listed players by `unavailability.type` (`other` = `internationalDuty` and anything else); empty when the key is absent (unknown), 0 when FotMob sent an empty list |
| `{side}_unavail_n_rated` | listed players with a rating at the cutoff |
| `{side}_unavail_off`, `{side}_unavail_def` | Σ over rated listed players of (rating − replacement level of his position); unrated listed players add 0 by definition |
| `{side}_unavail_off_w`, `{side}_unavail_def_w` | the same weighted by the player's minutes share of his team's last 10 matches (capped at 1): long-term absentees who were not playing anyway count little |
| `{side}_unavail_value` | Σ market value of listed players; empty if any listed player has no value |
| `{side}_l5_n`, `{side}_l5_xg_n`, `{side}_xg_for_l5`, `{side}_xg_against_l5` | the team's last 5 matches in the details files (any of the collected competitions); mean team xG for / against over those with xG, empty when fewer than 3 have xG (Czech 1. Liga has no xG) |
| `{side}_res_l5_n`, `{side}_ppg_l5`, `{side}_gf_l5`, `{side}_ga_l5` | last 5 competitive results in `all_results.db` (all competitions, friendlies excluded): mean points (3/1/0 from the recorded score; awarded results count as recorded), goals for / against; empty with fewer than 3 |
| `{side}_rest_days` | days since the previous competitive result (friendlies excluded); empty when the team has none in the results table |
| `{side}_n_matches_14d` | competitive matches in the 14 × 24 h before kick-off |
| `{side}_euro_before_3d`, `{side}_euro_after_3d` | a European match (42/73/10216 or qualification) within 3 calendar days before / after (after = schedule, see above) |
| `league_hadv`, `global_hadv`, `league_hadv_dev`, `league_hadv_n` | ln(Σ home goals / Σ away goals) of the same competition over the 365 days before kick-off, shrunk towards the global value with 100 pseudo-matches; the global value over all competitive results in the same window; their difference; matches used |

### Coverage (rows of the current file; % of matches unless stated)

| FotMob id | Competition | Matches | Kick-offs | Lambda | Starter value | Lineup form | XI vs usual (both sides) | Unavailable key sent (% of sides) | xG last 5 (home) | Points last 5 | Rest days |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 47 | Premier League | 440 | 2025-08-15..2026-10-12 | 99.3 | 100.0 | 85.7 | 93.2 | 96.9 | 93.2 | 100.0 | 100.0 |
| 87 | LaLiga | 458 | 2025-08-15..2026-10-12 | 98.7 | 99.3 | 80.8 | 91.5 | 93.3 | 92.6 | 100.0 | 100.0 |
| 55 | Serie A | 440 | 2025-08-23..2026-10-12 | 98.0 | 100.0 | 81.8 | 91.4 | 96.4 | 92.3 | 100.0 | 100.0 |
| 54 | Bundesliga | 351 | 2025-08-22..2026-10-11 | 99.4 | 100.0 | 80.1 | 89.7 | 98.7 | 91.2 | 100.0 | 100.0 |
| 53 | Ligue 1 | 359 | 2025-08-15..2026-10-11 | 98.6 | 99.2 | 79.9 | 90.8 | 93.6 | 91.6 | 100.0 | 100.0 |
| 57 | Eredivisie | 381 | 2025-08-08..2026-10-11 | 95.0 | 99.2 | 81.1 | 88.7 | 90.4 | 91.6 | 100.0 | 100.0 |
| 61 | Liga Portugal | 377 | 2025-08-08..2026-10-12 | 92.8 | 58.6 | 80.1 | 89.7 | 87.9 | 92.0 | 100.0 | 100.0 |
| 40 | Belgian Pro League | 385 | 2025-07-25..2026-10-11 | 98.7 | 98.4 | 82.1 | 86.0 | 51.7 | 92.5 | 100.0 | 100.0 |
| 71 | Super Lig | 367 | 2025-08-08..2026-10-12 | 92.4 | 95.9 | 78.8 | 89.4 | 56.0 | 92.1 | 100.0 | 100.0 |
| 122 | Czech 1. Liga | 354 | 2025-07-18..2026-10-11 | 99.4 | 74.0 | 79.4 | 83.3 | 45.6 | 0.6 | 100.0 | 100.0 |
| 42 | Champions League | 207 | 2025-09-16..2026-09-10 | 100.0 | 100.0 | 80.2 | 95.7 | 94.7 | 95.7 | 100.0 | 100.0 |
| 73 | Europa League | 207 | 2025-09-24..2026-09-17 | 100.0 | 97.6 | 68.1 | 89.4 | 68.6 | 90.8 | 100.0 | 100.0 |
| 10216 | Conference League | 153 | 2025-10-02..2026-05-27 | 100.0 | 78.4 | 32.7 | 68.0 | 29.1 | 72.5 | 100.0 | 100.0 |
| 48 | Championship | 662 | 2025-08-08..2026-10-11 | 99.1 | 100.0 | 84.4 | 91.5 | 64.0 | 93.8 | 100.0 | 100.0 |
| 59 | Eliteserien | 321 | 2025-07-05..2026-10-12 | 99.7 | 98.8 | 77.3 | 77.9 | 95.6 | 91.0 | 100.0 | 100.0 |
| 38 | Austrian Bundesliga | 243 | 2025-08-01..2026-10-11 | 98.4 | 100.0 | 80.2 | 86.8 | 53.1 | 91.8 | 100.0 | 100.0 |
| 64 | Scottish Premiership | 276 | 2025-08-02..2026-10-11 | 99.3 | 95.3 | 81.2 | 90.9 | 63.8 | 93.1 | 100.0 | 100.0 |
| 135 | Greek Super League 1 | 277 | 2025-08-23..2026-10-12 | 94.6 | 61.7 | 78.3 | 89.9 | 49.1 | 92.1 | 100.0 | 100.0 |
| 46 | Danish Superligaen | 252 | 2025-07-18..2026-10-12 | 99.6 | 94.0 | 81.0 | 81.0 | 92.7 | 91.7 | 100.0 | 100.0 |
| 69 | Swiss Super League | 288 | 2025-07-25..2026-10-11 | 99.0 | 87.8 | 82.6 | 89.2 | 54.7 | 93.4 | 100.0 | 100.0 |

Overall: lambda 97.97 %, starter value both sides 92.8 %, lineup form 79.6 %, XI vs usual 89.7 % (home side), unavailable
key sent on 10,296 of 13,596 sides (75.7 %), xG last 5 87.2 % (home), points / rest / home advantage 100 %.
XI features are empty before the first ratings cutoff (2025-09-01) and for a team's first 3 collected matches.

## History lambdas (`walkforward_lambdas_results_*.csv`)

Same columns as `walkforward_dataset.py`, but `match_id`, `competition_id`, `home_team_id`, `away_team_id` are
**FotMob ids** (the results table has no DB uuids; `competition_id` = `competition_provider_id`). Production rating
code and defaults (`GlobalPoissonRatings`, `domestic_groups` keyed by competition id, `XG_GOAL_WEIGHT` 0.5,
lookback 400 d, half-life 180 d). Rows used: 168,347 of 168,579 (232 `awarded = 1` dropped; `awarded` NULL kept),
team 959006 mapped to 6500 (Reggiana, 5 rows). xG: production rows only (6,444); **history rows are goals-only**,
because the history details file (`fotmob_match_details_history.jsonl`) was still being collected (8–12 k of the
history matches at run time). Re-run with `--xg-details data/training/fotmob_match_details_history.jsonl` once it is
complete to give history matches the same goal/xG blend that production uses for the details competitions.

| Season (kick-off) | Rows | TARGET13 rows | TARGET13 history matches with a lambda |
|---|---|---|---|
| 2022/23 (from 2022-08-01) | 18,035 | 3,743 | 3,743 / 3,743 |
| 2023/24 | 18,857 | 3,742 | 3,742 / 3,742 |
| 2024/25 (to 2025-06-30) | 18,837 | 3,826 | 3,826 / 3,826 |
| July 2025 file | 1,822 | 38 | — |

Cutoffs before mid-2022 have only the history from 2021-07 (the results table starts there), so the first cutoffs
rest on ≈ 13 months of results; the table covers 115 competitions before 2025-07 (all production competitions after).

**Reproduction check** (`walkforward_from_results_check.json`, cutoffs 2026-08-10 / 09-07 / 10-05, production rows):
against the reference file `walkforward_lambdas_xg.csv` the mean |Δ ln λ| is 0.0022–0.0026 (95–96 % of lambdas
within 1 %, max 0.18). The original DB-based code refitted now on the current production DB differs from that file by
the same amount (0.0022 at 2026-10-05), i.e. the production DB has changed since the reference file was written.
Against that fresh DB fit the results-table port differs by a mean |Δ ln λ| of 0.0002–0.0003 (max 0.008; 95.7–99.6 %
within 0.1 %); the training sets differ by one match (the results table skips one production match with an invalid
team id).

## `match_model_report.json` / `match_model_candidate.json`

Split used here: train < 2026-04-01 (4,396 matches from 2025-07-05), validation 2026-04-01..2026-06-30 (1,135),
test ≥ 2026-07-01 (1,129, to 2026-10-11). Report sections: `splits` (coverage per split), `selection` (L2 ×
recalibration grid, backward elimination, HGB grid), `ablations_validation` (GLM and HGB), `test` (per model: all /
league / european metrics, paired bootstrap CIs vs the baseline, calibration tables), `test_market` (591 test matches
with closing odds), `final_models`, `goal_layer_train_validation_only`, `note` (run history). The candidate holds the
selected GLM fitted on train + validation (`evaluated_model`) and refitted on all rows (`refit_all_rows`, not
evaluated), each with its exact term definitions (source column per equation, mean, sd, coefficient per sd and per
unit, missing indicators, score-model rho / NB dispersion). **Draft only; nothing in `backend/config/` was written.**

## Known gaps / caveats

1. Only ≈ 1.25 seasons of details (2025-07 → 2026-10): 4,396 training matches, 36 European test matches.
2. The production goal layer (`config/goal_model.json`) was fitted on lambda rows up to 2026-10-11, i.e. including the
   validation and test periods; `lambda_home/away` therefore carry an in-sample total-goals calibration. The report
   quantifies it with a baseline whose goal layer is refitted on train + validation only.
3. `unavailable` lists: the key is missing for 24 % of sides (null, not 0), with large differences between
   competitions (29 % of UECL sides have it, 97 % of Premier League sides). Of the 17,978 listed players in the
   current file none appeared in the match, consistent with pre-match snapshots (not proven).
4. Market values: missing for 41 % of Liga Portugal and 38 % of Greek Super League matches (one side or both).
5. Form and congestion use only competitions present in `all_results.db`; 478 early cup-round fixtures after
   2025-07-01 are missing there (see `data/history/README_history.md`), so a few rest-day / 14-day counts are too
   high / too low around those rounds. xG form uses only the details competitions (league + UEFA).
6. Positions of unavailable players come from the ratings file (latest team / usual position before the cutoff).
7. History rows: XI features need the stage-A ratings re-run on the history (`player_impact_asof_all.csv.gz`); with the
   current ratings file they are empty before 2025-09-01.
