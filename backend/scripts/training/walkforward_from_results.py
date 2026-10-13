"""Walk-forward rating lambdas from the multi-season results table (stage B, step 2).

Same method and output columns as scripts/training/walkforward_dataset.py, but the matches
come from data/history/all_results.db (table ``results``: FotMob history 2021-07 .. 2025-06
UNION the production DB from 2025-07, keyed by FotMob ids; see data/history/README_history.md)
instead of the production DB. For every weekly cutoff c the production rating code
(app/prediction/team_ratings.py: GlobalPoissonRatings with its default hyper-parameters,
domestic_groups keyed by competition id, XG_GOAL_WEIGHT goal/xG blend, DEFAULT_LOOKBACK_DAYS)
is fitted on matches with kickoff in [c - lookback, c) and predicts every match in
[c, c + step). Each row is a genuine pre-match prediction (no look-ahead).

Id space: the results table has no DB uuids, so ``match_id``, ``competition_id``,
``home_team_id`` and ``away_team_id`` hold FotMob ids (``competition_id`` =
``competition_provider_id``). Everything else has the walkforward_dataset.py meaning.

Data rules (documented in docs/training/player-impact-pipeline.md, stage B):
  * ``awarded = 1`` rows (forfeit scores) are dropped unless --keep-awarded; ``awarded`` NULL
    (unknown, most production rows) is kept, as the README of the table prescribes.
  * team 959006 (Reggiana's first 5 production matches of 2025/26) is mapped to 6500, the id
    FotMob uses everywhere else (README_history.md, production_vs_fixture_teams); --no-aliases
    turns this off.
  * xG: the table carries production xG only (NULL for history). --xg-details adds team xG
    from details JSONL files (fotmob_match_details_history.jsonl) for rows whose xG is NULL,
    which is how the production DB got its xG (backfill_match_xg.py from the details file).
    Only a match whose two xG values are both present is used; nothing is imputed.
  * --source production / history restricts the rows (production = the reproduction check
    against walkforward_lambdas_xg.csv, which was fitted on the production DB).
  * --exclude-conflicts production_vs_fixture_status drops the 19 production rows that FotMob
    now shows as cancelled (table ``conflicts``; README_history.md: Rimini's annulled Serie C
    matches, the Middlesbrough - Southampton play-off, two cup ties). Abandoned / cancelled
    history matches are not in ``results`` at all (no score).

Usage (from backend/):
  venv/Scripts/python.exe scripts/training/walkforward_from_results.py \
      --start 2022-08-01 --end 2025-06-30 \
      --xg-details data/training/fotmob_match_details_history.jsonl \
      --out data/training/walkforward_lambdas_results_2022_2025.csv
  # reproduction check against the DB-based file on the overlapping period
  venv/Scripts/python.exe scripts/training/walkforward_from_results.py --compare \
      --compare-cutoffs 2026-08-10,2026-09-07,2026-10-05 \
      --out data/training/walkforward_from_results_check.json
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sqlite3
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

from app.prediction.team_ratings import (  # noqa: E402
    DEFAULT_LOOKBACK_DAYS,
    XG_GOAL_WEIGHT,
    GlobalPoissonRatings,
    domestic_groups,
)

DATA = BACKEND_DIR / "data"
DEFAULT_RESULTS = DATA / "history" / "all_results.db"
EURO_PROVIDER_IDS = {"42", "73", "10216"}          # as walkforward_dataset.py
TEAM_ID_ALIASES = {"959006": "6500"}               # README_history.md: Reggiana split id
HEADER = [
    "match_id", "kickoff", "cutoff", "competition_id", "competition_provider_id", "competition_name",
    "is_euro", "home_team_id", "away_team_id", "home_matches", "away_matches",
    "lambda_home", "lambda_away", "home_score", "away_score",
]


def parse_utc(s: str) -> datetime:
    """ISO string (with or without 'Z' / offset / fraction) -> naive UTC datetime."""
    s = s.strip().replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def read_details_xg(paths: Iterable[Path]) -> dict[str, tuple[float, float]]:
    """match id -> (home_xg, away_xg) from details JSONL files (both values present only).

    A partial last line (file still being written) or an unparsable line is skipped.
    """
    out: dict[str, tuple[float, float]] = {}
    for path in paths:
        with open(path, "rb") as f:
            for raw in f:
                try:
                    r = json.loads(raw)
                    mid = str(r["match_provider_id"])
                except (ValueError, KeyError, TypeError):
                    continue
                hx, ax = r.get("home_xg"), r.get("away_xg")
                if hx is None or ax is None or mid in out:
                    continue
                out[mid] = (float(hx), float(ax))
    return out


def load_results(path: Path, source: str = "all", keep_awarded: bool = False, aliases: bool = True,
                 extra_xg: Optional[dict] = None,
                 exclude_conflict_kinds: Iterable[str] = ()) -> tuple[list[dict], dict]:
    """Rows of ``results`` as walkforward match dicts (sorted by kickoff, then id).

    ``exclude_conflict_kinds``: match ids listed in table ``conflicts`` under these kinds are
    dropped (e.g. ``production_vs_fixture_status``: production FINISHED, FotMob CANCELLED).
    """
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        q = ("select match_provider_id, competition_provider_id, coalesce(competition_name, ''), scheduled_at, "
             "home_team_provider_id, away_team_provider_id, home_score, away_score, home_xg, away_xg, awarded, "
             "source from results")
        rows = con.execute(q).fetchall()
        kinds = [k for k in exclude_conflict_kinds if k]
        excluded = set()
        if kinds:
            excluded = {r[0] for r in con.execute(
                f"select match_provider_id from conflicts where kind in ({','.join('?' * len(kinds))}) "
                "and match_provider_id is not null", kinds)}
    finally:
        con.close()
    stats = {"rows_in_table": len(rows), "dropped_awarded": 0, "dropped_source": 0, "aliased_team_ids": 0,
             "xg_from_table": 0, "xg_from_details": 0, "dropped_conflicts": 0,
             "excluded_conflict_kinds": list(kinds)}
    extra_xg = extra_xg or {}
    out = []
    for (mid, cpid, cname, at, h, a, hs, as_, hxg, axg, awarded, src) in rows:
        if source != "all" and src != source:
            stats["dropped_source"] += 1
            continue
        if mid in excluded:
            stats["dropped_conflicts"] += 1
            continue
        if awarded == 1 and not keep_awarded:
            stats["dropped_awarded"] += 1
            continue
        h, a = str(h), str(a)
        if aliases:
            if h in TEAM_ID_ALIASES or a in TEAM_ID_ALIASES:
                stats["aliased_team_ids"] += 1
            h, a = TEAM_ID_ALIASES.get(h, h), TEAM_ID_ALIASES.get(a, a)
        if hxg is not None and axg is not None:
            stats["xg_from_table"] += 1
        else:
            hxg = axg = None
            ex = extra_xg.get(str(mid))
            if ex is not None:
                hxg, axg = ex
                stats["xg_from_details"] += 1
        cp = "" if cpid is None else str(cpid)
        out.append({"id": str(mid), "home": h, "away": a, "hs": int(hs), "as": int(as_), "at": parse_utc(at),
                    "comp_id": cp, "comp_name": cname, "comp_pid": cp, "hxg": hxg, "axg": axg})
    out.sort(key=lambda d: (d["at"], d["id"]))
    stats["rows_used"] = len(out)
    return out, stats


def fit_and_predict(data: list[dict], cutoff: datetime, step_days: int,
                    lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> list[list]:
    """Production rating fit on [cutoff - lookback, cutoff) and predictions for [cutoff, cutoff + step)."""
    window_end = cutoff + timedelta(days=step_days)
    train = [d for d in data if cutoff - timedelta(days=lookback_days) <= d["at"] < cutoff]
    test = [d for d in data if cutoff <= d["at"] < window_end]
    if not train or not test:
        return []
    groups = domestic_groups(
        [d["home"] for d in train], [d["away"] for d in train],
        [d["comp_name"] for d in train], [d["comp_id"] for d in train],
    )
    w = XG_GOAL_WEIGHT

    def target(goals, xg):
        return goals if xg is None or w >= 1.0 else w * goals + (1 - w) * xg

    ratings = GlobalPoissonRatings().fit(
        [d["home"] for d in train], [d["away"] for d in train],
        [target(d["hs"], d["hxg"]) for d in train], [target(d["as"], d["axg"]) for d in train],
        [(cutoff - d["at"]).total_seconds() / 86400 for d in train],
        team_groups=groups,
    )
    out = []
    for d in test:
        lam = ratings.predict(d["home"], d["away"])
        if lam is None:
            continue
        out.append([
            d["id"], d["at"].isoformat(), cutoff.date().isoformat(), d["comp_id"], d["comp_pid"], d["comp_name"],
            int(d["comp_pid"] in EURO_PROVIDER_IDS), d["home"], d["away"], lam.home_matches, lam.away_matches,
            f"{lam.home:.5f}", f"{lam.away:.5f}", d["hs"], d["as"],
        ])
    return out


# ---------------------------------------------------------------- process pool plumbing
_WORKER_DATA: list[dict] = []


def _init_worker(data):
    global _WORKER_DATA
    _WORKER_DATA = data


def _work(args):
    cutoff_iso, step_days = args
    t0 = time.time()
    rows = fit_and_predict(_WORKER_DATA, datetime.fromisoformat(cutoff_iso), step_days)
    return cutoff_iso, rows, time.time() - t0


def cutoff_list(start: str, end: str, step_days: int) -> list[datetime]:
    c, e, out = datetime.fromisoformat(start), datetime.fromisoformat(end), []
    while c < e:
        out.append(c)
        c += timedelta(days=step_days)
    return out


def run(data: list[dict], cutoffs: list[datetime], step_days: int, workers: int):
    """Yield (cutoff, rows, seconds) in cutoff order (deterministic regardless of workers)."""
    if workers <= 1:
        for c in cutoffs:
            t0 = time.time()
            yield c.isoformat(), fit_and_predict(data, c, step_days), time.time() - t0
        return
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker, initargs=(data,)) as ex:
        yield from ex.map(_work, [(c.isoformat(), step_days) for c in cutoffs])


def write_atomic_csv(path: Path, rows_iter, header=HEADER) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    n = 0
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for rows in rows_iter:
            w.writerows(rows)
            n += len(rows)
            f.flush()
    os.replace(tmp, path)
    return n


# ---------------------------------------------------------------- reproduction check
def compare(args) -> dict:
    """Fit on the results table for a few cutoffs and compare with the DB-based lambdas file."""
    db = Path(args.db)
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        id_map = {r[0]: str(r[1]) for r in con.execute("select id, provider_id from matches")}
    finally:
        con.close()
    ref: dict[str, dict[str, tuple[float, float]]] = {}
    with open(args.compare_with, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pid = id_map.get(r["match_id"])
            if pid:
                ref.setdefault(r["cutoff"], {})[pid] = (float(r["lambda_home"]), float(r["lambda_away"]))
    cutoffs = [datetime.fromisoformat(c) for c in args.compare_cutoffs.split(",")]
    report = {"compare_with": str(args.compare_with), "cutoffs": args.compare_cutoffs, "variants": {}}
    for variant, source, keep_awarded, aliases in (("production_rows_as_db", "production", True, False),
                                                   ("all_rows_default_rules", "all", False, True)):
        data, stats = load_results(Path(args.results), source=source, keep_awarded=keep_awarded, aliases=aliases)
        per = []
        allh, alla = [], []
        for c in cutoffs:
            rows = fit_and_predict(data, c, args.step_days)
            refc = ref.get(c.date().isoformat(), {})
            dl = []
            for r in rows:
                if r[0] in refc:
                    lh, la = float(r[11]), float(r[12])
                    rh, ra = refc[r[0]]
                    dl.append((math.log(lh / rh), math.log(la / ra)))
            only_ref = len(set(refc) - {r[0] for r in rows})
            only_new = len({r[0] for r in rows} - set(refc))
            if dl:
                dh = [abs(x[0]) for x in dl]
                da = [abs(x[1]) for x in dl]
                allh += dh
                alla += da
                both = sorted(dh + da)
                per.append({"cutoff": c.date().isoformat(), "matched": len(dl), "only_in_reference": only_ref,
                            "only_in_new": only_new,
                            "mean_abs_dlog_lambda": round(sum(both) / len(both), 5),
                            "p95_abs_dlog_lambda": round(both[int(0.95 * (len(both) - 1))], 5),
                            "max_abs_dlog_lambda": round(both[-1], 5),
                            "share_within_1pct": round(sum(1 for x in both if x < 0.01) / len(both), 4)})
            else:
                per.append({"cutoff": c.date().isoformat(), "matched": 0, "only_in_reference": only_ref,
                            "only_in_new": only_new})
            print(variant, per[-1], flush=True)
        both = sorted(allh + alla)
        report["variants"][variant] = {
            "load_stats": stats, "per_cutoff": per,
            "overall": ({"n_lambdas": len(both), "mean_abs_dlog_lambda": round(sum(both) / len(both), 5),
                         "share_within_1pct": round(sum(1 for x in both if x < 0.01) / len(both), 4),
                         "share_within_5pct": round(sum(1 for x in both if x < 0.05) / len(both), 4)}
                        if both else None),
        }
    # Same comparison against a fresh fit of walkforward_dataset.py's loader on the CURRENT production
    # DB (read only): separates "same method" from "the DB changed since the reference file was built".
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import walkforward_dataset as WD
    db_data = WD.load_matches(db)
    for d in db_data:
        d["id"] = id_map.get(d["id"], d["id"])          # FotMob ids, so rows can be matched
    rs_data, _ = load_results(Path(args.results), source="production", keep_awarded=True, aliases=False)
    per, allv = [], []
    for c in cutoffs:
        new = {r[0]: (float(r[11]), float(r[12])) for r in fit_and_predict(rs_data, c, args.step_days)}
        fresh = {r[0]: (float(r[11]), float(r[12])) for r in fit_and_predict(db_data, c, args.step_days)}
        n_train_db = sum(1 for d in db_data if c - timedelta(days=DEFAULT_LOOKBACK_DAYS) <= d["at"] < c)
        n_train_rs = sum(1 for d in rs_data if c - timedelta(days=DEFAULT_LOOKBACK_DAYS) <= d["at"] < c)
        dl = sorted(abs(math.log(new[k][i] / fresh[k][i])) for k in set(new) & set(fresh) for i in (0, 1))
        allv += dl
        per.append({"cutoff": c.date().isoformat(), "train_matches_db": n_train_db, "train_matches_results": n_train_rs,
                    "matched": len(dl) // 2, "only_in_db_fit": len(set(fresh) - set(new)),
                    "only_in_results_fit": len(set(new) - set(fresh)),
                    "mean_abs_dlog_lambda": round(sum(dl) / len(dl), 6) if dl else None,
                    "max_abs_dlog_lambda": round(dl[-1], 6) if dl else None,
                    "share_within_0_1pct": round(sum(1 for x in dl if x < 0.001) / len(dl), 4) if dl else None})
        print("fresh_db_fit", per[-1], flush=True)
    report["fresh_db_fit_same_cutoffs"] = {
        "what": "walkforward_dataset.load_matches(production DB, read only) + the same fit, vs the results-table "
                "production rows (keep awarded, no aliases)",
        "per_cutoff": per,
        "mean_abs_dlog_lambda": round(sum(allv) / len(allv), 6) if allv else None}
    return report


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="walk-forward rating lambdas from all_results.db")
    ap.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    ap.add_argument("--start", default="2022-08-01")
    ap.add_argument("--end", default="2025-06-30", help="cutoffs < end (as walkforward_dataset.py)")
    ap.add_argument("--step-days", type=int, default=7)
    ap.add_argument("--source", choices=("all", "history", "production"), default="all")
    ap.add_argument("--keep-awarded", action="store_true")
    ap.add_argument("--no-aliases", action="store_true")
    ap.add_argument("--xg-details", action="append", type=Path, default=[],
                    help="details JSONL(s) whose team xG fills results rows without xG")
    ap.add_argument("--exclude-conflicts", default="",
                    help="comma-separated conflicts.kind values whose match ids are dropped "
                         "(production_vs_fixture_status = the 19 production matches FotMob cancelled)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", type=Path, default=DATA / "training" / "walkforward_lambdas_results_2022_2025.csv")
    ap.add_argument("--compare", action="store_true", help="reproduction check instead of a run")
    ap.add_argument("--compare-with", type=Path, default=DATA / "training" / "walkforward_lambdas_xg.csv")
    ap.add_argument("--compare-cutoffs", default="2026-08-10,2026-09-07,2026-10-05")
    ap.add_argument("--db", type=Path, default=BACKEND_DIR / "football_intelligence.db")
    args = ap.parse_args(argv)
    t0 = time.time()

    if args.compare:
        rep = compare(args)
        rep["seconds"] = round(time.time() - t0, 1)
        tmp = args.out.with_name(args.out.name + f".tmp{os.getpid()}")
        tmp.write_text(json.dumps(rep, indent=1), encoding="utf-8")
        os.replace(tmp, args.out)
        print(f"-> {args.out}")
        return 0

    extra = read_details_xg(args.xg_details) if args.xg_details else {}
    data, stats = load_results(args.results, args.source, args.keep_awarded, not args.no_aliases, extra,
                               exclude_conflict_kinds=args.exclude_conflicts.split(","))
    cutoffs = cutoff_list(args.start, args.end, args.step_days)
    print(f"{len(data)} matches loaded ({json.dumps(stats)}); {len(cutoffs)} cutoffs "
          f"{cutoffs[0].date()}..{cutoffs[-1].date()}; workers={args.workers}", flush=True)

    per_cut = []

    def rows_iter():
        for c_iso, rows, secs in run(data, cutoffs, args.step_days, args.workers):
            per_cut.append({"cutoff": c_iso[:10], "predicted": len(rows), "seconds": round(secs, 1)})
            print(f"{c_iso[:10]}: predicted={len(rows)} ({secs:.1f}s)", flush=True)
            yield rows

    n = write_atomic_csv(args.out, rows_iter())
    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "results": str(args.results), "source": args.source, "keep_awarded": args.keep_awarded,
        "team_id_aliases": None if args.no_aliases else TEAM_ID_ALIASES,
        "xg_details": [str(p) for p in args.xg_details], "xg_details_matches_read": len(extra),
        "load_stats": stats, "start": args.start, "end": args.end, "step_days": args.step_days,
        "rating_code": "app.prediction.team_ratings.GlobalPoissonRatings (defaults), domestic_groups, "
                       f"XG_GOAL_WEIGHT={XG_GOAL_WEIGHT}, lookback {DEFAULT_LOOKBACK_DAYS} d",
        "rows": n, "per_cutoff": per_cut, "seconds": round(time.time() - t0, 1),
    }
    meta_path = args.out.with_suffix(".meta.json")
    tmp = meta_path.with_name(meta_path.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    os.replace(tmp, meta_path)
    print(f"DONE rows={n} -> {args.out} ({meta['seconds']} s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
