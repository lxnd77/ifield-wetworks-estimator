# I-Field Wetworks Estimator — project memory

Read this before making changes. Full user-facing docs are in `README.md`;
this file is oriented at whoever (human or Claude) picks up development next.

## What this is

A web app for I-Field (interior turnkey contracting) that replaces a manual,
per-country Excel estimation workflow with a live tool: pick a country +
project duration, add Wetworks line items (tile, paint, gypsum ceiling, etc.)
per project location with a quantity, and it computes material cost + labor
cost + margin automatically. Exports two Excel files matching the exact
column format of Odoo's `sale.estimation` import and BOM import.

Origin: built from 5 source workbooks the client provided (Wetworks Product
Master, LBR Rate Calculation, INT_COST_SHEET_KSA, sample Sale Estimation
export, sample BOM Odoo export). The costing formulas in `backend/app/calc.py`
were reverse-engineered from those workbooks and are verified against them in
`backend/tests/test_calc.py`. If you're asked to add a new cost driver or
country, re-read the "How estimation works" section of `README.md` first —
it documents the derivation, not just the result.

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

- `backend/app/calc.py` — the costing engine (pure functions, no DB/ORM
  dependency, easiest place to unit test formula changes).
- `backend/app/service.py` — recompute + line/project totals, shared by API
  and export. `_recompute_all_lines` is called on every read of estimate
  lines/summary/export, so estimate costs are always a live view over current
  master data (country rates, BOM, coverage) — not a stale snapshot.
- `backend/app/models.py` — schema. Key relationships: `WetworksProduct` has
  many `BomLine` (recipe) and one `CoverageRate` (labor); `Country` has many
  `CountryMaterialPrice` (per support item); `Project` has many
  `ProjectLocation` and `EstimateLine`.
- `backend/app/export_excel.py` — the two Odoo-format exports. Column headers
  are hardcoded to match the sample files exactly; if the client's Odoo
  schema changes, update the header lists here first, then the row-building
  logic.
- `backend/app/seed_products.py` / `seed_ksa.py` — the actual extracted data
  from the client's workbooks. `seed_ksa.py`'s module docstring explains the
  design decisions (bundled vs. itemized BOM, why paint/gypsum ceiling got
  full itemization and others didn't).
- `frontend/src/pages/ProjectDetail.jsx` — the core estimator UI (locations,
  line items, live cost breakdown, export buttons).
- `frontend/src/pages/AdminProductDetail.jsx` / `AdminCountryDetail.jsx` —
  admin screens for configuring "needs setup" products and country rate
  cards / "add a country" flow.

## Current status

- 53 of 75 Wetworks products fully configured for KSA (Tile, False
  Ceiling/Gypsum, Paint, Punning, Dry Wall, IPS, Plaster). 22 flagged
  `needs_setup=True` (Stone, Counters, a couple of composite Flooring items,
  2 items with broken formulas in the source workbook) — addable to an
  estimate but price as $0 until an admin fills in BOM + coverage rate.
- Only KSA is seeded. "Add a country" creates an empty template
  (`is_template=True`) that needs its rate card + material prices filled in.
- No auth. Single implicit "Estimator" role, as scoped for V1.
- Excel export only — no direct Odoo API push (deliberately deferred).
- Full manual QA pass done in the authoring session: created a project via
  the actual UI (not just API), added locations/line items, verified live
  cost recompute, downloaded both export files, confirmed they match the
  sample column structure. See README's "Known limitations" for the open
  items (Punning's freight sub-formula, remobilization-for-long-projects
  rule, purchase-cost pack-rounding).

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
