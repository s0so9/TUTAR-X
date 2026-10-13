"""Unit tests for the FotMob squads/players collector (scripts/data_collection/collect_fotmob_squads_players.py).

Every payload below is a SYNTHETIC TEST FIXTURE shaped like FotMob league / teams /
playerData responses (structure copied from real responses, names and values made up
for the test). None of it is football data and none of it is written to the dataset:
the end-to-end test writes only into pytest's tmp_path.
"""

import gzip
import importlib.util
import json
import threading
from pathlib import Path

import httpx
import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "data_collection" / "collect_fotmob_squads_players.py"
_spec = importlib.util.spec_from_file_location("collect_fotmob_squads_players", _SCRIPT)
collector = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(collector)
parse = collector.fotmob_squads_parse  # the pure parser module the collector imports


# --------------------------------------------------------------------------- synthetic fixtures


def _league_fixture(league_id, team_ids, extra_fixture_team=None, nested=False):
    rows = [{"id": tid, "name": f"Fixture Club {tid}"} for tid in team_ids]
    table_data = {"tables": [{"table": {"all": rows[:2]}}, {"table": {"all": rows[2:]}}]} if nested else {
        "table": {"all": rows, "home": rows}
    }
    matches = []
    ids = list(team_ids) + ([extra_fixture_team] if extra_fixture_team else [])
    for i in range(0, len(ids) - 1, 2):
        matches.append({"id": str(9000 + i), "round": "1", "home": {"id": str(ids[i]), "name": f"Fixture Club {ids[i]}"},
                        "away": {"id": str(ids[i + 1]), "name": f"Fixture Club {ids[i + 1]}"}, "status": {}})
    return {
        "details": {"id": league_id, "name": f"Fixture League {league_id}", "selectedSeason": "2026/2027"},
        "table": [{"data": table_data}],
        "fixtures": {"allMatches": matches},
    }


def _member(pid, name, role_key, **kw):
    m = {"id": pid, "name": name, "role": {"key": role_key, "fallback": role_key}, "injury": None}
    m.update(kw)
    return m


def _team_fixture(team_id, player_ids):
    groups = [
        {"title": "coach", "members": [{"id": team_id * 100, "name": "Fixture Coach", "role": {"key": "coach"},
                                        "ccode": "XXX", "dateOfBirth": "1970-01-01"}]},
        {"title": "keepers", "members": [_member(player_ids[0], "Keeper A", "keeper_long", positionIds="11",
                                                 positionIdsDesc="GK", transferValue=1000, shirtNumber=1,
                                                 dateOfBirth="2000-01-01", height=190, rating=7.1, goals=0)]},
        {"title": "attackers", "members": [
            _member(pid, f"Attacker {pid}", "attacker_long", injured=True,
                    injury={"id": "42", "expectedReturn": "Late October 2026"})
            if i == 0 else _member(pid, f"Attacker {pid}", "attacker_long")
            for i, pid in enumerate(player_ids[1:])
        ]},
        {"title": "staff", "members": [{"id": team_id * 100 + 1, "name": "Fixture Analyst", "role": {"key": "analyst"}}]},
    ]
    return {"details": {"id": team_id, "name": f"Fixture Club {team_id}", "shortName": "FC", "country": "XXX",
                        "primaryLeagueId": 47, "primaryLeagueName": "Fixture League"},
            "squad": {"squad": groups}}


