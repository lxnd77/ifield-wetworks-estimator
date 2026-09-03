"""Shared business logic used by both the API and the Excel export."""
import math
from sqlalchemy.orm import Session
from . import models, project_types
from .calc import (
    compute_material_cost, compute_material_cost_from_components,
    compute_labor_cost, price_lookup_factory, LaborResult,
)


def recompute_estimate_line(db: Session, line: models.EstimateLine) -> models.EstimateLine:
    project = line.project
    product = line.product
    country = project.country

    if project_types.bom_per_line(project.project_type):
        return _recompute_furniture_line(line)

    price_lookup = price_lookup_factory(db, country.id)
    material = compute_material_cost(product.bom_lines, price_lookup, product.consumable_pct, product.ohp_pct)
    # Furniture projects price on material alone -- no coverage rate, no
    # labor. (compute_labor_cost also returns zero without a coverage rate,
    # but the explicit guard means furniture costing never depends on that
    # side effect, and a stray coverage rate on a furniture product can't
    # leak labor into the line.)
    if project_types.labor_applies(project.project_type):
        labor = compute_labor_cost(product.coverage_rate, country, project.duration_months)
    else:
        labor = LaborResult(cost_per_unit=0.0, wages_per_unit=0.0, expenses_per_unit=0.0)

    line.material_cost_per_unit = material.cost_per_unit
    line.labor_cost_per_unit = labor.cost_per_unit
    line.wages_cost_per_unit = labor.wages_per_unit
    line.labor_expenses_per_unit = labor.expenses_per_unit

    # Upsert the component snapshot by support_item_id rather than
    # delete-all/recreate, so a user-entered item_code (set during
    # estimation, independent of costing) survives a recompute triggered by
    # rate/BOM changes. Rows for support items no longer in the BOM are
    # dropped.
    existing_by_support_item = {c.support_item_id: c for c in line.components}
    seen_support_item_ids = set()
    for comp in material.components:
        # You can't buy a fraction of a drum/roll/pack -- the theoretical
        # consumption is rounded up to the nearest whole purchase unit for
        # the line's total, matching how the source Estimate Form priced
        # purchase quantities (see README "Known limitations").
        raw_qty = comp.qty_per_unit * line.qty
        rounded_qty = math.ceil(raw_qty)
        price_per_uom = (comp.cost_per_unit / comp.qty_per_unit) if comp.qty_per_unit else 0.0
        seen_support_item_ids.add(comp.support_item_id)
        row = existing_by_support_item.get(comp.support_item_id)
        if row is None:
            row = models.EstimateLineComponent(
                estimate_line_id=line.id,
                support_item_id=comp.support_item_id,
            )
            db.add(row)
        row.qty = rounded_qty
        row.unit_cost = comp.unit_price_usd
        row.total_cost = rounded_qty * price_per_uom
    for support_item_id, row in existing_by_support_item.items():
        if support_item_id not in seen_support_item_ids:
            db.delete(row)
    return line


def furniture_fx(project: models.Project) -> float:
    """CNY per USD for a furniture project -- the per-project snapshot, or the
    app default if it was never set."""
    return project.cny_per_usd or project_types.DEFAULT_CNY_PER_USD


def _recompute_furniture_line(line: models.EstimateLine) -> models.EstimateLine:
    """Furniture lines: components are user-authored (support item +
    qty_per_unit + CNY price + item code), so recompute only re-prices the
    rows the estimator entered -- it never adds or removes them.

        components_subtotal = sum(qty_per_unit * price_cny / fx)
        factory_work_usd    = factory_work_cost_cny / fx
        material_cost_per_unit = (components_subtotal + factory_work_usd)
                                 * (1 + product.ohp_pct)

    Consumable % does not apply to furniture; OHP % loads on the line total.
    No labor.
    """
    project = line.project
    product = line.product
    fx = furniture_fx(project)

    material = compute_material_cost_from_components(line.components, fx)
    factory_work_usd = (line.factory_work_cost_cny or 0.0) / fx
    subtotal = material.cost_per_unit + factory_work_usd
    line.material_cost_per_unit = subtotal * (1 + (product.ohp_pct or 0.0))
    line.labor_cost_per_unit = 0.0
    line.wages_cost_per_unit = 0.0
    line.labor_expenses_per_unit = 0.0

    priced = {c.support_item_id: c for c in material.components}
    for row in line.components:
        c = priced.get(row.support_item_id)
        if c is None:
            continue
        # unit_cost / total_cost are the raw converted price (no OHP -- that's
        # a line-level overhead). Furniture quantities are real measures
        # (m of fabric, sqm of stone) -- no whole-pack rounding.
        row.unit_cost = c.unit_price_usd
        row.qty = (row.qty_per_unit or 0.0) * line.qty
        row.total_cost = c.cost_per_unit * line.qty
    return line


def line_totals(project: models.Project, line: models.EstimateLine) -> dict:
    margin = line.margin_pct_override if line.margin_pct_override is not None else project.default_margin_pct
    material_total = line.material_cost_per_unit * line.qty
    labor_total = line.labor_cost_per_unit * line.qty
    cost_total = material_total + labor_total
    sales_value = cost_total * (1 + (margin or 0.0) / 100.0)
    return {
        "material_total": material_total,
        "labor_total": labor_total,
        "cost_total": cost_total,
        "margin_pct": margin or 0.0,
        "sales_value": sales_value,
    }


def project_summary(db: Session, project: models.Project) -> dict:
    material_total = 0.0
    labor_total = 0.0
    sales_total = 0.0
    needs_setup_count = 0
    for line in project.estimate_lines:
        totals = line_totals(project, line)
        material_total += totals["material_total"]
        labor_total += totals["labor_total"]
        sales_total += totals["sales_value"]
        if line.product.needs_setup:
            needs_setup_count += 1
    return {
        "material_total": material_total,
        "labor_total": labor_total,
        "cost_total": material_total + labor_total,
        "sales_total": sales_total,
        "line_count": len(project.estimate_lines),
        "needs_setup_count": needs_setup_count,
    }
