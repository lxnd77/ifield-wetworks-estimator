from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey, Text, UniqueConstraint
)
from sqlalchemy.orm import relationship
from .database import Base


class SupportItem(Base):
    """A purchasable material / BOM component (cement, gypsum board, paint tin,
    screws...). A Wetworks product's own 'primary' material (e.g. the tile itself)
    is also represented as a SupportItem so it can carry a country-specific price
    just like any other component."""
    __tablename__ = "support_items"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    default_code = Column(String, nullable=True)  # Odoo internal reference
    uom = Column(String, nullable=False, default="Pcs")
    notes = Column(Text, nullable=True)

    prices = relationship("CountryMaterialPrice", back_populates="support_item", cascade="all, delete-orphan")


class WetworksProduct(Base):
    """A Wetworks line item from the Product Master (e.g. 'Floor GVT Tile 60 X120')."""
    __tablename__ = "wetworks_products"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    uom = Column(String, nullable=False)
    category = Column(String, nullable=False)  # Tile / False Ceiling / Paint / Stone / Counters / Flooring
    default_code = Column(String, nullable=True)
    active = Column(Boolean, default=True)
    # True until an admin has supplied coverage-rate + BOM data for this product.
    needs_setup = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)

    bom_lines = relationship("BomLine", back_populates="product", cascade="all, delete-orphan",
                              order_by="BomLine.sort_order")
    coverage_rate = relationship("CoverageRate", back_populates="product", uselist=False,
                                  cascade="all, delete-orphan")


class BomLine(Base):
    """One recipe line: how much of a SupportItem is needed per 1 unit of a
    WetworksProduct, before/after wastage. Recipe quantities are global
    (country-independent) per the product decision -- only the SupportItem's
    price varies by country."""
    __tablename__ = "bom_lines"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("wetworks_products.id"), nullable=False)
    support_item_id = Column(Integer, ForeignKey("support_items.id"), nullable=False)
    qty_per_unit = Column(Float, nullable=False)  # before wastage
    wastage_pct = Column(Float, nullable=False, default=0.0)  # e.g. 0.1 = 10%
    markup_pct = Column(Float, nullable=False, default=0.0)  # e.g. CMBL%+OH% combined, mainly on primary material
    role = Column(String, nullable=False, default="fixing")  # 'primary' or 'fixing'
    sort_order = Column(Integer, nullable=False, default=0)

    product = relationship("WetworksProduct", back_populates="bom_lines")
    support_item = relationship("SupportItem")


class CoverageRate(Base):
    """How much labor a product needs: production coverage/day and headcount.
    Global (country-independent) per the product decision."""
    __tablename__ = "coverage_rates"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("wetworks_products.id"), nullable=False, unique=True)
    primary_coverage_per_day = Column(Float, nullable=False)  # e.g. sqm/day the crew produces
    secondary_coverage_per_day = Column(Float, nullable=True, default=0.0)  # e.g. grouting sqm/day per worker
    inhouse_count = Column(Integer, nullable=False, default=2)
    local_count = Column(Integer, nullable=False, default=0)

    product = relationship("WetworksProduct", back_populates="coverage_rate")

    @property
    def total_labor(self):
        return (self.inhouse_count or 0) + (self.local_count or 0)


