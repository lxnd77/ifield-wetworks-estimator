from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey, Text, UniqueConstraint
)
from sqlalchemy.orm import relationship
from .database import Base


class Vendor(Base):
    """An external supplier a SupportItem (BOM item) is actually bought from,
    e.g. a specific tile or paint supplier. Distinct from PurchasingCompany,
    which is the I-Field entity that buys from this vendor on the purchasing
    country's behalf."""

    # NOTE (furniture extension, phase 00): the catalog is no longer
    # Wetworks-only. WetworksProduct -> Product, table wetworks_products ->
    # products. "Wetworks" survives only as a project/product *type* value,
    # not in identifiers.
    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    notes = Column(Text, nullable=True)


class PurchasingCompany(Base):
    """An I-Field entity that buys a finished line item on behalf of the
    selling company, e.g. 'I FIELD FURNISHING TRADING LLC' (Dubai) for
    Wetworks. Tied to a Product as its default purchasing route."""
    __tablename__ = "purchasing_companies"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    country_name = Column(String, nullable=True)
    notes = Column(Text, nullable=True)


class SellingCompany(Base):
    """An I-Field entity that invoices the client, e.g. an I-Field Hong Kong
    entity for sales. Selected per project."""
    __tablename__ = "selling_companies"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    country_name = Column(String, nullable=True)
    notes = Column(Text, nullable=True)


class SupportItem(Base):
    """A purchasable material / BOM component (cement, gypsum board, paint tin,
    screws...). A product's own 'primary' material (e.g. the tile itself)
    is also represented as a SupportItem so it can carry a country-specific price
    just like any other component."""
    __tablename__ = "support_items"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    default_code = Column(String, nullable=True)  # Odoo internal reference
    # Odoo's own product.template external id (e.g.
    # "__export__.product_template_1546_5560096f"), once this item has been
    # imported and the Odoo-generated id is known. Distinct from
    # default_code (the Odoo internal reference/SKU) -- this is what makes a
    # re-import an update instead of a duplicate. Populated in export sheets
    # whenever set.
    odoo_id = Column(String, nullable=True)
    uom = Column(String, nullable=False, default="Pcs")
    notes = Column(Text, nullable=True)
    # Independent of Product.category -- classifies the BOM item
    # itself for purchasing/export purposes (which categories get a
    # user-entered item code during estimation: Paint/Tile/Stone/Metal).
    purchase_category = Column(String, nullable=True)
    default_vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    # The I-Field entity that buys this item from its vendor. On the product
    # import export, a BOM component goes on this company's workbook; when
    # unset it falls back to the line product's purchasing company (how
    # wetworks recipes are routed). Furniture components rely on this --
    # furniture products themselves have no purchasing company.
    purchasing_company_id = Column(Integer, ForeignKey("purchasing_companies.id"), nullable=True)

    prices = relationship("CountryMaterialPrice", back_populates="support_item", cascade="all, delete-orphan")
    default_vendor = relationship("Vendor")
    purchasing_company = relationship("PurchasingCompany")


class Product(Base):
    """A line item from the Product Master (e.g. 'Floor GVT Tile 60 X120')."""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    uom = Column(String, nullable=False)
    category = Column(String, nullable=False)  # Tile / False Ceiling / Paint / Stone / Counters / Flooring
    # Which estimation mode this product belongs to -- see app/project_types.py.
    # "wetworks" (material + labor) / "loose_furniture" / "fixed_furniture"
    # (material only, no coverage rate). A line item can only be added to a
    # project of the matching type.
    product_type = Column(String, nullable=False, server_default="wetworks")
    default_code = Column(String, nullable=True)
    # Odoo's own product.template external id, once known -- see
    # SupportItem.odoo_id for what this is and why it's separate from
    # default_code.
    odoo_id = Column(String, nullable=True)
    active = Column(Boolean, default=True)
    # True until an admin has supplied coverage-rate + BOM data for this product.
    needs_setup = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    # Default purchasing route: the I-Field entity that buys this finished
    # line item on behalf of the project's selling company (e.g. Dubai for
    # Wetworks projects). default_vendor_id is an override for the rare case the
    # line item is bought whole, directly from a vendor, bypassing the
    # purchasing company.
    purchasing_company_id = Column(Integer, ForeignKey("purchasing_companies.id"), nullable=True)
    default_vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    # Material cost markup on the primary BOM line, historically "CMBL%" +
    # overhead % in the source Estimate Form -- tracked per product (not per
    # BOM line) since the source data is one CMBL/OH pair per product,
    # applied only to its primary material.
    consumable_pct = Column(Float, nullable=False, default=0.0)
    ohp_pct = Column(Float, nullable=False, default=0.0)

    bom_lines = relationship("BomLine", back_populates="product", cascade="all, delete-orphan",
                              order_by="BomLine.sort_order")
    coverage_rate = relationship("CoverageRate", back_populates="product", uselist=False,
                                  cascade="all, delete-orphan")
    purchasing_company = relationship("PurchasingCompany")
    default_vendor = relationship("Vendor")


