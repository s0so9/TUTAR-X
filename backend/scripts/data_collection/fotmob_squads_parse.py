"""Pure parsers for the FotMob squads/players dataset (no network, no file IO).

Used by ``collect_fotmob_squads_players.py`` (collector, --from-raw rebuild, coverage) and usable
by any loader that reads the raw cache directly:
  backend/data/raw_cache/fotmob_squads_leagues/<league>_<YYYY-YYYY>.json.gz  -> parse_league
  backend/data/raw_cache/fotmob_teams/<team id>.json.gz                      -> parse_team / team_roster
  backend/data/raw_cache/fotmob_players/<player id>.json.gz                  -> parse_player
Field definitions: backend/data/players/README_players.md.

Honesty (AGENTS.md 8-14): values are copied as sent; a value FotMob does not send is null (also
list lengths and squad counts: null when the list itself is not sent, never 0 / []).
Three FotMob "unknown" placeholders are decoded to null, each with the sent value kept beside it:
``recentMatches[*].ratingProps.rating == 0`` -> ``rating`` null (``rating_raw``);
``birthDate.utcTime == "0001-01-01..."`` -> ``birth_date`` null (``birth_date_raw``);
squad-list / line-up ``age == 0`` -> ``age`` null (``age_raw``).
"""

from __future__ import annotations

from typing import Any, Iterator

DOMESTIC_LEAGUES: dict[int, str] = {
    47: "Premier League",
    87: "LaLiga",
    55: "Serie A",
    54: "Bundesliga",
    53: "Ligue 1",
    57: "Eredivisie",
    61: "Liga Portugal",
    40: "Belgian Pro League",
    71: "Super Lig",
    122: "Czech 1. Liga",
}
EURO_CUPS: dict[int, str] = {42: "Champions League", 73: "Europa League", 10216: "Conference League"}
TARGET13: list[int] = [*DOMESTIC_LEAGUES, *EURO_CUPS]

# squad.squad[*].members[*].role.key of players (observed) and the squad group titles
PLAYER_ROLE_KEYS = frozenset({"keeper_long", "defender_long", "midfielder_long", "attacker_long"})
PLAYER_GROUP_TITLES = frozenset({"keepers", "defenders", "midfielders", "attackers"})
COACH_ROLE_KEYS = frozenset({"coach"})
COACH_GROUP_TITLES = frozenset({"coach"})


# --------------------------------------------------------------------------- helpers


def _to_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


# FotMob's placeholder for an unknown birth date: playerData ``birthDate.utcTime == "0001-01-01T00:00:00.000Z"``
# (4 players on 2026-10-13; for the same players the squad page sends ``dateOfBirth: null`` and ``age: 0``).
BIRTH_DATE_PLACEHOLDER_PREFIX = "0001-01-01"


def birth_date(raw: Any) -> Any:
    """playerData ``birthDate.utcTime`` as sent, except FotMob's "unknown" placeholder ``0001-01-01...`` -> null
    (the sent value is kept in ``birth_date_raw``)."""
    if isinstance(raw, str) and raw.startswith(BIRTH_DATE_PLACEHOLDER_PREFIX):
        return None
    return raw


def listed_age(raw: Any) -> Any:
    """Squad-list / line-up ``age`` as sent, except ``0`` (FotMob sends it when the birth date is unknown;
    no player is 0 years old) -> null (the sent value is kept in ``age_raw``)."""
    if raw == 0 and not isinstance(raw, bool):
        return None
    return raw


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


# --------------------------------------------------------------------------- parsing: leagues


def _iter_table_rows(node: Any) -> Iterator[dict]:
    """Team rows of a league table payload: ``data.table.all`` and nested ``data.tables[*]``."""
    if not isinstance(node, dict):
        return
    table = node.get("table")
    if isinstance(table, dict):
        for row in _list(table.get("all")):
            if isinstance(row, dict):
                yield row
    for sub in _list(node.get("tables")):
        yield from _iter_table_rows(sub)


