"""Make data_quality_score nullable

Revision ID: 20261012_dq_nullable
Revises: e3771a48da89
Create Date: 2026-10-12

History note: this revision originally pointed at the *filename*
'b1a2c3d4e5f6_prediction_engine_tables' instead of the revision id, which made
`alembic upgrade head` fail with KeyError. Pointing it at b1a2c3d4e5f6 would
have created a second head (a02cb3bda619 also branches from b1a2c3d4e5f6), so
the chain is linearized here: this revision now follows e3771a48da89, the
previous single head. No database could have been stamped on the broken branch,
so re-parenting is safe.

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20261012_dq_nullable'
down_revision = 'e3771a48da89'
branch_labels = None
depends_on = None


def upgrade():
    """Make data_quality_score nullable to distinguish None (unknown) from 0.0 (measured poor quality)."""
    # batch_alter_table emits a plain ALTER COLUMN on PostgreSQL and uses the
    # copy-and-move strategy on SQLite (which has no ALTER COLUMN support).
    with op.batch_alter_table('prediction_versions') as batch_op:
        batch_op.alter_column(
            'data_quality_score',
            existing_type=sa.Float(),
            nullable=True,
            existing_server_default='0.0',
        )


def downgrade():
    """Revert data_quality_score to NOT NULL."""
    with op.batch_alter_table('prediction_versions') as batch_op:
        batch_op.alter_column(
            'data_quality_score',
            existing_type=sa.Float(),
            nullable=False,
            existing_server_default='0.0',
        )
