"""Generates the two Odoo import workbooks, matching the exact column
structure of the sample files the app must feed:
  - Sale_Estimation_sale.estimation.xlsx  (one workbook per project = one
    sale.estimation record, one estimation_line per EstimateLine, exploded
    into its BOM components as sale_estimation_component_product_line_ids)
  - BOM_ODOO_FORMAT.xlsx (one mrp.bom per EstimateLine -- a location-specific
    'virtual product', e.g. "Wall Paint- caprol in Lobby" -- with its BOM
    lines showing the per-unit recipe, mirroring the sample's pattern where
    each estimate line/location becomes its own named BOM.)

Only fields this app actually models are populated; Odoo-specific fields we
don't track (assigned_to/user, cost_center_type, dimension) are left blank
for the importing team to fill in if needed -- Odoo's xlsx import matches by
header text, not column position, so blank/omitted values are safe.
"""
from io import BytesIO
import openpyxl
from . import models, service


SALE_ESTIMATION_HEADERS = [
    "estimation_type_id", "project_estimation_id", "costing_type", "source_pricelist_id",
    "destination_pricelist_id", "description", "estimation_date", "delivery_date", "responsible",
    "apply_margin_percentage", "estimation_line_ids/product_id",
    "estimation_line_ids/sale_estimation_component_product_line_ids/product_id",
    "estimation_line_ids/sale_estimation_component_product_line_ids/default_code",
    "estimation_line_ids/sale_estimation_component_product_line_ids/user",
    "estimation_line_ids/sale_estimation_component_product_line_ids/product_uom_qty",
    "estimation_line_ids/sale_estimation_component_product_line_ids/cost_price",
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
    "estimation_line_ids/overhead_cost", "estimation_line_ids/sales_value",
    "estimation_line_ids/margin_percentage",
]

BOM_HEADERS = ["product", "reference", "product_qty", "bom_line_ids/product_id", "bom_line_ids/product_qty"]


def line_virtual_product_name(line: models.EstimateLine) -> str:
    return f"{line.product.name} in {line.location.name}"


def build_sale_estimation_workbook(db, project: models.Project) -> BytesIO:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(SALE_ESTIMATION_HEADERS)

    first_row_written = False
    for line in project.estimate_lines:
        totals = service.line_totals(project, line)
        avg_wastage = 0.0
        if line.product.bom_lines:
            weighted = [b.wastage_pct for b in line.product.bom_lines]
            avg_wastage = sum(weighted) / len(weighted) if weighted else 0.0

        line_header = {
            "estimation_line_ids/product_id": line_virtual_product_name(line),
            "estimation_line_ids/description": line.product.name,
            "estimation_line_ids/location": line.location.name,
            "estimation_line_ids/remark": line.remark or "",
            "estimation_line_ids/drawing_no": line.drawing_no or "",
            "estimation_line_ids/product_uom_qty": line.qty,
            "estimation_line_ids/material_cost": round(totals["material_total"], 2),
            "estimation_line_ids/wastage_percentage": round(avg_wastage * 100, 2),
            "estimation_line_ids/labor_cost": round(totals["labor_total"], 2),
            "estimation_line_ids/sales_value": round(totals["sales_value"], 2),
            "estimation_line_ids/margin_percentage": round(totals["margin_pct"], 2),
        }
        components = line.components or []
        if not components:
            row = {h: "" for h in SALE_ESTIMATION_HEADERS}
            if not first_row_written:
                row.update({
                    "estimation_type_id": "Wetworks", "project_estimation_id": project.id,
                    "costing_type": "Product and Service",
                    "source_pricelist_id": "Default AED pricelist",
                    "destination_pricelist_id": "Default AED pricelist",
                    "description": project.name,
                    "estimation_date": project.start_date, "delivery_date": project.end_date,
                    "responsible": project.estimator_name or "",
                })
                first_row_written = True
            row.update(line_header)
            ws.append([row[h] for h in SALE_ESTIMATION_HEADERS])
            continue

        for i, comp in enumerate(components):
            row = {h: "" for h in SALE_ESTIMATION_HEADERS}
            if not first_row_written:
                row.update({
                    "estimation_type_id": "Wetworks", "project_estimation_id": project.id,
                    "costing_type": "Product and Service",
                    "source_pricelist_id": "Default AED pricelist",
                    "destination_pricelist_id": "Default AED pricelist",
                    "description": project.name,
                    "estimation_date": project.start_date, "delivery_date": project.end_date,
                    "responsible": project.estimator_name or "",
                })
                first_row_written = True
            if i == 0:
                row.update(line_header)
            row.update({
                "estimation_line_ids/sale_estimation_component_product_line_ids/product_id": comp.support_item.name,
                "estimation_line_ids/sale_estimation_component_product_line_ids/default_code": comp.support_item.default_code or "",
                "estimation_line_ids/sale_estimation_component_product_line_ids/product_uom_qty": round(comp.qty, 4),
                "estimation_line_ids/sale_estimation_component_product_line_ids/cost_price": round(comp.unit_cost, 4),
            })
            ws.append([row[h] for h in SALE_ESTIMATION_HEADERS])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def build_bom_workbook(db, project: models.Project) -> BytesIO:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(BOM_HEADERS)

    for line in project.estimate_lines:
        product_name = line_virtual_product_name(line)
        reference = f"{(line.product.default_code or line.product.name[:6]).strip()}-{line.location.id}-{line.id}"
        bom_lines = line.product.bom_lines
        if not bom_lines:
            ws.append([product_name, reference, 1, "", ""])
            continue
        for i, b in enumerate(bom_lines):
            qty = b.qty_per_unit * (1 + (b.wastage_pct or 0))
            row = [product_name if i == 0 else "", reference if i == 0 else "",
                   1 if i == 0 else "", b.support_item.name, round(qty, 6)]
            ws.append(row)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
