"""Pure parsers for FotMob raw bodies used by the team-news live layer.

Shared by the live refresh (app/services/team_news/service.py) and the offline
backfill (scripts/live/load_player_data.py). No I/O, no database access.

Endpoints (raw JSON bodies, exactly as returned):
  * /api/data/teams?id=<team>          -> parse_team_payload
  * /api/data/playerData?id=<player>   -> parse_player_payload
  * /api/data/matchDetails?matchId=<m> -> parse_match_payload

Honesty rule (AGENTS.md 8-14): a value the source does not send is ``None``;
0 is kept only when the source sends 0. The only derived values are documented
where they are computed (``appeared``, card counts, broad role labels).
Player-stat field paths mirror scripts/data_collection/collect_fotmob_details.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from app.services.team_news.constants import (
    RAW_TYPE_TO_STATUS,
    SOURCE_MATCH_LINEUP,
    SOURCE_PLAYER_PROFILE,
    SOURCE_TEAM_SQUAD,
    STATUS_DOUBTFUL,
    STATUS_INJURED,
    STATUS_INTERNATIONAL_DUTY,
    STATUS_OTHER,
)


class PayloadError(ValueError):
    """The body is not a usable payload of the expected endpoint."""


# --------------------------------------------------------------------------- helpers


def to_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def to_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_str_id(value: Any) -> Optional[str]:
    """Provider ids are stored as text ("9825"); ints and numeric strings map alike."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    return text or None


def parse_utc(value: Any) -> Optional[datetime]:
    """FotMob time strings ("2026-10-13T19:00:00.000Z", "2026-10-14T19:00:00Z",
    "2026-08-01T00:00:00+00:00") or {"utcTime": ...} objects -> aware UTC datetime."""
    if isinstance(value, dict):
        value = value.get("utcTime")
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _date_only(value: Any) -> Optional[str]:
    """ISO date (YYYY-MM-DD) from "2001-03-24", "2001-03-24T00:00:00.000Z" or {"utcTime": ...}."""
    if isinstance(value, dict):
        value = value.get("utcTime")
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return None


def _clean_text(value: Any, max_len: int) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text[:max_len] if text else None


def status_for_raw_type(raw_type: Optional[str]) -> str:
    """Map a FotMob unavailability type to the layer's status vocabulary.

    Unknown or missing types map to "other" (the raw type is stored as sent)."""
    if not raw_type:
        return STATUS_OTHER
    if raw_type in RAW_TYPE_TO_STATUS:
        return RAW_TYPE_TO_STATUS[raw_type]
    if "doubt" in raw_type.lower():
        return STATUS_DOUBTFUL
    return STATUS_OTHER


# --------------------------------------------------------------------------- data classes


@dataclass
class PlayerObservation:
    """Profile facts about one player as sent by one source at one time."""

    provider_id: str
    source: str
    observed_at: Optional[datetime]
    name: Optional[str] = None
    date_of_birth: Optional[str] = None
    nationality: Optional[str] = None
    country_code: Optional[str] = None
    position: Optional[str] = None  # broad role label as sent ("Defender")
    primary_position: Optional[str] = None  # detailed label as sent ("Center Back")
    positions: Optional[list[dict[str, Any]]] = None
    shirt_number: Optional[int] = None
    height_cm: Optional[int] = None
    preferred_foot: Optional[str] = None
    team_provider_id: Optional[str] = None
    market_value_eur: Optional[int] = None
    market_value_as_of: Optional[datetime] = None
    contract_end: Optional[str] = None


@dataclass
class AvailabilityObservation:
    """One availability report for one player, as sent."""

    player_provider_id: str
    status: str
    raw_type: Optional[str] = None
    reason: Optional[str] = None
    injury_id: Optional[str] = None
    expected_return: Optional[str] = None
    expected_return_date: Optional[str] = None
    source_updated_at: Optional[datetime] = None
    team_provider_id: Optional[str] = None
    player_name: Optional[str] = None

    def report_key(self) -> tuple:
        """Fields whose change means a different report (old row is superseded)."""
        return (
            self.status,
            self.raw_type,
            self.reason,
            self.injury_id,
            self.expected_return,
            self.expected_return_date,
        )


@dataclass
class ParsedSquadMember:
    player: PlayerObservation
    role: Optional[str]
    role_key: Optional[str]
    shirt_number: Optional[int]
    availability: Optional[AvailabilityObservation]


