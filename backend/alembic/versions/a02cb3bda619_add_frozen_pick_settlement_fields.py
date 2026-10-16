"""add_frozen_pick_settlement_fields

Revision ID: a02cb3bda619
Revises: b1a2c3d4e5f6
Create Date: 2026-10-05 19:45:40.335763

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a02cb3bda619'
down_revision: Union[str, None] = 'b1a2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add frozen pick columns (immutable after creation)
    op.add_column('prediction_versions', sa.Column('selected_market', sa.String(50), nullable=True))
    op.add_column('prediction_versions', sa.Column('selection_text', sa.String(200), nullable=True))
    op.add_column('prediction_versions', sa.Column('selection_probability', sa.Float(), nullable=True))
    op.add_column('prediction_versions', sa.Column('selection_confidence', sa.Float(), nullable=True))
    op.add_column('prediction_versions', sa.Column('selection_odds', sa.Float(), nullable=True))
    op.add_column('prediction_versions', sa.Column('selection_fair_odds', sa.Float(), nullable=True))
    op.add_column('prediction_versions', sa.Column('selection_edge', sa.Float(), nullable=True))
    op.add_column('prediction_versions', sa.Column('value_classification', sa.String(50), nullable=True))
    op.add_column('prediction_versions', sa.Column('risk_level', sa.String(50), nullable=True))
    
    # Add settlement columns (populated after match finishes)
    op.add_column('prediction_versions', sa.Column('actual_result', sa.String(20), nullable=True))
    op.add_column('prediction_versions', sa.Column('profit_loss', sa.Float(), nullable=True))
    op.add_column('prediction_versions', sa.Column('settled_at', sa.DateTime(timezone=True), nullable=True))
    
    # Create indexes on actual_result for filtering
    op.create_index('ix_prediction_version_actual_result', 'prediction_versions', ['actual_result'])
    
    # Create index on settled_at for date filtering
    op.create_index('ix_prediction_version_settled_at', 'prediction_versions', ['settled_at'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_prediction_version_settled_at', 'prediction_versions')
    op.drop_index('ix_prediction_version_actual_result', 'prediction_versions')
    
    # Drop settlement columns
    op.drop_column('prediction_versions', 'settled_at')
    op.drop_column('prediction_versions', 'profit_loss')
    op.drop_column('prediction_versions', 'actual_result')
    
    # Drop frozen pick columns
    op.drop_column('prediction_versions', 'risk_level')
    op.drop_column('prediction_versions', 'value_classification')
    op.drop_column('prediction_versions', 'selection_edge')
    op.drop_column('prediction_versions', 'selection_fair_odds')
    op.drop_column('prediction_versions', 'selection_odds')
    op.drop_column('prediction_versions', 'selection_confidence')
    op.drop_column('prediction_versions', 'selection_probability')
    op.drop_column('prediction_versions', 'selection_text')
    op.drop_column('prediction_versions', 'selected_market')
