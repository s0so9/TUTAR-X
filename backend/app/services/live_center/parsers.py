"""Pure parsers: one FotMob ``/api/data/matchDetails`` body -> live-center contract.

No I/O here. Every value comes from the body; when the body does not carry a
section the value is ``None`` and the section is listed in ``missing`` (AGENTS.md
rules 10 and 14). Field paths: docs/live-center-data-sources.md.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from app.services.live_center.constants import (
    CARD_TYPES,
    CLOSED_STATUSES,
    ERROR_MESSAGES_TR,
    EVENT_DETAIL_TR,
    EVENT_GOAL,
    EVENT_OWN_GOAL,
    EVENT_PENALTY_GOAL,
    EVENT_PENALTY_MISSED,
    EVENT_PERIOD_END,
    EVENT_RED,
    EVENT_SECOND_YELLOW,
    EVENT_SUBSTITUTION,
    EVENT_VAR,
    EVENT_YELLOW,
    LINEUP_TYPE_MAP,
    LIVE_STATUSES,
    MISSING_REASONS_TR,
    PERIOD_ORDER,
    PROVIDER_FOTMOB,
    SHOT_BODY_PART_TR,
    SHOT_SITUATION_TR,
    SOURCE_GROUP_MAP,
    STAT_SPECS,
    STATUS_ABANDONED,
    STATUS_CANCELLED,
    STATUS_EXTRA_TIME,
    STATUS_FINISHED,
    STATUS_HALF_TIME,
    STATUS_LIVE,
    STATUS_PENALTIES,
    STATUS_POSTPONED,
    STATUS_SCHEDULED,
    TTL_FINISHED_SECONDS,
    TTL_LIVE_SECONDS,
    TTL_SCHEDULED_MIN_SECONDS,
    TTL_SCHEDULED_SECONDS,
    UNAVAILABILITY_REASON_TR,
    UNIT_COUNT,
    UNIT_DECIMAL,
    UNIT_PERCENT,
)
from app.services.live_center.schemas import (
    GridPos,
    LineupPlayer,
    Lineups,
    LiveCenterResponse,
    LiveEvent,
    MissingSection,
    MomentumPoint,
    PersonRef,
    ScorePair,
    Shot,
    StatEntry,
    Stats,
    TeamInfo,
    TeamLineup,
    Teams,
    UnavailablePlayer,
)


class LiveCenterPayloadError(ValueError):
    """The body is not a FotMob matchDetails object for the requested match."""


# =========================================================================== small helpers


def _int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value == value else None  # NaN guard
    if isinstance(value, str):
        m = re.match(r"^\s*(-?\d+)", value)
        return int(m.group(1)) if m else None
    return None


def _float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value == value else None
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _str(value: Any, max_len: int = 300) -> Optional[str]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:max_len] if value else None


def _id(value: Any) -> Optional[str]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, str) and value.strip() and value.strip() not in {"0", "None", "null"}:
        return value.strip()
    return None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _person(pid: Any, name: Any) -> Optional[PersonRef]:
    pid_s, name_s = _id(pid), _str(name)
    if pid_s is None and name_s is None:
        return None
    return PersonRef(id=pid_s, name=name_s)


def _parse_utc(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _tr_detail(text: Optional[str]) -> Optional[str]:
    """Turkish label for a FotMob event description; unknown texts are kept as sent."""
    if not text:
        return text
    return EVENT_DETAIL_TR.get(text.strip().lower(), text)


def _missing(section: str, reason: str) -> MissingSection:
    return MissingSection(section=section, reason=reason, message_tr=MISSING_REASONS_TR.get(reason))


# =========================================================================== status

_MINUTE_RE = re.compile(r"^\s*(\d+)\s*(?:\+\s*(\d+))?")


def parse_minute_text(text: Any) -> tuple[Optional[int], Optional[int]]:
    """"23'" -> (23, None); "45+2'" -> (45, 2); "HT" -> (None, None)."""
    if not isinstance(text, str):
        return None, None
    m = _MINUTE_RE.match(text.replace("’", "'"))
    if not m:
        return None, None
    return int(m.group(1)), (int(m.group(2)) if m.group(2) else None)


def _half_started(halfs: dict[str, Any], key: str) -> bool:
    return bool(_str(halfs.get(key)))


def parse_status(general: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    """Status block -> status/status_text/minute/added_time/period (+ penalties flag)."""
    reason = _dict(status.get("reason"))
    reason_key = (_str(reason.get("longKey")) or "").lower()
    reason_short = _str(reason.get("short"))
    live_time = _dict(status.get("liveTime"))
    halfs = _dict(status.get("halfs"))
    started = bool(status.get("started") or general.get("started"))
    finished = bool(status.get("finished") or general.get("finished"))
    out: dict[str, Any] = {"status_text": None, "minute": None, "added_time": None, "period": None}

    if status.get("cancelled"):
        if "postpon" in reason_key or (reason_short or "").lower() in {"pp", "ppd"}:
            out["status"] = STATUS_POSTPONED
        elif "abandon" in reason_key or (reason_short or "").lower() in {"ab", "abd", "aban"}:
            out["status"] = STATUS_ABANDONED
        else:
            out["status"] = STATUS_CANCELLED
        out["status_text"] = reason_short
        return out
    if finished:
        out.update(status=STATUS_FINISHED, period="FT", status_text=reason_short or "FT")
        return out
    if not started:
        out["status"] = STATUS_SCHEDULED
        return out

    short = _str(live_time.get("short"))
    out["status_text"] = short or reason_short
    short_norm = (short or "").replace("’", "'").strip().upper()
    if short_norm in {"HT", "HALF-TIME", "HALFTIME"}:
        out.update(status=STATUS_HALF_TIME, period="HT")
        return out
    if "PEN" in short_norm or "penalt" in reason_key:
        out.update(status=STATUS_PENALTIES, period="PEN")
        return out
    minute, added = parse_minute_text(short)
    out["minute"], out["added_time"] = minute, added
    if _half_started(halfs, "firstExtraHalfStarted") or _half_started(halfs, "secondExtraHalfStarted") or (
        minute is not None and minute > 90
    ):
        out.update(status=STATUS_EXTRA_TIME, period="ET")
    elif _half_started(halfs, "secondHalfStarted") or (minute is not None and minute > 45):
        out.update(status=STATUS_LIVE, period="2H")
    else:
        out.update(status=STATUS_LIVE, period="1H")
    return out


def ttl_for(status: str, kickoff: Optional[datetime], now: datetime) -> int:
    """Contract TTLs: 15 s live, 5 min before kick-off (expiring at kick-off), 1 h closed."""
    if status in LIVE_STATUSES:
        return TTL_LIVE_SECONDS
    if status in CLOSED_STATUSES:
        return TTL_FINISHED_SECONDS
    if kickoff is not None:
        to_kickoff = (kickoff - now).total_seconds()
        return int(max(TTL_SCHEDULED_MIN_SECONDS, min(TTL_SCHEDULED_SECONDS, to_kickoff)))
    return TTL_SCHEDULED_SECONDS


# =========================================================================== events


def _event_period(minute: Optional[int], shootout: bool) -> Optional[str]:
    if shootout:
        return "PEN"
    if minute is None:
        return None
    if minute <= 45:
        return "1H"
    if minute <= 90:
        return "2H"
    return "ET"


def _period_end_label(e: dict[str, Any]) -> Optional[str]:
    return _str(e.get("halfStrShort")) or _str(e.get("halfStrKey"))


def _var_detail(e: dict[str, Any]) -> Optional[str]:
    var = _dict(e.get("VAR"))
    decision = _dict(var.get("decision"))
    values = [_tr_detail(v) for v in _list(decision.get("value")) if isinstance(v, str) and v.strip()]
    text = " - ".join(values) if values else None
    if var.get("pendingDecision"):
        text = (text + " (karar bekleniyor)") if text else "karar bekleniyor"
    return text


def _score_pair(values: Any) -> Optional[ScorePair]:
    vals = _list(values)
    if len(vals) != 2:
        return None
    h, a = _int(vals[0]), _int(vals[1])
    if h is None and a is None:
        return None
    return ScorePair(home=h, away=a)


def _stable_id(prefix: str, *parts: Any) -> str:
    return prefix + "-" + "-".join("" if p is None else str(p) for p in parts)


def parse_events(content: dict[str, Any]) -> Optional[list[LiveEvent]]:
    """``content.matchFacts.events.events`` (+ ``penaltyShootoutEvents``) -> chronological events.

    Returns None when the source sent no event block. Source types AddedTime,
    Comment and the PenaltyShootout aggregate are not contract events.
    """
    block = _dict(_dict(content.get("matchFacts")).get("events"))
    raw = block.get("events")
    if not isinstance(raw, list):
        return None
    shootout = [e for e in _list(block.get("penaltyShootoutEvents")) if isinstance(e, dict)]

    keyed: list[tuple[tuple, LiveEvent]] = []
    for idx, e in enumerate([e for e in raw if isinstance(e, dict)] + shootout):
        is_shootout = bool(e.get("isPenaltyShootoutEvent")) or idx >= len(raw)
        ev = _parse_event(e, idx, is_shootout)
        if ev is None:
            continue
        key = (PERIOD_ORDER.get(ev.period or "", 9), ev.minute if ev.minute is not None else 999, ev.added_time or 0, idx)
        keyed.append((key, ev))
    keyed.sort(key=lambda kv: kv[0])
    return [ev for _, ev in keyed]


def _parse_event(e: dict[str, Any], idx: int, shootout: bool) -> Optional[LiveEvent]:
    etype = e.get("type")
    minute = _int(e.get("time"))
    added = _int(e.get("overloadTime")) or None  # FotMob sends 0/null for "no added time"
    period = _event_period(minute, shootout)
    side = None
    if isinstance(e.get("isHome"), bool):
        side = "home" if e["isHome"] else "away"
    player_raw = _dict(e.get("player"))
    player = _person(player_raw.get("id") or e.get("playerId"), player_raw.get("name") or e.get("nameStr") or e.get("fullName"))
    event_id = _id(e.get("eventId"))

    if etype == "Goal":
        desc_key = (_str(e.get("goalDescriptionKey")) or "").lower()
        if e.get("ownGoal"):
            ctype = EVENT_OWN_GOAL
        elif desc_key == "penalty" or shootout:
            ctype = EVENT_PENALTY_GOAL
        else:
            ctype = EVENT_GOAL
        assist = _person(e.get("assistPlayerId"), e.get("assistInput")) if e.get("assistPlayerId") or e.get("assistInput") else None
        detail = _str(e.get("goalDescription"))
        if ctype == EVENT_PENALTY_GOAL and detail and detail.strip().lower() == "penalty":
            detail = None  # the type already says penalty
        detail = _tr_detail(detail)
        if shootout:
            detail = "Penaltı atışları" + (f" ({detail})" if detail and detail.lower() != "penalty" else "")
        return LiveEvent(
            id=event_id or _stable_id("goal", minute, added, player.id if player else None, idx),
            minute=minute,
            added_time=added,
            period=period,
            side=side,
            type=ctype,
            player=player,
            assist=assist,
            score_after=_score_pair(e.get("newScore")) if not shootout else _score_pair(e.get("penShootoutScore")),
            detail=detail,
        )
    if etype == "MissedPenalty":
        return LiveEvent(
            id=event_id or _stable_id("penmiss", minute, added, player.id if player else None, idx),
            minute=minute,
            added_time=added,
            period=period,
            side=side,
            type=EVENT_PENALTY_MISSED,
            player=player,
            score_after=_score_pair(e.get("penShootoutScore")) if shootout else None,
            detail="Penaltı atışları" if shootout else None,
        )
    if etype == "Card":
        ctype = CARD_TYPES.get(_str(e.get("card")) or "")
        if ctype is None:
            return None
        detail = _str(_dict(e.get("cardReason")).get("defaultText")) or _str(_dict(e.get("cardDescription")).get("defaultText"))
        detail = _tr_detail(detail)
        return LiveEvent(
            id=event_id or _stable_id("card", minute, added, player.id if player else None, idx),
            minute=minute,
            added_time=added,
            period=period,
            side=side,
            type=ctype,
            player=player,
            detail=detail,
        )
    if etype == "Substitution":
        swap = _list(e.get("swap"))
        p_in = _person(_dict(swap[0]).get("id"), _dict(swap[0]).get("name")) if len(swap) > 0 else None
        p_out = _person(_dict(swap[1]).get("id"), _dict(swap[1]).get("name")) if len(swap) > 1 else None
        return LiveEvent(
            id=_stable_id("sub", minute, added, p_in.id if p_in else None, p_out.id if p_out else None),
            minute=minute,
            added_time=added,
            period=period,
            side=side,
            type=EVENT_SUBSTITUTION,
            player_in=p_in,
            player_out=p_out,
            detail="Sakatlık" if e.get("injuredPlayerOut") else None,
        )
    if etype == "VAR":
        return LiveEvent(
            id=event_id or _stable_id("var", minute, added, player.id if player else None, idx),
            minute=minute,
            added_time=added,
            period=period,
            side=side,
            type=EVENT_VAR,
            player=player,
            detail=_var_detail(e),
        )
    if etype == "Half":
        label = _period_end_label(e)
        # a period end belongs to the period it closes
        return LiveEvent(
            id=_stable_id("half", label, minute),
            minute=minute,
            added_time=None,
            period=period,
            side=None,
            type=EVENT_PERIOD_END,
            score_after=ScorePair(home=_int(e.get("homeScore")), away=_int(e.get("awayScore")))
            if e.get("homeScore") is not None or e.get("awayScore") is not None
            else None,
            detail=label,
        )
    return None


# =========================================================================== lineups


def position_group(position_id: Any, usual_position_id: Any) -> Optional[str]:
    """FotMob pitch-slot id (11 GK, 3x/5x defence, 6x-9x midfield, 10x/11x attack;
    see the docs) -> GK/DEF/MID/FWD; falls back to usualPlayingPositionId (0-3)."""
    pid = _int(position_id)
    if pid is not None:
        if pid == 11:
            return "GK"
        if 30 <= pid <= 59:
            return "DEF"
        if 60 <= pid <= 99:
            return "MID"
        if 100 <= pid <= 119:
            return "FWD"
    upid = _int(usual_position_id)
    return {0: "GK", 1: "DEF", 2: "MID", 3: "FWD"}.get(upid) if upid is not None else None


def _formation_counts(formation: Optional[str]) -> Optional[list[int]]:
    if not formation:
        return None
    parts = formation.replace(" ", "").split("-")
    try:
        counts = [int(p) for p in parts if p]
    except ValueError:
        return None
    return counts if counts and all(c > 0 for c in counts) else None


def compute_grid(starters: list[dict[str, Any]], formation: Optional[str]) -> dict[int, GridPos]:
    """Starter list index -> formation grid cell, from FotMob ``horizontalLayout``
    (x: own goal -> attack, y: 0 = left flank ... 1 = right flank).

    Goalkeeper (smallest x) is row 0. When the formation string's lines add up to
    the outfield players, players sorted by x fill the lines in order; otherwise
    rows are the distinct x values. Inside a row, col 0 is the left flank.
    Returns {} when the source sent no layout for every starter.
    """
    coords: list[tuple[int, float, float]] = []
    for i, p in enumerate(starters):
        hl = _dict(p.get("horizontalLayout"))
        x, y = _float(hl.get("x")), _float(hl.get("y"))
        if x is None or y is None:
            return {}
        coords.append((i, x, y))
    if len(coords) < 2:
        return {}
    coords.sort(key=lambda c: (c[1], c[2]))
    gk, outfield = coords[0], coords[1:]
    rows: list[list[tuple[int, float, float]]] = [[gk]]
    counts = _formation_counts(formation)
    if counts and sum(counts) == len(outfield):
        pos = 0
        for n in counts:
            rows.append(outfield[pos : pos + n])
            pos += n
    else:
        by_x: dict[float, list[tuple[int, float, float]]] = defaultdict(list)
        for c in outfield:
            by_x[round(c[1], 3)].append(c)
        rows.extend(by_x[k] for k in sorted(by_x))
    grid: dict[int, GridPos] = {}
    for r, row in enumerate(rows):
        ordered = sorted(row, key=lambda c: c[2])
        for col, c in enumerate(ordered):
            grid[c[0]] = GridPos(row=r, col=col, rows_in_formation=len(rows), cols_in_row=len(ordered))
    return grid


def _player_tallies(events: Optional[list[LiveEvent]]) -> Optional[dict[str, dict[str, int]]]:
    """Per-player goals/assists/cards from the event timeline (None without a timeline)."""
    if events is None:
        return None
    tally: dict[str, dict[str, int]] = defaultdict(lambda: {"goals": 0, "assists": 0, "yellow": 0, "red": 0})
    for ev in events:
        if ev.period == "PEN":
            continue  # shoot-out kicks are not match goals
        pid = ev.player.id if ev.player else None
        if ev.type in (EVENT_GOAL, EVENT_PENALTY_GOAL) and pid:
            tally[pid]["goals"] += 1
        if ev.type in (EVENT_GOAL, EVENT_PENALTY_GOAL) and ev.assist and ev.assist.id:
            tally[ev.assist.id]["assists"] += 1
        if ev.type in (EVENT_YELLOW, EVENT_SECOND_YELLOW) and pid:
            tally[pid]["yellow"] += 1
        if ev.type in (EVENT_RED, EVENT_SECOND_YELLOW) and pid:
            tally[pid]["red"] += 1
    return tally


def _sub_minutes(p: dict[str, Any], events: Optional[list[LiveEvent]]) -> tuple[Optional[int], Optional[int]]:
    sub_in = sub_out = None
    for se in _list(_dict(p.get("performance")).get("substitutionEvents")):
        if not isinstance(se, dict):
            continue
        if se.get("type") == "subIn" and sub_in is None:
            sub_in = _int(se.get("time"))
        elif se.get("type") == "subOut" and sub_out is None:
            sub_out = _int(se.get("time"))
    pid = _id(p.get("id"))
    if events and pid and (sub_in is None or sub_out is None):
        for ev in events:
            if ev.type != EVENT_SUBSTITUTION:
                continue
            if sub_in is None and ev.player_in and ev.player_in.id == pid:
                sub_in = ev.minute
            if sub_out is None and ev.player_out and ev.player_out.id == pid:
                sub_out = ev.minute
    return sub_in, sub_out


def _rating(p: dict[str, Any]) -> Optional[float]:
    perf = _dict(p.get("performance"))
    value = perf.get("rating")
    if isinstance(value, dict):  # some FotMob blocks send {"num": "7.4"}
        value = value.get("num")
    r = _float(value)
    return r if r is not None and r > 0 else None  # FotMob uses 0 for "not rated"


def _lineup_player(
    p: dict[str, Any],
    grid: Optional[GridPos],
    tallies: Optional[dict[str, dict[str, int]]],
    events: Optional[list[LiveEvent]],
) -> LineupPlayer:
    pid = _id(p.get("id"))
    t = tallies.get(pid) if (tallies is not None and pid) else None
    zero = {"goals": 0, "assists": 0, "yellow": 0, "red": 0}
    counts = (t or zero) if tallies is not None else None
    sub_in, sub_out = _sub_minutes(p, events)
    return LineupPlayer(
        id=pid,
        name=_str(p.get("name")),
        shirt=_int(p.get("shirtNumber")),
        position=position_group(p.get("positionId"), p.get("usualPlayingPositionId")),
        grid=grid,
        captain=bool(p.get("isCaptain")),
        rating=_rating(p),
        goals=counts["goals"] if counts is not None else None,
        assists=counts["assists"] if counts is not None else None,
        yellow=counts["yellow"] if counts is not None else None,
        red=counts["red"] if counts is not None else None,
        sub_out_minute=sub_out,
        sub_in_minute=sub_in,
        position_id=_int(p.get("positionId")),
    )


def _lineup_type(raw: Any) -> Optional[str]:
    text = (_str(raw) or "").lower()
    if not text:
        return None
    if text in LINEUP_TYPE_MAP:
        return LINEUP_TYPE_MAP[text]
    if "last" in text:
        return "last_starting11"
    return None


def parse_team_lineup(
    team: dict[str, Any],
    lineup_type_raw: Any,
    tallies: Optional[dict[str, dict[str, int]]],
    events: Optional[list[LiveEvent]],
) -> tuple[TeamLineup, bool]:
    """-> (lineup, layout_complete). ``tallies`` is None before kick-off (counts unknown)."""
    starters_raw = [p for p in _list(team.get("starters")) if isinstance(p, dict)]
    subs_raw = [p for p in _list(team.get("subs")) if isinstance(p, dict)]
    formation = _str(team.get("formation"), 30)
    grid = compute_grid(starters_raw, formation) if starters_raw else {}
    coach_raw = team.get("coach")
    coach = None
    if isinstance(coach_raw, dict):
        coach = _person(coach_raw.get("id"), coach_raw.get("name"))
    elif isinstance(coach_raw, list) and coach_raw and isinstance(coach_raw[0], dict):
        coach = _person(coach_raw[0].get("id"), coach_raw[0].get("name"))
    unavailable = []
    for u in _list(team.get("unavailable")):
        if not isinstance(u, dict):
            continue
        un = _dict(u.get("unavailability"))
        code = _str(un.get("type"), 50)
        unavailable.append(
            UnavailablePlayer(
                id=_id(u.get("id")),
                name=_str(u.get("name")),
                reason=UNAVAILABILITY_REASON_TR.get((code or "").lower(), code),
                reason_code=code,
                expected_return=_str(un.get("expectedReturn"), 100),
                expected_return_date=_str(un.get("expectedReturnDate"), 40),
            )
        )
    lineup = TeamLineup(
        formation=formation,
        lineup_type=_lineup_type(lineup_type_raw) if starters_raw else None,
        coach=coach,
        starters=[_lineup_player(p, grid.get(i), tallies, events) for i, p in enumerate(starters_raw)],
        substitutes=[_lineup_player(p, None, tallies, events) for p in subs_raw],
        unavailable=unavailable,
    )
    return lineup, bool(grid) or not starters_raw


# =========================================================================== stats

_PCT_RE = re.compile(r"\((\d+(?:[.,]\d+)?)\s*%\)")
_LEADING_NUMBER_RE = re.compile(r"^\s*-?\d+(?:[.,]\d+)?")


def _raw_pair(s: dict[str, Any]) -> list[dict[str, Any]]:
    raw = s.get("rawStats")
    if isinstance(raw, list) and len(raw) == 2:
        return [r if isinstance(r, dict) else {} for r in raw]
    return [{}, {}]


def _display_pair(s: dict[str, Any]) -> list[Any]:
    vals = s.get("stats")
    return vals if isinstance(vals, list) and len(vals) == 2 else [None, None]


def _side_value(raw: dict[str, Any], display: Any, unit: str) -> Optional[float | int]:
    value = raw.get("value") if raw else None
    if value is None:
        value = display
    if isinstance(value, str):  # display text such as "573 (92%)" or "3.54"
        m = _LEADING_NUMBER_RE.match(value)
        value = m.group(0).replace(",", ".") if m else None
    if unit == UNIT_DECIMAL:
        return _float(value)
    num = _float(value)
    if num is None:
        return None
    return int(num) if float(num).is_integer() else num


def _percent_of_total(raw: dict[str, Any], display: Any) -> Optional[float | int]:
    if isinstance(display, str):
        m = _PCT_RE.search(display)
        if m:
            v = float(m.group(1).replace(",", "."))
            return int(v) if v.is_integer() else v
    value, total = _float(raw.get("value")), _float(raw.get("total"))
    if value is None or total is None or total <= 0:
        return None
    return int(round(100.0 * value / total))


def _text(display: Any) -> Optional[str]:
    if display is None or isinstance(display, bool):
        return None
    if isinstance(display, float) and display.is_integer():
        display = int(display)
    return _str(display, 60)


def parse_stats_period(block: Any) -> Optional[list[StatEntry]]:
    """One ``content.stats.Periods.<Period>`` block -> ordered stat entries
    (only stats the source sent, entries with both sides null are dropped)."""
    groups = _list(_dict(block).get("stats"))
    if not groups:
        return None
    source: dict[str, tuple[str, dict[str, Any]]] = {}
    order: list[str] = []
    for g in groups:
        if not isinstance(g, dict):
            continue
        gkey = _str(g.get("key")) or ""
        for s in _list(g.get("stats")):
            if not isinstance(s, dict) or s.get("type") == "title":
                continue
            key = _str(s.get("key"))
            if key and key not in source:
                source[key] = (gkey, s)
                order.append(key)
    out: list[StatEntry] = []
    used: set[str] = set()
    for spec in STAT_SPECS:
        src_key = next((k for k in spec.source_keys if k in source), None)
        if src_key is None:
            continue
        used.add(src_key)
        _, s = source[src_key]
        raws, displays = _raw_pair(s), _display_pair(s)
        if spec.derived == "percent_of_total":
            home, away = _percent_of_total(raws[0], displays[0]), _percent_of_total(raws[1], displays[1])
        else:
            home, away = _side_value(raws[0], displays[0], spec.unit), _side_value(raws[1], displays[1], spec.unit)
        if home is None and away is None:
            continue
        out.append(
            StatEntry(
                key=spec.key,
                label_tr=spec.label_tr,
                group=spec.group,
                home=home,
                away=away,
                unit=spec.unit,
                home_text=_text(displays[0]),
                away_text=_text(displays[1]),
            )
        )
    for key in order:  # stats this table does not know yet: passed through, source title as label
        if key in used:
            continue
        gkey, s = source[key]
        unit = UNIT_DECIMAL if s.get("format") == "double" else UNIT_COUNT
        raws, displays = _raw_pair(s), _display_pair(s)
        home, away = _side_value(raws[0], displays[0], unit), _side_value(raws[1], displays[1], unit)
        if home is None and away is None:
            continue
        out.append(
            StatEntry(
                key=f"src_{key}",
                label_tr=_str(s.get("title")) or key,
                group=SOURCE_GROUP_MAP.get(gkey, "Genel"),
                home=home,
                away=away,
                unit=unit,
                home_text=_text(displays[0]),
                away_text=_text(displays[1]),
            )
        )
    return out or None


# =========================================================================== shotmap / momentum

_SHOT_PERIOD = {"FirstHalf": "1H", "SecondHalf": "2H", "FirstExtraHalf": "ET", "SecondExtraHalf": "ET"}


def _shot_outcome(s: dict[str, Any]) -> Optional[str]:
    et = s.get("eventType")
    if et == "Goal":
        return "goal"
    if et == "Post":
        return "post"
    if et == "Miss":
        return "missed"
    if et == "AttemptSaved":
        return "blocked" if s.get("isBlocked") else "saved"
    return None


def parse_shotmap(content: dict[str, Any], home_id: Optional[str], away_id: Optional[str]) -> Optional[list[Shot]]:
    sm = content.get("shotmap")
    if not isinstance(sm, dict) or not isinstance(sm.get("shots"), list):
        return None
    shots: list[Shot] = []
    for s in sm["shots"]:
        if not isinstance(s, dict):
            continue
        team = _id(s.get("teamId"))
        side = "home" if team is not None and team == home_id else ("away" if team is not None and team == away_id else None)
        outcome = _shot_outcome(s)
        on_target = outcome in ("goal", "saved")
        situation, body = _str(s.get("situation"), 40), _str(s.get("shotType"), 40)
        shots.append(
            Shot(
                minute=_int(s.get("min")),
                added_time=_int(s.get("minAdded")) or None,
                side=side,
                player=_person(s.get("playerId"), s.get("playerName") or s.get("fullName")),
                x=_float(s.get("x")),
                y=_float(s.get("y")),
                xg=_float(s.get("expectedGoals")),
                xgot=_float(s.get("expectedGoalsOnTarget")) if on_target else None,
                outcome=outcome,
                situation=situation,
                situation_tr=SHOT_SITUATION_TR.get(situation or ""),
                body_part=body,
                body_part_tr=SHOT_BODY_PART_TR.get(body or ""),
                is_own_goal=bool(s.get("isOwnGoal")),
                period=_SHOT_PERIOD.get(_str(s.get("period")) or ""),
            )
        )
    shots.sort(key=lambda sh: (sh.minute if sh.minute is not None else 999, sh.added_time or 0))
    return shots


def parse_momentum(content: dict[str, Any]) -> Optional[list[MomentumPoint]]:
    """``content.matchFacts.momentum.main.data`` (fallback ``content.momentum.main.data``)."""
    for holder in (_dict(content.get("matchFacts")).get("momentum"), content.get("momentum")):
        data = _dict(_dict(holder).get("main")).get("data")
        if isinstance(data, list) and data:
            pts = []
            for d in data:
                if not isinstance(d, dict):
                    continue
                minute, value = _float(d.get("minute")), _float(d.get("value"))
                if minute is None or value is None:
                    continue
                pts.append(
                    MomentumPoint(
                        minute=int(minute) if minute.is_integer() else minute,
                        value=int(value) if value.is_integer() else value,
                    )
                )
            return pts or None
    return None


# =========================================================================== whole body


def _halftime_score(content: dict[str, Any], status: str) -> Optional[ScorePair]:
    if status in (STATUS_SCHEDULED, STATUS_POSTPONED, STATUS_CANCELLED):
        return None
    events = _list(_dict(_dict(content.get("matchFacts")).get("events")).get("events"))
    for e in events:
        if isinstance(e, dict) and e.get("type") == "Half" and (_str(e.get("halfStrShort")) or "").upper() == "HT":
            h, a = _int(e.get("homeScore")), _int(e.get("awayScore"))
            if h is not None and a is not None:
                return ScorePair(home=h, away=a)
    return None


def _penalty_score(status_block: dict[str, Any]) -> Optional[ScorePair]:
    pens = _dict(status_block.get("reason")).get("penalties")
    return _score_pair(pens)


def parse_match_details(
    data: Any,
    *,
    match_id: str,
    provider_match_id: str,
    fetched_at: datetime,
    now: Optional[datetime] = None,
) -> LiveCenterResponse:
    """FotMob matchDetails body -> LiveCenterResponse. Raises LiveCenterPayloadError."""
    if not isinstance(data, dict):
        raise LiveCenterPayloadError("body is not a JSON object")
    general = _dict(data.get("general"))
    header = _dict(data.get("header"))
    content = _dict(data.get("content"))
    body_id = _id(general.get("matchId")) or _id(_dict(content.get("matchFacts")).get("matchId"))
    if body_id is None:
        raise LiveCenterPayloadError("body has no general.matchId")
    if body_id != str(provider_match_id):
        raise LiveCenterPayloadError(f"body is for match {body_id}, requested {provider_match_id}")
    now = now or datetime.now(timezone.utc)
    status_block = _dict(header.get("status"))
    st = parse_status(general, status_block)
    status = st["status"]
    started = status not in (STATUS_SCHEDULED, STATUS_POSTPONED, STATUS_CANCELLED)
    kickoff = _parse_utc(general.get("matchTimeUTCDate")) or _parse_utc(status_block.get("utcTime"))
    missing: list[MissingSection] = []

    # teams + score
    hdr_teams = [t for t in _list(header.get("teams")) if isinstance(t, dict)]
    home_hdr = hdr_teams[0] if len(hdr_teams) == 2 else {}
    away_hdr = hdr_teams[1] if len(hdr_teams) == 2 else {}
    home_gen, away_gen = _dict(general.get("homeTeam")), _dict(general.get("awayTeam"))
    home_id = _id(home_gen.get("id")) or _id(home_hdr.get("id"))
    away_id = _id(away_gen.get("id")) or _id(away_hdr.get("id"))
    poll = _dict(_dict(_dict(content.get("matchFacts")).get("poll")).get("oddspoll"))
    teams = Teams(
        home=TeamInfo(
            id=home_id,
            name=_str(home_gen.get("name")) or _str(home_hdr.get("name")),
            short_name=_str(poll.get("HomeTeam"), 60),
            logo_url=_str(home_hdr.get("imageUrl"), 500),
        ),
        away=TeamInfo(
            id=away_id,
            name=_str(away_gen.get("name")) or _str(away_hdr.get("name")),
            short_name=_str(poll.get("AwayTeam"), 60),
            logo_url=_str(away_hdr.get("imageUrl"), 500),
        ),
    )
    # FotMob sends score 0-0 before kick-off: shown as unknown until the match starts.
    score = ScorePair(home=_int(home_hdr.get("score")), away=_int(away_hdr.get("score"))) if started else ScorePair()

    # info box
    info = _dict(_dict(content.get("matchFacts")).get("infoBox"))
    stadium = _dict(info.get("Stadium"))
    referee = _dict(info.get("Referee"))
    tournament = _dict(info.get("Tournament"))

    # events
    events = parse_events(content)
    if events is None:
        if started:
            missing.append(_missing("events", "events_not_provided"))
        events_list: list[LiveEvent] = []
    else:
        events_list = events
    tallies = _player_tallies(events) if started else None

    # lineups
    lu = _dict(content.get("lineup"))
    lineups = {}
    for side, key in (("home", "homeTeam"), ("away", "awayTeam")):
        team_raw = _dict(lu.get(key))
        lineup, layout_ok = parse_team_lineup(team_raw, lu.get("lineupType"), tallies, events)
        lineups[side] = lineup
        if not lineup.starters:
            missing.append(_missing(f"lineups.{side}", "lineup_not_announced"))
        elif not layout_ok:
            missing.append(_missing(f"lineups.{side}.grid", "no_layout"))

    # stats
    periods = _dict(_dict(content.get("stats")).get("Periods"))
    stats_all = parse_stats_period(periods.get("All"))
    first_half = parse_stats_period(periods.get("FirstHalf"))
    second_half = parse_stats_period(periods.get("SecondHalf"))
    if stats_all is None:
        missing.append(_missing("stats", "not_started" if not started else "not_provided"))
    elif status in (STATUS_FINISHED,) and (first_half is None or second_half is None):
        missing.append(_missing("stats.halves", "half_stats_not_provided"))

    # shotmap
    shotmap = parse_shotmap(content, home_id, away_id)
    if not started:
        shotmap = None
        missing.append(_missing("shotmap", "not_started"))
    elif shotmap is None:
        missing.append(_missing("shotmap", "shotmap_not_covered"))
    elif not shotmap:
        total = next((s for s in (stats_all or []) if s.key == "total_shots"), None)
        if total is None or (total.home or 0) + (total.away or 0) > 0:
            # shots were taken (or the count is unknown) but no shot was mapped
            shotmap = None
            missing.append(_missing("shotmap", "shotmap_not_covered"))

    # momentum
    momentum = parse_momentum(content) if started else None
    if not started:
        missing.append(_missing("momentum", "not_started"))
    elif momentum is None:
        missing.append(_missing("momentum", "momentum_not_provided"))

    return LiveCenterResponse(
        match_id=match_id,
        provider=PROVIDER_FOTMOB,
        provider_match_id=body_id,
        fetched_at=fetched_at,
        cache_ttl_seconds=ttl_for(status, kickoff, now),
        status=status,
        status_text=st["status_text"],
        minute=st["minute"],
        added_time=st["added_time"],
        period=st["period"],
        kickoff=kickoff,
        competition=_str(general.get("leagueName")) or _str(tournament.get("leagueName")),
        competition_id=_id(general.get("parentLeagueId")) or _id(general.get("leagueId")),
        round=_str(general.get("leagueRoundName")) or _str(tournament.get("roundName")),
        venue=_str(stadium.get("name")),
        venue_city=_str(stadium.get("city")),
        referee=_str(referee.get("text")),
        attendance=_int(info.get("Attendance")),
        score=score,
        halftime_score=_halftime_score(content, status),
        penalty_score=_penalty_score(status_block),
        teams=teams,
        events=events_list,
        lineups=Lineups(home=lineups["home"], away=lineups["away"]),
        stats=Stats(all=stats_all or [], first_half=first_half, second_half=second_half),
        shotmap=shotmap,
        momentum=momentum,
        missing=missing,
    )


__all__ = [
    "ERROR_MESSAGES_TR",
    "LiveCenterPayloadError",
    "compute_grid",
    "parse_events",
    "parse_match_details",
    "parse_minute_text",
    "parse_momentum",
    "parse_shotmap",
    "parse_stats_period",
    "parse_status",
    "parse_team_lineup",
    "position_group",
    "ttl_for",
]
