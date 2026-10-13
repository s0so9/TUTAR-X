"""Match-level pre-kickoff feature set for the match model (stage B, step 1).

One row per match of the FotMob details files (TARGET13 + the Set B leagues that were
collected; see data/training/README_fotmob_details.md), built only from information
available before kick-off. Field definitions, coverage and gaps:
data/training/README_match_features.md; method: docs/training/player-impact-pipeline.md
(stage B).

Feature groups (a side's features are prefixed home_ / away_):
  base     walk-forward rating lambdas (lambdas CSV: walkforward_dataset.py or
           walkforward_from_results.py), then the production goal layer
           (app/prediction/goal_model.py, config/goal_model.json, read only)
  value    starters' market value of each side (line-up totalStarterMarketValue) and
           ln(V_home / V_away) - the production squad-value signal
  form_prod production lineup form (experiment_lineup_strength.py definition: starters' prior
           minutes-weighted FotMob rating vs the team's usual XI)
  xi       stage-A RAPM ratings (player_impact_asof.csv.gz, latest cutoff strictly before
           kick-off): XI offence/defence (sum over the 11 starters), the team's usual XI
           (mean of its last N line-ups before kick-off, valued at the same cutoff, scaled to
           11 players), and XI minus usual
  absent   players FotMob lists as unavailable in the match's line-up block (pre-match
           snapshot: none of the 17,978 listed players of the current file appeared in the
           match): counts by type and summed rating above the replacement level of the
           player's position (unweighted, and weighted by the player's minutes share)
  form     last-5 form: team xG for/against (details matches), points / goals (results)
  rest     days since the previous competitive match, matches in the previous 14 days,
           European match within 3 days before / after (the "after" flag uses the fixture
           schedule, known before kick-off)
  context  competition type (league / cup / european) and the competition's home advantage
           (shrunk log home/away goal ratio over the previous 365 days) minus the global one
Labels (never features): y_home_goals, y_away_goals, y_home_xg, y_away_xg.

No-look-ahead rules: every history-based value uses matches with kickoff strictly before this
kick-off (the match's own id and duplicate fixtures of the same pair within 1 day are
excluded); from the match itself only pre-match line-up data is read (starters, their usual
positions, starter market values, the unavailable list). tests/test_match_features_training.py
checks that adding post-kick-off data does not change any feature.

Missing information stays empty (null) in the CSV; nothing is imputed here.

``unavailable[*].expected_return`` is never read: in the history file it is a later state of the
injury record (look-ahead, README_fotmob_details.md, history gap 6). read_details() drops the key
when it loads a record, so no feature can depend on it (tests/test_match_features_training.py).

Multi-season run options (2026-10-13 full re-run):
  --slim             keep only the record / player keys this script reads (memory: the two details
                     files hold ~830k player rows)
  --lazy-ratings     stream the ratings file one cutoff at a time (rows must be grouped by cutoff
                     in ascending order, as player_impact.py writes them); records are processed in
                     kick-off order, so each cutoff block is read once
  --results-exclude-awarded / --results-exclude-conflicts KIND[,KIND]: drop awarded results and the
                     match ids of all_results.db ``conflicts`` (e.g. production_vs_fixture_status =
                     19 production matches FotMob cancelled) from the results used for last-5 points /
                     goals, rest days, congestion and home advantage

Usage (from backend/):
  venv/Scripts/python.exe scripts/training/build_match_features.py
  # multi-season re-run (after stage A was re-run on the history):
  venv/Scripts/python.exe scripts/training/build_match_features.py \
      --details data/training/fotmob_match_details.jsonl \
      --details data/training/fotmob_match_details_history.jsonl \
      --lambdas data/training/walkforward_lambdas_results_2022_2025.csv \
      --lambdas data/training/walkforward_lambdas_xg_2025h2.csv --lambdas data/training/walkforward_lambdas_xg.csv \
      --ratings data/training/player_impact_asof_all.csv.gz --meta data/training/player_impact_meta_all.json \
      --out data/training/match_features_all.csv.gz --report data/training/match_features_all_report.json
"""

from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import io
import json
import math
import os
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

BACKEND_DIR = Path(__file__).resolve().parents[2]
TRAINING_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TRAINING_DIR))

DATA = BACKEND_DIR / "data"
TRAIN_DATA = DATA / "training"
DEFAULT_DETAILS = [TRAIN_DATA / "fotmob_match_details.jsonl"]
DEFAULT_LAMBDAS = [TRAIN_DATA / "walkforward_lambdas_xg_2025h2.csv", TRAIN_DATA / "walkforward_lambdas_xg.csv",
                   TRAIN_DATA / "walkforward_lambdas_results_2025_07.csv"]
DEFAULT_RAW_DIR = DATA / "raw_cache" / "fotmob_match_details"
DEFAULT_RESULTS = DATA / "history" / "all_results.db"

EURO_MAIN = {"42", "73", "10216"}                                  # UCL, UEL, UECL (row competition type)
EURO_ALL = EURO_MAIN | {"10611", "10613", "10615"}                 # + their qualification competitions
CUP_MARKERS = ("Cup", "Pokal", "Coupe", "Copa", "Coppa", "Beker", "Taça", "Taca", "Kupa", "Pokalen",
               "Trophy", "Shield", "Supercup", "Super Cup", "Supercopa", "Supercoppa")
POSITION_ID = {0: "GK", 1: "DEF", 2: "MID", 3: "FWD"}
FRINGE_MINUTES = 450.0
SIDES = ("home", "away")

