"""
Products API (plan §7 - Product is canonical, reusable across creatives).

M3 added create/list/get. M4 adds read-only views onto the two Analysis
Artifacts a Product owns (ProductReferenceImage, ProductLockProfile) -
enough to verify the Product Isolation and Product Lock Profile Stages
worked, ahead of the proper assembled Blueprint view in M7.
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.product import Product
from app.models.product_lock_profile import ProductLockProfile
from app.models.product_reference_image import ProductReferenceImage
from app.models.project import Project
from app.schemas import (
    ProductCreate,
    ProductLockProfileRead,
    ProductRead,
    ProductReferenceImageRead,
)

router = APIRouter(prefix="/api/products", tags=["products"])


@router.post("", response_model=ProductRead, status_code=201)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)) -> Product:
    if payload.project_id is not None and db.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    product = Product(display_name=payload.display_name, project_id=payload.project_id)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get("", response_model=list[ProductRead])
def list_products(project_id: str | None = None, db: Session = Depends(get_db)) -> list[Product]:
    stmt = select(Product).order_by(Product.created_at.desc())
    if project_id is not None:
        stmt = stmt.where(Product.project_id == project_id)
    return list(db.scalars(stmt))


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: str, db: Session = Depends(get_db)) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("/{product_id}/reference-images", response_model=list[ProductReferenceImageRead])
def list_current_reference_images(
    product_id: str, db: Session = Depends(get_db)
) -> list[ProductReferenceImage]:
    if db.get(Product, product_id) is None:
        raise HTTPException(status_code=404, detail="Product not found")

    stmt = select(ProductReferenceImage).where(
        ProductReferenceImage.product_id == product_id,
        ProductReferenceImage.is_current.is_(True),
    )
    return list(db.scalars(stmt))


@router.get("/{product_id}/reference-images/{reference_image_id}/file")
def get_reference_image_file(
    product_id: str, reference_image_id: str, db: Session = Depends(get_db)
) -> FileResponse:
    image = db.get(ProductReferenceImage, reference_image_id)
    if image is None or image.product_id != product_id:
        raise HTTPException(status_code=404, detail="Reference image not found")
    return FileResponse(image.file_path)


@router.get("/{product_id}/lock-profile", response_model=ProductLockProfileRead)
def get_current_lock_profile(product_id: str, db: Session = Depends(get_db)) -> ProductLockProfileRead:
    if db.get(Product, product_id) is None:
        raise HTTPException(status_code=404, detail="Product not found")

    stmt = select(ProductLockProfile).where(
        ProductLockProfile.product_id == product_id,
        ProductLockProfile.is_current.is_(True),
    )
    profile = db.scalars(stmt).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="No Product Lock Profile generated yet")

    return ProductLockProfileRead(
        id=profile.id,
        schema_version=profile.schema_version,
        is_current=profile.is_current,
        structured=json.loads(profile.structured_json),
        reference_image_ids=json.loads(profile.reference_image_ids_json),
        created_at=profile.created_at,
    )
