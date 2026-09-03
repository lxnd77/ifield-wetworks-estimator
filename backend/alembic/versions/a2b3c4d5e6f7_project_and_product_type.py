"""project_type / product_type discriminator; furniture dates optional

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-09-02 00:30:00.000000

Phase 01 of the furniture extension.

- projects.project_type / products.product_type: String NOT NULL, server
  default "wetworks" so every existing row backfills to the original mode.
  The default is kept in place (harmless for the app, helps raw inserts).
- projects.start_date / end_date become nullable -- furniture projects may
  omit them. Wetworks still requires them, enforced at the API layer.

Costing and exports are unchanged by this migration; a furniture product
with a BOM and no coverage rate already prices as material-only because
calc.compute_labor_cost returns zero without a coverage rate.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('projects') as batch_op:
        batch_op.add_column(sa.Column(
            'project_type', sa.String(), nullable=False, server_default='wetworks'))
        batch_op.alter_column('start_date', existing_type=sa.Date(), nullable=True)
        batch_op.alter_column('end_date', existing_type=sa.Date(), nullable=True)
    with op.batch_alter_table('products') as batch_op:
        batch_op.add_column(sa.Column(
            'product_type', sa.String(), nullable=False, server_default='wetworks'))


def downgrade() -> None:
    with op.batch_alter_table('products') as batch_op:
        batch_op.drop_column('product_type')
    with op.batch_alter_table('projects') as batch_op:
        batch_op.alter_column('end_date', existing_type=sa.Date(), nullable=False)
        batch_op.alter_column('start_date', existing_type=sa.Date(), nullable=False)
        batch_op.drop_column('project_type')
