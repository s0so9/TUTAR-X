# Live layer: team news (squads, availability, line-ups, last-5 form)

**Özet (TR):** Değişen verinin canlı katmanı. FotMob'dan kadrolar, sakatlık/ceza listeleri, tahmini ve
açıklanan ilk 11'ler ve bitmiş maçların oyuncu istatistikleri zaman damgalı olarak veritabanına yazılır;
`GET /api/v1/matches/{match_id}/team-news` her takım için ilk 11'i (oyuncuların son 5 maç formu ile),
eksik oyuncuları (son 5 maçtaki gol/xG/dakika payları ile), takımın son 5 maçını ve verinin tazeliğini
döndürür. Eksik veri her zaman `null` + `missing_reason` kodudur, asla 0 değildir. Arka plan yenilemesi
varsayılan olarak kapalıdır (`TEAM_NEWS_REFRESH_ENABLED=false`); cron için
`scripts/live/refresh_team_news.py --once` vardır. Model değişikliği ve arayüz bu işte yoktur.

Owner of this layer: agent `live:team-news` (2026-10-13). Code: `backend/app/services/team_news/`,
endpoints `backend/app/api/v1/endpoints/team_news.py` + `teams.py`, jobs `backend/scripts/live/`,
migration `backend/alembic/versions/20261013_team_news_live_layer.py` (revision `20261013_team_news`).

---

## 1. What changes and where it comes from

| Data | Source (FotMob unofficial API, `settings.fotmob_base_url`) | Stored in |
|---|---|---|
| Squad + squad injury list | `/api/data/teams?id=<team>` → `squad.squad[*].members[*]` | `players`, `team_squad_members`, `player_availability` (source `fotmob_team_squad`) |
| Player profile + injury / international duty | `/api/data/playerData?id=<player>` | `players`, `player_availability` (source `fotmob_player_profile`) |
| Expected / confirmed XI and the match unavailable list | `/api/data/matchDetails?matchId=<match>` → `content.lineup` | `lineup_snapshots`, `player_availability` (source `fotmob_match_lineup`), `team_news_matches` |
| Per-player match stats (finished matches) | same `matchDetails` → `content.playerStats`, `content.lineup`, `content.matchFacts.events` | `player_match_stats` |
| Team results and team xG (last 5) | local `matches` table (already maintained) | read only |
| Match discovery | local `matches` + `/api/data/leagues?id=<league>` (`fixtures.allMatches`) | `team_news_matches` (header) |

Target competitions (`TEAM_NEWS_COMPETITIONS`, FotMob ids): Premier League 47, LaLiga 87, Serie A 55,
Bundesliga 54, Ligue 1 53, Eredivisie 57, Liga Portugal 61, Belgian Pro League 40, Super Lig 71,
Czech 1. Liga 122, Champions League 42, Europa League 73, Conference League 10216.

## 2. Tables (Alembic `20261013_team_news`, PostgreSQL-ready types)

All tables have `id` (UUID text), `created_at`, `updated_at`. Provider ids are FotMob ids stored as text;
`*_id` foreign keys are filled only when the referenced local row exists (upcoming matches are not in
`matches`, so `team_news_matches` / snapshots carry the FotMob id and a nullable `match_id`).

* **players** (existing, previously unused; extended): identity (`provider_id`, `name`) + slowly
  changing profile: `date_of_birth`, `nationality`, `country_code`, `position` (broad role as sent, e.g.
  "Defender"), `primary_position` ("Center Back"), `positions` (JSON `[{id, label, ...}]` as sent),
  `height_cm`, `preferred_foot`, `shirt_number`, current team (`team_provider_id`, `team_id`),
  `market_value_eur` + `market_value_as_of` + `market_value_source`, `contract_end`, `profile_source`,
  `profile_observed_at`. Merge rule: an observation at least as new as `profile_observed_at` overwrites
  the fields it sends; an older one only fills NULL fields. `profile_source` is the best-ranked source
  that has observed the player (player profile > squad > line-up) and `profile_observed_at` its latest
  observation. Current team comes only from squads/profiles. The market value is written as a unit:
  the squad endpoint sends no valuation date (`market_value_as_of` NULL); the profile sends dated values
  (latest EUR entry of `marketValues.values`).
