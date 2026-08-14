# Deploying to Vercel

The repo is set up to deploy as a **single Vercel project**: the React/Vite
frontend is built as a static site, and the FastAPI backend is deployed as a
Python serverless function under `/api`, both served from the same domain
(no CORS/env wiring needed on the frontend). This is wired up via three
files at the repo root:

- [`vercel.json`](vercel.json) -- `buildCommand`/`outputDirectory` build
  `frontend/` into `frontend/dist` and serve it as Vercel's native static
  site (files resolve at their real paths -- `/index.html`, `/assets/*`,
  `/favicon.svg`, etc. -- no custom routing needed for that half). A single
  rewrite, `/((?!api/).*) -> /index.html`, falls back to the SPA's
  `index.html` for client-side React Router paths (e.g. `/admin/products/35`)
  that aren't real files, while explicitly excluding `/api/*` so it can
  never shadow the API. `api/index.py` at the repo root is zero-config
  auto-detected by Vercel as a Python serverless function and every
  `/api/*` request routes to it automatically (Vercel treats a file
  exporting a full ASGI app as a "framework" and wildcards its whole
  subtree -- no explicit route needed, and trying to write one is what
  broke this the first two times: a custom rewrite/route destination like
  `/api/index` doesn't correspond to anything real, since the function's
  actual route is exactly `/api`).
- [`api/index.py`](api/index.py) -- the serverless entrypoint. Exports the
  FastAPI/ASGI `app` from `backend/app/main.py` unchanged.
- [`requirements.txt`](requirements.txt) -- Python deps for that function
  (Vercel's Python builder reads this from the project root). Trimmed down
  from `backend/requirements.txt`: no `uvicorn` (Vercel's own runtime serves
  the ASGI app directly) or `pytest` (doesn't run in prod), plus
  `psycopg2-binary` added for Postgres (see below).

## 1. You need a real database -- SQLite will not work here

Locally the app defaults to a SQLite file (`backend/ifield_wetworks.db`).
That's fine for `uvicorn --reload` on your machine, but **serverless
functions have a read-only filesystem (aside from `/tmp`, which is wiped
between invocations)**, so SQLite can't persist data on Vercel.

`backend/app/database.py` already reads `DATABASE_URL` from the environment
and swaps engines with zero code changes -- point it at a hosted Postgres
instance:

- **Vercel Postgres** (Storage tab in the Vercel dashboard) -- easiest,
  integrates env vars automatically.
- **Neon** or **Supabase** -- both have a generous free tier and work
  identically; just copy the connection string.

Either way, use the `postgresql+psycopg2://...` form (SQLAlchemy needs the
`+psycopg2` driver suffix; most providers give you a plain `postgresql://`
string -- just add `+psycopg2` after `postgresql`).

## 2. Create the Vercel project

1. Push this repo to GitHub (already done) and import it in Vercel
   ("Add New... -> Project").
2. **Root Directory**: leave as the repo root (not `frontend/`) -- `vercel.json`
   handles routing both the static build and the API from there.
3. Framework preset: "Other" (the `buildCommand`/`outputDirectory` in
   `vercel.json` override framework auto-detection).
4. Add the environment variable **`DATABASE_URL`** with your Postgres
   connection string (Project Settings -> Environment Variables). Apply it to
   Production (and Preview, if you want preview deploys to hit the same DB,
   or point Preview at a separate database).
5. Deploy.

## 3. Seed the production database (once)

`Base.metadata.create_all()` runs automatically on cold start (see
`backend/app/main.py`), so the tables get created -- but they'll be empty.
Run the existing seed script against the production database from your
machine (it's the same script `README.md`'s manual setup uses locally, just
pointed at Postgres instead of SQLite):

```bash
cd backend
DATABASE_URL="postgresql+psycopg2://user:pass@host/db" python3 seed.py
```

This is destructive (it wipes and rebuilds), so only run it once against
production, or deliberately when you want to reset it back to the seeded
KSA dataset.

## Notes / gotchas

- `psycopg2-binary` is only in the root `requirements.txt` (used by the
  Vercel function), not `backend/requirements.txt` (used for local dev) --
  local dev stays on SQLite with no Postgres driver needed unless you
  explicitly set `DATABASE_URL` locally too.
- CORS is already wide open (`allow_origins=["*"]` in `main.py`) from
  earlier local-dev work; since frontend and API now share one origin on
  Vercel it's not load-bearing, but there's no need to tighten it unless you
  want to.
- Cold starts: each invocation re-imports `backend/app/main.py`, which
  re-runs `Base.metadata.create_all()` -- idempotent and cheap, not a
  concern.
