"""
Standalone script — Phase 9.7 of Product Lock v2 (see
MIGRATION_PLAN.md's "ADR: Canonical Product Reference" §11/§12).

Built per the user's explicit 2026-07-23 decision: "build a backfill
script but don't run it yet." Retroactively running the Reference
Scoring Stage's real, paid Tier-2 vision calls across every existing
product's already-stored reference images is a real-money decision the
ADR itself says must be the user's own call - so this is deliberately
NOT wired into any API endpoint or automatic flow. It only runs when
someone invokes it directly, on purpose.

Usage (from backend/, with the venv active):
    python -m scripts.backfill_reference_scoring --dry-run
        Reports how many unscored candidates each product has, and
        does not spend a single real vision call - the tool for
        estimating real cost before deciding to actually run this.

    python -m scripts.backfill_reference_scoring
        Runs Reference Scoring for real across every current product
        with unscored candidates.

    python -m scripts.backfill_reference_scoring --product-id <id>
        Scopes either mode above to one product, for a smaller/test run
        before committing to scoring everything.
"""

import argparse

from app.db import SessionLocal
from app.services.reference_scoring_backfill import backfill_all_products


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report unscored candidate counts per product without spending any real vision calls.",
    )
    parser.add_argument(
        "--product-id",
        help="Scope to a single product instead of every current product.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        product_ids = [args.product_id] if args.product_id else None
        results = backfill_all_products(db, dry_run=args.dry_run, product_ids=product_ids)
    finally:
        db.close()

    if not results:
        print("No products with unscored candidates found - nothing to do.")
        return

    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"Reference Scoring backfill ({mode}) - {len(results)} product(s) with unscored candidates:\n")
    for result in results:
        if args.dry_run:
            print(f"  {result.display_name} ({result.product_id}): {result.candidate_count} unscored candidate(s)")
        elif result.succeeded:
            print(
                f"  {result.display_name} ({result.product_id}): scored "
                f"{result.candidate_count} candidate(s) - succeeded"
            )
        else:
            print(f"  {result.display_name} ({result.product_id}): FAILED - {result.error}")

    if args.dry_run:
        total = sum(r.candidate_count for r in results)
        print(f"\n{total} total unscored candidate(s) across {len(results)} product(s) would be scored.")
        print("Re-run without --dry-run to actually spend the real vision calls.")


if __name__ == "__main__":
    main()