* **team_squad_members**: team × player × season (season exactly as sent, `details.latestSeason`),
  `role` (group title: keepers/defenders/midfielders/attackers), `role_key`, `shirt_number`,
  `first_seen_at`, `last_seen_at`. Unique (team, player, season). The current squad = members whose
  `last_seen_at` equals the latest observation of the team. Coaches are skipped (not players).
* **player_availability**: one row per observed report: `status` (`injured | suspended | doubtful |
  international_duty | other`), `raw_type` (type as sent), `reason` (text as sent, e.g. "Back injury",
  profile only), `injury_id` (FotMob injury code), `expected_return` (text as sent), `expected_return_date`
  (only when sent), `source`, `source_updated_at` (profile `lastUpdated`), `first_observed_at`,
  `last_observed_at`, `cleared_at` (NULL while active), `cleared_reason` (`not_listed | superseded`),
  `timestamp_basis` (`observed` = fetch time, `match_kickoff` = backfilled from a post-match response,
  stamped with the kickoff), `match_id` / `provider_match_id` / `side` (match lists only).
* **player_match_stats**: per player per finished match, unique (`provider_match_id`,
  `player_provider_id`): match/player/team ids, `side`, `started`, `appeared`, `minutes`, `rating`, `goals`,
  `assists`, `xg`, `xa`, `npxg`, `xgot`, `shots`, `shots_on_target`, `yellow_cards`, `red_cards`,
  `position_id` (pitch slot, starters), `usual_position_id` (0 GK, 1 DEF, 2 MID, 3 FWD), `is_goalkeeper`,
  `sub_in_minute`, `sub_out_minute`, `stats_available`, `shotmap_count`, `market_value_eur` (line-up value
  near match time), `match_date`, `competition_provider_id`, `source`, `fetched_at`.
* **lineup_snapshots**: per match × side × distinct content: `lineup_type` and `lineup_source` as sent,
  `based_on_match_id` (lineupType `lastStarting11` only), `formation`, `starter_ids`, `starters`
  (`[{id, name, shirt_number, position_id, usual_position_id}]`), `bench` (NULL when not sent),
  `content_hash`, `observed_at` (first observation of this content), `last_observed_at`,
  `timestamp_basis`. A pre-match prediction can store the snapshot id it used.
