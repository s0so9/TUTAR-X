"""Collect pre-match bookmaker odds for the featured matches of a day from FotMob's match-odds endpoint.

RESEARCH PROTOTYPE (2026-10-15) - not wired into the app or the model.

Source: ``GET https://www.fotmob.com/api/data/matchOdds?matchId=<FotMob match id>&ccode3=<ISO3 country>``
(the same unofficial JSON API family as ``/api/data/matchDetails``). FotMob shows odds of its affiliate
bookmakers per country, so the bookmaker depends on ``ccode3`` (observed 2026-10-15: DEU Tipico, AUT Interwetten,
GBR Bet365 / Betfair / Betfred (varies), ESP Bet365 / 1xBet (varies), FRA Unibet, BEL Ladbrokes, PRT Bwin, POL SuperBet,
MEX Novibet; TUR, USA, ITA, NLD, BRA answer ``null`` = no odds). The request is answered with a 307 redirect that
adds ``&bettingProvider=<provider key>``; this script follows it (limiter before every hop) and records the
provider. Odds belong to a FotMob match id, so no team mapping is needed; a Draw-No-Bet market (team names inside)
is used as an extra identity check where the provider sends one.

!!! LEGAL STATUS - READ BEFORE USE !!!
  * https://www.fotmob.com/robots.txt: ``User-agent: *`` has ``Disallow: /api/*`` (only a few search bots are allowed).
  * https://www.fotmob.com/tos.txt ("DATA USAGE & SCRAPING"): use of FotMob data without express written consent
    is prohibited; "automatic services (robots, spiders, ...) as well as other methods for systematic, regular, or
    bulk retrieval of data is expressly forbidden".
  The project's other FotMob collectors already operate in the same area. This script therefore does NOT run
  unless ``--accept-fotmob-terms-risk`` is passed: the owner must decide (ideally with FotMob's written
  permission). It never works around 403 / challenge pages (exit code 2) and uses the shared limiter.

Usage (from backend/):
  venv/Scripts/python.exe scripts/data_collection/collect_odds_fotmob.py --date 2026-10-15 \
      --countries DEU,AUT,ESP --accept-fotmob-terms-risk
Output: data/odds/<date>.jsonl (one line = one bookmaker's prices for one match at one fetch time), plus
data/odds/<date>.fotmob_run.json (counts, countries without odds, rejected markets, errors).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

import httpx

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import fotmob_rate  # noqa: E402  (shared cross-process FotMob limiter, sibling module)
import odds_common as oc  # noqa: E402

SOURCE = "fotmob_matchodds"
DEFAULT_COUNTRIES = "DEU,AUT,ESP"
# FotMob market key (headerTranslationKey) -> canonical market
KEY_1X2 = "who_will_win"
KEY_BTTS = "both_score"
KEY_DC = "double_chance"
KEY_OU = "odds_goals_over_under"
KEY_DNB = "odds_draw_no_bet"

_NUM_RE = re.compile(r"(\d+(?:[.,]\d+)?)")


def _sel_name(sel: dict[str, Any]) -> str:
    return str(sel.get("name") or "").strip().lower()


def _line_from(*texts: Any) -> Optional[float]:
    for t in texts:
        if t is None:
            continue
        m = _NUM_RE.search(str(t))
        if m:
            try:
                return float(m.group(1).replace(",", "."))
            except ValueError:
                continue
    return None


def parse_fotmob_match_odds(payload: Any) -> dict[str, Any]:
    """Canonical markets from one FotMob ``matchOdds`` answer.

    Returns {provider, provider_id, odds_type, markets, markets_rejected, headers_seen, dnb_team_names}.
    ``markets`` only holds markets whose prices are complete and plausible (``oc.build_market``); a market that
    was present but failed validation is listed in ``markets_rejected`` with the reason; one that the provider did
    not send is simply absent (``missing_markets`` is derived by the caller). Nothing is filled in.
    """
    out: dict[str, Any] = {
        "provider": payload.get("persistentKey"),
        "provider_id": str(payload.get("providerId")) if payload.get("providerId") is not None else None,
        "odds_type": (payload.get("odds") or {}).get("oddsType"),
        "markets": {},
        "markets_rejected": {},
        "headers_seen": [],
        "dnb_team_names": None,
    }
    odds = payload.get("odds") or {}
    all_markets: list[dict[str, Any]] = []
    for tab in odds.get("oddsTabMarkets") or []:
        all_markets.extend(tab.get("markets") or [])
    all_markets.extend(odds.get("matchfactMarkets") or [])

    raw: dict[str, dict[str, Any]] = {}  # canonical market -> outcome -> raw price (first one wins)
    seen: list[str] = []
    for m in all_markets:
        key = (m.get("headerTranslationKey") or (m.get("fotMobMarketTypeId") or {}).get("translationKey") or "").strip()
        if key and key not in seen:
            seen.append(key)
        sels = m.get("selections") or []
        header = m.get("header")
        if key == KEY_1X2:
            mapping = {"1": "home", "x": "draw", "2": "away"}
            vals = {mapping[_sel_name(s)]: s.get("oddsDecimal") for s in sels if _sel_name(s) in mapping}
            raw.setdefault("1x2", vals)
        elif key == KEY_BTTS:
            vals = {_sel_name(s): s.get("oddsDecimal") for s in sels if _sel_name(s) in ("yes", "no")}
            raw.setdefault("btts", vals)
        elif key == KEY_DC:
            dmap = {"1x": "1x", "x1": "1x", "12": "12", "21": "12", "x2": "x2", "2x": "x2"}
            vals = {dmap[_sel_name(s)]: s.get("oddsDecimal") for s in sels if _sel_name(s) in dmap}
            raw.setdefault("double_chance", vals)
        elif key == KEY_OU:
            # one market per line ("Over/Under 2.5": Over / Under) or one market with "Over 2.5" / "Under 2.5"
            by_line: dict[float, dict[str, Any]] = {}
            for s in sels:
                nm = _sel_name(s)
                side = "over" if nm.startswith("over") else "under" if nm.startswith("under") else None
                line = _line_from(s.get("name"), s.get("value"), header)
                if side is None or line is None:
                    continue
                by_line.setdefault(line, {})[side] = s.get("oddsDecimal")
            for line, vals in by_line.items():
                name = oc.ou_market_name(line)
                if name:
                    raw.setdefault(name, vals)
        elif key == KEY_DNB:
            names = [str(s.get("name") or "") for s in sels]
            if len(names) == 2 and out["dnb_team_names"] is None:
                out["dnb_team_names"] = names
    out["headers_seen"] = seen
    for name, vals in raw.items():
        rec = oc.build_market(name, vals)
        if rec is None:
            missing = [o for o in oc.MARKETS[name] if oc.parse_decimal_odds(vals.get(o)) is None]
            out["markets_rejected"][name] = f"incomplete or implausible prices (missing/invalid: {missing})" if missing else "overround outside 0.99-1.40"
        else:
            out["markets"][name] = rec
    return out


def check_team_names(fixture: oc.Fixture, dnb_names: Optional[list[str]]) -> tuple[str, str]:
    """('verified' | 'mismatch' | 'not_available', evidence). Draw No Bet selections are [home team, away team]."""
    if not dnb_names:
        return "not_available", "provider sends no market with team names"
    sh = oc.team_similarity(fixture.home, dnb_names[0])
    sa = oc.team_similarity(fixture.away, dnb_names[1])
    if min(sh, sa) >= oc.ACCEPT_MIN_CONFIDENCE:
        return "verified", f"draw-no-bet team names {dnb_names} match (sim {sh:.2f}/{sa:.2f})"
    return "mismatch", f"draw-no-bet team names {dnb_names} do not match fixture '{fixture.home}' - '{fixture.away}' (sim {sh:.2f}/{sa:.2f})"


def snapshot_from_payload(fixture: oc.Fixture, country: str, payload: Any, fetched_at) -> tuple[Optional[dict[str, Any]], dict[str, Any]]:
    """(snapshot or None, notes). None when the payload is not usable pre-match odds for this fixture."""
    parsed = parse_fotmob_match_odds(payload)
    notes: dict[str, Any] = {"provider": parsed["provider"], "markets_rejected": parsed["markets_rejected"], "headers_seen": parsed["headers_seen"]}
    if parsed["odds_type"] != "PreMatch":
        notes["skipped"] = f"oddsType is {parsed['odds_type']!r}, not PreMatch"
        return None, notes
    if not parsed["markets"]:
        notes["skipped"] = "no usable canonical market in the answer"
        return None, notes
    status, evidence = check_team_names(fixture, parsed["dnb_team_names"])
    notes["team_check"] = status
    if status == "mismatch":
        notes["skipped"] = evidence
        return None, notes
    mapping = {
        "method": "fotmob_match_id",
        "confidence": 1.0,
        "evidence": "request keyed by the FotMob match id; " + evidence,
        "team_name_check": status,
    }
    snap = oc.build_snapshot(
        fixture=fixture,
        source=SOURCE,
        bookmaker=str(parsed["provider"]),
        markets=parsed["markets"],
        fetched_at=fetched_at,
        mapping=mapping,
        region=country,
        extra={"provider_id": parsed["provider_id"], "markets_rejected": parsed["markets_rejected"]},
    )
    return snap, notes


def select_fixtures(fixtures: list[oc.Fixture], now, *, hours_ahead: float, match_ids: Optional[set[str]], max_matches: Optional[int]) -> list[oc.Fixture]:
    """Pre-match only: not started / finished / cancelled and kicking off within ``hours_ahead``."""
    sel = []
    for f in fixtures:
        if f.started or f.finished or f.cancelled or f.kickoff <= now:
            continue
        if (f.kickoff - now).total_seconds() > hours_ahead * 3600:
            continue
        if match_ids and f.match_id not in match_ids:
            continue
        sel.append(f)
    return sel[:max_matches] if max_matches else sel


def collect(
    client: Any,
    fixtures: list[oc.Fixture],
    countries: list[str],
    *,
    pins: Optional[dict[str, str]] = None,
    limiter: Any = None,
    raw_dir: Optional[Path] = None,
    clock=oc.now_utc,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """One request (+ redirect hop) per match and country. Returns (snapshots, run report). Raises
    ``oc.FotmobBlocked`` (stop the run) / ``oc.FotmobRateLimited``; other per-request errors are logged and skipped."""
    snaps: list[dict[str, Any]] = []
    report: dict[str, Any] = {"requests_matches": 0, "no_odds": [], "skipped": [], "errors": [], "providers_seen": {}}
    for fx in fixtures:
        for cc in countries:
            q = f"/api/data/matchOdds?matchId={fx.match_id}&ccode3={cc}"
            if pins and cc in pins:
                q += f"&bettingProvider={pins[cc]}"
            report["requests_matches"] += 1
            try:
                payload = oc.fotmob_get(client, q, limiter=limiter)
            except (oc.FotmobBlocked, oc.FotmobRateLimited):
                raise
            except Exception as exc:  # noqa: BLE001 - one bad answer must not stop the day
                report["errors"].append({"match_id": fx.match_id, "country": cc, "error": oc.redact(exc)})
                continue
            fetched_at = clock()
            if not payload:
                report["no_odds"].append({"match_id": fx.match_id, "country": cc})
                continue
            if raw_dir is not None:
                raw_dir.mkdir(parents=True, exist_ok=True)
                (raw_dir / f"fotmob_matchOdds_{fx.match_id}_{cc}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
            snap, notes = snapshot_from_payload(fx, cc, payload, fetched_at)
            if notes.get("provider"):
                report["providers_seen"].setdefault(cc, [])
                if notes["provider"] not in report["providers_seen"][cc]:
                    report["providers_seen"][cc].append(notes["provider"])
            if snap is None:
                report["skipped"].append({"match_id": fx.match_id, "country": cc, **{k: v for k, v in notes.items() if k in ("provider", "skipped")}})
                continue
            snaps.append(snap)
    return snaps, report


def collect_from_raw(raw_dir: Path, fixtures: list[oc.Fixture]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """OFFLINE: parse previously recorded raw answers (``fotmob_matchOdds_<matchId>_<CC>.json``) into snapshots.
    No network. ``fetched_at`` is the file's modification time (when the answer was recorded)."""
    from datetime import datetime, timezone

    by_id = {f.match_id: f for f in fixtures}
    snaps: list[dict[str, Any]] = []
    report: dict[str, Any] = {"files": 0, "no_odds": [], "skipped": [], "errors": [], "providers_seen": {}}
    for path in sorted(raw_dir.glob("fotmob_matchOdds_*_*.json")):
        m = re.fullmatch(r"fotmob_matchOdds_(\d+)_([A-Z]{3})\.json", path.name)
        if not m:
            continue
        report["files"] += 1
        mid, cc = m.group(1), m.group(2)
        fx = by_id.get(mid)
        if fx is None:
            report["skipped"].append({"file": path.name, "skipped": "match id not in the fixture list"})
            continue
        if fx.started or fx.finished or fx.cancelled:
            report["skipped"].append({"file": path.name, "skipped": "fixture already started/finished/cancelled"})
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            report["errors"].append({"file": path.name, "error": str(exc)})
            continue
        if not payload:
            report["no_odds"].append({"match_id": mid, "country": cc})
            continue
        fetched_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        snap, notes = snapshot_from_payload(fx, cc, payload, fetched_at)
        if notes.get("provider"):
            report["providers_seen"].setdefault(cc, [])
            if notes["provider"] not in report["providers_seen"][cc]:
                report["providers_seen"][cc].append(notes["provider"])
        if snap is None:
            report["skipped"].append({"file": path.name, **{k: v for k, v in notes.items() if k in ("provider", "skipped")}})
            continue
        snap["fetched_at_source"] = "raw file modification time"
        snaps.append(snap)
    return snaps, report


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", default=oc.now_utc().strftime("%Y-%m-%d"), help="UTC date of the fixture list (YYYY-MM-DD)")
    ap.add_argument("--countries", default=DEFAULT_COUNTRIES, help="comma-separated ISO3 country codes (FotMob picks the bookmaker per country)")
    ap.add_argument("--pin", action="append", default=[], metavar="CC=PROVIDER_KEY", help="pin the provider of a country, e.g. DEU=Tipico_Germany (only valid keys of that country work)")
    ap.add_argument("--competitions", default=",".join(str(x) for x in oc.TARGET13))
    ap.add_argument("--fixtures-json", type=Path, help="FotMob day-list JSON instead of fetching it (offline)")
    ap.add_argument("--match-ids", help="comma-separated FotMob match ids to keep")
    ap.add_argument("--max-matches", type=int)
    ap.add_argument("--hours-ahead", type=float, default=36.0)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--raw-dir", type=Path, help="also store the raw answers here (research samples)")
    ap.add_argument("--from-raw", type=Path, help="OFFLINE: parse recorded raw answers from this directory (needs --fixtures-json); no network, no flag needed")
    ap.add_argument("--accept-fotmob-terms-risk", action="store_true", help="required: acknowledges FotMob robots.txt (Disallow /api/*) and ToS")
    args = ap.parse_args(argv)

    if args.from_raw:
        if not args.fixtures_json:
            print("--from-raw needs --fixtures-json", file=sys.stderr)
            return 1
        fx_all = oc.parse_fotmob_matches_payload(json.loads(args.fixtures_json.read_text(encoding="utf-8")), [int(x) for x in args.competitions.split(",") if x.strip()])
        snaps, report = collect_from_raw(args.from_raw, fx_all)
        out = args.out or (oc.DEFAULT_ODDS_DIR / f"{args.date}.jsonl")
        n = oc.append_jsonl(out, snaps)
        report.update({"date": args.date, "mode": "offline_from_raw", "snapshots_written": n, "output": str(out)})
        out.with_name(out.stem + ".fotmob_run.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"offline: parsed {report['files']} raw files, wrote {n} snapshots to {out}; skipped {len(report['skipped'])}")
        return 0

    if not args.accept_fotmob_terms_risk:
        print(
            "Refusing to run: FotMob's robots.txt disallows /api/* for generic clients and its terms forbid automated, "
            "systematic or bulk retrieval without written consent (see the docstring). Pass --accept-fotmob-terms-risk "
            "only if the owner accepted that risk.",
            file=sys.stderr,
        )
        return 3
    featured = [int(x) for x in args.competitions.split(",") if x.strip()]
    countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    pins = {}
    for item in args.pin:
        cc, _, key = item.partition("=")
        if cc and key:
            pins[cc.strip().upper()] = key.strip()
    out = args.out or (oc.DEFAULT_ODDS_DIR / f"{args.date}.jsonl")

    with httpx.Client(timeout=25.0) as client:
        try:
            if args.fixtures_json:
                fixtures = oc.parse_fotmob_matches_payload(json.loads(args.fixtures_json.read_text(encoding="utf-8")), featured)
            else:
                fixtures = oc.fetch_fotmob_fixtures(client, args.date, featured, limiter=fotmob_rate)
            ids = {x.strip() for x in args.match_ids.split(",")} if args.match_ids else None
            chosen = select_fixtures(fixtures, oc.now_utc(), hours_ahead=args.hours_ahead, match_ids=ids, max_matches=args.max_matches)
            print(f"{len(fixtures)} featured fixtures on {args.date}, {len(chosen)} pre-match within {args.hours_ahead:g} h; countries {countries}")
            snaps, report = collect(client, chosen, countries, pins=pins, raw_dir=args.raw_dir, limiter=fotmob_rate)
        except oc.FotmobBlocked as exc:
            print(f"STOP: {exc}. Nothing is worked around.", file=sys.stderr)
            return 2
        except oc.FotmobRateLimited as exc:
            print(f"STOP: {exc}; the shared limiter is cooling down.", file=sys.stderr)
            return 4
    n = oc.append_jsonl(out, snaps)
    report.update({"date": args.date, "fixtures_featured": len(fixtures), "fixtures_collected": len(chosen), "countries": countries, "snapshots_written": n, "output": str(out)})
    run_path = out.with_name(out.stem + ".fotmob_run.json")
    run_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {n} snapshots to {out}; no-odds answers {len(report['no_odds'])}, skipped {len(report['skipped'])}, errors {len(report['errors'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
