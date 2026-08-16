"""KSA country seed: coverage rates (labor) + BOM/material data, reverse
engineered from 10062026_LBR_Rate_Calculation_ETRA_Final_Sent.xlsx and
10062026_INT_COST_SHEET_KSA.xlsx (the "Khadar Villa" sample estimate).

Design notes (see README for the full writeup):
  - Every product gets a bundled "primary material" BOM line using the
    Estimate Form's already-USD-converted MATERIAL UNIT PRICE / WSTG% /
    (CMBL%+OH%) -- this reproduces that sheet's Material Cost/Unit exactly.
  - Wall Paint (caprol/Jotun) and RG/MR Gypsum Ceiling additionally get a
    fully itemized BOM (primer/stucco/paint; board/channels/screws/tape...)
    sourced from the Paint / RG Ceiling / MR Ceiling sheets, because that
    itemized detail is what the target BOM Odoo export format expects and
    because the source data for exactly these two families was clean and
    complete. Everything else uses the single bundled line until an admin
    supplies a fuller recipe.
  - Coverage rates (how much labor a product needs) come from the LBR sheet,
    matched to products by tile format / work type. Where LBR labels a
    generic "Tilling"/"Grouting" coverage column, that is treated as the
    PRIMARY / SECONDARY coverage-per-day for whatever work type the row
    describes (ceiling, punning, paint...), matching how the source sheet
    itself reuses those columns.
"""

# (lbr_key -> (primary_coverage_per_day, secondary_coverage_per_day, inhouse_count,
#              local_count, inhouse_salary_month_local, local_salary_month_local))
# Salary is per-trade (set on the product's coverage rate), not a single
# country-wide figure -- confirmed against column O ("In-House Salary/Month")
# of the source LBR Rate Calculation sheet, which is NOT uniform: most
# tiling/stone/skirting trades are 45,000 SAR/month, but painting, punning,
# gypsum ceiling, dry wall, plaster, and waterproofing are 40,000.
LBR_COVERAGE = {
    "floor_1200x600": (14, 25, 2, 0, 45000, 0),
    "floor_600x600": (16, 25, 2, 0, 45000, 0),
    "floor_600x300": (18, 25, 2, 0, 45000, 0),
    "floor_300x300": (20, 25, 2, 0, 45000, 0),
    "floor_1200x600_20mm": (8, 25, 2, 0, 45000, 0),
    "marble_flooring": (8, 50, 4, 0, 45000, 0),
    "marble_cladding": (5, 50, 4, 0, 45000, 0),
    "marble_skirting": (20, 50, 4, 0, 45000, 0),
    "tile_skirting": (50, 50, 2, 0, 45000, 0),
    "tile_skirting_20mm": (25, 25, 2, 0, 45000, 0),
    "wall_1200x1200": (10, 24.3, 2, 0, 45000, 0),
    "wall_1200x600": (12, 24.3, 2, 0, 45000, 0),
    "wall_600x600": (12, 24.3, 2, 0, 45000, 0),
    "wall_600x300": (14, 24.3, 2, 0, 45000, 0),
    "gypsum_ceiling": (14, 0, 3, 0, 40000, 0),
    "gypsum_corniche": (20, 0, 2, 0, 45000, 0),
    "dry_wall_partition": (10, 0, 3, 0, 40000, 0),
    "wall_punning": (15, 0, 2, 0, 40000, 0),
    "ceiling_punning": (10, 0, 2, 0, 40000, 0),
    "wall_paint": (18, 0, 1, 0, 40000, 0),
    "ceiling_paint": (14, 0, 1, 0, 40000, 0),
    "decorative_paint": (9, 0, 1, 0, 40000, 0),
    "exterior_paint": (15, 0, 1, 0, 40000, 0),
    "ips_30mm": (55, 0, 3, 0, 45000, 0),
    "ips_50mm": (40, 0, 3, 0, 45000, 0),
    "plaster": (10, 0, 1, 0, 40000, 0),
    "waterproofing_2coat": (15, 0, 1, 0, 40000, 0),
    "staircase_step": (15.5, 10, 2, 0, 45000, 0),
    "staircase_skirting": (20, 20, 2, 0, 45000, 0),
}

