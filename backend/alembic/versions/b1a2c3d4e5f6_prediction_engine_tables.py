"""Add prediction engine tables

Revision ID: b1a2c3d4e5f6
Revises: a0c16f627575
Create Date: 2025-01-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1a2c3d4e5f6'
down_revision: Union[str, None] = 'a0c16f627575'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create prediction engine tables."""
    
    # Create prediction_versions table
    op.create_table(
        'prediction_versions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('match_id', sa.String(length=100), nullable=False),
        sa.Column('stage', sa.String(length=50), nullable=False),
        sa.Column('prediction_data', sa.JSON(), nullable=False),
        sa.Column('model_versions', sa.JSON(), nullable=True),
        sa.Column('data_quality_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('confidence_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('notes', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for prediction_versions
    op.create_index(
        'ix_prediction_version_match',
        'prediction_versions',
        ['match_id', 'stage'],
        unique=False
    )
    op.create_index(
        'ix_prediction_version_created',
        'prediction_versions',
        ['created_at'],
        unique=False
    )
    
    # Create track_record table
    op.create_table(
        'track_record',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('prediction_version_id', sa.String(length=36), nullable=False),
        sa.Column('match_id', sa.String(length=100), nullable=False),
        sa.Column('predicted_home_win', sa.Float(), nullable=False),
        sa.Column('predicted_draw', sa.Float(), nullable=False),
        sa.Column('predicted_away_win', sa.Float(), nullable=False),
        sa.Column('actual_outcome', sa.String(length=20), nullable=False),
        sa.Column('actual_home_score', sa.Integer(), nullable=False),
        sa.Column('actual_away_score', sa.Integer(), nullable=False),
        sa.Column('prediction_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('match_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('over_2_5_predicted', sa.Float(), nullable=True),
        sa.Column('over_2_5_actual', sa.Boolean(), nullable=True),
        sa.Column('btts_predicted', sa.Float(), nullable=True),
        sa.Column('btts_actual', sa.Boolean(), nullable=True),
        sa.Column('home_odds', sa.Float(), nullable=True),
        sa.Column('draw_odds', sa.Float(), nullable=True),
        sa.Column('away_odds', sa.Float(), nullable=True),
        sa.Column('league_id', sa.String(length=100), nullable=True),
        sa.Column('model_id', sa.String(length=100), nullable=True),
        sa.Column('stage', sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(['prediction_version_id'], ['prediction_versions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for track_record
    op.create_index(
        op.f('ix_track_record_prediction_version_id'),
        'track_record',
        ['prediction_version_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_track_record_match_id'),
        'track_record',
        ['match_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_track_record_prediction_timestamp'),
        'track_record',
        ['prediction_timestamp'],
        unique=False
    )
    op.create_index(
        'ix_track_record_league',
        'track_record',
        ['league_id', 'prediction_timestamp'],
        unique=False
    )
    op.create_index(
        'ix_track_record_model',
        'track_record',
        ['model_id', 'prediction_timestamp'],
        unique=False
    )
    op.create_index(
        op.f('ix_track_record_league_id'),
        'track_record',
        ['league_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_track_record_model_id'),
        'track_record',
        ['model_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_track_record_stage'),
        'track_record',
        ['stage'],
        unique=False
    )


def downgrade() -> None:
    """Drop prediction engine tables."""
    
    # Drop indexes first
    op.drop_index('ix_track_record_model', table_name='track_record')
    op.drop_index('ix_track_record_league', table_name='track_record')
    op.drop_index(op.f('ix_track_record_stage'), table_name='track_record')
    op.drop_index(op.f('ix_track_record_model_id'), table_name='track_record')
    op.drop_index(op.f('ix_track_record_league_id'), table_name='track_record')
    op.drop_index(op.f('ix_track_record_prediction_timestamp'), table_name='track_record')
    op.drop_index(op.f('ix_track_record_match_id'), table_name='track_record')
    op.drop_index(op.f('ix_track_record_prediction_version_id'), table_name='track_record')
    
    op.drop_index('ix_prediction_version_created', table_name='prediction_versions')
    op.drop_index('ix_prediction_version_match', table_name='prediction_versions')
    
    # Drop tables
    op.drop_table('track_record')
    op.drop_table('prediction_versions')
