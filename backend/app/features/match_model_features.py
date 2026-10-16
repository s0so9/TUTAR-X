"""Runtime features for the match model (the live counterpart of
``scripts/training/build_match_features.py``).

The match model (``app.prediction.match_model``) was trained on the feature rows of
``data/training/match_features.csv.gz``. This module computes the same columns for a live fixture
from what exists at prediction time:

  value      starters' market value of each side from the FotMob line-up already fetched for the
             squad-value signal (``app.prediction.squad_value.fetch_squad_info``: ``starter_value``)
  xi         as-of player ratings (``player_impact_latest.json`` or, until it exists, the latest cutoff
             of ``data/training/player_impact_asof.csv.gz`` strictly before kick-off), the line-up's
             ``starter_ids``, and the team's usual XI = mean of its previous <= 10 line-ups in the
             details JSONL files (valued at the same cutoff, scaled to 11 players, >= 3 needed)
  form       last 5 matches of the team in the details competitions (details JSONL records, extended
             with production-DB matches played after the details files end, with their DB xG):
             mean xG for / against (>= 3 with xG); last 5 competitive results (production DB, all
             competitions, friendlies excluded): points, goals for / against (>= 3)
  rest       days since the previous competitive result, results in the previous 14 days, European
             match within 3 calendar days before; the "after" flag needs the fixture schedule
             (``schedule`` source) and is unknown (None) without one
  context    European competition flag (FotMob ids 42/73/10216 + qualifications), the competition's
             shrunk home advantage over the previous 365 days minus the global one (production DB)
  absent     counts of FotMob's pre-match unavailable list by type (``squad_info.unavailable``);
             the rating-based absentee columns need player ids, which the squad info does not carry

Every definition, window and threshold is the training script's (constants below; a test checks
they equal the script's). A value the sources do not provide stays None - nothing is imputed.
Runtime approximations (predicted line-ups, unknown positions of unrated starters, details
files that end before kick-off, DB vs results-table differences) are recorded per match in
``RuntimeFeatures.notes`` and quantified by ``scripts/training/check_runtime_parity.py``
(docs/training/match-model-runtime.md).
"""

from __future__ import annotations

import bisect
import csv
import gzip
import json
import logging
import math
import os
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
TRAINING_DATA = BACKEND_DIR / "data" / "training"
DEFAULT_DETAILS_FILES = (TRAINING_DATA / "fotmob_match_details.jsonl",
                         TRAINING_DATA / "fotmob_match_details_history.jsonl")
DEFAULT_ASOF_RATINGS = TRAINING_DATA / "player_impact_asof.csv.gz"
DEFAULT_ASOF_META = TRAINING_DATA / "player_impact_meta.json"
DEFAULT_LATEST_RATINGS = (BACKEND_DIR / "config" / "player_impact_latest.json",
                          TRAINING_DATA / "player_impact_latest.json")
DEFAULT_SQUAD_SNAPSHOT = BACKEND_DIR / "data" / "players" / "squad_members_2026_27.jsonl"

# ---- definitions copied from scripts/training/build_match_features.py (tests check equality) ----
EURO_MAIN = {"42", "73", "10216"}
EURO_ALL = EURO_MAIN | {"10611", "10613", "10615"}
CUP_MARKERS = ("Cup", "Pokal", "Coupe", "Copa", "Coppa", "Beker", "Taça", "Taca", "Kupa", "Pokalen",
               "Trophy", "Shield", "Supercup", "Super Cup", "Supercopa", "Supercoppa")
POSITION_ID = {0: "GK", 1: "DEF", 2: "MID", 3: "FWD"}
FRINGE_MINUTES = 450.0
SIDES = ("home", "away")
USUAL_N = 10
MIN_USUAL = 3
FORM_N = 5
FORM_MIN = 3
HADV_WINDOW_DAYS = 365
HADV_SHRINK_MATCHES = 100.0
CONGESTION_DAYS = 14
EURO_WINDOW_DAYS = 3
DUPLICATE_FIXTURE_DAYS = 1.0

SIDE_KEYS = ["xi_n", "xi_off", "xi_def", "xi_unrated", "usual_n", "usual_off", "usual_def", "xi_d_off", "xi_d_def",
             "unavail_listed", "n_injury", "n_suspension", "n_other", "unavail_n_rated", "unavail_off", "unavail_def",
             "unavail_off_w", "unavail_def_w", "unavail_value",
             "l5_n", "l5_xg_n", "xg_for_l5", "xg_against_l5", "res_l5_n", "ppg_l5", "gf_l5", "ga_l5",
             "rest_days", "n_matches_14d", "euro_before_3d", "euro_after_3d"]
MATCH_KEYS = ["comp_is_euro", "value_log_ratio", "lineup_form", "league_hadv", "global_hadv", "league_hadv_dev",
              "league_hadv_n", "home_starters_value", "away_starters_value"]
# columns the runtime cannot produce (no source at prediction time); a model using them is refused
UNSUPPORTED_COLUMNS = {
    "lineup_form": "training uses the as-of production lineup form of experiment_xi_impact.production_features; "
                   "no runtime equivalent (config/player_form.json is a different, static snapshot)",
    "unavail_n_rated": "needs the unavailable players' ids (squad info has names only)",
    "unavail_off": "needs the unavailable players' ids (squad info has names only)",
    "unavail_def": "needs the unavailable players' ids (squad info has names only)",
    "unavail_off_w": "needs the unavailable players' ids (squad info has names only)",
    "unavail_def_w": "needs the unavailable players' ids (squad info has names only)",
}
# match-level columns usable by model terms (per-side columns are SIDE_KEYS)
SUPPORTED_MATCH_COLUMNS = {"comp_is_euro", "value_log_ratio", "league_hadv", "global_hadv", "league_hadv_dev",
                           "league_hadv_n"}
SUPPORTED_SIDE_COLUMNS = {k for k in SIDE_KEYS if k not in UNSUPPORTED_COLUMNS}

