"""
Reference Scoring backfill — Phase 9.7 of Product Lock v2 (see
MIGRATION_PLAN.md's "ADR: Canonical Product Reference" §11/§12).

Not wired into any automatic flow or API endpoint - the ADR explicitly
flags this as "an open, real-money decision... flagged for the user's
own call," and the user's own 2026-07-23 decision was "build a
backfill script but don't run it yet." This is deliberately a
standalone service function invoked only by
scripts/backfill_reference_scoring.py, never something a stray request
or background task could trigger.

Reuses run_reference_scoring (Phase 9.2/9.6) unchanged - a product
reached via this backfill behaves identically to one scored through
the ordinary POST .../score-references endpoint. dry_run mode reports
what WOULD be scored (unscored candidate counts, a proxy for real
cost) without spending a single vision call - the concrete tool for
making that real-money decision an informed one before it's ever
actually run.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.product import Product
from app.services.reference_acquisition import get_unscored_candidates
from app.services.reference_scoring_stage import run_reference_scoring


@dataclass
class ProductBackfillResult:
    product_id: str
    display_name: str
    candidate_count: int
    # None in dry-run mode - nothing was actually attempted, so there
    # is no real success/failure to report yet, only a candidate count.
    succeeded: bool | None
    error: str | None = None


def backfill_all_products(
    db: Session, *, dry_run: bool = False, product_ids: list[str] | None = None
) -> list[ProductBackfillResult]:
    """
    Runs Reference Scoring over every current Product's unscored
    candidates (or just `product_ids`, if given). Each product commits
    independently - one product's failure never rolls back or blocks
    any other product's progress, the same "no partial write on
    failure" discipline run_reference_scoring itself already keeps at
    the per-image level. Products with nothing unscored are silently
    skipped - not reported, since there is nothing to decide about them.
    """
    stmt = select(Product)
    if product_ids is not None:
        stmt = stmt.where(Product.id.in_(product_ids))
    products = list(db.scalars(stmt))

    results: list[ProductBackfillResult] = []

    for product in products:
        candidates = get_unscored_candidates(db, product.id)
        if not candidates:
            continue

        if dry_run:
            results.append(
                ProductBackfillResult(
                    product_id=product.id,
                    display_name=product.display_name,
                    candidate_count=len(candidates),
                    succeeded=None,
                )
            )
            continue

        stage_result = run_reference_scoring(db, product.id)
        if stage_result.succeeded:
            db.commit()
        else:
            db.rollback()

        results.append(
            ProductBackfillResult(
                product_id=product.id,
                display_name=product.display_name,
                candidate_count=len(candidates),
                succeeded=stage_result.succeeded,
                error=stage_result.error,
            )
        )

    return results