def _player_fixture(pid, team_id=1, full=True):
    if not full:
        return {"id": pid, "name": f"Bare Player {pid}"}
    return {
        "id": pid,
        "name": f"Fixture Player {pid}",
        "birthDate": {"utcTime": "2000-02-03T00:00:00.000Z"},
        "contractEnd": {"utcTime": "2029-06-30T00:00:00.000Z"},
        "isCoach": False,
        "primaryTeam": {"teamId": team_id, "teamName": "Fixture Club", "onLoan": False},
        "positionDescription": {
            "positions": [{"strPos": {"label": "Striker", "key": "striker"}, "strPosShort": {"label": "ST", "key": "st"},
                           "occurences": 12, "position": "115", "isMainPosition": True}],
            "primaryPosition": {"label": "Attacker", "key": "attacker_long"},
            "nonPrimaryPositions": [{"label": "Winger", "key": "winger"}],
        },
        "injuryInformation": {"name": "Hamstring injury", "key": "injury_42",
                              "expectedReturn": {"expectedReturnKey": "expected_return_date_late",
                                                 "expectedReturnDateParam": "October 2026",
                                                 "expectedReturnFallback": "Late October 2026"},
                              "lastUpdated": {"utcTime": "2026-10-01T00:00:00.000Z"}},
        "internationalDuty": None,
        # titles deliberately NOT English: the parser must key on translationKey
        "playerInformation": [
            {"title": "Boy", "translationKey": "height_sentencecase", "value": {"numberValue": 183, "fallback": "183 cm"}},
            {"title": "Ülke", "translationKey": "country_sentencecase", "value": {"fallback": "Fixtureland"},
             "countryCode": "FXL", "nationalTeamId": 77},
            {"title": "Değer", "translationKey": "transfer_value", "value": {"numberValue": 2500000, "fallback": "€2.5m"}},
            {"title": "Forma", "translationKey": "shirt", "value": {"numberValue": 9}},
        ],
        "mainLeague": {"leagueId": 47, "leagueName": "Fixture League", "season": "2026/2027",
                       "stats": [{"title": "Goals", "localizedTitleId": "goals", "value": 0},
                                 {"title": "Rating", "localizedTitleId": "rating", "value": 6.9}]},
        "recentMatches": [
            {"id": 501, "matchDate": {"utcTime": "2026-10-10T18:00:00.000Z"}, "teamId": team_id, "opponentTeamId": 2,
             "isHomeTeam": True, "leagueId": 47, "minutesPlayed": 90, "goals": 1, "assists": 0, "yellowCards": 0,
             "redCards": 0, "ratingProps": {"rating": "7.4"}, "onBench": False, "playedInMatch": True,
             "lineupPositionId": 115},
            {"id": 502, "matchDate": {"utcTime": "2026-10-03T18:00:00.000Z"}, "teamId": team_id, "opponentTeamId": 3,
             "isHomeTeam": False, "leagueId": 42, "minutesPlayed": 0, "goals": 0, "assists": 0, "yellowCards": 0,
             "redCards": 0, "ratingProps": {"rating": None}, "onBench": True, "playedInMatch": False},
            # FotMob's "no rating" marker is the integer 0 (unused sub / no rating coverage)
            {"id": 503, "matchDate": {"utcTime": "2026-09-26T18:00:00.000Z"}, "teamId": team_id, "opponentTeamId": 4,
             "minutesPlayed": 0, "ratingProps": {"rating": 0}, "onBench": True, "playedInMatch": False},
        ],
        "marketValues": {"values": [{"date": "2026-10-01T00:00:00+00:00", "value": 2500000, "currency": "EUR",
                                     "lowerBound": 2000000, "upperBound": 3000000, "source": "fixture-source",
                                     "teamId": team_id, "teamName": "Fixture Club", "isPeriodStart": False}]},
        "careerHistory": {"fullCareer": True, "careerItems": {
            "senior": {"teamEntries": [{"teamId": team_id, "team": "Fixture Club", "startDate": "2024-07-01T00:00:00",
                                        "endDate": None, "active": True, "appearances": "51", "goals": "7",
                                        "assists": "3", "hasUncertainData": False}],
                       "seasonEntries": [{"seasonName": "2026/2027", "teamId": team_id, "team": "Fixture Club",
                                          "appearances": "8", "goals": "1", "assists": "0", "rating": {"rating": "7.01"},
                                          "tournamentStats": [{"leagueId": 47, "appearances": "6"}]}]},
            "national team": {"teamEntries": [], "seasonEntries": []},
        }},
        "traits": {"key": "stats_comparison_attackers", "items": [{"key": "goals", "title": "Goals", "value": 0.4}]},
        "statSeasons": [{"seasonName": "2026/2027", "tournaments": [{"name": "Fixture League", "tournamentId": 47}]}],
        "firstSeasonStats": {
            "topStatCard": {"items": [{"localizedTitleId": "matches_uppercase", "statValue": "6", "per90": 6}]},
            "statsSection": {"items": [{"items": [{"localizedTitleId": "expected_goals", "statValue": "1.20",
                                                   "per90": 0.2, "percentileRank": 55.0, "statFormat": "fraction"}]}]},
        },
        "nextMatch": {"matchId": 777, "homeId": team_id, "awayId": 2, "matchDate": "2026-10-20T19:00:00Z",
                      "leagueId": 47, "parentLeagueId": 47},
    }


# --------------------------------------------------------------------------- leagues / team index


def test_parse_league_uses_table_and_fixtures():
    lp = parse.parse_league(_league_fixture(47, [1, 2, 3, 4]), 47, "2026-10-13T00:00:00+00:00")
    assert lp["table_team_count"] == 4 and lp["fixture_team_count"] == 4
    assert set(lp["teams"]) == {1, 2, 3, 4}
    assert all(e["in_table"] and e["in_fixtures"] for e in lp["teams"].values())
    assert lp["selected_season"] == "2026/2027"


