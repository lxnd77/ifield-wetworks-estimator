import os
from urllib.parse import urlsplit, urlunsplit
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Works out of the box with SQLite for easy local/dev use, but swap DATABASE_URL
# to a Postgres DSN for production self-hosting -- no code changes required
# elsewhere (set an explicit "postgresql+<driver>://" URL to use a different
# driver than the default below).
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./ifield_wetworks.db")

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif DATABASE_URL.startswith("postgresql://"):
    # A bare "postgresql://..." string (what Neon/Supabase/etc. hand you) is
    # normalized to pg8000 -- a pure-Python driver with no compiled extension,
    # so it can't hit a missing-wheel problem on whatever Python version the
    # host runs (psycopg2 and psycopg both broke Vercel's build when it picked
    # a brand-new CPython version neither had prebuilt wheels for yet). pg8000
    # doesn't understand libpq-style query params (sslmode, channel_binding),
    # so those are dropped here and SSL is requested via connect_args instead.
    parts = urlsplit(DATABASE_URL)
    DATABASE_URL = urlunsplit(("postgresql+pg8000", parts.netloc, parts.path, "", ""))
    connect_args = {"ssl_context": True}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
