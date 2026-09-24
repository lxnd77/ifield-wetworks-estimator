# I-Field Estimator — project memory

Read this before making changes. Full user-facing docs are in `README.md`;
this file is oriented at whoever (human or Claude) picks up development next.

## What this is

A web app for I-Field (interior turnkey contracting) that replaces a manual,
per-country Excel estimation workflow with a live tool: pick a country, add
line items per project location with a quantity, and it computes cost +
margin automatically. Exports three Excel files matching Odoo's
`sale.estimation`, BOM, and product-import formats.

Every project has a **type**, chosen at creation (see `app/project_types.py`,
the single source of truth):

| type | costing | BOM | dates |
|---|---|---|---|
| `wetworks` | material **+ labor** | fixed product recipe (`BomLine`) | required |
| `loose_furniture` | material only | **per estimate line** + a Factory Work charge | optional |
| `fixed_furniture` | material only | same as loose | optional |

"Loose" vs "fixed" furniture are identical in the engine — they differ only
by label and the Odoo `estimation_type_id` on export. A line item can only
be added to a project of its matching `product_type`.

### Furniture BOM model (differs from wetworks)

Wetworks products carry a fixed recipe; `service.recompute_estimate_line`
explodes it into `EstimateLineComponent` rows on every read. Furniture
products carry **no recipe** — the estimator picks each support item
(`purchase_category` in Fabric / Stone / Metal / Accessories) and enters,
per project: `qty_per_unit`, `unit_price_cny` (the purchase price in Chinese
yuan — furniture is China-sourced), and a **project-unique `item_code`**.
Recompute for a furniture line only *re-prices* those rows — it never adds
or removes them (`service._recompute_furniture_line`):

```
component_usd  = qty_per_unit * unit_price_cny / project.cny_per_usd
factory_work$  = line.factory_work_cost_cny / project.cny_per_usd   (qty always 1)
material_cost_per_unit = (Σ component_usd + factory_work$) * (1 + product.ohp_pct)
```

Consumable % does **not** apply to furniture; OHP % loads on the line total
(components + Factory Work), not per component. `Project.cny_per_usd` is
snapshotted from `project_types.DEFAULT_CNY_PER_USD` at creation and editable
per project. Every furniture line with components must have an `item_code`
and a `factory_work_cost_cny`; every component must have a price and an
`item_code` — enforced on save and on export.

### Item codes (all project types)

An exported product = **project + product + item code**. `Project.code` is
required (`_validate_project_payload`; export refuses a legacy project without
one). Every export name is `qualified_name()` = `<name> <project code> <item
code>`, and every code column (`reference_code()`) is `<project code> <item
code>`, falling back to just the project code when the item code is blank.
Keys compare via `export_excel.norm_code` (trimmed, case-insensitive). Codes
may repeat: same product + code on two furniture lines must carry the same BOM
(checked at export, `_furniture_bom_signature` — not on save, since lines are
mid-edit then); same support item + code must carry the same CNY price
(checked on component save and export). Export id columns (`product_id/id`,
product-import `id`) are deliberately blank: catalog `odoo_id`s belong to the
shared catalog record, not the project-specific product.

> **History (furniture extension):** the app was "I-Field Wetworks
> Estimator"; `WetworksProduct`/`wetworks_products` were renamed to
> `Product`/`products` (alembic `f1a2b3c4d5e6`) and `seed_data_ksa.json` to
> `seed_catalog.json`. Local dev DB filenames (`ifield_wetworks.db`) and the
> repo directory name are deliberately unchanged (deploy-path coordination).
> "Wetworks" survives only as a project/product *type*.

Origin: the wetworks side was built from 5 client workbooks (Wetworks Product
Master, LBR Rate Calculation, INT_COST_SHEET_KSA, sample Sale Estimation
export, sample BOM Odoo export); its costing formulas in
`backend/app/calc.py` are reverse-engineered from those and verified in
`backend/tests/test_calc.py`. The furniture catalog was loaded from a later
`Product Master NEW.xlsx` via `backend/import_catalog.py`. If you're asked to
add a new cost driver or country, re-read the "How estimation works" section
of `README.md` first — it documents the derivation, not just the result.

## Stack

- Backend: FastAPI + SQLAlchemy (`backend/app/`), SQLite by default
  (`DATABASE_URL` env var swaps to Postgres with zero code changes).
- Frontend: React + Vite + Tailwind v4 (`frontend/src/`), no state library —
  plain `useState`/`useEffect` + axios, deliberately kept simple.
