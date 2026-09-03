"""Generates the Odoo import workbooks, matching the exact column structure
of the sample files the app must feed:
  - Sale_Estimation_sale.estimation.xlsx  (one workbook per project = one
    sale.estimation record, one estimation_line per EstimateLine, exploded
    into its BOM components as sale_estimation_component_product_line_ids)
  - BOM_ODOO_FORMAT.xlsx (one mrp.bom per (product, item_code) -- named after
    the standardized product for wetworks, e.g. "Wall Paint- caprol"; for
    furniture the name is qualified as "<product> <project code> <item code>"
    and the recipe is the estimator's per-line components + a qty-1 Factory
    Work row. `reference` is left blank for the importing team.)
  - Product_Import_<project>.zip (one .xlsx per participating company --
    see build_product_import_workbooks's docstring for the placement rules)

Only fields this app actually models are populated; Odoo-specific fields we
don't track (assigned_to/user, cost_center_type, dimension on the sale
estimation sheet) are left blank for the importing team to fill in if
needed -- Odoo's xlsx import matches by header text, not column position,
so blank/omitted values are safe.

The sale estimation sheet's product_id columns and the product import
sheet's own "id" column get the Odoo external id populated alongside them,
from Product.odoo_id / SupportItem.odoo_id, whenever that's been set
-- blank otherwise. That's what lets Odoo match an existing record instead
of creating a duplicate or relying on name matching. The BOM sheet does not
carry id columns -- it only ever references products/support items by name.
"""
from io import BytesIO
import openpyxl
from . import models, service, project_types


SALE_ESTIMATION_HEADERS = [
    "estimation_type_id", "project_estimation_id", "costing_type", "source_pricelist_id",
    "destination_pricelist_id", "description", "estimation_date", "delivery_date", "responsible",
    "apply_margin_percentage", "estimation_line_ids/product_id",
    "estimation_line_ids/product_id/id",
    "estimation_line_ids/sale_estimation_component_product_line_ids/product_id",
    "estimation_line_ids/sale_estimation_component_product_line_ids/product_id/id",
    "estimation_line_ids/sale_estimation_component_product_line_ids/default_code",
    "estimation_line_ids/sale_estimation_component_product_line_ids/user",
    "estimation_line_ids/sale_estimation_component_product_line_ids/product_uom_qty",
    "estimation_line_ids/sale_estimation_component_product_line_ids/dimension",
    "estimation_line_ids/assigned_to", "estimation_line_ids/description",
    "estimation_line_ids/cost_center_type", "estimation_line_ids/default_code",
    "estimation_line_ids/dimension", "estimation_line_ids/location", "estimation_line_ids/remark",
    "estimation_line_ids/drawing_no", "estimation_line_ids/product_uom_qty",
    "estimation_line_ids/material_cost", "estimation_line_ids/wastage_percentage",
    "estimation_line_ids/wastage_uom_qty", "estimation_line_ids/labor_cost_percentage",
    "estimation_line_ids/labor_cost", "estimation_line_ids/other_cost_percentage",
    "estimation_line_ids/other_cost", "estimation_line_ids/freight_cost_percentage",
    "estimation_line_ids/freight_cost", "estimation_line_ids/overhead_cost_percentage",
    "estimation_line_ids/overhead_cost", "estimation_line_ids/margin_percentage",
]

# company_id is always left blank -- the importing team fills it in per the
# target Odoo company, this app has no single company to assign per mrp.bom.
BOM_HEADERS = [
    "product", "reference", "product_qty", "company_id",
    "bom_line_ids/product_id", "bom_line_ids/product_qty",
]

# Odoo's standard product.template xlsx-import convention: header text drives
# the match, not column position, same as the two exports above. One vendor
# per row is all the product-import sheet needs (seller_ids is a one2many,
# but a single value here creates a single vendor pricelist line) -- see
# build_product_import_workbooks's docstring for how that vendor is chosen
# per row. "id" is populated from the product's/support item's odoo_id when
# set (so the row updates that existing Odoo record) and left blank
# otherwise -- Odoo assigns it on first import; a blank "id" row that's
# actually a re-import of something already in Odoo will create a duplicate
# instead of updating it, so fill in odoo_id (via the API/admin screens)
# once it's known. "standard_price" is populated only on BOM component
# (support item) rows, from that country's material price for the item --
# finished-product rows (Manufacture or Buy line items) are left blank since
# the app doesn't track a standalone purchase price for them.
PRODUCT_IMPORT_HEADERS = [
    "id", "name", "default_code", "seller_ids/partner_id", "route_ids",
    "purchase_method", "invoice_policy", "detailed_type", "standard_price",
]