def parse_league(data: dict, league_id: int, snapshot_at: str | None) -> dict:
    """Teams of one league/season response: table rows (``table[*].data``) and fixtures
    (``fixtures.allMatches[*].home/away``)."""
    details = _dict(data.get("details"))
    teams: dict[int, dict] = {}

    def entry(tid: int, name: Any) -> dict:
        e = teams.setdefault(
            tid, {"team_id": tid, "name": None, "in_table": False, "in_fixtures": False, "fixture_matches": 0}
        )
        if e["name"] is None and name:
            e["name"] = name
        return e

    for t in _list(data.get("table")):
        for row in _iter_table_rows(_dict(t).get("data")):
            tid = _to_int(row.get("id"))
            if tid is not None:
                entry(tid, row.get("name"))["in_table"] = True
    matches = _list(_dict(data.get("fixtures")).get("allMatches"))
    for m in matches:
        for side in ("home", "away"):
            side_team = _dict(_dict(m).get(side))
            tid = _to_int(side_team.get("id"))
            if tid is None:
                continue
            e = entry(tid, side_team.get("name"))
            e["in_fixtures"] = True
            e["fixture_matches"] += 1
    return {
        "league_id": league_id,
        "league_name": details.get("name"),
        "selected_season": details.get("selectedSeason"),
        "table_team_count": sum(1 for e in teams.values() if e["in_table"]),
        "fixture_team_count": sum(1 for e in teams.values() if e["in_fixtures"]),
        "fixture_count": len(matches),
        "snapshot_at": snapshot_at,
        "teams": teams,
    }


def build_team_index(parsed_leagues: list[dict]) -> dict[int, dict]:
    """Deduplicated club list with the competitions each club is in (table and/or fixtures)."""
    index: dict[int, dict] = {}
    for lp in parsed_leagues:
        lid = lp["league_id"]
        for tid, e in lp["teams"].items():
            t = index.setdefault(tid, {"team_id": tid, "name": e["name"], "competitions": {}})
            if t["name"] is None and e["name"]:
                t["name"] = e["name"]
            t["competitions"][lid] = {
                "league_id": lid,
                "league_name": lp["league_name"],
                "in_table": e["in_table"],
                "in_fixtures": e["in_fixtures"],
                "fixture_matches": e["fixture_matches"],
                # a European-cup club that appears in the season's fixtures but not in the
                # league-phase table (qualifying / knock-out-only participant)
                "qualifying_only": bool(lid in EURO_CUPS and e["in_fixtures"] and not e["in_table"]),
                "league_snapshot_at": lp["snapshot_at"],
            }
    for t in index.values():
        domestic = any(lid in DOMESTIC_LEAGUES for lid in t["competitions"])
        t["group"] = "target_league" if domestic else "european_cup_only"
    return index


def ordered_team_ids(index: dict[int, dict], league_order: list[int]) -> list[int]:
    """Clubs of the 10 leagues first (in league order), then the European-cup-only clubs."""
    pos = {lid: i for i, lid in enumerate(league_order)}

    def key(tid: int) -> tuple:
        t = index[tid]
        first = min((pos.get(lid, len(pos)) for lid in t["competitions"]), default=len(pos))
        return (t["group"] != "target_league", first, tid)

    return sorted(index, key=key)


# --------------------------------------------------------------------------- parsing: teams


def classify_member(group_title: Any, role_key: Any) -> str:
    if role_key in COACH_ROLE_KEYS or group_title in COACH_GROUP_TITLES:
        return "coach"
    if role_key in PLAYER_ROLE_KEYS or group_title in PLAYER_GROUP_TITLES:
        return "player"
    return "other"


def _injury(member: dict) -> tuple[Any, Any]:
    inj = member.get("injury")
    if isinstance(inj, dict):
        return inj.get("id"), inj.get("expectedReturn")
    return None, None


def parse_squad_member(m: dict, group_title: Any, team_id: int, team_name: Any, snapshot_at: str | None) -> dict:
    role = _dict(m.get("role"))
    injury_id, injury_expected_return = _injury(m)
    return {
        "team_id": team_id,
        "team_name": team_name,
        "player_id": _to_int(m.get("id")),
        "name": m.get("name"),
        "squad_group": group_title,
        "role_key": role.get("key"),
        "role_label": role.get("fallback"),
        "position_id": m.get("positionId"),
        "position_ids": m.get("positionIds"),
        "position_ids_desc": m.get("positionIdsDesc"),
        "shirt_number": m.get("shirtNumber"),
        "age": listed_age(m.get("age")),
        "age_raw": m.get("age"),
        "date_of_birth": m.get("dateOfBirth"),
        "height": m.get("height"),
        "ccode": m.get("ccode"),
        "cname": m.get("cname"),
        "national_team_id": m.get("nationalTeamId"),
        "transfer_value": m.get("transferValue"),
        "injured": m.get("injured"),
        "injury": m.get("injury"),
        "injury_id": injury_id,
        "injury_expected_return": injury_expected_return,
        "rating": m.get("rating"),
        "goals": m.get("goals"),
        "penalties": m.get("penalties"),
        "assists": m.get("assists"),
        "ycards": m.get("ycards"),
        "rcards": m.get("rcards"),
        "exclude_from_ranking": m.get("excludeFromRanking"),
        "roster_source": "squad",
        "lineup_role": None,
        "lineup_match_id": None,
        "lineup_match_date": None,
        "lineup_entry": None,
        "snapshot_at": snapshot_at,
    }


