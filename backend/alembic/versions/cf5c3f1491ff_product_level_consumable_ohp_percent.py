"""product-level consumable % and OHP % markup

Revision ID: cf5c3f1491ff
Revises: d8ebc2150e7d
Create Date: 2026-08-18 20:45:12.000000

Replaces BomLine.markup_pct (one combined value per BOM line) with
WetworksProduct.consumable_pct + WetworksProduct.ohp_pct (two values per
product, matching how the source Estimate Form actually recorded CMBL% and
OH% -- one pair per product, applied to its primary material line only).

Before dropping markup_pct, backfills consumable_pct from each product's
primary BOM line's markup_pct so existing computed costs are unaffected --
the CMBL/OH split isn't separately recoverable from the old combined column,
but the total (and therefore every existing cost) is preserved exactly.
ohp_pct is left at 0 for backfilled rows; split it manually afterward if you
want the two halves to mean something.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf5c3f1491ff'
down_revision: Union[str, None] = 'd8ebc2150e7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('wetworks_products') as batch_op:
        batch_op.add_column(sa.Column('consumable_pct', sa.Float(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('ohp_pct', sa.Float(), nullable=False, server_default='0'))

    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT product_id, markup_pct FROM bom_lines WHERE role = 'primary' AND markup_pct != 0"
    )).fetchall()
    for product_id, markup_pct in rows:
        bind.execute(
            sa.text("UPDATE wetworks_products SET consumable_pct = :m WHERE id = :pid"),
            {"m": markup_pct, "pid": product_id},
        )

    with op.batch_alter_table('bom_lines') as batch_op:
        batch_op.drop_column('markup_pct')


def downgrade() -> None:
    with op.batch_alter_table('bom_lines') as batch_op:
        batch_op.add_column(sa.Column('markup_pct', sa.Float(), nullable=False, server_default='0'))

    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT id, consumable_pct, ohp_pct FROM wetworks_products WHERE consumable_pct != 0 OR ohp_pct != 0"
    )).fetchall()
    for product_id, consumable_pct, ohp_pct in rows:
        bind.execute(
            sa.text(
                "UPDATE bom_lines SET markup_pct = :m WHERE product_id = :pid AND role = 'primary'"
            ),
            {"m": (consumable_pct or 0) + (ohp_pct or 0), "pid": product_id},
        )

    with op.batch_alter_table('wetworks_products') as batch_op:
        batch_op.drop_column('ohp_pct')
        batch_op.drop_column('consumable_pct')