# defaults (documented in the README)
USUAL_N = 10
MIN_USUAL = 3
FORM_N = 5
FORM_MIN = 3
HADV_WINDOW_DAYS = 365
HADV_SHRINK_MATCHES = 100.0
CONGESTION_DAYS = 14
EURO_WINDOW_DAYS = 3
DUPLICATE_FIXTURE_DAYS = 1.0


# ============================================================================ small helpers
def parse_utc(s: str) -> datetime:
    """ISO string (with or without 'Z' / offset / fraction / space) -> naive UTC datetime."""
    s = str(s).strip().replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def is_friendly(name: Optional[str]) -> bool:
    return bool(name) and "Friendl" in name


def competition_type(pid: str, name: Optional[str]) -> str:
    if pid in EURO_ALL:
        return "european"
    if name and any(m in name for m in CUP_MARKERS):
        return "cup"
    return "league"


def mean(xs: list) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


# ============================================================================ inputs
RECORD_KEYS = ("match_provider_id", "scheduled_at", "competition_provider_id", "season", "source_league_id",
               "home_team_provider_id", "away_team_provider_id", "home_score", "away_score", "home_xg", "away_xg",
               "home_starters_market_value", "away_starters_market_value", "awarded", "players", "unavailable")
PLAYER_KEYS = ("player_id", "is_starter", "team_side", "usual_position_id", "rating", "minutes_played")


def slim_record(r: dict) -> dict:
    """Only the keys this script (and experiment_xi_impact.production_features) reads."""
    out = {k: r.get(k) for k in RECORD_KEYS if k in r}
    out["players"] = [{k: p.get(k) for k in PLAYER_KEYS} for p in r.get("players") or []]
    return out


def read_details(paths: Iterable[Path], slim: bool = False) -> tuple[list[dict], dict]:
    """Details records (first occurrence of a match id wins), awarded matches dropped, sorted by kickoff.

    Unparsable lines (e.g. the partial last line of a file that is still being written) are
    skipped and counted. ``unavailable[*].expected_return`` is removed from every record (not a
    match-time value in the history file; never a feature). ``slim`` keeps only the keys read here.
    """
    seen, out = set(), []
    stats = Counter()
    for path in paths:
        with open(path, "rb") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    mid = str(r["match_provider_id"])
                    r["_at"] = parse_utc(r["scheduled_at"])
                except (ValueError, KeyError, TypeError):
                    stats["unparsable_lines"] += 1
                    continue
                if mid in seen:
                    stats["duplicate_ids"] += 1
                    continue
                seen.add(mid)
                if r.get("awarded"):
                    stats["awarded_dropped"] += 1
                    continue
                for u in r.get("unavailable") or []:
                    if isinstance(u, dict) and u.pop("expected_return", None) is not None:
                        stats["expected_return_dropped"] += 1
                if slim:
                    at = r["_at"]
                    r = slim_record(r)
                    r["_at"] = at
                r["_file"] = Path(path).name
                out.append(r)
    out.sort(key=lambda r: (r["_at"], str(r["match_provider_id"])))
    stats["records"] = len(out)
    return out, dict(stats)


def unavailable_presence(raw_dir: Optional[Path], match_id: str) -> Optional[tuple[Optional[bool], Optional[bool]]]:
    """(home key present, away key present) of content.lineup.<side>Team.unavailable in the raw
    response; None when the raw file is missing or unreadable."""
    if raw_dir is None:
        return None
    p = raw_dir / f"{match_id}.json.gz"
    try:
        with gzip.open(p, "rb") as f:
            d = json.loads(f.read())
    except (OSError, EOFError, ValueError):
        return None
    lu = ((d.get("content") or {}).get("lineup")) or {}
    out = []
    for side in ("homeTeam", "awayTeam"):
        t = lu.get(side)
        out.append(None if not isinstance(t, dict) else ("unavailable" in t))
    return out[0], out[1]


def db_id_map(db_path: Optional[Path]) -> dict[str, str]:
    if db_path is None or not Path(db_path).exists():
        return {}
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        return {r[0]: str(r[1]) for r in con.execute("select id, provider_id from matches")}
    finally:
        con.close()


def read_lambdas(paths: Iterable[Path], id_map: dict[str, str]) -> dict[str, dict]:
    """FotMob match id -> {lh, la, cutoff, source}; first file wins. DB uuids are mapped through
    ``id_map``; files from walkforward_from_results.py already carry FotMob ids."""
    out: dict[str, dict] = {}
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                mid = r["match_id"]
                pid = id_map.get(mid) if "-" in mid else mid
                if not pid or pid in out:
                    continue
                out[pid] = {"lh": float(r["lambda_home"]), "la": float(r["lambda_away"]),
                            "cutoff": r["cutoff"], "source": Path(path).name}
    return out


