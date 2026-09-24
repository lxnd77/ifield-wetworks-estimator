"""Run once to (re)create the schema and load the product catalog + KSA
country seed data. Safe to re-run: it wipes and rebuilds.

The catalog is loaded verbatim from app/seed_catalog.json -- a full export
of the actual, cleaned-up catalog (BOM item names distinct from their
product, per-item vendor assignments, per-family purchasing companies,
shared/restructured BOM lines) rather than the original raw workbook
extraction. See app/seed_catalog.json's own place in git history for what
changed and when; regenerate it (see dump_seed_data.py) whenever further
catalog cleanup happens in an admin session, so it doesn't get lost on the
next re-seed.

Usage:  python seed.py
"""
import sys
import os
import json
from collections import Counter
sys.path.insert(0, os.path.dirname(__file__))

from app.database import Base, engine, SessionLocal
from app import models

SEED_DATA_PATH = os.path.join(os.path.dirname(__file__), "app", "seed_catalog.json")


def run():
    with open(SEED_DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Each *_id_map translates the JSON's source ids (from the dev DB
        # this was dumped from) to the freshly-assigned ids in this DB --
        # letting the DB pick its own ids avoids fighting Postgres's
        # sequence/identity handling on a direct id insert.
        vendor_id_map = {}
        for row in data["vendors"]:
            v = models.Vendor(name=row["name"], notes=row.get("notes"))
            db.add(v)
            db.flush()
            vendor_id_map[row["id"]] = v.id

        purchasing_company_id_map = {}
        for row in data["purchasing_companies"]:
            pc = models.PurchasingCompany(
                name=row["name"], country_name=row.get("country_name"), notes=row.get("notes"),
            )
            db.add(pc)
            db.flush()
            purchasing_company_id_map[row["id"]] = pc.id

        selling_company_id_map = {}
        for row in data["selling_companies"]:
            sc = models.SellingCompany(
                name=row["name"], country_name=row.get("country_name"), notes=row.get("notes"),
            )
            db.add(sc)
            db.flush()
            selling_company_id_map[row["id"]] = sc.id

        country_id_map = {}
        for row in data["countries"]:
            country = models.Country(**{k: v for k, v in row.items() if k != "id"})
            db.add(country)
            db.flush()
            country_id_map[row["id"]] = country.id

        product_id_map = {}
        for row in data["products"]:
            p = models.Product(
                name=row["name"], uom=row["uom"], category=row["category"],
                product_type=row.get("product_type", "wetworks"),
                default_code=row.get("default_code"), odoo_id=row.get("odoo_id"),
                active=bool(row.get("active", True)), needs_setup=bool(row.get("needs_setup", True)),
                notes=row.get("notes"),
                purchasing_company_id=purchasing_company_id_map.get(row.get("purchasing_company_id")),
                default_vendor_id=vendor_id_map.get(row.get("default_vendor_id")),
                consumable_pct=row.get("consumable_pct", 0.0), ohp_pct=row.get("ohp_pct", 0.0),
            )
            db.add(p)
            db.flush()
            product_id_map[row["id"]] = p.id

        support_item_id_map = {}
        for row in data["support_items"]:
            si = models.SupportItem(
                name=row["name"], default_code=row.get("default_code"), odoo_id=row.get("odoo_id"),
                uom=row["uom"], notes=row.get("notes"), purchase_category=row.get("purchase_category"),
                default_vendor_id=vendor_id_map.get(row.get("default_vendor_id")),
                purchasing_company_id=purchasing_company_id_map.get(row.get("purchasing_company_id")),
            )
            db.add(si)
            db.flush()
            support_item_id_map[row["id"]] = si.id

        for row in data["bom_lines"]:
            db.add(models.BomLine(
                product_id=product_id_map[row["product_id"]],
                support_item_id=support_item_id_map[row["support_item_id"]],
                qty_per_unit=row["qty_per_unit"], wastage_pct=row.get("wastage_pct", 0.0),
                role=row.get("role", "primary"), sort_order=row.get("sort_order", 0),
            ))

        for row in data["country_material_prices"]:
            db.add(models.CountryMaterialPrice(
                country_id=country_id_map[row["country_id"]],
                support_item_id=support_item_id_map[row["support_item_id"]],
                unit_price_local=row["unit_price_local"],
            ))

        for row in data["coverage_rates"]:
            db.add(models.CoverageRate(
                product_id=product_id_map[row["product_id"]],
                primary_coverage_per_day=row["primary_coverage_per_day"],
                secondary_coverage_per_day=row.get("secondary_coverage_per_day"),
                inhouse_count=row.get("inhouse_count", 0), local_count=row.get("local_count", 0),
                inhouse_salary_month_local=row.get("inhouse_salary_month_local", 0.0),
                local_salary_month_local=row.get("local_salary_month_local", 0.0),
            ))

        db.commit()

        total = len(data["products"])
        by_type = Counter(p.product_type for p in db.query(models.Product))
        ww_ready = db.query(models.Product).filter(
            models.Product.product_type == "wetworks", models.Product.needs_setup == False).count()
        print(f"Seeded {total} products: "
              f"{by_type.get('wetworks', 0)} wetworks ({ww_ready} configured for KSA), "
              f"{by_type.get('loose_furniture', 0)} loose furniture, "
              f"{by_type.get('fixed_furniture', 0)} fixed furniture.")
        print(f"Support items: {db.query(models.SupportItem).count()}")
        print(f"BOM lines: {db.query(models.BomLine).count()}")
        print(f"Coverage rates: {db.query(models.CoverageRate).count()}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
