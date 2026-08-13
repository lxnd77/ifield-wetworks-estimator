# I-Field Wetworks Estimator

A web app that turns I-Field's manual, per-country Excel estimation process (LBR
Rate Calculation + INT_COST_SHEET) into a live, parameterized estimation tool:
pick a country and project duration, add Wetworks line items per location with
a quantity, and the app computes material cost, labor cost and a margin-applied
sales value automatically -- then exports the estimate as two Odoo-import-ready
Excel files (`sale.estimation` and BOM) in the exact column format of the
sample files you provided.

## Quick start (Docker -- recommended for self-hosting)

```bash
docker compose up --build
```

- App: http://localhost
- API docs (Swagger): http://localhost:8000/docs

The first boot seeds the database with the full Wetworks Product Master (75
products) and a fully-configured **Saudi Arabia (KSA)** country profile, built
from the sample workbooks you supplied. Subsequent restarts never re-seed or
wipe data (see `backend/entrypoint.sh`).

By default data is stored in SQLite inside a Docker volume (`backend_data`).
For production, point `DATABASE_URL` (in `docker-compose.yml`) at a Postgres
instance instead -- no code changes needed, just install `psycopg2-binary` and
uncomment the `db` service.

## Manual setup (no Docker)

**Backend**
```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 seed.py            # creates + seeds the database (safe to re-run; wipes and rebuilds)
uvicorn app.main:app --reload --port 8000
```

**Frontend**
```bash
cd frontend
npm install
npm run dev                # http://localhost:5173, proxies /api to localhost:8000
# or: npm run build && npx vite preview   for a production-like local check
```

## How estimation works

An estimate is a **Project** (country + start/end date + margin %) containing
one or more **Locations** (e.g. Lobby, King Rooms), each with **Estimate Lines**
(a Wetworks product + quantity). Every line's cost is computed live from two
independent pieces, both parameterized by country and (for labor) project
duration:

### Material cost

Every product has a **BOM** (bill of material): one or more Support Items,
each with a quantity needed per 1 unit of the product, a wastage %, and an
optional markup % (historically "CMBL%" + overhead % in the source sheet, which
applied to the primary material only). Each Support Item has its own
**country-specific unit price**.

```
material_cost_per_unit = sum over BOM lines of:
    qty_per_unit * (1 + wastage_pct) * unit_price(support_item, country) * (1 + markup_pct)
```

Most products (Tile, Paint, False Ceiling, Punning, Dry Wall, IPS, Plaster) use
this exactly, reverse-engineered from and verified against the KSA sample
workbook's own "Material Cost/Unit" column to within floating-point rounding.
Wall Paint and RG/MR Gypsum Ceiling additionally carry a **fully itemized BOM**
(primer/stucco/paint; gypsum board/channels/screws/tape/compound) sourced from
the Paint and RG/MR Ceiling sheets, because the target BOM Odoo export format
expects that level of detail and the source data for those two families was
complete. Everything else uses a single bundled "primary material" BOM line
until an admin enriches it further (see "Configuring products" below).

**Note on quantities:** the BOM stores the *exact theoretical* consumption
(e.g. 1 can of paint per 65 sqm = 0.01538 cans/sqm), matching how the BOM Odoo
export sample expressed quantities. The legacy Estimate Form instead rounded
up to whole packs/bags when computing purchase cost, which read a few percent
higher for small-coverage items like paint. If your team wants purchase-cost
estimates to round up to whole packs, that's a straightforward addition to
`calc.py`.

### Labor cost

Every product also has a **Coverage Rate**: how much of the product a crew
produces per day (and, for tiling, a separate grouting coverage/day), plus
crew headcount (in-house / local split). Every country has a labor rate card:
salaries, working days/month, a wages overhead %, and per-worker expenses
(food, accommodation, local travel -- recurring monthly allowances; air ticket
and visa -- one-off annual mobilization costs).

```
wages_per_unit   = crew_day_cost / primary_coverage_per_day
                  + (avg_worker_day_cost / secondary_coverage_per_day)   [grouting, if any]
                  ... plus wages overhead %

expenses_per_unit = (food + accommodation + local_travel) [monthly, amortized over a working month]
                   + (air_ticket + visa) [annual, amortized over the ACTUAL PROJECT DURATION]
                   ... all allocated across the crew's daily output
```

