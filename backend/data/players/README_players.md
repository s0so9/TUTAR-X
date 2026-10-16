# FotMob squads and players — TARGET13, season 2026/2027

> **AS-OF-TODAY SNAPSHOT — NEVER use these rows as features for matches played before `snapshot_at`.**
> Squads, injuries, market values, season stats, contract data and recent-match lists describe the
> moment the response was fetched (`snapshot_at`, UTC). Joining them to past matches leaks the future
> into training (look-ahead). Use them for upcoming matches only, or as the latest state of a player.
> For past matches use the match-time data in `backend/data/training/fotmob_match_details.jsonl`
> (line-ups, ratings, market value and injury lists *as of each match*).

**Source:** FotMob unofficial API (`settings.fotmob_base_url`, default `https://www.fotmob.com`):
`/api/data/leagues?id=<league>&season=2026/2027`, `/api/data/teams?id=<team>`,
`/api/data/playerData?id=<player>`, and (fallback roster only) `/api/data/matchDetails?matchId=<match>`.
**Collector:** `backend/scripts/data_collection/collect_fotmob_squads_players.py` (fetching, raw cache,
build, coverage). **Parsers:** `backend/scripts/data_collection/fotmob_squads_parse.py` (pure functions,
importable by loaders). **Independent re-fetch check:** `backend/scripts/data_collection/verify_fotmob_squads_players.py`.
**Tests:** `backend/tests/test_collect_fotmob_squads_players.py` (synthetic fixtures only).
**Honesty rule (AGENTS.md 8-14):** values are copied as sent. A value FotMob does not send is `null`
(this includes lists and list lengths: `positions`, `recent_matches_n`, `market_values_n` and the squad counts of a
club without a squad list are `null`, not `[]` / `0`); `0` appears only where FotMob sends `0`.
Three FotMob "unknown" placeholders are decoded to `null`, each with the sent value kept in a `*_raw` field:
the "no rating" marker `recentMatches[*].ratingProps.rating == 0` → `rating: null` (`rating_raw`);
the placeholder birth date `birthDate.utcTime == "0001-01-01T00:00:00.000Z"` → `birth_date: null` (`birth_date_raw`);
the squad-list / line-up `age == 0` (sent for the same players, whose `dateOfBirth` is `null`) → `age: null` (`age_raw`).

## Scope

| FotMob id | Competition | Why |
|---|---|---|
| 47, 87, 55, 54, 53 | Premier League, LaLiga, Serie A, Bundesliga, Ligue 1 | 10 strongest leagues by UEFA association coefficient |
| 57, 61, 40, 71, 122 | Eredivisie, Liga Portugal, Belgian Pro League ("First Division A"), Süper Lig, Czech 1. Liga | ″ |
| 42, 73, 10216 | Champions League, Europa League, Conference League | every club of the 2026/2027 league phase |

Club list = every team id in `table[*].data.table.all` (and nested `data.tables[*]`) **or** in
`fixtures.allMatches[*].home/away` of the 13 league responses for season `2026/2027`, deduplicated.
A European-cup club that appears in that season's fixtures but not in the league-phase table would be kept
with `qualifying_only: true`; there are none: the three cup responses list only the 36 league-phase clubs
(144 / 144 / 108 fixtures, rounds 1–8 / 1–8 / 1–6). Qualifying rounds live under other FotMob league ids
and are not part of this dataset.

## Files (all in `backend/data/players/`, git-ignored except this README)

| File | One row per | Content |
|---|---|---|
| `teams_2026_27.jsonl` | club | id, name, country, competitions (table/fixture membership), coach, roster source, snapshot |
| `squad_members_2026_27.jsonl` | club × listed player | squad-list entry: role, positions, shirt, age, dob, height, nationality, transfer value, injury flag, season numbers as listed |
| `players.jsonl` | player (unique) | profile from playerData: dob, contract, primary team, positions, height, foot, country, shirt, market value, injury information, international duty, main-league season stats, first-season detailed stats, traits, next match |
| `player_recent_matches.jsonl` | player × match | `recentMatches[*]`: date, team, opponent, home/away, league, minutes, goals, assists, cards, rating, bench/played flags, line-up slot |
| `player_market_values.jsonl` | player × valuation | `marketValues.values[*]`: date, value, currency, bounds, source, team |
| `player_career.jsonl` | player × career entry | `careerHistory.careerItems.<section>.teamEntries/seasonEntries[*]`, values exactly as sent |
| `collect_errors.jsonl` | failed attempt | `kind, id, error, detail, attempts, at` (+ `http_status`, `season`); created on the first error — absent after the 2026-10-13 run (no errors) |

Every parsed row carries `snapshot_at` = `fetched_at` of the response it was parsed from
(team rows and squad rows: the team response; player rows: the playerData response).

## Raw cache and manifests (contract for loaders)