def squad_groups(data: dict) -> list | None:
    """``squad.squad`` (list of groups), or None when FotMob sends no squad for the club."""
    groups = _dict(data.get("squad")).get("squad")
    return groups if isinstance(groups, list) else None


def _lineup_entries(team_lineup: dict) -> list[tuple[str, dict]]:
    return (
        [("starter", e) for e in _list(team_lineup.get("starters")) if isinstance(e, dict)]
        + [("sub", e) for e in _list(team_lineup.get("subs")) if isinstance(e, dict)]
        + [("unavailable", e) for e in _list(team_lineup.get("unavailable")) if isinstance(e, dict)]
    )


MAX_FALLBACK_MATCHES = 6


def needs_fallback_matches(data: dict) -> bool:
    """A club without a squad list AND without ``overview.lastLineupStats`` players."""
    if squad_groups(data) is not None:
        return False
    return not _lineup_entries(_dict(_dict(data.get("overview")).get("lastLineupStats")))


def fallback_match_candidates(data: dict, limit: int = MAX_FALLBACK_MATCHES) -> list[int]:
    """Finished matches of the club, most recent first (``overview.lastMatch.id``, then
    ``overview.overviewFixtures[*]`` with ``status.finished`` by ``status.utcTime``), at most ``limit``.
    Empty unless :func:`needs_fallback_matches`."""
    if not needs_fallback_matches(data):
        return []
    overview = _dict(data.get("overview"))
    finished = []
    for f in _list(overview.get("overviewFixtures")):
        f = _dict(f)
        status = _dict(f.get("status"))
        mid = _to_int(f.get("id"))
        if mid is not None and status.get("finished") is True and not status.get("cancelled"):
            finished.append((str(status.get("utcTime") or ""), mid))
    out: list[int] = []
    last = _to_int(_dict(overview.get("lastMatch")).get("id"))
    if last is not None:
        out.append(last)
    for _, mid in sorted(finished, reverse=True):
        if mid not in out:
            out.append(mid)
    return out[:limit]


def lineup_side(match_data: Any, team_id: int) -> dict | None:
    """The club's side of ``content.lineup`` in a matchDetails response, or None."""
    lineup = _dict(_dict(_dict(match_data).get("content")).get("lineup"))
    for key in ("homeTeam", "awayTeam"):
        side = _dict(lineup.get(key))
        if _to_int(side.get("id")) == team_id:
            return side
    return None


def has_lineup(match_data: Any, team_id: int) -> bool:
    """The club has starters or substitutes in that match's line-up (an 'unavailable'-only list is not a line-up)."""
    side = lineup_side(match_data, team_id)
    return bool(side and (_list(side.get("starters")) or _list(side.get("subs"))))


def fallback_roster(
    data: dict, team_id: int, matches: list[tuple[int, Any]] | None = None
) -> tuple[str | None, int | None, str | None, list[tuple[str, dict]]]:
    """(source, match id, match date, [(lineup role, entry)]) for a club FotMob sends no squad list for.

    1. ``overview.lastLineupStats`` of the same teams response (starters, subs, unavailable);
    2. else the first of ``matches`` [(match id, matchDetails response)] - given in
       :func:`fallback_match_candidates` order, most recent first - whose line-up has the club's
       starters/subs. Clubs with a squad list never use this."""
    if squad_groups(data) is not None:
        return None, None, None, []
    overview = _dict(data.get("overview"))
    last_lineup = _dict(overview.get("lastLineupStats"))
    entries = _lineup_entries(last_lineup)
    if entries:
        match_id = _to_int(_dict(last_lineup.get("lastMatch")).get("matchId"))
        last_match = _dict(overview.get("lastMatch"))
        match_date = _dict(last_match.get("status")).get("utcTime") if _to_int(last_match.get("id")) == match_id else None
        return "overview.lastLineupStats", match_id, match_date, entries
    for match_id, match_data in matches or []:
        if match_data is not None and has_lineup(match_data, team_id):
            general = _dict(_dict(match_data).get("general"))
            mid = _to_int(general.get("matchId")) or match_id
            return "matchDetails.content.lineup", mid, general.get("matchTimeUTCDate"), _lineup_entries(
                lineup_side(match_data, team_id) or {}
            )
    return None, None, None, []


