"""Full multi-season run additions (2026-10-14): look-back grid in the trainer's time-forward
tuning, the runtime JSON export and its loader. All data here is SYNTHETIC TEST DATA."""

from __future__ import annotations

import csv
import gzip
import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "scripts" / "training"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import export_player_impact_latest as EX  # noqa: E402
import player_impact as PI  # noqa: E402
from app.prediction.player_impact import PlayerImpactRatings  # noqa: E402
from test_player_impact_stints import _write_synthetic_rapm_inputs  # noqa: E402


def _run(tmp_path: Path, extra: list[str]) -> tuple[list[dict], dict, Path, Path]:
    sp, dp = _write_synthetic_rapm_inputs(tmp_path)
    out, meta = tmp_path / "r.csv.gz", tmp_path / "m.json"
    rc = PI.main(["--stints", str(sp), "--details", str(dp), "--out", str(out), "--meta", str(meta),
                  "--start", "2026-02-01", "--end", "2026-03-01", "--step-days", "14", *extra])
    assert rc == 0
    with gzip.open(out, "rt", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(meta.read_text(encoding="utf-8")), out, meta


def test_lookback_grid_is_tuned_and_used(tmp_path):
    rows, meta, _o, _m = _run(tmp_path, ["--val-start", "2026-01-20", "--val-end", "2026-01-27",
                                         "--val-step-days", "7", "--val-window-days", "7",
                                         "--lambdas", "50,500", "--half-lives", "365", "--team-lambdas", "1e7",
                                         "--lookbacks", "5,60"])
    wmse = meta["validation"]["wmse"]
    assert any(k.startswith("lb5_") for k in wmse) and any(k.startswith("lb60_") for k in wmse)
    hp = meta["hyper_parameters"]
    chosen = hp["chosen_by_validation"]
    assert chosen.startswith(f"lb{hp['lookback_days']:g}_")
    full = {k: v for k, v in wmse.items() if "_full_" in k}
    assert wmse[chosen] == min(full.values())
    assert hp["grid"]["lookbacks"] == [5.0, 60.0]
    # validation windows stay before the last window end recorded in the meta file
    assert meta["validation"]["last_window_end"] == "2026-02-03"
    assert {r["cutoff"] for r in rows} == {"2026-02-01", "2026-02-15", "2026-03-01"}


def test_single_lookback_keeps_unprefixed_keys(tmp_path):
    _rows, meta, _o, _m = _run(tmp_path, ["--val-start", "2026-01-20", "--val-end", "2026-01-20",
                                          "--val-window-days", "7", "--lambdas", "50", "--half-lives", "365",
                                          "--team-lambdas", "1e7"])
    assert all(not k.startswith("lb") for k in meta["validation"]["wmse"])
    assert meta["hyper_parameters"]["lookback_days"] == 730.0


def test_export_latest_and_runtime_loader(tmp_path):
    rows, meta, out, meta_path = _run(tmp_path, ["--lambda", "50", "--half-life", "365", "--team-lambda", "1e7"])
    js = tmp_path / "latest.json"
    doc = EX.export(out, meta_path, js)
    assert doc["cutoff"] == "2026-03-01"
    last = {r["player_id"]: r for r in rows if r["cutoff"] == "2026-03-01"}
    assert set(doc["players"]) == set(last)
    for pid, r in last.items():
        p = doc["players"][pid]
        assert p["offence"] == float(r["offence"]) and p["defence"] == float(r["defence"])
        assert p["prior_only"] == ("prior_only" in r["flags"].split(";"))
        assert p["rapm_minutes"] == float(r["rapm_minutes"])
    rt = PlayerImpactRatings.load_latest_json(js)
    assert rt.cutoff == "2026-03-01"
    assert rt.get("1001").offence == float(last["1001"]["offence"])
    # an unknown player gets the replacement level of his position and is flagged
    xi = rt.xi_strength(["1001", "999999"], {"999999": "MID"})
    assert xi.unknown_player_ids == ("999999",) and "replacement_level_used" in xi.flags
    mid = meta["per_cutoff"][-1]["replacement_level"]["MID"]
    assert xi.contributions[1].offence == pytest.approx(mid["offence"])


def test_runtime_loader_rejects_bad_documents(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"format": "something_else", "cutoff": "2026-01-01", "players": {}}), encoding="utf-8")
    with pytest.raises(ValueError):
        PlayerImpactRatings.load_latest_json(bad)
    no_repl = tmp_path / "no_repl.json"
    no_repl.write_text(json.dumps({"format": EX.FORMAT, "cutoff": "2026-01-01",
                                   "players": {"1": {"offence": 0.1, "defence": 0.0}}}), encoding="utf-8")
    with pytest.raises(ValueError):
        PlayerImpactRatings.load_latest_json(no_repl)
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"format": EX.FORMAT, "cutoff": "2026-01-01", "players": {"1": {"offence": None}},
                                 "replacement_level": {"UNK": {"offence": 0.0, "defence": 0.0}}}), encoding="utf-8")
    with pytest.raises(ValueError):   # malformed entries are skipped, never filled in -> no ratings left
        PlayerImpactRatings.load_latest_json(empty)