@dataclass
class ParsedTeam:
    team_provider_id: str
    team_name: Optional[str]
    season: Optional[str]
    squad_sent: bool  # squad.squad was a list (False: no squad in the payload)
    members: list[ParsedSquadMember] = field(default_factory=list)
    skipped_non_players: int = 0  # coach entries (not players) skipped


@dataclass
class ParsedPlayerProfile:
    player: PlayerObservation
    availability: list[AvailabilityObservation]
    # True when the payload carries the injuryInformation/internationalDuty keys
    # (null = "nothing reported"); False when both keys are absent, i.e. the
    # payload cannot confirm or clear an earlier report.
    availability_sent: bool
    recent_matches: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ParsedLineupSide:
    side: str
    team_provider_id: Optional[str]
    team_name: Optional[str]
    formation: Optional[str]
    starters: list[dict[str, Any]]
    bench: Optional[list[dict[str, Any]]]  # None: the source sent no bench list
    unavailable: Optional[list[AvailabilityObservation]]  # None: the key was not sent
    players: list[PlayerObservation]
    based_on_match_id: Optional[str] = None  # lastStarting11: <side>Team.lastMatch.matchId

    @property
    def has_lineup(self) -> bool:
        return bool(self.starters)


@dataclass
class ParsedMatch:
    provider_match_id: str
    kickoff_at: Optional[datetime]
    competition_provider_id: Optional[str]
    league_id: Optional[str]
    home_team_provider_id: Optional[str]
    away_team_provider_id: Optional[str]
    home_team_name: Optional[str]
    away_team_name: Optional[str]
    status: str  # scheduled|started|finished|cancelled (from FotMob flags)
    home_score: Optional[int]
    away_score: Optional[int]
    lineup_type: Optional[str]
    lineup_source: Optional[str]
    sides: dict[str, ParsedLineupSide]
    player_stats: list[dict[str, Any]]  # only for finished matches
    events_sent: bool  # content.matchFacts.events.events was a list (card counts possible)


# --------------------------------------------------------------------------- teams


def parse_team_payload(data: Any, observed_at: Optional[datetime]) -> ParsedTeam:
    """/api/data/teams?id=<team> body -> squad members + squad injury list.

    Paths: details.id/name/latestSeason (fallback overview.season),
    squad.squad[*] {title, members[*]}. Coach entries (role.key == "coach" or
    the "coach" group) are not players and are skipped.
    Member fields: id, name, shirtNumber, ccode, cname, role{key, fallback},
    positionIds ("64,75,32"), positionIdsDesc ("CDM,CM,RB"), height, dateOfBirth,
    transferValue (EUR, no valuation date sent), injured, injury{id, expectedReturn}.
    """
    if not isinstance(data, dict):
        raise PayloadError("team payload is not an object")
    details = data.get("details") or {}
    team_id = to_str_id(details.get("id"))
    if team_id is None:
        raise PayloadError("details.id missing")
    season = _clean_text(details.get("latestSeason"), 20)
    if season is None:
        season = _clean_text((data.get("overview") or {}).get("season"), 20)

    squad_block = data.get("squad")
    groups = squad_block.get("squad") if isinstance(squad_block, dict) else None
    parsed = ParsedTeam(
        team_provider_id=team_id,
        team_name=_clean_text(details.get("name"), 200),
        season=season,
        # an empty squad list (seen for some teams) is treated like "not sent":
        # it must not clear injuries observed earlier
        squad_sent=isinstance(groups, list)
        and any(isinstance(g, dict) and g.get("members") for g in groups),
    )
    if not isinstance(groups, list):
        return parsed

    seen: set[str] = set()
    for group in groups:
        if not isinstance(group, dict):
            continue
        title = _clean_text(group.get("title"), 50)
        for m in group.get("members") or []:
            if not isinstance(m, dict):
                continue
            role = m.get("role") if isinstance(m.get("role"), dict) else {}
            role_key = _clean_text(role.get("key"), 50)
            if title == "coach" or role_key == "coach":
                parsed.skipped_non_players += 1
                continue
            pid = to_str_id(m.get("id"))
            if pid is None or pid in seen:
                continue
            seen.add(pid)
            shirt = to_int(m.get("shirtNumber"))
            player = PlayerObservation(
                provider_id=pid,
                source=SOURCE_TEAM_SQUAD,
                observed_at=observed_at,
                name=_clean_text(m.get("name"), 200),
                date_of_birth=_date_only(m.get("dateOfBirth")),
                nationality=_clean_text(m.get("cname"), 100),
                country_code=_clean_text(m.get("ccode"), 10),
                position=_clean_text(role.get("fallback"), 50),
                positions=_squad_positions(m.get("positionIds"), m.get("positionIdsDesc")),
                shirt_number=shirt,
                height_cm=to_int(m.get("height")),
                team_provider_id=team_id,
                market_value_eur=to_int(m.get("transferValue")),
                market_value_as_of=None,  # the squad endpoint sends no valuation date
            )
            availability = None
            injury = m.get("injury") if isinstance(m.get("injury"), dict) else None
            if m.get("injured") is True or injury is not None:
                availability = AvailabilityObservation(
                    player_provider_id=pid,
                    status=STATUS_INJURED,
                    raw_type="injured",  # squad flag `injured: true` / `injury` object
                    injury_id=to_str_id((injury or {}).get("id")),
                    expected_return=_clean_text((injury or {}).get("expectedReturn"), 100),
                    team_provider_id=team_id,
                    player_name=player.name,
                )
            parsed.members.append(
                ParsedSquadMember(
                    player=player,
                    role=title,
                    role_key=role_key,
                    shirt_number=shirt,
                    availability=availability,
                )
            )
    return parsed


