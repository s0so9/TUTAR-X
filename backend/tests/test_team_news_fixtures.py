"""SYNTHETIC TEST FIXTURES for the team-news live layer - NOT real football data.

Builders of payloads shaped like FotMob raw bodies (/api/data/teams,
/api/data/playerData, /api/data/matchDetails, /api/data/leagues) with made-up
ids (99xxxx), names ("Synthetic Player 12") and numbers. They exist only to
exercise parsers/services in tests; nothing here is a real statistic.
This module defines no tests itself.
"""

from __future__ import annotations

from typing import Any, Optional

SYN_HOME_TEAM = 990001
SYN_AWAY_TEAM = 990002
SYN_LEAGUE = 47  # a TARGET13 id so discovery code paths are exercised


def syn_player_id(team: int, n: int) -> int:
    return team * 100 + n  # e.g. 99000101 .. 99000125


def synthetic_team_payload(
    team_id: int = SYN_HOME_TEAM,
    *,
    season: Optional[str] = "2026/2027",
    n_players: int = 14,
    injured: Optional[dict[int, tuple[str, str]]] = None,
    include_squad: bool = True,
) -> dict[str, Any]:
    """injured: {player number: (injury id, expected return text)}."""
    injured = injured or {}
    groups: list[dict[str, Any]] = [
        {
            "title": "coach",
            "members": [
                {"id": team_id * 100 + 99, "name": "Synthetic Coach", "role": {"key": "coach", "fallback": "Coach"}}
            ],
        }
    ]
    by_role = {"keepers": [], "defenders": [], "midfielders": [], "attackers": []}
    roles = [("keepers", "keeper_long", "Keeper", 0, "11", "GK")] + [
        ("defenders", "defender_long", "Defender", 1, "34,38", "CB,LB")
    ] * 4 + [("midfielders", "midfielder_long", "Midfielder", 2, "64,75", "CDM,CM")] * 4 + [
        ("attackers", "attacker_long", "Attacker", 3, "115", "ST")
    ] * 2
    for n in range(1, n_players + 1):
        title, key, fallback, pos, ids, desc = roles[(n - 1) % len(roles)]
        member = {
            "id": syn_player_id(team_id, n),
            "name": f"Synthetic Player {team_id}-{n}",
            "shirtNumber": n,
            "ccode": "SYN",
            "cname": "Synthland",
            "role": {"key": key, "fallback": fallback},
            "positionId": pos,
            "injury": None,
            "rating": None,
            "goals": 0,
            "assists": 0,
            "rcards": 0,
            "ycards": 0,
            "positionIds": ids,
            "positionIdsDesc": desc,
            "height": 170 + n,
            "age": 20 + n,
            "dateOfBirth": f"{2000 + (n % 6)}-01-{10 + n:02d}",
            "transferValue": 1_000_000 * n,
        }
        if n in injured:
            injury_id, expected = injured[n]
            member["injured"] = True
            member["injury"] = {"id": injury_id, "expectedReturn": expected}
        by_role[title].append(member)
    for title in ("keepers", "defenders", "midfielders", "attackers"):
        groups.append({"title": title, "members": by_role[title]})
    payload: dict[str, Any] = {
        "details": {"id": team_id, "type": "team", "name": f"Synthetic FC {team_id}", "latestSeason": season},
        "overview": {"season": season},
    }
    if include_squad:
        payload["squad"] = {"squad": groups, "isNationalTeam": False}
    return payload


