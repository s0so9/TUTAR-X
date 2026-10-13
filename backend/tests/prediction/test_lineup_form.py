"""Tests for the lineup-form adjustment (app.prediction.lineup_form). Fixture values are synthetic."""

import json

from app.prediction.lineup_form import LineupForm, get_lineup_form


def _form():
    players = {str(i): 7.0 for i in range(1, 12)} | {str(i): 6.5 for i in range(21, 32)} | {"99": 6.0}
    return LineupForm(gamma=0.1, players=players, usual={"H": 7.0, "A": 6.5}, min_known=7)


def test_weaker_than_usual_home_xi_lowers_home_supremacy():
    form = _form()
    usual = form.shift("H", [str(i) for i in range(1, 12)], "A", [str(i) for i in range(21, 32)])
    assert abs(usual) < 1e-12
    weakened = [str(i) for i in range(1, 9)] + ["99", "99", "99"]   # three regulars replaced
    assert form.shift("H", weakened, "A", [str(i) for i in range(21, 32)]) < 0


def test_unknown_xi_or_team_means_no_adjustment():
    form = _form()
    assert form.shift("H", ["x"] * 11, "A", [str(i) for i in range(21, 32)]) is None
    assert form.shift(None, [], "A", []) is None
    assert form.shift("H", [str(i) for i in range(1, 12)], "Z", [str(i) for i in range(21, 32)]) is None


def test_config_loading(tmp_path):
    good = tmp_path / "player_form.json"
    good.write_text(json.dumps({"gamma_form": 0.12, "players": {"1": 7.0}, "teams_usual_xi": {"H": 7.0}}))
    assert get_lineup_form.__wrapped__(good).gamma == 0.12
    assert get_lineup_form.__wrapped__(tmp_path / "missing.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"gamma_form": 5, "players": {}, "teams_usual_xi": {}}))
    assert get_lineup_form.__wrapped__(bad) is None
