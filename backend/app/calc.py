"""Costing engine.

Reproduces, in generalized/parameterized form, the two source workbooks:
  - LBR Rate Calculation (labor cost per unit of a product, driven by
    coverage/day + crew headcount + country wage & expense parameters +
    project duration)
  - INT_COST_SHEET (material cost per unit, driven by a BOM recipe of
    support items, each with its own wastage% and an optional markup%
    for CMBL/overhead that historically applied to the primary material)

All monetary internal computation happens in USD. Country records store
figures in their natural local currency plus an fx rate to USD so admins
can edit them the way the source sheets present them.
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class ComponentCost:
    support_item_id: int
    support_item_name: str
    qty_per_unit: float  # for 1 unit of the product, wastage-included
    unit_price_usd: float
    cost_per_unit: float


@dataclass
class MaterialResult:
    cost_per_unit: float
    components: List[ComponentCost] = field(default_factory=list)


@dataclass
class LaborResult:
    cost_per_unit: float
    wages_per_unit: float
    expenses_per_unit: float
    breakdown: dict = field(default_factory=dict)


def compute_material_cost(bom_lines, price_lookup) -> MaterialResult:
    """bom_lines: iterable of BomLine ORM objects (with .support_item loaded).
    price_lookup: callable(support_item_id) -> unit_price_usd
    """
    components = []
    total = 0.0
    for line in bom_lines:
        qty_with_wastage = line.qty_per_unit * (1 + (line.wastage_pct or 0))
        unit_price = price_lookup(line.support_item_id)
        cost = qty_with_wastage * unit_price * (1 + (line.markup_pct or 0))
        components.append(ComponentCost(
            support_item_id=line.support_item_id,
            support_item_name=line.support_item.name if line.support_item else "",
            qty_per_unit=qty_with_wastage,
            unit_price_usd=unit_price,
            cost_per_unit=cost,
        ))
        total += cost
    return MaterialResult(cost_per_unit=total, components=components)


def compute_labor_cost(coverage_rate, country, duration_months: float) -> LaborResult:
    """coverage_rate: CoverageRate ORM object.
    country: Country ORM object.
    duration_months: project duration used to amortize one-off mobilization
    costs (air ticket, visa) over the actual length of the engagement --
    shorter projects carry a higher per-unit mobilization cost, matching the
    'duration implies how long labor is supplied' requirement.
    """
    if coverage_rate is None or not coverage_rate.primary_coverage_per_day:
        return LaborResult(cost_per_unit=0.0, wages_per_unit=0.0, expenses_per_unit=0.0,
                            breakdown={"error": "no coverage rate configured"})

    wd_month = country.working_days_per_month or 26.0
    inhouse_day_rate = 0.0
    if country.inhouse_fx_rate_to_usd:
        inhouse_day_rate = (country.inhouse_salary_month_local / wd_month) / country.inhouse_fx_rate_to_usd
    local_day_rate = 0.0
    if country.local_fx_rate_to_usd and country.local_salary_month_local:
        local_day_rate = (country.local_salary_month_local / wd_month) / country.local_fx_rate_to_usd

    inhouse_n = coverage_rate.inhouse_count or 0
    local_n = coverage_rate.local_count or 0
    headcount = inhouse_n + local_n
    if headcount <= 0:
        headcount = 1

    total_crew_day_cost = inhouse_day_rate * inhouse_n + local_day_rate * local_n
    avg_worker_day_rate = total_crew_day_cost / headcount

    primary_cov = coverage_rate.primary_coverage_per_day
    secondary_cov = coverage_rate.secondary_coverage_per_day or 0.0

    primary_wage_per_unit = total_crew_day_cost / primary_cov if primary_cov else 0.0
    secondary_wage_per_unit = (avg_worker_day_rate / secondary_cov) if secondary_cov else 0.0

    sum_wage = primary_wage_per_unit + secondary_wage_per_unit
    ohp_on_wages = sum_wage * (country.wages_oh_rate_pct or 0.0)
    total_wages_per_unit = sum_wage + ohp_on_wages

    site_fx = country.site_fx_rate_to_usd or 1.0
    # Food/accommodation/local travel: monthly local allowance -> daily USD,
    # amortized over a standard working month (recurring cost, independent of
    # project duration -- the worker is fed/housed every day they're on site).
    food_per_day = (country.food_per_month_local or 0.0) / wd_month / site_fx
    accommodation_per_day = (country.accommodation_per_month_local or 0.0) / wd_month / site_fx
    local_travel_per_day = (country.local_travel_per_month_local or 0.0) / wd_month / site_fx
    other_per_day = country.other_allowance_per_day_usd or 0.0

    # Air ticket / visa: one-off annual mobilization cost, amortized over the
    # ACTUAL project duration -- shorter projects carry a higher per-unit
    # mobilization cost since the same fixed cost is recovered over less output.
    air_ticket_per_year = (country.air_ticket_per_year_local or 0.0) / site_fx
    visa_per_year = (country.visa_per_year_local or 0.0) / site_fx
    working_days_total_project = max(wd_month * max(duration_months, 0.1), 1.0)
    air_ticket_per_day = air_ticket_per_year / working_days_total_project
    visa_per_day = visa_per_year / working_days_total_project

    def per_unit(daily_rate):
        return (daily_rate * headcount) / primary_cov if primary_cov else 0.0

    food_u = per_unit(food_per_day)
    accommodation_u = per_unit(accommodation_per_day)
    local_travel_u = per_unit(local_travel_per_day)
    air_ticket_u = per_unit(air_ticket_per_day)
    visa_u = per_unit(visa_per_day)
    other_u = per_unit(other_per_day)

    total_expenses = food_u + accommodation_u + local_travel_u + air_ticket_u + visa_u + other_u
    total = total_wages_per_unit + total_expenses

    return LaborResult(
        cost_per_unit=total,
        wages_per_unit=total_wages_per_unit,
        expenses_per_unit=total_expenses,
        breakdown={
            "inhouse_day_rate": inhouse_day_rate,
            "local_day_rate": local_day_rate,
            "headcount": headcount,
            "primary_wage_per_unit": primary_wage_per_unit,
            "secondary_wage_per_unit": secondary_wage_per_unit,
            "ohp_on_wages": ohp_on_wages,
            "food_per_unit": food_u,
            "accommodation_per_unit": accommodation_u,
            "local_travel_per_unit": local_travel_u,
            "air_ticket_per_unit": air_ticket_u,
            "visa_per_unit": visa_u,
            "other_per_unit": other_u,
            "working_days_total_project": working_days_total_project,
        },
    )


def price_lookup_factory(db, country_id: int):
    from .models import CountryMaterialPrice, Country
    country = db.query(Country).get(country_id)
    fx = country.material_fx_rate_to_usd or 1.0
    rows = db.query(CountryMaterialPrice).filter(CountryMaterialPrice.country_id == country_id).all()
    prices = {r.support_item_id: (r.unit_price_local or 0.0) / fx for r in rows}

    def lookup(support_item_id):
        return prices.get(support_item_id, 0.0)

    return lookup


def compute_estimate_line(product, coverage_rate, country, duration_months, price_lookup):
    material = compute_material_cost(product.bom_lines, price_lookup)
    labor = compute_labor_cost(coverage_rate, country, duration_months)
    return material, labor