def test_nested_tables_and_fixtures_only_cup_club():
    lp = parse.parse_league(_league_fixture(42, [1, 5, 6], extra_fixture_team=99, nested=True), 42, "t")
    assert lp["table_team_count"] == 3
    assert lp["teams"][99]["in_fixtures"] and not lp["teams"][99]["in_table"]
    index = parse.build_team_index([parse.parse_league(_league_fixture(47, [1, 2]), 47, "t"), lp])
    assert index[1]["group"] == "target_league" and set(index[1]["competitions"]) == {47, 42}
    assert index[99]["group"] == "european_cup_only"
    assert index[99]["competitions"][42]["qualifying_only"] is True
    assert index[5]["competitions"][42]["qualifying_only"] is False
    order = parse.ordered_team_ids(index, [47, 42])
    assert order[:2] == [1, 2]  # clubs of the domestic leagues come first
    assert set(order[2:]) == {5, 6, 99}


# --------------------------------------------------------------------------- squads


def test_parse_team_separates_players_coach_and_staff():
    team, members, others = parse.parse_team(_team_fixture(10, [11, 12, 13]), 10, "2026-10-13T00:00:00+00:00")
    assert [m["player_id"] for m in members] == [11, 12, 13]
    assert team["coach"]["id"] == 1000 and team["coach_count"] == 1
    assert others == [{"id": 1001, "name": "Fixture Analyst", "group": "staff", "role_key": "analyst"}]
    keeper, injured, fit = members
    assert keeper["role_key"] == "keeper_long" and keeper["squad_group"] == "keepers"
    assert keeper["transfer_value"] == 1000 and keeper["height"] == 190 and keeper["position_ids_desc"] == "GK"
    # FotMob sends `injured` only when true and `injury: null` otherwise: copied as sent, never defaulted
    assert injured["injured"] is True and injured["injury_id"] == "42"
    assert injured["injury_expected_return"] == "Late October 2026"
    assert fit["injured"] is None and fit["injury"] is None
    # values FotMob did not send stay null (not 0)
    assert fit["transfer_value"] is None and fit["rating"] is None and fit["goals"] is None
    assert keeper["goals"] == 0  # 0 only because the source sent 0
    assert all(m["snapshot_at"] == "2026-10-13T00:00:00+00:00" for m in members)


def _no_squad_team_fixture(team_id, last_lineup=True):
    """Synthetic club for which FotMob sends `squad.squad: null` (seen for 2 real clubs)."""
    last = 8800 + team_id
    overview = {
        "lastMatch": {"id": last, "status": {"utcTime": "2026-10-09T12:30:00.000Z", "finished": True}},
        "overviewFixtures": [
            {"id": 8790 + team_id, "status": {"utcTime": "2026-09-10T19:00:00.000Z", "finished": True}},
            {"id": last, "status": {"utcTime": "2026-10-09T12:30:00.000Z", "finished": True}},
            {"id": 8810 + team_id, "status": {"utcTime": "2026-10-20T19:00:00.000Z", "finished": False}},
        ],
    }
    if last_lineup:
        overview["lastLineupStats"] = {
            "lastMatch": {"matchId": last},
            "starters": [{"id": 71, "name": "Lineup Starter", "age": 24, "shirtNumber": "9", "countryCode": "FXL",
                          "countryName": "Fixtureland", "positionId": 115, "usualPlayingPositionId": 3,
                          "marketValue": 123, "horizontalLayout": {"x": 0.1}}],
            "subs": [{"id": 72, "name": "Lineup Sub", "usualPlayingPositionId": 0}],
            "unavailable": [{"id": 73, "name": "Lineup Injured",
                             "unavailability": {"type": "injury", "expectedReturn": "About a week"}}],
        }
    return {"details": {"id": team_id, "name": f"No-Squad Club {team_id}"},
            "squad": {"squad": None, "isNationalTeam": False}, "overview": overview}


def _match_fixture(match_id, team_id, with_lineup=True):
    club = ({"id": team_id, "starters": [{"id": 81, "name": "Match Starter", "shirtNumber": "4"}],
             "subs": [{"id": 82, "name": "Match Sub"}], "unavailable": []}
            if with_lineup else {"id": team_id, "starters": [], "subs": [], "unavailable": [{"id": 83, "name": "Out"}]})
    return {"general": {"matchId": str(match_id), "matchTimeUTCDate": "2026-09-10T19:00:00.000Z"},
            "content": {"lineup": {"homeTeam": {"id": 999, "starters": [{"id": 1}], "subs": []}, "awayTeam": club}}}