def synthetic_player_payload(
    player_id: int,
    *,
    team_id: int = SYN_HOME_TEAM,
    injury: Optional[dict[str, Any]] = None,
    market_values: Optional[list[tuple[str, int]]] = None,
    include_injury_key: bool = True,
) -> dict[str, Any]:
    market_values = market_values or [("2026-09-01T00:00:00+00:00", 5_000_000), ("2026-10-01T00:00:00+00:00", 6_000_000)]
    payload: dict[str, Any] = {
        "id": player_id,
        "name": f"Synthetic Player {player_id}",
        "birthDate": {"utcTime": "2001-03-24T00:00:00.000Z", "timezone": "UTC"},
        "contractEnd": {"utcTime": "2030-06-30T00:00:00.000Z", "timezone": "UTC"},
        "primaryTeam": {"teamId": team_id, "teamName": f"Synthetic FC {team_id}", "onLoan": False},
        "positionDescription": {
            "positions": [
                {
                    "strPos": {"label": "Center Back", "key": "centerback"},
                    "strPosShort": {"label": "CB", "key": "centerback_short"},
                    "position": "34",
                    "isMainPosition": True,
                }
            ],
            "primaryPosition": {"label": "Center Back", "key": "centerback"},
        },
        "internationalDuty": None,
        "playerInformation": [
            {"value": {"numberValue": 190, "fallback": "190 cm"}, "translationKey": "height_sentencecase"},
            {"value": {"numberValue": 4, "fallback": 4}, "translationKey": "shirt"},
            {"value": {"key": "left", "fallback": "Left"}, "translationKey": "preferred_foot"},
            {"value": {"fallback": "Synthland"}, "translationKey": "country_sentencecase", "countryCode": "SYN"},
        ],
        "marketValues": {
            "values": [{"date": d, "value": v, "currency": "EUR", "source": "synthetic"} for d, v in market_values]
        },
        "recentMatches": [],
    }
    if include_injury_key:
        payload["injuryInformation"] = injury
    return payload


def synthetic_injury(name: str = "Synthetic knock", injury_id: str = "45", expected: str = "Late October 2026"):
    return {
        "name": name,
        "key": f"injury_{injury_id}",
        "expectedReturn": {"expectedReturnFallback": expected, "expectedReturnDateParam": None},
        "lastUpdated": {"utcTime": "2026-10-10T00:00:00.000Z"},
    }


def _lineup_player(team: int, n: int, *, starter: bool, position_id: Optional[int] = None, perf: Optional[dict] = None):
    entry = {
        "id": syn_player_id(team, n),
        "name": f"Synthetic Player {team}-{n}",
        "shirtNumber": str(n),
        "usualPlayingPositionId": 0 if n == 1 else (1 if n <= 5 else (2 if n <= 9 else 3)),
        "countryName": "Synthland",
        "countryCode": "SYN",
        "marketValue": 1_000_000 * n,
    }
    if starter:
        entry["positionId"] = position_id if position_id is not None else (11 if n == 1 else 30 + n)
    if perf is not None:
        entry["performance"] = perf
    return entry