# product_name -> lbr_key  (only products with confirmed LBR coverage are listed;
# everything else is left out of scope for V1 and stays needs_setup=True)
PRODUCT_COVERAGE_MAP = {
    "Floor GVT Tile 60 X120": "floor_1200x600",
    "Floor GVT Tile 60 X60": "floor_600x600",
    "Floor GVT Tile 60 X30": "floor_600x300",
    "Floor Ceramic Tile 60 X30": "floor_600x300",
    "Floor Ceramic Tile 30 X30": "floor_300x300",
    "Floor full body - 120X60": "floor_1200x600",
    "Floor full body - 60X60": "floor_600x600",
    "Floor full body- Digital - 120X60": "floor_1200x600",
    "Floor full body- Digital - 60X60": "floor_600x600",
    "Floor Full body Tile 120X20": "floor_1200x600",
    "Floor Full Body Tile 60 X60 - 20 mm": "floor_1200x600_20mm",
    "Floor full body - light colour 60X120": "floor_1200x600",
    "Floor full body - Dark colour 60X120": "floor_1200x600",

    "Skirting GVT Tile 60 X60, 60x120": "tile_skirting",
    "Skirting GVT Tile 30 X60": "tile_skirting",
    "Skirting Ceramic 60X 30": "tile_skirting",
    "Skirting Ceramic 30X 30": "tile_skirting",
    "Skirting full body - 120X60": "tile_skirting",
    "Skirting full body - 60X60": "tile_skirting",
    "Skirting full body- Digital - 120X60": "tile_skirting_20mm",
    "Skirting full body- Digital - 60X60": "tile_skirting",
    "Skirting Full body Tile 120X20": "tile_skirting",
    "Skirting Full body Tile 60 X60 - 20 mm": "tile_skirting_20mm",
    "Skirting full body - light colour 60X120": "tile_skirting",
    "Skirting full body - Dark colour 60X120": "tile_skirting",
    "Skirting SS trim": "tile_skirting",

    "Wall Full body Digital 60 X120": "wall_1200x600",
    "Wall full body- Digital - 60X60": "wall_600x600",
    "Wall Tile ceramic 30 X60": "wall_600x300",

    "Staircase Tile Tread- Tiles- full body": "staircase_step",
    "Staircase Tiles Riser- full body": "staircase_step",
    "Staircase Tile Landing- full body": "staircase_step",
    "Staircase Tile skirting - full body": "staircase_skirting",

    "Wall Punning - DXB Material": "wall_punning",
    "RG Gypsum False ceiling": "gypsum_ceiling",
    "RG Gypsum False ceiling with shadow Gap": "gypsum_ceiling",
    "RG Gypsum False ceiling with corniche": "gypsum_ceiling",
    "MR Gypsum False ceiling": "gypsum_ceiling",
    "MR Gypsum False ceiling with shadow gap": "gypsum_ceiling",
    "Dry Wall Partition - RG": "dry_wall_partition",
    "Dry Wall Partition - FR": "dry_wall_partition",
    "Dry Wall Partition - MR": "dry_wall_partition",
    "Dry Wall Partition - Cement Board": "dry_wall_partition",

    "Wall Paint- caprol": "wall_paint",
    "Wall Paint- Jotun": "wall_paint",
    "Ceiling Emulsion Paint - caprol": "ceiling_paint",
    "Ceiling Emulsion Paint - Jotun": "ceiling_paint",
    "Decorative paint- makhmaliya": "decorative_paint",
    "Decorative paint - cemnet finish": "decorative_paint",
    "Exterior Paint - capa grain": "exterior_paint",

    "IPS flooring 30 mm": "ips_30mm",
    "IPS flooring 50 mm": "ips_50mm",
    "Plaster": "plaster",
    "water proofing wet areas - liquid applied": "waterproofing_2coat",
}