def test_fallback_roster_from_last_lineup_is_labelled():
    data = _no_squad_team_fixture(30)
    assert parse.squad_groups(data) is None and parse.fallback_match_candidates(data) == []
    team, rows = parse.team_roster(data, 30, "T")
    # no squad list sent: its counts are unknown (null), not 0
    assert team["squad_list_sent"] is False and team["squad_player_count"] is None
    assert team["coach_count"] is None and team["squad_other_members"] is None and team["coach"] is None
    assert team["roster_source"] == "overview.lastLineupStats" and team["fallback_roster_count"] == 3
    assert [(r["player_id"], r["lineup_role"]) for r in rows] == [(71, "starter"), (72, "sub"), (73, "unavailable")]
    starter = rows[0]
    assert starter["roster_source"] == "overview.lastLineupStats" and starter["lineup_match_id"] == 8830
    assert starter["lineup_match_date"] == "2026-10-09T12:30:00.000Z"
    assert starter["shirt_number"] == "9" and starter["ccode"] == "FXL" and starter["age"] == 24
    assert "horizontalLayout" not in starter["lineup_entry"] and starter["lineup_entry"]["marketValue"] == 123
    # a line-up entry carries no squad fields: they stay null (unknown), never defaulted
    assert starter["injured"] is None and starter["transfer_value"] is None and starter["role_key"] is None
    assert rows[2]["lineup_entry"]["unavailability"]["type"] == "injury"
    assert all(r["snapshot_at"] == "T" for r in rows)


def test_fallback_roster_walks_back_to_the_latest_match_with_a_lineup():
    data = _no_squad_team_fixture(31, last_lineup=False)
    # most recent finished first; the unfinished fixture is never a candidate
    assert parse.fallback_match_candidates(data) == [8831, 8821]
    matches = [(8831, _match_fixture(8831, 31, with_lineup=False)), (8821, _match_fixture(8821, 31))]
    assert not parse.has_lineup(matches[0][1], 31) and parse.has_lineup(matches[1][1], 31)
    team, rows = parse.team_roster(data, 31, "T", matches, {8831: "M1", 8821: "M2"})
    assert team["roster_source"] == "matchDetails.content.lineup"
    assert [(r["player_id"], r["lineup_role"], r["lineup_match_id"]) for r in rows] == [
        (81, "starter", 8821), (82, "sub", 8821)]
    assert all(r["snapshot_at"] == "M2" and r["lineup_match_date"] == "2026-09-10T19:00:00.000Z" for r in rows)
    # no cached match with a line-up: no roster, nothing invented
    team, rows = parse.team_roster(data, 31, "T", matches[:1], {8831: "M1"})
    assert team["roster_source"] is None and rows == []
    # clubs WITH a squad list never use a fallback
    assert parse.fallback_match_candidates(_team_fixture(10, [11, 12])) == []
    team, rows = parse.team_roster(_team_fixture(10, [11, 12]), 10, "T")
    assert team["roster_source"] == "squad" and {r["roster_source"] for r in rows} == {"squad"}


def test_classify_member():
    assert parse.classify_member("coach", "coach") == "coach"
    assert parse.classify_member("keepers", "keeper_long") == "player"
    assert parse.classify_member("defenders", None) == "player"
    assert parse.classify_member("staff", "analyst") == "other"


# --------------------------------------------------------------------------- players


def test_parse_player_profile_fields():
    row, recent, mvs, career = parse.parse_player(_player_fixture(500, team_id=10), 500, "S", [10])
    assert row["player_id"] == 500 and row["response_id"] == 500
    assert row["birth_date"] == "2000-02-03T00:00:00.000Z" and row["contract_end"] == "2029-06-30T00:00:00.000Z"
    assert row["primary_team_id"] == 10 and row["on_loan"] is False
    assert row["position_primary_key"] == "attacker_long" and row["positions"][0]["position_id"] == "115"
    assert row["positions"][0]["occurrences"] == 12
    # keyed by translationKey, not by the (localised) title
    assert row["height_cm"] == 183 and row["country_code"] == "FXL" and row["national_team_id"] == 77
    assert row["market_value"] == 2500000 and row["market_value_text"] == "€2.5m" and row["shirt_number"] == 9
    # not sent -> null
    assert row["preferred_foot"] is None and row["age"] is None and row["contract_end_date"] is None
    assert row["injury_key"] == "injury_42" and row["injury_expected_return_text"] == "Late October 2026"
    assert row["injury_last_updated"] == "2026-10-01T00:00:00.000Z"
    assert row["international_duty"] is None
    assert row["main_league"] == {"league_id": 47, "league_name": "Fixture League", "season": "2026/2027",
                                  "stats": {"goals": 0, "rating": 6.9}}
    fss = row["first_season_stats"]
    assert fss["presumed_tournament_id"] == 47 and fss["top_stat_card"]["matches_uppercase"]["value"] == "6"
    assert fss["stats"]["expected_goals"]["percentile_rank"] == 55.0
    assert row["next_match"]["match_id"] == 777 and row["squad_team_ids"] == [10]
    assert row["recent_matches_n"] == 3 and row["market_values_n"] == 1 and row["snapshot_at"] == "S"