def read_results(results_db: Optional[Path], prod_db: Optional[Path], exclude_awarded: bool = False,
                 exclude_conflict_kinds: Iterable[str] = ()) -> tuple[list[dict], str]:
    """All finished results (FotMob ids) for schedule/form/home-advantage features.

    Preferred: all_results.db (history + production). Fallback: the production DB (read only).
    ``exclude_awarded`` drops ``awarded = 1`` rows (forfeit scores; NULL = unknown is kept);
    ``exclude_conflict_kinds`` drops the match ids listed in table ``conflicts`` under those kinds.
    """
    if results_db is not None and Path(results_db).exists():
        con = sqlite3.connect(f"file:{Path(results_db).as_posix()}?mode=ro", uri=True)
        try:
            where = " where awarded is not 1" if exclude_awarded else ""
            rows = con.execute(
                "select match_provider_id, competition_provider_id, coalesce(competition_name, ''), scheduled_at, "
                "home_team_provider_id, away_team_provider_id, home_score, away_score from results" + where).fetchall()
            kinds = [k for k in exclude_conflict_kinds if k]
            if kinds:
                bad = {r[0] for r in con.execute(
                    f"select match_provider_id from conflicts where kind in ({','.join('?' * len(kinds))}) "
                    "and match_provider_id is not null", kinds)}
                rows = [r for r in rows if r[0] not in bad]
        finally:
            con.close()
        src = f"results:{Path(results_db).name}" + (" (awarded excluded)" if exclude_awarded else "") + (
            f" (conflicts excluded: {','.join(kinds)})" if kinds else "")
    elif prod_db is not None and Path(prod_db).exists():
        con = sqlite3.connect(f"file:{Path(prod_db).as_posix()}?mode=ro", uri=True)
        try:
            rows = con.execute(
                """select m.provider_id, c.provider_id, coalesce(c.name, ''), m.scheduled_at, th.provider_id,
                          ta.provider_id, m.home_score, m.away_score
                   from matches m left join competitions c on c.id = m.competition_id
                   join teams th on th.id = m.home_team_id join teams ta on ta.id = m.away_team_id
                   where m.status = 'FINISHED' and m.home_score is not null and m.away_score is not null"""
            ).fetchall()
        finally:
            con.close()
        src = f"production_db:{Path(prod_db).name}"
    else:
        return [], "none"
    out = []
    for mid, cp, cname, at, h, a, hs, as_ in rows:
        if h is None or a is None or hs is None or as_ is None:
            continue
        out.append({"id": str(mid), "comp": "" if cp is None else str(cp), "name": cname, "at": parse_utc(at),
                    "home": str(h), "away": str(a), "hs": int(hs), "as": int(as_)})
    out.sort(key=lambda r: (r["at"], r["id"]))
    return out, src


@dataclass
class Ratings:
    cutoffs: list[str] = field(default_factory=list)          # sorted ISO dates
    cutoff_dt: list[datetime] = field(default_factory=list)
    table: dict = field(default_factory=dict)                  # cutoff -> pid -> (off, def, minutes_share, pos)
    repl: dict = field(default_factory=dict)                   # cutoff -> pos -> (off, def)

    def cutoff_before(self, kick: datetime) -> Optional[str]:
        """Latest cutoff strictly before the kick-off (its ratings use matches before the cutoff)."""
        i = bisect.bisect_left(self.cutoff_dt, kick) - 1
        return self.cutoffs[i] if i >= 0 else None


def read_ratings(path: Optional[Path], meta_path: Optional[Path]) -> Ratings:
    rt = Ratings()
    if path is None or not Path(path).exists():
        return rt
    fringe: dict = defaultdict(lambda: defaultdict(list))
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            cut = row["cutoff"]
            pos = row["position"] or "UNK"
            off, dfn = float(row["offence"]), float(row["defence"])
            ms = float(row["minutes_share"]) if row.get("minutes_share") not in (None, "") else None
            rt.table.setdefault(cut, {})[row["player_id"]] = (off, dfn, ms, pos)
            if float(row["minutes"]) < FRINGE_MINUTES:
                fringe[cut][pos].append((off, dfn))
                fringe[cut]["*"].append((off, dfn))
    meta_repl = {}
    if meta_path is not None and Path(meta_path).exists():
        meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
        for e in meta.get("per_cutoff") or []:
            meta_repl[e["cutoff"]] = e.get("replacement_level") or {}
    for cut in rt.table:
        rt.repl[cut] = {}
        for pos in ("GK", "DEF", "MID", "FWD", "UNK"):
            m = meta_repl.get(cut, {}).get(pos)
            if m:   # the training script's own replacement level (stage A runtime convention)
                rt.repl[cut][pos] = (float(m["offence"]), float(m["defence"]))
                continue
            pool = fringe[cut].get(pos) if len(fringe[cut].get(pos, [])) >= 5 else fringe[cut].get("*")
            if pool:
                rt.repl[cut][pos] = (mean([p[0] for p in pool]), mean([p[1] for p in pool]))
    rt.cutoffs = sorted(rt.table)
    rt.cutoff_dt = [datetime.fromisoformat(c) for c in rt.cutoffs]
    return rt


