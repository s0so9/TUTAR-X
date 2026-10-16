# Live team-news raw archive (FotMob)

**Written by:** the team-news live layer — `backend/app/services/team_news/raw_store.py`, used by
`scripts/live/refresh_team_news.py` and by the optional in-API refresh loop (`TEAM_NEWS_REFRESH_ENABLED`).
**Source:** FotMob unofficial API (`settings.fotmob_base_url`), endpoints `/api/data/matchDetails?matchId=`,
`/api/data/teams?id=`, `/api/data/playerData?id=`. League fixture lists (`/api/data/leagues`) are used for
discovery only and are not archived.
**Purpose:** every distinct observation that the live layer wrote to the database can be re-parsed offline
(`scripts/live/load_player_data.py --include-live`). Nothing here is edited; bodies are stored exactly as
received (gzip), written atomically (temp file + `os.replace`).

## Layout

| Path | Content |
|---|---|
| `match_details/<FotMob match id>/<UTC yyyymmddThhmmssffffffZ>.json.gz` | untouched `/api/data/matchDetails` body |
| `teams/<FotMob team id>/<stamp>.json.gz` | untouched `/api/data/teams` body |
| `players/<FotMob player id>/<stamp>.json.gz` | untouched `/api/data/playerData` body |
| `<kind>/_manifest.jsonl` | one line per stored body: `id`, `fetched_at` (UTC ISO, client clock when the response arrived), `http_status` (always 200; failures are not stored), `bytes` (uncompressed), `relevant_sha256`, `path` (relative to this directory) |

## When a body is stored

A body is stored only when the SHA-256 of its *relevant parsed content* differs from the last body stored for
the same entity by the same process: for match details the status, line-up type, formations, starters, bench,
unavailable lists and (finished matches) player stats; for teams the season and the squad with injuries; for
players the core profile and the injury/international-duty reports. Identical refreshes (every 5–15 minutes
before kickoff) therefore do not duplicate files. After a process restart the first fetch of each entity is
stored again once.

## Field definitions

The bodies are FotMob's own JSON. The field paths that the layer reads are documented in
`backend/app/services/team_news/parsers.py` and in `docs/live-layer.md` (section "Parsed fields").

## Coverage / known gaps

* Coverage depends on when the refresh ran: only matches of the configured competitions
  (`TEAM_NEWS_COMPETITIONS`, default the 13 target competitions) within the refresh windows are fetched.
* Pre-match line-ups are FotMob's (`lineupType` `predicted` until the official XI is published, then
  `standard`). The archive shows what FotMob published at each observation time, not what is true.
* Bodies that failed (HTTP errors, 403/captcha, invalid JSON) are not stored; the refresh logs them and the
  match registry (`team_news_matches.last_error`) records the last error.

## Contents so far

| As of (UTC) | match_details | teams | players | Size | Written by |
|---|---|---|---|---|---|
| 2026-10-13 19:05 | 124 bodies (63 matches: 18 each UCL/UEL/UECL + 9 league matches, kickoff 2026-10-12 19:00 → 2026-10-16 18:45) | 163 bodies (116 squads of teams playing within 72 h; 47 of them twice because a first run stopped early) | 1 body | 9.8 MB | verification runs of `scripts/live/refresh_team_news.py --once` against a DB copy |
