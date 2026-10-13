"""Independent re-fetch check of the FotMob squads/players dataset (VERIFICATION ONLY).

Picks N random players from ``backend/data/players/players.jsonl``, re-fetches
``/api/data/playerData`` with ``urllib`` (a different HTTP stack than the collector's httpx),
extracts 20 fields with code that shares nothing with the collector's parser, and compares
them with the parsed rows (players.jsonl, player_market_values.jsonl, player_career.jsonl,
player_recent_matches.jsonl). Writes nothing.

Every mismatch is classified by applying the same independent extractor to the raw cache
file (``backend/data/raw_cache/fotmob_players/<id>.json.gz``) that the parsed row came from:
  parser_bug      raw-cache value != parsed value  -> the collector's parser is wrong
  source_changed  raw-cache value == parsed value != live value -> FotMob changed since snapshot_at

Politeness: the shared limiter (fotmob_rate.acquire) before every request, >= 1 s between
requests, report_429 + abort on HTTP 429, abort on 403 / non-JSON (challenge) answers.

``--offline-all`` (no network): the same independent extractor applied to EVERY cached raw file,
compared with the parsed rows (any mismatch there is a parser bug).

Usage (from backend/):
  venv/Scripts/python.exe scripts/data_collection/verify_fotmob_squads_players.py --n 10 --seed 20261013
  venv/Scripts/python.exe scripts/data_collection/verify_fotmob_squads_players.py --offline-all
Exit code: 0 = no parser_bug, 1 = at least one parser_bug, 2 = aborted (429/403/challenge).
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import fotmob_rate  # noqa: E402

BACKEND_DIR = SCRIPT_DIR.parents[1]
OUT_DIR = BACKEND_DIR / "data" / "players"
RAW_DIR = BACKEND_DIR / "data" / "raw_cache" / "fotmob_players"
URL = "https://www.fotmob.com/api/data/playerData?id={pid}"
USER_AGENT = "Mozilla/5.0 (TUTAR X research collector; low-rate)"


# ------------------------------------------------------------------ independent extraction


def _info(d: dict, translation_key: str) -> dict:
    for item in d.get("playerInformation") or []:
        if item.get("translationKey") == translation_key:
            return item
    return {}


def extract(d: dict) -> dict:
    """20 fields straight from a playerData body (independent of the collector's parser)."""
    ml = d.get("mainLeague") or {}
    values = (d.get("marketValues") or {}).get("values") or []
    sections = ((d.get("careerHistory") or {}).get("careerItems") or {}).values()
    recent = {}
    for m in d.get("recentMatches") or []:
        r = (m.get("ratingProps") or {}).get("rating")
        # documented dataset rule: FotMob's integer 0 = "no rating" -> null
        rating = None if r in (None, "", 0) else float(r)
        recent[int(m["id"])] = (
            m.get("minutesPlayed"), m.get("goals"), m.get("assists"), m.get("yellowCards"), m.get("redCards"),
            rating, m.get("onBench"),
        )
    bd = (d.get("birthDate") or {}).get("utcTime")
    # documented dataset rule: FotMob's "unknown" placeholder 0001-01-01 -> null (raw kept in birth_date_raw)
    if isinstance(bd, str) and bd[:10] == "0001-01-01":
        bd = None
    return {
        "name": d.get("name"),
        "birth_date": bd,
        "contract_end": (d.get("contractEnd") or {}).get("utcTime"),
        "primary_team_id": (d.get("primaryTeam") or {}).get("teamId"),
        "primary_team_name": (d.get("primaryTeam") or {}).get("teamName"),
        "on_loan": (d.get("primaryTeam") or {}).get("onLoan"),
        "position_primary_key": ((d.get("positionDescription") or {}).get("primaryPosition") or {}).get("key"),
        "height_cm": (_info(d, "height_sentencecase").get("value") or {}).get("numberValue"),
        "preferred_foot": (_info(d, "preferred_foot").get("value") or {}).get("key"),
        "country_code": _info(d, "country_sentencecase").get("countryCode"),
        "shirt_number": (_info(d, "shirt").get("value") or {}).get("numberValue"),
        "market_value": (_info(d, "transfer_value").get("value") or {}).get("numberValue"),
        "injury_key": (d.get("injuryInformation") or {}).get("key"),
        "international_duty_present": d.get("internationalDuty") is not None,
        "main_league_id": ml.get("leagueId"),
        "main_league_season": ml.get("season"),
        "main_league_stats": {s.get("localizedTitleId"): s.get("value") for s in ml.get("stats") or []} or None,
        "market_values_count": len(values),
        "market_value_last": [values[-1].get("date"), values[-1].get("value")] if values else None,
        "career_rows": sum(len(s.get("teamEntries") or []) + len(s.get("seasonEntries") or []) for s in sections),
        "_recent": recent,
    }


def parsed_view(pid: int, prow: dict, mv_rows: list[dict], career_rows: list[dict], recent_rows: list[dict]) -> dict:
    ml = prow.get("main_league") or {}
    return {
        "name": prow.get("name"),
        "birth_date": prow.get("birth_date"),
        "contract_end": prow.get("contract_end"),
        "primary_team_id": prow.get("primary_team_id"),
        "primary_team_name": prow.get("primary_team_name"),
        "on_loan": prow.get("on_loan"),
        "position_primary_key": prow.get("position_primary_key"),
        "height_cm": prow.get("height_cm"),
        "preferred_foot": prow.get("preferred_foot"),
        "country_code": prow.get("country_code"),
        "shirt_number": prow.get("shirt_number"),
        "market_value": prow.get("market_value"),
        "injury_key": prow.get("injury_key"),
        "international_duty_present": prow.get("international_duty") is not None,
        "main_league_id": ml.get("league_id"),
        "main_league_season": ml.get("season"),
        "main_league_stats": ml.get("stats") or None,
        "market_values_count": len(mv_rows),
        "market_value_last": [mv_rows[-1]["date"], mv_rows[-1]["value"]] if mv_rows else None,
        "career_rows": len(career_rows),
        "_recent": {
            r["match_id"]: (r["minutes_played"], r["goals"], r["assists"], r["yellow_cards"], r["red_cards"],
                            r["rating"], r["on_bench"])
            for r in recent_rows
        },
    }


# ------------------------------------------------------------------ io


def _rows(path: Path, wanted: set[int]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = defaultdict(list)
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("player_id") in wanted:
                out[r["player_id"]].append(r)
    return out


class Abort(RuntimeError):
    pass


def fetch_live(pid: int, timeout: float) -> dict:
    fotmob_rate.acquire()
    req = urllib.request.Request(URL.format(pid=pid), headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ctype = resp.headers.get("Content-Type", "")
            body = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            fotmob_rate.report_429(float(exc.headers.get("Retry-After") or 60))
        raise Abort(f"HTTP {exc.code} for player {pid}") from exc
    if "json" not in ctype.lower():
        raise Abort(f"non-JSON answer ({ctype}) for player {pid}: possible challenge page")
    return json.loads(body)


# ------------------------------------------------------------------ main


def compare(pid: int, reference: dict, parsed: dict, raw: dict | None, per_field: dict, recent_stats: Counter,
            details: list[str]) -> None:
    """Compare ``reference`` (live, or the raw cache in --offline-all) with ``parsed``; when ``raw`` is
    given, a mismatch whose raw value equals the parsed value is a source change, else a parser bug."""
    for field in [k for k in reference if not k.startswith("_")]:
        per_field[field]["compared"] += 1
        if reference[field] == parsed[field]:
            per_field[field]["equal"] += 1
        elif raw is not None and raw[field] == parsed[field]:
            per_field[field]["source_changed"] += 1
            details.append(f"{pid} {field}: source_changed parsed/raw={parsed[field]!r} live={reference[field]!r}")
        else:
            per_field[field]["parser_bug"] += 1
            details.append(f"{pid} {field}: PARSER_BUG parsed={parsed[field]!r} reference={reference[field]!r}")
    for mid, pv in parsed["_recent"].items():
        if mid not in reference["_recent"]:
            recent_stats["parsed_only (dropped from the reference list)"] += 1
            continue
        recent_stats["compared"] += 1
        if reference["_recent"][mid] == pv:
            recent_stats["equal"] += 1
        elif raw is not None and raw["_recent"].get(mid) == pv:
            recent_stats["source_changed"] += 1
            details.append(f"{pid} recent {mid}: source_changed parsed={pv} live={reference['_recent'][mid]}")
        else:
            recent_stats["parser_bug"] += 1
            details.append(f"{pid} recent {mid}: PARSER_BUG parsed={pv} reference={reference['_recent'][mid]}")
    recent_stats["reference_only (new since snapshot)"] += len(set(reference["_recent"]) - set(parsed["_recent"]))


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=10, help="players to re-fetch live")
    ap.add_argument("--seed", type=int, default=20261013)
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between live requests (min 1)")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--offline-all", action="store_true",
                    help="no network: compare the independent extraction of EVERY cached raw file with the parsed rows")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--raw-dir", default=str(RAW_DIR))
    args = ap.parse_args(argv)
    out_dir, raw_dir = Path(args.out_dir), Path(args.raw_dir)

    players = {}
    with (out_dir / "players.jsonl").open("r", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            players[r["player_id"]] = r
    if args.offline_all:
        sample = sorted(players)
    else:
        sample = random.Random(args.seed).sample(sorted(players), min(args.n, len(players)))
    wanted = set(sample)
    mv = _rows(out_dir / "player_market_values.jsonl", wanted)
    career = _rows(out_dir / "player_career.jsonl", wanted)
    recent = _rows(out_dir / "player_recent_matches.jsonl", wanted)

    per_field: dict[str, Counter] = defaultdict(Counter)
    details: list[str] = []
    recent_stats: Counter = Counter()
    for i, pid in enumerate(sample):
        raw = extract(json.loads(gzip.decompress((raw_dir / f"{pid}.json.gz").read_bytes())))
        parsed = parsed_view(pid, players[pid], mv.get(pid, []), career.get(pid, []), recent.get(pid, []))
        if args.offline_all:
            compare(pid, raw, parsed, None, per_field, recent_stats, details)
            continue
        if i:
            time.sleep(max(1.0, args.delay))
        try:
            live = extract(fetch_live(pid, args.timeout))
        except Abort as exc:
            print(f"ABORTED: {exc}")
            return 2
        compare(pid, live, parsed, raw, per_field, recent_stats, details)
        print(f"checked player {pid} ({players[pid].get('name')}, snapshot {players[pid].get('snapshot_at')})",
              flush=True)

    mode = "offline: raw cache vs parsed rows" if args.offline_all else "live re-fetch vs parsed rows"
    print()
    print(f"Mode: {mode}; players: {len(sample)}" + ("" if args.offline_all else f" (seed {args.seed}): {sample}"))
    print()
    print("| Field | Compared | Equal | Source changed | Parser bug |")
    print("|---|---|---|---|---|")
    bugs = 0
    for field, c in per_field.items():
        bugs += c["parser_bug"]
        print(f"| {field} | {c['compared']} | {c['equal']} | {c['source_changed']} | {c['parser_bug']} |")
    bugs += recent_stats["parser_bug"]
    print(f"| recent matches (7 values per match) | {recent_stats['compared']} | {recent_stats['equal']} | "
          f"{recent_stats['source_changed']} | {recent_stats['parser_bug']} |")
    print()
    print(f"Recent-match list changes: {dict(recent_stats)}")
    print(f"Fields compared per player: {len(per_field)} + recent matches; total parser bugs: {bugs}")
    for d in details[:200]:
        print("  " + d)
    return 1 if bugs else 0


if __name__ == "__main__":
    sys.exit(main())
