"""
Project<->Product membership - Phase 10.5 of AI Creative Engine vNext
(see MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §3). A
ProjectProduct row is created the moment a Product is actually linked to
a Slide belonging to a Project-scoped Slideshow (app.routers.slideshows'
assign_product/add_slide_product endpoints) - never earlier, since that
link is the first point a Product's identity is genuinely confirmed for
this Project's work, not a guess. This mirrors the existing "resolution
is never automatic except when a human has already chosen the target"
rule (Listing resolution) - here the human already chose the target by
calling assign-product/add-slide-product at all, so recording that
choice's Project membership is a safe, automatic side effect, not a new
resolution decision.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project_product import ProjectProduct


def ensure_project_product_membership(db: Session, project_id: str | None, product_id: str) -> None:
    """
    Idempotent: does nothing if project_id is None (an unscoped
    Slideshow has no Project to record membership against) or if this
    exact membership already exists. Flushes, doesn't commit - the
    caller owns the transaction, same convention as every other
    _persist_*/ensure_* helper in this codebase.
    """
    if project_id is None:
        return

    already_member = db.scalars(
        select(ProjectProduct).where(
            ProjectProduct.project_id == project_id,
            ProjectProduct.product_id == product_id,
        )
    ).first()
    if already_member is not None:
        return

    db.add(ProjectProduct(project_id=project_id, product_id=product_id))
    db.flush()