# which runtime groups produce which per-side / match columns (only required groups are computed)
COLUMN_GROUP = {
    **{k: "xi" for k in ("xi_n", "xi_off", "xi_def", "xi_unrated", "usual_n", "usual_off", "usual_def",
                         "xi_d_off", "xi_d_def")},
    **{k: "absent" for k in ("unavail_listed", "n_injury", "n_suspension", "n_other", "unavail_value")},
    **{k: "xg_form" for k in ("l5_n", "l5_xg_n", "xg_for_l5", "xg_against_l5")},
    **{k: "results" for k in ("res_l5_n", "ppg_l5", "gf_l5", "ga_l5", "rest_days", "n_matches_14d",
                              "euro_before_3d")},
    "euro_after_3d": "schedule",
    **{k: "hadv" for k in ("league_hadv", "global_hadv", "league_hadv_dev", "league_hadv_n")},
    "comp_is_euro": "context", "value_log_ratio": "value",
}
ALL_GROUPS = frozenset(COLUMN_GROUP.values())


# ============================================================================ small helpers
def to_naive_utc(value: Any) -> datetime:
    """datetime / ISO string -> naive UTC (the training files' convention)."""
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip().replace(" ", "T")
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def is_friendly(name: Optional[str]) -> bool:
    return bool(name) and "Friendl" in name


def competition_type(pid: Optional[str], name: Optional[str]) -> str:
    if pid in EURO_ALL:
        return "european"
    if name and any(m in name for m in CUP_MARKERS):
        return "cup"
    return "league"


