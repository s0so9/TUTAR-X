# backend/data/odds - bookmaker odds snapshots (research prototype, 2026-10-15)

Pre-match bookmaker prices for the featured matches (10 leagues + UCL / UEL / UECL), collected by the prototype scripts in
`backend/scripts/data_collection/` and written one **snapshot per line** to `<UTC date>.jsonl`. Nothing here is wired into the
app or the model; the lead decides. Report with the source comparison, costs and legal notes:
`docs/research/2026-10-15-odds-sources.md`.

## What is real and what is not (AGENTS.md rules 8-10, 14)

* `2026-10-15.jsonl` (6 lines) is **real data**: bookmaker prices that FotMob displayed for two Europa League matches on
  2026-10-15 around 12:05 UTC (6112294 Salzburg - Milan, 6112353 Hoffenheim - Besiktas), parsed OFFLINE from the raw answers saved in
  `backend/data/research/odds_samples/raw_matchodds_2026-10-15/`. It is a feasibility sample, not a dataset.
* The Odds-API.io and OddsPapi collectors have **never been run against the live services** (no API key exists yet). Their tests use
  SYNTHETIC responses, labelled as such inside `backend/tests/test_collect_odds_*.py`; no synthetic value is ever written here.
* A price that a source does not send is **absent** (`missing_markets` lists it); a price that is broken or implausible is dropped
  and named in `markets_rejected`. Nothing is filled with 0 or a guess.

## Line format (`odds_snapshot_v1`)

One JSON object per line = one bookmaker's prices for one match at one fetch time (poll again to build a time series).

```
fotmob_match_id   our match id (== matches.provider_id)
match             {fotmob_match_id, home, away, kickoff_utc, competition_id, competition_name}
source            fotmob_matchodds | odds_api_io | oddspapi
bookmaker         provider as the source names it (FotMob: persistentKey such as Tipico_Germany; the bookmaker depends on the country code)
region            FotMob ccode3 used for the request (null for the other sources)
odds_type         "pre_match" (in-play answers are skipped)
fetched_at        UTC time of the request; odds_updated_at = the source's own timestamp when it sends one
seconds_to_kickoff
is_closing        always false: a closing line is the last snapshot taken just before kick-off, decided by the consumer
mapping           {method: fotmob_match_id | teams+kickoff, confidence 0-1, evidence, ...}  (team_name_check for FotMob)
markets           canonical markets that are present and plausible:
                    1x2 {home, draw, away} | double_chance {1x, 12, x2} | btts {yes, no} | ou_1.5 / ou_2.5 / ou_3.5 {over, under}
                  each with odds, overround, margin, p_proportional, p_shin, shin_z
missing_markets   canonical markets the source did not send
markets_rejected  markets that were sent but failed validation, with the reason
```

Margin removal: `p_proportional` = (1/o_i) / sum(1/o_j); `p_shin` = Shin (1993) insider model, solved as in Strumbelj (2014), the same maths as
`scripts/research/xdata_devig.py` (pure Python here, checked against the scipy version in the tests). On 13,841 football-data.co.uk
pre-closing 1X2 price sets (Pinnacle where complete, else the market average) Shin minus proportional is -0.0004 log loss on the 1,966-match
test window, 90 % CI -0.0014 .. +0.0005, i.e. no proven difference (`backend/data/research/xdata_devig.json`). **Double chance** probabilities sum to 2 (proportional scaling to 2; Shin does not apply, `p_shin` is null).
Markets are rejected unless 0.99 <= overround <= 1.40 (lower means an arbitrage / wrong parse, higher a broken price).

## Run

From `backend/`:

| script | needs | notes |
|---|---|---|
| `collect_odds_fotmob.py --date D --countries DEU,AUT,ESP --accept-fotmob-terms-risk` | nothing (no key) | **Refuses to run without the flag**: FotMob robots.txt disallows `/api/*` and its terms forbid automated / bulk retrieval. The flag is the owner's decision. `--from-raw DIR --fixtures-json FILE` parses saved answers offline (no flag, no network). |
| `collect_odds_oddspapi.py --date D --bookmakers pinnacle,bet365` | env `ODDSPAPI_API_KEY` (free account) | 3-4 billable requests per run (free plan: 250 per month); `--max-requests` caps a run. |
| `collect_odds_oddsapiio.py --date D --bookmakers Iddaa,Bet365` | env `ODDS_API_IO_KEY` | free keys are paused (archive 2026-10-03); paid Solo plan from GBP 49 / month. 1 request per 10 matches. |

All three take `--fixtures-json FILE` (a saved FotMob `/api/data/matches?date=YYYYMMDD` answer) instead of fetching the day list, and
`--out`. FotMob requests (day list, odds) go through the shared limiter `fotmob_rate.acquire()` before every hop; 403 / challenge pages stop the
run (exit 2), 429 reports the cool-down to every collector. API keys are read from the environment only, are sent as the vendors' `apiKey`
query parameter, and are redacted from every error text; no vendor / affiliate links are stored.

For a **closing line** run the collector once about 20-30 minutes before kick-off and keep the last snapshot (the lines carry `seconds_to_kickoff`).
