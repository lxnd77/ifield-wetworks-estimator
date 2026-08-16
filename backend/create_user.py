"""Create (or promote) a user account. Run against whichever DATABASE_URL
you want -- local SQLite by default, or point it at production Neon the
same way seed.py is run there.

Usage:
    python create_user.py --username rishabh --password '...' --admin
    python create_user.py --username shamnaz --password '...'
"""
import argparse
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal
from app import models
from app.auth import hash_password


def run(username: str, password: str, is_admin: bool):
    db = SessionLocal()
    try:
        existing = db.query(models.User).filter(models.User.username == username).first()
        if existing:
            existing.password_hash = hash_password(password)
            existing.is_admin = is_admin
            db.commit()
            print(f"Updated existing user '{username}' (admin={is_admin}).")
        else:
            db.add(models.User(username=username, password_hash=hash_password(password), is_admin=is_admin))
            db.commit()
            print(f"Created user '{username}' (admin={is_admin}).")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--admin", action="store_true")
    args = parser.parse_args()
    run(args.username, args.password, args.admin)
