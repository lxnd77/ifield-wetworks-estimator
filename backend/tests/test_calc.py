"""Regression tests locking the costing engine to values independently
verified against the source KSA sample workbooks (see README for the
formula writeup). Run with: pytest tests/ (from backend/)."""
import sys
import os
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.calc import compute_labor_cost, compute_material_cost


def make_ksa_country():
    return SimpleNamespace(
        working_days_per_month=26,
        inhouse_fx_rate_to_usd=94,
        local_fx_rate_to_usd=94,
        wages_oh_rate_pct=0.15,
        site_fx_rate_to_usd=3.75,
        food_per_month_local=900, accommodation_per_month_local=550, local_travel_per_month_local=90,
        air_ticket_per_year_local=1800, visa_per_year_local=13800, other_allowance_per_day_usd=0.5,
    )


def test_labor_cost_floor_tiling_1200x600():
    coverage = SimpleNamespace(primary_coverage_per_day=14, secondary_coverage_per_day=25,
                                inhouse_count=2, local_count=0,
                                inhouse_salary_month_local=45000, local_salary_month_local=0)
    res = compute_labor_cost(coverage, make_ksa_country(), duration_months=12)
    # source sheet: Total Rate/U/M = 8.108063284233497 (sheet rounds some
    # intermediate $/day inputs before reuse; this engine computes from
    # first principles, hence the small tolerance)
    assert abs(res.cost_per_unit - 8.108063284233497) < 0.01


def test_labor_cost_marble_flooring():
    coverage = SimpleNamespace(primary_coverage_per_day=8, secondary_coverage_per_day=50,
                                inhouse_count=4, local_count=0,
                                inhouse_salary_month_local=45000, local_salary_month_local=0)
    res = compute_labor_cost(coverage, make_ksa_country(), duration_months=12)
    assert abs(res.cost_per_unit - 25.83730496453901) < 0.02


def test_shorter_duration_raises_labor_cost():
    """Air ticket / visa are amortized over the actual project duration --
    a shorter project should cost more per unit, not less or the same."""
    coverage = SimpleNamespace(primary_coverage_per_day=14, secondary_coverage_per_day=25,
                                inhouse_count=2, local_count=0,
                                inhouse_salary_month_local=45000, local_salary_month_local=0)
    country = make_ksa_country()
    long_run = compute_labor_cost(coverage, country, duration_months=12)
    short_run = compute_labor_cost(coverage, country, duration_months=3)
    assert short_run.cost_per_unit > long_run.cost_per_unit


def test_material_cost_matches_estimate_form_formula():
    # Floor GVT Tile 60x120: unit_price=13.5, wastage=10%, CMBL=15%, OH=10%
    bom_line = SimpleNamespace(qty_per_unit=1.0, wastage_pct=0.1, markup_pct=0.25,
                                support_item_id=1, support_item=None)
    result = compute_material_cost([bom_line], lambda sid: 13.5)
    assert abs(result.cost_per_unit - 18.5625) < 1e-9


def test_material_cost_sums_multiple_bom_lines():
    lines = [
        SimpleNamespace(qty_per_unit=1 / 130, wastage_pct=0.0, markup_pct=0.0, support_item_id=1, support_item=None),
        SimpleNamespace(qty_per_unit=1 / 35, wastage_pct=0.0, markup_pct=0.0, support_item_id=2, support_item=None),
        SimpleNamespace(qty_per_unit=1 / 65, wastage_pct=0.0, markup_pct=0.0, support_item_id=3, support_item=None),
    ]
    prices = {1: 14.756756756756756, 2: 15.070270270270269, 3: 46.486486486486484}
    result = compute_material_cost(lines, lambda sid: prices[sid])
    assert abs(result.cost_per_unit - 1.2592693792693792) < 1e-6
