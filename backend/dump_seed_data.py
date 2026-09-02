"""Snapshot the current catalog master data (products, BOM, coverage rates,
vendors, purchasing/selling companies, country rate cards) from whatever
DATABASE_URL points at into app/seed_catalog.json -- the file seed.py loads
from.

Run this after any admin-side cleanup (renaming BOM items, assigning
vendors, reassigning purchasing companies, fixing coverage rates, etc.) so
the work survives the next `python seed.py` re-seed instead of being wiped
by it. Only catalog/master-data tables are captured -- users, projects, and
estimate lines are never included here (seed.py doesn't touch them either
way, this script just mirrors the same scope).

Usage:  python dump_seed_data.py [output_path.json]
        DATABASE_URL="postgresql://..." python dump_seed_data.py   # to snapshot production instead of local
"""
import sys
import os
import json
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal
from app import models

DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "app", "seed_catalog.json")


def _row(obj, fields):
    return {f: getattr(obj, f) for f in fields}


def run(output_path: str):
    db = SessionLocal()
    try:
        data = {
            "vendors": [_row(v, ["id", "name", "notes"]) for v in db.query(models.Vendor).order_by(models.Vendor.id)],
            "purchasing_companies": [
                _row(p, ["id", "name", "country_name", "notes"])
                for p in db.query(models.PurchasingCompany).order_by(models.PurchasingCompany.id)
            ],
            "selling_companies": [
                _row(s, ["id", "name", "country_name", "notes"])
                for s in db.query(models.SellingCompany).order_by(models.SellingCompany.id)
            ],
            "countries": [
                _row(c, [
                    "id", "name", "code", "is_active", "is_template", "site_currency_code",
                    "site_fx_rate_to_usd", "inhouse_labor_currency_code", "inhouse_fx_rate_to_usd",
                    "local_labor_currency_code", "local_fx_rate_to_usd", "material_currency_code",
                    "material_fx_rate_to_usd", "working_days_per_month", "wages_oh_rate_pct",
                    "food_per_month_local", "accommodation_per_month_local", "local_travel_per_month_local",
                    "air_ticket_per_year_local", "visa_per_year_local", "other_allowance_per_day_usd", "notes",
                ])
                for c in db.query(models.Country).order_by(models.Country.id)
            ],
            "products": [
                _row(p, [
                    "id", "name", "uom", "category", "default_code", "odoo_id", "active", "needs_setup",
                    "notes", "purchasing_company_id", "default_vendor_id", "consumable_pct", "ohp_pct",
                ])
                for p in db.query(models.Product).order_by(models.Product.id)
            ],
            "support_items": [
                _row(s, ["id", "name", "default_code", "odoo_id", "uom", "notes", "purchase_category", "default_vendor_id"])
                for s in db.query(models.SupportItem).order_by(models.SupportItem.id)
            ],
            "bom_lines": [
                _row(b, ["id", "product_id", "support_item_id", "qty_per_unit", "wastage_pct", "role", "sort_order"])
                for b in db.query(models.BomLine).order_by(models.BomLine.product_id, models.BomLine.sort_order)
            ],
            "country_material_prices": [
                _row(m, ["id", "country_id", "support_item_id", "unit_price_local"])
                for m in db.query(models.CountryMaterialPrice).order_by(models.CountryMaterialPrice.id)
            ],
            "coverage_rates": [
                _row(c, [
                    "id", "product_id", "primary_coverage_per_day", "secondary_coverage_per_day",
                    "inhouse_count", "local_count", "inhouse_salary_month_local", "local_salary_month_local",
                ])
                for c in db.query(models.CoverageRate).order_by(models.CoverageRate.id)
            ],
        }
    finally:
        db.close()

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    for key, rows in data.items():
        print(f"{key}: {len(rows)}")
    print(f"Written to {output_path}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUTPUT
    run(out)
