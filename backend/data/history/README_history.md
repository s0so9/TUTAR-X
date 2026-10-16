# Results history before the production DB (2021-07-01 .. 2025-06-30) + one training results table

Built 2026-10-13 for the "train the system properly" sprint: walk-forward team ratings need about one
year of results before every training match, and training covers 2022/23, 2023/24 and 2024/25, so this
dataset adds FotMob results from 2021-07 up to the production DB start (2025-07-01).

**Source:** FotMob unofficial API, `GET https://www.fotmob.com/api/data/leagues?id=<league>&season=<season>`,
field `fixtures.allMatches` (one request per competition-season).
**Collector:** `backend/scripts/data_collection/collect_fotmob_history_results.py`.
**Union builder:** `backend/scripts/data_collection/build_all_results.py` (no network).
**Tests:** `backend/tests/test_collect_fotmob_history_results.py` (synthetic fixtures only).

**Honesty rule (AGENTS.md 8-14):** nothing is invented or imputed. A score exists only when FotMob marks the
match finished (FINISHED or AWARDED); everything else is NULL. xG is NULL for history rows (the
history-details track supplies it later). Unknown `awarded` / `season` values are NULL, never 0 or a guess.

## Files

| File | Content |
|---|---|
| `history_results.db` | SQLite: `competitions`, `competition_selection`, `seasons`, `teams`, `matches` (kickoff < 2025-07-01), `matches_after_cutoff` (boundary-season matches, for checks only), `duplicate_match_ids`, `meta` |
| `all_results.db` | SQLite: `results` (history UNION production, FotMob ids), `conflicts` (boundary checks), `meta` |
| `competition_selection.csv` | decision + reason for all 500 production-DB competitions (+ FotMob name/country when fetched) |
| `fetch_log.jsonl` | one line per HTTP request (endpoint, params, status, bytes, elapsed) and per event (discovery fallback, stop, ...) |
| `collect_run1.log` .. `collect_run3.log`, `build_all_results.log`, `spot_check.log`, `spot_check.json` | run logs of 2026-10-13 |
| `raw_probe/` | gzip bodies of the 21 discovery answers where FotMob returned another season than requested (calendar-year leagues), kept for traceability |
| `raw_spotcheck/` | gzip `matchDetails` bodies of the 10 spot-checked matches |
| `../raw_cache/fotmob_leagues/<league>_<season>.json.gz` ("/" in the season replaced by "-", e.g. `47_2021-2022.json.gz`) | untouched league responses (shared with other collectors; an existing file is reused, never re-fetched) |

## Re-running

```bash
cd backend
venv/Scripts/python.exe scripts/data_collection/collect_fotmob_history_results.py --dry-run    # plan from the cache, no network
venv/Scripts/python.exe scripts/data_collection/collect_fotmob_history_results.py              # fetch what is missing + rebuild
venv/Scripts/python.exe scripts/data_collection/collect_fotmob_history_results.py --from-raw   # rebuild history_results.db, no network
venv/Scripts/python.exe scripts/data_collection/collect_fotmob_history_results.py --coverage   # coverage tables (markdown)
venv/Scripts/python.exe scripts/data_collection/collect_fotmob_history_results.py --spot-check 10
venv/Scripts/python.exe scripts/data_collection/build_all_results.py                           # rebuild all_results.db (idempotent)
```

Politeness: one worker, >= 0.6 s between this collector's requests, the shared limiter
`fotmob_rate.acquire()` before every request, `report_429(Retry-After or 60)` on HTTP 429, stop on 403 /
HTML / captcha / challenge pages, `--max-requests` cap (default 1500). Collection is resumable: every
competition-season whose raw file exists is reused, and both databases are rebuilt from the raw cache
(temp file + `os.replace`). `build_all_results.py` reads the production DB read-only and can be re-run
whenever it grows. The collector's `--include <ids>` force-includes extra competitions.

Requests made on 2026-10-13 (18:23-18:38 UTC), as logged in `fetch_log.jsonl`: 577 league requests + 10
matchDetails (spot check) by the collector; all HTTP 200, no 429, no 403. Manual probe requests made during
setup (before 18:23) are not logged: the collector agent's final report counts 10 of them (597 requests in
total, the figure in docs/PROGRESS.md), while an earlier version of this README said 5; neither figure can be
checked from the logs. 21 of the league requests were season-discovery answers for calendar-year competitions
(see below). 6 league requests (1 discovery + 5 seasons) went to The Atlantic Cup 9514 before the name rule
excluded it; its 5 season files stay unused in the raw cache. 39 of the 590 season files used here (TARGET13
2022/23-2024/25, written 18:09-18:17 UTC) were already cached and were reused, not fetched again.

## Scope and competition selection

1. **TARGET13** (13): Premier League 47, LaLiga 87, Serie A 55, Bundesliga 54, Ligue 1 53, Eredivisie 57,
   Liga Portugal 61, Belgian Pro League 40, Super Lig 71, Czech 1. Liga 122, Champions League 42,
   Europa League 73, Conference League 10216.
