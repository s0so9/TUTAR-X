"""Parsers of the team-news layer (SYNTHETIC fixtures + one optional real raw file)."""

from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.team_news.constants import (
    SOURCE_MATCH_LINEUP,
    SOURCE_PLAYER_PROFILE,
    SOURCE_TEAM_SQUAD,
)
from app.services.team_news.parsers import (
    PayloadError,
    parse_league_fixtures,
    parse_match_payload,
    parse_player_payload,
    parse_team_payload,
    parse_utc,
    status_for_raw_type,
)
from tests.test_team_news_fixtures import (
    SYN_AWAY_TEAM,
    SYN_HOME_TEAM,
    syn_player_id,
    synthetic_injury,
    synthetic_league_payload,
    synthetic_match_payload,
    synthetic_player_payload,
    synthetic_team_payload,
)

T0 = datetime(2026, 10, 13, 18, 0, tzinfo=timezone.utc)


def test_parse_utc_variants():
    assert parse_utc("2026-10-13T19:00:00.000Z") == datetime(2026, 10, 13, 19, 0, tzinfo=timezone.utc)
    assert parse_utc("2026-10-14T19:00:00Z") == datetime(2026, 10, 14, 19, 0, tzinfo=timezone.utc)
    assert parse_utc({"utcTime": "2026-08-01T00:00:00+00:00"}) == datetime(2026, 8, 1, tzinfo=timezone.utc)
    assert parse_utc(None) is None and parse_utc("garbage") is None


def test_status_mapping_keeps_unknown_as_other():
    assert status_for_raw_type("injury") == "injured"
    assert status_for_raw_type("suspension") == "suspended"
    assert status_for_raw_type("internationalDuty") == "international_duty"
    assert status_for_raw_type("Doubtful") == "doubtful"
    assert status_for_raw_type("somethingNew") == "other"
    assert status_for_raw_type(None) == "other"


def test_team_payload_members_injuries_and_coach_skipped():
    data = synthetic_team_payload(injured={2: ("45", "Back in training"), 7: ("30", "Late October 2026")})
    parsed = parse_team_payload(data, T0)
    assert parsed.team_provider_id == str(SYN_HOME_TEAM)
    assert parsed.season == "2026/2027"
    assert parsed.squad_sent is True
    assert parsed.skipped_non_players == 1  # the coach
    assert len(parsed.members) == 14
    m2 = next(m for m in parsed.members if m.player.provider_id == str(syn_player_id(SYN_HOME_TEAM, 2)))
    assert m2.role == "defenders" and m2.role_key == "defender_long"
    assert m2.player.positions == [{"id": 34, "label": "CB"}, {"id": 38, "label": "LB"}]
    assert m2.player.market_value_eur == 2_000_000
    assert m2.player.market_value_as_of is None  # the squad endpoint sends no valuation date
    assert m2.player.source == SOURCE_TEAM_SQUAD and m2.player.team_provider_id == str(SYN_HOME_TEAM)
    assert m2.availability is not None
    assert (m2.availability.status, m2.availability.injury_id, m2.availability.expected_return) == (
        "injured", "45", "Back in training",
    )
    fit = [m for m in parsed.members if m.availability is None]
    assert len(fit) == 12


def test_team_payload_without_squad_or_id():
    parsed = parse_team_payload(synthetic_team_payload(include_squad=False), T0)
    assert parsed.squad_sent is False and parsed.members == []
    empty = synthetic_team_payload()
    empty["squad"]["squad"] = []  # FotMob sends this for a few teams
    assert parse_team_payload(empty, T0).squad_sent is False
    with pytest.raises(PayloadError):
        parse_team_payload({"details": {}}, T0)


def test_player_payload_profile_and_injury():
    pid = syn_player_id(SYN_HOME_TEAM, 3)
    parsed = parse_player_payload(synthetic_player_payload(pid, injury=synthetic_injury()), T0)
    p = parsed.player
    assert p.source == SOURCE_PLAYER_PROFILE
    assert (p.date_of_birth, p.contract_end) == ("2001-03-24", "2030-06-30")
    assert (p.height_cm, p.shirt_number, p.preferred_foot, p.country_code) == (190, 4, "left", "SYN")
    assert p.primary_position == "Center Back"
    assert p.positions == [{"id": 34, "label": "CB", "name": "Center Back", "is_main": True}]
    assert p.market_value_eur == 6_000_000  # latest dated EUR value
    assert p.market_value_as_of == datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert p.team_provider_id == str(SYN_HOME_TEAM)
    assert parsed.availability_sent is True
    [a] = parsed.availability
    assert (a.status, a.reason, a.injury_id, a.expected_return) == (
        "injured", "Synthetic knock", "45", "Late October 2026",
    )
    assert a.source_updated_at == datetime(2026, 10, 10, tzinfo=timezone.utc)


def test_player_payload_no_injury_vs_keys_absent():
    pid = syn_player_id(SYN_HOME_TEAM, 3)
    fit = parse_player_payload(synthetic_player_payload(pid, injury=None), T0)
    assert fit.availability == [] and fit.availability_sent is True  # null = nothing reported
    del_payload = synthetic_player_payload(pid, include_injury_key=False)
    del_payload.pop("internationalDuty")
    unknown = parse_player_payload(del_payload, T0)
    assert unknown.availability_sent is False  # keys absent: cannot clear earlier reports


