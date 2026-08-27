"""vendors, purchasing companies, selling companies, and item codes

Revision ID: d8ebc2150e7d
Revises: d6df830062bb
Create Date: 2026-08-18 20:32:55.596231

Adds the master data + fields for the multi-company purchasing/selling
model: Vendor (actual BOM-item supplier), PurchasingCompany (I-Field entity
that buys a finished line item, e.g. Dubai for Wetworks), SellingCompany
(I-Field entity that invoices the client, set per project), plus the
user-entered item codes (on estimate lines and their exploded BOM
components) used to build Odoo product reference codes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8ebc2150e7d'
down_revision: Union[str, None] = 'd6df830062bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('vendors',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_table('purchasing_companies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('country_name', sa.String(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_table('selling_companies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('country_name', sa.String(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    # batch_alter_table so this also works on SQLite (which can't ALTER
    # constraints directly -- batch mode does a copy-and-move instead). This
    # is a transparent no-op wrapper on Postgres.
    with op.batch_alter_table('support_items') as batch_op:
        batch_op.add_column(sa.Column('purchase_category', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('default_vendor_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_support_items_default_vendor_id_vendors', 'vendors', ['default_vendor_id'], ['id'])

    with op.batch_alter_table('wetworks_products') as batch_op:
        batch_op.add_column(sa.Column('purchasing_company_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('default_vendor_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_wetworks_products_purchasing_company_id_purchasing_companies', 'purchasing_companies', ['purchasing_company_id'], ['id'])
        batch_op.create_foreign_key('fk_wetworks_products_default_vendor_id_vendors', 'vendors', ['default_vendor_id'], ['id'])

    with op.batch_alter_table('projects') as batch_op:
        batch_op.add_column(sa.Column('code', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('selling_company_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_projects_selling_company_id_selling_companies', 'selling_companies', ['selling_company_id'], ['id'])

    with op.batch_alter_table('estimate_lines') as batch_op:
        batch_op.add_column(sa.Column('item_code', sa.String(), nullable=True))

    with op.batch_alter_table('estimate_line_components') as batch_op:
        batch_op.add_column(sa.Column('item_code', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('estimate_line_components') as batch_op:
        batch_op.drop_column('item_code')

    with op.batch_alter_table('estimate_lines') as batch_op:
        batch_op.drop_column('item_code')

    with op.batch_alter_table('projects') as batch_op:
        batch_op.drop_constraint('fk_projects_selling_company_id_selling_companies', type_='foreignkey')
        batch_op.drop_column('selling_company_id')
        batch_op.drop_column('code')

    with op.batch_alter_table('wetworks_products') as batch_op:
        batch_op.drop_constraint('fk_wetworks_products_default_vendor_id_vendors', type_='foreignkey')
        batch_op.drop_constraint('fk_wetworks_products_purchasing_company_id_purchasing_companies', type_='foreignkey')
        batch_op.drop_column('default_vendor_id')
        batch_op.drop_column('purchasing_company_id')

    with op.batch_alter_table('support_items') as batch_op:
        batch_op.drop_constraint('fk_support_items_default_vendor_id_vendors', type_='foreignkey')
        batch_op.drop_column('default_vendor_id')
        batch_op.drop_column('purchase_category')

    op.drop_table('selling_companies')
    op.drop_table('purchasing_companies')
    op.drop_table('vendors')