2. **Second tiers of the 10 countries** (10, always included; ids found in the production DB by name,
   country verified against FotMob `details.country`): Championship 48 ENG, LaLiga2 140 ESP, Serie B 86 ITA,
   2. Bundesliga 146 GER, Ligue 2 110 FRA, Eerste Divisie 111 NED, Liga Portugal 2 185 POR, Challenger Pro
   League 264 BEL (FotMob still calls it "First Division B"), 1. Lig 165 TUR, FNL 253 CZE. (Production-DB
   names are FotMob stage names such as "Championship Playoff"; Serie B 8814 in the DB is Brazil's.)
3. **Context** (92): every other production-DB competition in which teams that appear in TARGET13 matches
   (production DB FINISHED TARGET13 matches + TARGET13 history of step 1: 330 history teams) played
   **>= 3 FINISHED production-DB matches** (= at least 3 matches with a TARGET13-connected team on either
   side), unless a name rule excludes it: club friendlies (incl. "The Atlantic Cup", a pre-season friendly
   tournament), youth/U-xx, women's, reserve/B-team leagues (Premier League 2, MLS Next Pro), futsal/beach,
   exhibitions (Baller League, charity/legends/all-star games). The rule picks domestic leagues of
   European-cup clubs, domestic cups, third tiers of relegated clubs (League One, Serie C, Liga 3 POR),
   UEFA qualifiers (10611/10613/10615), super cups with >= 3 matches (Spain 139, Italy 222, Turkey 166),
   relegation play-off competitions with >= 3 matches (58, 9666, 10025), the FIFA Club World Cup (78).
   Each competition's reason (match counts) is in `competitions.reason_included` and
   `competition_selection.csv`.

Excluded: 385 of 500 production-DB competitions: 275 with no TARGET13-connected match, 85 by name rule
(57 women's, 13 youth, 7 exhibition, 5 friendlies incl. Club Friendlies 489 with 989 connected matches and
The Atlantic Cup 9514, 3 reserve) and **25 with only 1-2 connected matches** (the >= 3 rule): UEFA Super Cup
74, Community Shield 247 and 16 other super cups with 1-2 production matches (188, 192, 195, 200, 207,
237, 266, 272, 521, 8816, 8924, 9069, 9431, 9504, 9862, 10009), FIFA Intercontinental Cup 10703, Cup 9528
and the relegation play-offs Belgian Pro League Qualification 41, Bundesliga Qualification 9081,
2. Bundesliga Qualification 9734, Liga Portugal Qualification 10215, Liga Portugal 2 Qualification 9668.
These add roughly 1-2 matches per season each; force-include them with the collector's `--include` option
if wanted (about 5 requests each).

## Seasons fetched

* **core**: every season of `allAvailableSeasons` overlapping 2021-07-01 .. 2025-06-30 by name:
  `2021/2022` .. `2024/2025` (split-year) and `2021` .. `2025` (calendar-year). TARGET13: exactly
  2021/2022 .. 2024/2025.
* **boundary**: the split-year season `2025/2026`, fetched for every split-year competition because some
  of them start before 2025-07-01. It contributed 37 pre-cutoff matches (Moldova National Division 8 in
  June 2025, Svenska Cupen 29 in May-June 2025); its later matches go to `matches_after_cutoff` and are only
  used for the production cross-checks below.
* **prewindow**: when a competition's earliest core-season kickoff is later than 2021-09-30, the season
  before its earliest core season is fetched too, and only its matches with kickoff in [2021-07-01, cutoff)
  are kept. Reason: FotMob labels super cups with shifted seasons (the Supercopa de Espana played in
  January 2023 is season "2021/2022"; the January 2022 edition is "2020/2021"). 20 such seasons were
  fetched; they added exactly the January 2022 super cups (Spain 3, Italy Inter v Juventus 1, Turkey
  Besiktas v Antalyaspor 1); the other 17 (cups and play-off competitions that start late in the season)
  had no match after 2021-07-01, which confirms their earlier seasons ended before the window.
* **Season discovery:** a season name FotMob does not know silently returns the latest season, so every
  answer is checked against `details.selectedSeason` + `details.id` and never cached under a wrong name.
  The first request per competition asks for `2024/2025`; for the 21 calendar-year competitions FotMob
  answered with the current season, whose `allAvailableSeasons` then gave the real names (body kept in
  `raw_probe/`).
* **Kickoff filter:** `matches` keeps every match of a core/boundary season with kickoff < 2025-07-01T00:00:00Z
  (prewindow: also >= 2021-07-01). Calendar-year 2021 seasons and the June 2021 UCL qualifiers therefore
  add 1,049 matches before 2021-07-01 (earliest 2021-02-06); filter on `scheduled_at` if you need the
  exact window.

## What `fixtures.allMatches` contains (checked)

* **All stages of a league are listed under the parent id**, with no stage id per match. Round numbers
  restart in play-off stages, so `round` is NOT unique within a season. Stage sub-league ids exist only in
  the composite `table` (e.g. 891505 "Belgian Pro League Playoff Championship Group").
  * Belgian Pro League 40: 2021/22 and 2022/23 = 306 regular + 24 play-off matches (Champions' and Europe
    play-off, 4 teams each, numbered as rounds 1-6 again). 2023/24 = 240 + 72 play-off matches (Champions'
    30, Europe 30, relegation 12) numbered 31-40 + the Conference League play-off final; 2024/25 has the same
    73 extra matches but numbers the play-off rounds 1-10 again.
  * Czech 1. Liga 122 (16 teams from 2021/22): 240 regular + championship and relegation groups (15 + 15,
    rounds 1-5 again) + the European play-off (`1/2`, `final`); 2023/24 has one more `final` match. The
    relegation play-off against FNL clubs is a separate competition (10025, included).
  * Super Lig 71 2022/23: 342 fixtures of 19 teams; 29 are awarded results 3-0/0-3, all involving Hatayspor or
    Gaziantep FK, which withdrew after the February 2023 earthquake. Awarded matches come as
    `finished: true, awarded: true, reason AW` with the forfeit score in `scoreStr`.
  * Eredivisie 57 includes its European play-offs; Serie A 55 2022/23 includes the relegation tie-breaker.
  * Relegation/promotion play-offs between divisions are separate FotMob competitions
    ("... Qualification": 41, 58, 9081, 9666, 9668, 9734, 10025, 10215).
* **UEFA:** 42/73/10216 hold the group/league phase, the knock-out round play-offs and the knock-out rounds;
  qualifying rounds are 10611/10613/10615 (context). The UCL qualification has its June preliminary round
  for 2021/22-2023/24 only (see gaps).
* **Penalty shoot-outs:** `scoreStr` is the score after 90/120 minutes (reason `Pen`/`AET`); shoot-out
  goals are not included.
* The `playoff` bracket of knock-out competitions was compared with `allMatches`: 0 bracket matches were
  missing from `allMatches` over all 590 season files.

## Status and score rules

`status` is derived from FotMob's flags: `cancelled` -> CANCELLED (or POSTPONED / ABANDONED by
`reason`), `awarded` -> AWARDED, reason `Ab`/`aborted` -> ABANDONED, `finished` -> FINISHED, else
POSTPONED / STARTED_NOT_FINISHED / NOT_PLAYED. Flag combinations seen in all 590 season files (every
match in them: kept, after-cutoff and the 762 pre-window matches of prewindow seasons that are not kept):

| status | reason | finished | started | cancelled | awarded | matches |
|---|---|---|---|---|---|---|
| FINISHED | FT | 1 | 1 | 0 | 0 | 99,042 |
| FINISHED | Pen | 1 | 1 | 0 | 0 | 1,930 |
| FINISHED | AET | 1 | 1 | 0 | 0 | 1,113 |
| CANCELLED | Can | 0 | 0 | 1 | NULL | 737 |
| AWARDED | AW | 1 | 1 | 0 | 1 | 266 |
| ABANDONED | Ab | **1** | 1 | **1** | NULL | 37 |
| NOT_PLAYED | NULL | 0 | 0 | 0 | NULL | 4 (future super-cup fixtures, after the cutoff) |

**Abandoned matches** come as `finished: true` AND `cancelled: true` with the score at the moment of
abandonment in `scoreStr`; that is not a result, so their scores are NULL (`score_str` keeps the raw
text). A replay is a separate match id: 27 of the 29 abandoned history matches have a later meeting of the
same home and away teams in the same competition-season. 2 have none, so their outcome is not in the
training table: Troyes v Valenciennes (Ligue 2, 2024-05-03, abandoned at 1-1) and Salernitana v Sampdoria
(Serie B relegation play-out, 2025-06-22, abandoned at 0-2). A live `matchDetails` check on 2026-10-13 still
shows both as abandoned.

**Awarded scores** are the decision's score as FotMob sends it in `scoreStr` (history, 228 matches): 0-3
106, 3-0 96, **0-0 16**, 5-0 4, 0-5 2, 0-1 2, 2-0 1, 0-2 1. An awarded 0-0 is not a forfeit win but a double
forfeit or a walkover without a winner. Example: Paris FC v Lyon (Coupe de France, 2021-12-17) was awarded 0-0
after both clubs were thrown out. The next round's Nice v "Paris FC/Lyon" (2022-01-02) is a walkover against
the placeholder team 1323733, also awarded 0-0. **Scores are only set for FINISHED and AWARDED.** No
POSTPONED status occurred: FotMob moves postponed matches to their new date. None of the 630 CANCELLED
history matches has a score. Most belong to excluded or withdrawn clubs and interrupted seasons (Ukraine
2021/22 after the invasion, Catania in Serie C 2021/22, Sochaux and Bordeaux in Ligue 2 2023/24 and
2024/25, Taranto and Turris in Serie C 2024/25, Deinze in the Challenger Pro League 2024/25, Leon at the
2025 Club World Cup); for some smaller blocks the data shows no reason (e.g. 16 Czech Cup 2023/24 ties all
dated 2023-09-27, 20 Cymru Premier 2021/22 fixtures).

## `history_results.db`

* `matches` (83,214 rows; PK `provider_id`): `provider_id` (FotMob match id), `competition_provider_id`
  (requested parent league id), `season` (FotMob season name), `round` / `round_name` (as sent, not unique per
  season), `scheduled_at` (`status.utcTime`, ISO UTC `YYYY-MM-DDTHH:MM:SSZ`), `home_team_provider_id` /
  `away_team_provider_id` (`home.id` / `away.id`), `home_score` / `away_score` (parsed from
  `status.scoreStr` for FINISHED/AWARDED only, else NULL), `status`, `status_reason` / `status_reason_key`
  (`status.reason.short` / `.longKey`), `finished` / `started` / `cancelled` / `awarded` (FotMob flags,
  1/0, NULL when not sent), `score_str` (raw), `source` = `fotmob_league_fixtures` (or
  `fotmob_league_playoff_bracket` for a bracket-only match: none exist).
