from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class SupportItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    default_code: Optional[str] = None
    uom: str


class BomLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    support_item_id: int
    support_item: SupportItemOut
    qty_per_unit: float
    wastage_pct: float
    markup_pct: float
    role: str
    sort_order: int


class BomLineIn(BaseModel):
    support_item_id: Optional[int] = None
    new_support_item_name: Optional[str] = None
    new_support_item_uom: Optional[str] = None
    new_support_item_default_code: Optional[str] = None
    qty_per_unit: float
    wastage_pct: float = 0.0
    markup_pct: float = 0.0
    role: str = "fixing"
    sort_order: int = 0


class CoverageRateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    primary_coverage_per_day: float
    secondary_coverage_per_day: Optional[float] = 0.0
    inhouse_count: int
    local_count: int
    inhouse_salary_month_local: float
    local_salary_month_local: float


class CoverageRateIn(BaseModel):
    primary_coverage_per_day: float
    secondary_coverage_per_day: float = 0.0
    inhouse_count: int = 2
    local_count: int = 0
    inhouse_salary_month_local: float = 0.0
    local_salary_month_local: float = 0.0


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    uom: str
    category: str
    default_code: Optional[str] = None
    active: bool
    needs_setup: bool
    notes: Optional[str] = None


class ProductDetailOut(ProductOut):
    bom_lines: List[BomLineOut] = []
    coverage_rate: Optional[CoverageRateOut] = None


class ProductIn(BaseModel):
    name: str
    uom: str
    category: str
    default_code: Optional[str] = None
    notes: Optional[str] = None


class CountryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    code: str
    is_active: bool
    is_template: bool
    site_currency_code: str
    site_fx_rate_to_usd: float
    inhouse_labor_currency_code: str
    inhouse_fx_rate_to_usd: float
    local_labor_currency_code: str
    local_fx_rate_to_usd: float
    material_currency_code: str
    material_fx_rate_to_usd: float
    working_days_per_month: float
    wages_oh_rate_pct: float
    food_per_month_local: float
    accommodation_per_month_local: float
    local_travel_per_month_local: float
    air_ticket_per_year_local: float
    visa_per_year_local: float
    other_allowance_per_day_usd: float
    notes: Optional[str] = None


class CountryIn(BaseModel):
    name: str
    code: str
    site_currency_code: str = "USD"
    site_fx_rate_to_usd: float = 1.0
    inhouse_labor_currency_code: str = "USD"
    inhouse_fx_rate_to_usd: float = 1.0
    local_labor_currency_code: str = "USD"
    local_fx_rate_to_usd: float = 1.0
    material_currency_code: str = "USD"
    material_fx_rate_to_usd: float = 1.0
    working_days_per_month: float = 26.0
    wages_oh_rate_pct: float = 0.15
    food_per_month_local: float = 0.0
    accommodation_per_month_local: float = 0.0
    local_travel_per_month_local: float = 0.0
    air_ticket_per_year_local: float = 0.0
    visa_per_year_local: float = 0.0
    other_allowance_per_day_usd: float = 0.0
    notes: Optional[str] = None


class CountryMaterialPriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    support_item_id: int
    support_item: SupportItemOut
    unit_price_local: float


class CountryMaterialPriceIn(BaseModel):
    support_item_id: int
    unit_price_local: float


class ProjectLocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    sort_order: int


class ProjectLocationIn(BaseModel):
    name: str
    sort_order: int = 0


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    country_id: int
    country: CountryOut
    client_name: Optional[str] = None
    address: Optional[str] = None
    estimator_name: Optional[str] = None
    start_date: date
    end_date: date
    default_margin_pct: float
    display_currency: str
    notes: Optional[str] = None
    created_at: datetime
    locations: List[ProjectLocationOut] = []


class ProjectIn(BaseModel):
    name: str
    country_id: int
    client_name: Optional[str] = None
    address: Optional[str] = None
    estimator_name: Optional[str] = None
    start_date: date
    end_date: date
    default_margin_pct: float = 0.0
    display_currency: str = "USD"
    notes: Optional[str] = None


class EstimateLineComponentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    support_item_id: int
    support_item: SupportItemOut
    qty: float
    unit_cost: float
    total_cost: float


class EstimateLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    location_id: int
    product_id: int
    product: ProductOut
    qty: float
    margin_pct_override: Optional[float] = None
    drawing_no: Optional[str] = None
    remark: Optional[str] = None
    material_cost_per_unit: float
    labor_cost_per_unit: float
    wages_cost_per_unit: float
    labor_expenses_per_unit: float
    components: List[EstimateLineComponentOut] = []

    @property
    def total_cost_per_unit(self) -> float:
        return self.material_cost_per_unit + self.labor_cost_per_unit


class EstimateLineIn(BaseModel):
    location_id: int
    product_id: int
    qty: float
    margin_pct_override: Optional[float] = None
    drawing_no: Optional[str] = None
    remark: Optional[str] = None
