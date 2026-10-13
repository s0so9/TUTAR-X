"""Tests for the trained goal layer (app.prediction.goal_model)."""

import json
import math

from app.prediction.goal_model import GoalLayer, get_goal_layer


def test_identity_when_untrained():
    layer = GoalLayer()
    assert layer.adjust(2.2, 0.7) == (2.2, 0.7)


def test_shrinks_total_and_keeps_supremacy():
    layer = GoalLayer(m=math.log(1.35), a=0.6, b=0.0, trained=True)
    high_h, high_a = layer.adjust(3.0, 2.0)   # high-scoring prediction
    low_h, low_a = layer.adjust(0.8, 0.6)     # low-scoring prediction
    # totals move toward the mean from both sides
    assert high_h + high_a < 5.0
    assert low_h + low_a > 1.4
    # home/away ratio (supremacy) unchanged
    assert math.isclose(high_h / high_a, 1.5, rel_tol=1e-9)
    assert math.isclose(low_h / low_a, 0.8 / 0.6, rel_tol=1e-9)


def test_loads_config_and_rejects_bad_files(tmp_path):
    good = tmp_path / "goal_model.json"
    good.write_text(json.dumps({"params": {"m": 0.26, "a": 0.67, "b": 0.035, "rho": -0.023, "nb_dispersion": 49.0}}))
    layer = get_goal_layer.__wrapped__(good)
    assert layer.trained and layer.rho == -0.023 and layer.nb_dispersion == 49.0

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"params": {"m": 0.26, "a": 9.0, "b": 0.0}}))
    assert get_goal_layer.__wrapped__(bad).trained is False
    assert get_goal_layer.__wrapped__(tmp_path / "missing.json").trained is False


def test_shipped_config_is_trained():
    layer = get_goal_layer()
    assert layer.trained
    assert 0.3 < layer.a < 1.0
