"""scripts/live/load_player_data.py and refresh_team_news.py (no network).

Raw files are SYNTHETIC payloads written to a temp dir; the target DB is a
scratch SQLite file.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select

from app.database.models import (
    Base,
    LineupSnapshot,
    Player,
    PlayerAvailability,
    PlayerMatchStat,
    TeamSquadMember,
)
from tests.test_team_news_fixtures import (
    SYN_HOME_TEAM,
    syn_player_id,
    synthetic_injury,
    synthetic_match_payload,
    synthetic_player_payload,
    synthetic_team_payload,
)

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "live"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"tn_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_gz(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(payload).encode("utf-8")))


@pytest.fixture()
def raw_root(tmp_path):
    root = tmp_path / "raw_cache"
    hp = lambda n: syn_player_id(SYN_HOME_TEAM, n)  # noqa: E731
    write_gz(
        root / "fotmob_match_details" / "6900001.json.gz",
        synthetic_match_payload(
            6900001, kickoff="2026-10-04T15:00:00.000Z", status="finished", lineup_type="standard",
            home_score=1, away_score=0, unavailable={"home": [(14, "injury", "Unknown")], "away": []},
            stats={hp(9): {"minutes": 90, "rating": 7.1, "goals": 1, "xg": 0.4, "shotmap": 1}},
        ),
    )
    (root / "fotmob_match_details" / "6900002.json.gz").write_bytes(b"not gzip")  # unreadable
    write_gz(root / "fotmob_teams" / f"{SYN_HOME_TEAM}.json.gz", synthetic_team_payload(injured={5: ("30", "Unknown")}))
    (root / "fotmob_teams" / "_manifest.jsonl").write_text(
        json.dumps({"id": SYN_HOME_TEAM, "fetched_at": "2026-10-13T18:21:07+00:00", "http_status": 200, "bytes": 1})
        + "\n"
        + json.dumps({"id": 123, "fetched_at": "2026-10-13T18:22:07+00:00", "http_status": 404, "bytes": 0})
        + "\n"
        + '{"id": 990009, "fetched_at": "2026-10-13T18:2',  # partial last line
        encoding="utf-8",
    )
    write_gz(root / "fotmob_players" / f"{hp(5)}.json.gz", synthetic_player_payload(hp(5), injury=synthetic_injury()))
    (root / "fotmob_players" / f"{hp(6)}.json.gz").write_bytes(b"\x1f\x8b broken")
    (root / "fotmob_players" / "_manifest.jsonl").write_text(
        "\n".join(
            json.dumps({"id": pid, "fetched_at": "2026-10-13T18:30:00+00:00", "http_status": 200, "bytes": 1})
            for pid in (hp(5), hp(6))
        )
        + "\n",
        encoding="utf-8",
    )
    return root


def counts(url: str) -> dict[str, int]:
    engine = create_engine(url)
    try:
        with engine.connect() as c:
            return {
                m.__tablename__: c.execute(select(func.count()).select_from(m)).scalar_one()
                for m in (Player, TeamSquadMember, PlayerAvailability, PlayerMatchStat, LineupSnapshot)
            }
    finally:
        engine.dispose()


def test_load_player_data_backfill_is_idempotent(raw_root, tmp_path, monkeypatch, capsys):
    url = f"sqlite:///{(tmp_path / 'scratch.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)  # restored after the test (main() sets it too)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    loader = load_script("load_player_data")
    assert loader.main(["--database-url", url, "--raw-root", str(raw_root), "--all-files"]) == 0
    first = counts(url)
    assert first["player_match_stats"] == 22 and first["lineup_snapshots"] == 2 and first["team_squad_members"] == 14
    # availability: match list (1) + squad (1) + profile (1)
    assert first["player_availability"] == 3
    assert loader.main(["--database-url", url, "--raw-root", str(raw_root), "--all-files"]) == 0
    assert counts(url) == first  # idempotent
    out = capsys.readouterr().out
    assert '"unreadable": 1' in out  # broken match file / broken player file are skipped and counted


def test_scripts_refuse_production_and_unmigrated_db(tmp_path, monkeypatch):
    loader = load_script("load_player_data")
    prod = (Path(__file__).resolve().parents[1] / "football_intelligence.db").as_posix()
    with pytest.raises(SystemExit):
        loader.main(["--database-url", f"sqlite:///{prod}"])
    url = f"sqlite:///{(tmp_path / 'empty.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    assert loader.main(["--database-url", url]) == 2  # tables missing
    refresher = load_script("refresh_team_news")
    with pytest.raises(SystemExit):
        refresher.main(["--once", "--database-url", f"sqlite:///{prod}"])
    assert refresher.main(["--once", "--database-url", url]) == refresher.EXIT_NOT_MIGRATED