def _mean(xs: Sequence[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def _sql_dt(dt: datetime) -> str:
    """Parameter format of the DB's DATETIME text columns (SQLAlchemy's SQLite storage format)."""
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")


def _files_signature(paths: Sequence[Path]) -> Tuple:
    sig = []
    for p in paths:
        try:
            st = os.stat(p)
            sig.append((str(p), st.st_size, st.st_mtime_ns))
        except OSError:
            sig.append((str(p), None, None))
    return tuple(sig)


# ============================================================================ details history
# per-team entry: (kickoff, match_id, opponent_id, starter_ids tuple, {player_id: position}, (xg_for, xg_against)|None, source)
HistEntry = Tuple[datetime, str, str, Tuple[str, ...], Dict[str, str], Optional[Tuple[float, float]], str]


class LineupHistory:
    """Per-team line-ups and team xG from the details JSONL files (training's DetailsHistory),
    plus each player's usual position over time and each competition's last details kick-off."""

    def __init__(self) -> None:
        self.by_team: Dict[str, List[HistEntry]] = defaultdict(list)
        self.keys: Dict[str, List[datetime]] = {}
        self.match_ids: set = set()
        self.awarded_ids: set = set()
        self.competitions: set = set()
        self.comp_last_kickoff: Dict[str, datetime] = {}
        self.player_positions: Dict[str, List[Tuple[datetime, str]]] = {}
        self._player_pos_keys: Dict[str, List[datetime]] = {}
        self.stats: Counter = Counter()
        self.files: List[str] = []
        self.last_kickoff: Optional[datetime] = None

    # ------------------------------------------------------------------ building
    @classmethod
    def from_records(cls, records: Iterable[dict]) -> "LineupHistory":
        """Build from already-parsed details records (first occurrence of a match id wins,
        awarded matches dropped - exactly as build_match_features.read_details)."""
        h = cls()
        pos_rows: Dict[str, List[Tuple[datetime, str]]] = defaultdict(list)
        for r in records:
            h._add_record(r, pos_rows)
        h._finish(pos_rows)
        return h

    @classmethod
    def from_files(cls, paths: Sequence[Path]) -> "LineupHistory":
        h = cls()
        pos_rows: Dict[str, List[Tuple[datetime, str]]] = defaultdict(list)
        for path in paths:
            path = Path(path)
            if not path.exists():
                h.stats["missing_files"] += 1
                continue
            h.files.append(str(path))
            with open(path, "rb") as f:
                for raw in f:
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except ValueError:
                        h.stats["unparsable_lines"] += 1   # e.g. the partial last line of a file being written
                        continue
                    h._add_record(r, pos_rows)
        h._finish(pos_rows)
        return h

    def _add_record(self, r: dict, pos_rows: Dict[str, List[Tuple[datetime, str]]]) -> None:
        try:
            mid = str(r["match_provider_id"])
            at = to_naive_utc(r["scheduled_at"])
        except (KeyError, TypeError, ValueError):
            self.stats["unparsable_lines"] += 1
            return
        if mid in self.match_ids or mid in self.awarded_ids:
            self.stats["duplicate_ids"] += 1
            return
        if r.get("awarded"):
            self.awarded_ids.add(mid)
            self.stats["awarded_dropped"] += 1
            return
        self.match_ids.add(mid)
        comp = str(r.get("competition_provider_id"))
        self.competitions.add(comp)
        if comp not in self.comp_last_kickoff or at > self.comp_last_kickoff[comp]:
            self.comp_last_kickoff[comp] = at
        if self.last_kickoff is None or at > self.last_kickoff:
            self.last_kickoff = at
        players = r.get("players") or []
        for side in SIDES:
            other = "away" if side == "home" else "home"
            team = str(r.get(f"{side}_team_provider_id"))
            opp = str(r.get(f"{other}_team_provider_id"))
            starters = [p for p in players if p.get("is_starter") and p.get("team_side") == side]
            ids = tuple(str(p["player_id"]) for p in starters)
            pos = {str(p["player_id"]): POSITION_ID.get(p.get("usual_position_id"), "UNK") for p in starters}
            for pid, ps in pos.items():
                if ps != "UNK":
                    pos_rows[pid].append((at, ps))
            xf, xa = r.get(f"{side}_xg"), r.get(f"{other}_xg")
            xg = (float(xf), float(xa)) if xf is not None and xa is not None else None
            self.by_team[team].append((at, mid, opp, ids, pos, xg, "details"))
        self.stats["records"] += 1

    def _finish(self, pos_rows: Dict[str, List[Tuple[datetime, str]]]) -> None:
        for lst in self.by_team.values():
            lst.sort(key=lambda t: (t[0], t[1]))
        self.keys = {t: [x[0] for x in lst] for t, lst in self.by_team.items()}
        for pid, rows in pos_rows.items():
            rows.sort()
            compact: List[Tuple[datetime, str]] = []
            for at, ps in rows:
                if not compact or compact[-1][1] != ps:
                    compact.append((at, ps))
            self.player_positions[pid] = compact
            self._player_pos_keys[pid] = [x[0] for x in compact]

    # ------------------------------------------------------------------ queries
    def before(self, team: str, kick: datetime, match_id: str, opp: str, n: int,
               extra: Sequence[HistEntry] = ()) -> List[HistEntry]:
        """The team's entries strictly before kick-off, newest first, without this match and
        duplicate fixtures of the same pair within 1 day (training's DetailsHistory.before).
        ``extra`` entries (production-DB matches the details files do not hold) are merged in."""
        lst = self.by_team.get(team) or []
        j = bisect.bisect_left(self.keys.get(team) or [], kick)
        cands = list(lst[:j])
        if extra:
            cands = sorted(cands + [e for e in extra if e[0] < kick], key=lambda t: (t[0], t[1]))
        out: List[HistEntry] = []
        for t in reversed(cands):
            if t[1] == match_id or (t[2] == opp and (kick - t[0]).total_seconds() < DUPLICATE_FIXTURE_DAYS * 86400):
                continue
            out.append(t)
            if len(out) >= n:
                break
        return out

    def position_before(self, player_id: str, kick: datetime) -> Optional[str]:
        """The player's latest usual position (GK/DEF/MID/FWD) as a starter before kick-off."""
        keys = self._player_pos_keys.get(player_id)
        if not keys:
            return None
        i = bisect.bisect_left(keys, kick) - 1
        return self.player_positions[player_id][i][1] if i >= 0 else None


_history_cache: Dict[Tuple, LineupHistory] = {}
_history_lock = threading.Lock()


def get_lineup_history(paths: Sequence[Path]) -> LineupHistory:
    """Cached LineupHistory of the given details files; rebuilt when a file changes."""
    paths = tuple(Path(p) for p in paths)
    sig = _files_signature(paths)
    with _history_lock:
        hit = _history_cache.get(sig)
        if hit is not None:
            return hit
        hist = LineupHistory.from_files(paths)
        _history_cache.clear()
        _history_cache[sig] = hist
        logger.info("match-model lineup history: %s records from %s (%s)", hist.stats.get("records", 0),
                    [Path(p).name for p in paths], dict(hist.stats))
        return hist


# ============================================================================ ratings
@dataclass
class RatingsCut:
    """Player ratings of one cutoff: pid -> (offence, defence, minutes_share, position), and the
    replacement level per position (training's read_ratings convention)."""

    cutoff: str
    table: Dict[str, Tuple[float, float, Optional[float], str]]
    repl: Dict[str, Tuple[float, float]]
    source: str

    @property
    def cutoff_dt(self) -> datetime:
        return datetime.fromisoformat(self.cutoff[:10])


def _repl_levels(fringe: Dict[str, List[Tuple[float, float]]], meta_repl: Optional[dict]) -> Dict[str, Tuple[float, float]]:
    out: Dict[str, Tuple[float, float]] = {}
    for pos in ("GK", "DEF", "MID", "FWD", "UNK"):
        m = (meta_repl or {}).get(pos)
        if m:
            out[pos] = (float(m["offence"]), float(m["defence"]))
            continue
        pool = fringe.get(pos) if len(fringe.get(pos, [])) >= 5 else fringe.get("*")
        if pool:
            out[pos] = (_mean([p[0] for p in pool]), _mean([p[1] for p in pool]))
    return out


def _fnum(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


class AsofRatings:
    """``player_impact_asof.csv.gz``: one block of rows per cutoff (ratings fitted on matches before
    the cutoff date). ``for_kickoff`` returns the latest cutoff strictly before kick-off, exactly as
    build_match_features.Ratings.cutoff_before. Blocks are loaded on demand and cached."""

    def __init__(self, path: Path, meta_path: Optional[Path] = None, preload: bool = False, max_cached: int = 4):
        self.path = Path(path)
        self.meta_repl: Dict[str, dict] = {}
        cutoffs = None
        if meta_path is not None and Path(meta_path).exists():
            meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
            per = meta.get("per_cutoff") or []
            for e in per:
                self.meta_repl[e["cutoff"]] = e.get("replacement_level") or {}
        self._blocks: Dict[str, RatingsCut] = {}
        self._order: List[str] = []
        self.max_cached = max_cached
        self._lock = threading.Lock()
        if preload:
            self._load_all()
            cutoffs = sorted(self._blocks)
            self.max_cached = len(cutoffs) + 1
        if cutoffs is None:
            # one pass: every cutoff, keeping the rows of the latest one (the block live use needs)
            seen = set()
            latest: Optional[str] = None
            kept: List[list] = []
            with gzip.open(self.path, "rt", encoding="utf-8", newline="") as f:
                rd = csv.reader(f)
                header = next(rd)
                ci = header.index("cutoff")
                for row in rd:
                    c = row[ci]
                    seen.add(c)
                    if latest is None or c > latest:
                        latest, kept = c, [row]
                    elif c == latest:
                        kept.append(row)
            cutoffs = sorted(seen)
            if latest is not None:
                self._blocks[latest] = self._rows_to_cut(latest, (dict(zip(header, r)) for r in kept))
                self._order.append(latest)
        self.cutoffs = cutoffs
        self.cutoff_dt = [datetime.fromisoformat(c) for c in cutoffs]

    def cutoff_before(self, kick: datetime) -> Optional[str]:
        i = bisect.bisect_left(self.cutoff_dt, kick) - 1
        return self.cutoffs[i] if i >= 0 else None

    def _rows_to_cut(self, cut: str, rows: Iterable[dict]) -> RatingsCut:
        table: Dict[str, Tuple[float, float, Optional[float], str]] = {}
        fringe: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
        for row in rows:
            pos = row["position"] or "UNK"
            off, dfn = float(row["offence"]), float(row["defence"])
            ms = float(row["minutes_share"]) if row.get("minutes_share") not in (None, "") else None
            table[row["player_id"]] = (off, dfn, ms, pos)
            if float(row["minutes"]) < FRINGE_MINUTES:
                fringe[pos].append((off, dfn))
                fringe["*"].append((off, dfn))
        return RatingsCut(cut, table, _repl_levels(fringe, self.meta_repl.get(cut)), f"asof:{self.path.name}")

    def _load_all(self) -> None:
        rows_by_cut: Dict[str, List[dict]] = defaultdict(list)
        with gzip.open(self.path, "rt", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                rows_by_cut[row["cutoff"]].append(row)
        for cut, rows in rows_by_cut.items():
            self._blocks[cut] = self._rows_to_cut(cut, rows)
        self._order = sorted(self._blocks)

    def block(self, cut: str) -> Optional[RatingsCut]:
        with self._lock:
            hit = self._blocks.get(cut)
            if hit is not None:
                return hit
        rows = []
        with gzip.open(self.path, "rt", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if row["cutoff"] == cut:
                    rows.append(row)
        if not rows:
            return None
        rc = self._rows_to_cut(cut, rows)
        with self._lock:
            self._blocks[cut] = rc
            self._order.append(cut)
            while len(self._order) > self.max_cached:
                self._blocks.pop(self._order.pop(0), None)
        return rc

    def for_kickoff(self, kick: datetime) -> Optional[RatingsCut]:
        cut = self.cutoff_before(kick)
        return self.block(cut) if cut else None


class LatestRatings:
    """Runtime export of the latest ratings (``player_impact_latest.json``; one cutoff).

    Accepted layout: ``{"cutoff": "YYYY-MM-DD", "players": {pid: {"offence", "defence", "position"?,
    "minutes"?, "minutes_share"?}} | [{"player_id", ...}], "replacement_level"?: {pos: {"offence",
    "defence"}}}``. Without replacement levels they are computed from the fringe players
    (< 450 minutes) as build_match_features.read_ratings does. Usable only for kick-offs after
    the cutoff date (the ratings were fitted on matches before it)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        cut = data.get("cutoff") or data.get("cutoff_date") or data.get("as_of")
        if not cut:
            raise ValueError(f"{self.path}: no cutoff")
        players = data.get("players")
        if isinstance(players, dict):
            items = [(str(k), v) for k, v in players.items()]
        elif isinstance(players, list):
            items = [(str(p.get("player_id")), p) for p in players]
        else:
            raise ValueError(f"{self.path}: no players")
        table: Dict[str, Tuple[float, float, Optional[float], str]] = {}
        fringe: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
        for pid, p in items:
            off, dfn = _fnum(p.get("offence")), _fnum(p.get("defence"))
            if pid in ("", "None") or off is None or dfn is None:
                continue                      # never invent a rating for a malformed entry
            pos = p.get("position") or "UNK"
            table[pid] = (off, dfn, _fnum(p.get("minutes_share")), pos)
            minutes = _fnum(p.get("minutes"))
            if minutes is not None and minutes < FRINGE_MINUTES:
                fringe[pos].append((off, dfn))
                fringe["*"].append((off, dfn))
        if not table:
            raise ValueError(f"{self.path}: no usable player ratings")
        self.cut = RatingsCut(str(cut)[:10], table, _repl_levels(fringe, data.get("replacement_level")),
                              f"latest:{self.path.name}")

    def for_kickoff(self, kick: datetime) -> Optional[RatingsCut]:
        return self.cut if self.cut.cutoff_dt < kick else None


class RatingsProvider:
    """Latest export first (when its cutoff is before kick-off), else the as-of file."""

    def __init__(self, latest_paths: Sequence[Path] = DEFAULT_LATEST_RATINGS,
                 asof_path: Optional[Path] = DEFAULT_ASOF_RATINGS, asof_meta: Optional[Path] = DEFAULT_ASOF_META,
                 asof_preload: bool = False):
        self.latest: Optional[LatestRatings] = None
        self.latest_error: Optional[str] = None
        for p in latest_paths or ():
            if p and Path(p).exists():
                try:
                    self.latest = LatestRatings(Path(p))
                    break
                except (OSError, ValueError, TypeError, KeyError) as e:
                    self.latest_error = f"{p}: {e}"
                    logger.error("player_impact_latest unreadable (%s); falling back to the as-of file", e)
        self.asof: Optional[AsofRatings] = None
        if asof_path is not None and Path(asof_path).exists():
            self.asof = AsofRatings(Path(asof_path), Path(asof_meta) if asof_meta else None, preload=asof_preload)

    def for_kickoff(self, kick: datetime) -> Optional[RatingsCut]:
        if self.latest is not None:
            rc = self.latest.for_kickoff(kick)
            if rc is not None:
                return rc
        return self.asof.for_kickoff(kick) if self.asof is not None else None


_ratings_cache: Dict[Tuple, RatingsProvider] = {}
_ratings_lock = threading.Lock()


def get_ratings_provider(latest_paths: Sequence[Path], asof_path: Optional[Path],
                         asof_meta: Optional[Path]) -> RatingsProvider:
    paths = tuple(Path(p) for p in latest_paths or ()) + tuple(Path(p) for p in (asof_path, asof_meta) if p)
    sig = _files_signature(paths)
    with _ratings_lock:
        hit = _ratings_cache.get(sig)
        if hit is None:
            hit = RatingsProvider(latest_paths, asof_path, asof_meta)
            _ratings_cache.clear()
            _ratings_cache[sig] = hit
        return hit


# ============================================================================ positions snapshot
_snapshot_cache: Dict[Tuple, Tuple[Optional[datetime], Dict[str, str]]] = {}


def load_squad_snapshot_positions(path: Path = DEFAULT_SQUAD_SNAPSHOT) -> Tuple[Optional[datetime], Dict[str, str]]:
    """(snapshot time, player id -> GK/DEF/MID/FWD) from the as-of-today squad lists. Only used for
    kick-offs after the snapshot (never for past matches: README_players.md)."""
    sig = _files_signature([Path(path)])
    hit = _snapshot_cache.get(sig)
    if hit is not None:
        return hit
    out: Dict[str, str] = {}
    snap: Optional[datetime] = None
    try:
        with open(path, "rb") as f:
            for raw in f:
                try:
                    r = json.loads(raw)
                except ValueError:
                    continue
                pid = r.get("player_id")
                pos = POSITION_ID.get(r.get("position_id"))
                if pid is not None and pos:
                    out.setdefault(str(pid), pos)
                if r.get("snapshot_at"):
                    try:
                        t = to_naive_utc(r["snapshot_at"])
                        snap = t if snap is None or t > snap else snap
                    except ValueError:
                        pass
    except OSError:
        pass
    _snapshot_cache.clear()
    _snapshot_cache[sig] = (snap, out)
    return snap, out


# ============================================================================ SQL source (production DB)
# one result row: (kickoff, match_id, comp_id, comp_name, home_team, away_team, home_score, away_score,
#                  home_xg, away_xg, status)
ResultRow = Tuple[datetime, str, str, str, str, str, Optional[int], Optional[int], Optional[float], Optional[float], str]

_TEAM_ROWS_SQL = """
SELECT m.provider_id, m.scheduled_at, c.provider_id, c.name, th.provider_id, ta.provider_id,
       m.home_score, m.away_score, m.home_xg, m.away_xg, m.status
FROM matches m
JOIN teams th ON th.id = m.home_team_id
JOIN teams ta ON ta.id = m.away_team_id
LEFT JOIN competitions c ON c.id = m.competition_id
WHERE (m.home_team_id IN ({ids}) OR m.away_team_id IN ({ids}))
  AND m.scheduled_at >= :start AND m.scheduled_at < :end
ORDER BY m.scheduled_at {order}
LIMIT :lim
"""
_HADV_SQL = """
SELECT c.provider_id, c.name, COUNT(*), SUM(m.home_score), SUM(m.away_score)
FROM matches m LEFT JOIN competitions c ON c.id = m.competition_id
WHERE m.scheduled_at >= :start AND m.scheduled_at < :end AND m.status = 'FINISHED'
  AND m.home_score IS NOT NULL AND m.away_score IS NOT NULL
GROUP BY c.provider_id, c.name
"""


class SqlMatchSource:
    """Read-only queries against the production schema (matches / teams / competitions).

    ``execute(sql, params) -> list of tuples`` is either a SQLAlchemy session (``from_session``) or
    a sqlite3 connection (``from_sqlite``); the SQL is portable (named parameters, no dialect
    functions). Only finished matches with both scores count as results, as in
    build_match_features.read_results' production-DB branch.
    """

    def __init__(self, execute: Callable[[str, dict], List[tuple]], exclude_ids: Optional[set] = None):
        self._execute = execute
        self.exclude_ids = set(exclude_ids or ())
        self._team_uuid_cache: Dict[str, List[str]] = {}
        self._hadv_cache: Dict[Tuple[str, str], List[tuple]] = {}

    @classmethod
    def from_session(cls, session, exclude_ids: Optional[set] = None) -> "SqlMatchSource":
        from sqlalchemy import text

        def run(sql: str, params: dict) -> List[tuple]:
            return [tuple(r) for r in session.execute(text(sql), params).fetchall()]
        return cls(run, exclude_ids)

    @classmethod
    def from_sqlite(cls, con, exclude_ids: Optional[set] = None) -> "SqlMatchSource":
        def run(sql: str, params: dict) -> List[tuple]:
            return [tuple(r) for r in con.execute(sql, params).fetchall()]
        return cls(run, exclude_ids)

    def team_uuids(self, team_pid: str) -> List[str]:
        hit = self._team_uuid_cache.get(team_pid)
        if hit is None:
            hit = [r[0] for r in self._execute("SELECT id FROM teams WHERE provider_id = :pid", {"pid": str(team_pid)})]
            self._team_uuid_cache[team_pid] = hit
        return hit

    def competition_provider_id(self, competition_id: Optional[str]) -> Optional[str]:
        """FotMob id of a competition given its DB uuid or its provider id."""
        if not competition_id:
            return None
        rows = self._execute("SELECT provider_id FROM competitions WHERE id = :cid", {"cid": str(competition_id)})
        if rows:
            return str(rows[0][0])
        rows = self._execute("SELECT provider_id FROM competitions WHERE provider_id = :cid", {"cid": str(competition_id)})
        return str(rows[0][0]) if rows else None

    def team_provider_id(self, team_id: Optional[str]) -> Optional[str]:
        if not team_id:
            return None
        rows = self._execute("SELECT provider_id FROM teams WHERE id = :tid", {"tid": str(team_id)})
        return str(rows[0][0]) if rows else None

    def team_rows(self, team_pid: str, start: datetime, end: datetime, limit: int, newest_first: bool = True) -> List[ResultRow]:
        uuids = self.team_uuids(team_pid)
        if not uuids:
            return []
        params = {f"t{i}": u for i, u in enumerate(uuids)}
        params.update(start=_sql_dt(start), end=_sql_dt(end), lim=int(limit))
        sql = _TEAM_ROWS_SQL.format(ids=", ".join(f":t{i}" for i in range(len(uuids))),
                                    order="DESC" if newest_first else "ASC")
        out: List[ResultRow] = []
        for mid, at, cp, cname, h, a, hs, as_, hx, ax, status in self._execute(sql, params):
            if str(mid) in self.exclude_ids:
                continue
            out.append((to_naive_utc(at), str(mid), "" if cp is None else str(cp), cname or "", str(h), str(a),
                        hs, as_, None if hx is None else float(hx), None if ax is None else float(ax),
                        str(getattr(status, "value", status))))
        return out

    def has_any(self, team_pid: str) -> bool:
        return bool(self.team_uuids(team_pid)) and bool(
            self.team_rows(team_pid, datetime(1900, 1, 1), datetime(2999, 1, 1), 1))

    def hadv_rows(self, start: datetime, end: datetime) -> List[tuple]:
        key = (_sql_dt(start), _sql_dt(end))
        hit = self._hadv_cache.get(key)
        if hit is None:
            hit = self._execute(_HADV_SQL, {"start": key[0], "end": key[1]})
            if self.exclude_ids:
                # subtract excluded matches inside the window (they are few)
                ex = self._execute(
                    "SELECT m.provider_id, c.provider_id, c.name, m.home_score, m.away_score FROM matches m "
                    "LEFT JOIN competitions c ON c.id = m.competition_id WHERE m.scheduled_at >= :start "
                    "AND m.scheduled_at < :end AND m.status = 'FINISHED' AND m.home_score IS NOT NULL "
                    "AND m.away_score IS NOT NULL", {"start": key[0], "end": key[1]}) if len(self.exclude_ids) else []
                sub: Dict[Tuple, List[int]] = defaultdict(lambda: [0, 0, 0])
                for mid, cp, cname, hs, as_ in ex:
                    if str(mid) in self.exclude_ids:
                        s = sub[(cp, cname)]
                        s[0] += 1
                        s[1] += hs
                        s[2] += as_
                hit = [(cp, cname, n - sub[(cp, cname)][0], (hg or 0) - sub[(cp, cname)][1],
                        (ag or 0) - sub[(cp, cname)][2]) for cp, cname, n, hg, ag in hit]
            if len(self._hadv_cache) > 64:
                self._hadv_cache.clear()
            self._hadv_cache[key] = hit
        return hit


# ============================================================================ result containers
@dataclass
class SquadSide:
    """The line-up facts the features need for one side (from TeamSquadInfo or a details record)."""

    team_id: Optional[str]
    starter_ids: List[str]
    starter_value: Optional[float]
    lineup_type: Optional[str] = None
    unavailable: Optional[list] = None          # None = no usable pre-match list
    positions: Dict[str, str] = field(default_factory=dict)   # optional, player id -> GK/DEF/MID/FWD


def squad_sides_from_info(info) -> Optional[Tuple[SquadSide, SquadSide]]:
    """(home, away) SquadSide from app.prediction.squad_value's (TeamSquadInfo, TeamSquadInfo)."""
    if not info:
        return None
    out = []
    for t in info:
        out.append(SquadSide(team_id=t.team_id, starter_ids=list(t.starter_ids or []), starter_value=t.starter_value,
                             lineup_type=t.lineup_type, unavailable=t.unavailable))
    return out[0], out[1]


@dataclass
class RuntimeFeatures:
    """One match's feature row under the training CSV's column names, with provenance."""

    values: Dict[str, Any]
    match_id: Optional[str]
    kickoff: datetime
    home_team_id: Optional[str]
    away_team_id: Optional[str]
    competition_id: Optional[str]
    ratings_cutoff: Optional[str] = None
    ratings_source: Optional[str] = None
    lineup_type: Optional[str] = None
    groups_computed: Tuple[str, ...] = ()
    notes: Dict[str, Any] = field(default_factory=dict)

    def get(self, column: str) -> Any:
        return self.values.get(column)


@dataclass
class RuntimeSources:
    """Everything the feature computation reads (all optional; a missing source -> None features)."""

    history: Optional[LineupHistory] = None
    db: Optional[SqlMatchSource] = None
    ratings: Optional[RatingsProvider] = None
    schedule: Optional[Callable[[str, datetime, datetime], List[Tuple[datetime, str, str]]]] = None
    snapshot_positions: Optional[Tuple[Optional[datetime], Dict[str, str]]] = None
    extend_history_from_db: bool = True


# ============================================================================ feature computation
def _xi_strength(rc: RatingsCut, ids: Sequence[str], pos: Dict[str, str]) -> Tuple[Optional[float], Optional[float], int]:
    off = dfn = 0.0
    unknown = 0
    for pid in ids:
        v = rc.table.get(pid)
        if v is None:
            unknown += 1
            r = rc.repl.get(pos.get(pid, "UNK")) or rc.repl.get("UNK")
            if r is None:
                return None, None, unknown
            off += r[0]
            dfn += r[1]
        else:
            off += v[0]
            dfn += v[1]
    return off, dfn, unknown


def _side_xi(rc: Optional[RatingsCut], ids: List[str], pos: Dict[str, str], prev: List[HistEntry]) -> Dict[str, Any]:
    keys = ("xi_n", "xi_off", "xi_def", "xi_unrated", "usual_n", "usual_off", "usual_def", "xi_d_off", "xi_d_def")
    out: Dict[str, Any] = dict.fromkeys(keys)
    out["xi_n"] = len(ids)
    if rc is None or len(ids) != 11:
        return out
    off, dfn, unk = _xi_strength(rc, ids, pos)
    if off is None:
        return out
    out.update(xi_off=off, xi_def=dfn, xi_unrated=unk)
    lineups = [t for t in prev if t[3]][:USUAL_N]
    out["usual_n"] = len(lineups)
    if len(lineups) < MIN_USUAL:
        return out
    uo = ud = 0.0
    for t in lineups:
        o, d, _u = _xi_strength(rc, t[3], t[4])
        if o is None:
            return out
        uo += o / len(t[3]) * 11.0
        ud += d / len(t[3]) * 11.0
    uo /= len(lineups)
    ud /= len(lineups)
    out.update(usual_off=uo, usual_def=ud, xi_d_off=off - uo, xi_d_def=dfn - ud)
    return out


def _side_absent(listed: Optional[list]) -> Dict[str, Any]:
    out: Dict[str, Any] = dict.fromkeys(("unavail_listed", "n_injury", "n_suspension", "n_other", "unavail_n_rated",
                                         "unavail_off", "unavail_def", "unavail_off_w", "unavail_def_w",
                                         "unavail_value"))
    if listed is None:
        return out                       # no usable pre-match list: unknown, never 0
    out["unavail_listed"] = 1
    reasons = [getattr(u, "reason", None) if not isinstance(u, dict) else u.get("type") for u in listed]
    c = Counter((r or "other") for r in reasons)
    out["n_injury"] = c.get("injury", 0)
    out["n_suspension"] = c.get("suspension", 0)
    out["n_other"] = sum(v for k, v in c.items() if k not in ("injury", "suspension"))
    vals = [getattr(u, "market_value", None) if not isinstance(u, dict) else u.get("market_value") for u in listed]
    out["unavail_value"] = float(sum(v for v in vals if v is not None)) if all(v is not None for v in vals) else None
    return out


def _side_xg_form(prev: List[HistEntry]) -> Dict[str, Any]:
    out: Dict[str, Any] = dict.fromkeys(("l5_n", "l5_xg_n", "xg_for_l5", "xg_against_l5"))
    last = prev[:FORM_N]
    xg = [t[5] for t in last if t[5] is not None]
    out["l5_n"], out["l5_xg_n"] = len(last), len(xg)
    if len(xg) >= FORM_MIN:
        out["xg_for_l5"] = _mean([x[0] for x in xg])
        out["xg_against_l5"] = _mean([x[1] for x in xg])
    return out


# training TeamResults entry: (kickoff, match_id, opponent, euro, goals_for, goals_against, points)
def _team_results(db: SqlMatchSource, team: str, kick: datetime, match_id: Optional[str], opp: Optional[str],
                  limit: int = 60) -> List[tuple]:
    rows = db.team_rows(team, kick - timedelta(days=800), kick, limit)
    out = []
    for at, mid, cp, cname, h, a, hs, as_, _hx, _ax, status in rows:
        if status != "FINISHED" or hs is None or as_ is None or is_friendly(cname):
            continue
        if h == team:
            o, gf, ga = a, hs, as_
        elif a == team:
            o, gf, ga = h, as_, hs
        else:
            continue
        if mid == match_id or (o == opp and (kick - at).total_seconds() < DUPLICATE_FIXTURE_DAYS * 86400):
            continue
        pts = 3 if gf > ga else (1 if gf == ga else 0)
        out.append((at, mid, o, cp in EURO_ALL, gf, ga, pts))
    out.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return out


def _side_results(prev_results: List[tuple], kick: datetime, has_any: bool) -> Dict[str, Any]:
    out: Dict[str, Any] = dict.fromkeys(("res_l5_n", "ppg_l5", "gf_l5", "ga_l5", "rest_days", "n_matches_14d",
                                         "euro_before_3d"))
    res = prev_results[:FORM_N]
    out["res_l5_n"] = len(res)
    if len(res) >= FORM_MIN:
        out["ppg_l5"] = _mean([t[6] for t in res])
        out["gf_l5"] = _mean([t[4] for t in res])
        out["ga_l5"] = _mean([t[5] for t in res])
    if not has_any:
        out["rest_days"] = out["n_matches_14d"] = out["euro_before_3d"] = None
        return out
    if prev_results:
        out["rest_days"] = (kick - prev_results[0][0]).total_seconds() / 86400.0
    out["n_matches_14d"] = sum(1 for t in prev_results if (kick - t[0]).total_seconds() < CONGESTION_DAYS * 86400)
    out["euro_before_3d"] = int(any(t[3] and (kick.date() - t[0].date()).days <= EURO_WINDOW_DAYS
                                    for t in prev_results[:6]))
    return out


def _db_history_entries(db: SqlMatchSource, history: Optional[LineupHistory], team: str, kick: datetime,
                        comps: set) -> List[HistEntry]:
    """Production-DB matches of the team in the details competitions that the details files do not
    hold and that were played after the details files end for that competition: no line-up known,
    DB xG (the DB and details xG were identical on all 6,798 shared matches, 2026-10-14)."""
    if db is None:
        return []
    rows = db.team_rows(team, kick - timedelta(days=800), kick, 80)
    out: List[HistEntry] = []
    for at, mid, cp, _cname, h, a, hs, as_, hx, ax, status in rows:
        if status != "FINISHED" or hs is None or as_ is None or cp not in comps:
            continue
        if history is not None:
            if mid in history.match_ids or mid in history.awarded_ids:
                continue
            last = history.comp_last_kickoff.get(cp)
            if last is not None and at <= last:
                continue                    # inside the details coverage: the details files decide
        if h == team:
            opp, xf, xa = a, hx, ax
        elif a == team:
            opp, xf, xa = h, ax, hx
        else:
            continue
        xg = (float(xf), float(xa)) if xf is not None and xa is not None else None
        out.append((at, mid, opp, (), {}, xg, "db"))
    return out


def _hadv(db: SqlMatchSource, comp: Optional[str], kick: datetime) -> Dict[str, Any]:
    start = kick - timedelta(days=HADV_WINDOW_DAYS)
    n_g = hg_g = ag_g = 0
    n = hg = ag = 0
    for cp, cname, cnt, shg, sag in db.hadv_rows(start, kick):
        if is_friendly(cname or ""):
            continue
        n_g += cnt
        hg_g += shg or 0
        ag_g += sag or 0
        if comp is not None and ("" if cp is None else str(cp)) == comp:
            n += cnt
            hg += shg or 0
            ag += sag or 0
    if n_g == 0 or hg_g <= 0 or ag_g <= 0:
        return {"league_hadv": None, "global_hadv": None, "league_hadv_dev": None, "league_hadv_n": 0}
    g = math.log(hg_g / ag_g)
    if n == 0 or hg <= 0 or ag <= 0:
        return {"league_hadv": None, "global_hadv": g, "league_hadv_dev": None, "league_hadv_n": n}
    w = n / (n + HADV_SHRINK_MATCHES)
    lg = w * math.log(hg / ag) + (1 - w) * g
    return {"league_hadv": lg, "global_hadv": g, "league_hadv_dev": lg - g, "league_hadv_n": n}


def compute_runtime_features(*, kickoff: Any, home_team_id: Optional[str], away_team_id: Optional[str],
                             competition_id: Optional[str], squad: Optional[Tuple[SquadSide, SquadSide]],
                             sources: RuntimeSources, match_id: Optional[str] = None,
                             groups: Optional[Iterable[str]] = None) -> RuntimeFeatures:
    """The training feature columns for one fixture, from the runtime sources.

    ``home_team_id`` / ``away_team_id`` / ``competition_id`` are FotMob ids; ``match_id`` the FotMob
    match id (excluded from every history window). Only the requested ``groups`` (see
    COLUMN_GROUP; default: all) are computed - the others stay None and are listed in
    ``groups_computed``. Data strictly before kick-off only.
    """
    kick = to_naive_utc(kickoff)
    groups = set(ALL_GROUPS if groups is None else groups)
    th = None if home_team_id is None else str(home_team_id)
    ta = None if away_team_id is None else str(away_team_id)
    comp = None if competition_id is None else str(competition_id)
    mid = None if match_id is None else str(match_id)
    vals: Dict[str, Any] = {f"{s}_{k}": None for s in SIDES for k in SIDE_KEYS}
    vals.update(dict.fromkeys(MATCH_KEYS))
    notes: Dict[str, Any] = {}
    feats = RuntimeFeatures(vals, mid, kick, th, ta, comp, groups_computed=tuple(sorted(groups)), notes=notes)

    # ---------------------------------------------------------------- match level
    if comp is not None:
        ctype = "european" if comp in EURO_MAIN else competition_type(comp, None)
        vals["comp_is_euro"] = int(ctype == "european")
    else:
        notes["competition_unknown"] = True
    if squad is not None:
        hs, as_ = squad
        feats.lineup_type = hs.lineup_type or as_.lineup_type
        vh, va = hs.starter_value, as_.starter_value
        vals["home_starters_value"] = float(vh) if vh else None
        vals["away_starters_value"] = float(va) if va else None
        vals["value_log_ratio"] = math.log(vh / va) if vh and va and vh > 0 and va > 0 else None
    else:
        notes["no_lineup"] = True

    # ---------------------------------------------------------------- ratings cut
    rc: Optional[RatingsCut] = None
    if "xi" in groups:
        if sources.ratings is not None:
            rc = sources.ratings.for_kickoff(kick)
        if rc is None:
            notes["ratings_unavailable"] = True
        else:
            feats.ratings_cutoff, feats.ratings_source = rc.cutoff, rc.source

    hist = sources.history
    need_hist = bool({"xi", "xg_form"} & groups)
    comps = set(hist.competitions) if hist is not None else set()
    snap_time, snap_pos = sources.snapshot_positions or (None, {})

    for side, team, opp in (("home", th, ta), ("away", ta, th)):
        sq = None if squad is None else (squad[0] if side == "home" else squad[1])
        prev: List[HistEntry] = []
        if need_hist and team is not None:
            extra = (_db_history_entries(sources.db, hist, team, kick, comps)
                     if sources.extend_history_from_db and sources.db is not None and comps else [])
            if extra:
                notes[f"{side}_db_only_history_entries"] = sum(1 for e in extra if e[0] < kick)
            if hist is not None or extra:
                prev = (hist or LineupHistory()).before(team, kick, mid or "", opp or "", max(USUAL_N, FORM_N), extra)
            in_window = [t for t in prev[:USUAL_N] if t[6] == "db"]
            if in_window:
                notes[f"{side}_usual_window_without_lineup"] = len(in_window)
        if "xi" in groups and sq is not None:
            ids = [str(p) for p in sq.starter_ids]
            pos: Dict[str, str] = {}
            src = Counter()
            for pid in ids:
                if rc is not None and pid in rc.table:
                    continue                         # rated: position not needed
                p = sq.positions.get(pid)
                if p:
                    src["lineup"] += 1
                else:
                    p = hist.position_before(pid, kick) if hist is not None else None
                    if p:
                        src["details_history"] += 1
                    elif snap_time is not None and kick >= snap_time and pid in snap_pos:
                        p = snap_pos[pid]
                        src["squad_snapshot"] += 1
                    else:
                        src["unknown"] += 1
                if p:
                    pos[pid] = p
            if src:
                notes[f"{side}_unrated_position_source"] = dict(src)
            for k, v in _side_xi(rc, ids, pos, prev).items():
                vals[f"{side}_{k}"] = v
        elif "xi" in groups:
            vals[f"{side}_xi_n"] = None
        if "absent" in groups and sq is not None:
            for k, v in _side_absent(sq.unavailable).items():
                vals[f"{side}_{k}"] = v
        if "xg_form" in groups:
            for k, v in _side_xg_form(prev).items():
                vals[f"{side}_{k}"] = v
        if ("results" in groups) and sources.db is not None and team is not None:
            pr = _team_results(sources.db, team, kick, mid, opp)
            has_any = bool(pr) or sources.db.has_any(team)
            for k, v in _side_results(pr, kick, has_any).items():
                vals[f"{side}_{k}"] = v
        if "schedule" in groups and team is not None:
            if sources.schedule is None:
                notes["euro_after_unknown_no_schedule"] = True
            else:
                fx = sources.schedule(team, kick, kick + timedelta(days=EURO_WINDOW_DAYS + 1))
                vals[f"{side}_euro_after_3d"] = int(any(
                    f_comp in EURO_ALL and f_mid != mid and f_at > kick
                    and (f_at.date() - kick.date()).days <= EURO_WINDOW_DAYS for f_at, f_mid, f_comp in fx))
    if "hadv" in groups and sources.db is not None:
        vals.update(_hadv(sources.db, comp, kick))
    return feats


def db_schedule(db: SqlMatchSource) -> Callable[[str, datetime, datetime], List[Tuple[datetime, str, str]]]:
    """Fixture schedule from the DB rows of a team (any status). The production DB holds finished
    matches only, so this is only a schedule for historical checks (parity), not for live use."""
    def fixtures(team: str, start: datetime, end: datetime) -> List[Tuple[datetime, str, str]]:
        rows = db.team_rows(team, start, end, 20, newest_first=False)
        return [(at, mid, cp) for at, mid, cp, *_rest in rows]
    return fixtures


def load_result_exclusions(all_results_db: Optional[Path], awarded: bool,
                           conflict_kinds: Sequence[str]) -> set:
    """Match ids to drop from the results (training flags --results-exclude-awarded /
    --results-exclude-conflicts), read from data/history/all_results.db (read-only)."""
    if all_results_db is None or not Path(all_results_db).exists() or (not awarded and not conflict_kinds):
        return set()
    import sqlite3
    con = sqlite3.connect(f"file:{Path(all_results_db).as_posix()}?mode=ro", uri=True)
    try:
        out = set()
        if awarded:
            out |= {str(r[0]) for r in con.execute("select match_provider_id from results where awarded = 1")}
        kinds = [k for k in conflict_kinds if k]
        if kinds:
            out |= {str(r[0]) for r in con.execute(
                f"select match_provider_id from conflicts where kind in ({','.join('?' * len(kinds))}) "
                "and match_provider_id is not null", kinds)}
        return out
    finally:
        con.close()
