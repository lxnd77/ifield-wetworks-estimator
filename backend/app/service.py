"""Shared business logic used by both the API and the Excel export."""
import math
from sqlalchemy.orm import Session
from . import models
from .calc import compute_material_cost, compute_labor_cost, price_lookup_factory


def recompute_estimate_line(db: Session, line: models.EstimateLine) -> models.EstimateLine:
    project = line.project
    product = line.product
    country = project.country

    price_lookup = price_lookup_factory(db, country.id)
    material = compute_material_cost(product.bom_lines, price_lookup)
    labor = compute_labor_cost(product.coverage_rate, country, project.duration_months)

    line.material_cost_per_unit = material.cost_per_unit
    line.labor_cost_per_unit = labor.cost_per_unit
    line.wages_cost_per_unit = labor.wages_per_unit
    line.labor_expenses_per_unit = labor.expenses_per_unit

    # replace component snapshot
    for c in list(line.components):
        db.delete(c)
    db.flush()
    for comp in material.components:
        # You can't buy a fraction of a drum/roll/pack -- the theoretical
        # consumption is rounded up to the nearest whole purchase unit for
        # the line's total, matching how the source Estimate Form priced
        # purchase quantities (see README "Known limitations").
        raw_qty = comp.qty_per_unit * line.qty
        rounded_qty = math.ceil(raw_qty)
        price_per_uom = (comp.cost_per_unit / comp.qty_per_unit) if comp.qty_per_unit else 0.0
        db.add(models.EstimateLineComponent(
            estimate_line_id=line.id,
            support_item_id=comp.support_item_id,
            qty=rounded_qty,
            unit_cost=comp.unit_price_usd,
            total_cost=rounded_qty * price_per_uom,
        ))
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