def test_parse_player_rows():
    _, recent, mvs, career = parse.parse_player(_player_fixture(500, team_id=10), 500, "S", [10])
    assert recent[0]["match_id"] == 501 and recent[0]["rating"] == 7.4 and recent[0]["rating_raw"] == "7.4"
    assert recent[0]["minutes_played"] == 90 and recent[0]["is_home_team"] is True
    assert recent[1]["rating"] is None and recent[1]["on_bench"] is True and recent[1]["lineup_position_id"] is None
    # integer 0 = FotMob's "no rating" marker: null in `rating`, kept as sent in `rating_raw`
    assert recent[2]["rating"] is None and recent[2]["rating_raw"] == 0 and recent[2]["minutes_played"] == 0
    assert parse.match_rating("6.95") == 6.95 and parse.match_rating(0) is None
    assert parse.match_rating(None) is None and parse.match_rating("x") is None
    assert mvs == [{"player_id": 500, "date": "2026-10-01T00:00:00+00:00", "value": 2500000, "currency": "EUR",
                    "lower_bound": 2000000, "upper_bound": 3000000, "source": "fixture-source", "team_id": 10,
                    "team_name": "Fixture Club", "is_period_start": False, "snapshot_at": "S"}]
    team_rows = [c for c in career if c["entry_type"] == "team"]
    season_rows = [c for c in career if c["entry_type"] == "season"]
    assert len(team_rows) == 1 and len(season_rows) == 1
    # career counts are kept exactly as sent (FotMob sends them as strings)
    assert team_rows[0]["appearances"] == "51" and team_rows[0]["section"] == "senior"
    assert season_rows[0]["rating"] == "7.01" and season_rows[0]["tournament_stats"] == [{"leagueId": 47, "appearances": "6"}]


def test_parse_player_minimal_payload_is_all_null():
    row, recent, mvs, career = parse.parse_player(_player_fixture(7, full=False), 7, "S")
    assert recent == [] and mvs == [] and career == []
    for key in ("birth_date", "height_cm", "preferred_foot", "market_value", "injury_information",
                "main_league", "first_season_stats", "traits", "next_match", "career_full",
                # lists / list lengths FotMob did not send: null, never [] / 0
                "positions", "recent_matches_n", "market_values_n"):
        assert row[key] is None, key
    assert row["squad_team_ids"] == []


def test_parse_player_lists_sent_as_null_stay_null_and_empty_lists_count_zero():
    """SYNTHETIC: FotMob sends `recentMatches: null`, `marketValues: null`, `positionDescription.positions: null`
    for some players; an explicitly empty list is a real 0."""
    payload = {"id": 8, "name": "Null Lists", "recentMatches": None, "marketValues": None,
               "positionDescription": {"positions": None, "primaryPosition": None}}
    row, recent, mvs, _ = parse.parse_player(payload, 8, "S")
    assert row["positions"] is None and row["recent_matches_n"] is None and row["market_values_n"] is None
    assert recent == [] and mvs == []
    payload = {"id": 9, "name": "Empty Lists", "recentMatches": [], "marketValues": {"values": []},
               "positionDescription": {"positions": []}}
    row, _, _, _ = parse.parse_player(payload, 9, "S")
    assert row["positions"] == [] and row["recent_matches_n"] == 0 and row["market_values_n"] == 0


def test_unknown_birth_date_and_age_placeholders_become_null_with_raw_kept():
    """SYNTHETIC: FotMob's placeholder for an unknown birth date is 0001-01-01 (playerData) and age 0 (squad page)."""
    row, _, _, _ = parse.parse_player({"id": 10, "birthDate": {"utcTime": "0001-01-01T00:00:00.000Z"}}, 10, "S")
    assert row["birth_date"] is None and row["birth_date_raw"] == "0001-01-01T00:00:00.000Z"
    row, _, _, _ = parse.parse_player(_player_fixture(11), 11, "S")
    assert row["birth_date"] == row["birth_date_raw"] == "2000-02-03T00:00:00.000Z"
    data = _team_fixture(12, [121, 122])
    data["squad"]["squad"][1]["members"][0].update({"age": 0, "dateOfBirth": None})
    data["squad"]["squad"][2]["members"][0]["age"] = 27
    _, members, _ = parse.parse_team(data, 12, "S")
    assert members[0]["age"] is None and members[0]["age_raw"] == 0 and members[0]["date_of_birth"] is None
    assert members[1]["age"] == members[1]["age_raw"] == 27
    assert parse.listed_age(None) is None and parse.listed_age(False) is False


# --------------------------------------------------------------------------- raw cache / resume


def test_manifest_latest_ok_and_partial_last_line(tmp_path):
    store = collector.RawStore(tmp_path)
    (tmp_path / "_manifest.jsonl").write_text(
        '{"id": 1, "fetched_at": "2026-10-13T10:00:00+00:00", "http_status": 200, "bytes": 5}\n'
        '{"id": 1, "fetched_at": "2026-10-13T12:00:00+00:00", "http_status": 200, "bytes": 6}\n'
        '{"id": 1, "fetched_at": "2026-10-13T13:00:00+00:00", "http_status": 500, "bytes": 0}\n'
        '{"id": 2, "fetched_at": "2026-10-13T11:00:00+00:00", "http_status": 404, "bytes": 9}\n'
        '{"id": 3, "fetched_at": "2026-10-13T1',
        encoding="utf-8",
    )
    assert store.latest_ok() == {1: "2026-10-13T12:00:00+00:00"}
    store.append({"id": 4, "fetched_at": "2026-10-13T14:00:00+00:00", "http_status": 200, "bytes": 1})
    store.close()
    assert store.latest_ok() == {1: "2026-10-13T12:00:00+00:00", 4: "2026-10-13T14:00:00+00:00"}