def _squad_positions(ids: Any, labels: Any) -> Optional[list[dict[str, Any]]]:
    """"64,75,32" + "CDM,CM,RB" -> [{"id": 64, "label": "CDM"}, ...] (as sent, same order)."""
    id_list = [to_int(x) for x in str(ids).split(",")] if ids not in (None, "") else []
    label_list = [x.strip() for x in str(labels).split(",")] if labels not in (None, "") else []
    n = max(len(id_list), len(label_list))
    if n == 0:
        return None
    out = []
    for i in range(n):
        out.append(
            {
                "id": id_list[i] if i < len(id_list) else None,
                "label": (label_list[i] or None) if i < len(label_list) else None,
            }
        )
    return out


# --------------------------------------------------------------------------- players


def _player_info_value(items: Any, translation_key: str) -> Optional[dict[str, Any]]:
    for item in items or []:
        if isinstance(item, dict) and item.get("translationKey") == translation_key:
            return item
    return None


def parse_player_payload(data: Any, observed_at: Optional[datetime]) -> ParsedPlayerProfile:
    """/api/data/playerData?id=<player> body -> profile + availability.

    Paths: id, name, birthDate.utcTime, contractEnd.utcTime, primaryTeam.teamId,
    positionDescription.primaryPosition.label, positionDescription.positions[*]
    (position, strPosShort.label, strPos.label, isMainPosition),
    playerInformation[*] by translationKey (height_sentencecase, shirt,
    preferred_foot, country_sentencecase), marketValues.values[*] {date, value,
    currency} (latest date with currency EUR), injuryInformation {name, key,
    expectedReturn.expectedReturnFallback, lastUpdated}, internationalDuty,
    recentMatches[*] (kept raw for callers).
    """
    if not isinstance(data, dict):
        raise PayloadError("player payload is not an object")
    pid = to_str_id(data.get("id"))
    if pid is None:
        raise PayloadError("id missing")
    info = data.get("playerInformation")

    height = _player_info_value(info, "height_sentencecase")
    shirt = _player_info_value(info, "shirt")
    foot = _player_info_value(info, "preferred_foot")
    country = _player_info_value(info, "country_sentencecase")

    pos_desc = data.get("positionDescription") if isinstance(data.get("positionDescription"), dict) else {}
    positions = []
    for p in pos_desc.get("positions") or []:
        if not isinstance(p, dict):
            continue
        positions.append(
            {
                "id": to_int(p.get("position")),
                "label": ((p.get("strPosShort") or {}).get("label")),
                "name": ((p.get("strPos") or {}).get("label")),
                "is_main": p.get("isMainPosition") if isinstance(p.get("isMainPosition"), bool) else None,
            }
        )

    mv_value, mv_date = None, None
    mv = data.get("marketValues")
    values = mv.get("values") if isinstance(mv, dict) else None
    if isinstance(values, list):
        dated = [
            (parse_utc(v.get("date")), v)
            for v in values
            if isinstance(v, dict) and v.get("currency") == "EUR" and to_int(v.get("value")) is not None
        ]
        dated = [(d, v) for d, v in dated if d is not None]
        if dated:
            mv_date, latest = max(dated, key=lambda x: x[0])
            mv_value = to_int(latest.get("value"))

    primary_team = data.get("primaryTeam") if isinstance(data.get("primaryTeam"), dict) else {}
    player = PlayerObservation(
        provider_id=pid,
        source=SOURCE_PLAYER_PROFILE,
        observed_at=observed_at,
        name=_clean_text(data.get("name"), 200),
        date_of_birth=_date_only(data.get("birthDate")),
        nationality=_clean_text(((country or {}).get("value") or {}).get("fallback"), 100),
        country_code=_clean_text((country or {}).get("countryCode"), 10),
        primary_position=_clean_text((pos_desc.get("primaryPosition") or {}).get("label"), 50),
        positions=positions or None,
        shirt_number=to_int(((shirt or {}).get("value") or {}).get("numberValue")),
        height_cm=to_int(((height or {}).get("value") or {}).get("numberValue")),
        preferred_foot=_clean_text(((foot or {}).get("value") or {}).get("key"), 20),
        team_provider_id=to_str_id(primary_team.get("teamId")),
        market_value_eur=mv_value,
        market_value_as_of=mv_date,
        contract_end=_date_only(data.get("contractEnd")),
    )

    availability: list[AvailabilityObservation] = []
    injury = data.get("injuryInformation")
    if isinstance(injury, dict):
        expected = injury.get("expectedReturn") if isinstance(injury.get("expectedReturn"), dict) else {}
        key = _clean_text(injury.get("key"), 50)
        injury_id = key[len("injury_"):] if key and key.startswith("injury_") else None
        availability.append(
            AvailabilityObservation(
                player_provider_id=pid,
                status=STATUS_INJURED,
                raw_type=key or "injuryInformation",
                reason=_clean_text(injury.get("name"), 200),
                injury_id=injury_id,
                expected_return=_clean_text(expected.get("expectedReturnFallback"), 100),
                expected_return_date=_clean_text(expected.get("expectedReturnDateParam"), 40),
                source_updated_at=parse_utc(injury.get("lastUpdated")),
                team_provider_id=player.team_provider_id,
                player_name=player.name,
            )
        )
    duty = data.get("internationalDuty")
    if duty:
        reason = None
        if isinstance(duty, dict):
            reason = _clean_text(duty.get("name") or duty.get("teamName") or duty.get("fallback"), 200)
        elif isinstance(duty, str):
            reason = _clean_text(duty, 200)
        availability.append(
            AvailabilityObservation(
                player_provider_id=pid,
                status=STATUS_INTERNATIONAL_DUTY,
                raw_type="internationalDuty",
                reason=reason,
                team_provider_id=player.team_provider_id,
                player_name=player.name,
            )
        )
    recent = data.get("recentMatches")
    return ParsedPlayerProfile(
        player=player,
        availability=availability,
        availability_sent=("injuryInformation" in data) or ("internationalDuty" in data),
        recent_matches=[m for m in recent if isinstance(m, dict)] if isinstance(recent, list) else [],
    )


