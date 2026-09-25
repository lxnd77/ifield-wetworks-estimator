"""support items carry their own purchasing company

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-09-25 00:00:00.000000

Furniture products are always Manufacture lines whose BOM items are bought by
whichever I-Field purchasing company is responsible for them, so the product
import export routes each component to its support item's purchasing company
(falling back to the product's, which is how wetworks recipes still work).

- support_items: add `purchasing_company_id` (nullable FK).
- Backfill: every furniture support item (purchase_category in Fabric / Stone
  / Metal / Accessories) with no company is set to GUANGZHOU DAKA TRADING
  CO.,LTD, if that company exists. Downgrade drops the column.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen copies -- a migration must not import app config that may change.
_CHINA_COMPANY = "GUANGZHOU DAKA TRADING CO.,LTD"
_FURNITURE_CATEGORIES = ("Fabric", "Stone", "Metal", "Accessories")


def upgrade() -> None:
    with op.batch_alter_table('support_items') as batch_op:
        batch_op.add_column(sa.Column('purchasing_company_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_support_items_purchasing_company_id', 'purchasing_companies',
            ['purchasing_company_id'], ['id'])

    bind = op.get_bind()
    pc_id = bind.execute(
        sa.text("SELECT id FROM purchasing_companies WHERE name = :n"), {"n": _CHINA_COMPANY}
    ).scalar()
    if pc_id is not None:
        stmt = sa.text(
            "UPDATE support_items SET purchasing_company_id = :pc "
            "WHERE purchasing_company_id IS NULL AND purchase_category IN :cats"
        ).bindparams(sa.bindparam("cats", expanding=True))
        bind.execute(stmt, {"pc": pc_id, "cats": list(_FURNITURE_CATEGORIES)})


def downgrade() -> None:
    with op.batch_alter_table('support_items') as batch_op:
        batch_op.drop_constraint('fk_support_items_purchasing_company_id', type_='foreignkey')
        batch_op.drop_column('purchasing_company_id')
