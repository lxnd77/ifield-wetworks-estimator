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
import openpyxl
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, engine
from app import models, service, export_excel
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


# ---- furniture costing: material only, no labor (phase 02 / 05) ----

_line_seq = [0]


def _make_line(db, project_type, *, with_coverage=False, factory_work=None, item_code=None,
               consumable_pct=0.0, ohp_pct=0.0):
    """Insert a self-contained catalog + a one-line estimate; return the line.

    One BOM item consuming 2 per unit of a $10 support item -> $20/unit
    material before markup. Testland fx = 1.0, line qty = 3.

    Wetworks: the 2-per-unit qty is a fixed BomLine recipe.
    Furniture: it's a user-entered EstimateLineComponent (role 'primary'),
    plus the per-line `factory_work` charge.
    """
    country = db.query(models.Country).filter_by(code="TST").one()
    _line_seq[0] += 1
    suffix = f"{project_type}-{_line_seq[0]}"
    furniture = project_type != "wetworks"
    product = models.Product(
        name=f"P {suffix}", uom="Pcs", category="Test", product_type=project_type,
        needs_setup=False, consumable_pct=consumable_pct, ohp_pct=ohp_pct,
    )
    db.add(product)
    db.flush()
    si = models.SupportItem(name=f"SI {suffix}", uom="Pcs", purchase_category="Fabric")
    db.add(si)
    db.flush()
    db.add(models.CountryMaterialPrice(country_id=country.id, support_item_id=si.id,
                                       unit_price_local=10.0))
    if not furniture:
        db.add(models.BomLine(product_id=product.id, support_item_id=si.id,
                              qty_per_unit=2.0, wastage_pct=0.0, role="primary", sort_order=0))
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
    line = models.EstimateLine(project_id=project.id, location_id=loc.id, product_id=product.id,
                               qty=3.0, item_code=item_code, factory_work_cost=factory_work)
    db.add(line)
    db.flush()
    if furniture:
        db.add(models.EstimateLineComponent(
            estimate_line_id=line.id, support_item_id=si.id, qty_per_unit=2.0, role="primary",
            qty=0.0, unit_cost=0.0, total_cost=0.0))
        db.flush()
    return line


def test_furniture_line_prices_material_only():
    db = SessionLocal()
    try:
        # Even with a stray coverage rate, a furniture line carries no labor;
        # material = components ($20) + Factory Work ($5).
        line = _make_line(db, "loose_furniture", with_coverage=True, factory_work=5.0, item_code="F1")
        service.recompute_estimate_line(db, line)
        db.commit()
        assert line.material_cost_per_unit == 25.0
        assert line.labor_cost_per_unit == 0.0
        assert line.wages_cost_per_unit == 0.0
        assert line.labor_expenses_per_unit == 0.0
        comp = line.components[0]
        assert comp.qty == 6.0 and comp.unit_cost == 10.0 and comp.total_cost == 60.0
    finally:
        db.close()


def test_furniture_material_markup_applies_to_primary_component():
    db = SessionLocal()
    try:
        line = _make_line(db, "fixed_furniture", factory_work=0.0, item_code="F2",
                          consumable_pct=0.15, ohp_pct=0.10)
        service.recompute_estimate_line(db, line)
        db.commit()
        # 2 * 10 * 1.25 = 25 (primary row picks up the markup)
        assert line.material_cost_per_unit == 25.0
    finally:
        db.close()


def test_furniture_component_reprices_on_qty_and_price_change():
    db = SessionLocal()
    try:
        line = _make_line(db, "loose_furniture", factory_work=1.0, item_code="F3")
        service.recompute_estimate_line(db, line)
        db.commit()
        assert line.material_cost_per_unit == 21.0
        line.qty = 5.0
        service.recompute_estimate_line(db, line)
        db.commit()
        assert line.components[0].qty == 10.0          # 2 per unit * 5
        assert line.material_cost_per_unit == 21.0     # per-unit cost unchanged
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