LINEUP_LAYOUT_KEYS = frozenset({"horizontalLayout", "verticalLayout"})


def parse_lineup_member(
    entry: dict, lineup_role: str, source: str, match_id: int | None, match_date: Any, team_id: int,
    team_name: Any, snapshot_at: str | None,
) -> dict:
    """A fallback roster row: same columns as a squad row; what a line-up entry does not carry is null."""
    row = parse_squad_member({}, None, team_id, team_name, snapshot_at)
    row.update(
        {
            "player_id": _to_int(entry.get("id")),
            "name": entry.get("name"),
            "age": listed_age(entry.get("age")),
            "age_raw": entry.get("age"),
            "shirt_number": entry.get("shirtNumber"),
            "ccode": entry.get("countryCode"),
            "cname": entry.get("countryName"),
            "roster_source": source,
            "lineup_role": lineup_role,
            "lineup_match_id": match_id,
            "lineup_match_date": match_date,
            "lineup_entry": {k: v for k, v in entry.items() if k not in LINEUP_LAYOUT_KEYS},
        }
    )
    return row


def team_roster(
    data: dict, team_id: int, snapshot_at: str | None, matches: list[tuple[int, Any]] | None = None,
    match_snapshots: dict[int, str] | None = None,
) -> tuple[dict, list[dict]]:
    """(team fields, roster rows): the squad list, or the labelled fallback roster when FotMob sends none.
    ``matches`` / ``match_snapshots``: cached matchDetails responses of :func:`fallback_match_candidates`."""
    team, members, _others = parse_team(data, team_id, snapshot_at)
    source, match_id, match_date, entries = fallback_roster(data, team_id, matches)
    team["roster_source"] = "squad" if squad_groups(data) is not None else source
    team["fallback_roster_count"] = 0
    if source:
        snap = snapshot_at if source == "overview.lastLineupStats" else (match_snapshots or {}).get(match_id)
        seen: set[int] = set()
        for role, entry in entries:
            row = parse_lineup_member(entry, role, source, match_id, match_date, team_id, team["name"], snap)
            if row["player_id"] is None or row["player_id"] in seen:
                continue
            seen.add(row["player_id"])
            members.append(row)
        team["fallback_roster_count"] = len(members)
    return team, members


def parse_team(data: dict, team_id: int, snapshot_at: str | None) -> tuple[dict, list[dict], list[dict]]:
    """(team fields, player squad rows, other non-player/non-coach members) of a teams response."""
    details = _dict(data.get("details"))
    team_name = details.get("name")
    members: list[dict] = []
    coaches: list[dict] = []
    others: list[dict] = []
    for group in squad_groups(data) or []:
        title = _dict(group).get("title")
        for m in _list(_dict(group).get("members")):
            if not isinstance(m, dict):
                continue
            role_key = _dict(m.get("role")).get("key")
            kind = classify_member(title, role_key)
            if kind == "coach":
                coaches.append(
                    {
                        "id": _to_int(m.get("id")),
                        "name": m.get("name"),
                        "ccode": m.get("ccode"),
                        "cname": m.get("cname"),
                        "date_of_birth": m.get("dateOfBirth"),
                    }
                )
            elif kind == "player":
                members.append(parse_squad_member(m, title, team_id, team_name, snapshot_at))
            else:
                others.append({"id": _to_int(m.get("id")), "name": m.get("name"), "group": title, "role_key": role_key})
    # without a squad list (FotMob sends ``squad.squad: null``) the counts are unknown -> null, not 0
    sent = squad_groups(data) is not None
    team = {
        "name": team_name,
        "short_name": details.get("shortName"),
        "country": details.get("country"),
        "primary_league_id": details.get("primaryLeagueId"),
        "primary_league_name": details.get("primaryLeagueName"),
        "latest_season": details.get("latestSeason"),
        "coach": coaches[0] if coaches else None,
        "coach_count": len(coaches) if sent else None,
        "squad_list_sent": sent,
        "squad_player_count": len(members) if sent else None,
        "squad_other_members": others if sent else None,
        "response_team_id": _to_int(details.get("id")),
    }
    return team, members, others