* **team_news_matches**: registry of tracked matches: FotMob match id, local `match_id`, competition,
  home/away FotMob ids and names, `kickoff_at`, `source_status` (`scheduled | started | finished |
  cancelled`, from FotMob flags), `header_source`, `details_fetched_at`, `home_/away_unavailable_observed_at`
  (NULL = that side's list was never sent), `stats_ingested_at`, `last_error`.

### Availability lifecycle (history is never deleted)

A fresh, complete observation of a *scope* is reconciled with the active rows of that scope: a squad
(source `fotmob_team_squad`, per team), a match list (`fotmob_match_lineup`, per match and side) or a
profile (`fotmob_player_profile`, per player). Same report again → `last_observed_at` moves; a player no
longer listed → `cleared_at` = observation time, `cleared_reason = not_listed`; a changed report (status,
type, injury id or expected-return text) → old row `superseded`, new row inserted. Observations older
than the newest one already applied to the scope are ignored (`stale`), so replays and backfills are
idempotent. A match list whose key is absent from the response (`unavailable` not sent) changes nothing;
an empty list clears. This gives time-stamped availability features for training: "was X listed out
at time T" = `first_observed_at <= T < coalesce(cleared_at, ∞)`.

### Line-up types (as sent) and the derived `lineup_status`

| `lineupType` | `lineup_status` | Meaning |
|---|---|---|
| `standard` | `confirmed` | official XI (published ~1 h before kickoff; also the final XI of finished matches) |
| `predicted` | `predicted` | FotMob's predicted XI for this match (usually no bench) |
| `lastStarting11` | `last_match_xi` | the team's XI of its previous match (`lineup.source = lastStartingLineups`, `<side>Team.lastMatch.matchId` → `based_on_match_id`). A placeholder, **not** a prediction |
| other (e.g. `unavailable`) | `other` | no usable XI; no snapshot is stored when there are no starters |

## 3. Parsed fields (raw paths)

Parsers: `backend/app/services/team_news/parsers.py` (pure functions, shared by live refresh and backfill).

* **teams**: `details.id/name/latestSeason` (fallback `overview.season`); members `id, name, shirtNumber,
  ccode, cname, role{key,fallback}, positionIds, positionIdsDesc, height, dateOfBirth, transferValue,
  injured, injury{id, expectedReturn}`. Squad injury → status `injured`, `raw_type` "injured" (the squad
  flag; the squad endpoint carries no suspensions). An empty `squad.squad` list (FotMob sends one for a
  few teams) is treated as "not sent": it neither writes members nor clears injuries.
* **playerData**: `id, name, birthDate.utcTime, contractEnd.utcTime, primaryTeam.teamId,
  positionDescription.primaryPosition.label, positionDescription.positions[*]`, `playerInformation[*]` by
  `translationKey` (`height_sentencecase`, `shirt`, `preferred_foot`, `country_sentencecase`),
  `marketValues.values[*]{date, value, currency}`, `injuryInformation{name, key "injury_<id>",
  expectedReturn.expectedReturnFallback, expectedReturnDateParam, lastUpdated}`, `internationalDuty`.
  `injuryInformation: null` = nothing reported (clears); both keys absent = cannot confirm or clear.
* **matchDetails**: `general.matchId, leagueId, parentLeagueId (competition), homeTeam, awayTeam,
  matchTimeUTCDate, started, finished`; `header.status.{finished, started, cancelled}`; `header.teams[*].score`;
  `content.lineup.{lineupType, source, homeTeam/awayTeam.{id, name, formation, starters, subs,
  unavailable[*].{id, name, unavailability.{type, injuryId, expectedReturn, expectedReturnDate}}, lastMatch}}`.
  Unavailable `type` → status: `injury` → injured, `suspension` → suspended, `internationalDuty` →
  international_duty, anything containing "doubt" → doubtful, else other (raw type kept).
  Player stats (finished only) mirror `collect_fotmob_details.py`: `content.playerStats[pid].stats[*].stats`
  by stable `key` (`rating_title, minutes_played, goals, assists, expected_goals, expected_assists,
  expected_goals_on_target_variant, expected_goals_non_penalty, total_shots, ShotsOnTarget`), rating
  fallback `performance.rating`, `shotmap` length, `isGoalkeeper`; sub minutes from
  `performance.substitutionEvents`.

**Derived values (documented, not invented):** `appeared` = starter or a `subIn` event;
`yellow_cards` = number of `Card` events with `card == "Yellow"` in `content.matchFacts.events.events`,
`red_cards` = `Red` + `YellowRed` (a second-yellow dismissal counts as yellow 1 + red 1); both NULL when the
response has no event list. FotMob omits xG/xA/shots for players without a shot/chance: those stay NULL.

## 4. API

`GET /api/v1/matches/{match_id}/team-news` — `match_id` = local UUID, `fotmob_<id>` or the bare FotMob id.
DB only (no provider call). 404 `{"missing_reason": "match_not_tracked"}` when the match is neither in
`matches` nor in `team_news_matches`; 503 `{"error": "team_news_not_migrated"}` before the migration.
Per side (`home`, `away`):

* `lineup`: latest snapshot observed at or before `as_of` (`lineup_type`, `lineup_status`, label, formation,
  `observed_at`, `last_observed_at`, `timestamp_basis`, starters, bench), each starter with `form`.
* `absentees`: reports active at `as_of` from the match list, the squad and profiles, merged per player
  (primary source priority match list > squad > profile, all `reports` listed), with `form`, `share` and
  `listed_in_lineup` (true when the same player is a starter in the snapshot: sources disagree).
* `last5`: the team's last 5 FINISHED matches before kickoff from `matches` (W/D/L, goals, xG for/against,
  `xg_matches`, `player_data` per match).
* `freshness`: `lineup_observed_at`, `match_unavailable_observed_at`, `squad_observed_at`,
  `player_profiles_observed_at`, `player_match_stats_fetched_at`, `last_team_match_at`.
