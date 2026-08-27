"""estimate line description + dimension

Revision ID: a1b2c3d4e5f6
Revises: cf5c3f1491ff
Create Date: 2026-08-21 00:00:00.000000

Adds EstimateLine.description and EstimateLine.dimension, both used only by
the Odoo product-import export (product_description / product_dimension
columns). Kept distinct from the existing `remark` field, which stays
sale-estimation-sheet-only.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'cf5c3f1491ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('estimate_lines') as batch_op:
        batch_op.add_column(sa.Column('description', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('dimension', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('estimate_lines') as batch_op:
        batch_op.drop_column('dimension')
        batch_op.drop_column('description')