class Country(Base):
    __tablename__ = "countries"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    code = Column(String, nullable=False, unique=True)  # short code e.g. "KSA"
    is_active = Column(Boolean, default=True)
    is_template = Column(Boolean, default=False)  # True = created via "add a country" wizard, awaiting data

    # currencies / fx (rate = local units per 1 USD)
    site_currency_code = Column(String, default="USD")
    site_fx_rate_to_usd = Column(Float, default=1.0)
    inhouse_labor_currency_code = Column(String, default="USD")
    inhouse_fx_rate_to_usd = Column(Float, default=1.0)
    local_labor_currency_code = Column(String, default="USD")
    local_fx_rate_to_usd = Column(Float, default=1.0)
    material_currency_code = Column(String, default="USD")
    material_fx_rate_to_usd = Column(Float, default=1.0)

    working_days_per_month = Column(Float, default=26.0)
    wages_oh_rate_pct = Column(Float, default=0.15)

    inhouse_salary_month_local = Column(Float, default=0.0)
    local_salary_month_local = Column(Float, default=0.0)

    # NOTE: food/accommodation/local travel are entered as MONTHLY local-currency
    # allowances (same as salary) and amortized over working_days_per_month --
    # this matches the source LBR sheet exactly (e.g. 900 SAR/month -> $9.24/day).
    food_per_month_local = Column(Float, default=0.0)
    accommodation_per_month_local = Column(Float, default=0.0)
    local_travel_per_month_local = Column(Float, default=0.0)
    air_ticket_per_year_local = Column(Float, default=0.0)
    visa_per_year_local = Column(Float, default=0.0)
    other_allowance_per_day_usd = Column(Float, default=0.0)

    notes = Column(Text, nullable=True)

    material_prices = relationship("CountryMaterialPrice", back_populates="country", cascade="all, delete-orphan")


class CountryMaterialPrice(Base):
    __tablename__ = "country_material_prices"
    __table_args__ = (UniqueConstraint("country_id", "support_item_id", name="uq_country_support_item"),)

    id = Column(Integer, primary_key=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False)
    support_item_id = Column(Integer, ForeignKey("support_items.id"), nullable=False)
    unit_price_local = Column(Float, nullable=False, default=0.0)

    country = relationship("Country", back_populates="material_prices")
    support_item = relationship("SupportItem", back_populates="prices")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False)
    client_name = Column(String, nullable=True)
    address = Column(String, nullable=True)
    estimator_name = Column(String, nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    default_margin_pct = Column(Float, nullable=False, default=0.0)
    display_currency = Column(String, nullable=False, default="USD")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    country = relationship("Country")
    locations = relationship("ProjectLocation", back_populates="project", cascade="all, delete-orphan")
    estimate_lines = relationship("EstimateLine", back_populates="project", cascade="all, delete-orphan")

    @property
    def duration_months(self):
        days = (self.end_date - self.start_date).days
        return max(days, 1) / 30.4368


class ProjectLocation(Base):
    __tablename__ = "project_locations"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    sort_order = Column(Integer, default=0)

    project = relationship("Project", back_populates="locations")
    estimate_lines = relationship("EstimateLine", back_populates="location", cascade="all, delete-orphan")


class EstimateLine(Base):
    __tablename__ = "estimate_lines"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("project_locations.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("wetworks_products.id"), nullable=False)
    qty = Column(Float, nullable=False)
    margin_pct_override = Column(Float, nullable=True)
    drawing_no = Column(String, nullable=True)
    remark = Column(String, nullable=True)

    # computed / cached at save time (per unit, in USD)
    material_cost_per_unit = Column(Float, default=0.0)
    labor_cost_per_unit = Column(Float, default=0.0)
    wages_cost_per_unit = Column(Float, default=0.0)
    labor_expenses_per_unit = Column(Float, default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="estimate_lines")
    location = relationship("ProjectLocation", back_populates="estimate_lines")
    product = relationship("WetworksProduct")
    components = relationship("EstimateLineComponent", back_populates="estimate_line", cascade="all, delete-orphan")


class EstimateLineComponent(Base):
    """Snapshot of the exploded BOM for one estimate line, at the country prices
    used when the line was last computed. Powers the BOM Odoo export."""
    __tablename__ = "estimate_line_components"

    id = Column(Integer, primary_key=True)
    estimate_line_id = Column(Integer, ForeignKey("estimate_lines.id"), nullable=False)
    support_item_id = Column(Integer, ForeignKey("support_items.id"), nullable=False)
    qty = Column(Float, nullable=False)  # total qty for the line's full estimate qty
    unit_cost = Column(Float, nullable=False)  # USD per uom of the support item
    total_cost = Column(Float, nullable=False)

    estimate_line = relationship("EstimateLine", back_populates="components")
    support_item = relationship("SupportItem")