def test_needs_fetch(tmp_path):
    from datetime import datetime, timezone

    raw = tmp_path / "1.json.gz"
    assert collector.needs_fetch(raw, "2026-10-13T12:00:00+00:00", None)  # no raw file
    raw.write_bytes(gzip.compress(b"{}"))
    assert collector.needs_fetch(raw, None, None)  # raw without a 200 manifest line
    assert not collector.needs_fetch(raw, "2026-10-13T12:00:00+00:00", None)
    cutoff = datetime(2026, 10, 13, 13, tzinfo=timezone.utc)
    assert collector.needs_fetch(raw, "2026-10-13T12:00:00+00:00", cutoff)
    assert not collector.needs_fetch(raw, "2026-10-13T14:00:00+00:00", cutoff)


def test_detect_block():
    assert collector.detect_block(403, "application/json", b"{}") == "http_403"
    assert collector.detect_block(503, "text/html", b"<html>Just a moment...</html>") == "challenge_page"
    assert collector.detect_block(200, "text/html", b"<html>hello</html>") == "non_json_200"
    assert collector.detect_block(200, "application/json; charset=utf-8", b'{"captcha_team": 1}') is None
    assert collector.detect_block(500, "text/plain", b"oops") is None


# --------------------------------------------------------------------------- fetcher behaviour


def _fetcher(handler, stop=None, reported=None):
    return collector.Fetcher(
        "https://fixture.invalid", 5.0, 2, stop or threading.Event(), acquire=lambda: None,
        report_429=(reported.append if reported is not None else (lambda s: None)),
        transport=httpx.MockTransport(handler), backoff_base=0.0,
    )


def test_fetcher_retries_429_and_5xx_then_succeeds():
    responses = [httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(502, text="bad gateway"),
                 httpx.Response(200, json={"id": 1})]
    reported, logged = [], []
    f = _fetcher(lambda req: responses.pop(0), reported=reported)
    res = f.get("/api/data/playerData", {"id": 1}, lambda st, nb, ts: logged.append(st))
    assert isinstance(res, collector.Fetched) and res.data == {"id": 1} and res.attempts == 3
    assert reported == [7.0] and logged == [429, 502]


def test_fetcher_retries_a_transient_limiter_oserror_before_requesting():
    state = {"fails": 2, "acquired": 0}

    def flaky_acquire():
        if state["fails"]:
            state["fails"] -= 1
            raise PermissionError(13, "access denied (simulated Windows file lock)")
        state["acquired"] += 1

    calls = []
    f = collector.Fetcher("https://fixture.invalid", 5.0, 0, threading.Event(), acquire=flaky_acquire,
                          report_429=lambda s: None,
                          transport=httpx.MockTransport(lambda req: calls.append(1) or httpx.Response(200, json={"id": 1})),
                          backoff_base=0.0)
    res = f.get("/x", {}, lambda *a: None)
    assert isinstance(res, collector.Fetched) and f.limiter_retries == 2
    assert state["acquired"] == 1 and len(calls) == 1  # one request, sent only after acquire() succeeded


def test_run_pool_logs_unexpected_exceptions_and_continues(tmp_path):
    errors = collector.ErrorLog(tmp_path / "errors.jsonl")
    state = collector.RunState(max_consecutive_failures=5, deadline=None)
    seen = []

    def handle(item):
        seen.append(item)
        if item == 2:
            raise ValueError("synthetic failure")
        return True

    counts = collector.run_pool([1, 2, 3], handle, 1, 0.0, threading.Event(), state, "players",
                                errors=errors, kind="player")
    errors.close()
    assert seen == [1, 2, 3] and counts["ok"] == 2 and counts["failed"] == 1
    rows = _read(tmp_path / "errors.jsonl")
    assert [(r["kind"], r["id"], r["error"]) for r in rows] == [("player", 2, "unexpected_exception")]
    assert "synthetic failure" in rows[0]["detail"]


def test_fetcher_404_is_not_retried():
    calls = []
    f = _fetcher(lambda req: calls.append(1) or httpx.Response(404, text="nf"))
    res = f.get("/x", {}, lambda *a: None)
    assert isinstance(res, collector.Failed) and res.error == "http_404" and len(calls) == 1