def qualified_name(base: str, project: models.Project, item_code) -> str:
    """`<base> <project code> <item code>`. Furniture exports fold the project
    code + item code into every product / BOM-component name, so two line
    items of the same product (or the same support item used on different
    lines with different prices) stay distinct Odoo records. Blank parts are
    skipped."""
    parts = [(base or "").strip()]
    if project.code:
        parts.append(project.code.strip())
    code = (item_code or "").strip()
    if code:
        parts.append(code)
    return " ".join(p for p in parts if p)


def line_product_name(project: models.Project, line: models.EstimateLine) -> str:
    """The finished-product name for an estimate line in the exports -- plain
    for wetworks, qualified with project + line item code for furniture."""
    if project_types.bom_per_line(project.project_type):
        return qualified_name(line.product.name, project, line.item_code)
    return line.product.name


def component_export_name(project: models.Project, comp) -> str:
    if project_types.bom_per_line(project.project_type):
        return qualified_name(comp.support_item.name, project, comp.item_code)
    return comp.support_item.name


def factory_work_name(product: models.Product, project: models.Project, item_code=None) -> str:
    """Every furniture line that carries a BOM includes this as a qty-1
    component -- the per-project assembly charge. Project + line item code are
    folded in so lines of the same product get distinct Factory Work rows."""
    return qualified_name(f"Factory Work for {product.name}", project, item_code)


# Sentinel standing in for the synthetic Factory Work row while iterating a
# furniture line's components.
_FACTORY_WORK = object()


def _line_component_rows(project: models.Project, line: models.EstimateLine) -> list:
    """The component rows to emit for a line: its stored components, plus the
    synthetic Factory Work row for a furniture line that has any."""
    rows = list(line.components or [])
    if rows and project_types.bom_per_line(project.project_type):
        rows.append(_FACTORY_WORK)
    return rows


def reference_code(project: models.Project, item_code) -> str:
    """Project code + user-entered item code, e.g. "FLH PT-01". No item code
    means no reference at all -- a project code alone isn't a usable Odoo
    product reference, so it's left blank rather than half-built."""
    if not item_code:
        return ""
    return f"{project.code} {item_code}" if project.code else item_code


