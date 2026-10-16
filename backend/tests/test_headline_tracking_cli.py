"""backend/scripts/live/headline_tracking.py: guards and an offline backfill into a scratch database."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine

from app.database.models import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND_DIR / "scripts" / "live" / "headline_tracking.py"


def run_cli(*args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    import os

    env = dict(os.environ)
    env.pop("DATABASE_URL", None)
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=BACKEND_DIR, env=env, capture_output=True, text=True,
        encoding="utf-8", timeout=120,
    )


def test_nothing_to_do_is_an_error():
    result = run_cli()
    assert result.returncode == 2 and "nothing to do" in result.stderr


def test_it_refuses_to_guess_the_database():
    result = run_cli("--once")
    assert result.returncode == 2 and "--database-url" in result.stderr


def test_it_refuses_the_production_file_without_the_flag():
    production = (BACKEND_DIR / "football_intelligence.db").as_posix()
    result = run_cli("--once", "--database-url", f"sqlite:///{production}")
    assert result.returncode != 0 and "--allow-production-db" in result.stderr


def test_backfill_into_a_scratch_database_is_idempotent(tmp_path):
    db = tmp_path / "scratch.db"
    Base.metadata.create_all(bind=create_engine(f"sqlite:///{db.as_posix()}"))
    url = f"sqlite:///{db.as_posix()}"

    first = run_cli("--backfill-2026-10-14", "--no-live", "--database-url", url)
    assert first.returncode == 0, first.stderr
    summary = json.loads(first.stdout)["backfill"]
    # no matches table rows in the scratch database: frozen, but nothing to settle against
    assert (summary["matches"], summary["frozen"], summary["settled"]) == (7, 14, 0)
    assert len(summary["unsettled"]) == 7

    second = run_cli("--backfill-2026-10-14", "--no-live", "--database-url", url)
    assert second.returncode == 0, second.stderr
    again = json.loads(second.stdout)["backfill"]
    assert (again["frozen"], again["already_there"]) == (0, 14)

    rows = sqlite3.connect(db).execute(
        "select stage, count(*) from prediction_versions group by stage order by stage"
    ).fetchall()
    assert rows == [("headline_banko", 7), ("headline_oranli", 7)]
