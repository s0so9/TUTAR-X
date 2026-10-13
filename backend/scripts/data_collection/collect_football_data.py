"""Collect football-data.co.uk results + bookmaker odds and map them to our DB.

Source: https://www.football-data.co.uk (free CSVs; results, match stats and
pre-match / closing odds). Terms: free for personal/non-commercial use, credit
football-data.co.uk. We make ~60 requests in total and cache every file.

Network note (2026-10-13): from this machine www.football-data.co.uk answers
with a redirect to football-data.co.uk whose server is unreachable (TCP
timeout). The script therefore falls back to the Internet Archive copy of the
exact same URL (https://web.archive.org/web/<ts>id_/<url>) and records the
snapshot timestamp of every file in raw/football_data/manifest.json. An
archived in-progress season file is only as fresh as its snapshot.

Outputs (backend/data/external/):
  football_data_matches.csv    one row per source match (+ DB ids, normalised closing probs)
  team_name_map.csv            rows with source=football_data
  team_name_unmapped.csv       rows with source=football_data
  football_data_coverage.json  per-division coverage numbers

Usage (from backend/):
  venv/Scripts/python.exe -I scripts/data_collection/collect_football_data.py            # download (cached) + build
  venv/Scripts/python.exe -I scripts/data_collection/collect_football_data.py --skip-download
  venv/Scripts/python.exe -I scripts/data_collection/collect_football_data.py --refresh-current   # re-fetch 2627

History mode (past seasons 2021/22-2024/25 + a 2025/26 re-check, mapped to FotMob
match ids through FotMob league fixture lists; logic in football_data_history.py;
writes football_data_history*.csv/json and never touches the outputs above):
  venv/Scripts/python.exe -I scripts/data_collection/collect_football_data.py --history
  venv/Scripts/python.exe -I scripts/data_collection/collect_football_data.py --history --skip-download
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from external_common import (  # noqa: E402
    EXTERNAL_DIR,
    RAW_DIR,
    USER_AGENT,
    SourceMatch,
    build_db_index,
    db_connect,
    fixture_overlap_map,
    load_db_competitions,
    load_db_matches,
    load_db_teams,
    load_manifest,
    name_similarity,
    save_manifest,
    write_team_map,
)

SOURCE = "football_data"
FD_RAW = RAW_DIR / "football_data"
MANIFEST = FD_RAW / "manifest.json"
OUT_MATCHES = EXTERNAL_DIR / "football_data_matches.csv"
OUT_COVERAGE = EXTERNAL_DIR / "football_data_coverage.json"

ORIGIN = "https://www.football-data.co.uk"
WAYBACK = "https://web.archive.org/web/{ts}id_/{url}"

# Seasons overlapping our DB (2025-07-01 .. 2026-10-12). 2627 is in progress.
SEASONS = ["2526", "2627"]
CURRENT_SEASON = "2627"

# Main-league files: code -> (ClubElo-style country code, league name)
MAIN_DIVISIONS = {
    "E0": ("ENG", "Premier League"), "E1": ("ENG", "Championship"), "E2": ("ENG", "League One"),
    "E3": ("ENG", "League Two"), "EC": ("ENG", "National League"),
    "SC0": ("SCO", "Premiership"), "SC1": ("SCO", "Championship"), "SC2": ("SCO", "League One"),
    "SC3": ("SCO", "League Two"),
    "D1": ("GER", "Bundesliga"), "D2": ("GER", "2. Bundesliga"),
    "I1": ("ITA", "Serie A"), "I2": ("ITA", "Serie B"),
    "SP1": ("ESP", "La Liga"), "SP2": ("ESP", "Segunda Division"),
    "F1": ("FRA", "Ligue 1"), "F2": ("FRA", "Ligue 2"),
    "N1": ("NED", "Eredivisie"), "B1": ("BEL", "Jupiler Pro League"), "P1": ("POR", "Liga Portugal"),
    "T1": ("TUR", "Super Lig"), "G1": ("GRE", "Super League"),
}
# "New leagues" files (all seasons in one file, closing odds only)
EXTRA_LEAGUES = {
    "ARG": "ARG", "AUT": "AUT", "BRA": "BRA", "CHN": "CHN", "DNK": "DEN", "FIN": "FIN", "IRL": "IRL",
    "JPN": "JPN", "MEX": "MEX", "NOR": "NOR", "POL": "POL", "ROU": "ROU", "RUS": "RUS", "SWE": "SWE",
    "SWZ": "SUI", "USA": "USA",
}

NON_ODDS_COLUMNS = {
    "Div", "Date", "Time", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR", "HTHG", "HTAG", "HTR", "Referee",
    "HS", "AS", "HST", "AST", "HF", "AF", "HC", "AC", "HY", "AY", "HR", "AR", "HHW", "AHW", "HO", "AO",
    "HFKC", "AFKC", "HBP", "ABP", "Attendance", "Country", "League", "Season", "Home", "Away", "HG", "AG", "Res",
}
STAT_COLUMNS = ["HTHG", "HTAG", "HTR", "HS", "AS", "HST", "AST", "HF", "AF", "HC", "AC", "HY", "AY", "HR", "AR",
                "Referee"]

# Closing-odds preference: Pinnacle closing, then market average closing, then Bet365 closing.
CLOSE_1X2 = [("PSCH", "PSCD", "PSCA"), ("AvgCH", "AvgCD", "AvgCA"), ("B365CH", "B365CD", "B365CA")]
CLOSE_OU25 = [("PC>2.5", "PC<2.5"), ("AvgC>2.5", "AvgC<2.5"), ("B365C>2.5", "B365C<2.5")]
PRE_1X2 = [("PSH", "PSD", "PSA"), ("AvgH", "AvgD", "AvgA"), ("B365H", "B365D", "B365A")]


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def _fetch(url: str, timeout: float) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), resp.geturl()


def _looks_like_csv(body: bytes) -> bool:
    head = body[:400].decode("utf-8-sig", errors="replace")
    return ("HomeTeam" in head or ",Home," in head) and "<html" not in head.lower()


def download_all(refresh_current: bool, delay: float) -> None:
    manifest = load_manifest(MANIFEST)
    origin_ok = True
    targets: list[tuple[str, str, Path]] = []
    for season in SEASONS:
        for div in MAIN_DIVISIONS:
            targets.append((f"{season}/{div}", f"{ORIGIN}/mmz4281/{season}/{div}.csv", FD_RAW / season / f"{div}.csv"))
    for code in EXTRA_LEAGUES:
        targets.append((f"new/{code}", f"{ORIGIN}/new/{code}.csv", FD_RAW / "new" / f"{code}.csv"))

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    for key, url, path in targets:
        is_current = key.startswith(CURRENT_SEASON) or key.startswith("new/")
        if path.exists() and not (refresh_current and is_current):
            continue
        body = final_url = None
        via = None
        if origin_ok:
            try:
                body, final_url = _fetch(url, timeout=15)
                via = "origin"
                if not _looks_like_csv(body):
                    body = None
            except Exception as exc:  # origin unreachable from this network
                print(f"[origin] {key}: {exc!r} -> using web.archive.org from now on")
                origin_ok = False
        if body is None:
            for attempt in range(4):
                try:
                    body, final_url = _fetch(WAYBACK.format(ts=today, url=url), timeout=60)
                    via = "wayback"
                    break
                except urllib.error.HTTPError as exc:
                    if exc.code == 404:
                        print(f"[wayback] {key}: no archived copy")
                        break
                    print(f"[wayback] {key}: HTTP {exc.code}, retry")
                    time.sleep(10 * (attempt + 1))
                except Exception as exc:
                    print(f"[wayback] {key}: {exc!r}, retry")
                    time.sleep(5 * (attempt + 1))
        if body is None or not _looks_like_csv(body):
            manifest[key] = {"url": url, "status": "unavailable", "checked_at": datetime.now(timezone.utc).isoformat()}
            save_manifest(MANIFEST, manifest)
            time.sleep(delay)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        snapshot = None
        if via == "wayback" and final_url and "/web/" in final_url:
            snapshot = final_url.split("/web/")[1].split("id_")[0]
        manifest[key] = {
            "url": url, "fetched_via": via, "effective_url": final_url, "wayback_snapshot": snapshot,
            "bytes": len(body), "fetched_at": datetime.now(timezone.utc).isoformat(), "status": "ok",
        }
        save_manifest(MANIFEST, manifest)
        print(f"[ok] {key} via {via} snapshot={snapshot} bytes={len(body)}")
        time.sleep(delay)


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------


def _parse_date(text: str) -> date | None:
    text = (text or "").strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def _int(text: str | None) -> int | None:
    try:
        return int(float(text)) if text not in (None, "") else None
    except ValueError:
        return None


def _float(text: str | None) -> float | None:
    try:
        v = float(text) if text not in (None, "") else None
    except ValueError:
        return None
    return v if v and v > 1.0 else None  # decimal odds must be > 1


def _read_csv(path: Path) -> list[dict]:
    raw = path.read_bytes()
    if path.suffix == ".gz":  # history files are cached gzip-compressed (football_data_history.py)
        raw = gzip.decompress(raw)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    rows = list(csv.DictReader(io.StringIO(text)))
    return [{(k or "").strip(): (v or "").strip() for k, v in r.items() if k} for r in rows]


def load_source_rows(min_day: date) -> tuple[list[dict], list[str]]:
    """Return unified rows and the ordered list of original odds columns present."""
    rows: list[dict] = []
    odds_cols: list[str] = []
    seen_cols: set[str] = set()

    def note_cols(cols):
        for c in cols:
            if c and c not in NON_ODDS_COLUMNS and c not in seen_cols:
                seen_cols.add(c)
                odds_cols.append(c)

    for season in SEASONS:
        for div, (country, league) in MAIN_DIVISIONS.items():
            path = FD_RAW / season / f"{div}.csv"
            if not path.exists():
                continue
            for r in _read_csv(path):
                d = _parse_date(r.get("Date", ""))
                if not d or not r.get("HomeTeam"):
                    continue
                note_cols(r.keys())
                rows.append({**r, "_date": d, "_division": div, "_country": country, "_league": league,
                             "_season": season, "_home": r["HomeTeam"], "_away": r["AwayTeam"],
                             "_hg": _int(r.get("FTHG")), "_ag": _int(r.get("FTAG")), "_ftr": r.get("FTR", "")})
    for code, country in EXTRA_LEAGUES.items():
        path = FD_RAW / "new" / f"{code}.csv"
        if not path.exists():
            continue
        for r in _read_csv(path):
            d = _parse_date(r.get("Date", ""))
            if not d or d < min_day or not r.get("Home"):
                continue
            note_cols(r.keys())
            rows.append({**r, "_date": d, "_division": code, "_country": country,
                         "_league": f"{r.get('Country', '')} {r.get('League', '')}".strip(),
                         "_season": r.get("Season", ""), "_home": r["Home"], "_away": r["Away"],
                         "_hg": _int(r.get("HG")), "_ag": _int(r.get("AG")), "_ftr": r.get("Res", "")})
    return rows, odds_cols


def implied(row: dict, prefs: list[tuple[str, ...]]) -> tuple[str | None, list[float | None], float | None]:
    """Margin-free implied probabilities (proportional normalisation) from the first complete odds set."""
    for cols in prefs:
        odds = [_float(row.get(c)) for c in cols]
        if all(o is not None for o in odds):
            inv = [1.0 / o for o in odds]  # type: ignore[operator]
            s = sum(inv)
            return cols[0], [round(x / s, 5) for x in inv], round(s - 1.0, 5)
    return None, [None] * len(prefs[0]), None


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def build() -> dict:
    con = db_connect()
    teams = load_db_teams(con)
    comps = load_db_competitions(con)
    db_matches = load_db_matches(con)
    con.close()
    db_min = min(m.day for m in db_matches)
    db_max = max(m.day for m in db_matches)
    db_index = build_db_index(db_matches)
    by_pair: dict[tuple[str, str], list] = defaultdict(list)
    for m in db_matches:
        by_pair[(m.home_id, m.away_id)].append(m)

    rows, odds_cols = load_source_rows(db_min)
    print(f"source rows: {len(rows)}  odds columns: {len(odds_cols)}  DB range {db_min}..{db_max}")

    # Team mapping by fixture overlap, done per country (all divisions and
    # seasons of that country together, so promoted/relegated teams keep their
    # full match history) so equal names in different countries never collide.
    team_map: dict[tuple[str, str], dict] = {}
    mapped_rows, unmapped_rows = [], []
    by_div: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_div[r["_country"]].append(r)
    for div, drows in by_div.items():
        sms = [SourceMatch(r["_date"], r["_home"], r["_away"], r["_hg"], r["_ag"]) for r in drows]
        res = fixture_overlap_map(sms, db_index, db_min, db_max)
        names = sorted({r["_home"] for r in drows} | {r["_away"] for r in drows})
        for name in names:
            info = res.get(name)
            divs = sorted({r["_division"] for r in drows if name in (r["_home"], r["_away"])})
            context = f"{div}: {'+'.join(divs)}"
            if info and info["db_team_id"]:
                tid = info["db_team_id"]
                sim = name_similarity(name, teams[tid][0])
                team_map[(div, name)] = {"id": tid, **info}
                mapped_rows.append({
                    "source": SOURCE, "source_name": name, "source_context": context, "db_team_id": tid,
                    "db_team_provider_id": teams[tid][1], "db_team_name": teams[tid][0],
                    "method": "fixture_overlap+name" if sim >= 0.85 else "fixture_overlap",
                    "confidence": info["confidence"],
                    "evidence": f"{info['votes']}/{info['n_matches']} results co-occur (runner-up {info['runner_up_votes']}); name_sim={sim:.2f}",
                })
            else:
                cand = info["candidate_id"] if info else None
                reason = "no results inside DB date range" if not info else (
                    f"below threshold: {info['votes']}/{info['n_matches']} votes, runner-up {info['runner_up_votes']}")
                unmapped_rows.append({
                    "source": SOURCE, "source_name": name, "source_context": context,
                    "best_candidate_db_team_name": teams[cand][0] if cand else "",
                    "best_candidate_score": info["confidence"] if info else "", "reason": reason,
                })
    write_team_map(SOURCE, mapped_rows, unmapped_rows)

    # Match-level link: same DB home/away ids within +-1 day.
    out_fields = (["date", "time", "division", "country", "league", "season", "home", "away",
                   "home_db_team_id", "away_db_team_id", "db_match_id", "db_competition_name",
                   "db_competition_provider_id", "db_score_agrees", "FTHG", "FTAG", "FTR"]
                  + STAT_COLUMNS
                  + ["close_1x2_source", "p_close_home", "p_close_draw", "p_close_away", "close_1x2_overround",
                     "close_ou25_source", "p_close_over25", "p_close_under25", "close_ou25_overround",
                     "pre_1x2_source", "p_pre_home", "p_pre_draw", "p_pre_away", "pre_1x2_overround"]
                  + odds_cols)
    cov: dict[str, Counter] = defaultdict(Counter)
    div_meta: dict[str, dict] = {}
    rows.sort(key=lambda r: (r["_date"], r["_division"], r["_home"]))
    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_MATCHES.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            div = r["_division"]
            div_meta.setdefault(div, {"country": r["_country"], "league": r["_league"]})
            h = team_map.get((r["_country"], r["_home"]), {}).get("id")
            a = team_map.get((r["_country"], r["_away"]), {}).get("id")
            in_range = db_min <= r["_date"] <= db_max
            c = cov[div]
            c["matches"] += 1
            c["in_db_range"] += int(in_range)
            c["both_teams_mapped"] += int(bool(h and a))
            dbm = None
            if h and a:
                cands = [m for m in by_pair.get((h, a), []) if abs((m.day - r["_date"]).days) <= 1]
                if len(cands) == 1:
                    dbm = cands[0]
            agrees = None
            if dbm is not None:
                c["linked_to_db_match"] += 1
                agrees = (dbm.home_score == r["_hg"] and dbm.away_score == r["_ag"])
                c["score_agrees"] += int(bool(agrees))
            src_1x2, p1x2, ovr = implied(r, CLOSE_1X2)
            src_ou, pou, ovr_ou = implied(r, CLOSE_OU25)
            src_pre, ppre, ovr_pre = implied(r, PRE_1X2)
            c["has_close_1x2"] += int(src_1x2 is not None)
            c["has_close_ou25"] += int(src_ou is not None)
            out = {k: r.get(k, "") for k in STAT_COLUMNS + odds_cols}
            comp = comps.get(dbm.competition_id) if dbm and dbm.competition_id else None
            out.update({
                "date": r["_date"].isoformat(), "time": r.get("Time", ""), "division": div,
                "country": r["_country"], "league": r["_league"], "season": r["_season"],
                "home": r["_home"], "away": r["_away"], "home_db_team_id": h or "", "away_db_team_id": a or "",
                "db_match_id": dbm.id if dbm else "", "db_competition_name": comp[0] if comp else "",
                "db_competition_provider_id": comp[1] if comp else "",
                "db_score_agrees": "" if agrees is None else int(agrees),
                "FTHG": "" if r["_hg"] is None else r["_hg"], "FTAG": "" if r["_ag"] is None else r["_ag"],
                "FTR": r["_ftr"],
                "close_1x2_source": src_1x2 or "", "p_close_home": p1x2[0], "p_close_draw": p1x2[1],
                "p_close_away": p1x2[2], "close_1x2_overround": ovr,
                "close_ou25_source": src_ou or "", "p_close_over25": pou[0], "p_close_under25": pou[1],
                "close_ou25_overround": ovr_ou,
                "pre_1x2_source": src_pre or "", "p_pre_home": ppre[0], "p_pre_draw": ppre[1],
                "p_pre_away": ppre[2], "pre_1x2_overround": ovr_pre,
            })
            for k in ("p_close_home", "p_close_draw", "p_close_away", "close_1x2_overround", "p_close_over25",
                      "p_close_under25", "close_ou25_overround", "p_pre_home", "p_pre_draw", "p_pre_away",
                      "pre_1x2_overround"):
                if out[k] is None:
                    out[k] = ""
            w.writerow(out)

    coverage = {}
    for div, c in sorted(cov.items()):
        n = c["in_db_range"] or 0
        coverage[div] = {**div_meta[div], **dict(c),
                         "pct_linked_of_in_range": round(100.0 * c["linked_to_db_match"] / n, 1) if n else None}
    total = Counter()
    for c in cov.values():
        total.update(c)
    coverage["_total"] = {**dict(total), "pct_linked_of_in_range": round(
        100.0 * total["linked_to_db_match"] / total["in_db_range"], 1) if total["in_db_range"] else None,
        "teams_mapped": len(mapped_rows), "teams_unmapped": len(unmapped_rows),
        "db_range": [db_min.isoformat(), db_max.isoformat()], "odds_columns": odds_cols}
    OUT_COVERAGE.write_text(json.dumps(coverage, indent=2), encoding="utf-8")
    return coverage


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--refresh-current", action="store_true", help="re-fetch in-progress season files")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between requests")
    ap.add_argument("--history", action="store_true",
                    help="past seasons 2021/22-2024/25 (+ 2025/26 re-check) mapped to FotMob match ids -> "
                         "football_data_history.csv; extra options: see football_data_history.py --help")
    args, rest = ap.parse_known_args()
    if args.history:
        # Separate pipeline: never rewrites football_data_matches.csv / football_data_coverage.json.
        import football_data_history

        extra = (["--skip-download"] if args.skip_download else []) + ["--delay", str(max(1.0, args.delay))]
        sys.exit(football_data_history.main(rest + extra))
    if rest:
        ap.error(f"unrecognized arguments: {' '.join(rest)}")
    if not args.skip_download:
        download_all(args.refresh_current, args.delay)
    cov = build()
    print(f"{'div':5} {'country':4} {'matches':>7} {'inRange':>7} {'linked':>6} {'pct':>6} {'scoreOK':>7} {'close1x2':>8} {'closeOU':>7}")
    for div, c in cov.items():
        if div == "_total":
            continue
        print(f"{div:5} {c['country']:4} {c['matches']:7} {c.get('in_db_range', 0):7} {c.get('linked_to_db_match', 0):6} "
              f"{str(c['pct_linked_of_in_range']):>6} {c.get('score_agrees', 0):7} {c.get('has_close_1x2', 0):8} {c.get('has_close_ou25', 0):7}")
    t = cov["_total"]
    print(f"TOTAL matches={t['matches']} in_range={t['in_db_range']} linked={t['linked_to_db_match']} "
          f"({t['pct_linked_of_in_range']}%) teams mapped={t['teams_mapped']} unmapped={t['teams_unmapped']}")


if __name__ == "__main__":
    main()