# --------------------------------------------------------------------------- matches

# playerStats keys (stable `key`, never the English title) -> output field.
PLAYER_STAT_KEYS = {
    "rating_title": "rating",
    "minutes_played": "minutes",
    "goals": "goals",
    "assists": "assists",
    "expected_goals": "xg",
    "expected_assists": "xa",
    "expected_goals_on_target_variant": "xgot",
    "expected_goals_non_penalty": "npxg",
    "total_shots": "shots",
    "ShotsOnTarget": "shots_on_target",
}


def _player_stat_values(entry: Optional[dict[str, Any]]) -> dict[str, Any]:
    found: dict[str, Any] = {}
    if not entry:
        return found
    for block in entry.get("stats") or []:
        if not isinstance(block, dict):
            continue
        for _title, sv in (block.get("stats") or {}).items():
            if not isinstance(sv, dict):
                continue
            key = sv.get("key")
            if key in PLAYER_STAT_KEYS and PLAYER_STAT_KEYS[key] not in found:
                stat = sv.get("stat") or {}
                if "value" in stat:
                    found[PLAYER_STAT_KEYS[key]] = stat.get("value")
    return found


def _sub_minutes(perf: dict[str, Any]) -> tuple[Optional[int], Optional[int]]:
    sub_in = sub_out = None
    for ev in perf.get("substitutionEvents") or []:
        if not isinstance(ev, dict):
            continue
        if ev.get("type") == "subIn" and sub_in is None:
            sub_in = to_int(ev.get("time"))
        elif ev.get("type") == "subOut" and sub_out is None:
            sub_out = to_int(ev.get("time"))
    return sub_in, sub_out


