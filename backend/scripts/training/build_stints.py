"""Build on-pitch segments ("stints") from raw FotMob matchDetails responses.

Stage A, step 1 of the player-impact pipeline (docs/training/player-impact-pipeline.md).

A stint is a stretch of play during which neither line-up changes. Boundaries are
kick-off, substitutions and red cards (straight red or second yellow); half-time is
NOT a boundary. For every stint the output row carries the players on the pitch on
both sides, the man-advantage state, and the home/away xG, non-penalty xG, shots and
goals that happened inside it, plus the elapsed duration in minutes.

Match list: taken ONLY from the JSONL files given with --details (fotmob_match_details
schema; the history file adds "season"). The raw directory is never listed, because
collectors add files to it concurrently. Unreadable or partial gzip files are skipped
and counted, and so are JSONL lines that do not parse (e.g. a partial last line).

Raw field paths (relative to the response root):
  line-ups      content.lineup.{homeTeam|awayTeam}.{id, starters[*].id, subs[*].id}
  events        content.matchFacts.events.events[*]
                  Substitution: time, overloadTime, isHome, swap[0] = player ON, swap[1] = player OFF
                                (verified on 61,505 events against the line-up subIn/subOut flags),
                                homeScore/awayScore = score when the change happened
                  Card:         card in {"Red", "YellowRed"} removes playerId from the pitch
                                (cards overturned by VAR are absent from the list)
                  Goal:         isHome = benefiting side (also for own goals), ownGoal,
                                newScore = score after the goal, shotmapEvent.id = shot id,
                                goalDescriptionKey == "penalty", isPenaltyShootoutEvent
                  AddedTime:    minutesAddedInput (announced stoppage) at time 45/90/105/120
  shots         content.shotmap.shots[*]: teamId (for own goals: the team of the player who
                put it in his own net), period (FirstHalf/SecondHalf/FirstHalfExtra/
                SecondHalfExtra/PenaltyShootout), min, minAdded, expectedGoals, situation
                ("Penalty"), isOwnGoal
  half clocks   header.status.halfs.{firstHalfStarted, firstHalfEnded, secondHalfStarted,
                secondHalfEnded, firstExtraHalfStarted, secondExtraHalfStarted}
  team xG       content.stats.Periods.All.stats[*].stats[*] with key "expected_goals" /
                "expected_goals_non_penalty" (strings, [home, away])
  score         header.teams[0|1].score
  red cards     header.status.numberOfHomeRedCards / numberOfAwayRedCards (cross-check)

Clock (minutes of play from kick-off, stoppage time included, the breaks excluded):
  * each half h has a length L_h = regulation (45, or 15 in extra time) + stoppage. The
    stoppage comes from the half's start/end timestamps when they are plausible
    (regulation - 3 <= length <= regulation + 25), else from the announced added time,
    else from the latest stoppage minute seen in events/shots, else 0; it is then raised,
    if needed, to the latest stoppage minute seen in that half (an event at 90+7 needs at
    least 7 minutes of stoppage). The source is recorded per match.
  * a FotMob minute label "m" or "m+k" (k = overloadTime / minAdded) of half h covers the
    interval [r-1, r) with r = (m - first minute of the half) + k, e.g. 46' is the first
    minute of the second half and 90+4 the fourth minute of second-half stoppage.
  * line-up changes are placed at the START of their minute (r - 1): half-time
    substitutions, which FotMob labels 46', then fall exactly on the break.
  * shots and goals are placed in the MIDDLE of their minute (r - 0.5), so a non-goal shot
    in the same minute as a change counts after the change (not resolvable without
    seconds; counted in the validation as same_minute_shots / same_minute_xg).
  * a goal in the same minute as a change is ordered with the score the change event
    carries: if that score already includes the goal, the goal (and its shot) is moved
    before the change.
  * positions are clamped to [0, L_h] inside their half; the elapsed position of half h is
    the sum of the lengths of the earlier halves plus the position inside h.

Own goals count as goals for the benefiting side and are never xG (their shotmap rows
carry 0 or null xG). Penalty-shootout shots and goals are excluded. Matches without a
shotmap (e.g. Czech 1. Liga) get xG = null in every stint (unknown, never 0).

Per-match validation (data/training/stints_validation.csv, summary in --report):
  lineup_ok   11 starters per side, every substitution takes off a player who is on the
              pitch and brings on one who is not, red cards found == header red-card counts
              (a red card for a bench player / coach / substituted player is no line-up change)
  goals_ok    goals summed over stints == header score (shoot-out excluded)
  xg_check    pass if |sum of stint xG - team xG (content.stats)| <= 0.05 for both sides;
              "n/a" when the match has neither team xG nor a shotmap; otherwise the failure is
              classified with FotMob's per-player stat xG (content.playerStats):
              fail_team_stat_differs (shots = player stats != team stat),
              fail_shot_values_differ (player stats = team stat != shots), fail_unexplained,
              fail_no_shotmap. Stint xG always equals the shotmap total.
  minutes_ok  every player's on-pitch minutes from the stints, counted on FotMob's nominal
              clock (stoppage collapsed, a change at minute m counts as m), are within 1
              minute of FotMob's minutes_played (minutes_consistent: within 3)
  length_ok   90 <= match length <= 125 (120 <= length <= 160 with extra time)
  usable      lineup_ok and goals_ok and minutes_consistent: the stints that the player model uses

Usage (from backend/):
  venv/Scripts/python.exe scripts/training/build_stints.py \
      --details data/training/fotmob_match_details.jsonl \
      [--details data/training/fotmob_match_details_history.jsonl] \
      --out data/training/stints.jsonl.gz
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import os
import sys
import time
import zlib
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DETAILS = BACKEND_DIR / "data" / "training" / "fotmob_match_details.jsonl"
DEFAULT_RAW_DIR = BACKEND_DIR / "data" / "raw_cache" / "fotmob_match_details"
DEFAULT_OUT = BACKEND_DIR / "data" / "training" / "stints.jsonl.gz"
DEFAULT_VALIDATION = BACKEND_DIR / "data" / "training" / "stints_validation.csv"
DEFAULT_REPORT = BACKEND_DIR / "data" / "training" / "stints_report.json"

XG_TOLERANCE = 0.05
MINUTES_TOLERANCE = 1          # strict check (reported)
MINUTES_USABLE_TOLERANCE = 3   # larger gaps = FotMob sources disagree on who played: match not usable
HALF_ORDER = ("H1", "H2", "ET1", "ET2")
HALF_FIRST_MINUTE = {"H1": 0, "H2": 45, "ET1": 90, "ET2": 105}
HALF_LAST_MINUTE = {"H1": 45, "H2": 90, "ET1": 105, "ET2": 120}
HALF_REGULATION = {"H1": 45.0, "H2": 45.0, "ET1": 15.0, "ET2": 15.0}
ADDED_TIME_AT = {45: "H1", 90: "H2", 105: "ET1", 120: "ET2"}
SHOT_PERIOD = {"FirstHalf": "H1", "SecondHalf": "H2", "FirstHalfExtra": "ET1", "SecondHalfExtra": "ET2"}
RED_CARDS = {"Red", "YellowRed"}
TIMESTAMP_FORMAT = "%d.%m.%Y %H:%M:%S"
EPS = 1e-6

VALIDATION_FIELDS = [
    "match_id", "kickoff", "competition_id", "season", "n_segments", "extra_time", "match_length",
    "h1_length", "h2_length", "et1_length", "et2_length", "h1_length_source", "h2_length_source",
    "starters_home", "starters_away", "subs_home", "subs_away", "reds_home", "reds_away",
    "header_reds_home", "header_reds_away", "red_cards_ignored", "lineup_ok", "lineup_issues",
    "score_home", "score_away", "segment_goals_home", "segment_goals_away", "goals_ok",
    "xg_available", "team_xg_home", "team_xg_away", "stats_player_xg_home", "stats_player_xg_away",
    "segment_xg_home", "segment_xg_away",
    "xg_diff_home", "xg_diff_away", "team_npxg_home", "team_npxg_away", "segment_npxg_home",
    "segment_npxg_away", "xg_check", "minutes_players_checked", "minutes_max_abs_diff",
    "minutes_players_off", "minutes_ok", "minutes_consistent", "length_ok", "same_minute_shots",
    "same_minute_xg", "goals_moved_before_change", "goals_mixed_order", "own_goals",
    "shootout_shots_skipped", "usable", "passed", "fail_reasons",
]


# --------------------------------------------------------------------------- helpers

def _to_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _timestamp(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, TIMESTAMP_FORMAT)
    except ValueError:
        return None


def event_half(minute: int) -> str:
    """Half of a matchFacts event from its minute (45+k is first-half stoppage)."""
    if minute <= 45:
        return "H1"
    if minute <= 90:
        return "H2"
    if minute <= 105:
        return "ET1"
    return "ET2"


def minute_label(minute: Optional[int], overload: Optional[int]) -> str:
    if minute is None:
        return "?"
    return f"{minute}+{overload}" if overload else str(minute)


def team_stat_pair(content: dict, key: str) -> tuple[Optional[float], Optional[float]]:
    """[home, away] of the first full-match team stat with this key (strings parsed)."""
    periods = ((content.get("stats") or {}).get("Periods") or {})
    for group in (periods.get("All") or {}).get("stats") or []:
        for row in group.get("stats") or []:
            if row.get("key") == key:
                vals = row.get("stats") or [None, None]
                if len(vals) >= 2:
                    return _to_float(vals[0]), _to_float(vals[1])
    return None, None


def player_stats_xg(content: dict, team_ids: dict) -> dict[str, Optional[float]]:
    """Sum per side of content.playerStats[*] 'expected_goals' (FotMob omits it for players without a shot)."""
    sums: dict[str, Optional[float]] = {"home": None, "away": None}
    for entry in (content.get("playerStats") or {}).values():
        if not isinstance(entry, dict):
            continue
        team = _to_int(entry.get("teamId"))
        side = "home" if team == team_ids["home"] else "away" if team == team_ids["away"] else None
        if side is None:
            continue
        for block in entry.get("stats") or []:
            for sv in (block.get("stats") or {}).values():
                if isinstance(sv, dict) and sv.get("key") == "expected_goals":
                    val = _to_float((sv.get("stat") or {}).get("value"))
                    if val is not None:
                        sums[side] = (sums[side] or 0.0) + val
                    break
    return sums


# --------------------------------------------------------------------------- clock

def half_lengths(status: dict, events: list, shots: list, extra_time: bool) -> tuple[dict, dict]:
    """Length (minutes, stoppage included) of every half played, and where it came from."""
    halves = HALF_ORDER if extra_time else HALF_ORDER[:2]
    observed = {h: 0 for h in HALF_ORDER}
    for e in events:
        if e.get("type") == "PenaltyShootout" or e.get("isPenaltyShootoutEvent"):
            continue
        t, ov = _to_int(e.get("time")), _to_int(e.get("overloadTime")) or 0
        if t is not None and ov > 0:
            h = event_half(t)
            observed[h] = max(observed[h], ov)
    for s in shots:
        h = SHOT_PERIOD.get(s.get("period"))
        ov = _to_int(s.get("minAdded")) or 0
        if h and ov > 0:
            observed[h] = max(observed[h], ov)
    announced: dict[str, float] = {}
    for e in events:
        if e.get("type") == "AddedTime":
            h = ADDED_TIME_AT.get(_to_int(e.get("time")))
            val = _to_float(e.get("minutesAddedInput"))
            if h and val is not None and val >= 0 and h not in announced:
                announced[h] = val
    halfs = status.get("halfs") or {}
    stamps = {}
    for h, (a, b) in (("H1", ("firstHalfStarted", "firstHalfEnded")),
                      ("H2", ("secondHalfStarted", "secondHalfEnded"))):
        ta, tb = _timestamp(halfs.get(a)), _timestamp(halfs.get(b))
        if ta and tb:
            stamps[h] = (tb - ta).total_seconds() / 60.0
    lengths, sources = {}, {}
    for h in halves:
        reg = HALF_REGULATION[h]
        t = stamps.get(h)
        if t is not None and reg - 3 <= t <= reg + 25:
            stoppage, src = max(0.0, t - reg), "timestamps"
        elif h in announced:
            stoppage, src = announced[h], "announced"
        elif observed[h] > 0:
            stoppage, src = float(observed[h]), "observed"
        else:
            stoppage, src = 0.0, "none"
        if observed[h] > stoppage:
            stoppage = float(observed[h])
            src += "+raised_to_observed"
        lengths[h] = reg + stoppage
        sources[h] = src
    return lengths, sources


class Clock:
    """Maps FotMob minute labels to elapsed minutes of play."""

    def __init__(self, lengths: dict):
        self.lengths = lengths
        self.offsets = {}
        acc = 0.0
        for h in HALF_ORDER:
            if h in lengths:
                self.offsets[h] = acc
                acc += lengths[h]
        self.total = acc

    def position(self, half: str, minute: int, overload: int, shift: float) -> float:
        """Elapsed minutes at (end of minute label) + shift, clamped into the half."""
        if half not in self.lengths:  # event in a half that was not detected as played
            half = [h for h in HALF_ORDER if h in self.lengths][-1]
        rel = (minute - HALF_FIRST_MINUTE[half]) + overload + shift
        rel = min(max(rel, 0.0), self.lengths[half])
        return self.offsets[half] + rel

    def halves_between(self, start: float, end: float) -> list[str]:
        out = []
        for h, off in self.offsets.items():
            if start < off + self.lengths[h] - EPS and end > off + EPS:
                out.append(h)
        return out


# --------------------------------------------------------------------------- one match

def build_match(raw: dict, meta: dict) -> tuple[list[dict], dict]:
    """Stints and the validation row for one match. Never raises on odd data: issues are flagged."""
    content = raw.get("content") or {}
    header = raw.get("header") or {}
    status = header.get("status") or {}
    general = raw.get("general") or {}
    events = ((content.get("matchFacts") or {}).get("events") or {}).get("events") or []
    shotmap = content.get("shotmap") or {}
    shots_raw = shotmap.get("shots") if isinstance(shotmap.get("shots"), list) else None
    shots = shots_raw or []
    lineup = content.get("lineup") or {}
    match_id = str(meta["match_id"])
    issues: list[str] = []

    val: dict[str, Any] = {k: None for k in VALIDATION_FIELDS}
    val.update({"match_id": match_id, "kickoff": meta.get("kickoff"), "competition_id": meta.get("competition_id"),
                "season": meta.get("season")})

    teams = {"home": lineup.get("homeTeam") or {}, "away": lineup.get("awayTeam") or {}}
    team_ids = {"home": _to_int((general.get("homeTeam") or {}).get("id")),
                "away": _to_int((general.get("awayTeam") or {}).get("id"))}
    for side in ("home", "away"):
        if team_ids[side] is None:
            team_ids[side] = _to_int(teams[side].get("id"))
    if meta.get("home_team_id") is not None and team_ids["home"] != meta.get("home_team_id"):
        issues.append("home_team_id_mismatch_with_jsonl")
    if meta.get("away_team_id") is not None and team_ids["away"] != meta.get("away_team_id"):
        issues.append("away_team_id_mismatch_with_jsonl")

    starters = {s: [_to_int(p.get("id")) for p in (teams[s].get("starters") or []) if _to_int(p.get("id")) is not None]
                for s in ("home", "away")}
    bench = {s: {_to_int(p.get("id")) for p in (teams[s].get("subs") or []) if _to_int(p.get("id")) is not None}
             for s in ("home", "away")}
    val["starters_home"], val["starters_away"] = len(starters["home"]), len(starters["away"])
    if not starters["home"] or not starters["away"]:
        val.update({"lineup_ok": False, "lineup_issues": "no_lineup", "passed": False, "fail_reasons": "no_lineup"})
        return [], val
    for s in ("home", "away"):
        if len(starters[s]) != 11:
            issues.append(f"{s}_starters_{len(starters[s])}")
        if len(set(starters[s])) != len(starters[s]):
            issues.append(f"{s}_duplicate_starter")

    extra_time = bool((status.get("halfs") or {}).get("firstExtraHalfStarted"))
    for s in shots:
        if s.get("period") in ("FirstHalfExtra", "SecondHalfExtra"):
            extra_time = True
    for e in events:
        if e.get("type") in ("PenaltyShootout", "AddedTime", "Half") or e.get("isPenaltyShootoutEvent"):
            if e.get("type") == "Half" and _to_int(e.get("time")) == 120:
                extra_time = True
            continue
        t = _to_int(e.get("time"))
        if t is not None and t > 90:
            extra_time = True
    lengths, sources = half_lengths(status, events, shots, extra_time)
    clock = Clock(lengths)
    val.update({
        "extra_time": extra_time, "match_length": round(clock.total, 3),
        "h1_length": round(lengths["H1"], 3), "h2_length": round(lengths["H2"], 3),
        "et1_length": round(lengths["ET1"], 3) if "ET1" in lengths else None,
        "et2_length": round(lengths["ET2"], 3) if "ET2" in lengths else None,
        "h1_length_source": sources["H1"], "h2_length_source": sources["H2"],
    })
    end_minute = 120 if extra_time else 90

    # ---- line-up changes (substitutions, red cards)
    changes = []
    for idx, e in enumerate(events):
        typ = e.get("type")
        t = _to_int(e.get("time"))
        ov = _to_int(e.get("overloadTime")) or 0
        if t is None or e.get("isPenaltyShootoutEvent"):
            continue
        side = "home" if e.get("isHome") else "away"
        score = (_to_int(e.get("homeScore")), _to_int(e.get("awayScore")))
        if typ == "Substitution":
            swap = e.get("swap") or []
            if len(swap) != 2:
                issues.append("substitution_without_pair")
                continue
            changes.append({"kind": "substitution", "idx": idx, "side": side, "minute": t, "ov": ov,
                            "in": _to_int(swap[0].get("id")), "out": _to_int(swap[1].get("id")), "score": score})
        elif typ == "Card" and e.get("card") in RED_CARDS:
            pid = _to_int(e.get("playerId"))
            if pid is None:
                pid = _to_int((e.get("player") or {}).get("id"))
            changes.append({"kind": "red_card", "idx": idx, "side": side, "minute": t, "ov": ov,
                            "player": pid, "score": score})
    for c in changes:
        c["pos"] = clock.position(event_half(c["minute"]), c["minute"], c["ov"], -1.0)
        c["nominal"] = float(min(c["minute"], HALF_LAST_MINUTE[event_half(c["minute"])]))
    changes.sort(key=lambda c: (c["pos"], c["idx"]))

    # ---- goals (non shoot-out), positioned and ordered against same-minute changes
    goals = []
    moved = mixed = own_goals = 0
    for idx, e in enumerate(events):
        if e.get("type") != "Goal" or e.get("isPenaltyShootoutEvent"):
            continue
        t = _to_int(e.get("time"))
        if t is None:
            issues.append("goal_without_minute")
            continue
        ov = _to_int(e.get("overloadTime")) or 0
        pos = clock.position(event_half(t), t, ov, -0.5)
        new = e.get("newScore") or [None, None]
        same = [c for c in changes if c["minute"] == t and c["ov"] == ov]
        if same and None not in new:
            before = [c for c in same if None not in c["score"]
                      and c["score"][0] >= new[0] and c["score"][1] >= new[1]]
            if before and len(before) == len(same):
                pos = min(c["pos"] for c in same) - EPS
                moved += 1
            elif before:
                mixed += 1
        own = bool(e.get("ownGoal"))
        own_goals += own
        goals.append({"pos": pos, "side": "home" if e.get("isHome") else "away", "own_goal": own,
                      "penalty": e.get("goalDescriptionKey") == "penalty",
                      "shot_id": _to_int((e.get("shotmapEvent") or {}).get("id")), "minute": t, "ov": ov})
    goal_pos_by_shot = {g["shot_id"]: g["pos"] for g in goals if g["shot_id"] is not None}

    # ---- shots (xG); own goals and shoot-out kicks excluded
    xg_available = shots_raw is not None and len(shots_raw) > 0
    shot_rows = []
    shootout_skipped = 0
    change_minutes = {(c["minute"], c["ov"]) for c in changes}
    same_minute_shots, same_minute_xg = 0, 0.0
    for s in shots:
        period = s.get("period")
        if period == "PenaltyShootout":
            shootout_skipped += 1
            continue
        if s.get("isOwnGoal"):
            continue
        half = SHOT_PERIOD.get(period)
        team = _to_int(s.get("teamId"))
        side = "home" if team == team_ids["home"] else "away" if team == team_ids["away"] else None
        if half is None or side is None:
            issues.append("shot_unknown_period_or_team")
            continue
        minute = _to_int(s.get("min")) or 0
        ov = _to_int(s.get("minAdded")) or 0
        sid = _to_int(s.get("id"))
        pos = goal_pos_by_shot.get(sid)
        if pos is None:
            pos = clock.position(half, minute, ov, -0.5)
            label_minute = minute
            if (label_minute, ov) in change_minutes:
                same_minute_shots += 1
                same_minute_xg += _to_float(s.get("expectedGoals")) or 0.0
        xg = _to_float(s.get("expectedGoals"))
        if xg is None:
            issues.append("shot_without_xg")
            xg = 0.0
        shot_rows.append({"pos": pos, "side": side, "xg": xg, "penalty": s.get("situation") == "Penalty"})

    # ---- walk the changes to build stints
    on = {"home": list(starters["home"]), "away": list(starters["away"])}
    reds = {"home": 0, "away": 0}
    subs = {"home": 0, "away": 0}
    ignored_reds = 0
    segments: list[dict] = []
    seg_start, seg_start_nominal, start_label = 0.0, 0.0, "0"
    nominal_minutes: dict[int, float] = defaultdict(float)

    def close(end: float, end_nominal: float, reason: str, end_label: str) -> None:
        if end <= seg_start + EPS:
            return
        segments.append({
            "start": seg_start, "end": end, "start_nominal": seg_start_nominal, "end_nominal": end_nominal,
            "start_label": start_label, "end_label": end_label, "end_reason": reason,
            "home_players": sorted(on["home"]), "away_players": sorted(on["away"]),
        })
        for s in ("home", "away"):
            for pid in on[s]:
                nominal_minutes[pid] += end_nominal - seg_start_nominal

    i = 0
    while i < len(changes):
        group = [changes[i]]
        while i + len(group) < len(changes) and abs(changes[i + len(group)]["pos"] - changes[i]["pos"]) < EPS:
            group.append(changes[i + len(group)])
        pos = group[0]["pos"]
        nominal = group[0]["nominal"]
        label = minute_label(group[0]["minute"], group[0]["ov"])
        new_on = {"home": list(on["home"]), "away": list(on["away"])}
        effective = set()
        for c in group:
            s = c["side"]
            if c["kind"] == "substitution":
                subs[s] += 1
                if c["out"] in new_on[s]:
                    new_on[s].remove(c["out"])
                else:
                    issues.append(f"{s}_sub_off_not_on_pitch")
                if c["in"] in new_on[s] or c["in"] in new_on["home" if s == "away" else "away"]:
                    issues.append(f"{s}_sub_on_already_on_pitch")
                else:
                    if c["in"] not in bench[s]:
                        issues.append(f"{s}_sub_on_not_in_bench_list")
                    new_on[s].append(c["in"])
                effective.add("substitution")
            else:
                if c["player"] in new_on[s]:
                    new_on[s].remove(c["player"])
                    reds[s] += 1
                    effective.add("red_card")
                else:
                    other = "home" if s == "away" else "away"
                    if c["player"] in new_on[other]:
                        issues.append("red_card_side_mismatch")
                    ignored_reds += 1   # bench player, coach, or already substituted: no line-up change
        changed = set(new_on["home"]) != set(on["home"]) or set(new_on["away"]) != set(on["away"])
        if changed and pos > seg_start + EPS:
            close(pos, nominal, "+".join(sorted(effective)), label)   # closes with the players before the change
            seg_start, seg_start_nominal, start_label = pos, nominal, label
        on = new_on
        i += len(group)
    close(clock.total, float(end_minute), "full_time", "FT" if not extra_time else "AET")

    for s in ("home", "away"):
        if len(on[s]) != 11 - reds[s]:
            issues.append(f"{s}_players_on_pitch_{len(on[s])}_with_{reds[s]}_reds")
    header_reds = (_to_int(status.get("numberOfHomeRedCards")), _to_int(status.get("numberOfAwayRedCards")))
    if None not in header_reds and (reds["home"], reds["away"]) != header_reds:
        issues.append("red_cards_differ_from_header")

    # ---- assign shots and goals to stints
    ends = [seg["end"] for seg in segments]

    def seg_index(pos: float) -> int:
        lo, hi = 0, len(ends) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if pos < ends[mid]:
                hi = mid
            else:
                lo = mid + 1
        return lo

    for seg in segments:
        for s in ("home", "away"):
            seg[f"{s}_goals"] = 0
            seg[f"{s}_np_goals"] = 0
            seg[f"{s}_shots"] = 0 if xg_available else None
            seg[f"{s}_xg"] = 0.0 if xg_available else None
            seg[f"{s}_npxg"] = 0.0 if xg_available else None
    if segments:
        for g in goals:
            seg = segments[seg_index(g["pos"])]
            seg[f"{g['side']}_goals"] += 1
            if not g["penalty"]:
                seg[f"{g['side']}_np_goals"] += 1
        if xg_available:
            for sh in shot_rows:
                seg = segments[seg_index(sh["pos"])]
                seg[f"{sh['side']}_shots"] += 1
                seg[f"{sh['side']}_xg"] += sh["xg"]
                if not sh["penalty"]:
                    seg[f"{sh['side']}_npxg"] += sh["xg"]

    # ---- game state: score at stint start and minutes by state (home perspective)
    goal_events = sorted((g["pos"], g["side"]) for g in goals)
    for seg in segments:
        hs = sum(1 for p, sd in goal_events if p < seg["start"] and sd == "home")
        as_ = sum(1 for p, sd in goal_events if p < seg["start"] and sd == "away")
        seg["score_start"] = [hs, as_]
        lead = level = trail = 0.0
        t0 = seg["start"]
        for p, sd in goal_events:
            if p < seg["start"] or p >= seg["end"]:
                continue
            d = hs - as_
            span = p - t0
            lead += span if d > 0 else 0.0
            level += span if d == 0 else 0.0
            trail += span if d < 0 else 0.0
            t0 = p
            hs += sd == "home"
            as_ += sd == "away"
        d = hs - as_
        span = seg["end"] - t0
        lead += span if d > 0 else 0.0
        level += span if d == 0 else 0.0
        trail += span if d < 0 else 0.0
        seg["home_lead_minutes"] = round(lead, 4)
        seg["level_minutes"] = round(level, 4)
        seg["home_trail_minutes"] = round(trail, 4)

    # ---- validation
    score = [_to_int(t.get("score")) for t in (header.get("teams") or [{}, {}])[:2]]
    seg_goals = (sum(s["home_goals"] for s in segments), sum(s["away_goals"] for s in segments))
    goals_ok = len(score) == 2 and None not in score and tuple(score) == seg_goals
    team_xg = team_stat_pair(content, "expected_goals")
    team_npxg = team_stat_pair(content, "expected_goals_non_penalty")
    stats_xg = player_stats_xg(content, team_ids)
    seg_xg = (sum(s["home_xg"] for s in segments), sum(s["away_xg"] for s in segments)) if xg_available else (None, None)
    seg_npxg = (sum(s["home_npxg"] for s in segments), sum(s["away_npxg"] for s in segments)) if xg_available else (None, None)
    xg_diff = (None, None)
    if None not in team_xg and xg_available:
        xg_diff = (seg_xg[0] - team_xg[0], seg_xg[1] - team_xg[1])
        side_fail = set()
        for k, s in enumerate(("home", "away")):
            if abs(xg_diff[k]) <= XG_TOLERANCE:
                continue
            # FotMob sends three xG figures: per shot (shotmap), per player (playerStats) and per
            # team (stats). When two of them agree the third one is the odd one out.
            pst = stats_xg[s]
            if pst is not None and abs(pst - seg_xg[k]) <= XG_TOLERANCE:
                side_fail.add("team_stat_differs")       # shots = player stats != team stat
            elif pst is not None and abs(pst - team_xg[k]) <= XG_TOLERANCE:
                side_fail.add("shot_values_differ")      # player stats = team stat != shots
            else:
                side_fail.add("unexplained")
        xg_check = "pass" if not side_fail else "fail_" + "+".join(sorted(side_fail))
    elif None not in team_xg:
        xg_check = "fail_no_shotmap"
    elif xg_available:
        xg_check = "fail_no_team_xg"
    else:
        xg_check = "n/a"

    fotmob_minutes = meta.get("minutes") or {}
    checked = off = 0
    max_diff = 0.0
    on_pitch_ever = set(nominal_minutes)
    for pid, mins in fotmob_minutes.items():
        if mins is None:
            continue
        ours = nominal_minutes.get(int(pid), 0.0)
        if mins == 0 and int(pid) not in on_pitch_ever:
            continue
        checked += 1
        diff = abs(ours - mins)
        max_diff = max(max_diff, diff)
        off += diff > MINUTES_TOLERANCE
    minutes_ok = checked > 0 and off == 0
    minutes_consistent = checked > 0 and max_diff <= MINUTES_USABLE_TOLERANCE
    length_ok = (120.0 <= clock.total <= 160.0) if extra_time else (90.0 <= clock.total <= 125.0)
    lineup_ok = not issues
    usable = lineup_ok and goals_ok and minutes_consistent

    reasons = []
    if not lineup_ok:
        reasons.append("lineup")
    if not goals_ok:
        reasons.append("goals")
    if xg_check.startswith("fail"):
        reasons.append(xg_check.replace("fail_", "xg_"))
    if not minutes_ok:
        reasons.append("minutes_gt_1" if minutes_consistent else f"minutes_gt_{MINUTES_USABLE_TOLERANCE}")
    if not length_ok:
        reasons.append("length")

    val.update({
        "n_segments": len(segments), "subs_home": subs["home"], "subs_away": subs["away"],
        "reds_home": reds["home"], "reds_away": reds["away"],
        "header_reds_home": header_reds[0], "header_reds_away": header_reds[1], "red_cards_ignored": ignored_reds,
        "lineup_ok": lineup_ok, "lineup_issues": ";".join(sorted(set(issues))),
        "score_home": score[0] if score else None, "score_away": score[1] if len(score) > 1 else None,
        "segment_goals_home": seg_goals[0], "segment_goals_away": seg_goals[1], "goals_ok": goals_ok,
        "xg_available": xg_available, "team_xg_home": team_xg[0], "team_xg_away": team_xg[1],
        "stats_player_xg_home": None if stats_xg["home"] is None else round(stats_xg["home"], 4),
        "stats_player_xg_away": None if stats_xg["away"] is None else round(stats_xg["away"], 4),
        "segment_xg_home": None if seg_xg[0] is None else round(seg_xg[0], 4),
        "segment_xg_away": None if seg_xg[1] is None else round(seg_xg[1], 4),
        "xg_diff_home": None if xg_diff[0] is None else round(xg_diff[0], 4),
        "xg_diff_away": None if xg_diff[1] is None else round(xg_diff[1], 4),
        "team_npxg_home": team_npxg[0], "team_npxg_away": team_npxg[1],
        "segment_npxg_home": None if seg_npxg[0] is None else round(seg_npxg[0], 4),
        "segment_npxg_away": None if seg_npxg[1] is None else round(seg_npxg[1], 4),
        "xg_check": xg_check, "minutes_players_checked": checked, "minutes_max_abs_diff": round(max_diff, 3),
        "minutes_players_off": off, "minutes_ok": minutes_ok, "minutes_consistent": minutes_consistent,
        "length_ok": length_ok,
        "same_minute_shots": same_minute_shots, "same_minute_xg": round(same_minute_xg, 4),
        "goals_moved_before_change": moved, "goals_mixed_order": mixed, "own_goals": own_goals,
        "shootout_shots_skipped": shootout_skipped, "usable": usable, "passed": not reasons,
        "fail_reasons": ";".join(reasons),
    })

    rows = []
    for k, seg in enumerate(segments):
        n_home, n_away = len(seg["home_players"]), len(seg["away_players"])
        row = {
            "match_id": match_id, "kickoff": meta.get("kickoff"), "competition_id": meta.get("competition_id"),
            "source_league_id": meta.get("source_league_id"), "season": meta.get("season"),
            "home_team_id": team_ids["home"], "away_team_id": team_ids["away"], "seg": k,
            "start": round(seg["start"], 4), "end": round(seg["end"], 4),
            "duration": round(seg["end"] - seg["start"], 4),
            "start_nominal": seg["start_nominal"], "end_nominal": seg["end_nominal"],
            "start_label": seg["start_label"], "end_label": seg["end_label"], "end_reason": seg["end_reason"],
            "halves": clock.halves_between(seg["start"], seg["end"]),
            "home_players": seg["home_players"], "away_players": seg["away_players"],
            "n_home": n_home, "n_away": n_away, "man_adv": n_home - n_away,
            "xg_available": xg_available,
        }
        for s in ("home", "away"):
            for key in ("xg", "npxg"):
                v = seg[f"{s}_{key}"]
                row[f"{s}_{key}"] = None if v is None else round(v, 5)
            row[f"{s}_shots"] = seg[f"{s}_shots"]
            row[f"{s}_goals"] = seg[f"{s}_goals"]
            row[f"{s}_np_goals"] = seg[f"{s}_np_goals"]
        row.update({
            "score_start": seg["score_start"], "home_lead_minutes": seg["home_lead_minutes"],
            "level_minutes": seg["level_minutes"], "home_trail_minutes": seg["home_trail_minutes"],
            "lineup_ok": lineup_ok, "goals_ok": goals_ok, "xg_check": xg_check,
            "minutes_ok": minutes_ok, "usable": usable, "match_passed": not reasons,
        })
        rows.append(row)
    return rows, val


# --------------------------------------------------------------------------- I/O

def read_details(paths: Iterable[Path]) -> tuple[list[dict], dict]:
    """Match metadata from fotmob_match_details-style JSONL files (first occurrence of an id wins)."""
    metas: dict[str, dict] = {}
    stats = Counter()
    for path in paths:
        with open(path, "rb") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    mid = str(r["match_provider_id"])
                except (ValueError, KeyError, TypeError):
                    stats["jsonl_unparsable_lines"] += 1
                    continue
                if mid in metas:
                    stats["jsonl_duplicate_ids"] += 1
                    continue
                stats[f"jsonl_rows:{path.name}"] += 1
                if r.get("awarded"):
                    stats["awarded_skipped"] += 1
                    continue
                minutes = {}
                for p in r.get("players") or []:
                    pid = _to_int(p.get("player_id"))
                    if pid is not None and p.get("minutes_played") is not None:
                        minutes[pid] = _to_int(p.get("minutes_played"))
                kickoff = r.get("scheduled_at")
                metas[mid] = {
                    "match_id": mid, "kickoff": kickoff, "competition_id": _to_int(r.get("competition_provider_id")),
                    "source_league_id": _to_int(r.get("source_league_id")), "season": r.get("season"),
                    "home_team_id": _to_int(r.get("home_team_provider_id")),
                    "away_team_id": _to_int(r.get("away_team_provider_id")), "minutes": minutes,
                }
    ordered = sorted(metas.values(), key=lambda m: (m["kickoff"] or "", m["match_id"]))
    return ordered, dict(stats)


def load_raw(raw_dir: Path, match_id: str) -> tuple[Optional[dict], Optional[str]]:
    path = raw_dir / f"{match_id}.json.gz"
    if not path.exists():
        return None, "raw_missing"
    try:
        with gzip.open(path, "rb") as f:
            data = f.read()
        return json.loads(data), None
    except (OSError, EOFError, zlib.error, ValueError, UnicodeDecodeError):
        return None, "raw_unreadable"


def _work(args: tuple[str, list[dict]]) -> list[tuple[str, list[dict], Optional[dict], Optional[str]]]:
    raw_dir, metas = args
    out = []
    for meta in metas:
        raw, err = load_raw(Path(raw_dir), meta["match_id"])
        if raw is None:
            out.append((meta["match_id"], [], None, err))
            continue
        try:
            rows, val = build_match(raw, meta)
        except Exception as exc:  # odd structure: report, never crash the run
            out.append((meta["match_id"], [], None, f"parse_error:{type(exc).__name__}"))
            continue
        out.append((meta["match_id"], rows, val, None))
    return out


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def summarize(vals: list[dict], read_stats: dict, skipped: Counter, n_rows: int, seconds: float,
              details: list[str]) -> dict:
    def pct(a: int, b: int) -> Optional[float]:
        return round(100.0 * a / b, 2) if b else None

    n = len(vals)
    reasons = Counter()
    issues = Counter()
    by_comp: dict[Any, Counter] = defaultdict(Counter)
    xg_diffs, minute_diffs, lengths = [], [], []
    same_xg = 0.0
    total_xg = 0.0
    for v in vals:
        for r in (v["fail_reasons"] or "").split(";"):
            if r:
                reasons[r] += 1
        for r in (v["lineup_issues"] or "").split(";"):
            if r:
                issues[r] += 1
        c = by_comp[v["competition_id"]]
        c["matches"] += 1
        c["passed"] += bool(v["passed"])
        c["usable"] += bool(v["usable"])
        c["lineup_ok"] += bool(v["lineup_ok"])
        c["goals_ok"] += bool(v["goals_ok"])
        c["xg_pass"] += v["xg_check"] == "pass"
        c["xg_na"] += v["xg_check"] == "n/a"
        c["minutes_ok"] += bool(v["minutes_ok"])
        c["segments"] += v["n_segments"] or 0
        if v["xg_diff_home"] is not None:
            xg_diffs += [abs(v["xg_diff_home"]), abs(v["xg_diff_away"])]
        if v["minutes_max_abs_diff"] is not None:
            minute_diffs.append(v["minutes_max_abs_diff"])
        if v["match_length"] is not None:
            lengths.append(v["match_length"])
        same_xg += v["same_minute_xg"] or 0.0
        total_xg += (v["segment_xg_home"] or 0.0) + (v["segment_xg_away"] or 0.0)

    def quant(xs: list[float], qs=(0.5, 0.9, 0.95, 0.99, 1.0)) -> dict:
        if not xs:
            return {}
        s = sorted(xs)
        return {f"p{int(q * 100)}": round(s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))], 4) for q in qs}

    return {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "details_files": details,
        "read": read_stats,
        "skipped_matches": dict(skipped),
        "matches_built": n,
        "stint_rows": n_rows,
        "seconds": round(seconds, 1),
        "passed_all_checks": {"n": sum(bool(v["passed"]) for v in vals), "pct": pct(sum(bool(v["passed"]) for v in vals), n)},
        "usable": {"n": sum(bool(v["usable"]) for v in vals), "pct": pct(sum(bool(v["usable"]) for v in vals), n),
                   "usable_with_xg": sum(bool(v["usable"]) and bool(v["xg_available"]) for v in vals),
                   "definition": f"lineup_ok and goals_ok and every player's minutes within {MINUTES_USABLE_TOLERANCE} of FotMob"},
        "check_pass_pct": {
            "lineup_ok": pct(sum(bool(v["lineup_ok"]) for v in vals), n),
            "goals_ok": pct(sum(bool(v["goals_ok"]) for v in vals), n),
            "xg_pass_of_matches_with_team_xg": pct(sum(v["xg_check"] == "pass" for v in vals),
                                                   sum(v["team_xg_home"] is not None for v in vals)),
            "xg_check_counts": dict(Counter(v["xg_check"] for v in vals)),
            "minutes_ok_within_1": pct(sum(bool(v["minutes_ok"]) for v in vals), n),
            f"minutes_within_{MINUTES_USABLE_TOLERANCE}": pct(sum(bool(v["minutes_consistent"]) for v in vals), n),
            "length_ok": pct(sum(bool(v["length_ok"]) for v in vals), n),
        },
        "fail_reasons": dict(reasons.most_common()),
        "lineup_issues": dict(issues.most_common()),
        "abs_xg_diff_per_side": quant(xg_diffs),
        "max_abs_minutes_diff_per_match": quant(minute_diffs),
        "match_length_minutes": quant(lengths, (0.0, 0.01, 0.5, 0.99, 1.0)),
        "half_length_sources": {
            "h1": dict(Counter(v["h1_length_source"] for v in vals)),
            "h2": dict(Counter(v["h2_length_source"] for v in vals)),
        },
        "same_minute_shots": {"shots": sum(v["same_minute_shots"] or 0 for v in vals),
                              "xg": round(same_xg, 2), "share_of_all_xg_pct": pct(same_xg, total_xg) if total_xg else None},
        "goals_moved_before_change": sum(v["goals_moved_before_change"] or 0 for v in vals),
        "goals_mixed_order": sum(v["goals_mixed_order"] or 0 for v in vals),
        "by_competition": {str(k): dict(c) for k, c in sorted(by_comp.items(), key=lambda kv: str(kv[0]))},
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--details", action="append", type=Path,
                    help="fotmob_match_details-style JSONL (repeatable); default: the 2025-26 file")
    ap.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--validation-out", type=Path, default=DEFAULT_VALIDATION)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    ap.add_argument("--limit", type=int, default=0, help="only the first N matches (debugging)")
    args = ap.parse_args(argv)

    t0 = time.time()
    details = args.details or [DEFAULT_DETAILS]
    metas, read_stats = read_details(details)
    if args.limit:
        metas = metas[: args.limit]
    print(f"{len(metas)} matches from {len(details)} JSONL file(s) {read_stats}", flush=True)

    chunk = 100
    jobs = [(str(args.raw_dir), metas[i:i + chunk]) for i in range(0, len(metas), chunk)]
    results = []
    if args.workers > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for part in pool.map(_work, jobs):
                results.extend(part)
    else:
        for job in jobs:
            results.extend(_work(job))

    order = {m["match_id"]: k for k, m in enumerate(metas)}
    results.sort(key=lambda r: order[r[0]])
    skipped = Counter()
    vals, n_rows = [], 0
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        for mid, rows, val, err in results:
            if err:
                skipped[err] += 1
                continue
            vals.append(val)
            for row in rows:
                gz.write((json.dumps(row, separators=(",", ":")) + "\n").encode("utf-8"))
                n_rows += 1
    _atomic_write(args.out, buf.getvalue())

    sio = io.StringIO()
    w = csv.DictWriter(sio, fieldnames=VALIDATION_FIELDS, lineterminator="\n")
    w.writeheader()
    for v in vals:
        w.writerow(v)
    _atomic_write(args.validation_out, sio.getvalue().encode("utf-8"))

    report = summarize(vals, read_stats, skipped, n_rows, time.time() - t0, [str(p) for p in details])
    _atomic_write(args.report, json.dumps(report, indent=1).encode("utf-8"))
    print(json.dumps({k: report[k] for k in ("matches_built", "stint_rows", "skipped_matches", "passed_all_checks",
                                             "usable", "check_pass_pct", "fail_reasons", "lineup_issues",
                                             "abs_xg_diff_per_side",
                                             "max_abs_minutes_diff_per_match", "same_minute_shots", "seconds")}, indent=1),
          flush=True)
    print(f"-> {args.out}  {args.validation_out}  {args.report}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
