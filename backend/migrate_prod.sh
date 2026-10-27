#!/usr/bin/env bash
# Run pending Alembic migrations against the database in backend/.env
# (production Neon), then print the resulting revision. See DEPLOY.md
# section 4 -- run this after any deploy that changes the schema.
#
# Usage (from the repo root or anywhere):  bash backend/migrate_prod.sh
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "backend/.env not found -- it must define DATABASE_URL" >&2
  exit 1
fi

# Read DATABASE_URL without sourcing .env (the URL's "&" breaks shell
# sourcing), strip a Windows CR, and pass it as plain postgresql:// so
# app/database.py drops the libpq-only params (sslmode, channel_binding)
# that pg8000 rejects and requests SSL itself.
url="$(grep '^DATABASE_URL=' .env | head -1 | cut -d= -f2- | tr -d '\r')"
if [ -z "$url" ]; then
  echo "DATABASE_URL is empty in backend/.env" >&2
  exit 1
fi
export DATABASE_URL="${url/#postgresql+pg8000:\/\//postgresql://}"

if [ -x venv/Scripts/python ]; then
  PY=venv/Scripts/python
else
  PY=venv/bin/python
fi

echo "Before:"
"$PY" -m alembic current
"$PY" -m alembic upgrade head
echo "After:"
"$PY" -m alembic current