# product_name -> (unit_price_usd, wastage_pct, cmbl_pct, oh_pct) from the Estimate Form.
# markup_pct stored on the BOM line = cmbl_pct + oh_pct.
PRODUCT_MATERIAL_MAP = {
    "Floor GVT Tile 60 X120": (13.5, 0.1, 0.15, 0.1),
    "Floor GVT Tile 60 X60": (13.5, 0.1, 0.15, 0.1),
    "Floor GVT Tile 60 X30": (13.5, 0.1, 0.15, 0.1),
    "Skirting GVT Tile 60 X60, 60x120": (1.345, 0.1, 0.2, 0.3),
    "Skirting GVT Tile 30 X60": (1.9666666666666668, 0.1, 0.2, 0.3),
    "Floor Ceramic Tile 60 X30": (4.35, 0.1, 0.15, 0.1),
    "Skirting Ceramic 60X 30": (1.45, 0.1, 0.2, 0.3),
    "Floor Ceramic Tile 30 X30": (3.96, 0.1, 0.15, 0.1),
    "Skirting Ceramic 30X 30": (1.32, 0.1, 0.2, 0.3),
    "Floor full body - 120X60": (7.85, 0.1, 0.15, 0.1),
    "Floor full body - 60X60": (6.85, 0.1, 0.15, 0.1),
    "Skirting full body - 120X60": (1.9625, 0.1, 0.2, 0.3),
    "Skirting full body - 60X60": (1.7125, 0.1, 0.2, 0.3),
    "Floor full body- Digital - 120X60": (8.46, 0.1, 0.15, 0.1),
    "Floor full body- Digital - 60X60": (5.78, 0.1, 0.15, 0.1),
    "Skirting full body- Digital - 120X60": (8.46, 0.1, 0.2, 0.3),
    "Skirting full body- Digital - 60X60": (1.7125, 0.1, 0.2, 0.3),
    "Floor Full body Tile 120X20": (6.3, 0.1, 0.15, 0.1),
    "Skirting Full body Tile 120X20": (3.15, 0.1, 0.15, 0.1),
    "Floor Full Body Tile 60 X60 - 20 mm": (11.82, 0.1, 0.15, 0.1),
    "Skirting Full body Tile 60 X60 - 20 mm": (2.955, 0.1, 0.15, 0.1),
    "Floor full body - light colour 60X120": (5.47, 0.1, 0.15, 0.1),
    "Floor full body - Dark colour 60X120": (5.97, 0.1, 0.15, 0.1),
    "Skirting full body - light colour 60X120": (1.8233333333333333, 0.1, 0.15, 0.1),
    "Skirting full body - Dark colour 60X120": (1.99, 0.1, 0.15, 0.1),
    "Wall Full body Digital 60 X120": (8.46, 0.1, 0.15, 0.1),
    "Wall full body- Digital - 60X60": (5.78, 0.1, 0.15, 0.1),
    "Wall Tile ceramic 30 X60": (3.84, 0.1, 0.15, 0.1),
    "Staircase Tile Tread- Tiles- full body": (25.65, 0.1, 0.15, 0.1),
    "Staircase Tiles Riser- full body": (13.5, 0.1, 0.15, 0.1),
    "Staircase Tile Landing- full body": (22.95, 0.1, 0.15, 0.1),
    "Staircase Tile skirting - full body": (7.46, 0.1, 0.2, 0.1),
    "Skirting SS trim": (1.0, 0.1, 0.15, 0.1),

    "Wall Punning - DXB Material": (1.1866666666666668, 0.1, 0.1, 0.1),
    "RG Gypsum False ceiling": (9.233839876126126, 0.1, 0.15, 0.1),
    "RG Gypsum False ceiling with shadow Gap": (9.481356092342342, 0.1, 0.15, 0.1),
    "RG Gypsum False ceiling with corniche": (12.481356092342342, 0.1, 0.15, 0.1),
    "MR Gypsum False ceiling": (9.722560957207206, 0.1, 0.15, 0.1),
    "MR Gypsum False ceiling with shadow gap": (9.970077173423421, 0.1, 0.15, 0.1),
    "Dry Wall Partition - RG": (13.329679972972974, 0.1, 0.15, 0.1),
    "Dry Wall Partition - FR": (15.481517810810812, 0.1, 0.15, 0.1),
    "Dry Wall Partition - MR": (14.160031324324326, 0.1, 0.15, 0.1),
    "Dry Wall Partition - Cement Board": (20.819490783783785, 0.1, 0.15, 0.1),

    "Exterior Paint - capa grain": (2.2042009132420093, 0.1, 0.05, 0.1),
    "Wall Paint- caprol": (1.2988756756756756, 0.1, 0.1, 0.1),
    "Wall Paint- Jotun": (2.0662162162162163, 0.1, 0.1, 0.1),
    "Ceiling Emulsion Paint - caprol": (1.2988756756756756, 0.1, 0.15, 0.1),
    "Ceiling Emulsion Paint - Jotun": (2.0662162162162163, 0.1, 0.15, 0.1),
    "Decorative paint- makhmaliya": (3.4808219178082194, 0.1, 0.05, 0.1),
    "Decorative paint - cemnet finish": (21.783904109589038, 0.1, 0.05, 0.1),

    "Granite work - Kotra black - 18-20 mm": (20.0, 0.1, 0.15, 0.1),
    "Senter stone 12 mm": (35.0, 0.1, 0.05, 0.05),
    "Sentre stone 18 mm - threshold (400)": (80.0, 0.1, 0.05, 0.05),
    "Sentre stone 18 mm - threshold (250)": (80.0, 0.1, 0.05, 0.05),
    "Senter stone 6 mm": (23.0, 0.1, 0.05, 0.05),
    "Marble works- Material @$50/ sq mt - 18-20mm": (50.0, 0.1, 0.15, 0.1),
    "Marble works- Material @$75/ sq mt - 18-20mm": (75.0, 0.1, 0.15, 0.1),
    "Marble works- Material @$100/ sq mt - 18-20mm": (100.0, 0.1, 0.15, 0.1),
    "Marble works- Material @$50/ sq mt - 18-20mm - Skirting": (15.0, 0.1, 0.15, 0.1),
    "Marble works- Material @$75/ sq mt - 18-20mm - Skirting": (20.0, 0.1, 0.15, 0.1),
    "Marble works- Material @$100/ sq mt - 18-20mm - Skirting": (25.0, 0.1, 0.15, 0.1),
    "Pasco Cement tile - parking area": (3.753063725490196, 0.1, 0.0, 0.1),
    "Clay Tile": (4.65, 0.2, 0.05, 0.15),
    "Stone jali": (4.8, 0.1, 0.15, 0.1),

    "IPS flooring 30 mm": (3.032, 0.1, 0.15, 0.1),
    "IPS flooring 50 mm": (6.064, 0.1, 0.15, 0.1),
    "Plaster": (7.0, 0.1, 0.05, 0.1),
}

