"""Auth + project-isolation tests. Run with: pytest tests/ (from backend/)."""
import os
import sys
import uuid
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Point at an isolated on-disk SQLite file *before* importing anything from
# `app` -- database.py reads DATABASE_URL at import time.
_TEST_DB = os.path.join(os.path.dirname(__file__), f"test_auth_{uuid.uuid4().hex}.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, engine
from app import models, service
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


# ---- project types (furniture extension, phase 01) ----

def test_project_types_endpoint(client):
    token = _login(client, "alice", "alicepass")
    r = client.get("/api/project-types", headers=_auth(token))
    assert r.status_code == 200, r.text
    by_value = {t["value"]: t for t in r.json()}
    assert set(by_value) == {"wetworks", "loose_furniture", "fixed_furniture"}
    assert by_value["wetworks"]["labor_applies"] is True
    assert by_value["loose_furniture"]["labor_applies"] is False
    assert by_value["fixed_furniture"]["dates_required"] is False


def _country_id(client, token):
    return client.get("/api/countries", headers=_auth(token)).json()[0]["id"]


def test_furniture_project_allows_missing_dates(client):
    token = _login(client, "alice", "alicepass")
    r = client.post("/api/projects", headers=_auth(token), json={
        "name": "LF Project", "country_id": _country_id(client, token),
        "project_type": "loose_furniture",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["project_type"] == "loose_furniture"
    assert body["start_date"] is None and body["end_date"] is None


def test_wetworks_project_requires_dates(client):
    token = _login(client, "alice", "alicepass")
    r = client.post("/api/projects", headers=_auth(token), json={
        "name": "WW no dates", "country_id": _country_id(client, token),
    })
    assert r.status_code == 422


def test_unknown_project_type_rejected(client):
    token = _login(client, "alice", "alicepass")
    r = client.post("/api/projects", headers=_auth(token), json={
        "name": "bogus", "country_id": _country_id(client, token),
        "project_type": "nope", "start_date": "2026-01-01", "end_date": "2026-02-01",
    })
    assert r.status_code == 422


def test_products_filtered_by_type(client):
    token = _login(client, "alice", "alicepass")
    # test DB has no products at all, but the filter must still be honored
    # (and not error) -- an unknown type simply yields an empty list.
    r = client.get("/api/products?product_type=loose_furniture", headers=_auth(token))
    assert r.status_code == 200
    assert r.json() == []


# ---- furniture costing: material only, no labor (phase 02) ----

def _make_line(db, project_type, *, with_coverage):
    """Insert a self-contained catalog + a one-line estimate and return the
    (db, line). BOM: 2 units of a support item priced at $10 -> $20/unit
    material. Testland's fx rates all default to 1.0."""
    country = db.query(models.Country).filter_by(code="TST").one()
    suffix = f"{project_type}-{with_coverage}"
    product = models.Product(
        name=f"P {suffix}", uom="Pcs", category="Test", product_type=project_type,
        needs_setup=False, consumable_pct=0.0, ohp_pct=0.0,
    )
    db.add(product)
    db.flush()
    si = models.SupportItem(name=f"SI {suffix}", uom="Pcs")
    db.add(si)
    db.flush()
    db.add(models.BomLine(product_id=product.id, support_item_id=si.id,
                          qty_per_unit=2.0, wastage_pct=0.0, role="primary", sort_order=0))
    db.add(models.CountryMaterialPrice(country_id=country.id, support_item_id=si.id,
                                       unit_price_local=10.0))
    if with_coverage:
        db.add(models.CoverageRate(
            product_id=product.id, primary_coverage_per_day=10.0, secondary_coverage_per_day=0.0,
            inhouse_count=1, local_count=0, inhouse_salary_month_local=2600.0,
            local_salary_month_local=0.0))
    project = models.Project(
        name=f"Proj {suffix}", country_id=country.id, project_type=project_type,
        start_date=date(2026, 1, 1), end_date=date(2026, 7, 1), default_margin_pct=0.0)
    db.add(project)
    db.flush()
    loc = models.ProjectLocation(project_id=project.id, name="L")
    db.add(loc)
    db.flush()
    line = models.EstimateLine(project_id=project.id, location_id=loc.id,
                               product_id=product.id, qty=3.0)
    db.add(line)
    db.flush()
    return line


def test_furniture_line_prices_material_only():
    db = SessionLocal()
    try:
        # A furniture product even *with* a stray coverage rate must not
        # pick up any labor cost.
        line = _make_line(db, "loose_furniture", with_coverage=True)
        service.recompute_estimate_line(db, line)
        db.commit()
        assert line.material_cost_per_unit == 20.0
        assert line.labor_cost_per_unit == 0.0
        assert line.wages_cost_per_unit == 0.0
        assert line.labor_expenses_per_unit == 0.0
    finally:
        db.close()


def test_wetworks_line_still_has_labor():
    db = SessionLocal()
    try:
        line = _make_line(db, "wetworks", with_coverage=True)
        service.recompute_estimate_line(db, line)
        db.commit()
        assert line.material_cost_per_unit == 20.0
        # 2600/26/1 = $100/day crew; /10 coverage = $10; +15% Testland OH = $11.50
        assert abs(line.labor_cost_per_unit - 11.5) < 1e-6
    finally:
        db.close()