| Directory (`backend/data/raw_cache/…`) | File | Manifest `id` |
|---|---|---|
| `fotmob_squads_leagues/` | `<league id>_2026-2027.json.gz` | league id (lines also carry `"season": "2026/2027"`) |
| `fotmob_teams/` | `<team id>.json.gz` | FotMob team id |
| `fotmob_players/` | `<player id>.json.gz` | FotMob player id |
| `fotmob_squads_fallback_matches/` | `<match id>.json.gz` | FotMob match id (fallback roster only) |

* Raw files are the **untouched response bodies**, gzip-compressed, written atomically (temp file in the
  same directory + `os.replace`, retried while a reader holds the target on Windows). A refresh replaces
  the file; the previous body is not kept.
* `_manifest.jsonl`: one line per HTTP response received, appended in arrival order:
  `{"id": <int>, "fetched_at": "<UTC ISO, seconds>", "http_status": <int>, "bytes": <int>}`.
  `bytes` = length of the decoded response body (what is stored, before gzip).
  * A `200` line is appended **only after** the raw file was replaced, so the most recent `200` line of an
    id is the snapshot time of the file on disk.
  * Non-200 responses (404, 429, 5xx, …) get a line but never touch the raw file (an older good file stays).
  * A 200 answer whose JSON does not have the expected shape (league: `details` + `fixtures`/`table`;
    team: `details` + `squad`; player: an `id`; match: `general` + `content`) is **not** stored and gets
    **no** manifest line; it is logged in `collect_errors.jsonl` (`unexpected_shape`).
  * Transport failures (timeouts, connection errors) have no HTTP response: errors file only.
  * Readers must tolerate a partial last line (interrupted run); the collector does.
* The parsed files are always rebuilt from the raw cache (`--from-raw` = the same build, no network), so a
  parser change never needs a re-fetch.

## Field definitions

Paths are relative to the response root. "As sent" = copied without conversion (ids are cast to int).

### `teams_2026_27.jsonl`

| Field | Source / definition |
|---|---|
| `team_id` | FotMob team id (= `teams.provider_id` in the production DB) |
| `name` | teams response `details.name` (league table/fixture name when there is no team response) |
| `group` | `target_league` = the club is in one of the 10 leagues; `european_cup_only` = only in 42/73/10216 |
| `competitions[*]` | per competition: `league_id`, `league_name` (league response `details.name`), `in_table`, `in_fixtures`, `fixture_matches` (count in `fixtures.allMatches`), `qualifying_only`, `league_snapshot_at` |
| `competition_ids` | the `league_id`s above, in TARGET13 order |
| `team_response_available` | a valid teams response is cached |
| `short_name`, `country`, `primary_league_id`, `primary_league_name`, `latest_season` | `details.shortName`, `details.country` (FotMob 3-letter code), `details.primaryLeagueId`, `details.primaryLeagueName`, `details.latestSeason` |
| `coach` | first member of the squad group `coach` (`role.key == "coach"`): `{id, name, ccode, cname, date_of_birth}`; `null` when not listed |
| `coach_count` | members in that group (`null` when `squad_list_sent` is false: unknown, not 0) |
| `squad_list_sent` | `squad.squad` is a list (false = FotMob sends `squad.squad: null`) |
| `squad_player_count` | player rows from the squad list (`null` when `squad_list_sent` is false) |
| `squad_other_members` | members that are neither players nor coach (not fetched); `[]` for every club with a squad list in this snapshot, `null` when `squad_list_sent` is false |
| `roster_source` | `squad`, or for clubs without a squad list the fallback used: `overview.lastLineupStats` / `matchDetails.content.lineup`; `null` = no roster at all |
| `fallback_roster_count` | rows taken from the fallback line-up |
| `response_team_id` | `details.id` (equals `team_id` for every club) |
| `snapshot_at` | `fetched_at` of the teams response |

### `squad_members_2026_27.jsonl`

`m` = `squad.squad[g].members[i]` of the teams response; players = groups `keepers`, `defenders`,
`midfielders`, `attackers` (role keys `keeper_long`, `defender_long`, `midfielder_long`, `attacker_long`).
The `coach` group goes to the teams file.