# ---- exports: estimation_type_id + labor column per type (phase 03) ----

def _sheet_rows(buf):
    ws = openpyxl.load_workbook(buf).active
    rows = list(ws.iter_rows(values_only=True))
    return rows[0], rows[1:]


def _built_line(db, project_type, *, with_coverage=False, factory_work=7.0, item_code="X1"):
    line = _make_line(db, project_type, with_coverage=with_coverage,
                      factory_work=factory_work if project_type != "wetworks" else None,
                      item_code=item_code)
    service.recompute_estimate_line(db, line)
    db.commit()
    return line


def test_sale_estimation_furniture_type_blank_labor_and_factory_work_row():
    db = SessionLocal()
    try:
        line = _built_line(db, "loose_furniture", with_coverage=True)
        header, data = _sheet_rows(export_excel.build_sale_estimation_workbook(db, line.project))
        assert data[0][header.index("estimation_type_id")] == "Loose Furniture"
        labor_col = header.index("estimation_line_ids/labor_cost")
        assert all(r[labor_col] in (None, "") for r in data)
        comp_col = header.index(
            "estimation_line_ids/sale_estimation_component_product_line_ids/product_id")
        names = [r[comp_col] for r in data if r[comp_col]]
        assert f"Factory Work for {line.product.name} {line.item_code}" in names
    finally:
        db.close()


def test_sale_estimation_wetworks_type_and_labor_present():
    db = SessionLocal()
    try:
        line = _built_line(db, "wetworks", with_coverage=True)
        header, data = _sheet_rows(export_excel.build_sale_estimation_workbook(db, line.project))
        assert data[0][header.index("estimation_type_id")] == "Wetworks"
        labor_col = header.index("estimation_line_ids/labor_cost")
        labor_vals = [r[labor_col] for r in data if r[labor_col] not in (None, "")]
        assert labor_vals and abs(labor_vals[0] - 11.5) < 1e-6
    finally:
        db.close()


def test_bom_export_furniture_has_components_and_factory_work():
    db = SessionLocal()
    try:
        line = _built_line(db, "fixed_furniture")
        bom_header, bom_data = _sheet_rows(export_excel.build_bom_workbook(db, line.project))
        assert bom_data[0][bom_header.index("product")] == line.product.name
        fw_name = f"Factory Work for {line.product.name} {line.item_code}"
        comp_names = [r[bom_header.index("bom_line_ids/product_id")] for r in bom_data]
        assert line.components[0].support_item.name in comp_names
        assert fw_name in comp_names
        fw_qty = [r[bom_header.index("bom_line_ids/product_qty")] for r in bom_data
                  if r[bom_header.index("bom_line_ids/product_id")] == fw_name]
        assert fw_qty == [1]
    finally:
        db.close()


def test_product_import_furniture_manufacture_and_factory_work_buy_row():
    db = SessionLocal()
    try:
        line = _built_line(db, "loose_furniture")
        sc = models.SellingCompany(name="SC ftest")
        pc = models.PurchasingCompany(name="PC ftest")
        db.add_all([sc, pc])
        db.flush()
        line.project.selling_company_id = sc.id
        line.product.purchasing_company_id = pc.id
        db.commit()
        books = dict(export_excel.build_product_import_workbooks(db, line.project))
        assert "SC ftest" in books
        _, sc_rows = _sheet_rows(books["SC ftest"])
        by_name = {r[1]: r for r in sc_rows}
        assert by_name[line.product.name][4].startswith("Manufacture")     # route_ids
        fw = by_name[f"Factory Work for {line.product.name} {line.item_code}"]
        assert fw[4].startswith("Buy") and fw[7] == "Storable Product" and fw[8] in (None, "")
    finally:
        db.close()