def _card_counts(content: dict[str, Any]) -> tuple[bool, dict[str, list[int]]]:
    """Card events from content.matchFacts.events.events (type == "Card").

    Returns (events_sent, {player id: [yellow, red]}). yellow = events with
    card "Yellow"; red = events with card "Red" or "YellowRed" (a second-yellow
    dismissal therefore counts as yellow 1 + red 1). Derived counts: only
    meaningful when events_sent is True.
    """
    mf = content.get("matchFacts")
    events = (mf.get("events") or {}).get("events") if isinstance(mf, dict) and isinstance(mf.get("events"), dict) else None
    if not isinstance(events, list):
        return False, {}
    counts: dict[str, list[int]] = {}
    for ev in events:
        if not isinstance(ev, dict) or ev.get("type") != "Card":
            continue
        pid = to_str_id((ev.get("player") or {}).get("id") if isinstance(ev.get("player"), dict) else None)
        if pid is None:
            pid = to_str_id(ev.get("playerId"))
        if pid is None:
            continue
        c = counts.setdefault(pid, [0, 0])
        card = ev.get("card")
        if card == "Yellow":
            c[0] += 1
        elif card in ("Red", "YellowRed"):
            c[1] += 1
    return True, counts


def _lineup_entry(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": to_int(p.get("id")),
        "name": _clean_text(p.get("name"), 200),
        "shirt_number": to_int(p.get("shirtNumber")),
        "position_id": to_int(p.get("positionId")),
        "usual_position_id": to_int(p.get("usualPlayingPositionId")),
    }


def _match_status(general: dict[str, Any], status: dict[str, Any]) -> str:
    if status.get("cancelled"):
        return "cancelled"
    if general.get("finished") or status.get("finished"):
        return "finished"
    if general.get("started") or status.get("started"):
        return "started"
    return "scheduled"