This is the direct, generalized reverse-engineering of the LBR Rate
Calculation sheet's formulas -- verified to reproduce its "Total Rate/U/M"
column to within ~0.05% (the sheet itself rounds some intermediate $/day
figures before reuse; this engine computes from first principles instead of
compounding that rounding).

**Why duration matters (as requested):** air ticket and visa costs are
one-off per mobilization, so a *shorter* project recovers the same fixed cost
over less production, raising the per-unit labor cost -- try changing a
project's end date and re-opening it to see this in action. Food/accommodation
are recurring and don't change with duration. The current model assumes one
mobilization per worker per project; a "remobilize after N months" rule (for
very long projects) was intentionally left as a clean follow-on -- the
duration math is centralized in `backend/app/calc.py::compute_labor_cost`.

### Coverage of the product catalog

53 of the 75 Wetworks Product Master items are fully configured for KSA (Tile,
False Ceiling/Gypsum, Paint, Punning, Dry Wall Partition, IPS flooring,
Plaster) -- matching the categories the source workbooks covered. The
remaining 22 (Stone/Marble, Vanity Counters, a few composite Flooring items,
and 2 items with broken formulas in the source file) are seeded but flagged
**"needs setup"**: they can still be added to an estimate, but cost shows as
$0 until an admin fills in a BOM and coverage rate for them.

## Adding a country

Products → Countries → **+ Add a country** creates an empty rate-card
template (flagged "needs data" everywhere it appears). Open it to fill in:
currencies/FX rates, working days/month, wages overhead %, salaries, and the
per-worker expense figures -- the same fields the KSA sample workbook has, laid
out the same way. Material prices are set per support item from each
product's page (Products → a product → **Material prices**, with a country
selector). BOM recipes and coverage rates are shared across countries by
design (only prices/wages vary per the product decision); if a future country
genuinely needs a different recipe or coverage rate, that's a schema change
worth discussing rather than a workaround.

## Configuring a "needs setup" product

Open **Products → (product)**. Set a **Coverage rate** (primary coverage/day,
optional secondary/grouting coverage/day, in-house/local crew counts) and add
**BOM lines** (pick or create a Support Item, set qty/unit, wastage %, markup
%). Once both exist, the product's "needs setup" flag clears automatically and
it prices normally in every country (once that country has prices for its
support items).

## Exporting to Odoo

From a project page: **Export Sale Estimation (.xlsx)** and **Export BOM
(.xlsx)** produce workbooks matching the exact header structure of the sample
files you provided (`sale.estimation` one2many rows, and the BOM import
format). Each project location's line item becomes its own named "virtual
product" (`{product} in {location}`, mirroring the sample's `Paint in Lobby`
pattern) so per-location costing survives the import into Odoo. Odoo-specific
fields this app doesn't model (assigned_to/user, cost_center_type, dimension)
are left blank -- Odoo's xlsx import matches columns by header text, not
position, so this is safe; fill them in Odoo after import if your workflow
needs them.

## Project layout

```
backend/
  app/
    models.py        SQLAlchemy schema
    calc.py           costing engine (pure functions, unit-testable)
    service.py        recompute + totals, shared by API and export
    export_excel.py    the two Odoo-format exports
    seed_products.py   verbatim Wetworks Product Master catalog
    seed_ksa.py         KSA coverage/BOM/country data, reverse-engineered from the sample workbooks
    main.py            FastAPI routes
  seed.py              creates + seeds the DB
frontend/
  src/pages/            Projects, ProjectDetail (estimator), Admin (Products, Countries)
docker-compose.yml
```

## Known limitations / good next steps

- Only KSA is fully seeded; other countries start as empty templates (per your call).
- Only Tile/Ceiling/Paint/Punning/DryWall/IPS/Plaster are fully automated; Stone,
  Counters, and a couple of composite Flooring items need BOM + coverage data.
- The Punning sheet's "freight cost" sub-formula wasn't cleanly recoverable
  from the source file's visible columns; the punning support item price uses
  the base material cost only -- worth checking against the source once you can
  clarify that formula with whoever built the original sheet.
- No authentication yet (single "Estimator" role, as requested for V1) -- add
  an auth layer before exposing this beyond a trusted internal network.
- No direct Odoo API push (Excel export only, per your call) -- the data layer
  (`service.py`) is structured so that's a addable later without reworking the
  costing engine.
