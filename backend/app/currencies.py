"""Each I-Field company keeps its books in its own currency, so the product
import's standard_price on a company's workbook is converted into it (see
export_excel.build_product_import_workbooks). A company's currency_code /
fx_rate_to_usd are editable in Admin > Settings; these are the defaults a
company gets from its country when they're left blank.

The INR / NGN rates are placeholders -- set the live rate on the company.
A CNY company's rate is only a fallback: exports use the project's own
cny_per_usd, so furniture prices entered in CNY land on its sheet unchanged.
"""
from . import project_types

_BY_COUNTRY = {
    "china": ("CNY", project_types.DEFAULT_CNY_PER_USD),
    "india": ("INR", 88.0),
    "nigeria": ("NGN", 1500.0),
    "hong kong": ("USD", 1.0),
    "uae": ("USD", 1.0),
    "dubai": ("USD", 1.0),
}


def default_for_country(country_name):
    """(currency_code, units per 1 USD) for a company in this country --
    USD for anything not listed."""
    return _BY_COUNTRY.get((country_name or "").strip().lower(), ("USD", 1.0))


def default_rate(currency_code) -> float:
    for code, rate in _BY_COUNTRY.values():
        if code == currency_code:
            return rate
    return 1.0
