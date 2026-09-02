"""furniture per-line BOM: component qty_per_unit/role, line factory_work_cost

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-09-02 01:00:00.000000

Phase 05 of the furniture extension. Furniture BOM component quantities are
entered per project, not fixed on the product recipe, and every furniture
line with a BOM carries a per-project "Factory Work" charge.

- estimate_line_components.qty_per_unit (nullable): furniture user input;
  stays null for wetworks (recipe-driven).
- estimate_line_components.role (NOT NULL, server default 'fixing'):
  markup applies to 'primary' rows only, mirroring bom_lines.role.
- estimate_lines.factory_work_cost (nullable): the per-line furniture
  Factory Work charge in USD.

Wetworks costing and exports are unchanged.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('estimate_line_components') as batch_op:
        batch_op.add_column(sa.Column('qty_per_unit', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column(
            'role', sa.String(), nullable=False, server_default='fixing'))
    with op.batch_alter_table('estimate_lines') as batch_op:
        batch_op.add_column(sa.Column('factory_work_cost', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('estimate_lines') as batch_op:
        batch_op.drop_column('factory_work_cost')
    with op.batch_alter_table('estimate_line_components') as batch_op:
        batch_op.drop_column('role')
        batch_op.drop_column('qty_per_unit')