def build_sale_estimation_workbook(db, project: models.Project) -> BytesIO:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(SALE_ESTIMATION_HEADERS)

    # estimation_type_id drives the Odoo record type; furniture projects
    # stamp a different one (see project_types.py). labor_cost is emitted
    # only for wetworks -- for furniture the column stays in the header row
    # but every value is blank (Odoo matches by header, so blank is safe and
    # keeps one code path).
    labor_applies = project_types.labor_applies(project.project_type)
    first_row_meta = {
        "estimation_type_id": project_types.odoo_estimation_type(project.project_type),
        "project_estimation_id": project.name,
        "costing_type": "Product and Service",
        "source_pricelist_id": "Default AED pricelist",
        "destination_pricelist_id": "Default AED pricelist",
        "description": project.name,
        "estimation_date": project.start_date or "",
        "delivery_date": project.end_date or "",
        "responsible": project.estimator_name or "",
    }

    first_row_written = False
    for line in project.estimate_lines:
        totals = service.line_totals(project, line)
        avg_wastage = 0.0
        if line.product.bom_lines:
            weighted = [b.wastage_pct for b in line.product.bom_lines]
            avg_wastage = sum(weighted) / len(weighted) if weighted else 0.0

        line_header = {
            "estimation_line_ids/product_id": line_product_name(project, line),
            "estimation_line_ids/product_id/id": line.product.odoo_id or "",
            "estimation_line_ids/description": line.product.name,
            "estimation_line_ids/location": line.location.name,
            "estimation_line_ids/remark": line.remark or "",
            "estimation_line_ids/drawing_no": line.drawing_no or "",
            "estimation_line_ids/product_uom_qty": line.qty,
            # material_cost (column AA) is left blank -- Odoo derives it
            # automatically from the component BOM cost lines already in
            # this export (columns L-Q), so populating it here would
            # conflict with that calculation.
            "estimation_line_ids/wastage_percentage": round(avg_wastage * 100, 2),
            "estimation_line_ids/labor_cost": round(line.labor_cost_per_unit, 2) if labor_applies else "",
            "estimation_line_ids/margin_percentage": round(totals["margin_pct"] / 100, 4),
        }
        # Furniture: OHP % is a line-level overhead on (components + Factory
        # Work), not baked into component prices -- hand it to Odoo as a
        # percentage so it applies it once. Wetworks bakes its markup into the
        # primary component and leaves this blank.
        if not labor_applies:
            line_header["estimation_line_ids/overhead_cost_percentage"] = round(line.product.ohp_pct or 0.0, 4)
        comp_rows = _line_component_rows(project, line)
        if not comp_rows:
            row = {h: "" for h in SALE_ESTIMATION_HEADERS}
            if not first_row_written:
                row.update(first_row_meta)
                first_row_written = True
            row.update(line_header)
            ws.append([row[h] for h in SALE_ESTIMATION_HEADERS])
            continue

        for i, comp in enumerate(comp_rows):
            row = {h: "" for h in SALE_ESTIMATION_HEADERS}
            if not first_row_written:
                row.update(first_row_meta)
                first_row_written = True
            if i == 0:
                row.update(line_header)
            if comp is _FACTORY_WORK:
                row.update({
                    "estimation_line_ids/sale_estimation_component_product_line_ids/product_id":
                        factory_work_name(line.product, project, line.item_code),
                    "estimation_line_ids/sale_estimation_component_product_line_ids/product_uom_qty": 1,
                })
            else:
                row.update({
                    "estimation_line_ids/sale_estimation_component_product_line_ids/product_id":
                        component_export_name(project, comp),
                    "estimation_line_ids/sale_estimation_component_product_line_ids/product_id/id": comp.support_item.odoo_id or "",
                    "estimation_line_ids/sale_estimation_component_product_line_ids/default_code": comp.support_item.default_code or "",
                    # comp.qty is the total across the line's full qty
                    # (qty_per_unit * line.qty); Odoo wants the per-unit rate.
                    "estimation_line_ids/sale_estimation_component_product_line_ids/product_uom_qty":
                        round(comp.qty / line.qty, 6) if line.qty else 0,
                })
            ws.append([row[h] for h in SALE_ESTIMATION_HEADERS])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def build_product_import_workbooks(db, project: models.Project) -> list:
    """One workbook per participating company -- the project's selling
    company plus every distinct purchasing company used by its line items'
    products -- for importing product.template records into Odoo. Returns a
    list of (company_name, BytesIO) pairs, one per company that ended up
    with at least one row.

    Placement rules -- a line item's product is what's manufactured (or
    bought whole) by its purchasing company, then bought from there by the
    selling company for resale to the client.
      - Manufacture line (product has >=1 BOM lines): the finished product
        gets a row ONLY on the selling company's workbook, as Manufacture,
        with NO vendor (it's assembled in-house, not bought from anyone --
        the line item itself is never placed on the purchasing company's
        workbook either -- only its exploded components are). Each exploded
        BOM component gets a row on BOTH the
        purchasing company's workbook (Buy, vendor = the support item's own
        default vendor -- who the purchasing company actually buys the raw
        material from) and the selling company's workbook (Buy, vendor =
        the purchasing company -- the selling company only ever deals with
        the purchasing company, never the raw-material vendor directly).
      - Buy line (product has no BOM lines): the product gets a row on
        BOTH the purchasing company's workbook (Buy, vendor = the product's
        own default vendor) and the selling company's workbook (Buy,
        vendor = the purchasing company).

    A line whose product has no purchasing company set only gets its
    selling-side row (there's no purchasing workbook to place components or
    the Buy-line row in). If the project has no selling company set,
    Buy lines and BOM components still get their purchasing-side row, but
    Manufacture line items get no row anywhere (they only ever go on the
    selling sheet).
    """
    sheets: dict = {}

    def sheet_for(company):
        # Keyed by (model class, id) -- PurchasingCompany and SellingCompany
        # are separate tables with independent id sequences, so a bare id
        # would collide two unrelated companies that happen to share a
        # numeric id (e.g. both id=1) into the same workbook.
        if company is None:
            return None
        key = (type(company), company.id)
        if key not in sheets:
            sheets[key] = {"name": company.name, "rows": [], "seen": set()}
        return sheets[key]

    def add_row(sheet, key, name, default_code, vendor_name, is_manufacture, odoo_id=None, standard_price=""):
        if sheet is None or key in sheet["seen"]:
            return
        sheet["seen"].add(key)
        route = "Manufacture,Replenish on Order (MTO)" if is_manufacture else "Buy,Replenish on Order (MTO)"
        sheet["rows"].append([
            odoo_id or "", name, default_code, vendor_name, route,
            "On ordered quantities", "Ordered quantities", "Storable Product", standard_price,
        ])

    selling_sheet = sheet_for(project.selling_company)
    furniture = project_types.bom_per_line(project.project_type)

    for line in project.estimate_lines:
        product = line.product
        purchasing_sheet = sheet_for(product.purchasing_company)
        purchasing_company_name = product.purchasing_company.name if product.purchasing_company else ""
        # Wetworks: Manufacture iff the product has a recipe. Furniture: iff
        # this line has user-entered components.
        is_manufacture = bool(product.bom_lines) or (furniture and bool(line.components))

        # Furniture folds project + item code into the name; wetworks keeps
        # the plain names and only uses default_code for the reference.
        line_name = line_product_name(project, line)
        line_key = ("product", product.id, line.item_code)
        line_default_code = reference_code(project, line.item_code)
        line_vendor = "" if is_manufacture else purchasing_company_name
        add_row(selling_sheet, line_key, line_name, line_default_code,
                line_vendor, is_manufacture, odoo_id=product.odoo_id)

        if is_manufacture:
            for comp in line.components:
                support_item = comp.support_item
                vendor_name = support_item.default_vendor.name if support_item.default_vendor else ""
                key = ("support_item", support_item.id, comp.item_code)
                comp_name = component_export_name(project, comp)
                comp_default_code = reference_code(project, comp.item_code)
                standard_price = round(comp.unit_cost, 4)
                add_row(purchasing_sheet, key, comp_name,
                        comp_default_code, vendor_name, False,
                        odoo_id=support_item.odoo_id, standard_price=standard_price)
                add_row(selling_sheet, key, comp_name,
                        comp_default_code, purchasing_company_name, False,
                        odoo_id=support_item.odoo_id, standard_price=standard_price)
            if furniture and line.components:
                # Factory Work: a Buy line on both sheets, vendor = purchasing
                # company, price left blank (it's project-specific and already
                # on the sale-estimation component line).
                fw_name = factory_work_name(product, project, line.item_code)
                fw_key = ("factory_work", product.id, line.item_code)
                fw_code = reference_code(project, line.item_code)
                add_row(purchasing_sheet, fw_key, fw_name, fw_code, purchasing_company_name, False)
                add_row(selling_sheet, fw_key, fw_name, fw_code, purchasing_company_name, False)
        else:
            purchasing_vendor = product.default_vendor.name if product.default_vendor else ""
            add_row(purchasing_sheet, line_key, line_name, line_default_code,
                    purchasing_vendor, is_manufacture, odoo_id=product.odoo_id)

    workbooks = []
    for sheet in sheets.values():
        if not sheet["rows"]:
            continue
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws.append(PRODUCT_IMPORT_HEADERS)
        for row in sheet["rows"]:
            ws.append(row)
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        workbooks.append((sheet["name"], buf))

    return workbooks


