# Deploying to Vercel

The repo deploys as a **single Vercel project, single Python function**:
FastAPI (`backend/app/main.py`) serves both the JSON API under `/api/*` and
the built React/Vite frontend for everything else, from the same process.

## Why it's structured this way

This took several iterations to get right, worth knowing before you touch
it again:

- Vercel auto-detected a **"FastAPI" Framework Preset** on this repo (it saw
  `requirements.txt` + `api/index.py`). That preset routes **every** request
  -- including static assets -- into the Python function, ignoring any
  static build output entirely. Fighting that (via `rewrites`, then the
  legacy `builds`/`routes` format) across several attempts never reliably
  got static files served.
- Switching the Framework Preset to "Other" fixed static serving, but
  changed the default Python version Vercel picks for the build from 3.12
  to 3.14 -- and neither `.python-version` nor `pyproject.toml`'s
  `requires-python` (both normally valid ways to pin it) were respected on
  this build path. `psycopg2-binary`, then `psycopg[binary]`, then even
  `pydantic-core`'s Rust extension (via PyO3, capped at Python 3.13) all
  failed to build under 3.14.
- The fix: stop fighting the "FastAPI preset routes everything to the
  function" behavior and **use it on purpose** -- mount the built frontend
  as static files inside `main.py` itself (see the bottom of that file), so
  the single function correctly handles both API and static/SPA routing no
  matter what Vercel's routing layer does around it. Framework Preset stays
  "FastAPI" (Python 3.12, no build failures), and `vercel.json` only needs
  to run the frontend build so `frontend/dist` exists for the function to
  read.
- **Driver choice**: `pg8000` (pure Python, no compiled extension) instead
  of `psycopg2`/`psycopg`, so a future Python version bump on Vercel's side
  can't reintroduce a missing-wheel build failure. `backend/app/database.py`
  auto-rewrites a bare `postgresql://` URL (what Neon/Supabase/etc. hand
  you) to use it and strips libpq-only query params (`sslmode`,
  `channel_binding`) it doesn't understand, requesting SSL via connect args
  instead. An explicit `postgresql+<driver>://` URL is left untouched, so
  self-hosting with a different driver still works.

## Files involved

- [`vercel.json`](vercel.json) -- just `buildCommand` (`cd frontend && npm
  install && npm run build`), so `frontend/dist` exists before the Python
  function is packaged.
- [`api/index.py`](api/index.py) -- serverless entrypoint, imports the
  FastAPI app from `backend/app/main.py` unchanged.
- [`requirements.txt`](requirements.txt) -- Python deps for that function
  (Vercel's builder reads this from the project root). No `uvicorn`
  (Vercel's own runtime serves the ASGI app) or `pytest` (doesn't run in
  prod).
- `backend/app/main.py` -- the bottom of the file mounts `frontend/dist` as
  static files and adds a catch-all route (registered *last*, so it never
  shadows `/api/*`) that serves a matching static file if one exists, or
  `index.html` as the SPA fallback for client-side React Router paths.

## 1. You need a real database -- SQLite will not work here

Locally the app defaults to a SQLite file (`backend/ifield_wetworks.db`).
That's fine for `uvicorn --reload` on your machine, but **serverless
functions have a read-only filesystem (aside from `/tmp`, which is wiped
between invocations)**, so SQLite can't persist data on Vercel.

`backend/app/database.py` reads `DATABASE_URL` from the environment --
point it at a hosted Postgres instance:

- **Vercel Postgres** (Storage tab in the Vercel dashboard) -- easiest,
  integrates env vars automatically.
- **Neon** or **Supabase** -- both have a generous free tier and work
  identically; just copy the connection string as-is (a bare
  `postgresql://...` string is fine, see above).

## 2. Create the Vercel project

1. Push this repo to GitHub (already done) and import it in Vercel
   ("Add New... -> Project").
2. **Root Directory**: repo root (not `frontend/`).
3. **Framework Preset**: "FastAPI" -- yes, on purpose (see above). Don't
   switch it to "Other" again without re-adding the static-serving code's
   equivalent, or you'll hit the Python-3.14 build failures documented above.
4. Add the environment variable **`DATABASE_URL`** with your Postgres
   connection string (Project Settings -> Environment Variables). Apply it
   to Production (and Preview, if you want preview deploys to hit the same
   DB, or point Preview at a separate database).
5. Deploy.

## 3. Seed the production database (once)

`Base.metadata.create_all()` runs automatically on cold start (see
`backend/app/main.py`), so the tables get created -- but they'll be empty.
Run the existing seed script against the production database from your
machine:

```bash
cd backend
DATABASE_URL="postgresql://user:pass@host/db" python3 seed.py
```

This is destructive (it wipes and rebuilds), so only run it once against
production, or deliberately when you want to reset it back to the seeded
KSA dataset.

## Notes / gotchas

- `pg8000` is only in the root `requirements.txt` (used by the Vercel
  function), not `backend/requirements.txt` (used for local dev) -- local
  dev stays on SQLite with no Postgres driver needed unless you explicitly
  set `DATABASE_URL` locally too.
- CORS is wide open (`allow_origins=["*"]` in `main.py`) from earlier
  local-dev work; since frontend and API share one origin on Vercel it's
  not load-bearing, but no need to tighten it unless you want to.
- Cold starts: each invocation re-imports `backend/app/main.py`, which
  re-runs `Base.metadata.create_all()` -- idempotent and cheap, not a
  concern.
- Locally, `frontend/dist` won't exist unless you've run `npm run build` --
  the static-serving block in `main.py` is skipped in that case (checked
  with `Path.is_dir()`), so the normal dev workflow (`npm run dev` on
  :5173 proxying `/api` to `:8000`) is unaffected.
