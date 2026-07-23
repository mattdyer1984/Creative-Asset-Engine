"""
Projects API.

M0 scope: create and list Projects only — enough for the empty/populated
Project list screen. Rename/delete and the Project detail view (Creatives,
Import, etc.) arrive in M1 alongside the Import Provider architecture.

GET .../products (Phase 10.5, AI Creative Engine vNext, see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §3) is the read side
of ProjectProduct - the only way to actually observe which Products a
Project's work has come to involve, populated automatically by
app.services.project_product.ensure_project_product_membership whenever
a Product gets linked to one of the Project's Slides.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.product import Product
from app.models.project import Project
from app.models.project_product import ProjectProduct
from app.schemas import ProductRead, ProjectCreate, ProjectRead

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)) -> list[Project]:
    return list(db.scalars(select(Project).order_by(Project.created_at.desc())))


@router.post("", response_model=ProjectRead, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> Project:
    project = Project(name=payload.name, notes=payload.notes)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: str, db: Session = Depends(get_db)) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}/products", response_model=list[ProductRead])
def list_project_products(project_id: str, db: Session = Depends(get_db)) -> list[Product]:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return list(
        db.scalars(
            select(Product)
            .join(ProjectProduct, ProjectProduct.product_id == Product.id)
            .where(ProjectProduct.project_id == project_id)
            .order_by(Product.created_at.desc())
        )
    )
