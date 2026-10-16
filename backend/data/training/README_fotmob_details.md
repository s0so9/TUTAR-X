# FotMob match details — training dataset (players, line-ups, team xG)

**Source:** FotMob unofficial API, `GET {settings.fotmob_base_url}/api/data/matchDetails?matchId=<FotMob match id>`.
Match ids come from either
* `--source db` (default): `matches.provider_id` of FINISHED matches in `backend/football_intelligence.db` →
  `fotmob_match_details.jsonl` (2025-07 → 2026-10), or
* `--source fixtures`: FotMob season fixture lists (`/api/data/leagues?id=<league>&season=<season>`) →
  `fotmob_match_details_history.jsonl` (complete past seasons, see [History seasons](#history-seasons-fotmob_match_details_historyjsonl)).

**Collector:** `backend/scripts/data_collection/collect_fotmob_details.py` (resumable, polite: the shared
cross-process limiter `fotmob_rate.py` is called before every request (one global budget for all FotMob collectors
on the machine; an HTTP 429 is reported to it so every collector pauses), ≤3 workers / ≥0.3 s between requests per
worker for `--source db`, ≤2 workers / ≥0.4 s for `--source fixtures`, exponential backoff + jitter on timeouts /
connection errors / 429 / 5xx, global cool-down after a 429, a worker stops after 5 consecutive failed matches, HTTP
403 or a challenge page stops the whole run with exit code 2 and is never worked around). Raw responses are written
atomically (temp file `*.tmp` + `os.replace`), so readers never see a partial file.
**Honesty rule:** nothing is invented or imputed. A value FotMob does not send is `null`; `0` appears only when
FotMob sends `0`.

## Files

| File | Content |
|---|---|
| `fotmob_match_details.jsonl` | one JSON object per match (schema below) |
| `fotmob_details_errors.jsonl` | one line per failed attempt: `match_provider_id, competition_provider_id, error, detail, attempts, at` |
| `fotmob_match_details_history.jsonl` | past seasons from FotMob fixture lists: one JSON object per match, same schema plus `season` ([History seasons](#history-seasons-fotmob_match_details_historyjsonl)) |
| `fotmob_details_history_errors.jsonl` | errors of the history runs: same columns plus `season`; fixture-list problems have `match_provider_id = null`, `error = league_*` |
| `../raw_cache/fotmob_match_details/<match id>.json.gz` | the untouched raw API response of every collected match of both files (gzip). Lets the datasets be re-parsed without re-fetching: `--from-raw --output <new file>` |
| `../raw_cache/fotmob_leagues/<league>_<season, "/"→"-">.json.gz` | untouched `/api/data/leagues` responses used as fixture lists (gzip; shared with the history-results collector, see `../history/README_history.md`; an existing file is reused, never re-fetched) |

## Re-running / extending

```bash
cd backend
# resume or extend (skips ids already in the output file); A and B are the predefined sets
venv/Scripts/python.exe scripts/data_collection/collect_fotmob_details.py --competitions A,B
venv/Scripts/python.exe scripts/data_collection/collect_fotmob_details.py --competitions 47,71 --concurrency 2
# coverage table (markdown)
venv/Scripts/python.exe scripts/data_collection/collect_fotmob_details.py --competitions A,B --coverage
# re-parse the raw cache with a changed parser (no network)
venv/Scripts/python.exe scripts/data_collection/collect_fotmob_details.py --competitions A,B --from-raw --output data/training/fotmob_match_details_v2.jsonl
# past seasons from FotMob fixture lists (history file; newest season first; resumable)
venv/Scripts/python.exe scripts/data_collection/collect_fotmob_details.py --source fixtures --seasons 2024/2025,2023/2024,2022/2023 --competitions TARGET13
venv/Scripts/python.exe scripts/data_collection/collect_fotmob_details.py --source fixtures --seasons 2024/2025,2023/2024,2022/2023 --competitions TARGET13 --coverage
```

Set A = 47, 87, 55, 54, 53, 42, 73, 10216. Set B = 71, 57, 61, 40, 48, 59, 38, 64, 122, 135, 46, 69.
TARGET13 = 47, 87, 55, 54, 53, 57, 61, 40, 71, 122, 42, 73, 10216 (the 10 strongest leagues by UEFA association
coefficient + Champions League, Europa League, Conference League).

## Match-level fields

Paths are relative to the response root. `content.stats.Periods.All.stats[*].stats[*]` rows of `type == "title"`
are section headers (always `[null, null]`) and are skipped.

| Field | Type | Source path / definition |
|---|---|---|
| `match_provider_id` | str | `general.matchId` (FotMob match id) |
| `scheduled_at` | str (ISO UTC) | `general.matchTimeUTCDate` |
| `competition_provider_id` | int | db source: from the DB (`competitions.provider_id`, the parent FotMob league id that was requested); history file: the FotMob league id whose fixture list was requested |
| `season` | str | **history file only** (inserted after `competition_provider_id`): the requested season, e.g. `2024/2025` (`YYYY` for calendar-year leagues) |
| `source_league_id` / `source_parent_league_id` | int | `general.leagueId` / `general.parentLeagueId` (leagueId can be a sub-season/stage id, e.g. 900416 for Czech 1. Liga) |
| `home_team_provider_id` / `away_team_provider_id` | int | `general.homeTeam.id` / `general.awayTeam.id` (FotMob team ids = `teams.provider_id`) |
| `home_score` / `away_score` | int | `header.teams[0].score` / `header.teams[1].score` |
| `awarded` | bool | `header.status.awarded`; history file: also `true` when the season fixture list marks the match awarded. The score is then the awarded (official) score, while player stats describe whatever was actually played (none for walkovers) |
| `home_xg` / `away_xg` | float \| null | first row with `key == "expected_goals"` in `content.stats.Periods.All.stats[*].stats[*]` → `.stats[0]` / `.stats[1]` (sent as strings, parsed to float). `null` when FotMob has no xG for the match |
| `lineup_type` / `lineup_source` | str \| null | `content.lineup.lineupType` / `content.lineup.source` (e.g. `standard`, `enetpulse`/`opta`) |
| `home_formation` / `away_formation` | str \| null | `content.lineup.homeTeam.formation` / `.awayTeam.formation` |
| `{side}_starters_market_value` | int \| null | `content.lineup.{side}Team.totalStarterMarketValue` (EUR, as sent) |
| `{side}_starters_avg_age` | float \| null | `content.lineup.{side}Team.averageStarterAge` |
| `{side}_team_rating` | float \| null | `content.lineup.{side}Team.rating` (FotMob team match rating) |
| `team_stats` | object \| null | every full-match team stat as `{key: [home, away]}` from `content.stats.Periods.All.stats[*].stats[*]` (`key`, `stats`), raw values exactly as sent (some are strings like `"240 (80%)"`; xG values are strings). Includes `expected_goals_open_play`, `expected_goals_set_play`, `expected_goals_non_penalty`, `expected_goals_on_target`, `total_shots`, `big_chance`, `BallPossesion`, … when FotMob has them |
| `players` | list | see below; starters then subs, home then away |
| `unavailable` | list | `content.lineup.{side}Team.unavailable[*]` → `{player_id, name, team_side, type (injury/suspension/…), expected_return, market_value}` |
| `db_check` | object \| null | `home_team_matches_db`, `away_team_matches_db`, `score_matches_db`: comparison of the API values with the local DB row; always `null` in the history file (matches not in the DB) |
| `fetched_at` | str (ISO UTC) | collector clock when the response was parsed (`--from-raw`, or a history match whose raw response was already cached: the raw file's mtime) |

## Player fields (`players[*]`)

`lp` = the line-up entry `content.lineup.{homeTeam|awayTeam}.{starters|subs}[*]`;
`ps` = `content.playerStats["<player id>"]`; `ps.stat(k)` = the first `ps.stats[*].stats[<title>].stat.value`
whose `.key == k` (matched by the stable `key`, never by the English title).

| Field | Type | Source path / definition |
|---|---|---|
| `player_id` | int | `lp.id` (FotMob player id) |
| `name` | str | `lp.name` |
| `team_side` | `home`/`away` | which line-up list the player is in |
| `team_provider_id` | int | `content.lineup.{side}Team.id` |
| `is_starter` | bool | player is in `starters` (true) or `subs` (false) |
| `appeared` | bool | derived: `is_starter` or a `subIn` event exists in `lp.performance.substitutionEvents` |
| `position` | `GK`/`DEF`/`MID`/`FWD` \| null | label of `lp.usualPlayingPositionId` (0 GK, 1 DEF, 2 MID, 3 FWD) — the player's *usual* role |
| `usual_position_id` | int \| null | `lp.usualPlayingPositionId` (raw) |
| `position_id` | int \| null | `lp.positionId` (raw FotMob pitch-slot id for starters, e.g. 11 = GK, 3x back line, 6x/7x midfield, 8x/10x attacking, 115 central striker; subs usually null) |
| `is_goalkeeper` | bool \| null | `ps.isGoalkeeper` |
| `shirt_number` | str \| null | `lp.shirtNumber` |
| `age` | int \| null | `lp.age` (varies between matches for the same player, i.e. it looks like age at match time) |
| `minutes_played` | int \| null | `ps.stat("minutes_played")` |
| `sub_in_minute` / `sub_out_minute` | int \| null | `lp.performance.substitutionEvents[*].time` with `type == "subIn"` / `"subOut"` |
| `rating` | float \| null | `ps.stat("rating_title")` (FotMob rating, 2 decimals); fallback `lp.performance.rating` (1 decimal) |
| `rating_source` | `playerStats`/`lineup`/null | which of the two paths gave `rating` |
| `goals` | int \| null | `ps.stat("goals")` (not sent for goalkeepers) |
| `assists` | int \| null | `ps.stat("assists")` |
| `xg` | float \| null | `ps.stat("expected_goals")` |
| `xa` | float \| null | `ps.stat("expected_assists")` |
| `xgot` | float \| null | `ps.stat("expected_goals_on_target_variant")` |
| `npxg` | float \| null | `ps.stat("expected_goals_non_penalty")` |
| `shots` | int \| null | `ps.stat("total_shots")` |
| `shots_on_target` | int \| null | `ps.stat("ShotsOnTarget")` |
| `shotmap_count` | int \| null | `len(ps.shotmap)`; `null` when FotMob sends no `shotmap` key (competition without shot data). NOTE: own goals appear in the shotmap (`isOwnGoal: true`) and are counted here |
| `stats_available` | bool | `ps.stats` exists and is non-empty (false for unused subs) |
| `market_value` | int \| null | `lp.marketValue` (EUR, as sent; varies between matches for the same player, i.e. it looks like a value near match time) |

### How FotMob encodes "zero" (important for training)

FotMob **omits** `expected_goals`, `expected_assists`, `total_shots`, `ShotsOnTarget`, `xgot`, `npxg` for a player
who had no shot / no chance created, instead of sending 0. This dataset keeps those as `null` (AGENTS.md: no
invented values). A training pipeline that wants 0 can apply the rule documented by the data itself:

* `stats_available == true` **and** `shotmap_count == 0` → the player took no shots in a competition where FotMob
  tracks shots, so `xg`/`shots` = 0 is a defensible imputation (decided by the model owner, not by this dataset).
* `shotmap_count == null` → FotMob has no shot data for that match; xG is genuinely unknown.

`goals`/`assists` are sent explicitly (including 0) for outfield players who played; goalkeepers usually do not
get `goals`/`assists` keys. Players who did not appear have no stats at all (`stats_available == false`, every stat
`null`).

## Coverage

Generated with `--coverage --competitions A,B` after the 2026-10-13 run.

| FotMob id | Competition | Finished in DB | Collected | Error rows* | Line-up present | Team xG | Player ratings | Player xG | Player minutes | Market values | Rated appearances | Unavailable list | Avg players/match | Score/team mismatch vs DB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 47 | Premier League | 440 | 440 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 91.2% | 74.3% | 40.0 | 0 |
| 87 | LaLiga | 458 | 458 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 92.9% | 77.7% | 44.8 | 0 |
| 55 | Serie A | 440 | 440 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 92.8% | 84.8% | 46.9 | 0 |
| 54 | Bundesliga | 351 | 351 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 91.3% | 81.8% | 39.9 | 0 |
| 53 | Ligue 1 | 359 | 359 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 92.0% | 70.2% | 39.9 | 0 |
| 42 | Champions League | 207 | 207 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 92.8% | 83.6% | 43.7 | 0 |
| 73 | Europa League | 207 | 207 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 93.4% | 80.7% | 44.1 | 0 |
| 10216 | Conference League | 153 | 153 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 92.2% | 25.5% | 43.9 | 0 |
| 71 | Super Lig | 367 | 367 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 90.5% | 75.5% | 41.6 | 0 |
| 57 | Eredivisie ECL Playoff | 381 | 381 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 92.3% | 77.2% | 44.1 | 0 |
| 61 | Liga Portugal | 377 | 377 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 92.2% | 76.4% | 40.9 | 0 |
| 40 | Belgian Pro League ECL Playoff | 385 | 385 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 91.8% | 66.2% | 40.7 | 0 |
| 48 | Championship Playoff | 664 | 662 | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 92.4% | 75.5% | 40.0 | 0 |
| 59 | Eliteserien | 321 | 321 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 92.4% | 30.8% | 39.3 | 0 |
| 38 | Bundesliga | 243 | 243 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 91.6% | 71.2% | 39.8 | 0 |
| 64 | Premiership | 276 | 276 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 93.0% | 78.6% | 40.0 | 0 |
| 122 | 1. Liga | 354 | 354 | 0 | 100.0% | 0.0% | 100.0% | 0.0% | 100.0% | 100.0% | 92.7% | 66.4% | 42.9 | 0 |
| 135 | Super League Relegation Group | 277 | 277 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 92.2% | 66.1% | 45.1 | 0 |
| 46 | Superligaen | 252 | 252 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 92.5% | 69.4% | 39.9 | 0 |
| 69 | Super League | 288 | 288 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 93.1% | 73.6% | 39.9 | 0 |
| | **Total** | 6800 | 6798 | 2 | 100.0% | 94.8% | 100.0% | 94.8% | 100.0% | 100.0% | 92.2% | 71.8% | 41.8 | 0 |

Match-level columns (Team xG ... Market values) = share of collected matches where the value exists (team xG: both sides; player columns: at least one player). Rated appearances = share of players who appeared (starter or subbed on) with a rating. Unavailable list = share of matches with a non-empty injury/suspension list. *Error rows = error-file rows for matches still not collected.

## Known gaps / caveats

Collected 2026-10-13 (one run, 1,129 s, ~6 requests/s with 3 workers, 0 transport errors, 0 HTTP 429).
Totals: **6,798 matches**, 284,163 player rows (211,060 appearances), 0 duplicate match ids, 0 score or team-id
mismatches against the DB.

1. **Czech 1. Liga (122): no xG at all.** FotMob sends no team `expected_goals` and no player `xg`/`xa`/`xgot`
   and no `shotmap` key for this league (354/354 matches). Ratings, minutes, goals, assists and `total_shots`
   (when > 0) are present. Every other competition has team and player xG in 100 % of collected matches.
2. **Zero shooting stats are omitted by FotMob** (see the section above): `xg`/`shots`/`xa` are `null`, not 0, for
   players without a shot / chance. Use `stats_available` + `shotmap_count` to decide on imputation.
3. **Own goals sit in the shotmap.** 462 appearances have `xg == null` but `shotmap_count > 0`; checked samples are
   own goals (`isOwnGoal: true`, no xG). Do not read `shotmap_count` as "shots taken" without that caveat.
4. **Ratings:** 16,420 of 211,060 appearances (7.8 %) have no rating — mostly short cameos (median 5 minutes
   played). `rating_source == "lineup"` (1-decimal fallback) occurs only twice.
5. **Market value:** `null` for 12,458 appearances (5.9 %). For the same player the value changes from match to
   match (464 of 491 Premier League players with ≥ 5 matches), so it looks like a value near match time rather
   than today's value; FotMob does not document this — treat it as "probably point-in-time", not proven.
   `age` also changes between matches (age at match time).
6. **Injury/suspension lists (`unavailable`) are present for finished matches** in 71.8 % of matches (25.5 %
   UECL, 30.8 % Eliteserien, 66–85 % elsewhere). They look like match-time snapshots (e.g. matches of
   2025-08-15 list "expected return: Mid August 2025"). An empty list means "nothing listed", not "verified
   fully fit".
7. **2 DB matches are not in the dataset** (Championship play-off Middlesbrough – Southampton, FotMob ids
   5427701 on 2026-05-09 and 5427703 on 2026-05-12): FotMob reports both as **Cancelled** (`header.status.cancelled`),
   while the DB stores them as FINISHED with scores 0-0 and 2-1. The DB rows look wrong; they are logged in
   `fotmob_details_errors.jsonl` (`parse_not_finished_in_source`).
8. **Shotmap missing although stats exist** in 4 matches (Championship 3, Swiss Super League 1); team xG is
   present there.
9. **Player xG vs team xG:** |Σ player xG − team xG| per team-side has median 0.01, p95 0.06, max 0.91
   (n = 12,888 team-sides): rounding plus shots not attributed to a player in a few matches.
10. **Line-up provider:** `lineup_source` is `enetpulse` for 6,764 matches and `optaSdapi` for 34 Championship
    matches; whether ratings are on exactly the same scale across providers has not been checked.
11. **Positions:** `position` is the player's *usual* role, not the role in this match; `position_id` (pitch slot)
    exists only for starters (all 134,607 bench rows have `null`).
12. **Competition names in the DB are stage names** for some leagues (e.g. "Eredivisie ECL Playoff",
    "Championship Playoff", "Super League Relegation Group") although `competition_provider_id` is the parent
    league and all its stages are included; `source_league_id` tells the stages apart.
13. **Time window:** only matches FINISHED in the local DB (2025-07 → 2026-10-12), i.e. roughly one and a quarter
    seasons per league. Older seasons are in the separate history file (next section).

## History seasons: `fotmob_match_details_history.jsonl`

**What:** the same match details for **complete past seasons** 2024/2025, 2023/2024 and 2022/2023 of TARGET13 =
Premier League 47, LaLiga 87, Serie A 55, Bundesliga 54, Ligue 1 53, Eredivisie 57, Liga Portugal 61, Belgian Pro
League 40, Süper Lig 71, Czech 1. Liga 122 (the 10 strongest leagues by UEFA association coefficient) + Champions
League 42, Europa League 73, Conference League 10216; plus a 2024/2025 tail for 48, 38, 64, 135, 46, 69 and the
calendar-year season 2024 of Eliteserien 59 (tables below).

**Match ids:** `GET /api/data/leagues?id=<league>&season=<season>` → `fixtures.allMatches[*]`, kept when
`status.finished == true` and `status.cancelled != true`. Awarded matches (`status.awarded`) are kept and flagged
(`awarded = true`). A league response is used only if `details.selectedSeason == <season>` and `details.id == <league>`;
otherwise the list is rejected and logged, never silently replaced by another season. League responses are cached
untouched (gzip, atomic write) in `../raw_cache/fotmob_leagues/`; the cache is shared with the history-results
collector and an existing file is reused instead of fetched. A match whose raw response already exists in
`../raw_cache/fotmob_match_details/` is parsed from that file instead of re-fetched (`--no-reuse-raw` forces a fetch).

**Schema:** identical to `fotmob_match_details.jsonl` (all field tables above apply) except:

| Field | History file |
|---|---|
| `season` | NEW, right after `competition_provider_id`: the requested season (`2024/2025`, …; `2024` for Eliteserien) |
| `competition_provider_id` | the FotMob league id whose fixture list was requested |
| `awarded` | `header.status.awarded` **or** the fixture list's `status.awarded` |
| `db_check` | always `null` (these matches are not in the production DB) |

Errors: `fotmob_details_history_errors.jsonl` (same columns as the db-source error file plus `season`; fixture-list
problems have `match_provider_id = null` and `error = league_*`). After the runs below it is **empty**.

```bash
cd backend
venv/Scripts/python.exe scripts/data_collection/collect_fotmob_details.py --source fixtures \
    --seasons 2024/2025,2023/2024,2022/2023 --competitions TARGET13            # collect / resume
venv/Scripts/python.exe scripts/data_collection/collect_fotmob_details.py --source fixtures \
    --seasons 2024/2025,2023/2024,2022/2023 --competitions TARGET13 --coverage # table below (no network)
venv/Scripts/python.exe scripts/data_collection/collect_fotmob_details.py --source fixtures \
    --seasons 2024/2025 --competitions 47 --from-raw --output <new.jsonl> --errors <new_err.jsonl>  # re-parse
```

### Coverage (TARGET13)

Generated with `--source fixtures --seasons 2024/2025,2023/2024,2022/2023 --competitions TARGET13 --coverage`
after the 2026-10-13 run.

| FotMob id | Competition | Season | Fixture list (finished, not cancelled) | Collected | Missing | Error ids* | Line-ups | Player ratings | Team xG | Player xG | Unavailable lists | Awarded | Rated appearances | Avg players/match | Mismatch vs fixture list |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 47 | Premier League (ENG) | 2024/2025 | 380 | 380 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 98.4% | 0 | 91.2% | 40.0 | 0 |
| 87 | LaLiga (ESP) | 2024/2025 | 380 | 380 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 82.6% | 0 | 92.7% | 44.6 | 0 |
| 55 | Serie A (ITA) | 2024/2025 | 380 | 380 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 88.9% | 0 | 92.2% | 46.5 | 0 |
| 54 | Bundesliga (GER) | 2024/2025 | 306 | 306 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 94.4% | 1 | 91.3% | 39.9 | 0 |
| 53 | Ligue 1 (FRA) | 2024/2025 | 306 | 306 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 78.1% | 0 | 91.7% | 39.9 | 0 |
| 57 | Eredivisie (NED) | 2024/2025 | 309 | 309 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 83.5% | 0 | 92.0% | 44.0 | 0 |
| 61 | Liga Portugal (POR) | 2024/2025 | 306 | 306 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 79.7% | 0 | 91.5% | 39.9 | 0 |
| 40 | First Division A (BEL) | 2024/2025 | 313 | 313 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 99.0% | 1 | 90.9% | 40.2 | 0 |
| 71 | Super Lig (TUR) | 2024/2025 | 342 | 342 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 76.3% | 1 | 89.6% | 41.7 | 0 |
| 122 | 1. Liga (CZE) | 2024/2025 | 276 | 276 | 0 | 0 | 100.0% | 0.4% | 0.0% | 0.0% | 97.5% | 0 | 0.3% | 42.0 | 0 |
| 42 | Champions League (INT) | 2024/2025 | 189 | 189 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 93.1% | 0 | 92.5% | 43.5 | 0 |
| 73 | Europa League (INT) | 2024/2025 | 189 | 189 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 73.5% | 0 | 92.6% | 43.9 | 0 |
| 10216 | Conference League (INT) | 2024/2025 | 153 | 153 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 62.1% | 0 | 92.1% | 42.8 | 0 |
|  | **Subtotal 2024/2025** | 2024/2025 | 3829 | 3829 | 0 | 0 | 100.0% | 92.8% | 92.8% | 92.8% | 86.3% | 3 | 85.0% | 42.2 | 0 |
| 47 | Premier League (ENG) | 2023/2024 | 380 | 380 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 96.8% | 0 | 91.2% | 39.9 | 0 |
| 87 | LaLiga (ESP) | 2023/2024 | 380 | 380 | 0 | 0 | 100.0% | 99.7% | 99.7% | 99.7% | 84.2% | 0 | 92.1% | 43.9 | 0 |
| 55 | Serie A (ITA) | 2023/2024 | 380 | 380 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 97.6% | 0 | 92.0% | 46.6 | 0 |
| 54 | Bundesliga (GER) | 2023/2024 | 306 | 306 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 96.1% | 0 | 90.8% | 39.7 | 0 |
| 53 | Ligue 1 (FRA) | 2023/2024 | 306 | 306 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 80.4% | 0 | 91.6% | 40.0 | 0 |
| 57 | Eredivisie (NED) | 2023/2024 | 309 | 309 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 89.0% | 0 | 91.9% | 43.2 | 0 |
| 61 | Liga Portugal (POR) | 2023/2024 | 306 | 306 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 77.1% | 0 | 90.8% | 40.0 | 0 |
| 40 | First Division A (BEL) | 2023/2024 | 313 | 313 | 0 | 0 | 99.7% | 99.4% | 99.4% | 99.4% | 93.0% | 1 | 90.7% | 37.9 | 0 |
| 71 | Super Lig (TUR) | 2023/2024 | 380 | 380 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 69.5% | 1 | 89.9% | 41.7 | 0 |
| 122 | 1. Liga (CZE) | 2023/2024 | 277 | 277 | 0 | 0 | 100.0% | 0.0% | 0.0% | 0.0% | 77.6% | 0 | 0.0% | 40.9 | 0 |
| 42 | Champions League (INT) | 2023/2024 | 125 | 125 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 97.6% | 0 | 92.1% | 43.3 | 0 |
| 73 | Europa League (INT) | 2023/2024 | 141 | 141 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 83.7% | 0 | 92.2% | 43.6 | 0 |
| 10216 | Conference League (INT) | 2023/2024 | 141 | 141 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 76.6% | 0 | 92.6% | 43.3 | 0 |
|  | **Subtotal 2023/2024** | 2023/2024 | 3744 | 3744 | 0 | 0 | 100.0% | 92.5% | 92.5% | 92.5% | 86.2% | 2 | 84.6% | 41.7 | 0 |
| 47 | Premier League (ENG) | 2022/2023 | 380 | 380 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 78.2% | 0 | 91.7% | 40.0 | 0 |
| 87 | LaLiga (ESP) | 2022/2023 | 380 | 380 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 70.5% | 0 | 92.7% | 44.0 | 0 |
| 55 | Serie A (ITA) | 2022/2023 | 381 | 381 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 55.9% | 0 | 92.9% | 46.9 | 0 |
| 54 | Bundesliga (GER) | 2022/2023 | 306 | 306 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 68.3% | 0 | 92.0% | 39.8 | 0 |
| 53 | Ligue 1 (FRA) | 2022/2023 | 380 | 380 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 58.9% | 0 | 92.5% | 39.7 | 0 |
| 57 | Eredivisie (NED) | 2022/2023 | 312 | 312 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 68.6% | 0 | 92.0% | 43.4 | 0 |
| 61 | Liga Portugal (POR) | 2022/2023 | 306 | 306 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 53.9% | 0 | 91.5% | 39.9 | 0 |
| 40 | First Division A (BEL) | 2022/2023 | 330 | 330 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 67.6% | 2 | 91.9% | 36.7 | 0 |
| 71 | Super Lig (TUR) | 2022/2023 | 342 | 342 | 0 | 0 | 91.5% | 91.5% | 91.5% | 91.5% | 53.2% | 29 | 90.6% | 38.3 | 0 |
| 122 | 1. Liga (CZE) | 2022/2023 | 276 | 276 | 0 | 0 | 100.0% | 0.0% | 0.0% | 0.0% | 47.5% | 0 | 0.0% | 39.9 | 0 |
| 42 | Champions League (INT) | 2022/2023 | 125 | 125 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 68.0% | 0 | 92.2% | 43.4 | 0 |
| 73 | Europa League (INT) | 2022/2023 | 141 | 141 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 71.6% | 0 | 92.9% | 44.0 | 0 |
| 10216 | Conference League (INT) | 2022/2023 | 141 | 141 | 0 | 0 | 100.0% | 99.3% | 99.3% | 99.3% | 59.6% | 0 | 92.1% | 43.3 | 0 |
|  | **Subtotal 2022/2023** | 2022/2023 | 3800 | 3800 | 0 | 0 | 99.2% | 91.9% | 91.9% | 91.9% | 63.1% | 31 | 85.3% | 41.2 | 0 |
|  | **Total** | all | 11373 | 11373 | 0 | 0 | 99.7% | 92.4% | 92.4% | 92.4% | 78.5% | 36 | 85.0% | 41.7 | 0 |

Duplicate match ids in the output: 0. Rows whose id is not in the cached fixture list: 0. Fixture-list scores that
could not be parsed (not compared): 0. Line-ups / Player ratings / Player xG = share of collected matches with at
least one player row / rated player / player xG value; Team xG = both sides present; Unavailable lists = non-empty
injury/suspension list; Awarded = count of matches flagged awarded. Rated appearances = share of players who appeared
(starter or subbed on) with a rating. Mismatch = home/away team id or score differs from the fixture list.
*Error ids = distinct still-missing match ids with at least one row in the errors file.

Totals (TARGET13): **11,373 matches**, 474,552 player rows, 349,462 appearances.

### Coverage (optional tail: 2024/2025 of other Set B leagues, Eliteserien 2024)

Generated with `--source fixtures --seasons 2024/2025 --competitions 48,38,64,135,46,69 --coverage` and
`--source fixtures --seasons 2024 --competitions 59 --coverage` (Eliteserien plays calendar-year seasons).

| FotMob id | Competition | Season | Fixture list (finished, not cancelled) | Collected | Missing | Error ids* | Line-ups | Player ratings | Team xG | Player xG | Unavailable lists | Awarded | Rated appearances | Avg players/match | Mismatch vs fixture list |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 48 | Championship (ENG) | 2024/2025 | 557 | 557 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 95.9% | 0 | 92.2% | 40.0 | 0 |
| 38 | Bundesliga (AUT) | 2024/2025 | 195 | 195 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 83.6% | 0 | 92.2% | 36.0 | 0 |
| 64 | Premiership (SCO) | 2024/2025 | 228 | 228 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 74.6% | 0 | 93.1% | 39.9 | 0 |
| 135 | Super League 1 (GRE) | 2024/2025 | 236 | 236 | 0 | 0 | 100.0% | 97.9% | 2.5% | 2.5% | 59.3% | 0 | 90.1% | 39.9 | 0 |
| 46 | Superligaen (DEN) | 2024/2025 | 193 | 193 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 97.4% | 0 | 91.8% | 39.8 | 0 |
| 69 | Super League (SUI) | 2024/2025 | 228 | 228 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 79.4% | 0 | 93.0% | 39.7 | 0 |
| 59 | Eliteserien (NOR) | 2024 | 240 | 240 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 65.8% | 0 | 91.8% | 39.2 | 0 |
|  | **Total tail** | | 1877 | 1877 | 0 | 0 | | | | | | 0 | | | 0 |

Tail notes: Greek Super League 1 (135) 2024/25 has team/player xG in only 6 of 236 matches (FotMob sent none for
the rest; the current season has 100 %). Eliteserien 2024 excludes Rosenborg – Lillestrøm 2024-07-21 (4385584,
abandoned, marked cancelled). Eliteserien 2025 matches before 2025-07-01 are in **neither** file (the DB window
starts 2025-07-01 and the 2025 season list was not collected).

**Whole history file:** 13,250 matches (TARGET13 11,373 + tail 1,877), 548,501 player rows, 407,002 appearances,
0 duplicate ids, 0 ids shared with `fotmob_match_details.jsonl`, errors file empty. Tail run 19:31 → 19:42 UTC,
1,877 matchDetails requests, 0 failed matches; no 429 was reported to the shared limiter (`cooldown_until` still 0.0
at 19:42 UTC). The run summary prints `non_success_attempts` (retried or failed requests by kind) since the
Eliteserien step, which reported `{}`; earlier runs did not count retries that later succeeded.

### Run and verification (2026-10-13)

* Run 18:16 → 19:31 UTC: 39 fixture lists (34 fetched, 5 already cached by the history-results collector), 11,373
  matches (11,369 fetched in the run, 4 parsed from raw responses cached minutes earlier by a 4-match smoke test),
  0 failed matches, 2 workers ≈ 2.5 requests/s under the shared 5 req/s budget. No 429 was
  reported to the shared limiter (`cooldown_until` still 0.0); no 403 or challenge page. The first run stopped after
  1,516 matches on a `PermissionError` raised inside the shared limiter (see gap 9 below); the resumed run skipped
  those 1,516 ids and finished the rest.
* Collected vs fixture lists: 11,373 / 11,373, 0 missing in every competition-season (table above); 0 duplicate ids;
  0 ids shared with `fotmob_match_details.jsonl`; 0 home/away-team or score mismatches against the fixture lists.
* Independent re-fetch of 3 random matches (seed 20261013, one per season: 3919280 Serie A 2022/23, 4221743
  Bundesliga 2023/24, 4506928 LaLiga 2024/25). The values were re-extracted by a separate script that does not import
  the collector. It uses English stat titles instead of keys (`"FotMob rating"`, `"Expected goals (xG)"`, `"Total shots"`, …),
  the score from `header.status.scoreStr`, the kick-off from `header.status.utcTime` and team ids from `header.teams`:
  **1,446 fields compared, 0 mismatches** (match fields, 10 team stats, starters / bench / unavailable sets, 10 stats per player).
* `--from-raw` re-parse of Premier League 2024/2025: 380 / 380 rows identical to the collected rows (every field
  and the key order; `fetched_at` identical to the second).
* Independent QA (separate code, no collector import; 2026-10-13 ~19:50 UTC). Every one of the 13,250 rows was
  re-extracted from its raw gzip (player stats and team xG by English title, score from `scoreStr`, kick-off from
  `header.status.utcTime`): **15,649,528 fields compared, 0 mismatches**, 0 zeros where the raw response has no
  value, 0 unreadable or truncated raw files. The 46 fixture lists were re-parsed: 13,250 expected = 13,250
  collected, 0 missing, 0 extra, 0 duplicates, 0 team or score mismatches, 36 awarded (flagged in both the list
  and the header). Every `scheduled_at` is UTC (`Z`) and inside its season window, and none is in the future.
  All 598 cells of the coverage tables above were reproduced. A live re-fetch of 8 matches and 1 fixture list
  through the shared limiter equals the cached raw responses (9,750 fields, 0 mismatches). An offline resume
  test re-added 5 removed rows byte-identically without any request.
* `tests/test_collect_fotmob_details.py`: fixture-list parsing, season/league check, history record shape,
  `--from-raw` + `--coverage` on a synthetic league, CLI defaults per source, atomic write, 429/403/challenge
  handling and limiter-lock retry (all offline).

### Known gaps / caveats (history file)

1. **UEFA competitions = main tournament only.** `fixtures.allMatches` of 42/73/10216 holds the group or league
   phase and the knockout rounds, **not the qualifying rounds**: Champions League 125 (2022/23, 2023/24: 96 group
   + 29 knockout) and 189 (2024/25: 144 league phase + 45 knockout) matches; Europa League 141/141/189; Conference
   League 141/141/153. Each group / stage has its own `source_league_id`.
2. **Czech 1. Liga (122): no xG and (almost) no player ratings in past seasons.** Ratings exist in 0 of 276 / 277
   matches (2022/23, 2023/24) and in 1 of 276 (2024/25), unlike the current season. Minutes, goals, assists,
   line-ups and injury lists are present. `lineup_source` is `null` for 276/276, 275/277 and 214/276 Czech matches
   (2022/23, 2023/24, 2024/25).
3. **Awarded matches (36):** the score is the awarded (official) score. The 29 Süper Lig 2022/23 walkovers (Hatayspor
   and Gaziantep FK withdrew after the February 2023 earthquake) and Standard Liège – Westerlo 2024-05-10 (4449361) have
   no line-up at all (`players = []`). Six others were played and then awarded, and their player stats describe
   what was played, e.g. Union Berlin – Bochum 2024-12-14 (4534664): awarded 0-2, played 1-1 (player goals sum to 2).
   Exclude or special-case `awarded == true` in goal/xG models.
4. **Excluded as cancelled** (not in the file): Bournemouth – Luton 2023-12-16 (4193691, abandoned; the replay is
   included) and Montpellier – Clermont 2023-10-08 (4219326, abandoned).
5. **Market values thin out with age:** `market_value` is present for 55.8 % (2024/25), 41.1 % (2023/24) and
   23.5 % (2022/23) of appearances; `home_starters_market_value` for 56.1 % / 38.6 % / 19.7 % of matches and
   `away_starters_market_value` for 56.2 % / 38.6 % / 20.0 %. Missing values stay `null` (never 0). `age` is present
   for 100 % / 82.8 % / 62.9 % of player rows.
6. **Injury/suspension lists thin out with age:** non-empty in 86.3 % / 86.2 % / 63.1 % of matches (2024/25 /
   2023/24 / 2022/23). Types: injury 31,340, suspension 455, internationalDuty 19, null 4 entries. An empty list
   means "nothing listed", not "fully fit".
   **`expected_return` is NOT a match-time value in the history file (look-ahead leakage):** FotMob sends a later
   state of the injury record. Entries for 2022/23 matches name a return year of 2025 3,875 times and 2026 235 times,
   but 2023 only 251 times. Over the whole history file, 9,014 of the 18,516 entries with a parseable date are more
   than 365 days after kick-off; e.g. Joshua Dasilva is listed for August 2024 Brentford matches with "Late May 2026"
   (the raw response says exactly that). List membership looks plausible: only 1.0 % / 2.5 % / 3.6 % (2022/23 /
   2023/24 / 2024/25) of listed players played both their team's previous and next match, against 8.5 % in the
   current-season file. 138 entries (133 matches) list a player who is also in that match's line-up (121 appeared),
   41 of them "Doubtful". Do not use `expected_return` from this file as a pre-match feature. Use list membership
   with care.
7. **Ratings:** outside Czechia 91.4–92.1 % of appearances are rated per season. Unrated appearances are mostly
   short cameos (outside Czechia: 26,612 unrated appearances with minutes, median 4 minutes played). Line-ups but no ratings and no xG in 3
   single matches: 4205608 (LaLiga 2024-03-03), 4206400 (Belgium 2024-02-16), 4010272 (UECL 2022-10-06).
8. **Player xG vs team xG:** |Σ player xG − team xG| per team-side has median 0.01, p95 0.12, max 1.88 (n = 21,014
   team-sides with team xG and at least one player `xg`), which is wider than the current season (p95 0.06).
   Counting every team-side with team xG gives n = 21,022 and max 2.17: 8 sides have team xG but no player `xg` at
   all, 6 of them with team xG 0 and 2 because the line-up list is incomplete (4206358 home: 8 line-up entries vs 18
   `playerStats` players; 4257234 away: 10 vs 21; see gap 11). 898 TARGET13 player rows have `xg == null` with
   `shotmap_count > 0`. 589 of them hold only own goals. The other 309 (243 matches) have shotmap shots with
   `expectedGoals` while FotMob sends no player xG stat: 219 shots under 0.005 xG (FotMob omits the stat when it
   would show 0.00), 79 penalties (0.79 each) and 11 other shots. The dataset keeps `xg = null` there, as sent.
   `lineup_source` is `null` for 2,973 of 11,373 matches (`enetpulse` otherwise).
9. **Shared limiter bug (Windows):** `fotmob_rate.acquire()` can raise `PermissionError [WinError 5]` when it
   `mkdir`s its lock directory while another process removes it (only `FileExistsError` is handled there). This
   collector now retries the limiter call on `OSError` and never skips it. The bug itself is in the shared module.
10. **Overlap with the db-source file:** none (0 shared ids); the history seasons end before the DB window starts
    (2025-07-01).
11. **Players with stats but no line-up entry are not in `players`.** `players` is built from the line-up lists
    (`content.lineup.{side}Team.starters/subs`). Some players exist only in `content.playerStats`, and the parser
    drops them. TARGET13: 613 such players in 495 matches; 227 of them have minutes > 0 (184 matches), they scored
    14 goals, and 102 have an xG value (20.15 in total). 16 team-sides have fewer than 11 starters, because the
    line-up list itself is incomplete. Tail: 103 players in 89 matches (48 with minutes). The db-source file has the
    same pattern (186 players in 156 matches, 29 with minutes, 3 goals). Nothing is invented. The raw responses
    hold these players (`playerStats[<id>]` with `teamId`), so a re-parse with `--from-raw` can recover them if the
    schema is extended. Per-player aggregates (minutes, goals, xG) are therefore slightly incomplete in these
    matches.
12. **`appeared` follows the line-up flags, not minutes.** `appeared` = starter or a `subIn` event. 92 bench rows
    (58 TARGET13 + 34 tail) have `minutes_played > 0` but no `subIn` event, so `appeared == false`. 55 TARGET13
    rows with `appeared == true` have stats but no `minutes_played`. Use `minutes_played` when it is present.
13. **Interrupted runs:** resume skips ids already in the output and tolerates a partially written last line. That
    partial line stays in the file as a line that does not parse, so readers should skip unparsable lines. The
    delivered history file has 0 such lines.