def parse_match_payload(data: Any, fetched_at: Optional[datetime]) -> ParsedMatch:
    """/api/data/matchDetails?matchId=<id> body -> header, line-ups, unavailable lists,
    and (finished matches only) per-player stats.

    Line-up paths: content.lineup.lineupType / .source, content.lineup.{homeTeam,
    awayTeam}.{id, name, formation, starters[*], subs[*], unavailable[*]}.
    `unavailable` absent -> None (list not sent); present and empty -> [] (nothing listed).
    Unavailable entry: id, name, unavailability{type, injuryId, expectedReturn,
    expectedReturnDate}.
    """
    if not isinstance(data, dict):
        raise PayloadError("matchDetails payload is not an object")
    general = data.get("general") or {}
    header = data.get("header") or {}
    content = data.get("content") or {}
    status = header.get("status") or {}
    match_id = to_str_id(general.get("matchId"))
    if match_id is None:
        raise PayloadError("general.matchId missing")

    teams = header.get("teams") if isinstance(header.get("teams"), list) else []
    home_general = general.get("homeTeam") or {}
    away_general = general.get("awayTeam") or {}
    home_id = to_str_id(home_general.get("id")) or (to_str_id(teams[0].get("id")) if len(teams) == 2 else None)
    away_id = to_str_id(away_general.get("id")) or (to_str_id(teams[1].get("id")) if len(teams) == 2 else None)
    match_status = _match_status(general, status)

    lineup = content.get("lineup") if isinstance(content.get("lineup"), dict) else {}
    kickoff = parse_utc(general.get("matchTimeUTCDate")) or parse_utc(status.get("utcTime"))
    sides: dict[str, ParsedLineupSide] = {}
    for side, key, fallback_id, fallback_name in (
        ("home", "homeTeam", home_id, home_general.get("name")),
        ("away", "awayTeam", away_id, away_general.get("name")),
    ):
        t = lineup.get(key) if isinstance(lineup.get(key), dict) else {}
        team_id = to_str_id(t.get("id")) or fallback_id
        starters_raw = [p for p in (t.get("starters") or []) if isinstance(p, dict)]
        subs_raw = t.get("subs")
        players: list[PlayerObservation] = []
        for p in starters_raw + [p for p in (subs_raw or []) if isinstance(p, dict)]:
            pid = to_str_id(p.get("id"))
            if pid is None:
                continue
            players.append(
                PlayerObservation(
                    provider_id=pid,
                    source=SOURCE_MATCH_LINEUP,
                    observed_at=fetched_at,
                    name=_clean_text(p.get("name"), 200),
                    nationality=_clean_text(p.get("countryName"), 100),
                    country_code=_clean_text(p.get("countryCode"), 10),
                )
            )
        unavailable = None
        if isinstance(t.get("unavailable"), list):
            unavailable = []
            for u in t["unavailable"]:
                if not isinstance(u, dict):
                    continue
                pid = to_str_id(u.get("id"))
                if pid is None:
                    continue
                un = u.get("unavailability") if isinstance(u.get("unavailability"), dict) else {}
                raw_type = _clean_text(un.get("type"), 50)
                unavailable.append(
                    AvailabilityObservation(
                        player_provider_id=pid,
                        status=status_for_raw_type(raw_type),
                        raw_type=raw_type,
                        injury_id=to_str_id(un.get("injuryId")),
                        expected_return=_clean_text(un.get("expectedReturn"), 100),
                        expected_return_date=_clean_text(un.get("expectedReturnDate"), 40),
                        team_provider_id=team_id,
                        player_name=_clean_text(u.get("name"), 200),
                    )
                )
                players.append(
                    PlayerObservation(
                        provider_id=pid,
                        source=SOURCE_MATCH_LINEUP,
                        observed_at=fetched_at,
                        name=_clean_text(u.get("name"), 200),
                        nationality=_clean_text(u.get("countryName"), 100),
                        country_code=_clean_text(u.get("countryCode"), 10),
                    )
                )
        sides[side] = ParsedLineupSide(
            side=side,
            team_provider_id=team_id,
            team_name=_clean_text(t.get("name") or fallback_name, 200),
            formation=_clean_text(t.get("formation"), 20),
            starters=[_lineup_entry(p) for p in starters_raw],
            bench=[_lineup_entry(p) for p in subs_raw if isinstance(p, dict)] if isinstance(subs_raw, list) else None,
            unavailable=unavailable,
            players=players,
            based_on_match_id=to_str_id((t.get("lastMatch") or {}).get("matchId"))
            if isinstance(t.get("lastMatch"), dict)
            else None,
        )

    events_sent, cards = _card_counts(content)
    player_stats: list[dict[str, Any]] = []
    if match_status == "finished":
        player_stats = _player_stat_rows(lineup, content, sides, cards, events_sent, home_id, away_id)

    return ParsedMatch(
        provider_match_id=match_id,
        kickoff_at=kickoff,
        competition_provider_id=to_str_id(general.get("parentLeagueId")) or to_str_id(general.get("leagueId")),
        league_id=to_str_id(general.get("leagueId")),
        home_team_provider_id=home_id,
        away_team_provider_id=away_id,
        home_team_name=_clean_text(home_general.get("name"), 200),
        away_team_name=_clean_text(away_general.get("name"), 200),
        status=match_status,
        home_score=to_int(teams[0].get("score")) if len(teams) == 2 else None,
        away_score=to_int(teams[1].get("score")) if len(teams) == 2 else None,
        lineup_type=_clean_text(lineup.get("lineupType"), 30),
        lineup_source=_clean_text(lineup.get("source"), 50),
        sides=sides,
        player_stats=player_stats,
        events_sent=events_sent,
    )