| Field | Source / definition |
|---|---|
| `team_id`, `team_name` | the club whose squad lists the player |
| `player_id`, `name` | `m.id`, `m.name` |
| `squad_group`, `role_key`, `role_label` | group `title`, `m.role.key`, `m.role.fallback` |
| `position_id` | `m.positionId` — role group code, observed 0 = GK, 1 = DEF, 2 = MID, 3 = FWD (matches the group in every row) |
| `position_ids`, `position_ids_desc` | `m.positionIds` (comma-separated FotMob pitch-slot ids, string), `m.positionIdsDesc` (e.g. `"CB"`, `"CDM,CM"`); `null` when not sent |
| `shirt_number`, `date_of_birth`, `height` | `m.shirtNumber`, `m.dateOfBirth` (`YYYY-MM-DD`), `m.height` (cm) |
| `age`, `age_raw` | `m.age`; FotMob sends `0` when it has no birth date (4 squad rows on 2026-10-13, all with `dateOfBirth: null`) → `age: null`, `age_raw: 0`. Otherwise `age == age_raw`. Fallback rows: the line-up entry's `age`, same rule |
| `ccode`, `cname`, `national_team_id` | `m.ccode`, `m.cname`, `m.nationalTeamId` (nationality) |
| `transfer_value` | `m.transferValue` (EUR, as sent; `null` when FotMob has no value) |
| `injured` | `m.injured` — FotMob sends this key **only when true**; `null` = key absent |
| `injury`, `injury_id`, `injury_expected_return` | `m.injury` as sent (`{id, expectedReturn}` or `null`), and its two fields |
| `rating`, `goals`, `penalties`, `assists`, `ycards`, `rcards` | season numbers as listed on FotMob's squad page. The response does not state their scope. Compared with playerData `mainLeague` (current season) for the 5,501 squad rows whose `mainLeague` is the club's primary league: goals equal in 4,826 / 5,082 comparable rows, assists 4,769 / 4,970, yellow cards 5,067 / 5,501, rating equal in 2,831 and within 0.01 in 1,546 of 4,423 (46 differ more). Read them as "FotMob squad page, roughly the primary-league season so far", not as an exact source of truth |
| `exclude_from_ranking` | `m.excludeFromRanking` |
| `roster_source` | `squad` for squad-list rows; fallback rows: see below |
| `lineup_role`, `lineup_match_id`, `lineup_match_date`, `lineup_entry` | fallback rows only: `starter`/`sub`/`unavailable`, the line-up's match id and kick-off (UTC), and the line-up entry as sent (layout keys removed; includes `marketValue` at that match and `unavailability` for unavailable players). `null` for squad rows |
| `snapshot_at` | `fetched_at` of the teams response (fallback rows from matchDetails: of that response) |

**Fallback roster (clubs FotMob sends no squad list for).** When `squad.squad` is `null`, the roster is taken,
clearly labelled, from (1) `overview.lastLineupStats` of the same teams response (`starters`, `subs`,
`unavailable`), else (2) the club's side of `content.lineup` in a matchDetails response: the collector walks back
through the club's finished matches (`overview.lastMatch.id`, then `overview.overviewFixtures[*]` with
`status.finished`, newest first, at most 6 requests) and uses the first one whose line-up has starters or subs
(FotMob has no line-ups for some domestic leagues; an `unavailable`-only list is not used). Fallback rows have only
`player_id, name, age, shirt_number, ccode, cname`; every squad-only field (`injured`, `transfer_value`, `rating`, …)
is `null` = **unknown**, not "not injured". In this snapshot: Shakhtar Donetsk (9728) → `overview.lastLineupStats`
of match 5909176 (2026-10-09, 25 players); Sabah FK (951893) → matchDetails of UCL match 6106293 (2026-09-10,
22 players; its three later domestic matches have no line-up in FotMob).

### `players.jsonl`

`d` = the playerData response; `info[k]` = the `playerInformation[*]` entry whose stable `translationKey == k`
(never matched by the English title).

