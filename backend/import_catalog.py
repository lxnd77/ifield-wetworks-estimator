"""Import a furniture "Product Master" workbook into the catalog.

The workbook is a flat Odoo product.template sheet -- columns:
    name | uom_id | standard_price | categ_id | Vendor

`categ_id` is a "Family / Sub-family" string that decides what the row is:
    "FFE / *"      -> a Product,  product_type = loose_furniture
    "Joinery / *"  -> a Product,  product_type = fixed_furniture
    "Support*"     -> a SupportItem (a BOM component), purchase_category set
                     from SUPPORT_CATEGORY below

Everything is upserted by name (Products by name + product_type), so a
revised sheet re-imports cleanly. `standard_price` is loaded as a
CountryMaterialPrice only when it is set AND --country is given.

After importing, run `python dump_seed_data.py` so the additions land in
app/seed_catalog.json and survive the next `python seed.py`.

Usage:
    python import_catalog.py "Product Master NEW.xlsx"
    python import_catalog.py "Product Master NEW.xlsx" --country KSA   # if the sheet has prices
    python import_catalog.py "Product Master NEW.xlsx" --dry-run
    DATABASE_URL="postgresql://..." python import_catalog.py ...       # target production
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import openpyxl

from app.database import SessionLocal
from app import models, project_types


# Support-item name -> purchase_category. Every furniture support item gets
# one of project_types.FURNITURE_BOM_CATEGORIES (the component picker filters
# on it, so an unclassified item would be invisible on a furniture line).
# Plywood / boards go under "Accessories" as the least-bad of the four --
# an admin can reclassify from the support-items screen.
SUPPORT_CATEGORY = {
    # Support / Fabric
    "Fabric": "Fabric", "Leather": "Fabric", "PU": "Fabric", "PVC": "Fabric",
    "Partial Leather": "Fabric", "Flame retardant treatment": "Fabric",
    "Water repellent treatment": "Fabric", "Laminated Fabric with backing": "Fabric",
    # Support (bare)
    "Stone": "Stone", "Accessories": "Accessories", "Media Hub": "Accessories",
    "LED": "Accessories", "Plywood 12mm": "Accessories", "Plywood 9mm": "Accessories",
    # Support / Doors & Windows -- metal ironmongery
    "Butt Hinge": "Metal", "Door Handle": "Metal", "Half Thumb Turn": "Metal",
    "Latch Lock": "Metal", "Lock": "Metal", "One Side Door Handle": "Metal",
    "Thumb Turn": "Metal", "Door Closer": "Metal",
}
# Fallback by sub-family when a name isn't in the map above.
SUPPORT_CATEGORY_BY_SUBFAMILY = {
    "Fabric": "Fabric",
    "Doors & Windows": "Metal",
}
_DEFAULT_SUPPORT_CATEGORY = "Accessories"

FAMILY_TO_PRODUCT_TYPE = {
    "FFE": project_types.LOOSE_FURNITURE,
    "Joinery": project_types.FIXED_FURNITURE,
}


def _cell(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _read_rows(path):
    ws = openpyxl.load_workbook(path, data_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    # The header row isn't necessarily row 1 (the sheet has a blank leading
    # row and column) -- find the row that carries the column names.
    hdr_row = next(
        (i for i, r in enumerate(rows)
         if {(_cell(c) or "").lower() for c in r} >= {"name", "categ_id"}),
        None,
    )
    if hdr_row is None:
        sys.exit("could not find a header row with 'name' and 'categ_id' columns")
    header = [(_cell(c) or "").lower() for c in rows[hdr_row]]
    idx = {name: header.index(name) for name in ("name", "uom_id", "standard_price", "categ_id")}
    vendor_i = header.index("vendor") if "vendor" in header else None
    out = []
    for r in rows[hdr_row + 1:]:
        name = _cell(r[idx["name"]])
        if not name:
            continue
        out.append({
            "name": name,
            "uom": _cell(r[idx["uom_id"]]) or "Nos",
            "price": r[idx["standard_price"]],
            "categ": _cell(r[idx["categ_id"]]) or "",
            "vendor": _cell(r[vendor_i]) if vendor_i is not None else None,
        })
    return out


def _support_category(name, subfamily):
    if name in SUPPORT_CATEGORY:
        return SUPPORT_CATEGORY[name]
    return SUPPORT_CATEGORY_BY_SUBFAMILY.get(subfamily, _DEFAULT_SUPPORT_CATEGORY)


def run(path, country_code=None, dry_run=False):
    rows = _read_rows(path)
    db = SessionLocal()
    stats = {"vendors": 0, "products_new": 0, "products_updated": 0,
             "support_new": 0, "support_updated": 0, "prices": 0, "skipped_dupes": 0}
    dupe_names = []

    country = None
    if country_code:
        country = db.query(models.Country).filter_by(code=country_code).first()
        if not country:
            sys.exit(f"country code {country_code!r} not found")

    vendor_cache = {v.name: v for v in db.query(models.Vendor)}

    def get_vendor(vname):
        if not vname:
            return None
        v = vendor_cache.get(vname)
        if v is None:
            v = models.Vendor(name=vname)
            db.add(v)
            db.flush()
            vendor_cache[vname] = v
            stats["vendors"] += 1
        return v

    # Newly imported support items are bought by the China entity (the
    # furniture catalog is China-sourced); existing assignments are kept.
    china_company = db.query(models.PurchasingCompany).filter_by(
        name=project_types.FACTORY_WORK_PURCHASING_COMPANY).first()

    seen_products = set()   # (name, product_type)
    seen_support = set()    # name

    for row in rows:
        family, _, subfamily = row["categ"].partition(" / ")
        family = family.strip()
        subfamily = subfamily.strip()
        vendor = get_vendor(row["vendor"])

        if family == "Support":
            if row["name"] in seen_support:
                stats["skipped_dupes"] += 1
                dupe_names.append(row["name"])
                continue
            seen_support.add(row["name"])
            si = db.query(models.SupportItem).filter_by(name=row["name"]).first()
            new = si is None
            if new:
                si = models.SupportItem(name=row["name"])
                db.add(si)
            si.uom = row["uom"]
            si.purchase_category = _support_category(row["name"], subfamily)
            if vendor:
                si.default_vendor_id = vendor.id
            if si.purchasing_company_id is None and china_company:
                si.purchasing_company_id = china_company.id
            db.flush()
            stats["support_new" if new else "support_updated"] += 1
            _maybe_price(db, country, si, row["price"], stats)
            continue

        ptype = FAMILY_TO_PRODUCT_TYPE.get(family)
        if ptype is None:
            continue  # unknown family -- ignore
        key = (row["name"], ptype)
        if key in seen_products:
            stats["skipped_dupes"] += 1
            dupe_names.append(f"{row['name']} ({family})")
            continue
        seen_products.add(key)
        p = db.query(models.Product).filter_by(name=row["name"], product_type=ptype).first()
        new = p is None
        if new:
            p = models.Product(name=row["name"], product_type=ptype)
            db.add(p)
        p.uom = row["uom"]
        p.category = row["categ"]
        p.active = True
        p.needs_setup = False   # furniture: BOM is per estimate line, nothing to configure
        if vendor:
            p.default_vendor_id = vendor.id
        db.flush()
        stats["products_new" if new else "products_updated"] += 1

    if dry_run:
        db.rollback()
        print("(dry run -- nothing committed)")
    else:
        db.commit()
    for k, v in stats.items():
        print(f"  {k}: {v}")
    if dupe_names:
        print("  duplicate names collapsed to the first occurrence: " + ", ".join(dupe_names))
    db.close()


def _maybe_price(db, country, support_item, raw_price, stats):
    if country is None or raw_price in (None, ""):
        return
    try:
        price = float(raw_price)
    except (TypeError, ValueError):
        return
    row = db.query(models.CountryMaterialPrice).filter_by(
        country_id=country.id, support_item_id=support_item.id).first()
    if row is None:
        row = models.CountryMaterialPrice(country_id=country.id, support_item_id=support_item.id)
        db.add(row)
    row.unit_price_local = price
    stats["prices"] += 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("workbook")
    ap.add_argument("--country", help="country code to attach standard_price to (if the sheet has prices)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(args.workbook, args.country, args.dry_run)
