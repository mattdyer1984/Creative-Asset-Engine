"""
One-time backfill: Slideshow/Slide/ProductAppearance from existing
Creative/CreativeBlueprint/Product.product_id data (Phase 2.2 of the
Slideshow/Slide migration roadmap).

Idempotent: Slideshow.id reuses Creative.id verbatim, so re-running this
against a DB where some Creatives were already backfilled simply skips
them (checked by primary key) rather than creating duplicates - this is
what lets the Alembic migration that calls this be re-run safely if
anything created a Creative between backfill and cutover.

Does not touch Creative/CreativeBlueprint - purely additive. The old
tables remain the live, authoritative source of truth until Phase 2.7.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.creative import Creative
from app.models.product_appearance import ProductAppearance
from app.models.slide import Slide
from app.models.slideshow import Slideshow


@dataclass
class BackfillStats:
    slideshows_created: int = 0
    slides_created: int = 0
    product_appearances_created: int = 0
    skipped_already_backfilled: int = 0


def backfill_slideshows(db: Session) -> BackfillStats:
    stats = BackfillStats()

    for creative in db.query(Creative).all():
        if db.get(Slideshow, creative.id) is not None:
            stats.skipped_already_backfilled += 1
            continue

        blueprint = creative.blueprint

        slideshow = Slideshow(
            id=creative.id,
            project_id=creative.project_id,
            imported_at=creative.imported_at,
            status=blueprint.status,
            current_marketing_analysis_id=blueprint.current_marketing_analysis_id,
            current_recreation_prompt_id=blueprint.current_recreation_prompt_id,
            last_failed_stage=blueprint.last_failed_stage,
            last_failed_stage_error=blueprint.last_failed_stage_error,
            source_references_json=blueprint.source_references_json,
            future_generated_assets_json=blueprint.future_generated_assets_json,
            created_at=blueprint.created_at,
            updated_at=blueprint.updated_at,
        )
        db.add(slideshow)
        db.flush()
        stats.slideshows_created += 1

        slide = Slide(
            slideshow_id=slideshow.id,
            slide_index=0,
            stored_file_path=creative.stored_file_path,
            original_filename=creative.original_filename,
            source_type=creative.source_type,
            source_locator=creative.source_locator,
            raw_metadata_json=creative.raw_metadata_json,
            current_ocr_result_id=blueprint.current_ocr_result_id,
            current_creative_fingerprint_id=blueprint.current_creative_fingerprint_id,
        )
        db.add(slide)
        db.flush()
        stats.slides_created += 1

        # A ProductAppearance is only created if a product was assigned -
        # this was a user assertion, not a detection, hence prominence
        # "primary", confidence 1.0, and no bounding box (see
        # ProductAppearance's module docstring).
        if creative.product_id is not None:
            appearance = ProductAppearance(
                slide_id=slide.id,
                product_id=creative.product_id,
                prominence="primary",
                confidence=1.0,
                is_current=True,
            )
            db.add(appearance)
            stats.product_appearances_created += 1

    db.commit()
    return stats
