"""Single source of truth for the three estimation modes.

- ``wetworks``        -- the original: material cost + labor cost. Dates are
                         required (they drive labor mobilization
                         amortization in calc.compute_labor_cost).
- ``loose_furniture`` -- material cost only. No coverage rate, no labor.
- ``fixed_furniture`` -- identical to loose_furniture in the engine; differs
                         only by label and the Odoo ``estimation_type_id``
                         stamped on the sale-estimation export.

Both ``Project.project_type`` and ``Product.product_type`` take these
values, and a line item can only be added to a project of the matching
type. This module is imported by the API (validation, the
``/api/project-types`` endpoint), the costing service (phase 02), and the
Excel exports (phase 03) so the rules live in exactly one place.

The ``odoo_estimation_type`` strings for the two furniture modes are
provisional -- they must match values that already exist in the client's
Odoo ``estimation_type_id`` model. Change them here once confirmed.
"""

WETWORKS = "wetworks"
LOOSE_FURNITURE = "loose_furniture"
FIXED_FURNITURE = "fixed_furniture"

DEFAULT = WETWORKS

CONFIG = {
    WETWORKS: {
        "label": "Wetworks",
        "labor_applies": True,
        # False: the product's BOM recipe fixes component quantities.
        # True: component quantities are entered per estimate line, and each
        # line with a BOM carries a per-project "Factory Work" charge.
        "bom_per_line": False,
        "dates_required": True,
        "odoo_estimation_type": "Wetworks",
    },
    LOOSE_FURNITURE: {
        "label": "Loose Furniture",
        "labor_applies": False,
        "bom_per_line": True,
        "dates_required": False,
        "odoo_estimation_type": "Loose Furniture",  # TODO confirm exact Odoo value
    },
    FIXED_FURNITURE: {
        "label": "Fixed Furniture",
        "labor_applies": False,
        "bom_per_line": True,
        "dates_required": False,
        "odoo_estimation_type": "Fixed Furniture",  # TODO confirm exact Odoo value
    },
}

# Support-item purchase_category values the furniture side uses (drives the
# component picker filter). Wetworks uses Paint / Tile / Stone / Metal.
FURNITURE_BOM_CATEGORIES = ["Fabric", "Stone", "Metal", "Accessories"]

VALUES = tuple(CONFIG)


def _cfg(project_type):
    return CONFIG.get(project_type or DEFAULT, CONFIG[DEFAULT])


def is_valid(project_type) -> bool:
    return project_type in CONFIG


def label(project_type) -> str:
    return _cfg(project_type)["label"]


def labor_applies(project_type) -> bool:
    return _cfg(project_type)["labor_applies"]


def bom_per_line(project_type) -> bool:
    return _cfg(project_type)["bom_per_line"]


def dates_required(project_type) -> bool:
    return _cfg(project_type)["dates_required"]


def odoo_estimation_type(project_type) -> str:
    return _cfg(project_type)["odoo_estimation_type"]


def as_api_list() -> list:
    """Payload for GET /api/project-types -- the frontend builds its
    project-type picker and column/visibility rules from this."""
    return [{"value": v, **CONFIG[v]} for v in VALUES]
