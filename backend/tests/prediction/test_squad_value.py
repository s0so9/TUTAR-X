"""Tests for the starting-XI market value adjustment (app.prediction.squad_value)."""

import math

from app.prediction.squad_value import (
    SQUAD_VALUE_BETA,
    _parse_side,
    squad_value_multipliers,
)


def test_richer_side_gets_more_expected_goals():
    home_mult, away_mult, x = squad_value_multipliers(1_000_000_000, 50_000_000)
    assert x == math.log(20)
    assert home_mult > 1 > away_mult
    assert math.isclose(home_mult * away_mult, 1.0)
    assert math.isclose(home_mult, math.exp(SQUAD_VALUE_BETA * math.log(20)))


def test_equal_values_change_nothing():
    home_mult, away_mult, x = squad_value_multipliers(300e6, 300e6)
    assert (home_mult, away_mult, x) == (1.0, 1.0, 0.0)


def test_missing_values_mean_no_adjustment():
    assert squad_value_multipliers(None, 300e6) is None
    assert squad_value_multipliers(300e6, 0) is None


def test_parse_side_reads_unavailable_players():
    side = _parse_side(
        {
            "name": "Arsenal",
            "totalStarterMarketValue": 604395264,
            "unavailable": [
                {"name": "William Saliba", "marketValue": 120390607,
                 "unavailability": {"type": "injury", "expectedReturn": "Back in training"}},
            ],
        },
        "predicted",
    )
    assert side.starter_value == 604395264.0
    assert side.lineup_type == "predicted"
    assert side.unavailable[0].name == "William Saliba"
    assert side.unavailable[0].reason == "injury"


def test_parse_side_without_value_is_unavailable():
    assert _parse_side({"name": "X"}, None).starter_value is None


def test_missing_unavailable_key_is_no_data_not_zero():
    # e.g. Bayern in FotMob match 6106240: no "unavailable" key at all
    side = _parse_side({"name": "Bayern", "totalStarterMarketValue": 900e6}, "predicted")
    assert side.unavailable is None


def test_finished_match_has_no_pre_match_injury_data():
    # Finished matches: the list is not the pre-match report
    side = _parse_side({"name": "X", "totalStarterMarketValue": 1e8, "unavailable": []}, "standard",
                       match_finished=True)
    assert side.unavailable is None


def test_confirmed_pre_kickoff_lineup_keeps_its_list():
    # 2026-10-13 Lens-Sporting: confirmed XI before kickoff, players listed
    side = _parse_side({"name": "Lens", "totalStarterMarketValue": 1e8, "unavailable": [
        {"name": "P", "unavailability": {"type": "injury"}}]}, "standard", match_finished=False)
    assert [p.name for p in side.unavailable] == ["P"]


def test_upcoming_match_with_empty_list_means_nobody_reported_missing():
    side = _parse_side({"name": "X", "totalStarterMarketValue": 1e8, "unavailable": []}, "predicted")
    assert side.unavailable == []


def test_unavailable_count_feature_is_none_without_data():
    from app.features.match_features import squad_feature_values
    from app.prediction.squad_value import TeamSquadInfo

    no_data = TeamSquadInfo(team_name="H", starter_value=1e8, lineup_type="standard", unavailable=None)  # finished
    reported = TeamSquadInfo(team_name="A", starter_value=2e8, lineup_type="predicted", unavailable=[])
    values = squad_feature_values((no_data, reported))
    assert values["home_unavailable_count"] is None      # no data, never 0
    assert values["away_unavailable_count"] == 0.0       # pre-match list, nobody listed
    assert values["home_starter_value"] == 1e8
    assert squad_feature_values(None) == {
        "home_starter_value": None, "home_unavailable_count": None,
        "away_starter_value": None, "away_unavailable_count": None,
    }