class LazyRatings(Ratings):
    """Ratings read one cutoff block at a time (for files with millions of rows).

    The file must hold each cutoff's rows as one contiguous block, blocks in ascending cutoff
    order (player_impact.py writes it that way). ``table.get`` / ``repl.get`` of the current block
    are served from memory; a later cutoff advances the stream, an earlier one restarts it.
    Replacement levels follow read_ratings(): the meta file's level when present, else the
    fringe-player mean of the block.
    """

    def __init__(self, path: Path, meta_path: Optional[Path]):
        super().__init__()
        self.path = Path(path)
        self.meta_repl: dict = {}
        cutoffs = None
        if meta_path is not None and Path(meta_path).exists():
            meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
            per = meta.get("per_cutoff") or []
            for e in per:
                self.meta_repl[e["cutoff"]] = e.get("replacement_level") or {}
            cutoffs = sorted({e["cutoff"] for e in per}) or None
        if cutoffs is None:             # one pass over the cutoff column
            seen = set()
            with gzip.open(self.path, "rt", encoding="utf-8", newline="") as f:
                rd = csv.reader(f)
                next(rd)
                for row in rd:
                    seen.add(row[0])
            cutoffs = sorted(seen)
        self.cutoffs = cutoffs
        self.cutoff_set = set(cutoffs)
        self.cutoff_dt = [datetime.fromisoformat(c) for c in cutoffs]
        self._fh = None
        self._reader = None
        self._pending = None
        self._ahead = None
        self._last_read = None
        self._cur: Optional[str] = None
        self._block: dict = {}
        self._repl: dict = {}
        self.blocks_read = 0
        self.restarts = 0
        self.table = _LazyView(self, "table")
        self.repl = _LazyView(self, "repl")

    def _open(self):
        if self._fh is not None:
            self._fh.close()
        self._fh = gzip.open(self.path, "rt", encoding="utf-8", newline="")
        self._reader = csv.DictReader(self._fh)
        self._pending = None
        self._ahead = None
        self._last_read = None
        self._cur = None

    def _next_block(self) -> Optional[tuple[str, dict, dict]]:
        rows = []
        cut = None
        while True:
            row = self._pending if self._pending is not None else next(self._reader, None)
            self._pending = None
            if row is None:
                break
            if cut is None:
                cut = row["cutoff"]
            elif row["cutoff"] != cut:
                self._pending = row
                break
            rows.append(row)
        if cut is None:
            return None
        if self._last_read is not None and cut <= self._last_read:
            raise ValueError(f"ratings file is not grouped by ascending cutoff ({cut} after {self._last_read})")
        self._last_read = cut
        table, fringe = {}, defaultdict(list)
        for row in rows:
            pos = row["position"] or "UNK"
            off, dfn = float(row["offence"]), float(row["defence"])
            ms = float(row["minutes_share"]) if row.get("minutes_share") not in (None, "") else None
            table[row["player_id"]] = (off, dfn, ms, pos)
            if float(row["minutes"]) < FRINGE_MINUTES:
                fringe[pos].append((off, dfn))
                fringe["*"].append((off, dfn))
        repl = {}
        for pos in ("GK", "DEF", "MID", "FWD", "UNK"):
            m = self.meta_repl.get(cut, {}).get(pos)
            if m:
                repl[pos] = (float(m["offence"]), float(m["defence"]))
                continue
            pool = fringe.get(pos) if len(fringe.get(pos, [])) >= 5 else fringe.get("*")
            if pool:
                repl[pos] = (mean([q[0] for q in pool]), mean([q[1] for q in pool]))
        self.blocks_read += 1
        return cut, table, repl

    def _load(self, cut: str) -> None:
        if cut == self._cur:
            return
        if self._reader is None or (self._cur is not None and cut < self._cur):
            if self._reader is not None:
                self.restarts += 1
            self._open()
        while True:
            blk = self._ahead if self._ahead is not None else self._next_block()
            self._ahead = None
            if blk is None:                 # end of file: no rows for this cutoff
                self._cur, self._block, self._repl = cut, {}, {}
                return
            if blk[0] < cut:
                continue
            if blk[0] == cut:
                self._cur, self._block, self._repl = blk
                return
            self._ahead = blk               # the requested cutoff has no rows; keep the later block
            self._cur, self._block, self._repl = cut, {}, {}
            return

    def close(self):
        if self._fh is not None:
            self._fh.close()
            self._fh = None


class _LazyView:
    def __init__(self, owner: LazyRatings, what: str):
        self.owner, self.what = owner, what

    def get(self, cut, default=None):
        if cut is None or cut not in self.owner.cutoff_set:
            return default
        self.owner._load(cut)
        return self.owner._block if self.what == "table" else self.owner._repl

    def __contains__(self, cut):
        return cut in self.owner.cutoff_set

    def __iter__(self):
        return iter(self.owner.cutoffs)

    def __len__(self):
        return len(self.owner.cutoffs)


# ============================================================================ indexes
class TeamResults:
    """Per-team competitive results (friendlies excluded) for form / rest / congestion."""

    def __init__(self, results: list[dict]):
        self.by_team: dict[str, list[tuple]] = defaultdict(list)
        for r in results:
            if is_friendly(r["name"]):
                continue
            euro = r["comp"] in EURO_ALL
            for team, opp, gf, ga in ((r["home"], r["away"], r["hs"], r["as"]), (r["away"], r["home"], r["as"], r["hs"])):
                pts = 3 if gf > ga else (1 if gf == ga else 0)
                self.by_team[team].append((r["at"], r["id"], opp, euro, gf, ga, pts))
        for lst in self.by_team.values():
            lst.sort(key=lambda t: (t[0], t[1]))
        self.keys = {t: [x[0] for x in lst] for t, lst in self.by_team.items()}

    def before(self, team: str, kick: datetime, match_id: str, opp: str) -> list[tuple]:
        """Results strictly before kick-off, newest first, without this match / duplicate fixtures."""
        lst = self.by_team.get(team)
        if not lst:
            return []
        j = bisect.bisect_left(self.keys[team], kick)
        out = []
        for k in range(j - 1, -1, -1):
            t = lst[k]
            if t[1] == match_id or (t[2] == opp and (kick - t[0]).total_seconds() < DUPLICATE_FIXTURE_DAYS * 86400):
                continue
            out.append(t)
        return out

    def euro_after(self, team: str, kick: datetime, match_id: str, days: int) -> bool:
        """A European fixture after kick-off within ``days`` calendar days (schedule information)."""
        lst = self.by_team.get(team)
        if not lst:
            return False
        j = bisect.bisect_right(self.keys[team], kick)
        for k in range(j, len(lst)):
            t = lst[k]
            if (t[0].date() - kick.date()).days > days:
                break
            if t[3] and t[1] != match_id:
                return True
        return False

    def has_any(self, team: str) -> bool:
        return team in self.by_team


