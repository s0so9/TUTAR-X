"""Collect pre-match bookmaker odds (Pinnacle, Bet365, ...) for the featured matches of a day from OddsPapi.

RESEARCH PROTOTYPE (2026-10-15) - not wired into the app or the model. NOT yet run against the live service: it
needs an API key that the owner has to create (free account at https://oddspapi.io, "Sign Up"). All tests use
SYNTHETIC responses shaped after the vendor's public v4 documentation (https://oddspapi.io/us/docs); the real answers
have never been seen, so the first live run must be checked by hand (see "Unverified" below).

Service facts (vendor pages read 2026-10-15; the free-tier numbers come from the vendor's own blog, verify at signup):
  * base ``https://api.oddspapi.io/v4``, key as query parameter ``apiKey``; the API host answers from this network
  * free account: 250 requests/month, no per-market surcharge ("1 request = 1 call to a billable endpoint, whatever it returns");
    ``/v4/historical-odds`` is free and does not count; every endpoint has a 1000 ms cool-down
  * ``GET /v4/markets`` -> [{marketId, marketName, marketType, handicap, period, playerProp, outcomes:[{outcomeId, outcomeName}]}]
  * ``GET /v4/fixtures?sportId=10&from&to&statusId=0&hasOdds=true&bookmakers=`` -> fixtureId, participant1Name/2Name,
    startTime, tournamentId (window of at most 48 h when only from/to are given; sportId 10 = soccer)
  * ``GET /v4/odds-by-tournaments?tournamentIds=<a,b,..>&bookmakers=<max 3>`` -> every upcoming fixture of those
    tournaments with ``bookmakerOdds.<slug>.markets.<marketId>.outcomes.<outcomeId>.players."0".price``

Flow (about 3-4 billable requests per run): markets (cached 7 days, ``data/odds/.oddspapi_markets.json``) -> fixtures of the
time window -> mapping to our FotMob fixtures by team names + kick-off (confidence; unmapped listed with the reason,
never guessed) -> odds-by-tournaments -> margin-free probabilities (proportional + Shin) -> ``data/odds/<date>.jsonl``
(+ ``<date>.oddspapi_run.json``).

Unverified (check on the first real run): that Turkish bookmakers such as Iddaa exist in ``/v4/bookmakers`` (not found on the
public "sportsbooks" page); the exact market names of double chance; whether ``odds-by-tournaments`` accepts many ids at once
(chunks of 10 are used). Markets that cannot be classified are counted in the run report, never guessed.

Key: environment variable ``ODDSPAPI_API_KEY`` (never written to disk, never logged; URLs in errors are redacted).

Usage (from backend/):
  $env:ODDSPAPI_API_KEY = "..."   (bash: export ODDSPAPI_API_KEY=...)
  venv/Scripts/python.exe scripts/data_collection/collect_odds_oddspapi.py --date 2026-10-15 --bookmakers pinnacle,bet365
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

import httpx

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import odds_common as oc  # noqa: E402

SOURCE = "oddspapi"
BASE_URL = "https://api.oddspapi.io/v4"
ENV_KEY = "ODDSPAPI_API_KEY"
SOCCER_SPORT_ID = 10
DEFAULT_BOOKMAKERS = "pinnacle,bet365"  # max 3 per odds-by-tournaments request
TOURNAMENT_CHUNK = 10
MARKETS_CACHE = oc.DEFAULT_ODDS_DIR / ".oddspapi_markets.json"
MARKETS_CACHE_MAX_AGE_S = 7 * 24 * 3600

RequestBudget = oc.RequestBudget
QuotaStop = oc.QuotaStop
OddsPapiError = oc.VendorError


def api_get(client: Any, path: str, params: dict[str, Any], key: str, budget: oc.RequestBudget) -> Any:
    return oc.vendor_get(client, BASE_URL, path, params, key, budget, remaining_header="x-ratelimit-remaining")


# --------------------------------------------------------------------------------------------------
# market classification (marketId -> canonical market + outcomeId -> outcome key)
# --------------------------------------------------------------------------------------------------
_DC_NAMES = {"1X": "1x", "X1": "1x", "12": "12", "21": "12", "X2": "x2", "2X": "x2"}
_BAD_WORDS = ("half", "1st", "2nd", "team total", "team goal", "home team", "away team", "corner", "card", "booking", "asian", "handicap", "minute", "odd/", "odd even", "even", "exact")


def classify_markets(markets: Any) -> dict[int, tuple[str, dict[int, str]]]:
    """``/v4/markets`` answer -> {marketId: (canonical market, {outcomeId: outcome key})} for the full-time soccer markets we use.

    Only full-time, non-player markets are read. 1X2 by ``marketType == "1x2"`` (3 outcomes 1/X/2); both teams to score by name;
    over/under only for the tracked lines (1.5 / 2.5 / 3.5, from the market's ``handicap``) and a name that contains "over under";
    double chance by name with outcomes 1X / 12 / X2. Anything else is ignored (and counted by the caller)."""
    out: dict[int, tuple[str, dict[int, str]]] = {}
    seen_canonical: set[str] = set()
    ordered = sorted((x for x in markets if isinstance(x, dict)), key=lambda x: x["marketId"] if isinstance(x.get("marketId"), int) else 10**12) if isinstance(markets, list) else []
    for m in ordered:
        if m.get("playerProp") or str(m.get("period") or "fulltime").lower() != "fulltime":
            continue
        if m.get("sportId") not in (None, SOCCER_SPORT_ID):
            continue
        mid = m.get("marketId")
        name = str(m.get("marketName") or "").strip().lower()
        outs = {o.get("outcomeId"): str(o.get("outcomeName") or "").strip() for o in (m.get("outcomes") or []) if isinstance(o, dict)}
        if not isinstance(mid, int) or any(w in name for w in _BAD_WORDS):
            continue
        canonical: Optional[str] = None
        mapping: dict[int, str] = {}
        if str(m.get("marketType") or "").lower() == "1x2" and len(outs) == 3:
            by = {n.upper(): oid for oid, n in outs.items()}
            if set(by) == {"1", "X", "2"}:
                canonical, mapping = "1x2", {by["1"]: "home", by["X"]: "draw", by["2"]: "away"}
        elif name == "both teams to score" and len(outs) == 2:
            by = {n.lower(): oid for oid, n in outs.items()}
            if set(by) == {"yes", "no"}:
                canonical, mapping = "btts", {by["yes"]: "yes", by["no"]: "no"}
        elif name.startswith("over under") and len(outs) == 2:
            line = oc.ou_market_name(m.get("handicap"))
            by = {n.lower(): oid for oid, n in outs.items()}
            if line and set(by) == {"over", "under"}:
                canonical, mapping = line, {by["over"]: "over", by["under"]: "under"}
        elif name in ("double chance", "double chance full time") and len(outs) == 3:
            keys = {_DC_NAMES.get(n.upper().replace(" ", "")): oid for oid, n in outs.items()}
            if None not in keys and set(keys) == {"1x", "12", "x2"}:
                canonical, mapping = "double_chance", {oid: k for k, oid in keys.items()}
        if canonical and canonical not in seen_canonical:  # first (lowest id) market of a kind wins
            seen_canonical.add(canonical)
            out[mid] = (canonical, mapping)
    return out


def load_markets(client: Any, key: str, budget: oc.RequestBudget, cache: Path, *, now: float | None = None) -> list[dict[str, Any]]:
    """Markets list from the cache file (<= 7 days old) or ``GET /v4/markets`` (one billable request, then cached)."""
    now = time.time() if now is None else now
    try:
        if cache.exists() and now - cache.stat().st_mtime < MARKETS_CACHE_MAX_AGE_S:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return data
    except (OSError, ValueError):
        pass
    data = api_get(client, "/markets", {"language": "en"}, key, budget)
    if isinstance(data, list) and data:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data if isinstance(data, list) else []


# --------------------------------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------------------------------
def parse_fixtures(raw: Any) -> list[oc.EventLite]:
    out: list[oc.EventLite] = []
    for f in raw if isinstance(raw, list) else []:
        if not isinstance(f, dict):
            continue
        kickoff = oc.parse_utc(f.get("startTime"))
        home, away = f.get("participant1Name"), f.get("participant2Name")
        if not f.get("fixtureId") or not home or not away or kickoff is None:
            continue
        out.append(oc.EventLite(event_id=str(f["fixtureId"]), home=str(home), away=str(away), kickoff=kickoff, league=str(f.get("tournamentId")) if f.get("tournamentId") is not None else None))
    return out


def _price(outcome: Any) -> Optional[Any]:
    """price of the first player entry ("0") of an outcome when it is active; None when missing / suspended."""
    players = outcome.get("players") if isinstance(outcome, dict) else None
    entry = (players or {}).get("0") if isinstance(players, dict) else None
    if not isinstance(entry, dict) or entry.get("active") is False:
        return None
    return entry.get("price")


def parse_bookmaker_odds(book: Any, classes: dict[int, tuple[str, dict[int, str]]]) -> tuple[dict[str, dict[str, Any]], dict[str, str], Optional[str]]:
    """One bookmaker block of an odds-by-tournaments fixture -> (canonical markets, rejected, newest changedAt)."""
    raw: dict[str, dict[str, Any]] = {}
    rejected: dict[str, str] = {}
    updated: Optional[str] = None
    if not isinstance(book, dict) or book.get("suspended") is True or book.get("bookmakerIsActive") is False:
        return {}, {"_bookmaker": "suspended or inactive"}, None
    for mid_s, m in (book.get("markets") or {}).items():
        try:
            cls = classes.get(int(mid_s))
        except (TypeError, ValueError):
            cls = None
        if cls is None or not isinstance(m, dict):
            continue
        canonical, outmap = cls
        if m.get("marketActive") is False:
            rejected.setdefault(canonical, "market inactive")
            continue
        vals: dict[str, Any] = {}
        for oid_s, o in (m.get("outcomes") or {}).items():
            try:
                key = outmap.get(int(oid_s))
            except (TypeError, ValueError):
                key = None
            if key is None:
                continue
            vals[key] = _price(o)
            players = o.get("players") if isinstance(o, dict) else None
            ts = ((players or {}).get("0") or {}).get("changedAt") if isinstance(players, dict) else None
            if ts and (updated is None or str(ts) > updated):
                updated = str(ts)
        raw.setdefault(canonical, vals)
    markets: dict[str, dict[str, Any]] = {}
    for canonical, vals in raw.items():
        rec = oc.build_market(canonical, vals)
        if rec is None:
            bad = [o for o in oc.MARKETS[canonical] if oc.parse_decimal_odds(vals.get(o)) is None]
            rejected[canonical] = f"missing/inactive/invalid prices {bad}" if bad else "overround outside 0.99-1.40"
        else:
            markets[canonical] = rec
    return markets, rejected, updated


def parse_fixture_odds(fixture_obj: Any, classes: dict[int, tuple[str, dict[int, str]]]) -> list[dict[str, Any]]:
    out = []
    for slug, book in ((fixture_obj or {}).get("bookmakerOdds") or {}).items():
        markets, rejected, updated = parse_bookmaker_odds(book, classes)
        if markets:
            out.append({"bookmaker": slug, "markets": markets, "rejected": rejected, "updated_at": updated})
    return out


# --------------------------------------------------------------------------------------------------
# flow
# --------------------------------------------------------------------------------------------------
def collect(
    client: Any,
    key: str,
    fixtures: list[oc.Fixture],
    bookmakers: list[str],
    budget: oc.RequestBudget,
    *,
    markets_cache: Path = MARKETS_CACHE,
    clock=oc.now_utc,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    report: dict[str, Any] = {"mapped": [], "unmapped": [], "fixtures_listed": 0, "odds_requests": 0, "no_odds_for_fixture": [], "bookmakers_requested": bookmakers, "markets_classified": {}, "stopped": None}
    if not fixtures:
        return [], report
    start = min(f.kickoff for f in fixtures) - timedelta(minutes=30)
    end = max(f.kickoff for f in fixtures) + timedelta(minutes=30)
    if end - start >= timedelta(hours=48):
        raise OddsPapiError("time window of the fixture list is 48 h or longer; the vendor rejects that (use --hours-ahead <= 40)")
    snaps: list[dict[str, Any]] = []
    try:
        classes = classify_markets(load_markets(client, key, budget, markets_cache))
        report["markets_classified"] = {canonical: mid for mid, (canonical, _) in sorted(classes.items())}
        listed = api_get(client, "/fixtures", {"sportId": SOCCER_SPORT_ID, "from": oc.iso_z(start), "to": oc.iso_z(end), "statusId": 0, "hasOdds": "true", "bookmakers": ",".join(bookmakers)}, key, budget)
        events = parse_fixtures(listed)
        report["fixtures_listed"] = len(events)
        mapped, unmapped = oc.map_events_to_fixtures(fixtures, events)
        report["unmapped"] = unmapped
        by_id = {f.match_id: f for f in fixtures}
        tournaments = sorted({mapped[mid][0].league for mid in mapped if mapped[mid][0].league}, key=str)
        odds_by_fixture: dict[str, Any] = {}
        for i in range(0, len(tournaments), TOURNAMENT_CHUNK):
            chunk = tournaments[i : i + TOURNAMENT_CHUNK]
            resp = api_get(client, "/odds-by-tournaments", {"tournamentIds": ",".join(chunk), "bookmakers": ",".join(bookmakers)}, key, budget)
            report["odds_requests"] += 1
            for f in resp if isinstance(resp, list) else []:
                if isinstance(f, dict) and f.get("fixtureId") is not None:
                    odds_by_fixture[str(f["fixtureId"])] = f
        fetched_at = clock()
        for mid in (f.match_id for f in fixtures):
            if mid not in mapped:
                continue
            ev, conf, evidence = mapped[mid]
            fx = by_id[mid]
            parsed = parse_fixture_odds(odds_by_fixture.get(str(ev.event_id)), classes)
            report["mapped"].append({"fotmob_match_id": mid, "vendor_fixture_id": ev.event_id, "confidence": conf, "tournament_id": ev.league, "bookmakers_with_odds": [p["bookmaker"] for p in parsed]})
            if not parsed:
                report["no_odds_for_fixture"].append(mid)
                continue
            mapping = {"method": "teams+kickoff", "confidence": conf, "evidence": f"{evidence}; vendor fixture {ev.event_id} '{ev.home}' - '{ev.away}'", "vendor_event_id": ev.event_id}
            for p in parsed:
                snaps.append(oc.build_snapshot(fixture=fx, source=SOURCE, bookmaker=p["bookmaker"], markets=p["markets"], fetched_at=fetched_at, mapping=mapping, odds_updated_at=p["updated_at"], extra={"markets_rejected": p["rejected"]}))
    except QuotaStop as exc:
        report["stopped"] = str(exc)
    report["requests_used"] = budget.used
    return snaps, report


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", default=oc.now_utc().strftime("%Y-%m-%d"), help="UTC date of the fixture list (YYYY-MM-DD)")
    ap.add_argument("--bookmakers", default=DEFAULT_BOOKMAKERS, help="comma-separated vendor slugs, at most 3 (see GET /v4/bookmakers)")
    ap.add_argument("--competitions", default=",".join(str(x) for x in oc.TARGET13))
    ap.add_argument("--fixtures-json", type=Path, help="FotMob day-list JSON instead of fetching it")
    ap.add_argument("--hours-ahead", type=float, default=36.0)
    ap.add_argument("--max-requests", type=int, default=8, help="hard cap of billable vendor requests in this run (free plan: 250 per month)")
    ap.add_argument("--markets-cache", type=Path, default=MARKETS_CACHE, help="where /v4/markets is cached (7 days) so it is billed once")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)

    key = os.environ.get(ENV_KEY, "").strip()
    if not key:
        print(f"{ENV_KEY} is not set. Create a free account at https://oddspapi.io (Sign Up), copy the key from the account page and set the environment variable; the key is never written to disk by this script.", file=sys.stderr)
        return 5
    bookmakers = [b.strip() for b in args.bookmakers.split(",") if b.strip()]
    if not 1 <= len(bookmakers) <= 3:
        print("--bookmakers needs 1 to 3 slugs (vendor limit per odds-by-tournaments request)", file=sys.stderr)
        return 1
    featured = [int(x) for x in args.competitions.split(",") if x.strip()]
    out = args.out or (oc.DEFAULT_ODDS_DIR / f"{args.date}.jsonl")
    with httpx.Client(timeout=25.0) as fm_client:
        try:
            if args.fixtures_json:
                fixtures = oc.parse_fotmob_matches_payload(json.loads(args.fixtures_json.read_text(encoding="utf-8")), featured)
            else:
                fixtures = oc.fetch_fotmob_fixtures(fm_client, args.date, featured)
        except (oc.FotmobBlocked, oc.FotmobRateLimited) as exc:
            print(f"STOP: FotMob fixture list: {exc}. Use --fixtures-json to supply the day list.", file=sys.stderr)
            return 2
    now = oc.now_utc()
    fixtures = [f for f in fixtures if not (f.started or f.finished or f.cancelled) and now < f.kickoff <= now + timedelta(hours=args.hours_ahead)]
    print(f"{len(fixtures)} pre-match featured fixtures on {args.date}")
    budget = RequestBudget(max_requests=args.max_requests, min_interval=1.1)  # vendor cool-down is 1000 ms per endpoint
    with httpx.Client(timeout=30.0) as client:
        try:
            snaps, report = collect(client, key, fixtures, bookmakers, budget, markets_cache=args.markets_cache)
        except OddsPapiError as exc:
            print(f"STOP: {oc.redact(exc, key)}", file=sys.stderr)
            return 4
    n = oc.append_jsonl(out, snaps)
    report.update({"date": args.date, "fixtures_collected": len(fixtures), "snapshots_written": n, "output": str(out)})
    out.with_name(out.stem + ".oddspapi_run.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {n} snapshots to {out}; mapped {len(report['mapped'])}, unmapped {len(report['unmapped'])}, billable requests {report.get('requests_used')}, stopped: {report['stopped']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
