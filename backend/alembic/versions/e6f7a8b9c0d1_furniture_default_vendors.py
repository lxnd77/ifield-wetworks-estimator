"""furniture BOM items default to "Default {Country} {Material} Vendor"

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-09-25 00:00:00.000000

Data-only. Every furniture support item (purchase_category in Fabric / Stone /
Metal / Accessories) with no default vendor, and a purchasing company with a
country, gets the vendor "Default {company country} {category} Vendor",
created if missing. Items that already have a vendor keep it. From here on
service.assign_furniture_default_vendor applies the same rule when a support
item is created or imported.

Downgrade clears the vendor on items pointing at one of these default vendors
and deletes the default vendors nothing else references.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e6f7a8b9c0d1'
down_revision: Union[str, None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen copy -- a migration must not import app config that may change.
_FURNITURE_CATEGORIES = ("Fabric", "Stone", "Metal", "Accessories")


def _name(country, category):
    return f"Default {country} {category} Vendor"


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT s.id, s.purchase_category, p.country_name FROM support_items s "
        "JOIN purchasing_companies p ON p.id = s.purchasing_company_id "
        "WHERE s.default_vendor_id IS NULL AND s.purchase_category IN :cats"
    ).bindparams(sa.bindparam("cats", expanding=True)), {"cats": list(_FURNITURE_CATEGORIES)}).fetchall()
    vendor_ids = {}
    for si_id, category, country in rows:
        country = (country or "").strip()
        if not country:
            continue
        name = _name(country, category)
        if name not in vendor_ids:
            vid = bind.execute(sa.text("SELECT id FROM vendors WHERE name = :n"), {"n": name}).scalar()
            if vid is None:
                bind.execute(sa.text("INSERT INTO vendors (name) VALUES (:n)"), {"n": name})
                vid = bind.execute(sa.text("SELECT id FROM vendors WHERE name = :n"), {"n": name}).scalar()
            vendor_ids[name] = vid
        bind.execute(sa.text("UPDATE support_items SET default_vendor_id = :v WHERE id = :s"),
                     {"v": vendor_ids[name], "s": si_id})


def downgrade() -> None:
    bind = op.get_bind()
    vendors = bind.execute(sa.text(
        "SELECT id FROM vendors WHERE name LIKE 'Default % Vendor' AND ("
        + " OR ".join(f"name LIKE '% {c} Vendor'" for c in _FURNITURE_CATEGORIES) + ")"
    )).fetchall()
    for (vid,) in vendors:
        bind.execute(sa.text(
            "UPDATE support_items SET default_vendor_id = NULL WHERE default_vendor_id = :v "
            "AND purchase_category IN :cats"
        ).bindparams(sa.bindparam("cats", expanding=True)),
            {"v": vid, "cats": list(_FURNITURE_CATEGORIES)})
        used = bind.execute(sa.text(
            "SELECT (SELECT COUNT(*) FROM support_items WHERE default_vendor_id = :v) + "
            "(SELECT COUNT(*) FROM products WHERE default_vendor_id = :v)"), {"v": vid}).scalar()
        if not used:
            bind.execute(sa.text("DELETE FROM vendors WHERE id = :v"), {"v": vid})