def synthetic_match_payload(
    match_id: int,
    *,
    home: int = SYN_HOME_TEAM,
    away: int = SYN_AWAY_TEAM,
    kickoff: str = "2026-10-20T19:00:00.000Z",
    status: str = "scheduled",
    lineup_type: Optional[str] = "predicted",
    home_starters: Optional[list[int]] = None,
    away_starters: Optional[list[int]] = None,
    with_bench: bool = False,
    unavailable: Optional[dict[str, Optional[list[tuple[int, str, Optional[str]]]]]] = None,
    stats: Optional[dict[int, dict[str, Any]]] = None,
    subs_in: Optional[dict[int, int]] = None,
    cards: Optional[list[tuple[int, str]]] = None,
    with_events: bool = True,
    home_score: Optional[int] = None,
    away_score: Optional[int] = None,
    league_id: int = SYN_LEAGUE,
    last_match: Optional[int] = None,
) -> dict[str, Any]:
    """unavailable: {"home": [(player number, type, expectedReturn)] | None (key absent)}.
    stats: {player id: {"minutes": .., "rating": .., "goals": .., "xg": .., "shotmap": n}}.
    subs_in: {player id: minute}; cards: [(player id, "Yellow"|"Red"|"YellowRed")]."""
    home_starters = home_starters if home_starters is not None else list(range(1, 12))
    away_starters = away_starters if away_starters is not None else list(range(1, 12))
    unavailable = unavailable or {}
    stats = stats or {}
    subs_in = subs_in or {}
    finished = status == "finished"
    started = status in ("started", "finished")

    def side(team: int, starters: list[int], side_key: str) -> dict[str, Any]:
        bench_numbers = [n for n in range(12, 15)] if with_bench else []
        t: dict[str, Any] = {
            "id": team,
            "name": f"Synthetic FC {team}",
            "formation": "4-3-3",
            "starters": [_lineup_player(team, n, starter=True) for n in starters],
        }
        if with_bench:
            subs = []
            for n in bench_numbers:
                pid = syn_player_id(team, n)
                perf = {"substitutionEvents": [{"time": subs_in[pid], "type": "subIn"}]} if pid in subs_in else {}
                subs.append(_lineup_player(team, n, starter=False, perf=perf))
            t["subs"] = subs
        if last_match is not None:  # lineupType lastStarting11 carries the source match
            t["lastMatch"] = {"matchId": last_match, "homeTeamId": team, "matchDate": "2026-10-10T20:45:00"}
        lst = unavailable.get(side_key, "absent")
        if lst != "absent" and lst is not None:
            t["unavailable"] = [
                {
                    "id": syn_player_id(team, n),
                    "name": f"Synthetic Player {team}-{n}",
                    "unavailability": {"type": typ, "expectedReturn": exp, "injuryId": 30 if typ == "injury" else None},
                }
                for n, typ, exp in lst
            ]
        return t

    player_stats: dict[str, Any] = {}
    for pid, s in stats.items():
        top: dict[str, Any] = {}
        if "rating" in s:
            top["FotMob rating"] = {"key": "rating_title", "stat": {"value": s["rating"], "type": "double"}}
        if "minutes" in s:
            top["Minutes played"] = {"key": "minutes_played", "stat": {"value": s["minutes"], "type": "integer"}}
        for key, out in (("goals", "goals"), ("assists", "assists"), ("xg", "expected_goals"), ("xa", "expected_assists")):
            if key in s:
                top[out] = {"key": out, "stat": {"value": s[key]}}
        player_stats[str(pid)] = {
            "id": pid,
            "isGoalkeeper": s.get("gk", False),
            "stats": [{"title": "Top stats", "key": "top_stats", "stats": top}] if top else [],
            "shotmap": [{"x": 1}] * s["shotmap"] if s.get("shotmap") is not None else None,
        }
        if s.get("shotmap") is None:
            player_stats[str(pid)].pop("shotmap")

    events = [
        {"type": "Card", "time": 50, "card": card, "player": {"id": pid, "name": "x"}} for pid, card in (cards or [])
    ]
    content: dict[str, Any] = {
        "lineup": {
            "matchId": match_id,
            "lineupType": lineup_type,
            "source": "synthetic",
            "homeTeam": side(home, home_starters, "home"),
            "awayTeam": side(away, away_starters, "away"),
        },
        "playerStats": player_stats if finished else None,
    }
    if with_events:
        content["matchFacts"] = {"events": {"events": events}}
    return {
        "general": {
            "matchId": str(match_id),
            "leagueId": 900000 + league_id,
            "parentLeagueId": league_id,
            "homeTeam": {"name": f"Synthetic FC {home}", "id": home},
            "awayTeam": {"name": f"Synthetic FC {away}", "id": away},
            "matchTimeUTCDate": kickoff,
            "started": started,
            "finished": finished,
        },
        "header": {
            "teams": [
                {"name": f"Synthetic FC {home}", "id": home, "score": home_score if started else 0},
                {"name": f"Synthetic FC {away}", "id": away, "score": away_score if started else 0},
            ],
            "status": {"utcTime": kickoff, "started": started, "finished": finished, "cancelled": False},
        },
        "content": content,
    }


def synthetic_league_payload(league_id: int, matches: list[dict[str, Any]]) -> dict[str, Any]:
    """matches: [{"id", "home", "away", "utcTime", "finished"}]"""
    return {
        "details": {"id": league_id, "selectedSeason": "2026/2027"},
        "fixtures": {
            "allMatches": [
                {
                    "id": str(m["id"]),
                    "home": {"id": str(m["home"]), "name": f"Synthetic FC {m['home']}"},
                    "away": {"id": str(m["away"]), "name": f"Synthetic FC {m['away']}"},
                    "status": {
                        "utcTime": m["utcTime"],
                        "started": m.get("finished", False),
                        "finished": m.get("finished", False),
                        "cancelled": False,
                    },
                }
                for m in matches
            ]
        },
    }
