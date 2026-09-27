"""Odoo units of measure, company currencies, Factory Work vendor

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-09-27 00:00:00.000000

- products.uom / support_items.uom are rewritten onto the Odoo unit names in
  app/uoms.py ("Nos." -> "Nos", "LMT" -> "Rm", "Pcs"/"Set" -> "Units", ...;
  anything unrecognised -> "Units"). Not reversible -- downgrade leaves them.
- purchasing_companies / selling_companies gain currency_code +
  fx_rate_to_usd, backfilled from country_name (China CNY, India INR,
  Nigeria NGN, everything else USD).
- estimate_lines gains factory_work_vendor_id; the "FAD" vendor is created and
  set on every existing furniture line.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, None] = 'e6f7a8b9c0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen copies -- a migration must not import app config that may change.
_UOMS = [
    "Units", "Bags", "Boards", "Boxes", "Drum", "Nos", "Rolls", "Dozens",
    "g", "oz", "lb", "kg", "t", "Hours", "Days",
    "mm", "cm", "in", "ft", "yd", "m", "km", "mi", "ft²", "m²",
    "in³", "fl oz (US)", "qt (US)", "L", "gal (US)", "ft³", "m³",
    "Cubic Meter", "Rm", "Sqm",
]
_ALIASES = {
    "nos.": "Nos", "no": "Nos", "no.": "Nos",
    "pcs": "Units", "pc": "Units", "set": "Units", "packets": "Units", "packet": "Units",
    "unit": "Units", "lmt": "Rm", "lm": "Rm", "drums": "Drum", "box": "Boxes",
    "roll": "Rolls", "bag": "Bags", "board": "Boards", "sq m": "Sqm", "sqmt": "Sqm",
    "cum": "Cubic Meter", "ltr": "L", "litre": "L", "liter": "L",
}
_CURRENCY_BY_COUNTRY = {
    "china": ("CNY", 7.2), "india": ("INR", 88.0), "nigeria": ("NGN", 1500.0),
}
_FAD = "FAD"
_FURNITURE_TYPES = ("loose_furniture", "fixed_furniture")


def _uom(value):
    key = (value or "").strip().lower()
    by_lower = {u.lower(): u for u in _UOMS}
    return by_lower.get(key) or _ALIASES.get(key) or "Units"


def upgrade() -> None:
    bind = op.get_bind()

    for table in ("products", "support_items"):
        for (old,) in bind.execute(sa.text(f"SELECT DISTINCT uom FROM {table}")).fetchall():
            new = _uom(old)
            if new != old:
                bind.execute(sa.text(f"UPDATE {table} SET uom = :new WHERE uom = :old"),
                             {"new": new, "old": old})

    for table in ("purchasing_companies", "selling_companies"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("currency_code", sa.String(), nullable=False, server_default="USD"))
            batch.add_column(sa.Column("fx_rate_to_usd", sa.Float(), nullable=False, server_default="1"))
        for cid, country in bind.execute(sa.text(f"SELECT id, country_name FROM {table}")).fetchall():
            cur = _CURRENCY_BY_COUNTRY.get((country or "").strip().lower())
            if cur:
                bind.execute(sa.text(f"UPDATE {table} SET currency_code = :c, fx_rate_to_usd = :r WHERE id = :i"),
                             {"c": cur[0], "r": cur[1], "i": cid})

    with op.batch_alter_table("estimate_lines") as batch:
        batch.add_column(sa.Column("factory_work_vendor_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_estimate_lines_factory_work_vendor", "vendors",
                                 ["factory_work_vendor_id"], ["id"])
    vid = bind.execute(sa.text("SELECT id FROM vendors WHERE name = :n"), {"n": _FAD}).scalar()
    if vid is None:
        bind.execute(sa.text("INSERT INTO vendors (name) VALUES (:n)"), {"n": _FAD})
        vid = bind.execute(sa.text("SELECT id FROM vendors WHERE name = :n"), {"n": _FAD}).scalar()
    bind.execute(sa.text(
        "UPDATE estimate_lines SET factory_work_vendor_id = :v WHERE project_id IN "
        "(SELECT id FROM projects WHERE project_type IN :types)"
    ).bindparams(sa.bindparam("types", expanding=True)), {"v": vid, "types": list(_FURNITURE_TYPES)})


def downgrade() -> None:
    with op.batch_alter_table("estimate_lines") as batch:
        batch.drop_constraint("fk_estimate_lines_factory_work_vendor", type_="foreignkey")
        batch.drop_column("factory_work_vendor_id")
    for table in ("purchasing_companies", "selling_companies"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("fx_rate_to_usd")
            batch.drop_column("currency_code")
