"""Collect pre-match bookmaker odds (incl. the Turkish "Iddaa" feed) for the featured matches of a day from Odds-API.io.

RESEARCH PROTOTYPE (2026-10-15) - not wired into the app or the model. NOT yet run against the live service: it
needs an API key that the owner has to create (free sign-up with an e-mail address, no card). All tests use
SYNTHETIC responses shaped after the vendor's OpenAPI document (docs.odds-api.io/api-reference/openapi.json).

Service: https://odds-api.io (v3 REST, base ``https://api.odds-api.io/v3``). Facts used here (vendor docs, read via
the Internet Archive on 2026-10-15; verify on the day of signup):
  * the public ``GET /v3/bookmakers`` list (no key needed, fetched 2026-10-15) contains 430 bookmakers, among them
    ``Iddaa``, ``Bet365``, ``Betfair Exchange``, ``Unibet``, ``1xbet``;
  * free plan: 100 requests/hour (500/day), 2 recreational bookmakers of your choice (``PUT /bookmakers/selected/select``),
    all markets, live + pre-match, "intended for development and testing" (production/commercial use needs a paid plan);
  * ``GET /v3/events`` (sport, league, status, from, to, limit, skip) -> id, home, away, date, league{name,slug};
  * ``GET /v3/odds/multi?eventIds=<up to 10>&bookmakers=<names>`` -> odds of up to 10 events for ONE request;
    market names ``ML`` (1X2), ``Totals`` (over/under, line in ``hdp``/``max``), ``Both Teams To Score``, ``Double Chance``.

Flow: our featured fixtures of the day (FotMob day list through the shared limiter, or ``--fixtures-json``) ->
vendor events of the same time window -> mapping by team names + kick-off (confidence; unmapped are listed with the
reason, never guessed) -> odds/multi in batches of 10 -> margin-free probabilities (proportional + Shin) ->
``data/odds/<date>.jsonl`` (+ ``<date>.oddsapiio_run.json``).

Key: environment variable ``ODDS_API_IO_KEY`` (never written to disk, never logged; URLs in errors are redacted).

Usage (from backend/):
  set ODDS_API_IO_KEY=...   (PowerShell: $env:ODDS_API_IO_KEY = "...")
  venv/Scripts/python.exe scripts/data_collection/collect_odds_oddsapiio.py --date 2026-10-15 [--bookmakers Iddaa,Bet365]
Without ``--bookmakers`` the bookmakers selected in the account (``GET /bookmakers/selected``) are used, else Iddaa,Bet365.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

import httpx

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import odds_common as oc  # noqa: E402

SOURCE = "odds_api_io"
BASE_URL = "https://api.odds-api.io/v3"
ENV_KEY = "ODDS_API_IO_KEY"
DEFAULT_BOOKMAKERS = "Iddaa,Bet365"
BATCH = 10  # /odds/multi accepts up to 10 events per request


# shared plumbing lives in odds_common; the old names stay available from this module
OddsApiError = oc.VendorError
QuotaStop = oc.QuotaStop
RequestBudget = oc.RequestBudget


def api_get(client: Any, path: str, params: dict[str, Any], key: str, budget: oc.RequestBudget) -> Any:
    return oc.vendor_get(client, BASE_URL, path, params, key, budget)


# --------------------------------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------------------------------
def parse_events(raw: Any) -> list[oc.EventLite]:
    """``GET /events`` answer -> EventLite list (events without id, names or a parseable date are dropped)."""
    out: list[oc.EventLite] = []
    for e in raw if isinstance(raw, list) else []:
        if not isinstance(e, dict):
            continue
        kickoff = oc.parse_utc(e.get("date"))
        if e.get("id") is None or not e.get("home") or not e.get("away") or kickoff is None:
            continue
        league = e.get("league") or {}
        out.append(oc.EventLite(event_id=e["id"], home=str(e["home"]), away=str(e["away"]), kickoff=kickoff, league=league.get("slug") or league.get("name")))
    return out


def _first(entries: Any) -> dict[str, Any]:
    return entries[0] if isinstance(entries, list) and entries and isinstance(entries[0], dict) else {}


def _ci_get(d: dict[str, Any], *names: str) -> Any:
    low = {str(k).lower(): v for k, v in d.items()}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return None


def parse_bookmaker_markets(markets: Any) -> tuple[dict[str, dict[str, Any]], dict[str, str], Optional[str]]:
    """One bookmaker's market list -> (canonical markets, rejected {market: reason}, newest updatedAt).

    Only full-time markets are read (``ML``, ``Totals``, ``Both Teams To Score``, ``Double Chance``; the half-time
    variants have other names and are ignored). Incomplete or implausible prices reject the market, never repair it."""
    raw: dict[str, dict[str, Any]] = {}
    updated: Optional[str] = None
    for m in markets if isinstance(markets, list) else []:
        name = str(m.get("name") or "").strip().lower()
        ts = m.get("updatedAt")
        if ts and (updated is None or str(ts) > updated):
            updated = str(ts)
        entries = m.get("odds") or []
        if name == "ml":
            e = _first(entries)
            raw.setdefault("1x2", {"home": e.get("home"), "draw": e.get("draw"), "away": e.get("away")})
        elif name == "both teams to score":
            e = _first(entries)
            raw.setdefault("btts", {"yes": _ci_get(e, "yes"), "no": _ci_get(e, "no")})
        elif name == "double chance":
            e = _first(entries)
            raw.setdefault("double_chance", {"1x": _ci_get(e, "1X"), "12": _ci_get(e, "12"), "x2": _ci_get(e, "X2")})
        elif name == "totals":
            for e in entries:
                if not isinstance(e, dict):
                    continue
                line = e.get("hdp") if e.get("hdp") is not None else e.get("max")
                mk = oc.ou_market_name(line)
                if mk:
                    raw.setdefault(mk, {"over": e.get("over"), "under": e.get("under")})
    markets_out: dict[str, dict[str, Any]] = {}
    rejected: dict[str, str] = {}
    for mk, vals in raw.items():
        rec = oc.build_market(mk, vals)
        if rec is None:
            bad = [o for o in oc.MARKETS[mk] if oc.parse_decimal_odds(vals.get(o)) is None]
            rejected[mk] = f"missing/invalid prices {bad}" if bad else "overround outside 0.99-1.40"
        else:
            markets_out[mk] = rec
    return markets_out, rejected, updated


def parse_event_odds(resp: Any) -> list[dict[str, Any]]:
    """``EventResponse`` -> [{bookmaker, markets, rejected, updated_at}] (bookmakers without any usable market dropped)."""
    out = []
    books = resp.get("bookmakers") if isinstance(resp, dict) else None
    for bname, mlist in (books or {}).items():
        markets, rejected, updated = parse_bookmaker_markets(mlist)
        if markets:
            out.append({"bookmaker": bname, "markets": markets, "rejected": rejected, "updated_at": updated})
    return out


# --------------------------------------------------------------------------------------------------
# flow
# --------------------------------------------------------------------------------------------------
def list_events(client: Any, key: str, start, end, budget: RequestBudget, *, page_size: int = 200, max_pages: int = 10) -> list[oc.EventLite]:
    events: list[oc.EventLite] = []
    skip = 0
    for _ in range(max_pages):
        page = api_get(client, "/events", {"sport": "football", "status": "pending", "from": oc.iso_z(start), "to": oc.iso_z(end), "limit": page_size, "skip": skip}, key, budget)
        events.extend(parse_events(page))
        if not isinstance(page, list) or len(page) < page_size:
            break
        skip += page_size
    return events


def selected_bookmakers(client: Any, key: str, budget: RequestBudget) -> list[str]:
    """Bookmakers selected in the account (free plan: 2). [] when the call fails or answers something unexpected."""
    try:
        raw = api_get(client, "/bookmakers/selected", {}, key, budget)
    except OddsApiError:
        return []
    names = []
    for b in raw if isinstance(raw, list) else []:
        n = b.get("name") if isinstance(b, dict) else b
        if isinstance(n, str) and n:
            names.append(n)
    return names


def collect(
    client: Any,
    key: str,
    fixtures: list[oc.Fixture],
    bookmakers: list[str],
    budget: RequestBudget,
    *,
    clock=oc.now_utc,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    report: dict[str, Any] = {"mapped": [], "unmapped": [], "events_listed": 0, "odds_requests": 0, "no_odds_for_event": [], "bookmakers_requested": bookmakers, "stopped": None}
    if not fixtures:
        return [], report
    start = min(f.kickoff for f in fixtures) - timedelta(minutes=30)
    end = max(f.kickoff for f in fixtures) + timedelta(minutes=30)
    snaps: list[dict[str, Any]] = []
    try:
        events = list_events(client, key, start, end, budget)
        report["events_listed"] = len(events)
        mapped, unmapped = oc.map_events_to_fixtures(fixtures, events)
        report["unmapped"] = unmapped
        by_id = {f.match_id: f for f in fixtures}
        order = [mid for mid in (f.match_id for f in fixtures) if mid in mapped]
        for i in range(0, len(order), BATCH):
            chunk = order[i : i + BATCH]
            ids = ",".join(str(mapped[mid][0].event_id) for mid in chunk)
            resp = api_get(client, "/odds/multi", {"eventIds": ids, "bookmakers": ",".join(bookmakers)}, key, budget)
            report["odds_requests"] += 1
            fetched_at = clock()
            by_event = {str(e.get("id")): e for e in (resp if isinstance(resp, list) else []) if isinstance(e, dict)}
            for mid in chunk:
                ev, conf, evidence = mapped[mid]
                fx = by_id[mid]
                entry = by_event.get(str(ev.event_id))
                parsed = parse_event_odds(entry) if entry else []
                report["mapped"].append({"fotmob_match_id": mid, "event_id": ev.event_id, "confidence": conf, "league": ev.league, "bookmakers_with_odds": [p["bookmaker"] for p in parsed]})
                if not parsed:
                    report["no_odds_for_event"].append(mid)
                    continue
                mapping = {"method": "teams+kickoff", "confidence": conf, "evidence": f"{evidence}; vendor event {ev.event_id} '{ev.home}' - '{ev.away}'", "vendor_event_id": ev.event_id}
                for p in parsed:
                    snaps.append(
                        oc.build_snapshot(
                            fixture=fx, source=SOURCE, bookmaker=p["bookmaker"], markets=p["markets"], fetched_at=fetched_at,
                            mapping=mapping, odds_updated_at=p["updated_at"], extra={"markets_rejected": p["rejected"]},
                        )
                    )
    except QuotaStop as exc:
        report["stopped"] = str(exc)
    report["requests_used"] = budget.used
    report["ratelimit_remaining_header"] = budget.remaining_header
    return snaps, report


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", default=oc.now_utc().strftime("%Y-%m-%d"), help="UTC date of the fixture list (YYYY-MM-DD)")
    ap.add_argument("--bookmakers", help="comma-separated vendor bookmaker names (default: the account's selected ones, else Iddaa,Bet365)")
    ap.add_argument("--competitions", default=",".join(str(x) for x in oc.TARGET13))
    ap.add_argument("--fixtures-json", type=Path, help="FotMob day-list JSON instead of fetching it")
    ap.add_argument("--hours-ahead", type=float, default=36.0)
    ap.add_argument("--max-requests", type=int, default=40, help="hard cap of vendor requests in this run")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)

    key = os.environ.get(ENV_KEY, "").strip()
    if not key:
        print(
            f"{ENV_KEY} is not set. Create a free key at https://odds-api.io (e-mail sign-up, no card), then set the "
            f"environment variable; the key is never written to disk by this script.",
            file=sys.stderr,
        )
        return 5
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
    budget = RequestBudget(max_requests=args.max_requests)
    with httpx.Client(timeout=25.0) as client:
        try:
            if args.bookmakers:
                bookmakers = [b.strip() for b in args.bookmakers.split(",") if b.strip()]
            else:
                bookmakers = selected_bookmakers(client, key, budget) or DEFAULT_BOOKMAKERS.split(",")
            snaps, report = collect(client, key, fixtures, bookmakers, budget)
        except OddsApiError as exc:
            print(f"STOP: {oc.redact(exc, key)}", file=sys.stderr)
            return 4
    n = oc.append_jsonl(out, snaps)
    report.update({"date": args.date, "fixtures_collected": len(fixtures), "snapshots_written": n, "output": str(out)})
    out.with_name(out.stem + ".oddsapiio_run.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {n} snapshots to {out}; mapped {len(report['mapped'])}, unmapped {len(report['unmapped'])}, requests {report.get('requests_used')}, stopped: {report['stopped']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
