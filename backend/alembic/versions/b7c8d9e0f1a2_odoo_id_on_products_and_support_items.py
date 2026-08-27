"""odoo_id on products and support items

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-08-22 12:00:00.000000

Adds WetworksProduct.odoo_id and SupportItem.odoo_id -- Odoo's own
product.template external id, once an item has actually been imported into
Odoo and the id is known. Distinct from default_code (the Odoo internal
reference/SKU): this is what lets a re-import update the existing Odoo
record instead of creating a duplicate. Populated into the "id" column of
the product-import export, and into new "<field>/id" companion columns
alongside every product/support-item reference in the sale estimation and
BOM exports, whenever set.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('wetworks_products') as batch_op:
        batch_op.add_column(sa.Column('odoo_id', sa.String(), nullable=True))
    with op.batch_alter_table('support_items') as batch_op:
        batch_op.add_column(sa.Column('odoo_id', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('support_items') as batch_op:
        batch_op.drop_column('odoo_id')
    with op.batch_alter_table('wetworks_products') as batch_op:
        batch_op.drop_column('odoo_id')
