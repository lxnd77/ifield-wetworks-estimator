FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# SQLite lives here by default; mount a volume at /app/data and set
# DATABASE_URL=sqlite:////app/data/ifield_wetworks.db to persist it outside
# the container, or point DATABASE_URL at Postgres instead.
ENV DATABASE_URL=sqlite:////app/data/ifield_wetworks.db
RUN mkdir -p /app/data

EXPOSE 8000

# On first boot (empty DB) this seeds the KSA catalog; on subsequent boots
# the seed script is safe to skip -- see entrypoint.sh.
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