* `matches_after_cutoff` (19,153 rows): same columns, boundary-season matches with kickoff >= 2025-07-01.
* `seasons` (590 rows): `season_role` (core / boundary / prewindow), `fetch_status`, `n_matches` (rows in
  `matches`), `n_source` (len `allMatches`), `n_after_cutoff`, `n_before_window` (prewindow matches
  dropped), `n_finished`, `n_awarded`, `n_abandoned`, `n_cancelled`, `n_postponed`, `n_other_status`,
  `n_bracket_only`, `n_duplicate_ids`, `n_no_kickoff`, `n_score_unparsed`, `first_kickoff`, `last_kickoff`,
  `fetched_at` (raw file mtime, UTC), `raw_file`.
* `competitions` (115 rows): `provider_id`, `name` / `country` / `fotmob_type` (FotMob `details`),
  `reason_included`, `selection_group` (TARGET13 / second_tier / context / forced), `db_name`,
  `n_db_finished`, `n_db_connected`, `n_connected_teams`, `all_available_seasons` (JSON), `note`.
* `competition_selection` (500 rows): decision and reason for every production-DB competition.
* `teams` (4,436 rows): `provider_id`, `name` (latest name seen), `n_matches`, `first_kickoff`, `last_kickoff`.
* `duplicate_match_ids`: a match id met in two competition-seasons (first kept): **0 rows**.
* Totals: 82,327 FINISHED, 228 AWARDED, 630 CANCELLED, 29 ABANDONED; by kickoff year 2021 12,346 /
  2022 19,889 / 2023 20,866 / 2024 20,583 / 2025 9,530. 0 unparsed scores, 0 matches without kickoff or team.

## `all_results.db` -> table `results` (the training table)

`results` = history (`history_results.matches`, kickoff < 2025-07-01, FINISHED or AWARDED with a score:
82,555 rows) UNION production-DB FINISHED matches with `scheduled_at >= 2025-07-01` (86,024 rows) =
**168,579 rows, 168,579 distinct match ids**, 8,430 teams.

| Column | Definition |
|---|---|
| `match_provider_id` | FotMob match id (PK) |
| `competition_provider_id` | FotMob league id (production: `competitions.provider_id`) |
| `competition_name` | FotMob `details.name` when the competition is in the history selection, else the production-DB name (often a stage name) |
| `season` | FotMob season name: always for history; for production only when the match is in a fetched boundary-season file (18,584 of 86,024), else NULL |
| `scheduled_at` | ISO UTC. Production `scheduled_at` is naive UTC: it equals FotMob's `utcTime` for all 18,584 production matches found in the fixture files |
| `home_team_provider_id`, `away_team_provider_id` | FotMob team ids (production uuids mapped through `teams.provider_id`) |
| `home_score`, `away_score` | history: FotMob `scoreStr`; production: DB values |
| `home_xg`, `away_xg` | production DB values (6,444 rows); NULL for history |
| `awarded` | history: FotMob flag (228 = 1). Production: FotMob fixture flag when the match is in a boundary-season file, else the match-details dataset flag (1,227), else NULL (66,232 unknown); 4 production rows are 1 |
| `source` | `history` / `production` |
| `competition_in_history_scope` | 1 when the competition is one of the 115 history competitions (production: 25,338 of 86,024 rows), so a training set can keep one scope across the cutoff |

Training notes: drop `awarded = 1` rows (forfeit scores, not football) unless you want them. Filter with
`awarded IS NOT 1` (or `COALESCE(awarded, 0) = 0`), **not** `awarded = 0`: `awarded` is NULL (unknown) for
66,232 production rows, and `awarded = 0` would silently drop all of them. That includes 5,546 of the 25,338
in-scope production rows, mostly 2026 matches outside the fetched boundary files; TARGET13 production rows
all have a flag. Production rows outside the history scope (60,686, e.g. youth, women's,
friendlies and lower leagues) have no history before 2025-07-01. The 19 production rows that FotMob now
shows as cancelled (`conflicts.kind = 'production_vs_fixture_status'`) keep their production scores in
`results`; exclude them through `conflicts` if annulled results should not count.

### Boundary checks (`conflicts` table)

* `same_id_both_sides` (one id in history and production): **0**. `same_fixture_different_ids` (same teams
  within 48 h across the cutoff): **0**. History duplicate ids: **0**.
