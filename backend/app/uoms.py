"""The units of measure a product or support item may carry -- the unit names
that exist in the client's Odoo (they go straight into the product import's
`product_uom` column, so they must match Odoo's names exactly).

`normalize()` maps the free-text units the catalog was loaded with ("Nos.",
"LMT", "Pcs", ...) onto this list; the API rejects anything else.
`frontend/src/uoms.js` is a hand-kept mirror.
"""

UOMS = [
    "Units", "Bags", "Boards", "Boxes", "Drum", "Nos", "Rolls", "Dozens",
    "g", "oz", "lb", "kg", "t",
    "Hours", "Days",
    "mm", "cm", "in", "ft", "yd", "m", "km", "mi",
    "ft²", "m²",
    "in³", "fl oz (US)", "qt (US)", "L", "gal (US)", "ft³", "m³",
    "Cubic Meter", "Rm", "Sqm",
]

DEFAULT = "Units"

# Factory Work is a one-off service charge, always qty 1.
FACTORY_WORK = "Units"

_BY_LOWER = {u.lower(): u for u in UOMS}

# Legacy catalog spellings (lower-cased) -> an Odoo unit.
_ALIASES = {
    "nos.": "Nos", "no": "Nos", "no.": "Nos",
    "pcs": "Units", "pc": "Units", "set": "Units", "packets": "Units", "packet": "Units",
    "unit": "Units",
    # Linear / running metre.
    "lmt": "Rm", "lm": "Rm",
    "drums": "Drum",
    "box": "Boxes",
    "roll": "Rolls",
    "bag": "Bags",
    "board": "Boards",
    "sq m": "Sqm", "sqmt": "Sqm",
    "cum": "Cubic Meter",
    "ltr": "L", "litre": "L", "liter": "L",
}


def normalize(value) -> str:
    """The Odoo unit for a legacy/free-text unit -- DEFAULT when unknown."""
    key = (value or "").strip().lower()
    return _BY_LOWER.get(key) or _ALIASES.get(key) or DEFAULT


def coerce(value) -> str:
    """For API input: the Odoo unit for an exact name or a known legacy
    spelling; ValueError for anything else."""
    key = (value or "").strip().lower()
    unit = _BY_LOWER.get(key) or _ALIASES.get(key)
    if unit is None:
        raise ValueError(f"unknown unit of measure {value!r} -- use one of: {', '.join(UOMS)}")
    return unit
