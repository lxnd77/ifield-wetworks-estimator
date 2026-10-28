"""Password hashing + JWT auth.

Deliberately stdlib-only for hashing (hashlib.pbkdf2_hmac) and PyJWT for
tokens (pure Python, no compiled extension) -- bcrypt/passlib and psycopg2
both burned real time on Vercel's build picking a Python version with no
prebuilt wheel for a compiled dependency (see DEPLOY.md). Nothing here
needs to compile.
"""
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session

from . import models
from .database import get_db, IS_PRODUCTION

JWT_SECRET = os.environ.get("JWT_SECRET", "")
if not JWT_SECRET:
    # Anyone who knows the fallback secret (it's in this public repo) can mint
    # an admin token, so a live deployment refuses to start without one.
    if IS_PRODUCTION:
        raise RuntimeError("JWT_SECRET must be set (e.g. `python -c \"import secrets; print(secrets.token_urlsafe(48))\"`)")
    JWT_SECRET = "dev-only-insecure-secret-change-me"
JWT_ALGORITHM = "HS256"
TOKEN_TTL_DAYS = 14

PBKDF2_ITERATIONS = 260_000

# Login lockout, tracked on the user row (not in memory: on Vercel each
# request may land on a different function instance). An admin password
# reset clears it.
MAX_FAILED_LOGINS = 5
LOCKOUT_DURATION = timedelta(minutes=15)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt_hex, digest_hex = password_hash.split("$", 1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(digest_hex)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return hmac.compare_digest(actual, expected)


# Checked against on an unknown username so it costs the same as a wrong
# password (no username probing by timing). Hash of a random, discarded string.
DUMMY_PASSWORD_HASH = (
    "5188dff11fbb9c09ccae2cf1f3b64428$6528395ca6f19ad27cbecba65802428f701d1fc89cd6a32d4bdf3be983193466"
)


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(days=TOKEN_TTL_DAYS)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> int:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except jwt.PyJWTError:
        raise HTTPException(401, "invalid or expired token")


def get_current_user(authorization: str = Header(default=None), db: Session = Depends(get_db)) -> models.User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "not authenticated")
    token = authorization.split(" ", 1)[1].strip()
    user_id = _decode_token(token)
    user = db.query(models.User).get(user_id)
    if not user:
        raise HTTPException(401, "not authenticated")
    return user


def get_current_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if not user.is_admin:
        raise HTTPException(403, "admin only")
    return user
