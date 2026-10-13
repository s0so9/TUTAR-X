"""Live layer: team news (player profile, squads, availability, line-ups, player match stats)

Revision ID: 20261013_team_news
Revises: 20261013_pv_index_align
Create Date: 2026-10-13

Adds the tables of the team-news live layer (docs/live-layer.md):

* players: profile columns (current team provider id, country code, primary
  position, positions, preferred foot, market value EUR + as-of date + source,
  contract end, profile source/observed_at). The existing table was unused.
* team_squad_members, player_availability, player_match_stats,
  lineup_snapshots, team_news_matches (new).

Every new column is nullable unless the layer always knows the value (ids,
timestamps of an observation, source labels). Types are PostgreSQL-ready
(String/Integer/BigInteger/Float/Boolean/DateTime(timezone=True)/JSON).

Production note: backend/football_intelligence.db was created with
Base.metadata.create_all() and has no alembic_version table. Apply with
  alembic stamp 20261013_pv_index_align && alembic upgrade head
(see docs/live-layer.md, "Apply / restart").
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20261013_team_news"
down_revision = "20261013_pv_index_align"
branch_labels = None
depends_on = None


def _base_columns():
    return [
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _player_columns():
    return [
        sa.Column("team_provider_id", sa.String(length=100), nullable=True),
        sa.Column("country_code", sa.String(length=10), nullable=True),
        sa.Column("primary_position", sa.String(length=50), nullable=True),
        sa.Column("positions", sa.JSON(), nullable=True),
        sa.Column("preferred_foot", sa.String(length=20), nullable=True),
        sa.Column("market_value_eur", sa.BigInteger(), nullable=True),
        sa.Column("market_value_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("market_value_source", sa.String(length=40), nullable=True),
        sa.Column("contract_end", sa.String(length=20), nullable=True),
        sa.Column("profile_source", sa.String(length=40), nullable=True),
        sa.Column("profile_observed_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade():
    # --- players: profile columns (plain ADD COLUMN works on SQLite and PostgreSQL)
    for column in _player_columns():
        op.add_column("players", column)
    op.create_index("ix_players_team_provider_id", "players", ["team_provider_id"], unique=False)

    # --- team_squad_members
    op.create_table(
        "team_squad_members",
        sa.Column("team_provider_id", sa.String(length=100), nullable=False),
        sa.Column("team_id", sa.String(length=36), nullable=True),
        sa.Column("player_id", sa.String(length=36), nullable=False),
        sa.Column("player_provider_id", sa.String(length=100), nullable=False),
        sa.Column("season", sa.String(length=20), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=True),
        sa.Column("role_key", sa.String(length=50), nullable=True),
        sa.Column("shirt_number", sa.Integer(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        *_base_columns(),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_provider_id", "player_provider_id", "season", name="uq_team_squad_member"),
    )
    op.create_index("ix_team_squad_members_team_id", "team_squad_members", ["team_id"], unique=False)
    op.create_index("ix_team_squad_members_player_id", "team_squad_members", ["player_id"], unique=False)
    op.create_index(
        "ix_team_squad_members_player_provider_id", "team_squad_members", ["player_provider_id"], unique=False
    )
    op.create_index("ix_team_squad_team_season", "team_squad_members", ["team_provider_id", "season"], unique=False)

    # --- player_availability
    op.create_table(
        "player_availability",
        sa.Column("player_id", sa.String(length=36), nullable=False),
        sa.Column("player_provider_id", sa.String(length=100), nullable=False),
        sa.Column("team_id", sa.String(length=36), nullable=True),
        sa.Column("team_provider_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("raw_type", sa.String(length=50), nullable=True),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.Column("injury_id", sa.String(length=50), nullable=True),
        sa.Column("expected_return", sa.String(length=100), nullable=True),
        sa.Column("expected_return_date", sa.String(length=40), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleared_reason", sa.String(length=20), nullable=True),
        sa.Column("timestamp_basis", sa.String(length=20), nullable=False),
        sa.Column("match_id", sa.String(length=36), nullable=True),
        sa.Column("provider_match_id", sa.String(length=100), nullable=True),
        sa.Column("side", sa.String(length=4), nullable=True),
        *_base_columns(),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_player_availability_player_id", "player_availability", ["player_id"], unique=False)
    op.create_index("ix_player_availability_team_id", "player_availability", ["team_id"], unique=False)
    op.create_index("ix_player_availability_match_id", "player_availability", ["match_id"], unique=False)
    op.create_index(
        "ix_player_availability_player_active", "player_availability", ["player_provider_id", "cleared_at"],
        unique=False,
    )
    op.create_index(
        "ix_player_availability_team_active", "player_availability",
        ["team_provider_id", "source", "cleared_at"], unique=False,
    )
    op.create_index(
        "ix_player_availability_provider_match", "player_availability", ["provider_match_id", "side"],
        unique=False,
    )

    # --- player_match_stats
    op.create_table(
        "player_match_stats",
        sa.Column("provider_match_id", sa.String(length=100), nullable=False),
        sa.Column("match_id", sa.String(length=36), nullable=True),
        sa.Column("match_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("competition_provider_id", sa.String(length=100), nullable=True),
        sa.Column("player_id", sa.String(length=36), nullable=False),
        sa.Column("player_provider_id", sa.String(length=100), nullable=False),
        sa.Column("team_id", sa.String(length=36), nullable=True),
        sa.Column("team_provider_id", sa.String(length=100), nullable=True),
        sa.Column("side", sa.String(length=4), nullable=True),
        sa.Column("started", sa.Boolean(), nullable=True),
        sa.Column("appeared", sa.Boolean(), nullable=True),
        sa.Column("minutes", sa.Integer(), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("goals", sa.Integer(), nullable=True),
        sa.Column("assists", sa.Integer(), nullable=True),
        sa.Column("xg", sa.Float(), nullable=True),
        sa.Column("xa", sa.Float(), nullable=True),
        sa.Column("npxg", sa.Float(), nullable=True),
        sa.Column("xgot", sa.Float(), nullable=True),
        sa.Column("shots", sa.Integer(), nullable=True),
        sa.Column("shots_on_target", sa.Integer(), nullable=True),
        sa.Column("yellow_cards", sa.Integer(), nullable=True),
        sa.Column("red_cards", sa.Integer(), nullable=True),
        sa.Column("position_id", sa.Integer(), nullable=True),
        sa.Column("usual_position_id", sa.Integer(), nullable=True),
        sa.Column("is_goalkeeper", sa.Boolean(), nullable=True),
        sa.Column("sub_in_minute", sa.Integer(), nullable=True),
        sa.Column("sub_out_minute", sa.Integer(), nullable=True),
        sa.Column("stats_available", sa.Boolean(), nullable=True),
        sa.Column("shotmap_count", sa.Integer(), nullable=True),
        sa.Column("market_value_eur", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        *_base_columns(),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"]),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_match_id", "player_provider_id", name="uq_player_match_stat"),
    )
    op.create_index("ix_player_match_stats_match_id", "player_match_stats", ["match_id"], unique=False)
    op.create_index("ix_player_match_stats_player_id", "player_match_stats", ["player_id"], unique=False)
    op.create_index("ix_player_match_stats_team_id", "player_match_stats", ["team_id"], unique=False)
    op.create_index(
        "ix_player_match_stats_player_date", "player_match_stats", ["player_provider_id", "match_date"],
        unique=False,
    )
    op.create_index(
        "ix_player_match_stats_team_date", "player_match_stats", ["team_provider_id", "match_date"], unique=False
    )

    # --- lineup_snapshots
    op.create_table(
        "lineup_snapshots",
        sa.Column("provider_match_id", sa.String(length=100), nullable=False),
        sa.Column("match_id", sa.String(length=36), nullable=True),
        sa.Column("side", sa.String(length=4), nullable=False),
        sa.Column("team_provider_id", sa.String(length=100), nullable=True),
        sa.Column("team_id", sa.String(length=36), nullable=True),
        sa.Column("lineup_type", sa.String(length=30), nullable=True),
        sa.Column("lineup_source", sa.String(length=50), nullable=True),
        sa.Column("based_on_match_id", sa.String(length=100), nullable=True),
        sa.Column("formation", sa.String(length=20), nullable=True),
        sa.Column("starter_ids", sa.JSON(), nullable=False),
        sa.Column("starters", sa.JSON(), nullable=False),
        sa.Column("bench", sa.JSON(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timestamp_basis", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        *_base_columns(),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lineup_snapshots_match_id", "lineup_snapshots", ["match_id"], unique=False)
    op.create_index("ix_lineup_snapshots_team_id", "lineup_snapshots", ["team_id"], unique=False)
    op.create_index(
        "ix_lineup_snapshot_match_side", "lineup_snapshots", ["provider_match_id", "side", "observed_at"],
        unique=False,
    )

    # --- team_news_matches
    op.create_table(
        "team_news_matches",
        sa.Column("provider_match_id", sa.String(length=100), nullable=False),
        sa.Column("match_id", sa.String(length=36), nullable=True),
        sa.Column("competition_provider_id", sa.String(length=100), nullable=True),
        sa.Column("home_team_provider_id", sa.String(length=100), nullable=True),
        sa.Column("away_team_provider_id", sa.String(length=100), nullable=True),
        sa.Column("home_team_name", sa.String(length=200), nullable=True),
        sa.Column("away_team_name", sa.String(length=200), nullable=True),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_status", sa.String(length=20), nullable=True),
        sa.Column("header_source", sa.String(length=40), nullable=True),
        sa.Column("details_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("home_unavailable_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("away_unavailable_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stats_ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        *_base_columns(),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_match_id", name="uq_team_news_match_provider"),
    )
    op.create_index("ix_team_news_matches_match_id", "team_news_matches", ["match_id"], unique=False)
    op.create_index(
        "ix_team_news_matches_competition_provider_id", "team_news_matches", ["competition_provider_id"],
        unique=False,
    )
    op.create_index("ix_team_news_matches_kickoff_at", "team_news_matches", ["kickoff_at"], unique=False)


def downgrade():
    op.drop_index("ix_team_news_matches_kickoff_at", table_name="team_news_matches")
    op.drop_index("ix_team_news_matches_competition_provider_id", table_name="team_news_matches")
    op.drop_index("ix_team_news_matches_match_id", table_name="team_news_matches")
    op.drop_table("team_news_matches")

    op.drop_index("ix_lineup_snapshot_match_side", table_name="lineup_snapshots")
    op.drop_index("ix_lineup_snapshots_team_id", table_name="lineup_snapshots")
    op.drop_index("ix_lineup_snapshots_match_id", table_name="lineup_snapshots")
    op.drop_table("lineup_snapshots")

    op.drop_index("ix_player_match_stats_team_date", table_name="player_match_stats")
    op.drop_index("ix_player_match_stats_player_date", table_name="player_match_stats")
    op.drop_index("ix_player_match_stats_team_id", table_name="player_match_stats")
    op.drop_index("ix_player_match_stats_player_id", table_name="player_match_stats")
    op.drop_index("ix_player_match_stats_match_id", table_name="player_match_stats")
    op.drop_table("player_match_stats")

    op.drop_index("ix_player_availability_provider_match", table_name="player_availability")
    op.drop_index("ix_player_availability_team_active", table_name="player_availability")
    op.drop_index("ix_player_availability_player_active", table_name="player_availability")
    op.drop_index("ix_player_availability_match_id", table_name="player_availability")
    op.drop_index("ix_player_availability_team_id", table_name="player_availability")
    op.drop_index("ix_player_availability_player_id", table_name="player_availability")
    op.drop_table("player_availability")

    op.drop_index("ix_team_squad_team_season", table_name="team_squad_members")
    op.drop_index("ix_team_squad_members_player_provider_id", table_name="team_squad_members")
    op.drop_index("ix_team_squad_members_player_id", table_name="team_squad_members")
    op.drop_index("ix_team_squad_members_team_id", table_name="team_squad_members")
    op.drop_table("team_squad_members")

    op.drop_index("ix_players_team_provider_id", table_name="players")
    # batch mode: SQLite rebuilds the table (copy + rename); PostgreSQL emits DROP COLUMN.
    with op.batch_alter_table("players") as batch_op:
        for column in reversed(_player_columns()):
            batch_op.drop_column(column.name)
