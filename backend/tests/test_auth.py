"""Auth + project-isolation tests. Run with: pytest tests/ (from backend/)."""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Point at an isolated on-disk SQLite file *before* importing anything from
# `app` -- database.py reads DATABASE_URL at import time.
_TEST_DB = os.path.join(os.path.dirname(__file__), f"test_auth_{uuid.uuid4().hex}.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, engine
from app import models
from app.auth import hash_password


@pytest.fixture(scope="module")
def client():
    db = SessionLocal()
    country = models.Country(name="Testland", code="TST", is_active=True, is_template=False)
    db.add(country)
    db.flush()
    db.add(models.User(username="admin", password_hash=hash_password("adminpass"), is_admin=True))
    db.add(models.User(username="alice", password_hash=hash_password("alicepass"), is_admin=False))
    db.add(models.User(username="bob", password_hash=hash_password("bobpass"), is_admin=False))
    db.commit()
    db.close()

    with TestClient(app) as c:
        yield c

    engine.dispose()
    if os.path.exists(_TEST_DB):
        os.remove(_TEST_DB)


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_success(client):
    token = _login(client, "alice", "alicepass")
    r = client.get("/api/auth/me", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["username"] == "alice"


def test_login_wrong_password(client):
    r = client.post("/api/auth/login", json={"username": "alice", "password": "wrong"})
    assert r.status_code == 401


def test_login_unknown_user(client):
    r = client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
    assert r.status_code == 401


def test_missing_token_rejected(client):
    r = client.get("/api/countries")
    assert r.status_code == 401


def test_garbage_token_rejected(client):
    r = client.get("/api/countries", headers=_auth("not-a-real-token"))
    assert r.status_code == 401


def test_valid_token_allows_access(client):
    token = _login(client, "alice", "alicepass")
    r = client.get("/api/countries", headers=_auth(token))
    assert r.status_code == 200


def _new_project(client, token, name):
    country_id = client.get("/api/countries", headers=_auth(token)).json()[0]["id"]
    r = client.post("/api/projects", headers=_auth(token), json={
        "name": name, "country_id": country_id,
        "start_date": "2026-01-01", "end_date": "2026-06-01",
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_project_isolation_between_users(client):
    alice_token = _login(client, "alice", "alicepass")
    bob_token = _login(client, "bob", "bobpass")

    alice_project_id = _new_project(client, alice_token, "Alice's Project")
    bob_project_id = _new_project(client, bob_token, "Bob's Project")

    alice_list = client.get("/api/projects", headers=_auth(alice_token)).json()
    assert [p["name"] for p in alice_list] == ["Alice's Project"]

    bob_list = client.get("/api/projects", headers=_auth(bob_token)).json()
    assert [p["name"] for p in bob_list] == ["Bob's Project"]

    # Bob can't see or touch Alice's project by id.
    assert client.get(f"/api/projects/{alice_project_id}", headers=_auth(bob_token)).status_code == 404
    assert client.delete(f"/api/projects/{alice_project_id}", headers=_auth(bob_token)).status_code == 404
    assert client.post(f"/api/projects/{alice_project_id}/locations", headers=_auth(bob_token),
                        json={"name": "Lobby"}).status_code == 404


def test_admin_sees_all_projects(client):
    admin_token = _login(client, "admin", "adminpass")
    names = {p["name"] for p in client.get("/api/projects", headers=_auth(admin_token)).json()}
    assert {"Alice's Project", "Bob's Project"}.issubset(names)


def test_non_admin_cannot_manage_users(client):
    alice_token = _login(client, "alice", "alicepass")
    assert client.get("/api/users", headers=_auth(alice_token)).status_code == 403
    assert client.post("/api/users", headers=_auth(alice_token),
                        json={"username": "eve", "password": "x"}).status_code == 403


def test_admin_can_create_user(client):
    admin_token = _login(client, "admin", "adminpass")
    r = client.post("/api/users", headers=_auth(admin_token), json={"username": "carol", "password": "carolpass"})
    assert r.status_code == 200, r.text
    assert r.json()["is_admin"] is False
    # New account can log in immediately.
    _login(client, "carol", "carolpass")


def test_admin_can_reset_password(client):
    admin_token = _login(client, "admin", "adminpass")
    dave_id = client.post("/api/users", headers=_auth(admin_token),
                           json={"username": "dave", "password": "oldpass"}).json()["id"]
    r = client.put(f"/api/users/{dave_id}/password", headers=_auth(admin_token), json={"new_password": "newpass"})
    assert r.status_code == 200, r.text
    _login(client, "dave", "newpass")
    assert client.post("/api/auth/login", json={"username": "dave", "password": "oldpass"}).status_code == 401


def test_non_admin_cannot_reset_password(client):
    alice_token = _login(client, "alice", "alicepass")
    admin_id = client.get("/api/auth/me", headers=_auth(alice_token)).json()["id"]
    r = client.put(f"/api/users/{admin_id}/password", headers=_auth(alice_token), json={"new_password": "x"})
    assert r.status_code == 403