* top level: `match.as_of` (= kickoff for started/finished matches → point-in-time view; now for upcoming),
  `sources` (with Turkish labels and observed_at), `notes` (TR), `is_development_data: false`.

**Form** (`PlayerForm`, window = the team's last 5 finished matches before kickoff): `apps`, `starts`,
`minutes`, `goals`, `assists`, `xg`, `xa`, `avg_rating` over the window matches that have player data
(`matches_with_data`); `coverage` counts how many appearances contributed to each sum (FotMob omits
values). xG uses one documented zero rule: an appearance with `stats_available` and `shotmap_count == 0`
counts as xG 0 (shot data tracked, no shot) — `coverage.xg_zero_rule_apps`. No zero rule for xA (FotMob
also omits xA for some players who created chances). A player with 0 appearances in matches whose full
line-ups are known gets minutes/goals/assists/xG/xA 0 and `missing_reason` `did_not_appear`.

**Share** (`ContributionShare`, absentees): over the window matches with player data — player goals /
team goals (from the score), player xG / team xG (matches table, only matches with team xG and a known
player xG), player minutes / team minutes (team minutes per match = the longest `minutes_played` of any
team player). Undefined ratios are NULL with a reason (`team_scored_no_goals`, `team_xg_unavailable`, ...).

`GET /api/v1/teams/{team_id}/squad[?include_former=true]` — latest observed squad with profile fields and
active availability reports; `availability_status` = `unavailable` | `no_report` (never "fit").
`missing_reason = squad_not_observed` when the squad was never fetched; 404 for unknown teams.

`missing_reason` codes → Turkish UI text: `app/services/team_news/constants.py` `MISSING_REASON_LABELS_TR`
(codes: `match_not_tracked, lineup_not_observed, team_not_in_local_db, no_finished_matches_before_kickoff,
no_player_match_data, partial_player_match_data, did_not_appear, availability_not_observed,
team_scored_no_goals, team_xg_unavailable, player_goals_unavailable, player_xg_unavailable,
team_minutes_unavailable, squad_not_observed, team_not_found`; several can be comma-joined).

## 5. Jobs

### 5.1 Cron / manual: `scripts/live/refresh_team_news.py --once`

```bash
cd backend
venv/Scripts/python.exe scripts/live/refresh_team_news.py --once --database-url sqlite:///./football_intelligence.db --allow-production-db
#   --hours-ahead 72 --lookback-hours 24 --squads {none,window,all} --max-requests 800
#   --competitions 47,42 --no-fixtures --no-finished --no-raw
#   --match-id 6106260 / --team-id 9825 / --player-id 955406   (targeted refresh)
```

One cycle: discover target matches (local DB + league fixtures, cached 1 h) → refresh every scheduled
match kicking off within the window (snapshot + match lists) → ingest player stats of matches finished
within the lookback (until one fetch ≥ 6 h after kickoff) → squads (`window` = teams of the upcoming
matches, `all` = every team in the competitions' fixtures). Exit codes: 0 ok, 2 HTTP 429 (shared
cool-down set), 3 FotMob 403/captcha/challenge (stop, do not retry, report), 4 tables missing.
`--database-url` is required; the production file additionally needs `--allow-production-db`.

### 5.2 In-API loop (optional): `TEAM_NEWS_REFRESH_ENABLED=true`

Started in the FastAPI lifespan only when enabled (default **off**) and only when the tables exist
(otherwise an error is logged and the API starts normally). Ticks every 60 s:

| Work | Cadence (settings) |
|---|---|
| squads of every team in the target competitions | every 6 h (`TEAM_NEWS_SQUAD_REFRESH_HOURS`) |
| matches kicking off within 72 h (`TEAM_NEWS_HOURS_AHEAD`) | every 15 min (`TEAM_NEWS_MATCH_REFRESH_MINUTES`), every 5 min within 2 h of kickoff (`TEAM_NEWS_NEAR_KICKOFF_*`) |
| matches finished in the last 24 h (`TEAM_NEWS_FINISHED_LOOKBACK_HOURS`) | every 30 min (`TEAM_NEWS_FINISHED_REFRESH_MINUTES`) until settled |

DB work runs in worker threads (one session per unit of work), never on the event loop. A 403, a
captcha/challenge page (also a non-JSON 200) stops the loop for the process lifetime (logged as ERROR);
a plain 5xx error page or a 429 only fails the request / skips the rest of the tick. One failing match or
squad is logged and counted (`errors`) without stopping the cycle. The first tick after start-up does
everything that is due (≈ 13 fixture lists + 60–100 matches + ~300 squads ≈ 6–7 min at 1 request/s);
later ticks only fetch what is due. Use either the loop or the cron job, not both.

### 5.3 Politeness and raw archive

* In-process pacing ≥ 1 s between requests across all clients of the process
  (`TEAM_NEWS_FOTMOB_MIN_INTERVAL_SECONDS`, floor 1 s), one request in flight, plus
  `scripts/data_collection/fotmob_rate.py` `acquire_async()` before every request (retries included);
  429 → `report_429(Retry-After or 60)`; DNS/connect errors: 2 retries (3 s, 6 s). User-Agent of the
  training collectors.
* Short response caches: matchDetails 60 s (0 for finished-match ingest), teams 10 min, players 1 h,
  league fixtures 1 h.
* Raw bodies whose relevant parsed content changed are kept gzip'ed (atomic) under
  `backend/data/raw_cache/live_team_news/<kind>/<id>/<stamp>.json.gz` with `_manifest.jsonl`
  (README in that directory). `TEAM_NEWS_KEEP_RAW=false` disables it.

### 5.4 Live verification run

One `--once` cycle on the backfilled DB copy (2026-10-13 18:57–19:00 UTC, `--squads window`, build of
18:57; later changes — empty squad lists, profile-source bookkeeping, 5xx handling — are covered by unit
tests): 189 FotMob requests (13 league fixture lists, 58 upcoming matches, 2 finished matches,
116 squads) in 3 min 18 s, 0 errors, 0 HTTP 429/403; 47 of the 58 upcoming matches had a line-up
(`standard` for the 19:00 UCL matches ~1 h before kickoff, `predicted` for the next day,
`lastStarting11` placeholders further out), 3,358 squad members and 306 squad injuries written, 176 raw
bodies archived. `build_team_news` then answers in ~20 ms (warm) for Arsenal–Lille and Manchester
City–PSG with real last-5 form, absentees with shares and per-source freshness. A targeted run
(`--match-id 6106254 --team-id 9847 --player-id 1574189`, 3 requests) confirmed the profile path
(injury id 69 resolved to "Thigh injury" by the player profile).

## 6. Backfill: `scripts/live/load_player_data.py`

```bash
cd backend
venv/Scripts/python.exe scripts/live/load_player_data.py --database-url sqlite:///C:/path/copy.db [--only matches|teams|players] [--include-live]
```

Idempotent import of the raw caches (only manifest-listed files; unreadable files and partial manifest
lines are skipped and counted): `fotmob_match_details` (index `data/training/fotmob_match_details.jsonl`
with the collector's `fetched_at`) → player_match_stats, lineup snapshots, match-time availability
(`timestamp_basis = match_kickoff`), registry; `fotmob_teams` + `fotmob_players` (`_manifest.jsonl`
`fetched_at`, `http_status == 200`) → players, squads, current availability. One commit per 200 files; an
unexpected DB error replays the batch without the failing file.

**Run on a copy of the production DB (2026-10-13, 19:02 UTC, after `alembic stamp` + `upgrade` on the copy):**

| Step | Files | OK | Unreadable / payload errors / DB errors | Seconds |
|---|---|---|---|---|
| `fotmob_match_details` (dataset index) | 6,798 | 6,798 | 0 / 0 / 0 | 176.9 |
| `fotmob_teams` (manifest, http 200) | 231 | 231 | 0 / 0 / 0 | 5.3 |
| `fotmob_players` (manifest, http 200; collection still running) | 5,105 | 5,105 | 0 / 0 / 0 | 13.7 |
| **total** | | | | **196.7** |

Rows written: `players` 13,607 (5,105 with a full player profile; 6,007 with a market value, 4,572 of
them with a valuation date; 6,771 with a current team), `team_squad_members` 6,771 (219 teams with season
"2026/2027" + 10 calendar-year teams with season "2026"; the other 2 of the 231 team files, Shakhtar
Donetsk 9728 and Sabah FK 951893, carry an empty squad list), `player_availability` 19,182 (match-time
lists stamped at kickoff: injured 15,333, suspended
2,184, international duty 461; squad injuries 662; profile injuries 542), `player_match_stats` 284,163
(= the 284,163 player rows of `README_fotmob_details.md`; 211,060 appearances, 149,556 starts, all rows
linked to `matches`; 20 competitions incl. Set B), `lineup_snapshots` 13,596 (2 per match, all
`standard`, basis `match_kickoff`), `team_news_matches` 6,798. A second run (121 s, players preloaded) changed no
match-derived, squad or match-list row (284,163 / 13,596 / 6,771 / 17,978 again); its only additions came
from 273 player files the squads-players collector wrote in between (+35 profile injury rows). Earlier
full runs with previous builds took 274–295 s on a busier machine.

## 7. Apply / restart (lead, after tonight's matches)

The production DB (`backend/football_intelligence.db`) was created with `create_all()` and has **no
`alembic_version` table**. A schema comparison of a copy stamped at `20261013_pv_index_align` and upgraded
to `20261013_team_news` shows **zero differences** against the ORM models, so:

```bash
cd backend
# 0. stop the API (supervisor) and back up the DB
cp football_intelligence.db football_intelligence.db.bak-$(date +%Y%m%d%H%M)
# 1. mark the current schema, then apply the live-layer revision
venv/Scripts/python.exe -m alembic stamp 20261013_pv_index_align
venv/Scripts/python.exe -m alembic upgrade head        # adds 5 tables + 11 players columns (~0.3 s)
# 2. optional: backfill from the raw caches (~3-5 min, idempotent; the SQLite file grows from ~87 MB to ~375 MB)
venv/Scripts/python.exe scripts/live/load_player_data.py --database-url sqlite:///./football_intelligence.db --allow-production-db
# 3. either enable the in-API loop ...
#    backend/.env:  TEAM_NEWS_REFRESH_ENABLED=true
#    ... or schedule the cron job every 15 min:
#    venv/Scripts/python.exe scripts/live/refresh_team_news.py --once --database-url sqlite:///./football_intelligence.db --allow-production-db
# 4. restart the API (scripts/run_api.py under the supervisor)
```

Before the migration the app still imports and serves everything; the two new endpoints answer 503
`team_news_not_migrated`, and the loop refuses to start. Rollback: `alembic downgrade 20261013_pv_index_align`
(drops the 5 tables and the 11 player columns) or restore the backup.

## 8. Tests

`backend/tests/test_team_news_*.py` (SYNTHETIC fixtures in `test_team_news_fixtures.py`, no network, scratch
DBs): parsers (+ one format check against a real raw file when present), store/apply rules (clearing,
superseding, stale observations, idempotency, merge rules), async services with a mock transport (cycle,
due checks, 403/429/challenge handling), the refresh loop cadence and start/stop, read model (form, zero
rule, shares, point-in-time view), endpoints (200/404/503), scripts (idempotent backfill, production guard),
migration upgrade/downgrade with an autogenerate diff of zero.

## 9. Known gaps / caveats

* Squads carry injuries only (no suspensions); suspensions come from match lists. Player profiles are
  fetched by the backfill/targeted refresh, not by the loop (≈ 7,800 players would cost too many requests).
* `doubtful` was never observed in FotMob payloads so far; the status exists for completeness.
* Injury codes (`injury_id`) are not mapped to names except where a player profile sends `name`.
* `recentMatches` of player profiles (other competitions, national teams) is not ingested; form is computed
  from matchDetails of matches in `matches` only, so cup matches without collected details lower
  `matches_with_data`.
* `fotmob_rate._Lock` can raise `PermissionError` on Windows when another process removes the lock
  directory at the same moment (not `FileExistsError`); the team-news client retries, the shared module
  itself does not.
* DNS lookups of www.fotmob.com fail intermittently on this machine; the client retries connect errors
  twice.