# --------------------------------------------------------------------------- parsing: players


def player_information(data: dict) -> dict[str, dict]:
    """``playerInformation[*]`` keyed by the stable ``translationKey`` (never the English title)."""
    out: dict[str, dict] = {}
    for item in _list(data.get("playerInformation")):
        if isinstance(item, dict) and item.get("translationKey") and item["translationKey"] not in out:
            out[item["translationKey"]] = item
    return out


def _info_value(info: dict[str, dict], key: str, field: str) -> Any:
    return _dict(_dict(info.get(key)).get("value")).get(field)


def _stats_map(stats: Any, key_field: str = "localizedTitleId", value_field: str = "value") -> dict[str, Any] | None:
    if not isinstance(stats, list):
        return None
    out: dict[str, Any] = {}
    for s in stats:
        if isinstance(s, dict) and s.get(key_field) and s[key_field] not in out:
            out[s[key_field]] = s.get(value_field)
    return out


def _first_season_stats(data: dict) -> dict | None:
    """``firstSeasonStats`` compacted. FotMob does not label which season/tournament these stats
    belong to; ``presumed_*`` = ``statSeasons[0]`` / its first tournament (FotMob's default entry)."""
    fss = data.get("firstSeasonStats")
    if not isinstance(fss, dict):
        return None

    def items(section: Any) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for it in _list(_dict(section).get("items")):
            if not isinstance(it, dict):
                continue
            if isinstance(it.get("items"), list):  # a stats group
                for sub in it["items"]:
                    if isinstance(sub, dict) and sub.get("localizedTitleId") and sub["localizedTitleId"] not in out:
                        out[sub["localizedTitleId"]] = _stat_item(sub)
            elif it.get("localizedTitleId") and it["localizedTitleId"] not in out:
                out[it["localizedTitleId"]] = _stat_item(it)
        return out

    seasons = _list(data.get("statSeasons"))
    first = _dict(seasons[0]) if seasons else {}
    tournaments = _list(first.get("tournaments"))
    t0 = _dict(tournaments[0]) if tournaments else {}
    return {
        "presumed_season": first.get("seasonName"),
        "presumed_tournament_id": t0.get("tournamentId"),
        "presumed_tournament_name": t0.get("name"),
        "top_stat_card": items(fss.get("topStatCard")) or None,
        "stats": items(fss.get("statsSection")) or None,
    }


def match_rating(raw: Any) -> float | None:
    """``recentMatches[*].ratingProps.rating``: real ratings arrive as strings ("7.4"); FotMob sends the
    integer 0 when it has no rating (unused substitutes, matches without rating coverage). A FotMob
    rating is never 0, so 0 -> null here; ``rating_raw`` keeps the value exactly as sent."""
    value = _to_float(raw)
    if value is None or value == 0:
        return None
    return value


def _stat_item(it: dict) -> dict:
    return {
        "value": it.get("statValue"),
        "per90": it.get("per90"),
        "percentile_rank": it.get("percentileRank"),
        "percentile_rank_per90": it.get("percentileRankPer90"),
        "format": it.get("statFormat"),
    }


