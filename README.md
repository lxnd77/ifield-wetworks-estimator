# I-Field Estimator

A web app that turns I-Field's manual, per-country Excel estimation process into
a live, parameterized estimation tool: pick a project type and country, add line
items per location with a quantity, and the app computes cost and a
margin-applied sales value automatically -- then exports the estimate as three
Odoo-import-ready Excel files (`sale.estimation`, BOM, and product import) in the
exact column format of the sample files you provided.

**Every project has a type**, chosen at creation:

| Type | Costing | BOM quantities |
| --- | --- | --- |
| **Wetworks** | material **+ labor** (LBR Rate + INT\_COST sheets) | fixed per product (recipe) |
| **Loose Furniture** | material only | entered per estimate line + a "Factory Work" charge |
| **Fixed Furniture** | material only | same as Loose |

Loose and Fixed Furniture are identical in the engine -- they differ only by
label and the Odoo `estimation_type_id` on export. Formerly "I-Field Wetworks
Estimator"; the Wetworks costing is unchanged by the furniture extension.

## Quick start (Docker -- recommended for self-hosting)

```bash
docker compose up --build
```

- App: http://localhost
- API docs (Swagger): http://localhost:8000/docs

The first boot seeds the database with the full catalog -- 283 products (76
Wetworks, 166 Loose Furniture, 41 Fixed Furniture), 87 support items, 28
vendors -- and a **Saudi Arabia (KSA)** country profile. The Wetworks side is
priced from the sample workbooks; furniture support items still need per-country
prices (Admin -> Country). Subsequent restarts never re-seed or wipe data (see
`backend/entrypoint.sh`).

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

## Deploying to Vercel

See [DEPLOY.md](DEPLOY.md) -- the repo is pre-configured to deploy as a
single Vercel project (static frontend + FastAPI backend as a Python
serverless function under `/api`, same domain). You'll need a hosted
Postgres database (Vercel Postgres, Neon, Supabase...); SQLite doesn't work
in a serverless environment.

## How estimation works

