"""Build backend/data/history/all_results.db: one FotMob-keyed results table for training.

TRAINING DATA BUILDER (no network).

    results = history      (data/history/history_results.db, kickoff < 2025-07-01T00:00:00Z,
                            status FINISHED or AWARDED with a score; collect_fotmob_history_results.py)
              UNION
              production   (backend/football_intelligence.db opened READ-ONLY, status FINISHED,
                            scheduled_at >= 2025-07-01)

Everything is keyed by FotMob ids: production uuids are mapped through matches.provider_id,
teams.provider_id and competitions.provider_id. The build is idempotent (temp file + os.replace), so it
can be re-run whenever the production DB grows.

Columns of ``results``
  match_provider_id, competition_provider_id, competition_name, season (NULL if unknown), scheduled_at
  (ISO UTC), home_team_provider_id, away_team_provider_id, home_score, away_score, home_xg, away_xg
  (production values; NULL for history rows), awarded (1/0, NULL when no FotMob source says), source
  ('history' | 'production'), competition_in_history_scope (1 when the competition is one of the
  history selection, so a training set can keep one scope across the boundary).

Boundary checks (table ``conflicts``)
  same_id_both_sides            one FotMob match id in history and production (kept: production row)
  same_fixture_different_ids    same home/away teams within 48 h across the boundary, different ids
  production_vs_fixture_*       a production row disagrees with FotMob's own league fixtures of the
                                boundary seasons (history_results.db.matches_after_cutoff): teams,
                                score, kickoff (> 1 h) or status (fixture not finished / awarded)
  invalid_team_id               production row whose team provider id is not a positive FotMob id, or whose
                                team uuid has no teams row (skipped)

Honesty (AGENTS.md 8-14): no value is invented. xG exists only where the production DB has it;
``awarded`` of a production row comes from FotMob's league fixtures (boundary seasons) or from the
match-details dataset, else NULL; ``season`` of a production row comes from the league fixtures, else NULL.

Usage (from backend/):
  venv/Scripts/python.exe scripts/data_collection/build_all_results.py
  venv/Scripts/python.exe scripts/data_collection/build_all_results.py --report-only
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_PROD_DB = BACKEND_DIR / "football_intelligence.db"
DEFAULT_HISTORY_DB = BACKEND_DIR / "data" / "history" / "history_results.db"
DEFAULT_DETAILS = BACKEND_DIR / "data" / "training" / "fotmob_match_details.jsonl"
DEFAULT_OUT = BACKEND_DIR / "data" / "history" / "all_results.db"
CUTOFF = "2025-07-01T00:00:00Z"
PROD_CUTOFF = "2025-07-01 00:00:00"
TARGET13 = [47, 87, 55, 54, 53, 57, 61, 40, 71, 122, 42, 73, 10216]

SCHEMA = """
CREATE TABLE results (
    match_provider_id INTEGER PRIMARY KEY,
    competition_provider_id INTEGER,
    competition_name TEXT,
    season TEXT,
    scheduled_at TEXT NOT NULL,
    home_team_provider_id INTEGER NOT NULL,
    away_team_provider_id INTEGER NOT NULL,
    home_score INTEGER NOT NULL,
    away_score INTEGER NOT NULL,
    home_xg REAL,
    away_xg REAL,
    awarded INTEGER,
    source TEXT NOT NULL,
    competition_in_history_scope INTEGER NOT NULL
);
CREATE INDEX ix_results_kickoff ON results (scheduled_at);
CREATE INDEX ix_results_home ON results (home_team_provider_id);
CREATE INDEX ix_results_away ON results (away_team_provider_id);
CREATE INDEX ix_results_comp ON results (competition_provider_id, season);
CREATE TABLE conflicts (
    kind TEXT NOT NULL,
    match_provider_id INTEGER,
    other_match_provider_id INTEGER,
    detail TEXT
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""

COLS = [
    "match_provider_id", "competition_provider_id", "competition_name", "season", "scheduled_at",
    "home_team_provider_id", "away_team_provider_id", "home_score", "away_score", "home_xg", "away_xg",
    "awarded", "source", "competition_in_history_scope",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _int(value: Any) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def prod_iso(value: str) -> str:
    """Production 'YYYY-MM-DD HH:MM:SS.ffffff' (naive UTC) -> 'YYYY-MM-DDTHH:MM:SSZ'."""
    dt = datetime.fromisoformat(str(value))
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


def _ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=30)


def load_history(history_db: Path) -> dict[str, Any]:
    conn = _ro(history_db)
    try:
        comp_names = {r[0]: r[1] for r in conn.execute("SELECT provider_id, name FROM competitions")}
        rows = conn.execute(
            "SELECT provider_id, competition_provider_id, season, scheduled_at, home_team_provider_id,"
            " away_team_provider_id, home_score, away_score, awarded, status FROM matches"
        ).fetchall()
        after = {r[0]: r for r in conn.execute(
            "SELECT provider_id, competition_provider_id, season, scheduled_at, home_team_provider_id,"
            " away_team_provider_id, home_score, away_score, awarded, status FROM matches_after_cutoff"
        )}
        dup = conn.execute("SELECT COUNT(*), SUM(same_teams), SUM(same_score) FROM duplicate_match_ids").fetchone()
    finally:
        conn.close()
    return {"comp_names": comp_names, "rows": rows, "after": after, "duplicates": dup}


def load_details_awarded(path: Path) -> dict[int, int]:
    out: dict[int, int] = {}
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            mid = _int(r.get("match_provider_id"))
            if mid is not None and isinstance(r.get("awarded"), bool):
                out[mid] = int(r["awarded"])
    return out


def load_production(prod_db: Path) -> tuple[list[tuple], dict[int, str], dict[int, str]]:
    conn = _ro(prod_db)
    try:
        rows = conn.execute(
            # LEFT JOIN: a match whose team uuid has no teams row must surface as invalid_team_id, not vanish
            """SELECT m.provider_id, co.provider_id, co.name, m.scheduled_at, ht.provider_id, at.provider_id,
                      m.home_score, m.away_score, m.home_xg, m.away_xg
               FROM matches m
               LEFT JOIN teams ht ON ht.id = m.home_team_id
               LEFT JOIN teams at ON at.id = m.away_team_id
               LEFT JOIN competitions co ON co.id = m.competition_id
               WHERE m.status = 'FINISHED' AND m.scheduled_at >= ?""",
            (PROD_CUTOFF,),
        ).fetchall()
        comp_names = {_int(r[0]): r[1] for r in conn.execute("SELECT provider_id, name FROM competitions")}
        team_names = {_int(r[0]): r[1] for r in conn.execute("SELECT provider_id, name FROM teams")}
    finally:
        conn.close()
    return rows, comp_names, team_names


def build(history_db: Path, prod_db: Path, details: Path, out_db: Path) -> dict[str, Any]:
    hist = load_history(history_db)
    prod_rows, prod_comp_names, _team_names = load_production(prod_db)
    details_awarded = load_details_awarded(details)
    scope = set(hist["comp_names"])

    def comp_name(cid: int | None) -> str | None:
        return hist["comp_names"].get(cid) or prod_comp_names.get(cid)

    results: dict[int, dict[str, Any]] = {}
    conflicts: list[tuple[str, int | None, int | None, str]] = []
    stats: Counter = Counter()

    # ---- history side
    for (mid, comp, season, kickoff, h, a, hs, as_, aw, status) in hist["rows"]:
        stats[f"history_status:{status}"] += 1
        if status not in ("FINISHED", "AWARDED") or hs is None or as_ is None:
            stats["history_skipped_no_result"] += 1
            continue
        if kickoff >= CUTOFF:  # cannot happen (history_results.db is cut), guard anyway
            stats["history_skipped_after_cutoff"] += 1
            continue
        results[mid] = {
            "match_provider_id": mid, "competition_provider_id": comp, "competition_name": comp_name(comp),
            "season": season, "scheduled_at": kickoff, "home_team_provider_id": h, "away_team_provider_id": a,
            "home_score": hs, "away_score": as_, "home_xg": None, "away_xg": None,
            "awarded": aw, "source": "history", "competition_in_history_scope": 1,
        }
    stats["history_rows"] = len(results)

    # index history fixtures by team pair for the cross-boundary duplicate check
    by_pair: dict[tuple[int, int], list[tuple[datetime, int]]] = defaultdict(list)
    for r in results.values():
        by_pair[(r["home_team_provider_id"], r["away_team_provider_id"])].append((_parse_iso(r["scheduled_at"]), r["match_provider_id"]))

    # ---- production side
    after = hist["after"]
    for (pid, comp, cname, sched, ht, at, hs, as_, hxg, axg) in prod_rows:
        mid, cid, h, a = _int(pid), _int(comp), _int(ht), _int(at)
        if mid is None:
            stats["production_skipped_bad_match_id"] += 1
            continue
        if h is None or a is None or h <= 0 or a <= 0:
            conflicts.append(("invalid_team_id", mid, None, json.dumps({"home": ht, "away": at, "competition": comp})))
            stats["production_skipped_invalid_team_id"] += 1
            continue
        if hs is None or as_ is None:
            stats["production_skipped_no_score"] += 1
            continue
        kickoff = prod_iso(sched)
        fx = after.get(mid)
        awarded = None
        season = None
        if fx is not None:
            stats["production_with_fixture"] += 1
            season = fx[2]
            awarded = fx[8]
            if (fx[4], fx[5]) != (h, a):
                conflicts.append(("production_vs_fixture_teams", mid, None,
                                  json.dumps({"production": [h, a], "fixture": [fx[4], fx[5]]})))
            if fx[9] not in ("FINISHED", "AWARDED"):
                conflicts.append(("production_vs_fixture_status", mid, None,
                                  json.dumps({"production": "FINISHED", "fixture": fx[9], "score": [hs, as_]})))
            elif (fx[6], fx[7]) != (hs, as_):
                conflicts.append(("production_vs_fixture_score", mid, None,
                                  json.dumps({"production": [hs, as_], "fixture": [fx[6], fx[7]]})))
            if abs((_parse_iso(fx[3]) - _parse_iso(kickoff)).total_seconds()) > 3600:
                conflicts.append(("production_vs_fixture_kickoff", mid, None,
                                  json.dumps({"production": kickoff, "fixture": fx[3]})))
        if awarded is None and mid in details_awarded:
            awarded = details_awarded[mid]
            stats["production_awarded_from_details"] += 1
        if awarded is None:
            stats["production_awarded_unknown"] += 1
        row = {
            "match_provider_id": mid, "competition_provider_id": cid, "competition_name": comp_name(cid) or cname,
            "season": season, "scheduled_at": kickoff, "home_team_provider_id": h, "away_team_provider_id": a,
            "home_score": hs, "away_score": as_, "home_xg": hxg, "away_xg": axg, "awarded": awarded,
            "source": "production", "competition_in_history_scope": int(cid in scope),
        }
        prev = results.get(mid)
        if prev is not None:
            if prev["source"] == "history":
                conflicts.append(("same_id_both_sides", mid, None, json.dumps({
                    "history": [prev["scheduled_at"], prev["home_score"], prev["away_score"]],
                    "production": [kickoff, hs, as_]})))
                stats["same_id_both_sides"] += 1
            else:
                stats["production_duplicate_id"] += 1
                continue
        # cross-boundary same fixture with a different id (history side only lies before the cutoff)
        k = _parse_iso(kickoff)
        if k < _parse_iso(CUTOFF) + timedelta(days=3):
            for (hk, hmid) in by_pair.get((h, a), []):
                if hmid != mid and abs((hk - k).total_seconds()) <= 48 * 3600:
                    conflicts.append(("same_fixture_different_ids", mid, hmid,
                                      json.dumps({"production_kickoff": kickoff, "history_kickoff": hk.isoformat()})))
                    stats["same_fixture_different_ids"] += 1
        results[mid] = row
        stats["production_rows"] += 1

    # ---- write (atomic)
    out_db.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_db.with_name(out_db.name + ".tmp")
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(tmp)
    conn.executescript(SCHEMA)
    conn.executemany(f"INSERT INTO results ({','.join(COLS)}) VALUES ({','.join('?' * len(COLS))})",
                     [tuple(r[c] for c in COLS) for r in sorted(results.values(), key=lambda r: (r["scheduled_at"], r["match_provider_id"]))])
    conn.executemany("INSERT INTO conflicts VALUES (?,?,?,?)", conflicts)
    kinds = Counter(c[0] for c in conflicts)
    dup = hist["duplicates"]
    meta = {
        "built_at": _utc_now(),
        "cutoff": CUTOFF,
        "history_db": str(history_db),
        "production_db": str(prod_db),
        "n_results": str(len(results)),
        "n_history": str(sum(1 for r in results.values() if r["source"] == "history")),
        "n_production": str(sum(1 for r in results.values() if r["source"] == "production")),
        "conflicts": json.dumps(dict(kinds)),
        "history_duplicate_ids": json.dumps({"n": dup[0], "same_teams": dup[1], "same_score": dup[2]}),
        "stats": json.dumps(dict(stats)),
    }
    conn.executemany("INSERT INTO meta VALUES (?,?)", list(meta.items()))
    conn.commit()
    conn.close()
    os.replace(tmp, out_db)
    return {"stats": dict(stats), "conflicts": dict(kinds), "n_results": len(results)}


def report(out_db: Path, prod_db: Path) -> str:
    """Counts by source / season-year, conflicts, and history coverage of 2025/26 TARGET13 teams."""
    conn = _ro(out_db)
    lines: list[str] = []
    try:
        lines.append("source counts: " + json.dumps(dict(conn.execute("SELECT source, COUNT(*) FROM results GROUP BY source").fetchall())))
        n, nd = conn.execute("SELECT COUNT(*), COUNT(DISTINCT match_provider_id) FROM results").fetchone()
        lines.append(f"rows={n} distinct match ids={nd} duplicate ids={n - nd}")
        lines.append("by kickoff year x source:")
        for y, src, c in conn.execute("SELECT substr(scheduled_at,1,4), source, COUNT(*) FROM results GROUP BY 1,2 ORDER BY 1,2"):
            lines.append(f"  {y} {src}: {c}")
        lines.append("awarded: " + json.dumps(conn.execute(
            "SELECT source, SUM(awarded = 1), SUM(awarded = 0), SUM(awarded IS NULL) FROM results GROUP BY source").fetchall()))
        lines.append("season known: " + json.dumps(conn.execute(
            "SELECT source, SUM(season IS NOT NULL), COUNT(*) FROM results GROUP BY source").fetchall()))
        lines.append("xg present: " + json.dumps(conn.execute(
            "SELECT source, SUM(home_xg IS NOT NULL AND away_xg IS NOT NULL), COUNT(*) FROM results GROUP BY source").fetchall()))
        lines.append("conflicts: " + json.dumps(dict(conn.execute("SELECT kind, COUNT(*) FROM conflicts GROUP BY kind").fetchall())))

        # TARGET13 teams of 2025/26 (production FINISHED TARGET13 matches 2025-07-01 .. 2026-06-30)
        teams: dict[int, set[int]] = defaultdict(set)
        for comp, h, a in conn.execute(
            f"SELECT competition_provider_id, home_team_provider_id, away_team_provider_id FROM results WHERE source = 'production'"
            f" AND scheduled_at >= '2025-07-01' AND scheduled_at < '2026-07-01' AND competition_provider_id IN ({','.join(map(str, TARGET13))})"
        ):
            teams[comp].update((h, a))
        hist_count: Counter = Counter()
        hist_last_year: Counter = Counter()
        for h, a, k in conn.execute("SELECT home_team_provider_id, away_team_provider_id, scheduled_at FROM results WHERE source = 'history'"):
            for t in (h, a):
                hist_count[t] += 1
                if k >= "2024-07-01":
                    hist_last_year[t] += 1
    finally:
        conn.close()
    pc = _ro(prod_db)
    try:
        tnames = {_int(r[0]): r[1] for r in pc.execute("SELECT provider_id, name FROM teams")}
    finally:
        pc.close()
    all_teams = set().union(*teams.values()) if teams else set()
    lines.append("")
    lines.append("TARGET13 teams of 2025/26 (production FINISHED matches 2025-07-01..2026-06-30) with history (kickoff < 2025-07-01):")
    lines.append("| Competition | Teams | >= 1 history match | >= 20 history matches in 2024-07-01..2025-06-30 | Without history |")
    lines.append("|---|---|---|---|---|")
    for comp in TARGET13:
        ts = teams.get(comp, set())
        no_hist = sorted(t for t in ts if hist_count[t] == 0)
        lines.append(f"| {comp} | {len(ts)} | {sum(1 for t in ts if hist_count[t] > 0)} | "
                     f"{sum(1 for t in ts if hist_last_year[t] >= 20)} | "
                     f"{', '.join(f'{tnames.get(t)} ({t})' for t in no_hist) or '-'} |")
    lines.append(f"| all (distinct) | {len(all_teams)} | {sum(1 for t in all_teams if hist_count[t] > 0)} | "
                 f"{sum(1 for t in all_teams if hist_last_year[t] >= 20)} | "
                 f"{sum(1 for t in all_teams if hist_count[t] == 0)} teams |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--history", default=str(DEFAULT_HISTORY_DB))
    ap.add_argument("--db", default=str(DEFAULT_PROD_DB), help="production DB (opened read-only)")
    ap.add_argument("--details", default=str(DEFAULT_DETAILS), help="fotmob_match_details.jsonl (awarded flags)")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)
    if not args.report_only:
        res = build(Path(args.history), Path(args.db), Path(args.details), Path(args.out))
        print(f"[{_utc_now()}] built {args.out}: {res['n_results']} rows; conflicts {res['conflicts']}")
        print("stats:", json.dumps(res["stats"], indent=1))
    print(report(Path(args.out), Path(args.db)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