def parse_player(
    data: dict, player_id: int, snapshot_at: str | None, squad_team_ids: list[int] | None = None
) -> tuple[dict, list[dict], list[dict], list[dict]]:
    """(players row, recent-match rows, market-value rows, career rows) of a playerData response."""
    info = player_information(data)
    primary = _dict(data.get("primaryTeam"))
    posdesc = _dict(data.get("positionDescription"))
    primary_pos = _dict(posdesc.get("primaryPosition"))
    # null (not []) when FotMob sends no positions list (positionDescription null / positions null)
    positions: list[dict] | None = [] if isinstance(posdesc.get("positions"), list) else None
    for p in _list(posdesc.get("positions")):
        p = _dict(p)
        positions.append(
            {
                "position_id": p.get("position"),
                "key": _dict(p.get("strPos")).get("key"),
                "label": _dict(p.get("strPos")).get("label"),
                "short_key": _dict(p.get("strPosShort")).get("key"),
                "short_label": _dict(p.get("strPosShort")).get("label"),
                "occurrences": p.get("occurences"),
                "is_main": p.get("isMainPosition"),
            }
        )
    country = _dict(info.get("country_sentencecase"))
    injury = data.get("injuryInformation")
    inj = _dict(injury)
    inj_ret = _dict(inj.get("expectedReturn"))
    main_league = data.get("mainLeague")
    ml = _dict(main_league)
    traits = data.get("traits")
    nm = _dict(data.get("nextMatch"))
    career = _dict(data.get("careerHistory"))
    mv_values = _list(_dict(data.get("marketValues")).get("values"))
    recent = _list(data.get("recentMatches"))
    # list lengths only when FotMob sends the list (recentMatches / marketValues can be null) -> else null, not 0
    recent_sent = isinstance(data.get("recentMatches"), list)
    mv_sent = isinstance(_dict(data.get("marketValues")).get("values"), list)
    raw_birth_date = _dict(data.get("birthDate")).get("utcTime")

    row = {
        "player_id": player_id,
        "response_id": _to_int(data.get("id")),
        "name": data.get("name"),
        "gender": data.get("gender"),
        "status": data.get("status"),
        "is_coach": data.get("isCoach"),
        "is_captain": data.get("isCaptain"),
        "birth_date": birth_date(raw_birth_date),
        "birth_date_raw": raw_birth_date,
        "contract_end": _dict(data.get("contractEnd")).get("utcTime"),
        "primary_team_id": _to_int(primary.get("teamId")),
        "primary_team_name": primary.get("teamName"),
        "on_loan": primary.get("onLoan"),
        "position_primary_key": primary_pos.get("key"),
        "position_primary_label": primary_pos.get("label"),
        "positions": positions,
        "non_primary_positions": posdesc.get("nonPrimaryPositions"),
        "height_cm": _info_value(info, "height_sentencecase", "numberValue"),
        "preferred_foot": _info_value(info, "preferred_foot", "key"),
        "country_code": country.get("countryCode"),
        "country_name": _dict(country.get("value")).get("fallback") if country else None,
        "national_team_id": country.get("nationalTeamId"),
        "shirt_number": _info_value(info, "shirt", "numberValue"),
        "age": _info_value(info, "age_sentencecase", "numberValue"),
        "market_value": _info_value(info, "transfer_value", "numberValue"),
        "market_value_text": _info_value(info, "transfer_value", "fallback"),
        "contract_end_date": _info_value(info, "contract_end", "dateValue"),
        "player_information_keys": sorted(info),
        "injury_information": injury,
        "injury_key": inj.get("key"),
        "injury_name": inj.get("name"),
        "injury_expected_return_key": inj_ret.get("expectedReturnKey"),
        "injury_expected_return_param": inj_ret.get("expectedReturnDateParam"),
        "injury_expected_return_text": inj_ret.get("expectedReturnFallback"),
        "injury_last_updated": _dict(inj.get("lastUpdated")).get("utcTime"),
        "international_duty": data.get("internationalDuty"),
        "main_league": (
            {
                "league_id": ml.get("leagueId"),
                "league_name": ml.get("leagueName"),
                "season": ml.get("season"),
                "stats": _stats_map(ml.get("stats")),
            }
            if isinstance(main_league, dict)
            else None
        ),
        "first_season_stats": _first_season_stats(data),
        "traits": traits,
        "next_match": (
            {
                "match_id": nm.get("matchId"),
                "home_id": nm.get("homeId"),
                "away_id": nm.get("awayId"),
                "match_date": nm.get("matchDate"),
                "league_id": nm.get("leagueId"),
                "parent_league_id": nm.get("parentLeagueId"),
            }
            if nm
            else None
        ),
        "career_full": career.get("fullCareer") if career else None,
        "recent_matches_n": len(recent) if recent_sent else None,
        "market_values_n": len(mv_values) if mv_sent else None,
        "squad_team_ids": sorted(set(squad_team_ids or [])),
        "snapshot_at": snapshot_at,
    }

    recent_rows = []
    for m in recent:
        m = _dict(m)
        rp = _dict(m.get("ratingProps"))
        recent_rows.append(
            {
                "player_id": player_id,
                "match_id": _to_int(m.get("id")),
                "match_date": _dict(m.get("matchDate")).get("utcTime"),
                "team_id": _to_int(m.get("teamId")),
                "team_name": m.get("teamName"),
                "opponent_team_id": _to_int(m.get("opponentTeamId")),
                "opponent_team_name": m.get("opponentTeamName"),
                "is_home_team": m.get("isHomeTeam"),
                "league_id": _to_int(m.get("leagueId")),
                "league_name": m.get("leagueName"),
                "stage": m.get("stage"),
                "home_score": m.get("homeScore"),
                "away_score": m.get("awayScore"),
                "minutes_played": m.get("minutesPlayed"),
                "goals": m.get("goals"),
                "assists": m.get("assists"),
                "yellow_cards": m.get("yellowCards"),
                "red_cards": m.get("redCards"),
                "rating": match_rating(rp.get("rating")),
                "rating_raw": rp.get("rating"),
                "is_top_rating": rp.get("isTopRating"),
                "player_of_the_match": m.get("playerOfTheMatch"),
                "on_bench": m.get("onBench"),
                "played_in_match": m.get("playedInMatch"),
                "lineup_position_id": m.get("lineupPositionId"),
                "snapshot_at": snapshot_at,
            }
        )

    mv_rows = []
    for v in mv_values:
        v = _dict(v)
        mv_rows.append(
            {
                "player_id": player_id,
                "date": v.get("date"),
                "value": v.get("value"),
                "currency": v.get("currency"),
                "lower_bound": v.get("lowerBound"),
                "upper_bound": v.get("upperBound"),
                "source": v.get("source"),
                "team_id": _to_int(v.get("teamId")),
                "team_name": v.get("teamName"),
                "is_period_start": v.get("isPeriodStart"),
                "snapshot_at": snapshot_at,
            }
        )

    career_rows = []
    for section, body in _dict(career.get("careerItems")).items():
        body = _dict(body)
        for i, e in enumerate(_list(body.get("teamEntries"))):
            e = _dict(e)
            career_rows.append(
                {
                    "player_id": player_id,
                    "section": section,
                    "entry_type": "team",
                    "entry_index": i,
                    "team_id": _to_int(e.get("teamId")),
                    "team": e.get("team"),
                    "team_gender": e.get("teamGender"),
                    "transfer_type": e.get("transferType"),
                    "start_date": e.get("startDate"),
                    "end_date": e.get("endDate"),
                    "active": e.get("active"),
                    "role": e.get("role"),
                    "appearances": e.get("appearances"),
                    "goals": e.get("goals"),
                    "assists": e.get("assists"),
                    "has_uncertain_data": e.get("hasUncertainData"),
                    "snapshot_at": snapshot_at,
                }
            )
        for i, e in enumerate(_list(body.get("seasonEntries"))):
            e = _dict(e)
            career_rows.append(
                {
                    "player_id": player_id,
                    "section": section,
                    "entry_type": "season",
                    "entry_index": i,
                    "season_name": e.get("seasonName"),
                    "team_id": _to_int(e.get("teamId")),
                    "team": e.get("team"),
                    "team_gender": e.get("teamGender"),
                    "transfer_type": e.get("transferType"),
                    "appearances": e.get("appearances"),
                    "goals": e.get("goals"),
                    "assists": e.get("assists"),
                    "rating": _dict(e.get("rating")).get("rating"),
                    "tournament_stats": e.get("tournamentStats"),
                    "snapshot_at": snapshot_at,
                }
            )
    return row, recent_rows, mv_rows, career_rows


# --------------------------------------------------------------------------- validation


def valid_league(data: Any) -> bool:
    return isinstance(data, dict) and isinstance(data.get("details"), dict) and (
        "fixtures" in data or "table" in data
    )


def valid_team(data: Any) -> bool:
    return isinstance(data, dict) and isinstance(data.get("details"), dict) and isinstance(data.get("squad"), dict)


def valid_player(data: Any) -> bool:
    return isinstance(data, dict) and _to_int(data.get("id")) is not None


def valid_match(data: Any) -> bool:
    return isinstance(data, dict) and isinstance(data.get("content"), dict) and isinstance(data.get("general"), dict)