def test_match_payload_prematch_predicted_lineup_and_unavailable_semantics():
    data = synthetic_match_payload(
        6100001,
        unavailable={"home": [(2, "injury", "Late October 2026"), (5, "suspension", "Unknown")], "away": None},
    )
    p = parse_match_payload(data, T0)
    assert p.provider_match_id == "6100001" and p.status == "scheduled"
    assert p.competition_provider_id == "47" and p.league_id == "900047"
    assert p.kickoff_at == datetime(2026, 10, 20, 19, tzinfo=timezone.utc)
    assert p.lineup_type == "predicted"
    home, away = p.sides["home"], p.sides["away"]
    assert len(home.starters) == 11 and home.formation == "4-3-3"
    assert home.starters[0] == {
        "id": syn_player_id(SYN_HOME_TEAM, 1), "name": f"Synthetic Player {SYN_HOME_TEAM}-1",
        "shirt_number": 1, "position_id": 11, "usual_position_id": 0,
    }
    assert home.bench is None  # no `subs` key sent (predicted line-ups)
    assert [(u.status, u.raw_type) for u in home.unavailable] == [("injured", "injury"), ("suspended", "suspension")]
    assert home.unavailable[0].injury_id == "30"
    assert away.unavailable is None  # key absent -> not sent (must not clear anything)
    assert p.player_stats == []
    assert all(o.source == SOURCE_MATCH_LINEUP for o in home.players)


def test_match_payload_empty_unavailable_list_is_not_none():
    p = parse_match_payload(synthetic_match_payload(6100002, unavailable={"home": [], "away": []}), T0)
    assert p.sides["home"].unavailable == [] and p.sides["away"].unavailable == []


def test_match_payload_finished_player_stats_and_cards():
    hp = lambda n: syn_player_id(SYN_HOME_TEAM, n)  # noqa: E731
    data = synthetic_match_payload(
        6100003,
        status="finished",
        lineup_type="standard",
        with_bench=True,
        home_score=2,
        away_score=1,
        stats={
            hp(9): {"minutes": 90, "rating": 7.8, "goals": 2, "xg": 1.35, "shotmap": 4},
            hp(4): {"minutes": 90, "rating": 6.9, "goals": 0, "shotmap": 0},  # no shot: FotMob omits xG
            hp(12): {"minutes": 15, "rating": 6.1, "goals": 0, "shotmap": 0},
        },
        subs_in={hp(12): 75},
        cards=[(hp(4), "Yellow"), (hp(4), "YellowRed")],
    )
    p = parse_match_payload(data, T0)
    assert p.status == "finished" and (p.home_score, p.away_score) == (2, 1)
    rows = {r["player_provider_id"]: r for r in p.player_stats}
    assert len(rows) == 11 + 3 + 11 + 3
    scorer = rows[str(hp(9))]
    assert (scorer["minutes"], scorer["rating"], scorer["goals"], scorer["xg"]) == (90, 7.8, 2, 1.35)
    assert scorer["started"] is True and scorer["appeared"] is True and scorer["shotmap_count"] == 4
    defender = rows[str(hp(4))]
    assert defender["xg"] is None and defender["stats_available"] is True and defender["shotmap_count"] == 0
    assert (defender["yellow_cards"], defender["red_cards"]) == (1, 1)
    sub = rows[str(hp(12))]
    assert sub["started"] is False and sub["appeared"] is True and sub["sub_in_minute"] == 75
    unused = rows[str(hp(13))]
    assert unused["appeared"] is False and unused["minutes"] is None and unused["stats_available"] is False
    assert unused["yellow_cards"] == 0  # event list sent and has no card for him
    assert p.sides["home"].bench is not None and len(p.sides["home"].bench) == 3


def test_match_payload_without_event_list_has_unknown_cards():
    data = synthetic_match_payload(6100004, status="finished", home_score=0, away_score=0, with_events=False)
    p = parse_match_payload(data, T0)
    assert p.events_sent is False
    assert all(r["yellow_cards"] is None and r["red_cards"] is None for r in p.player_stats)


def test_league_fixtures():
    data = synthetic_league_payload(
        47,
        [
            {"id": 7001, "home": SYN_HOME_TEAM, "away": SYN_AWAY_TEAM, "utcTime": "2026-10-20T19:00:00Z"},
            {"id": 7002, "home": SYN_AWAY_TEAM, "away": SYN_HOME_TEAM, "utcTime": "2026-10-01T19:00:00Z", "finished": True},
        ],
    )
    fx = parse_league_fixtures(data, "47")
    assert [(f.provider_match_id, f.status) for f in fx] == [("7001", "scheduled"), ("7002", "finished")]
    assert fx[0].home_team_provider_id == str(SYN_HOME_TEAM)


def test_real_raw_match_details_shape_if_present():
    """Format check against one untouched FotMob body from the shared raw cache (read-only).

    Skipped when the cache is not on this machine."""
    raw_dir = Path(__file__).resolve().parents[1] / "data" / "raw_cache" / "fotmob_match_details"
    files = sorted(raw_dir.glob("*.json.gz"))[:3] if raw_dir.exists() else []
    if not files:
        pytest.skip("raw FotMob match-details cache not present")
    for f in files:
        data = json.loads(gzip.decompress(f.read_bytes()))
        p = parse_match_payload(data, T0)
        assert p.provider_match_id == f.name.split(".")[0]
        assert p.status == "finished"
        assert p.sides["home"].starters and p.sides["away"].starters
        assert p.player_stats and all(r["player_provider_id"] for r in p.player_stats)
        assert any(r["minutes"] is not None for r in p.player_stats)


def test_match_payload_last_starting11_placeholder():
    data = synthetic_match_payload(6100005, lineup_type="lastStarting11", last_match=6099999, with_bench=True)
    p = parse_match_payload(data, T0)
    assert p.lineup_type == "lastStarting11"
    assert p.sides["home"].based_on_match_id == "6099999" and p.sides["away"].based_on_match_id == "6099999"
    assert parse_match_payload(synthetic_match_payload(6100006), T0).sides["home"].based_on_match_id is None