def test_factory_work_name_carries_item_code_for_repeated_products():
    db = SessionLocal()
    try:
        # one product ("Sofa"), two line items with different item codes
        line = _make_line(db, "loose_furniture", factory_work=10.0, item_code="SOFA-A")
        service.recompute_estimate_line(db, line)
        db.flush()
        loc = line.location
        si = line.components[0].support_item
        l2 = models.EstimateLine(project_id=line.project_id, location_id=loc.id,
                                 product_id=line.product_id, qty=1.0,
                                 item_code="SOFA-B", factory_work_cost=10.0)
        db.add(l2)
        db.flush()
        db.add(models.EstimateLineComponent(estimate_line_id=l2.id, support_item_id=si.id,
                                            qty_per_unit=1.0, role="primary",
                                            qty=0.0, unit_cost=0.0, total_cost=0.0))
        db.flush()
        service.recompute_estimate_line(db, l2)
        db.commit()
        _, bom = _sheet_rows(export_excel.build_bom_workbook(db, line.project))
        names = {r[4] for r in bom if r[4]}
        assert f"Factory Work for {line.product.name} SOFA-A" in names
        assert f"Factory Work for {line.product.name} SOFA-B" in names
    finally:
        db.close()


def test_furniture_line_needs_unique_item_code(client):
    token = _login(client, "alice", "alicepass")
    h = _auth(token)
    cid = _country_id(client, token)
    # a furniture product with a priced support item
    prod = client.post("/api/products", headers=h, json={
        "name": "ICtest chair", "uom": "Pcs", "category": "Seating",
        "product_type": "loose_furniture"}).json()
    si = client.post("/api/products/{}/bom-lines".format(prod["id"]), headers=h, json={
        "new_support_item_name": "ICtest fabric", "new_support_item_uom": "m",
        "qty_per_unit": 1, "role": "primary"}).json()["support_item_id"]
    # (the bom-line above just creates the support item; furniture ignores the recipe)
    client.put(f"/api/countries/{cid}/material-prices", headers=h,
               json={"support_item_id": si, "unit_price_local": 20})
    pid = client.post("/api/projects", headers=h, json={
        "name": "IC proj", "country_id": cid, "project_type": "loose_furniture"}).json()["id"]
    loc = client.post(f"/api/projects/{pid}/locations", headers=h, json={"name": "L"}).json()["id"]
    l1 = client.post(f"/api/projects/{pid}/estimate-lines", headers=h,
                     json={"location_id": loc, "product_id": prod["id"], "qty": 2}).json()["id"]
    client.post(f"/api/estimate-lines/{l1}/components", headers=h,
                json={"support_item_id": si, "qty_per_unit": 3, "role": "primary"})
    # line now has a component but no item code -> save must fail
    r = client.put(f"/api/estimate-lines/{l1}", headers=h,
                   json={"location_id": loc, "product_id": prod["id"], "qty": 2})
    assert r.status_code == 422
    # give it a code -> ok
    r = client.put(f"/api/estimate-lines/{l1}", headers=h, json={
        "location_id": loc, "product_id": prod["id"], "qty": 2,
        "item_code": "CH-1", "factory_work_cost": 40})
    assert r.status_code == 200, r.text
    # a second line reusing the same code -> fail
    l2 = client.post(f"/api/projects/{pid}/estimate-lines", headers=h,
                     json={"location_id": loc, "product_id": prod["id"], "qty": 1}).json()["id"]
    client.post(f"/api/estimate-lines/{l2}/components", headers=h,
                json={"support_item_id": si, "qty_per_unit": 1, "role": "primary"})
    r = client.put(f"/api/estimate-lines/{l2}", headers=h, json={
        "location_id": loc, "product_id": prod["id"], "qty": 1, "item_code": "ch-1"})
    assert r.status_code == 422
    # export is blocked while l2 has no code / factory work
    r = client.get(f"/api/projects/{pid}/export/bom", headers=h)
    assert r.status_code == 422 and "Factory Work" in r.json()["detail"]
