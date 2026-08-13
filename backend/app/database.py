import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Works out of the box with SQLite for easy local/dev use, but swap DATABASE_URL
# to a Postgres DSN (e.g. postgresql+psycopg2://user:pass@host/db) for production
# self-hosting -- no code changes required elsewhere.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./ifield_wetworks.db")

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