* `production_vs_fixture_*`: production rows compared with FotMob's own league fixtures of the boundary
  seasons (18,584 matched): teams, score, status and kickoff.
  * `production_vs_fixture_status` (19): production FINISHED, FotMob CANCELLED: Rimini's 15 Serie C 2025/26
    matches (results annulled), Championship play-off Middlesbrough v Southampton 5427701/5427703 (also in
    README_fotmob_details.md), Egersund v Lyn (Norwegian Cup), Stranraer v Queen's Park (Scottish Cup).
  * `production_vs_fixture_score` (4): results awarded after the match; production keeps the on-pitch score,
    FotMob shows the award (Okzhetpes v Zhetysu 1-2 vs 3-0, Imisli v Sumqayit 1-0 vs 0-3, Sakaryaspor v
    Sivasspor 0-0 vs 0-3, Luton v Swindon EFL Trophy 1-2 vs 3-0). These rows have `awarded = 1` with the
    production score: drop them with the other awarded rows.
  * `production_vs_fixture_teams` (4): Reggiana appears as team 959006 in its first 5 production matches of
    2025/26 and as 6500 everywhere else (FotMob's fixtures, the rest of production, all history). Not
    remapped here; map 959006 -> 6500 in training if you merge them.
  * `production_vs_fixture_kickoff`: 0.
* `invalid_team_id` (1): production match 1000004956 (KNVB Beker Women) has away team provider id `-1`
  (HERA United); skipped. (Since the QA fix of 2026-10-13, a production match whose team uuid has no `teams`
  row is also reported here; before, the inner join dropped it silently. There are none today.)
* **Reverse check (QA, 2026-10-13; not stored in `conflicts`):** 478 of the 19,043 FINISHED/AWARDED fixtures
  with kickoff >= 2025-07-01 in the fetched files are **not in the production DB** (they are dated
  2025-07-13..2026-05-17), so they are in neither side of `results`. Most are the first rounds of cups:
  Coupe de France rounds 6-8 (298), DBU Pokalen round 1 (46), Puchar Polski 1/64 + 1/32 (38), Scottish Cup
  round 1 (30), Swiss Cup 1/32 (20), Israel Cup 1/64 (16), NIR League Cup 1/32 (6). The Challenger Pro League
  (264) is missing 11 league matches. 12 of the 16 AWARDED fixtures after the cutoff are among the 478, for
  example Slavia v Sparta Prague (2026-05-09) and Hapoel v Maccabi Tel Aviv (2025-10-19). One finished Ligue 1
  match is also missing: Nantes v Toulouse, 2026-05-17.
* **Duplicates inside production (outside the history scope):** 6 Premier League 2 play-off fixtures are in
  the production DB twice, as competition 10176 (ids 5403662-5403667) and 9084 (ids 1000011001-1000011006),
  so both copies are in `results`. Club friendlies with two matches between the same clubs on one day are
  real, not duplicates. No in-scope fixture appears twice.

## Coverage

### TARGET13 per competition-season (core seasons)

"Known size" is outside knowledge: the double round robin of the regular season for leagues (play-offs
come on top) and the full format for UEFA competitions. Every deviation is explained in the last column.
The boundary seasons 2025/2026 of TARGET13 contributed 0 pre-cutoff matches.

| Competition | Season | allMatches | Kept | Finished | Awarded | Abandoned | Cancelled | Known size (basis) | Deviation | Explanation |
|---|---|---|---|---|---|---|---|---|---|---|
| 47 Premier League | 2021/2022 | 380 | 380 | 380 | 0 | 0 | 0 | 380 (20 teams round robin) | +0 | - |
| 47 Premier League | 2022/2023 | 380 | 380 | 380 | 0 | 0 | 0 | 380 (20 teams round robin) | +0 | - |
| 47 Premier League | 2023/2024 | 381 | 381 | 380 | 0 | 1 | 0 | 380 (20 teams round robin) | +1 | Bournemouth v Luton 2023-12-16 abandoned at 1-1 (ABANDONED, no score); replay 2024-03-13 (4-3) is a separate id |
| 47 Premier League | 2024/2025 | 380 | 380 | 380 | 0 | 0 | 0 | 380 (20 teams round robin) | +0 | - |
| 87 LaLiga | 2021/2022 | 380 | 380 | 380 | 0 | 0 | 0 | 380 (20 teams round robin) | +0 | - |
| 87 LaLiga | 2022/2023 | 380 | 380 | 380 | 0 | 0 | 0 | 380 (20 teams round robin) | +0 | - |
| 87 LaLiga | 2023/2024 | 380 | 380 | 380 | 0 | 0 | 0 | 380 (20 teams round robin) | +0 | - |
| 87 LaLiga | 2024/2025 | 380 | 380 | 380 | 0 | 0 | 0 | 380 (20 teams round robin) | +0 | - |
| 55 Serie A | 2021/2022 | 380 | 380 | 380 | 0 | 0 | 0 | 380 (20 teams round robin) | +0 | - |
| 55 Serie A | 2022/2023 | 381 | 381 | 381 | 0 | 0 | 0 | 380 (20 teams round robin) | +1 | relegation tie-breaker Spezia v Hellas Verona 1-3 (2023-06-11, round `final`) |
| 55 Serie A | 2023/2024 | 380 | 380 | 380 | 0 | 0 | 0 | 380 (20 teams round robin) | +0 | - |
| 55 Serie A | 2024/2025 | 380 | 380 | 380 | 0 | 0 | 0 | 380 (20 teams round robin) | +0 | - |
| 54 Bundesliga | 2021/2022 | 306 | 306 | 306 | 0 | 0 | 0 | 306 (18 teams round robin) | +0 | - |
| 54 Bundesliga | 2022/2023 | 306 | 306 | 306 | 0 | 0 | 0 | 306 (18 teams round robin) | +0 | - |
| 54 Bundesliga | 2023/2024 | 306 | 306 | 306 | 0 | 0 | 0 | 306 (18 teams round robin) | +0 | - |
| 54 Bundesliga | 2024/2025 | 306 | 306 | 305 | 1 | 0 | 0 | 306 (18 teams round robin) | +0 | 0; 1 awarded: Union Berlin v Bochum 0-2 (2024-12-14) |
| 53 Ligue 1 | 2021/2022 | 382 | 382 | 380 | 0 | 2 | 0 | 380 (20 teams round robin) | +2 | 2 abandoned: Nice v Marseille 2021-08-22 (at 1-0, replay 2021-10-27 1-1) and Lyon v Marseille 2021-11-21 (at 0-0, replay 2022-02-01 2-1) |
| 53 Ligue 1 | 2022/2023 | 380 | 380 | 380 | 0 | 0 | 0 | 380 (20 teams round robin) | +0 | - |
| 53 Ligue 1 | 2023/2024 | 307 | 307 | 306 | 0 | 1 | 0 | 306 (18 teams round robin) | +1 | Montpellier v Clermont 2023-10-08 abandoned at 4-2; replay 2023-11-29 (1-1) |
| 53 Ligue 1 | 2024/2025 | 306 | 306 | 306 | 0 | 0 | 0 | 306 (18 teams round robin) | +0 | - |
| 57 Eredivisie | 2021/2022 | 312 | 312 | 312 | 0 | 0 | 0 | 306 (18 teams round robin) | +6 | European play-offs: two-legged semi-finals (4) + two-legged final (2) |
| 57 Eredivisie | 2022/2023 | 312 | 312 | 312 | 0 | 0 | 0 | 306 (18 teams round robin) | +6 | European play-offs: two-legged semi-finals (4) + two-legged final (2) |
| 57 Eredivisie | 2023/2024 | 309 | 309 | 309 | 0 | 0 | 0 | 306 (18 teams round robin) | +3 | European play-offs: single-leg semi-finals (2) + final (1) |
| 57 Eredivisie | 2024/2025 | 309 | 309 | 309 | 0 | 0 | 0 | 306 (18 teams round robin) | +3 | European play-offs: single-leg semi-finals (2) + final (1) |
| 61 Liga Portugal | 2021/2022 | 306 | 306 | 306 | 0 | 0 | 0 | 306 (18 teams round robin) | +0 | - |
| 61 Liga Portugal | 2022/2023 | 306 | 306 | 306 | 0 | 0 | 0 | 306 (18 teams round robin) | +0 | - |
| 61 Liga Portugal | 2023/2024 | 306 | 306 | 306 | 0 | 0 | 0 | 306 (18 teams round robin) | +0 | - |
| 61 Liga Portugal | 2024/2025 | 306 | 306 | 306 | 0 | 0 | 0 | 306 (18 teams round robin) | +0 | - |
| 40 First Division A | 2021/2022 | 330 | 330 | 328 | 2 | 0 | 0 | 306 (18 teams round robin) | +24 | Champions' play-off (4 teams, 12) + Europe play-off (4 teams, 12), numbered rounds 1-6 again; 2 awarded 5-0 |
| 40 First Division A | 2022/2023 | 330 | 330 | 328 | 2 | 0 | 0 | 306 (18 teams round robin) | +24 | Champions' play-off (12) + Europe play-off (12), numbered rounds 1-6 again; 2 awarded (5-0, 0-5) |
| 40 First Division A | 2023/2024 | 313 | 313 | 312 | 1 | 0 | 0 | 240 (16 teams round robin) | +73 | Champions' play-off (6 teams, 30) + Europe play-off (30) + relegation play-off (4 teams, 12) as rounds 31-40, + Conference League play-off final; 1 awarded 0-5 |
| 40 First Division A | 2024/2025 | 313 | 313 | 312 | 1 | 0 | 0 | 240 (16 teams round robin) | +73 | same structure as 2023/24 (72 + final) but the play-off rounds are numbered 1-10 again; 1 awarded 5-0 |
| 71 Super Lig | 2021/2022 | 380 | 380 | 380 | 0 | 0 | 0 | 380 (20 teams round robin) | +0 | - |
| 71 Super Lig | 2022/2023 | 342 | 342 | 313 | 29 | 0 | 0 | 342 (19 teams round robin) | +0 | 0; 29 of the 342 are awarded 3-0/0-3, all involving Hatayspor or Gaziantep FK (withdrew after the February 2023 earthquake) |
| 71 Super Lig | 2023/2024 | 380 | 380 | 379 | 1 | 0 | 0 | 380 (20 teams round robin) | +0 | 0; 1 awarded: Istanbulspor v Trabzonspor 0-3 |
| 71 Super Lig | 2024/2025 | 342 | 342 | 341 | 1 | 0 | 0 | 342 (19 teams round robin) | +0 | 0; 1 awarded: Galatasaray v Adana Demirspor 3-0 |
| 122 1. Liga | 2021/2022 | 276 | 276 | 276 | 0 | 0 | 0 | 240 (16 teams round robin) | +36 | championship + relegation groups (6 teams, 5 rounds: 15 + 15, numbered rounds 1-5 again) + European play-off (`1/2` 4, `final` 2) |
| 122 1. Liga | 2022/2023 | 276 | 276 | 276 | 0 | 0 | 0 | 240 (16 teams round robin) | +36 | as 2021/22 |
| 122 1. Liga | 2023/2024 | 277 | 277 | 277 | 0 | 0 | 0 | 240 (16 teams round robin) | +37 | as 2021/22 + one extra UECL play-off match Mlada Boleslav v Hradec Kralove (2024-05-31, round `final`) |
| 122 1. Liga | 2024/2025 | 276 | 276 | 276 | 0 | 0 | 0 | 240 (16 teams round robin) | +36 | as 2021/22 |
| 42 Champions League | 2021/2022 | 125 | 125 | 125 | 0 | 0 | 0 | 125 (96 group + 29 KO) | +0 | - |
| 42 Champions League | 2022/2023 | 125 | 125 | 125 | 0 | 0 | 0 | 125 (96 group + 29 KO) | +0 | - |
| 42 Champions League | 2023/2024 | 125 | 125 | 125 | 0 | 0 | 0 | 125 (96 group + 29 KO) | +0 | - |
| 42 Champions League | 2024/2025 | 189 | 189 | 189 | 0 | 0 | 0 | 189 (144 league + 16 play-off + 29 KO) | +0 | - |
| 73 Europa League | 2021/2022 | 141 | 141 | 139 | 0 | 0 | 2 | 141 (96 group + 16 KO play-off + 29 KO) | +0 | 0; the two Leipzig v Spartak Moscow round-of-16 legs are CANCELLED (Spartak excluded), no score |
| 73 Europa League | 2022/2023 | 141 | 141 | 141 | 0 | 0 | 0 | 141 (96 group + 16 KO play-off + 29 KO) | +0 | - |
| 73 Europa League | 2023/2024 | 141 | 141 | 141 | 0 | 0 | 0 | 141 (96 group + 16 KO play-off + 29 KO) | +0 | - |
| 73 Europa League | 2024/2025 | 189 | 189 | 189 | 0 | 0 | 0 | 189 (144 league + 16 play-off + 29 KO) | +0 | - |
| 10216 Conference League | 2021/2022 | 141 | 141 | 140 | 1 | 0 | 0 | 141 (96 group + 16 KO play-off + 29 KO) | +0 | 0; 1 awarded: Tottenham v Rennes 0-3 (2021-12-09) |
| 10216 Conference League | 2022/2023 | 141 | 141 | 141 | 0 | 0 | 0 | 141 (96 group + 16 KO play-off + 29 KO) | +0 | - |
| 10216 Conference League | 2023/2024 | 141 | 141 | 141 | 0 | 0 | 0 | 141 (96 group + 16 KO play-off + 29 KO) | +0 | - |
| 10216 Conference League | 2024/2025 | 153 | 153 | 153 | 0 | 0 | 0 | 153 (108 league + 16 play-off + 29 KO) | +0 | - |

### All 115 competitions (matches with kickoff < 2025-07-01)

| FotMob id | Competition | Country | Group | Seasons ok | Seasons missing | Kept matches | Finished | Awarded | Not played* | After cutoff (boundary) | First kickoff | Last kickoff |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 87 | LaLiga | ESP | TARGET13 | 5 | 0 | 1520 | 1520 | 0 | 0 | 380 | 2021-08-13T19:00:00Z | 2025-05-25T19:00:00Z |
| 47 | Premier League | ENG | TARGET13 | 5 | 0 | 1521 | 1520 | 0 | 1 | 380 | 2021-08-13T19:00:00Z | 2025-05-25T15:00:00Z |
| 55 | Serie A | ITA | TARGET13 | 5 | 0 | 1521 | 1521 | 0 | 0 | 380 | 2021-08-21T16:30:00Z | 2025-05-25T18:45:00Z |
| 40 | First Division A | BEL | TARGET13 | 5 | 0 | 1286 | 1280 | 6 | 0 | 313 | 2021-07-23T18:45:00Z | 2025-05-29T16:30:00Z |
| 57 | Eredivisie | NED | TARGET13 | 5 | 0 | 1242 | 1242 | 0 | 0 | 309 | 2021-08-13T18:00:00Z | 2025-05-25T16:00:00Z |
| 61 | Liga Portugal | POR | TARGET13 | 5 | 0 | 1224 | 1224 | 0 | 0 | 306 | 2021-08-06T19:15:00Z | 2025-05-17T17:00:00Z |
| 71 | Super Lig | TUR | TARGET13 | 5 | 0 | 1444 | 1413 | 31 | 0 | 306 | 2021-08-13T17:30:00Z | 2025-06-01T16:00:00Z |
| 53 | Ligue 1 | FRA | TARGET13 | 5 | 0 | 1375 | 1372 | 0 | 3 | 306 | 2021-08-06T19:00:00Z | 2025-05-17T19:00:00Z |
| 122 | 1. Liga | CZE | TARGET13 | 5 | 0 | 1105 | 1105 | 0 | 0 | 276 | 2021-07-24T14:00:00Z | 2025-05-25T14:00:00Z |
| 54 | Bundesliga | GER | TARGET13 | 5 | 0 | 1224 | 1223 | 1 | 0 | 306 | 2021-08-13T18:30:00Z | 2025-05-17T13:30:00Z |
| 42 | Champions League | INT | TARGET13 | 5 | 0 | 564 | 564 | 0 | 0 | 189 | 2021-09-14T16:45:00Z | 2025-05-31T19:00:00Z |
| 73 | Europa League | INT | TARGET13 | 5 | 0 | 612 | 610 | 0 | 2 | 189 | 2021-09-15T14:30:00Z | 2025-05-21T19:00:00Z |
| 10216 | Conference League | INT | TARGET13 | 5 | 0 | 576 | 575 | 1 | 0 | 153 | 2021-09-14T14:30:00Z | 2025-05-28T19:00:00Z |
| 140 | LaLiga2 | ESP | second_tier | 5 | 0 | 1872 | 1872 | 0 | 0 | 468 | 2021-08-13T18:00:00Z | 2025-06-21T19:00:00Z |
| 48 | Championship | ENG | second_tier | 5 | 0 | 2229 | 2228 | 0 | 1 | 560 | 2021-08-06T18:45:00Z | 2025-05-24T14:01:00Z |
| 165 | 1. Lig | TUR | second_tier | 5 | 0 | 1390 | 1360 | 30 | 0 | 385 | 2021-08-13T17:30:00Z | 2025-05-29T17:00:00Z |
| 111 | Eerste Divisie | NED | second_tier | 5 | 0 | 1521 | 1520 | 0 | 1 | 380 | 2021-08-06T18:00:00Z | 2025-05-09T18:00:00Z |
| 146 | 2. Bundesliga | GER | second_tier | 5 | 0 | 1224 | 1224 | 0 | 0 | 306 | 2021-07-23T18:30:00Z | 2025-05-18T13:30:00Z |
| 185 | Liga Portugal 2 | POR | second_tier | 5 | 0 | 1224 | 1224 | 0 | 0 | 306 | 2021-08-07T09:45:00Z | 2025-05-17T13:00:00Z |
| 86 | Serie B | ITA | second_tier | 5 | 0 | 1562 | 1558 | 1 | 3 | 390 | 2021-08-20T18:30:00Z | 2025-06-22T18:30:00Z |
| 110 | Ligue 2 | FRA | second_tier | 5 | 0 | 1518 | 1443 | 2 | 73 | 306 | 2021-07-24T13:00:00Z | 2025-05-10T17:00:00Z |
| 264 | First Division B | BEL | second_tier | 5 | 0 | 796 | 766 | 0 | 30 | 278 | 2021-08-13T18:00:00Z | 2025-05-11T14:00:00Z |
| 253 | FNL | CZE | second_tier | 5 | 0 | 961 | 960 | 0 | 1 | 240 | 2021-07-23T16:00:00Z | 2025-05-25T15:00:00Z |
| 10615 | Conference League Qualification | INT | context | 5 | 0 | 1088 | 1086 | 2 | 0 | 258 | 2021-07-06T15:45:00Z | 2024-08-29T19:00:00Z |
| 69 | Super League | SUI | context | 5 | 0 | 816 | 815 | 1 | 0 | 229 | 2021-07-24T16:00:00Z | 2025-05-24T16:00:00Z |
| 136 | 1. Division | CYP | context | 5 | 0 | 968 | 964 | 4 | 0 | 240 | 2021-08-20T16:00:00Z | 2025-05-18T16:00:00Z |
| 46 | Superligaen | DEN | context | 5 | 0 | 772 | 772 | 0 | 0 | 193 | 2021-07-16T17:00:00Z | 2025-06-01T16:30:00Z |
| 10611 | Champions League Qualification | INT | context | 5 | 0 | 361 | 361 | 0 | 0 | 92 | 2021-06-22T18:00:00Z | 2024-08-28T19:00:00Z |
| 182 | Super Liga | SRB | context | 5 | 0 | 1192 | 1190 | 2 | 0 | 296 | 2021-07-16T15:55:00Z | 2025-05-25T17:00:00Z |
| 10613 | Europa League Qualification | INT | context | 5 | 0 | 184 | 184 | 0 | 0 | 82 | 2021-08-03T17:00:00Z | 2024-08-29T19:00:00Z |
| 59 | Eliteserien | NOR | context | 5 | 0 | 1055 | 1054 | 0 | 1 | 146 | 2021-05-09T16:00:00Z | 2025-06-30T17:00:00Z |
| 64 | Premiership | SCO | context | 5 | 0 | 912 | 912 | 0 | 0 | 228 | 2021-07-31T12:30:00Z | 2025-05-18T14:00:00Z |
| 196 | Ekstraklasa | POL | context | 5 | 0 | 1225 | 1223 | 1 | 1 | 306 | 2021-07-23T16:00:00Z | 2025-05-24T15:30:00Z |
| 38 | Bundesliga | AUT | context | 5 | 0 | 780 | 780 | 0 | 0 | 195 | 2021-07-23T18:30:00Z | 2025-06-01T15:00:00Z |
| 135 | Super League 1 | GRE | context | 5 | 0 | 956 | 954 | 2 | 0 | 236 | 2021-09-11T15:15:00Z | 2025-05-22T17:00:00Z |
| 67 | Allsvenskan | SWE | context | 5 | 0 | 1066 | 1066 | 0 | 0 | 134 | 2021-04-10T13:00:00Z | 2025-06-30T17:00:00Z |
| 189 | Liga I | ROU | context | 5 | 0 | 1266 | 1265 | 0 | 1 | 317 | 2021-07-15T17:30:00Z | 2025-05-24T18:00:00Z |
| 270 | First Professional League | BUL | context | 5 | 0 | 1081 | 1081 | 0 | 0 | 293 | 2021-07-23T15:45:00Z | 2025-05-31T15:30:00Z |
| 118 | Premier League | ARM | context | 5 | 0 | 705 | 662 | 7 | 36 | 135 | 2021-07-30T15:00:00Z | 2025-05-28T15:00:00Z |
| 173 | Prva Liga | SVN | context | 5 | 0 | 721 | 718 | 2 | 1 | 180 | 2021-07-16T15:00:00Z | 2025-05-25T15:30:00Z |
| 63 | Premier League | RUS | context | 5 | 0 | 960 | 959 | 1 | 0 | 270 | 2021-07-23T17:00:00Z | 2025-05-24T13:30:00Z |
| 127 | Ligat ha'Al | ISR | context | 5 | 0 | 960 | 955 | 5 | 0 | 240 | 2021-08-28T15:45:00Z | 2025-05-24T17:30:00Z |
| 441 | Premier League | UKR | context | 5 | 0 | 1020 | 861 | 2 | 157 | 240 | 2021-07-23T16:30:00Z | 2025-05-25T15:00:00Z |
| 133 | EFL Cup | ENG | context | 5 | 0 | 372 | 371 | 1 | 0 | 91 | 2021-07-31T14:00:00Z | 2025-03-16T16:30:00Z |
| 126 | Premier Division | IRL | context | 5 | 0 | 834 | 832 | 2 | 0 | 66 | 2021-03-19T17:45:00Z | 2025-06-27T19:00:00Z |
| 267 | Premier League | BIH | context | 5 | 0 | 792 | 788 | 4 | 0 | 180 | 2021-07-16T18:00:00Z | 2025-05-31T15:00:00Z |
| 51 | Veikkausliiga | FIN | context | 5 | 0 | 739 | 738 | 1 | 0 | 101 | 2021-04-24T12:00:00Z | 2025-06-28T20:00:00Z |
| 252 | HNL | CRO | context | 5 | 0 | 720 | 720 | 0 | 0 | 180 | 2021-07-16T16:55:00Z | 2025-05-25T15:00:00Z |
| 209 | DFB Pokal | GER | context | 5 | 0 | 252 | 251 | 1 | 0 | 63 | 2021-08-06T18:45:00Z | 2025-05-24T18:00:00Z |
| 151 | Turkish Cup | TUR | context | 5 | 0 | 497 | 495 | 2 | 0 | 102 | 2021-09-28T10:00:00Z | 2025-05-14T17:45:00Z |
| 138 | Copa del Rey | ESP | context | 6 | 0 | 465 | 464 | 1 | 0 | 117 | 2021-11-30T15:00:00Z | 2025-04-26T20:00:00Z |
| 176 | 1. liga | SVK | context | 5 | 0 | 777 | 776 | 1 | 0 | 192 | 2021-07-23T18:00:00Z | 2025-05-23T16:00:00Z |
| 231 | National Division | MDA | context | 5 | 0 | 385 | 368 | 10 | 7 | 106 | 2021-07-01T15:00:00Z | 2025-06-29T17:00:00Z |
| 262 | Premier League | AZE | context | 5 | 0 | 652 | 652 | 0 | 0 | 199 | 2021-08-14T14:30:00Z | 2025-05-25T15:30:00Z |
| 215 | Besta deildin | ISL | context | 5 | 0 | 696 | 696 | 0 | 0 | 84 | 2021-04-30T20:00:00Z | 2025-06-29T19:15:00Z |
| 225 | Premier League | KAZ | context | 5 | 0 | 828 | 800 | 2 | 26 | 82 | 2021-03-13T09:00:00Z | 2025-06-29T15:00:00Z |
| 254 | Czech Cup | CZE | context | 5 | 0 | 248 | 232 | 0 | 16 | 57 | 2021-08-24T15:00:00Z | 2025-05-14T17:00:00Z |
| 141 | Coppa Italia | ITA | context | 5 | 0 | 180 | 180 | 0 | 0 | 45 | 2021-08-07T17:05:00Z | 2025-05-14T19:00:00Z |
| 108 | League One | ENG | context | 5 | 0 | 2232 | 2228 | 0 | 4 | 557 | 2021-08-07T14:00:00Z | 2025-05-25T12:01:00Z |
| 147 | Serie C | ITA | context | 5 | 0 | 4770 | 4652 | 0 | 118 | 1184 | 2021-08-28T15:30:00Z | 2025-06-07T19:15:00Z |
| 186 | Taca de Portugal | POR | context | 5 | 0 | 444 | 443 | 1 | 0 | 111 | 2021-09-23T18:45:00Z | 2025-05-25T16:15:00Z |
| 132 | FA Cup | ENG | context | 6 | 0 | 555 | 552 | 0 | 3 | 123 | 2021-11-05T19:55:00Z | 2025-05-17T15:30:00Z |
| 134 | Coupe de France | FRA | context | 6 | 0 | 1404 | 1389 | 7 | 8 | 362 | 2021-10-30T13:00:00Z | 2025-05-24T19:00:00Z |
| 228 | A Lyga | LTU | context | 5 | 0 | 810 | 808 | 2 | 0 | 90 | 2021-03-05T16:00:00Z | 2025-06-30T16:00:00Z |
| 248 | Premium liiga | EST | context | 5 | 0 | 812 | 787 | 1 | 24 | 88 | 2021-03-13T11:00:00Z | 2025-06-29T16:00:00Z |
| 226 | Virsliga | LVA | context | 5 | 0 | 792 | 744 | 16 | 32 | 78 | 2021-03-13T11:00:00Z | 2025-06-30T16:00:00Z |
| 116 | Cymru Premier | WAL | context | 5 | 0 | 805 | 781 | 0 | 24 | 195 | 2021-08-13T18:45:00Z | 2025-05-18T16:10:00Z |
| 129 | Premiership | NIR | context | 5 | 0 | 926 | 923 | 1 | 2 | 233 | 2021-08-27T18:45:00Z | 2025-05-11T13:00:00Z |
| 235 | KNVB Cup | NED | context | 6 | 0 | 231 | 231 | 0 | 0 | 57 | 2021-10-26T16:45:00Z | 2025-04-21T16:00:00Z |
| 249 | Prva Liga | MKD | context | 5 | 0 | 781 | 747 | 12 | 22 | 198 | 2021-08-08T15:30:00Z | 2025-05-18T15:00:00Z |
| 212 | NB I | HUN | context | 5 | 0 | 792 | 792 | 0 | 0 | 198 | 2021-07-30T16:15:00Z | 2025-05-25T12:15:00Z |
| 193 | Russian Cup | RUS | context | 5 | 0 | 313 | 313 | 0 | 0 | 94 | 2021-08-25T10:00:00Z | 2025-06-01T15:00:00Z |
| 145 | Greece Cup | GRE | context | 5 | 0 | 415 | 401 | 13 | 1 | 64 | 2021-08-28T14:00:00Z | 2025-05-17T17:00:00Z |
| 263 | Premier League | BLR | context | 5 | 0 | 1072 | 1025 | 17 | 30 | 128 | 2021-03-12T14:30:00Z | 2025-06-29T16:00:00Z |
| 163 | Challenge League | SUI | context | 5 | 0 | 720 | 719 | 1 | 0 | 181 | 2021-07-23T18:30:00Z | 2025-05-23T18:15:00Z |
| 250 | Premier League | FRO | context | 5 | 0 | 616 | 614 | 1 | 1 | 60 | 2021-03-06T15:00:00Z | 2025-06-29T16:15:00Z |
| 149 | Cup | BEL | context | 6 | 0 | 132 | 132 | 0 | 0 | 33 | 2021-10-26T18:00:00Z | 2025-05-04T16:00:00Z |
| 206 | Cup | NOR | context | 6 | 0 | 632 | 630 | 2 | 0 | 83 | 2021-07-24T11:00:00Z | 2025-06-25T16:00:00Z |
| 278 | Cup | AUT | context | 5 | 0 | 253 | 252 | 0 | 1 | 63 | 2021-07-16T15:00:00Z | 2025-05-01T15:00:00Z |
| 242 | DBU Pokalen | DEN | context | 5 | 0 | 436 | 433 | 2 | 1 | 109 | 2021-08-03T16:00:00Z | 2025-05-29T15:00:00Z |
| 164 | Cup | SUI | context | 5 | 0 | 252 | 252 | 0 | 0 | 63 | 2021-08-13T17:30:00Z | 2025-06-01T12:00:00Z |
| 180 | League Cup | SCO | context | 5 | 0 | 380 | 369 | 11 | 0 | 95 | 2021-07-09T18:45:00Z | 2024-12-15T15:30:00Z |
| 171 | Svenska Cupen | SWE | context | 5 | 0 | 509 | 504 | 1 | 4 | 90 | 2021-06-09T17:30:00Z | 2025-06-30T17:00:00Z |
| 330 | Cup | CYP | context | 5 | 0 | 121 | 120 | 1 | 0 | 29 | 2021-09-22T16:00:00Z | 2025-05-24T17:00:00Z |
| 203 | 1. Divisjon | NOR | context | 5 | 0 | 1063 | 1063 | 0 | 0 | 137 | 2021-05-15T13:30:00Z | 2025-06-29T15:00:00Z |
| 190 | Cupa României | ROU | context | 6 | 0 | 140 | 140 | 0 | 0 | 43 | 2021-11-30T18:30:00Z | 2025-05-14T17:30:00Z |
| 58 | Eredivisie Qualification | NED | context | 6 | 0 | 48 | 47 | 1 | 0 | 12 | 2022-05-09T18:00:00Z | 2025-06-01T16:00:00Z |
| 142 | EFL Trophy | ENG | context | 5 | 0 | 508 | 508 | 0 | 0 | 127 | 2021-08-24T18:00:00Z | 2025-04-13T14:00:00Z |
| 275 | Croatian Cup | CRO | context | 6 | 0 | 62 | 62 | 0 | 0 | 47 | 2021-10-26T11:00:00Z | 2025-05-29T17:00:00Z |
| 9097 | Cup | ISR | context | 6 | 0 | 205 | 204 | 1 | 0 | 61 | 2022-01-11T17:00:00Z | 2025-05-29T17:40:00Z |
| 137 | Scottish Cup | SCO | context | 5 | 0 | 420 | 416 | 2 | 2 | 101 | 2021-09-17T18:45:00Z | 2025-05-24T14:00:00Z |
| 143 | Suomen Cup | FIN | context | 5 | 0 | 281 | 281 | 0 | 0 | 3 | 2021-02-06T11:30:00Z | 2025-06-24T15:30:00Z |
| 198 | Puchar Polski | POL | context | 5 | 0 | 275 | 272 | 3 | 0 | 69 | 2021-08-04T14:00:00Z | 2025-05-02T14:00:00Z |
| 271 | Cup | BUL | context | 5 | 0 | 132 | 132 | 0 | 0 | 33 | 2021-09-21T12:45:00Z | 2025-05-22T16:00:00Z |
| 342 | Finland Cup | FIN | context | 4 | 0 | 124 | 124 | 0 | 0 | 0 | 2022-01-28T12:00:00Z | 2025-03-29T11:00:00Z |
| 219 | FAI Cup | IRL | context | 5 | 0 | 146 | 144 | 1 | 1 | 31 | 2021-07-23T18:45:00Z | 2025-05-18T14:00:00Z |
| 78 | FIFA Club World Cup | INT | context | 5 | 0 | 79 | 75 | 0 | 4 | 10 | 2022-02-03T16:30:00Z | 2025-06-30T19:00:00Z |
| 10076 | League Cup | ISL | context | 4 | 0 | 252 | 240 | 2 | 10 | 0 | 2022-02-09T19:00:00Z | 2025-03-25T13:00:00Z |
| 177 | FA Cup | SVK | context | 6 | 0 | 164 | 164 | 0 | 0 | 65 | 2022-03-01T13:00:00Z | 2025-05-01T13:00:00Z |
| 187 | League Cup | POR | context | 5 | 0 | 144 | 144 | 0 | 0 | 7 | 2021-07-23T19:15:00Z | 2025-01-11T19:45:00Z |
| 217 | Icelandic Cup | ISL | context | 5 | 0 | 152 | 152 | 0 | 0 | 3 | 2021-06-22T18:00:00Z | 2025-06-19T20:00:00Z |
| 9098 | Toto Cup UEFA Qualifiers Match | ISR | context | 5 | 0 | 36 | 36 | 0 | 0 | 9 | 2021-07-15T17:30:00Z | 2024-12-25T18:00:00Z |
| 9112 | Liga 3 | POR | context | 5 | 0 | 1266 | 1264 | 2 | 0 | 296 | 2021-08-13T16:00:00Z | 2025-05-17T14:00:00Z |
| 213 | FA Cup | HUN | context | 6 | 0 | 60 | 60 | 0 | 0 | 15 | 2022-02-05T12:00:00Z | 2025-05-14T17:00:00Z |
| 442 | Cup | UKR | context | 5 | 0 | 42 | 38 | 0 | 4 | 15 | 2021-10-26T16:30:00Z | 2025-05-14T15:30:00Z |
| 9389 | Irish Cup | NIR | context | 6 | 0 | 101 | 100 | 0 | 1 | 31 | 2022-03-04T19:45:00Z | 2025-05-03T13:30:00Z |
| 10025 | 1. Liga Qualification | CZE | context | 5 | 0 | 16 | 16 | 0 | 0 | 4 | 2022-05-19T15:00:00Z | 2025-06-01T13:00:00Z |
| 139 | Super Cup | ESP | context | 6 | 0 | 12 | 12 | 0 | 0 | 6 | 2022-01-12T19:00:00Z | 2025-01-12T19:00:00Z |
| 166 | Super Cup | TUR | context | 5 | 0 | 4 | 3 | 1 | 0 | 3 | 2022-01-05T17:45:00Z | 2024-08-03T17:45:00Z |
| 174 | Cup | SVN | context | 5 | 0 | 56 | 56 | 0 | 0 | 15 | 2021-09-15T13:00:00Z | 2025-05-14T18:00:00Z |
| 183 | Cup | SRB | context | 6 | 0 | 29 | 28 | 0 | 1 | 7 | 2022-04-06T14:00:00Z | 2025-05-21T16:00:00Z |
| 222 | Super Cup | ITA | context | 6 | 0 | 8 | 8 | 0 | 0 | 4 | 2022-01-12T20:00:00Z | 2025-01-06T19:00:00Z |
| 8978 | League Cup | NIR | context | 5 | 0 | 116 | 116 | 0 | 0 | 37 | 2021-11-09T19:45:00Z | 2025-03-09T15:00:00Z |
| 9521 | Cup | BLR | context | 6 | 0 | 20 | 20 | 0 | 0 | 5 | 2022-04-06T14:00:00Z | 2025-05-24T16:00:00Z |
| 9666 | Ligue 1 Qualification | FRA | context | 5 | 0 | 12 | 12 | 0 | 0 | 4 | 2022-05-17T18:30:00Z | 2025-05-29T18:30:00Z |
| | **Total** | | | 590 | 0 | 83214 | 82327 | 228 | 659 | 19153 | | |

*Not played = cancelled + postponed + other non-finished statuses (scores NULL).

## Verification (2026-10-13)

* Per competition-season counts of TARGET13 vs known sizes: table above, every deviation explained.
* 0 duplicate match ids (history: PK + `duplicate_match_ids` empty; `results`: 168,579 rows = 168,579
  distinct ids).
* **TARGET13 teams of 2025/26 with history** (teams in production FINISHED TARGET13 matches
  2025-07-01..2026-06-30): **232 of 232** have history matches; **229** have >= 20 history matches in
  2024-07-01..2025-06-30. All TARGET13 leagues: every team. The 3 thin ones are Conference League clubs whose
  domestic league is not in the production DB (so not a candidate): Hamrun Spartans (Malta, 18 history
  matches, all UEFA qualifiers), Drita (Kosovo, 16), Lincoln Red Imps (Gibraltar, 30).
* **Spot check:** 10 random FINISHED history matches compared with `matchDetails` (`general.homeTeam/awayTeam.id`,
  `header.teams[*].score`, kickoff, status): **10/10 agree** (`spot_check.json`; 10 extra requests through
  the limiter).
* Rebuilding both databases from the raw cache gives identical counts (idempotent).
* Unit tests: `tests/test_collect_fotmob_history_results.py` 7 passed (season rules, status/score rules incl.
  the abandoned shape, bracket-only matches, season-fallback detection, exclusion rules, cutoff partition,
  duplicate recording, prewindow seasons). QA added an 8th test for `build_all_results.build` (the union, and
  production rows with team id -1 or a missing team row reported in `conflicts`): 8 + 4 limiter tests passed.

### Independent QA (2026-10-13, separate agent, own code paths)

* Re-parsed all 590 raw season files with independent code: all 83,214 `matches` and 19,153
  `matches_after_cutoff` rows agree with the raw responses field by field, including teams, kickoff, score,
  status, flags, `score_str`, season and round. Every `selectedSeason` and league id matches its file name, no
  match id appears in two files, and the playoff bracket adds nothing. Both coverage tables above (52
  TARGET13 rows and 115 competition rows) and the flag-combination table recompute exactly.
* `results`: all 82,555 history rows and 86,024 production rows were recomputed from `history_results.db` and
  the production DB (read-only), field by field, with 0 differences. All id columns are SQLite integers, with
  no uuid and no non-positive id. Every kickoff is ISO UTC `...Z` and none is in the future (latest
  2026-10-12T22:30:00Z). No match id appears on both sides of the cutoff, and no team pair meets within 7
  days across it in either orientation. The 28 conflicts and the selection of all 500 competitions (decisions
  and counts) recompute exactly.
* Rebuilding from the raw cache (`--from-raw` into a scratch path) and running `build_all_results.py` twice
  gave byte-identical table content and an identical `competition_selection.csv`.
* Live check: 15 `matchDetails` requests through the shared limiter (awarded 0-0, both abandoned matches
  without replay, a cancelled match, Pen/AET, a prewindow super cup, a boundary-season and a pre-July-2021
  match, the Rimini / Reggiana / awarded conflicts, 3 random matches). All 15 agree with
  `history_results.db`, and the production conflicts are what FotMob shows. The collector's 10 saved
  spot-check bodies also agree.

## Known gaps and caveats

1. **Only production-DB competitions are candidates.** Clubs whose domestic league is not in the
   production DB (seen for Malta, Kosovo and Gibraltar) only have their UEFA matches. Leagues that are in
   the DB but had no TARGET13-connected team (e.g. Albania 260, Montenegro 232) are excluded by the rule.
2. **UCL qualification preliminary round 2024/25 and 2025/26 is not in FotMob's 10611**: those seasons start
   on 2024-07-09 and 2025-07-08, while 2021/22-2023/24 include the late-June preliminary round. These
   matches are in neither history nor production.
3. **Competitions excluded by the >= 3 rule** (single-match super cups, two-legged relegation play-offs: see
   the list above) are not in the history.
4. **`round` is not unique within a season** (play-off stages restart the numbering; Belgium even differs
   between seasons). There is no stage id in `allMatches`.
5. **Awarded results** (228 in history) carry the decision's score: mostly 3-0 / 0-3 (Belgium 5-0 / 0-5), but
   16 are 0-0 (double forfeits or walkovers without a winner, one against the placeholder team "Paris FC/Lyon"
   1323733) and 4 have other scores (2-0, 0-2, 0-1, 0-1). **Abandoned** matches have no score. 27 of 29 have
   a later meeting of the same home and away teams in the same competition-season, normally the replay under
   another id. 2 have none (Troyes v Valenciennes 2024-05-03, Salernitana v Sampdoria 2025-06-22), so their
   outcome is missing.
6. **Before-window matches:** 1,049 matches before 2021-07-01 come with the calendar-year 2021 seasons and
   the June 2021 qualifiers (kept, flagged only by their date).
7. **Production rows** have `season` only for 18,584 matches and `awarded` only for 19,792 (FotMob fixture
   or match-details flag); the rest is NULL (unknown, not 0).
8. **EFL Trophy (142)** is included (TARGET13-connected clubs such as Luton play in it) although it contains
   Premier League/Championship academy sides (separate team ids).
9. **Shared limiter race (Windows):** `fotmob_rate.acquire()` raised `PermissionError` once (mkdir of the
   lock directory while another process removed it); this collector retries on `PermissionError`, the shared
   module itself only handles `FileExistsError`.
10. **Fixtures in neither side of `results`:** 478 FINISHED/AWARDED FotMob fixtures after the cutoff are
    not in the production DB, mostly the first cup rounds (see the reverse check under Boundary checks).
    Of the 16 AWARDED FotMob fixtures after the cutoff, production has 4, with the on-pitch score
    (`production_vs_fixture_score`), and is missing 12.
11. **6 duplicate fixtures inside production** (Premier League 2 play-off under 10176 and 9084, outside the
    history scope) are both in `results`; filter on `competition_in_history_scope = 1` or deduplicate them.