class HomeAdvantage:
    """Shrunk log home/away goal ratio of a competition over a trailing window, vs the global one."""

    def __init__(self, results: list[dict]):
        comp_rows: dict[str, list[tuple]] = defaultdict(list)
        glob = []
        for r in results:
            if is_friendly(r["name"]):
                continue
            comp_rows[r["comp"]].append((r["at"], r["hs"], r["as"]))
            glob.append((r["at"], r["hs"], r["as"]))
        self.comp = {c: self._cum(v) for c, v in comp_rows.items()}
        self.glob = self._cum(glob)

    @staticmethod
    def _cum(rows):
        rows.sort(key=lambda t: t[0])
        at, ch, ca = [], [0], [0]
        for t, h, a in rows:
            at.append(t)
            ch.append(ch[-1] + h)
            ca.append(ca[-1] + a)
        return at, ch, ca

    @staticmethod
    def _window(cum, kick, days):
        at, ch, ca = cum
        j = bisect.bisect_left(at, kick)
        i = bisect.bisect_left(at, kick - timedelta(days=days))
        return j - i, ch[j] - ch[i], ca[j] - ca[i]

    def at(self, comp: str, kick: datetime) -> dict:
        n_g, hg_g, ag_g = self._window(self.glob, kick, HADV_WINDOW_DAYS)
        if n_g == 0 or hg_g <= 0 or ag_g <= 0:
            return {"league_hadv": None, "global_hadv": None, "league_hadv_dev": None, "league_hadv_n": 0}
        g = math.log(hg_g / ag_g)
        cum = self.comp.get(comp)
        n, hg, ag = self._window(cum, kick, HADV_WINDOW_DAYS) if cum else (0, 0, 0)
        if n == 0 or hg <= 0 or ag <= 0:
            return {"league_hadv": None, "global_hadv": g, "league_hadv_dev": None, "league_hadv_n": n}
        w = n / (n + HADV_SHRINK_MATCHES)
        lg = w * math.log(hg / ag) + (1 - w) * g
        return {"league_hadv": lg, "global_hadv": g, "league_hadv_dev": lg - g, "league_hadv_n": n}


class DetailsHistory:
    """Per-team line-ups and team xG from the details records (sorted by kickoff)."""

    def __init__(self, records: list[dict]):
        self.by_team: dict[str, list[tuple]] = defaultdict(list)
        for r in records:
            for side in SIDES:
                team = str(r[f"{side}_team_provider_id"])
                opp = str(r[f"{'away' if side == 'home' else 'home'}_team_provider_id"])
                starters = [p for p in r.get("players") or [] if p.get("is_starter") and p.get("team_side") == side]
                ids = [str(p["player_id"]) for p in starters]
                pos = {str(p["player_id"]): POSITION_ID.get(p.get("usual_position_id"), "UNK") for p in starters}
                xf = r.get(f"{side}_xg")
                xa = r.get(f"{'away' if side == 'home' else 'home'}_xg")
                xg = (float(xf), float(xa)) if xf is not None and xa is not None else None
                self.by_team[team].append((r["_at"], str(r["match_provider_id"]), opp, ids, pos, xg))
        for lst in self.by_team.values():
            lst.sort(key=lambda t: (t[0], t[1]))
        self.keys = {t: [x[0] for x in lst] for t, lst in self.by_team.items()}

    def before(self, team: str, kick: datetime, match_id: str, opp: str, n: int) -> list[tuple]:
        lst = self.by_team.get(team)
        if not lst:
            return []
        j = bisect.bisect_left(self.keys[team], kick)
        out = []
        for k in range(j - 1, -1, -1):
            t = lst[k]
            if t[1] == match_id or (t[2] == opp and (kick - t[0]).total_seconds() < DUPLICATE_FIXTURE_DAYS * 86400):
                continue
            out.append(t)
            if len(out) >= n:
                break
        return out


# ============================================================================ feature computation
def production_form_value(records: list[dict]) -> dict[str, dict]:
    """Production lineup form + value (experiment_lineup_strength.py definition, via stage A's
    re-implementation in experiment_xi_impact.py, which reproduces it exactly)."""
    import experiment_xi_impact as X  # local import: keeps this module importable without numpy-heavy setup
    return X.production_features(records)


def xi_strength(rt: Ratings, cut: str, ids: list[str], pos: dict) -> tuple[Optional[float], Optional[float], int]:
    tab, rp = rt.table.get(cut, {}), rt.repl.get(cut, {})
    off = dfn = 0.0
    unknown = 0
    for pid in ids:
        v = tab.get(pid)
        if v is None:
            unknown += 1
            r = rp.get(pos.get(pid, "UNK")) or rp.get("UNK")
            if r is None:
                return None, None, unknown
            off += r[0]
            dfn += r[1]
        else:
            off += v[0]
            dfn += v[1]
    return off, dfn, unknown


def side_xi_features(rt: Ratings, cut: Optional[str], starters: list[dict], prev: list[tuple],
                     usual_n: int, min_usual: int) -> dict:
    keys = ("xi_n", "xi_off", "xi_def", "xi_unrated", "usual_n", "usual_off", "usual_def", "xi_d_off", "xi_d_def")
    out = dict.fromkeys(keys)
    out["xi_n"] = len(starters)
    if cut is None or len(starters) != 11:
        return out
    ids = [str(p["player_id"]) for p in starters]
    pos = {str(p["player_id"]): POSITION_ID.get(p.get("usual_position_id"), "UNK") for p in starters}
    off, dfn, unk = xi_strength(rt, cut, ids, pos)
    if off is None:
        return out
    out.update(xi_off=off, xi_def=dfn, xi_unrated=unk)
    lineups = [t for t in prev if t[3]][:usual_n]
    out["usual_n"] = len(lineups)
    if len(lineups) < min_usual:
        return out
    uo = ud = 0.0
    for t in lineups:
        o, d, _u = xi_strength(rt, cut, t[3], t[4])
        if o is None:
            return out
        uo += o / len(t[3]) * 11.0
        ud += d / len(t[3]) * 11.0
    uo /= len(lineups)
    ud /= len(lineups)
    out.update(usual_off=uo, usual_def=ud, xi_d_off=off - uo, xi_d_def=dfn - ud)
    return out


