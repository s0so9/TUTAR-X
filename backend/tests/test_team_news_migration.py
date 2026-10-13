"""Alembic revision 20261013_team_news: upgrade / downgrade on a scratch SQLite file.

The Alembic Config is built without alembic.ini so env.py does not call
logging.fileConfig (which would disable the loggers other tests rely on).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.config import settings
from app.database import models  # noqa: F401  (registers the models)
from app.database.base import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]
NEW_TABLES = {"team_squad_members", "player_availability", "player_match_stats", "lineup_snapshots", "team_news_matches"}
NEW_PLAYER_COLUMNS = {
    "team_provider_id", "country_code", "primary_position", "positions", "preferred_foot", "market_value_eur",
    "market_value_as_of", "market_value_source", "contract_end", "profile_source", "profile_observed_at",
}


@pytest.fixture()
def alembic_cfg(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'scratch_migration.db').as_posix()}"
    monkeypatch.setattr(settings, "database_url", url)  # env.py reads settings.database_url
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg, url


def test_upgrade_matches_models_then_downgrade_and_reupgrade(alembic_cfg):
    cfg, url = alembic_cfg
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    try:
        insp = inspect(engine)
        assert NEW_TABLES <= set(insp.get_table_names())
        assert NEW_PLAYER_COLUMNS <= {c["name"] for c in insp.get_columns("players")}
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            assert ctx.get_current_revision() == "20261013_team_news"
            assert compare_metadata(ctx, Base.metadata) == []  # migrated schema == ORM models

        command.downgrade(cfg, "20261013_pv_index_align")
        insp = inspect(engine)
        assert not (NEW_TABLES & set(insp.get_table_names()))
        assert not (NEW_PLAYER_COLUMNS & {c["name"] for c in insp.get_columns("players")})

        command.upgrade(cfg, "head")
        assert NEW_TABLES <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_single_head():
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert "20261013_team_news" in heads
