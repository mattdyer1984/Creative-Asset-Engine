"""
Listings API - Phase 5.11 of the catalogue layer (see MIGRATION_PLAN.md's
frozen catalogue ADR). The new, unknown-URL entry point: unlike
/api/products/{id}/source-import (Phase 5.6), the caller here does not
already know which Product/Bundle a URL represents - that resolution
happens via the resolve-* endpoints below, always as an explicit,
separate human action (per the ADR's identity section: resolution is
never automatic).

404 vs. 400 convention used throughout: 404 when the path parameter
itself (listing_id) doesn't resolve to a real row - checked directly in
the router, same pattern as every other router in this codebase. 400 for
every other domain violation (unknown product/bundle id, already
resolved, malformed member resolution) - those are app.services.
listing_import's ValueErrors, caught and translated here.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.listing import Listing
from app.schemas import (
    ListingDetailRead,
    ListingRead,
    ListingResolveExistingBundleRequest,
    ListingResolveExistingProductRequest,
    ListingResolveNewBundleRequest,
    ListingResolveNewProductRequest,
    ListingSourceImportRequest,
    PendingBundleMemberHintRead,
)
from app.services.listing_import import (
    BundleMemberResolution,
    get_pending_bundle_title,
    get_pending_member_hints,
    get_pending_product_title,
    import_listing,
    resolve_listing_to_existing_bundle,
    resolve_listing_to_existing_product,
    resolve_listing_to_new_bundle,
    resolve_listing_to_new_product,
)

router = APIRouter(prefix="/api/listings", tags=["listings"])


@router.post("/source-import", response_model=ListingRead)
def create_listing_source_import(payload: ListingSourceImportRequest, db: Session = Depends(get_db)) -> Listing:
    """
    Runs synchronously - same reasoning as the existing per-product
    source-import endpoint (Phase 5.6): a single fetch+parse is done by
    the time the response is sent, not a backgrounded pipeline.
    """
    return import_listing(db, payload.url)


@router.get("/{listing_id}", response_model=ListingDetailRead)
def get_listing(listing_id: str, db: Session = Depends(get_db)) -> ListingDetailRead:
    listing = db.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")

    hints = get_pending_member_hints(db, listing_id)
    return ListingDetailRead(
        **ListingRead.model_validate(listing).model_dump(),
        pending_bundle_hints=[PendingBundleMemberHintRead(**hint) for hint in hints],
        pending_bundle_title=get_pending_bundle_title(db, listing_id),
        pending_product_title=get_pending_product_title(db, listing_id),
    )


@router.post("/{listing_id}/resolve-existing-product", response_model=ListingRead)
def resolve_existing_product(
    listing_id: str, payload: ListingResolveExistingProductRequest, db: Session = Depends(get_db)
) -> Listing:
    if db.get(Listing, listing_id) is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    try:
        return resolve_listing_to_existing_product(db, listing_id, payload.product_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{listing_id}/resolve-new-product", response_model=ListingRead)
def resolve_new_product(
    listing_id: str, payload: ListingResolveNewProductRequest, db: Session = Depends(get_db)
) -> Listing:
    if db.get(Listing, listing_id) is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    try:
        return resolve_listing_to_new_product(db, listing_id, payload.display_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{listing_id}/resolve-existing-bundle", response_model=ListingRead)
def resolve_existing_bundle(
    listing_id: str, payload: ListingResolveExistingBundleRequest, db: Session = Depends(get_db)
) -> Listing:
    if db.get(Listing, listing_id) is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    try:
        return resolve_listing_to_existing_bundle(db, listing_id, payload.bundle_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{listing_id}/resolve-new-bundle", response_model=ListingRead)
def resolve_new_bundle(
    listing_id: str, payload: ListingResolveNewBundleRequest, db: Session = Depends(get_db)
) -> Listing:
    if db.get(Listing, listing_id) is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    try:
        member_resolutions = [
            BundleMemberResolution(
                existing_product_id=member.existing_product_id,
                new_product_display_name=member.new_product_display_name,
                quantity=member.quantity,
            )
            for member in payload.members
        ]
        return resolve_listing_to_new_bundle(db, listing_id, payload.display_name, member_resolutions)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
