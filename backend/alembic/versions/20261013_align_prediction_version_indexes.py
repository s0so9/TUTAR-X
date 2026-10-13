"""Align prediction_versions index names with SQLAlchemy models

Revision ID: 20261013_pv_index_align
Revises: 20261012_dq_nullable
Create Date: 2026-10-13

Revision a02cb3bda619 created indexes named
  ix_prediction_version_actual_result (actual_result)
  ix_prediction_version_settled_at    (settled_at)
while app/database/models.py (PredictionVersion.__table_args__) declares
  ix_prediction_version_settled (settled_at)
  ix_prediction_version_market  (selected_market)

Databases built with Base.metadata.create_all() already carry the model names,
so this revision brings migrated databases in line with the models. After it,
`alembic upgrade head` on an empty database yields no autogenerate diff.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20261013_pv_index_align'
down_revision = '20261012_dq_nullable'
branch_labels = None
depends_on = None


def _existing_index_names() -> set:
    bind = op.get_bind()
    return {ix["name"] for ix in sa.inspect(bind).get_indexes('prediction_versions')}


def upgrade():
    existing = _existing_index_names()

    if 'ix_prediction_version_settled_at' in existing:
        op.drop_index('ix_prediction_version_settled_at', table_name='prediction_versions')
    if 'ix_prediction_version_actual_result' in existing:
        op.drop_index('ix_prediction_version_actual_result', table_name='prediction_versions')

    if 'ix_prediction_version_settled' not in existing:
        op.create_index('ix_prediction_version_settled', 'prediction_versions', ['settled_at'])
    if 'ix_prediction_version_market' not in existing:
        op.create_index('ix_prediction_version_market', 'prediction_versions', ['selected_market'])


def downgrade():
    existing = _existing_index_names()

    if 'ix_prediction_version_market' in existing:
        op.drop_index('ix_prediction_version_market', table_name='prediction_versions')
    if 'ix_prediction_version_settled' in existing:
        op.drop_index('ix_prediction_version_settled', table_name='prediction_versions')

    if 'ix_prediction_version_actual_result' not in existing:
        op.create_index('ix_prediction_version_actual_result', 'prediction_versions', ['actual_result'])
    if 'ix_prediction_version_settled_at' not in existing:
        op.create_index('ix_prediction_version_settled_at', 'prediction_versions', ['settled_at'])