def build_bom_workbook(db, project: models.Project) -> BytesIO:
    """One mrp.bom per unique (product, item_code) pair -- the same product
    used across multiple locations/lines with the same item code is the same
    Odoo product, so it only needs one BOM entry; a different item code
    makes it a distinct product reference and earns its own entry."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(BOM_HEADERS)

    seen = set()
    for line in project.estimate_lines:
        key = (line.product_id, line.item_code)
        if key in seen:
            continue
        seen.add(key)

        product_name = line_product_name(project, line)
        reference = ""

        if project_types.bom_per_line(project.project_type):
            # Furniture: recipe is per-line -- (support item, user qty_per_unit)
            # plus the qty-1 Factory Work row. No wastage. Component names are
            # qualified with the project + component item code.
            bom = [(component_export_name(project, c), c.qty_per_unit or 0.0)
                   for c in line.components]
            if line.components:
                bom.append((factory_work_name(line.product, project, line.item_code), 1))
        else:
            bom = [(b.support_item.name, b.qty_per_unit * (1 + (b.wastage_pct or 0)))
                   for b in line.product.bom_lines]

        if not bom:
            ws.append([product_name, reference, 1, "", "", ""])
            continue
        for i, (comp_name, qty) in enumerate(bom):
            ws.append([product_name if i == 0 else "", reference if i == 0 else "",
                       1 if i == 0 else "", "", comp_name, round(qty, 6)])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
