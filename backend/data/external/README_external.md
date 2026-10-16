# External training data (non-FotMob)

Collected 2026-10-13 by `backend/scripts/data_collection/collect_football_data.py` and
`collect_clubelo.py` (run from `backend/` with `venv/Scripts/python.exe -I ...`). Both scripts
cache every download under `raw/` and can be re-run; re-runs reuse the cache (2526 files,
ClubElo club histories) unless `--refresh-current` / `--refresh` is passed.
Our DB is opened read-only (`sqlite3 file:...?mode=ro`).

Past seasons (2021/22 to 2025/26, 14 divisions) are a separate dataset mapped to **FotMob match
ids**: `collect_football_data.py --history` (logic in `football_data_history.py`) writes
`football_data_history*.{csv,json}` and never rewrites `football_data_matches.csv`. See
[Past seasons mapped to FotMob](#past-seasons-mapped-to-fotmob-football_data_historycsv).

Everything in this folder is real third-party data. Nothing is generated or imputed: a missing
value is an empty cell, and a team that could not be matched with enough confidence has an
empty `db_team_id` and is listed in `team_name_unmapped.csv`.

## Sources and terms

| Source | What | Terms / licence notes |
|---|---|---|
| football-data.co.uk (Joseph Buchdahl) | Results, match stats, pre-match and closing odds per division and season | Free download for personal, non-commercial use; credit football-data.co.uk; no redistribution as a product. We made about 60 requests and cache the files. |
| Internet Archive (web.archive.org) | Archived copies of the football-data.co.uk CSV URLs | Used only because football-data.co.uk itself is unreachable from this network (see below). Each file records its Wayback snapshot timestamp in `raw/football_data/manifest.json`. The history build also uses the archive's CDX index (one listing per season) and two archived season bundles (`2223/data.zip`, `2324/all-euro-data-2023-2024.xlsx`); about 76 archive requests in total, at most 1 per 1.5 s. |
| FotMob league fixture lists (`/api/data/leagues?id=<league>&season=<YYYY/YYYY>`) | Fixture id, teams, UTC kick-off and score of every league match, used only to map past-season rows to FotMob match ids | Shared cache `backend/data/raw_cache/fotmob_leagues/` (untouched gzip bodies). All 70 league-seasons needed were already cached by another collector on 2026-10-13, so the history build made **0 FotMob requests**; missing ones would be fetched one at a time through the shared limiter `fotmob_rate.py`. |
| ClubElo (clubelo.com, Lars Schiefler) | Club Elo ratings, Golo rating, published 1/X/2 for upcoming games | Free, public site; no formal licence published on the site. Credit ClubElo; keep request volume low. We made 3 page requests plus 1 per club history. |

### Network constraints found on 2026-10-13 (important)

- `www.football-data.co.uk` answers with a redirect to `football-data.co.uk`, whose server
  (217.160.0.246) never accepts the connection from this machine (TCP timeout on ports 80 and 443).
  The scripts try the origin first and then fall back to the Internet Archive copy of the
  same URL. **An archived file is only as fresh as its snapshot** (see the manifest and the
  coverage table): several 2025/26 files were archived before the season ended, and every 2026/27
  file stops at its snapshot date.
- `api.clubelo.com` (the CSV API, 37.128.134.74) also times out, and the website's dated pages
  (`/YYYY-MM-DD`) now redirect to the homepage. The website itself works, so we use:
  `/Ranking` (every rated club today), the homepage and `/Fixtures` (ClubElo's own 1/X/2 for
  upcoming games) and `/<ClubSlug>` (the club's full weekly Elo history, embedded as chart data).
  Consequence: instead of ~66 weekly all-club snapshots we have **one all-club snapshot for
  2026-10-13** plus **weekly histories for a selected set of clubs** (the 18 clubs of the
  2026-10-13 UCL fixtures plus the highest-rated level-1 clubs of ENG/ESP/GER/ITA/FRA/TUR, capped
  by `--max-clubs`). Raise the cap or add `--countries` to collect more (about 10 s per club).

## Files

| File | Rows | Content |
|---|---:|---|
| `football_data_matches.csv` | 10,611 | One row per football-data.co.uk match from 2025-07-01 on. Fixed columns: `date, time, division, country, league, season, home, away, home_db_team_id, away_db_team_id`, `db_match_id` (the DB match between the same two teams within +-1 day), `db_competition_name/provider_id, db_score_agrees, FTHG, FTAG, FTR`. Half-time score and match stats follow (`HTHG HTAG HTR HS AS HST AST HF AF HC AC HY AY HR AR Referee`; main leagues only), then the normalised probabilities, then all 122 original odds columns under their original names. |
| `football_data_coverage.json` | - | The per-division counts behind the coverage table below. |
| `clubelo_snapshots.csv` | 3,406 | `date, club, club_slug, country, level, elo, golo, db_team_id, source`. Rows with `source=ranking_page_current` hold all 1,727 rated clubs on 2026-10-13; the page rounds Elo to an integer. Rows with `source=club_history_weekly` hold the Elo (float) on each match date since 2025-07-01 for 29 clubs. `level` is the club's current level from the site, empty when the site shows none. `golo` is ClubElo's goal-based rating. |
| `clubelo_ucl_2026-10-13.csv` | 9 | The nine UCL fixtures of 2026-10-13: each club's latest Elo, the raw Elo expectation without home advantage, ClubElo's published 1/X/2 and the home advantage those numbers imply. |
| `team_name_map.csv` | - | `source, source_name, source_context, db_team_id, db_team_provider_id, db_team_name, method, confidence, evidence`. Rows with `source=football_data_fotmob` (355) map football-data names of the history build to **FotMob team ids** (`db_team_provider_id`); there `db_team_id` is filled only when that FotMob team also exists in our DB (340 of 355) and `db_team_name` is FotMob's current name of the team. |
| `team_name_unmapped.csv` | - | Every source team left unmapped, with its best candidate and the reason (no `football_data_fotmob` row: every history name was mapped). |
| `football_data_history.csv` | 25,201 | One row per football-data.co.uk match of 2021/22 to 2025/26 in 14 divisions, with FotMob match/team ids, a score check and the closing and pre-closing odds. See the section below. |
| `football_data_history_unmapped.csv` | 6 | The rows without a FotMob match id, with the reason and the nearest FotMob fixture of the same pair. |
| `football_data_history_coverage.json` | - | Per division-season numbers of the history build (file used, snapshot, rows, mapping, score check, odds availability, team-mapping methods), the FotMob cache report and a markdown table (`_markdown`). |

### Normalised probabilities (football_data_matches.csv)

- `p_close_home/draw/away`: the bookmaker margin is removed by proportional normalisation, `p_i = (1/o_i) / sum_j(1/o_j)`. The odds come from the first complete set in this order: Pinnacle closing (`PSCH/PSCD/PSCA`), market-average closing (`AvgCH/...`), Bet365 closing (`B365CH/...`). `close_1x2_source` names the set used and `close_1x2_overround` holds the margin.
- `p_close_over25/under25`: the same method, from `PC>2.5/PC<2.5`, then `AvgC>2.5/AvgC<2.5`, then `B365C>2.5`. The "new leagues" files (ARG AUT BRA CHN DNK FIN) carry no O/U odds, so these cells are empty for them.
- `p_pre_*`: the same for pre-closing odds (`PSH`, `AvgH`, `B365H`), main leagues only.
- Many rows have no Pinnacle closing columns, so the market average is used instead: `AvgCH` 6,885 rows, `PSCH` 3,725 rows and 1 row with no closing 1X2.

### Odds columns present (original names)

- **Main leagues, before closing:**
  - 1X2: `B365 BFD BMGM BV BW CL LB PS Max Avg BFE` + `H/D/A`.
  - O/U 2.5: `B365 P Max Avg BFE` + `>2.5/<2.5`.
  - Asian handicap: `AHh`, `B365AHH/A PAHH/A MaxAHH/A AvgAHH/A BFEAHH/A`.
- **Main leagues, closing:** the closing version of every column above (`...C...`, e.g. `PSCH`, `PC>2.5`, `AHCh`, `PCAHH`).
- **New-league files:** closing odds only: `PSCH/D/A, MaxCH/D/A, AvgCH/D/A, BFECH/D/A`, plus `B365CH/D/A` where present.

The full list is in `football_data_coverage.json -> _total.odds_columns`.

## Team-name matching

- **football-data.co.uk to DB, by fixture overlap.** Each source result (date, score) is compared with the DB matches that have the same score within +-1 day. The source home team votes for each of their DB home teams and the source away team for each DB away team. The real team collects about one vote per match; any other team collects only a few scattered votes.
  - A name is accepted when it has at least 3 votes, votes / matches is at least 0.5 and the runner-up has at most half the top votes. Matching runs per country, over all divisions and seasons together.
  - Result: 530 names mapped, nearly all with 100% of their results matching. **8 are unmapped**: newly promoted teams with only 1 to 5 results in the archived 2026/27 files (Ascoli, Benevento, Vicenza, Academico Viseu, Maritimo, Amedspor, Corum, Iraklis). Their matches stay in the table with an empty DB id.
- **ClubElo to DB, by name.**
  - The candidate pool for a club is the set of DB teams that played in its country's league competitions. Those competitions are taken from the football-data rows linked to DB matches.
  - Normalisation: lower case, accents removed (Turkish letters included), generic tokens (FC, SC, AFC, CF, AC, FK, SK, ...) dropped. A manual alias table in `collect_clubelo.py` and the verified football-data names are used as extra variants.
  - A match is accepted at similarity >= 0.86 with a lead of at least 0.08 over the runner-up. When a club has no pool, or is not found in its pool, only a unique exact normalised name among all senior DB teams is accepted (confidence 0.8).
  - Reserve, youth and women sides are never mapped automatically. A DB team claimed by two clubs stays unmapped for both.
  - Result: **1,093 of 1,727 ClubElo clubs mapped, 634 unmapped**, most of them in countries the DB covers thinly. Of the 18 clubs in the UCL fixtures, Sabah FK and Slavia Praha are unmapped.

## Coverage of football-data.co.uk matches against our DB (by date + both teams)

DB range: 2025-07-01 .. 2026-10-12.
- "Linked": a DB match between the same two DB teams within +-1 day.
- "Score agrees": the DB final score equals FTHG-FTAG.
- The last column is the Wayback snapshot date of each file.

| Division | Country | League | Rows | In DB range | Linked to DB match | % linked | Score agrees | Close 1X2 | Close O/U 2.5 | Archive snapshots (2526 / 2627 or new) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| ARG | ARG | Argentina Liga Profesional | 659 | 659 | 659 | 100.0 | 654 | 659 | 0 | 20261005 |
| AUT | AUT | Austria Bundesliga | 234 | 234 | 234 | 100.0 | 234 | 234 | 0 | 20261005 |
| B1 | BEL | Jupiler Pro League | 365 | 365 | 365 | 100.0 | 365 | 365 | 365 | 20261005 / 20260921 |
| BRA | BRA | Brazil Serie A | 541 | 541 | 537 | 99.3 | 537 | 541 | 0 | 20261005 |
| CHN | CHN | China Super League | 320 | 320 | 320 | 100.0 | 320 | 320 | 0 | 20261011 |
| D1 | GER | Bundesliga | 342 | 342 | 342 | 100.0 | 342 | 342 | 342 | 20260829 / 20261005 |
| D2 | GER | 2. Bundesliga | 306 | 306 | 306 | 100.0 | 306 | 306 | 306 | 20260921 / unavailable |
| DNK | DEN | Denmark Superliga | 246 | 246 | 245 | 99.6 | 245 | 246 | 0 | 20261005 |
| E0 | ENG | Premier League | 420 | 420 | 420 | 100.0 | 420 | 420 | 420 | 20261006 / 20260921 |
| E1 | ENG | Championship | 635 | 635 | 635 | 100.0 | 635 | 635 | 635 | 20260714 / 20260921 |
| E2 | ENG | League One | 612 | 612 | 612 | 100.0 | 612 | 612 | 612 | 20260714 / 20260914 |
| E3 | ENG | League Two | 654 | 654 | 654 | 100.0 | 654 | 654 | 654 | 20260714 / 20261005 |
| EC | ENG | National League | 672 | 672 | 671 | 99.9 | 671 | 672 | 672 | 20260714 / 20260928 |
| F1 | FRA | Ligue 1 | 351 | 351 | 350 | 99.7 | 350 | 351 | 351 | 20260829 / 20260928 |
| F2 | FRA | Ligue 2 | 322 | 322 | 322 | 100.0 | 322 | 322 | 322 | 20260412 / 20261005 |
| FIN | FIN | Finland Veikkausliiga | 254 | 254 | 248 | 97.6 | 248 | 254 | 0 | 20261011 |
| G1 | GRE | Super League | 227 | 227 | 221 | 97.4 | 221 | 227 | 227 | 20260412 / 20260928 |
| I1 | ITA | Serie A | 430 | 430 | 430 | 100.0 | 430 | 430 | 430 | 20260829 / 20260928 |
| I2 | ITA | Serie B | 379 | 379 | 362 | 95.5 | 362 | 379 | 379 | 20260412 / 20261005 |
| N1 | NED | Eredivisie | 369 | 369 | 369 | 100.0 | 369 | 369 | 369 | 20261005 / 20261005 |
| P1 | POR | Liga Portugal | 241 | 241 | 239 | 99.2 | 239 | 240 | 240 | 20260316 / 20260813 |
| SC0 | SCO | Premiership | 222 | 222 | 222 | 100.0 | 222 | 222 | 222 | 20260316 / 20261005 |
| SC1 | SCO | Championship | 200 | 200 | 200 | 100.0 | 200 | 200 | 200 | 20260412 / 20261005 |
| SC2 | SCO | League One | 159 | 159 | 159 | 100.0 | 159 | 159 | 159 | 20260412 / unavailable |
| SC3 | SCO | League Two | 160 | 160 | 159 | 99.4 | 159 | 160 | 160 | 20260412 / unavailable |
| SP1 | ESP | La Liga | 400 | 400 | 400 | 100.0 | 400 | 400 | 400 | 20260714 / 20260829 |
| SP2 | ESP | Segunda Division | 549 | 549 | 549 | 100.0 | 549 | 549 | 549 | 20260829 / 20261005 |
| T1 | TUR | Super Lig | 342 | 342 | 334 | 97.7 | 334 | 342 | 342 | 20260901 / 20260914 |
| **Total** | | | 10611 | 10611 | 10564 | 99.6 | 10559 | 10610 | 8356 | |


All 10,611 source rows fall inside the DB date range, and **10,564 (99.6%) are linked to a DB match**. Of those, 10,559 have the same score. The other 5 disagree; they are kept unchanged and flagged `db_score_agrees=0`.

## Gaps and caveats

- **Freshness.** Every file is an Internet Archive snapshot (last column of the table).
  - Some 2025/26 files were archived before the season ended and are incomplete: P1 and SC0 (2026-03-16); SC1, SC2, SC3, G1, I2 and F2 (2026-04-12).
  - The 2026/27 files stop between 2026-08-13 (P1) and 2026-10-05.
  - No archived 2026/27 file exists for D2, SC2 or SC3.
- **Not downloaded.** The run was stopped at the time limit before the new-league files IRL JPN MEX NOR POL ROU RUS SWE SWZ USA. Re-run `collect_football_data.py` to fetch them; the cache lets it resume where it stopped.
- **Refresh.** When the origin server becomes reachable, run `collect_football_data.py --refresh-current` to replace the archived 2026/27 files.
- **ClubElo has no weekly all-club snapshots** because the API is unreachable. We have today's snapshot for every club and histories for 29 clubs only.
  - Sabah FK's club page has no history we could parse, so its Elo is the current ranking value (2026-10-13, integer).
  - For more histories, run `collect_clubelo.py --max-clubs 200 --countries ENG,ESP,GER,ITA,FRA,TUR,POR,NED,BEL` (about 10 s per club, cached).
- **ClubElo `level`** is the club's level today, not at the historical date.
- **ClubElo coverage** is mostly Europe plus a growing set of other countries. A club outside it has no Elo, and the missing value must not be read as a zero rating.

## Past seasons mapped to FotMob (football_data_history.csv)

Built 2026-10-13 by `collect_football_data.py --history` (code: `football_data_history.py`). It covers the
seasons **2021/22, 2022/23, 2023/24, 2024/25 and 2025/26** for 14 divisions: E0 SP1 I1 D1 F1 N1 P1 B1 T1
(top) and E1 SP2 I2 D2 F2 (second tier). Purpose: closing odds for models trained on 2022-2025 data,
so they can be benchmarked against the closing market. These seasons are not in our DB, so rows carry
**FotMob ids** (`fotmob_match_id` = FotMob match id = `matches.provider_id` in the DB once a match is
imported) instead of DB ids. `football_data_matches.csv` is left as it is; the 2025/26 rows of this file
overlap it (see the DB check below).

```bash
cd backend
venv/Scripts/python.exe -I scripts/data_collection/collect_football_data.py --history                  # resumable download + build
venv/Scripts/python.exe -I scripts/data_collection/collect_football_data.py --history --skip-download  # offline rebuild from raw/
venv/Scripts/python.exe -I scripts/data_collection/football_data_history.py --checks-only --spot-check 20 --db-check
```

### Sources and raw files

- **Season files.** `mmz4281/<2122..2425>/<div>.csv`, fetched from the Internet Archive because the origin
  times out. The archive's CDX index is listed once per season (`raw/football_data/cdx/<season>.json.gz`)
  and the newest replayable capture of each file is downloaded unchanged into
  `raw/football_data/<season>/<div>.csv.gz` (gzip, written atomically). A file is called complete when it has
  at least n_teams x (n_teams - 1) matches (a full double round robin). When it is not, newer captures are
  tried; the archive sometimes serves an older capture than the one requested (2023/24 E0: both the
  2024-09-10 capture and its 2026-07-14 re-capture replay the partial 2024-01-03 file).
- **Season bundles.** When a division stays incomplete, the archived season bundles are used: `data.zip` (every
  division CSV) and `all-euro-data-YYYY-YYYY.xlsx` (one sheet per division, read with the standard library;
  Excel date serials and day fractions are turned back into `dd/mm/yyyy` and `HH:MM`). Used:
  `2223/data.zip` (snapshot 2026-04-04) for I2 and F2, and `2324/all-euro-data-2023-2024.xlsx` (2025-01-28) for
  E0, I2 and F2. Check: in the 27 division files that exist both as CSV and inside a bundle, the 9,577 common
  rows are identical in all 1,007,266 cells (every column, including `Time` and all odds) except one referee
  name that football-data corrected between the two versions. The 2024/25 xlsx (2025-01-11) is older than the
  partial P1 file and was not downloaded.
- **2025/26 re-check.** The files behind `football_data_matches.csv` (`raw/football_data/2526/<div>.csv`) were
  compared with a fresh CDX listing on 2026-10-13. For the three still-partial files (P1, I2, F2) the archive was
  also asked for its capture closest to now, because the CDX index lags behind what the archive can replay.
  **No later capture exists for any of the 14 files**, and no 2025/26 bundle is archived; the manifest keys
  `2526_latest/<div>` record the check. A later capture with more rows would be stored as
  `raw/football_data/2526_latest/<div>.csv.gz` and used automatically.
- **Manifest.** `raw/football_data/manifest.json` holds, per key `<season>/<div>`, `<season>/bundle/<name>` and
  `2526_latest/<div>`: URL, served Wayback snapshot, requested CDX timestamp, digest, rows, date range,
  completeness and the captures already tried.
- **FotMob fixture lists.** `backend/data/raw_cache/fotmob_leagues/<league>_<YYYY-YYYY>.json.gz` for league ids
  47, 87, 55, 54, 53, 57, 61, 40, 71, 48, 140, 86, 146, 110 and seasons 2021/2022 to 2025/2026. A cached file is
  used only when its `details.id` and `details.selectedSeason` equal the requested league and season (70/70 did).

### Mapping (nothing is guessed)

1. **Team names, per division-season.**
   - Anchors: the verified `football_data` -> DB map above (DB `teams.provider_id` is the FotMob team id). An anchor
     is kept only when that FotMob team plays in the league-season and at least 90% of its matches against other
     anchors are found as exact FotMob (home, away) pairs within +-1 day.
   - Other names: opponent-consistent votes. A match against an already mapped opponent points at the FotMob team
     that met that opponent at the same venue within +-1 day. A name is accepted with at least 3 votes, at least
     80% of its considered matches and a runner-up of at most 25% of the top votes.
   - A score-based fixture overlap exists as a last resort; it was not needed.
   - Final check for every name: at least 90% of its matches must be found as exact FotMob pairs.
   - Result: 355 (country, name) -> FotMob id rows in `team_name_map.csv` (`source=football_data_fotmob`): 285
     anchors and 70 by opponent votes. No name has two ids and no id has two names. Lowest name similarities,
     all with full fixture agreement: FeralpiSalo -> Union Brescia (FotMob shows the club's current name), Belenenses
     -> Cova da Piedade SAD (B-SAD), RWD Molenbeek -> RWDM Brussels.
2. **Rows.** The FotMob fixture of the mapped (home id, away id) pair within +-1 day of the football-data date.
   Exactly one candidate is required, and one FotMob fixture can back only one row. **Scores are never used to
   pick a row**; `score_agrees` compares them afterwards.

### Columns of football_data_history.csv

| Column | Meaning |
|---|---|
| `season, division, country, league` | football-data season code (`2122` = 2021/22) and division |
| `fotmob_league_id, fotmob_season` | the FotMob league-season matched against (`2021/2022`) |
| `fd_file, fd_snapshot` | the source used (manifest key: `<season>/<div>`, `<season>/bundle/<name>#<div>` or `2526_latest/<div>`) and its Wayback snapshot |
| `fd_file_complete` | 1 when the source file holds a full season (at least n_teams x (n_teams - 1) matches, a full double round robin), **0 = partial season file** (archived before the season ended: P1 2024/25 and P1, I2, F2 2025/26, 982 rows). The same list is in `football_data_history_coverage.json -> _total.partial_division_seasons` |
| `date, time, home, away, FTHG, FTAG, FTR` | as in the football-data file (`date` ISO; `time` is UK time) |
| `map_status` | `mapped`, `no_fixture` (no FotMob fixture of the pair within +-1 day), `unmapped_team`, `ambiguous`, `no_fotmob_fixture_list` |
| `fotmob_match_id, fotmob_home_id, fotmob_away_id` | FotMob ids of the matched fixture; empty when not mapped |
| `fotmob_home_name, fotmob_away_name, fotmob_utc_time, fotmob_round` | from the fixture list (FotMob shows a club's current name) |
| `fotmob_home_score, fotmob_away_score, fotmob_awarded` | parsed from `status.scoreStr`; `fotmob_awarded` is FotMob's `status.awarded` (1 = awarded result, 0 = not awarded) and stays **empty when FotMob sends no flag** (1 row: the abandoned Troyes v Valenciennes, see the gaps below) |
| `score_agrees` | 1 when the FotMob score equals FTHG-FTAG, 0 when not, empty when either score is missing |
| `close_1x2_*`, `close_ou25_*`, `pre_1x2_*`, `pre_ou25_*` | source column used, margin-free probabilities and overround. Same method as `football_data_matches.csv`: proportional normalisation of the first complete set among Pinnacle, market average, Bet365. Pre-closing O/U 2.5 (new here) uses `P>2.5`, `Avg>2.5`, `B365>2.5` in that order |
| 30 original odds columns | `PSCH PSCD PSCA AvgCH AvgCD AvgCA B365CH B365CD B365CA`, `PC>2.5 PC<2.5 AvgC>2.5 AvgC<2.5 B365C>2.5 B365C<2.5`, `PSH PSD PSA AvgH AvgD AvgA B365H B365D B365A`, `P>2.5 P<2.5 Avg>2.5 Avg<2.5 B365>2.5 B365<2.5`, unchanged; empty when the file has no value. 13 cells in 5 rows hold football-data placeholders instead of odds (`0` in O/U columns of Newcastle v Man City 2021-12-19, Bayern Munich v M'gladbach 2025-05-10, Paris SG v Le Havre 2025-04-19, Barcelona v Girona 2025-10-18; `#` in `B365CH` of Utrecht v Feyenoord 2023-01-08). They are kept as sent and never used for probabilities (only odds > 1 count), so treat values <= 1 or non-numeric as missing |

### Coverage per division-season

- "Mapped" is the share of football-data rows with a FotMob match id.
- "Score agrees" counts mapped rows with both scores.
- "FotMob matches w/o row" are finished FotMob fixtures that no football-data row maps to.
- "Source, snapshot" is the file used and its Wayback snapshot date; **partial** marks a season file archived before
  the season ended (`fd_file_complete=0`).

| Season | Div | FotMob id | Rows | Mapped | Score agrees | Close 1X2: PS / Avg / B365 | Close O/U 2.5 | Pre 1X2 / O/U | FotMob matches w/o row | Source, snapshot |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---|
| 21/22 | E0 | 47 | 380 | 380 (100.0%) | 380/380 (100.0%) | 380 / 0 / 0 | 380 | 380 / 380 | 0 | csv 2024-01-03 |
| 21/22 | SP1 | 87 | 380 | 380 (100.0%) | 380/380 (100.0%) | 380 / 0 / 0 | 380 | 380 / 380 | 0 | csv 2023-09-22 |
| 21/22 | I1 | 55 | 380 | 380 (100.0%) | 380/380 (100.0%) | 380 / 0 / 0 | 380 | 379 / 379 | 0 | csv 2024-01-19 |
| 21/22 | D1 | 54 | 306 | 306 (100.0%) | 306/306 (100.0%) | 306 / 0 / 0 | 306 | 306 / 306 | 0 | csv 2024-06-12 |
| 21/22 | F1 | 53 | 380 | 380 (100.0%) | 380/380 (100.0%) | 380 / 0 / 0 | 380 | 380 / 380 | 0 | csv 2025-10-24 |
| 21/22 | N1 | 57 | 306 | 306 (100.0%) | 306/306 (100.0%) | 306 / 0 / 0 | 306 | 306 / 306 | 6 | csv 2025-03-21 |
| 21/22 | P1 | 61 | 306 | 306 (100.0%) | 306/306 (100.0%) | 306 / 0 / 0 | 306 | 306 / 306 | 0 | csv 2025-01-22 |
| 21/22 | B1 | 40 | 306 | 306 (100.0%) | 306/306 (100.0%) | 306 / 0 / 0 | 306 | 306 / 306 | 24 | csv 2025-10-24 |
| 21/22 | T1 | 71 | 380 | 380 (100.0%) | 380/380 (100.0%) | 379 / 1 / 0 | 380 | 380 / 380 | 0 | csv 2025-04-13 |
| 21/22 | E1 | 48 | 552 | 552 (100.0%) | 552/552 (100.0%) | 552 / 0 / 0 | 552 | 552 / 552 | 5 | csv 2024-01-03 |
| 21/22 | SP2 | 140 | 462 | 462 (100.0%) | 462/462 (100.0%) | 462 / 0 / 0 | 462 | 462 / 462 | 6 | csv 2025-03-21 |
| 21/22 | I2 | 86 | 380 | 380 (100.0%) | 380/380 (100.0%) | 380 / 0 / 0 | 380 | 380 / 380 | 10 | csv 2024-02-04 |
| 21/22 | D2 | 146 | 306 | 306 (100.0%) | 306/306 (100.0%) | 306 / 0 / 0 | 306 | 306 / 306 | 0 | csv 2024-06-11 |
| 21/22 | F2 | 110 | 380 | 380 (100.0%) | 380/380 (100.0%) | 380 / 0 / 0 | 380 | 380 / 380 | 0 | csv 2025-10-24 |
| 22/23 | E0 | 47 | 380 | 380 (100.0%) | 380/380 (100.0%) | 380 / 0 / 0 | 380 | 380 / 380 | 0 | csv 2026-07-14 |
| 22/23 | SP1 | 87 | 380 | 380 (100.0%) | 380/380 (100.0%) | 380 / 0 / 0 | 380 | 380 / 380 | 0 | csv 2023-09-22 |
| 22/23 | I1 | 55 | 380 | 380 (100.0%) | 380/380 (100.0%) | 380 / 0 / 0 | 380 | 380 / 380 | 1 | csv 2024-02-04 |
| 22/23 | D1 | 54 | 306 | 306 (100.0%) | 306/306 (100.0%) | 306 / 0 / 0 | 306 | 306 / 306 | 0 | csv 2024-06-11 |
| 22/23 | F1 | 53 | 380 | 380 (100.0%) | 380/380 (100.0%) | 380 / 0 / 0 | 380 | 380 / 380 | 0 | csv 2025-10-24 |
| 22/23 | N1 | 57 | 306 | 305 (99.7%) | 305/305 (100.0%) | 306 / 0 / 0 | 306 | 306 / 306 | 7 | csv 2025-03-21 |
| 22/23 | P1 | 61 | 306 | 306 (100.0%) | 306/306 (100.0%) | 306 / 0 / 0 | 306 | 306 / 306 | 0 | csv 2025-01-22 |
| 22/23 | B1 | 40 | 306 | 306 (100.0%) | 306/306 (100.0%) | 306 / 0 / 0 | 306 | 306 / 306 | 24 | csv 2025-10-25 |
| 22/23 | T1 | 71 | 342 | 337 (98.5%) | 337/337 (100.0%) | 313 / 0 / 0 | 313 | 313 / 313 | 5 | csv 2025-04-13 |
| 22/23 | E1 | 48 | 552 | 552 (100.0%) | 552/552 (100.0%) | 552 / 0 / 0 | 552 | 552 / 552 | 5 | csv 2024-01-03 |
| 22/23 | SP2 | 140 | 462 | 462 (100.0%) | 462/462 (100.0%) | 462 / 0 / 0 | 462 | 462 / 462 | 6 | csv 2025-03-21 |
| 22/23 | I2 | 86 | 380 | 380 (100.0%) | 380/380 (100.0%) | 380 / 0 / 0 | 380 | 380 / 380 | 10 | data.zip 2026-04-04 |
| 22/23 | D2 | 146 | 306 | 306 (100.0%) | 306/306 (100.0%) | 306 / 0 / 0 | 306 | 306 / 306 | 0 | csv 2024-06-11 |
| 22/23 | F2 | 110 | 380 | 380 (100.0%) | 380/380 (100.0%) | 380 / 0 / 0 | 380 | 380 / 380 | 0 | data.zip 2026-04-04 |
| 23/24 | E0 | 47 | 380 | 380 (100.0%) | 380/380 (100.0%) | 380 / 0 / 0 | 380 | 380 / 380 | 0 | xlsx 2025-01-28 |
| 23/24 | SP1 | 87 | 380 | 380 (100.0%) | 380/380 (100.0%) | 380 / 0 / 0 | 380 | 380 / 380 | 0 | csv 2025-12-31 |
| 23/24 | I1 | 55 | 380 | 380 (100.0%) | 380/380 (100.0%) | 380 / 0 / 0 | 380 | 380 / 380 | 0 | csv 2026-04-22 |
| 23/24 | D1 | 54 | 306 | 306 (100.0%) | 306/306 (100.0%) | 306 / 0 / 0 | 306 | 306 / 306 | 0 | csv 2024-06-11 |
| 23/24 | F1 | 53 | 306 | 306 (100.0%) | 306/306 (100.0%) | 306 / 0 / 0 | 306 | 306 / 306 | 0 | csv 2026-01-01 |
| 23/24 | N1 | 57 | 306 | 306 (100.0%) | 306/306 (100.0%) | 306 / 0 / 0 | 306 | 306 / 306 | 3 | csv 2026-01-01 |
| 23/24 | P1 | 61 | 306 | 306 (100.0%) | 306/306 (100.0%) | 306 / 0 / 0 | 306 | 306 / 306 | 0 | csv 2025-01-22 |
| 23/24 | B1 | 40 | 312 | 312 (100.0%) | 312/312 (100.0%) | 312 / 0 / 0 | 312 | 312 / 312 | 1 | csv 2026-02-18 |
| 23/24 | T1 | 71 | 380 | 380 (100.0%) | 380/380 (100.0%) | 380 / 0 / 0 | 380 | 380 / 380 | 0 | csv 2026-01-01 |
| 23/24 | E1 | 48 | 552 | 552 (100.0%) | 552/552 (100.0%) | 552 / 0 / 0 | 552 | 552 / 552 | 5 | csv 2026-07-14 |
| 23/24 | SP2 | 140 | 462 | 462 (100.0%) | 462/462 (100.0%) | 462 / 0 / 0 | 462 | 462 / 462 | 6 | csv 2025-12-31 |
| 23/24 | I2 | 86 | 380 | 380 (100.0%) | 380/380 (100.0%) | 380 / 0 / 0 | 380 | 379 / 379 | 10 | xlsx 2025-01-28 |
| 23/24 | D2 | 146 | 306 | 306 (100.0%) | 306/306 (100.0%) | 306 / 0 / 0 | 306 | 306 / 306 | 0 | csv 2024-06-13 |
| 23/24 | F2 | 110 | 380 | 380 (100.0%) | 379/380 (99.7%) | 380 / 0 / 0 | 380 | 380 / 380 | 0 | xlsx 2025-01-28 |
| 24/25 | E0 | 47 | 380 | 380 (100.0%) | 380/380 (100.0%) | 380 / 0 / 0 | 380 | 380 / 380 | 0 | csv 2025-12-31 |
| 24/25 | SP1 | 87 | 380 | 380 (100.0%) | 380/380 (100.0%) | 380 / 0 / 0 | 380 | 380 / 380 | 0 | csv 2025-12-31 |
| 24/25 | I1 | 55 | 380 | 380 (100.0%) | 380/380 (100.0%) | 380 / 0 / 0 | 380 | 380 / 380 | 0 | csv 2026-01-01 |
| 24/25 | D1 | 54 | 306 | 306 (100.0%) | 306/306 (100.0%) | 306 / 0 / 0 | 306 | 306 / 306 | 0 | csv 2026-02-07 |
| 24/25 | F1 | 53 | 306 | 306 (100.0%) | 306/306 (100.0%) | 306 / 0 / 0 | 306 | 306 / 306 | 0 | csv 2026-02-07 |
| 24/25 | N1 | 57 | 306 | 306 (100.0%) | 306/306 (100.0%) | 306 / 0 / 0 | 306 | 306 / 306 | 3 | csv 2026-01-01 |
| 24/25 | P1 | 61 | 162 | 162 (100.0%) | 162/162 (100.0%) | 162 / 0 / 0 | 162 | 162 / 162 | 144 | csv 2025-01-22, **partial** |
| 24/25 | B1 | 40 | 312 | 312 (100.0%) | 312/312 (100.0%) | 312 / 0 / 0 | 312 | 312 / 312 | 1 | csv 2026-02-18 |
| 24/25 | T1 | 71 | 342 | 342 (100.0%) | 342/342 (100.0%) | 342 / 0 / 0 | 342 | 342 / 342 | 0 | csv 2026-02-07 |
| 24/25 | E1 | 48 | 552 | 552 (100.0%) | 552/552 (100.0%) | 552 / 0 / 0 | 552 | 552 / 552 | 5 | csv 2025-12-31 |
| 24/25 | SP2 | 140 | 462 | 462 (100.0%) | 462/462 (100.0%) | 462 / 0 / 0 | 462 | 462 / 462 | 6 | csv 2026-03-08 |
| 24/25 | I2 | 86 | 380 | 380 (100.0%) | 379/380 (99.7%) | 380 / 0 / 0 | 380 | 380 / 380 | 9 | csv 2026-03-08 |
| 24/25 | D2 | 146 | 306 | 306 (100.0%) | 306/306 (100.0%) | 306 / 0 / 0 | 306 | 306 / 306 | 0 | csv 2026-03-08 |
| 24/25 | F2 | 110 | 306 | 306 (100.0%) | 306/306 (100.0%) | 306 / 0 / 0 | 306 | 306 / 306 | 0 | csv 2026-03-08 |
| 25/26 | E0 | 47 | 380 | 380 (100.0%) | 380/380 (100.0%) | 210 / 170 / 0 | 380 | 380 / 380 | 0 | csv 2026-10-06 |
| 25/26 | SP1 | 87 | 380 | 380 (100.0%) | 380/380 (100.0%) | 188 / 192 / 0 | 380 | 380 / 380 | 0 | csv 2026-07-14 |
| 25/26 | I1 | 55 | 380 | 380 (100.0%) | 380/380 (100.0%) | 198 / 182 / 0 | 380 | 380 / 380 | 0 | csv 2026-08-29 |
| 25/26 | D1 | 54 | 306 | 306 (100.0%) | 306/306 (100.0%) | 149 / 157 / 0 | 306 | 306 / 306 | 0 | csv 2026-08-29 |
| 25/26 | F1 | 53 | 306 | 306 (100.0%) | 306/306 (100.0%) | 153 / 153 / 0 | 306 | 306 / 306 | 0 | csv 2026-08-29 |
| 25/26 | N1 | 57 | 306 | 306 (100.0%) | 306/306 (100.0%) | 142 / 164 / 0 | 306 | 306 / 306 | 3 | csv 2026-10-05 |
| 25/26 | P1 | 61 | 232 | 232 (100.0%) | 232/232 (100.0%) | 153 / 79 / 0 | 232 | 232 / 232 | 74 | csv 2026-03-16, **partial** |
| 25/26 | B1 | 40 | 311 | 311 (100.0%) | 311/311 (100.0%) | 96 / 215 / 0 | 311 | 311 / 311 | 2 | csv 2026-10-05 |
| 25/26 | T1 | 71 | 306 | 306 (100.0%) | 306/306 (100.0%) | 135 / 171 / 0 | 306 | 306 / 306 | 0 | csv 2026-09-01 |
| 25/26 | E1 | 48 | 552 | 552 (100.0%) | 552/552 (100.0%) | 271 / 281 / 0 | 552 | 552 / 552 | 3 | csv 2026-07-14 |
| 25/26 | SP2 | 140 | 462 | 462 (100.0%) | 462/462 (100.0%) | 198 / 264 / 0 | 462 | 462 / 462 | 6 | csv 2026-08-29 |
| 25/26 | I2 | 86 | 329 | 329 (100.0%) | 329/329 (100.0%) | 90 / 239 / 0 | 329 | 329 / 329 | 61 | csv 2026-04-12, **partial** |
| 25/26 | D2 | 146 | 306 | 306 (100.0%) | 306/306 (100.0%) | 90 / 216 / 0 | 306 | 306 / 306 | 0 | csv 2026-09-21 |
| 25/26 | F2 | 110 | 259 | 259 (100.0%) | 259/259 (100.0%) | 99 / 160 / 0 | 259 | 259 / 259 | 47 | csv 2026-04-12, **partial** |
| **Total** | | | 25201 | 25195 (99.98%) | 25193/25195 (99.99%) | 25172 with closing 1X2 | 25172 | 25170 / 25170 | 498 | |

**Summary.**
- Mapped: 25,195 of 25,201 rows (99.98%). Top divisions 15,041 of 15,047; every top division-season is at
  least 98.5% (lowest: T1 2022/23). Second tiers 10,154 of 10,154.
- Score agreement: 25,193 of 25,195 mapped rows (99.99%).
- Closing 1X2 and O/U 2.5 odds: 25,172 rows (every row except the 29 awarded Super Lig 2022/23 matches);
  pre-closing: 25,170.
- Pinnacle closing odds are used for every row with odds in 2021/22 to 2024/25, except one T1 2021/22 row
  (market average). In 2025/26 they are used for 2,172 of 4,815 rows and the market average for the other 2,643.
- Partial season files (`fd_file_complete=0`): 4 division-seasons, 982 rows: P1 2024/25 (162 of 306 matches),
  P1 2025/26 (232 of 306), I2 2025/26 (329 of 380), F2 2025/26 (259 of 306).
- Awarded results: 35 mapped rows have `fotmob_awarded=1` (24 of them are the Super Lig 2022/23 rows without odds).
  The other 11 carry closing odds that were priced for the match as played, e.g. Union Berlin v Bochum 2024-12-14
  (awarded 0-2). Drop `fotmob_awarded=1` and `score_agrees=0` rows when scoring results against the closing market.

### Verification (2026-10-13)

- **Spot check.** 20 random mapped rows re-read against the FotMob fixture cache
  (`football_data_history.py --checks-only --spot-check 20`, seed 20261013): 20/20 have the same pair and a
  date within +-1 day.
- **Independent check against our DB (2025/26).** All 4,811 rows that `football_data_matches.csv` links to a
  DB match carry exactly that match's `provider_id` as `fotmob_match_id`: 0 differences (`--db-check`). The
  other 4 rows have no DB link there. Three are 2025/26 Serie B matches of Reggiana (Palermo v Reggiana,
  Reggiana v Empoli, Juve Stabia v Reggiana): the DB has two Reggiana teams (FotMob ids 6500 and 959006) and
  stores these three matches with 959006, while FotMob's league fixture list uses 6500. The match ids are the
  same (4905979, 4906003, 4906010). The fourth, Nantes v Toulouse 2026-05-17 (4830760), is not in the DB.
  Join on `fotmob_match_id`, not on team ids.
- **Reproducibility.** An offline rebuild (`--history --skip-download`) reproduces `football_data_history.csv`
  byte for byte. `football_data_matches.csv` and `football_data_coverage.json` are unchanged (sha256 checked),
  and the current-season build still reproduces them exactly.
- **Tests.** `tests/test_football_data_history.py`: 19 tests on synthetic fixtures (mapping rules, the +-1 day
  window, duplicate guard, odds method, capture selection, xlsx/zip readers, the FotMob fetch path with a
  fake client: one limiter call per request, 429 reported, 403/challenge page stops, other seasons never cached;
  a missing FotMob `awarded` flag stays empty; partial season files are labelled).
- **Independent QA (2026-10-13).** Re-checked with separate code (own CSV, zip and xlsx readers, own FotMob
  parser, own odds maths and UK-time conversion):
  - all 25,201 rows re-read from the raw files: 0 differences in date, teams, time, score and the 30 odds columns;
  - all four probability sets recomputed: the preference order holds in every row, probabilities sum to 1 within
    1e-5 (5-decimal rounding), and closing sets use only closing columns;
  - every mapped row re-checked against the FotMob cache (ids, names, UTC time, round, score, awarded flag). No FotMob
    match is used twice, no football-data match appears twice and no date lies in the future. The kick-off time
    (`time` as UK time) equals FotMob's UTC time in 25,055 of 25,195 mapped rows; the rest are short offsets or
    rescheduled matches within the +-1 day window;
  - the coverage table above, the coverage JSON and the bundle check (27 files, 9,577 rows, 1,007,266 cells,
    1 referee name) reproduced exactly;
  - live FotMob check (9 requests through `fotmob_rate.py`): 6 league fixture lists are identical to the cache for
    all 1,875 mapped rows of those league-seasons, and 3 match pages confirm the edge cases below.
  - Fixed by the QA: `fotmob_awarded` was 0 instead of empty for the one fixture FotMob sends without an `awarded`
    flag, and the `fd_file_complete` column was added to label partial season files.

### Gaps and caveats (history build)

- **Unmapped rows (6, listed in `football_data_history_unmapped.csv`).**
  - 5 Super Lig 2022/23 matches awarded after Gaziantep and Hatayspor withdrew (February 2023 earthquake).
    football-data and FotMob date them 15 to 21 days apart, and they have no odds.
  - Groningen v Ajax 2022/23: football-data 2023-05-14, FotMob 2023-05-16 13:00 UTC (match 3900621, re-checked
    live on 2026-10-13), same 2-3 score. Only one FotMob fixture of the pair exists that season, but the date gap
    is outside the +-1 day rule.
  - They stay unmapped (+-1 day rule); the report names the nearest FotMob fixture of the pair.
- **Score disagreements (2, kept with `score_agrees=0`).**
  - Cittadella v Pisa (I2, 2024-08-27): played 1-1 per football-data, FotMob shows the awarded 0-3.
  - Troyes v Valenciennes (F2, 2024-05-03): football-data 0-1, FotMob 1-1. This row exists only in the 2023/24
    xlsx bundle; the later per-division CSV lacks the match. FotMob marks fixture 4219847 as abandoned
    (`status.reason` "Ab", `cancelled=true`, 1-1 when it was stopped, no `awarded` flag; confirmed live on
    2026-10-13), so its FotMob score is not a final result and `fotmob_awarded` is empty. It is the only mapped row
    whose FotMob fixture is cancelled.
- **Rows that only the bundles contain.** The extra F2 rows that made the bundles win over the 379-row CSVs are
  Bordeaux v Rodez 2023-06-02 (2022/23 data.zip; 0-1 in both sources, an awarded result for FotMob, `fotmob_awarded=1`) and
  Troyes v Valenciennes 2024-05-03 (2023/24 xlsx, above).
- **Partial files with no complete archived copy** (`fd_file_complete=0`, marked **partial** in the table).
  - P1 2024/25: 162 of 306 matches, up to 2025-01-20. The only capture is from 2025-01-22 and the 2024/25 xlsx is
    from 2025-01-11.
  - 2025/26: P1 232 rows (snapshot 2026-03-16), I2 329 and F2 259 (both 2026-04-12). The column "FotMob matches
    w/o row" shows how many league matches are missing.
- **Play-offs are not in the football-data league files.** These FotMob fixtures have no row:
  - promotion play-offs: E1 3-5, SP2 6, I2 9-10 (with the relegation play-out) and N1 3-6 per season;
  - the Serie A 2022/23 relegation play-off;
  - the Belgian play-offs of 2021/22 and 2022/23 (24 each). From 2023/24 the B1 file includes them, except:
    Standard Liège v Westerlo 2024-05-10 (awarded 0-5), the 2024/25 final Royal Antwerp v Sporting Charleroi
    (2025-05-29), and in 2025/26 FCV Dender EH v RAAL La Louvière (2026-05-03) and the final Gent v Genk (2026-05-31).
- **FotMob names are current names**, not the names at the time (e.g. FeralpiSalo is shown as Union Brescia).
  Use the ids, not the names, to join.
- **Freshness.** Every file is an archive snapshot. Re-run `--history` later: new captures are tried
  automatically and a fuller 2025/26 file would replace the partial one.

## Elo convention (ClubElo)

Source: ClubElo's own methodology page (archived copy, 2024-12-17).

- The expected result is `E = 1 / (10^(-dr/400) + 1)`. **E is the expected score (win = 1, draw = 0.5), not a win probability.**
- `dr` is the Elo difference **plus HFA** (home-field advantage).
- HFA is not a published constant. ClubElo adjusts it daily for each country with `HFA += sum(dElo) * 0.075`.
- ClubElo's 1/X/2 probabilities come from a histogram of past results at each Elo difference.

Because of this, `clubelo_ucl_2026-10-13.csv` reports three separate things:
- `expected_score_home_no_hfa`: E with dr = home Elo - away Elo, i.e. no home advantage.
- `clubelo_p_home/draw/away`: ClubElo's published probabilities, from its homepage and /Fixtures page as fetched on 2026-10-13 around 17:00 UTC.
- `implied_hfa_points` = `-400*log10(1/(p1 + 0.5*pX) - 1) - (Elo_home - Elo_away)`: the HFA that ClubElo's own numbers imply, 67 to 83 points for these games.

Sabah FK v Slavia Praha was not listed on ClubElo's fixtures pages when they were fetched, so it has no published 1/X/2.

