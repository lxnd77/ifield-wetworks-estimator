"""furniture component pricing: per-component CNY price + item code, drop role

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-09-03 00:00:00.000000

Phase 08. Furniture BOM components are now priced by the estimator (in CNY)
per project rather than looked up from CountryMaterialPrice, and each carries
its own project-unique item code. The per-component role gate is gone --
Consumable % no longer applies to furniture and OHP % is applied to the line
total (components + Factory Work), not per component.

- estimate_line_components: drop `role`; add `unit_price_cny` (nullable --
  furniture only; wetworks components stay recipe-priced).
- estimate_lines: `factory_work_cost` -> `factory_work_cost_cny` (same
  column, the value is now understood as CNY).
- projects: add `cny_per_usd` (nullable) -- the per-project CNY->USD rate,
  snapshotted from project_types.DEFAULT_CNY_PER_USD at creation.

Wetworks costing and exports are unchanged. `bom_lines.role` (the wetworks
recipe primary/fixing flag) is untouched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('estimate_line_components') as batch_op:
        batch_op.add_column(sa.Column('unit_price_cny', sa.Float(), nullable=True))
        batch_op.drop_column('role')
    with op.batch_alter_table('estimate_lines') as batch_op:
        batch_op.alter_column('factory_work_cost', new_column_name='factory_work_cost_cny')
    with op.batch_alter_table('projects') as batch_op:
        batch_op.add_column(sa.Column('cny_per_usd', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('projects') as batch_op:
        batch_op.drop_column('cny_per_usd')
    with op.batch_alter_table('estimate_lines') as batch_op:
        batch_op.alter_column('factory_work_cost_cny', new_column_name='factory_work_cost')
    with op.batch_alter_table('estimate_line_components') as batch_op:
        batch_op.add_column(sa.Column(
            'role', sa.String(), nullable=False, server_default='fixing'))
        batch_op.drop_column('unit_price_cny')
