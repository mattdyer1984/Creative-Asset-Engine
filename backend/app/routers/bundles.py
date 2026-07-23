"""
Bundles API - Phase 5.11 of the catalogue layer (see MIGRATION_PLAN.md's
frozen catalogue ADR). Read-only: bundles are created via
/api/listings/{id}/resolve-new-bundle, not directly here - this router's
only job is the Bundle View (GET /api/bundles/{id}), assembled from
member ProductProfiles, per the ADR's Bundle philosophy: a bundle's
"profile" is a list of its members' real, unmodified atomic profiles -
never a new merge/vocabulary of its own. Calls the existing, unmodified
Phase 5.5 assemble_product_profile once per member - no new merge logic
exists anywhere in this router.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.product import Product
from app.models.product_bundle import ProductBundle
from app.models.product_bundle_member import ProductBundleMember
from app.schemas import BundleMemberProfileRead, BundleViewRead
from app.services.product_profile import assemble_product_profile

router = APIRouter(prefix="/api/bundles", tags=["bundles"])


@router.get("/{bundle_id}", response_model=BundleViewRead)
def get_bundle_view(bundle_id: str, db: Session = Depends(get_db)) -> BundleViewRead:
    bundle = db.get(ProductBundle, bundle_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Bundle not found")

    members = list(
        db.query(ProductBundleMember).filter(ProductBundleMember.bundle_id == bundle_id)
    )
    member_views = []
    for member in members:
        product = db.get(Product, member.product_id)
        if product is None:
            continue  # defensive - FK integrity should make this unreachable
        member_views.append(
            BundleMemberProfileRead(
                product_id=product.id,
                quantity=member.quantity,
                profile=assemble_product_profile(db, product),
            )
        )

    return BundleViewRead(id=bundle.id, display_name=bundle.display_name, members=member_views)
