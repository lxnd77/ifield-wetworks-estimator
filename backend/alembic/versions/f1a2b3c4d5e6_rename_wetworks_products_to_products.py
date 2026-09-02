"""rename wetworks_products to products

Revision ID: f1a2b3c4d5e6
Revises: b7c8d9e0f1a2
Create Date: 2026-09-02 00:00:00.000000

Phase 00 of the furniture extension: the catalog is no longer Wetworks-only,
so the ORM class WetworksProduct -> Product and the table wetworks_products
-> products. Pure rename -- no columns, data, or indexes change.

The child foreign keys (bom_lines.product_id, coverage_rates.product_id,
estimate_lines.product_id) follow the renamed table automatically on both
Postgres (FKs track the table by oid) and SQLite >= 3.25 (ALTER TABLE
RENAME rewrites referencing FK clauses). The existing constraint *names*
that embed "wetworks_products" (e.g.
fk_wetworks_products_default_vendor_id_vendors) are left untouched -- they
are cosmetic and renaming them would need a full table rebuild on SQLite
for no functional gain.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table('wetworks_products', 'products')


def downgrade() -> None:
    op.rename_table('products', 'wetworks_products')