An estimate is a **Project** (type + country + margin %, plus start/end dates
for Wetworks) containing one or more **Locations** (e.g. Lobby, King Rooms),
each with **Estimate Lines** (a product of the project's type + quantity).
Every line's cost is recomputed live on every read from current master data.

- **Wetworks:** `material_cost + labor_cost`, both below.
- **Furniture (loose / fixed):** `material_cost` only -- no labor, no coverage
  rate. See "Furniture BOM" below.

### Material cost

Every product has a **BOM** (bill of material): one or more Support Items,
each with a quantity needed per 1 unit of the product, a wastage %, and a
role (`primary` or `fixing`). Each Support Item has its own
**country-specific unit price**. The product itself carries **Consumable %**
(CMBL%) and **OHP %** (overhead %) -- historically a single combined "markup
%" in the source sheet, tracked here as two product-level fields matching how
the Estimate Form actually recorded them -- applied only to the product's
`primary` BOM line(s), never to `fixing` lines (screws, tape, etc.).

```
material_cost_per_unit = sum over BOM lines of:
    qty_per_unit * (1 + wastage_pct) * unit_price(support_item, country)
        * (1 + consumable_pct + ohp_pct if role == "primary" else 1)
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

### Furniture BOM (loose / fixed furniture)

Furniture products carry **no fixed recipe** -- component quantities vary by
project. On each furniture estimate line the estimator adds components from the
support-item catalog (filtered to `purchase_category` in **Fabric / Stone /
Metal / Accessories**) and types the `qty_per_unit` for that project. Recompute
only re-prices those rows against current country prices -- it never adds or
removes them.

Every furniture line that has components also carries a **Factory Work** charge
-- a per-project assembly/labour price, quantity always 1, entered on the line.
It's folded into `material_cost_per_unit` and appears in all three exports as a
`Factory Work for <product> <item_code>` component row. Such lines require a
**project-unique item code** (the standalone BOM export is keyed by it); the app
refuses to export until every furniture line with a BOM has both.

```
material_cost_per_unit = factory_work_cost
    + sum over components of:
        qty_per_unit * unit_price(support_item, country)
            * (1 + consumable_pct + ohp_pct if role == "primary" else 1)
```

### Labor cost (wetworks only)

Every Wetworks product also has a **Coverage Rate**: how much of the product a crew
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

**Wetworks:** 54 of 76 Product Master items are fully configured for KSA (Tile,
False Ceiling/Gypsum, Paint, Punning, Dry Wall Partition, IPS flooring,
Plaster). The rest (Stone/Marble, Vanity Counters, a few composite Flooring
items, 2 with broken source formulas) are seeded but flagged **"needs setup"**:
addable to an estimate, but $0 until an admin fills in a BOM and coverage rate.

**Furniture:** 166 Loose + 41 Fixed Furniture products, loaded from
`Product Master NEW.xlsx` via `backend/import_catalog.py`. They have no recipe
to configure (the BOM is per estimate line), so they're never "needs setup" --
but their 22 support items have **no KSA prices yet**, so a furniture line's
components read $0 until an admin sets per-country prices.

## Adding a country

Admin → Countries → **+ Add a country** creates an empty template (flagged
"needs data"). For **Wetworks** projects, open it to fill in currencies/FX
rates, working days/month, wages overhead %, salaries, and per-worker expenses
-- the same fields the KSA sample workbook has. **Material prices** (used by
every project type) are set per support item -- from a product's page
(Products → a product → **Material prices**, country selector), or in bulk via
`import_catalog.py --country <CODE>` if the client sends a priced sheet.
Wetworks BOM recipes and coverage rates are shared across countries by design;
a future country needing a different recipe is a schema change to discuss.

## Configuring a "needs setup" product (Wetworks)

Open **Products → (product)**. Set a **Coverage rate** (primary coverage/day,
optional secondary/grouting coverage/day, in-house/local crew counts), a
**Material markup** (Consumable %/OHP %, applied to the primary BOM line),
and add **BOM lines** (pick or create a Support Item, set qty/unit, wastage
%, role). Once a coverage rate and at least one BOM line exist, the product's
"needs setup" flag clears automatically and it prices normally in every
country (once that country has prices for its support items).

Furniture products have no per-product setup -- the Product Type editor is the
only extra field, and the BOM is built per estimate line.

## Exporting to Odoo

From a project page: **Export Sale Estimation**, **Export BOM**, and **Export
Product Import for Odoo** (a .zip, one workbook per participating company)
produce workbooks matching the exact header structure of the sample files you
provided. The Sale Estimation sheet's `estimation_type_id` is stamped from the
project type -- `Wetworks` / `Loose Furniture` / `Fixed Furniture` (the two
furniture strings are **provisional**, pending confirmation of the real values
in your Odoo). The labor-cost column is left blank for furniture projects.
Odoo-specific fields this app doesn't model are left blank -- Odoo's xlsx import
matches columns by header text, not position, so this is safe.

## Project layout

```
backend/
  app/
    models.py          SQLAlchemy schema
    project_types.py   the three estimation modes + their rules (source of truth)
    calc.py            costing engine (pure functions, unit-testable)
    service.py         recompute + totals, shared by API and export
    export_excel.py    the three Odoo-format exports
    seed_catalog.json  the catalog seed.py actually loads (live admin-cleaned snapshot)
    seed_products.py   original verbatim Wetworks Product Master (historical reference only)
    seed_ksa.py        KSA coverage/BOM/country data reverse-engineered from workbooks (historical)
    main.py            FastAPI routes
  seed.py              creates + seeds the DB
  import_catalog.py    loads a furniture "Product Master" xlsx into the catalog
  dump_seed_data.py    snapshots the live catalog back into seed_catalog.json
frontend/
  src/pages/           Projects, ProjectDetail (estimator), Admin (Products, Countries)
  src/projectTypes.js  frontend mirror of project_types.py
docker-compose.yml
```

## Known limitations / good next steps

- **Furniture support items have no KSA prices** -- a furniture line's
  components read $0 until an admin sets per-country prices. Send a priced
  sheet and `import_catalog.py --country KSA` loads them in bulk.
- The furniture `estimation_type_id` strings on the Sale Estimation export
  (`Loose Furniture` / `Fixed Furniture`) are **provisional** -- confirm the
  real values in your Odoo and change them in `backend/app/project_types.py`
  (marked `TODO`).
- Whether furniture door hardware (hinges, locks, handles) is best classified
  `Metal` vs `Accessories` is a judgement call the importer made -- reclassify
  from the support-items admin screen if needed.
- Only KSA is fully seeded; other countries start as empty templates.
- Wetworks: only Tile/Ceiling/Paint/Punning/DryWall/IPS/Plaster are fully
  automated; Stone, Counters, and a couple of composite Flooring items need BOM
  + coverage data. The Punning sheet's "freight cost" sub-formula wasn't
  cleanly recoverable and uses base material cost only.
- No authentication yet (single "Estimator" role, as requested for V1).
- No direct Odoo API push (Excel export only) -- `service.py` is structured so
  that's addable later without reworking the costing engine.
