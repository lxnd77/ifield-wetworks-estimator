#!/bin/sh
set -e

# Seed only on first boot (empty/uninitialized database) -- never wipes data
# on restart. To force a full reseed, delete the DB file (sqlite) or drop
# the schema (Postgres) and restart the container.
python3 - <<'PY'
import sys
sys.path.insert(0, ".")
from app.database import Base, engine, SessionLocal
from app import models

Base.metadata.create_all(bind=engine)
db = SessionLocal()
try:
    count = db.query(models.WetworksProduct).count()
finally:
    db.close()

if count == 0:
    print("Empty database detected -- running initial seed (KSA catalog)...")
    import subprocess
    subprocess.run(["python3", "seed.py"], check=True)
else:
    print(f"Database already has {count} products -- skipping seed.")
PY

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