def side_absent_features(rt: Ratings, cut: Optional[str], listed: Optional[bool], entries: list[dict]) -> dict:
    keys = ("unavail_listed", "n_injury", "n_suspension", "n_other", "unavail_n_rated", "unavail_off",
            "unavail_def", "unavail_off_w", "unavail_def_w", "unavail_value")
    out = dict.fromkeys(keys)
    out["unavail_listed"] = None if listed is None else int(listed)
    if not listed:
        return out
    c = Counter((u.get("type") or "other") for u in entries)
    out["n_injury"] = c.get("injury", 0)
    out["n_suspension"] = c.get("suspension", 0)
    out["n_other"] = sum(v for k, v in c.items() if k not in ("injury", "suspension"))
    vals = [u.get("market_value") for u in entries]
    out["unavail_value"] = float(sum(v for v in vals if v is not None)) if all(v is not None for v in vals) else None
    if cut is None:
        return out
    tab, rp = rt.table.get(cut, {}), rt.repl.get(cut, {})
    n_rated, so, sd, wo, wd = 0, 0.0, 0.0, 0.0, 0.0
    for u in entries:
        v = tab.get(str(u.get("player_id")))
        if v is None:
            continue          # unrated (fringe / unseen): at replacement level by definition, adds 0
        r = rp.get(v[3]) or rp.get("UNK")
        if r is None:
            continue
        n_rated += 1
        ao, ad = v[0] - r[0], v[1] - r[1]
        share = min(v[2], 1.0) if v[2] is not None else 0.0
        so += ao
        sd += ad
        wo += share * ao
        wd += share * ad
    out.update(unavail_n_rated=n_rated, unavail_off=so, unavail_def=sd, unavail_off_w=wo, unavail_def_w=wd)
    return out


def side_form_features(prev_details: list[tuple], prev_results: list[tuple]) -> dict:
    out = dict.fromkeys(("l5_n", "l5_xg_n", "xg_for_l5", "xg_against_l5", "res_l5_n", "ppg_l5", "gf_l5", "ga_l5"))
    last = prev_details[:FORM_N]
    xg = [t[5] for t in last if t[5] is not None]
    out["l5_n"], out["l5_xg_n"] = len(last), len(xg)
    if len(xg) >= FORM_MIN:
        out["xg_for_l5"] = mean([x[0] for x in xg])
        out["xg_against_l5"] = mean([x[1] for x in xg])
    res = prev_results[:FORM_N]
    out["res_l5_n"] = len(res)
    if len(res) >= FORM_MIN:
        out["ppg_l5"] = mean([t[6] for t in res])
        out["gf_l5"] = mean([t[4] for t in res])
        out["ga_l5"] = mean([t[5] for t in res])
    return out


def side_rest_features(tr: TeamResults, team: str, kick: datetime, match_id: str, prev_results: list[tuple]) -> dict:
    out = dict.fromkeys(("rest_days", "n_matches_14d", "euro_before_3d", "euro_after_3d"))
    if not tr.has_any(team):
        return out            # team unknown to the results table: everything unknown
    if prev_results:
        out["rest_days"] = (kick - prev_results[0][0]).total_seconds() / 86400.0
    out["n_matches_14d"] = sum(1 for t in prev_results if (kick - t[0]).total_seconds() < CONGESTION_DAYS * 86400)
    out["euro_before_3d"] = int(any(t[3] and (kick.date() - t[0].date()).days <= EURO_WINDOW_DAYS
                                    for t in prev_results[:6]))
    out["euro_after_3d"] = int(tr.euro_after(team, kick, match_id, EURO_WINDOW_DAYS))
    return out


@dataclass
class Inputs:
    records: list[dict]
    lambdas: dict
    results: list[dict]
    ratings: Ratings
    presence: dict                      # match id -> (home, away) key presence or None
    layer: object                       # GoalLayer-like: .adjust(lh, la)
    comp_names: dict = field(default_factory=dict)   # match id -> competition name (optional)
    usual_n: int = USUAL_N
    min_usual: int = MIN_USUAL
    competitions: Optional[set] = None  # restrict output rows to these competition ids


