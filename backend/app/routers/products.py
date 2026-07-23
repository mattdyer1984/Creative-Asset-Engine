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

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
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
    LibraryStatusUpdateRequest,
    ProductCreate,
    ProductLockProfileRead,
    ProductRead,
    ProductReferenceImageRead,
    ProductSourceImportRead,
    ProductSourceImportRequest,
)
from app.services.background_execution import run_reference_scoring_in_background
from app.services.product_profile import ProductProfile, assemble_product_profile
from app.services.product_source_import import import_product_source
from app.storage import save_product_reference_image

router = APIRouter(prefix="/api/products", tags=["products"])

# Phase 9.6 of Product Lock v2 (see MIGRATION_PLAN.md's ADR §4) - the
# real, closed set library_status may hold. The Pydantic layer keeps the
# field a plain string (matching the model's own open-vocabulary
# design), so this is where the actual constraint lives - a manual
# override should never be able to write a value the Reference Scoring
# Stage itself would never produce.
VALID_LIBRARY_STATUSES = {"included", "rejected", "superseded"}
ISOLATION_METHOD_USER_UPLOAD = "user_upload"


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


@router.get("/{product_id}/reference-library", response_model=list[ProductReferenceImageRead])
def get_reference_library(product_id: str, db: Session = Depends(get_db)) -> list[ProductReferenceImage]:
    """
    Phase 9.1/9.2 of Product Lock v2 (see MIGRATION_PLAN.md's "ADR:
    Canonical Product Reference" §3/§8). The Canonical Reference Library
    is not a new table - it's this query: every current
    ProductReferenceImage with library_status="included". A plain list,
    not a single artifact, since there is no "the" Library version to
    fetch by id.
    """
    if db.get(Product, product_id) is None:
        raise HTTPException(status_code=404, detail="Product not found")

    stmt = select(ProductReferenceImage).where(
        ProductReferenceImage.product_id == product_id,
        ProductReferenceImage.is_current.is_(True),
        ProductReferenceImage.library_status == "included",
    )
    return list(db.scalars(stmt))


@router.post("/{product_id}/score-references", status_code=202)
def score_references(
    product_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> dict:
    """
    Phase 9.2 of Product Lock v2 (see MIGRATION_PLAN.md's ADR §4/§8).
    Explicitly triggers the Reference Scoring Stage in the background -
    real, paid vision calls per unscored candidate, same reasoning
    Phase 8.3/8.4 kept image generation/validation out of the automatic
    pipeline. No atomic status-claim guard here (unlike
    POST .../analyze) - Product has no status field to claim against;
    a concurrent double-trigger would at worst repeat a vision call on
    a candidate the first run hasn't finished scoring yet, not corrupt
    state, since scoring writes are idempotent per-candidate.
    """
    if db.get(Product, product_id) is None:
        raise HTTPException(status_code=404, detail="Product not found")

    background_tasks.add_task(run_reference_scoring_in_background, product_id)
    return {"status": "scheduled"}


@router.post(
    "/{product_id}/reference-images/upload",
    response_model=ProductReferenceImageRead,
    status_code=201,
)
async def upload_reference_image(
    product_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)
) -> ProductReferenceImage:
    """
    Phase 9.6 of Product Lock v2 (see MIGRATION_PLAN.md's ADR §4/§8,
    "Priority 3" in the acquisition-source list). A directly
    user-supplied reference image - unlike every other
    ProductReferenceImage source (Product Isolation crops, Product
    Source URL imports), there is no upstream Stage/import to trigger;
    this endpoint IS the acquisition step. Created as an ordinary,
    unscored candidate (library_status left null) - it enters the
    Library the same way every other candidate does, via the Reference
    Scoring Stage, not by being auto-included on upload.
    """
    if db.get(Product, product_id) is None:
        raise HTTPException(status_code=404, detail="Product not found")

    content = await file.read()

    image = ProductReferenceImage(
        product_id=product_id,
        analysis_run_id=None,
        isolation_method=ISOLATION_METHOD_USER_UPLOAD,
        file_path="",  # placeholder, set below once the row has an id
    )
    db.add(image)
    db.flush()

    stored_path = save_product_reference_image(product_id, image.id, content)
    image.file_path = str(stored_path)

    db.commit()
    db.refresh(image)
    return image


@router.post(
    "/{product_id}/reference-images/{reference_image_id}/library-status",
    response_model=ProductReferenceImageRead,
)
def update_library_status(
    product_id: str, reference_image_id: str, payload: LibraryStatusUpdateRequest, db: Session = Depends(get_db)
) -> ProductReferenceImage:
    """
    Phase 9.6 of Product Lock v2 (see MIGRATION_PLAN.md's ADR §4/§8) -
    the human-in-the-loop override the ADR's Replaced/superseded section
    requires: lets a user manually include/reject/supersede an image
    rather than trusting the automatic score, and is also how a user
    confirms a non-blocking upgrade prompt (§9) - "supersede the old
    one" is exactly a manual library-status write on the old image.
    """
    if payload.status not in VALID_LIBRARY_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of {sorted(VALID_LIBRARY_STATUSES)}",
        )

    image = db.get(ProductReferenceImage, reference_image_id)
    if image is None or image.product_id != product_id:
        raise HTTPException(status_code=404, detail="Reference image not found")

    image.library_status = payload.status
    db.commit()
    db.refresh(image)
    return image


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
