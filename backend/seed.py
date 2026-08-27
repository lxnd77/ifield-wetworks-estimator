"""Run once to (re)create the schema and load the Wetworks product catalog +
KSA country seed data. Safe to re-run: it wipes and rebuilds.

Usage:  python seed.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import Base, engine, SessionLocal
from app import models
from app.seed_products import PRODUCTS
from app.seed_ksa import (
    KSA_COUNTRY, PRODUCT_COVERAGE_MAP, PRODUCT_MATERIAL_MAP, LBR_COVERAGE,
    PAINT_ITEMIZED_BOM, GYPSUM_ITEMIZED_BOM,
)


def run():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # 0. Default purchasing route for Wetworks: all Wetworks purchases are
        #    routed through the Dubai entity, which then buys BOM items from
        #    the actual per-item vendors (set individually on SupportItem).
        dubai = models.PurchasingCompany(
            name="I FIELD FURNISHING TRADING LLC", country_name="UAE",
            notes="Default purchasing company for Wetworks line items.",
        )
        db.add(dubai)
        db.flush()

        # 1. Products
        product_by_name = {}
        for name, uom, category, default_price in PRODUCTS:
            has_material = name in PRODUCT_MATERIAL_MAP
            has_coverage = name in PRODUCT_COVERAGE_MAP
            p = models.WetworksProduct(
                name=name, uom=uom, category=category,
                needs_setup=not (has_material and has_coverage),
                purchasing_company_id=dubai.id,
            )
            db.add(p)
            product_by_name[name] = p
        db.flush()

        # 2. Country
        country = models.Country(**KSA_COUNTRY)
        db.add(country)
        db.flush()

        # 3. Bundled "primary material" support item + BOM line + price, for every
        #    product that has Estimate Form data. CMBL%/OH% are product-level
        #    (consumable_pct/ohp_pct), applied by calc.py to the primary line only.
        for name, (unit_price, wastage, cmbl, oh) in PRODUCT_MATERIAL_MAP.items():
            product = product_by_name.get(name)
            if not product:
                continue
            product.consumable_pct = cmbl
            product.ohp_pct = oh
            si = models.SupportItem(name=name, default_code=None, uom=product.uom)
            db.add(si)
            db.flush()
            db.add(models.BomLine(
                product_id=product.id, support_item_id=si.id,
                qty_per_unit=1.0, wastage_pct=wastage,
                role="primary", sort_order=0,
            ))
            db.add(models.CountryMaterialPrice(
                country_id=country.id, support_item_id=si.id, unit_price_local=unit_price,
            ))

        # 4. Replace bundled BOM with itemized BOM for Paint + Gypsum Ceiling families
        #    -- these have their own per-component prices, not a CMBL/OH markup.
        for family_map, sort_start in ((PAINT_ITEMIZED_BOM, 0), (GYPSUM_ITEMIZED_BOM, 0)):
            for product_name, lines in family_map.items():
                product = product_by_name.get(product_name)
                if not product:
                    continue
                product.consumable_pct = 0.0
                product.ohp_pct = 0.0
                # remove the bundled line for this product
                db.query(models.BomLine).filter(models.BomLine.product_id == product.id).delete()
                for i, (comp_name, code, uom, qty, wastage, price) in enumerate(lines):
                    si = db.query(models.SupportItem).filter(models.SupportItem.name == comp_name).first()
                    if not si:
                        si = models.SupportItem(name=comp_name, default_code=code, uom=uom)
                        db.add(si)
                        db.flush()
                    db.add(models.BomLine(
                        product_id=product.id, support_item_id=si.id,
                        qty_per_unit=qty, wastage_pct=wastage,
                        role="fixing" if i > 0 else "primary", sort_order=i,
                    ))
                    existing_price = db.query(models.CountryMaterialPrice).filter(
                        models.CountryMaterialPrice.country_id == country.id,
                        models.CountryMaterialPrice.support_item_id == si.id,
                    ).first()
                    if not existing_price:
                        db.add(models.CountryMaterialPrice(
                            country_id=country.id, support_item_id=si.id, unit_price_local=price,
                        ))

        # 5. Coverage rates
        for name, lbr_key in PRODUCT_COVERAGE_MAP.items():
            product = product_by_name.get(name)
            if not product:
                continue
            primary, secondary, inhouse_n, local_n, inhouse_salary, local_salary = LBR_COVERAGE[lbr_key]
            db.add(models.CoverageRate(
                product_id=product.id, primary_coverage_per_day=primary,
                secondary_coverage_per_day=secondary, inhouse_count=inhouse_n, local_count=local_n,
                inhouse_salary_month_local=inhouse_salary, local_salary_month_local=local_salary,
            ))

        db.commit()

        total = len(PRODUCTS)
        configured = db.query(models.WetworksProduct).filter(models.WetworksProduct.needs_setup == False).count()
        print(f"Seeded {total} products ({configured} fully configured for KSA, {total - configured} flagged needs_setup).")
        print(f"Support items: {db.query(models.SupportItem).count()}")
        print(f"BOM lines: {db.query(models.BomLine).count()}")
        print(f"Coverage rates: {db.query(models.CoverageRate).count()}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
