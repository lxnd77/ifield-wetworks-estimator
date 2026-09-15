import os
import re
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, joinedload

from . import models, schemas, service, auth, calc, project_types
from .database import Base, engine, get_db
from .export_excel import (
    build_sale_estimation_workbook, build_bom_workbook, build_product_import_workbooks, norm_code,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="I-Field Estimator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- auth
@app.post("/api/auth/login", response_model=schemas.TokenOut)
def login(payload: schemas.LoginIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if not user or not auth.verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "invalid username or password")
    return schemas.TokenOut(access_token=auth.create_access_token(user.id), user=user)


@app.get("/api/auth/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(auth.get_current_user)):
    return user


@app.get("/api/users", response_model=List[schemas.UserOut])
def list_users(db: Session = Depends(get_db), admin: models.User = Depends(auth.get_current_admin)):
    return db.query(models.User).order_by(models.User.username).all()


@app.post("/api/users", response_model=schemas.UserOut)
def create_user(payload: schemas.UserIn, db: Session = Depends(get_db), admin: models.User = Depends(auth.get_current_admin)):
    if db.query(models.User).filter(models.User.username == payload.username).first():
        raise HTTPException(400, f"username {payload.username} already exists")
    u = models.User(username=payload.username, password_hash=auth.hash_password(payload.password), is_admin=payload.is_admin)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@app.put("/api/users/{user_id}/password", response_model=schemas.UserOut)
def reset_user_password(user_id: int, payload: schemas.PasswordResetIn, db: Session = Depends(get_db), admin: models.User = Depends(auth.get_current_admin)):
    u = db.query(models.User).get(user_id)
    if not u:
        raise HTTPException(404, "user not found")
    u.password_hash = auth.hash_password(payload.new_password)
    db.commit()
    db.refresh(u)
    return u


# ---------------------------------------------------------------- products
@app.get("/api/products", response_model=List[schemas.ProductOut])
def list_products(category: Optional[str] = None, product_type: Optional[str] = None,
                  db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    q = db.query(models.Product).options(
        joinedload(models.Product.purchasing_company),
        joinedload(models.Product.default_vendor),
    ).filter(models.Product.active == True)
    if category:
        q = q.filter(models.Product.category == category)
    if product_type:
        q = q.filter(models.Product.product_type == product_type)
    return q.order_by(models.Product.category, models.Product.name).all()


@app.get("/api/products/{product_id}", response_model=schemas.ProductDetailOut)
def get_product(product_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    p = db.query(models.Product).options(
        joinedload(models.Product.bom_lines).joinedload(models.BomLine.support_item),
        joinedload(models.Product.coverage_rate),
        joinedload(models.Product.purchasing_company),
        joinedload(models.Product.default_vendor),
    ).get(product_id)
    if not p:
        raise HTTPException(404, "product not found")
    return p


@app.post("/api/products", response_model=schemas.ProductOut)
def create_product(payload: schemas.ProductIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if not project_types.is_valid(payload.product_type):
        raise HTTPException(422, f"unknown product_type {payload.product_type!r}")
    # Furniture products carry no catalog-level recipe or coverage rate (the
    # BOM is entered per estimate line), so nothing needs setting up.
    needs_setup = project_types.labor_applies(payload.product_type)
    p = models.Product(**payload.model_dump(), needs_setup=needs_setup)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@app.put("/api/products/{product_id}", response_model=schemas.ProductOut)
def update_product(product_id: int, payload: schemas.ProductIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    p = db.query(models.Product).get(product_id)
    if not p:
        raise HTTPException(404, "product not found")
    if not project_types.is_valid(payload.product_type):
        raise HTTPException(422, f"unknown product_type {payload.product_type!r}")
    for k, v in payload.model_dump().items():
        setattr(p, k, v)
    _refresh_needs_setup(db, p)
    db.commit()
    db.refresh(p)
    return p


@app.put("/api/products/{product_id}/coverage-rate", response_model=schemas.CoverageRateOut)
def set_coverage_rate(product_id: int, payload: schemas.CoverageRateIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    p = db.query(models.Product).get(product_id)
    if not p:
        raise HTTPException(404, "product not found")
    if p.coverage_rate:
        for k, v in payload.model_dump().items():
            setattr(p.coverage_rate, k, v)
        cr = p.coverage_rate
    else:
        cr = models.CoverageRate(product_id=product_id, **payload.model_dump())
        db.add(cr)
    _refresh_needs_setup(db, p)
    db.commit()
    db.refresh(cr)
    return cr


@app.post("/api/products/{product_id}/bom-lines", response_model=schemas.BomLineOut)
def add_bom_line(product_id: int, payload: schemas.BomLineIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    p = db.query(models.Product).get(product_id)
    if not p:
        raise HTTPException(404, "product not found")
    support_item_id = payload.support_item_id
    if not support_item_id:
        if not payload.new_support_item_name:
            raise HTTPException(400, "support_item_id or new_support_item_name required")
        si = models.SupportItem(
            name=payload.new_support_item_name,
            uom=payload.new_support_item_uom or "Pcs",
            default_code=payload.new_support_item_default_code,
        )
        db.add(si)
        db.flush()
        support_item_id = si.id
    line = models.BomLine(
        product_id=product_id, support_item_id=support_item_id,
        qty_per_unit=payload.qty_per_unit, wastage_pct=payload.wastage_pct,
        role=payload.role, sort_order=payload.sort_order,
    )
    db.add(line)
    _refresh_needs_setup(db, p)
    db.commit()
    db.refresh(line)
    return line


@app.put("/api/bom-lines/{bom_line_id}", response_model=schemas.BomLineOut)
def update_bom_line(bom_line_id: int, payload: schemas.BomLineIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    line = db.query(models.BomLine).get(bom_line_id)
    if not line:
        raise HTTPException(404, "bom line not found")
    if payload.support_item_id:
        line.support_item_id = payload.support_item_id
    line.qty_per_unit = payload.qty_per_unit
    line.wastage_pct = payload.wastage_pct
    line.role = payload.role
    line.sort_order = payload.sort_order
    db.commit()
    db.refresh(line)
    return line


@app.delete("/api/bom-lines/{bom_line_id}")
def delete_bom_line(bom_line_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    line = db.query(models.BomLine).get(bom_line_id)
    if not line:
        raise HTTPException(404, "bom line not found")
    product = line.product
    db.delete(line)
    _refresh_needs_setup(db, product)
    db.commit()
    return {"ok": True}


def _refresh_needs_setup(db: Session, product: models.Product):
    db.flush()
    if not project_types.labor_applies(product.product_type):
        # Furniture products have no catalog recipe or coverage rate -- the
        # BOM is supplied per estimate line -- so they are always ready.
        product.needs_setup = False
        return
    has_bom = db.query(models.BomLine).filter(models.BomLine.product_id == product.id).count() > 0
    has_coverage = db.query(models.CoverageRate).filter(models.CoverageRate.product_id == product.id).count() > 0
    product.needs_setup = not (has_bom and has_coverage)


# ---------------------------------------------------------------- support items
@app.get("/api/support-items", response_model=List[schemas.SupportItemOut])
def list_support_items(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    return db.query(models.SupportItem).options(
        joinedload(models.SupportItem.default_vendor)
    ).order_by(models.SupportItem.name).all()


@app.post("/api/support-items", response_model=schemas.SupportItemOut)
def create_support_item(payload: schemas.SupportItemIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    si = models.SupportItem(**payload.model_dump())
    db.add(si)
    db.commit()
    db.refresh(si)
    return si


@app.put("/api/support-items/{support_item_id}", response_model=schemas.SupportItemOut)
def update_support_item(support_item_id: int, payload: schemas.SupportItemIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    si = db.query(models.SupportItem).get(support_item_id)
    if not si:
        raise HTTPException(404, "support item not found")
    for k, v in payload.model_dump().items():
        setattr(si, k, v)
    db.commit()
    db.refresh(si)
    return si


# ---------------------------------------------------------------- vendors / purchasing / selling companies
@app.get("/api/vendors", response_model=List[schemas.VendorOut])
def list_vendors(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    return db.query(models.Vendor).order_by(models.Vendor.name).all()


@app.post("/api/vendors", response_model=schemas.VendorOut)
def create_vendor(payload: schemas.VendorIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if db.query(models.Vendor).filter(models.Vendor.name == payload.name).first():
        raise HTTPException(400, f"vendor {payload.name} already exists")
    v = models.Vendor(**payload.model_dump())
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


@app.put("/api/vendors/{vendor_id}", response_model=schemas.VendorOut)
def update_vendor(vendor_id: int, payload: schemas.VendorIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    v = db.query(models.Vendor).get(vendor_id)
    if not v:
        raise HTTPException(404, "vendor not found")
    for k, val in payload.model_dump().items():
        setattr(v, k, val)
    db.commit()
    db.refresh(v)
    return v


@app.delete("/api/vendors/{vendor_id}")
def delete_vendor(vendor_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    v = db.query(models.Vendor).get(vendor_id)
    if not v:
        raise HTTPException(404, "vendor not found")
    db.delete(v)
    db.commit()
    return {"ok": True}


@app.get("/api/purchasing-companies", response_model=List[schemas.PurchasingCompanyOut])
def list_purchasing_companies(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    return db.query(models.PurchasingCompany).order_by(models.PurchasingCompany.name).all()


@app.post("/api/purchasing-companies", response_model=schemas.PurchasingCompanyOut)
def create_purchasing_company(payload: schemas.PurchasingCompanyIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if db.query(models.PurchasingCompany).filter(models.PurchasingCompany.name == payload.name).first():
        raise HTTPException(400, f"purchasing company {payload.name} already exists")
    pc = models.PurchasingCompany(**payload.model_dump())
    db.add(pc)
    db.commit()
    db.refresh(pc)
    return pc


@app.put("/api/purchasing-companies/{purchasing_company_id}", response_model=schemas.PurchasingCompanyOut)
def update_purchasing_company(purchasing_company_id: int, payload: schemas.PurchasingCompanyIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    pc = db.query(models.PurchasingCompany).get(purchasing_company_id)
    if not pc:
        raise HTTPException(404, "purchasing company not found")
    for k, v in payload.model_dump().items():
        setattr(pc, k, v)
    db.commit()
    db.refresh(pc)
    return pc


@app.delete("/api/purchasing-companies/{purchasing_company_id}")
def delete_purchasing_company(purchasing_company_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    pc = db.query(models.PurchasingCompany).get(purchasing_company_id)
    if not pc:
        raise HTTPException(404, "purchasing company not found")
    db.delete(pc)
    db.commit()
    return {"ok": True}


@app.get("/api/selling-companies", response_model=List[schemas.SellingCompanyOut])
def list_selling_companies(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    return db.query(models.SellingCompany).order_by(models.SellingCompany.name).all()


@app.post("/api/selling-companies", response_model=schemas.SellingCompanyOut)
def create_selling_company(payload: schemas.SellingCompanyIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if db.query(models.SellingCompany).filter(models.SellingCompany.name == payload.name).first():
        raise HTTPException(400, f"selling company {payload.name} already exists")
    sc = models.SellingCompany(**payload.model_dump())
    db.add(sc)
    db.commit()
    db.refresh(sc)
    return sc


@app.put("/api/selling-companies/{selling_company_id}", response_model=schemas.SellingCompanyOut)
def update_selling_company(selling_company_id: int, payload: schemas.SellingCompanyIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    sc = db.query(models.SellingCompany).get(selling_company_id)
    if not sc:
        raise HTTPException(404, "selling company not found")
    for k, v in payload.model_dump().items():
        setattr(sc, k, v)
    db.commit()
    db.refresh(sc)
    return sc


@app.delete("/api/selling-companies/{selling_company_id}")
def delete_selling_company(selling_company_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    sc = db.query(models.SellingCompany).get(selling_company_id)
    if not sc:
        raise HTTPException(404, "selling company not found")
    db.delete(sc)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- countries
@app.get("/api/countries", response_model=List[schemas.CountryOut])
def list_countries(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    return db.query(models.Country).order_by(models.Country.name).all()


@app.get("/api/countries/{country_id}", response_model=schemas.CountryOut)
def get_country(country_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    c = db.query(models.Country).get(country_id)
    if not c:
        raise HTTPException(404, "country not found")
    return c


# New countries start as a copy of this one -- its whole rate card and every
# material price -- for an admin to adjust.
SOURCE_COUNTRY_CODE = "KSA"
_COUNTRY_IDENTITY_FIELDS = {"name", "code", "notes"}


@app.post("/api/countries", response_model=schemas.CountryOut)
def create_country(payload: schemas.CountryIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if db.query(models.Country).filter(models.Country.code == payload.code).first():
        raise HTTPException(400, f"country code {payload.code} already exists")
    data = payload.model_dump()
    source = db.query(models.Country).options(joinedload(models.Country.material_prices)).filter(
        models.Country.code == SOURCE_COUNTRY_CODE).first()
    if source:
        # Rate-card fields the caller didn't explicitly send come from the
        # source country.
        for field in schemas.CountryIn.model_fields:
            if field not in _COUNTRY_IDENTITY_FIELDS and field not in payload.model_fields_set:
                data[field] = getattr(source, field)
    # Still a template: the copied figures are Saudi's until an admin saves
    # this country's own rate card.
    c = models.Country(**data, is_active=True, is_template=True)
    if source:
        c.material_prices = [
            models.CountryMaterialPrice(support_item_id=p.support_item_id, unit_price_local=p.unit_price_local)
            for p in source.material_prices
        ]
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@app.delete("/api/countries/{country_id}")
def delete_country(country_id: int, db: Session = Depends(get_db), admin: models.User = Depends(auth.get_current_admin)):
    c = db.query(models.Country).get(country_id)
    if not c:
        raise HTTPException(404, "country not found")
    if c.code == SOURCE_COUNTRY_CODE:
        raise HTTPException(400, f"{c.name} can't be deleted -- new countries are copied from it.")
    in_use = db.query(models.Project).filter(models.Project.country_id == country_id).count()
    if in_use:
        raise HTTPException(400, f"{c.name} is used by {in_use} project(s) -- delete or move those first.")
    db.delete(c)
    db.commit()
    return {"ok": True}


@app.put("/api/countries/{country_id}", response_model=schemas.CountryOut)
def update_country(country_id: int, payload: schemas.CountryIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    c = db.query(models.Country).get(country_id)
    if not c:
        raise HTTPException(404, "country not found")
    for k, v in payload.model_dump().items():
        setattr(c, k, v)
    c.is_template = False
    db.commit()
    db.refresh(c)
    return c


@app.get("/api/countries/{country_id}/material-prices", response_model=List[schemas.CountryMaterialPriceOut])
def list_material_prices(country_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    return db.query(models.CountryMaterialPrice).options(
        joinedload(models.CountryMaterialPrice.support_item)
    ).filter(models.CountryMaterialPrice.country_id == country_id).all()


@app.put("/api/countries/{country_id}/material-prices", response_model=schemas.CountryMaterialPriceOut)
def upsert_material_price(country_id: int, payload: schemas.CountryMaterialPriceIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    row = db.query(models.CountryMaterialPrice).filter(
        models.CountryMaterialPrice.country_id == country_id,
        models.CountryMaterialPrice.support_item_id == payload.support_item_id,
    ).first()
    if row:
        row.unit_price_local = payload.unit_price_local
    else:
        row = models.CountryMaterialPrice(country_id=country_id, **payload.model_dump())
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------- project types
@app.get("/api/project-types")
def list_project_types(user: models.User = Depends(auth.get_current_user)):
    """The three estimation modes and their rules -- the frontend builds its
    project-type picker and per-type column visibility from this."""
    return project_types.as_api_list()


# ---------------------------------------------------------------- projects
def _owned_project_query(db: Session, user: models.User):
    q = db.query(models.Project)
    if not user.is_admin:
        q = q.filter(models.Project.owner_id == user.id)
    return q


def _get_owned_project(db: Session, project_id: int, user: models.User, options=()) -> models.Project:
    q = db.query(models.Project).options(*options)
    p = q.get(project_id)
    if not p or (not user.is_admin and p.owner_id != user.id):
        raise HTTPException(404, "project not found")
    return p


@app.get("/api/projects", response_model=List[schemas.ProjectOut])
def list_projects(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    return _owned_project_query(db, user).options(
        joinedload(models.Project.country),
        joinedload(models.Project.selling_company),
        joinedload(models.Project.owner),
        joinedload(models.Project.locations),
    ).order_by(models.Project.created_at.desc()).all()


@app.get("/api/projects/{project_id}", response_model=schemas.ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    return _get_owned_project(db, project_id, user, options=[
        joinedload(models.Project.country),
        joinedload(models.Project.selling_company),
        joinedload(models.Project.owner),
        joinedload(models.Project.locations),
    ])


def _validate_project_payload(payload: schemas.ProjectIn):
    if not project_types.is_valid(payload.project_type):
        raise HTTPException(422, f"unknown project_type {payload.project_type!r}")
    # Every exported product name / reference starts with the project code.
    if not (payload.code or "").strip():
        raise HTTPException(422, "A project code is required (it prefixes every item code in the exports).")
    payload.code = payload.code.strip()
    if project_types.dates_required(payload.project_type) and not (payload.start_date and payload.end_date):
        raise HTTPException(422, "start_date and end_date are required for this project type")
    if payload.cny_per_usd is not None and payload.cny_per_usd <= 0:
        raise HTTPException(422, "cny_per_usd must be greater than 0")


@app.post("/api/projects", response_model=schemas.ProjectOut)
def create_project(payload: schemas.ProjectIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    _validate_project_payload(payload)
    data = payload.model_dump()
    # Furniture: snapshot the CNY->USD rate so a saved estimate doesn't move
    # when the app default changes later.
    if project_types.bom_per_line(payload.project_type) and not data.get("cny_per_usd"):
        data["cny_per_usd"] = project_types.DEFAULT_CNY_PER_USD
    p = models.Project(**data, owner_id=user.id)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@app.put("/api/projects/{project_id}", response_model=schemas.ProjectOut)
def update_project(project_id: int, payload: schemas.ProjectIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    p = _get_owned_project(db, project_id, user)
    _validate_project_payload(payload)
    for k, v in payload.model_dump().items():
        setattr(p, k, v)
    db.flush()
    _recompute_all_lines(db, p)
    db.commit()
    db.refresh(p)
    return p


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    p = _get_owned_project(db, project_id, user)
    db.delete(p)
    db.commit()
    return {"ok": True}


@app.post("/api/projects/{project_id}/locations", response_model=schemas.ProjectLocationOut)
def add_location(project_id: int, payload: schemas.ProjectLocationIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    _get_owned_project(db, project_id, user)
    loc = models.ProjectLocation(project_id=project_id, **payload.model_dump())
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc


@app.delete("/api/locations/{location_id}")
def delete_location(location_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    loc = db.query(models.ProjectLocation).options(joinedload(models.ProjectLocation.project)).get(location_id)
    if not loc:
        raise HTTPException(404, "location not found")
    if not user.is_admin and loc.project.owner_id != user.id:
        raise HTTPException(404, "location not found")
    db.delete(loc)
    db.commit()
    return {"ok": True}


def _recompute_all_lines(db: Session, project: models.Project) -> list:
    """Recompute every line of a project and return them (ordered by id).

    Everything recompute and the API response touch is loaded up front in a
    handful of queries, and the country price table is read once -- on
    Vercel + hosted Postgres every extra round trip is expensive, and this
    runs on every estimate read."""
    lines = db.query(models.EstimateLine).options(
        joinedload(models.EstimateLine.product).joinedload(models.Product.bom_lines)
        .joinedload(models.BomLine.support_item),
        joinedload(models.EstimateLine.product).joinedload(models.Product.coverage_rate),
        joinedload(models.EstimateLine.product).joinedload(models.Product.purchasing_company),
        joinedload(models.EstimateLine.product).joinedload(models.Product.default_vendor),
        joinedload(models.EstimateLine.components).joinedload(models.EstimateLineComponent.support_item)
        .joinedload(models.SupportItem.default_vendor),
    ).filter(models.EstimateLine.project_id == project.id).order_by(models.EstimateLine.id).all()
    price_lookup = None
    if lines and not project_types.bom_per_line(project.project_type):
        price_lookup = calc.price_lookup_factory(db, project.country_id)
    for line in lines:
        service.recompute_estimate_line(db, line, price_lookup=price_lookup)
    return lines


def _commit_if_changed(db: Session):
    """Reads recompute costs on the fly; only pay for a write transaction
    when a recomputed value actually moved."""
    if db.new or db.deleted or any(db.is_modified(o) for o in db.dirty):
        db.commit()


def _product_costs(db: Session, project: models.Project) -> dict:
    """Per-unit material/labor cost for every active wetworks product of the
    project's type (see project_product_costs). Furniture lines are priced
    per line on the server, so they need no product-level cost map."""
    if project_types.bom_per_line(project.project_type):
        return {}
    price_lookup = calc.price_lookup_factory(db, project.country_id)
    products = db.query(models.Product).options(
        joinedload(models.Product.bom_lines).joinedload(models.BomLine.support_item),
        joinedload(models.Product.coverage_rate),
    ).filter(
        models.Product.active == True,
        models.Product.product_type == project.project_type,
    ).all()
    result = {}
    for p in products:
        material = calc.compute_material_cost(p.bom_lines, price_lookup, p.consumable_pct, p.ohp_pct)
        labor_cost = calc.compute_labor_cost(
            p.coverage_rate, project.country, project.duration_months).cost_per_unit
        result[p.id] = schemas.ProductCostOut(
            material_cost_per_unit=material.cost_per_unit,
            labor_cost_per_unit=labor_cost,
            needs_setup=p.needs_setup,
            product_type=p.product_type,
        )
    return result


_WORKSPACE_PROJECT_OPTIONS = (
    joinedload(models.Project.country),
    joinedload(models.Project.selling_company),
    joinedload(models.Project.owner),
    joinedload(models.Project.locations),
)


def _workspace(db: Session, project: models.Project, include_catalog: bool) -> dict:
    lines = _recompute_all_lines(db, project)
    _commit_if_changed(db)
    out = {"project": project, "lines": lines, "product_costs": _product_costs(db, project)}
    if include_catalog:
        out["products"] = db.query(models.Product).options(
            joinedload(models.Product.purchasing_company),
            joinedload(models.Product.default_vendor),
        ).filter(
            models.Product.active == True,
            models.Product.product_type == project.project_type,
        ).order_by(models.Product.category, models.Product.name).all()
        out["selling_companies"] = db.query(models.SellingCompany).order_by(models.SellingCompany.name).all()
        out["support_items"] = db.query(models.SupportItem).options(
            joinedload(models.SupportItem.default_vendor)
        ).order_by(models.SupportItem.name).all()
    return out


# ---------------------------------------------------------------- estimate lines
@app.get("/api/projects/{project_id}/workspace", response_model=schemas.ProjectWorkspaceOut)
def project_workspace(project_id: int, catalog: bool = True, db: Session = Depends(get_db),
                      user: models.User = Depends(auth.get_current_user)):
    """The estimator screen's single load call: project, recomputed lines,
    the wetworks product cost map, and (unless catalog=false) the product /
    selling-company / support-item lists."""
    project = _get_owned_project(db, project_id, user, options=_WORKSPACE_PROJECT_OPTIONS)
    return _workspace(db, project, include_catalog=catalog)


@app.put("/api/projects/{project_id}/estimate", response_model=schemas.ProjectWorkspaceOut)
def save_estimate(project_id: int, payload: schemas.EstimateSaveIn, db: Session = Depends(get_db),
                  user: models.User = Depends(auth.get_current_user)):
    """Save the estimator's whole draft (locations + lines) in one
    transaction: it either all applies or nothing does, so a rejected line
    can never leave half a save behind (which used to re-create lines on the
    next Save)."""
    project = _get_owned_project(db, project_id, user, options=_WORKSPACE_PROJECT_OPTIONS + (
        joinedload(models.Project.estimate_lines),))
    existing_locs = {l.id: l for l in project.locations}
    existing_lines = {l.id: l for l in project.estimate_lines}

    kept_locs = []
    loc_by_key = {}
    for loc_in in payload.locations:
        if loc_in.id is not None:
            loc = existing_locs.get(loc_in.id)
            if loc is None:
                raise HTTPException(422, f"Location {loc_in.id} does not belong to this project.")
            loc.name, loc.sort_order = loc_in.name, loc_in.sort_order
        else:
            loc = models.ProjectLocation(name=loc_in.name, sort_order=loc_in.sort_order)
            project.locations.append(loc)
        if loc_in.key:
            loc_by_key[loc_in.key] = loc
        kept_locs.append(loc)
    for loc in list(project.locations):
        if all(loc is not k for k in kept_locs):
            project.locations.remove(loc)
            db.delete(loc)

    product_ids = {l.product_id for l in payload.lines}
    product_types = dict(db.query(models.Product.id, models.Product.product_type)
                         .filter(models.Product.id.in_(product_ids)).all()) if product_ids else {}

    kept_lines = []
    for line_in in payload.lines:
        if line_in.location_id is not None:
            loc = next((l for l in kept_locs if l.id == line_in.location_id), None)
        else:
            loc = loc_by_key.get(line_in.location_key)
        if loc is None:
            raise HTTPException(422, "A line item refers to a location that isn't in this save.")
        if product_types.get(line_in.product_id) != project.project_type:
            raise HTTPException(422, f"Product {line_in.product_id} can't be added to a "
                                     f"{project_types.label(project.project_type)} project.")
        fields = line_in.model_dump(exclude={"id", "location_id", "location_key"})
        if line_in.id is not None:
            line = existing_lines.get(line_in.id)
            if line is None:
                raise HTTPException(422, f"Line {line_in.id} does not belong to this project.")
            for k, v in fields.items():
                setattr(line, k, v)
        else:
            line = models.EstimateLine(**fields)
            project.estimate_lines.append(line)
        line.location = loc
        kept_lines.append(line)
    for line in list(project.estimate_lines):
        if all(line is not k for k in kept_lines):
            project.estimate_lines.remove(line)
            db.delete(line)

    db.flush()
    for line in kept_lines:
        _validate_furniture_line(line)
    out = _workspace(db, project, include_catalog=False)
    # The edits were flushed above, so _workspace's commit-if-changed can't
    # see them -- always commit a save.
    db.commit()
    return out


@app.get("/api/projects/{project_id}/estimate-lines", response_model=List[schemas.EstimateLineOut])
def list_estimate_lines(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    project = _get_owned_project(db, project_id, user)
    # Always recompute before returning so edits to country rates / BOM /
    # coverage made after the line was created are reflected immediately --
    # estimate lines are a live view over current master data, not a
    # point-in-time snapshot.
    lines = _recompute_all_lines(db, project)
    _commit_if_changed(db)
    return lines


@app.post("/api/projects/{project_id}/estimate-lines", response_model=schemas.EstimateLineOut)
def add_estimate_line(project_id: int, payload: schemas.EstimateLineIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    _get_owned_project(db, project_id, user)
    line = models.EstimateLine(project_id=project_id, **payload.model_dump())
    db.add(line)
    db.flush()
    db.refresh(line)
    service.recompute_estimate_line(db, line)
    db.commit()
    db.refresh(line)
    return line


def _get_owned_line(db: Session, line_id: int, user: models.User) -> models.EstimateLine:
    line = db.query(models.EstimateLine).options(joinedload(models.EstimateLine.project)).get(line_id)
    if not line or (not user.is_admin and line.project.owner_id != user.id):
        raise HTTPException(404, "estimate line not found")
    return line


def _validate_furniture_line(line: models.EstimateLine):
    """A furniture line that carries BOM components must have an item code.
    Reusing a code is allowed: an exported product is identified by project +
    product + code, so two lines of the same product with the same code are
    the same product -- the export checks they carry the same BOM (a line is
    usually still mid-edit when saved, so it isn't enforced here)."""
    if not project_types.bom_per_line(line.project.project_type) or not line.components:
        return
    if not (line.item_code or "").strip():
        raise HTTPException(422, "This furniture line has BOM components -- it needs an item code.")


def _all_project_components(db: Session, project_id: int):
    return db.query(models.EstimateLineComponent).join(models.EstimateLine).filter(
        models.EstimateLine.project_id == project_id).all()


def _validate_furniture_component(db: Session, comp: models.EstimateLineComponent):
    """Furniture BOM components need a price (CNY, > 0) and an item code. The
    same support item + code is the same exported product, so reusing that
    pair elsewhere in the project must keep the same price."""
    code = (comp.item_code or "").strip()
    if not code:
        raise HTTPException(422, "Each furniture BOM component needs an item code.")
    if not comp.unit_price_cny or comp.unit_price_cny <= 0:
        raise HTTPException(422, "Each furniture BOM component needs a price (CNY, greater than 0).")
    project_id = comp.estimate_line.project_id
    for other in _all_project_components(db, project_id):
        if (other.id != comp.id and other.support_item_id == comp.support_item_id
                and norm_code(other.item_code) == norm_code(code)
                and abs((other.unit_price_cny or 0.0) - comp.unit_price_cny) > 1e-9):
            name = other.support_item.name if other.support_item else "This item"
            raise HTTPException(422, f"'{name}' with item code '{code}' is already priced at "
                                     f"¥{other.unit_price_cny:g} elsewhere in this project -- use the same "
                                     f"price or a different item code.")


@app.put("/api/estimate-lines/{line_id}", response_model=schemas.EstimateLineOut)
def update_estimate_line(line_id: int, payload: schemas.EstimateLineIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    line = _get_owned_line(db, line_id, user)
    for k, v in payload.model_dump().items():
        setattr(line, k, v)
    db.flush()
    _validate_furniture_line(line)
    service.recompute_estimate_line(db, line)
    db.commit()
    db.refresh(line)
    return line


def _get_owned_component(db: Session, component_id: int, user: models.User) -> models.EstimateLineComponent:
    comp = db.query(models.EstimateLineComponent).options(
        joinedload(models.EstimateLineComponent.estimate_line)
        .joinedload(models.EstimateLine.project)
    ).get(component_id)
    if not comp or (not user.is_admin and comp.estimate_line.project.owner_id != user.id):
        raise HTTPException(404, "estimate line component not found")
    return comp


@app.post("/api/estimate-lines/{line_id}/components", response_model=schemas.EstimateLineComponentOut)
def add_estimate_line_component(line_id: int, payload: schemas.EstimateLineComponentIn,
                                db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    line = _get_owned_line(db, line_id, user)
    if not project_types.bom_per_line(line.project.project_type):
        raise HTTPException(400, "components are driven by the product recipe for this project type")
    if db.query(models.EstimateLineComponent).filter_by(
            estimate_line_id=line_id, support_item_id=payload.support_item_id).first():
        raise HTTPException(400, "that support item is already a component of this line")
    comp = models.EstimateLineComponent(
        support_item_id=payload.support_item_id,
        qty_per_unit=payload.qty_per_unit, unit_price_cny=payload.unit_price_cny,
        item_code=payload.item_code, qty=0.0, unit_cost=0.0, total_cost=0.0,
    )
    line.components.append(comp)
    db.flush()
    _validate_furniture_component(db, comp)
    service.recompute_estimate_line(db, line)
    db.commit()
    db.refresh(comp)
    return comp


@app.put("/api/estimate-line-components/{component_id}", response_model=schemas.EstimateLineComponentOut)
def update_estimate_line_component(component_id: int, payload: schemas.EstimateLineComponentIn,
                                   db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    comp = _get_owned_component(db, component_id, user)
    comp.support_item_id = payload.support_item_id
    comp.qty_per_unit = payload.qty_per_unit
    comp.unit_price_cny = payload.unit_price_cny
    comp.item_code = payload.item_code
    db.flush()
    _validate_furniture_component(db, comp)
    service.recompute_estimate_line(db, comp.estimate_line)
    db.commit()
    db.refresh(comp)
    return comp


@app.delete("/api/estimate-line-components/{component_id}")
def delete_estimate_line_component(component_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    comp = _get_owned_component(db, component_id, user)
    line = comp.estimate_line
    # Through the collection, so recompute below no longer prices it.
    line.components.remove(comp)
    db.flush()
    service.recompute_estimate_line(db, line)
    db.commit()
    return {"ok": True}


@app.delete("/api/estimate-lines/{line_id}")
def delete_estimate_line(line_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    line = _get_owned_line(db, line_id, user)
    db.delete(line)
    db.commit()
    return {"ok": True}


@app.put("/api/estimate-line-components/{component_id}/code", response_model=schemas.EstimateLineComponentOut)
def set_estimate_line_component_code(component_id: int, payload: schemas.EstimateLineComponentCodeIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    comp = db.query(models.EstimateLineComponent).options(
        joinedload(models.EstimateLineComponent.estimate_line).joinedload(models.EstimateLine.project)
    ).get(component_id)
    if not comp or (not user.is_admin and comp.estimate_line.project.owner_id != user.id):
        raise HTTPException(404, "estimate line component not found")
    comp.item_code = payload.item_code
    db.commit()
    db.refresh(comp)
    return comp


@app.get("/api/projects/{project_id}/summary")
def project_summary(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    project = _get_owned_project(db, project_id, user)
    _recompute_all_lines(db, project)
    _commit_if_changed(db)
    return service.project_summary(db, project)


@app.get("/api/projects/{project_id}/product-costs", response_model=dict[int, schemas.ProductCostOut])
def project_product_costs(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    """Per-unit material/labor cost for every active product, computed for
    this project's country + duration. Read-only -- lets the frontend price
    line items locally while editing (see ProjectDetail.jsx) without an API
    round trip per keystroke, and without duplicating the costing formulas
    in JS. Reuses calc.py exactly as recompute_estimate_line does. Also
    included in /workspace."""
    project = _get_owned_project(db, project_id, user)
    return _product_costs(db, project)


# ---------------------------------------------------------------- export
@app.get("/api/projects/{project_id}/export/sale-estimation")
def export_sale_estimation(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    project = _load_project_for_export(db, project_id, user)
    buf = build_sale_estimation_workbook(db, project)
    filename = f"Sale_Estimation_{project.name.replace(' ', '_')}.xlsx"
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/projects/{project_id}/export/bom")
def export_bom(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    project = _load_project_for_export(db, project_id, user)
    buf = build_bom_workbook(db, project)
    filename = f"BOM_{project.name.replace(' ', '_')}.xlsx"
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/projects/{project_id}/export/product-import")
def export_product_import(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    project = _load_project_for_export(db, project_id, user)
    workbooks = build_product_import_workbooks(db, project)

    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        used_names = set()
        for company_name, wb_buf in workbooks:
            base = re.sub(r'[\\/*?:\[\]]', "_", company_name).strip() or "Company"
            name = f"{base}.xlsx"
            n = 2
            while name in used_names:
                name = f"{base} ({n}).xlsx"
                n += 1
            used_names.add(name)
            zf.writestr(name, wb_buf.getvalue())
    zip_buf.seek(0)

    filename = f"Product_Import_{project.name.replace(' ', '_')}.zip"
    return StreamingResponse(
        zip_buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _load_project_for_export(db: Session, project_id: int, user: models.User) -> models.Project:
    project = _get_owned_project(db, project_id, user, options=[
        joinedload(models.Project.selling_company),
        joinedload(models.Project.estimate_lines).joinedload(models.EstimateLine.product)
        .joinedload(models.Product.purchasing_company),
        joinedload(models.Project.estimate_lines).joinedload(models.EstimateLine.product)
        .joinedload(models.Product.default_vendor),
        joinedload(models.Project.estimate_lines).joinedload(models.EstimateLine.product)
        .joinedload(models.Product.bom_lines),
        joinedload(models.Project.estimate_lines).joinedload(models.EstimateLine.location),
        joinedload(models.Project.estimate_lines).joinedload(models.EstimateLine.components).joinedload(
            models.EstimateLineComponent.support_item).joinedload(models.SupportItem.default_vendor),
    ])
    _recompute_all_lines(db, project)
    _commit_if_changed(db)
    _validate_project_for_export(project)
    return project


def _furniture_bom_signature(line: models.EstimateLine):
    """What must match for two lines to be the same exported product: the
    components (support item, code, qty, price) and the Factory Work cost."""
    comps = sorted(
        (c.support_item_id, norm_code(c.item_code), round(c.qty_per_unit or 0.0, 6), round(c.unit_price_cny or 0.0, 6))
        for c in line.components
    )
    return round(line.factory_work_cost_cny or 0.0, 6), tuple(comps)


def _validate_project_for_export(project: models.Project):
    """Every project needs a code (it prefixes every exported name and
    reference). Furniture lines that carry a BOM must be export-ready: an
    item code, a Factory Work cost, and every component with a price and an
    item code. An exported product is project + product + code, so lines
    sharing a product + code must carry the same BOM, and components sharing
    a support item + code must carry the same price."""
    if not (project.code or "").strip():
        raise HTTPException(422, "Cannot export yet: set a project code first "
                                 "(Edit project code) -- it prefixes every item code.")
    if not project_types.bom_per_line(project.project_type):
        return
    problems = []
    bom_by_key = {}
    price_by_comp_key = {}
    for line in project.estimate_lines:
        label = line.product.name if line.product else f"line {line.id}"
        code = (line.item_code or "").strip()
        key = (line.product_id, norm_code(code))
        signature = _furniture_bom_signature(line)
        if key in bom_by_key and bom_by_key[key] != signature:
            problems.append(f"'{label}' with item code '{code or '(blank)'}' has a different BOM on different "
                            f"lines -- the same product and code must have the same BOM, or use a different item code")
        bom_by_key.setdefault(key, signature)
        if not line.components:
            continue
        if not code:
            problems.append(f"'{label}' has BOM components but no item code")
        if not line.factory_work_cost_cny or line.factory_work_cost_cny <= 0:
            problems.append(f"'{label}' has BOM components but no Factory Work cost")
        for comp in line.components:
            si = comp.support_item.name if comp.support_item else "component"
            ccode = (comp.item_code or "").strip()
            if not ccode:
                problems.append(f"'{label}': component '{si}' has no item code")
            if not comp.unit_price_cny or comp.unit_price_cny <= 0:
                problems.append(f"'{label}': component '{si}' has no price")
                continue
            comp_key = (comp.support_item_id, norm_code(ccode))
            if comp_key in price_by_comp_key and abs(price_by_comp_key[comp_key] - comp.unit_price_cny) > 1e-9:
                problems.append(f"component '{si}' with item code '{ccode}' has different prices -- the same "
                                f"item and code must have the same price, or use a different item code")
            price_by_comp_key.setdefault(comp_key, comp.unit_price_cny)
    if problems:
        raise HTTPException(422, "Cannot export yet: " + "; ".join(sorted(set(problems))))


@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


# ---------------------------------------------------------------- static frontend
# On Vercel every request lands on this single serverless function regardless
# of path (see DEPLOY.md), so the built frontend is served from here too --
# registered last so it never shadows the /api/* routes above. Locally this
# is a no-op (dist/ doesn't exist unless you've run `npm run build`); the dev
# workflow of `npm run dev` on :5173 proxying to this API is unaffected.
_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if _frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        candidate = _frontend_dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_frontend_dist / "index.html")
