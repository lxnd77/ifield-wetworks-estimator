import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Works out of the box with SQLite for easy local/dev use, but swap DATABASE_URL
# to a Postgres DSN for production self-hosting -- no code changes required
# elsewhere. A bare "postgresql://..." string (what Neon/Supabase/etc. hand you)
# is normalized to the psycopg (v3) driver, since that's what's installed for
# the Vercel serverless function -- psycopg2's lack of prebuilt wheels for
# newer Python versions was breaking the build there.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./ifield_wetworks.db")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