@pytest.mark.parametrize("response", [
    httpx.Response(403, text="forbidden"),
    httpx.Response(200, text="<html><div class='cf-chl'>captcha</div></html>", headers={"content-type": "text/html"}),
])
def test_fetcher_stops_everything_on_block(response):
    stop = threading.Event()
    f = _fetcher(lambda req: response, stop=stop)
    with pytest.raises(collector.Blocked):
        f.get("/x", {}, lambda *a: None)
    assert stop.is_set()


# --------------------------------------------------------------------------- end to end (synthetic, tmp_path)


def _mock_api(counter):
    leagues = {47: _league_fixture(47, [1, 2]), 42: _league_fixture(42, [1, 3])}
    teams = {1: _team_fixture(1, [101, 102]), 2: _team_fixture(2, [201, 202]), 3: _team_fixture(3, [301, 102])}

    def handler(req):
        counter.append(req.url.path)
        q = dict(req.url.params)
        if req.url.path == "/api/data/leagues":
            assert q["season"] == "2026/2027"
            return httpx.Response(200, json=leagues[int(q["id"])])
        if req.url.path == "/api/data/teams":
            return httpx.Response(200, json=teams[int(q["id"])])
        if req.url.path == "/api/data/playerData":
            pid = int(q["id"])
            if pid == 202:
                return httpx.Response(404, text="nf")
            return httpx.Response(200, json=_player_fixture(pid, team_id=pid // 100))
        return httpx.Response(404)

    return handler


def _read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_collect_end_to_end_resume_refresh_and_from_raw(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    args = collector.parse_args(["--leagues", "47,42", "--raw-root", str(raw), "--out-dir", str(out),
                                 "--base-url", "https://fixture.invalid", "--max-retries", "0"])
    args.delay, args.backoff_base = 0.0, 0.0
    calls = []
    rc = collector.collect(args, transport=httpx.MockTransport(_mock_api(calls)), acquire=lambda: None,
                           report_429=lambda s: None)
    assert rc == 0
    # 2 league lists + 3 squads + 5 unique squad players (102 is listed by clubs 1 and 3)
    assert len(calls) == 10
    teams = {t["team_id"]: t for t in _read(out / "teams_2026_27.jsonl")}
    assert set(teams) == {1, 2, 3}
    assert teams[1]["competition_ids"] == [47, 42] and teams[3]["group"] == "european_cup_only"
    assert teams[1]["coach"]["name"] == "Fixture Coach" and teams[1]["squad_player_count"] == 2
    squad = _read(out / "squad_members_2026_27.jsonl")
    assert len(squad) == 6
    players = {p["player_id"]: p for p in _read(out / "players.jsonl")}
    assert set(players) == {101, 102, 201, 301}  # 202 answered 404 -> missing, not invented
    assert players[102]["squad_team_ids"] == [1, 3]
    manifest = _read(raw / "fotmob_players" / "_manifest.jsonl")
    assert {(m["id"], m["http_status"]) for m in manifest} == {(101, 200), (102, 200), (201, 200), (202, 404), (301, 200)}
    assert set(manifest[0]) == {"id", "fetched_at", "http_status", "bytes"}
    body = json.loads(gzip.decompress((raw / "fotmob_players" / "101.json.gz").read_bytes()))
    assert body == _player_fixture(101, team_id=1)  # untouched response body
    errors = _read(out / "collect_errors.jsonl")
    assert [(e["kind"], e["id"], e["error"]) for e in errors] == [("player", 202, "http_404")]
    snapshot = {p: players[p]["snapshot_at"] for p in players}

    # resume: everything already cached -> only the 404 player is retried
    calls.clear()
    assert collector.collect(args, transport=httpx.MockTransport(_mock_api(calls)), acquire=lambda: None,
                             report_429=lambda s: None) == 0
    assert calls == ["/api/data/playerData"]

    # offline rebuild reproduces the same parsed rows
    before = {name: (out / name).read_text(encoding="utf-8") for name in collector.output_names("2026/2027").values()}
    collector.build_outputs(raw, out, [47, 42], "2026/2027")
    after = {name: (out / name).read_text(encoding="utf-8") for name in collector.output_names("2026/2027").values()}
    assert before == after
    assert {p["player_id"]: p["snapshot_at"] for p in _read(out / "players.jsonl")} == snapshot

    # --refresh-older-than 0: every snapshot is older than "now" -> everything is fetched again
    calls.clear()
    args.refresh_older_than = 0.0
    assert collector.collect(args, transport=httpx.MockTransport(_mock_api(calls)), acquire=lambda: None,
                             report_429=lambda s: None) == 0
    assert len(calls) == 10  # 2 + 3 + 5 unique players (202 is requested again and 404s again)


def test_collect_fetches_fallback_lineup_for_club_without_squad(tmp_path):
    leagues = {42: _league_fixture(42, [1, 31])}
    teams = {1: _team_fixture(1, [101, 102]), 31: _no_squad_team_fixture(31, last_lineup=False)}
    calls = []

    def handler(req):
        calls.append((req.url.path, dict(req.url.params)))
        q = dict(req.url.params)
        if req.url.path == "/api/data/leagues":
            return httpx.Response(200, json=leagues[int(q["id"])])
        if req.url.path == "/api/data/teams":
            return httpx.Response(200, json=teams[int(q["id"])])
        if req.url.path == "/api/data/matchDetails":
            mid = int(q["matchId"])
            return httpx.Response(200, json=_match_fixture(mid, 31, with_lineup=(mid == 8821)))
        return httpx.Response(200, json=_player_fixture(int(q["id"])))

    args = collector.parse_args(["--leagues", "42", "--raw-root", str(tmp_path / "raw"), "--out-dir",
                                 str(tmp_path / "out"), "--base-url", "https://fixture.invalid"])
    args.delay, args.backoff_base = 0.0, 0.0
    assert collector.collect(args, transport=httpx.MockTransport(handler), acquire=lambda: None,
                             report_429=lambda s: None) == 0
    # the last match has no line-up -> the collector walks back to the previous finished match
    assert [c for c in calls if c[0] == "/api/data/matchDetails"] == [
        ("/api/data/matchDetails", {"matchId": "8831"}), ("/api/data/matchDetails", {"matchId": "8821"})]
    assert (tmp_path / "raw" / "fotmob_squads_fallback_matches" / "8821.json.gz").exists()
    players = {p["player_id"] for p in _read(tmp_path / "out" / "players.jsonl")}
    assert players == {101, 102, 81, 82}
    teams_out = {t["team_id"]: t for t in _read(tmp_path / "out" / "teams_2026_27.jsonl")}
    assert teams_out[31]["roster_source"] == "matchDetails.content.lineup" and teams_out[31]["squad_list_sent"] is False
    assert teams_out[1]["roster_source"] == "squad" and teams_out[1]["team_response_available"] is True


def test_club_without_team_response_keeps_the_schema_with_nulls(tmp_path):
    calls = []
    inner = _mock_api(calls)

    def handler(req):
        if req.url.path == "/api/data/teams" and req.url.params["id"] == "2":
            return httpx.Response(503, text="unavailable")
        return inner(req)

    args = collector.parse_args(["--leagues", "47", "--raw-root", str(tmp_path / "raw"), "--out-dir",
                                 str(tmp_path / "out"), "--base-url", "https://fixture.invalid", "--max-retries", "0"])
    args.delay, args.backoff_base = 0.0, 0.0
    collector.collect(args, transport=httpx.MockTransport(handler), acquire=lambda: None, report_429=lambda s: None)
    teams = {t["team_id"]: t for t in _read(tmp_path / "out" / "teams_2026_27.jsonl")}
    assert set(teams[1]) == set(teams[2])
    assert teams[2]["team_response_available"] is False and teams[2]["snapshot_at"] is None
    assert teams[2]["roster_source"] is None and teams[2]["coach"] is None and teams[2]["squad_list_sent"] is None
    assert teams[2]["name"] == "Fixture Club 2"  # from the league table
    errors = _read(tmp_path / "out" / "collect_errors.jsonl")
    assert [(e["kind"], e["id"], e["error"], e["http_status"]) for e in errors] == [("team", 2, "http_503", 503)]


def test_teams_only_skips_player_requests(tmp_path):
    args = collector.parse_args(["--leagues", "47", "--raw-root", str(tmp_path / "raw"), "--out-dir",
                                 str(tmp_path / "out"), "--base-url", "https://fixture.invalid", "--teams-only"])
    args.delay, args.backoff_base = 0.0, 0.0
    calls = []
    assert collector.collect(args, transport=httpx.MockTransport(_mock_api(calls)), acquire=lambda: None,
                             report_429=lambda s: None) == 0
    assert calls.count("/api/data/playerData") == 0 and calls.count("/api/data/teams") == 2
    assert len(_read(tmp_path / "out" / "squad_members_2026_27.jsonl")) == 4
    assert _read(tmp_path / "out" / "players.jsonl") == []


def test_blocked_run_returns_exit_code_2(tmp_path):
    args = collector.parse_args(["--leagues", "47", "--raw-root", str(tmp_path / "raw"), "--out-dir",
                                 str(tmp_path / "out"), "--base-url", "https://fixture.invalid", "--no-build"])
    args.delay, args.backoff_base = 0.0, 0.0
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(403, text="forbidden")

    assert collector.collect(args, transport=httpx.MockTransport(handler), acquire=lambda: None,
                             report_429=lambda s: None) == 2
    assert len(calls) == 1  # stopped at the first 403, nothing else was requested
    manifest = _read(tmp_path / "raw" / "fotmob_squads_leagues" / "_manifest.jsonl")
    assert manifest[0]["http_status"] == 403 and manifest[0]["season"] == "2026/2027"
