import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, joinedload

from . import models, schemas, service, auth, calc
from .database import Base, engine, get_db
from .export_excel import build_sale_estimation_workbook, build_bom_workbook

Base.metadata.create_all(bind=engine)

app = FastAPI(title="I-Field Wetworks Estimator")

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
def list_products(category: Optional[str] = None, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    q = db.query(models.WetworksProduct).filter(models.WetworksProduct.active == True)
    if category:
        q = q.filter(models.WetworksProduct.category == category)
    return q.order_by(models.WetworksProduct.category, models.WetworksProduct.name).all()


@app.get("/api/products/{product_id}", response_model=schemas.ProductDetailOut)
def get_product(product_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    p = db.query(models.WetworksProduct).options(
        joinedload(models.WetworksProduct.bom_lines).joinedload(models.BomLine.support_item),
        joinedload(models.WetworksProduct.coverage_rate),
    ).get(product_id)
    if not p:
        raise HTTPException(404, "product not found")
    return p


@app.post("/api/products", response_model=schemas.ProductOut)
def create_product(payload: schemas.ProductIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    p = models.WetworksProduct(**payload.model_dump(), needs_setup=True)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@app.put("/api/products/{product_id}", response_model=schemas.ProductOut)
def update_product(product_id: int, payload: schemas.ProductIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    p = db.query(models.WetworksProduct).get(product_id)
    if not p:
        raise HTTPException(404, "product not found")
    for k, v in payload.model_dump().items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p


@app.put("/api/products/{product_id}/coverage-rate", response_model=schemas.CoverageRateOut)
def set_coverage_rate(product_id: int, payload: schemas.CoverageRateIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    p = db.query(models.WetworksProduct).get(product_id)
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
    p = db.query(models.WetworksProduct).get(product_id)
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
        markup_pct=payload.markup_pct, role=payload.role, sort_order=payload.sort_order,
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
    line.markup_pct = payload.markup_pct
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


def _refresh_needs_setup(db: Session, product: models.WetworksProduct):
    db.flush()
    has_bom = db.query(models.BomLine).filter(models.BomLine.product_id == product.id).count() > 0
    has_coverage = db.query(models.CoverageRate).filter(models.CoverageRate.product_id == product.id).count() > 0
    product.needs_setup = not (has_bom and has_coverage)


# ---------------------------------------------------------------- support items
@app.get("/api/support-items", response_model=List[schemas.SupportItemOut])
def list_support_items(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    return db.query(models.SupportItem).order_by(models.SupportItem.name).all()


@app.post("/api/support-items", response_model=schemas.SupportItemOut)
def create_support_item(payload: schemas.SupportItemOut, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    si = models.SupportItem(name=payload.name, default_code=payload.default_code, uom=payload.uom)
    db.add(si)
    db.commit()
    db.refresh(si)
    return si


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


@app.post("/api/countries", response_model=schemas.CountryOut)
def create_country(payload: schemas.CountryIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if db.query(models.Country).filter(models.Country.code == payload.code).first():
        raise HTTPException(400, f"country code {payload.code} already exists")
    c = models.Country(**payload.model_dump(), is_active=True, is_template=True)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


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
        joinedload(models.Project.owner),
        joinedload(models.Project.locations),
    ).order_by(models.Project.created_at.desc()).all()


@app.get("/api/projects/{project_id}", response_model=schemas.ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    return _get_owned_project(db, project_id, user, options=[
        joinedload(models.Project.country),
        joinedload(models.Project.owner),
        joinedload(models.Project.locations),
    ])


@app.post("/api/projects", response_model=schemas.ProjectOut)
def create_project(payload: schemas.ProjectIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    p = models.Project(**payload.model_dump(), owner_id=user.id)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@app.put("/api/projects/{project_id}", response_model=schemas.ProjectOut)
def update_project(project_id: int, payload: schemas.ProjectIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    p = _get_owned_project(db, project_id, user)
    for k, v in payload.model_dump().items():
        setattr(p, k, v)
    db.commit()
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


def _recompute_all_lines(db: Session, project: models.Project):
    for line in project.estimate_lines:
        service.recompute_estimate_line(db, line)


# ---------------------------------------------------------------- estimate lines
@app.get("/api/projects/{project_id}/estimate-lines", response_model=List[schemas.EstimateLineOut])
def list_estimate_lines(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    project = _get_owned_project(db, project_id, user)
    # Always recompute before returning so edits to country rates / BOM /
    # coverage made after the line was created are reflected immediately --
    # estimate lines are a live view over current master data, not a
    # point-in-time snapshot.
    _recompute_all_lines(db, project)
    db.commit()
    return db.query(models.EstimateLine).options(
        joinedload(models.EstimateLine.product),
        joinedload(models.EstimateLine.components).joinedload(models.EstimateLineComponent.support_item),
    ).filter(models.EstimateLine.project_id == project_id).all()


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


@app.put("/api/estimate-lines/{line_id}", response_model=schemas.EstimateLineOut)
def update_estimate_line(line_id: int, payload: schemas.EstimateLineIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    line = _get_owned_line(db, line_id, user)
    for k, v in payload.model_dump().items():
        setattr(line, k, v)
    db.flush()
    service.recompute_estimate_line(db, line)
    db.commit()
    db.refresh(line)
    return line


@app.delete("/api/estimate-lines/{line_id}")
def delete_estimate_line(line_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    line = _get_owned_line(db, line_id, user)
    db.delete(line)
    db.commit()
    return {"ok": True}


@app.get("/api/projects/{project_id}/summary")
def project_summary(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    project = _get_owned_project(db, project_id, user, options=[
        joinedload(models.Project.estimate_lines).joinedload(models.EstimateLine.product),
    ])
    _recompute_all_lines(db, project)
    db.commit()
    return service.project_summary(db, project)


@app.get("/api/projects/{project_id}/product-costs", response_model=dict[int, schemas.ProductCostOut])
def project_product_costs(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    """Per-unit material/labor cost for every active product, computed for
    this project's country + duration. Read-only -- lets the frontend price
    line items locally while editing (see ProjectDetail.jsx) without an API
    round trip per keystroke, and without duplicating the costing formulas
    in JS. Reuses calc.py exactly as recompute_estimate_line does."""
    project = _get_owned_project(db, project_id, user)
    price_lookup = calc.price_lookup_factory(db, project.country_id)
    products = db.query(models.WetworksProduct).options(
        joinedload(models.WetworksProduct.bom_lines),
        joinedload(models.WetworksProduct.coverage_rate),
    ).filter(models.WetworksProduct.active == True).all()
    result = {}
    for p in products:
        material = calc.compute_material_cost(p.bom_lines, price_lookup)
        labor = calc.compute_labor_cost(p.coverage_rate, project.country, project.duration_months)
        result[p.id] = schemas.ProductCostOut(
            material_cost_per_unit=material.cost_per_unit,
            labor_cost_per_unit=labor.cost_per_unit,
            needs_setup=p.needs_setup,
        )
    return result


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


def _load_project_for_export(db: Session, project_id: int, user: models.User) -> models.Project:
    project = _get_owned_project(db, project_id, user, options=[
        joinedload(models.Project.estimate_lines).joinedload(models.EstimateLine.product),
        joinedload(models.Project.estimate_lines).joinedload(models.EstimateLine.location),
        joinedload(models.Project.estimate_lines).joinedload(models.EstimateLine.components).joinedload(
            models.EstimateLineComponent.support_item),
    ])
    _recompute_all_lines(db, project)
    db.commit()
    return project


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
