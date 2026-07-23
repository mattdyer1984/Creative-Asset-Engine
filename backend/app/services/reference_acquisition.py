"""
Reference Acquisition — Phase 9.2 of Product Lock v2 (see
MIGRATION_PLAN.md's "ADR: Canonical Product Reference" §4).

Not a new pipeline - a query. Every real acquisition mechanism already
exists and is unchanged by this ADR: `_try_download_and_save_reference_image`
(Phase 5.1, Priority 1 - official source URLs) and
`SlideProductIsolationStage` (Phase 2.4a, Priority 4 - slideshow crops)
both already write `ProductReferenceImage` rows today. This module is
just the "give me every current candidate for this product, regardless
of how it got here" read the Reference Scoring Stage needs to do its
job - Priority 3 (user upload) is deliberately excluded from what this
function returns being "new" (the rows it acquires will show up here
automatically once that upload path exists, Phase 9.6 - no change
needed to this function when that lands).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.product_reference_image import ProductReferenceImage


def get_candidate_reference_images(db: Session, product_id: str) -> list[ProductReferenceImage]:
    """Every current ProductReferenceImage row for a product - the full candidate pool for scoring."""
    return list(
        db.scalars(
            select(ProductReferenceImage).where(
                ProductReferenceImage.product_id == product_id,
                ProductReferenceImage.is_current.is_(True),
            )
        )
    )


def get_unscored_candidates(db: Session, product_id: str) -> list[ProductReferenceImage]:
    """
    The subset Reference Scoring should actually spend a Tier 2 vision
    call on: candidates with no library_status yet. Already-"included"/
    "rejected"/"superseded" rows are never rescored just because
    acquisition ran again (ADR §4, "Reuse existing Library").
    """
    return [
        image
        for image in get_candidate_reference_images(db, product_id)
        if image.library_status is None
    ]