- Packaging: `docker-compose.yml` (backend + nginx-served frontend). Docker
  build was written but could NOT be test-built in the sandbox that authored
  it (no dockerd access there) — verify `docker compose up --build` works as
  the first sanity check in any environment that has Docker.

## Commands

```bash
# Backend
cd backend && python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 seed.py                 # rebuilds + seeds DB from scratch (destructive)
python3 -m pytest tests/ -v     # costing-engine regression tests
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm install
npm run dev                     # http://localhost:5173, proxies /api -> :8000
npm run build                   # production build to dist/

# Docker (untested in sandbox, verify first)
docker compose up --build       # app on :80, api docs on :8000/docs
```

## Where things live

- `backend/app/project_types.py` — the three estimation modes and their
  rules (`labor_applies`, `bom_per_line`, `dates_required`,
  `odoo_estimation_type`, `FURNITURE_BOM_CATEGORIES`). Imported by the API,
  the costing service, and the exports. The furniture
  `odoo_estimation_type` strings ("Loose Furniture" / "Fixed Furniture") are
  **provisional** — marked `TODO`, pending the real values in the client's
  Odoo. `frontend/src/projectTypes.js` is a hand-kept mirror.
- `backend/app/calc.py` — the costing engine (pure functions, no DB/ORM
  dependency, easiest place to unit test formula changes).
  `compute_material_cost` explodes a wetworks recipe;
  `compute_material_cost_from_components` sums user-entered furniture
  component quantities; both apply the product's consumable%/OHP% markup to
  `role == "primary"` lines only.
- `backend/app/service.py` — recompute + line/project totals, shared by API
  and export. `main._recompute_all_lines` is called on every read of estimate
  lines/summary/workspace/export, so estimate costs are always a live view
  over current master data. It eager-loads everything and reads the country
  price table once (production is Vercel + hosted Postgres, where every query
  is a slow round trip — keep it that way), and reads only commit when a value
  moved (`_commit_if_changed`).
- Estimator screen API: `GET /api/projects/{id}/workspace` is the single page
  load (project, recomputed lines, cost map, catalog lists; `?catalog=false`
  for refreshes), and `PUT /api/projects/{id}/estimate` saves the whole draft
  (locations + lines, new ones by client `key`) in **one transaction** —
  replaces the old per-row request loop that could half-save and then
  duplicate lines on retry. Sessions use `expire_on_commit=False`, so code
  that adds/removes child rows must go through the relationship collection
  (e.g. `line.components.append/remove`), not bare `db.add`/`db.delete`, or
  the response serializes stale collections.
- Countries: `POST /api/countries` copies the `KSA` country's whole rate card
  + every material price (`SOURCE_COUNTRY_CODE`); `DELETE` is admin-only and
  refuses KSA or a country used by a project. Branches on `project_types.bom_per_line`:
  `_recompute_furniture_line` re-prices user components + `factory_work_cost`
  and never rebuilds them; the wetworks path rebuilds from the recipe.
- `backend/app/models.py` — schema. Key relationships: `Product` has
  many `BomLine` (wetworks recipe) and one `CoverageRate` (wetworks labor);
  `Country` has many `CountryMaterialPrice` (per support item); `Project`
  has many `ProjectLocation` and `EstimateLine`; `EstimateLine` has many
  `EstimateLineComponent` (derived for wetworks, user-authored for furniture).
- `backend/app/export_excel.py` — the three Odoo-format exports. Column
  headers are hardcoded to match the sample files exactly. Furniture differs
  from wetworks only where it must: furniture `estimation_type_id`, blank
  labor column, `overhead_cost_percentage` = the product OHP (Odoo applies it
  line-level), per-line components instead of a recipe, the synthetic
  `Factory Work` component row (qty 1), and every furniture product /
  component name qualified as `<name> <project code> <item code>` via
  `qualified_name()` so repeated products / re-priced support items stay
  distinct Odoo records. Product import is one workbook per company: a BOM
  component goes on its `SupportItem.purchasing_company`'s workbook (falling
  back to the product's — wetworks recipe items carry none), so furniture
  lines, which are always Manufacture and whose products have no purchasing
  company, fan out to whichever companies buy their items. Furniture Factory
  Work always goes to `project_types.FACTORY_WORK_PURCHASING_COMPANY` (the
  China entity). Export refuses a furniture component whose support item
  has no purchasing company.
- `backend/import_catalog.py` — loads a flat Odoo `product.template`
  workbook (`name | uom_id | standard_price | categ_id | Vendor`), upserting
  by name: `FFE / *` → loose furniture products, `Joinery / *` → fixed
  furniture products, `Support*` → support items (`purchase_category`
  assigned). Idempotent. Run `python dump_seed_data.py` afterwards to fold
  the result into `seed_catalog.json`.