class BomLine(Base):
    """One recipe line: how much of a SupportItem is needed per 1 unit of a
    Product, before/after wastage. Recipe quantities are global
    (country-independent) per the product decision -- only the SupportItem's
    price varies by country."""
    __tablename__ = "bom_lines"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    support_item_id = Column(Integer, ForeignKey("support_items.id"), nullable=False)
    qty_per_unit = Column(Float, nullable=False)  # before wastage
    wastage_pct = Column(Float, nullable=False, default=0.0)  # e.g. 0.1 = 10%
    role = Column(String, nullable=False, default="fixing")  # 'primary' or 'fixing' -- consumable/OHP % (on the product) applies only to 'primary' lines
    sort_order = Column(Integer, nullable=False, default=0)

    product = relationship("Product", back_populates="bom_lines")
    support_item = relationship("SupportItem")


class CoverageRate(Base):
    """How much labor a product needs: production coverage/day and headcount.
    Global (country-independent) per the product decision."""
    __tablename__ = "coverage_rates"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, unique=True)
    primary_coverage_per_day = Column(Float, nullable=False)  # e.g. sqm/day the crew produces
    secondary_coverage_per_day = Column(Float, nullable=True, default=0.0)  # e.g. grouting sqm/day per worker
    inhouse_count = Column(Integer, nullable=False, default=2)
    local_count = Column(Integer, nullable=False, default=0)
    # Wages vary by trade (a tiler earns differently than a painter), so salary
    # is set per product, not on the country's rate card.
    inhouse_salary_month_local = Column(Float, nullable=False, default=0.0)
    local_salary_month_local = Column(Float, nullable=False, default=0.0)

    product = relationship("Product", back_populates="coverage_rate")

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


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    is_admin = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    # Estimation mode -- see app/project_types.py. "wetworks" (material +
    # labor, dates required) / "loose_furniture" / "fixed_furniture"
    # (material only, dates optional). Drives which products can be added,
    # whether labor is costed, and the Odoo estimation_type_id on export.
    project_type = Column(String, nullable=False, server_default="wetworks")
    # Short code (e.g. "FLH") used as the project half of the Odoo product
    # reference code: f"{code} {item_code}" e.g. "FLH PT-01".
    code = Column(String, nullable=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False)
    selling_company_id = Column(Integer, ForeignKey("selling_companies.id"), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    client_name = Column(String, nullable=True)
    address = Column(String, nullable=True)
    estimator_name = Column(String, nullable=True)
    # Required for wetworks projects (they drive labor mobilization
    # amortization); optional for furniture, where nothing reads them for
    # costing. Enforced per project_type at the API layer, not the schema.
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    default_margin_pct = Column(Float, nullable=False, default=0.0)
    display_currency = Column(String, nullable=False, default="USD")
    # Furniture only: CNY per 1 USD. Furniture component prices and the
    # Factory Work charge are entered in Chinese yuan (the products are
    # China-sourced) and divided by this to get USD. Snapshotted from
    # project_types.DEFAULT_CNY_PER_USD at creation, editable per project so a
    # saved estimate doesn't move when the live rate does. Unused for wetworks.
    cny_per_usd = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    country = relationship("Country")
    selling_company = relationship("SellingCompany")
    owner = relationship("User")
    locations = relationship("ProjectLocation", back_populates="project", cascade="all, delete-orphan")
    estimate_lines = relationship("EstimateLine", back_populates="project", cascade="all, delete-orphan")

    @property
    def duration_months(self):
        # Furniture projects may have no dates; nothing reads this for their
        # costing, so a neutral 1.0 keeps compute_labor_cost's math finite.
        if not self.start_date or not self.end_date:
            return 1.0
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
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    qty = Column(Float, nullable=False)
    margin_pct_override = Column(Float, nullable=True)
    drawing_no = Column(String, nullable=True)
    remark = Column(String, nullable=True)  # sale estimation export only
    # Free-text product description -- distinct from `remark`, which is a
    # sale-estimation-sheet-only field. Not currently surfaced in any export
    # (was product-import's product_description column, removed).
    description = Column(String, nullable=True)
    dimension = Column(String, nullable=True)  # not currently surfaced in any export (was product-import's product_dimension column, removed)
    # User-entered during estimation; combines with Project.code to form the
    # Odoo product reference code for this line item. Required + unique within
    # the project for furniture lines that carry components (the standalone
    # BOM export is keyed by it) -- enforced at the API layer.
    item_code = Column(String, nullable=True)

    # Furniture only: the per-project "Factory Work for <product>" charge that
    # every furniture line with a BOM must carry (qty is always 1), entered in
    # CNY. Converted to USD (via Project.cny_per_usd), folded into
    # material_cost_per_unit, and emitted as a qty-1 component row in all three
    # exports. Null / unused for wetworks.
    factory_work_cost_cny = Column(Float, nullable=True)

    # computed / cached at save time (per unit, in USD)
    material_cost_per_unit = Column(Float, default=0.0)
    labor_cost_per_unit = Column(Float, default=0.0)
    wages_cost_per_unit = Column(Float, default=0.0)
    labor_expenses_per_unit = Column(Float, default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="estimate_lines")
    location = relationship("ProjectLocation", back_populates="estimate_lines")
    product = relationship("Product")
    components = relationship("EstimateLineComponent", back_populates="estimate_line", cascade="all, delete-orphan")


class EstimateLineComponent(Base):
    """One BOM component of an estimate line, priced at the country rates used
    when the line was last computed. Powers the BOM Odoo export.

    For WETWORKS lines these rows are a *derived snapshot* -- rebuilt on every
    recompute by exploding the product's fixed recipe (qty_per_unit stays
    null; `qty` is the whole-pack-rounded total).

    For FURNITURE lines these rows are *user-authored* -- the estimator picks
    each support item (Fabric / Stone / Metal / Accessories) and enters
    `qty_per_unit`, `unit_price_cny`, and a project-unique `item_code` for this
    project; recompute only re-prices them, never adds or removes them.
    """
    __tablename__ = "estimate_line_components"

    id = Column(Integer, primary_key=True)
    estimate_line_id = Column(Integer, ForeignKey("estimate_lines.id"), nullable=False)
    support_item_id = Column(Integer, ForeignKey("support_items.id"), nullable=False)
    # Furniture: user-entered consumption per 1 unit of the product. Wetworks:
    # null (the recipe drives it; only the rounded total `qty` is stored).
    qty_per_unit = Column(Float, nullable=True)
    # Furniture: user-entered purchase price in CNY. Wetworks: null (priced
    # from CountryMaterialPrice).
    unit_price_cny = Column(Float, nullable=True)
    qty = Column(Float, nullable=False)  # total qty for the line's full estimate qty
    unit_cost = Column(Float, nullable=False)  # USD per uom of the support item
    total_cost = Column(Float, nullable=False)
    # User-entered during estimation; preserved across recompute_estimate_line
    # (which upserts by support_item_id rather than delete/recreate) so it
    # survives rate/BOM changes that trigger a recompute.
    item_code = Column(String, nullable=True)

    estimate_line = relationship("EstimateLine", back_populates="components")
    support_item = relationship("SupportItem")