def build_rows(inp: Inputs) -> list[dict]:
    """One feature row per details record (pure function of the inputs; used by the tests)."""
    dh = DetailsHistory(inp.records)
    tr = TeamResults(inp.results)
    ha = HomeAdvantage(inp.results)
    prod = production_form_value(inp.records)
    names = dict(inp.comp_names)
    for r in inp.results:
        names.setdefault(r["id"], r["name"])
    rows = []
    for r in inp.records:
        mid = str(r["match_provider_id"])
        comp = str(r.get("competition_provider_id"))
        if inp.competitions is not None and comp not in inp.competitions:
            continue
        kick = r["_at"]
        th, ta = str(r["home_team_provider_id"]), str(r["away_team_provider_id"])
        cname = names.get(mid)
        ctype = competition_type(comp, cname) if comp not in EURO_MAIN else "european"
        row = {
            "match_id": mid, "kickoff": kick.isoformat(), "season": r.get("season"),
            "competition_provider_id": comp, "competition_name": cname,
            "source_league_id": r.get("source_league_id"), "comp_type": ctype,
            "comp_is_euro": int(ctype == "european"), "home_team_id": th, "away_team_id": ta,
            "details_source": r.get("_file"),
            "y_home_goals": r.get("home_score"), "y_away_goals": r.get("away_score"),
            "y_home_xg": r.get("home_xg"), "y_away_xg": r.get("away_xg"),
        }
        lam = inp.lambdas.get(mid)
        if lam:
            lh, la = inp.layer.adjust(lam["lh"], lam["la"])
            row.update(lambda_cutoff=lam["cutoff"], lambda_source=lam["source"], lambda_home_raw=lam["lh"],
                       lambda_away_raw=lam["la"], lambda_home=lh, lambda_away=la)
        else:
            row.update(dict.fromkeys(("lambda_cutoff", "lambda_source", "lambda_home_raw", "lambda_away_raw",
                                      "lambda_home", "lambda_away")))
        vh, va = r.get("home_starters_market_value"), r.get("away_starters_market_value")
        row["home_starters_value"] = float(vh) if vh else None
        row["away_starters_value"] = float(va) if va else None
        row["value_log_ratio"] = math.log(vh / va) if vh and va else None
        pf = prod.get(mid) or {}
        row["lineup_form"] = pf.get("form")
        cut = inp.ratings.cutoff_before(kick)
        row["ratings_cutoff"] = cut
        row["ratings_age_days"] = (kick - datetime.fromisoformat(cut)).total_seconds() / 86400.0 if cut else None
        pres = inp.presence.get(mid)
        for side, team, opp in (("home", th, ta), ("away", ta, th)):
            starters = [p for p in r.get("players") or [] if p.get("is_starter") and p.get("team_side") == side]
            prev_d = dh.before(team, kick, mid, opp, max(inp.usual_n, FORM_N))
            feats = side_xi_features(inp.ratings, cut, starters, prev_d, inp.usual_n, inp.min_usual)
            entries = [u for u in r.get("unavailable") or [] if u.get("team_side") == side]
            if pres is not None and pres[0 if side == "home" else 1] is not None:
                listed = pres[0 if side == "home" else 1]
            else:     # raw file unavailable: a non-empty parsed list proves the key was sent
                listed = True if entries else None
            feats.update(side_absent_features(inp.ratings, cut, listed, entries))
            prev_r = tr.before(team, kick, mid, opp)
            feats.update(side_form_features(prev_d, prev_r))
            feats.update(side_rest_features(tr, team, kick, mid, prev_r))
            for k, v in feats.items():
                row[f"{side}_{k}"] = v
        row.update(ha.at(comp, kick))
        rows.append(row)
    return rows


SIDE_KEYS = ["xi_n", "xi_off", "xi_def", "xi_unrated", "usual_n", "usual_off", "usual_def", "xi_d_off", "xi_d_def",
             "unavail_listed", "n_injury", "n_suspension", "n_other", "unavail_n_rated", "unavail_off", "unavail_def",
             "unavail_off_w", "unavail_def_w", "unavail_value",
             "l5_n", "l5_xg_n", "xg_for_l5", "xg_against_l5", "res_l5_n", "ppg_l5", "gf_l5", "ga_l5",
             "rest_days", "n_matches_14d", "euro_before_3d", "euro_after_3d"]
COLUMNS = (["match_id", "kickoff", "season", "competition_provider_id", "competition_name", "source_league_id",
            "comp_type", "comp_is_euro", "home_team_id", "away_team_id", "details_source",
            "y_home_goals", "y_away_goals", "y_home_xg", "y_away_xg",
            "lambda_cutoff", "lambda_source", "lambda_home_raw", "lambda_away_raw", "lambda_home", "lambda_away",
            "home_starters_value", "away_starters_value", "value_log_ratio", "lineup_form",
            "ratings_cutoff", "ratings_age_days"]
           + [f"{s}_{k}" for s in SIDES for k in SIDE_KEYS]
           + ["league_hadv", "global_hadv", "league_hadv_dev", "league_hadv_n"])
LABEL_COLUMNS = ("y_home_goals", "y_away_goals", "y_home_xg", "y_away_xg")
FEATURE_GROUPS = {   # used by train_match_model.py for ablations (per-side names without prefix)
    "base": ["lambda_home", "lambda_away"],
    "value": ["value_log_ratio"],
    "form_prod": ["lineup_form"],
    "xi": ["xi_d_off", "xi_d_def"],
    "absent": ["n_injury", "n_suspension", "unavail_off_w", "unavail_def_w"],
    "form": ["xg_for_l5", "xg_against_l5", "ppg_l5"],
    "rest": ["rest_days", "n_matches_14d", "euro_before_3d", "euro_after_3d"],
    "context": ["comp_is_euro", "league_hadv_dev"],
}


def fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(int(v))
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return ""
        return f"{v:.6g}" if abs(v) >= 1e6 else f"{round(v, 6):.6f}".rstrip("0").rstrip(".") if v != 0 else "0"
    return str(v)


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    with open(tmp, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:   # deterministic bytes
            with io.TextIOWrapper(gz, encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(COLUMNS)
                for r in rows:
                    w.writerow([fmt(r.get(c)) for c in COLUMNS])
    os.replace(tmp, path)


def coverage(rows: list[dict]) -> dict:
    """Non-null share of every feature column, per competition and overall."""
    by_comp = defaultdict(list)
    for r in rows:
        by_comp[r["competition_provider_id"]].append(r)
    cols = [c for c in COLUMNS if c not in ("match_id", "kickoff", "home_team_id", "away_team_id")]
    overall = {c: round(sum(r.get(c) is not None for r in rows) / max(len(rows), 1), 4) for c in cols}
    comp = {}
    for cp, rs in sorted(by_comp.items(), key=lambda kv: -len(kv[1])):
        comp[cp] = {"n": len(rs), "first": min(r["kickoff"] for r in rs)[:10], "last": max(r["kickoff"] for r in rs)[:10],
                    **{k: round(sum(r.get(c) is not None for r in rs) / len(rs), 4) for k, c in (
                        ("lambda", "lambda_home"), ("value", "value_log_ratio"), ("lineup_form", "lineup_form"),
                        ("xg_l5_home", "home_xg_for_l5"), ("ppg_l5_home", "home_ppg_l5"),
                        ("rest_home", "home_rest_days"), ("league_hadv", "league_hadv_dev"))},
                    "xi_both": round(sum(r.get("home_xi_d_off") is not None and r.get("away_xi_d_off") is not None
                                         for r in rs) / len(rs), 4),
                    "unavail_key_sent_share_of_sides": round(sum(r.get(f"{s}_unavail_listed") == 1 for r in rs
                                                                 for s in SIDES) / (2 * len(rs)), 4)}
    listed = Counter()
    for r in rows:
        for s in SIDES:
            listed[{None: "unknown", 0: "key_absent", 1: "key_present"}[r.get(f"{s}_unavail_listed")]] += 1
    return {"overall_non_null_share": overall, "per_competition": comp, "unavailable_key_per_side": dict(listed)}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="pre-kick-off match features (stage B)")
    ap.add_argument("--details", action="append", type=Path)
    ap.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    ap.add_argument("--lambdas", action="append", type=Path)
    ap.add_argument("--db", type=Path, default=BACKEND_DIR / "football_intelligence.db")
    ap.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    ap.add_argument("--ratings", type=Path, default=TRAIN_DATA / "player_impact_asof.csv.gz")
    ap.add_argument("--meta", type=Path, default=TRAIN_DATA / "player_impact_meta.json")
    ap.add_argument("--usual-n", type=int, default=USUAL_N)
    ap.add_argument("--min-usual", type=int, default=MIN_USUAL)
    ap.add_argument("--competitions", default=None, help="comma-separated FotMob league ids (default: all in details)")
    ap.add_argument("--slim", action="store_true", help="keep only the record keys this script reads (memory)")
    ap.add_argument("--lazy-ratings", action="store_true", help="stream the ratings file one cutoff at a time")
    ap.add_argument("--results-exclude-awarded", action="store_true",
                    help="drop awarded = 1 results from the results used for form / rest / home advantage")
    ap.add_argument("--results-exclude-conflicts", default="",
                    help="comma-separated all_results.db conflicts.kind values whose match ids are dropped")
    ap.add_argument("--out", type=Path, default=TRAIN_DATA / "match_features.csv.gz")
    ap.add_argument("--report", type=Path, default=TRAIN_DATA / "match_features_report.json")
    args = ap.parse_args(argv)
    t0 = time.time()

    from app.prediction.goal_model import get_goal_layer
    layer = get_goal_layer()
    details = args.details or DEFAULT_DETAILS
    lambda_files = args.lambdas or DEFAULT_LAMBDAS
    records, dstats = read_details(details, slim=args.slim)
    print(f"details: {dstats}", flush=True)
    id_map = db_id_map(args.db)
    lambdas = read_lambdas(lambda_files, id_map)
    results, res_src = read_results(args.results, args.db, exclude_awarded=args.results_exclude_awarded,
                                    exclude_conflict_kinds=args.results_exclude_conflicts.split(","))
    print(f"lambdas {len(lambdas)}, results {len(results)} ({res_src}) [{time.time() - t0:.0f}s]", flush=True)
    ratings = LazyRatings(args.ratings, args.meta) if args.lazy_ratings else read_ratings(args.ratings, args.meta)
    print(f"ratings: {len(ratings.cutoffs)} cutoffs "
          f"({ratings.cutoffs[0] if ratings.cutoffs else '-'}..{ratings.cutoffs[-1] if ratings.cutoffs else '-'}) "
          f"[{time.time() - t0:.0f}s]", flush=True)
    presence = {}
    missing_raw = 0
    for r in records:
        mid = str(r["match_provider_id"])
        p = unavailable_presence(args.raw_dir, mid)
        if p is None:
            missing_raw += 1
        presence[mid] = p
    print(f"raw presence read ({missing_raw} raw files missing/unreadable) [{time.time() - t0:.0f}s]", flush=True)
    comps = set(args.competitions.split(",")) if args.competitions else None
    rows = build_rows(Inputs(records, lambdas, results, ratings, presence, layer, usual_n=args.usual_n,
                             min_usual=args.min_usual, competitions=comps))
    write_rows(args.out, rows)
    lazy_stats = ({"blocks_read": ratings.blocks_read, "restarts": ratings.restarts}
                  if isinstance(ratings, LazyRatings) else None)
    rep = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": {"details": [str(p) for p in details], "lambdas": [str(p) for p in lambda_files],
                   "results": res_src, "ratings": str(args.ratings), "meta": str(args.meta),
                   "raw_dir": str(args.raw_dir), "usual_n": args.usual_n, "min_usual": args.min_usual,
                   "slim": args.slim, "lazy_ratings": lazy_stats,
                   "goal_layer": {"m": layer.m, "a": layer.a, "b": layer.b, "rho": layer.rho,
                                  "nb_dispersion": layer.nb_dispersion, "trained": layer.trained}},
        "details_stats": dstats, "raw_files_missing": missing_raw, "rows": len(rows),
        "rows_with_lambda": sum(r["lambda_home"] is not None for r in rows),
        "coverage": coverage(rows), "seconds": round(time.time() - t0, 1),
    }
    tmp = args.report.with_name(args.report.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    os.replace(tmp, args.report)
    print(f"-> {args.out} ({len(rows)} rows, {rep['rows_with_lambda']} with lambda) {rep['seconds']} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