| Field | Source / definition |
|---|---|
| `player_id` | requested id; `response_id` = `d.id` (equal for every row) |
| `name`, `gender`, `status`, `is_coach`, `is_captain` | `d.name`, `d.gender`, `d.status`, `d.isCoach`, `d.isCaptain` |
| `birth_date`, `birth_date_raw` | `d.birthDate.utcTime`; FotMob's placeholder `"0001-01-01T00:00:00.000Z"` (unknown birth date: 4 players on 2026-10-13 — 2130409, 2196470, 1814510, 1828112) → `birth_date: null`, `birth_date_raw` keeps the sent value. Otherwise equal |
| `contract_end` | `d.contractEnd.utcTime` (`d.contractEnd` is absent for 2,461 players → `null`) |
| `primary_team_id`, `primary_team_name`, `on_loan` | `d.primaryTeam.teamId`, `.teamName`, `.onLoan` |
| `position_primary_key`, `position_primary_label` | `d.positionDescription.primaryPosition.key` / `.label` (e.g. `centerback`, `striker`, `keeper_long`) |
| `positions[*]` | `d.positionDescription.positions[*]`: `position_id` (`position`, FotMob pitch-slot id as string), `key`/`label` (`strPos`), `short_key`/`short_label` (`strPosShort`), `occurrences` (`occurences`), `is_main` (`isMainPosition`). `null` when FotMob sends no list (551 players: `positions: null` for 549, `positionDescription: null` for 2) |
| `non_primary_positions` | `d.positionDescription.nonPrimaryPositions` as sent |
| `height_cm` | `info["height_sentencecase"].value.numberValue` |
| `preferred_foot` | `info["preferred_foot"].value.key` (`right` / `left` / `both`) |
| `country_code`, `country_name`, `national_team_id` | `info["country_sentencecase"].countryCode`, `.value.fallback`, `.nationalTeamId` |
| `shirt_number`, `age` | `info["shirt"].value.numberValue`, `info["age_sentencecase"].value.numberValue` |
| `market_value`, `market_value_text` | `info["transfer_value"].value.numberValue` (EUR; the text is FotMob's display string, e.g. `€50.2m`) |
| `contract_end_date` | `info["contract_end"].value.dateValue` |
| `player_information_keys` | the `translationKey`s FotMob sent for this player |
| `injury_information` | `d.injuryInformation` exactly as sent (`null` = FotMob lists no injury) |
| `injury_key`, `injury_name`, `injury_expected_return_key`, `injury_expected_return_param`, `injury_expected_return_text`, `injury_last_updated` | `injuryInformation.key`, `.name`, `.expectedReturn.expectedReturnKey`, `.expectedReturn.expectedReturnDateParam`, `.expectedReturn.expectedReturnFallback`, `.lastUpdated.utcTime` |
| `international_duty` | `d.internationalDuty` as sent |
| `main_league` | `{league_id, league_name, season, stats}` from `d.mainLeague`; `stats` = `{localizedTitleId: value}` of `mainLeague.stats[*]` (e.g. `goals`, `assists`, `rating`, `matches_uppercase`, `minutes_played`, `yellow_cards`, `clean_sheet_title`) |
| `first_season_stats` | compact `d.firstSeasonStats`: `top_stat_card` and `stats` = `{localizedTitleId: {value (statValue, string as sent), per90, percentile_rank, percentile_rank_per90, format}}` from `topStatCard.items` and `statsSection.items[*].items`. The response does not say which season/tournament these belong to; `presumed_season` / `presumed_tournament_id` / `presumed_tournament_name` = `statSeasons[0]` and its first tournament (FotMob's default entry). Checked on all players: wherever the presumed entry equals `mainLeague` (5,646 players), `top_stat_card.matches_uppercase` equals the `mainLeague` matches count in 5,309 / 5,309 and, where no matches figure is sent, goals agree in 309 / 309 (28 have no comparable figure). For 745 players the presumed entry is another competition; 427 have no `firstSeasonStats` (`null`) |
| `traits` | `d.traits` as sent (`{key, title, items[{key, title, value}]}`: share relative to players of the same position) |
| `next_match` | `{match_id, home_id, away_id, match_date, league_id, parent_league_id}` from `d.nextMatch` |
| `career_full` | `d.careerHistory.fullCareer` |
| `recent_matches_n`, `market_values_n` | lengths of `d.recentMatches`, `d.marketValues.values`; `null` when FotMob sends no list (`recentMatches: null` for 182 players, `marketValues: null` for 769) — those players have no rows in the child files |
| `squad_team_ids` | clubs (of this dataset) whose roster lists the player |
| `snapshot_at` | `fetched_at` of the playerData response |

### `player_recent_matches.jsonl`

`r` = `d.recentMatches[*]` (FotMob's list of the player's recent matches for all his teams, club and
national team, newest first; up to ~70 entries).

| Field | Source |
|---|---|
| `player_id`, `match_id` | requested player id, `r.id` (FotMob match id = `matches.provider_id`) |
| `match_date` | `r.matchDate.utcTime` |
| `team_id`, `team_name`, `opponent_team_id`, `opponent_team_name`, `is_home_team` | `r.teamId`, `r.teamName`, `r.opponentTeamId`, `r.opponentTeamName`, `r.isHomeTeam` |
| `league_id`, `league_name`, `stage` | `r.leagueId`, `r.leagueName`, `r.stage` |
| `home_score`, `away_score` | `r.homeScore`, `r.awayScore` |
| `minutes_played`, `goals`, `assists`, `yellow_cards`, `red_cards` | `r.minutesPlayed`, `r.goals`, `r.assists`, `r.yellowCards`, `r.redCards` |
| `rating` | `r.ratingProps.rating` parsed to float; **`null` when FotMob sends the integer `0`** (its "no rating" marker: every integer rating seen is 0 — unused substitutes, and matches without rating coverage — while real ratings arrive as strings such as `"7.4"`) |
| `rating_raw` | `r.ratingProps.rating` exactly as sent |
| `is_top_rating`, `player_of_the_match` | `r.ratingProps.isTopRating`, `r.playerOfTheMatch` |
| `on_bench`, `played_in_match`, `lineup_position_id` | `r.onBench`, `r.playedInMatch`, `r.lineupPositionId` (pitch slot; absent for unused subs → `null`) |

### `player_market_values.jsonl`

`v` = `d.marketValues.values[*]` (oldest first): `date`, `value`, `currency`, `lower_bound` (`lowerBound`),
`upper_bound` (`upperBound`), `source`, `team_id`, `team_name`, `is_period_start` (`isPeriodStart`) — as sent
(`teamColor` dropped).

### `player_career.jsonl`

From `d.careerHistory.careerItems.<section>` (`senior`, `national team`, `youth`):
`section`, `entry_type` (`team` = `teamEntries[*]`, `season` = `seasonEntries[*]`), `entry_index` (position in
FotMob's list, most recent first). Team rows: `team_id`, `team`, `team_gender`, `transfer_type`, `start_date`,
`end_date`, `active`, `role`, `appearances`, `goals`, `assists`, `has_uncertain_data`. Season rows:
`season_name`, `team_id`, `team`, `team_gender`, `transfer_type`, `appearances`, `goals`, `assists`,
`rating` (`rating.rating`), `tournament_stats` (list as sent: per competition `leagueId`, `leagueName`,
`appearances`, `goals`, `assists`, `rating`, …). **Counts and ratings are kept exactly as sent — FotMob
sends them as strings** (`"51"`, `"7.38"`). **Team-entry dates are also as sent and come in mixed formats:**
`start_date` is an ISO string in 55,814 rows, an integer epoch in **milliseconds** in 133 (e.g. `1782864000000` =
2026-07-01) and `""` in 85; `end_date` is an ISO string in 46,423, `null` in 9,391, epoch ms in 59 and `""` in 159.
Normalise before comparing dates.

## Re-running, resuming and the periodic refresh

```bash
cd backend
# complete / resume: fetches only what is missing (no raw file or no HTTP-200 manifest line), then rebuilds
venv/Scripts/python.exe scripts/data_collection/collect_fotmob_squads_players.py
# periodic refresh job: re-fetch what is older than N hours
venv/Scripts/python.exe scripts/data_collection/collect_fotmob_squads_players.py --teams-only --refresh-older-than 6   # 13 league lists + 231 squads (~3 min): injury flags, squad changes
venv/Scripts/python.exe scripts/data_collection/collect_fotmob_squads_players.py --refresh-older-than 20             # + every playerData (~55 min at ~2 req/s)
# rebuild the parsed files from the raw cache (no network), coverage tables, verification
venv/Scripts/python.exe scripts/data_collection/collect_fotmob_squads_players.py --from-raw
venv/Scripts/python.exe scripts/data_collection/collect_fotmob_squads_players.py --coverage
venv/Scripts/python.exe scripts/data_collection/verify_fotmob_squads_players.py --offline-all
venv/Scripts/python.exe scripts/data_collection/verify_fotmob_squads_players.py --n 10 --seed 20261013   # 10 live requests
```

* One collecting instance at a time: `backend/data/raw_cache/.fotmob_squads_players.lock` (heartbeat every
  30 s, considered stale after 10 min). `--from-raw` and `--coverage` do not take the lock.
* Politeness: ≤ 2 workers (`--workers` is clamped), ≥ 0.5 s between two requests of a worker (`--delay` is
  clamped), `fotmob_rate.acquire()` before every request (global budget shared by all collectors), HTTP 429 →
  `report_429(Retry-After or 60)` + exponential backoff, 5xx/timeouts → backoff (`--max-retries 4`), the run
  stops after 8 consecutive failed requests, and **HTTP 403 / a captcha / a challenge page / an HTML answer
  stops the whole run at once (exit code 2)** — never worked around.
* Exit codes: 0 = done, 1 = stopped early (consecutive failures / interrupted / `--max-minutes`), 2 = blocked.
* Players that leave every roster stay in the raw cache but drop out of the parsed files at the next build;
  new squad members are fetched by the next run.

## Coverage (generated with `--coverage` after the 2026-10-13 run)

Run: 2026-10-13 18:21–19:24 UTC. League lists and squads 18:21–18:24, playerData 18:21–19:24 (main pass 57.1 min,
6,987 requests, ~2.1 requests/s with 2 workers under the shared limiter; two resume passes, 64 requests; plus
21 requests of a smoke test and 10 of the live verification).
All 7,067 responses in the four manifests are HTTP 200 (13 league lists, 231 squads, 6,819 player profiles,
4 fallback match details): **0 × 429, 0 × 403, 0 challenge pages, 0 timeouts**. Raw cache: teams 12 MB, players 92 MB.
6,819 player files are cached; 6,818 are in the current rosters (the extra one is the single `unavailable` entry of
a Sabah match without line-up, superseded by the walk-back).

#### Teams and players per competition (season 2026/2027)

| FotMob id | Competition | selectedSeason | Table teams | Fixture teams | Clubs (union) | Qualifying-only | Squad lists sent | Roster players | playerData parsed | Missing |
|---|---|---|---|---|---|---|---|---|---|---|
| 47 | Premier League | 2026/2027 | 20 | 20 | 20 | 0 | 20 | 542 | 542 | 0 |
| 87 | LaLiga | 2026/2027 | 20 | 20 | 20 | 0 | 20 | 516 | 516 | 0 |
| 55 | Serie A | 2026/2027 | 20 | 20 | 20 | 0 | 20 | 602 | 602 | 0 |
| 54 | Bundesliga | 2026/2027 | 18 | 18 | 18 | 0 | 18 | 531 | 531 | 0 |
| 53 | Ligue 1 | 2026/2027 | 18 | 18 | 18 | 0 | 18 | 491 | 491 | 0 |
| 57 | Eredivisie | 2026/2027 | 18 | 18 | 18 | 0 | 18 | 549 | 549 | 0 |
| 61 | Liga Portugal | 2026/2027 | 18 | 18 | 18 | 0 | 18 | 550 | 550 | 0 |
| 40 | First Division A | 2026/2027 | 18 | 18 | 18 | 0 | 18 | 571 | 571 | 0 |
| 71 | Super Lig | 2026/2027 | 18 | 18 | 18 | 0 | 18 | 541 | 541 | 0 |
| 122 | 1. Liga | 2026/2027 | 16 | 16 | 16 | 0 | 16 | 506 | 506 | 0 |
| 42 | Champions League | 2026/2027 | 36 | 36 | 36 | 0 | 34 | 1001 | 1001 | 0 |
| 73 | Europa League | 2026/2027 | 36 | 36 | 36 | 0 | 36 | 1091 | 1091 | 0 |
| 10216 | Conference League | 2026/2027 | 36 | 36 | 36 | 0 | 36 | 1052 | 1052 | 0 |

Unique clubs: **231** (184 in the 10 leagues, 47 European-cup-only); team responses: **231**; roster source per club: {'squad': 229, 'overview.lastLineupStats': 1, 'matchDetails.content.lineup': 1}; roster rows: **6818** ({'squad': 6771, 'overview.lastLineupStats': 25, 'matchDetails.content.lineup': 22}); unique roster players: **6818**; playerData parsed: **6818**; missing: **0**. Per-competition counts overlap (a club plays its league and a cup).

#### playerData field coverage (share of parsed players where FotMob sends the value)

| Scope | Players | Birth date | Foot | Height | Market value | Contract end | Country | Position | Injury info (non-null) | Intl duty (non-null) | Main-league stats | Recent matches | MV history | Career | Traits |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 47 Premier League | 542 | 100.0% | 99.8% | 96.9% | 98.9% | 70.8% | 100.0% | 96.9% | 15.5% | 0.0% | 97.0% | 99.6% | 98.9% | 100.0% | 98.3% |
| 87 LaLiga | 516 | 100.0% | 99.2% | 97.9% | 95.0% | 76.9% | 100.0% | 94.8% | 12.6% | 0.0% | 98.3% | 100.0% | 95.0% | 100.0% | 95.3% |
| 55 Serie A | 602 | 100.0% | 96.8% | 87.9% | 93.2% | 69.3% | 100.0% | 87.7% | 13.1% | 0.0% | 91.7% | 99.2% | 93.2% | 100.0% | 87.4% |
| 54 Bundesliga | 531 | 100.0% | 94.4% | 89.6% | 93.6% | 56.3% | 100.0% | 83.8% | 15.1% | 0.0% | 91.0% | 96.6% | 93.6% | 100.0% | 85.7% |
| 53 Ligue 1 | 491 | 100.0% | 95.7% | 78.2% | 88.8% | 62.5% | 100.0% | 85.9% | 10.4% | 0.0% | 93.5% | 99.8% | 88.8% | 100.0% | 84.1% |
| 57 Eredivisie | 549 | 99.8% | 79.2% | 76.5% | 83.8% | 69.6% | 100.0% | 74.7% | 9.5% | 0.0% | 87.1% | 96.9% | 83.8% | 100.0% | 77.8% |
| 61 Liga Portugal | 550 | 99.8% | 93.1% | 80.7% | 82.0% | 65.3% | 100.0% | 82.4% | 4.4% | 0.0% | 92.0% | 97.5% | 82.0% | 100.0% | 76.0% |
| 40 First Division A | 571 | 100.0% | 77.4% | 77.8% | 86.5% | 63.0% | 100.0% | 78.6% | 8.9% | 0.0% | 89.7% | 97.9% | 86.5% | 100.0% | 79.0% |
| 71 Super Lig | 541 | 100.0% | 92.6% | 86.1% | 86.3% | 65.6% | 100.0% | 80.8% | 7.2% | 0.0% | 85.8% | 94.8% | 86.3% | 100.0% | 80.2% |
| 122 1. Liga | 506 | 100.0% | 39.3% | 74.1% | 89.1% | 46.8% | 100.0% | 79.2% | 10.9% | 0.0% | 89.3% | 97.2% | 89.1% | 100.0% | 71.3% |
| 42 Champions League | 1001 | 99.9% | 90.8% | 89.7% | 93.3% | 71.0% | 100.0% | 91.5% | 11.8% | 0.0% | 94.0% | 99.4% | 93.3% | 100.0% | 88.4% |
| 73 Europa League | 1091 | 99.9% | 83.2% | 85.5% | 90.9% | 61.0% | 100.0% | 85.1% | 8.7% | 0.0% | 90.7% | 96.2% | 90.9% | 100.0% | 77.5% |
| 10216 Conference League | 1052 | 100.0% | 70.6% | 76.1% | 85.6% | 62.2% | 100.0% | 80.7% | 7.3% | 0.0% | 82.4% | 96.4% | 85.6% | 100.0% | 65.6% |
| **All (unique)** | 6818 | 99.9% | 83.0% | 82.7% | 88.7% | 63.9% | 100.0% | 83.1% | 9.7% | 0.0% | 89.6% | 97.3% | 88.7% | 100.0% | 78.6% |

Squad-list rows (6771; fallback line-up rows excluded): date of birth 99.9%, height 82.4%, transfer value 88.7%, shirt 96.7%, season rating 66.6%, `injured: true` 662 rows, non-null `injury` 662 rows.

#### Squad injury flag vs playerData injuryInformation (separate FotMob fields, not reconciled)

| Squad lists injury | playerData has injuryInformation | Squad rows |
|---|---|---|
| yes | yes | 661 |
| yes | no | 1 |
| no | no | 6109 |

Disagreements (1 rows; first 40):

- 163604 Karl Darlow (team 10260): squad injured=True injury={"id": "130", "expectedReturn": "Late October 2026"} | playerData injuryInformation=(None, None)

QA live re-check (2026-10-13 19:39 UTC, not written to the dataset): FotMob's Manchester United squad page no longer
flags Darlow (`injured` absent, `injury: null`), so the two FotMob fields now agree; the disagreement was a transient
source state at snapshot time. The dataset keeps the snapshot as fetched.

#### Squad members without a parsed playerData (0)

Recent form depth: 5,809 of 6,818 players (85.2 %) have ≥ 5 matches with `played_in_match: true` in
`player_recent_matches.jsonl`; 509 have none (youngsters / long-term injured / new signings). Recent-match dates
2025-10-12 → 2026-10-13T16:45Z; 0 rows are dated after their `snapshot_at`. 222,615 rows: 144,875 played and rated,
28,055 played without a rating (`rating_raw: 0`, competitions without FotMob ratings, e.g. friendlies / lower cups),
49,647 not played and unrated (`rating_raw: 0`), and 38 rows `played_in_match: false` that still carry a rating (as sent).

## Verification (2026-10-13)

| Check | Result |
|---|---|
| Clubs per league vs table size | every competition: table teams = fixture teams = clubs in the dataset (20/20/20/18/18/18/18/18/18/16 and 36/36/36); 0 qualifying-only clubs |
| Squad members vs playerData | 6,818 unique roster players, 6,818 parsed playerData, **0 missing**; 0 players listed by two clubs; `response_id == player_id` for all |
| Offline: independent extractor on every raw file vs parsed rows (`verify_fotmob_squads_players.py --offline-all`) | 6,818 players × 20 fields + 222,615 recent-match rows × 7 values: **0 mismatches** |
| Live re-fetch of 10 random players (seed 20261013, urllib instead of httpx, own extractor) | 20 fields × 10 players + 374 recent-match rows: **0 mismatches**, 0 source changes (players 1478295, 1249185, 785411, 1414859, 1669621, 1049799, 1280020, 540415, 1187691, 1512617) |
| Resume | a third run fetched 0 leagues / 0 squads / 0 players (0 requests) |
| `--from-raw` | rebuilding from the raw cache reproduces all six parsed files byte-identically (sha256 before/after); the build at the end of every run is the same code path. After the QA parser fix (below) a `--from-raw` rebuild changed exactly `players.jsonl`, `squad_members_2026_27.jsonl` and `teams_2026_27.jsonl`; the three child files stayed byte-identical |
| Unit tests | `tests/test_collect_fotmob_squads_players.py`: 25 passed after the QA fix (synthetic fixtures only) |
| Independent QA (separate agent, own code, 2026-10-13 19:30–19:50 UTC) | Every row of all six files re-extracted from the raw gzip responses and compared field by field (teams, all 22 squad fields of 6,771 squad rows, 47 fallback rows against `lastLineupStats` / matchDetails, ~40 player fields, all fields of 222,615 recent-match / 344,648 market-value / 151,803 career rows): **0 mismatches**. Manifests: 7,067 lines, all 200, one per raw file, `bytes` = decoded body length for every file, no temp files. 0 duplicate keys; `snapshot_at` on every row and equal to the latest 200 manifest line. Live spot-check of 13 requests through the shared limiter (UCL 2026/27 fixtures, 3 squads, 8 players): only change = the Darlow flag above. Found and fixed: zero / empty-list defaults where FotMob sends `null` (`positions` 551, `recent_matches_n` 182, `market_values_n` 769, squad counts of the 2 no-squad clubs) and the undocumented birth-date / age placeholders (4 players) |
| Squad injury flag vs playerData `injuryInformation` | separate FotMob fields, reported, not reconciled: 661 both injured, 6,109 both not, **1 disagreement** — Karl Darlow (163604, Manchester United 10260): squad `injured: true`, `injury {id 130, "Late October 2026"}`, playerData `injuryInformation: null` |

## Known gaps and caveats

1. **Snapshot, not history.** Everything here describes 2026-10-13 18:21–19:24 UTC. The snapshot overlaps UCL
   matchday 2: the two 16:45 UTC matches (6106414 Lens–Sporting CP, 6106424 Sabah FK–Slavia Prague) appear in the
   recent lists of 85 players, all fetched at or after 18:41:56 UTC (players of those clubs fetched earlier do not
   have them); the 19:00 UTC matches were not finished for any snapshot (they appear only as `next_match`).
   Refresh before using the injury / form layer for a later match.
2. **Two clubs without a FotMob squad list** (both Champions League): Shakhtar Donetsk 9728 and Sabah FK 951893 →
   labelled fallback rosters (see above); no coach, no squad-page fields (`injured`, `transfer_value`, season numbers)
   for them. Their players' playerData is complete.
3. **Optional playerData fields are often not sent** (`null`, never imputed): preferred foot 83.0 % present
   (Czech 1. Liga 39.3 %), height 82.7 %, market value 88.7 %, contract end 63.9 %, primary position 83.1 %,
   main-league stats 89.6 %, traits 78.6 %. Squad lists: height 82.4 %, transfer value 88.7 %, season rating 66.6 %.
4. **`internationalDuty` is `null` for all 6,818 players** in this snapshot (FotMob sends the key with `null`; no
   international window on 2026-10-13). Its non-null shape is therefore not documented yet.
5. **Ratings:** FotMob's integer `0` in `recentMatches[*].ratingProps.rating` = no rating → `rating: null`
   (`rating_raw` keeps the 0). Squad-list and `mainLeague` ratings never use 0.
6. **Primary team vs listing club:** 127 players have `primary_team_id` different from the club whose squad lists
   them — mostly the club's U21 side (e.g. Manchester City U21 for players in Manchester City's squad); 7 have
   `on_loan: true`.
7. **`first_season_stats` entry is presumed** (see the field notes): 745 players' presumed entry is not their
   `main_league`; use `main_league` for "current season, main league".
8. **Recent-match lists** mix club and national-team matches (all teams of the player) and include matches without
   FotMob rating coverage; filter by `team_id` / `league_id` as needed. Length varies (1–70 per player when sent;
   `recentMatches: null` for 182 players → `recent_matches_n: null`, no rows).
9. **Squad season numbers** (`squad_members.rating/goals/...`) are FotMob squad-page values whose scope is not stated
   (see the field note) — prefer `players.main_league.stats`.
10. **Windows file locking:** 12 player items of the main pass failed with `PermissionError(13)` ("access denied").
    The ones inspected left no temp file and no manifest line, which points at the shared limiter's state-file
    `os.replace` (`fotmob_rate.acquire()` runs before the request); the exact location of each was not logged by that
    run. All 12 were fetched by the resume pass. The collector now retries an `OSError` from the limiter before any
    request is sent (`limiter_retries` in the log) and records any unexpected error with file:line in
    `collect_errors.jsonl`.
11. **Unknown birth dates are placeholders at the source:** FotMob sends `birthDate.utcTime = 0001-01-01` (and on
    the squad page `dateOfBirth: null`, `age: 0`) for 4 players (2130409 Sebas Wermenbol, 2196470 Mamadu Balde,
    1814510 Zois Karagyris, 1828112 Amit Ohana). They are `null` in `birth_date` / `age`; the sent values stay in
    `birth_date_raw` / `age_raw`. Never compute an age from the `*_raw` fields.
12. **`recentMatches` vs the production DB** (read-only cross-check of 222,099 rows whose match is in `matches`):
    kick-off differs in 6 rows, the score in 43 rows of 6 matches, home/away in 2 rows. These are FotMob source
    differences between endpoints (e.g. the 2026-01-18 Africa Cup of Nations final 5073478: `recentMatches` 0-3, DB
    1-0; two UEFA Youth League matches 4953911 / 4953912 whose dates, sides and scores are swapped relative to the DB),
    kept as sent. Use `matches` / matchDetails as the source of truth for results.