- `backend/app/seed_catalog.json` — the actual catalog `seed.py` loads:
  products, BOM lines, coverage rates, vendors, purchasing/selling
  companies, country rate card. It's a live snapshot (via
  `dump_seed_data.py`) of the catalog *as cleaned up through the admin UI*
  (BOM item names distinct from their product, vendor assignments,
  per-family purchasing companies) — **not** a hand-maintained source file.
  After any admin-side catalog cleanup, re-run `python dump_seed_data.py`
  against whichever DB you edited (local or, via `DATABASE_URL=... python
  dump_seed_data.py`, production) so the work is captured before anyone
  runs `seed.py` again and wipes it. `backend/app/seed_products.py` /
  `seed_ksa.py` are the *original* reverse-engineered/verbatim workbook
  data — kept for historical reference only, no longer read by `seed.py`.
- `frontend/src/pages/ProjectDetail.jsx` — the core estimator UI (locations,
  line items, live cost breakdown, export buttons).
- `frontend/src/pages/AdminProductDetail.jsx` / `AdminCountryDetail.jsx` —
  admin screens for configuring "needs setup" products and country rate
  cards / "add a country" flow.

## Current status

- Catalog: **283 products** (76 wetworks, 166 loose furniture, 41 fixed
  furniture) + 87 support items + 28 vendors, all in `seed_catalog.json`.
- 54 of 76 wetworks products fully configured for KSA (Tile, False
  Ceiling/Gypsum, Paint, Punning, Dry Wall, IPS, Plaster). The rest are
  `needs_setup=True` — addable but price $0 until an admin fills in BOM +
  coverage rate.
- Furniture products are `needs_setup=False` (no catalog recipe), but their
  support items have **no KSA prices yet** — a furniture line's components
  show $0 until an admin sets per-country prices (Admin → Country, or
  `import_catalog.py --country KSA` if a priced sheet arrives).
- Only KSA is seeded. "Add a country" creates an empty template
  (`is_template=True`).
- No auth beyond a single implicit "Estimator" role. Excel export only — no
  direct Odoo API push (deferred).
- QA: all three project types verified end to end (each with all three
  exports); alembic chain runs clean baseline↔head; pytest green
  (`backend/tests/`). See README's "Known limitations" for open wetworks
  items (Punning's freight sub-formula, remobilization rule, pack-rounding)
  and the provisional furniture `odoo_estimation_type` strings.

## Conventions / gotchas

- Don't pass an arrow function with an *implicit return* directly to
  `useEffect` (e.g. `useEffect(() => api.get(...).then(...), [])`) — the
  returned Promise gets treated by React as an effect cleanup function and
  throws (`"destroy is not a function"` in dev, minified in prod). Always use
  a block body (`() => { ... }`) for effect callbacks that don't intentionally
  return a cleanup function. This bit the first draft in `AdminCountries.jsx`
  / `AdminCountryDetail.jsx` — fixed, but watch for the pattern elsewhere.
- `seed.py` is destructive (`drop_all` then rebuild) — fine for dev, but the
  Docker entrypoint (`backend/entrypoint.sh`) only calls it when the DB is
  empty, specifically so container restarts never wipe real project data.
- Money is computed and stored in USD internally everywhere; `Country`
  records carry local-currency inputs + fx rates so admins can edit rate
  cards the way the source spreadsheets presented them.
- Wetworks `EstimateLineComponent` rows are a *derived snapshot* (rebuilt
  from the recipe every recompute); furniture ones are *user data* (only
  re-priced). Anything that touches recompute must keep that branch — a
  furniture line's components carry the estimator's `qty_per_unit` /
  `unit_price_cny` / `item_code` and must survive rate/qty changes.
- Furniture money is entered in **CNY** (`unit_price_cny`,
  `factory_work_cost_cny`) and converted with `Project.cny_per_usd`; the
  stored `EstimateLineComponent.unit_cost` / `total_cost` are the derived
  USD, and everything downstream (line totals, exports) is USD as before.
- `EstimateLine.factory_work_cost_cny` is folded into `material_cost_per_unit`
  (it's not a separate cost bucket), and appears in exports as a synthetic
  component, not a stored `EstimateLineComponent`.
- Adding a fourth project type, or splitting loose/fixed furniture behaviour:
  everything keys off `app/project_types.py` — add the config entry there and
  the mirror in `frontend/src/projectTypes.js`, then follow the `bom_per_line`
  / `labor_applies` branches.