def _player_stat_rows(
    lineup: dict[str, Any],
    content: dict[str, Any],
    sides: dict[str, ParsedLineupSide],
    cards: dict[str, list[int]],
    events_sent: bool,
    home_id: Optional[str],
    away_id: Optional[str],
) -> list[dict[str, Any]]:
    player_stats_block = content.get("playerStats") if isinstance(content.get("playerStats"), dict) else {}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for side, key in (("home", "homeTeam"), ("away", "awayTeam")):
        t = lineup.get(key) if isinstance(lineup.get(key), dict) else {}
        team_id = sides[side].team_provider_id or (home_id if side == "home" else away_id)
        for is_starter, plist in ((True, t.get("starters") or []), (False, t.get("subs") or [])):
            for p in plist:
                if not isinstance(p, dict):
                    continue
                pid = to_str_id(p.get("id"))
                if pid is None or pid in seen:
                    continue
                seen.add(pid)
                entry = player_stats_block.get(pid)
                entry = entry if isinstance(entry, dict) else None
                vals = _player_stat_values(entry)
                perf = p.get("performance") if isinstance(p.get("performance"), dict) else {}
                sub_in, sub_out = _sub_minutes(perf)
                rating = to_float(vals.get("rating"))
                if rating is None:
                    rating = to_float(perf.get("rating"))
                shotmap = entry.get("shotmap") if entry else None
                card = cards.get(pid)
                rows.append(
                    {
                        "player_provider_id": pid,
                        "name": _clean_text(p.get("name"), 200),
                        "team_provider_id": team_id,
                        "side": side,
                        "started": is_starter,
                        # derived: starter, or came on (a subIn event exists)
                        "appeared": bool(is_starter or sub_in is not None),
                        "minutes": to_int(vals.get("minutes")),
                        "rating": rating,
                        "goals": to_int(vals.get("goals")),
                        "assists": to_int(vals.get("assists")),
                        "xg": to_float(vals.get("xg")),
                        "xa": to_float(vals.get("xa")),
                        "npxg": to_float(vals.get("npxg")),
                        "xgot": to_float(vals.get("xgot")),
                        "shots": to_int(vals.get("shots")),
                        "shots_on_target": to_int(vals.get("shots_on_target")),
                        "yellow_cards": (card[0] if card else 0) if events_sent else None,
                        "red_cards": (card[1] if card else 0) if events_sent else None,
                        "position_id": to_int(p.get("positionId")),
                        "usual_position_id": to_int(p.get("usualPlayingPositionId")),
                        "is_goalkeeper": entry.get("isGoalkeeper") if entry and isinstance(entry.get("isGoalkeeper"), bool) else None,
                        "sub_in_minute": sub_in,
                        "sub_out_minute": sub_out,
                        "stats_available": bool(entry and entry.get("stats")),
                        "shotmap_count": len(shotmap) if isinstance(shotmap, list) else None,
                        "market_value_eur": to_int(p.get("marketValue")),
                    }
                )
    return rows


def lineup_content(side: ParsedLineupSide, lineup_type: Optional[str], lineup_source: Optional[str]) -> dict[str, Any]:
    """Canonical content of a line-up observation (hashed to detect changes)."""
    return {
        "lineup_type": lineup_type,
        "lineup_source": lineup_source,
        "formation": side.formation,
        "team_provider_id": side.team_provider_id,
        "based_on_match_id": side.based_on_match_id,
        "starters": side.starters,
        "bench": side.bench,
    }


# --------------------------------------------------------------------------- league fixtures


@dataclass
class FixtureRef:
    provider_match_id: str
    competition_provider_id: str
    kickoff_at: Optional[datetime]
    home_team_provider_id: Optional[str]
    away_team_provider_id: Optional[str]
    home_team_name: Optional[str]
    away_team_name: Optional[str]
    status: str  # scheduled|started|finished|cancelled


def parse_league_fixtures(data: Any, competition_provider_id: str) -> list[FixtureRef]:
    """/api/data/leagues?id=<league> body -> fixtures.allMatches[*] of the season sent.

    Fields: id, home{id, name}, away{id, name}, status{utcTime, started,
    finished, cancelled}. Used for discovery (which matches/teams to refresh).
    """
    if not isinstance(data, dict):
        raise PayloadError("league payload is not an object")
    fixtures = data.get("fixtures") if isinstance(data.get("fixtures"), dict) else {}
    out: list[FixtureRef] = []
    for m in fixtures.get("allMatches") or []:
        if not isinstance(m, dict):
            continue
        mid = to_str_id(m.get("id"))
        if mid is None:
            continue
        status = m.get("status") if isinstance(m.get("status"), dict) else {}
        home = m.get("home") if isinstance(m.get("home"), dict) else {}
        away = m.get("away") if isinstance(m.get("away"), dict) else {}
        out.append(
            FixtureRef(
                provider_match_id=mid,
                competition_provider_id=str(competition_provider_id),
                kickoff_at=parse_utc(status.get("utcTime")),
                home_team_provider_id=to_str_id(home.get("id")),
                away_team_provider_id=to_str_id(away.get("id")),
                home_team_name=_clean_text(home.get("name"), 200),
                away_team_name=_clean_text(away.get("name"), 200),
                status=_match_status({}, status),
            )
        )
    return out