# Itemized BOM for the two families with clean, complete source data.
# (support_item_name, default_code, uom, qty_per_unit_before_wastage, wastage_pct, unit_price_usd)
PAINT_ITEMIZED_BOM = {
    "Wall Paint- caprol": [
        ("Primer (Caprol 1x Primer)", "PT-12", "Sqm", 1 / 130, 0.0, 14.756756756756756),
        ("Stucco (Caprol 2x Stucco)", "PT-11", "Sqm", 1 / 35, 0.0, 15.070270270270269),
        ("Paint PT-01 (Caprol Silk Finish, 2 coats)", "PT-01", "Sqm", 1 / 65, 0.0, 46.486486486486484),
    ],
    "Wall Paint- Jotun": [
        ("Primer (Jotun 1x Primer)", "PT-22", "Sqm", 1 / 130, 0.0, 20.27027027027027),
        ("Stucco (Jotun 2x Stucco)", "PT-21", "Sqm", 1 / 35, 0.0, 28.378378378378375),
        ("Paint PT-02 (Jotun Silk Finish, 2 coats)", "PT-02", "Sqm", 1 / 65, 0.0, 67.56756756756756),
    ],
}

GYPSUM_ITEMIZED_BOM = {
    # (support_item_name, default_code, uom, qty_per_sqm, wastage_pct, unit_price_usd)
    # qty_per_sqm already includes the source sheet's wastage% (10% boards/screws/
    # tape/compound/plywood, 5% channels/wall-angle) -- verified to reproduce the
    # RG Ceiling sheet's own Price Per SQM total (9.233839876126126) to the cent.
    "RG Gypsum False ceiling": [
        ("RG TE 12.5 x 1200 x 2400 mm, RG Gypsum Board", "GYP-01", "Pcs", 0.4532, 0.0, 4.056756756756757),
        ("GY MP 38 MC 050 12/12 3000mm, Main Channal", None, "Pcs", 0.8640625, 0.0, 1.4783783783783782),
        ("GY MP 23 FC 050 64/35 3000, Furring Channel", None, "Pcs", 0.8640625, 0.0, 2.1972972972972973),
        ("GY MP 25/25 WA 050 3000, Wall Angle", None, "Pcs", 0.978031, 0.0, 1.018918918918919),
        ("GM A HS 6 40, Hammer Screw", None, "Pcs", 0.0088, 0.0, 5.213513513513513),
        ("GM A WDG 6 40, Wedge anchor", None, "Pcs", 0.018104, 0.0, 10.945945945945946),
        ("GA WH SD M4.2 13 YZ, Wafer Head Self Drilling Screw", None, "Pcs", 0.011315, 0.0, 7.47027027027027),
        ("GA BH ST M3.5 25 YZ, Bugle Head Self Tapping Screw", None, "Pcs", 0.014483, 0.0, 5.472972972972973),
        ("GN JT F 50MM 90M ROLL, Fibre Joint Tape", None, "Roll", 0.044, 0.0, 2.532432432432432),
        ("GT JC-100 READYMIX JOINT COMPOUND 28KG", None, "Drum", 0.033, 0.0, 14.356756756756756),
        ("12mm Ply wood backing for curtain pelmet", None, "Pcs", 0.165, 0.0, 13.513513513513512),
    ],
    "MR Gypsum False ceiling": [
        ("MR TE 12.5 x 1200 x 2400 mm, MR Gypsum Board", "GYP-02", "Pcs", 0.4532, 0.0, 5.135135135135135),
        ("GY MP 38 MC 050 12/12 3000mm, Main Channal", None, "Pcs", 0.8640625, 0.0, 1.4783783783783782),
        ("GY MP 23 FC 050 64/35 3000, Furring Channel", None, "Pcs", 0.8640625, 0.0, 2.1972972972972973),
        ("GY MP 25/25 WA 050 3000, Wall Angle", None, "Pcs", 0.978031, 0.0, 1.018918918918919),
        ("GM A HS 6 40, Hammer Screw", None, "Pcs", 0.0088, 0.0, 5.213513513513513),
        ("GM A WDG 6 40, Wedge anchor", None, "Pcs", 0.018104, 0.0, 10.945945945945946),
        ("GA WH SD M4.2 13 YZ, Wafer Head Self Drilling Screw", None, "Pcs", 0.011315, 0.0, 7.47027027027027),
        ("GA BH ST M3.5 25 YZ, Bugle Head Self Tapping Screw", None, "Pcs", 0.014483, 0.0, 5.472972972972973),
        ("GN JT F 50MM 90M ROLL, Fibre Joint Tape", None, "Roll", 0.044, 0.0, 2.532432432432432),
        ("GT JC-100 READYMIX JOINT COMPOUND 28KG", None, "Drum", 0.033, 0.0, 14.356756756756756),
        ("12mm Ply wood backing for curtain pelmet", None, "Pcs", 0.165, 0.0, 13.513513513513512),
    ],
}

KSA_COUNTRY = dict(
    name="Saudi Arabia",
    code="KSA",
    is_active=True,
    is_template=False,
    site_currency_code="SAR",
    site_fx_rate_to_usd=3.75,
    inhouse_labor_currency_code="INR",
    inhouse_fx_rate_to_usd=94.0,
    local_labor_currency_code="SAR",
    local_fx_rate_to_usd=3.75,
    material_currency_code="USD",
    material_fx_rate_to_usd=1.0,
    working_days_per_month=26.0,
    wages_oh_rate_pct=0.15,
    food_per_month_local=900.0,
    accommodation_per_month_local=550.0,
    local_travel_per_month_local=90.0,
    air_ticket_per_year_local=1800.0,
    visa_per_year_local=13800.0,
    other_allowance_per_day_usd=0.5,
    notes="Seeded from the 'Khadar Villa' KSA sample workbooks (LBR Rate Calculation + INT_COST_SHEET).",
)
