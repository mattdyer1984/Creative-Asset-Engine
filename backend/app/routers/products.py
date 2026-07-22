"""
Products API (plan §7 - Product is canonical, reusable across creatives).

M3 added create/list/get. M4 adds read-only views onto the two Analysis
Artifacts a Product owns (ProductReferenceImage, ProductLockProfile) -
enough to verify the Product Isolation and Product Lock Profile Stages
worked, ahead of the proper assembled Blueprint view in M7.

Phase 5.6 of Product Intelligence (see MIGRATION_PLAN.md) adds
source-import (submit a URL, get evidence) and profile (the assembled,
canonical, multi-source view) - the API surface for everything Phase
5.1-5.5 built.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.product import Product
from app.models.product_lock_profile import ProductLockProfile
from app.models.product_reference_image import ProductReferenceImage
from app.models.product_source_import import ProductSourceImport
from app.models.project import Project
from app.schemas import (
    ProductCreate,
    ProductLockProfileRead,
    ProductRead,
    ProductReferenceImageRead,
    ProductSourceImportRead,
    ProductSourceImportRequest,
)
from app.services.product_profile import ProductProfile, assemble_product_profile
from app.services.product_source_import import import_product_source

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
        structured=profile.structured_json,
        reference_image_ids=profile.reference_image_ids_json,
        created_at=profile.created_at,
    )


@router.post("/{product_id}/source-import", response_model=ProductSourceImportRead)
def create_source_import(
    product_id: str, payload: ProductSourceImportRequest, db: Session = Depends(get_db)
) -> ProductSourceImport:
    """
    Submits a Product Source URL - the adapter is resolved automatically
    from the URL itself (Phase 5.2's registry), the caller never picks a
    platform. Runs synchronously: a single fetch+parse is a different
    operation shape than Phase 3's multi-provider AI pipelines, not the
    same "always background it" case (see MIGRATION_PLAN.md's Phase 5.6).
    Returns 200, not 202 - unlike /analyze, the work described by this
    request really is done by the time the response is sent.
    """
    if db.get(Product, product_id) is None:
        raise HTTPException(status_code=404, detail="Product not found")

    return import_product_source(db, product_id, payload.url)


@router.get("/{product_id}/profile", response_model=ProductProfile)
def get_product_profile(product_id: str, db: Session = Depends(get_db)) -> ProductProfile:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    return assemble_product_profile(db, product)
